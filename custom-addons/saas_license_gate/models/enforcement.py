# License-gate enforcement on write-heavy models.
#
# Reads the current license verdict from saas.license.gate (cached in
# ir.config_parameter, refreshed by the hourly cron) and blocks writes
# according to the Phase 4.1 design:
#
#   verdict          account.move    sale.order    stock.picking
#   ─────────────────────────────────────────────────────────────
#   active           write           write         write
#   grace            write           READ-ONLY     READ-ONLY     ← DIAN escape hatch
#   expired/revoked  READ-ONLY       READ-ONLY     READ-ONLY
#   stale (>14d)     READ-ONLY       READ-ONLY     READ-ONLY
#   bad-signature    READ-ONLY       READ-ONLY     READ-ONLY
#   image-mismatch   READ-ONLY       READ-ONLY     READ-ONLY
#   network-failed   write           write         write          ← transient; verdict
#                                                                   stays 'active' or
#                                                                   'grace' until the
#                                                                   14-day stale cliff
#
# The "DIAN escape hatch" exists because Colombian regulators require
# customers to keep posting invoices for the period they paid for, even
# if they let the license lapse — refusing account.move writes during
# the grace window would violate that obligation.
#
# Enforcement is at the create()/write() boundary on the inherited
# models. unlink() is NOT blocked: deletion is operator-style cleanup
# (typically uses sudo() or admin) and blocking it would also block
# Odoo's own automatic cleanup paths (e.g. cancelled draft moves).

from odoo import _, api, models
from odoo.exceptions import UserError


def _gate(env):
    return env['saas.license.gate']


def _human_status(env):
    """Best-effort human-readable verdict; returns 'unknown' if the
    gate model isn't reachable (shouldn't happen in production but
    keeps tests + isolated module loads from crashing)."""
    try:
        status, _payload = _gate(env).current_status()
    except KeyError:
        return 'unknown'
    return status


class _LicenseGuard:
    """Shared mixin behavior. Not a real Odoo mixin — Odoo's model
    metaclass doesn't combine cleanly with abstract bases — but
    expresses the contract for the three subclasses below."""

    # Subclasses set this to True if they're allowed during grace
    # (currently only account.move per the DIAN regulatory requirement).
    _LICENSE_GRACE_WRITABLE = False

    def _check_license_write_allowed(self):
        status = _human_status(self.env)
        if status == 'active':
            return  # always OK
        if status == 'grace' and self._LICENSE_GRACE_WRITABLE:
            return  # DIAN escape hatch: account.move stays writable
        raise UserError(_(
            "License invalid (%(status)s) — writes to %(model)s are "
            "blocked until the license is restored. Contact your Goliatt "
            "operator. Account.move writes remain available during the "
            "grace period to let you close the books for the term you "
            "already paid for."
        ) % {'status': status, 'model': self._description or self._name})


class AccountMoveLicenseGuard(_LicenseGuard, models.Model):
    _inherit = 'account.move'
    _LICENSE_GRACE_WRITABLE = True  # DIAN escape hatch

    @api.model_create_multi
    def create(self, vals_list):
        self._check_license_write_allowed()
        return super().create(vals_list)

    def write(self, vals):
        self._check_license_write_allowed()
        return super().write(vals)


class SaleOrderLicenseGuard(_LicenseGuard, models.Model):
    _inherit = 'sale.order'
    _LICENSE_GRACE_WRITABLE = False  # blocked in grace + below

    @api.model_create_multi
    def create(self, vals_list):
        self._check_license_write_allowed()
        return super().create(vals_list)

    def write(self, vals):
        self._check_license_write_allowed()
        return super().write(vals)


class StockPickingLicenseGuard(_LicenseGuard, models.Model):
    _inherit = 'stock.picking'
    _LICENSE_GRACE_WRITABLE = False  # blocked in grace + below

    @api.model_create_multi
    def create(self, vals_list):
        self._check_license_write_allowed()
        return super().create(vals_list)

    def write(self, vals):
        self._check_license_write_allowed()
        return super().write(vals)

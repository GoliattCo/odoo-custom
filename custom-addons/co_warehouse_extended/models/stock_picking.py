from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    quality_check_notes = fields.Html(
        string='Quality Check Notes',
        help='Notes from quality inspection during goods receipt.',
    )
    quality_check_passed = fields.Boolean(
        string='Quality Check Passed',
        default=True,
    )
    co_invoice_id = fields.Many2one(
        'account.move',
        string='Linked Invoice',
        domain="[('move_type', 'in', ['in_invoice', 'in_refund'])]",
        help='Vendor invoice linked to this receipt.',
        copy=False,
    )
    co_auto_invoice = fields.Boolean(
        string='Auto-Create Invoice',
        help='Automatically create a vendor bill when this receipt is validated.',
    )

    def button_validate(self):
        """Override to auto-create invoice from receipt when flag is set."""
        res = super().button_validate()
        for picking in self:
            if (
                picking.co_auto_invoice
                and picking.picking_type_code == 'incoming'
                and not picking.co_invoice_id
                and picking.purchase_id
            ):
                picking._create_vendor_bill()
        return res

    def _create_vendor_bill(self):
        """Create a vendor bill from the receipt linked to a purchase order."""
        self.ensure_one()
        po = self.purchase_id
        if not po:
            raise UserError(_('No purchase order linked to this receipt.'))

        # Use Odoo's standard PO action to create invoice
        po.action_create_invoice()

        # Link the last created invoice back
        invoices = po.invoice_ids.filtered(lambda m: m.state == 'draft')
        if invoices:
            self.co_invoice_id = invoices[-1].id

    def action_view_invoice(self):
        """Open the linked vendor bill."""
        self.ensure_one()
        if not self.co_invoice_id:
            raise UserError(_('No invoice linked to this receipt.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.co_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    co_purchase_request_id = fields.Many2one(
        'co.purchase.request',
        string='Purchase Request',
        readonly=True,
        copy=False,
    )

    # Supplier payment tracking: show related invoices and payments
    co_payment_state_summary = fields.Text(
        string='Payment Summary',
        compute='_compute_payment_state_summary',
    )

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_residual')
    def _compute_payment_state_summary(self):
        for po in self:
            lines = []
            for inv in po.invoice_ids:
                state_label = dict(
                    inv._fields['payment_state'].selection
                ).get(inv.payment_state, inv.payment_state or '')
                lines.append(
                    '%s: %s (Residual: %s %s)' % (
                        inv.name or _('Draft'),
                        state_label,
                        '{:,.2f}'.format(inv.amount_residual),
                        inv.currency_id.name,
                    )
                )
            po.co_payment_state_summary = '\n'.join(lines) if lines else _('No invoices')

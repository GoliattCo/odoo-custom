# Social Country Club Management — Design Spec

**Date:** 2026-03-12
**Author:** Manuel Caro
**Status:** Draft

---

## Goal

Build a suite of Odoo 18.0 modules for managing a social country club, covering affiliate memberships, billing, golf, equestrian, tennis, and events. All modules available in English and Spanish.

---

## Module Architecture

```
club_core            ← foundation (affiliates, memberships, billing)
├── club_golf        ← depends on club_core
├── club_equestrian  ← depends on club_core
├── club_tennis      ← depends on club_core
└── club_events      ← depends on club_core, website_event, payment
```

All modules live in `custom-addons/` in the `remcaro-rgb/odoo-custom` repo. Each follows standard Odoo 18.0 addon structure.

**Odoo module dependencies:**
- `club_core`: `base`, `mail`, `account`, `portal`
- `club_golf`: `club_core`
- `club_equestrian`: `club_core`
- `club_tennis`: `club_core`
- `club_events`: `club_core`, `event`, `website_event`, `payment`

---

## Prototype Build Phases

| Phase | Modules | Key Deliverables |
|---|---|---|
| 1 | `club_core` | Affiliate registration, membership plans, billing, portal |
| 2 | `club_golf` | Tee times, handicap, scorecards, caddies, carts, bags |
| 3 | `club_equestrian` + `club_tennis` | Stable/horse mgmt, arena/court bookings, rankings |
| 4 | `club_events` | Internal/external events, registration, payments |

Each phase delivers installable module(s) with security groups, demo data, tests, and Spanish translations.

---

## Standard Module Structure (all modules)

```
club_<name>/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── <model>.py (one file per model)
├── views/
│   └── <model>_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── club_security.xml       ← security groups + ir.rule record rules
├── data/
│   └── demo_data.xml
├── i18n/
│   └── es.po
└── tests/
    └── test_<feature>.py
```

---

## Phase 1: `club_core`

### Affiliate Inheritance Strategy

`club.affiliate` uses **delegation inheritance** (`_inherits`):

```python
class ClubAffiliate(models.Model):
    _name = 'club.affiliate'
    _inherits = {'res.partner': 'partner_id'}
    _description = 'Club Affiliate'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    # all res.partner fields transparently available
    # club-specific fields defined below
```

This creates a separate `club_affiliate` table linked to `res.partner` via `partner_id`. Regular partners are unaffected. Affiliates appear in partner lists only if explicitly joined.

### Models

#### `club.affiliate`
| Field | Type | Description |
|---|---|---|
| `partner_id` | Many2one | → `res.partner` (delegation, required) |
| `membership_type` | Selection | individual / family_primary / family_dependent / corporate_admin / corporate_employee |
| `membership_ids` | One2many | → `club.membership` (via `affiliate_id`) |
| `family_group_id` | Many2one | → `club.family.group` (if dependent) |
| `corporate_group_id` | Many2one | → `club.corporate.group` (if employee) |
| `affiliate_number` | Char | Auto-generated unique club ID (sequence) |
| `membership_status` | Computed Char | active / suspended / expired — computed from active `club.membership` |
| `photo` | Binary | Member photo |

#### `club.membership.plan`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Plan name (e.g. "Individual Anual") |
| `fee` | Float | Fee amount |
| `billing_period` | Selection | monthly / annual |
| `grace_period_days` | Integer | Days after expiry before suspension (default: 15) |
| `late_fee_amount` | Float | Late fee charged after grace period (creates a separate invoice) |
| `golf_access` | Boolean | Includes golf access |
| `equestrian_access` | Boolean | Includes equestrian access |
| `tennis_access` | Boolean | Includes tennis access |
| `product_id` | Many2one | → `product.product` (for invoicing) |
| `late_fee_product_id` | Many2one | → `product.product` (for late fee invoicing) |

#### `club.membership`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` |
| `plan_id` | Many2one | → `club.membership.plan` |
| `start_date` | Date | Membership start |
| `end_date` | Date | Computed: `start_date + 1 month` (monthly) or `start_date + 1 year` (annual); stored, recomputed on plan change |
| `status` | Selection | draft / active / suspended / expired / cancelled |
| `invoice_ids` | Many2many | → `account.move` via relation table `club_membership_account_move_rel` |
| `notes` | Text | Staff notes |

> **Billing link:** `invoice_ids` uses a Many2many with a relation table instead of One2many, avoiding the need to extend `account.move` with a back-reference field. Invoices are linked manually on creation via `membership.invoice_ids = [(4, invoice.id)]`.

#### `club.family.group`
| Field | Type | Description |
|---|---|---|
| `primary_member_id` | Many2one | → `club.affiliate` |
| `dependent_ids` | One2many | → `club.affiliate` (via `family_group_id`) |
| `billing_affiliate_id` | Many2one | → `club.affiliate` (receives invoices) |

#### `club.corporate.group`
| Field | Type | Description |
|---|---|---|
| `company_partner_id` | Many2one | → `res.partner` (company) |
| `admin_id` | Many2one | → `club.affiliate` (corporate admin) |
| `employee_ids` | One2many | → `club.affiliate` (via `corporate_group_id`) |
| `max_employees` | Integer | Maximum authorized members |

### Billing Logic

- **Membership activation** (`status` → `active`): create `account.move` invoice using `plan.product_id`; link via `membership.invoice_ids`
- **`end_date` computation:**
  - monthly: `start_date + relativedelta(months=1)`
  - annual: `start_date + relativedelta(years=1)`
  - Stored field, recomputed when `plan_id` or `start_date` changes
- **Renewal cron** (`ir.cron`, daily): memberships expiring within 7 days → generate next period invoice, link to membership
- **Late fee:** After `end_date + grace_period_days` if any linked invoice is unpaid → create a **new separate** `account.move` with `late_fee_product_id`; set membership `status = suspended`. Posted invoices are never modified.
- **On invoice payment** (`account.move` `payment_state = paid` compute triggers): membership cron re-checks status → renews `end_date`, restores `status = active` if suspended

### Security Groups + Record Rules

| Group | Access |
|---|---|
| `club_core.group_club_admin` | Full CRUD on all club models |
| `club_core.group_club_staff` | Read/write affiliates, memberships; no plan/config access |
| `club_core.group_club_member` | Portal: read own affiliate + membership + invoices only |

**Portal record rules** (`ir.rule` domains):
- `club.affiliate`: `[('partner_id', '=', user.partner_id.id)]`
- `club.membership`: `[('affiliate_id.partner_id', '=', user.partner_id.id)]`
- `account.move` (portal): filtered via Odoo's existing portal invoice rule (no custom rule needed)

### Views
- Affiliate kanban + list + form (with membership history tab)
- Membership plan list + form
- Membership list + form with inline linked invoices
- Family group form, Corporate group form
- Dashboard: active members count, expiring this month, suspended count

---

## Phase 2: `club_golf`

### Shared Caddie Base (used by golf and tennis)

To avoid duplication between `club.golf.caddie` and `club.tennis.caddie`, a shared **abstract mixin** is defined in `club_core`:

```python
class ClubCaddyMixin(models.AbstractModel):
    _name = 'club.caddie.mixin'
    _description = 'Caddie/Staff Mixin'

    partner_id = fields.Many2one('res.partner', required=True)
    employee_number = fields.Char()
    # availability handled in concrete models (different sport contexts)
```

`club.golf.caddie` and `club.tennis.caddie` both inherit from this mixin (`_inherit = ['club.caddie.mixin']`) and add sport-specific fields. This provides shared structure without coupling the models.

### Models

#### `club.golf.course`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Course name |
| `holes` | Integer | 9 or 18 |
| `par` | Integer | Course par |
| `slope_rating` | Float | WHS slope rating (used in handicap calc) |
| `course_rating` | Float | WHS course rating (used in handicap calc) |

#### `club.golf.tee.time`
| Field | Type | Description |
|---|---|---|
| `date` | Date | Round date |
| `time_slot` | Float | Start time (e.g. 7.5 = 07:30) |
| `course_id` | Many2one | → `club.golf.course` |
| `affiliate_ids` | Many2many | → `club.affiliate` (max 4, enforced by constraint) |
| `guest_count` | Integer | Non-member guests |
| `caddie_id` | Many2one | → `club.golf.caddie` (optional) |
| `cart_id` | Many2one | → `club.golf.cart` (optional) |
| `bag_ids` | Many2many | → `club.golf.bag` |
| `status` | Selection | available / booked / completed / cancelled |

**Conflict detection:** `@api.constrains('date', 'time_slot', 'course_id')` raises `ValidationError` if another tee time exists for the same course + date + time_slot.

**Caddie conflict:** `@api.constrains('date', 'time_slot', 'caddie_id')` raises `ValidationError` if caddie is already assigned at that date/time.

**Cart conflict:** `@api.constrains('date', 'time_slot', 'cart_id')` raises `ValidationError` for rental carts already assigned; owned carts only block if assigned to another affiliate.

#### `club.golf.caddie` (inherits `club.caddie.mixin`)
| Field | Type | Description |
|---|---|---|
| `availability_ids` | One2many | → `club.golf.caddie.availability` |
| `tee_time_ids` | One2many | → `club.golf.tee.time` (via `caddie_id`) |

#### `club.golf.caddie.availability`
| Field | Type | Description |
|---|---|---|
| `caddie_id` | Many2one | → `club.golf.caddie` |
| `day_of_week` | Selection | 0=Monday … 6=Sunday |
| `time_from` | Float | Available from |
| `time_to` | Float | Available until |

#### `club.golf.cart`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Cart identifier/number |
| `cart_type` | Selection | rental / owned |
| `owner_id` | Many2one | → `club.affiliate` (required if owned) |
| `status` | Selection | available / in_use / maintenance |
| `battery_level` | Integer | % charge (electric carts) |
| `maintenance_log` | Text | Maintenance notes |
| `tee_time_ids` | One2many | → `club.golf.tee.time` (via `cart_id`) |

#### `club.golf.bag`
| Field | Type | Description |
|---|---|---|
| `tag_number` | Char | Bag tag/ID (unique) |
| `owner_id` | Many2one | → `club.affiliate` |
| `locker_number` | Char | Storage locker assignment |
| `status` | Selection | stored / with_member |
| `notes` | Text | Description / special instructions |

#### `club.golf.scorecard`
| Field | Type | Description |
|---|---|---|
| `tee_time_id` | Many2one | → `club.golf.tee.time` |
| `affiliate_id` | Many2one | → `club.affiliate` |
| `course_id` | Many2one | → `club.golf.course` |
| `date` | Date | Round date |
| `line_ids` | One2many | → `club.golf.scorecard.line` (one per hole) |
| `gross_score` | Integer | Computed: sum of `line_ids.score` |
| `course_handicap` | Integer | Computed from affiliate's handicap index + course slope/rating |
| `net_score` | Integer | Computed: `gross_score − course_handicap` |
| `score_differential` | Float | Computed: WHS formula (see below) |

#### `club.golf.scorecard.line`
| Field | Type | Description |
|---|---|---|
| `scorecard_id` | Many2one | → `club.golf.scorecard` |
| `hole_number` | Integer | 1–18 (validated against course.holes) |
| `par` | Integer | Par for this hole |
| `score` | Integer | Strokes taken |

> **Note:** Using `One2many` lines instead of 18 fixed fields supports both 9-hole and 18-hole courses and enables proper reporting.

#### `club.golf.handicap`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` (unique) |
| `handicap_index` | Float | Current WHS handicap index |
| `revision_date` | Date | Date of last recalculation |
| `history_ids` | One2many | → `club.golf.handicap.history` |

#### `club.golf.handicap.history`
| Field | Type | Description |
|---|---|---|
| `handicap_id` | Many2one | → `club.golf.handicap` |
| `date` | Date | Revision date |
| `handicap_index` | Float | Index at this revision |
| `scorecard_ids` | Many2many | Scorecards used in this calculation |

### WHS Handicap Calculation (Simplified)

> **Scope note:** This implementation uses a simplified WHS formula suitable for club use. The Playing Conditions Calculation (PCC) daily adjustment and the Soft Cap / Hard Cap mechanisms are **out of scope** for this prototype.

**Score Differential** (computed on scorecard save):
```
score_differential = (113 / slope_rating) × (gross_score − course_rating)
```

**Handicap Index** (recomputed after each scorecard):
- Requires minimum **3 scorecards** to establish an index
- Use up to the last 20 differentials; take the **lowest N** based on count:
  - 3–6 rounds: lowest 1
  - 7–8 rounds: lowest 2
  - 9–11 rounds: lowest 3
  - 12–14 rounds: lowest 4
  - 15–16 rounds: lowest 5
  - 17–18 rounds: lowest 6
  - 19 rounds: lowest 7
  - 20 rounds: lowest 8
- `handicap_index = average(lowest_N_differentials) × 0.96`
- Rounded to 1 decimal place
- If fewer than 3 scorecards on file: `handicap_index = None` (displayed as "—")

---

## Phase 3a: `club_equestrian`

### Models

#### `club.horse`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Horse name |
| `breed` | Char | Breed |
| `color` | Char | Coat color |
| `birth_date` | Date | Date of birth |
| `owner_id` | Many2one | → `club.affiliate` (must be active) |
| `registration_number` | Char | Club registration number (auto-sequence) |
| `stall_id` | Many2one | → `club.stall` (writable; authoritative source of stall assignment) |
| `photo` | Binary | Horse photo |

#### `club.stall`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Stall number/name |
| `barn_section` | Char | Barn/section label |
| `horse_id` | Many2one | → `club.horse` (computed inverse of `horse.stall_id`; read-only) |
| `status` | Computed Selection | vacant / occupied / maintenance — derived from `horse_id` and maintenance flag |
| `under_maintenance` | Boolean | Manual maintenance flag |
| `notes` | Text | Special instructions |

> **Single source of truth:** `horse.stall_id` is the writable field. `stall.horse_id` is a `@api.depends('horse_id')`-computed inverse — it searches for a horse whose `stall_id = self`. `stall.status` is computed: `occupied` if `horse_id`, `maintenance` if `under_maintenance`, else `vacant`.

#### `club.horse.feeding`
| Field | Type | Description |
|---|---|---|
| `horse_id` | Many2one | → `club.horse` |
| `feed_type` | Char | Feed name/type |
| `quantity` | Float | Amount |
| `unit` | Selection | kg / lbs / flakes |
| `schedule` | Selection | morning / afternoon / evening |
| `responsible_id` | Many2one | → `res.users` (staff) |
| `notes` | Text | Additional instructions |

#### `club.vet.record`
| Field | Type | Description |
|---|---|---|
| `horse_id` | Many2one | → `club.horse` |
| `date` | Date | Visit date |
| `vet_name` | Char | Veterinarian name |
| `procedure` | Text | Procedure / diagnosis |
| `next_visit_date` | Date | Next scheduled visit |
| `attachment_ids` | Many2many | → `ir.attachment` |

#### `club.arena`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Arena name |
| `arena_type` | Selection | dressage / jumping / outdoor / multipurpose |
| `capacity` | Integer | Max riders simultaneously |
| `under_maintenance` | Boolean | Maintenance flag |

#### `club.equestrian.booking`
| Field | Type | Description |
|---|---|---|
| `arena_id` | Many2one | → `club.arena` |
| `affiliate_id` | Many2one | → `club.affiliate` |
| `horse_id` | Many2one | → `club.horse` (owner must match affiliate) |
| `date` | Date | Booking date |
| `time_slot` | Float | Start time |
| `duration` | Float | Hours (max 2, enforced by constraint) |
| `status` | Selection | booked / completed / cancelled |

**Conflict detection:** `@api.constrains` checks for overlapping bookings on same arena + date + time range.

### Business Logic
- Horse owner must be active affiliate (`@api.constrains`)
- Arena conflict: overlapping time range check using `time_slot` + `duration`
- Vet next visit alert: daily cron checks `next_visit_date` within 7 days → `message_post` on horse chatter + email owner via `mail.template`
- Daily feeding sheet: QWeb PDF report grouped by schedule, filtered by date

---

## Phase 3b: `club_tennis`

### Models

#### `club.tennis.court`
| Field | Type | Description |
|---|---|---|
| `name` | Char | Court name/number |
| `surface` | Selection | clay / hard / grass / artificial |
| `indoor` | Boolean | Indoor or outdoor |
| `under_maintenance` | Boolean | Maintenance flag |

#### `club.tennis.booking`
| Field | Type | Description |
|---|---|---|
| `court_id` | Many2one | → `club.tennis.court` |
| `affiliate_ids` | Many2many | → `club.affiliate` (max 4) |
| `date` | Date | Booking date |
| `time_slot` | Float | Start time |
| `duration` | Float | 1 or 2 hours (enforced by constraint) |
| `caddie_id` | Many2one | → `club.tennis.caddie` (optional) |
| `status` | Selection | booked / completed / cancelled |

**Conflict detection:** same court + overlapping time range → `ValidationError`.
**Caddie conflict:** caddie already assigned at same date/time → `ValidationError`.

#### `club.tennis.caddie` (inherits `club.caddie.mixin`)
| Field | Type | Description |
|---|---|---|
| `availability_ids` | One2many | → `club.tennis.caddie.availability` |
| `booking_ids` | One2many | → `club.tennis.booking` (via `caddie_id`) |

#### `club.tennis.caddie.availability`
| Field | Type | Description |
|---|---|---|
| `caddie_id` | Many2one | → `club.tennis.caddie` |
| `day_of_week` | Selection | 0=Monday … 6=Sunday |
| `time_from` | Float | Available from |
| `time_to` | Float | Available until |

#### `club.tennis.match`
| Field | Type | Description |
|---|---|---|
| `booking_id` | Many2one | → `club.tennis.booking` |
| `player_ids` | Many2many | → `club.affiliate` |
| `set_1_score` | Char | e.g. "6-4" |
| `set_2_score` | Char | |
| `set_3_score` | Char | Optional tiebreak set |
| `winner_id` | Many2one | → `club.affiliate` |
| `ranking_points_awarded` | Integer | Points added to winner's ranking |

#### `club.tennis.ranking`
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` (unique per category) |
| `category` | Selection | men / women / junior / senior / mixed |
| `points` | Integer | Total ranking points |
| `rank` | Integer | Computed position within category (sorted desc by points) |
| `matches_played` | Integer | Total matches recorded |
| `matches_won` | Integer | Total wins |

**Ranking update:** on `club.tennis.match` save → update winner's `points += ranking_points_awarded`, `matches_played += 1`, `matches_won += 1`; update loser's `matches_played += 1`. After update, recompute `rank` for all affiliates in the affected category (sorted by `points` descending, rank = position).

---

## Phase 4: `club_events`

### Models

#### `club.event` (extends `event.event` via `_inherit`)
| Field | Type | Description |
|---|---|---|
| `event_scope` | Selection | internal / external |
| `sport_category` | Selection | golf / equestrian / tennis / social / general |
| `member_only` | Boolean | Restrict visibility to active affiliates |
| `member_price` | Float | Ticket price for affiliates |
| `public_price` | Float | Ticket price for external attendees |

#### `club.event.registration` (extends `event.registration` via `_inherit`)
| Field | Type | Description |
|---|---|---|
| `affiliate_id` | Many2one | → `club.affiliate` (auto-linked if registrant is an affiliate) |
| `attendee_type` | Selection | member / guest / public |
| `payment_move_id` | Many2one | → `account.move` (invoice if paid event) |
| `payment_status` | Computed Selection | pending / paid / refunded — computed from `payment_move_id.payment_state` |

> **Payment status sync:** `payment_status` is a `@api.depends('payment_move_id.payment_state')` computed field — it reads directly from the linked invoice's state. No separate write override needed; it stays in sync automatically.

### Business Logic
- Internal events: `member_only = True`; portal filters to active affiliates only via record rule
- External events: public `website_event` registration page; payment via Odoo `payment` acquirer
- Attendee type auto-set: if registrant's `partner_id` matches an active affiliate → `member`, else `public`
- Price auto-applied: `member` → `member_price`, `public` → `public_price`
- Capacity: `seats_availability` (from `event.event`) enforced by Odoo base
- Confirmation email: uses `mail.template` with `lang="{{ object.partner_id.lang }}"` for per-language rendering (Spanish affiliates receive Spanish emails automatically)

---

## Internationalization (all modules)

- All Python model fields, `_sql_constraints`, error messages use Odoo's `_()` lazy translation
- All XML view strings use standard Odoo translatable patterns
- Email templates use `lang="{{ object.partner_id.lang }}"` attribute for per-registrant language rendering — no `.po` extraction needed for template bodies; field labels/menu items extracted via standard `makepot`
- Each module ships `i18n/es.po` covering field labels, menu items, button text, validation messages
- Spanish (`es`) installed as a language in the system; users switch per-profile preference

---

## Security Model (all modules)

| Group | Defined in | Access |
|---|---|---|
| Club Admin | `club_core` | Full CRUD on all club models |
| Club Staff | `club_core` | Read/write affiliates, memberships; no billing config |
| Club Member (portal) | `club_core` | Read own affiliate + membership only |
| Golf Staff | `club_golf` | CRUD on golf models |
| Equestrian Staff | `club_equestrian` | CRUD on equestrian models |
| Tennis Staff | `club_tennis` | CRUD on tennis models |
| Events Staff | `club_events` | CRUD on event models |

**Portal record rules (`ir.rule`):**
| Model | Domain |
|---|---|
| `club.affiliate` | `[('partner_id', '=', user.partner_id.id)]` |
| `club.membership` | `[('affiliate_id.partner_id', '=', user.partner_id.id)]` |
| `club.golf.tee.time` | `[('affiliate_ids.partner_id', 'in', [user.partner_id.id])]` |
| `club.tennis.booking` | `[('affiliate_ids.partner_id', 'in', [user.partner_id.id])]` |
| `club.equestrian.booking` | `[('affiliate_id.partner_id', '=', user.partner_id.id)]` |

---

## Demo Data (all modules)

Each module ships `data/demo_data.xml`:
- `club_core`: 10 individual affiliates, 2 family groups, 1 corporate group, 3 membership plans
- `club_golf`: 1 course (18-hole), 5 tee times, 2 caddies, 4 carts (2 rental/2 owned), 5 bags, 3 scorecards with lines, handicap records
- `club_equestrian`: 3 horses, 6 stalls, 1 arena, 3 bookings, 2 vet records, feeding schedules
- `club_tennis`: 3 courts, 2 caddies, 5 bookings, 3 matches, ranking data
- `club_events`: 2 internal events, 1 external event with registrations

---

## Testing Strategy (all modules)

- Unit tests in `tests/test_<feature>.py` using `odoo.tests.common.TransactionCase`
- All test classes decorated with `@tagged('club', 'post_install', '-at_install')`
- Each module tests:
  - Model constraints (tee time conflicts, stall double-assignment, max affiliates per booking)
  - Business logic (billing cron, `end_date` computation, handicap calculation, ranking update)
  - Access rights (admin vs staff vs portal member — record rule enforcement)
  - Computed fields (membership_status, stall.status, payment_status)
- Run all club tests: `docker compose exec odoo /odoo/odoo-bin test -d odoo --test-tags club`
- Run single module: `--test-tags club_golf`

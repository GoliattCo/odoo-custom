from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('goliatt_pms', 'post_install', '-at_install')
class TestPmsReservation(TransactionCase):
    """Tests for the Goliatt PMS module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.property = cls.env['pms.property'].create({
            'name': 'Test Hotel',
            'code': 'TST01',
            'property_type': 'hotel',
            'star_rating': '4',
            'check_in_time': 15.0,
            'check_out_time': 11.0,
        })
        cls.room_type = cls.env['pms.room.type'].create({
            'name': 'Test Standard',
            'code': 'TSTD',
            'property_id': cls.property.id,
            'max_adults': 2,
            'max_children': 1,
            'bed_type': 'queen',
            'base_rate': 200000,
        })
        cls.room = cls.env['pms.room'].create({
            'name': 'T101',
            'room_type_id': cls.room_type.id,
            'floor': '1',
        })
        cls.room_2 = cls.env['pms.room'].create({
            'name': 'T102',
            'room_type_id': cls.room_type.id,
            'floor': '1',
        })
        cls.guest = cls.env['res.partner'].create({
            'name': 'Test Guest',
            'email': 'test@example.com',
            'is_hotel_guest': True,
        })
        cls.today = date.today()

    def _create_reservation(self, **kwargs):
        vals = {
            'property_id': self.property.id,
            'guest_id': self.guest.id,
            'checkin_date': self.today + timedelta(days=1),
            'checkout_date': self.today + timedelta(days=4),
            'room_type_id': self.room_type.id,
            'room_id': self.room.id,
            'adults': 1,
            'daily_rate': 200000,
        }
        vals.update(kwargs)
        return self.env['pms.reservation'].create(vals)

    # ------------------------------------------------------------------
    # 1. Reservation lifecycle: create -> confirm -> checkin -> checkout
    # ------------------------------------------------------------------
    def test_01_reservation_lifecycle(self):
        res = self._create_reservation()
        self.assertEqual(res.state, 'confirmed')

        # Confirm (idempotent)
        res.action_confirm()
        self.assertEqual(res.state, 'confirmed')

        # Check in
        res.action_checkin()
        self.assertEqual(res.state, 'checked_in')

        # Check out
        res.action_checkout()
        self.assertEqual(res.state, 'checked_out')

    # ------------------------------------------------------------------
    # 2. Check-in sets room status to occupied
    # ------------------------------------------------------------------
    def test_02_checkin_sets_room_occupied(self):
        res = self._create_reservation()
        self.assertEqual(self.room.status, 'available')

        res.action_checkin()
        self.assertEqual(self.room.status, 'occupied')
        self.assertEqual(self.room.housekeeping_status, 'dirty')
        self.assertEqual(self.room.current_reservation_id, res)

    # ------------------------------------------------------------------
    # 3. Check-out sets room available, creates housekeeping task
    # ------------------------------------------------------------------
    def test_03_checkout_room_and_housekeeping(self):
        res = self._create_reservation()
        res.action_checkin()

        hk_count_before = self.env['pms.housekeeping.task'].search_count([
            ('room_id', '=', self.room.id),
        ])

        res.action_checkout()
        self.assertEqual(self.room.status, 'available')
        self.assertEqual(self.room.housekeeping_status, 'dirty')
        self.assertFalse(self.room.current_reservation_id)

        hk_count_after = self.env['pms.housekeeping.task'].search_count([
            ('room_id', '=', self.room.id),
        ])
        self.assertEqual(hk_count_after, hk_count_before + 1)

    # ------------------------------------------------------------------
    # 4. Folio charge/payment balance computed correctly
    # ------------------------------------------------------------------
    def test_04_folio_balance(self):
        res = self._create_reservation()
        folio = self.env['pms.folio'].create({
            'reservation_id': res.id,
        })
        self.env['pms.folio.charge'].create({
            'folio_id': folio.id,
            'description': 'Room charge',
            'quantity': 2,
            'unit_price': 200000,
            'department': 'rooms',
        })
        self.env['pms.folio.charge'].create({
            'folio_id': folio.id,
            'description': 'Minibar',
            'quantity': 1,
            'unit_price': 50000,
            'department': 'minibar',
        })
        self.assertEqual(folio.total_charges, 450000)

        self.env['pms.folio.payment'].create({
            'folio_id': folio.id,
            'amount': 300000,
            'payment_method': 'credit_card',
        })
        self.assertEqual(folio.total_payments, 300000)
        self.assertEqual(folio.balance, 150000)

    # ------------------------------------------------------------------
    # 5. Nights computed correctly
    # ------------------------------------------------------------------
    def test_05_nights_computed(self):
        res = self._create_reservation(
            checkin_date=self.today,
            checkout_date=self.today + timedelta(days=5),
        )
        self.assertEqual(res.nights, 5)

    # ------------------------------------------------------------------
    # 6. Availability computed correctly
    # ------------------------------------------------------------------
    def test_06_availability(self):
        avail = self.env['pms.availability'].create({
            'property_id': self.property.id,
            'room_type_id': self.room_type.id,
            'date': self.today,
            'total_inventory': 10,
            'sold': 3,
            'out_of_order': 1,
        })
        self.assertEqual(avail.available, 6)

    # ------------------------------------------------------------------
    # 7. Night audit computes occupancy stats
    # ------------------------------------------------------------------
    def test_07_night_audit_stats(self):
        # Create a checked-in reservation for today
        res = self._create_reservation(
            checkin_date=self.today,
            checkout_date=self.today + timedelta(days=3),
        )
        res.action_checkin()

        audit = self.env['pms.night.audit'].create({
            'property_id': self.property.id,
            'audit_date': self.today,
        })
        self.assertEqual(audit.rooms_sold, 1)
        self.assertGreater(audit.occupancy_pct, 0)

    # ------------------------------------------------------------------
    # 8. Cancel reservation works
    # ------------------------------------------------------------------
    def test_08_cancel_reservation(self):
        res = self._create_reservation()
        res.action_cancel()
        self.assertEqual(res.state, 'cancelled')
        self.assertTrue(res.cancellation_date)

    # ------------------------------------------------------------------
    # 9. Constraint: checkout > checkin
    # ------------------------------------------------------------------
    def test_09_checkout_after_checkin_constraint(self):
        with self.assertRaises(ValidationError):
            self._create_reservation(
                checkin_date=self.today + timedelta(days=5),
                checkout_date=self.today + timedelta(days=3),
            )

    # ------------------------------------------------------------------
    # 10. Auto-sequence on reservation, folio, HK task
    # ------------------------------------------------------------------
    def test_10_auto_sequences(self):
        res = self._create_reservation()
        self.assertTrue(res.name.startswith('RES-'))

        folio = self.env['pms.folio'].create({
            'reservation_id': res.id,
        })
        self.assertTrue(folio.name.startswith('FOL-'))

        hk = self.env['pms.housekeeping.task'].create({
            'room_id': self.room.id,
            'task_type': 'stayover',
        })
        self.assertTrue(hk.name.startswith('HK-'))

    # ------------------------------------------------------------------
    # Extra: Checkin without room raises error
    # ------------------------------------------------------------------
    def test_11_checkin_without_room_raises(self):
        res = self._create_reservation(room_id=False)
        with self.assertRaises(UserError):
            res.action_checkin()

    # ------------------------------------------------------------------
    # Extra: Cannot cancel checked-in reservation
    # ------------------------------------------------------------------
    def test_12_cannot_cancel_checked_in(self):
        res = self._create_reservation()
        res.action_checkin()
        with self.assertRaises(UserError):
            res.action_cancel()

    # ------------------------------------------------------------------
    # Extra: Housekeeping task lifecycle
    # ------------------------------------------------------------------
    def test_13_housekeeping_lifecycle(self):
        hk = self.env['pms.housekeeping.task'].create({
            'room_id': self.room_2.id,
            'task_type': 'checkout_clean',
        })
        self.assertEqual(hk.state, 'pending')

        hk.action_start()
        self.assertEqual(hk.state, 'in_progress')
        self.assertTrue(hk.start_time)
        self.assertEqual(self.room_2.housekeeping_status, 'cleaning')

        hk.action_complete()
        self.assertEqual(hk.state, 'completed')
        self.assertTrue(hk.end_time)
        self.assertEqual(self.room_2.housekeeping_status, 'clean')

        hk.action_inspect()
        self.assertEqual(hk.state, 'inspected')
        self.assertEqual(self.room_2.housekeeping_status, 'inspected')

    # ------------------------------------------------------------------
    # Extra: Folio close with balance raises error
    # ------------------------------------------------------------------
    def test_14_folio_close_with_balance(self):
        res = self._create_reservation()
        folio = self.env['pms.folio'].create({
            'reservation_id': res.id,
        })
        self.env['pms.folio.charge'].create({
            'folio_id': folio.id,
            'description': 'Room charge',
            'quantity': 1,
            'unit_price': 200000,
        })
        with self.assertRaises(UserError):
            folio.action_close()

    # ------------------------------------------------------------------
    # Extra: Total amount computed from daily_rate * nights
    # ------------------------------------------------------------------
    def test_15_total_amount_computed(self):
        res = self._create_reservation(
            checkin_date=self.today,
            checkout_date=self.today + timedelta(days=3),
            daily_rate=300000,
        )
        self.assertEqual(res.total_amount, 900000)

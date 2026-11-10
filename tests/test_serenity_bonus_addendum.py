"""Serenity Skinner declined-services and ESC bonus tests."""

from __future__ import annotations

import unittest

from lib.esc_bonus_calc import calculate_esc_bonus
from lib.esc_bonus_pdf_export import generate_esc_bonus_pdf
from lib.receptionist_payroll_calc import (
    DEFAULT_DECLINED_APPOINTMENT_RATE,
    ReceptionistPayrollRow,
    calculate_receptionist_payroll,
)
from lib.receptionist_roster import ensure_declined_services_roster, roster_from_saved_data


class DeclinedServicesBonusTests(unittest.TestCase):
    def test_declined_and_regular_appointments_stack(self):
        row = ReceptionistPayrollRow(
            name="Serenity Skinner",
            appointment_rate=3.0,
            appointments_set=10,
            has_declined_services_plan=True,
            declined_appointments_set=5,
            declined_appointment_rate=DEFAULT_DECLINED_APPOINTMENT_RATE,
        )
        result = calculate_receptionist_payroll(row)
        self.assertEqual(result.appointment_pay, 30.0)
        self.assertEqual(result.declined_pay, 30.0)
        self.assertEqual(result.total_pay, 60.0)

    def test_roster_backfill_sets_serenity_plan(self):
        roster = roster_from_saved_data(
            {
                "receptionist": [
                    {
                        "name": "Serenity Skinner",
                        "last_name": "SKINNER",
                        "appointment_rate": 2.0,
                        "has_warranty_bonus": True,
                        "has_csi_bonus": True,
                    }
                ]
            }
        )
        self.assertTrue(ensure_declined_services_roster(roster))
        row = roster["receptionist"][0]
        self.assertTrue(row.has_declined_services_plan)
        self.assertEqual(row.appointment_rate, 3.0)
        self.assertEqual(row.declined_appointment_rate, 6.0)


class EscBonusTests(unittest.TestCase):
    def test_two_percent_of_net_paid(self):
        result = calculate_esc_bonus(
            employee_name="Serenity Skinner",
            bonus_month="October 2026",
            amount_paid=1000.0,
            chargebacks=100.0,
        )
        self.assertEqual(result.net_paid, 900.0)
        self.assertEqual(result.bonus_amount, 18.0)

    def test_denied_claims_pay_zero(self):
        result = calculate_esc_bonus(
            employee_name="Serenity Skinner",
            bonus_month="October 2026",
            amount_paid=0.0,
        )
        self.assertEqual(result.bonus_amount, 0.0)

    def test_pdf_builds(self):
        result = calculate_esc_bonus(
            employee_name="Serenity Skinner",
            bonus_month="October 2026",
            amount_paid=500.0,
            paid_on_label="November 10, 2026 (separate check)",
        )
        from lib.esc_bonus_calc import result_to_dict

        pdf = generate_esc_bonus_pdf(result_to_dict(result))
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

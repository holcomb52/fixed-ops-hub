"""Brandy Sistrunk RecallPulse tiered appointment bonus tests."""

from __future__ import annotations

import unittest

from lib.receptionist_payroll_calc import (
    RECALL_PULSE_STRETCH_BONUS,
    calculate_recall_pulse_appointment_bonus,
    calculate_receptionist_payroll,
    recall_pulse_qualified_tier,
    recall_pulse_rate_for_appointments,
    ReceptionistPayrollRow,
)


class RecallPulseBonusTests(unittest.TestCase):
    def test_tier_one_rate_on_all_appointments(self):
        self.assertEqual(recall_pulse_rate_for_appointments(15), 3.0)
        self.assertEqual(calculate_recall_pulse_appointment_bonus(15), 45.0)

    def test_tier_two_rate_on_all_appointments(self):
        self.assertEqual(recall_pulse_rate_for_appointments(25), 8.0)
        self.assertEqual(calculate_recall_pulse_appointment_bonus(25), 200.0)

    def test_tier_three_rate_on_all_appointments(self):
        self.assertEqual(recall_pulse_rate_for_appointments(35), 12.0)
        self.assertEqual(calculate_recall_pulse_appointment_bonus(35), 420.0)

    def test_tier_four_rate_on_all_appointments(self):
        label, rate = recall_pulse_qualified_tier(45)
        self.assertEqual(label, "Tier 4 · 36+ appointments")
        self.assertEqual(rate, 15.0)
        self.assertEqual(calculate_recall_pulse_appointment_bonus(45), 675.0)

    def test_forty_appointments_top_tier(self):
        self.assertEqual(calculate_recall_pulse_appointment_bonus(40), 600.0)

    def test_stretch_toggle_adds_to_total(self):
        row = ReceptionistPayrollRow(
            name="Brandy Sistrunk",
            has_recall_pulse_plan=True,
            has_csi_bonus=True,
            appointments_set=35,
            stretch_bonus_qualified=True,
            stretch_bonus_amount=RECALL_PULSE_STRETCH_BONUS,
        )
        result = calculate_receptionist_payroll(row)
        self.assertEqual(result.appointment_pay, 420.0)
        self.assertEqual(result.stretch_pay, 500.0)
        self.assertEqual(result.total_pay, 920.0)

    def test_other_receptionists_unaffected(self):
        row = ReceptionistPayrollRow(
            name="Misty Carver",
            appointment_rate=2.0,
            appointments_set=10,
        )
        result = calculate_receptionist_payroll(row)
        self.assertEqual(result.appointment_pay, 20.0)
        self.assertEqual(result.stretch_pay, 0.0)

    def test_cashiers_import_skips_brandy_sistrunk(self):
        from lib.receptionist_payroll_parser import (
            CashierReportSummary,
            cashiers_appointment_count_for_row,
            skips_cashiers_appointment_import,
        )

        brandy = ReceptionistPayrollRow(
            name="Brandy Sistrunk",
            last_name="SISTRUNK",
            taker_codes=["22SISTRUNKB"],
            has_recall_pulse_plan=True,
        )
        misty = ReceptionistPayrollRow(
            name="Misty Carver",
            last_name="CARVER",
            taker_codes=["22CARVERM"],
        )
        by_code = {
            "22SISTRUNKB": CashierReportSummary("22SISTRUNKB", "SISTRUNK", 40, "Sistrunk"),
            "22CARVERM": CashierReportSummary("22CARVERM", "CARVER", 12, "Carver"),
        }
        by_last = {
            "SISTRUNK": by_code["22SISTRUNKB"],
            "CARVER": by_code["22CARVERM"],
        }
        self.assertTrue(skips_cashiers_appointment_import(brandy))
        self.assertEqual(cashiers_appointment_count_for_row(brandy, by_code, by_last), 0.0)
        self.assertEqual(cashiers_appointment_count_for_row(misty, by_code, by_last), 12.0)


if __name__ == "__main__":
    unittest.main()

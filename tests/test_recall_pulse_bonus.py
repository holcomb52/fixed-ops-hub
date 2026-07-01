"""Brandy Sistrunk RecallPulse tiered appointment bonus tests."""

from __future__ import annotations

import unittest

from lib.receptionist_payroll_calc import (
    RECALL_PULSE_STRETCH_BONUS,
    calculate_recall_pulse_appointment_bonus,
    calculate_receptionist_payroll,
    ReceptionistPayrollRow,
)


class RecallPulseBonusTests(unittest.TestCase):
    def test_pdf_example_forty_appointments(self):
        self.assertEqual(calculate_recall_pulse_appointment_bonus(40), 320.0)

    def test_tier_one_only(self):
        self.assertEqual(calculate_recall_pulse_appointment_bonus(15), 45.0)

    def test_twenty_five_appointments(self):
        self.assertEqual(calculate_recall_pulse_appointment_bonus(25), 125.0)

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
        self.assertEqual(result.appointment_pay, 245.0)
        self.assertEqual(result.stretch_pay, 500.0)
        self.assertEqual(result.total_pay, 745.0)

    def test_other_receptionists_unaffected(self):
        row = ReceptionistPayrollRow(
            name="Misty Carver",
            appointment_rate=2.0,
            appointments_set=10,
        )
        result = calculate_receptionist_payroll(row)
        self.assertEqual(result.appointment_pay, 20.0)
        self.assertEqual(result.stretch_pay, 0.0)


if __name__ == "__main__":
    unittest.main()

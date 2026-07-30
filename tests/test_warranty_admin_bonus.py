"""Warranty Administrator monthly bonus pay plan tests."""

from __future__ import annotations

import unittest

from lib.warranty_admin_bonus_calc import (
    MAX_MONTHLY_BONUS,
    STRETCH_BONUS,
    calculate_warranty_admin_bonus,
)
from lib.warranty_admin_bonus_pdf_export import generate_warranty_admin_bonus_pdf
from lib.warranty_admin_bonus_calc import result_to_dict


class WarrantyAdminBonusTests(unittest.TestCase):
    def test_top_tiers_with_stretch(self):
        result = calculate_warranty_admin_bonus(
            employee_name="Warranty Admin",
            bonus_month="July 2026",
            receivables_balance=85_000,
            avg_days_to_submit=2.0,
            first_pass_pct=90.0,
        )
        self.assertEqual(result.receivables.amount, 400.0)
        self.assertEqual(result.avg_days.amount, 300.0)
        self.assertEqual(result.first_pass.amount, 300.0)
        self.assertTrue(result.stretch_earned)
        self.assertEqual(result.stretch_amount, STRETCH_BONUS)
        self.assertEqual(result.total_bonus, 1250.0)
        self.assertEqual(result.total_bonus, MAX_MONTHLY_BONUS)

    def test_mid_tiers_no_stretch(self):
        result = calculate_warranty_admin_bonus(
            employee_name="Warranty Admin",
            bonus_month="July 2026",
            receivables_balance=90_000,
            avg_days_to_submit=2.5,
            first_pass_pct=87.0,
        )
        self.assertEqual(result.receivables.amount, 250.0)
        self.assertEqual(result.avg_days.amount, 150.0)
        self.assertEqual(result.first_pass.amount, 150.0)
        self.assertFalse(result.stretch_earned)
        self.assertEqual(result.total_bonus, 550.0)

    def test_over_limits_zero(self):
        result = calculate_warranty_admin_bonus(
            employee_name="Warranty Admin",
            bonus_month="July 2026",
            receivables_balance=120_000,
            avg_days_to_submit=4.0,
            first_pass_pct=80.0,
        )
        self.assertEqual(result.total_bonus, 0.0)

    def test_compliance_reduction(self):
        result = calculate_warranty_admin_bonus(
            employee_name="Warranty Admin",
            bonus_month="July 2026",
            receivables_balance=80_000,
            avg_days_to_submit=1.5,
            first_pass_pct=92.0,
            compliance_reduction=250.0,
        )
        self.assertEqual(result.metrics_subtotal, 1250.0)
        self.assertEqual(result.total_bonus, 1000.0)

    def test_pdf_exports_bytes(self):
        result = calculate_warranty_admin_bonus(
            employee_name="Warranty Admin",
            bonus_month="July 2026",
            receivables_balance=80_000,
            avg_days_to_submit=1.5,
            first_pass_pct=92.0,
            notes="Ready for payroll",
        )
        pdf = generate_warranty_admin_bonus_pdf(result_to_dict(result))
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

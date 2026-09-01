"""CSI / NPS bonus calculation tests."""

from __future__ import annotations

import unittest

from lib.csi_bonus_calc import BONUS_MID, BONUS_TOP, calculate_csi_bonus
from lib.csi_bonus_pdf_export import generate_csi_bonus_pdf
from lib.csi_bonus_storage import serialize_csi_bonus_session


class CsiBonusTests(unittest.TestCase):
    def test_top_tier_at_or_above_national(self):
        result = calculate_csi_bonus(
            employee_name="Serenity Skinner",
            bonus_month="February 2026",
            store_nps=82.0,
            national_average=80.0,
            business_center_average=75.0,
        )
        self.assertEqual(result.bonus_amount, BONUS_TOP)
        self.assertIn("National Average", result.tier_label)

    def test_mid_tier_between_benchmarks(self):
        result = calculate_csi_bonus(
            employee_name="Brandy Sistrunk",
            bonus_month="February 2026",
            store_nps=78.0,
            national_average=80.0,
            business_center_average=75.0,
        )
        self.assertEqual(result.bonus_amount, BONUS_MID)

    def test_no_bonus_below_business_center(self):
        result = calculate_csi_bonus(
            employee_name="Brandy Sistrunk",
            bonus_month="February 2026",
            store_nps=70.0,
            national_average=80.0,
            business_center_average=75.0,
        )
        self.assertEqual(result.bonus_amount, 0.0)

    def test_snapshot_and_pdf(self):
        snap = serialize_csi_bonus_session(
            employee_name="Serenity Skinner",
            bonus_month="February 2026",
            store_nps=82.0,
            national_average=80.0,
            business_center_average=75.0,
        )
        self.assertEqual(snap["bonus_amount"], BONUS_TOP)
        pdf = generate_csi_bonus_pdf(snap)
        self.assertTrue(len(pdf) > 500)


if __name__ == "__main__":
    unittest.main()

"""End-of-month Fixed Ops report tests."""

from __future__ import annotations

import unittest

from lib.eom_report_calc import calculate_eom_report, result_to_dict
from lib.eom_report_pdf_export import generate_eom_report_pdf


class EomReportTests(unittest.TestCase):
    def test_available_hours_and_efficiency(self):
        # July 26 sample: 15 techs × 8 × 26 = 3120 available; 1844.7 / 3099.34 efficiency
        result = calculate_eom_report(
            report_month="July 2026",
            tech_count=15,
            hours_per_day=8,
            work_days=26,
            total_clock_time=3099.34,
            tech_flagged_hours=1844.7,
            lot_porters=4,
            cashiers=4,
            advisors=6,
            shuttle_drivers=2,
        )
        self.assertEqual(result.total_available_hours, 3120.0)
        self.assertAlmostEqual(result.efficiency_pct, (1844.7 / 3099.34) * 100.0, places=2)

    def test_zero_clock_time_efficiency(self):
        result = calculate_eom_report(
            report_month="August 2026",
            tech_count=10,
            hours_per_day=8,
            work_days=20,
            total_clock_time=0,
            tech_flagged_hours=100,
        )
        self.assertEqual(result.efficiency, 0.0)
        self.assertEqual(result.total_available_hours, 1600.0)

    def test_pdf_exports_bytes(self):
        result = calculate_eom_report(
            report_month="July 2026",
            tech_count=15,
            hours_per_day=8,
            work_days=26,
            total_clock_time=3099.34,
            tech_flagged_hours=1844.7,
            notes="Ready for controller",
        )
        pdf = generate_eom_report_pdf(result_to_dict(result))
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

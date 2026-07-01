"""Warranty ELR exclusion and running-total logic."""

from __future__ import annotations

import unittest

from lib.warranty_labor_calc import (
    WarrantyLaborRow,
    summarize_reviewed_running_total,
    summarize_rows,
)


def _row(**kwargs) -> WarrantyLaborRow:
    defaults = {
        "line_id": "0001-R1",
        "recid": "R1",
        "ro_date": "06/01/26",
        "advisor_no": "",
        "cwi_flag": "",
        "op_code": "OP",
        "op_desc": "Test",
        "tech_hrs": 1.0,
        "lbr_cost": 0.0,
        "lbr_sale": 100.0,
        "lbr_gross": 0.0,
        "sheet_elr": 0.0,
        "first_name": "",
        "last_name": "",
        "make_code": "",
        "misc_code": "",
        "notes": "",
        "exclusion": "",
    }
    defaults.update(kwargs)
    return WarrantyLaborRow(**defaults)


class WarrantyLaborCalcTests(unittest.TestCase):
    def test_single_excluded_line_removed_from_totals(self):
        rows = [
            _row(line_id="0001-R1", tech_hrs=2.0, lbr_sale=500.0),
            _row(line_id="0002-R1", tech_hrs=1.0, lbr_sale=200.0, exclusion="Tires"),
        ]
        summary = summarize_rows(rows)

        self.assertEqual(summary.included_rows, 1)
        self.assertEqual(summary.excluded_rows, 1)
        self.assertEqual(summary.total_lbr_sale, 500.0)
        self.assertEqual(summary.total_tech_hrs, 2.0)
        self.assertEqual(summary.effective_labor_rate, 250.0)

    def test_all_lines_excluded_on_repair_order(self):
        rows = [
            _row(line_id="0001-R2", recid="R2", exclusion="Maintenance"),
            _row(line_id="0002-R2", recid="R2", tech_hrs=3.0, lbr_sale=900.0, exclusion="Tires"),
        ]
        summary = summarize_reviewed_running_total(rows, {"R2"})

        self.assertEqual(summary.included_rows, 0)
        self.assertEqual(summary.total_lbr_sale, 0.0)
        self.assertEqual(summary.total_tech_hrs, 0.0)
        self.assertEqual(summary.effective_labor_rate, 0.0)

    def test_reviewed_ros_only_with_per_line_exclusions(self):
        rows = [
            _row(line_id="0001-R3", recid="R3", tech_hrs=1.0, lbr_sale=279.29),
            _row(line_id="0002-R3", recid="R3", tech_hrs=2.0, lbr_sale=400.0, exclusion="Battery"),
            _row(line_id="0003-R4", recid="R4", tech_hrs=5.0, lbr_sale=1000.0),
        ]
        summary = summarize_reviewed_running_total(rows, {"R3"})

        self.assertEqual(summary.included_rows, 1)
        self.assertEqual(summary.total_lbr_sale, 279.29)
        self.assertEqual(summary.total_tech_hrs, 1.0)
        self.assertAlmostEqual(summary.effective_labor_rate, 279.29)

    def test_unreviewed_repair_orders_not_in_running_total(self):
        rows = [
            _row(line_id="0001-R5", recid="R5", tech_hrs=10.0, lbr_sale=5000.0),
            _row(line_id="0002-R6", recid="R6", tech_hrs=1.0, lbr_sale=100.0),
        ]
        summary = summarize_reviewed_running_total(rows, {"R6"})

        self.assertEqual(summary.total_lbr_sale, 100.0)
        self.assertEqual(summary.total_tech_hrs, 1.0)


if __name__ == "__main__":
    unittest.main()

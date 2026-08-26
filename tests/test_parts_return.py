"""Parts return allowance planner tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import openpyxl

from lib.parts_return_calc import (
    age_value_score,
    build_return_plan,
    is_hardware_description,
    is_multipack,
)
from lib.parts_return_parser import (
    PartsInventoryLine,
    merge_parts_reports,
    parse_parts_workbook,
)


def _line(**kwargs) -> PartsInventoryLine:
    base = dict(
        part_number="P1",
        description="FILTER OIL",
        qoh=2,
        age=12,
        pack=1,
        cost=10.0,
        value=20.0,
        source="MNS",
    )
    base.update(kwargs)
    return PartsInventoryLine(**base)


def _write_workbook(path: Path, rows: list[tuple]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "QOH",
            "Part Number",
            "Description",
            "Detail",
            "SRC",
            "Bin",
            "Bin2",
            "STS",
            "RC",
            "Age",
            "HI",
            "PO Date",
            "QPR",
            "OT",
            "Pack",
            "Cost",
            "Value",
            "Group",
        ]
    )
    for row in rows:
        ws.append(list(row))
    wb.save(path)


class PartsReturnTests(unittest.TestCase):
    def test_hardware_and_multipack_flags(self):
        self.assertTrue(is_hardware_description("BOLT HEX FLANGE HEAD"))
        self.assertTrue(is_hardware_description("NUT HEX FLANGE"))
        self.assertFalse(is_hardware_description("FILTER ENGINE OIL"))
        self.assertTrue(is_multipack(_line(pack=12)))
        self.assertFalse(is_multipack(_line(pack=1)))

    def test_age_value_prefers_old_high_dollar(self):
        self.assertGreater(age_value_score(20, 100), age_value_score(10, 100))
        self.assertGreater(age_value_score(10, 200), age_value_score(10, 50))

    def test_build_plan_filters_and_fills_allowance(self):
        lines = [
            _line(part_number="OLD$", description="BATTERY", age=16, value=500, cost=500, qoh=1),
            _line(part_number="BOLT1", description="BOLT HEX", age=20, value=400, cost=50, qoh=8),
            _line(part_number="MP1", description="FLUID", age=15, value=300, cost=25, qoh=12, pack=12),
            _line(part_number="MID", description="GASKET", age=14, value=200, cost=200, qoh=1),
            _line(part_number="LOW", description="CLAMP HOSE", age=11, value=50, cost=50, qoh=1),
        ]
        plan = build_return_plan(lines, allowance=750, exclude_multipack=True, exclude_hardware=True)
        selected_pns = [c.line.part_number for c in plan.selected]
        self.assertEqual(selected_pns[0], "OLD$")
        self.assertIn("MID", selected_pns)
        self.assertNotIn("BOLT1", selected_pns)
        self.assertNotIn("MP1", selected_pns)
        self.assertLessEqual(plan.selected_value, 750.01)
        self.assertGreaterEqual(plan.remaining_allowance, 0)

    def test_partial_qty_uses_remaining_dollars(self):
        lines = [
            _line(
                part_number="EXPENSIVE",
                description="MODULE",
                age=18,
                qoh=10,
                cost=100,
                value=1000,
                pack=1,
            )
        ]
        plan = build_return_plan(lines, allowance=250, allow_partial_qty=True)
        self.assertEqual(len(plan.selected), 1)
        self.assertEqual(plan.selected[0].return_qty, 2)
        self.assertEqual(plan.selected[0].return_value, 200.0)

    def test_parse_and_merge_workbooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            mns = Path(tmp) / "mns.xlsx"
            mnr = Path(tmp) / "mnr.xlsx"
            _write_workbook(
                mns,
                [
                    (1, "AAA-1", "BATTERY", "", 701, "A1", None, "AP", "E", 16, 2025, None, None, None, 1, 100, 100, None),
                    (2, "BOLT-1", "BOLT HEX", "", 701, "B1", None, "AP", "E", 14, 2025, None, None, None, 2, 5, 10, None),
                ],
            )
            _write_workbook(
                mnr,
                [
                    (4, "AAA-1", "BATTERY", "", 701, "A1", None, "AP", "E", 18, 2025, None, None, None, 1, 100, 400, None),
                    (1, "CCC-1", "SENSOR", "", 701, "C1", None, "AP", "E", 12, 2025, None, None, None, 1, 40, 40, None),
                ],
            )
            mns_lines = parse_parts_workbook(mns, "MNS")
            mnr_lines = parse_parts_workbook(mnr, "MNR")
            self.assertEqual(len(mns_lines), 2)
            merged = merge_parts_reports(mns_lines, mnr_lines)
            by_pn = {r.part_number: r for r in merged}
            self.assertEqual(by_pn["AAA-1"].source, "MNS+MNR")
            self.assertEqual(by_pn["AAA-1"].age, 18)
            self.assertEqual(by_pn["AAA-1"].value, 400)
            self.assertEqual(by_pn["CCC-1"].source, "MNR")

    def test_snapshot_and_pdf(self):
        from lib.parts_return_pdf_export import generate_parts_return_pdf
        from lib.parts_return_snapshot import serialize_parts_return_plan

        lines = [
            _line(part_number="OLD$", description="BATTERY", age=16, value=500, cost=500, qoh=1),
            _line(part_number="MID", description="GASKET", age=14, value=200, cost=200, qoh=1),
        ]
        plan = build_return_plan(lines, allowance=750)
        snap = serialize_parts_return_plan(
            plan,
            label="August 2026 Returns",
            mns_name="mns.xlsx",
            mnr_name="mnr.xlsx",
            mns_count=1,
            mnr_count=1,
            candidate_count=2,
        )
        self.assertEqual(snap["selected_count"], 2)
        pdf = generate_parts_return_pdf(snap)
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

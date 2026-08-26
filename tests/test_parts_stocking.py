"""Parts stocking planner tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import openpyxl

from lib.parts_stocking_calc import build_stocking_plan
from lib.parts_stocking_parser import SixMonthSalesLine, parse_six_month_sales_workbook


def _write_6ms(path: Path, rows: list[tuple]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["QOH", "Sold", "Make", "Part#", "Description", "Source", "Cost", "Extended"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


class PartsStockingTests(unittest.TestCase):
    def test_parse_6ms_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "6ms.xlsx"
            _write_6ms(
                path,
                [
                    (1036, 8625, "CH", "68522999-AA", "OIL 0W20", "726", 6.66, 57442.5),
                    (8, 1635, "CH", "1BP00007-AA", "OIL 5W30 CASE", "725", 7.35, 12017.25),
                ],
            )
            lines = parse_six_month_sales_workbook(path)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0].part_number, "68522999-AA")
            self.assertEqual(lines[0].sold_6mo, 8625)

    def test_order_when_below_target(self):
        plan = build_stocking_plan(
            [
                SixMonthSalesLine(
                    part_number="68522999-AA",
                    description="OIL 0W20",
                    qoh=1036,
                    sold_6mo=8625,
                    cost=6.66,
                )
            ],
            target_months=1.0,
        )
        line = plan.lines[0]
        self.assertEqual(line.status, "order")
        self.assertEqual(line.monthly_demand, 1437.5)
        self.assertEqual(line.target_on_hand, 1438)
        self.assertEqual(line.order_qty, 402)

    def test_negative_qoh_orders_enough_to_reach_target(self):
        plan = build_stocking_plan(
            [
                SixMonthSalesLine(
                    part_number="1BP00466-AB",
                    description="FILTER ENGINE OIL",
                    qoh=-5,
                    sold_6mo=1202,
                    cost=8.1,
                )
            ],
            target_months=1.0,
        )
        line = plan.lines[0]
        self.assertEqual(line.status, "order")
        self.assertEqual(line.target_on_hand, 201)
        self.assertEqual(line.order_qty, 206)

    def test_ok_when_at_or_above_target(self):
        plan = build_stocking_plan(
            [
                SixMonthSalesLine(
                    part_number="P1",
                    description="PART",
                    qoh=200,
                    sold_6mo=600,
                    cost=10.0,
                )
            ],
            target_months=1.0,
        )
        self.assertEqual(plan.lines[0].status, "ok")
        self.assertEqual(plan.lines[0].order_qty, 0)

    def test_no_sales_skips_order(self):
        plan = build_stocking_plan(
            [
                SixMonthSalesLine(
                    part_number="P2",
                    description="DEAD STOCK",
                    qoh=50,
                    sold_6mo=0,
                    cost=5.0,
                )
            ],
        )
        self.assertEqual(plan.lines[0].status, "no_sales")
        self.assertEqual(plan.lines[0].order_qty, 0)


if __name__ == "__main__":
    unittest.main()

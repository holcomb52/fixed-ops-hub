"""Warranty labor spreadsheet parser — DMS and attorney FINAL layouts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from lib.warranty_labor_parser import parse_warranty_labor_report


class WarrantyLaborParserTests(unittest.TestCase):
    def _write_sheet(self, headers, rows) -> Path:
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(headers)
        for row in rows:
            ws.append(row)
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        path = Path(tmp.name)
        wb.save(path)
        return path

    def test_parses_dms_layout(self):
        path = self._write_sheet(
            [
                "RECID",
                "RO-DATE",
                "CWI-FLAG",
                "SVC-OP-CODES",
                "OP-DESC",
                "TECH HRS",
                "LBR SALE",
                "STD-MK-CODE",
            ],
            [
                [577420, "2026-05-02", "C", "08CHZZWIPER4", "WASHER CONCERN", 0.8, 223.2, "RAM"],
            ],
        )
        try:
            rows = parse_warranty_labor_report(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].recid, "577420")
            self.assertEqual(rows[0].tech_hrs, 0.8)
            self.assertEqual(rows[0].lbr_sale, 223.2)
            self.assertEqual(rows[0].op_code, "08CHZZWIPER4")
            self.assertEqual(rows[0].make_code, "RAM")
        finally:
            path.unlink(missing_ok=True)

    def test_parses_attorney_final_layout(self):
        path = self._write_sheet(
            [None, "RO-DATE", "RO#", "MAKE", "CWI", "JOB-NO", "OP-DESC", "HOURS", "BILL-AMT", "DISCOUNT"],
            [
                ["1", "2026-06-01", 578484, "RAM", "C", 1, "COOLING", 2, 577, None],
                [None, "2026-06-01", 578484, "RAM", "C", 4, "COOLING", 1, 295, None],
                ["2", "2026-06-02", 578536, "JE", "C", 1, "CTRL MDL", 1.5, 456, 12.5],
            ],
        )
        try:
            rows = parse_warranty_labor_report(path)
            self.assertEqual(len(rows), 3)

            self.assertEqual(rows[0].recid, "578484")
            self.assertEqual(rows[0].ro_date, "06/01/2026")
            self.assertEqual(rows[0].make_code, "RAM")
            self.assertEqual(rows[0].cwi_flag, "C")
            self.assertEqual(rows[0].op_code, "1")
            self.assertEqual(rows[0].op_desc, "COOLING")
            self.assertEqual(rows[0].tech_hrs, 2.0)
            self.assertEqual(rows[0].lbr_sale, 577.0)

            self.assertEqual(rows[1].recid, "578484")
            self.assertEqual(rows[1].op_code, "4")
            self.assertEqual(rows[1].tech_hrs, 1.0)
            self.assertEqual(rows[1].lbr_sale, 295.0)

            self.assertEqual(rows[2].recid, "578536")
            self.assertEqual(rows[2].make_code, "JE")
            self.assertIn("Discount: 12.5", rows[2].notes)
            self.assertAlmostEqual(rows[2].elr, 456 / 1.5)
        finally:
            path.unlink(missing_ok=True)

    def test_attorney_file_on_disk_if_present(self):
        path = Path(
            "/Users/bigstud/Library/CloudStorage/OneDrive-AMSI-NewSmyrnaBeachChrysler/"
            "WARRANTY LABOR RATE/Copy of New Smyrna CDJR Labor ROs June 2026 FINAL.xlsx"
        )
        if not path.exists():
            self.skipTest("Attorney spreadsheet not available on this machine")

        rows = parse_warranty_labor_report(path, sheet_name="FINAL")
        self.assertEqual(len(rows), 73)
        self.assertEqual(len({row.recid for row in rows}), 49)
        self.assertEqual(rows[0].recid, "578484")
        self.assertEqual(rows[0].tech_hrs, 2.0)
        self.assertEqual(rows[0].lbr_sale, 577.0)
        self.assertEqual(rows[0].make_code, "RAM")
        self.assertTrue(all(row.recid for row in rows))
        self.assertTrue(all(row.tech_hrs >= 0 for row in rows))


if __name__ == "__main__":
    unittest.main()

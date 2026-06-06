"""Parse advisor payroll report (PAYROLL.xlsx from office scanner)."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Dict, List, Union

import openpyxl

PAYROLL_NAME_MAP = {
    "JOEY MALDONADO": "Richard Maldonado",
    "TOM LEBLANC": "Tom LeBlanc",
    "MATTHEW GARRIGAN": "Matthew Garrigan",
    "BRADY HATCHER": "Brady Hatcher",
    "FELIX FIGUEROA": "Felix Figueroa",
}


@dataclass
class AdvisorReportRow:
    advisor_id: str
    pdf_name: str
    display_name: str
    repair_order_count: float
    operation_count: float
    tech_hours: float
    labor_sales: float
    parts_sales: float
    parts_labor_sales: float
    tech_hours_per_ro: float


def _normalize_name(raw: str) -> str:
    key = (raw or "").strip().upper()
    return PAYROLL_NAME_MAP.get(key, raw.strip().title())


def parse_advisor_payroll_report(source: Union[str, BytesIO, BinaryIO]) -> List[AdvisorReportRow]:
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.active
    rows: List[AdvisorReportRow] = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[1]:
            continue
        name = str(row[1]).strip()
        if name.upper() == "HOUSE ADVISOR":
            continue

        ro_count = float(row[2] or 0)
        tech_hours = float(row[4] or 0)
        parts_sales = float(row[8] or 0)
        parts_labor = float(row[10] or 0)
        hours_per_ro = float(row[7] or 0)
        if not hours_per_ro and ro_count:
            hours_per_ro = tech_hours / ro_count

        rows.append(
            AdvisorReportRow(
                advisor_id=str(row[0] or "").strip(),
                pdf_name=name,
                display_name=_normalize_name(name),
                repair_order_count=ro_count,
                operation_count=float(row[3] or 0),
                tech_hours=tech_hours,
                labor_sales=float(row[5] or 0),
                parts_sales=parts_sales,
                parts_labor_sales=parts_labor,
                tech_hours_per_ro=hours_per_ro,
            )
        )

    return rows


def report_by_name(rows: List[AdvisorReportRow]) -> Dict[str, AdvisorReportRow]:
    return {r.display_name.upper(): r for r in rows}

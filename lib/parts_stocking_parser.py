"""Parse CDK/Chrysler 6-month sales (6MS) parts exports."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Iterable, List, Optional, Union

import openpyxl

REQUIRED_HEADERS = {
    "qoh": "QOH",
    "sold": "Sold",
    "part_number": "Part#",
    "description": "Description",
    "cost": "Cost",
}


@dataclass
class SixMonthSalesLine:
    part_number: str
    description: str
    qoh: float
    sold_6mo: float
    cost: float
    make: str = ""
    source: str = ""
    extended: float = 0.0


def _norm_header(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _header_map(row: Iterable) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row):
        key = _norm_header(cell)
        if key:
            mapping[key] = idx
    return mapping


def _cell(row, index: Optional[int], default=None):
    if index is None or index >= len(row):
        return default
    return row[index]


def _as_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).replace(",", "").replace("$", "").strip()
        try:
            return float(text)
        except ValueError:
            return default


def parse_six_month_sales_workbook(
    source: Union[str, BytesIO, BinaryIO],
) -> List[SixMonthSalesLine]:
    """Parse a 6MS (.xlsx) export into inventory lines."""
    wb = openpyxl.load_workbook(source, data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        headers = _header_map(rows[0])
        missing = [
            label
            for key, label in REQUIRED_HEADERS.items()
            if _norm_header(label) not in headers
        ]
        if missing:
            raise ValueError(f"Missing columns in 6MS file: {', '.join(missing)}")

        qoh_i = headers[_norm_header("QOH")]
        sold_i = headers[_norm_header("Sold")]
        pn_i = headers[_norm_header("Part#")]
        desc_i = headers[_norm_header("Description")]
        cost_i = headers[_norm_header("Cost")]
        make_i = headers.get(_norm_header("Make"))
        source_i = headers.get(_norm_header("Source"))
        extended_i = headers.get(_norm_header("Extended"))

        lines: List[SixMonthSalesLine] = []
        for row in rows[1:]:
            if not row:
                continue
            part_number = str(_cell(row, pn_i, "") or "").strip()
            if not part_number:
                continue
            qoh = _as_float(_cell(row, qoh_i), 0.0)
            sold = _as_float(_cell(row, sold_i), 0.0)
            cost = _as_float(_cell(row, cost_i), 0.0)
            extended = _as_float(_cell(row, extended_i), 0.0)
            if extended <= 0 and sold > 0 and cost > 0:
                extended = round(sold * cost, 2)
            lines.append(
                SixMonthSalesLine(
                    part_number=part_number,
                    description=str(_cell(row, desc_i, "") or "").strip(),
                    qoh=qoh,
                    sold_6mo=sold,
                    cost=cost,
                    make=str(_cell(row, make_i, "") or "").strip(),
                    source=str(_cell(row, source_i, "") or "").strip(),
                    extended=extended,
                )
            )
        return lines
    finally:
        wb.close()

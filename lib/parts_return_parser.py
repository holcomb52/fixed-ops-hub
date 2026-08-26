"""Parse CDK/Chrysler MNS (months no sale) and MNR (months no receipt) parts exports."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Iterable, List, Optional, Union

import openpyxl

SOURCE_MNS = "MNS"
SOURCE_MNR = "MNR"

REQUIRED_HEADERS = {
    "qoh": "QOH",
    "part_number": "Part Number",
    "description": "Description",
    "age": "Age",
    "pack": "Pack",
    "cost": "Cost",
    "value": "Value",
}


@dataclass
class PartsInventoryLine:
    part_number: str
    description: str
    qoh: float
    age: float
    pack: float
    cost: float
    value: float
    source: str  # MNS | MNR
    bin_location: str = ""
    sts: str = ""
    detail: str = ""


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


def parse_parts_workbook(
    source: Union[str, BytesIO, BinaryIO],
    report_type: str,
) -> List[PartsInventoryLine]:
    """Parse an MNS or MNR .xlsx export into inventory lines."""
    report_type = (report_type or "").strip().upper()
    if report_type not in {SOURCE_MNS, SOURCE_MNR}:
        raise ValueError("report_type must be MNS or MNR")

    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows)
        except StopIteration:
            return []
        headers = _header_map(header_row)
        missing = [
            label
            for key, label in REQUIRED_HEADERS.items()
            if _norm_header(label) not in headers
        ]
        if missing:
            raise ValueError(
                f"Missing columns in {report_type} file: {', '.join(missing)}"
            )

        qoh_i = headers[_norm_header("QOH")]
        pn_i = headers[_norm_header("Part Number")]
        desc_i = headers[_norm_header("Description")]
        age_i = headers[_norm_header("Age")]
        pack_i = headers[_norm_header("Pack")]
        cost_i = headers[_norm_header("Cost")]
        value_i = headers[_norm_header("Value")]
        bin_i = headers.get(_norm_header("Bin"))
        sts_i = headers.get(_norm_header("STS"))
        detail_i = headers.get(_norm_header("Detail"))

        lines: List[PartsInventoryLine] = []
        for row in rows:
            if not row:
                continue
            part_number = str(_cell(row, pn_i, "") or "").strip()
            if not part_number:
                continue
            qoh = _as_float(_cell(row, qoh_i), 0.0)
            cost = _as_float(_cell(row, cost_i), 0.0)
            value = _as_float(_cell(row, value_i), 0.0)
            if value <= 0 and qoh > 0 and cost > 0:
                value = round(qoh * cost, 2)
            lines.append(
                PartsInventoryLine(
                    part_number=part_number,
                    description=str(_cell(row, desc_i, "") or "").strip(),
                    qoh=qoh,
                    age=_as_float(_cell(row, age_i), 0.0),
                    pack=max(_as_float(_cell(row, pack_i), 1.0), 1.0),
                    cost=cost,
                    value=value,
                    source=report_type,
                    bin_location=str(_cell(row, bin_i, "") or "").strip(),
                    sts=str(_cell(row, sts_i, "") or "").strip(),
                    detail=str(_cell(row, detail_i, "") or "").strip(),
                )
            )
        return lines
    finally:
        wb.close()


def merge_parts_reports(
    mns_lines: List[PartsInventoryLine],
    mnr_lines: List[PartsInventoryLine],
) -> List[PartsInventoryLine]:
    """
    Combine MNS + MNR under one return allowance. When the same part appears in
    both, keep the higher age and value, and tag source as MNS+MNR.
    """
    by_part: dict[str, PartsInventoryLine] = {}
    for line in list(mns_lines) + list(mnr_lines):
        key = line.part_number.upper()
        existing = by_part.get(key)
        if existing is None:
            by_part[key] = PartsInventoryLine(**{**line.__dict__})
            continue
        sources = set()
        for tag in (existing.source, line.source):
            for piece in str(tag).split("+"):
                piece = piece.strip().upper()
                if piece:
                    sources.add(piece)
        if sources == {"MNS", "MNR"}:
            merged_source = "MNS+MNR"
        else:
            merged_source = "+".join(sorted(sources))
        by_part[key] = PartsInventoryLine(
            part_number=existing.part_number,
            description=existing.description or line.description,
            qoh=max(existing.qoh, line.qoh),
            age=max(existing.age, line.age),
            pack=max(existing.pack, line.pack),
            cost=max(existing.cost, line.cost),
            value=max(existing.value, line.value),
            source=merged_source,
            bin_location=existing.bin_location or line.bin_location,
            sts=existing.sts or line.sts,
            detail=existing.detail or line.detail,
        )
    return sorted(by_part.values(), key=lambda r: (-r.age, -r.value, r.part_number))

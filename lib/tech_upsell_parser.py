"""Parse Ignite upsell analysis spreadsheets for technician closing %."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Dict, List, Union

import pandas as pd

from lib.flag_pdf_parser import PDF_NAME_MAP, normalize_tech_name
from lib.tech_roster import normalize_tech_number


@dataclass
class UpsellTechMetrics:
    tech_number: str
    raw_name: str
    display_name: str
    ro_count: int
    closing_pct: float
    hours_sold: float
    items_sold: int


def _normalize_header(value) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _find_header_row(df: pd.DataFrame) -> int:
    for idx in range(min(len(df), 15)):
        row = [_normalize_header(v) for v in df.iloc[idx].tolist()]
        if "technician name" in row and "closing" in " ".join(row):
            return idx
    return 0


def _column_index(headers: List[str], *needles: str) -> int:
    joined = " ".join(headers)
    for needle in needles:
        for i, header in enumerate(headers):
            if needle in header:
                return i
    raise KeyError(f"Missing column matching {needles!r} in {joined!r}")


def _match_display_name(raw_name: str, roster_names: List[str]) -> str:
    key = raw_name.strip().upper()
    if key in PDF_NAME_MAP:
        return PDF_NAME_MAP[key]

    title = raw_name.strip().title()
    roster_by_upper = {name.upper(): name for name in roster_names}
    if key in roster_by_upper:
        return roster_by_upper[key]
    if title in roster_names:
        return title

    # Fall back to PDF-style normalization (handles abbreviated PDF names).
    normalized = normalize_tech_name(raw_name)
    if normalized in roster_names:
        return normalized
    if normalized.upper() in roster_by_upper:
        return roster_by_upper[normalized.upper()]
    return normalized


def parse_upsell_report(
    source: Union[str, BinaryIO, BytesIO],
    roster_names: List[str],
) -> Dict[str, UpsellTechMetrics]:
    """Parse upsell analysis Excel. Returns metrics keyed by roster display name."""
    df = pd.read_excel(source, header=None)
    header_row = _find_header_row(df)
    headers = [_normalize_header(v) for v in df.iloc[header_row].tolist()]

    idx_number = _column_index(headers, "technician#", "technician #", "tech #")
    idx_name = _column_index(headers, "technician name", "tech name", "name")
    idx_ros = _column_index(headers, "ros", "ro count", "repair order")
    idx_hours = _column_index(headers, "hours sold", "hours")
    idx_sold = _column_index(headers, "sold", "items sold")
    idx_close = _column_index(headers, "closing")

    by_name: Dict[str, UpsellTechMetrics] = {}
    for _, row in df.iloc[header_row + 1 :].iterrows():
        raw_name = str(row.iloc[idx_name] or "").strip()
        if not raw_name or raw_name.lower() in {"nan", "total", "technician name"}:
            continue

        tech_number = normalize_tech_number(row.iloc[idx_number])
        display_name = _match_display_name(raw_name, roster_names)
        closing_raw = row.iloc[idx_close]
        closing_pct = float(str(closing_raw).replace("%", "").strip() or 0)

        metrics = UpsellTechMetrics(
            tech_number=tech_number,
            raw_name=raw_name,
            display_name=display_name,
            ro_count=int(float(row.iloc[idx_ros] or 0)),
            closing_pct=closing_pct,
            hours_sold=float(row.iloc[idx_hours] or 0),
            items_sold=int(float(row.iloc[idx_sold] or 0)),
        )
        by_name[display_name] = metrics
        if tech_number:
            by_name[f"#{tech_number}"] = metrics

    return by_name

"""Parse CASHIERS.xlsx appointment report."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Dict, List, Union

import openpyxl

# Codes that should never fill a receptionist appointment count from CASHIERS.
CASHIERS_SKIP_CODES = frozenset({"SVCPTL", "NUMA", "22SISTRUNKB"})


def cashiers_taker_codes(row) -> list[str]:
    return [str(code).strip().upper() for code in (getattr(row, "taker_codes", None) or []) if str(code).strip()]


def skips_cashiers_appointment_import(row) -> bool:
    """RecallPulse appointments (Brandy / 22SISTRUNKB) are entered by hand, not from CASHIERS."""
    if bool(getattr(row, "has_recall_pulse_plan", False)):
        return True
    if str(getattr(row, "name", "") or "").strip() == "Brandy Sistrunk":
        return True
    return "22SISTRUNKB" in cashiers_taker_codes(row)


def cashiers_appointment_count_for_row(
    row,
    by_code: Dict[str, CashierReportSummary],
    by_last: Dict[str, CashierReportSummary],
) -> float:
    """CASHIERS appointment total for a roster row, or 0 if skipped / unmatched."""
    if skips_cashiers_appointment_import(row):
        return 0.0
    appt_count = 0.0
    for code in cashiers_taker_codes(row):
        report = by_code.get(code)
        if report:
            appt_count += report.appointments_set
    if appt_count:
        return float(appt_count)
    last_name = str(getattr(row, "last_name", "") or "").strip().upper()
    if last_name:
        report = by_last.get(last_name)
        if report:
            return float(report.appointments_set)
    return 0.0

# Dealer taker codes that do not follow the 22LASTNAME pattern.
CODE_LAST_NAME = {
    "SVCPTL": "SVCPTL",
    "NUMA": "NUMA",
}

# Known code → display name for bonus employees discovered on the report.
BONUS_CODE_LABELS = {
    "22SKINNERS": "Skinner",
    "SVCPTL": "Service Portal",
    "NUMA": "Numa",
    "22RAINGED": "Rainge",
    "22GARRIGANM": "Garrigan",
    "22FIGUEROAF": "Figueroa",
    "22HOLCOMBB": "Holcomb",
    "22MALDONADOR": "Maldonado",
}


@dataclass
class CashierReportSummary:
    code: str
    last_name: str
    appointments_set: float
    display_label: str


def last_name_from_taker_code(code: str) -> str:
    raw = (code or "").strip().upper()
    if not raw:
        return ""
    if raw in CODE_LAST_NAME:
        return CODE_LAST_NAME[raw]
    # 22LASTNAMEF  or  22LASTNAME1 (digit suffix variants)
    match = re.match(r"^22([A-Z]+?)(?:[A-Z]|\d+)$", raw)
    if match:
        return match.group(1)
    match = re.match(r"^22([A-Z]+)([A-Z])$", raw)
    if match:
        return match.group(1)
    return raw


def display_label_for_code(code: str) -> str:
    raw = (code or "").strip().upper()
    if raw in BONUS_CODE_LABELS:
        return BONUS_CODE_LABELS[raw]
    last = last_name_from_taker_code(raw)
    return last.title() if last else raw


def parse_cashiers_report(source: Union[str, BytesIO, BinaryIO]) -> List[CashierReportSummary]:
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.active
    counts: Dict[str, float] = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        code = str(row[0]).strip().upper()
        appt_flag = row[6]
        if appt_flag in (1, 1.0, "1", True):
            counts[code] = counts.get(code, 0.0) + 1.0

    summaries: List[CashierReportSummary] = []
    for code, count in sorted(counts.items()):
        summaries.append(
            CashierReportSummary(
                code=code,
                last_name=last_name_from_taker_code(code),
                appointments_set=count,
                display_label=display_label_for_code(code),
            )
        )
    return summaries


def report_by_code(rows: List[CashierReportSummary]) -> Dict[str, CashierReportSummary]:
    return {r.code.upper(): r for r in rows}


def report_by_last_name(rows: List[CashierReportSummary]) -> Dict[str, CashierReportSummary]:
    out: Dict[str, CashierReportSummary] = {}
    for row in rows:
        key = row.last_name.upper()
        if key in out:
            out[key] = CashierReportSummary(
                code=out[key].code,
                last_name=key,
                appointments_set=out[key].appointments_set + row.appointments_set,
                display_label=out[key].display_label,
            )
        else:
            out[key] = row
    return out

"""Match flag sheet PDF data to roster technicians by name or tech number."""

from __future__ import annotations

from io import BytesIO
from typing import Dict, List, Optional, Tuple

from lib.flag_pdf_parser import FlagSheetParseResult, TechFlagData, parse_flag_sheet
from lib.tech_payroll_calc import TechPayrollRow
from lib.tech_roster import normalize_tech_number

FlagHoursEntry = Tuple[float, float]


def _name_key(name: str) -> str:
    return " ".join((name or "").upper().split())


def names_match(roster_name: str, flag_name: str) -> bool:
    if _name_key(roster_name) == _name_key(flag_name):
        return True
    roster_parts = (roster_name or "").split()
    flag_parts = (flag_name or "").split()
    if len(roster_parts) >= 2 and len(flag_parts) >= 2:
        return (
            roster_parts[0].upper() == flag_parts[0].upper()
            and roster_parts[-1].upper() == flag_parts[-1].upper()
        )
    return False


def build_flag_maps(
    technicians: List[TechFlagData],
) -> Tuple[Dict[str, FlagHoursEntry], Dict[str, FlagHoursEntry], Dict[str, dict]]:
    by_name: Dict[str, FlagHoursEntry] = {}
    by_number: Dict[str, FlagHoursEntry] = {}
    cp_by_name: Dict[str, dict] = {}

    for tech in technicians:
        entry: FlagHoursEntry = (tech.flat_rate_hours, tech.dollars_earned)
        name_keys = {
            tech.display_name,
            _name_key(tech.display_name),
            tech.pdf_name.strip(),
            _name_key(tech.pdf_name),
        }
        for key in name_keys:
            if key:
                by_name[key] = entry

        if tech.tech_number:
            by_number[normalize_tech_number(tech.tech_number)] = entry

        cp_entry = {
            "cp_hours": tech.cp_hours,
            "cp_ro_count": tech.cp_ro_count,
            "cp_hrs_per_ro": tech.cp_hrs_per_ro,
        }
        for key in name_keys:
            if key:
                cp_by_name[key] = cp_entry

    return by_name, by_number, cp_by_name


def match_flag_for_row(
    row: TechPayrollRow,
    technicians: List[TechFlagData],
    by_name: Dict[str, FlagHoursEntry],
    by_number: Dict[str, FlagHoursEntry],
) -> Optional[FlagHoursEntry]:
    if row.name in by_name:
        return by_name[row.name]

    name_key = _name_key(row.name)
    if name_key in by_name:
        return by_name[name_key]

    tech_number = normalize_tech_number(row.tech_number)
    if tech_number and tech_number in by_number:
        return by_number[tech_number]

    for tech in technicians:
        if names_match(row.name, tech.display_name):
            return (tech.flat_rate_hours, tech.dollars_earned)
    return None


def match_cp_for_row(row: TechPayrollRow, cp_by_name: Dict[str, dict]) -> Optional[dict]:
    if row.name in cp_by_name:
        return cp_by_name[row.name]
    name_key = _name_key(row.name)
    if name_key in cp_by_name:
        return cp_by_name[name_key]
    for key, metrics in cp_by_name.items():
        if names_match(row.name, key):
            return metrics
    return None


def parse_flag_pdf_bytes(pdf_bytes: bytes) -> FlagSheetParseResult:
    return parse_flag_sheet(BytesIO(pdf_bytes))


def apply_flag_to_teams(
    teams: Dict[str, List[TechPayrollRow]],
    parsed: FlagSheetParseResult,
) -> int:
    """Apply flag hours/dollars and CP metrics to roster rows. Returns match count."""
    by_name, by_number, cp_by_name = build_flag_maps(parsed.technicians)
    matched = 0

    for rows in teams.values():
        for row in rows:
            entry = match_flag_for_row(row, parsed.technicians, by_name, by_number)
            if entry:
                row.flat_rate_hours, row.dollars_earned = entry
                matched += 1

            cp_metrics = match_cp_for_row(row, cp_by_name)
            if cp_metrics:
                row.cp_hours = float(cp_metrics.get("cp_hours", 0) or 0)
                row.cp_ro_count = int(cp_metrics.get("cp_ro_count", 0) or 0)
                row.cp_hrs_per_ro = float(cp_metrics.get("cp_hrs_per_ro", 0) or 0)

    return matched
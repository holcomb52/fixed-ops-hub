"""Persist and mutate technician team rosters."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, List, Tuple

from lib.tech_payroll_calc import DEFAULT_TEAMS, DEFAULT_TECH_NUMBERS, QUICK_LUBE_TECHS, TechPayrollRow

ROSTER_PATH = Path(__file__).resolve().parent.parent / "data" / "tech_roster.json"

ROLE_OPTIONS = {
    "Regular": ("none", []),
    "Foreman ($2/hr team bonus)": ("team_per_hr_2", []),
    "Foreman ($1/hr team bonus)": ("team_per_hr_1", []),
    "Quick lube bonus recipient": ("none", list(QUICK_LUBE_TECHS)),
}


def role_label(row: TechPayrollRow) -> str:
    if row.foreman_rule == "team_per_hr_2":
        return "Foreman ($2/hr)"
    if row.foreman_rule == "team_per_hr_1":
        return "Foreman ($1/hr)"
    if row.quick_lube_sources:
        return "Quick lube bonus"
    return "Regular"


def role_option_key(row: TechPayrollRow) -> str:
    if row.foreman_rule == "team_per_hr_2":
        return "Foreman ($2/hr team bonus)"
    if row.foreman_rule == "team_per_hr_1":
        return "Foreman ($1/hr team bonus)"
    if row.quick_lube_sources:
        return "Quick lube bonus recipient"
    return "Regular"


def _clone_row(row: TechPayrollRow) -> TechPayrollRow:
    return TechPayrollRow(**copy.deepcopy(row.__dict__))


def clone_teams(teams: Dict[str, List[TechPayrollRow]]) -> Dict[str, List[TechPayrollRow]]:
    return {team: [_clone_row(row) for row in rows] for team, rows in teams.items()}


def normalize_tech_number(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isdigit())


def _serialize_row(row: TechPayrollRow) -> dict:
    return {
        "name": row.name,
        "tech_number": row.tech_number,
        "hourly_rate": row.hourly_rate,
        "foreman_rule": row.foreman_rule,
        "quick_lube_sources": list(row.quick_lube_sources),
    }


def serialize_roster(teams: Dict[str, List[TechPayrollRow]]) -> dict:
    return {
        team: [_serialize_row(row) for row in rows]
        for team, rows in teams.items()
    }


def teams_from_saved_data(teams_data: dict) -> Dict[str, List[TechPayrollRow]]:
    """Rebuild roster rows from saved payroll or roster JSON."""
    teams: Dict[str, List[TechPayrollRow]] = {}
    for team_name, techs in teams_data.items():
        teams[team_name] = []
        ordered = sorted(techs, key=lambda t: t.get("index", 0))
        for tech in ordered:
            tech_number = str(tech.get("tech_number", "") or "")
            if not tech_number:
                tech_number = DEFAULT_TECH_NUMBERS.get(tech["name"], "")
            teams[team_name].append(
                TechPayrollRow(
                    name=tech["name"],
                    team=team_name,
                    tech_number=tech_number,
                    hourly_rate=float(tech.get("rate", tech.get("hourly_rate", 0)) or 0),
                    flat_rate_hours=float(tech.get("hours", 0) or 0),
                    dollars_earned=float(tech.get("dollars", 0) or 0),
                    training_hours=float(tech.get("train", tech.get("training_hours", 0)) or 0),
                    spiff=float(tech.get("spiff", 0) or 0),
                    notes=str(tech.get("notes", "") or ""),
                    foreman_rule=tech.get("foreman_rule", "none"),
                    quick_lube_sources=list(tech.get("quick_lube_sources", [])),
                )
            )
    return teams


def load_roster() -> Dict[str, List[TechPayrollRow]]:
    if ROSTER_PATH.exists():
        data = json.loads(ROSTER_PATH.read_text())
        return teams_from_saved_data(data)
    return clone_teams(DEFAULT_TEAMS)


def save_roster(teams: Dict[str, List[TechPayrollRow]]) -> None:
    ROSTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_PATH.write_text(json.dumps(serialize_roster(teams), indent=2))


def all_technician_names(teams: Dict[str, List[TechPayrollRow]]) -> List[str]:
    names: List[str] = []
    for rows in teams.values():
        names.extend(row.name for row in rows)
    return names


def all_tech_numbers(teams: Dict[str, List[TechPayrollRow]], exclude_name: str = "") -> List[str]:
    numbers: List[str] = []
    for rows in teams.values():
        for row in rows:
            if row.name == exclude_name:
                continue
            if row.tech_number:
                numbers.append(row.tech_number)
    return numbers


def _validate_tech_number(
    teams: Dict[str, List[TechPayrollRow]],
    tech_number: str,
    exclude_name: str = "",
) -> Tuple[bool, str]:
    clean = normalize_tech_number(tech_number)
    if not clean:
        return False, "Enter a tech number."
    if clean in all_tech_numbers(teams, exclude_name=exclude_name):
        return False, f"Tech number {clean} is already assigned."
    return True, clean


def _apply_role(row: TechPayrollRow, role_label_key: str, team_rows: List[TechPayrollRow], row_index: int) -> None:
    foreman_rule, quick_lube_sources = ROLE_OPTIONS[role_label_key]
    if foreman_rule != "none":
        for i, other in enumerate(team_rows):
            if i != row_index and other.foreman_rule in ("team_per_hr_2", "team_per_hr_1"):
                other.foreman_rule = "none"
        row.foreman_rule = foreman_rule
        row.quick_lube_sources = []
    elif quick_lube_sources:
        row.foreman_rule = "none"
        row.quick_lube_sources = list(quick_lube_sources)
        for other in team_rows:
            if other is not row and other.quick_lube_sources:
                other.quick_lube_sources = []
    else:
        row.foreman_rule = "none"
        row.quick_lube_sources = []


def add_technician(
    teams: Dict[str, List[TechPayrollRow]],
    team_name: str,
    name: str,
    hourly_rate: float,
    tech_number: str,
    role: str = "Regular",
) -> Tuple[bool, str]:
    clean_name = " ".join(name.split())
    if not clean_name:
        return False, "Enter a technician name."
    if clean_name in all_technician_names(teams):
        return False, f"{clean_name} is already on a team."
    if team_name not in teams:
        return False, "Unknown team."
    if role not in ROLE_OPTIONS:
        return False, "Unknown role."

    ok, tech_num_or_msg = _validate_tech_number(teams, tech_number)
    if not ok:
        return False, tech_num_or_msg

    row = TechPayrollRow(clean_name, team_name, tech_number=tech_num_or_msg, hourly_rate=float(hourly_rate))
    _apply_role(row, role, teams[team_name], len(teams[team_name]))
    teams[team_name].append(row)
    return True, f"Added {clean_name} to {team_name}."


def remove_technician(
    teams: Dict[str, List[TechPayrollRow]],
    team_name: str,
    index: int,
) -> Tuple[bool, str]:
    rows = teams.get(team_name, [])
    if index < 0 or index >= len(rows):
        return False, "Technician not found."
    removed = rows.pop(index)
    return True, f"Removed {removed.name} from {team_name}."


def move_technician(
    teams: Dict[str, List[TechPayrollRow]],
    from_team: str,
    index: int,
    to_team: str,
) -> Tuple[bool, str]:
    if from_team == to_team:
        return False, "Choose a different team."
    if from_team not in teams or to_team not in teams:
        return False, "Unknown team."

    rows = teams[from_team]
    if index < 0 or index >= len(rows):
        return False, "Technician not found."

    row = rows.pop(index)
    row.team = to_team

    if row.foreman_rule in ("team_per_hr_2", "team_per_hr_1"):
        for other in teams[to_team]:
            if other.foreman_rule in ("team_per_hr_2", "team_per_hr_1"):
                row.foreman_rule = "none"
                break
        else:
            pass
    if row.quick_lube_sources:
        for other in teams[to_team]:
            if other.quick_lube_sources:
                row.quick_lube_sources = []
                break

    teams[to_team].append(row)
    return True, f"Moved {row.name} to {to_team}."


def update_technician(
    teams: Dict[str, List[TechPayrollRow]],
    team_name: str,
    index: int,
    hourly_rate: float,
    tech_number: str,
    role: str,
) -> Tuple[bool, str]:
    rows = teams.get(team_name, [])
    if index < 0 or index >= len(rows):
        return False, "Technician not found."
    if role not in ROLE_OPTIONS:
        return False, "Unknown role."

    row = rows[index]
    ok, tech_num_or_msg = _validate_tech_number(teams, tech_number, exclude_name=row.name)
    if not ok:
        return False, tech_num_or_msg

    row.hourly_rate = float(hourly_rate)
    row.tech_number = tech_num_or_msg
    _apply_role(row, role, rows, index)
    return True, f"Updated {row.name}."


def reset_roster() -> Dict[str, List[TechPayrollRow]]:
    return clone_teams(DEFAULT_TEAMS)

"""Persist and mutate receptionist rosters."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.receptionist_payroll_calc import (
    CSI_BONUS_DEFAULT_NAMES,
    DEFAULT_WARRANTY_BONUS,
    TYPE_RECEPTIONIST,
    ReceptionistPayrollRow,
    ensure_receptionist_row_fields,
)

ROSTER_PATH = Path(__file__).resolve().parent.parent / "data" / "receptionist_roster.json"


def normalize_roster(roster: Dict[str, List[ReceptionistPayrollRow]]) -> Dict[str, List[ReceptionistPayrollRow]]:
    rows = roster.get(TYPE_RECEPTIONIST, [])
    for i, row in enumerate(rows):
        rows[i] = ensure_receptionist_row_fields(row)
    roster[TYPE_RECEPTIONIST] = rows
    return roster


def _clone_row(row: ReceptionistPayrollRow) -> ReceptionistPayrollRow:
    return ensure_receptionist_row_fields(ReceptionistPayrollRow(**copy.deepcopy(row.__dict__)))


def clone_roster(roster: Dict[str, List[ReceptionistPayrollRow]]) -> Dict[str, List[ReceptionistPayrollRow]]:
    return {TYPE_RECEPTIONIST: [_clone_row(row) for row in roster.get(TYPE_RECEPTIONIST, [])]}


def default_roster() -> Dict[str, List[ReceptionistPayrollRow]]:
    return {
        TYPE_RECEPTIONIST: [
            ReceptionistPayrollRow("Misty Carver", last_name="CARVER", taker_codes=["22CARVERM"]),
            ReceptionistPayrollRow("Jennifer Cleary", last_name="CLEARY", taker_codes=["22CLEARYJ"]),
            ReceptionistPayrollRow(
                "Brandy Sistrunk",
                last_name="SISTRUNK",
                taker_codes=["22SISTRUNKB"],
                has_csi_bonus=True,
                has_recall_pulse_plan=True,
            ),
            ReceptionistPayrollRow("Kayla Hoffman", last_name="HOFFMAN", taker_codes=["22HOFFMANK"]),
            ReceptionistPayrollRow("Samantha Rodriguez", last_name="RODRIGUEZ", taker_codes=["22RODRIGUEZS"]),
            ReceptionistPayrollRow(
                "Serenity Skinner",
                last_name="SKINNER",
                taker_codes=["22SKINNERS"],
                has_warranty_bonus=True,
                warranty_bonus_amount=DEFAULT_WARRANTY_BONUS,
                has_csi_bonus=True,
            ),
        ],
    }


def flatten_roster(roster: Dict[str, List[ReceptionistPayrollRow]]) -> List[ReceptionistPayrollRow]:
    return list(roster.get(TYPE_RECEPTIONIST, []))


def format_receptionist_display_name(row: ReceptionistPayrollRow) -> str:
    """Show first and last name even when only the first name is stored in name."""
    name = (row.name or "").strip()
    last = (row.last_name or "").strip()
    if not name:
        return last.title() if last else ""
    if not last or last.upper() in name.upper():
        return name
    if len(name.split()) == 1:
        return f"{name} {last.title()}"
    return name


def build_receptionist_full_name(name: str, last_name: str) -> str:
    name = (name or "").strip()
    last = (last_name or "").strip().upper()
    if not name:
        return ""
    if last and last not in name.upper():
        first = name.split()[0]
        return f"{first} {last.title()}"
    return name


def _row_from_dict(item: dict) -> ReceptionistPayrollRow:
    name = item.get("name", "")
    has_csi_bonus = bool(item.get("has_csi_bonus", False))
    if not has_csi_bonus and name in CSI_BONUS_DEFAULT_NAMES:
        has_csi_bonus = True
    return ReceptionistPayrollRow(
        name=name,
        last_name=item.get("last_name", ""),
        employee_type=TYPE_RECEPTIONIST,
        taker_codes=list(item.get("taker_codes", [])),
        appointment_rate=float(item.get("appointment_rate", 0) or 0),
        has_warranty_bonus=bool(item.get("has_warranty_bonus", False)),
        warranty_bonus_amount=float(item.get("warranty_bonus_amount", DEFAULT_WARRANTY_BONUS) or DEFAULT_WARRANTY_BONUS),
        has_csi_bonus=has_csi_bonus,
        has_recall_pulse_plan=bool(
            item.get("has_recall_pulse_plan", name == "Brandy Sistrunk")
        ),
    )


def _serialize_row(row: ReceptionistPayrollRow) -> dict:
    return {
        "name": row.name,
        "last_name": row.last_name,
        "employee_type": row.employee_type,
        "taker_codes": list(row.taker_codes),
        "appointment_rate": row.appointment_rate,
        "has_warranty_bonus": row.has_warranty_bonus,
        "warranty_bonus_amount": row.warranty_bonus_amount,
        "has_csi_bonus": row.has_csi_bonus,
        "has_recall_pulse_plan": row.has_recall_pulse_plan,
    }


def serialize_roster(roster: Dict[str, List[ReceptionistPayrollRow]]) -> dict:
    return {
        TYPE_RECEPTIONIST: [_serialize_row(row) for row in roster.get(TYPE_RECEPTIONIST, [])],
        "bonus": [],
    }


def roster_from_saved_data(data: dict) -> Dict[str, List[ReceptionistPayrollRow]]:
    saved = data.get(TYPE_RECEPTIONIST, [])
    if not saved:
        return default_roster()
    return normalize_roster({TYPE_RECEPTIONIST: [_row_from_dict(item) for item in saved]})


def load_roster() -> Dict[str, List[ReceptionistPayrollRow]]:
    from lib.roster_supabase_sync import ROSTER_KEY_RECEPTIONISTS, load_roster_data

    remote = load_roster_data(ROSTER_KEY_RECEPTIONISTS)
    if remote is not None:
        return roster_from_saved_data(remote)
    if ROSTER_PATH.exists():
        try:
            data = json.loads(ROSTER_PATH.read_text())
            return roster_from_saved_data(data)
        except (json.JSONDecodeError, OSError):
            pass
    roster = default_roster()
    save_roster(roster)
    return roster


def save_roster(roster: Dict[str, List[ReceptionistPayrollRow]]):
    from lib.roster_supabase_sync import ROSTER_KEY_RECEPTIONISTS, save_roster_data

    data = serialize_roster(roster)
    try:
        ROSTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROSTER_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
    save_roster_data(ROSTER_KEY_RECEPTIONISTS, data, session_error_key="_receptionist_roster_sync_error")


def add_employee(
    roster: Dict[str, List[ReceptionistPayrollRow]],
    name: str,
    last_name: str = "",
    taker_codes: Optional[List[str]] = None,
    appointment_rate: float = 0.0,
    has_warranty_bonus: bool = False,
    warranty_bonus_amount: float = DEFAULT_WARRANTY_BONUS,
    has_csi_bonus: bool = False,
) -> Tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "Enter a name."
    for row in flatten_roster(roster):
        if row.name.lower() == name.lower():
            return False, f"{name} is already on the roster."
    roster.setdefault(TYPE_RECEPTIONIST, []).append(
        ReceptionistPayrollRow(
            name=name,
            last_name=(last_name or name.split()[-1]).strip().upper(),
            taker_codes=[c.strip().upper() for c in (taker_codes or []) if c.strip()],
            appointment_rate=appointment_rate,
            has_warranty_bonus=has_warranty_bonus,
            warranty_bonus_amount=warranty_bonus_amount,
            has_csi_bonus=has_csi_bonus,
        )
    )
    return True, f"Added {name}."


def remove_employee(roster: Dict[str, List[ReceptionistPayrollRow]], name: str) -> Tuple[bool, str]:
    before = len(roster.get(TYPE_RECEPTIONIST, []))
    roster[TYPE_RECEPTIONIST] = [row for row in roster.get(TYPE_RECEPTIONIST, []) if row.name != name]
    if len(roster[TYPE_RECEPTIONIST]) < before:
        return True, f"Removed {name}."
    return False, f"{name} not found."


def update_employee(
    roster: Dict[str, List[ReceptionistPayrollRow]],
    name: str,
    *,
    new_name: Optional[str] = None,
    appointment_rate: Optional[float] = None,
    taker_codes: Optional[List[str]] = None,
    last_name: Optional[str] = None,
    has_warranty_bonus: Optional[bool] = None,
    warranty_bonus_amount: Optional[float] = None,
    has_csi_bonus: Optional[bool] = None,
) -> Tuple[bool, str]:
    for row in flatten_roster(roster):
        if row.name != name:
            continue
        if new_name and new_name.strip() and new_name != name:
            for other in flatten_roster(roster):
                if other.name.lower() == new_name.strip().lower() and other.name != name:
                    return False, f"{new_name} is already on the roster."
            row.name = new_name.strip()
        elif new_name and new_name.strip():
            row.name = new_name.strip()
        if appointment_rate is not None:
            row.appointment_rate = appointment_rate
        if taker_codes is not None:
            row.taker_codes = [c.strip().upper() for c in taker_codes if c.strip()]
        if last_name is not None:
            row.last_name = last_name.strip().upper()
        if has_warranty_bonus is not None:
            row.has_warranty_bonus = has_warranty_bonus
        if warranty_bonus_amount is not None:
            row.warranty_bonus_amount = warranty_bonus_amount
        if has_csi_bonus is not None:
            row.has_csi_bonus = has_csi_bonus
        return True, f"Updated {row.name}."
    return False, f"{name} not found."


def ensure_recall_pulse_roster(roster: Dict[str, List[ReceptionistPayrollRow]]) -> bool:
    """Backfill Brandy Sistrunk's RecallPulse plan flag on existing rosters."""
    changed = False
    for row in flatten_roster(roster):
        if row.name == "Brandy Sistrunk" and not row.has_recall_pulse_plan:
            row.has_recall_pulse_plan = True
            changed = True
    return changed


def reset_roster() -> Dict[str, List[ReceptionistPayrollRow]]:
    roster = default_roster()
    save_roster(roster)
    return roster

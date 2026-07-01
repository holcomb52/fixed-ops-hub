"""Persist and mutate service advisor rosters by pay plan."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.advisor_payroll_calc import (
    PLAN_LABELS,
    PLAN_META,
    PLAN_NEW_ADVISORS,
    PLAN_NEW_ADVISORS_GUARANTEE,
    PLAN_SEASONED,
    AdvisorPayrollRow,
    apply_plan_defaults,
    ensure_advisor_row_fields,
    format_guarantee_expires,
    normalize_advisor_plan_type,
    plan_has_weekly_guarantee,
)

ROSTER_PATH = Path(__file__).resolve().parent.parent / "data" / "advisor_roster.json"

PLAN_ORDER = [PLAN_SEASONED, PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE]

# Advisors who belong on the weekly-guarantee plan (backfilled / moved on roster load).
GUARANTEE_ROSTER_ADVISORS = frozenset({"Brady Hatcher"})


def _name_on_guarantee_plan(name: str) -> bool:
    clean = (name or "").strip()
    if not clean:
        return False
    if clean in GUARANTEE_ROSTER_ADVISORS:
        return True
    return clean.split()[0].lower() == "shane"


def ensure_guarantee_roster_advisors(roster: Dict[str, List[AdvisorPayrollRow]]) -> bool:
    """Move known guarantee advisors onto the guarantee plan. Returns True if roster changed."""
    changed = False
    for plan in PLAN_ORDER:
        if plan == PLAN_NEW_ADVISORS_GUARANTEE:
            continue
        rows = roster.get(plan, [])
        for row in list(rows):
            if not _name_on_guarantee_plan(row.name):
                continue
            rows.remove(row)
            row.plan_type = PLAN_NEW_ADVISORS_GUARANTEE
            apply_plan_defaults(row, PLAN_NEW_ADVISORS_GUARANTEE)
            roster.setdefault(PLAN_NEW_ADVISORS_GUARANTEE, []).append(row)
            changed = True
    return changed


def _clone_row(row: AdvisorPayrollRow) -> AdvisorPayrollRow:
    return ensure_advisor_row_fields(AdvisorPayrollRow(**copy.deepcopy(row.__dict__)))


def normalize_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> Dict[str, List[AdvisorPayrollRow]]:
    for plan, rows in roster.items():
        for i, row in enumerate(rows):
            rows[i] = ensure_advisor_row_fields(row)
    return roster


def clone_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> Dict[str, List[AdvisorPayrollRow]]:
    return {plan: [_clone_row(row) for row in rows] for plan, rows in roster.items()}


def default_roster() -> Dict[str, List[AdvisorPayrollRow]]:
    return {
        PLAN_SEASONED: [
            apply_plan_defaults(
                AdvisorPayrollRow("Tom LeBlanc", plan_type=PLAN_SEASONED, advisor_id="049"),
                PLAN_SEASONED,
            ),
            apply_plan_defaults(
                AdvisorPayrollRow("Richard Maldonado", plan_type=PLAN_SEASONED, advisor_id="3490"),
                PLAN_SEASONED,
            ),
        ],
        PLAN_NEW_ADVISORS: [
            apply_plan_defaults(
                AdvisorPayrollRow("Matthew Garrigan", plan_type=PLAN_NEW_ADVISORS, advisor_id="3809"),
                PLAN_NEW_ADVISORS,
            ),
        ],
        PLAN_NEW_ADVISORS_GUARANTEE: [
            apply_plan_defaults(
                AdvisorPayrollRow(
                    "Brady Hatcher",
                    plan_type=PLAN_NEW_ADVISORS_GUARANTEE,
                    advisor_id="3816",
                ),
                PLAN_NEW_ADVISORS_GUARANTEE,
            ),
        ],
    }


def flatten_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> List[AdvisorPayrollRow]:
    rows: List[AdvisorPayrollRow] = []
    for plan in PLAN_ORDER:
        rows.extend(roster.get(plan, []))
    return rows


def _serialize_row(row: AdvisorPayrollRow) -> dict:
    return {
        "name": row.name,
        "plan_type": row.plan_type,
        "advisor_id": row.advisor_id,
        "top_labor_rate": row.top_labor_rate,
        "weekly_guarantee": row.weekly_guarantee,
        "guarantee_expires": format_guarantee_expires(row.guarantee_expires),
    }


def serialize_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> dict:
    return {plan: [_serialize_row(row) for row in roster.get(plan, [])] for plan in PLAN_ORDER}


def roster_from_saved_data(data: dict) -> Dict[str, List[AdvisorPayrollRow]]:
    roster = {plan: [] for plan in PLAN_ORDER}
    for raw_plan, items in data.items():
        for item in items:
            plan_type = normalize_advisor_plan_type(item.get("plan_type", raw_plan))
            if plan_type not in PLAN_ORDER:
                continue
            meta = PLAN_META.get(plan_type, PLAN_META[PLAN_NEW_ADVISORS])
            row = AdvisorPayrollRow(
                name=item["name"],
                plan_type=plan_type,
                advisor_id=str(item.get("advisor_id", "") or ""),
                top_labor_rate=float(item.get("top_labor_rate", meta["top_labor_rate"])),
                weekly_guarantee=float(
                    item.get("weekly_guarantee", meta.get("weekly_guarantee", 1000.0))
                ),
                guarantee_expires=format_guarantee_expires(item.get("guarantee_expires", "")),
            )
            roster[plan_type].append(apply_plan_defaults(row, plan_type))
    roster = normalize_roster(roster)
    if not any(roster.values()):
        return clone_roster(default_roster())
    return roster


def load_roster() -> Dict[str, List[AdvisorPayrollRow]]:
    from lib.roster_supabase_sync import ROSTER_KEY_ADVISORS, load_roster_data

    remote = load_roster_data(ROSTER_KEY_ADVISORS)
    if remote is not None:
        roster = roster_from_saved_data(remote)
    elif ROSTER_PATH.exists():
        try:
            data = json.loads(ROSTER_PATH.read_text())
            roster = roster_from_saved_data(data)
        except (json.JSONDecodeError, OSError):
            roster = clone_roster(default_roster())
    else:
        roster = clone_roster(default_roster())
    if ensure_guarantee_roster_advisors(roster):
        save_roster(roster)
    return roster


def save_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> None:
    from lib.roster_supabase_sync import ROSTER_KEY_ADVISORS, save_roster_data

    data = serialize_roster(roster)
    try:
        ROSTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROSTER_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
    save_roster_data(ROSTER_KEY_ADVISORS, data, session_error_key="_advisor_roster_sync_error")


def all_advisor_names(roster: Dict[str, List[AdvisorPayrollRow]]) -> List[str]:
    return [row.name for row in flatten_roster(roster)]


def add_advisor(
    roster: Dict[str, List[AdvisorPayrollRow]],
    plan_type: str,
    name: str,
    advisor_id: str = "",
    guarantee_expires: str = "",
) -> Tuple[bool, str]:
    if plan_type not in PLAN_ORDER:
        return False, "Unknown pay plan."
    clean_name = " ".join(name.split())
    if not clean_name:
        return False, "Enter an advisor name."
    if clean_name in all_advisor_names(roster):
        return False, f"{clean_name} is already on the roster."

    row = apply_plan_defaults(
        AdvisorPayrollRow(
            clean_name,
            plan_type=plan_type,
            advisor_id=str(advisor_id or "").strip(),
            guarantee_expires=format_guarantee_expires(guarantee_expires),
        ),
        plan_type,
    )
    roster.setdefault(plan_type, []).append(row)
    return True, f"Added {clean_name} to {PLAN_LABELS[plan_type]}."


def remove_advisor(
    roster: Dict[str, List[AdvisorPayrollRow]],
    plan_type: str,
    index: int,
) -> Tuple[bool, str]:
    rows = roster.get(plan_type, [])
    if index < 0 or index >= len(rows):
        return False, "Advisor not found."
    removed = rows.pop(index)
    return True, f"Removed {removed.name} from {PLAN_LABELS[plan_type]}."


def change_advisor_plan(
    roster: Dict[str, List[AdvisorPayrollRow]],
    from_plan: str,
    index: int,
    to_plan: str,
) -> Tuple[bool, str]:
    if from_plan == to_plan:
        return False, "Choose a different pay plan."
    if from_plan not in PLAN_ORDER or to_plan not in PLAN_ORDER:
        return False, "Unknown pay plan."

    rows = roster.get(from_plan, [])
    if index < 0 or index >= len(rows):
        return False, "Advisor not found."

    row = rows.pop(index)
    row.plan_type = to_plan
    apply_plan_defaults(row, to_plan)
    roster.setdefault(to_plan, []).append(row)
    return True, f"Moved {row.name} to {PLAN_LABELS[to_plan]}."


def update_advisor(
    roster: Dict[str, List[AdvisorPayrollRow]],
    plan_type: str,
    index: int,
    advisor_id: str,
    top_labor_rate: Optional[float] = None,
    guarantee_expires: Optional[str] = None,
) -> Tuple[bool, str]:
    rows = roster.get(plan_type, [])
    if index < 0 or index >= len(rows):
        return False, "Advisor not found."
    row = rows[index]
    row.advisor_id = str(advisor_id or "").strip()
    if plan_type in (PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE) and top_labor_rate is not None:
        row.top_labor_rate = float(top_labor_rate)
    if plan_has_weekly_guarantee(plan_type) and guarantee_expires is not None:
        row.guarantee_expires = format_guarantee_expires(guarantee_expires)
    return True, f"Updated {row.name}."


def reset_roster() -> Dict[str, List[AdvisorPayrollRow]]:
    return clone_roster(default_roster())

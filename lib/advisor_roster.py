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


def _clone_row(row: AdvisorPayrollRow) -> AdvisorPayrollRow:
    return ensure_advisor_row_fields(AdvisorPayrollRow(**copy.deepcopy(row.__dict__)))


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
            apply_plan_defaults(
                AdvisorPayrollRow(
                    "Felix Figueroa",
                    plan_type=PLAN_NEW_ADVISORS,
                    advisor_id="3812",
                    top_labor_rate=12.0,
                ),
                PLAN_NEW_ADVISORS,
            ),
            apply_plan_defaults(
                AdvisorPayrollRow("Brady Hatcher", plan_type=PLAN_NEW_ADVISORS, advisor_id="3816"),
                PLAN_NEW_ADVISORS,
            ),
        ],
        PLAN_NEW_ADVISORS_GUARANTEE: [],
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
    if not any(roster.values()):
        return clone_roster(default_roster())
    return roster


def load_roster() -> Dict[str, List[AdvisorPayrollRow]]:
    if ROSTER_PATH.exists():
        data = json.loads(ROSTER_PATH.read_text())
        return roster_from_saved_data(data)
    return clone_roster(default_roster())


def save_roster(roster: Dict[str, List[AdvisorPayrollRow]]) -> None:
    ROSTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_PATH.write_text(json.dumps(serialize_roster(roster), indent=2))


def all_advisor_names(roster: Dict[str, List[AdvisorPayrollRow]]) -> List[str]:
    return [row.name for row in flatten_roster(roster)]


def add_advisor(
    roster: Dict[str, List[AdvisorPayrollRow]],
    plan_type: str,
    name: str,
    advisor_id: str = "",
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

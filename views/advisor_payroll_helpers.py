"""Service advisor payroll session helpers."""

from __future__ import annotations

import re
from typing import Dict, Optional

import streamlit as st

from lib.advisor_payroll_calc import (
    ALIGNMENT_BONUS_AMOUNT,
    AdvisorPayrollRow,
    ensure_advisor_row_fields,
)
from lib.advisor_payroll_parser import report_by_name
from lib.advisor_roster import flatten_roster, load_roster, normalize_roster

ADVISOR_FIELDS = {
    "total_hours": 0.0,
    "write_off_hours": 0.0,
    "policy_expense": 0.0,
    "num_advisors": 4,
    "warranty_labor_rate": 264.03,
    "hours_deducted": 0.0,
    "pay_period_objective": 200.0,
    "hours_sold": 0.0,
    "repair_order_count": 0.0,
    "parts_labor_sales": 0.0,
    "parts_sales": 0.0,
    "variable_amount": ALIGNMENT_BONUS_AMOUNT,
    "menu_presentation": 0.0,
    "parts_commission_rate": 0.03,
    "spiff": 0.0,
    "hourly_pay_override": 0.0,
}

CSI_TIER_KEYS = ["none", "top", "middle", "bottom"]
ADVISOR_TOGGLE_FIELDS = ("csi_tier", "cp_bump", "alignment_bonus")
ADVISOR_TEXT_FIELDS = ("notes",)


def _name_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()


def advisor_field_key(name: str, field: str) -> str:
    return f"advisor_pay_{_name_slug(name)}_{field}"


def adv_key(idx: int, field: str) -> str:
    """Legacy index-based key — use advisor_field_key(name, field) instead."""
    rows = flatten_roster(st.session_state.get("advisor_roster", {}))
    if 0 <= idx < len(rows):
        return advisor_field_key(rows[idx].name, field)
    return f"adv_{idx}_{field}"


def advisor_section_open_key(name: str) -> str:
    return f"advisor_open_{_name_slug(name)}"


def advisor_section_toggle_key(name: str) -> str:
    return f"advisor_toggle_{_name_slug(name)}"


def clear_advisor_field_keys():
    for key in list(st.session_state.keys()):
        if key.startswith("advisor_pay_"):
            del st.session_state[key]
        elif key.startswith("adv_"):
            del st.session_state[key]


def _field_default(row: AdvisorPayrollRow, field: str, default):
    if field == "csi_tier":
        return row.csi_tier or "none"
    if field == "cp_bump":
        return bool(getattr(row, "cp_bump_qualified", False))
    if field == "alignment_bonus":
        return bool(getattr(row, "alignment_bonus_qualified", False))
    if field == "notes":
        return str(row.notes or "")
    return getattr(row, field, default)


def _capture_advisor_store_entry(row: AdvisorPayrollRow) -> dict:
    store = st.session_state.get("advisor_value_store", {})
    saved = store.get(row.name, {})
    entry: Dict[str, object] = {}

    for field, default in ADVISOR_FIELDS.items():
        key = advisor_field_key(row.name, field)
        if key in st.session_state:
            entry[field] = st.session_state[key]
        elif field in saved:
            entry[field] = saved[field]

    for field in ADVISOR_TOGGLE_FIELDS:
        key = advisor_field_key(row.name, field)
        if key in st.session_state:
            entry[field] = st.session_state[key]
        elif field in saved:
            entry[field] = saved[field]

    notes_key = advisor_field_key(row.name, "notes")
    if notes_key in st.session_state:
        entry["notes"] = st.session_state[notes_key]
    elif "notes" in saved:
        entry["notes"] = saved["notes"]

    return entry


def refresh_advisor_value_store():
    """Persist widget values so collapsed advisor sections keep their data."""
    rows = flatten_roster(st.session_state.advisor_roster)
    store = st.session_state.setdefault("advisor_value_store", {})
    for row in rows:
        entry = _capture_advisor_store_entry(row)
        if entry:
            store[row.name] = {**store.get(row.name, {}), **entry}


def apply_advisor_value_store():
    """Restore advisor widget values for collapsed sections and missing keys."""
    rows = flatten_roster(st.session_state.advisor_roster)
    store = st.session_state.get("advisor_value_store", {})

    def _hydrate(row: AdvisorPayrollRow, field: str, value):
        key = advisor_field_key(row.name, field)
        is_open = bool(st.session_state.get(advisor_section_open_key(row.name), False))
        if not is_open or key not in st.session_state:
            st.session_state[key] = value

    for row in rows:
        saved = store.get(row.name, {})
        for field, default in ADVISOR_FIELDS.items():
            val = saved.get(field, _field_default(row, field, default))
            _hydrate(row, field, float(val if val is not None else default))
        _hydrate(row, "csi_tier", saved.get("csi_tier", _field_default(row, "csi_tier", "none")))
        _hydrate(
            row,
            "cp_bump",
            bool(saved.get("cp_bump", _field_default(row, "cp_bump", False))),
        )
        _hydrate(
            row,
            "alignment_bonus",
            bool(saved.get("alignment_bonus", _field_default(row, "alignment_bonus", False))),
        )
        _hydrate(row, "notes", str(saved.get("notes", _field_default(row, "notes", "")) or ""))


def persist_advisor_changes(advisor_idx: int | None = None, advisor_name: str | None = None):
    """Capture widget values and auto-save the in-progress advisor payroll."""
    if advisor_name:
        st.session_state[advisor_section_open_key(advisor_name)] = True
    elif advisor_idx is not None:
        rows = flatten_roster(st.session_state.advisor_roster)
        if 0 <= advisor_idx < len(rows):
            st.session_state[advisor_section_open_key(rows[advisor_idx].name)] = True

    refresh_advisor_value_store()
    from lib.payroll_autosave import autosave_advisor_payroll

    autosave_advisor_payroll()
    st.rerun()


def toggle_advisor_section(name: str):
    """Collapse or expand an advisor section without losing entered values."""
    open_key = advisor_section_open_key(name)
    was_open = bool(st.session_state.get(open_key, False))
    if was_open:
        refresh_advisor_value_store()
        from lib.payroll_autosave import autosave_advisor_payroll

        autosave_advisor_payroll()
        st.session_state[open_key] = False
    else:
        st.session_state[open_key] = True


def _migrate_legacy_section_open_keys(rows: list[AdvisorPayrollRow]):
    for i, row in enumerate(rows):
        legacy = f"adv_{i}_expanded"
        if legacy in st.session_state:
            st.session_state[advisor_section_open_key(row.name)] = bool(st.session_state.pop(legacy))


def _migrate_legacy_index_keys(rows: list[AdvisorPayrollRow]):
    for i, row in enumerate(rows):
        for field in list(ADVISOR_FIELDS) + list(ADVISOR_TOGGLE_FIELDS) + list(ADVISOR_TEXT_FIELDS):
            legacy = f"adv_{i}_{field}"
            if legacy in st.session_state:
                st.session_state[advisor_field_key(row.name, field)] = st.session_state.pop(legacy)


def capture_advisor_values(rows: list[AdvisorPayrollRow]) -> dict:
    values: Dict[str, dict] = {}
    for row in rows:
        values[row.name] = {
            "hours_sold": float(
                st.session_state.get(advisor_field_key(row.name, "hours_sold"), row.hours_sold) or 0
            ),
            "parts_sales": float(
                st.session_state.get(advisor_field_key(row.name, "parts_sales"), row.parts_sales) or 0
            ),
            "parts_labor_sales": float(
                st.session_state.get(
                    advisor_field_key(row.name, "parts_labor_sales"), row.parts_labor_sales
                )
                or 0
            ),
            "repair_order_count": float(
                st.session_state.get(
                    advisor_field_key(row.name, "repair_order_count"), row.repair_order_count
                )
                or 0
            ),
            "spiff": float(st.session_state.get(advisor_field_key(row.name, "spiff"), row.spiff) or 0),
            "cp_bump": bool(
                st.session_state.get(advisor_field_key(row.name, "cp_bump"), row.cp_bump_qualified)
            ),
            "alignment_bonus": bool(
                st.session_state.get(
                    advisor_field_key(row.name, "alignment_bonus"), row.alignment_bonus_qualified
                )
            ),
            "csi_tier": st.session_state.get(advisor_field_key(row.name, "csi_tier"), row.csi_tier or "none"),
            "notes": str(st.session_state.get(advisor_field_key(row.name, "notes"), row.notes) or ""),
        }
    return values


def _init_advisor_fields(row: AdvisorPayrollRow, overrides: Optional[dict] = None):
    overrides = overrides or {}
    for field, default in ADVISOR_FIELDS.items():
        key = advisor_field_key(row.name, field)
        roster_val = getattr(row, field, default)
        if field in overrides:
            st.session_state[key] = float(overrides[field] or 0)
        else:
            st.session_state[key] = float(roster_val if roster_val is not None else default)

    st.session_state[advisor_field_key(row.name, "csi_tier")] = overrides.get(
        "csi_tier", row.csi_tier or "none"
    )
    st.session_state[advisor_field_key(row.name, "cp_bump")] = overrides.get(
        "cp_bump", row.cp_bump_qualified
    )
    st.session_state[advisor_field_key(row.name, "alignment_bonus")] = overrides.get(
        "alignment_bonus", row.alignment_bonus_qualified
    )
    st.session_state[advisor_field_key(row.name, "notes")] = overrides.get("notes", row.notes or "")


def apply_roster_to_session(roster: dict, values_by_name: Optional[dict] = None):
    clear_advisor_field_keys()
    st.session_state.advisor_roster = normalize_roster(roster)
    rows = flatten_roster(st.session_state.advisor_roster)
    values_by_name = values_by_name or {}
    for row in rows:
        _init_advisor_fields(row, overrides=values_by_name.get(row.name))
    refresh_advisor_value_store()


def init_advisor_payroll_session():
    from lib.advisor_roster import ensure_guarantee_roster_advisors, save_roster

    if "advisor_roster" not in st.session_state:
        apply_roster_to_session(load_roster())
    else:
        st.session_state.advisor_roster = normalize_roster(st.session_state.advisor_roster)
        if ensure_guarantee_roster_advisors(st.session_state.advisor_roster):
            save_roster(st.session_state.advisor_roster)
    if "advisor_report_loaded" not in st.session_state:
        st.session_state.advisor_report_loaded = False

    rows = flatten_roster(st.session_state.advisor_roster)
    _migrate_legacy_section_open_keys(rows)
    _migrate_legacy_index_keys(rows)
    apply_advisor_value_store()


def apply_advisor_report_to_session(report_rows) -> int:
    """Apply parsed payroll report rows to matching advisors."""
    by_name = report_by_name(report_rows)
    matched = 0
    rows = flatten_roster(st.session_state.advisor_roster)
    for row in rows:
        report = by_name.get(row.name.upper())
        if not report:
            continue
        st.session_state[advisor_field_key(row.name, "hours_sold")] = float(report.tech_hours)
        st.session_state[advisor_field_key(row.name, "parts_sales")] = float(report.parts_sales)
        st.session_state[advisor_field_key(row.name, "parts_labor_sales")] = float(
            report.parts_labor_sales
        )
        st.session_state[advisor_field_key(row.name, "repair_order_count")] = float(
            report.repair_order_count
        )
        row.advisor_id = report.advisor_id
        matched += 1
    st.session_state.advisor_report_loaded = matched > 0
    refresh_advisor_value_store()
    from lib.payroll_autosave import autosave_advisor_payroll

    autosave_advisor_payroll()
    return matched


def _session_bool(name: str, field: str, default: bool = False) -> bool:
    key = advisor_field_key(name, field)
    if key in st.session_state:
        return bool(st.session_state[key])
    saved = st.session_state.get("advisor_value_store", {}).get(name, {})
    return bool(saved.get(field, default))


def _session_text(name: str, field: str, default: str = "") -> str:
    key = advisor_field_key(name, field)
    if key in st.session_state:
        return str(st.session_state[key] or "")
    saved = st.session_state.get("advisor_value_store", {}).get(name, {})
    return str(saved.get(field, default) or "")


def _session_float(name: str, field: str, default: float = 0.0) -> float:
    key = advisor_field_key(name, field)
    if key in st.session_state:
        return float(st.session_state[key] or 0)
    saved = st.session_state.get("advisor_value_store", {}).get(name, {})
    return float(saved.get(field, default) or 0)


def sync_advisor(row: AdvisorPayrollRow) -> AdvisorPayrollRow:
    name = row.name
    override = _session_float(name, "hourly_pay_override", 0)
    csi_tier = _session_text(name, "csi_tier", row.csi_tier or "none")
    if csi_tier not in CSI_TIER_KEYS:
        csi_tier = "none"
    return AdvisorPayrollRow(
        name=row.name,
        plan_type=row.plan_type,
        advisor_id=row.advisor_id,
        top_labor_rate=row.top_labor_rate,
        weekly_guarantee=row.weekly_guarantee,
        guarantee_expires=getattr(row, "guarantee_expires", ""),
        total_hours=_session_float(name, "total_hours", row.total_hours),
        write_off_hours=_session_float(name, "write_off_hours", row.write_off_hours),
        policy_expense=_session_float(name, "policy_expense", row.policy_expense),
        num_advisors=int(_session_float(name, "num_advisors", row.num_advisors)),
        warranty_labor_rate=_session_float(name, "warranty_labor_rate", row.warranty_labor_rate),
        hours_deducted=_session_float(name, "hours_deducted", row.hours_deducted),
        pay_period_objective=_session_float(name, "pay_period_objective", row.pay_period_objective),
        hours_sold=_session_float(name, "hours_sold", row.hours_sold),
        repair_order_count=_session_float(name, "repair_order_count", row.repair_order_count),
        parts_labor_sales=_session_float(name, "parts_labor_sales", row.parts_labor_sales),
        parts_sales=_session_float(name, "parts_sales", row.parts_sales),
        cp_bump_qualified=_session_bool(name, "cp_bump", row.cp_bump_qualified),
        alignment_bonus_qualified=_session_bool(name, "alignment_bonus", row.alignment_bonus_qualified),
        csi_tier=csi_tier,
        variable_amount=_session_float(name, "variable_amount", row.variable_amount),
        menu_presentation=_session_float(name, "menu_presentation", row.menu_presentation),
        parts_commission_rate=_session_float(name, "parts_commission_rate", row.parts_commission_rate),
        spiff=_session_float(name, "spiff", row.spiff),
        notes=_session_text(name, "notes", row.notes),
        hourly_pay_override=override if override > 0 else None,
    )


def all_advisors_synced() -> list:
    rows = flatten_roster(st.session_state.advisor_roster)
    return [
        sync_advisor(ensure_advisor_row_fields(AdvisorPayrollRow(**row.__dict__))) for row in rows
    ]

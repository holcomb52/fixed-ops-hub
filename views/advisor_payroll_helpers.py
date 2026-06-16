"""Service advisor payroll session helpers."""

from __future__ import annotations

from typing import Dict, Optional

import streamlit as st

from lib.advisor_payroll_calc import (
    ALIGNMENT_BONUS_AMOUNT,
    AdvisorPayrollRow,
)
from lib.advisor_payroll_parser import report_by_name
from lib.advisor_roster import flatten_roster, load_roster

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


def adv_key(idx: int, field: str) -> str:
    return f"adv_{idx}_{field}"


def clear_advisor_field_keys():
    for key in list(st.session_state.keys()):
        if key.startswith("adv_"):
            del st.session_state[key]


def _capture_advisor_store_entry(i: int, row: AdvisorPayrollRow) -> dict:
    entry: Dict[str, object] = {}
    for field in ADVISOR_FIELDS:
        key = adv_key(i, field)
        if key in st.session_state:
            entry[field] = st.session_state[key]
    for field in ADVISOR_TOGGLE_FIELDS:
        key = adv_key(i, field)
        if key in st.session_state:
            entry[field] = st.session_state[key]
    notes_key = adv_key(i, "notes")
    if notes_key in st.session_state:
        entry["notes"] = st.session_state[notes_key]
    return entry


def refresh_advisor_value_store():
    """Persist widget values so collapsed advisor sections keep their data."""
    rows = flatten_roster(st.session_state.advisor_roster)
    store = st.session_state.setdefault("advisor_value_store", {})
    for i, row in enumerate(rows):
        entry = _capture_advisor_store_entry(i, row)
        if entry:
            store[row.name] = {**store.get(row.name, {}), **entry}


def apply_advisor_value_store():
    """Restore advisor widget values removed when sections are collapsed."""
    rows = flatten_roster(st.session_state.advisor_roster)
    store = st.session_state.get("advisor_value_store", {})
    for i, row in enumerate(rows):
        saved = store.get(row.name, {})
        for field, default in ADVISOR_FIELDS.items():
            key = adv_key(i, field)
            if key not in st.session_state:
                val = saved.get(field, getattr(row, field, default))
                st.session_state[key] = float(val if val is not None else default)
        if adv_key(i, "csi_tier") not in st.session_state:
            st.session_state[adv_key(i, "csi_tier")] = saved.get("csi_tier", row.csi_tier or "none")
        if adv_key(i, "cp_bump") not in st.session_state:
            st.session_state[adv_key(i, "cp_bump")] = bool(
                saved.get("cp_bump", row.cp_bump_qualified)
            )
        if adv_key(i, "alignment_bonus") not in st.session_state:
            st.session_state[adv_key(i, "alignment_bonus")] = bool(
                saved.get("alignment_bonus", row.alignment_bonus_qualified)
            )


def capture_advisor_values(rows: list[AdvisorPayrollRow]) -> dict:
    values: Dict[str, dict] = {}
    for i, row in enumerate(rows):
        values[row.name] = {
            "hours_sold": float(st.session_state.get(adv_key(i, "hours_sold"), row.hours_sold) or 0),
            "parts_sales": float(st.session_state.get(adv_key(i, "parts_sales"), row.parts_sales) or 0),
            "parts_labor_sales": float(
                st.session_state.get(adv_key(i, "parts_labor_sales"), row.parts_labor_sales) or 0
            ),
            "repair_order_count": float(
                st.session_state.get(adv_key(i, "repair_order_count"), row.repair_order_count) or 0
            ),
            "spiff": float(st.session_state.get(adv_key(i, "spiff"), row.spiff) or 0),
            "cp_bump": bool(st.session_state.get(adv_key(i, "cp_bump"), row.cp_bump_qualified)),
            "alignment_bonus": bool(
                st.session_state.get(adv_key(i, "alignment_bonus"), row.alignment_bonus_qualified)
            ),
            "csi_tier": st.session_state.get(adv_key(i, "csi_tier"), row.csi_tier or "none"),
            "notes": str(st.session_state.get(adv_key(i, "notes"), row.notes) or ""),
        }
    return values


def _init_advisor_fields(i: int, row: AdvisorPayrollRow, overrides: Optional[dict] = None):
    overrides = overrides or {}
    for field, default in ADVISOR_FIELDS.items():
        key = adv_key(i, field)
        roster_val = getattr(row, field, default)
        if field in overrides:
            st.session_state[key] = float(overrides[field] or 0)
        else:
            st.session_state[key] = float(roster_val if roster_val is not None else default)

    st.session_state[adv_key(i, "csi_tier")] = overrides.get("csi_tier", row.csi_tier or "none")
    st.session_state[adv_key(i, "cp_bump")] = overrides.get("cp_bump", row.cp_bump_qualified)
    st.session_state[adv_key(i, "alignment_bonus")] = overrides.get(
        "alignment_bonus", row.alignment_bonus_qualified
    )
    st.session_state[adv_key(i, "notes")] = overrides.get("notes", row.notes or "")


def apply_roster_to_session(roster: dict, values_by_name: Optional[dict] = None):
    clear_advisor_field_keys()
    st.session_state.advisor_roster = roster
    rows = flatten_roster(roster)
    values_by_name = values_by_name or {}
    for i, row in enumerate(rows):
        _init_advisor_fields(i, row, overrides=values_by_name.get(row.name))


def init_advisor_payroll_session():
    if "advisor_roster" not in st.session_state:
        apply_roster_to_session(load_roster())
    if "advisor_report_loaded" not in st.session_state:
        st.session_state.advisor_report_loaded = False

    rows = flatten_roster(st.session_state.advisor_roster)
    for i, row in enumerate(rows):
        for field, default in ADVISOR_FIELDS.items():
            key = adv_key(i, field)
            if key not in st.session_state:
                val = getattr(row, field, default)
                st.session_state[key] = float(val if val is not None else default)
        if adv_key(i, "csi_tier") not in st.session_state:
            st.session_state[adv_key(i, "csi_tier")] = row.csi_tier or "none"
        if adv_key(i, "cp_bump") not in st.session_state:
            st.session_state[adv_key(i, "cp_bump")] = bool(getattr(row, "cp_bump_qualified", False))
        if adv_key(i, "alignment_bonus") not in st.session_state:
            st.session_state[adv_key(i, "alignment_bonus")] = bool(
                getattr(row, "alignment_bonus_qualified", False)
            )
        if adv_key(i, "notes") not in st.session_state:
            st.session_state[adv_key(i, "notes")] = row.notes or ""


def apply_advisor_report_to_session(report_rows) -> int:
    """Apply parsed payroll report rows to matching advisors."""
    by_name = report_by_name(report_rows)
    matched = 0
    rows = flatten_roster(st.session_state.advisor_roster)
    for i, row in enumerate(rows):
        report = by_name.get(row.name.upper())
        if not report:
            continue
        st.session_state[adv_key(i, "hours_sold")] = float(report.tech_hours)
        st.session_state[adv_key(i, "parts_sales")] = float(report.parts_sales)
        st.session_state[adv_key(i, "parts_labor_sales")] = float(report.parts_labor_sales)
        st.session_state[adv_key(i, "repair_order_count")] = float(report.repair_order_count)
        row.advisor_id = report.advisor_id
        matched += 1
    st.session_state.advisor_report_loaded = matched > 0
    refresh_advisor_value_store()
    return matched


def sync_advisor(idx: int, row: AdvisorPayrollRow) -> AdvisorPayrollRow:
    override = float(st.session_state.get(adv_key(idx, "hourly_pay_override"), 0) or 0)
    csi_tier = st.session_state.get(adv_key(idx, "csi_tier"), "none")
    if csi_tier not in CSI_TIER_KEYS:
        csi_tier = "none"
    return AdvisorPayrollRow(
        name=row.name,
        plan_type=row.plan_type,
        advisor_id=row.advisor_id,
        top_labor_rate=row.top_labor_rate,
        weekly_guarantee=row.weekly_guarantee,
        total_hours=float(st.session_state[adv_key(idx, "total_hours")]),
        write_off_hours=float(st.session_state[adv_key(idx, "write_off_hours")]),
        policy_expense=float(st.session_state[adv_key(idx, "policy_expense")]),
        num_advisors=int(st.session_state[adv_key(idx, "num_advisors")]),
        warranty_labor_rate=float(st.session_state[adv_key(idx, "warranty_labor_rate")]),
        hours_deducted=float(st.session_state[adv_key(idx, "hours_deducted")]),
        pay_period_objective=float(st.session_state[adv_key(idx, "pay_period_objective")]),
        hours_sold=float(st.session_state[adv_key(idx, "hours_sold")]),
        repair_order_count=float(st.session_state[adv_key(idx, "repair_order_count")]),
        parts_labor_sales=float(st.session_state[adv_key(idx, "parts_labor_sales")]),
        parts_sales=float(st.session_state[adv_key(idx, "parts_sales")]),
        cp_bump_qualified=bool(st.session_state.get(adv_key(idx, "cp_bump"), False)),
        alignment_bonus_qualified=bool(st.session_state.get(adv_key(idx, "alignment_bonus"), False)),
        csi_tier=csi_tier,
        variable_amount=float(st.session_state[adv_key(idx, "variable_amount")]),
        menu_presentation=float(st.session_state[adv_key(idx, "menu_presentation")]),
        parts_commission_rate=float(st.session_state[adv_key(idx, "parts_commission_rate")]),
        spiff=float(st.session_state[adv_key(idx, "spiff")]),
        notes=str(st.session_state.get(adv_key(idx, "notes"), "") or ""),
        hourly_pay_override=override if override > 0 else None,
    )


def all_advisors_synced() -> list:
    rows = flatten_roster(st.session_state.advisor_roster)
    return [sync_advisor(i, AdvisorPayrollRow(**row.__dict__)) for i, row in enumerate(rows)]

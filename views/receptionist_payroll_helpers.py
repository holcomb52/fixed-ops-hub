"""Receptionist payroll session helpers."""

from __future__ import annotations

import re
from typing import Dict, Optional

import streamlit as st

from lib.receptionist_payroll_calc import (
    CSI_TIER_KEYS,
    CSI_TIER_NONE,
    RECEPTIONIST_CSI_TIER_OPTIONS,
    TIRE_PAY_RATE,
    ReceptionistPayrollRow,
    ensure_receptionist_row_fields,
)
from lib.receptionist_payroll_parser import report_by_code, report_by_last_name
from lib.receptionist_roster import flatten_roster, load_roster, normalize_roster, save_roster, update_employee

RECEPTIONIST_FIELDS = {
    "appointments_set": 0.0,
    "tires_sold": 0.0,
    "appointment_rate": 0.0,
    "bonus_amount": 0.0,
    "spiff": 0.0,
}


def rec_key(name: str, field: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return f"rec_{slug}_{field}"


def section_open_key(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return f"receptionist_open_{slug}"


def section_toggle_key(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return f"receptionist_toggle_{slug}"


def form_key(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return f"receptionist_form_{slug}"


def clear_receptionist_field_keys():
    for key in list(st.session_state.keys()):
        if key.startswith("receptionist_open_") or key.startswith("receptionist_toggle_"):
            continue
        if key.startswith("rec_"):
            del st.session_state[key]


def _tires_text_key(name: str) -> str:
    return rec_key(name, "tires_sold_input")


def _appointment_rate_text_key(name: str) -> str:
    return rec_key(name, "appointment_rate_input")


def _format_rate_text(rate: float) -> str:
    if not rate:
        return ""
    if float(rate).is_integer():
        return str(int(rate))
    return f"{float(rate):.2f}".rstrip("0").rstrip(".")


def _parse_appointment_rate(name: str, row: ReceptionistPayrollRow | None = None) -> float:
    text_key = _appointment_rate_text_key(name)
    if text_key in st.session_state:
        raw = str(st.session_state.get(text_key, "")).strip().replace("$", "")
        try:
            return max(float(raw) if raw else 0.0, 0.0)
        except ValueError:
            return 0.0
    store = st.session_state.get("receptionist_value_store", {}).get(name, {})
    if "appointment_rate" in store:
        return float(store["appointment_rate"] or 0)
    if row is not None:
        return float(row.appointment_rate or 0)
    return 0.0


def _parse_tires_value(name: str, row: ReceptionistPayrollRow | None = None) -> float:
    text_key = _tires_text_key(name)
    if text_key in st.session_state:
        raw = str(st.session_state.get(text_key, "")).strip()
        try:
            return max(float(raw) if raw else 0.0, 0.0)
        except ValueError:
            return 0.0
    num_key = rec_key(name, "tires_sold")
    if num_key in st.session_state:
        return float(st.session_state.get(num_key, 0) or 0)
    store = st.session_state.get("receptionist_value_store", {})
    if name in store and "tires_sold" in store[name]:
        return float(store[name]["tires_sold"] or 0)
    if row is not None:
        return float(row.tires_sold or 0)
    return 0.0


def _tires_widgets_active(name: str) -> bool:
    return _tires_text_key(name) in st.session_state or rec_key(name, "tires_sold") in st.session_state


def _capture_store_entry(row: ReceptionistPayrollRow) -> dict:
    store = st.session_state.get("receptionist_value_store", {})
    saved = store.get(row.name, {})
    entry: Dict[str, object] = {}
    for field in RECEPTIONIST_FIELDS:
        if field in ("tires_sold", "appointment_rate"):
            continue
        key = rec_key(row.name, field)
        if key in st.session_state:
            entry[field] = st.session_state[key]
        elif field in saved:
            entry[field] = saved[field]
    entry["appointment_rate"] = _parse_appointment_rate(row.name, row)
    entry["tires_sold"] = _parse_tires_value(row.name, row)
    label_key = rec_key(row.name, "bonus_label")
    if label_key in st.session_state:
        entry["bonus_label"] = st.session_state[label_key]
    elif "bonus_label" in saved:
        entry["bonus_label"] = saved["bonus_label"]
    warranty_key = rec_key(row.name, "warranty_bonus")
    if warranty_key in st.session_state:
        entry["warranty_bonus"] = st.session_state[warranty_key]
    elif "warranty_bonus" in saved:
        entry["warranty_bonus"] = saved["warranty_bonus"]
    csi_key = rec_key(row.name, "csi_tier")
    if csi_key in st.session_state:
        entry["csi_tier"] = st.session_state[csi_key]
    elif "csi_tier" in saved:
        entry["csi_tier"] = saved["csi_tier"]
    notes_key = rec_key(row.name, "notes")
    if notes_key in st.session_state:
        entry["notes"] = st.session_state[notes_key]
    elif "notes" in saved:
        entry["notes"] = saved["notes"]
    return entry


def refresh_receptionist_value_store():
    rows = flatten_roster(st.session_state.receptionist_roster)
    store = st.session_state.setdefault("receptionist_value_store", {})
    for row in rows:
        entry = _capture_store_entry(row)
        if entry:
            store[row.name] = {**store.get(row.name, {}), **entry}
        elif row.name not in store:
            store[row.name] = {}


def _commit_tires_input(name: str):
    save_receptionist_form(name)


def _commit_appointment_rate_input(name: str):
    save_receptionist_form(name)


def _commit_receptionist_inputs(name: str):
    """Copy live widget values into session keys the summary chart reads."""
    row = next(
        (item for item in flatten_roster(st.session_state.receptionist_roster) if item.name == name),
        None,
    )
    if row is None:
        return
    rate = _parse_appointment_rate(name, row)
    tires = _parse_tires_value(name, row)
    st.session_state[rec_key(name, "appointment_rate")] = rate
    st.session_state[rec_key(name, "tires_sold")] = tires
    store = st.session_state.setdefault("receptionist_value_store", {})
    store[name] = {**store.get(name, {}), "appointment_rate": rate, "tires_sold": tires}


def save_receptionist_form(name: str):
    """Commit pay-period fields for one receptionist and refresh the summary."""
    _commit_receptionist_inputs(name)
    st.session_state[section_open_key(name)] = True
    refresh_receptionist_value_store()
    from lib.payroll_autosave import autosave_receptionist_payroll

    autosave_receptionist_payroll()
    st.rerun()


def capture_open_receptionist_inputs():
    """Snapshot widget values before unrelated controls (export, confirm) rerun."""
    for row in flatten_roster(st.session_state.receptionist_roster):
        rate = _parse_appointment_rate(row.name, row)
        st.session_state[rec_key(row.name, "appointment_rate")] = rate
        if _tires_widgets_active(row.name):
            st.session_state[rec_key(row.name, "tires_sold")] = _parse_tires_value(row.name, row)
    refresh_receptionist_value_store()


def apply_roster_appointment_rates_to_session():
    """Restore $/appointment text and numeric keys before widgets render."""
    store = st.session_state.get("receptionist_value_store", {})
    for row in flatten_roster(st.session_state.receptionist_roster):
        saved = store.get(row.name, {})
        is_open = bool(st.session_state.get(section_open_key(row.name), False))
        rate = float(saved.get("appointment_rate", row.appointment_rate) or 0)
        num_key = rec_key(row.name, "appointment_rate")
        text_key = _appointment_rate_text_key(row.name)
        text_val = str(st.session_state.get(text_key, "")).strip()
        if not is_open or num_key not in st.session_state:
            st.session_state[num_key] = rate
        if not is_open or text_key not in st.session_state or not text_val:
            st.session_state[text_key] = _format_rate_text(rate)


def apply_receptionist_value_store():
    apply_roster_appointment_rates_to_session()
    store = st.session_state.get("receptionist_value_store", {})
    for row in flatten_roster(st.session_state.receptionist_roster):
        saved = store.get(row.name, {})
        is_open = bool(st.session_state.get(section_open_key(row.name), False))

        def _hydrate(key: str, value):
            if not is_open or key not in st.session_state:
                st.session_state[key] = value

        for field, default in RECEPTIONIST_FIELDS.items():
            if field in ("appointment_rate", "tires_sold"):
                continue
            val = saved.get(field, getattr(row, field, default))
            _hydrate(rec_key(row.name, field), float(val if val is not None else default))
        tires = float(saved.get("tires_sold", _parse_tires_value(row.name, row)) or 0)
        _hydrate(rec_key(row.name, "tires_sold"), tires)
        _hydrate(_tires_text_key(row.name), str(int(tires)) if tires else "")
        _hydrate(rec_key(row.name, "bonus_label"), saved.get("bonus_label", row.bonus_label or "Bonus"))
        _hydrate(rec_key(row.name, "warranty_bonus"), bool(saved.get("warranty_bonus", False)))
        _hydrate(rec_key(row.name, "csi_tier"), saved.get("csi_tier", CSI_TIER_NONE))
        _hydrate(rec_key(row.name, "notes"), str(saved.get("notes", row.notes) or ""))


def _read_appointment_rate(name: str, row: ReceptionistPayrollRow) -> float:
    return _parse_appointment_rate(name, row)


def persist_appointment_rate(name: str):
    for row in flatten_roster(st.session_state.receptionist_roster):
        if row.name != name:
            continue
        rate = _read_appointment_rate(name, row)
        update_employee(st.session_state.receptionist_roster, name, appointment_rate=rate)
        save_roster(st.session_state.receptionist_roster)
        store = st.session_state.setdefault("receptionist_value_store", {})
        store[name] = {**store.get(name, {}), "appointment_rate": rate}
        return


def persist_appointment_rate_change(name: str):
    """Save only when the $/appointment field changes."""
    persist_appointment_rate(name)
    refresh_receptionist_value_store()
    from lib.payroll_autosave import autosave_receptionist_payroll

    autosave_receptionist_payroll()


def sync_all_appointment_rates_to_roster():
    changed = False
    for row in flatten_roster(st.session_state.receptionist_roster):
        key = rec_key(row.name, "appointment_rate")
        if key not in st.session_state:
            continue
        rate = float(st.session_state.get(key, row.appointment_rate) or 0)
        if rate != row.appointment_rate:
            update_employee(st.session_state.receptionist_roster, row.name, appointment_rate=rate)
            changed = True
    if changed:
        save_roster(st.session_state.receptionist_roster)


def _saved_field(row: ReceptionistPayrollRow, field: str, default):
    store = st.session_state.get("receptionist_value_store", {})
    saved = store.get(row.name, {})
    if field in saved:
        return saved[field]
    return getattr(row, field, default)


def _session_float(row: ReceptionistPayrollRow, field: str, default: float = 0.0) -> float:
    if field == "tires_sold":
        return _parse_tires_value(row.name, row)
    if field == "appointment_rate":
        return _read_appointment_rate(row.name, row)
    key = rec_key(row.name, field)
    if key in st.session_state:
        return float(st.session_state.get(key, default) or 0)
    return float(_saved_field(row, field, default) or 0)


def _session_bool(row: ReceptionistPayrollRow, field: str, default: bool = False) -> bool:
    key = rec_key(row.name, field)
    if key in st.session_state:
        return bool(st.session_state.get(key, default))
    return bool(_saved_field(row, field, default))


def _session_text(row: ReceptionistPayrollRow, field: str, default: str = "") -> str:
    key = rec_key(row.name, field)
    if key in st.session_state:
        return str(st.session_state.get(key, default) or "")
    return str(_saved_field(row, field, default) or "")


def persist_receptionist_changes(name: str | None = None):
    """Capture pay-period field edits and refresh the bottom summary chart."""
    if name:
        st.session_state[section_open_key(name)] = True
        _commit_receptionist_inputs(name)
    refresh_receptionist_value_store()
    from lib.payroll_autosave import autosave_receptionist_payroll

    autosave_receptionist_payroll()
    st.rerun()


def capture_receptionist_values(rows: list[ReceptionistPayrollRow]) -> dict:
    values: Dict[str, dict] = {}
    for row in rows:
        values[row.name] = {
            "appointments_set": float(
                st.session_state.get(rec_key(row.name, "appointments_set"), row.appointments_set) or 0
            ),
            "tires_sold": float(
                st.session_state.get(rec_key(row.name, "tires_sold"), _parse_tires_value(row.name)) or 0
            ),
            "appointment_rate": _read_appointment_rate(
                row.name,
                row,
            ),
            "bonus_amount": float(
                st.session_state.get(rec_key(row.name, "bonus_amount"), row.bonus_amount) or 0
            ),
            "bonus_label": st.session_state.get(
                rec_key(row.name, "bonus_label"), row.bonus_label or "Bonus"
            ),
            "spiff": float(st.session_state.get(rec_key(row.name, "spiff"), row.spiff) or 0),
            "warranty_bonus": bool(st.session_state.get(rec_key(row.name, "warranty_bonus"), False)),
            "csi_tier": st.session_state.get(rec_key(row.name, "csi_tier"), CSI_TIER_NONE),
            "notes": str(st.session_state.get(rec_key(row.name, "notes"), row.notes) or ""),
        }
    return values


def _init_fields(row: ReceptionistPayrollRow, overrides: Optional[dict] = None):
    overrides = overrides or {}
    for field, default in RECEPTIONIST_FIELDS.items():
        key = rec_key(row.name, field)
        roster_val = getattr(row, field, default)
        if field in overrides:
            st.session_state[key] = float(overrides[field] or 0)
        else:
            st.session_state[key] = float(roster_val if roster_val is not None else default)
    st.session_state[rec_key(row.name, "bonus_label")] = overrides.get(
        "bonus_label", row.bonus_label or "Bonus"
    )
    st.session_state[rec_key(row.name, "warranty_bonus")] = bool(
        overrides.get("warranty_bonus", False)
    )
    st.session_state[rec_key(row.name, "csi_tier")] = overrides.get("csi_tier", CSI_TIER_NONE)
    st.session_state[rec_key(row.name, "notes")] = overrides.get("notes", row.notes or "")
    tires = float(overrides.get("tires_sold", st.session_state.get(rec_key(row.name, "tires_sold"), 0)) or 0)
    st.session_state[_tires_text_key(row.name)] = str(int(tires)) if tires else ""
    rate = float(overrides.get("appointment_rate", st.session_state.get(rec_key(row.name, "appointment_rate"), 0)) or 0)
    st.session_state[_appointment_rate_text_key(row.name)] = _format_rate_text(rate)


def apply_roster_to_session(roster: dict, values_by_name: Optional[dict] = None):
    clear_receptionist_field_keys()
    st.session_state.receptionist_roster = normalize_roster(roster)
    values_by_name = values_by_name or {}
    for row in flatten_roster(roster):
        _init_fields(row, overrides=values_by_name.get(row.name))


def _clear_legacy_index_keys():
    """Remove old index-based widget keys (rec_0_*, rec_1_*, …) from prior builds."""
    for key in list(st.session_state.keys()):
        if re.match(r"^rec_\d+_", key):
            del st.session_state[key]


def init_receptionist_payroll_session():
    _clear_legacy_index_keys()
    if "receptionist_roster" not in st.session_state:
        apply_roster_to_session(load_roster())
    else:
        st.session_state.receptionist_roster = normalize_roster(st.session_state.receptionist_roster)
    if "receptionist_report_loaded" not in st.session_state:
        st.session_state.receptionist_report_loaded = False

    apply_roster_appointment_rates_to_session()
    apply_receptionist_value_store()
    refresh_receptionist_value_store()
    for row in flatten_roster(st.session_state.receptionist_roster):
        legacy_open = rec_key(row.name, "expanded")
        open_key = section_open_key(row.name)
        if legacy_open in st.session_state and open_key not in st.session_state:
            st.session_state[open_key] = bool(st.session_state.get(legacy_open, False))
        if open_key not in st.session_state:
            st.session_state[open_key] = False


def apply_cashiers_report_to_session(report_rows) -> int:
    by_code = report_by_code(report_rows)
    by_last = report_by_last_name(report_rows)
    matched = 0

    for row in flatten_roster(st.session_state.receptionist_roster):
        appt_count = 0.0
        for code in row.taker_codes:
            report = by_code.get(code.upper())
            if report:
                appt_count += report.appointments_set
        if not appt_count and row.last_name:
            report = by_last.get(row.last_name.upper())
            if report:
                appt_count = report.appointments_set
        if appt_count:
            st.session_state[rec_key(row.name, "appointments_set")] = float(appt_count)
            matched += 1

    st.session_state.receptionist_report_loaded = matched > 0
    refresh_receptionist_value_store()
    from lib.payroll_autosave import autosave_receptionist_payroll

    autosave_receptionist_payroll()
    return matched


def sync_receptionist(row: ReceptionistPayrollRow) -> ReceptionistPayrollRow:
    row = ensure_receptionist_row_fields(row)
    rate = _session_float(row, "appointment_rate", row.appointment_rate)
    return ReceptionistPayrollRow(
        name=row.name,
        last_name=row.last_name,
        employee_type=row.employee_type,
        taker_codes=list(row.taker_codes),
        appointment_rate=rate,
        appointments_set=_session_float(row, "appointments_set", row.appointments_set),
        tires_sold=_session_float(row, "tires_sold", row.tires_sold),
        tire_rate=TIRE_PAY_RATE,
        bonus_amount=_session_float(row, "bonus_amount", row.bonus_amount),
        has_warranty_bonus=row.has_warranty_bonus,
        warranty_bonus_amount=float(row.warranty_bonus_amount or 0),
        warranty_bonus_qualified=_session_bool(row, "warranty_bonus", row.warranty_bonus_qualified),
        has_csi_bonus=row.has_csi_bonus,
        csi_tier=_session_text(row, "csi_tier", CSI_TIER_NONE),
        bonus_label=_session_text(row, "bonus_label", row.bonus_label or "Bonus"),
        spiff=_session_float(row, "spiff", row.spiff),
        notes=_session_text(row, "notes", row.notes),
    )


def all_receptionists_synced() -> list:
    return [sync_receptionist(row) for row in flatten_roster(st.session_state.receptionist_roster)]


def toggle_receptionist_section(name: str, employee_names: list[str]):
    capture_open_receptionist_inputs()
    open_key = section_open_key(name)
    is_open = st.session_state.get(open_key, False)
    if is_open:
        refresh_receptionist_value_store()
        st.session_state[open_key] = False
    else:
        for other in employee_names:
            st.session_state[section_open_key(other)] = False
        st.session_state[open_key] = True

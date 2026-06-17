"""Shared payroll session helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Optional

import streamlit as st

from lib.tech_payroll_calc import TechPayrollRow
from lib.tech_roster import load_roster


def parse_period_token(token: str) -> Optional[date]:
    token = (token or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def format_period_date(value: date) -> str:
    return value.strftime("%m/%d/%y")


def format_pay_period(start: date, end: date) -> str:
    return f"{format_period_date(start)}-{format_period_date(end)}"


def pay_period_weeks() -> float:
    start = st.session_state.get("payroll_period_start")
    end = st.session_state.get("payroll_period_end")
    if start and end and end >= start:
        return max(((end - start).days + 1) / 7.0, 1.0)
    return 2.0


def set_pay_period_dates(start: date, end: date) -> None:
    st.session_state.payroll_period_start = start
    st.session_state.payroll_period_end = end
    st.session_state.pay_period = format_pay_period(start, end)


def set_pay_period_from_string(period: str) -> None:
    if not period or "-" not in period:
        return
    start_text, end_text = period.split("-", 1)
    start = parse_period_token(start_text)
    end = parse_period_token(end_text)
    if start and end:
        set_pay_period_dates(start, end)


def sync_pay_period_from_dates() -> None:
    start = st.session_state.get("payroll_period_start")
    end = st.session_state.get("payroll_period_end")
    if start and end and end >= start:
        st.session_state.pay_period = format_pay_period(start, end)


def init_pay_period_state() -> None:
    pending_start = st.session_state.pop("pending_pay_period_start", None)
    pending_end = st.session_state.pop("pending_pay_period_end", None)
    if pending_start and pending_end:
        set_pay_period_dates(pending_start, pending_end)
        return

    if (
        "payroll_period_start" in st.session_state
        and "payroll_period_end" in st.session_state
    ):
        sync_pay_period_from_dates()
        return
    if st.session_state.get("pay_period"):
        set_pay_period_from_string(st.session_state.pay_period)
        return
    end = date.today()
    start = end - timedelta(days=13)
    set_pay_period_dates(start, end)


def field_key(team_name: str, idx: int, field: str) -> str:
    safe_team = team_name.replace(" ", "_").replace("'", "")
    return f"pay_{safe_team}_{idx}_{field}"


PAYROLL_ROW_FIELDS = ("hours", "dollars", "rate", "train", "spiff", "notes")


def ensure_row_fields(team_name: str, idx: int, row: TechPayrollRow, overrides: Optional[Dict] = None):
    """Ensure every payroll widget key exists before reading session state."""
    missing = any(
        field_key(team_name, idx, fld) not in st.session_state
        for fld in PAYROLL_ROW_FIELDS
    )
    if missing:
        init_row_fields(team_name, idx, row, overrides=overrides)


def ensure_all_row_fields():
    for team_name, rows in st.session_state.tech_teams.items():
        for i, row in enumerate(rows):
            ensure_row_fields(team_name, i, row)


def init_row_fields(team_name: str, idx: int, row: TechPayrollRow, overrides: Optional[Dict] = None):
    overrides = overrides or {}
    defaults = {
        "hours": row.flat_rate_hours,
        "dollars": row.dollars_earned,
        "rate": row.hourly_rate,
        "train": row.training_hours,
        "spiff": row.spiff,
        "notes": row.notes or "",
    }
    for fld, val in defaults.items():
        if fld == "notes":
            st.session_state[field_key(team_name, idx, fld)] = str(overrides.get(fld, val) or "")
        else:
            st.session_state[field_key(team_name, idx, fld)] = float(overrides.get(fld, val) or 0)


def clear_payroll_field_keys():
    for key in list(st.session_state.keys()):
        if key.startswith("pay_"):
            del st.session_state[key]


def capture_tech_values(teams: dict) -> dict:
    """Preserve entered values by technician name across roster changes."""
    values = {}
    for team_name, rows in teams.items():
        for i, row in enumerate(rows):
            values[row.name] = {
                "hours": float(st.session_state.get(field_key(team_name, i, "hours"), row.flat_rate_hours) or 0),
                "dollars": float(st.session_state.get(field_key(team_name, i, "dollars"), row.dollars_earned) or 0),
                "rate": float(st.session_state.get(field_key(team_name, i, "rate"), row.hourly_rate) or 0),
                "train": float(st.session_state.get(field_key(team_name, i, "train"), row.training_hours) or 0),
                "spiff": float(st.session_state.get(field_key(team_name, i, "spiff"), row.spiff) or 0),
                "notes": str(st.session_state.get(field_key(team_name, i, "notes"), row.notes) or ""),
                "tech_number": row.tech_number,
            }
    return values


def apply_teams_to_session(teams: dict, values_by_name: Optional[Dict] = None):
    """Replace roster in session and rebuild widget keys."""
    values_by_name = values_by_name or {}
    clear_payroll_field_keys()
    st.session_state.tech_teams = teams
    for team_name, rows in teams.items():
        for i, row in enumerate(rows):
            overrides = values_by_name.get(row.name)
            if overrides and "tech_number" in overrides:
                row.tech_number = overrides["tech_number"]
            init_row_fields(team_name, i, row, overrides=overrides)


def render_pay_period_selector():
    st.markdown("##### 📅 Payroll cycle")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.date_input(
            "Start date",
            key="payroll_period_start",
            format="MM/DD/YYYY",
        )
    with c2:
        st.date_input(
            "End date",
            key="payroll_period_end",
            format="MM/DD/YYYY",
        )
    with c3:
        sync_pay_period_from_dates()
        period = st.session_state.get("pay_period", "")
        start = st.session_state.get("payroll_period_start")
        end = st.session_state.get("payroll_period_end")
        if period:
            st.markdown(
                f'<div style="margin-top:1.75rem;color:#94a3b8;">'
                f'Active pay period: <strong style="color:#e2e8f0;">{period}</strong></div>',
                unsafe_allow_html=True,
            )
        if start and end and end < start:
            st.warning("End date must be on or after the start date.")
    st.caption("Pick the payroll dates manually, or upload a flag sheet PDF to auto-fill them.")


def init_payroll_session():
    if "tech_teams" not in st.session_state:
        st.session_state.tech_teams = load_roster()
    if "pay_period" not in st.session_state:
        st.session_state.pay_period = ""
    if "pdf_loaded" not in st.session_state:
        st.session_state.pdf_loaded = False
    if "flag_pdf_bytes" not in st.session_state:
        st.session_state.flag_pdf_bytes = None
    if "flag_pdf_filename" not in st.session_state:
        st.session_state.flag_pdf_filename = ""
    if "active_run_id" not in st.session_state:
        st.session_state.active_run_id = None
    if "active_advisor_run_id" not in st.session_state:
        st.session_state.active_advisor_run_id = None
    if "advisor_payroll_completed" not in st.session_state:
        st.session_state.advisor_payroll_completed = False
    if "payroll_completed" not in st.session_state:
        st.session_state.payroll_completed = False
    if "active_receptionist_run_id" not in st.session_state:
        st.session_state.active_receptionist_run_id = None
    if "receptionist_payroll_completed" not in st.session_state:
        st.session_state.receptionist_payroll_completed = False

    init_pay_period_state()
    ensure_all_row_fields()


def _field_float(team_name: str, idx: int, field: str, default: float = 0.0) -> float:
    return float(st.session_state.get(field_key(team_name, idx, field), default) or 0)


def sync_row(team_name: str, idx: int, row: TechPayrollRow) -> TechPayrollRow:
    ensure_row_fields(team_name, idx, row)
    row.flat_rate_hours = _field_float(team_name, idx, "hours", row.flat_rate_hours)
    row.dollars_earned = _field_float(team_name, idx, "dollars", row.dollars_earned)
    row.hourly_rate = _field_float(team_name, idx, "rate", row.hourly_rate)
    row.training_hours = _field_float(team_name, idx, "train", row.training_hours)
    row.spiff = _field_float(team_name, idx, "spiff", row.spiff)
    row.notes = str(st.session_state.get(field_key(team_name, idx, "notes"), row.notes) or "")
    return row


def all_rows_synced() -> dict:
    ensure_all_row_fields()
    synced = {}
    for team_name, rows in st.session_state.tech_teams.items():
        synced[team_name] = [
            sync_row(team_name, i, TechPayrollRow(**row.__dict__))
            for i, row in enumerate(rows)
        ]
    return synced


def persist_technician_changes(team_name: str | None = None, idx: int | None = None):
    """Auto-save the in-progress technician payroll."""
    from lib.payroll_autosave import autosave_technician_payroll

    autosave_technician_payroll()


def store_flag_pdf(uploaded_file, pdf_bytes: bytes | None = None):
    """Save uploaded flag sheet bytes for viewing on Flag Sheet tab."""
    if pdf_bytes is None:
        uploaded_file.seek(0)
        pdf_bytes = uploaded_file.read()
    st.session_state.flag_pdf_bytes = pdf_bytes
    st.session_state.flag_pdf_filename = uploaded_file.name

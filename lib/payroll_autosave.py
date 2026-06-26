"""Auto-save in-progress payroll runs on every field change."""

from __future__ import annotations

import streamlit as st


def autosave_advisor_payroll() -> None:
    pay_period = st.session_state.get("pay_period")
    if not pay_period:
        return

    from lib.advisor_payroll_storage import save_advisor_payroll_run
    from views.advisor_payroll_helpers import all_advisors_synced
    from views.payroll_helpers import pay_period_weeks

    status = "completed" if st.session_state.get("advisor_payroll_completed") else "draft"
    run_id, sync_error = save_advisor_payroll_run(
        all_advisors_synced(),
        pay_period,
        pay_period_weeks(),
        run_id=st.session_state.get("active_advisor_run_id"),
        status=status,
    )
    st.session_state.active_advisor_run_id = run_id
    if sync_error:
        st.session_state["_advisor_payroll_sync_error"] = sync_error
    elif status == "completed":
        st.session_state.advisor_payroll_completed = True


def autosave_receptionist_payroll() -> None:
    pay_period = st.session_state.get("pay_period")
    if not pay_period:
        return

    from lib.receptionist_payroll_storage import save_receptionist_payroll_run
    from views.receptionist_payroll_helpers import all_receptionists_synced

    status = "completed" if st.session_state.get("receptionist_payroll_completed") else "draft"
    run_id, sync_error = save_receptionist_payroll_run(
        all_receptionists_synced(),
        pay_period,
        run_id=st.session_state.get("active_receptionist_run_id"),
        status=status,
    )
    st.session_state.active_receptionist_run_id = run_id
    if sync_error:
        st.session_state["_receptionist_payroll_sync_error"] = sync_error
    elif status == "completed":
        st.session_state.receptionist_payroll_completed = True


def autosave_technician_payroll() -> None:
    pay_period = st.session_state.get("pay_period")
    if not pay_period or not st.session_state.get("pdf_loaded"):
        return

    from lib.payroll_storage import save_payroll_run
    from views.payroll_helpers import all_rows_synced

    status = "completed" if st.session_state.get("payroll_completed") else "draft"
    run_id, sync_error = save_payroll_run(
        all_rows_synced(),
        pay_period,
        st.session_state.get("flag_pdf_bytes"),
        st.session_state.get("flag_pdf_filename", "flag_sheet.pdf"),
        run_id=st.session_state.get("active_run_id"),
        status=status,
    )
    st.session_state.active_run_id = run_id
    if sync_error:
        st.session_state["_technician_payroll_sync_error"] = sync_error
    elif status == "completed":
        st.session_state.payroll_completed = True

"""End-of-month Fixed Ops report for the controller."""

from __future__ import annotations

from calendar import month_name
from datetime import date

import streamlit as st

from components.ui import page_hero, stat_card, status_banner
from lib.eom_report_calc import calculate_eom_report
from lib.eom_report_pdf_export import generate_eom_report_pdf
from lib.eom_report_storage import save_eom_report_run, serialize_eom_report_session
from views.payroll_helpers import render_payroll_sync_error


def _month_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _init_state():
    defaults = {
        "eom_month": date.today().replace(day=1),
        "eom_tech_count": 0.0,
        "eom_hours_per_day": 8.0,
        "eom_work_days": 0.0,
        "eom_clock_time": 0.0,
        "eom_flagged_hours": 0.0,
        "eom_lot_porters": 0.0,
        "eom_cashiers": 0.0,
        "eom_advisors": 0.0,
        "eom_shuttle_drivers": 0.0,
        "eom_notes": "",
        "active_eom_report_run_id": None,
        "eom_report_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render():
    _init_state()

    st.markdown(
        page_hero(
            "EOM Report",
            "Monthly Fixed Ops headcount and tech efficiency for your controller — fill in, auto-calc, export PDF.",
            tag="Fixed Ops",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("eom_report_completed"):
        st.markdown(
            status_banner(
                f"Editing saved EOM · {st.session_state.get('eom_report_month_label') or _month_label(st.session_state.eom_month)} · "
                "Export PDF or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_eom_report_sync_error", table="eom_report_runs")

    st.date_input(
        "Report month",
        key="eom_month",
        format="MM/DD/YYYY",
        help="Use any day in the calendar month.",
    )
    month_label = _month_label(st.session_state.eom_month)
    st.caption(f"Reporting for **{month_label}**")

    st.markdown("---")
    st.markdown("##### Technician productivity")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.number_input("Number of techs", min_value=0.0, step=1.0, format="%.0f", key="eom_tech_count")
    with r2:
        st.number_input("Hours per day", min_value=0.0, step=0.5, format="%.1f", key="eom_hours_per_day")
    with r3:
        st.number_input("Work days in month", min_value=0.0, step=1.0, format="%.0f", key="eom_work_days")

    r4, r5 = st.columns(2)
    with r4:
        st.number_input(
            "Total clock time",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            key="eom_clock_time",
            help="Total technician clock hours for the month.",
        )
    with r5:
        st.number_input(
            "Tech flagged hours",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            key="eom_flagged_hours",
            help="Total flag / production hours for the month.",
        )

    st.markdown("---")
    st.markdown("##### Headcount")
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.number_input(
            "Lot porters",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key="eom_lot_porters",
            help="Includes Misty when applicable.",
        )
    with h2:
        st.number_input(
            "Cashiers",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key="eom_cashiers",
            help="Includes Brandy and Serenity when applicable.",
        )
    with h3:
        st.number_input("Advisors", min_value=0.0, step=1.0, format="%.0f", key="eom_advisors")
    with h4:
        st.number_input(
            "Part-time shuttle drivers",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key="eom_shuttle_drivers",
        )

    st.text_area(
        "Notes for controller (optional)",
        key="eom_notes",
        placeholder="Optional — prints on the PDF",
        height=80,
    )

    result = calculate_eom_report(
        report_month=month_label,
        tech_count=float(st.session_state.eom_tech_count or 0),
        hours_per_day=float(st.session_state.eom_hours_per_day or 0),
        work_days=float(st.session_state.eom_work_days or 0),
        total_clock_time=float(st.session_state.eom_clock_time or 0),
        tech_flagged_hours=float(st.session_state.eom_flagged_hours or 0),
        lot_porters=float(st.session_state.eom_lot_porters or 0),
        cashiers=float(st.session_state.eom_cashiers or 0),
        advisors=float(st.session_state.eom_advisors or 0),
        shuttle_drivers=float(st.session_state.eom_shuttle_drivers or 0),
        notes=st.session_state.eom_notes,
    )

    st.markdown("---")
    st.markdown("##### Calculated results")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            stat_card("Available hours", f"{result.total_available_hours:,.2f}", "cyan", "⏱"),
            unsafe_allow_html=True,
        )
        st.caption("Techs × hours/day × work days")
    with c2:
        st.markdown(
            stat_card("Efficiency", f"{result.efficiency_pct:.2f}%", "green", "📈"),
            unsafe_allow_html=True,
        )
        st.caption("Flagged hours ÷ clock time")
    with c3:
        st.markdown(
            stat_card("Techs", f"{result.tech_count:.0f}", "violet", "🔧"),
            unsafe_allow_html=True,
        )
        st.caption(f"{result.work_days:.0f} work days · {result.hours_per_day:.1f} hrs/day")

    st.markdown(
        status_banner(
            f"**{month_label}** · Available **{result.total_available_hours:,.2f}** hrs · "
            f"Efficiency **{result.efficiency_pct:.2f}%**",
            "success" if result.total_clock_time or result.tech_count else "warn",
        ),
        unsafe_allow_html=True,
    )

    snapshot = serialize_eom_report_session(
        report_month=month_label,
        tech_count=result.tech_count,
        hours_per_day=result.hours_per_day,
        work_days=result.work_days,
        total_clock_time=result.total_clock_time,
        tech_flagged_hours=result.tech_flagged_hours,
        lot_porters=result.lot_porters,
        cashiers=result.cashiers,
        advisors=result.advisors,
        shuttle_drivers=result.shuttle_drivers,
        notes=result.notes,
    )
    pdf_bytes = generate_eom_report_pdf(snapshot)
    file_stub = month_label.replace(" ", "_")

    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export PDF for controller",
            data=pdf_bytes,
            file_name=f"EOM_REPORT_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with e2:
        st.caption("PDF includes productivity math, headcount, and notes.")

    st.markdown("---")
    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This EOM report is complete and ready to save",
        key="eom_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
    ):
        run_id, sync_error = save_eom_report_run(
            snapshot,
            run_id=st.session_state.get("active_eom_report_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_eom_report_run_id = run_id
        st.session_state.eom_report_completed = True
        st.session_state.eom_report_month_label = month_label
        if sync_error:
            st.session_state["_eom_report_sync_error"] = sync_error
        else:
            st.session_state.pop("_eom_report_sync_error", None)
        st.session_state["_eom_saved_month"] = month_label
        del st.session_state["eom_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_eom_saved_month", None):
        if st.session_state.get("_eom_report_sync_error"):
            st.error(
                f"EOM for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under EOM Report · {saved}")
            st.balloons()

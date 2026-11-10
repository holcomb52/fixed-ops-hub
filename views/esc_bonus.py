"""Extended Service Contract claims bonus — separate check on the 10th."""

from __future__ import annotations

from calendar import month_name
from datetime import date

import streamlit as st

from lib.esc_bonus_calc import BONUS_RATE, ELIGIBLE_EMPLOYEES, calculate_esc_bonus
from lib.esc_bonus_pdf_export import generate_esc_bonus_pdf
from lib.esc_bonus_storage import save_esc_bonus_run, serialize_esc_bonus_session
from lib.page_ui import page_hero, stat_card, status_banner
from views.payroll_helpers import render_payroll_sync_error


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _month_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _paid_on_label(bonus_month: date) -> str:
    if bonus_month.month == 12:
        nxt = date(bonus_month.year + 1, 1, 10)
    else:
        nxt = date(bonus_month.year, bonus_month.month + 1, 10)
    return f"{month_name[nxt.month]} {nxt.day}, {nxt.year} (separate check)"


def _init_state():
    defaults = {
        "esc_employee_name": ELIGIBLE_EMPLOYEES[0],
        "esc_month": date.today().replace(day=1),
        "esc_amount_paid": 0.0,
        "esc_chargebacks": 0.0,
        "esc_notes": "",
        "active_esc_bonus_run_id": None,
        "esc_bonus_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render():
    _init_state()

    st.markdown(
        page_hero(
            "Service Contract Bonus",
            "Extended Service Contract claims bonus for Serenity Skinner — "
            "2% of parts & labor actually paid to the store. Separate check on the 10th.",
            tag="Claims",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("esc_bonus_completed"):
        st.markdown(
            status_banner(
                f"Editing saved ESC bonus · "
                f"{st.session_state.get('esc_bonus_month_label') or _month_label(st.session_state.esc_month)} · "
                "Export PDF or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_esc_bonus_sync_error", table="esc_bonus_runs")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.selectbox(
            "Employee",
            ELIGIBLE_EMPLOYEES,
            key="esc_employee_name",
            help="Pay plan addendum — Service Contract Claims Bonus.",
        )
    with c2:
        st.date_input(
            "Claims month",
            key="esc_month",
            format="MM/DD/YYYY",
            help="Month payment was received by the store (not authorization month).",
        )

    bonus_month: date = st.session_state.esc_month
    month_label = _month_label(bonus_month)
    paid_label = _paid_on_label(bonus_month)
    st.caption(
        f"Measured for **{month_label}** · Paid on **{paid_label}** · "
        f"Rate **{BONUS_RATE * 100:.0f}%** of net paid"
    )

    st.markdown("---")
    st.markdown("##### Enter service contract amounts paid to the store")
    st.caption(
        "Use accounting / claims tracking totals for **parts + labor actually paid** "
        "(not authorized). Exclude deductibles and customer-pay. Enter chargebacks for this month."
    )

    m1, m2 = st.columns(2)
    with m1:
        st.number_input(
            "Parts + labor paid ($)",
            min_value=0.0,
            step=50.0,
            format="%.2f",
            key="esc_amount_paid",
            help="Total paid by the service contract company on claims she submitted.",
        )
    with m2:
        st.number_input(
            "Chargebacks / reversals ($)",
            min_value=0.0,
            step=10.0,
            format="%.2f",
            key="esc_chargebacks",
            help="Deducted from paid total in the month the chargeback occurs.",
        )

    st.text_area(
        "Notes for payroll clerk (optional)",
        key="esc_notes",
        placeholder="Optional — claim refs, reconciliation notes — prints on the PDF",
        height=80,
    )

    result = calculate_esc_bonus(
        employee_name=st.session_state.esc_employee_name,
        bonus_month=month_label,
        amount_paid=float(st.session_state.esc_amount_paid or 0),
        chargebacks=float(st.session_state.esc_chargebacks or 0),
        notes=st.session_state.esc_notes,
        paid_on_label=paid_label,
    )

    st.markdown("---")
    st.markdown("##### Bonus summary")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            stat_card("Paid to store", _money(result.amount_paid), "cyan", "💵"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card("Chargebacks", _money(result.chargebacks), "orange", "↺"),
            unsafe_allow_html=True,
        )
    with s3:
        st.markdown(
            stat_card("Net paid", _money(result.net_paid), "cyan", "◎"),
            unsafe_allow_html=True,
        )
    with s4:
        accent = "green" if result.bonus_amount else "rose"
        st.markdown(
            stat_card("ESC bonus", _money(result.bonus_amount), accent, "📝"),
            unsafe_allow_html=True,
        )

    banner_kind = "success" if result.bonus_amount else "warn"
    st.markdown(
        status_banner(
            f"**{result.employee_name}** · {month_label} · "
            f"ESC claims bonus **{_money(result.bonus_amount)}** · {paid_label}",
            banner_kind,
        ),
        unsafe_allow_html=True,
    )

    snapshot = serialize_esc_bonus_session(
        employee_name=result.employee_name,
        bonus_month=month_label,
        amount_paid=result.amount_paid,
        chargebacks=result.chargebacks,
        notes=result.notes,
        paid_on_label=paid_label,
    )
    pdf_bytes = generate_esc_bonus_pdf(snapshot)
    file_stub = f"{result.employee_name.replace(' ', '_')}_{month_label.replace(' ', '_')}"

    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export PDF for separate check",
            data=pdf_bytes,
            file_name=f"ESC_BONUS_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with e2:
        st.caption("PDF is for the separate check on the 10th — not the bi-weekly payroll worksheet.")

    st.markdown("---")
    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This ESC bonus is complete and ready to save",
        key="esc_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
    ):
        run_id, sync_error = save_esc_bonus_run(
            snapshot,
            run_id=st.session_state.get("active_esc_bonus_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_esc_bonus_run_id = run_id
        st.session_state.esc_bonus_completed = True
        st.session_state.esc_bonus_month_label = month_label
        if sync_error:
            st.session_state["_esc_bonus_sync_error"] = sync_error
        else:
            st.session_state.pop("_esc_bonus_sync_error", None)
        st.session_state["_esc_saved_month"] = month_label
        del st.session_state["esc_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_esc_saved_month", None):
        if st.session_state.get("_esc_bonus_sync_error"):
            st.error(
                f"ESC bonus for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under Service Contract Bonus · {saved}")
            st.balloons()

    with st.expander("Pay plan addendum rules", expanded=False):
        st.markdown(
            f"""
            **Effective:** Pay Plan Addendum — Service Contract Claims Bonus & Declined Services Incentive

            **Eligible:** {", ".join(ELIGIBLE_EMPLOYEES)}

            1. Earn **{BONUS_RATE * 100:.0f}%** of parts and labor dollars **actually paid** to the store
               by the service contract company on claims she submits.
            2. Based on amount **paid**, not amount authorized.
            3. Excludes deductibles, customer-pay, and denied claims.
            4. Chargebacks reduce the bonus in the month they occur.
            5. Calculated after month-end close and paid on the **10th of the following month**
               as a **separate check** (not on bi-weekly payroll).
            """
        )

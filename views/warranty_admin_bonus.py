"""Warranty Administrator monthly bonus — standalone Fixed Ops Hub tab."""

from __future__ import annotations

from calendar import month_name
from datetime import date

import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.warranty_admin_bonus_calc import (
    MAX_MONTHLY_BONUS,
    STRETCH_BONUS,
    calculate_warranty_admin_bonus,
)
from lib.warranty_admin_bonus_pdf_export import generate_warranty_admin_bonus_pdf
from lib.warranty_admin_bonus_storage import (
    save_warranty_admin_bonus_run,
    serialize_warranty_admin_bonus_session,
)
from views.payroll_helpers import render_payroll_sync_error


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _month_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _paid_on_label(bonus_month: date) -> str:
    if bonus_month.month == 12:
        nxt = date(bonus_month.year + 1, 1, 1)
    else:
        nxt = date(bonus_month.year, bonus_month.month + 1, 1)
    return f"First payroll of {month_name[nxt.month]} {nxt.year}"


def _init_state():
    defaults = {
        "wab_employee_name": "Warranty Administrator",
        "wab_month": date.today().replace(day=1),
        "wab_receivables": 0.0,
        "wab_avg_days": 0.0,
        "wab_first_pass": 0.0,
        "wab_compliance_reduction": 0.0,
        "wab_notes": "",
        "active_warranty_admin_bonus_run_id": None,
        "warranty_admin_bonus_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render():
    _init_state()

    st.markdown(
        page_hero(
            "Warranty Admin Bonus",
            "Monthly performance bonus for the Warranty Administrator — enter three numbers, save, export PDF.",
            tag="Fixed Ops",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("warranty_admin_bonus_completed"):
        st.markdown(
            status_banner(
                f"Editing saved bonus · {st.session_state.get('wab_bonus_month_label') or _month_label(st.session_state.wab_month)} · "
                "Export PDF for payroll, or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_warranty_admin_bonus_sync_error", table="warranty_admin_bonus_runs")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.text_input(
            "Employee name",
            key="wab_employee_name",
            help="Usually the Warranty Administrator on this pay plan.",
        )
    with c2:
        st.date_input(
            "Bonus month",
            key="wab_month",
            format="MM/DD/YYYY",
            help="Use any day in the calendar month being measured.",
        )

    bonus_month: date = st.session_state.wab_month
    month_label = _month_label(bonus_month)
    paid_label = _paid_on_label(bonus_month)
    st.caption(f"Measured for **{month_label}** · Paid on **{paid_label}** · Max bonus {_money(MAX_MONTHLY_BONUS)}")

    st.markdown("---")
    st.markdown("##### Enter month-end results")
    st.caption("Open warranty receivables (last business day) · average days RO close → claim submit · first-pass approval %.")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.number_input(
            "Warranty receivables ($)",
            min_value=0.0,
            step=1000.0,
            format="%.2f",
            key="wab_receivables",
            help="≤ $85,000 = $400 · $85,001–$100,000 = $250 · over $100,000 = $0",
        )
    with m2:
        st.number_input(
            "Avg days to submit",
            min_value=0.0,
            step=0.1,
            format="%.1f",
            key="wab_avg_days",
            help="≤ 2.0 days = $300 · 2.1–3.0 = $150 · over 3.0 = $0",
        )
    with m3:
        st.number_input(
            "First-pass approval %",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.1f",
            key="wab_first_pass",
            help="≥ 90% = $300 · 85–89.9% = $150 · below 85% = $0",
        )

    with st.expander("Compliance reduction / notes (optional)", expanded=False):
        st.number_input(
            "Reduce bonus by ($)",
            min_value=0.0,
            step=25.0,
            format="%.2f",
            key="wab_compliance_reduction",
            help="Use for audit chargebacks / documentation issues. Leave 0 if fully eligible.",
        )
        st.text_area(
            "Notes for payroll clerk",
            key="wab_notes",
            placeholder="Optional — prints on the PDF",
            height=80,
        )

    result = calculate_warranty_admin_bonus(
        employee_name=st.session_state.wab_employee_name,
        bonus_month=month_label,
        receivables_balance=float(st.session_state.wab_receivables or 0),
        avg_days_to_submit=float(st.session_state.wab_avg_days or 0),
        first_pass_pct=float(st.session_state.wab_first_pass or 0),
        compliance_reduction=float(st.session_state.wab_compliance_reduction or 0),
        notes=st.session_state.wab_notes,
        paid_on_label=paid_label,
    )

    st.markdown("---")
    st.markdown("##### Bonus summary")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(stat_card("Receivables", _money(result.receivables.amount), "cyan", "💰"), unsafe_allow_html=True)
        st.caption(result.receivables.tier_label)
    with s2:
        st.markdown(stat_card("Submit days", _money(result.avg_days.amount), "orange", "⏱"), unsafe_allow_html=True)
        st.caption(result.avg_days.tier_label)
    with s3:
        st.markdown(stat_card("First-pass", _money(result.first_pass.amount), "green", "✅"), unsafe_allow_html=True)
        st.caption(result.first_pass.tier_label)
    with s4:
        stretch_note = f"Top tiers met · {_money(STRETCH_BONUS)}" if result.stretch_earned else "Need all top tiers"
        st.markdown(stat_card("Stretch", _money(result.stretch_amount), "violet", "⭐"), unsafe_allow_html=True)
        st.caption(stretch_note)

    if result.compliance_reduction:
        st.warning(f"Compliance reduction: −{_money(result.compliance_reduction)}")

    st.markdown(
        status_banner(
            f"**{result.employee_name}** · {month_label} · Total monthly bonus **{_money(result.total_bonus)}**",
            "success" if result.total_bonus else "warn",
        ),
        unsafe_allow_html=True,
    )

    snapshot = serialize_warranty_admin_bonus_session(
        employee_name=result.employee_name,
        bonus_month=month_label,
        receivables_balance=result.receivables.input_value,
        avg_days_to_submit=result.avg_days.input_value,
        first_pass_pct=result.first_pass.input_value,
        compliance_reduction=result.compliance_reduction,
        notes=result.notes,
        paid_on_label=paid_label,
    )
    pdf_bytes = generate_warranty_admin_bonus_pdf(snapshot)
    file_stub = month_label.replace(" ", "_")

    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export PDF for payroll clerk",
            data=pdf_bytes,
            file_name=f"WARRANTY_ADMIN_BONUS_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with e2:
        st.caption("PDF includes metrics, stretch, total, and notes — ready to email accounting.")

    st.markdown("---")
    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This monthly bonus is complete and ready to save",
        key="wab_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
    ):
        run_id, sync_error = save_warranty_admin_bonus_run(
            snapshot,
            run_id=st.session_state.get("active_warranty_admin_bonus_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_warranty_admin_bonus_run_id = run_id
        st.session_state.warranty_admin_bonus_completed = True
        st.session_state.wab_bonus_month_label = month_label
        if sync_error:
            st.session_state["_warranty_admin_bonus_sync_error"] = sync_error
        else:
            st.session_state.pop("_warranty_admin_bonus_sync_error", None)
        st.session_state["_wab_saved_month"] = month_label
        del st.session_state["wab_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_wab_saved_month", None):
        if st.session_state.get("_warranty_admin_bonus_sync_error"):
            st.error(
                f"Bonus for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under Warranty Admin Bonus · {saved}")
            st.balloons()

    with st.expander("Pay plan rules", expanded=False):
        st.markdown(
            f"""
            **Maximum monthly bonus:** {_money(MAX_MONTHLY_BONUS)} (in addition to hourly pay)

            1. **Warranty receivables** (last business day)  
               ≤ $85,000 → $400 · $85,001–$100,000 → $250 · over $100,000 → $0

            2. **Average days to submit** (RO close → claim submit)  
               ≤ 2.0 → $300 · 2.1–3.0 → $150 · over 3.0 → $0

            3. **First submission pay rate**  
               ≥ 90% → $300 · 85–89.9% → $150 · below 85% → $0

            **Stretch {_money(STRETCH_BONUS)}** if all top tiers are met in the same month.
            """
        )

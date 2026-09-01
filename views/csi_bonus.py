"""CSI / NPS bonus tab — Serenity Skinner & Brandy Sistrunk pay plan addendum."""

from __future__ import annotations

from calendar import month_name
from datetime import date

import streamlit as st

from lib.csi_bonus_calc import BONUS_MID, BONUS_TOP, ELIGIBLE_EMPLOYEES, calculate_csi_bonus
from lib.csi_bonus_pdf_export import generate_csi_bonus_pdf
from lib.csi_bonus_storage import save_csi_bonus_run, serialize_csi_bonus_session
from lib.page_ui import page_hero, stat_card, status_banner
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
        "csi_employee_name": ELIGIBLE_EMPLOYEES[0],
        "csi_month": date.today().replace(day=1),
        "csi_store_nps": 0.0,
        "csi_national_average": 0.0,
        "csi_business_center_average": 0.0,
        "csi_notes": "",
        "active_csi_bonus_run_id": None,
        "csi_bonus_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render():
    _init_state()

    st.markdown(
        page_hero(
            "CSI Bonus",
            "Net Promoter Score bonus for Serenity Skinner and Brandy Sistrunk — "
            "enter Stellantis NPS results, export PDF, save to Reports.",
            tag="NPS",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("csi_bonus_completed"):
        st.markdown(
            status_banner(
                f"Editing saved CSI bonus · "
                f"{st.session_state.get('csi_bonus_month_label') or _month_label(st.session_state.csi_month)} · "
                "Export PDF or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_csi_bonus_sync_error", table="csi_bonus_runs")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.selectbox(
            "Employee",
            ELIGIBLE_EMPLOYEES,
            key="csi_employee_name",
            help="Pay plan addendum applies to both reception team members listed.",
        )
    with c2:
        st.date_input(
            "Bonus month",
            key="csi_month",
            format="MM/DD/YYYY",
            help="Use any day in the calendar month being measured.",
        )

    bonus_month: date = st.session_state.csi_month
    month_label = _month_label(bonus_month)
    paid_label = _paid_on_label(bonus_month)
    st.caption(
        f"Measured for **{month_label}** · Paid on **{paid_label}** · "
        f"Top tier {_money(BONUS_TOP)} · Mid tier {_money(BONUS_MID)}"
    )

    st.markdown("---")
    st.markdown("##### Enter Stellantis NPS results")
    st.caption("Use official Stellantis reporting for store NPS and benchmark averages.")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.number_input(
            "Store NPS",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.1f",
            key="csi_store_nps",
            help="Your store's reported Net Promoter Score.",
        )
    with m2:
        st.number_input(
            "National average",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.1f",
            key="csi_national_average",
            help="Stellantis national NPS benchmark.",
        )
    with m3:
        st.number_input(
            "Business center average",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.1f",
            key="csi_business_center_average",
            help="Stellantis business center NPS benchmark.",
        )

    st.text_area(
        "Notes for payroll clerk (optional)",
        key="csi_notes",
        placeholder="Optional — prints on the PDF",
        height=80,
    )

    result = calculate_csi_bonus(
        employee_name=st.session_state.csi_employee_name,
        bonus_month=month_label,
        store_nps=float(st.session_state.csi_store_nps or 0),
        national_average=float(st.session_state.csi_national_average or 0),
        business_center_average=float(st.session_state.csi_business_center_average or 0),
        notes=st.session_state.csi_notes,
        paid_on_label=paid_label,
    )

    st.markdown("---")
    st.markdown("##### Bonus summary")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(
            stat_card("Store NPS", f"{result.store_nps:.1f}", "cyan", "📊"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card("Tier", result.tier_label[:28], "orange", "◎"),
            unsafe_allow_html=True,
        )
    with s3:
        accent = "green" if result.bonus_amount else "rose"
        st.markdown(
            stat_card("Bonus", _money(result.bonus_amount), accent, "💰"),
            unsafe_allow_html=True,
        )

    banner_kind = "success" if result.bonus_amount else "warn"
    st.markdown(
        status_banner(
            f"**{result.employee_name}** · {month_label} · "
            f"CSI / NPS bonus **{_money(result.bonus_amount)}** · {result.tier_label}",
            banner_kind,
        ),
        unsafe_allow_html=True,
    )

    snapshot = serialize_csi_bonus_session(
        employee_name=result.employee_name,
        bonus_month=month_label,
        store_nps=result.store_nps,
        national_average=result.national_average,
        business_center_average=result.business_center_average,
        notes=result.notes,
        paid_on_label=paid_label,
    )
    pdf_bytes = generate_csi_bonus_pdf(snapshot)
    file_stub = f"{result.employee_name.replace(' ', '_')}_{month_label.replace(' ', '_')}"

    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export PDF for payroll clerk",
            data=pdf_bytes,
            file_name=f"CSI_BONUS_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with e2:
        st.caption("PDF includes NPS scores, tier earned, bonus amount, and notes.")

    st.markdown("---")
    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This CSI bonus is complete and ready to save",
        key="csi_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
    ):
        run_id, sync_error = save_csi_bonus_run(
            snapshot,
            run_id=st.session_state.get("active_csi_bonus_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_csi_bonus_run_id = run_id
        st.session_state.csi_bonus_completed = True
        st.session_state.csi_bonus_month_label = month_label
        if sync_error:
            st.session_state["_csi_bonus_sync_error"] = sync_error
        else:
            st.session_state.pop("_csi_bonus_sync_error", None)
        st.session_state["_csi_saved_month"] = month_label
        del st.session_state["csi_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_csi_saved_month", None):
        if st.session_state.get("_csi_bonus_sync_error"):
            st.error(
                f"CSI bonus for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under CSI Bonus · {saved}")
            st.balloons()

    with st.expander("Pay plan addendum rules", expanded=False):
        st.markdown(
            f"""
            **Effective:** Pay Plan Addendum — CSI / NPS Bonus (replaces prior CSI bonus structures)

            **Eligible employees:** {", ".join(ELIGIBLE_EMPLOYEES)}

            Bonus eligibility uses official **Stellantis-reported NPS** results:

            1. **NPS at or above National Average** → {_money(BONUS_TOP)}
            2. **NPS between Business Center Average and National Average** → {_money(BONUS_MID)}
            3. **NPS below Business Center Average** → No bonus

            Stellantis may adjust benchmarks as CSI/NPS measurement changes.
            """
        )

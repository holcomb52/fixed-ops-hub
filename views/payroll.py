import streamlit as st

from components.ui import page_hero
from views.payroll_advisors import render as render_advisors
from views.payroll_helpers import init_payroll_session, render_pay_period_selector
from views.payroll_technicians import render as render_technicians


def render():
    init_payroll_session()

    st.markdown(
        page_hero(
            "Payroll",
            "Technician flag sheet payroll and service advisor pay plans in one place.",
            tag="Fixed Ops",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    render_pay_period_selector()

    st.markdown("---")

    if st.session_state.pop("pending_payroll_tab", None) == "advisors":
        st.session_state.payroll_sub_tab = "Service Advisors"

    sub_tab = st.radio(
        "Payroll section",
        ["Technicians", "Service Advisors"],
        horizontal=True,
        label_visibility="collapsed",
        key="payroll_sub_tab",
    )

    st.markdown("---")

    if sub_tab == "Technicians":
        render_technicians()
    else:
        render_advisors()

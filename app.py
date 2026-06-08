import streamlit as st

from components.ui import coming_soon_panel
from lib.app_auth import require_login
from lib.supabase_client import is_configured
from styles import CUSTOM_CSS
from views import flag_sheet, home, payroll, reports, warranty

st.set_page_config(
    page_title="Fixed Ops Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if not require_login():
    st.stop()

PAGES = {
    "Home": home.render,
    "Payroll": payroll.render,
    "Flag Sheet": flag_sheet.render,
    "Warranty": warranty.render,
    "Inventory": None,
    "Reports": reports.render,
}

with st.sidebar:
    st.markdown(
        """
        <div class="brand-block">
            <div class="brand-logo">⚡</div>
            <div class="brand-name">Fixed Ops Hub</div>
            <div class="brand-tag">Command Center</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "Home"

    pending_nav = st.session_state.pop("pending_nav", None)
    if pending_nav in PAGES:
        st.session_state.nav_page = pending_nav

    page = st.radio(
        "Navigate",
        list(PAGES.keys()),
        index=list(PAGES.keys()).index(st.session_state.nav_page)
        if st.session_state.nav_page in PAGES
        else 0,
        label_visibility="collapsed",
        key="nav_page",
        format_func=lambda x: {
            "Home": "🏠  Home",
            "Payroll": "💰  Payroll",
            "Flag Sheet": "📋  Flag Sheet",
            "Warranty": "🛡️  Warranty",
            "Inventory": "📦  Inventory",
            "Reports": "📊  Reports",
        }[x],
    )

    st.markdown("---")

    db_status = "ONLINE" if is_configured() else "OFFLINE"
    st.markdown(
        f"""
        <div class="sidebar-footer">
            <div>Database <strong>{db_status}</strong></div>
            <div style="margin-top:0.35rem">v0.2 · Supabase</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if PAGES[page] is None:
    labels = {"Inventory": "Inventory"}
    st.markdown(
        coming_soon_panel(
            labels[page] + " — Coming Soon",
            "This module is on the roadmap. Payroll is live and ready to build on.",
        ),
        unsafe_allow_html=True,
    )
else:
    PAGES[page]()

import sys

import streamlit as st

# Streamlit Community Cloud currently defaults to Python 3.14, which breaks this app
# (redacted KeyError / dataclass failures during import). Require 3.12 or 3.11.
if sys.version_info >= (3, 14):
    st.set_page_config(page_title="Fixed Ops Hub", page_icon="⚡", layout="wide")
    st.error(
        f"Fixed Ops Hub cannot run on Python {sys.version_info.major}.{sys.version_info.minor}."
    )
    st.markdown(
        """
### Fix in Streamlit Cloud (about 1 minute)

1. Open **Manage app** (bottom right) → **Settings**
2. Set **Python version** to **3.12** (or **3.11**)
3. Click **Save**, then **Reboot app**

If Python version is locked, **delete the app** and **Create app** again — choose
**Python 3.12** under **Advanced settings**, then paste your secrets.
"""
    )
    st.stop()

from lib.app_auth import (
    allowed_pages,
    clamp_nav_page,
    current_user_label,
    is_parts_manager,
    require_login,
    sign_out,
)
from lib.page_ui import coming_soon_panel
from lib.supabase_client import is_configured
from styles import CUSTOM_CSS
from views import flag_sheet, home, labor_rate, payroll, parts, reports, warranty, warranty_admin_bonus, csi_bonus, eom_report

st.set_page_config(
    page_title="Fixed Ops Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if not require_login():
    st.stop()

ALL_PAGES = {
    "Home": home.render,
    "Payroll": payroll.render,
    "Flag Sheet": flag_sheet.render,
    "Warranty": warranty.render,
    "Warranty Admin Bonus": warranty_admin_bonus.render,
    "CSI Bonus": csi_bonus.render,
    "EOM Report": eom_report.render,
    "Labor Rate": labor_rate.render,
    "Parts": parts.render,
    "Reports": reports.render,
}

NAV_LABELS = {
    "Home": "🏠  Home",
    "Payroll": "💰  Payroll",
    "Flag Sheet": "📋  Flag Sheet",
    "Warranty": "🛡️  Warranty",
    "Warranty Admin Bonus": "🏅  Warranty Admin Bonus",
    "CSI Bonus": "⭐  CSI Bonus",
    "EOM Report": "📅  EOM Report",
    "Labor Rate": "📈  Labor Rate",
    "Parts": "🔩  Parts",
    "Reports": "📊  Reports",
}

visible_page_names = allowed_pages()
PAGES = {name: ALL_PAGES[name] for name in visible_page_names if name in ALL_PAGES}

with st.sidebar:
    brand_tag = "Parts" if is_parts_manager() else "Command Center"
    st.markdown(
        f"""
        <div class="brand-block">
            <div class="brand-logo">⚡</div>
            <div class="brand-name">Fixed Ops Hub</div>
            <div class="brand-tag">{brand_tag}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Signed in as **{current_user_label()}**")

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = visible_page_names[0] if visible_page_names else "Parts"

    pending_nav = st.session_state.pop("pending_nav", None)
    if pending_nav in PAGES:
        st.session_state.nav_page = pending_nav

    st.session_state.nav_page = clamp_nav_page(st.session_state.nav_page)

    page = st.radio(
        "Navigate",
        list(PAGES.keys()),
        index=list(PAGES.keys()).index(st.session_state.nav_page)
        if st.session_state.nav_page in PAGES
        else 0,
        label_visibility="collapsed",
        key="nav_page",
        format_func=lambda x: NAV_LABELS.get(x, x),
    )

    st.markdown("---")
    if st.button("Sign out", use_container_width=True):
        sign_out()
        st.rerun()

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

if PAGES.get(page) is None:
    st.markdown(
        coming_soon_panel(
            f"{page} — Coming Soon",
            "This module is on the roadmap. Payroll is live and ready to build on.",
        ),
        unsafe_allow_html=True,
    )
else:
    if page == "Reports":
        reports.render(parts_only=is_parts_manager())
    else:
        PAGES[page]()

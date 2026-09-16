import sys

import streamlit as st

# Streamlit Community Cloud often defaults to Python 3.13/3.14, which breaks this app
# (redacted ImportError / KeyError / dataclass failures during import). Require 3.12 or 3.11.
_PY = sys.version_info
if _PY >= (3, 13):
    st.set_page_config(page_title="Fixed Ops Hub", page_icon="⚡", layout="wide")
    st.error(
        f"Fixed Ops Hub cannot run on Python {_PY.major}.{_PY.minor}."
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

try:
    from lib.app_auth import (
        allowed_pages,
        auth_enabled,
        clamp_nav_page,
        current_user_label,
        is_parts_manager,
        needs_password_warning,
        require_login,
        sign_out,
    )
    from lib.page_ui import coming_soon_panel, html_text
    from lib.supabase_client import configured_key_role, is_configured
    from styles import CUSTOM_CSS
    from views import (
        advisor_training,
        csi_bonus,
        eom_report,
        flag_sheet,
        home,
        labor_rate,
        payroll,
        parts,
        reports,
        warranty,
        warranty_admin_bonus,
    )
except Exception as exc:
    st.set_page_config(page_title="Fixed Ops Hub", page_icon="⚡", layout="wide")
    st.error(
        f"App failed to start on Python {_PY.major}.{_PY.minor}: "
        f"{type(exc).__name__}"
    )
    st.caption(str(exc)[:500] or "No details available.")
    st.markdown(
        """
### Most common fix

Streamlit Cloud must use **Python 3.12** (or **3.11**):

1. **Manage app** → **Settings** → **Python version** → **3.12**
2. **Save**, then **Reboot app**

If the version can’t be changed, delete and recreate the app with **Python 3.12**
under Advanced settings, then paste your secrets again.
"""
    )
    st.stop()


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
    "Advisor Training": advisor_training.render,
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
    "Advisor Training": "🎓  Advisor Training",
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
            <div class="brand-tag">{html_text(brand_tag)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Signed in as **{current_user_label()}**")
    if needs_password_warning(database_configured=is_configured(), auth_on=auth_enabled()):
        st.warning(
            "No APP_PASSWORD is set. Anyone with this URL can open payroll and reports. "
            "Add APP_PASSWORD in Streamlit secrets or .env."
        )
    if configured_key_role() == "anon":
        st.warning(
            "SUPABASE_KEY looks like the anon/publishable key. "
            "Use the service_role key so cloud saves still work after RLS is enabled."
        )

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = visible_page_names[0] if visible_page_names else "Parts"

    pending_nav = st.session_state.pop("pending_nav", None)
    if pending_nav in PAGES:
        st.session_state.nav_page = pending_nav

    st.session_state.nav_page = clamp_nav_page(st.session_state.nav_page)

    st.markdown('<div class="sidebar-nav-list">', unsafe_allow_html=True)
    with st.container(key="sidebar_nav"):
        for page_name in PAGES.keys():
            slug = page_name.lower().replace(" ", "-")
            active = st.session_state.nav_page == page_name
            if st.button(
                NAV_LABELS.get(page_name, page_name),
                key=f"sidebar_nav_{slug}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                if st.session_state.nav_page != page_name:
                    st.session_state.nav_page = page_name
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    page = st.session_state.nav_page

    st.markdown("---")
    if st.button("Sign out", use_container_width=True):
        sign_out()
        st.rerun()

    db_status = "ONLINE" if is_configured() else "OFFLINE"
    st.markdown(
        f"""
        <div class="sidebar-footer">
            <div>Database <strong>{db_status}</strong></div>
            <div style="margin-top:0.35rem">v0.3 · Supabase</div>
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

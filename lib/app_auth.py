"""Optional password gate with role-based access for cloud deployments."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

ROLE_ADMIN = "admin"
ROLE_PARTS_MANAGER = "parts_manager"

# Full navigation order for admins / local (no password) sessions.
ALL_PAGES = [
    "Home",
    "Payroll",
    "Flag Sheet",
    "Warranty",
    "Warranty Admin Bonus",
    "EOM Report",
    "Labor Rate",
    "Parts",
    "Reports",
]

PARTS_MANAGER_PAGES = ["Parts", "Reports"]


def _secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default) or default).strip()
    except Exception:
        return default


def _admin_password() -> str:
    return _secret("APP_PASSWORD")


def _parts_manager_password() -> str:
    return _secret("PARTS_MANAGER_PASSWORD")


def _parts_manager_label() -> str:
    return _secret("PARTS_MANAGER_LABEL", "Parts Manager") or "Parts Manager"


def auth_enabled() -> bool:
    return bool(_admin_password() or _parts_manager_password())


def current_role() -> str:
    return str(st.session_state.get("fixed_ops_role") or ROLE_ADMIN)


def current_user_label() -> str:
    role = current_role()
    if role == ROLE_PARTS_MANAGER:
        return str(st.session_state.get("fixed_ops_user_label") or _parts_manager_label())
    return str(st.session_state.get("fixed_ops_user_label") or "Admin")


def is_parts_manager() -> bool:
    return current_role() == ROLE_PARTS_MANAGER


def allowed_pages(role: Optional[str] = None) -> List[str]:
    role = role or current_role()
    if role == ROLE_PARTS_MANAGER:
        return list(PARTS_MANAGER_PAGES)
    return list(ALL_PAGES)


def default_page_for_role(role: Optional[str] = None) -> str:
    pages = allowed_pages(role)
    return pages[0] if pages else "Home"


def resolve_login(
    entered: str,
    *,
    admin_password: str = "",
    parts_manager_password: str = "",
    parts_manager_label: str = "Parts Manager",
) -> Optional[Tuple[str, str]]:
    """Return (role, display_label) when the password matches."""
    entered = (entered or "").strip()
    if not entered:
        return None
    if admin_password and entered == admin_password:
        return ROLE_ADMIN, "Admin"
    if parts_manager_password and entered == parts_manager_password:
        return ROLE_PARTS_MANAGER, parts_manager_label or "Parts Manager"
    return None


def _match_password(entered: str) -> Optional[Tuple[str, str]]:
    return resolve_login(
        entered,
        admin_password=_admin_password(),
        parts_manager_password=_parts_manager_password(),
        parts_manager_label=_parts_manager_label(),
    )


def sign_out() -> None:
    for key in (
        "fixed_ops_authenticated",
        "fixed_ops_role",
        "fixed_ops_user_label",
        "nav_page",
        "pending_nav",
    ):
        st.session_state.pop(key, None)


def require_login() -> bool:
    """Gate the app. Returns True when the session may proceed."""
    if not auth_enabled():
        st.session_state.setdefault("fixed_ops_role", ROLE_ADMIN)
        st.session_state.setdefault("fixed_ops_user_label", "Admin")
        return True

    if st.session_state.get("fixed_ops_authenticated"):
        return True

    st.markdown("## Fixed Ops Hub")
    st.caption("Sign in with your assigned password.")
    entered = st.text_input("Password", type="password", key="fixed_ops_login_password")
    if st.button("Sign in", type="primary", use_container_width=True):
        matched = _match_password(entered)
        if matched:
            role, label = matched
            st.session_state.fixed_ops_authenticated = True
            st.session_state.fixed_ops_role = role
            st.session_state.fixed_ops_user_label = label
            st.session_state.nav_page = default_page_for_role(role)
            st.rerun()
        st.error("Incorrect password.")
    return False


def clamp_nav_page(page: str) -> str:
    allowed = allowed_pages()
    if page in allowed:
        return page
    return default_page_for_role()

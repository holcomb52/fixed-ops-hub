"""Persist payroll rosters to Supabase so changes survive cloud app restarts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from lib.supabase_client import get_supabase

TABLE = "payroll_rosters"

ROSTER_KEY_ADVISORS = "advisors"
ROSTER_KEY_TECHNICIANS = "technicians"
ROSTER_KEY_RECEPTIONISTS = "receptionists"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_roster_data(roster_key: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    if not client:
        return None
    try:
        result = client.table(TABLE).select("data").eq("roster_key", roster_key).limit(1).execute()
        if result.data:
            data = result.data[0].get("data")
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def save_roster_data(
    roster_key: str,
    data: Dict[str, Any],
    session_error_key: str = "",
) -> Tuple[bool, str]:
    client = get_supabase()
    if not client:
        return True, ""

    row = {
        "roster_key": roster_key,
        "data": data,
        "updated_at": _now_iso(),
    }
    try:
        existing = client.table(TABLE).select("roster_key").eq("roster_key", roster_key).execute()
        if existing.data:
            client.table(TABLE).update(
                {"data": data, "updated_at": row["updated_at"]}
            ).eq("roster_key", roster_key).execute()
        else:
            client.table(TABLE).insert(row).execute()
        _notify_roster_sync(session_error_key, True, "")
        return True, ""
    except Exception as exc:
        err = str(exc)
        _notify_roster_sync(session_error_key, False, err)
        return False, err


def _notify_roster_sync(session_error_key: str, ok: bool, err: str) -> None:
    if not session_error_key:
        return
    try:
        import streamlit as st

        if not ok and err:
            st.session_state[session_error_key] = err
        elif ok:
            st.session_state.pop(session_error_key, None)
    except Exception:
        pass

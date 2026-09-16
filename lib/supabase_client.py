from __future__ import annotations

import base64
import json
import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client


def _secret_get(name: str) -> str:
    """Read a Streamlit secret without raising when secrets are missing/partial."""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    if value is None:
        return ""
    return str(value).strip()


def jwt_role(key: str) -> str:
    """Return the Supabase JWT role claim, or empty when the key is not a JWT."""
    try:
        parts = (key or "").split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return str(data.get("role") or "").strip()
    except Exception:
        return ""


def _credentials() -> tuple[str, str]:
    load_dotenv()
    url = (os.getenv("SUPABASE_URL") or "").strip() or _secret_get("SUPABASE_URL")
    key = (os.getenv("SUPABASE_KEY") or "").strip() or _secret_get("SUPABASE_KEY")
    return url, key


@st.cache_resource
def get_supabase():
    """Return a Supabase client, or None when credentials are not configured."""
    url, key = _credentials()
    if not url or not key:
        return None
    return create_client(url, key)


def is_configured() -> bool:
    return get_supabase() is not None


def configured_key_role() -> str:
    """Role encoded in the configured Supabase key (service_role / anon / '')."""
    _url, key = _credentials()
    return jwt_role(key) if key else ""

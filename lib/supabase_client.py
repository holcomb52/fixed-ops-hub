import os
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client


def _secret_get(name: str) -> str:
    """Read a Streamlit secret without raising when secrets are missing/partial."""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    if value is None:
        return ""
    return str(value).strip()


@st.cache_resource
def get_supabase() -> Optional[Client]:
    load_dotenv()

    url = (os.getenv("SUPABASE_URL") or "").strip() or _secret_get("SUPABASE_URL")
    key = (os.getenv("SUPABASE_KEY") or "").strip() or _secret_get("SUPABASE_KEY")

    if not url or not key:
        return None

    return create_client(url, key)


def is_configured() -> bool:
    return get_supabase() is not None

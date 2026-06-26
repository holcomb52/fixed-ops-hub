"""Shared Supabase upsert helpers for payroll run storage."""

from __future__ import annotations

from typing import Dict, Optional, Tuple


def upsert_payroll_run(client, table: str, row: dict, run_id: str) -> Tuple[bool, str]:
    """Insert or update a payroll run in Supabase. Returns (ok, error_message)."""
    try:
        existing = client.table(table).select("id").eq("id", run_id).execute()
        if existing.data:
            client.table(table).update(row).eq("id", run_id).execute()
        else:
            insert_row = dict(row)
            if "created_at" not in insert_row:
                insert_row["created_at"] = insert_row.get("updated_at") or insert_row.get("completed_at")
            client.table(table).insert(insert_row).execute()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def merge_run_records(existing: Optional[dict], incoming: dict) -> dict:
    """Merge list metadata without dropping a full local snapshot."""
    if not existing:
        return incoming
    merged = {**existing, **incoming}
    if incoming.get("snapshot"):
        merged["snapshot"] = incoming["snapshot"]
    elif existing.get("snapshot"):
        merged["snapshot"] = existing["snapshot"]
    return merged


def load_remote_run(client, table: str, run_id: str) -> Optional[dict]:
    try:
        result = client.table(table).select("*").eq("id", run_id).execute()
        if result.data:
            return result.data[0]
    except Exception:
        return None
    return None

"""Shared Supabase upsert helpers for payroll run storage."""

from __future__ import annotations

from typing import List, Optional, Tuple

from lib.json_safe import json_safe


def upsert_payroll_run(client, table: str, row: dict, run_id: str) -> Tuple[bool, str]:
    """Insert or update a payroll run in Supabase. Returns (ok, error_message)."""
    try:
        safe_row = json_safe(row)
        existing = client.table(table).select("id").eq("id", run_id).execute()
        if existing.data:
            client.table(table).update(safe_row).eq("id", run_id).execute()
        else:
            insert_row = dict(safe_row)
            if "created_at" not in insert_row:
                insert_row["created_at"] = insert_row.get("updated_at") or insert_row.get("completed_at")
            client.table(table).insert(insert_row).execute()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def find_run_id_for_pay_period(
    runs: List[dict],
    pay_period: str,
    *,
    prefer_status: Optional[str] = "draft",
) -> Optional[str]:
    """Find an existing run id for this pay period (prefer draft when completing)."""
    period = (pay_period or "").strip()
    if not period:
        return None
    preferred = None
    fallback = None
    for run in runs:
        if (run.get("pay_period") or "").strip() != period:
            continue
        run_id = run.get("id")
        if not run_id:
            continue
        if prefer_status and run.get("status") == prefer_status:
            preferred = run_id
            break
        if fallback is None:
            fallback = run_id
    return preferred or fallback


def merge_run_records(existing: Optional[dict], incoming: dict) -> dict:
    """Merge list metadata without dropping a full local snapshot.

    Prefer completed over draft so a stale remote draft cannot hide a successful
    Complete & Save (common when the flag PDF cloud upload fails after local save).
    """
    if not existing:
        return incoming
    merged = {**existing, **incoming}

    existing_status = existing.get("status")
    incoming_status = incoming.get("status")
    if existing_status == "completed" or incoming_status == "completed":
        merged["status"] = "completed"
    elif existing_status or incoming_status:
        merged["status"] = incoming_status or existing_status

    if incoming.get("snapshot"):
        merged["snapshot"] = incoming["snapshot"]
    elif existing.get("snapshot"):
        merged["snapshot"] = existing["snapshot"]

    # Keep local totals when the remote list row is metadata-only / empty.
    for key in (
        "grand_total",
        "grand_hours",
        "advisor_count",
        "employee_count",
        "pay_period",
        "flag_pdf_filename",
    ):
        if existing.get(key) not in (None, "") and incoming.get(key) in (None, ""):
            merged[key] = existing[key]

    return merged


def load_remote_run(client, table: str, run_id: str) -> Optional[dict]:
    try:
        result = client.table(table).select("*").eq("id", run_id).execute()
        if result.data:
            return result.data[0]
    except Exception:
        return None
    return None


def delete_remote_run(client, table: str, run_id: str) -> Tuple[bool, str]:
    """Delete a saved run from Supabase. Returns (ok, error_message)."""
    try:
        client.table(table).delete().eq("id", run_id).execute()
        return True, ""
    except Exception as exc:
        return False, str(exc)

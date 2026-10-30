"""Persist the warranty manual and optional repair-order audit history.

Local JSON is the fallback when Supabase is not configured. Cloud saves use the
service_role client, same as the other Fixed Ops Hub archives.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from lib.json_safe import json_safe
from lib.payroll_supabase_sync import delete_remote_run, load_remote_run, merge_run_records, upsert_payroll_run
from lib.supabase_client import get_supabase
from lib.warranty_audit_manual import build_manual_record

MANUAL_DIR = Path(__file__).resolve().parent.parent / "data" / "warranty_manual_archive"
AUDIT_DIR = Path(__file__).resolve().parent.parent / "data" / "warranty_audit_archive"
MANUAL_TABLE = "warranty_manuals"
AUDIT_TABLE = "warranty_audit_runs"
SQL_FILE = Path(__file__).resolve().parent.parent / "supabase" / "warranty_audit_tables.sql"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit_tables_sql() -> str:
    if SQL_FILE.exists():
        return SQL_FILE.read_text().strip()
    return ""


def cloud_error_message(raw: str) -> str:
    text = str(raw or "")
    if any(token in text for token in ("PGRST205", "Could not find the table", "does not exist")):
        return (
            "Saved on this computer, but Supabase is missing the warranty audit tables. "
            "Open Supabase → SQL Editor, run supabase/warranty_audit_tables.sql, then save again."
        )
    return f"Saved on this computer. Cloud sync failed: {text[:500]}"


def new_manual_record(filename: str, pdf_bytes: bytes) -> dict:
    return build_manual_record(
        filename,
        pdf_bytes,
        manual_id=str(uuid.uuid4()),
        uploaded_at=_now_iso(),
    )


def save_manual_record(record: dict) -> Tuple[dict, str]:
    """Replace the stored manual. Local save succeeds even when cloud sync fails."""
    stored = dict(record)
    stored["is_active"] = True
    _save_local_manual(stored)
    client = get_supabase()
    if not client:
        stored["storage_source"] = "local"
        return stored, ""
    try:
        _replace_remote_manual(client, stored)
    except Exception as exc:
        stored["storage_source"] = "local"
        return stored, cloud_error_message(str(exc))
    stored["storage_source"] = "supabase"
    return stored, ""


def load_active_manual() -> Optional[dict]:
    local = _load_local_manual()
    remote = None
    warning = ""
    client = get_supabase()
    if client:
        try:
            remote = _load_remote_manual(client)
        except Exception as exc:
            warning = cloud_error_message(str(exc))
    chosen, source = _pick_newer(local, remote)
    if chosen is None:
        return None
    chosen = dict(chosen)
    chosen["storage_source"] = source
    if warning and source == "local":
        chosen["storage_warning"] = warning
    if source == "supabase":
        _save_local_manual(chosen)
    return chosen


def save_audit_run(snapshot: dict, *, run_id: Optional[str] = None) -> Tuple[str, str]:
    run_id = run_id or str(uuid.uuid4())
    now = _now_iso()
    ro = snapshot.get("ro") or {}
    findings = snapshot.get("findings") or []
    required = [item for item in findings if item.get("counts_as_required_correction")]
    record = {
        "id": run_id,
        "ro_number": str(ro.get("ro_number") or "").strip(),
        "source_name": snapshot.get("source_name") or "",
        "status": "completed",
        "snapshot": snapshot,
        "finding_count": len(required),
        "critical_count": sum(1 for item in required if item.get("severity") == "critical"),
        "manual_id": snapshot.get("manual_id") or None,
        "completed_at": now,
        "updated_at": now,
    }
    _save_local_audit(run_id, record)
    client = get_supabase()
    if not client:
        return run_id, ""
    row = {
        "id": run_id,
        "ro_number": record["ro_number"],
        "source_name": record["source_name"],
        "status": "completed",
        "snapshot": snapshot,
        "finding_count": record["finding_count"],
        "critical_count": record["critical_count"],
        "manual_id": record["manual_id"],
        "completed_at": now,
        "updated_at": now,
    }
    ok, err = upsert_payroll_run(client, AUDIT_TABLE, row, run_id)
    if not ok:
        record["_sync_error"] = err
        _save_local_audit(run_id, record)
        return run_id, cloud_error_message(err)
    return run_id, ""


def list_warranty_audit_runs() -> List[dict]:
    runs: dict = {}
    for record in _list_local_audits():
        if record.get("id"):
            runs[record["id"]] = record
    client = get_supabase()
    if client:
        try:
            result = (
                client.table(AUDIT_TABLE)
                .select(
                    "id,ro_number,source_name,status,finding_count,critical_count,manual_id,completed_at,updated_at"
                )
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = merge_run_records(runs.get(row["id"]), {**row, "source": "supabase"})
        except Exception:
            pass
    return sorted(runs.values(), key=lambda item: item.get("completed_at") or "", reverse=True)


def load_warranty_audit_run(run_id: str) -> Optional[dict]:
    client = get_supabase()
    if client:
        remote = load_remote_run(client, AUDIT_TABLE, run_id)
        if remote:
            return remote
    return _load_local_audit(run_id)


def delete_warranty_audit_run(run_id: str) -> Tuple[bool, str]:
    if not run_id:
        return False, "Missing audit id."
    deleted_local = False
    path = AUDIT_DIR / run_id
    if path.exists():
        shutil.rmtree(path)
        deleted_local = True
    client = get_supabase()
    if client:
        ok, err = delete_remote_run(client, AUDIT_TABLE, run_id)
        if not ok:
            if deleted_local:
                return True, f"Removed locally; cloud delete failed: {err}"
            return False, err
        return True, ""
    if deleted_local:
        return True, ""
    return False, "Audit not found."


def apply_warranty_audit_snapshot_to_session(record: dict, run_id: str) -> None:
    import streamlit as st

    snapshot = dict(record.get("snapshot") or {})
    st.session_state.warranty_audit_result = snapshot
    st.session_state.warranty_audit_active_run_id = run_id
    ro_number = (record.get("ro_number") or (snapshot.get("ro") or {}).get("ro_number") or "").strip()
    st.session_state.warranty_audit_saved_label = ro_number or "Saved audit"


def _pick_newer(local: Optional[dict], remote: Optional[dict]) -> tuple[Optional[dict], str]:
    if local and remote:
        if _timestamp(remote) >= _timestamp(local):
            return remote, "supabase"
        return local, "local"
    if remote:
        return remote, "supabase"
    if local:
        return local, "local"
    return None, ""


def _timestamp(record: dict) -> str:
    value = record.get("uploaded_at") or record.get("updated_at") or ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _manual_path() -> Path:
    return MANUAL_DIR / "active" / "record.json"


def _save_local_manual(record: dict) -> None:
    path = _manual_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(json_safe(record), indent=2))
    temp.replace(path)


def _load_local_manual() -> Optional[dict]:
    path = _manual_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _replace_remote_manual(client, record: dict) -> None:
    row = {
        "id": record["id"],
        "filename": record.get("filename") or "",
        "title": record.get("title") or "",
        "page_count": int(record.get("page_count") or 0),
        "chunk_count": int(record.get("chunk_count") or 0),
        "text_characters": int(record.get("text_characters") or 0),
        "is_active": False,
        "warnings": record.get("warnings") or [],
        "chunks": record.get("chunks") or [],
        "uploaded_at": record.get("uploaded_at") or _now_iso(),
        "updated_at": record.get("uploaded_at") or _now_iso(),
    }
    client.table(MANUAL_TABLE).insert(json_safe(row)).execute()
    client.table(MANUAL_TABLE).update({"is_active": False}).eq("is_active", True).execute()
    client.table(MANUAL_TABLE).update({"is_active": True}).eq("id", record["id"]).execute()
    check = (
        client.table(MANUAL_TABLE)
        .select("id,is_active")
        .eq("id", record["id"])
        .limit(1)
        .execute()
    )
    flag = check.data[0].get("is_active") if check.data else False
    active = flag is True or flag == "true"
    if not active:
        raise RuntimeError(
            "The manual was stored on this computer but could not be marked active in Supabase."
        )
    client.table(MANUAL_TABLE).delete().eq("is_active", False).execute()


def _load_remote_manual(client) -> Optional[dict]:
    result = (
        client.table(MANUAL_TABLE)
        .select("*")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _audit_path(run_id: str) -> Path:
    return AUDIT_DIR / run_id


def _save_local_audit(run_id: str, record: dict) -> None:
    path = _audit_path(run_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "record.json").write_text(json.dumps(json_safe(record), indent=2))


def _load_local_audit(run_id: str) -> Optional[dict]:
    path = _audit_path(run_id) / "record.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _list_local_audits() -> List[dict]:
    if not AUDIT_DIR.exists():
        return []
    records = []
    for folder in AUDIT_DIR.iterdir():
        meta = folder / "record.json"
        if folder.is_dir() and meta.exists():
            try:
                records.append(json.loads(meta.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
    return records

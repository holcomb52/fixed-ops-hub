"""Persist the warranty manual and optional repair-order audit history.

Local JSON is the fallback when Supabase is not configured. Cloud saves use the
service_role client, same as the other Fixed Ops Hub archives.
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from lib.json_safe import json_safe
from lib.payroll_supabase_sync import delete_remote_run, load_remote_run, merge_run_records, upsert_payroll_run
from lib.supabase_client import get_supabase
from lib.warranty_audit_manual import build_manual_record, redact_secrets

MANUAL_DIR = Path(__file__).resolve().parent.parent / "data" / "warranty_manual_archive"
AUDIT_DIR = Path(__file__).resolve().parent.parent / "data" / "warranty_audit_archive"
MANUAL_TABLE = "warranty_manuals"
AUDIT_TABLE = "warranty_audit_runs"
SQL_FILE = Path(__file__).resolve().parent.parent / "supabase" / "warranty_audit_tables.sql"
MANUAL_KIND = "warranty_manual"
GUIDE_KIND = "audit_guide"


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
    return f"Saved on this computer. Cloud sync failed: {redact_secrets(text[:500])}"


def new_manual_record(filename: str, pdf_bytes: bytes) -> dict:
    return build_manual_record(
        filename,
        pdf_bytes,
        manual_id=str(uuid.uuid4()),
        uploaded_at=_now_iso(),
    )


def save_manual_record(record: dict, *, kind: str = "") -> Tuple[dict, str]:
    """Replace one stored reference document. Local save succeeds even when cloud sync fails."""
    stored = dict(record)
    stored["document_kind"] = kind or stored.get("document_kind") or MANUAL_KIND
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


def load_active_manual(kind: str = MANUAL_KIND) -> Optional[dict]:
    local = _load_local_manual(kind)
    remote = None
    warning = ""
    client = get_supabase()
    if client:
        try:
            remote = _load_remote_manual(client, kind)
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


def _uuid_or_none(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError):
        return None


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
        "manual_id": _uuid_or_none(snapshot.get("manual_id")),
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


_ARCHIVE_CACHE: dict[str, Path] = {}


def _archive_dir(preferred: Path) -> Path:
    """Use the repo data folder, or /tmp when Streamlit Cloud cannot write the repo."""
    key = str(preferred)
    cached = _ARCHIVE_CACHE.get(key)
    if cached is not None:
        return cached
    fallback = Path(tempfile.gettempdir()) / "fixed-ops-hub" / preferred.name
    for candidate in (preferred, fallback):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_ok"
            probe.write_text("1", encoding="utf-8")
            probe.unlink()
            _ARCHIVE_CACHE[key] = candidate
            return candidate
        except OSError:
            continue
    _ARCHIVE_CACHE[key] = fallback
    return fallback


def _manual_path(kind: str = MANUAL_KIND) -> Path:
    return _archive_dir(MANUAL_DIR) / (kind or MANUAL_KIND) / "record.json"


def _write_json(path: Path, payload: str) -> None:
    """Write JSON without letting a read-only Cloud disk crash the page."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(payload, encoding="utf-8")
        try:
            temp.replace(path)
        except OSError:
            path.write_text(payload, encoding="utf-8")
            try:
                temp.unlink()
            except OSError:
                pass
    except OSError:
        return


def _save_local_manual(record: dict) -> None:
    path = _manual_path(str(record.get("document_kind") or MANUAL_KIND))
    _write_json(path, json.dumps(json_safe(record), indent=2))


def _load_local_manual(kind: str = MANUAL_KIND) -> Optional[dict]:
    path = _manual_path(kind)
    if not path.exists() and kind == MANUAL_KIND:
        path = MANUAL_DIR / "active" / "record.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if kind == MANUAL_KIND and not data.get("document_kind"):
        data["document_kind"] = MANUAL_KIND
    if data.get("document_kind") not in {None, "", kind}:
        return None
    return data


def _replace_remote_manual(client, record: dict) -> None:
    kind = record.get("document_kind") or MANUAL_KIND
    row = {
        "id": record["id"],
        "filename": record.get("filename") or "",
        "title": record.get("title") or "",
        "page_count": int(record.get("page_count") or 0),
        "chunk_count": int(record.get("chunk_count") or 0),
        "text_characters": int(record.get("text_characters") or 0),
        "is_active": False,
        "document_kind": kind,
        "warnings": record.get("warnings") or [],
        "chunks": record.get("chunks") or [],
        "uploaded_at": record.get("uploaded_at") or _now_iso(),
        "updated_at": record.get("uploaded_at") or _now_iso(),
    }
    client.table(MANUAL_TABLE).insert(json_safe(row)).execute()
    client.table(MANUAL_TABLE).update({"is_active": False}).eq("is_active", True).eq("document_kind", kind).execute()
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
    client.table(MANUAL_TABLE).delete().eq("is_active", False).eq("document_kind", kind).execute()


def _load_remote_manual(client, kind: str = MANUAL_KIND) -> Optional[dict]:
    result = (
        client.table(MANUAL_TABLE)
        .select("*")
        .eq("is_active", True)
        .eq("document_kind", kind)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _audit_path(run_id: str) -> Path:
    return _archive_dir(AUDIT_DIR) / run_id


def _save_local_audit(run_id: str, record: dict) -> None:
    path = _audit_path(run_id) / "record.json"
    _write_json(path, json.dumps(json_safe(record), indent=2))


def _load_local_audit(run_id: str) -> Optional[dict]:
    path = _audit_path(run_id) / "record.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _list_local_audits() -> List[dict]:
    root = _archive_dir(AUDIT_DIR)
    if not root.exists():
        return []
    records = []
    for folder in root.iterdir():
        meta = folder / "record.json"
        if folder.is_dir() and meta.exists():
            try:
                records.append(json.loads(meta.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
    return records


LIVE_PHOTO_TABLE = "warranty_claim_live_photos"


def publish_live_photos(tray: list[dict]) -> str:
    """Upload any pictures the other device does not have yet."""
    client = get_supabase()
    if not client or not tray:
        return ""
    try:
        existing = _live_photo_index(client)
        position = max((row["position"] for row in existing.values()), default=0)
        for item in tray:
            sha = item.get("sha") or ""
            if not sha or sha in existing:
                continue
            position += 1
            client.table(LIVE_PHOTO_TABLE).insert(
                {
                    "sha": sha,
                    "name": item.get("name") or "photo.jpg",
                    "position": position,
                    "jpeg_b64": base64.b64encode(item["data"]).decode("ascii"),
                }
            ).execute()
    except Exception as exc:
        return cloud_error_message(str(exc))
    return ""


def fetch_live_photos(tray: list[dict]) -> tuple[list[dict], str]:
    """Return this device's pictures plus any new pictures saved from the other device."""
    client = get_supabase()
    if not client:
        return list(tray), ""
    try:
        remote = _live_photo_index(client)
    except Exception as exc:
        return list(tray), cloud_error_message(str(exc))
    by_sha = {item.get("sha"): item for item in tray if item.get("sha")}
    ordered = sorted(remote.values(), key=lambda row: row.get("position") or 0)
    merged: list[dict] = []
    for row in ordered:
        sha = row["sha"]
        if sha in by_sha:
            merged.append(by_sha[sha])
            continue
        try:
            loaded = (
                client.table(LIVE_PHOTO_TABLE)
                .select("jpeg_b64")
                .eq("sha", sha)
                .limit(1)
                .execute()
            )
            payload = (loaded.data or [{}])[0].get("jpeg_b64") or ""
            data = base64.b64decode(payload) if payload else b""
        except Exception as exc:
            return list(tray), cloud_error_message(str(exc))
        if not data:
            continue
        merged.append(
            {
                "name": row.get("name") or "photo.jpg",
                "sha": sha,
                "raw_sha": sha,
                "data": data,
            }
        )
    known = {item["sha"] for item in merged}
    for item in tray:
        if item.get("sha") not in known:
            merged.append(item)
    return merged, ""


def delete_live_photo(sha: str) -> str:
    client = get_supabase()
    if not client or not sha:
        return ""
    try:
        client.table(LIVE_PHOTO_TABLE).delete().eq("sha", sha).execute()
    except Exception as exc:
        return cloud_error_message(str(exc))
    return ""


def clear_live_photos() -> str:
    client = get_supabase()
    if not client:
        return ""
    try:
        client.table(LIVE_PHOTO_TABLE).delete().neq("sha", "").execute()
    except Exception as exc:
        return cloud_error_message(str(exc))
    return ""


def _live_photo_index(client) -> dict:
    result = (
        client.table(LIVE_PHOTO_TABLE)
        .select("sha,name,position")
        .order("position")
        .execute()
    )
    return {row["sha"]: row for row in (result.data or []) if row.get("sha")}

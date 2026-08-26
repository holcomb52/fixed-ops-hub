"""Persist parts stocking plans for Reports."""

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

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "parts_stocking_archive"
TABLE = "parts_stocking_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_path(run_id: str) -> Path:
    return ARCHIVE_DIR / run_id


def _save_local(run_id: str, record: dict):
    path = _local_path(run_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "record.json").write_text(json.dumps(json_safe(record), indent=2, allow_nan=False))


def _load_local(run_id: str) -> Optional[dict]:
    meta = _local_path(run_id) / "record.json"
    if not meta.exists():
        return None
    return json.loads(meta.read_text())


def _list_local() -> List[dict]:
    if not ARCHIVE_DIR.exists():
        return []
    runs = []
    for folder in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "record.json").exists():
            runs.append(json.loads((folder / "record.json").read_text()))
    return runs


def save_parts_stocking_run(
    snapshot: dict,
    *,
    run_id: Optional[str] = None,
    status: str = "completed",
    cloud_sync: bool = True,
) -> Tuple[str, str]:
    run_id = run_id or str(uuid.uuid4())
    now = _now_iso()
    record = {
        "id": run_id,
        "pay_period": snapshot.get("label") or "—",
        "status": status,
        "snapshot": snapshot,
        "grand_total": float(snapshot.get("order_total_cost", 0) or 0),
        "tech_count": float(snapshot.get("order_count", 0) or 0),
        "completed_at": now,
        "updated_at": now,
    }
    _save_local(run_id, record)

    sync_error = ""
    if not cloud_sync:
        return run_id, sync_error

    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "pay_period": record["pay_period"],
            "status": status,
            "snapshot": snapshot,
            "grand_total": record["grand_total"],
            "tech_count": record["tech_count"],
            "completed_at": now,
            "updated_at": now,
        }
        ok, err = upsert_payroll_run(client, TABLE, row, run_id)
        if not ok:
            sync_error = err
            record["_sync_error"] = err
            _save_local(run_id, record)
    return run_id, sync_error


def list_parts_stocking_runs() -> List[dict]:
    runs: dict = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select("id,pay_period,status,grand_total,tech_count,completed_at,updated_at")
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = merge_run_records(
                    runs.get(row["id"]),
                    {**row, "source": "supabase"},
                )
        except Exception:
            pass
    return sorted(runs.values(), key=lambda r: r.get("completed_at", ""), reverse=True)


def load_parts_stocking_run(run_id: str) -> Optional[dict]:
    client = get_supabase()
    if client:
        remote = load_remote_run(client, TABLE, run_id)
        if remote:
            return remote
    return _load_local(run_id)


def delete_parts_stocking_run(run_id: str) -> Tuple[bool, str]:
    if not run_id:
        return False, "Missing report id."
    deleted_local = False
    path = _local_path(run_id)
    if path.exists():
        shutil.rmtree(path)
        deleted_local = True

    client = get_supabase()
    if client:
        ok, err = delete_remote_run(client, TABLE, run_id)
        if not ok:
            if deleted_local:
                return True, f"Removed locally; cloud delete failed: {err}"
            return False, err
        return True, ""

    if deleted_local:
        return True, ""
    return False, "Report not found."

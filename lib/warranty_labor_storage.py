"""Persist warranty ELR analysis runs for save/reopen."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import streamlit as st

from lib.warranty_labor_calc import (
    WarrantyLaborRow,
    exclusion_widget_key,
    exclusion_widget_label,
    review_widget_key,
    summarize_reviewed_running_total,
    summarize_rows,
)
from lib.supabase_client import get_supabase
from lib.warranty_custom_exclusions import save_custom_exclusions

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "warranty_labor_archive"
TABLE = "warranty_labor_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_warranty_row(row: WarrantyLaborRow) -> dict:
    return asdict(row)


def deserialize_warranty_row(data: dict, index: Optional[int] = None) -> WarrantyLaborRow:
    fields = {f.name for f in WarrantyLaborRow.__dataclass_fields__.values()}
    payload = {key: data[key] for key in fields if key in data}
    if not payload.get("line_id"):
        recid = str(payload.get("recid", "row"))
        suffix = f"{index:04d}-" if index is not None else ""
        payload["line_id"] = f"{suffix}{recid}"
    return WarrantyLaborRow(**payload)


def serialize_warranty_session(
    rows: List[WarrantyLaborRow],
    source_name: str,
    sheet_name: str,
    custom_exclusions: List[str],
    upload_bytes: bytes | None = None,
    reviewed_recids: Optional[List[str]] = None,
) -> dict:
    summary = summarize_reviewed_running_total(rows, reviewed_recids or [])
    return {
        "source_name": source_name,
        "sheet_name": sheet_name,
        "run_label": f"{source_name} · {sheet_name}",
        "rows": [serialize_warranty_row(row) for row in rows],
        "custom_exclusions": list(custom_exclusions),
        "reviewed_recids": list(reviewed_recids or []),
        "source_xlsx_b64": base64.b64encode(upload_bytes).decode("ascii") if upload_bytes else "",
        "totals": {
            "effective_labor_rate": summary.effective_labor_rate,
            "total_lbr_sale": summary.total_lbr_sale,
            "total_tech_hrs": summary.total_tech_hrs,
            "included_rows": summary.included_rows,
            "excluded_rows": summary.excluded_rows,
            "total_rows": summary.total_rows,
        },
        "saved_at": _now_iso(),
    }


def _clear_exclusion_widgets():
    for key in list(st.session_state.keys()):
        if key.startswith("warranty_exc_"):
            del st.session_state[key]


def _clear_review_widgets():
    for key in list(st.session_state.keys()):
        if key.startswith("warranty_ro_reviewed_"):
            del st.session_state[key]


def apply_warranty_snapshot_to_session(record: dict, run_id: str):
    snapshot = record.get("snapshot", {})
    rows = [
        deserialize_warranty_row(item, index=index)
        for index, item in enumerate(snapshot.get("rows", []))
    ]
    custom_exclusions = list(snapshot.get("custom_exclusions", []))

    st.session_state.active_warranty_run_id = run_id
    st.session_state.warranty_labor_rows = rows
    st.session_state.warranty_custom_exclusions = custom_exclusions
    st.session_state.warranty_upload_name = snapshot.get("source_name", "warranty_labor.xlsx")
    st.session_state.warranty_sheet_name = snapshot.get("sheet_name", "Sheet1")
    st.session_state.warranty_run_label = snapshot.get("run_label", st.session_state.warranty_upload_name)

    source_b64 = snapshot.get("source_xlsx_b64", "")
    if source_b64:
        st.session_state.warranty_upload_bytes = base64.b64decode(source_b64)
        size = len(st.session_state.warranty_upload_bytes)
        name = st.session_state.warranty_upload_name
        st.session_state.warranty_upload_id = f"{name}:{size}"
        st.session_state.warranty_parsed_id = f"{name}:{size}:{st.session_state.warranty_sheet_name}"
    else:
        st.session_state.warranty_upload_bytes = None
        st.session_state.warranty_upload_id = f"saved:{run_id}"
        st.session_state.warranty_parsed_id = f"saved:{run_id}:{st.session_state.warranty_sheet_name}"

    reviewed_recids = {
        normalize_recid(recid) for recid in snapshot.get("reviewed_recids", [])
    }
    st.session_state.warranty_reviewed_ros = reviewed_recids
    st.session_state.warranty_last_upload_added_recids = set()

    _clear_exclusion_widgets()
    _clear_review_widgets()
    for row in rows:
        st.session_state[exclusion_widget_key(row)] = exclusion_widget_label(row.exclusion)
    for recid in reviewed_recids:
        st.session_state[review_widget_key(recid)] = True

    save_custom_exclusions(custom_exclusions)


def _local_path(run_id: str) -> Path:
    return ARCHIVE_DIR / run_id


def _save_local(run_id: str, record: dict):
    path = _local_path(run_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "record.json").write_text(json.dumps(record, indent=2))


def _load_local(run_id: str) -> Optional[dict]:
    meta_file = _local_path(run_id) / "record.json"
    if not meta_file.exists():
        return None
    return json.loads(meta_file.read_text())


def _list_local() -> List[dict]:
    if not ARCHIVE_DIR.exists():
        return []
    runs = []
    for folder in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "record.json").exists():
            runs.append(json.loads((folder / "record.json").read_text()))
    return runs


def save_warranty_labor_run(
    rows: List[WarrantyLaborRow],
    source_name: str,
    sheet_name: str,
    custom_exclusions: List[str],
    upload_bytes: bytes | None = None,
    run_id: Optional[str] = None,
    reviewed_recids: Optional[List[str]] = None,
) -> str:
    snapshot = serialize_warranty_session(
        rows,
        source_name,
        sheet_name,
        custom_exclusions,
        upload_bytes=upload_bytes,
        reviewed_recids=reviewed_recids,
    )
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()
    save_custom_exclusions(custom_exclusions)

    record = {
        "id": run_id,
        "run_label": snapshot["run_label"],
        "source_name": source_name,
        "sheet_name": sheet_name,
        "status": "saved",
        "snapshot": snapshot,
        "effective_labor_rate": snapshot["totals"]["effective_labor_rate"],
        "included_rows": snapshot["totals"]["included_rows"],
        "total_rows": snapshot["totals"]["total_rows"],
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    _save_local(run_id, record)

    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "run_label": record["run_label"],
            "source_name": source_name,
            "sheet_name": sheet_name,
            "status": "saved",
            "snapshot": snapshot,
            "effective_labor_rate": snapshot["totals"]["effective_labor_rate"],
            "included_rows": snapshot["totals"]["included_rows"],
            "total_rows": snapshot["totals"]["total_rows"],
            "completed_at": completed_at,
            "updated_at": completed_at,
        }
        try:
            existing = client.table(TABLE).select("id").eq("id", run_id).execute()
            if existing.data:
                client.table(TABLE).update(row).eq("id", run_id).execute()
            else:
                row["created_at"] = completed_at
                client.table(TABLE).insert(row).execute()
        except Exception:
            pass

    return run_id


def list_warranty_labor_runs() -> List[dict]:
    runs: dict = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select(
                    "id,run_label,source_name,sheet_name,status,"
                    "effective_labor_rate,included_rows,total_rows,completed_at,updated_at"
                )
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = {**row, "source": "supabase"}
        except Exception:
            pass

    return sorted(runs.values(), key=lambda item: item.get("completed_at", ""), reverse=True)


def load_warranty_labor_run(run_id: str) -> Optional[dict]:
    record = _load_local(run_id)

    client = get_supabase()
    if client and not record:
        try:
            result = client.table(TABLE).select("*").eq("id", run_id).execute()
            if result.data:
                record = result.data[0]
        except Exception:
            pass

    return record

"""Persist completed technician payroll runs."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from lib.payroll_export_data import build_payroll_snapshot
from lib.supabase_client import get_supabase, is_configured
from lib.tech_payroll_calc import TechPayrollRow
from lib.tech_roster import teams_from_saved_data
from views.payroll_helpers import apply_teams_to_session, set_pay_period_from_string

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "payroll_archive"
TABLE = "tech_payroll_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_payroll_session(synced_teams: Dict[str, List[TechPayrollRow]], pay_period: str) -> dict:
    """Capture full payroll state for save/reopen."""
    teams_data = {}
    for team_name, rows in synced_teams.items():
        teams_data[team_name] = []
        for i, row in enumerate(rows):
            teams_data[team_name].append({
                "index": i,
                "name": row.name,
                "tech_number": row.tech_number,
                "hours": row.flat_rate_hours,
                "dollars": row.dollars_earned,
                "rate": row.hourly_rate,
                "train": row.training_hours,
                "spiff": row.spiff,
                "notes": row.notes,
                "foreman_rule": row.foreman_rule,
                "quick_lube_sources": row.quick_lube_sources,
            })

    snapshot = build_payroll_snapshot(synced_teams, pay_period)
    return {
        "pay_period": pay_period,
        "teams": teams_data,
        "totals": {
            "grand_hours": snapshot["grand_hours"],
            "grand_total": snapshot["grand_total"],
        },
        "saved_at": _now_iso(),
    }


def snapshot_to_teams(snapshot: dict) -> Dict[str, List[TechPayrollRow]]:
    """Rebuild team rows from a saved snapshot."""
    return teams_from_saved_data(snapshot.get("teams", {}))


def apply_snapshot_to_session(
    snapshot: dict,
    run_id: str,
    flag_pdf_bytes: Optional[bytes],
    filename: str,
    status: str = "completed",
):
    """Restore a saved payroll run into the active session."""
    st.session_state.active_run_id = run_id
    pay_period = snapshot.get("pay_period", "")
    st.session_state.pay_period = pay_period
    set_pay_period_from_string(pay_period)
    st.session_state.pdf_loaded = bool(flag_pdf_bytes)
    st.session_state.flag_pdf_bytes = flag_pdf_bytes
    st.session_state.flag_pdf_filename = filename or "flag_sheet.pdf"
    st.session_state.payroll_completed = status == "completed"

    teams = teams_from_saved_data(snapshot.get("teams", {}))
    values_by_name = {}
    for team_name, techs in snapshot.get("teams", {}).items():
        for tech in techs:
            values_by_name[tech["name"]] = {
                "hours": float(tech.get("hours", 0) or 0),
                "dollars": float(tech.get("dollars", 0) or 0),
                "rate": float(tech.get("rate", 0) or 0),
                "train": float(tech.get("train", 0) or 0),
                "spiff": float(tech.get("spiff", 0) or 0),
                "notes": str(tech.get("notes", "") or ""),
                "tech_number": str(tech.get("tech_number", "") or ""),
            }
    apply_teams_to_session(teams, values_by_name)


def _local_path(run_id: str) -> Path:
    return ARCHIVE_DIR / run_id


def _save_local(run_id: str, record: dict, flag_pdf_bytes: Optional[bytes]):
    path = _local_path(run_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "record.json").write_text(json.dumps(record, indent=2))
    if flag_pdf_bytes:
        (path / "flag.pdf").write_bytes(flag_pdf_bytes)


def _load_local(run_id: str) -> Optional[dict]:
    path = _local_path(run_id)
    meta_file = path / "record.json"
    if not meta_file.exists():
        return None
    record = json.loads(meta_file.read_text())
    flag_path = path / "flag.pdf"
    record["_flag_pdf_bytes"] = flag_path.read_bytes() if flag_path.exists() else None
    return record


def _list_local() -> List[dict]:
    if not ARCHIVE_DIR.exists():
        return []
    runs = []
    for folder in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "record.json").exists():
            rec = json.loads((folder / "record.json").read_text())
            runs.append(rec)
    return runs


def save_payroll_run(
    synced_teams: Dict[str, List[TechPayrollRow]],
    pay_period: str,
    flag_pdf_bytes: Optional[bytes],
    flag_pdf_filename: str,
    run_id: Optional[str] = None,
) -> str:
    """Save or update a completed payroll run. Returns run id."""
    snapshot = serialize_payroll_session(synced_teams, pay_period)
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()

    record = {
        "id": run_id,
        "pay_period": pay_period,
        "status": "completed",
        "snapshot": snapshot,
        "flag_pdf_filename": flag_pdf_filename,
        "grand_total": snapshot["totals"]["grand_total"],
        "grand_hours": snapshot["totals"]["grand_hours"],
        "completed_at": completed_at,
        "updated_at": completed_at,
    }

    _save_local(run_id, record, flag_pdf_bytes)

    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "pay_period": pay_period,
            "status": "completed",
            "snapshot": snapshot,
            "flag_pdf_filename": flag_pdf_filename,
            "grand_total": snapshot["totals"]["grand_total"],
            "grand_hours": snapshot["totals"]["grand_hours"],
            "completed_at": completed_at,
            "updated_at": completed_at,
        }
        if flag_pdf_bytes:
            row["flag_pdf_base64"] = base64.b64encode(flag_pdf_bytes).decode("ascii")

        existing = client.table(TABLE).select("id").eq("id", run_id).execute()
        if existing.data:
            client.table(TABLE).update(row).eq("id", run_id).execute()
        else:
            row["created_at"] = completed_at
            client.table(TABLE).insert(row).execute()

    return run_id


def list_payroll_runs() -> List[dict]:
    """List completed runs, newest first."""
    runs: Dict[str, dict] = {}

    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select("id,pay_period,status,grand_total,grand_hours,completed_at,updated_at,flag_pdf_filename")
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = {**row, "source": "supabase"}
        except Exception:
            pass

    return sorted(runs.values(), key=lambda r: r.get("completed_at", ""), reverse=True)


def load_payroll_run(run_id: str) -> Optional[dict]:
    """Load a saved payroll run including flag PDF bytes."""
    record = _load_local(run_id)
    flag_bytes = record.pop("_flag_pdf_bytes", None) if record else None

    client = get_supabase()
    if client:
        try:
            result = client.table(TABLE).select("*").eq("id", run_id).execute()
            if result.data:
                row = result.data[0]
                if not record:
                    record = row
                b64 = row.get("flag_pdf_base64")
                if b64:
                    flag_bytes = base64.b64decode(b64)
        except Exception:
            pass

    if not record:
        return None

    record["flag_pdf_bytes"] = flag_bytes
    return record


def storage_available() -> bool:
    return True  # local always; supabase optional boost

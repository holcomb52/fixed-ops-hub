"""Persist completed technician payroll runs."""

from __future__ import annotations

import base64
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_supabase_sync import delete_remote_run, load_remote_run, merge_run_records, upsert_payroll_run
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
                "tech_category": row.tech_category,
                "cp_hours": row.cp_hours,
                "cp_ro_count": row.cp_ro_count,
                "cp_hrs_per_ro": row.cp_hrs_per_ro,
                "closing_pct": row.closing_pct,
                "supplemental_bonus": row.supplemental_bonus,
                "supplemental_tier": row.supplemental_tier,
                "pay_plan": row.pay_plan,
                "weekly_hour_guarantee": row.weekly_hour_guarantee,
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
                "cp_hours": float(tech.get("cp_hours", 0) or 0),
                "cp_ro_count": int(tech.get("cp_ro_count", 0) or 0),
                "cp_hrs_per_ro": float(tech.get("cp_hrs_per_ro", 0) or 0),
                "closing_pct": float(tech.get("closing_pct", 0) or 0),
                "supplemental_bonus": float(tech.get("supplemental_bonus", 0) or 0),
                "supplemental_tier": str(tech.get("supplemental_tier", "") or ""),
            }
    apply_teams_to_session(teams, values_by_name)

    cp_by_name = {}
    closing_by_name = {}
    for techs in snapshot.get("teams", {}).values():
        for tech in techs:
            name = tech["name"]
            cp_hrs_per_ro = float(tech.get("cp_hrs_per_ro", 0) or 0)
            if cp_hrs_per_ro or tech.get("cp_hours"):
                cp_by_name[name] = {
                    "cp_hours": float(tech.get("cp_hours", 0) or 0),
                    "cp_ro_count": int(tech.get("cp_ro_count", 0) or 0),
                    "cp_hrs_per_ro": cp_hrs_per_ro,
                }
            closing_pct = float(tech.get("closing_pct", 0) or 0)
            if closing_pct:
                closing_by_name[name] = closing_pct
    st.session_state.tech_cp_metrics_by_name = cp_by_name
    st.session_state.tech_closing_by_name = closing_by_name
    st.session_state.upsell_loaded = bool(closing_by_name)


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
    status: str = "completed",
) -> Tuple[str, str]:
    """Save or update a payroll run. Returns run id."""
    snapshot = serialize_payroll_session(synced_teams, pay_period)
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()

    record = {
        "id": run_id,
        "pay_period": pay_period,
        "status": status,
        "snapshot": snapshot,
        "flag_pdf_filename": flag_pdf_filename,
        "grand_total": snapshot["totals"]["grand_total"],
        "grand_hours": snapshot["totals"]["grand_hours"],
        "completed_at": completed_at,
        "updated_at": completed_at,
    }

    _save_local(run_id, record, flag_pdf_bytes)

    sync_error = ""
    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "pay_period": pay_period,
            "status": status,
            "snapshot": snapshot,
            "flag_pdf_filename": flag_pdf_filename,
            "grand_total": snapshot["totals"]["grand_total"],
            "grand_hours": snapshot["totals"]["grand_hours"],
            "completed_at": completed_at,
            "updated_at": completed_at,
        }
        if flag_pdf_bytes:
            row["flag_pdf_base64"] = base64.b64encode(flag_pdf_bytes).decode("ascii")

        ok, err = upsert_payroll_run(client, TABLE, row, run_id)
        if not ok:
            sync_error = err
            record["_sync_error"] = err
            _save_local(run_id, record, flag_pdf_bytes)

    return run_id, sync_error


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
                runs[row["id"]] = merge_run_records(
                    runs.get(row["id"]),
                    {**row, "source": "supabase"},
                )
        except Exception:
            pass

    return sorted(runs.values(), key=lambda r: r.get("completed_at", ""), reverse=True)


def load_payroll_run(run_id: str) -> Optional[dict]:
    """Load a saved payroll run including flag PDF bytes."""
    client = get_supabase()
    if client:
        remote = load_remote_run(client, TABLE, run_id)
        if remote:
            record = remote
            b64 = record.get("flag_pdf_base64")
            record["flag_pdf_bytes"] = base64.b64decode(b64) if b64 else None
            return record

    record = _load_local(run_id)
    if not record:
        return None

    flag_bytes = record.pop("_flag_pdf_bytes", None)
    record["flag_pdf_bytes"] = flag_bytes
    return record


def delete_payroll_run(run_id: str) -> Tuple[bool, str]:
    """Delete a technician payroll run from local archive and Supabase."""
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


def storage_available() -> bool:
    return True  # local always; supabase optional boost

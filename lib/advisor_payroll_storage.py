"""Persist completed service advisor payroll runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st

from lib.advisor_payroll_export_data import build_advisor_payroll_snapshot
from lib.advisor_payroll_calc import AdvisorPayrollRow, calculate_advisor_payroll
from lib.advisor_roster import roster_from_saved_data, serialize_roster
from lib.supabase_client import get_supabase
from lib.payroll_supabase_sync import load_remote_run, merge_run_records, upsert_payroll_run
from views.advisor_payroll_helpers import apply_roster_to_session
from views.payroll_helpers import set_pay_period_from_string

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "advisor_payroll_archive"
TABLE = "advisor_payroll_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_advisor_payroll_session(
    advisors: List[AdvisorPayrollRow],
    pay_period: str,
    pay_period_weeks: float,
) -> dict:
    results = [calculate_advisor_payroll(a, pay_period_weeks=pay_period_weeks) for a in advisors]
    export_snap = build_advisor_payroll_snapshot(advisors, results, pay_period, pay_period_weeks)

    advisor_data = []
    for i, (advisor, result) in enumerate(zip(advisors, results)):
        advisor_data.append({
            "index": i,
            "name": advisor.name,
            "plan_type": advisor.plan_type,
            "advisor_id": advisor.advisor_id,
            "top_labor_rate": advisor.top_labor_rate,
            "weekly_guarantee": advisor.weekly_guarantee,
            "hours_sold": advisor.hours_sold,
            "parts_sales": advisor.parts_sales,
            "parts_labor_sales": advisor.parts_labor_sales,
            "repair_order_count": advisor.repair_order_count,
            "spiff": advisor.spiff,
            "cp_bump": advisor.cp_bump_qualified,
            "alignment_bonus": advisor.alignment_bonus_qualified,
            "csi_tier": advisor.csi_tier,
            "notes": advisor.notes,
            "labor_pay": result.hourly_pay,
            "parts_pay": result.parts_pay,
            "csi_pay": result.csi_pay,
            "alignment_pay": result.variable_pay,
            "total_pay": result.total_pay,
        })

    roster = st.session_state.get("advisor_roster", {})
    return {
        "pay_period": pay_period,
        "pay_period_weeks": pay_period_weeks,
        "advisor_report_loaded": bool(st.session_state.get("advisor_report_loaded")),
        "roster": serialize_roster(roster),
        "advisors": advisor_data,
        "export": export_snap,
        "totals": {
            "grand_total": export_snap["grand_total"],
            "advisor_count": export_snap["advisor_count"],
        },
        "saved_at": _now_iso(),
    }


def apply_advisor_snapshot_to_session(
    snapshot: dict,
    run_id: str,
    status: str = "completed",
):
    """Restore a saved advisor payroll run into the active session."""
    st.session_state.active_advisor_run_id = run_id
    pay_period = snapshot.get("pay_period", "")
    st.session_state.pay_period = pay_period
    set_pay_period_from_string(pay_period)
    st.session_state.advisor_payroll_completed = status == "completed"
    st.session_state.advisor_report_loaded = bool(snapshot.get("advisor_report_loaded"))

    roster = roster_from_saved_data(snapshot.get("roster", {}))
    values_by_name = {}
    for adv in snapshot.get("advisors", []):
        values_by_name[adv["name"]] = {
            "hours_sold": float(adv.get("hours_sold", 0) or 0),
            "parts_sales": float(adv.get("parts_sales", 0) or 0),
            "parts_labor_sales": float(adv.get("parts_labor_sales", 0) or 0),
            "repair_order_count": float(adv.get("repair_order_count", 0) or 0),
            "spiff": float(adv.get("spiff", 0) or 0),
            "cp_bump": bool(adv.get("cp_bump", False)),
            "alignment_bonus": bool(adv.get("alignment_bonus", False)),
            "csi_tier": adv.get("csi_tier", "none"),
            "notes": str(adv.get("notes", "") or ""),
        }
    apply_roster_to_session(roster, values_by_name)
    from views.advisor_payroll_helpers import refresh_advisor_value_store

    refresh_advisor_value_store()
    st.session_state.pending_payroll_tab = "advisors"


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


def save_advisor_payroll_run(
    advisors: List[AdvisorPayrollRow],
    pay_period: str,
    pay_period_weeks: float,
    run_id: Optional[str] = None,
    status: str = "completed",
) -> Tuple[str, str]:
    snapshot = serialize_advisor_payroll_session(advisors, pay_period, pay_period_weeks)
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()

    record = {
        "id": run_id,
        "pay_period": pay_period,
        "status": status,
        "snapshot": snapshot,
        "grand_total": snapshot["totals"]["grand_total"],
        "advisor_count": snapshot["totals"]["advisor_count"],
        "completed_at": completed_at,
        "updated_at": completed_at,
    }

    _save_local(run_id, record)

    sync_error = ""
    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "pay_period": pay_period,
            "status": status,
            "snapshot": snapshot,
            "grand_total": snapshot["totals"]["grand_total"],
            "advisor_count": snapshot["totals"]["advisor_count"],
            "completed_at": completed_at,
            "updated_at": completed_at,
        }
        ok, err = upsert_payroll_run(client, TABLE, row, run_id)
        if not ok:
            sync_error = err
            record["_sync_error"] = err
            _save_local(run_id, record)

    return run_id, sync_error


def list_advisor_payroll_runs() -> List[dict]:
    runs: dict = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select("id,pay_period,status,grand_total,advisor_count,completed_at,updated_at")
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


def load_advisor_payroll_run(run_id: str) -> Optional[dict]:
    client = get_supabase()
    if client:
        remote = load_remote_run(client, TABLE, run_id)
        if remote:
            return remote

    return _load_local(run_id)

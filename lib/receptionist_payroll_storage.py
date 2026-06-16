"""Persist completed receptionist payroll runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import streamlit as st

from lib.receptionist_payroll_calc import ReceptionistPayrollRow, calculate_receptionist_payroll
from lib.receptionist_payroll_export_data import build_receptionist_payroll_snapshot
from lib.receptionist_roster import roster_from_saved_data, serialize_roster
from lib.supabase_client import get_supabase
from views.payroll_helpers import set_pay_period_from_string
from views.receptionist_payroll_helpers import apply_roster_to_session

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "receptionist_payroll_archive"
TABLE = "receptionist_payroll_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_receptionist_payroll_session(
    employees: List[ReceptionistPayrollRow],
    pay_period: str,
) -> dict:
    results = [calculate_receptionist_payroll(e) for e in employees]
    export_snap = build_receptionist_payroll_snapshot(employees, results, pay_period)

    employee_data = []
    for i, (employee, result) in enumerate(zip(employees, results)):
        employee_data.append({
            "index": i,
            "name": employee.name,
            "last_name": employee.last_name,
            "employee_type": employee.employee_type,
            "taker_codes": list(employee.taker_codes),
            "appointment_rate": employee.appointment_rate,
            "appointments_set": employee.appointments_set,
            "tires_sold": employee.tires_sold,
            "bonus_amount": employee.bonus_amount,
            "bonus_label": employee.bonus_label,
            "spiff": employee.spiff,
            "notes": employee.notes,
            "warranty_bonus": employee.warranty_bonus_qualified,
            "appointment_pay": result.appointment_pay,
            "tire_pay": result.tire_pay,
            "warranty_pay": result.warranty_pay,
            "bonus_pay": result.bonus_pay,
            "total_pay": result.total_pay,
        })

    roster = st.session_state.get("receptionist_roster", {})
    return {
        "pay_period": pay_period,
        "cashiers_report_loaded": bool(st.session_state.get("receptionist_report_loaded")),
        "roster": serialize_roster(roster),
        "employees": employee_data,
        "export": export_snap,
        "totals": {
            "grand_total": export_snap["grand_total"],
            "employee_count": export_snap["employee_count"],
        },
        "saved_at": _now_iso(),
    }


def apply_receptionist_snapshot_to_session(
    snapshot: dict,
    run_id: str,
    status: str = "completed",
):
    st.session_state.active_receptionist_run_id = run_id
    pay_period = snapshot.get("pay_period", "")
    st.session_state.pay_period = pay_period
    set_pay_period_from_string(pay_period)
    st.session_state.receptionist_payroll_completed = status == "completed"
    st.session_state.receptionist_report_loaded = bool(snapshot.get("cashiers_report_loaded"))

    roster = roster_from_saved_data(snapshot.get("roster", {}))
    values_by_name = {}
    for emp in snapshot.get("employees", []):
        values_by_name[emp["name"]] = {
            "appointments_set": float(emp.get("appointments_set", 0) or 0),
            "tires_sold": float(emp.get("tires_sold", 0) or 0),
            "bonus_amount": float(emp.get("bonus_amount", 0) or 0),
            "bonus_label": emp.get("bonus_label", ""),
            "spiff": float(emp.get("spiff", 0) or 0),
            "appointment_rate": float(emp.get("appointment_rate", 0) or 0),
            "warranty_bonus": bool(emp.get("warranty_bonus", False)),
            "notes": str(emp.get("notes", "") or ""),
        }
    apply_roster_to_session(roster, values_by_name)
    st.session_state.pending_payroll_tab = "receptionists"


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


def save_receptionist_payroll_run(
    employees: List[ReceptionistPayrollRow],
    pay_period: str,
    run_id: Optional[str] = None,
) -> str:
    snapshot = serialize_receptionist_payroll_session(employees, pay_period)
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()

    record = {
        "id": run_id,
        "pay_period": pay_period,
        "status": "completed",
        "snapshot": snapshot,
        "grand_total": snapshot["totals"]["grand_total"],
        "employee_count": snapshot["totals"]["employee_count"],
        "completed_at": completed_at,
        "updated_at": completed_at,
    }

    _save_local(run_id, record)

    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "pay_period": pay_period,
            "status": "completed",
            "snapshot": snapshot,
            "grand_total": snapshot["totals"]["grand_total"],
            "employee_count": snapshot["totals"]["employee_count"],
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


def list_receptionist_payroll_runs() -> List[dict]:
    runs: dict = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select("id,pay_period,status,grand_total,employee_count,completed_at,updated_at")
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = {**row, "source": "supabase"}
        except Exception:
            pass

    return sorted(runs.values(), key=lambda r: r.get("completed_at", ""), reverse=True)


def load_receptionist_payroll_run(run_id: str) -> Optional[dict]:
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

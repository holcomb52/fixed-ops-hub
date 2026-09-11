"""Persist Service Advisor daily training logs."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st

from lib.advisor_training_calc import (
    build_snapshot,
    empty_skills,
    empty_topics,
    normalize_skills,
    normalize_topics,
)
from lib.json_safe import json_safe
from lib.payroll_supabase_sync import delete_remote_run, load_remote_run, merge_run_records, upsert_payroll_run
from lib.supabase_client import get_supabase

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "advisor_training_archive"
TABLE = "advisor_training_logs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_advisor_training_session(
    *,
    trainee_name: str,
    trainer_name: str,
    log_date: str,
    day_number: int,
    topics: dict,
    skills: dict,
    other_topic_note: str = "",
    trainee_questions: str = "",
    trainer_notes: str = "",
    next_focus: str = "",
) -> dict:
    snapshot = build_snapshot(
        trainee_name=trainee_name,
        trainer_name=trainer_name,
        log_date=log_date,
        day_number=day_number,
        topics=topics,
        skills=skills,
        other_topic_note=other_topic_note,
        trainee_questions=trainee_questions,
        trainer_notes=trainer_notes,
        next_focus=next_focus,
    )
    snapshot["saved_at"] = _now_iso()
    return snapshot


def apply_advisor_training_snapshot_to_session(snapshot: dict, run_id: str, status: str = "completed"):
    topics = normalize_topics(snapshot.get("topics"))
    skills = normalize_skills(snapshot.get("skills"))

    st.session_state.active_advisor_training_run_id = run_id
    st.session_state.advisor_training_completed = status == "completed"
    st.session_state.at_trainee_name = snapshot.get("trainee_name") or ""
    st.session_state.at_trainer_name = snapshot.get("trainer_name") or ""
    st.session_state.at_day_number = int(snapshot.get("day_number") or 1)
    st.session_state.at_other_topic_note = snapshot.get("other_topic_note") or ""
    st.session_state.at_trainee_questions = snapshot.get("trainee_questions") or ""
    st.session_state.at_trainer_notes = snapshot.get("trainer_notes") or ""
    st.session_state.at_next_focus = snapshot.get("next_focus") or ""

    log_date = (snapshot.get("log_date") or "").strip()
    if log_date:
        try:
            st.session_state.at_log_date = datetime.strptime(log_date, "%Y-%m-%d").date()
        except ValueError:
            try:
                st.session_state.at_log_date = datetime.strptime(log_date, "%m/%d/%Y").date()
            except ValueError:
                pass

    for tid, on in topics.items():
        st.session_state[f"at_topic_{tid}"] = bool(on)
    for sid, level in skills.items():
        st.session_state[f"at_skill_{sid}"] = level or "—"


def clear_advisor_training_session():
    st.session_state.active_advisor_training_run_id = None
    st.session_state.advisor_training_completed = False
    st.session_state.at_trainee_name = ""
    st.session_state.at_trainer_name = ""
    st.session_state.at_day_number = 1
    st.session_state.at_other_topic_note = ""
    st.session_state.at_trainee_questions = ""
    st.session_state.at_trainer_notes = ""
    st.session_state.at_next_focus = ""
    from datetime import date as date_cls

    st.session_state.at_log_date = date_cls.today()
    for tid in empty_topics():
        st.session_state[f"at_topic_{tid}"] = False
    for sid in empty_skills():
        st.session_state[f"at_skill_{sid}"] = "—"


def topics_from_session() -> dict:
    return {tid: bool(st.session_state.get(f"at_topic_{tid}", False)) for tid in empty_topics()}


def skills_from_session() -> dict:
    out = empty_skills()
    for sid in out:
        raw = st.session_state.get(f"at_skill_{sid}", "—")
        out[sid] = "" if raw in (None, "", "—") else str(raw)
    return out


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


def save_advisor_training_log(
    snapshot: dict,
    *,
    run_id: Optional[str] = None,
    status: str = "completed",
    cloud_sync: bool = True,
) -> Tuple[str, str]:
    run_id = run_id or str(uuid.uuid4())
    now = _now_iso()
    period = snapshot.get("log_date") or "—"
    day = int(snapshot.get("day_number") or 0)
    record = {
        "id": run_id,
        "pay_period": period,
        "status": status,
        "snapshot": snapshot,
        "grand_total": float(day),
        "employee_name": snapshot.get("trainee_name", ""),
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
            "employee_name": record["employee_name"],
            "completed_at": now,
            "updated_at": now,
        }
        ok, err = upsert_payroll_run(client, TABLE, row, run_id)
        if not ok:
            sync_error = err
            record["_sync_error"] = err
            _save_local(run_id, record)
    return run_id, sync_error


def list_advisor_training_logs() -> List[dict]:
    runs: dict = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select(
                    "id,pay_period,status,grand_total,employee_name,completed_at,updated_at,snapshot"
                )
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                merged = merge_run_records(
                    runs.get(row["id"]),
                    {**row, "source": "supabase"},
                )
                if row.get("employee_name") and not merged.get("employee_name"):
                    merged["employee_name"] = row["employee_name"]
                if row.get("snapshot") and not merged.get("snapshot"):
                    merged["snapshot"] = row["snapshot"]
                runs[row["id"]] = merged
        except Exception:
            pass
    return sorted(runs.values(), key=lambda r: r.get("completed_at", ""), reverse=True)


def load_advisor_training_log(run_id: str) -> Optional[dict]:
    client = get_supabase()
    if client:
        remote = load_remote_run(client, TABLE, run_id)
        if remote:
            return remote
    return _load_local(run_id)


def delete_advisor_training_log(run_id: str) -> Tuple[bool, str]:
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

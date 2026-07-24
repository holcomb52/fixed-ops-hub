"""Persist customer-pay labor rate grid runs for Reports."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

from lib.labor_rate_grid import LaborGridResult, grid_to_dataframe_rows
from lib.supabase_client import get_supabase

ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "labor_rate_archive"
TABLE = "labor_rate_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_run_label(result: LaborGridResult) -> str:
    return (
        f"{result.strong_lo:.1f}–{result.strong_hi:.1f}h @ "
        f"${result.target_elr:,.0f}/hr"
    )


def serialize_labor_rate_snapshot(
    result: LaborGridResult,
    *,
    hour_range: str,
    boost_pct: int,
    use_custom_base: bool,
    notes: str = "",
    amount_overrides: Optional[Dict[str, float]] = None,
    run_label: Optional[str] = None,
    current_warranty_rate: Optional[float] = None,
    warranty_hours: Optional[float] = None,
) -> dict:
    """Flatten a generated grid into a JSON-safe snapshot for save/reopen."""
    matrix_out: Dict[str, Dict[str, float]] = {}
    for base, cols in result.matrix.items():
        matrix_out[f"{float(base):.1f}"] = {
            f"{float(tenth):.1f}": float(amount) for tenth, amount in cols.items()
        }

    overrides_out: Dict[str, float] = {}
    for raw_h, raw_amt in (amount_overrides or {}).items():
        try:
            overrides_out[f"{float(raw_h):.1f}"] = round(float(raw_amt), 2)
        except (TypeError, ValueError):
            continue

    label = str(run_label or "").strip() or _default_run_label(result)
    try:
        curr_w = float(current_warranty_rate) if current_warranty_rate is not None else 0.0
    except (TypeError, ValueError):
        curr_w = 0.0
    try:
        w_hours = float(warranty_hours) if warranty_hours is not None else 0.0
    except (TypeError, ValueError):
        w_hours = 0.0

    return {
        "run_label": label,
        "notes": str(notes or "").strip(),
        "inputs": {
            "hour_range": str(hour_range or "").strip(),
            "range_elr": float(result.target_elr),
            "base_elr": float(result.base_elr),
            "use_custom_base": bool(use_custom_base),
            "max_hours": float(result.max_hours),
            "boost_pct": int(boost_pct),
            "grid_name": label,
            "current_warranty_rate": curr_w,
            "warranty_hours": w_hours,
        },
        "result": {
            "target_elr": float(result.target_elr),
            "base_elr": float(result.base_elr),
            "strong_lo": float(result.strong_lo),
            "strong_hi": float(result.strong_hi),
            "max_hours": float(result.max_hours),
            "strength_boost": float(result.strength_boost),
            "strong_avg_elr": float(result.strong_avg_elr),
            "strong_min_elr": float(result.strong_min_elr),
            "strong_max_elr": float(result.strong_max_elr),
            "overall_avg_elr": float(result.overall_avg_elr),
            "outside_avg_elr": float(result.outside_avg_elr),
            "lowest_elr": float(result.lowest_elr),
            "lowest_elr_hours": float(result.lowest_elr_hours),
            "highest_elr": float(result.highest_elr),
            "highest_elr_hours": float(result.highest_elr_hours),
            "pct_above_target": float(result.pct_above_target),
            "pct_below_target": float(result.pct_below_target),
            "pct_at_target": float(result.pct_at_target),
            "cells_scored": int(result.cells_scored),
            "scale_factor": float(result.scale_factor),
        },
        "matrix": matrix_out,
        "cells": list(result.cells),
        "amount_overrides": overrides_out,
        "grid_rows": grid_to_dataframe_rows(result),
        "saved_at": _now_iso(),
    }


def apply_labor_rate_snapshot_to_session(record: dict, run_id: str) -> None:
    """Restore Labor Rate inputs so the page rebuilds this grid."""
    snapshot = record.get("snapshot") or {}
    inputs = snapshot.get("inputs") or {}
    result = snapshot.get("result") or {}

    hour_range = str(
        inputs.get("hour_range")
        or f"{result.get('strong_lo', 1.0)}-{result.get('strong_hi', 3.5)}"
    )
    st.session_state["labor_hour_range"] = hour_range
    st.session_state["labor_range_elr"] = float(
        inputs.get("range_elr") or result.get("target_elr") or 295.0
    )
    st.session_state["labor_use_base"] = bool(inputs.get("use_custom_base"))
    st.session_state["labor_base_elr"] = float(
        inputs.get("base_elr") or result.get("base_elr") or 270.0
    )
    st.session_state["labor_max_hours"] = float(
        inputs.get("max_hours") or result.get("max_hours") or 16.0
    )
    st.session_state["labor_boost_pct"] = int(inputs.get("boost_pct") or 10)
    st.session_state["labor_current_warranty_rate"] = float(
        inputs.get("current_warranty_rate") or 0.0
    )
    st.session_state["labor_warranty_hours"] = float(inputs.get("warranty_hours") or 0.0)
    st.session_state["active_labor_rate_run_id"] = run_id
    label = str(
        record.get("run_label")
        or snapshot.get("run_label")
        or inputs.get("grid_name")
        or "Labor rate grid"
    )
    st.session_state["labor_rate_run_label"] = label
    st.session_state["labor_grid_name"] = label
    restored_overrides: Dict[str, float] = {}
    for raw_h, raw_amt in (snapshot.get("amount_overrides") or {}).items():
        try:
            restored_overrides[f"{float(raw_h):.1f}"] = float(raw_amt)
        except (TypeError, ValueError):
            continue
    st.session_state["labor_grid_overrides"] = restored_overrides
    st.session_state["_labor_keep_overrides"] = True
    st.session_state["labor_editor_nonce"] = (
        int(st.session_state.get("labor_editor_nonce") or 0) + 1
    )
    st.session_state.pop("labor_elr_drill", None)


def _save_local(run_id: str, record: dict) -> None:
    folder = ARCHIVE_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "record.json").write_text(json.dumps(record, indent=2))


def _load_local(run_id: str) -> Optional[dict]:
    path = ARCHIVE_DIR / run_id / "record.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _list_local() -> List[dict]:
    if not ARCHIVE_DIR.exists():
        return []
    runs = []
    for folder in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if folder.is_dir() and (folder / "record.json").exists():
            try:
                runs.append(json.loads((folder / "record.json").read_text()))
            except (json.JSONDecodeError, OSError):
                continue
    return runs


def save_labor_rate_run(
    result: LaborGridResult,
    *,
    hour_range: str,
    boost_pct: int,
    use_custom_base: bool,
    notes: str = "",
    amount_overrides: Optional[Dict[str, float]] = None,
    run_label: Optional[str] = None,
    current_warranty_rate: Optional[float] = None,
    warranty_hours: Optional[float] = None,
    run_id: Optional[str] = None,
) -> str:
    snapshot = serialize_labor_rate_snapshot(
        result,
        hour_range=hour_range,
        boost_pct=boost_pct,
        use_custom_base=use_custom_base,
        notes=notes,
        amount_overrides=amount_overrides,
        run_label=run_label,
        current_warranty_rate=current_warranty_rate,
        warranty_hours=warranty_hours,
    )
    run_id = run_id or str(uuid.uuid4())
    completed_at = _now_iso()
    run_label = snapshot["run_label"]

    record = {
        "id": run_id,
        "run_label": run_label,
        "status": "saved",
        "snapshot": snapshot,
        "target_elr": float(result.target_elr),
        "strong_avg_elr": float(result.strong_avg_elr),
        "base_elr": float(result.base_elr),
        "strong_lo": float(result.strong_lo),
        "strong_hi": float(result.strong_hi),
        "pct_above_target": float(result.pct_above_target),
        "pct_below_target": float(result.pct_below_target),
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    _save_local(run_id, record)

    client = get_supabase()
    if client:
        row = {
            "id": run_id,
            "run_label": run_label,
            "status": "saved",
            "snapshot": snapshot,
            "target_elr": record["target_elr"],
            "strong_avg_elr": record["strong_avg_elr"],
            "base_elr": record["base_elr"],
            "strong_lo": record["strong_lo"],
            "strong_hi": record["strong_hi"],
            "pct_above_target": record["pct_above_target"],
            "pct_below_target": record["pct_below_target"],
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


def list_labor_rate_runs() -> List[dict]:
    runs: Dict[str, dict] = {}
    for rec in _list_local():
        runs[rec["id"]] = rec

    client = get_supabase()
    if client:
        try:
            result = (
                client.table(TABLE)
                .select(
                    "id,run_label,status,target_elr,strong_avg_elr,base_elr,"
                    "strong_lo,strong_hi,pct_above_target,pct_below_target,"
                    "completed_at,updated_at"
                )
                .order("completed_at", desc=True)
                .execute()
            )
            for row in result.data or []:
                runs[row["id"]] = {**row, "source": "supabase"}
        except Exception:
            pass

    return sorted(
        runs.values(), key=lambda item: item.get("completed_at", ""), reverse=True
    )


def load_labor_rate_run(run_id: str) -> Optional[dict]:
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


def delete_labor_rate_run(run_id: str) -> Tuple[bool, str]:
    """Delete a labor rate grid run from local archive and Supabase."""
    from lib.payroll_supabase_sync import delete_remote_run

    if not run_id:
        return False, "Missing report id."

    deleted_local = False
    folder = ARCHIVE_DIR / run_id
    if folder.exists():
        try:
            shutil.rmtree(folder)
            deleted_local = True
        except OSError as exc:
            return False, f"Could not delete local copy: {exc}"

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

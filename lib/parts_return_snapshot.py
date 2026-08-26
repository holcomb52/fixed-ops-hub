"""Serialize parts return plans for Reports / PDF."""

from __future__ import annotations

from datetime import date
from typing import List

from lib.parts_return_calc import PartsReturnPlan, ReturnCandidate
from lib.parts_return_parser import PartsInventoryLine


def _candidate_dict(item: ReturnCandidate) -> dict:
    line = item.line
    return {
        "part_number": line.part_number,
        "description": line.description,
        "source": line.source,
        "age": line.age,
        "bin_location": line.bin_location,
        "qoh": line.qoh,
        "pack": line.pack,
        "cost": line.cost,
        "value": line.value,
        "return_qty": item.return_qty,
        "return_value": item.return_value,
        "score": item.score,
        "skip_reason": item.skip_reason,
    }


def line_from_dict(data: dict) -> PartsInventoryLine:
    return PartsInventoryLine(
        part_number=str(data.get("part_number", "") or ""),
        description=str(data.get("description", "") or ""),
        qoh=float(data.get("qoh", 0) or 0),
        age=float(data.get("age", 0) or 0),
        pack=float(data.get("pack", 1) or 1),
        cost=float(data.get("cost", 0) or 0),
        value=float(data.get("value", data.get("return_value", 0)) or 0),
        source=str(data.get("source", "") or ""),
        bin_location=str(data.get("bin_location", "") or ""),
        sts=str(data.get("sts", "") or ""),
        detail=str(data.get("detail", "") or ""),
    )


def serialize_parts_return_plan(
    plan: PartsReturnPlan,
    *,
    label: str,
    mns_name: str = "",
    mnr_name: str = "",
    mns_count: int = 0,
    mnr_count: int = 0,
    candidate_count: int = 0,
    exclude_multipack: bool = True,
    exclude_hardware: bool = True,
    min_age: float = 0.0,
    min_value: float = 0.0,
    allow_partial: bool = True,
    notes: str = "",
) -> dict:
    return {
        "label": label,
        "report_date": date.today().isoformat(),
        "allowance": float(plan.allowance or 0),
        "selected_value": float(plan.selected_value or 0),
        "remaining_allowance": float(plan.remaining_allowance or 0),
        "selected_count": int(plan.selected_count),
        "skipped_count": len(plan.skipped),
        "candidate_count": int(candidate_count),
        "mns_name": mns_name,
        "mnr_name": mnr_name,
        "mns_count": int(mns_count),
        "mnr_count": int(mnr_count),
        "exclude_multipack": bool(exclude_multipack),
        "exclude_hardware": bool(exclude_hardware),
        "min_age": float(min_age or 0),
        "min_value": float(min_value or 0),
        "allow_partial": bool(allow_partial),
        "notes": notes or "",
        "selected": [_candidate_dict(item) for item in plan.selected],
        "skipped": [_candidate_dict(item) for item in plan.skipped[:100]],
        "selected_part_numbers": [item.line.part_number for item in plan.selected],
        "selected_qty_by_part": {
            item.line.part_number: item.return_qty for item in plan.selected
        },
    }


def plan_from_snapshot(snapshot: dict) -> PartsReturnPlan:
    """Rebuild a display plan from a saved snapshot (selected rows only for fill)."""
    selected: List[ReturnCandidate] = []
    for row in snapshot.get("selected") or []:
        line = line_from_dict(row)
        selected.append(
            ReturnCandidate(
                line=line,
                return_qty=float(row.get("return_qty", line.qoh) or 0),
                return_value=float(row.get("return_value", line.value) or 0),
                score=float(row.get("score", 0) or 0),
            )
        )
    skipped: List[ReturnCandidate] = []
    for row in snapshot.get("skipped") or []:
        line = line_from_dict(row)
        skipped.append(
            ReturnCandidate(
                line=line,
                return_qty=float(row.get("return_qty", line.qoh) or 0),
                return_value=float(row.get("return_value", line.value) or 0),
                score=float(row.get("score", 0) or 0),
                skip_reason=str(row.get("skip_reason", "") or ""),
            )
        )
    return PartsReturnPlan(
        allowance=float(snapshot.get("allowance", 0) or 0),
        selected=selected,
        skipped=skipped,
        remaining_allowance=float(snapshot.get("remaining_allowance", 0) or 0),
    )


def apply_parts_return_snapshot_to_session(snapshot: dict, run_id: str, status: str = "completed"):
    import streamlit as st

    st.session_state.active_parts_return_run_id = run_id
    st.session_state.parts_return_completed = status == "completed"
    st.session_state.parts_return_label = snapshot.get("label") or ""
    st.session_state.parts_allowance = float(snapshot.get("allowance", 0) or 0)
    st.session_state.parts_exclude_multipack = bool(snapshot.get("exclude_multipack", True))
    st.session_state.parts_exclude_hardware = bool(snapshot.get("exclude_hardware", True))
    st.session_state.parts_min_age = float(snapshot.get("min_age", 0) or 0)
    st.session_state.parts_min_value = float(snapshot.get("min_value", 0) or 0)
    st.session_state.parts_allow_partial = bool(snapshot.get("allow_partial", True))
    st.session_state.parts_notes = str(snapshot.get("notes", "") or "")
    st.session_state.parts_mns_name = str(snapshot.get("mns_name", "") or "")
    st.session_state.parts_mnr_name = str(snapshot.get("mnr_name", "") or "")
    st.session_state.parts_saved_snapshot = snapshot
    st.session_state.parts_selected_pns = list(
        snapshot.get("selected_part_numbers")
        or [row.get("part_number") for row in (snapshot.get("selected") or [])]
    )
    qty_map = snapshot.get("selected_qty_by_part") or {}
    if not qty_map:
        qty_map = {
            str(row.get("part_number")): float(row.get("return_qty") or 0)
            for row in (snapshot.get("selected") or [])
            if row.get("part_number")
        }
    st.session_state.parts_selected_qty = {
        str(k): float(v or 0) for k, v in qty_map.items()
    }
    st.session_state.parts_sel_seed = "restored"
    # Rebuild line lists from selected+skipped so the page can re-display without files.
    restored: List[PartsInventoryLine] = []
    seen = set()
    for row in list(snapshot.get("selected") or []) + list(snapshot.get("skipped") or []):
        pn = str(row.get("part_number", "") or "").upper()
        if not pn or pn in seen:
            continue
        seen.add(pn)
        restored.append(line_from_dict(row))
    st.session_state.parts_mns_lines = [r for r in restored if "MNS" in (r.source or "")]
    st.session_state.parts_mnr_lines = [r for r in restored if "MNR" in (r.source or "")]
    # Keep any source-only-MNS / MNR split; also put dual-tagged in both.
    if not st.session_state.parts_mns_lines and not st.session_state.parts_mnr_lines:
        st.session_state.parts_mns_lines = restored

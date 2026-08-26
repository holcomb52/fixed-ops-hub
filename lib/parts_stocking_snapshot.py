"""Serialize parts stocking plans for Reports / PDF."""

from __future__ import annotations

from calendar import month_name
from datetime import date
from typing import List

from lib.parts_stocking_calc import STATUS_LABELS, StockingPlan, StockingRecommendation
from lib.parts_stocking_parser import SixMonthSalesLine


def _line_dict(line: StockingRecommendation) -> dict:
    return {
        "part_number": line.part_number,
        "description": line.description,
        "make": line.make,
        "source": line.source,
        "qoh": line.qoh,
        "sold_6mo": line.sold_6mo,
        "cost": line.cost,
        "monthly_demand": line.monthly_demand,
        "target_on_hand": line.target_on_hand,
        "order_qty": line.order_qty,
        "order_cost": line.order_cost,
        "months_of_supply": line.months_of_supply,
        "status": line.status,
        "status_label": STATUS_LABELS.get(line.status, line.status),
    }


def serialize_stocking_plan(
    plan: StockingPlan,
    *,
    label: str,
    source_file: str = "",
    notes: str = "",
) -> dict:
    ok_count = sum(1 for line in plan.lines if line.status == "ok")
    overstock_count = sum(1 for line in plan.lines if line.status == "overstock")
    no_sales_count = sum(1 for line in plan.lines if line.status == "no_sales")
    return {
        "label": label,
        "report_date": date.today().isoformat(),
        "source_file": source_file,
        "target_months": float(plan.target_months or 0),
        "min_sold_6mo": float(plan.min_sold_6mo or 0),
        "overstock_factor": float(plan.overstock_factor or 2.0),
        "notes": notes or "",
        "candidate_count": len(plan.lines),
        "order_count": plan.order_count,
        "order_total_cost": plan.order_total_cost,
        "ok_count": ok_count,
        "overstock_count": overstock_count,
        "no_sales_count": no_sales_count,
        "lines": [_line_dict(line) for line in plan.lines],
        "order_lines": [_line_dict(line) for line in plan.order_lines],
    }


def line_from_dict(data: dict) -> SixMonthSalesLine:
    return SixMonthSalesLine(
        part_number=str(data.get("part_number", "") or ""),
        description=str(data.get("description", "") or ""),
        qoh=float(data.get("qoh", 0) or 0),
        sold_6mo=float(data.get("sold_6mo", 0) or 0),
        cost=float(data.get("cost", 0) or 0),
        make=str(data.get("make", "") or ""),
        source=str(data.get("source", "") or ""),
    )


def recommendation_from_dict(data: dict) -> StockingRecommendation:
    return StockingRecommendation(
        part_number=str(data.get("part_number", "") or ""),
        description=str(data.get("description", "") or ""),
        make=str(data.get("make", "") or ""),
        source=str(data.get("source", "") or ""),
        qoh=float(data.get("qoh", 0) or 0),
        sold_6mo=float(data.get("sold_6mo", 0) or 0),
        cost=float(data.get("cost", 0) or 0),
        monthly_demand=float(data.get("monthly_demand", 0) or 0),
        target_on_hand=float(data.get("target_on_hand", 0) or 0),
        order_qty=float(data.get("order_qty", 0) or 0),
        order_cost=float(data.get("order_cost", 0) or 0),
        months_of_supply=float(data.get("months_of_supply", 0) or 0),
        status=str(data.get("status", "ok") or "ok"),
    )


def apply_parts_stocking_snapshot_to_session(
    snapshot: dict,
    run_id: str,
    status: str = "completed",
):
    import streamlit as st

    st.session_state.active_parts_stocking_run_id = run_id
    st.session_state.parts_stocking_completed = status == "completed"
    st.session_state.parts_stock_label = snapshot.get("label") or ""
    st.session_state.parts_stock_target_months = float(snapshot.get("target_months", 1) or 1)
    st.session_state.parts_stock_min_sold = float(snapshot.get("min_sold_6mo", 0) or 0)
    st.session_state.parts_stock_overstock_factor = float(
        snapshot.get("overstock_factor", 2) or 2
    )
    st.session_state.parts_stock_notes = str(snapshot.get("notes", "") or "")
    st.session_state.parts_stock_name = str(snapshot.get("source_file", "") or "")
    st.session_state.parts_stock_filter = "Order"
    st.session_state.parts_active_tab = "Stocking"
    st.session_state.parts_saved_stock_snapshot = snapshot

    restored_lines: List[SixMonthSalesLine] = []
    seen = set()
    for row in snapshot.get("lines") or []:
        pn = str(row.get("part_number", "") or "").upper()
        if not pn or pn in seen:
            continue
        seen.add(pn)
        restored_lines.append(line_from_dict(row))
    st.session_state.parts_stock_lines = restored_lines

    if snapshot.get("source_file") and snapshot.get("label"):
        st.session_state.parts_stock_sig = f"restored:{run_id}"
    else:
        st.session_state.parts_stock_sig = f"restored:{run_id}"


def default_stocking_label() -> str:
    today = date.today()
    return f"{month_name[today.month]} {today.year} Stocking"

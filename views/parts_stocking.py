"""Parts stocking planner from 6-month sales (6MS) reports."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.parts_stocking_calc import STATUS_LABELS, StockingPlan, build_stocking_plan
from lib.parts_stocking_parser import parse_six_month_sales_workbook


def _init_state():
    defaults = {
        "parts_stock_bytes": None,
        "parts_stock_name": "",
        "parts_stock_sig": "",
        "parts_stock_lines": [],
        "parts_stock_target_months": 1.0,
        "parts_stock_min_sold": 1.0,
        "parts_stock_overstock_factor": 2.0,
        "parts_stock_filter": "Order",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _file_sig(name: str, data: bytes) -> str:
    return f"{name}:{len(data)}"


def _load_uploaded(uploaded):
    if not uploaded:
        return
    data = uploaded.getvalue()
    sig = _file_sig(uploaded.name, data)
    if st.session_state.get("parts_stock_sig") == sig:
        return
    try:
        lines = parse_six_month_sales_workbook(BytesIO(data))
    except Exception as exc:
        st.markdown(
            status_banner(f"6MS file failed: {exc}", "warn"),
            unsafe_allow_html=True,
        )
        return
    st.session_state.parts_stock_bytes = data
    st.session_state.parts_stock_name = uploaded.name
    st.session_state.parts_stock_sig = sig
    st.session_state.parts_stock_lines = lines
    st.markdown(
        status_banner(
            f"✓ Loaded 6MS: {len(lines)} parts from {uploaded.name}",
            "success",
        ),
        unsafe_allow_html=True,
    )


def _filter_lines(plan: StockingPlan, view: str):
    if view == "All":
        return plan.lines
    if view == "Order":
        return [line for line in plan.lines if line.status == "order"]
    if view == "OK":
        return [line for line in plan.lines if line.status == "ok"]
    if view == "Overstock":
        return [line for line in plan.lines if line.status == "overstock"]
    if view == "No sales":
        return [line for line in plan.lines if line.status == "no_sales"]
    return plan.lines


def _plan_to_df(lines) -> pd.DataFrame:
    rows = []
    for line in lines:
        mos = line.months_of_supply
        mos_label = "—" if mos == float("inf") else f"{mos:.1f}"
        rows.append(
            {
                "Part Number": line.part_number,
                "Description": line.description,
                "QOH": int(round(line.qoh)),
                "Sold (6 mo)": int(round(line.sold_6mo)),
                "Monthly avg": line.monthly_demand,
                "Target on hand": int(round(line.target_on_hand)),
                "Order qty": int(round(line.order_qty)),
                "Order $": line.order_cost,
                "Months supply": mos_label,
                "Status": STATUS_LABELS.get(line.status, line.status),
                "Cost": line.cost,
            }
        )
    return pd.DataFrame(rows)


def render():
    _init_state()

    st.markdown(
        page_hero(
            "Stocking",
            "Upload your 6-month sales (6MS) report. The planner compares on-hand qty to "
            "average monthly sales and tells you what to order and what to keep on the shelf.",
            tag="6MS",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<span class="legend-chip chip-manual">6MS = 6-month sales</span> '
        '<span class="legend-chip chip-calc">Target on hand = monthly avg × months of supply</span> '
        '<span class="legend-chip chip-live">Order qty = target − QOH (when below target)</span>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Upload 6MS (.xlsx) — 6-month sales",
        type=["xlsx", "xls"],
        key="parts_stock_uploader",
        help="CDK/Chrysler export with QOH, Sold, Part#, Description, and Cost.",
    )
    _load_uploaded(uploaded)
    if st.session_state.get("parts_stock_name"):
        st.caption(f"Loaded: {st.session_state.parts_stock_name}")

    lines = st.session_state.get("parts_stock_lines") or []
    if not lines:
        st.info("Upload a 6MS spreadsheet to build stocking recommendations.")
        return

    st.markdown("---")
    st.markdown("##### Stocking settings")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input(
            "Months of supply target",
            min_value=0.5,
            max_value=6.0,
            step=0.5,
            format="%.1f",
            key="parts_stock_target_months",
            help="How many months of average sales you want on the shelf.",
        )
    with c2:
        st.number_input(
            "Minimum sold (6 mo)",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key="parts_stock_min_sold",
            help="Ignore parts below this 6-month sales count.",
        )
    with c3:
        st.number_input(
            "Overstock threshold (× target)",
            min_value=1.5,
            max_value=6.0,
            step=0.5,
            format="%.1f",
            key="parts_stock_overstock_factor",
            help="Flag as overstock when QOH exceeds target by this multiplier.",
        )

    plan = build_stocking_plan(
        lines,
        target_months=float(st.session_state.parts_stock_target_months or 1.0),
        min_sold_6mo=float(st.session_state.parts_stock_min_sold or 0),
        overstock_factor=float(st.session_state.parts_stock_overstock_factor or 2.0),
    )

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            stat_card("Need to order", f"{plan.order_count}", accent="orange", icon="📦"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card(
                "Order $",
                f"${plan.order_total_cost:,.2f}",
                accent="purple",
                icon="$",
            ),
            unsafe_allow_html=True,
        )
    with s3:
        ok_count = sum(1 for line in plan.lines if line.status == "ok")
        st.markdown(
            stat_card("Adequate stock", f"{ok_count}", accent="green", icon="✓"),
            unsafe_allow_html=True,
        )
    with s4:
        st.markdown(
            stat_card("Overstock", f"{plan.overstock_count}", accent="cyan", icon="▲"),
            unsafe_allow_html=True,
        )

    st.caption(
        f"Based on **{st.session_state.parts_stock_target_months:.1f} month(s)** of supply "
        f"from 6-month average sales."
    )

    view = st.selectbox(
        "Show",
        ["Order", "All", "OK", "Overstock", "No sales"],
        key="parts_stock_filter",
    )
    filtered = _filter_lines(plan, view)
    table_df = _plan_to_df(filtered)

    if table_df.empty:
        st.info(f"No parts in the **{view}** view with the current settings.")
        return

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Monthly avg": st.column_config.NumberColumn(format="%.1f"),
            "Order $": st.column_config.NumberColumn(format="$%.2f"),
            "Cost": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    if plan.order_count:
        order_df = _plan_to_df(plan.order_lines)
        csv = order_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download order list (CSV)",
            data=csv,
            file_name="parts_stocking_order_list.csv",
            mime="text/csv",
            use_container_width=True,
        )

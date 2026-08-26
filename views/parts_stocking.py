"""Parts stocking planner from 6-month sales (6MS) reports."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.parts_stocking_calc import STATUS_LABELS, StockingPlan, build_stocking_plan
from lib.parts_stocking_parser import parse_six_month_sales_workbook
from lib.parts_stocking_pdf_export import generate_parts_stocking_pdf
from lib.parts_stocking_snapshot import default_stocking_label, serialize_stocking_plan
from lib.parts_stocking_storage import save_parts_stocking_run
from views.payroll_helpers import render_payroll_sync_error


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
        "parts_stock_label": "",
        "parts_stock_notes": "",
        "active_parts_stocking_run_id": None,
        "parts_stocking_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.get("parts_stock_label"):
        st.session_state.parts_stock_label = default_stocking_label()


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


def _filter_title(view: str) -> str:
    titles = {
        "Order": "Need to order",
        "OK": "Adequate stock",
        "Overstock": "Overstock",
        "No sales": "No sales",
        "All": "All parts",
    }
    return titles.get(view, view)


def _render_clickable_stat(
    col,
    *,
    filter_key: str,
    label: str,
    value: str,
    accent: str,
    icon: str,
    button_key: str,
):
    active = st.session_state.get("parts_stock_filter") == filter_key
    active_cls = " is-active" if active else ""
    card = stat_card(label, value, accent=accent, icon=icon)
    with col:
        st.markdown(
            f'<div class="stock-stat-card-marker accent-{accent}{active_cls}">{card}</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            label,
            key=button_key,
            use_container_width=True,
            help=f"Show {label.lower()}",
        ):
            st.session_state.parts_stock_filter = filter_key
            st.rerun()


def _render_quick_filter(label: str, filter_key: str, *, active: bool):
    if st.button(
        label,
        key=f"parts_stock_quick_{filter_key}",
        use_container_width=True,
        type="primary" if active else "secondary",
    ):
        st.session_state.parts_stock_filter = filter_key
        st.rerun()


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


def _current_snapshot(plan: StockingPlan) -> dict:
    label = (st.session_state.get("parts_stock_label") or "").strip()
    if not label:
        label = default_stocking_label()
    return serialize_stocking_plan(
        plan,
        label=label,
        source_file=st.session_state.get("parts_stock_name") or "",
        notes=str(st.session_state.get("parts_stock_notes") or ""),
    )


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

    if st.session_state.get("parts_stocking_completed"):
        st.markdown(
            status_banner(
                f"Editing saved stocking plan · {st.session_state.get('parts_stock_label') or 'Stocking'} · "
                "Export PDF or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_parts_stocking_sync_error", table="parts_stocking_runs")

    st.text_input(
        "Plan name (Reports label)",
        key="parts_stock_label",
        help="How this run appears under Reports → Parts Stocking.",
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
    snapshot = _current_snapshot(plan)

    ok_count = sum(1 for line in plan.lines if line.status == "ok")
    no_sales_count = sum(1 for line in plan.lines if line.status == "no_sales")

    st.markdown('<div class="stock-stat-grid">', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    _render_clickable_stat(
        s1,
        filter_key="Order",
        label="Need to order",
        value=f"{plan.order_count}",
        accent="orange",
        icon="📦",
        button_key="parts_stock_stat_order",
    )
    _render_clickable_stat(
        s2,
        filter_key="Order",
        label="Order $",
        value=f"${plan.order_total_cost:,.2f}",
        accent="purple",
        icon="$",
        button_key="parts_stock_stat_order_dollars",
    )
    _render_clickable_stat(
        s3,
        filter_key="OK",
        label="Adequate stock",
        value=f"{ok_count}",
        accent="green",
        icon="✓",
        button_key="parts_stock_stat_ok",
    )
    _render_clickable_stat(
        s4,
        filter_key="Overstock",
        label="Overstock",
        value=f"{plan.overstock_count}",
        accent="cyan",
        icon="▲",
        button_key="parts_stock_stat_overstock",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.caption(
        f"Based on **{st.session_state.parts_stock_target_months:.1f} month(s)** of supply "
        f"from 6-month average sales. Click a summary box to load that list."
    )

    st.markdown('<div class="stock-stat-filter-row">', unsafe_allow_html=True)
    q1, q2, q3 = st.columns([1, 1, 4])
    active_filter = st.session_state.get("parts_stock_filter") or "Order"
    with q1:
        _render_quick_filter("All parts", "All", active=active_filter == "All")
    with q2:
        _render_quick_filter(
            f"No sales ({no_sales_count})",
            "No sales",
            active=active_filter == "No sales",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    view = active_filter
    filtered = _filter_lines(plan, view)
    table_df = _plan_to_df(filtered)
    list_title = _filter_title(view)

    st.markdown(f"##### {list_title} · {len(filtered)} parts")

    if table_df.empty:
        st.info(f"No parts in **{list_title}** with the current settings.")
    else:
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

    st.text_area("Notes (optional — included on PDF)", key="parts_stock_notes", height=80)

    st.markdown("---")
    st.markdown("##### Export & save")
    pdf_bytes = generate_parts_stocking_pdf(snapshot)
    file_stub = str(snapshot.get("label") or "parts_stocking").replace(" ", "_")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export stocking plan PDF",
            data=pdf_bytes,
            file_name=f"PARTS_STOCKING_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with e2:
        st.caption("PDF lists parts to order, target on-hand levels, and plan settings.")

    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This stocking plan is complete and ready to save",
        key="parts_stock_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
    ):
        run_id, sync_error = save_parts_stocking_run(
            snapshot,
            run_id=st.session_state.get("active_parts_stocking_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_parts_stocking_run_id = run_id
        st.session_state.parts_stocking_completed = True
        st.session_state.parts_saved_stock_snapshot = snapshot
        if sync_error:
            st.session_state["_parts_stocking_sync_error"] = sync_error
        else:
            st.session_state.pop("_parts_stocking_sync_error", None)
        st.session_state["_parts_stock_saved_label"] = snapshot.get("label")
        del st.session_state["parts_stock_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_parts_stock_saved_label", None):
        if st.session_state.get("_parts_stocking_sync_error"):
            st.error(
                f"Stocking plan for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under Parts Stocking · {saved}")
            st.balloons()

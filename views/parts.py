"""Parts return allowance planner — shared MNS + MNR dollars."""

from __future__ import annotations

from calendar import month_name
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.parts_return_calc import build_return_plan
from lib.parts_return_parser import (
    SOURCE_MNR,
    SOURCE_MNS,
    merge_parts_reports,
    parse_parts_workbook,
)
from lib.parts_return_pdf_export import generate_parts_return_pdf
from lib.parts_return_snapshot import serialize_parts_return_plan
from lib.parts_return_storage import save_parts_return_run
from views.payroll_helpers import render_payroll_sync_error


def _init_state():
    defaults = {
        "parts_mns_bytes": None,
        "parts_mns_name": "",
        "parts_mnr_bytes": None,
        "parts_mnr_name": "",
        "parts_mns_sig": "",
        "parts_mnr_sig": "",
        "parts_mns_lines": [],
        "parts_mnr_lines": [],
        "parts_allowance": 5000.0,
        "parts_exclude_multipack": True,
        "parts_exclude_hardware": True,
        "parts_min_age": 0.0,
        "parts_min_value": 0.0,
        "parts_allow_partial": True,
        "parts_notes": "",
        "parts_return_label": "",
        "parts_return_month": date.today().replace(day=1),
        "active_parts_return_run_id": None,
        "parts_return_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.get("parts_return_label"):
        month = st.session_state.parts_return_month
        st.session_state.parts_return_label = f"{month_name[month.month]} {month.year} Returns"


def _file_sig(name: str, data: bytes) -> str:
    return f"{name}:{len(data)}"


def _load_uploaded(report_type: str, uploaded, bytes_key: str, name_key: str, sig_key: str):
    if not uploaded:
        return
    data = uploaded.getvalue()
    sig = _file_sig(uploaded.name, data)
    if st.session_state.get(sig_key) == sig:
        return
    try:
        lines = parse_parts_workbook(BytesIO(data), report_type)
    except Exception as exc:
        st.markdown(
            status_banner(f"{report_type} file failed: {exc}", "warn"),
            unsafe_allow_html=True,
        )
        return
    st.session_state[bytes_key] = data
    st.session_state[name_key] = uploaded.name
    st.session_state[sig_key] = sig
    st.session_state[f"parts_{report_type.lower()}_lines"] = lines
    st.session_state.pop("parts_saved_snapshot", None)
    st.markdown(
        status_banner(
            f"✓ Loaded {report_type}: {len(lines)} parts from {uploaded.name}",
            "success",
        ),
        unsafe_allow_html=True,
    )


def _combined_lines():
    mns = st.session_state.get("parts_mns_lines") or []
    mnr = st.session_state.get("parts_mnr_lines") or []
    if not mns and not mnr:
        return []
    return merge_parts_reports(mns, mnr)


def _plan_dataframe(plan):
    rows = []
    for item in plan.selected:
        line = item.line
        rows.append(
            {
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Bin": line.bin_location or "—",
                "QOH": line.qoh,
                "Return qty": item.return_qty,
                "Cost": line.cost,
                "Return $": item.return_value,
                "Score": round(item.score, 1),
            }
        )
    return pd.DataFrame(rows)


def _skipped_dataframe(plan, limit: int = 40):
    rows = []
    for item in plan.skipped[:limit]:
        line = item.line
        rows.append(
            {
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Value": line.value,
                "Pack": line.pack,
                "Reason": item.skip_reason,
            }
        )
    return pd.DataFrame(rows)


def _current_snapshot(plan, lines):
    label = (st.session_state.get("parts_return_label") or "").strip()
    if not label:
        month = st.session_state.parts_return_month
        label = f"{month_name[month.month]} {month.year} Returns"
    return serialize_parts_return_plan(
        plan,
        label=label,
        mns_name=st.session_state.get("parts_mns_name") or "",
        mnr_name=st.session_state.get("parts_mnr_name") or "",
        mns_count=len(st.session_state.get("parts_mns_lines") or []),
        mnr_count=len(st.session_state.get("parts_mnr_lines") or []),
        candidate_count=len(lines),
        exclude_multipack=bool(st.session_state.parts_exclude_multipack),
        exclude_hardware=bool(st.session_state.parts_exclude_hardware),
        min_age=float(st.session_state.parts_min_age or 0),
        min_value=float(st.session_state.parts_min_value or 0),
        allow_partial=bool(st.session_state.parts_allow_partial),
        notes=str(st.session_state.get("parts_notes") or ""),
    )


def render():
    _init_state()

    st.markdown(
        page_hero(
            "Parts",
            "One return allowance for MNS (months no sale) and MNR (months no receipt). "
            "Rank by age × value, then export PDF and save to Reports.",
            tag="Returns",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("parts_return_completed"):
        st.markdown(
            status_banner(
                f"Editing saved return plan · {st.session_state.get('parts_return_label') or 'Parts'} · "
                "Export PDF or Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_parts_return_sync_error", table="parts_return_runs")

    st.markdown(
        '<span class="legend-chip chip-manual">MNS = months no sale</span> '
        '<span class="legend-chip chip-calc">MNR = months no receipt</span> '
        '<span class="legend-chip chip-live">Same $ allowance covers both lists</span>',
        unsafe_allow_html=True,
    )

    st.date_input(
        "Return period month",
        key="parts_return_month",
        format="MM/DD/YYYY",
        help="Used for the Reports label and PDF title.",
    )
    st.text_input(
        "Plan name (Reports label)",
        key="parts_return_label",
        help="How this run appears under Reports → Parts Returns.",
    )

    c1, c2 = st.columns(2)
    with c1:
        mns_file = st.file_uploader(
            "Upload MNS (.xlsx) — months no sale",
            type=["xlsx", "xls"],
            key="parts_mns_uploader",
            help="Months No Sale export from the parts system.",
        )
        _load_uploaded(
            SOURCE_MNS,
            mns_file,
            "parts_mns_bytes",
            "parts_mns_name",
            "parts_mns_sig",
        )
        if st.session_state.get("parts_mns_name"):
            st.caption(
                f"Loaded: {st.session_state.parts_mns_name} · "
                f"{len(st.session_state.get('parts_mns_lines') or [])} lines"
            )
    with c2:
        mnr_file = st.file_uploader(
            "Upload MNR (.xlsx) — months no receipt",
            type=["xlsx", "xls"],
            key="parts_mnr_uploader",
            help="Months No Receipt export from the parts system.",
        )
        _load_uploaded(
            SOURCE_MNR,
            mnr_file,
            "parts_mnr_bytes",
            "parts_mnr_name",
            "parts_mnr_sig",
        )
        if st.session_state.get("parts_mnr_name"):
            st.caption(
                f"Loaded: {st.session_state.parts_mnr_name} · "
                f"{len(st.session_state.get('parts_mnr_lines') or [])} lines"
            )

    lines = _combined_lines()
    if not lines:
        st.info("Upload an MNS and/or MNR spreadsheet to build a return list.")
        return

    st.markdown("---")
    st.markdown("##### Shared return allowance")
    st.caption(
        "Both MNS and MNR feed one combined candidate list. "
        "The dollar amount below is the single return allowance for this plan."
    )
    a1, a2, a3, a4 = st.columns([1.2, 1, 1, 1])
    with a1:
        st.number_input(
            "Allowance ($)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            key="parts_allowance",
            help="One allowance applied across MNS + MNR together.",
        )
    with a2:
        st.checkbox("Exclude multipack", key="parts_exclude_multipack")
    with a3:
        st.checkbox("Exclude misc hardware", key="parts_exclude_hardware")
    with a4:
        st.checkbox("Allow partial qty", key="parts_allow_partial")

    f1, f2 = st.columns(2)
    with f1:
        st.number_input(
            "Minimum age (months)",
            min_value=0.0,
            step=1.0,
            format="%.0f",
            key="parts_min_age",
        )
    with f2:
        st.number_input(
            "Minimum line value ($)",
            min_value=0.0,
            step=25.0,
            format="%.2f",
            key="parts_min_value",
        )

    plan = build_return_plan(
        lines,
        float(st.session_state.parts_allowance or 0),
        exclude_multipack=bool(st.session_state.parts_exclude_multipack),
        exclude_hardware=bool(st.session_state.parts_exclude_hardware),
        min_age=float(st.session_state.parts_min_age or 0),
        min_value=float(st.session_state.parts_min_value or 0),
        allow_partial_qty=bool(st.session_state.parts_allow_partial),
    )
    snapshot = _current_snapshot(plan, lines)

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            stat_card("Candidates", f"{len(lines)}", accent="cyan", icon="📦"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card("To return", f"{plan.selected_count}", accent="green", icon="↩️"),
            unsafe_allow_html=True,
        )
    with s3:
        st.markdown(
            stat_card(
                "Return $",
                f"${plan.selected_value:,.2f}",
                accent="purple",
                icon="$",
            ),
            unsafe_allow_html=True,
        )
    with s4:
        st.markdown(
            stat_card(
                "Allowance left",
                f"${plan.remaining_allowance:,.2f}",
                accent="orange",
                icon="▤",
            ),
            unsafe_allow_html=True,
        )

    if plan.selected_count == 0:
        st.markdown(
            status_banner(
                "No returnable parts fit this allowance with the current filters.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown("##### Recommended returns (age × value)")
        df = _plan_dataframe(plan)
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download return list (CSV)",
            data=csv,
            file_name="parts_return_list.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with st.expander("Skipped / filtered parts", expanded=False):
        skipped_df = _skipped_dataframe(plan)
        if skipped_df.empty:
            st.caption("Nothing skipped.")
        else:
            st.caption(f"Showing first {len(skipped_df)} of {len(plan.skipped)} skipped lines.")
            st.dataframe(skipped_df, use_container_width=True, hide_index=True)

    st.text_area("Notes (optional — included on PDF)", key="parts_notes", height=80)

    st.markdown("---")
    st.markdown("##### Export & save")
    pdf_bytes = generate_parts_return_pdf(snapshot)
    file_stub = str(snapshot.get("label") or "parts_return").replace(" ", "_")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "📄 Export return plan PDF",
            data=pdf_bytes,
            file_name=f"PARTS_RETURN_{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
            disabled=plan.selected_count == 0,
        )
    with e2:
        st.caption("PDF lists selected parts, allowance used, and MNS/MNR file names.")

    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This return plan is complete and ready to save",
        key="parts_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not confirm or plan.selected_count == 0,
        use_container_width=True,
    ):
        run_id, sync_error = save_parts_return_run(
            snapshot,
            run_id=st.session_state.get("active_parts_return_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_parts_return_run_id = run_id
        st.session_state.parts_return_completed = True
        st.session_state.parts_saved_snapshot = snapshot
        if sync_error:
            st.session_state["_parts_return_sync_error"] = sync_error
        else:
            st.session_state.pop("_parts_return_sync_error", None)
        st.session_state["_parts_saved_label"] = snapshot.get("label")
        del st.session_state["parts_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_parts_saved_label", None):
        if st.session_state.get("_parts_return_sync_error"):
            st.warning(
                "Saved on this device, but cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under Parts Returns · {saved}")

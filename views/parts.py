"""Parts return allowance planner — shared MNS + MNR dollars."""

from __future__ import annotations

from calendar import month_name
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.parts_return_calc import build_return_plan, plan_from_selected_parts
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
        "parts_selected_pns": [],
        "parts_selected_qty": {},
        "parts_removed_pns": [],
        "parts_removed_qty": {},
        "parts_sel_seed": "",
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
    st.session_state.parts_sel_seed = ""
    st.session_state.parts_removed_pns = []
    st.session_state.parts_removed_qty = {}
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


def _selection_seed(lines) -> str:
    return "|".join(
        [
            st.session_state.get("parts_mns_sig") or "",
            st.session_state.get("parts_mnr_sig") or "",
            str(float(st.session_state.get("parts_allowance") or 0)),
            str(bool(st.session_state.get("parts_exclude_multipack"))),
            str(bool(st.session_state.get("parts_exclude_hardware"))),
            str(float(st.session_state.get("parts_min_age") or 0)),
            str(float(st.session_state.get("parts_min_value") or 0)),
            str(bool(st.session_state.get("parts_allow_partial"))),
            str(len(lines)),
        ]
    )


def _seed_selection_from_auto(lines) -> None:
    seed = _selection_seed(lines)
    if st.session_state.get("parts_sel_seed") == seed:
        return
    if st.session_state.get("parts_sel_seed") == "restored" and st.session_state.get(
        "parts_selected_pns"
    ):
        # Keep restored picks until files/filters change enough to make a new seed.
        st.session_state.parts_sel_seed = seed
        return
    auto = build_return_plan(
        lines,
        float(st.session_state.parts_allowance or 0),
        exclude_multipack=bool(st.session_state.parts_exclude_multipack),
        exclude_hardware=bool(st.session_state.parts_exclude_hardware),
        min_age=float(st.session_state.parts_min_age or 0),
        min_value=float(st.session_state.parts_min_value or 0),
        allow_partial_qty=bool(st.session_state.parts_allow_partial),
    )
    st.session_state.parts_selected_pns = [c.line.part_number for c in auto.selected]
    st.session_state.parts_selected_qty = {
        c.line.part_number: c.return_qty for c in auto.selected
    }
    st.session_state.parts_removed_pns = []
    st.session_state.parts_removed_qty = {}
    st.session_state.parts_sel_seed = seed


def _line_lookup(lines) -> dict:
    return {str(line.part_number).strip().upper(): line for line in lines}


def _selected_editor_df(plan) -> pd.DataFrame:
    rows = []
    for item in plan.selected:
        line = item.line
        rows.append(
            {
                "Include": True,
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Bin": line.bin_location or "—",
                "Return qty": item.return_qty,
                "Return $": item.return_value,
            }
        )
    return pd.DataFrame(rows)


def _removed_editor_df(lines) -> pd.DataFrame:
    by_pn = _line_lookup(lines)
    qty_map = st.session_state.get("parts_removed_qty") or {}
    rows = []
    for pn in st.session_state.get("parts_removed_pns") or []:
        line = by_pn.get(str(pn).strip().upper())
        if not line:
            continue
        qty = qty_map.get(line.part_number, qty_map.get(pn, line.qoh))
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = float(line.qoh or 0)
        unit = line.cost if line.cost > 0 else (
            line.value / line.qoh if line.qoh else 0
        )
        value = round(qty * unit, 2) if unit else round(float(line.value or 0), 2)
        rows.append(
            {
                "Include": False,
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Bin": line.bin_location or "—",
                "Return qty": qty,
                "Return $": value,
            }
        )
    return pd.DataFrame(rows)


def _available_editor_df(plan) -> pd.DataFrame:
    removed = {
        str(pn).strip().upper()
        for pn in (st.session_state.get("parts_removed_pns") or [])
    }
    rows = []
    for item in plan.skipped:
        line = item.line
        if line.part_number.upper() in removed:
            continue
        rows.append(
            {
                "Include": False,
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Value": line.value,
                "Pack": line.pack,
                "Note": item.skip_reason,
            }
        )
    return pd.DataFrame(rows)


def _sync_selection_from_editors(
    edited_sel: pd.DataFrame,
    edited_removed: pd.DataFrame,
    edited_avail: pd.DataFrame,
) -> bool:
    """Update suggested + removed trays from checkbox editors. Returns True if changed."""
    prev_selected = list(st.session_state.get("parts_selected_pns") or [])
    prev_qty = dict(st.session_state.get("parts_selected_qty") or {})
    prev_removed = list(st.session_state.get("parts_removed_pns") or [])
    prev_removed_qty = dict(st.session_state.get("parts_removed_qty") or {})

    selected: list[str] = []
    qty_map = dict(prev_qty)
    removed: list[str] = []
    removed_qty = dict(prev_removed_qty)

    # Still-checked suggested rows stay selected.
    unchecked_from_suggested: list[str] = []
    if edited_sel is not None and not edited_sel.empty:
        for _, row in edited_sel.iterrows():
            pn = str(row.get("Part Number") or "").strip()
            if not pn:
                continue
            if bool(row.get("Include")):
                selected.append(pn)
                try:
                    qty_map[pn] = float(row.get("Return qty") or qty_map.get(pn) or 0)
                except (TypeError, ValueError):
                    pass
            else:
                unchecked_from_suggested.append(pn)
                try:
                    removed_qty[pn] = float(
                        row.get("Return qty") or prev_qty.get(pn) or removed_qty.get(pn) or 0
                    )
                except (TypeError, ValueError):
                    removed_qty[pn] = prev_qty.get(pn, removed_qty.get(pn))
                qty_map.pop(pn, None)

    # Removed tray: keep unless Include is checked (add back).
    restored_from_removed: list[str] = []
    if edited_removed is not None and not edited_removed.empty:
        for _, row in edited_removed.iterrows():
            pn = str(row.get("Part Number") or "").strip()
            if not pn:
                continue
            if bool(row.get("Include")):
                restored_from_removed.append(pn)
                if pn not in selected:
                    selected.append(pn)
                try:
                    qty_map[pn] = float(
                        row.get("Return qty") or removed_qty.get(pn) or qty_map.get(pn) or 0
                    )
                except (TypeError, ValueError):
                    pass
                removed_qty.pop(pn, None)
            else:
                if pn not in removed:
                    removed.append(pn)
                try:
                    removed_qty[pn] = float(
                        row.get("Return qty") or removed_qty.get(pn) or 0
                    )
                except (TypeError, ValueError):
                    pass

    # Preserve prior removed order for anything not shown in the editor this pass.
    for pn in prev_removed:
        if pn in restored_from_removed or pn in selected:
            continue
        if pn not in removed:
            removed.append(pn)

    # Newly unchecked from suggested go to the front of the removed tray.
    for pn in reversed(unchecked_from_suggested):
        if pn in selected:
            continue
        if pn in removed:
            removed = [p for p in removed if p != pn]
        removed.insert(0, pn)

    if edited_avail is not None and not edited_avail.empty:
        for _, row in edited_avail.iterrows():
            pn = str(row.get("Part Number") or "").strip()
            if not pn:
                continue
            if bool(row.get("Include")):
                if pn not in selected:
                    selected.append(pn)
                qty_map.setdefault(pn, None)
                if pn in removed:
                    removed = [p for p in removed if p != pn]
                removed_qty.pop(pn, None)

    clean_qty = {k: v for k, v in qty_map.items() if v is not None and k in selected}
    clean_removed_qty = {
        k: v for k, v in removed_qty.items() if v is not None and k in removed
    }

    if (
        selected == prev_selected
        and clean_qty == prev_qty
        and removed == prev_removed
        and clean_removed_qty == prev_removed_qty
    ):
        return False

    st.session_state.parts_selected_pns = selected
    st.session_state.parts_selected_qty = clean_qty
    st.session_state.parts_removed_pns = removed
    st.session_state.parts_removed_qty = clean_removed_qty
    return True


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
        removed_part_numbers=list(st.session_state.get("parts_removed_pns") or []),
        removed_qty_by_part=dict(st.session_state.get("parts_removed_qty") or {}),
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

    _seed_selection_from_auto(lines)
    plan = plan_from_selected_parts(
        lines,
        float(st.session_state.parts_allowance or 0),
        st.session_state.get("parts_selected_pns") or [],
        qty_by_part=st.session_state.get("parts_selected_qty") or {},
        exclude_multipack=bool(st.session_state.parts_exclude_multipack),
        exclude_hardware=bool(st.session_state.parts_exclude_hardware),
        min_age=float(st.session_state.parts_min_age or 0),
        min_value=float(st.session_state.parts_min_value or 0),
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
        left_label = "Allowance left"
        left_value = plan.remaining_allowance
        accent = "orange"
        if left_value < -0.005:
            left_label = "Over allowance"
            left_value = abs(left_value)
            accent = "rose"
        st.markdown(
            stat_card(
                left_label,
                f"${left_value:,.2f}",
                accent=accent,
                icon="▤",
            ),
            unsafe_allow_html=True,
        )

    if plan.remaining_allowance < -0.005:
        st.markdown(
            status_banner(
                f"Selected parts are ${abs(plan.remaining_allowance):,.2f} over the "
                f"${plan.allowance:,.2f} allowance — uncheck something in Suggested returns.",
                "warn",
            ),
            unsafe_allow_html=True,
        )

    sel_fp = "|".join(st.session_state.get("parts_selected_pns") or [])
    rem_fp = "|".join(st.session_state.get("parts_removed_pns") or [])
    editor_token = abs(hash(f"{sel_fp}::{rem_fp}")) % 10_000_000

    st.markdown("##### Suggested returns")
    st.caption(
        "Auto-filled by age × value. Uncheck to park a part in Removed below — "
        "return $ always comes from this box."
    )
    sel_df = _selected_editor_df(plan)
    if sel_df.empty:
        st.info(
            "Nothing in the suggested box yet — check a part in Removed or Other candidates."
        )
        edited_sel = sel_df
    else:
        edited_sel = st.data_editor(
            sel_df,
            use_container_width=True,
            hide_index=True,
            key=f"parts_suggested_editor_{editor_token}",
            column_config={
                "Include": st.column_config.CheckboxColumn("Include", default=True),
                "Return $": st.column_config.NumberColumn(format="$%.2f"),
                "Return qty": st.column_config.NumberColumn(format="%.0f", min_value=0),
                "Age (mo)": st.column_config.NumberColumn(format="%.0f"),
            },
            disabled=["Part Number", "Description", "Source", "Age (mo)", "Bin", "Return $"],
        )

    st.markdown("##### Removed from suggested")
    st.caption(
        "Parts you unchecked from Suggested. Check Include to put them back — "
        "no hunting through the full list."
    )
    removed_df = _removed_editor_df(lines)
    if removed_df.empty:
        st.caption("No removed parts yet.")
        edited_removed = removed_df
    else:
        edited_removed = st.data_editor(
            removed_df,
            use_container_width=True,
            hide_index=True,
            key=f"parts_removed_editor_{editor_token}",
            column_config={
                "Include": st.column_config.CheckboxColumn(
                    "Add back",
                    default=False,
                    help="Check to move this part back into Suggested returns.",
                ),
                "Return $": st.column_config.NumberColumn(format="$%.2f"),
                "Return qty": st.column_config.NumberColumn(format="%.0f", min_value=0),
                "Age (mo)": st.column_config.NumberColumn(format="%.0f"),
            },
            disabled=["Part Number", "Description", "Source", "Age (mo)", "Bin", "Return $"],
        )

    st.markdown("##### Other candidates")
    st.caption("Check Include to move a part into Suggested returns and recalculate.")
    avail_df = _available_editor_df(plan)
    if avail_df.empty:
        st.caption("No other candidates.")
        edited_avail = avail_df
    else:
        edited_avail = st.data_editor(
            avail_df,
            use_container_width=True,
            hide_index=True,
            key=f"parts_available_editor_{editor_token}",
            height=360,
            column_config={
                "Include": st.column_config.CheckboxColumn("Include", default=False),
                "Value": st.column_config.NumberColumn(format="$%.2f"),
                "Age (mo)": st.column_config.NumberColumn(format="%.0f"),
                "Pack": st.column_config.NumberColumn(format="%.0f"),
            },
            disabled=[
                "Part Number",
                "Description",
                "Source",
                "Age (mo)",
                "Value",
                "Pack",
                "Note",
            ],
        )

    if _sync_selection_from_editors(edited_sel, edited_removed, edited_avail):
        st.rerun()

    if plan.selected_count:
        csv = _selected_editor_df(plan).drop(columns=["Include"], errors="ignore").to_csv(
            index=False
        ).encode("utf-8")
        st.download_button(
            "Download return list (CSV)",
            data=csv,
            file_name="parts_return_list.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if st.button("Reset to age × value suggestion", use_container_width=True):
        st.session_state.parts_sel_seed = ""
        st.session_state.parts_removed_pns = []
        st.session_state.parts_removed_qty = {}
        st.rerun()

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

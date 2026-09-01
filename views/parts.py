"""Parts return allowance planner — MNS return allowance."""

from __future__ import annotations

from calendar import month_name
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, stat_card, status_banner
from lib.parts_return_calc import (
    build_return_plan,
    plan_from_selected_parts,
    ranked_replacement_candidates,
)
from lib.parts_return_parser import (
    SOURCE_MNS,
    merge_parts_reports,
    parse_parts_workbook,
)
from lib.parts_return_pdf_export import generate_parts_return_pdf
from lib.parts_return_snapshot import serialize_parts_return_plan
from lib.parts_return_storage import save_parts_return_run
from views import parts_stocking
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
        "parts_offer_active": False,
        "parts_offer_queue": [],
        "parts_offer_index": 0,
        "parts_manual_mode": False,
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
    st.session_state.parts_offer_active = False
    st.session_state.parts_offer_queue = []
    st.session_state.parts_offer_index = 0
    st.session_state.parts_manual_mode = False
    st.markdown(
        status_banner(
            f"✓ Loaded {report_type}: {len(lines)} parts from {uploaded.name}",
            "success",
        ),
        unsafe_allow_html=True,
    )


def _combined_lines():
    mns = st.session_state.get("parts_mns_lines") or []
    if not mns:
        return []
    return merge_parts_reports(mns, [])


def _selection_seed(lines) -> str:
    return "|".join(
        [
            st.session_state.get("parts_mns_sig") or "",
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
    st.session_state.parts_offer_active = False
    st.session_state.parts_offer_queue = []
    st.session_state.parts_offer_index = 0
    st.session_state.parts_manual_mode = False
    st.session_state.parts_sel_seed = seed


def _start_replacement_offer(lines, remaining_allowance: float) -> None:
    """Open the next-suggestion window after a part is removed from Suggested."""
    if st.session_state.get("parts_manual_mode"):
        return
    candidates = ranked_replacement_candidates(
        lines,
        selected_part_numbers=st.session_state.get("parts_selected_pns") or [],
        skip_part_numbers=st.session_state.get("parts_removed_pns") or [],
        remaining_allowance=remaining_allowance,
        exclude_multipack=bool(st.session_state.parts_exclude_multipack),
        exclude_hardware=bool(st.session_state.parts_exclude_hardware),
        min_age=float(st.session_state.parts_min_age or 0),
        min_value=float(st.session_state.parts_min_value or 0),
        allow_partial_qty=bool(st.session_state.parts_allow_partial),
    )
    queue = [c.line.part_number for c in candidates]
    st.session_state.parts_offer_queue = queue
    st.session_state.parts_offer_index = 0
    st.session_state.parts_offer_active = bool(queue)
    st.session_state.parts_offer_qty = {
        c.line.part_number: c.return_qty for c in candidates
    }


def _current_offer_candidate(lines):
    if not st.session_state.get("parts_offer_active"):
        return None
    queue = st.session_state.get("parts_offer_queue") or []
    idx = int(st.session_state.get("parts_offer_index") or 0)
    if not queue or idx < 0 or idx >= len(queue):
        return None
    by_pn = _line_lookup(lines)
    line = by_pn.get(str(queue[idx]).strip().upper())
    if not line:
        return None
    qty_map = st.session_state.get("parts_offer_qty") or {}
    qty = float(qty_map.get(line.part_number, line.qoh) or line.qoh)
    unit = line.cost if line.cost > 0 else (line.value / line.qoh if line.qoh else 0)
    value = round(qty * unit, 2) if unit else round(float(line.value or 0), 2)
    return {
        "part_number": line.part_number,
        "description": line.description,
        "source": line.source,
        "age": line.age,
        "bin": line.bin_location or "—",
        "qty": qty,
        "value": value,
        "index": idx,
        "total": len(queue),
    }


def _accept_current_offer() -> None:
    offer_pn = None
    queue = st.session_state.get("parts_offer_queue") or []
    idx = int(st.session_state.get("parts_offer_index") or 0)
    if queue and 0 <= idx < len(queue):
        offer_pn = queue[idx]
    if not offer_pn:
        st.session_state.parts_offer_active = False
        return
    selected = list(st.session_state.get("parts_selected_pns") or [])
    if offer_pn not in selected:
        selected.append(offer_pn)
    qty_map = dict(st.session_state.get("parts_selected_qty") or {})
    offer_qty = (st.session_state.get("parts_offer_qty") or {}).get(offer_pn)
    if offer_qty is not None:
        qty_map[offer_pn] = float(offer_qty)
    removed = [
        pn for pn in (st.session_state.get("parts_removed_pns") or []) if pn != offer_pn
    ]
    rem_qty = dict(st.session_state.get("parts_removed_qty") or {})
    rem_qty.pop(offer_pn, None)
    st.session_state.parts_selected_pns = selected
    st.session_state.parts_selected_qty = qty_map
    st.session_state.parts_removed_pns = removed
    st.session_state.parts_removed_qty = rem_qty
    st.session_state.parts_offer_active = False
    st.session_state.parts_offer_queue = []
    st.session_state.parts_offer_index = 0


def _advance_offer() -> None:
    queue = st.session_state.get("parts_offer_queue") or []
    idx = int(st.session_state.get("parts_offer_index") or 0) + 1
    if idx >= len(queue):
        st.session_state.parts_offer_active = False
        st.session_state.parts_offer_index = 0
        st.session_state.parts_manual_mode = True
        return
    st.session_state.parts_offer_index = idx


def _enter_manual_selection() -> None:
    st.session_state.parts_offer_active = False
    st.session_state.parts_offer_queue = []
    st.session_state.parts_offer_index = 0
    st.session_state.parts_manual_mode = True


def _line_lookup(lines) -> dict:
    return {str(line.part_number).strip().upper(): line for line in lines}


def _selected_editor_df(plan) -> pd.DataFrame:
    rows = []
    for item in plan.selected:
        line = item.line
        unit = line.cost if line.cost > 0 else (
            line.value / line.qoh if line.qoh else 0
        )
        rows.append(
            {
                "Include": True,
                "Part Number": line.part_number,
                "Description": line.description,
                "Source": line.source,
                "Age (mo)": line.age,
                "Bin": line.bin_location or "—",
                "On hand": line.qoh,
                "Return qty": item.return_qty,
                "Unit $": round(float(unit or 0), 2),
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


def _as_qty(value, fallback: float = 0.0) -> float:
    if value is None or value == "":
        return float(fallback or 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback or 0)


def _qty_maps_equal(left: dict, right: dict) -> bool:
    if set(left.keys()) != set(right.keys()):
        return False
    for key in left:
        if abs(float(left[key] or 0) - float(right[key] or 0)) > 0.001:
            return False
    return True


def _sync_selection_from_editors(
    edited_sel: pd.DataFrame,
    edited_removed: pd.DataFrame,
    edited_avail: pd.DataFrame,
    lines=None,
) -> tuple[bool, list[str]]:
    """Update suggested + removed trays. Returns (changed, newly_unchecked_pns)."""
    prev_selected = list(st.session_state.get("parts_selected_pns") or [])
    prev_qty = dict(st.session_state.get("parts_selected_qty") or {})
    prev_removed = list(st.session_state.get("parts_removed_pns") or [])
    prev_removed_qty = dict(st.session_state.get("parts_removed_qty") or {})
    by_pn = _line_lookup(lines or [])

    selected: list[str] = []
    qty_map = dict(prev_qty)
    removed: list[str] = []
    removed_qty = dict(prev_removed_qty)

    # Still-checked suggested rows stay selected (qty may be partial).
    unchecked_from_suggested: list[str] = []
    if edited_sel is not None and not edited_sel.empty:
        for _, row in edited_sel.iterrows():
            pn = str(row.get("Part Number") or "").strip()
            if not pn:
                continue
            line = by_pn.get(pn.upper())
            max_qoh = float(line.qoh) if line else None
            if bool(row.get("Include")):
                selected.append(pn)
                qty = _as_qty(row.get("Return qty"), qty_map.get(pn, max_qoh or 0))
                if max_qoh is not None:
                    qty = max(0.0, min(qty, max_qoh))
                qty_map[pn] = qty
            else:
                unchecked_from_suggested.append(pn)
                removed_qty[pn] = _as_qty(
                    row.get("Return qty"),
                    prev_qty.get(pn, removed_qty.get(pn, max_qoh or 0)),
                )
                qty_map.pop(pn, None)

    # Removed tray: keep unless Include is checked (add back).
    restored_from_removed: list[str] = []
    if edited_removed is not None and not edited_removed.empty:
        for _, row in edited_removed.iterrows():
            pn = str(row.get("Part Number") or "").strip()
            if not pn:
                continue
            line = by_pn.get(pn.upper())
            max_qoh = float(line.qoh) if line else None
            if bool(row.get("Include")):
                restored_from_removed.append(pn)
                if pn not in selected:
                    selected.append(pn)
                qty = _as_qty(
                    row.get("Return qty"),
                    removed_qty.get(pn, qty_map.get(pn, max_qoh or 0)),
                )
                if max_qoh is not None:
                    qty = max(0.0, min(qty, max_qoh))
                qty_map[pn] = qty
                removed_qty.pop(pn, None)
            else:
                if pn not in removed:
                    removed.append(pn)
                removed_qty[pn] = _as_qty(
                    row.get("Return qty"),
                    removed_qty.get(pn, max_qoh or 0),
                )

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
                line = by_pn.get(pn.upper())
                if pn not in qty_map:
                    qty_map[pn] = float(line.qoh) if line else None
                if pn in removed:
                    removed = [p for p in removed if p != pn]
                removed_qty.pop(pn, None)

    clean_qty = {
        k: float(v)
        for k, v in qty_map.items()
        if v is not None and k in selected and float(v) > 0
    }
    # Drop zero-qty lines from suggested (partial send of nothing = not returning).
    selected = [pn for pn in selected if pn in clean_qty]
    clean_removed_qty = {
        k: float(v) for k, v in removed_qty.items() if v is not None and k in removed
    }

    if (
        selected == prev_selected
        and _qty_maps_equal(clean_qty, prev_qty)
        and removed == prev_removed
        and _qty_maps_equal(clean_removed_qty, prev_removed_qty)
    ):
        return False, []

    st.session_state.parts_selected_pns = selected
    st.session_state.parts_selected_qty = clean_qty
    st.session_state.parts_removed_pns = removed
    st.session_state.parts_removed_qty = clean_removed_qty
    return True, unchecked_from_suggested


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


def _render_parts_mode_switcher() -> str:
    if "parts_active_tab" not in st.session_state:
        st.session_state.parts_active_tab = "Returns"
    active = st.session_state.parts_active_tab

    with st.container(border=True):
        st.markdown(
            '<span class="parts-mode-marker"></span>'
            '<div class="parts-mode-banner">'
            '<div class="parts-mode-banner-title">Parts workspace</div>'
            '<div class="parts-mode-banner-sub">'
            "Choose <strong>Returns</strong> (MNS allowance) or "
            "<strong>Stocking</strong> (6MS order planner)"
            "</div></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            returns_active = active == "Returns"
            if st.button(
                "↩ Returns\nMNS return allowance",
                key="parts_pick_returns",
                use_container_width=True,
                type="primary" if returns_active else "secondary",
                help="Plan MNS parts returns against your allowance",
            ):
                if not returns_active:
                    st.session_state.parts_active_tab = "Returns"
                    st.rerun()
        with c2:
            stocking_active = active == "Stocking"
            if st.button(
                "📦 Stocking\n6MS order planner",
                key="parts_pick_stocking",
                use_container_width=True,
                type="primary" if stocking_active else "secondary",
                help="Upload 6-month sales and build order lists",
            ):
                if not stocking_active:
                    st.session_state.parts_active_tab = "Stocking"
                    st.rerun()

    return active


def render():
    _render_parts_mode_switcher()
    tab = st.session_state.get("parts_active_tab", "Returns")
    if tab == "Returns":
        _render_returns()
    else:
        parts_stocking.render()


def _render_returns():
    _init_state()

    st.markdown(
        page_hero(
            "Returns",
            "Return allowance planner for MNS (months no sale). "
            "Rank by age × value, then export PDF and save to Reports.",
            tag="MNS",
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
        '<span class="legend-chip chip-live">Age × value ranking · partial qty supported</span>',
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

    lines = _combined_lines()
    if not lines:
        st.info("Upload an MNS spreadsheet to build a return list.")
        return

    st.markdown("---")
    st.markdown("##### Return allowance")
    st.caption(
        "The dollar amount below is the return allowance for this plan."
    )
    a1, a2, a3, a4 = st.columns([1.2, 1, 1, 1])
    with a1:
        st.number_input(
            "Allowance ($)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            key="parts_allowance",
            help="Return allowance for this MNS plan.",
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
    offer_fp = f"{st.session_state.get('parts_offer_index')}:{len(st.session_state.get('parts_offer_queue') or [])}"
    editor_token = abs(hash(f"{sel_fp}::{rem_fp}::{offer_fp}")) % 10_000_000

    st.markdown("##### Suggested returns")
    st.caption(
        "Auto-filled by age × value. **Double-click Return qty** to send back only part of a "
        "line (example: change 14 oil filters to 5) — Return $ and allowance update from unit cost. "
        "Uncheck Include to park the whole part in Removed."
    )
    sel_df = _selected_editor_df(plan)
    if sel_df.empty:
        st.info(
            "Nothing in the suggested box yet — accept a next suggestion or pick manually."
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
                "On hand": st.column_config.NumberColumn(
                    "On hand",
                    format="%.0f",
                    help="Quantity on the shelf (cannot return more than this).",
                ),
                "Return qty": st.column_config.NumberColumn(
                    "Return qty",
                    format="%.0f",
                    min_value=0,
                    step=1,
                    help="Edit this to return a partial quantity. Return $ = qty × unit cost.",
                ),
                "Unit $": st.column_config.NumberColumn(format="$%.2f"),
                "Return $": st.column_config.NumberColumn(
                    format="$%.2f",
                    help="Recalculated from Return qty × Unit $.",
                ),
                "Age (mo)": st.column_config.NumberColumn(format="%.0f"),
            },
            disabled=[
                "Part Number",
                "Description",
                "Source",
                "Age (mo)",
                "Bin",
                "On hand",
                "Unit $",
                "Return $",
            ],
        )

    offer = _current_offer_candidate(lines)
    if st.session_state.get("parts_offer_active") and offer:
        st.markdown("##### Next suggested return")
        st.caption(
            f"Suggestion {offer['index'] + 1} of {offer['total']} · "
            f"${plan.remaining_allowance:,.2f} allowance remaining"
        )
        st.markdown(
            status_banner(
                f"<strong>{offer['part_number']}</strong> — {offer['description']} · "
                f"{offer['source']} · Age {offer['age']:.0f} mo · Bin {offer['bin']} · "
                f"Qty {offer['qty']:.0f} · <strong>${offer['value']:,.2f}</strong>",
                "info",
            ),
            unsafe_allow_html=True,
        )
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button(
                "➕ Add to suggested",
                type="primary",
                use_container_width=True,
                key="parts_offer_add",
            ):
                _accept_current_offer()
                st.rerun()
        with b2:
            if st.button(
                "Next suggestion →",
                use_container_width=True,
                key="parts_offer_next",
            ):
                _advance_offer()
                st.rerun()
        with b3:
            if st.button(
                "Manual selection",
                use_container_width=True,
                key="parts_offer_manual",
            ):
                _enter_manual_selection()
                st.rerun()
    elif st.session_state.get("parts_manual_mode"):
        st.markdown(
            status_banner(
                "Manual selection — pick parts from Other candidates below, "
                "or Add back from Removed.",
                "info",
            ),
            unsafe_allow_html=True,
        )
        if st.button("Back to guided suggestions", key="parts_exit_manual"):
            st.session_state.parts_manual_mode = False
            _start_replacement_offer(lines, max(float(plan.remaining_allowance or 0), 0.0))
            st.rerun()

    st.markdown("##### Removed from suggested")
    st.caption(
        "Parts you unchecked from Suggested. Check Add back to restore them."
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

    show_other = bool(
        st.session_state.get("parts_manual_mode")
        or not st.session_state.get("parts_offer_active")
    )
    edited_avail = pd.DataFrame()
    if show_other:
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
    else:
        st.caption(
            "Other candidates are hidden while a next suggestion is open — "
            "use **Manual selection** to pick from the full list."
        )

    changed, unchecked = _sync_selection_from_editors(
        edited_sel, edited_removed, edited_avail, lines=lines
    )
    if changed:
        after = plan_from_selected_parts(
            lines,
            float(st.session_state.parts_allowance or 0),
            st.session_state.get("parts_selected_pns") or [],
            qty_by_part=st.session_state.get("parts_selected_qty") or {},
            exclude_multipack=bool(st.session_state.parts_exclude_multipack),
            exclude_hardware=bool(st.session_state.parts_exclude_hardware),
            min_age=float(st.session_state.parts_min_age or 0),
            min_value=float(st.session_state.parts_min_value or 0),
        )
        # Uncheck whole line, or free dollars by lowering Return qty → offer next fill.
        prev_used = float(plan.selected_value or 0)
        freed = prev_used - float(after.selected_value or 0)
        if unchecked or freed > 0.5:
            _start_replacement_offer(lines, max(float(after.remaining_allowance or 0), 0.0))
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
        st.session_state.parts_offer_active = False
        st.session_state.parts_offer_queue = []
        st.session_state.parts_offer_index = 0
        st.session_state.parts_manual_mode = False
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
        st.caption("PDF lists selected parts, allowance used, and the MNS file name.")

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

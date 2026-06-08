from __future__ import annotations

import streamlit as st
import pandas as pd

from components.ui import page_hero, stat_card, status_banner
from lib.warranty_custom_exclusions import (
    add_custom_exclusion,
    load_custom_exclusions,
    remove_custom_exclusion,
)
from lib.warranty_labor_calc import (
    ELR_THRESHOLD,
    WarrantyLaborRow,
    apply_import_exclusions,
    exclusion_widget_key,
    exclusion_widget_label,
    get_builtin_exclusion_values,
    get_exclusion_select_options,
    label_to_exclusion,
    review_widget_key,
    rows_to_display_dicts,
    summarize_rows,
)
from lib.warranty_labor_parser import list_sheet_names, parse_warranty_labor_report
from lib.warranty_labor_pdf_export import (
    generate_warranty_analysis_pdf,
    generate_warranty_original_pdf,
)
from lib.warranty_labor_storage import apply_warranty_snapshot_to_session, save_warranty_labor_run

def _money(v: float) -> str:
    return f"${v:,.2f}"


def _init_warranty_session():
    if "warranty_labor_rows" not in st.session_state:
        st.session_state.warranty_labor_rows = []
    if "warranty_custom_exclusions" not in st.session_state:
        st.session_state.warranty_custom_exclusions = load_custom_exclusions()


def _clear_exclusion_widgets():
    for key in list(st.session_state.keys()):
        if key.startswith("warranty_exc_"):
            del st.session_state[key]


def _clear_review_widgets():
    for key in list(st.session_state.keys()):
        if key.startswith("warranty_ro_reviewed_"):
            del st.session_state[key]


def _init_review_widgets(recids: list[str]):
    reviewed_seed = st.session_state.get("warranty_reviewed_ros", set())
    for recid in recids:
        key = review_widget_key(recid)
        if key not in st.session_state:
            st.session_state[key] = recid in reviewed_seed


def _collect_reviewed_recids(recids: list[str]) -> set[str]:
    return {
        recid
        for recid in recids
        if st.session_state.get(review_widget_key(recid), False)
    }


def _sort_ro_groups(
    ro_groups: list[tuple[str, list[WarrantyLaborRow]]],
    reviewed_recids: set[str],
    jump_ro: str | None = None,
) -> list[tuple[str, list[WarrantyLaborRow]]]:
    def sort_key(item: tuple[str, list[WarrantyLaborRow]]):
        recid = item[0]
        if jump_ro and recid == jump_ro:
            return (0, 0, recid)
        return (1, recid in reviewed_recids, recid)

    return sorted(ro_groups, key=sort_key)


def _sync_row_exclusions(rows, custom_exclusions):
    for row in rows:
        key = exclusion_widget_key(row)
        if key not in st.session_state:
            st.session_state[key] = exclusion_widget_label(row.exclusion)
        row.exclusion = label_to_exclusion(st.session_state[key], custom_exclusions)


def _group_rows_by_ro(rows: list[WarrantyLaborRow]) -> list[tuple[str, list[WarrantyLaborRow]]]:
    grouped: dict[str, list[WarrantyLaborRow]] = {}
    order: list[str] = []
    for row in rows:
        recid = str(row.recid).strip()
        if recid not in grouped:
            grouped[recid] = []
            order.append(recid)
        grouped[recid].append(row)
    return [(recid, grouped[recid]) for recid in order]


def _elr_class(elr: float, excluded: bool) -> str:
    if excluded:
        return ""
    if elr >= ELR_THRESHOLD:
        return "warranty-ro-elr-good"
    if elr > 0:
        return "warranty-ro-elr-bad"
    return ""


def _render_ro_card(
    recid: str,
    ro_lines: list[WarrantyLaborRow],
    select_options: list[str],
    *,
    is_reviewed: bool,
    is_focus: bool,
):
    included_lines = [line for line in ro_lines if not (line.exclusion or "").strip()]
    ro_labor = sum(line.lbr_sale for line in included_lines)
    ro_hours = sum(line.tech_hrs for line in included_lines)
    all_excluded = len(included_lines) == 0
    header = ro_lines[0]
    card_class = "warranty-ro-card-reviewed" if is_reviewed else "warranty-ro-card-pending"
    if is_focus:
        card_class += " warranty-ro-card-focus"

    st.markdown(f'<div class="warranty-ro-wrap {card_class}">', unsafe_allow_html=True)
    with st.container(border=True):
        title_col, review_col, total_col = st.columns([1.35, 0.75, 1])
        with title_col:
            badge = (
                '<span class="warranty-review-badge done">Reviewed</span>'
                if is_reviewed
                else '<span class="warranty-review-badge pending">Needs review</span>'
            )
            st.markdown(f"**RO {recid}** {badge}", unsafe_allow_html=True)
            st.caption(
                f"{header.ro_date} · {len(ro_lines)} line{'s' if len(ro_lines) != 1 else ''}"
                + (" · all lines excluded" if all_excluded else "")
            )
        with review_col:
            st.checkbox(
                "Reviewed",
                key=review_widget_key(recid),
                help="Check when you have finished reviewing this repair order.",
            )
        with total_col:
            st.markdown(
                f'<div class="warranty-ro-total">{len(included_lines)} included<br>'
                f"{_money(ro_labor)} / {ro_hours:.2f} hrs</div>",
                unsafe_allow_html=True,
            )

        for line_index, line in enumerate(ro_lines, start=1):
            line_title = (
                f"Line {line_index} of {len(ro_lines)}"
                if len(ro_lines) > 1
                else "Operation line"
            )
            line_container = st.container(border=True) if len(ro_lines) > 1 else st.container()
            with line_container:
                _render_ro_line(line, line_title, select_options)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_ro_line(line: WarrantyLaborRow, line_title: str, select_options: list[str]):
    excluded = bool((line.exclusion or "").strip())
    elr_class = _elr_class(line.elr, excluded)
    st.markdown(f'<div class="warranty-ro-line-title">{line_title}</div>', unsafe_allow_html=True)
    top = st.columns([1.2, 1.8, 0.8, 0.9, 0.9])
    fields = [
        ("Op Code", line.op_code),
        ("Description", line.op_desc),
        ("Tech Hrs", f"{line.tech_hrs:.2f}"),
        ("Labor Sale", _money(line.lbr_sale)),
        ("ELR", _money(line.elr)),
    ]
    for col, (label, value) in zip(top, fields):
        col.markdown(
            f'<div class="warranty-ro-line-label">{label}</div>'
            f'<div class="{elr_class if label == "ELR" else ""}">{value}</div>',
            unsafe_allow_html=True,
        )
    st.selectbox(
        f"Exclusion · {line_title}",
        options=select_options,
        key=exclusion_widget_key(line),
        label_visibility="visible",
    )
    if excluded:
        st.caption("Excluded from shop ELR")


def _style_labor_table(df: pd.DataFrame):
    def _row_style(row):
        styles = [""] * len(row)
        exclusion = str(row.get("Exclusion", "") or "").strip()
        if exclusion and exclusion != "Included":
            return ["color: #94a3b8; text-decoration: line-through;" for _ in row]
        elr = float(row.get("ELR", 0) or 0)
        if elr >= ELR_THRESHOLD:
            styles[list(row.index).index("ELR")] = (
                "background-color: #14532d; color: #bbf7d0; font-weight: 700;"
            )
        elif elr > 0:
            styles[list(row.index).index("ELR")] = (
                "background-color: #7f1d1d; color: #fecaca; font-weight: 700;"
            )
        return styles

    return df.style.apply(_row_style, axis=1)


def _render_custom_exclusions_editor():
    st.markdown("##### Custom exclusions")
    st.caption("Add your own exclusion categories — they appear in every line's dropdown.")

    custom_exclusions = st.session_state.warranty_custom_exclusions
    add_col, btn_col = st.columns([3, 1])
    with add_col:
        new_exclusion = st.text_input(
            "New exclusion",
            placeholder="e.g. Sublet work",
            key="warranty_new_exclusion_input",
            label_visibility="collapsed",
        )
    with btn_col:
        if st.button("Add exclusion", use_container_width=True, key="warranty_add_exclusion_btn"):
            updated, error = add_custom_exclusion(
                new_exclusion,
                existing=custom_exclusions,
                reserved=get_builtin_exclusion_values() + custom_exclusions,
            )
            st.session_state.warranty_custom_exclusions = updated
            if error:
                st.session_state.warranty_exclusion_notice = ("warn", error)
            else:
                st.session_state.warranty_exclusion_notice = (
                    "success",
                    f"Added “{updated[-1]}” to exclusion dropdowns.",
                )
            st.rerun()

    if custom_exclusions:
        for label in custom_exclusions:
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {label}")
            if c2.button("Remove", key=f"warranty_remove_exc_{label}", use_container_width=True):
                st.session_state.warranty_custom_exclusions = remove_custom_exclusion(
                    label,
                    existing=custom_exclusions,
                )
                st.session_state.warranty_exclusion_notice = (
                    "success",
                    f"Removed “{label}” from custom exclusions.",
                )
                st.rerun()
    else:
        st.caption("No custom exclusions yet.")


def _render_review_progress(ro_groups: list[tuple[str, list[WarrantyLaborRow]]]):
    recids = [recid for recid, _ in ro_groups]
    reviewed = _collect_reviewed_recids(recids)
    total = len(ro_groups)
    reviewed_count = len(reviewed)
    remaining = total - reviewed_count
    progress = reviewed_count / total if total else 0.0

    st.markdown("##### Review progress")
    st.progress(progress, text=f"{reviewed_count} of {total} repair orders reviewed")
    if remaining:
        ordered = _sort_ro_groups(ro_groups, reviewed)
        next_ro = next(recid for recid, _ in ordered if recid not in reviewed)
        st.markdown(
            f'<div class="warranty-review-resume">'
            f"<strong>{remaining}</strong> RO{'s' if remaining != 1 else ''} left · "
            f'Resume at <span class="warranty-review-resume-ro">RO {next_ro}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.success("All repair orders reviewed for this import.")

    jump_col, filter_col = st.columns([1.2, 1.8])
    with jump_col:
        unreviewed = [recid for recid in recids if recid not in reviewed]
        jump_options = ["— Jump to RO —"] + [f"RO {recid}" for recid in unreviewed]
        picked = st.selectbox(
            "Resume here",
            jump_options,
            key="warranty_jump_ro_pick",
            label_visibility="collapsed",
        )
        if picked != jump_options[0]:
            st.session_state.warranty_jump_ro = picked.replace("RO ", "").strip()
        elif st.session_state.get("warranty_jump_ro") and st.session_state.warranty_jump_ro not in unreviewed:
            st.session_state.warranty_jump_ro = None
    with filter_col:
        st.radio(
            "Show",
            ["All (unreviewed first)", "Still to review", "Reviewed"],
            horizontal=True,
            key="warranty_review_filter",
            label_visibility="collapsed",
        )

    return reviewed


def _render_labor_rows(rows, custom_exclusions):
    active_exclusions = [row.exclusion for row in rows if row.exclusion]
    select_options = get_exclusion_select_options(custom_exclusions, active_exclusions)
    ro_groups = _group_rows_by_ro(rows)
    recids = [recid for recid, _ in ro_groups]
    _init_review_widgets(recids)

    multi_line_ros = sum(1 for _, ro_lines in ro_groups if len(ro_lines) > 1)

    st.markdown("##### Repair orders")
    st.caption(
        f"{len(ro_groups)} repair orders · {len(rows)} lines · "
        f"{multi_line_ros} ROs with multiple lines · "
        "Check **Reviewed** on each RO when done — progress saves with **Save to Reports**."
    )

    reviewed = _render_review_progress(ro_groups)

    filter_mode = st.session_state.get("warranty_review_filter", "All (unreviewed first)")
    if filter_mode == "Still to review":
        ro_groups = [(recid, lines) for recid, lines in ro_groups if recid not in reviewed]
    elif filter_mode == "Reviewed":
        ro_groups = [(recid, lines) for recid, lines in ro_groups if recid in reviewed]

    jump_ro = st.session_state.get("warranty_jump_ro")
    ro_groups = _sort_ro_groups(ro_groups, reviewed, jump_ro=jump_ro)

    if not ro_groups:
        st.info("No repair orders match this filter.")
        return

    for recid, ro_lines in ro_groups:
        _render_ro_card(
            recid,
            ro_lines,
            select_options,
            is_reviewed=recid in reviewed,
            is_focus=bool(jump_ro and recid == jump_ro),
        )


def render():
    _init_warranty_session()

    st.markdown(
        page_hero(
            "Warranty",
            "Analyze customer-pay repair orders for warranty effective labor rate.",
            tag="ELR Analysis",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<span class="legend-chip chip-calc">ELR = Labor Sale ÷ Tech Flagged Hours</span> '
        f'<span class="legend-chip chip-manual">Threshold {_money(ELR_THRESHOLD)} · '
        f'pick exclusions manually · blank = included in shop ELR</span>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("active_warranty_run_id"):
        run_label = st.session_state.get(
            "warranty_run_label",
            st.session_state.get("warranty_upload_name", "Saved analysis"),
        )
        st.info(f"Editing saved analysis: **{run_label}** — reopen anytime from **Reports**.")

    notice = st.session_state.pop("warranty_exclusion_notice", None)
    if notice:
        level, message = notice
        if level == "success":
            st.success(message)
        else:
            st.warning(message)

    if saved_label := st.session_state.pop("_warranty_saved_label", None):
        st.success(f"Warranty ELR analysis saved — find it in **Reports → Warranty ELR Analysis** ({saved_label}).")
        st.balloons()

    uploaded = st.file_uploader(
        "Upload warranty labor rate spreadsheet (.xlsx)",
        type=["xlsx"],
        help="Import customer-pay RO lines with labor sale and tech flagged hours.",
    )

    if uploaded:
        try:
            file_id = f"{uploaded.name}:{uploaded.size}"
            if st.session_state.get("warranty_upload_id") != file_id:
                uploaded.seek(0)
                st.session_state.warranty_sheet_names = list_sheet_names(uploaded)
                st.session_state.warranty_upload_id = file_id
                st.session_state.warranty_upload_name = uploaded.name
                st.session_state.warranty_run_label = uploaded.name

            sheet_names = st.session_state.get("warranty_sheet_names", ["Sheet1"])
            sheet = sheet_names[0] if len(sheet_names) == 1 else st.selectbox(
                "Worksheet",
                sheet_names,
                key="warranty_sheet_pick",
            )

            parse_id = f"{file_id}:{sheet}"
            if st.session_state.get("warranty_parsed_id") != parse_id:
                uploaded.seek(0)
                st.session_state.warranty_upload_bytes = uploaded.read()
                uploaded.seek(0)
                rows = parse_warranty_labor_report(uploaded, sheet_name=sheet)
                existing_by_index = None
                if st.session_state.get("active_warranty_run_id"):
                    existing_by_index = [r.exclusion for r in st.session_state.warranty_labor_rows]
                apply_import_exclusions(rows, existing_by_index=existing_by_index)
                _clear_exclusion_widgets()
                _clear_review_widgets()
                st.session_state.warranty_reviewed_ros = set()
                st.session_state.warranty_jump_ro = None
                for row in rows:
                    st.session_state[exclusion_widget_key(row)] = exclusion_widget_label(row.exclusion)
                st.session_state.warranty_labor_rows = rows
                st.session_state.warranty_parsed_id = parse_id
                st.session_state.warranty_sheet_name = sheet
                st.session_state.warranty_run_label = f"{uploaded.name} · {sheet}"
                load_msg = f"✓ Loaded {len(rows)} lines from {uploaded.name} · {sheet}"
                st.markdown(
                    status_banner(load_msg, "success"),
                    unsafe_allow_html=True,
                )
        except Exception as exc:
            st.markdown(status_banner(f"Import failed: {exc}", "warn"), unsafe_allow_html=True)

    rows = st.session_state.warranty_labor_rows
    if not rows:
        st.info(
            "Upload your warranty labor rate spreadsheet to analyze customer-pay effective labor rate. "
            "Each line can be tagged with an exclusion before calculating the shop ELR."
        )
        return

    custom_exclusions = st.session_state.warranty_custom_exclusions
    _render_custom_exclusions_editor()
    _render_labor_rows(rows, custom_exclusions)
    _sync_row_exclusions(rows, custom_exclusions)
    st.session_state.warranty_labor_rows = rows

    summary = summarize_rows(rows)

    st.markdown("---")
    st.markdown("##### Effective labor rate summary")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            stat_card("Shop ELR", _money(summary.effective_labor_rate), "cyan", "📊"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            stat_card("Labor Sale (included)", _money(summary.total_lbr_sale), "green", "💵"),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            stat_card("Tech Hours (included)", f"{summary.total_tech_hrs:.2f}", "orange", "⏱"),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            stat_card("Included Lines", f"{summary.included_rows}/{summary.total_rows}", "violet", "🧾"),
            unsafe_allow_html=True,
        )

    if summary.included_rows == 0:
        st.warning("All lines are excluded — include at least one line to calculate shop ELR.")
    elif summary.meets_threshold:
        st.markdown(
            status_banner(
                f"Shop ELR {_money(summary.effective_labor_rate)} meets the "
                f"{_money(ELR_THRESHOLD)} threshold.",
                "success",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            status_banner(
                f"Shop ELR {_money(summary.effective_labor_rate)} is below the "
                f"{_money(ELR_THRESHOLD)} threshold.",
                "warn",
            ),
            unsafe_allow_html=True,
        )

    st.caption(
        f"{summary.excluded_rows} excluded · "
        f"Formula: {_money(summary.total_lbr_sale)} labor sale ÷ {summary.total_tech_hrs:.2f} tech hours"
    )

    source_name = st.session_state.get("warranty_upload_name", "warranty_labor")
    sheet_name = st.session_state.get("warranty_sheet_name", "Sheet1")
    period_slug = source_name.rsplit(".", 1)[0].replace(" ", "_")

    st.markdown("##### Export PDF")
    exp1, exp2 = st.columns(2)
    with exp1:
        original_pdf = generate_warranty_original_pdf(rows, source_name, sheet_name)
        st.download_button(
            label="📄 Export original import PDF",
            data=original_pdf,
            file_name=f"WARRANTY_ELR_ORIGINAL_{period_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with exp2:
        analysis_pdf = generate_warranty_analysis_pdf(rows, summary, source_name, sheet_name)
        st.download_button(
            label="📄 Export analysis PDF (with exclusions)",
            data=analysis_pdf,
            file_name=f"WARRANTY_ELR_ANALYSIS_{period_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )

    st.markdown("##### Color-coded review")
    st.caption(
        f"Green ELR = {_money(ELR_THRESHOLD)} or above · Red ELR = below threshold · "
        "Grey strikethrough = excluded from shop ELR · Included = counted in shop ELR"
    )

    review_df = pd.DataFrame(rows_to_display_dicts(rows))
    st.dataframe(
        _style_labor_table(review_df),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.markdown("##### Save analysis")
    st.markdown(
        '<div class="glass-panel"><p style="color:#94a3b8;margin:0;">'
        "Saves this warranty ELR run to <strong>Reports → Warranty ELR Analysis</strong>. "
        "Reopen anytime to pick up exactly where you left off — exclusions, custom categories, and all.</p></div>",
        unsafe_allow_html=True,
    )

    if st.button("💾 Save to Reports", type="primary", use_container_width=True):
        reviewed_recids = sorted(
            _collect_reviewed_recids([str(row.recid) for row in rows])
        )
        run_id = save_warranty_labor_run(
            rows,
            source_name=source_name,
            sheet_name=sheet_name,
            custom_exclusions=custom_exclusions,
            upload_bytes=st.session_state.get("warranty_upload_bytes"),
            run_id=st.session_state.get("active_warranty_run_id"),
            reviewed_recids=reviewed_recids,
        )
        st.session_state.warranty_reviewed_ros = set(reviewed_recids)
        st.session_state.active_warranty_run_id = run_id
        st.session_state.warranty_run_label = st.session_state.get(
            "warranty_run_label",
            f"{source_name} · {sheet_name}",
        )
        st.session_state["_warranty_saved_label"] = st.session_state.warranty_run_label
        st.rerun()

"""Customer-pay labor rate grid for warranty rate submissions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui import page_hero, stat_card, status_banner
from lib.labor_rate_grid import (
    apply_amount_overrides,
    build_labor_grid,
    cells_vs_target,
    grid_to_dataframe_rows,
    grid_to_editor_dataframe,
    lookup_amount,
    overrides_from_editor_dataframe,
    parse_hour_range,
    summarize_hour_ranges,
)
from lib.labor_rate_pdf_export import build_labor_rate_grid_pdf
from lib.labor_rate_storage import save_labor_rate_run


def render():
    st.markdown(
        page_hero(
            "Labor Rate",
            "Set the hour range where most of your work falls and the ELR for that range. "
            "The grid builds itself for a Stellantis warranty labor rate request.",
            tag="Warranty Support",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("active_labor_rate_run_id"):
        st.info(
            f"Editing saved report: **{st.session_state.get('labor_rate_run_label', 'Labor rate grid')}** — "
            "changes update that Reports entry when you save again."
        )

    st.markdown("##### Strong labor range")
    st.caption(
        "This is your main customer-pay mix. Enter the hour band and the ELR you want "
        "that band to deliver — the grid is priced strongest here."
    )

    r1, r2 = st.columns([1.4, 1.1])
    with r1:
        hour_range = st.text_input(
            "Hour range",
            value="1.0-3.5",
            key="labor_hour_range",
            placeholder="e.g. 1.0-3.5",
            help="Where most of your customer-pay labor hours fall.",
        )
    with r2:
        range_elr = st.number_input(
            "ELR for this range ($/hr)",
            min_value=50.0,
            max_value=1000.0,
            value=295.0,
            step=1.0,
            key="labor_range_elr",
            help="Effective labor rate you want this hour range to average.",
        )

    st.markdown("##### Rest of the grid")
    o1, o2, o3 = st.columns([1.1, 1.1, 1.0])
    with o1:
        use_custom_base = st.checkbox(
            "Set a different ELR outside this range",
            value=False,
            key="labor_use_base",
        )
    with o2:
        base_elr_input = st.number_input(
            "ELR outside strong range ($/hr)",
            min_value=50.0,
            max_value=1000.0,
            value=round(float(range_elr) * 0.92, 2),
            step=1.0,
            key="labor_base_elr",
            disabled=not use_custom_base,
            help="Hours outside your strong range use this rate. Leave unchecked to auto-set ~8% below.",
        )
    with o3:
        max_hours = st.number_input(
            "Grid through (hrs)",
            min_value=4.0,
            max_value=24.0,
            value=16.0,
            step=0.5,
            key="labor_max_hours",
        )

    boost_pct = st.slider(
        "Extra lift at the center of the strong range",
        min_value=0,
        max_value=20,
        value=10,
        step=1,
        format="%d%%",
        key="labor_boost_pct",
        help="Peaks the dollars in the middle of your strong hour band (0–20%).",
    )

    st.markdown("##### Warranty rate request")
    st.caption(
        "Enter what you are paid today for warranty labor. We compare it to your "
        "strong-range ELR above to project the rate / labor-sale increase."
    )
    w1, w2 = st.columns([1.1, 1.1])
    with w1:
        current_warranty_rate = st.number_input(
            "Current warranty labor rate ($/hr)",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
            key="labor_current_warranty_rate",
            help="Your present OEM warranty labor rate per hour.",
        )
    with w2:
        warranty_hours = st.number_input(
            "Warranty labor hours (optional)",
            min_value=0.0,
            max_value=1_000_000.0,
            value=0.0,
            step=100.0,
            key="labor_warranty_hours",
            help="Annual or period warranty hours sold. Used to project total labor-sale $ increase.",
        )

    try:
        strong_lo, strong_hi = parse_hour_range(hour_range)
        generated = build_labor_grid(
            float(range_elr),
            strong_lo,
            strong_hi,
            base_elr=float(base_elr_input) if use_custom_base else None,
            max_hours=float(max_hours),
            strength_boost=float(boost_pct) / 100.0,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    # Clear manual edits when the generator inputs change
    grid_sig = (
        f"{float(range_elr):.2f}|{hour_range}|{float(base_elr_input):.2f}|"
        f"{bool(use_custom_base)}|{float(max_hours):.1f}|{int(boost_pct)}"
    )
    if st.session_state.get("_labor_grid_sig") != grid_sig:
        st.session_state._labor_grid_sig = grid_sig
        # Keep overrides restored from a saved report once; then track signature
        if not st.session_state.pop("_labor_keep_overrides", None):
            st.session_state.labor_grid_overrides = {}
            st.session_state.labor_editor_nonce = (
                int(st.session_state.get("labor_editor_nonce") or 0) + 1
            )

    if "labor_grid_overrides" not in st.session_state:
        st.session_state.labor_grid_overrides = {}
    if "labor_editor_nonce" not in st.session_state:
        st.session_state.labor_editor_nonce = 0

    overrides = {
        round(float(h), 1): float(a)
        for h, a in (st.session_state.labor_grid_overrides or {}).items()
    }
    result = apply_amount_overrides(generated, overrides)
    manual_count = len(overrides)

    proposed_rate = float(result.target_elr)
    current_rate = float(current_warranty_rate or 0.0)
    rate_increase_dollars = proposed_rate - current_rate if current_rate > 0 else None
    rate_increase_pct = (
        (rate_increase_dollars / current_rate) * 100.0
        if rate_increase_dollars is not None and current_rate > 0
        else None
    )
    hours_vol = float(warranty_hours or 0.0)
    sale_increase_dollars = (
        rate_increase_dollars * hours_vol
        if rate_increase_dollars is not None and hours_vol > 0
        else None
    )

    def _stat_with_sub(label: str, value: str, accent: str, icon: str, sub: str) -> None:
        card = stat_card(label, value, accent, icon)
        card = card.replace(
            "</div>\n        <div class=\"stat-glow\"></div>",
            f'</div>\n        <div class="stat-sub" style="margin-top:0.35rem;font-size:0.82rem;'
            f'opacity:0.85;">{sub}</div>\n'
            f'        <div class="stat-glow"></div>',
        )
        st.markdown(card, unsafe_allow_html=True)

    if current_rate > 0:
        wi1, wi2, wi3, wi4 = st.columns(4)
        with wi1:
            _stat_with_sub(
                "Current warranty",
                f"${current_rate:,.2f}",
                "violet",
                "W",
                "Today's warranty $/hr",
            )
        with wi2:
            _stat_with_sub(
                "Proposed (range ELR)",
                f"${proposed_rate:,.2f}",
                "cyan",
                "→",
                "Strong-range customer-pay ELR",
            )
        with wi3:
            if rate_increase_dollars is not None:
                _stat_with_sub(
                    "Rate increase",
                    f"{'+' if rate_increase_dollars >= 0 else ''}"
                    f"${rate_increase_dollars:,.2f}",
                    "green" if rate_increase_dollars >= 0 else "orange",
                    "↑" if rate_increase_dollars >= 0 else "↓",
                    "Per warranty labor hour",
                )
        with wi4:
            if rate_increase_pct is not None:
                _stat_with_sub(
                    "Rate increase %",
                    f"{'+' if rate_increase_pct >= 0 else ''}{rate_increase_pct:.1f}%",
                    "green" if rate_increase_pct >= 0 else "orange",
                    "%",
                    "vs current warranty rate",
                )
        if sale_increase_dollars is not None:
            st.markdown(
                status_banner(
                    f"Projected warranty labor sale increase: "
                    f"${sale_increase_dollars:,.0f} "
                    f"({'+' if (rate_increase_pct or 0) >= 0 else ''}"
                    f"{rate_increase_pct:.1f}%) on {hours_vol:,.0f} warranty hours "
                    f"at a ${rate_increase_dollars:,.2f}/hr rate lift "
                    f"(${current_rate:,.2f} → ${proposed_rate:,.2f}).",
                    "success" if sale_increase_dollars >= 0 else "warn",
                ),
                unsafe_allow_html=True,
            )
        elif rate_increase_dollars is not None:
            st.caption(
                "Add warranty labor hours above to also project total labor-sale $ increase."
            )

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            stat_card("Range ELR", f"${result.target_elr:,.2f}", "cyan", "$"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card(
                "Strong-band avg", f"${result.strong_avg_elr:,.2f}", "green", "◎"
            ),
            unsafe_allow_html=True,
        )
    with s3:
        _stat_with_sub(
            "Entire-grid avg",
            f"${result.overall_avg_elr:,.2f}",
            "orange",
            "∑",
            f"Avg ELR across all {result.cells_scored} cells",
        )
    with s4:
        st.markdown(
            stat_card("Outside ELR", f"${result.base_elr:,.2f}", "violet", "◇"),
            unsafe_allow_html=True,
        )

    e1, e2, e3, e4 = st.columns(4)

    with e1:
        _stat_with_sub(
            "Lowest ELR",
            f"${result.lowest_elr:,.2f}",
            "orange",
            "↓",
            f"At {result.lowest_elr_hours:.1f} hrs",
        )
    with e2:
        _stat_with_sub(
            "Highest ELR",
            f"${result.highest_elr:,.2f}",
            "green",
            "↑",
            f"At {result.highest_elr_hours:.1f} hrs",
        )
    with e3:
        _stat_with_sub(
            "% Above target",
            f"{result.pct_above_target:.1f}%",
            "cyan",
            "▲",
            f"Of {result.cells_scored} grid cells",
        )
        above_open = st.session_state.get("labor_elr_drill") == "above"
        if st.button(
            "Hide hours" if above_open else "Show hours above target",
            use_container_width=True,
            key="labor_drill_above",
            type="primary" if above_open else "secondary",
        ):
            st.session_state.labor_elr_drill = None if above_open else "above"
            st.rerun()
    with e4:
        _stat_with_sub(
            "% Below target",
            f"{result.pct_below_target:.1f}%",
            "violet",
            "▼",
            f"Of {result.cells_scored} grid cells",
        )
        below_open = st.session_state.get("labor_elr_drill") == "below"
        if st.button(
            "Hide hours" if below_open else "Show hours below target",
            use_container_width=True,
            key="labor_drill_below",
            type="primary" if below_open else "secondary",
        ):
            st.session_state.labor_elr_drill = None if below_open else "below"
            st.rerun()

    # Keep drill / reset buttons compact so they don't steal the stat-card look
    st.markdown(
        """
        <style>
        div.st-key-labor_drill_above button,
        div.st-key-labor_drill_below button,
        div.st-key-labor_drill_close button,
        div.st-key-labor_reset_overrides button {
            min-height: 2.5rem !important;
            padding: 0.45rem 0.85rem !important;
            white-space: normal !important;
            font-size: 0.85rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    drill = st.session_state.get("labor_elr_drill")
    if drill in ("above", "below"):
        drill_rows = cells_vs_target(result, drill)
        ranges = summarize_hour_ranges([float(r["hours"]) for r in drill_rows])
        title = "Above target ELR" if drill == "above" else "Below target ELR"
        tone = "success" if drill == "above" else "warn"
        st.markdown(
            status_banner(
                f"{title}: {len(drill_rows)} cell(s) · "
                f"hour ranges {', '.join(ranges) if ranges else '—'} · "
                f"target ${result.target_elr:,.2f}/hr (±$0.50 counts as at target).",
                tone,
            ),
            unsafe_allow_html=True,
        )
        if not drill_rows:
            st.info(f"No grid cells are {drill} your target ELR.")
        else:
            detail = pd.DataFrame(
                [
                    {
                        "Hours": f"{float(r['hours']):.1f}",
                        "Labor $": f"${float(r['amount']):,.2f}",
                        "ELR $/hr": f"${float(r['elr']):,.2f}",
                        "vs Target": (
                            f"+${float(r['vs_target']):,.2f}"
                            if float(r["vs_target"]) >= 0
                            else f"-${abs(float(r['vs_target'])):,.2f}"
                        ),
                        "Strong band": "Yes" if r["in_strong"] else "No",
                    }
                    for r in drill_rows
                ]
            )
            st.dataframe(
                detail,
                use_container_width=True,
                hide_index=True,
                height=min(420, 80 + 28 * len(drill_rows)),
            )
            c_close, _ = st.columns([1, 3])
            with c_close:
                if st.button("Close detail", key="labor_drill_close"):
                    st.session_state.labor_elr_drill = None
                    st.rerun()

    manual_note = (
        f" · {manual_count} manual cell edit(s) applied"
        if manual_count
        else ""
    )
    st.markdown(
        status_banner(
            f"For {result.strong_lo:.1f}–{result.strong_hi:.1f} hrs, grid averages "
            f"${result.strong_avg_elr:,.2f}/hr (you set ${result.target_elr:,.2f}). "
            f"Whole-grid avg ${result.overall_avg_elr:,.2f}/hr. "
            f"Outside that band uses ${result.base_elr:,.2f}/hr "
            f"(avg ${result.outside_avg_elr:,.2f}). "
            f"Lowest ELR ${result.lowest_elr:,.2f} at {result.lowest_elr_hours:.1f}h · "
            f"Highest ${result.highest_elr:,.2f} at {result.highest_elr_hours:.1f}h · "
            f"{result.pct_above_target:.1f}% of cells above target, "
            f"{result.pct_below_target:.1f}% below"
            + (
                f", {result.pct_at_target:.1f}% at target"
                if result.pct_at_target
                else ""
            )
            + manual_note
            + ". Use Show hours under % Above / % Below for each increment.",
            "success",
        ),
        unsafe_allow_html=True,
    )

    st.markdown("##### Customer-pay labor grid")
    st.caption(
        "Click any dollar cell to type a new amount. HOUR column stays locked. "
        "Stats at the top update from your edits. Manual cells are kept until you reset "
        "or change the generator inputs above."
    )

    editor_df = grid_to_editor_dataframe(result)
    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        disabled=["HOUR"],
        num_rows="fixed",
        key=f"labor_grid_editor_{int(st.session_state.labor_editor_nonce)}",
        column_config={
            "HOUR": st.column_config.NumberColumn("HOUR", format="%.1f"),
            "+.0": st.column_config.NumberColumn("+.0", format="%.2f", min_value=0.0),
            "+.1": st.column_config.NumberColumn("+.1", format="%.2f", min_value=0.0),
            "+.2": st.column_config.NumberColumn("+.2", format="%.2f", min_value=0.0),
            "+.3": st.column_config.NumberColumn("+.3", format="%.2f", min_value=0.0),
            "+.4": st.column_config.NumberColumn("+.4", format="%.2f", min_value=0.0),
        },
    )

    new_overrides = overrides_from_editor_dataframe(generated, edited_df)
    new_override_state = {f"{h:.1f}": float(a) for h, a in new_overrides.items()}
    old_override_state = {f"{h:.1f}": float(a) for h, a in overrides.items()}
    if new_override_state != old_override_state:
        st.session_state.labor_grid_overrides = new_override_state
        st.rerun()

    rset1, rset2 = st.columns([1, 3])
    with rset1:
        if st.button(
            "Reset manual edits",
            use_container_width=True,
            key="labor_reset_overrides",
            disabled=manual_count == 0,
        ):
            st.session_state.labor_grid_overrides = {}
            st.session_state.labor_editor_nonce = (
                int(st.session_state.get("labor_editor_nonce") or 0) + 1
            )
            st.rerun()
    with rset2:
        if manual_count:
            st.caption(
                f"{manual_count} cell(s) manually adjusted from the generated grid."
            )
        else:
            st.caption(
                "Read like your DMS: row = base hours, column = tenths. "
                "Example: 2.0 row + +.3 column = 2.3 hours."
            )

    grid_rows = grid_to_dataframe_rows(result)
    export_df = pd.DataFrame(
        [
            {
                "HOUR": r["HOUR"],
                "+.0": r["+.0"],
                "+.1": r["+.1"],
                "+.2": r["+.2"],
                "+.3": r["+.3"],
                "+.4": r["+.4"],
            }
            for r in grid_rows
        ]
    )

    with st.expander("Look up one labor time"):
        lookup_h = st.number_input(
            "Labor hours",
            min_value=0.0,
            max_value=float(max_hours),
            value=min(2.0, float(max_hours)),
            step=0.1,
            key="labor_lookup_h",
        )
        amt = lookup_amount(result, float(lookup_h))
        if amt is None:
            st.info("That time is outside this grid.")
        elif lookup_h <= 0:
            st.info("$0.00")
        else:
            elr_one = amt / float(lookup_h)
            st.success(
                f"{lookup_h:.1f} hrs → **${amt:,.2f}** customer-pay "
                f"(${elr_one:,.2f}/hr)"
            )

    csv_buf = export_df.to_csv(index=False).encode("utf-8")
    pdf_bytes = build_labor_rate_grid_pdf(
        title="Customer-Pay Labor Rate Grid",
        subtitle=(
            f"Strong range {result.strong_lo:.1f}–{result.strong_hi:.1f} hrs @ "
            f"${result.target_elr:,.2f}/hr · "
            f"Band avg ${result.strong_avg_elr:,.2f}/hr · "
            f"Outside ${result.base_elr:,.2f}/hr"
            + (f" · {manual_count} manual edits" if manual_count else "")
        ),
        grid_rows=grid_rows,
        summary=[
            ("Strong hour range", f"{result.strong_lo:.1f}–{result.strong_hi:.1f} hrs"),
            ("ELR for that range", f"${result.target_elr:,.2f}"),
            ("Strong-band avg ELR", f"${result.strong_avg_elr:,.2f}"),
            ("Grid avg ELR", f"${result.overall_avg_elr:,.2f}"),
            ("ELR outside range", f"${result.base_elr:,.2f}"),
            (
                "Lowest ELR",
                f"${result.lowest_elr:,.2f} at {result.lowest_elr_hours:.1f} hrs",
            ),
            (
                "Highest ELR",
                f"${result.highest_elr:,.2f} at {result.highest_elr_hours:.1f} hrs",
            ),
            ("% above target", f"{result.pct_above_target:.1f}%"),
            ("% below target", f"{result.pct_below_target:.1f}%"),
            *(
                [
                    ("Current warranty rate", f"${current_rate:,.2f}"),
                    (
                        "Proposed rate increase",
                        f"${rate_increase_dollars:,.2f}/hr "
                        f"({rate_increase_pct:+.1f}%)",
                    ),
                ]
                if rate_increase_dollars is not None and rate_increase_pct is not None
                else []
            ),
            *(
                [
                    (
                        "Projected labor sale increase",
                        f"${sale_increase_dollars:,.0f} on {hours_vol:,.0f} hrs",
                    )
                ]
                if sale_increase_dollars is not None
                else []
            ),
        ],
        strong_lo=result.strong_lo,
        strong_hi=result.strong_hi,
    )

    save_label = (
        "Update saved report"
        if st.session_state.get("active_labor_rate_run_id")
        else "Save to Reports"
    )
    default_name = (
        st.session_state.get("labor_rate_run_label")
        or f"{result.strong_lo:.1f}–{result.strong_hi:.1f}h @ "
        f"${result.target_elr:,.0f}/hr"
    )
    if "labor_grid_name" not in st.session_state:
        st.session_state.labor_grid_name = default_name

    grid_name = st.text_input(
        "Grid name",
        key="labor_grid_name",
        placeholder="e.g. Current DMS grid, Proposed $330 grid",
        help="Name this grid so you can tell it apart from your other saved grids in Reports.",
    )
    save_cols = st.columns(2 if st.session_state.get("active_labor_rate_run_id") else 1)
    with save_cols[0]:
        if st.button(
            f"💾 {save_label}",
            type="primary",
            use_container_width=True,
            key="labor_save_reports",
        ):
            chosen_name = str(grid_name or "").strip() or default_name
            run_id = save_labor_rate_run(
                result,
                hour_range=hour_range,
                boost_pct=int(boost_pct),
                use_custom_base=bool(use_custom_base),
                amount_overrides=dict(st.session_state.get("labor_grid_overrides") or {}),
                run_label=chosen_name,
                current_warranty_rate=current_rate,
                warranty_hours=hours_vol,
                run_id=st.session_state.get("active_labor_rate_run_id"),
            )
            st.session_state.active_labor_rate_run_id = run_id
            st.session_state.labor_rate_run_label = chosen_name
            st.session_state.labor_grid_name = chosen_name
            st.session_state["_labor_rate_saved_label"] = chosen_name
            st.rerun()
    if st.session_state.get("active_labor_rate_run_id"):
        with save_cols[1]:
            if st.button(
                "💾 Save as new grid",
                use_container_width=True,
                key="labor_save_as_new",
                help="Keep the current saved grid and also save this as a separate named report.",
            ):
                chosen_name = str(grid_name or "").strip() or default_name
                run_id = save_labor_rate_run(
                    result,
                    hour_range=hour_range,
                    boost_pct=int(boost_pct),
                    use_custom_base=bool(use_custom_base),
                    amount_overrides=dict(
                        st.session_state.get("labor_grid_overrides") or {}
                    ),
                    run_label=chosen_name,
                    current_warranty_rate=current_rate,
                    warranty_hours=hours_vol,
                    run_id=None,
                )
                st.session_state.active_labor_rate_run_id = run_id
                st.session_state.labor_rate_run_label = chosen_name
                st.session_state.labor_grid_name = chosen_name
                st.session_state["_labor_rate_saved_label"] = chosen_name
                st.rerun()

    saved_flash = st.session_state.pop("_labor_rate_saved_label", None)
    if saved_flash:
        st.success(
            f"Labor rate grid **{saved_flash}** saved — find it in "
            "**Reports → Labor Rate Grids**."
        )

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "Download CSV",
            data=csv_buf,
            file_name="customer-pay-labor-grid.csv",
            mime="text/csv",
            use_container_width=True,
            key="labor_csv",
        )
    with d2:
        st.download_button(
            "Export PDF",
            data=pdf_bytes,
            file_name="customer-pay-labor-grid.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="labor_pdf",
        )

    st.markdown(
        '<div class="glass-panel"><p style="color:#94a3b8;margin:0;">'
        "Save stores this customer-pay grid (inputs + dollars) under "
        "<strong>Reports → Labor Rate Grids</strong> so you can reopen it for your "
        "Stellantis warranty rate submission.</p></div>",
        unsafe_allow_html=True,
    )

"""Customer-pay labor rate grid for warranty rate submissions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui import page_hero, stat_card, status_banner
from lib.labor_rate_grid import (
    build_labor_grid,
    cells_vs_target,
    grid_to_dataframe_rows,
    lookup_amount,
    parse_hour_range,
    summarize_hour_ranges,
)
from lib.labor_rate_pdf_export import build_labor_rate_grid_pdf


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

    try:
        strong_lo, strong_hi = parse_hour_range(hour_range)
        result = build_labor_grid(
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

    s1, s2, s3, s4 = st.columns(4)
    cards = [
        ("Range ELR", f"${result.target_elr:,.2f}", "cyan", "$"),
        ("Strong-band avg", f"${result.strong_avg_elr:,.2f}", "green", "◎"),
        ("Strong band", f"{result.strong_lo:.1f}–{result.strong_hi:.1f}h", "orange", "⏱"),
        ("Outside ELR", f"${result.base_elr:,.2f}", "violet", "◇"),
    ]
    for col, (label, value, accent, icon) in zip([s1, s2, s3, s4], cards):
        with col:
            st.markdown(stat_card(label, value, accent, icon), unsafe_allow_html=True)

    e1, e2, e3, e4 = st.columns(4)

    def _stat_with_sub(label: str, value: str, accent: str, icon: str, sub: str) -> None:
        card = stat_card(label, value, accent, icon)
        card = card.replace(
            "</div>\n        <div class=\"stat-glow\"></div>",
            f'</div>\n        <div class="stat-sub" style="margin-top:0.35rem;font-size:0.82rem;'
            f'opacity:0.85;">{sub}</div>\n'
            f'        <div class="stat-glow"></div>',
        )
        st.markdown(card, unsafe_allow_html=True)

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

    # Keep drill buttons compact so they don't steal the stat-card look
    st.markdown(
        """
        <style>
        div.st-key-labor_drill_above button,
        div.st-key-labor_drill_below button,
        div.st-key-labor_drill_close button {
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

    st.markdown(
        status_banner(
            f"For {result.strong_lo:.1f}–{result.strong_hi:.1f} hrs, grid averages "
            f"${result.strong_avg_elr:,.2f}/hr (you set ${result.target_elr:,.2f}). "
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
            + ". Use Show hours under % Above / % Below for each increment. "
            "Highlighted rows are your strong range.",
            "success",
        ),
        unsafe_allow_html=True,
    )

    grid_rows = grid_to_dataframe_rows(result)
    display_rows = [
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
    df = pd.DataFrame(display_rows)

    def _style_strong(row):
        hour = str(row["HOUR"])
        strong = next(
            (gr.get("_strong") for gr in grid_rows if gr.get("HOUR") == hour),
            False,
        )
        if strong:
            return ["background-color: rgba(8, 145, 178, 0.18)"] * len(row)
        return [""] * len(row)

    try:
        st.dataframe(
            df.style.apply(_style_strong, axis=1),
            use_container_width=True,
            hide_index=True,
            height=520,
        )
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=520)

    st.caption(
        "Read like your DMS: row = base hours, column = tenths. "
        "Example: 2.0 row + +.3 column = 2.3 hours → dollar amount in that cell."
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

    csv_buf = df.to_csv(index=False).encode("utf-8")
    pdf_bytes = build_labor_rate_grid_pdf(
        title="Customer-Pay Labor Rate Grid",
        subtitle=(
            f"Strong range {result.strong_lo:.1f}–{result.strong_hi:.1f} hrs @ "
            f"${result.target_elr:,.2f}/hr · "
            f"Band avg ${result.strong_avg_elr:,.2f}/hr · "
            f"Outside ${result.base_elr:,.2f}/hr"
        ),
        grid_rows=grid_rows,
        summary=[
            ("Strong hour range", f"{result.strong_lo:.1f}–{result.strong_hi:.1f} hrs"),
            ("ELR for that range", f"${result.target_elr:,.2f}"),
            ("Strong-band avg ELR", f"${result.strong_avg_elr:,.2f}"),
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
        ],
        strong_lo=result.strong_lo,
        strong_hi=result.strong_hi,
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
            type="primary",
        )

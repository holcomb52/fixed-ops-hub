"""Customer-pay labor rate grid for warranty rate submissions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui import page_hero, stat_card, status_banner
from lib.labor_rate_grid import (
    build_labor_grid,
    grid_to_dataframe_rows,
    lookup_amount,
    parse_hour_range,
)
from lib.labor_rate_pdf_export import build_labor_rate_grid_pdf


def render():
    st.markdown(
        page_hero(
            "Labor Rate",
            "Build a customer-pay labor grid from your target ELR and the hour range "
            "where most of your work falls — ready for a Stellantis warranty rate request.",
            tag="Warranty Support",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    st.caption(
        "Enter target Effective Labor Rate and the hour band that carries most of your "
        "customer-pay mix. The grid is priced strongest in that band so you do not have "
        "to build the matrix by hand."
    )

    i1, i2, i3 = st.columns([1.1, 1.3, 1.0])
    with i1:
        target_elr = st.number_input(
            "Target ELR ($/hr)",
            min_value=50.0,
            max_value=1000.0,
            value=295.0,
            step=1.0,
            key="labor_target_elr",
            help="Customer-pay effective labor rate you want the strong hour band to deliver.",
        )
    with i2:
        hour_range = st.text_input(
            "Strong hour range (most of your work)",
            value="1.0-3.5",
            key="labor_hour_range",
            placeholder="e.g. 1.0-3.5",
            help="Jobs in this hour band are priced strongest to carry your target ELR.",
        )
    with i3:
        max_hours = st.number_input(
            "Grid through (hrs)",
            min_value=4.0,
            max_value=24.0,
            value=16.0,
            step=0.5,
            key="labor_max_hours",
        )

    boost_pct = st.slider(
        "How strong in that hour range",
        min_value=0,
        max_value=20,
        value=10,
        step=1,
        format="%d%%",
        key="labor_boost_pct",
        help="Extra lift at the center of your strong band (0–20%).",
    )

    try:
        strong_lo, strong_hi = parse_hour_range(hour_range)
        result = build_labor_grid(
            float(target_elr),
            strong_lo,
            strong_hi,
            max_hours=float(max_hours),
            strength_boost=float(boost_pct) / 100.0,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    s1, s2, s3, s4 = st.columns(4)
    cards = [
        ("Target ELR", f"${result.target_elr:,.2f}", "cyan", "$"),
        ("Strong-band ELR", f"${result.strong_avg_elr:,.2f}", "green", "◎"),
        ("Strong band", f"{result.strong_lo:.1f}–{result.strong_hi:.1f}h", "orange", "⏱"),
        (
            "Band ELR range",
            f"${result.strong_min_elr:,.0f}–${result.strong_max_elr:,.0f}",
            "violet",
            "↕",
        ),
    ]
    for col, (label, value, accent, icon) in zip([s1, s2, s3, s4], cards):
        with col:
            st.markdown(stat_card(label, value, accent, icon), unsafe_allow_html=True)

    st.markdown(
        status_banner(
            f"Grid is strongest from {result.strong_lo:.1f} to {result.strong_hi:.1f} hours. "
            f"Average ELR in that band: ${result.strong_avg_elr:,.2f}/hr "
            f"(target ${result.target_elr:,.2f}). Highlighted rows are in your strong range.",
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
            f"Target ELR ${result.target_elr:,.2f}/hr · "
            f"Strong band {result.strong_lo:.1f}–{result.strong_hi:.1f} hrs · "
            f"Band avg ${result.strong_avg_elr:,.2f}/hr"
        ),
        grid_rows=grid_rows,
        summary=[
            ("Target ELR", f"${result.target_elr:,.2f}"),
            ("Strong-band avg ELR", f"${result.strong_avg_elr:,.2f}"),
            ("Strong band", f"{result.strong_lo:.1f}–{result.strong_hi:.1f} hrs"),
            (
                "Band ELR min–max",
                f"${result.strong_min_elr:,.2f}–${result.strong_max_elr:,.2f}",
            ),
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

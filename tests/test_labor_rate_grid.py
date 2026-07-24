"""Labor rate grid builder tests."""

from __future__ import annotations

from lib.labor_rate_grid import (
    apply_amount_overrides,
    build_labor_grid,
    grid_to_dataframe_rows,
    grid_to_editor_dataframe,
    lookup_amount,
    overrides_from_editor_dataframe,
    parse_hour_range,
)
from lib.labor_rate_pdf_export import build_labor_rate_grid_pdf


def test_parse_hour_range():
    assert parse_hour_range("1.0-3.5") == (1.0, 3.5)
    assert parse_hour_range("2 to 4") == (2.0, 4.0)
    assert parse_hour_range("3.5 – 1.0") == (1.0, 3.5)


def test_strong_band_hits_target_elr():
    result = build_labor_grid(300.0, 1.0, 3.5, max_hours=12.0, strength_boost=0.10)
    assert abs(result.strong_avg_elr - 300.0) < 2.0  # rounding tolerance
    assert result.strong_max_elr >= result.strong_min_elr
    assert abs(result.outside_avg_elr - result.base_elr) < 2.0
    # Center of band should be at least as strong as a short fringe cell outside
    amt_2 = lookup_amount(result, 2.0)
    amt_8 = lookup_amount(result, 8.0)
    assert amt_2 is not None and amt_8 is not None
    assert (amt_2 / 2.0) >= (amt_8 / 8.0) - 5.0


def test_custom_base_elr_outside_range():
    result = build_labor_grid(
        320.0, 1.0, 2.5, base_elr=280.0, max_hours=10.0, strength_boost=0.05
    )
    assert abs(result.strong_avg_elr - 320.0) < 2.0
    assert abs(result.base_elr - 280.0) < 0.01
    assert abs(result.outside_avg_elr - 280.0) < 2.0


def test_elr_extremes_and_above_below_share():
    result = build_labor_grid(330.0, 2.0, 4.0, base_elr=320.0, max_hours=8.0)
    assert result.lowest_elr > 0
    assert result.highest_elr >= result.lowest_elr
    assert result.lowest_elr_hours > 0
    assert result.highest_elr_hours > 0
    assert result.cells_scored > 0
    total_pct = (
        result.pct_above_target + result.pct_below_target + result.pct_at_target
    )
    assert abs(total_pct - 100.0) < 0.2


def test_cells_vs_target_drilldown():
    from lib.labor_rate_grid import cells_vs_target, summarize_hour_ranges

    result = build_labor_grid(330.0, 2.0, 4.0, base_elr=320.0, max_hours=8.0)
    above = cells_vs_target(result, "above")
    below = cells_vs_target(result, "below")
    assert above or below
    for row in above:
        assert float(row["elr"]) > 330.0
    for row in below:
        assert float(row["elr"]) < 330.0
    ranges = summarize_hour_ranges([1.0, 1.1, 1.2, 3.0])
    assert "1.0–1.2" in ranges
    assert "3.0" in ranges


def test_grid_layout_and_pdf():
    result = build_labor_grid(295.0, 1.5, 4.0, max_hours=10.0)
    rows = grid_to_dataframe_rows(result)
    assert rows[0]["HOUR"] == "0.0"
    assert "+.0" in rows[0] and "+.4" in rows[0]
    assert lookup_amount(result, 0.0) == 0.0
    assert lookup_amount(result, 1.3) is not None

    pdf = build_labor_rate_grid_pdf(
        title="Test Labor Grid",
        grid_rows=rows,
        summary=[("Target ELR", "$295.00")],
        strong_lo=1.5,
        strong_hi=4.0,
    )
    assert pdf.startswith(b"%PDF")


def test_manual_amount_overrides_recompute_elr():
    base = build_labor_grid(300.0, 1.0, 3.5, max_hours=6.0, strength_boost=0.10)
    original = lookup_amount(base, 2.0)
    assert original is not None

    overridden = apply_amount_overrides(base, {2.0: 900.0})
    assert lookup_amount(overridden, 2.0) == 900.0
    assert abs(lookup_amount(overridden, 2.0) / 2.0 - 450.0) < 0.01
    # Unedited cells stay the same
    assert lookup_amount(overridden, 1.5) == lookup_amount(base, 1.5)
    assert overridden.cells_scored == base.cells_scored


def test_editor_dataframe_roundtrip_diff():
    base = build_labor_grid(295.0, 1.0, 3.0, max_hours=5.0)
    editor = grid_to_editor_dataframe(base)
    assert "HOUR" in editor.columns and "+.0" in editor.columns

    edited = editor.copy()
    # Find the 2.0 hour row and change +.0 cell
    mask = (edited["HOUR"] - 2.0).abs() < 1e-9
    assert mask.any()
    edited.loc[mask, "+.0"] = 777.77

    overrides = overrides_from_editor_dataframe(base, edited)
    assert 2.0 in overrides
    assert abs(overrides[2.0] - 777.77) < 0.01
    # No false positives when unchanged
    assert overrides_from_editor_dataframe(base, editor) == {}

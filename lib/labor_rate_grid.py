"""Customer-pay labor rate grid builder for warranty ELR submissions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

TENTHS = (0.0, 0.1, 0.2, 0.3, 0.4)
TENTH_LABELS = ("+.0", "+.1", "+.2", "+.3", "+.4")
# Cells within this $/hr of target count as "at target"
ELR_TARGET_TOLERANCE = 0.50


@dataclass(frozen=True)
class LaborGridResult:
    # ELR applied to the strong hour range (primary input)
    target_elr: float
    base_elr: float
    strong_lo: float
    strong_hi: float
    max_hours: float
    strength_boost: float
    # Display rows: base hour -> amounts for +.0 .. +.4
    matrix: Dict[float, Dict[float, float]]
    # Flat list of (hours, amount, elr, in_strong)
    cells: List[Dict[str, float | bool]]
    strong_avg_elr: float
    strong_min_elr: float
    strong_max_elr: float
    overall_avg_elr: float
    outside_avg_elr: float
    scale_factor: float
    # Grid-wide ELR extremes + share vs target
    lowest_elr: float
    lowest_elr_hours: float
    highest_elr: float
    highest_elr_hours: float
    pct_above_target: float
    pct_below_target: float
    pct_at_target: float
    cells_scored: int


def parse_hour_range(text: str) -> Tuple[float, float]:
    """Parse ranges like '1.0-3.5', '1 to 4', '2.5 – 5'."""
    raw = str(text or "").strip().lower()
    if not raw:
        raise ValueError("Enter an hour range, e.g. 1.0-3.5")
    raw = raw.replace("–", "-").replace("—", "-").replace("to", "-")
    parts = re.split(r"\s*-\s*", raw)
    if len(parts) != 2:
        raise ValueError("Use a range like 1.0-3.5")
    try:
        lo = float(parts[0].strip())
        hi = float(parts[1].strip())
    except ValueError as exc:
        raise ValueError("Hour range must be numbers, e.g. 1.0-3.5") from exc
    if lo < 0 or hi < 0:
        raise ValueError("Hours cannot be negative.")
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        hi = lo + 0.5
    return round(lo, 1), round(hi, 1)


def _round_money(value: float) -> float:
    """Dealer grids usually land on whole dollars or half-dollars."""
    if value <= 0:
        return 0.0
    return round(value * 2.0) / 2.0


def _inside_strength(hours: float, strong_lo: float, strong_hi: float, boost: float) -> float:
    """1.0 at band edges → (1 + boost) at center."""
    mid = (strong_lo + strong_hi) / 2.0
    half = max((strong_hi - strong_lo) / 2.0, 0.25)
    proximity = 1.0 - min(abs(hours - mid) / half, 1.0)
    return 1.0 + max(0.0, boost) * proximity


def _outside_fade(hours: float, strong_lo: float, strong_hi: float) -> float:
    """Gentle taper away from the strong band (keeps outside near base ELR)."""
    if hours < strong_lo:
        gap = strong_lo - hours
        return max(0.92, 1.0 - 0.02 * gap)
    gap = hours - strong_hi
    return max(0.94, 1.0 - 0.015 * gap)


def _iter_hours(max_hours: float) -> List[float]:
    """All billable times on the classic +.0 … +.4 grid through max_hours."""
    max_h = max(0.5, float(max_hours))
    out: List[float] = []
    base = 0.0
    while base <= max_h + 1e-9:
        for tenth in TENTHS:
            hours = round(base + tenth, 1)
            if hours <= max_h + 1e-9:
                out.append(hours)
        base = round(base + 0.5, 1)
    return out


def build_labor_grid(
    target_elr: float,
    strong_lo: float,
    strong_hi: float,
    *,
    base_elr: Optional[float] = None,
    max_hours: float = 16.0,
    strength_boost: float = 0.10,
) -> LaborGridResult:
    """
    Build a customer-pay labor matrix.

    `target_elr` is the ELR for the strong hour range (your main mix).
    `base_elr` is the ELR for hours outside that range (defaults slightly below).
    Strong-band cells are scaled so their average ELR matches `target_elr`.
    """
    range_elr = float(target_elr)
    if range_elr <= 0:
        raise ValueError("ELR for the strong hour range must be greater than zero.")
    lo = float(strong_lo)
    hi = float(strong_hi)
    if hi < lo:
        lo, hi = hi, lo
    if base_elr is None or float(base_elr) <= 0:
        base = round(range_elr * 0.92, 2)
    else:
        base = float(base_elr)
    boost = max(0.0, min(0.25, float(strength_boost)))
    max_h = max(hi + 1.0, float(max_hours))

    hours_list = _iter_hours(max_h)
    raw_amounts: Dict[float, float] = {}
    for hours in hours_list:
        if hours <= 0:
            raw_amounts[hours] = 0.0
            continue
        in_strong = lo - 1e-9 <= hours <= hi + 1e-9
        if in_strong:
            raw_amounts[hours] = (
                hours * range_elr * _inside_strength(hours, lo, hi, boost)
            )
        else:
            raw_amounts[hours] = hours * base * _outside_fade(hours, lo, hi)

    # Scale strong band so average ELR == range_elr
    strong_pairs = [
        (h, raw_amounts[h])
        for h in hours_list
        if h > 0 and lo - 1e-9 <= h <= hi + 1e-9
    ]
    if not strong_pairs:
        strong_pairs = [(h, raw_amounts[h]) for h in hours_list if h > 0][:10]

    strong_elrs = [amt / h for h, amt in strong_pairs if h > 0]
    avg_raw = sum(strong_elrs) / len(strong_elrs) if strong_elrs else range_elr
    strong_scale = range_elr / avg_raw if avg_raw else 1.0

    # Scale outside band so average ELR == base
    outside_pairs = [
        (h, raw_amounts[h])
        for h in hours_list
        if h > 0 and not (lo - 1e-9 <= h <= hi + 1e-9)
    ]
    outside_elrs = [amt / h for h, amt in outside_pairs if h > 0]
    avg_out = sum(outside_elrs) / len(outside_elrs) if outside_elrs else base
    outside_scale = base / avg_out if avg_out else 1.0

    cells: List[Dict[str, float | bool]] = []
    matrix: Dict[float, Dict[float, float]] = {}
    for hours in hours_list:
        in_strong = bool(hours > 0 and lo - 1e-9 <= hours <= hi + 1e-9)
        scale = strong_scale if in_strong or hours <= 0 else outside_scale
        amount = _round_money(raw_amounts[hours] * scale)
        tenths_int = int(round(hours * 10))
        base_tenths = (tenths_int // 5) * 5
        tenth_tenths = tenths_int - base_tenths
        base_row = round(base_tenths / 10.0, 1)
        tenth_col = round(tenth_tenths / 10.0, 1)

        matrix.setdefault(base_row, {})
        matrix[base_row][tenth_col] = amount
        cell_elr = (amount / hours) if hours > 0 else 0.0
        cells.append(
            {
                "hours": hours,
                "amount": amount,
                "elr": round(cell_elr, 2),
                "in_strong": in_strong,
            }
        )

    return _finalize_labor_grid_result(
        range_elr=range_elr,
        base=base,
        lo=lo,
        hi=hi,
        max_h=max_h,
        boost=boost,
        matrix=matrix,
        cells=cells,
        scale_factor=strong_scale,
    )


def _finalize_labor_grid_result(
    *,
    range_elr: float,
    base: float,
    lo: float,
    hi: float,
    max_h: float,
    boost: float,
    matrix: Dict[float, Dict[float, float]],
    cells: List[Dict[str, float | bool]],
    scale_factor: float,
) -> LaborGridResult:
    strong_cells = [c for c in cells if c["in_strong"] and float(c["hours"]) > 0]
    strong_elr_vals = [float(c["elr"]) for c in strong_cells]
    outside_cells = [
        c for c in cells if not c["in_strong"] and float(c["hours"]) > 0
    ]
    outside_elr_vals = [float(c["elr"]) for c in outside_cells]
    scored = [c for c in cells if float(c["hours"]) > 0]
    all_elr_vals = [float(c["elr"]) for c in scored]

    if scored:
        lowest = min(scored, key=lambda c: (float(c["elr"]), float(c["hours"])))
        highest = max(scored, key=lambda c: (float(c["elr"]), -float(c["hours"])))
        lowest_elr = float(lowest["elr"])
        lowest_hours = float(lowest["hours"])
        highest_elr = float(highest["elr"])
        highest_hours = float(highest["hours"])
        tol = ELR_TARGET_TOLERANCE
        above = sum(1 for c in scored if float(c["elr"]) > range_elr + tol)
        below = sum(1 for c in scored if float(c["elr"]) < range_elr - tol)
        at = len(scored) - above - below
        pct_above = round(100.0 * above / len(scored), 1)
        pct_below = round(100.0 * below / len(scored), 1)
        pct_at = round(100.0 * at / len(scored), 1)
    else:
        lowest_elr = highest_elr = 0.0
        lowest_hours = highest_hours = 0.0
        pct_above = pct_below = pct_at = 0.0

    return LaborGridResult(
        target_elr=range_elr,
        base_elr=base,
        strong_lo=lo,
        strong_hi=hi,
        max_hours=max_h,
        strength_boost=boost,
        matrix=matrix,
        cells=cells,
        strong_avg_elr=round(sum(strong_elr_vals) / len(strong_elr_vals), 2)
        if strong_elr_vals
        else 0.0,
        strong_min_elr=round(min(strong_elr_vals), 2) if strong_elr_vals else 0.0,
        strong_max_elr=round(max(strong_elr_vals), 2) if strong_elr_vals else 0.0,
        overall_avg_elr=round(sum(all_elr_vals) / len(all_elr_vals), 2)
        if all_elr_vals
        else 0.0,
        outside_avg_elr=round(sum(outside_elr_vals) / len(outside_elr_vals), 2)
        if outside_elr_vals
        else 0.0,
        scale_factor=round(float(scale_factor), 4),
        lowest_elr=round(lowest_elr, 2),
        lowest_elr_hours=lowest_hours,
        highest_elr=round(highest_elr, 2),
        highest_elr_hours=highest_hours,
        pct_above_target=pct_above,
        pct_below_target=pct_below,
        pct_at_target=pct_at,
        cells_scored=len(scored),
    )


def apply_amount_overrides(
    result: LaborGridResult,
    overrides: Dict[float, float] | None,
) -> LaborGridResult:
    """
    Replace selected cell dollar amounts and recalculate ELRs / summary stats.

    overrides maps labor hours (e.g. 2.3) -> dollar amount.
    """
    if not overrides:
        return result

    clean: Dict[float, float] = {}
    for raw_h, raw_amt in overrides.items():
        try:
            hours = round(float(raw_h), 1)
            amount = float(raw_amt)
        except (TypeError, ValueError):
            continue
        if hours < 0 or amount < 0:
            continue
        clean[hours] = round(amount, 2)

    if not clean:
        return result

    matrix: Dict[float, Dict[float, float]] = {
        base: dict(cols) for base, cols in result.matrix.items()
    }
    cells: List[Dict[str, float | bool]] = []
    for cell in result.cells:
        hours = float(cell["hours"])
        amount = float(clean.get(hours, cell["amount"]))
        tenths_int = int(round(hours * 10))
        base_tenths = (tenths_int // 5) * 5
        tenth_tenths = tenths_int - base_tenths
        base_row = round(base_tenths / 10.0, 1)
        tenth_col = round(tenth_tenths / 10.0, 1)
        matrix.setdefault(base_row, {})
        matrix[base_row][tenth_col] = amount
        cell_elr = (amount / hours) if hours > 0 else 0.0
        cells.append(
            {
                "hours": hours,
                "amount": amount,
                "elr": round(cell_elr, 2),
                "in_strong": bool(cell.get("in_strong")),
            }
        )

    return _finalize_labor_grid_result(
        range_elr=float(result.target_elr),
        base=float(result.base_elr),
        lo=float(result.strong_lo),
        hi=float(result.strong_hi),
        max_h=float(result.max_hours),
        boost=float(result.strength_boost),
        matrix=matrix,
        cells=cells,
        scale_factor=float(result.scale_factor),
    )


def grid_to_editor_dataframe(result: LaborGridResult):
    """Numeric dataframe for st.data_editor (HOUR + +.0…+.4)."""
    import pandas as pd

    rows = []
    for base in sorted(result.matrix.keys()):
        row: Dict[str, float] = {"HOUR": float(base)}
        for tenth, label in zip(TENTHS, TENTH_LABELS):
            amount = result.matrix.get(base, {}).get(tenth)
            row[label] = float(amount) if amount is not None else None
        rows.append(row)
    return pd.DataFrame(rows)


def overrides_from_editor_dataframe(
    base_result: LaborGridResult,
    edited_df,
) -> Dict[float, float]:
    """Diff edited dollars vs generated grid → manual override map."""
    overrides: Dict[float, float] = {}
    if edited_df is None:
        return overrides
    for _, row in edited_df.iterrows():
        try:
            base = round(float(row["HOUR"]), 1)
        except (TypeError, ValueError, KeyError):
            continue
        for tenth, label in zip(TENTHS, TENTH_LABELS):
            hours = round(base + tenth, 1)
            raw = row.get(label)
            if raw is None or (isinstance(raw, float) and raw != raw):  # NaN
                continue
            try:
                amount = round(float(raw), 2)
            except (TypeError, ValueError):
                continue
            generated = lookup_amount(base_result, hours)
            if generated is None:
                continue
            if abs(amount - float(generated)) > 0.009:
                overrides[hours] = amount
    return overrides


def grid_to_dataframe_rows(result: LaborGridResult) -> List[Dict[str, str]]:
    """Rows for a Streamlit/CSV table matching the classic HOUR / +.0…+.4 layout."""
    rows: List[Dict[str, str]] = []
    for base in sorted(result.matrix.keys()):
        row: Dict[str, str] = {"HOUR": f"{base:.1f}"}
        for tenth, label in zip(TENTHS, TENTH_LABELS):
            amount = result.matrix.get(base, {}).get(tenth)
            row[label] = f"{amount:.2f}" if amount is not None else ""
        row_hours = [round(base + t, 1) for t in TENTHS]
        row["_strong"] = any(
            result.strong_lo - 1e-9 <= h <= result.strong_hi + 1e-9
            for h in row_hours
            if h > 0
        )
        rows.append(row)
    return rows


def lookup_amount(result: LaborGridResult, hours: float) -> Optional[float]:
    h = round(float(hours), 1)
    for cell in result.cells:
        if abs(float(cell["hours"]) - h) < 1e-9:
            return float(cell["amount"])
    return None


def classify_cell_vs_target(
    elr: float,
    target_elr: float,
    *,
    tolerance: float = ELR_TARGET_TOLERANCE,
) -> str:
    """Return 'above' | 'below' | 'at' relative to target ELR."""
    if elr > target_elr + tolerance:
        return "above"
    if elr < target_elr - tolerance:
        return "below"
    return "at"


def cells_vs_target(
    result: LaborGridResult,
    category: str,
    *,
    tolerance: float = ELR_TARGET_TOLERANCE,
) -> List[Dict[str, float | bool | str]]:
    """
    Cells in the grid that are above / below / at the range target ELR.

    category: 'above' | 'below' | 'at'
    """
    cat = str(category or "").strip().lower()
    if cat not in {"above", "below", "at"}:
        return []
    target = float(result.target_elr)
    rows: List[Dict[str, float | bool | str]] = []
    for cell in result.cells:
        hours = float(cell["hours"])
        if hours <= 0:
            continue
        elr = float(cell["elr"])
        bucket = classify_cell_vs_target(elr, target, tolerance=tolerance)
        if bucket != cat:
            continue
        rows.append(
            {
                "hours": hours,
                "amount": float(cell["amount"]),
                "elr": elr,
                "vs_target": round(elr - target, 2),
                "in_strong": bool(cell.get("in_strong")),
                "category": bucket,
            }
        )
    rows.sort(key=lambda r: float(r["hours"]))
    return rows


def summarize_hour_ranges(hours_list: List[float]) -> List[str]:
    """Collapse sorted hour points into readable ranges, e.g. 2.0–3.4, 5.1."""
    if not hours_list:
        return []
    ordered = sorted({round(float(h), 1) for h in hours_list})
    ranges: List[str] = []
    start = prev = ordered[0]
    for h in ordered[1:]:
        if abs(h - prev - 0.1) < 1e-9:
            prev = h
            continue
        ranges.append(f"{start:.1f}" if start == prev else f"{start:.1f}–{prev:.1f}")
        start = prev = h
    ranges.append(f"{start:.1f}" if start == prev else f"{start:.1f}–{prev:.1f}")
    return ranges

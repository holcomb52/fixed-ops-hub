"""Technician supplemental bonus — CP hrs/RO × closing % matrix."""

from __future__ import annotations

from typing import Optional, Tuple

MIN_HRS_PER_RO = 2.25
MIN_CLOSING_PCT = 40.0

# Rows: hrs/RO bands (min inclusive). Columns: closing % bands (min inclusive).
# Values are bi-weekly bonus dollars.
SUPPLEMENTAL_BONUS_MATRIX = [
    ((2.25, 2.74), (40.0, 59.99), 75, "Tier 2"),
    ((2.25, 2.74), (60.0, 74.99), 100, "Tier 2+"),
    ((2.25, 2.74), (75.0, 89.99), 150, "Tier 3"),
    ((2.25, 2.74), (90.0, 100.0), 175, "Tier 3+"),
    ((2.75, 3.24), (40.0, 59.99), 125, "Tier 2"),
    ((2.75, 3.24), (60.0, 74.99), 175, "Tier 3"),
    ((2.75, 3.24), (75.0, 89.99), 225, "Tier 3+"),
    ((2.75, 3.24), (90.0, 100.0), 275, "Tier 4"),
    ((3.25, 999.0), (40.0, 59.99), 175, "Tier 3"),
    ((3.25, 999.0), (60.0, 74.99), 225, "Tier 3+"),
    ((3.25, 999.0), (75.0, 89.99), 300, "Tier 4"),
    ((3.25, 999.0), (90.0, 100.0), 350, "Tier 4+"),
]


def calc_supplemental_bonus(hrs_per_ro: float, closing_pct: float) -> Tuple[float, str]:
    """Return (bonus dollars, tier label). Both metrics must qualify or bonus is $0."""
    if hrs_per_ro < MIN_HRS_PER_RO or closing_pct < MIN_CLOSING_PCT:
        return 0.0, "No bonus"

    for (hr_min, hr_max), (close_min, close_max), amount, tier in SUPPLEMENTAL_BONUS_MATRIX:
        if hr_min <= hrs_per_ro <= hr_max and close_min <= closing_pct <= close_max:
            return float(amount), tier
    return 0.0, "No bonus"


def supplemental_bonus_label(hrs_per_ro: float, closing_pct: float, bonus: float, tier: str) -> str:
    if bonus <= 0:
        if hrs_per_ro < MIN_HRS_PER_RO:
            return f"CP {hrs_per_ro:.2f} hrs/RO — below {MIN_HRS_PER_RO} floor"
        if closing_pct < MIN_CLOSING_PCT:
            return f"{closing_pct:.1f}% close — below {MIN_CLOSING_PCT:.0f}% floor"
        return "No bonus — metrics not in matrix"
    return f"CP {hrs_per_ro:.2f} hrs/RO · {closing_pct:.1f}% close → {tier} ${bonus:.0f}"


def lookup_bonus(hrs_per_ro: float, closing_pct: float) -> Tuple[float, str, str]:
    """Return (bonus, tier, detail label)."""
    bonus, tier = calc_supplemental_bonus(hrs_per_ro, closing_pct)
    label = supplemental_bonus_label(hrs_per_ro, closing_pct, bonus, tier)
    return bonus, tier, label

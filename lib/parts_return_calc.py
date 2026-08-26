"""Select returnable parts within a dollar allowance using age vs value."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set

from lib.parts_return_parser import PartsInventoryLine

# Chrysler multipacks and misc hardware are generally not returnable.
HARDWARE_KEYWORDS = (
    "BOLT",
    "NUT",
    "SCREW",
    "WASHER",
    "CLIP",
    "FASTENER",
    "FASTNER",
    "RIVET",
    "STUD",
    "CLAMP",
    "HARDWARE",
    "RETAINER",
)


@dataclass
class ReturnCandidate:
    line: PartsInventoryLine
    return_qty: float
    return_value: float
    score: float
    skip_reason: str = ""


@dataclass
class PartsReturnPlan:
    allowance: float
    selected: List[ReturnCandidate] = field(default_factory=list)
    skipped: List[ReturnCandidate] = field(default_factory=list)
    remaining_allowance: float = 0.0

    @property
    def selected_value(self) -> float:
        return round(sum(c.return_value for c in self.selected), 2)

    @property
    def selected_count(self) -> int:
        return len(self.selected)


def is_hardware_description(description: str, extra_keywords: Sequence[str] = ()) -> bool:
    text = f" {(description or '').upper()} "
    keywords = list(HARDWARE_KEYWORDS) + [k.upper() for k in extra_keywords if k]
    for word in keywords:
        token = word.strip().upper()
        if not token:
            continue
        if token in text:
            return True
    return False


def is_multipack(line: PartsInventoryLine) -> bool:
    return float(line.pack or 1) > 1


def age_value_score(age: float, value: float) -> float:
    """Higher age and higher shelf value rank first."""
    return max(float(age or 0), 0.0) * max(float(value or 0), 0.0)


def classify_line(
    line: PartsInventoryLine,
    *,
    exclude_multipack: bool = True,
    exclude_hardware: bool = True,
    min_age: float = 0.0,
    min_value: float = 0.0,
    extra_hardware_keywords: Sequence[str] = (),
) -> Optional[str]:
    """Return skip reason, or None if the line may be returned."""
    if line.qoh <= 0 or line.value <= 0:
        return "No on-hand value"
    if line.age < min_age:
        return f"Age under {min_age:g} mo"
    if line.value < min_value:
        return f"Value under ${min_value:,.2f}"
    if exclude_multipack and is_multipack(line):
        return "Multipack (not returnable)"
    if exclude_hardware and is_hardware_description(
        line.description, extra_hardware_keywords
    ):
        return "Misc hardware (not returnable)"
    return None


def build_return_plan(
    lines: Sequence[PartsInventoryLine],
    allowance: float,
    *,
    exclude_multipack: bool = True,
    exclude_hardware: bool = True,
    min_age: float = 0.0,
    min_value: float = 0.0,
    allow_partial_qty: bool = True,
    extra_hardware_keywords: Sequence[str] = (),
    prefer_sources: Optional[Set[str]] = None,
) -> PartsReturnPlan:
    """
    Greedy fill by age×value score until the return allowance is used.

    Whole lines are preferred. If the next line would exceed remaining dollars and
    allow_partial_qty is on, return as many pack=1 units as fit.
    """
    allowance = max(float(allowance or 0), 0.0)
    plan = PartsReturnPlan(allowance=allowance, remaining_allowance=allowance)
    ranked: List[ReturnCandidate] = []

    for line in lines:
        reason = classify_line(
            line,
            exclude_multipack=exclude_multipack,
            exclude_hardware=exclude_hardware,
            min_age=min_age,
            min_value=min_value,
            extra_hardware_keywords=extra_hardware_keywords,
        )
        score = age_value_score(line.age, line.value)
        if prefer_sources and line.source in prefer_sources:
            score *= 1.15
        if "MNS" in (line.source or ""):
            # Slight dead-stock preference when scores are close.
            score *= 1.05
        candidate = ReturnCandidate(
            line=line,
            return_qty=line.qoh,
            return_value=round(line.value, 2),
            score=score,
            skip_reason=reason or "",
        )
        if reason:
            plan.skipped.append(candidate)
        else:
            ranked.append(candidate)

    ranked.sort(key=lambda c: (-c.score, -c.line.age, -c.line.value, c.line.part_number))

    remaining = allowance
    for candidate in ranked:
        if remaining <= 0.005:
            candidate.skip_reason = "Allowance full"
            plan.skipped.append(candidate)
            continue

        line = candidate.line
        unit_cost = line.cost if line.cost > 0 else (
            line.value / line.qoh if line.qoh > 0 else 0.0
        )

        if candidate.return_value <= remaining + 0.005:
            plan.selected.append(candidate)
            remaining = round(remaining - candidate.return_value, 2)
            continue

        if allow_partial_qty and unit_cost > 0 and not is_multipack(line):
            qty = int(remaining // unit_cost)
            if qty >= 1:
                value = round(qty * unit_cost, 2)
                plan.selected.append(
                    ReturnCandidate(
                        line=line,
                        return_qty=float(qty),
                        return_value=value,
                        score=candidate.score,
                    )
                )
                remaining = round(remaining - value, 2)
                continue

        candidate.skip_reason = "Exceeds remaining allowance"
        plan.skipped.append(candidate)

    plan.remaining_allowance = max(remaining, 0.0)
    return plan

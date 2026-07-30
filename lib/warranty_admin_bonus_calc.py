"""Warranty Administrator monthly performance bonus (Hourly + Performance Bonus plan)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


MAX_MONTHLY_BONUS = 1250.0
STRETCH_BONUS = 250.0

# Receivables (last business day of month)
RECEIVABLES_TOP = (85_000.0, 400.0)
RECEIVABLES_MID = (100_000.0, 250.0)

# Average days RO close → claim submit
DAYS_TOP = (2.0, 300.0)
DAYS_MID = (3.0, 150.0)

# First-pass approval rate (%)
FIRST_PASS_TOP = (90.0, 300.0)
FIRST_PASS_MID = (85.0, 150.0)


@dataclass
class MetricResult:
    label: str
    input_value: float
    amount: float
    tier_label: str
    top_tier: bool


@dataclass
class WarrantyAdminBonusResult:
    employee_name: str
    bonus_month: str
    receivables: MetricResult
    avg_days: MetricResult
    first_pass: MetricResult
    stretch_earned: bool
    stretch_amount: float
    metrics_subtotal: float
    compliance_reduction: float
    total_bonus: float
    notes: str = ""
    paid_on_label: str = ""


def receivables_bonus(balance: float) -> MetricResult:
    if balance <= RECEIVABLES_TOP[0]:
        amount, tier, top = RECEIVABLES_TOP[1], f"≤ ${RECEIVABLES_TOP[0]:,.0f}", True
    elif balance <= RECEIVABLES_MID[0]:
        amount, tier, top = RECEIVABLES_MID[1], f"${RECEIVABLES_TOP[0] + 1:,.0f} – ${RECEIVABLES_MID[0]:,.0f}", False
    else:
        amount, tier, top = 0.0, f"Over ${RECEIVABLES_MID[0]:,.0f}", False
    return MetricResult(
        label="Warranty receivables balance",
        input_value=float(balance or 0),
        amount=amount,
        tier_label=tier,
        top_tier=top,
    )


def avg_days_bonus(days: float) -> MetricResult:
    if days <= DAYS_TOP[0]:
        amount, tier, top = DAYS_TOP[1], f"≤ {DAYS_TOP[0]:.1f} days", True
    elif days <= DAYS_MID[0]:
        amount, tier, top = DAYS_MID[1], f"{DAYS_TOP[0] + 0.1:.1f} – {DAYS_MID[0]:.1f} days", False
    else:
        amount, tier, top = 0.0, f"Over {DAYS_MID[0]:.1f} days", False
    return MetricResult(
        label="Average days to submit claims",
        input_value=float(days or 0),
        amount=amount,
        tier_label=tier,
        top_tier=top,
    )


def first_pass_bonus(pct: float) -> MetricResult:
    if pct >= FIRST_PASS_TOP[0]:
        amount, tier, top = FIRST_PASS_TOP[1], f"≥ {FIRST_PASS_TOP[0]:.0f}%", True
    elif pct >= FIRST_PASS_MID[0]:
        amount, tier, top = FIRST_PASS_MID[1], f"{FIRST_PASS_MID[0]:.0f}% – {FIRST_PASS_TOP[0] - 0.1:.1f}%", False
    else:
        amount, tier, top = 0.0, f"Below {FIRST_PASS_MID[0]:.0f}%", False
    return MetricResult(
        label="Claims paid on first submission",
        input_value=float(pct or 0),
        amount=amount,
        tier_label=tier,
        top_tier=top,
    )


def calculate_warranty_admin_bonus(
    *,
    employee_name: str,
    bonus_month: str,
    receivables_balance: float,
    avg_days_to_submit: float,
    first_pass_pct: float,
    compliance_reduction: float = 0.0,
    notes: str = "",
    paid_on_label: str = "",
) -> WarrantyAdminBonusResult:
    recv = receivables_bonus(receivables_balance)
    days = avg_days_bonus(avg_days_to_submit)
    first = first_pass_bonus(first_pass_pct)
    stretch = recv.top_tier and days.top_tier and first.top_tier
    stretch_amount = STRETCH_BONUS if stretch else 0.0
    metrics_subtotal = recv.amount + days.amount + first.amount + stretch_amount
    reduction = max(float(compliance_reduction or 0), 0.0)
    total = max(metrics_subtotal - reduction, 0.0)
    return WarrantyAdminBonusResult(
        employee_name=(employee_name or "Warranty Administrator").strip(),
        bonus_month=bonus_month,
        receivables=recv,
        avg_days=days,
        first_pass=first,
        stretch_earned=stretch,
        stretch_amount=stretch_amount,
        metrics_subtotal=metrics_subtotal,
        compliance_reduction=reduction,
        total_bonus=round(total, 2),
        notes=(notes or "").strip(),
        paid_on_label=paid_on_label,
    )


def result_to_dict(result: WarrantyAdminBonusResult) -> dict:
    def _metric(m: MetricResult) -> dict:
        return {
            "label": m.label,
            "input_value": m.input_value,
            "amount": m.amount,
            "tier_label": m.tier_label,
            "top_tier": m.top_tier,
        }

    return {
        "employee_name": result.employee_name,
        "bonus_month": result.bonus_month,
        "receivables": _metric(result.receivables),
        "avg_days": _metric(result.avg_days),
        "first_pass": _metric(result.first_pass),
        "stretch_earned": result.stretch_earned,
        "stretch_amount": result.stretch_amount,
        "metrics_subtotal": result.metrics_subtotal,
        "compliance_reduction": result.compliance_reduction,
        "total_bonus": result.total_bonus,
        "notes": result.notes,
        "paid_on_label": result.paid_on_label,
        "max_monthly_bonus": MAX_MONTHLY_BONUS,
    }


def inputs_from_snapshot(snapshot: dict) -> dict:
    recv = snapshot.get("receivables") or {}
    days = snapshot.get("avg_days") or {}
    first = snapshot.get("first_pass") or {}
    return {
        "employee_name": snapshot.get("employee_name", "Warranty Administrator"),
        "bonus_month": snapshot.get("bonus_month", ""),
        "receivables_balance": float(recv.get("input_value", 0) or 0),
        "avg_days_to_submit": float(days.get("input_value", 0) or 0),
        "first_pass_pct": float(first.get("input_value", 0) or 0),
        "compliance_reduction": float(snapshot.get("compliance_reduction", 0) or 0),
        "notes": snapshot.get("notes", ""),
        "paid_on_label": snapshot.get("paid_on_label", ""),
    }

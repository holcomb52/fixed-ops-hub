"""Service advisor payroll calculations — mirrors ADVISOR PAYROLL.xlsx."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

ALIGNMENT_BONUS_AMOUNT = 500.0
CP_HOURS_BUMP_THRESHOLD = 2.25
TOM_JOEY_CP_BUMP_RATE = 13.0
ADVISOR_WEEKLY_GUARANTEE = 1000.0
NEW_HIRE_WEEKLY_GUARANTEE = ADVISOR_WEEKLY_GUARANTEE  # backward compat

PLAN_SEASONED = "seasoned"
PLAN_NEW_ADVISORS = "new_advisors"
PLAN_NEW_ADVISORS_GUARANTEE = "new_advisors_guarantee"
PLAN_NEW_HIRES = "new_hires"  # legacy key — migrated to PLAN_NEW_ADVISORS_GUARANTEE on load

PLAN_LABELS = {
    PLAN_SEASONED: "Seasoned Advisors",
    PLAN_NEW_ADVISORS: "New Advisors",
    PLAN_NEW_ADVISORS_GUARANTEE: "New Advisors Pay Plan/Guarantee",
    PLAN_NEW_HIRES: "New Advisors Pay Plan/Guarantee",
}

GUARANTEE_PLAN_TYPES = frozenset({PLAN_NEW_ADVISORS_GUARANTEE, PLAN_NEW_HIRES})
NEW_ADVISORS_COMMISSION_PLAN_TYPES = frozenset({PLAN_NEW_ADVISORS, *GUARANTEE_PLAN_TYPES})

PLAN_META = {
    PLAN_SEASONED: {
        "num_advisors": 4,
        "warranty_labor_rate": 264.03,
        "pay_period_objective": 200.0,
        "top_labor_rate": 9.5,
        "parts_commission_rate": 0.03,
    },
    PLAN_NEW_ADVISORS: {
        "num_advisors": 6,
        "warranty_labor_rate": 225.43,
        "pay_period_objective": 130.0,
        "top_labor_rate": 9.5,
        "parts_commission_rate": 0.03,
    },
    PLAN_NEW_ADVISORS_GUARANTEE: {
        "num_advisors": 6,
        "warranty_labor_rate": 225.43,
        "pay_period_objective": 130.0,
        "top_labor_rate": 9.5,
        "parts_commission_rate": 0.03,
        "weekly_guarantee": ADVISOR_WEEKLY_GUARANTEE,
    },
    PLAN_NEW_HIRES: {
        "num_advisors": 6,
        "warranty_labor_rate": 225.43,
        "pay_period_objective": 130.0,
        "top_labor_rate": 9.5,
        "parts_commission_rate": 0.03,
        "weekly_guarantee": ADVISOR_WEEKLY_GUARANTEE,
    },
}


def normalize_advisor_plan_type(plan_type: str) -> str:
    if plan_type == PLAN_NEW_HIRES:
        return PLAN_NEW_ADVISORS_GUARANTEE
    return plan_type


def plan_has_weekly_guarantee(plan_type: str) -> bool:
    return normalize_advisor_plan_type(plan_type) == PLAN_NEW_ADVISORS_GUARANTEE


def commission_plan_type(plan_type: str) -> str:
    if normalize_advisor_plan_type(plan_type) == PLAN_NEW_ADVISORS_GUARANTEE:
        return PLAN_NEW_ADVISORS
    return plan_type

# Standard / Felix CP bump rates (side table on advisor spreadsheet).
CP_BUMP_RATES = {
    6.5: 7.5,
    7.5: 8.5,
    8.0: 10.0,
    9.5: 12.0,
}

CSI_TIER_OPTIONS = {
    "none": ("None", 0.0),
    "top": ("Top", 1200.0),
    "middle": ("Middle", 750.0),
    "bottom": ("Bottom", 250.0),
}


@dataclass
class AdvisorPayrollRow:
    name: str
    plan_type: str = PLAN_NEW_ADVISORS
    top_labor_rate: float = 9.5
    weekly_guarantee: float = NEW_HIRE_WEEKLY_GUARANTEE
    advisor_id: str = ""
    total_hours: float = 0.0
    write_off_hours: float = 0.0
    policy_expense: float = 0.0
    num_advisors: int = 4
    warranty_labor_rate: float = 264.03
    hours_deducted: float = 0.0
    pay_period_objective: float = 200.0
    hours_sold: float = 0.0
    repair_order_count: float = 0.0
    parts_labor_sales: float = 0.0
    parts_sales: float = 0.0
    cp_bump_qualified: bool = False
    alignment_bonus_qualified: bool = False
    csi_tier: str = "none"
    variable_amount: float = ALIGNMENT_BONUS_AMOUNT
    menu_presentation: float = 0.0
    parts_commission_rate: float = 0.03
    spiff: float = 0.0
    notes: str = ""
    hourly_pay_override: Optional[float] = None


@dataclass
class TierResult:
    label: str
    rate: float
    payout: float
    qualifies: bool


@dataclass
class AdvisorPayrollResult:
    policy_per_advisor: float
    less_policy_hours: float
    payable_hours: float
    tiers: List[TierResult]
    hourly_pay: float
    hourly_tier_label: str
    hourly_rate: float
    cp_bump_active: bool
    csi_pay: float
    parts_pay: float
    variable_pay: float
    alignment_qualified: bool
    menu_pay: float
    spiff_pay: float
    total_pay: float
    payroll_pct: float
    commission_total: float
    guarantee_amount: float
    guarantee_top_up: float
    guarantee_active: bool


def apply_plan_defaults(row: AdvisorPayrollRow, plan_type: Optional[str] = None) -> AdvisorPayrollRow:
    plan = plan_type or row.plan_type
    meta = PLAN_META.get(plan, PLAN_META[PLAN_NEW_ADVISORS])
    row.plan_type = plan
    row.num_advisors = int(meta["num_advisors"])
    row.warranty_labor_rate = float(meta["warranty_labor_rate"])
    row.pay_period_objective = float(meta["pay_period_objective"])
    row.parts_commission_rate = float(meta["parts_commission_rate"])
    normalized = normalize_advisor_plan_type(plan)
    if normalized in (PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE) and row.top_labor_rate <= 0:
        row.top_labor_rate = float(meta["top_labor_rate"])
    elif normalized == PLAN_SEASONED:
        row.top_labor_rate = float(meta["top_labor_rate"])
    if plan_has_weekly_guarantee(plan):
        row.weekly_guarantee = float(meta.get("weekly_guarantee", ADVISOR_WEEKLY_GUARANTEE))
    return row


def _policy_hours(row: AdvisorPayrollRow) -> float:
    if row.num_advisors <= 0 or row.warranty_labor_rate <= 0:
        return 0.0
    per_advisor = row.policy_expense / row.num_advisors
    return per_advisor / row.warranty_labor_rate


def _payable_hours(row: AdvisorPayrollRow) -> float:
    less_policy = _policy_hours(row)
    return max(row.hours_sold - less_policy, 0.0)


def _cp_bump_active(row: AdvisorPayrollRow) -> bool:
    return row.cp_bump_qualified


def _rate_with_cp_bump(base_rate: float, row: AdvisorPayrollRow) -> float:
    if not _cp_bump_active(row):
        return base_rate
    return CP_BUMP_RATES.get(base_rate, base_rate)


def _tom_joey_tiers(row: AdvisorPayrollRow, payable: float) -> List[TierResult]:
    objective = row.pay_period_objective
    specs = [
        ("Less than 80%", 6.5, lambda h: 0 < h < 180),
        ("80 to 90%", 7.5, lambda h: 180 < h <= 190),
        ("90 to 99%", 8.0, lambda h: 190 < h < objective),
        ("100%+", 9.5, lambda h: h >= objective),
    ]
    return [
        TierResult(label=label, rate=rate, payout=payable * rate, qualifies=fn(payable))
        for label, rate, fn in specs
    ]


def _standard_tiers(row: AdvisorPayrollRow, payable: float, top_rate: float = 9.5) -> List[TierResult]:
    objective = row.pay_period_objective
    low_80 = objective * 0.8
    low_90 = objective * 0.9
    bump = _cp_bump_active(row)
    specs = [
        ("Less than 80%", 6.5, lambda h: 0 < h < low_80),
        ("80 to 90%", 7.5, lambda h: low_80 <= h < low_90),
        ("90 to 99%", 8.0, lambda h: low_90 <= h < objective),
        ("100%+", top_rate, lambda h: h >= objective),
    ]
    suffix = " (CP bump)" if bump else ""
    return [
        TierResult(
            label=f"{label}{suffix}",
            rate=_rate_with_cp_bump(base_rate, row),
            payout=payable * _rate_with_cp_bump(base_rate, row),
            qualifies=fn(payable),
        )
        for label, base_rate, fn in specs
    ]


def _pick_hourly_pay(tiers: List[TierResult]) -> tuple:
    qualifying = [t for t in tiers if t.qualifies]
    if not qualifying:
        return 0.0, "No qualifying tier"
    best = max(qualifying, key=lambda t: t.payout)
    return best.payout, best.label


def _commission_plan_type(row: AdvisorPayrollRow) -> str:
    return commission_plan_type(row.plan_type)


def calculate_advisor_payroll(
    row: AdvisorPayrollRow,
    pay_period_weeks: float = 2.0,
) -> AdvisorPayrollResult:
    policy_per_advisor = row.policy_expense / row.num_advisors if row.num_advisors else 0.0
    less_policy = _policy_hours(row)
    payable = _payable_hours(row)

    cp_bump = _cp_bump_active(row)

    commission_plan = _commission_plan_type(row)
    if commission_plan == PLAN_SEASONED:
        tiers = _tom_joey_tiers(row, payable)
        if cp_bump and payable > 0:
            hourly_pay = payable * TOM_JOEY_CP_BUMP_RATE
            hourly_label = "CP bump · $13/hr"
            hourly_rate = TOM_JOEY_CP_BUMP_RATE
        else:
            hourly_pay, hourly_label = _pick_hourly_pay(tiers)
            hourly_rate = hourly_pay / payable if hourly_pay > 0 and payable > 0 else 0.0
    else:
        tiers = _standard_tiers(row, payable, top_rate=row.top_labor_rate)
        hourly_pay, hourly_label = _pick_hourly_pay(tiers)
        hourly_rate = hourly_pay / payable if hourly_pay > 0 and payable > 0 else 0.0
    if row.hourly_pay_override is not None and row.hourly_pay_override > 0:
        hourly_pay = row.hourly_pay_override
        hourly_label = "Manual override"
        hourly_rate = hourly_pay / payable if payable > 0 else 0.0
    _, csi_pay = CSI_TIER_OPTIONS.get(row.csi_tier, CSI_TIER_OPTIONS["none"])
    parts_pay = row.parts_sales * row.parts_commission_rate
    alignment_qualified = row.alignment_bonus_qualified
    variable_pay = row.variable_amount if alignment_qualified else 0.0
    menu_pay = row.menu_presentation
    spiff_pay = row.spiff
    commission_total = hourly_pay + csi_pay + parts_pay + variable_pay + menu_pay + spiff_pay
    guarantee_amount = 0.0
    guarantee_top_up = 0.0
    guarantee_active = False
    total = commission_total

    if plan_has_weekly_guarantee(row.plan_type):
        guarantee_amount = row.weekly_guarantee * max(pay_period_weeks, 0.0)
        if guarantee_amount > commission_total:
            guarantee_active = True
            guarantee_top_up = guarantee_amount - commission_total
            total = guarantee_amount

    payroll_pct = (total / row.parts_labor_sales) if row.parts_labor_sales else 0.0

    return AdvisorPayrollResult(
        policy_per_advisor=policy_per_advisor,
        less_policy_hours=less_policy,
        payable_hours=payable,
        tiers=tiers,
        hourly_pay=hourly_pay,
        hourly_rate=hourly_rate,
        hourly_tier_label=hourly_label,
        cp_bump_active=cp_bump,
        csi_pay=csi_pay,
        parts_pay=parts_pay,
        variable_pay=variable_pay,
        alignment_qualified=alignment_qualified,
        menu_pay=menu_pay,
        spiff_pay=spiff_pay,
        total_pay=total,
        payroll_pct=payroll_pct,
        commission_total=commission_total,
        guarantee_amount=guarantee_amount,
        guarantee_top_up=guarantee_top_up,
        guarantee_active=guarantee_active,
    )


def clone_advisors(rows: List[AdvisorPayrollRow]) -> List[AdvisorPayrollRow]:
    return [AdvisorPayrollRow(**row.__dict__) for row in rows]

"""Build service advisor payroll snapshot for PDF export."""

from __future__ import annotations

from typing import List

from lib.advisor_payroll_calc import PLAN_LABELS, AdvisorPayrollRow, AdvisorPayrollResult, calculate_advisor_payroll


def build_advisor_payroll_snapshot(
    advisors: List[AdvisorPayrollRow],
    results: List[AdvisorPayrollResult],
    pay_period: str,
    pay_period_weeks: float = 2.0,
) -> dict:
    rows = []
    grand_total = 0.0

    for advisor, result in zip(advisors, results):
        grand_total += result.total_pay
        rows.append({
            "name": advisor.name,
            "advisor_id": advisor.advisor_id,
            "plan": PLAN_LABELS.get(advisor.plan_type, advisor.plan_type),
            "plan_type": advisor.plan_type,
            "hours_sold": advisor.hours_sold,
            "payable_hours": result.payable_hours,
            "hourly_rate": result.hourly_rate,
            "hourly_tier_label": result.hourly_tier_label,
            "labor_pay": result.hourly_pay,
            "parts_sales": advisor.parts_sales,
            "parts_pay": result.parts_pay,
            "csi_tier": advisor.csi_tier,
            "csi_pay": result.csi_pay,
            "alignment_pay": result.variable_pay,
            "spiff": result.spiff_pay,
            "cp_bump": advisor.cp_bump_qualified,
            "alignment_bonus": advisor.alignment_bonus_qualified,
            "commission_total": result.commission_total,
            "guarantee_amount": result.guarantee_amount,
            "guarantee_top_up": result.guarantee_top_up,
            "guarantee_active": result.guarantee_active,
            "total_pay": result.total_pay,
            "notes": advisor.notes,
        })

    return {
        "pay_period": pay_period or "—",
        "pay_period_weeks": pay_period_weeks,
        "advisors": rows,
        "grand_total": grand_total,
        "advisor_count": len(rows),
    }

"""Build payroll snapshot for PDF export."""

from __future__ import annotations

from typing import Dict, List, Optional

from lib.tech_payroll_calc import TechPayrollRow, all_hours_by_name, team_totals, weeks_in_pay_period


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _bonus_amount(row: TechPayrollRow, team_hrs: float, global_hours: dict) -> tuple:
    """Return (label, amount) for foreman or quick lube column."""
    if row.foreman_rule == "team_per_hr_2":
        return ("Foreman", row.foreman_bonus(team_hrs, global_hours))
    if row.foreman_rule == "team_per_hr_1":
        return ("Foreman", row.foreman_bonus(team_hrs, global_hours))
    if row.quick_lube_sources:
        return ("Quick Lube", row.quick_lube_bonus(global_hours))
    return ("", 0.0)


def build_payroll_snapshot(
    teams: Dict[str, List[TechPayrollRow]],
    pay_period: str,
    pay_period_weeks: Optional[float] = None,
) -> dict:
    global_hours = all_hours_by_name(teams)
    weeks = pay_period_weeks if pay_period_weeks is not None else weeks_in_pay_period(pay_period)
    snapshot = {
        "pay_period": pay_period or "—",
        "teams": [],
        "grand_hours": 0.0,
        "grand_total": 0.0,
    }

    for team_name, rows in teams.items():
        team_hrs = sum(r.flat_rate_hours for r in rows)
        totals = team_totals(rows, global_hours, weeks)
        techs = []

        for row in rows:
            bonus_label, bonus_amt = _bonus_amount(row, team_hrs, global_hours)
            total = row.total_pay(team_hrs, global_hours, weeks)
            techs.append({
                "name": row.name,
                "tech_number": row.tech_number,
                "hours": row.flat_rate_hours,
                "dollars": row.flag_base_pay(weeks),
                "flag_dollars": row.dollars_earned,
                "guarantee_top_up": row.guarantee_top_up(weeks),
                "payable_hours": row.payable_flag_hours(weeks),
                "rate": row.hourly_rate,
                "prod_bonus": row.production_bonus,
                "supplemental_bonus": row.supplemental_bonus,
                "supplemental_tier": row.supplemental_tier,
                "pay_plan": row.pay_plan,
                "weekly_hour_guarantee": row.weekly_hour_guarantee,
                "cp_hrs_per_ro": row.cp_hrs_per_ro,
                "closing_pct": row.closing_pct,
                "bonus_label": bonus_label,
                "bonus_amount": bonus_amt,
                "training_hours": row.training_hours,
                "training_pay": row.training_pay,
                "spiff": row.spiff,
                "notes": row.notes,
                "total_pay": total,
                "combined_pay": total + bonus_amt if row.quick_lube_sources else total,
            })

        snapshot["teams"].append({
            "name": team_name,
            "team_hours": team_hrs,
            "team_total": totals["total_pay"],
            "technicians": techs,
        })
        snapshot["grand_hours"] += team_hrs
        snapshot["grand_total"] += totals["total_pay"]

    return snapshot

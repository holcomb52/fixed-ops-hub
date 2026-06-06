"""Build payroll snapshot for PDF export."""

from __future__ import annotations

from typing import Dict, List

from lib.tech_payroll_calc import TechPayrollRow, all_hours_by_name, team_totals


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


def build_payroll_snapshot(teams: Dict[str, List[TechPayrollRow]], pay_period: str) -> dict:
    global_hours = all_hours_by_name(teams)
    snapshot = {
        "pay_period": pay_period or "—",
        "teams": [],
        "grand_hours": 0.0,
        "grand_total": 0.0,
    }

    for team_name, rows in teams.items():
        team_hrs = sum(r.flat_rate_hours for r in rows)
        totals = team_totals(rows, global_hours)
        techs = []

        for row in rows:
            bonus_label, bonus_amt = _bonus_amount(row, team_hrs, global_hours)
            total = row.total_pay(team_hrs, global_hours)
            techs.append({
                "name": row.name,
                "tech_number": row.tech_number,
                "hours": row.flat_rate_hours,
                "dollars": row.dollars_earned,
                "rate": row.hourly_rate,
                "prod_bonus": row.production_bonus,
                "bonus_label": bonus_label,
                "bonus_amount": bonus_amt,
                "training_hours": row.training_hours,
                "training_pay": row.training_pay,
                "spiff": row.spiff,
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

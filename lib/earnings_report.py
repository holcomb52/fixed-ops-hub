"""Aggregate employee earnings from saved payroll runs by date range."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from lib.advisor_payroll_storage import list_advisor_payroll_runs, load_advisor_payroll_run
from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_storage import list_payroll_runs, load_payroll_run
from lib.receptionist_payroll_storage import list_receptionist_payroll_runs, load_receptionist_payroll_run
from lib.tech_payroll_calc import weeks_in_pay_period
from lib.tech_roster import teams_from_saved_data


@dataclass
class EarningsLine:
    name: str
    role: str
    pay_period: str
    period_start: date
    period_end: date
    total_pay: float


@dataclass
class EmployeeEarningsSummary:
    name: str
    role: str
    total_pay: float
    pay_periods: List[str] = field(default_factory=list)
    lines: List[EarningsLine] = field(default_factory=list)


def parse_period_token(token: str) -> Optional[date]:
    token = (token or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def parse_pay_period_range(pay_period: str) -> Optional[Tuple[date, date]]:
    if not pay_period or "-" not in pay_period:
        return None
    start_text, end_text = pay_period.split("-", 1)
    start = parse_period_token(start_text)
    end = parse_period_token(end_text)
    if start and end:
        return start, end
    return None


def periods_overlap(
    period_start: date,
    period_end: date,
    query_start: date,
    query_end: date,
) -> bool:
    return period_start <= query_end and period_end >= query_start


def _tech_lines(snapshot: dict, pay_period: str, period_start: date, period_end: date) -> List[EarningsLine]:
    teams = teams_from_saved_data(snapshot.get("teams", {}))
    weeks = weeks_in_pay_period(pay_period)
    export = build_payroll_snapshot(teams, pay_period, weeks)
    lines: List[EarningsLine] = []
    for team in export.get("teams", []):
        for tech in team.get("technicians", []):
            lines.append(
                EarningsLine(
                    name=tech["name"],
                    role="Technician",
                    pay_period=pay_period,
                    period_start=period_start,
                    period_end=period_end,
                    total_pay=float(tech.get("combined_pay", tech.get("total_pay", 0)) or 0),
                )
            )
    return lines


def _advisor_lines(snapshot: dict, pay_period: str, period_start: date, period_end: date) -> List[EarningsLine]:
    lines: List[EarningsLine] = []
    for advisor in snapshot.get("advisors", []):
        lines.append(
            EarningsLine(
                name=advisor["name"],
                role="Service Advisor",
                pay_period=pay_period,
                period_start=period_start,
                period_end=period_end,
                total_pay=float(advisor.get("total_pay", 0) or 0),
            )
        )
    return lines


def _receptionist_lines(snapshot: dict, pay_period: str, period_start: date, period_end: date) -> List[EarningsLine]:
    lines: List[EarningsLine] = []
    for employee in snapshot.get("employees", []):
        lines.append(
            EarningsLine(
                name=employee["name"],
                role="Receptionist",
                pay_period=pay_period,
                period_start=period_start,
                period_end=period_end,
                total_pay=float(employee.get("total_pay", 0) or 0),
            )
        )
    return lines


def _ensure_snapshot(run: dict, role: str) -> dict:
    if run.get("snapshot"):
        return run
    run_id = run.get("id")
    if not run_id:
        return run
    if role == "Technician":
        loaded = load_payroll_run(run_id)
    elif role == "Service Advisor":
        loaded = load_advisor_payroll_run(run_id)
    else:
        loaded = load_receptionist_payroll_run(run_id)
    return loaded or run


def _lines_from_run(run: dict, role: str) -> List[EarningsLine]:
    run = _ensure_snapshot(run, role)
    snapshot = run.get("snapshot") or {}
    pay_period = run.get("pay_period") or snapshot.get("pay_period") or ""
    parsed = parse_pay_period_range(pay_period)
    if not parsed:
        return []
    period_start, period_end = parsed
    if role == "Technician":
        return _tech_lines(snapshot, pay_period, period_start, period_end)
    if role == "Service Advisor":
        return _advisor_lines(snapshot, pay_period, period_start, period_end)
    return _receptionist_lines(snapshot, pay_period, period_start, period_end)


def collect_earnings_lines(
    start_date: date,
    end_date: date,
    role_filter: str = "All",
    name_query: str = "",
) -> List[EarningsLine]:
    """Return one line per employee per pay period that overlaps the date range."""
    if end_date < start_date:
        return []

    name_query = (name_query or "").strip().lower()
    lines: List[EarningsLine] = []

    sources = []
    if role_filter in ("All", "Technician"):
        sources.extend(("Technician", run) for run in list_payroll_runs())
    if role_filter in ("All", "Service Advisor"):
        sources.extend(("Service Advisor", run) for run in list_advisor_payroll_runs())
    if role_filter in ("All", "Receptionist"):
        sources.extend(("Receptionist", run) for run in list_receptionist_payroll_runs())

    seen_periods: Dict[Tuple[str, str, str], bool] = {}

    for role, run in sources:
        pay_period = run.get("pay_period") or ""
        parsed = parse_pay_period_range(pay_period)
        if not parsed:
            continue
        period_start, period_end = parsed
        if not periods_overlap(period_start, period_end, start_date, end_date):
            continue

        dedupe_key = (role, pay_period, run.get("id", ""))
        if dedupe_key in seen_periods:
            continue
        seen_periods[dedupe_key] = True

        for line in _lines_from_run(run, role):
            if name_query and name_query not in line.name.lower():
                continue
            lines.append(line)

    lines.sort(key=lambda row: (row.name.lower(), row.period_start, row.role))
    return lines


def summarize_earnings(lines: List[EarningsLine]) -> List[EmployeeEarningsSummary]:
    grouped: Dict[Tuple[str, str], EmployeeEarningsSummary] = {}
    for line in lines:
        key = (line.name, line.role)
        if key not in grouped:
            grouped[key] = EmployeeEarningsSummary(name=line.name, role=line.role, total_pay=0.0)
        summary = grouped[key]
        summary.total_pay += line.total_pay
        if line.pay_period not in summary.pay_periods:
            summary.pay_periods.append(line.pay_period)
        summary.lines.append(line)

    results = list(grouped.values())
    results.sort(key=lambda row: (-row.total_pay, row.name.lower()))
    return results

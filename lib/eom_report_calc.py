"""End-of-month Fixed Ops staffing / efficiency report for the controller."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class EomReportResult:
    report_month: str
    tech_count: float
    hours_per_day: float
    work_days: float
    total_available_hours: float
    total_clock_time: float
    tech_flagged_hours: float
    efficiency: float
    lot_porters: float
    cashiers: float
    advisors: float
    shuttle_drivers: float
    notes: str = ""

    @property
    def efficiency_pct(self) -> float:
        return self.efficiency * 100.0


def calculate_eom_report(
    *,
    report_month: str,
    tech_count: float,
    hours_per_day: float,
    work_days: float,
    total_clock_time: float,
    tech_flagged_hours: float,
    lot_porters: float = 0.0,
    cashiers: float = 0.0,
    advisors: float = 0.0,
    shuttle_drivers: float = 0.0,
    notes: str = "",
) -> EomReportResult:
    techs = max(float(tech_count or 0), 0.0)
    hpd = max(float(hours_per_day or 0), 0.0)
    days = max(float(work_days or 0), 0.0)
    clock = max(float(total_clock_time or 0), 0.0)
    flagged = max(float(tech_flagged_hours or 0), 0.0)
    available = techs * hpd * days
    efficiency = (flagged / clock) if clock > 0 else 0.0
    return EomReportResult(
        report_month=(report_month or "").strip(),
        tech_count=techs,
        hours_per_day=hpd,
        work_days=days,
        total_available_hours=round(available, 2),
        total_clock_time=round(clock, 2),
        tech_flagged_hours=round(flagged, 2),
        efficiency=round(efficiency, 6),
        lot_porters=max(float(lot_porters or 0), 0.0),
        cashiers=max(float(cashiers or 0), 0.0),
        advisors=max(float(advisors or 0), 0.0),
        shuttle_drivers=max(float(shuttle_drivers or 0), 0.0),
        notes=(notes or "").strip(),
    )


def result_to_dict(result: EomReportResult) -> dict:
    data = asdict(result)
    data["efficiency_pct"] = round(result.efficiency_pct, 2)
    return data


def inputs_from_snapshot(snapshot: dict) -> dict:
    return {
        "report_month": snapshot.get("report_month", ""),
        "tech_count": float(snapshot.get("tech_count", 0) or 0),
        "hours_per_day": float(snapshot.get("hours_per_day", 8) or 8),
        "work_days": float(snapshot.get("work_days", 0) or 0),
        "total_clock_time": float(snapshot.get("total_clock_time", 0) or 0),
        "tech_flagged_hours": float(snapshot.get("tech_flagged_hours", 0) or 0),
        "lot_porters": float(snapshot.get("lot_porters", 0) or 0),
        "cashiers": float(snapshot.get("cashiers", 0) or 0),
        "advisors": float(snapshot.get("advisors", 0) or 0),
        "shuttle_drivers": float(snapshot.get("shuttle_drivers", 0) or 0),
        "notes": snapshot.get("notes", ""),
    }

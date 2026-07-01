"""Receptionist / cashier payroll calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

TIRE_PAY_RATE = 5.0
DEFAULT_WARRANTY_BONUS = 100.0
CSI_BONUS_NATIONAL_AVERAGE = 1000.0
CSI_BONUS_BUSINESS_CENTER = 500.0

CSI_TIER_NONE = "none"
CSI_TIER_NATIONAL = "national"
CSI_TIER_MID = "mid"

RECEPTIONIST_CSI_TIER_OPTIONS = {
    CSI_TIER_NONE: ("None", 0.0),
    CSI_TIER_NATIONAL: ("At/above national avg", CSI_BONUS_NATIONAL_AVERAGE),
    CSI_TIER_MID: ("Nat avg – business ctr avg", CSI_BONUS_BUSINESS_CENTER),
}

CSI_TIER_KEYS = [CSI_TIER_NATIONAL, CSI_TIER_MID, CSI_TIER_NONE]
CSI_BONUS_DEFAULT_NAMES = frozenset({"Brandy Sistrunk", "Serenity Skinner"})
BRANDY_SISTRUNK_NAME = "Brandy Sistrunk"

RECALL_PULSE_STRETCH_BONUS = 500.0
RECALL_PULSE_TIERS = (
    (1, 15, 3.0),
    (16, 25, 8.0),
    (26, 35, 12.0),
    (36, None, 15.0),
)

TYPE_RECEPTIONIST = "receptionist"
TYPE_BONUS = "bonus"

TYPE_LABELS = {
    TYPE_RECEPTIONIST: "Receptionist",
    TYPE_BONUS: "Bonus employee",
}


@dataclass
class ReceptionistPayrollRow:
    name: str
    last_name: str = ""
    employee_type: str = TYPE_RECEPTIONIST
    taker_codes: List[str] = field(default_factory=list)
    appointment_rate: float = 0.0
    appointments_set: float = 0.0
    tires_sold: float = 0.0
    tire_rate: float = TIRE_PAY_RATE
    has_warranty_bonus: bool = False
    warranty_bonus_amount: float = DEFAULT_WARRANTY_BONUS
    warranty_bonus_qualified: bool = False
    has_csi_bonus: bool = False
    csi_tier: str = CSI_TIER_NONE
    has_recall_pulse_plan: bool = False
    stretch_bonus_qualified: bool = False
    stretch_bonus_amount: float = RECALL_PULSE_STRETCH_BONUS
    bonus_amount: float = 0.0
    bonus_label: str = ""
    spiff: float = 0.0
    notes: str = ""


@dataclass
class ReceptionistPayrollResult:
    appointment_pay: float
    tire_pay: float
    warranty_pay: float
    csi_pay: float
    bonus_pay: float
    stretch_pay: float
    spiff_pay: float
    total_pay: float


def calculate_recall_pulse_appointment_bonus(appointments: float) -> float:
    """Tiered recall appointment bonus — incremental tiers per Brandy's pay plan."""
    total_appts = max(int(appointments), 0)
    if total_appts == 0:
        return 0.0
    bonus = 0.0
    for tier_start, tier_end, rate in RECALL_PULSE_TIERS:
        if total_appts < tier_start:
            break
        upper = tier_end if tier_end is not None else total_appts
        tier_appts = min(total_appts, upper) - tier_start + 1
        bonus += tier_appts * rate
    return bonus


def recall_pulse_tier_breakdown(appointments: float) -> list[tuple[str, float]]:
    """Human-readable tier lines for UI and PDF detail."""
    total_appts = max(int(appointments), 0)
    lines: list[tuple[str, float]] = []
    for tier_start, tier_end, rate in RECALL_PULSE_TIERS:
        if total_appts < tier_start:
            break
        upper = tier_end if tier_end is not None else total_appts
        tier_appts = min(total_appts, upper) - tier_start + 1
        if tier_appts <= 0:
            continue
        end_label = str(tier_end) if tier_end is not None else "+"
        lines.append((f"Tier {tier_start}–{end_label}: {tier_appts} × ${rate:.0f}", tier_appts * rate))
    return lines


def describe_recall_pulse_appointment_pay(appointments: float) -> str:
    parts = [f"{label} = ${amount:,.2f}" for label, amount in recall_pulse_tier_breakdown(appointments)]
    if not parts:
        return "0 recall appointments"
    return " · ".join(parts)


def ensure_receptionist_row_fields(row: ReceptionistPayrollRow) -> ReceptionistPayrollRow:
    if not hasattr(row, "has_csi_bonus"):
        row.has_csi_bonus = row.name in CSI_BONUS_DEFAULT_NAMES
    if not hasattr(row, "csi_tier"):
        row.csi_tier = CSI_TIER_NONE
    if not hasattr(row, "has_recall_pulse_plan"):
        row.has_recall_pulse_plan = row.name == BRANDY_SISTRUNK_NAME
    if not hasattr(row, "stretch_bonus_qualified"):
        row.stretch_bonus_qualified = False
    if not hasattr(row, "stretch_bonus_amount"):
        row.stretch_bonus_amount = RECALL_PULSE_STRETCH_BONUS
    return row


def calculate_receptionist_payroll(row: ReceptionistPayrollRow) -> ReceptionistPayrollResult:
    ensure_receptionist_row_fields(row)
    if row.has_recall_pulse_plan:
        appointment_pay = calculate_recall_pulse_appointment_bonus(row.appointments_set)
    else:
        appointment_pay = row.appointments_set * row.appointment_rate
    tire_pay = row.tires_sold * row.tire_rate

    warranty_pay = 0.0
    if row.has_warranty_bonus and row.warranty_bonus_qualified:
        warranty_pay = row.warranty_bonus_amount

    csi_pay = 0.0
    if row.has_csi_bonus:
        _, csi_pay = RECEPTIONIST_CSI_TIER_OPTIONS.get(row.csi_tier, RECEPTIONIST_CSI_TIER_OPTIONS[CSI_TIER_NONE])

    bonus_pay = row.bonus_amount if row.employee_type == TYPE_BONUS else 0.0
    stretch_pay = 0.0
    if row.has_recall_pulse_plan and row.stretch_bonus_qualified:
        stretch_pay = float(row.stretch_bonus_amount or RECALL_PULSE_STRETCH_BONUS)
    spiff_pay = row.spiff
    total_pay = appointment_pay + tire_pay + warranty_pay + csi_pay + bonus_pay + stretch_pay + spiff_pay

    return ReceptionistPayrollResult(
        appointment_pay=appointment_pay,
        tire_pay=tire_pay,
        warranty_pay=warranty_pay,
        csi_pay=csi_pay,
        bonus_pay=bonus_pay,
        stretch_pay=stretch_pay,
        spiff_pay=spiff_pay,
        total_pay=total_pay,
    )

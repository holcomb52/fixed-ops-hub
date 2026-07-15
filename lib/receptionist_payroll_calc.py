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


def recall_pulse_qualified_tier(appointments: float) -> tuple[str, float]:
    """Highest tier reached — that rate applies to every appointment in the period."""
    total_appts = max(int(appointments), 0)
    if total_appts >= 36:
        return "Tier 4 · 36+ appointments", 15.0
    if total_appts >= 26:
        return "Tier 3 · 26–35 appointments", 12.0
    if total_appts >= 16:
        return "Tier 2 · 16–25 appointments", 8.0
    if total_appts >= 1:
        return "Tier 1 · 1–15 appointments", 3.0
    return "No appointments", 0.0


def recall_pulse_rate_for_appointments(appointments: float) -> float:
    _, rate = recall_pulse_qualified_tier(appointments)
    return rate

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
    """Recall appointment bonus — highest tier reached pays that rate on all appts."""
    total_appts = max(int(appointments), 0)
    if total_appts == 0:
        return 0.0
    rate = recall_pulse_rate_for_appointments(total_appts)
    return total_appts * rate


def recall_pulse_tier_breakdown(appointments: float) -> list[tuple[str, float]]:
    """Human-readable pay line for UI and PDF detail."""
    total_appts = max(int(appointments), 0)
    if total_appts == 0:
        return []
    label, rate = recall_pulse_qualified_tier(total_appts)
    return [(f"{label}: {total_appts} × ${rate:.0f}", total_appts * rate)]


def describe_recall_pulse_appointment_pay(appointments: float) -> str:
    total_appts = max(int(appointments), 0)
    if total_appts == 0:
        return "0 recall appointments"
    label, rate = recall_pulse_qualified_tier(total_appts)
    return f"{total_appts} appts × ${rate:.0f} ({label})"


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

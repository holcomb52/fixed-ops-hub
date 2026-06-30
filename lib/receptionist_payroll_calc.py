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
    spiff_pay: float
    total_pay: float


def ensure_receptionist_row_fields(row: ReceptionistPayrollRow) -> ReceptionistPayrollRow:
    if not hasattr(row, "has_csi_bonus"):
        row.has_csi_bonus = False
    if not hasattr(row, "csi_tier"):
        row.csi_tier = CSI_TIER_NONE
    return row


def calculate_receptionist_payroll(row: ReceptionistPayrollRow) -> ReceptionistPayrollResult:
    ensure_receptionist_row_fields(row)
    appointment_pay = row.appointments_set * row.appointment_rate
    tire_pay = row.tires_sold * row.tire_rate

    warranty_pay = 0.0
    if row.has_warranty_bonus and row.warranty_bonus_qualified:
        warranty_pay = row.warranty_bonus_amount

    csi_pay = 0.0
    if row.has_csi_bonus:
        _, csi_pay = RECEPTIONIST_CSI_TIER_OPTIONS.get(row.csi_tier, RECEPTIONIST_CSI_TIER_OPTIONS[CSI_TIER_NONE])

    bonus_pay = row.bonus_amount if row.employee_type == TYPE_BONUS else 0.0
    spiff_pay = row.spiff
    total_pay = appointment_pay + tire_pay + warranty_pay + csi_pay + bonus_pay + spiff_pay

    return ReceptionistPayrollResult(
        appointment_pay=appointment_pay,
        tire_pay=tire_pay,
        warranty_pay=warranty_pay,
        csi_pay=csi_pay,
        bonus_pay=bonus_pay,
        spiff_pay=spiff_pay,
        total_pay=total_pay,
    )

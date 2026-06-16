"""Receptionist / cashier payroll calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

TIRE_PAY_RATE = 5.0
DEFAULT_WARRANTY_BONUS = 100.0

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
    bonus_amount: float = 0.0
    bonus_label: str = ""
    spiff: float = 0.0
    notes: str = ""


@dataclass
class ReceptionistPayrollResult:
    appointment_pay: float
    tire_pay: float
    warranty_pay: float
    bonus_pay: float
    spiff_pay: float
    total_pay: float


def calculate_receptionist_payroll(row: ReceptionistPayrollRow) -> ReceptionistPayrollResult:
    appointment_pay = row.appointments_set * row.appointment_rate
    tire_pay = row.tires_sold * row.tire_rate

    warranty_pay = 0.0
    if row.has_warranty_bonus and row.warranty_bonus_qualified:
        warranty_pay = row.warranty_bonus_amount

    bonus_pay = row.bonus_amount if row.employee_type == TYPE_BONUS else 0.0
    spiff_pay = row.spiff
    total_pay = appointment_pay + tire_pay + warranty_pay + bonus_pay + spiff_pay

    return ReceptionistPayrollResult(
        appointment_pay=appointment_pay,
        tire_pay=tire_pay,
        warranty_pay=warranty_pay,
        bonus_pay=bonus_pay,
        spiff_pay=spiff_pay,
        total_pay=total_pay,
    )

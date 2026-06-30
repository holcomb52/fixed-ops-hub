"""Build receptionist payroll snapshot for PDF export."""

from __future__ import annotations

from typing import List

from lib.receptionist_payroll_calc import (
    TYPE_BONUS,
    TYPE_LABELS,
    TYPE_RECEPTIONIST,
    ReceptionistPayrollRow,
    ReceptionistPayrollResult,
)


def build_receptionist_payroll_snapshot(
    employees: List[ReceptionistPayrollRow],
    results: List[ReceptionistPayrollResult],
    pay_period: str,
) -> dict:
    rows = []
    grand_total = 0.0

    for employee, result in zip(employees, results):
        grand_total += result.total_pay
        rows.append({
            "name": employee.name,
            "employee_type": employee.employee_type,
            "type_label": TYPE_LABELS.get(employee.employee_type, employee.employee_type),
            "appointments_set": employee.appointments_set,
            "appointment_rate": employee.appointment_rate,
            "appointment_pay": result.appointment_pay,
            "tires_sold": employee.tires_sold,
            "tire_pay": result.tire_pay,
            "warranty_pay": result.warranty_pay,
            "warranty_bonus_qualified": employee.warranty_bonus_qualified,
            "csi_pay": result.csi_pay,
            "csi_tier": employee.csi_tier,
            "bonus_amount": employee.bonus_amount,
            "bonus_label": employee.bonus_label,
            "bonus_pay": result.bonus_pay,
            "spiff": result.spiff_pay,
            "notes": employee.notes,
            "total_pay": result.total_pay,
        })

    receptionist_count = sum(1 for e in employees if e.employee_type == TYPE_RECEPTIONIST)
    bonus_count = sum(1 for e in employees if e.employee_type == TYPE_BONUS)

    return {
        "pay_period": pay_period or "—",
        "employees": rows,
        "grand_total": grand_total,
        "employee_count": len(rows),
        "receptionist_count": receptionist_count,
        "bonus_count": bonus_count,
    }

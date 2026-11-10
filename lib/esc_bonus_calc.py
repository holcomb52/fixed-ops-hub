"""Extended Service Contract (ESC) claims bonus — Serenity Skinner pay plan addendum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

BONUS_RATE = 0.02  # 2% of parts + labor dollars actually paid to the store

ELIGIBLE_EMPLOYEES: List[str] = [
    "Serenity Skinner",
]


@dataclass
class EscBonusResult:
    employee_name: str
    bonus_month: str
    amount_paid: float
    chargebacks: float
    net_paid: float
    bonus_rate: float
    bonus_amount: float
    notes: str = ""
    paid_on_label: str = ""


def calculate_esc_bonus(
    *,
    employee_name: str,
    bonus_month: str,
    amount_paid: float,
    chargebacks: float = 0.0,
    notes: str = "",
    paid_on_label: str = "",
) -> EscBonusResult:
    paid = max(float(amount_paid or 0), 0.0)
    charged = max(float(chargebacks or 0), 0.0)
    net = max(paid - charged, 0.0)
    bonus = round(net * BONUS_RATE, 2)
    return EscBonusResult(
        employee_name=(employee_name or ELIGIBLE_EMPLOYEES[0]).strip(),
        bonus_month=bonus_month,
        amount_paid=paid,
        chargebacks=charged,
        net_paid=net,
        bonus_rate=BONUS_RATE,
        bonus_amount=bonus,
        notes=(notes or "").strip(),
        paid_on_label=paid_on_label,
    )


def result_to_dict(result: EscBonusResult) -> dict:
    return {
        "employee_name": result.employee_name,
        "bonus_month": result.bonus_month,
        "amount_paid": result.amount_paid,
        "chargebacks": result.chargebacks,
        "net_paid": result.net_paid,
        "bonus_rate": result.bonus_rate,
        "bonus_amount": result.bonus_amount,
        "notes": result.notes,
        "paid_on_label": result.paid_on_label,
    }


def inputs_from_snapshot(snapshot: dict) -> dict:
    return {
        "employee_name": snapshot.get("employee_name", ELIGIBLE_EMPLOYEES[0]),
        "bonus_month": snapshot.get("bonus_month", ""),
        "amount_paid": float(snapshot.get("amount_paid", 0) or 0),
        "chargebacks": float(snapshot.get("chargebacks", 0) or 0),
        "notes": snapshot.get("notes", ""),
        "paid_on_label": snapshot.get("paid_on_label", ""),
    }

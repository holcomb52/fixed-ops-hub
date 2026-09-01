"""CSI / NPS bonus calculation for reception team pay plan addendum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

BONUS_TOP = 1000.0
BONUS_MID = 500.0

ELIGIBLE_EMPLOYEES: List[str] = [
    "Serenity Skinner",
    "Brandy Sistrunk",
]


@dataclass
class CsiBonusResult:
    employee_name: str
    bonus_month: str
    store_nps: float
    national_average: float
    business_center_average: float
    tier_label: str
    bonus_amount: float
    notes: str = ""
    paid_on_label: str = ""


def calculate_csi_bonus(
    *,
    employee_name: str,
    bonus_month: str,
    store_nps: float,
    national_average: float,
    business_center_average: float,
    notes: str = "",
    paid_on_label: str = "",
) -> CsiBonusResult:
    nps = float(store_nps or 0)
    national = float(national_average or 0)
    bc = float(business_center_average or 0)

    if nps >= national:
        amount = BONUS_TOP
        tier = "At or above National Average"
    elif nps >= bc:
        amount = BONUS_MID
        tier = "Between Business Center Average and National Average"
    else:
        amount = 0.0
        tier = "Below Business Center Average — no bonus"

    return CsiBonusResult(
        employee_name=(employee_name or ELIGIBLE_EMPLOYEES[0]).strip(),
        bonus_month=bonus_month,
        store_nps=nps,
        national_average=national,
        business_center_average=bc,
        tier_label=tier,
        bonus_amount=round(amount, 2),
        notes=(notes or "").strip(),
        paid_on_label=paid_on_label,
    )


def result_to_dict(result: CsiBonusResult) -> dict:
    return {
        "employee_name": result.employee_name,
        "bonus_month": result.bonus_month,
        "store_nps": result.store_nps,
        "national_average": result.national_average,
        "business_center_average": result.business_center_average,
        "tier_label": result.tier_label,
        "bonus_amount": result.bonus_amount,
        "notes": result.notes,
        "paid_on_label": result.paid_on_label,
        "bonus_top": BONUS_TOP,
        "bonus_mid": BONUS_MID,
    }


def inputs_from_snapshot(snapshot: dict) -> dict:
    return {
        "employee_name": snapshot.get("employee_name", ELIGIBLE_EMPLOYEES[0]),
        "bonus_month": snapshot.get("bonus_month", ""),
        "store_nps": float(snapshot.get("store_nps", 0) or 0),
        "national_average": float(snapshot.get("national_average", 0) or 0),
        "business_center_average": float(snapshot.get("business_center_average", 0) or 0),
        "notes": snapshot.get("notes", ""),
        "paid_on_label": snapshot.get("paid_on_label", ""),
    }

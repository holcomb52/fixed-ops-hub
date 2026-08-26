"""Stocking recommendations from 6-month sales data."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Literal

from lib.parts_stocking_parser import SixMonthSalesLine

StockStatus = Literal["order", "ok", "overstock", "no_sales"]

STATUS_LABELS = {
    "order": "Order",
    "ok": "OK",
    "overstock": "Overstock",
    "no_sales": "No sales",
}


@dataclass
class StockingRecommendation:
    part_number: str
    description: str
    make: str
    source: str
    qoh: float
    sold_6mo: float
    cost: float
    monthly_demand: float
    target_on_hand: float
    order_qty: float
    order_cost: float
    months_of_supply: float
    status: StockStatus


@dataclass
class StockingPlan:
    target_months: float
    min_sold_6mo: float
    overstock_factor: float
    lines: List[StockingRecommendation]

    @property
    def order_lines(self) -> List[StockingRecommendation]:
        return [line for line in self.lines if line.status == "order"]

    @property
    def order_count(self) -> int:
        return len(self.order_lines)

    @property
    def order_total_cost(self) -> float:
        return round(sum(line.order_cost for line in self.order_lines), 2)

    @property
    def overstock_count(self) -> int:
        return sum(1 for line in self.lines if line.status == "overstock")


def _months_of_supply(qoh: float, monthly_demand: float) -> float:
    if monthly_demand <= 0:
        return float("inf") if qoh > 0 else 0.0
    return qoh / monthly_demand


def build_stocking_plan(
    lines: List[SixMonthSalesLine],
    *,
    target_months: float = 1.0,
    min_sold_6mo: float = 1.0,
    overstock_factor: float = 2.0,
) -> StockingPlan:
    """Recommend order qty and target on-hand from 6MS sales."""
    target_months = max(float(target_months or 0), 0.0)
    min_sold_6mo = max(float(min_sold_6mo or 0), 0.0)
    overstock_factor = max(float(overstock_factor or 2.0), 1.0)

    recommendations: List[StockingRecommendation] = []
    for line in lines:
        sold = max(float(line.sold_6mo or 0), 0.0)
        qoh = float(line.qoh or 0)
        cost = max(float(line.cost or 0), 0.0)
        monthly = sold / 6.0

        if sold <= 0:
            status: StockStatus = "no_sales"
            target_on_hand = 0.0
            order_qty = 0.0
        elif sold < min_sold_6mo:
            status = "no_sales"
            target_on_hand = 0.0
            order_qty = 0.0
        else:
            target_on_hand = float(math.ceil(monthly * target_months))
            shortfall = target_on_hand - qoh
            order_qty = float(math.ceil(shortfall)) if shortfall > 0 else 0.0
            if order_qty > 0:
                status = "order"
            elif qoh > target_on_hand * overstock_factor:
                status = "overstock"
            else:
                status = "ok"

        order_cost = round(order_qty * cost, 2)
        recommendations.append(
            StockingRecommendation(
                part_number=line.part_number,
                description=line.description,
                make=line.make,
                source=line.source,
                qoh=qoh,
                sold_6mo=sold,
                cost=cost,
                monthly_demand=round(monthly, 2),
                target_on_hand=target_on_hand,
                order_qty=order_qty,
                order_cost=order_cost,
                months_of_supply=round(_months_of_supply(qoh, monthly), 2),
                status=status,
            )
        )

    recommendations.sort(
        key=lambda row: (
            row.status != "order",
            -row.order_cost,
            -row.sold_6mo,
            row.part_number,
        )
    )
    return StockingPlan(
        target_months=target_months,
        min_sold_6mo=min_sold_6mo,
        overstock_factor=overstock_factor,
        lines=recommendations,
    )

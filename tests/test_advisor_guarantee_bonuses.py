"""Guarantee advisors: CSI / alignment / SPIFF stack on top of the weekly floor."""

from lib.advisor_payroll_calc import (
    ALIGNMENT_BONUS_AMOUNT,
    PLAN_NEW_ADVISORS_GUARANTEE,
    AdvisorPayrollRow,
    apply_plan_defaults,
    calculate_advisor_payroll,
)


def _row(**kwargs) -> AdvisorPayrollRow:
    row = AdvisorPayrollRow(name="Vincent Iorio", plan_type=PLAN_NEW_ADVISORS_GUARANTEE)
    apply_plan_defaults(row)
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_guarantee_floor_without_bonuses():
    result = calculate_advisor_payroll(_row(hours_sold=0.0), pay_period_weeks=2.0)
    assert result.guarantee_amount == 2000.0
    assert result.guarantee_active is True
    assert result.bonus_pay == 0.0
    assert result.total_pay == 2000.0


def test_alignment_and_csi_paid_on_top_of_guarantee():
    result = calculate_advisor_payroll(
        _row(
            hours_sold=75.6,
            alignment_bonus_qualified=True,
            csi_tier="top",
        ),
        pay_period_weeks=2.0,
    )
    assert result.guarantee_amount == 2000.0
    assert result.bonus_pay == ALIGNMENT_BONUS_AMOUNT + 1200.0
    assert result.total_pay == result.guarantee_amount + result.bonus_pay
    assert result.total_pay == 2000.0 + 500.0 + 1200.0


def test_spiff_paid_on_top_of_guarantee():
    result = calculate_advisor_payroll(
        _row(hours_sold=10.0, spiff=75.0),
        pay_period_weeks=2.0,
    )
    assert result.spiff_pay == 75.0
    assert result.total_pay == result.guarantee_amount + 75.0


def test_bonuses_still_paid_when_commission_beats_guarantee():
    result = calculate_advisor_payroll(
        _row(
            hours_sold=200.0,
            parts_sales=10000.0,
            alignment_bonus_qualified=True,
            csi_tier="middle",
        ),
        pay_period_weeks=2.0,
    )
    assert result.commission_total > result.guarantee_amount
    assert result.guarantee_active is False
    assert result.bonus_pay == ALIGNMENT_BONUS_AMOUNT + 750.0
    assert result.total_pay == result.commission_total + result.bonus_pay

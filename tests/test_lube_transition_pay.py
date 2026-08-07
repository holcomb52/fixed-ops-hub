"""Flat Rate Lube declining period-dollar guarantee (Gary Freeze / Christopher Ingram)."""

from lib.tech_payroll_calc import (
    FLAT_RATE_LUBE_RATE,
    PERIOD_DOLLAR_GUARANTEE_1175,
    TechPayrollRow,
)
from lib.tech_roster import (
    ROLE_OPTIONS,
    ensure_roster_defaults,
    role_option_key,
    _apply_role,
)


def _row(**kwargs) -> TechPayrollRow:
    defaults = dict(
        name="Gary Freeze",
        team="Derrick's Team",
        hourly_rate=FLAT_RATE_LUBE_RATE,
        pay_plan="period_dollar_guarantee",
        period_dollar_guarantee=PERIOD_DOLLAR_GUARANTEE_1175,
        tech_category="quick_lube",
    )
    defaults.update(kwargs)
    return TechPayrollRow(**defaults)


def test_guarantee_tops_up_when_flat_earnings_below_floor():
    row = _row(flat_rate_hours=40.0, dollars_earned=700.0)  # PDF dollars ignored
    assert row.flat_rate_earnings() == 40.0 * FLAT_RATE_LUBE_RATE  # 870
    assert row.flag_base_pay() == PERIOD_DOLLAR_GUARANTEE_1175
    assert row.guarantee_top_up() == PERIOD_DOLLAR_GUARANTEE_1175 - 870.0


def test_flat_earnings_paid_when_above_guarantee():
    row = _row(flat_rate_hours=60.0)  # 60 × 21.75 = 1305 > 1175
    assert row.flag_base_pay() == 60.0 * FLAT_RATE_LUBE_RATE
    assert row.guarantee_top_up() == 0.0


def test_no_guarantee_uses_hours_times_rate():
    row = _row(flat_rate_hours=50.0, period_dollar_guarantee=0.0, dollars_earned=999.0)
    assert row.flag_base_pay() == 50.0 * FLAT_RATE_LUBE_RATE
    assert row.guarantee_top_up() == 0.0


def test_production_bonus_still_applies_during_guarantee():
    row = _row(flat_rate_hours=85.0)  # above 80 → $3/hr
    assert row.production_bonus == 85.0 * 3
    assert row.flag_base_pay() == 85.0 * FLAT_RATE_LUBE_RATE  # exceeds guarantee


def test_roster_migrates_old_gary_and_chris_once():
    teams = {
        "Derrick's Team": [
            TechPayrollRow(
                name="Gary Freeze",
                team="Derrick's Team",
                hourly_rate=17.5,
                tech_category="quick_lube",
                pay_plan="standard",
            ),
            TechPayrollRow(
                name="Christopher Ingram",
                team="Derrick's Team",
                hourly_rate=15.0,
                tech_category="apprentice",
                pay_plan="standard",
            ),
        ]
    }
    assert ensure_roster_defaults(teams) is True
    for row in teams["Derrick's Team"]:
        assert row.pay_plan == "period_dollar_guarantee"
        assert row.hourly_rate == FLAT_RATE_LUBE_RATE
        assert row.period_dollar_guarantee == PERIOD_DOLLAR_GUARANTEE_1175
        assert row.tech_category == "quick_lube"

    # Second load must not reset stage if clerk advanced to $590
    teams["Derrick's Team"][0].period_dollar_guarantee = 590.0
    assert ensure_roster_defaults(teams) is False
    assert teams["Derrick's Team"][0].period_dollar_guarantee == 590.0


def test_role_options_set_rate_and_guarantee_band():
    row = TechPayrollRow(name="X", team="T", hourly_rate=10.0)
    key = "Flat Rate Lube — Guar $590 (periods 3–4)"
    assert key in ROLE_OPTIONS
    _apply_role(row, key, [row], 0)
    assert row.hourly_rate == FLAT_RATE_LUBE_RATE
    assert row.period_dollar_guarantee == 590.0
    assert role_option_key(row) == key

"""Gregory Phillips tiered flag-rate pay plan."""

from lib.tech_payroll_calc import (
    TIERED_FLAG_RATE_BASE,
    TechPayrollRow,
    tiered_flag_rate_for_hours,
)
from lib.tech_roster import ensure_roster_defaults, role_option_key, _apply_role


def test_tier_boundaries():
    assert tiered_flag_rate_for_hours(0) == 45.0
    assert tiered_flag_rate_for_hours(62.5) == 45.0
    assert tiered_flag_rate_for_hours(62.51) == 50.0
    assert tiered_flag_rate_for_hours(79.9) == 50.0
    assert tiered_flag_rate_for_hours(80.0) == 53.0
    assert tiered_flag_rate_for_hours(89.9) == 53.0
    assert tiered_flag_rate_for_hours(90.0) == 54.0
    assert tiered_flag_rate_for_hours(99.9) == 54.0
    assert tiered_flag_rate_for_hours(100.0) == 55.0
    assert tiered_flag_rate_for_hours(149.9) == 55.0
    assert tiered_flag_rate_for_hours(150.0) == 65.0


def test_base_band_no_top_off():
    row = TechPayrollRow(
        name="Gregory Phillips",
        team="Derrick's Team",
        hourly_rate=TIERED_FLAG_RATE_BASE,
        pay_plan="tiered_flag_rate",
        flat_rate_hours=60.0,
    )
    assert row.display_flag_dollars() == 60.0 * 45
    assert row.flag_base_pay() == 60.0 * 45
    assert row.guarantee_top_up() == 0.0
    assert row.production_bonus == 0.0


def test_top_off_is_tier_minus_base():
    row = TechPayrollRow(
        name="Gregory Phillips",
        team="Derrick's Team",
        hourly_rate=TIERED_FLAG_RATE_BASE,
        pay_plan="tiered_flag_rate",
        flat_rate_hours=85.0,  # $53/hr
    )
    base = 85.0 * 45
    paid = 85.0 * 53
    assert row.display_flag_dollars() == base
    assert row.flag_base_pay() == paid
    assert row.guarantee_top_up() == paid - base
    assert row.total_pay() == paid


def test_top_tier_150():
    row = TechPayrollRow(
        name="Gregory Phillips",
        team="Derrick's Team",
        hourly_rate=TIERED_FLAG_RATE_BASE,
        pay_plan="tiered_flag_rate",
        flat_rate_hours=150.0,
    )
    assert row.flag_base_pay() == 150.0 * 65
    assert row.guarantee_top_up() == 150.0 * (65 - 45)


def test_roster_adds_gregory_with_plan():
    teams = {"Derrick's Team": [], "Olan's Team": []}
    assert ensure_roster_defaults(teams) is True
    names = {r.name for rows in teams.values() for r in rows}
    assert "Gregory Phillips" in names
    greg = next(r for rows in teams.values() for r in rows if r.name == "Gregory Phillips")
    assert greg.pay_plan == "tiered_flag_rate"
    assert greg.hourly_rate == TIERED_FLAG_RATE_BASE
    assert role_option_key(greg) == "Shop Tech — Tiered flag rate ($45+)"


def test_role_sets_tiered_plan():
    row = TechPayrollRow(name="X", team="T", hourly_rate=20.0)
    _apply_role(row, "Shop Tech — Tiered flag rate ($45+)", [row], 0)
    assert row.pay_plan == "tiered_flag_rate"
    assert row.hourly_rate == TIERED_FLAG_RATE_BASE

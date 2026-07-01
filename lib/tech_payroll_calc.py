"""Technician payroll calculations — mirrors TECH PAYROLL.xlsx logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

WEEKLY_HOUR_GUARANTEE_DEFAULT = 40.0


@dataclass
class TechPayrollRow:
    name: str
    team: str
    tech_number: str = ""
    hourly_rate: float = 0.0
    flat_rate_hours: float = 0.0
    dollars_earned: float = 0.0
    training_hours: float = 0.0
    spiff: float = 0.0
    notes: str = ""
    foreman_rule: str = "none"  # none | team_per_hr_2 | team_per_hr_1
    quick_lube_sources: List[str] = field(default_factory=list)
    tech_category: str = "shop"  # shop | apprentice | quick_lube — supplemental bonus is shop only
    cp_hours: float = 0.0
    cp_ro_count: int = 0
    cp_hrs_per_ro: float = 0.0
    closing_pct: float = 0.0
    supplemental_bonus: float = 0.0
    supplemental_tier: str = ""
    pay_plan: str = "standard"  # standard | weekly_hour_guarantee
    weekly_hour_guarantee: float = 0.0

    @property
    def effective_flag_rate(self) -> float:
        if self.flat_rate_hours > 0:
            return self.dollars_earned / self.flat_rate_hours
        return self.hourly_rate

    def guaranteed_hours_floor(self, pay_period_weeks: float) -> float:
        if self.pay_plan != "weekly_hour_guarantee" or self.weekly_hour_guarantee <= 0:
            return 0.0
        return self.weekly_hour_guarantee * max(pay_period_weeks, 0.0)

    def payable_flag_hours(self, pay_period_weeks: float) -> float:
        return max(self.flat_rate_hours, self.guaranteed_hours_floor(pay_period_weeks))

    def flag_base_pay(self, pay_period_weeks: float = 2.0) -> float:
        """Flag dollars with weekly hour guarantee applied when configured."""
        if self.pay_plan != "weekly_hour_guarantee" or self.weekly_hour_guarantee <= 0:
            return self.dollars_earned
        return self.payable_flag_hours(pay_period_weeks) * self.effective_flag_rate

    def guarantee_top_up(self, pay_period_weeks: float = 2.0) -> float:
        if self.pay_plan != "weekly_hour_guarantee":
            return 0.0
        return max(self.flag_base_pay(pay_period_weeks) - self.dollars_earned, 0.0)

    def guarantee_label(self, pay_period_weeks: float = 2.0) -> str:
        if self.pay_plan != "weekly_hour_guarantee" or self.weekly_hour_guarantee <= 0:
            return ""
        floor_hrs = self.guaranteed_hours_floor(pay_period_weeks)
        payable_hrs = self.payable_flag_hours(pay_period_weeks)
        if payable_hrs <= self.flat_rate_hours:
            return f"{self.weekly_hour_guarantee:.0f} hr/wk guarantee met by flag hours"
        return (
            f"{self.weekly_hour_guarantee:.0f} hr/wk guarantee · "
            f"{self.flat_rate_hours:.2f} flag hrs → {payable_hrs:.2f} paid hrs"
        )

    @property
    def prod_tier(self) -> Optional[tuple]:
        """Highest production bonus tier this tech qualifies for, or None."""
        return qualifying_prod_tier(self.flat_rate_hours)

    @property
    def prod_bonus_rate(self) -> float:
        """$/hr retro rate from the highest tier met."""
        tier = self.prod_tier
        return float(tier[1]) if tier else 0.0

    @property
    def production_bonus(self) -> float:
        """All flag hours × qualified $/hr when threshold is met (retro to period start)."""
        rate = self.prod_bonus_rate
        if not rate:
            return 0.0
        return self.flat_rate_hours * rate

    @property
    def training_pay(self) -> float:
        return self.training_hours * self.hourly_rate

    def foreman_bonus(self, team_total_hours: float, hours_by_name: Dict[str, float]) -> float:
        if self.foreman_rule == "team_per_hr_2":
            return team_total_hours * 2
        if self.foreman_rule == "team_per_hr_1":
            return team_total_hours * 1
        return 0.0

    def quick_lube_hours(self, hours_by_name: Dict[str, float]) -> float:
        """Sum of flag hours from quick-lube techs Noah earns bonus on."""
        if not self.quick_lube_sources:
            return 0.0
        return sum(hours_by_name.get(n, 0.0) for n in self.quick_lube_sources)

    def quick_lube_bonus(self, hours_by_name: Dict[str, float]) -> float:
        """Quick lube production bonus: selected tech hours × $1."""
        return self.quick_lube_hours(hours_by_name) * 1

    def foreman_bonus_label(self, team_total_hours: float) -> str:
        if self.foreman_rule == "team_per_hr_2":
            return f"All team hrs (incl. yours) {team_total_hours:.2f} × $2"
        if self.foreman_rule == "team_per_hr_1":
            return f"All team hrs (incl. yours) {team_total_hours:.2f} × $1"
        return ""

    def quick_lube_bonus_label(self, hours_by_name: Dict[str, float]) -> str:
        hrs = self.quick_lube_hours(hours_by_name)
        return f"Quick lube hrs {hrs:.2f} × $1"

    def total_pay(
        self,
        team_total_hours: float = 0.0,
        hours_by_name: Optional[Dict[str, float]] = None,
        pay_period_weeks: float = 2.0,
    ) -> float:
        hours_by_name = hours_by_name or {}
        return (
            self.flag_base_pay(pay_period_weeks)
            + self.production_bonus
            + self.supplemental_bonus
            + self.training_pay
            + self.foreman_bonus(team_total_hours, hours_by_name)
            + self.spiff
        )


# Quick-lube techs — Noah earns their combined flag hours × $1 (per TECH PAYROLL.xlsx col I)
QUICK_LUBE_TECHS = [
    "Charles Hinxman",
    "Christopher Ingram",
    "Gary Freeze",
    "Noah Ihnken",
    "Armand Liebes",
    "Zihair Busch",
]

# Techs in the Quick Lube Tech role (supplemental hrs/RO bonus does not apply).
QUICK_LUBE_TECH_CATEGORY_NAMES = [
    "Charles Hinxman",
    "Christopher Ingram",
    "Gary Freeze",
    "Armand Liebes",
    "Zihair Busch",
]


def supplemental_bonus_eligible(row: TechPayrollRow) -> bool:
    """Supplemental CP/close bonus applies to Shop Techs only."""
    return (
        row.tech_category == "shop"
        and row.foreman_rule == "none"
        and not row.quick_lube_sources
    )


def infer_tech_category(name: str, saved_category: str = "") -> str:
    if saved_category in ("shop", "apprentice", "quick_lube"):
        return saved_category
    if name in QUICK_LUBE_TECH_CATEGORY_NAMES:
        return "quick_lube"
    return "shop"


def ensure_tech_row_fields(row: TechPayrollRow) -> TechPayrollRow:
    """Backfill fields added after a row was created (live sessions / old saves)."""
    if not hasattr(row, "tech_category"):
        row.tech_category = infer_tech_category(row.name)
    if not hasattr(row, "pay_plan"):
        row.pay_plan = "standard"
    if not hasattr(row, "weekly_hour_guarantee"):
        row.weekly_hour_guarantee = 0.0
    if not hasattr(row, "cp_hours"):
        row.cp_hours = 0.0
    if not hasattr(row, "cp_ro_count"):
        row.cp_ro_count = 0
    if not hasattr(row, "cp_hrs_per_ro"):
        row.cp_hrs_per_ro = 0.0
    if not hasattr(row, "closing_pct"):
        row.closing_pct = 0.0
    if not hasattr(row, "supplemental_bonus"):
        row.supplemental_bonus = 0.0
    if not hasattr(row, "supplemental_tier"):
        row.supplemental_tier = ""
    return row


def normalize_teams(teams: Dict[str, List[TechPayrollRow]]) -> Dict[str, List[TechPayrollRow]]:
    for rows in teams.values():
        for i, row in enumerate(rows):
            rows[i] = ensure_tech_row_fields(row)
    return teams

# Tech numbers from flag sheet PDF (Tech# column)
DEFAULT_TECH_NUMBERS = {
    "Derrick Opp": "900798",
    "Quran Henry": "3707",
    "Carson Linker": "3788",
    "Kenneth Peterson": "3638",
    "Damian Blair": "3802",
    "John Richardson": "3811",
    "Charles Hinxman": "3520",
    "Christopher Ingram": "3824",
    "Gary Freeze": "3849",
    "Michael Holland": "3820",
    "Olan Halcomb": "46251",
    "George Webb": "3741",
    "Marvin Granick": "3694",
    "Noah Ihnken": "3725",
    "Dennis Pino": "3836",
    "Thomas Wyke": "3600",
    "Armand Liebes": "3662",
    "Dax Rosencrantz": "3851",
    "Zachary Daniels": "3854",
    "Zihair Busch": "3814",
    "Dale Potts": "3858",
}


def parse_period_token(token: str) -> Optional[date]:
    token = (token or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def weeks_in_pay_period(pay_period: str) -> float:
    if not pay_period or "-" not in pay_period:
        return 2.0
    start_text, end_text = pay_period.split("-", 1)
    start = parse_period_token(start_text)
    end = parse_period_token(end_text)
    if not start or not end or end < start:
        return 2.0
    return max(((end - start).days + 1) / 7.0, 1.0)


def _default_row(
    name: str,
    team: str,
    hourly_rate: float,
    **kwargs,
) -> TechPayrollRow:
    return TechPayrollRow(
        name,
        team,
        tech_number=DEFAULT_TECH_NUMBERS.get(name, ""),
        hourly_rate=hourly_rate,
        **kwargs,
    )


# Default roster pulled from 05/20/26–06/02/26 TECH PAYROLL.xlsx
DEFAULT_TEAMS = {
    "Derrick's Team": [
        _default_row("Derrick Opp", "Derrick's Team", 45, foreman_rule="team_per_hr_2"),
        _default_row("Quran Henry", "Derrick's Team", 25),
        _default_row("Carson Linker", "Derrick's Team", 17),
        _default_row("Kenneth Peterson", "Derrick's Team", 35),
        _default_row("Damian Blair", "Derrick's Team", 30),
        _default_row("John Richardson", "Derrick's Team", 25),
        _default_row("Charles Hinxman", "Derrick's Team", 22.75, tech_category="quick_lube"),
        _default_row("Christopher Ingram", "Derrick's Team", 15, tech_category="quick_lube"),
        _default_row("Gary Freeze", "Derrick's Team", 17.5, tech_category="quick_lube"),
        _default_row("Michael Holland", "Derrick's Team", 15),
    ],
    "Olan's Team": [
        _default_row("Olan Halcomb", "Olan's Team", 45, foreman_rule="team_per_hr_1"),
        _default_row("George Webb", "Olan's Team", 32),
        _default_row("Marvin Granick", "Olan's Team", 30.5),
        _default_row(
            "Noah Ihnken",
            "Olan's Team",
            15,
            quick_lube_sources=QUICK_LUBE_TECHS,
        ),
        _default_row("Dennis Pino", "Olan's Team", 29),
        _default_row("Thomas Wyke", "Olan's Team", 30),
        _default_row("Armand Liebes", "Olan's Team", 22.75, tech_category="quick_lube"),
        _default_row("Dax Rosencrantz", "Olan's Team", 27),
        _default_row("Zachary Daniels", "Olan's Team", 14),
        _default_row("Zihair Busch", "Olan's Team", 15, tech_category="quick_lube"),
        _default_row(
            "Dale Potts",
            "Olan's Team",
            28,
            pay_plan="weekly_hour_guarantee",
            weekly_hour_guarantee=WEEKLY_HOUR_GUARANTEE_DEFAULT,
        ),
    ],
}

PROD_BONUS_TIERS = [
    (80, 3, "$3/hr retro from start of pay period"),
    (90, 4, "$4/hr retro from start of pay period"),
    (100, 5, "$5/hr retro from start of pay period"),
    (150, 7, "$7/hr retro from start of pay period"),
]


def qualifying_prod_tier(hours: float) -> Optional[tuple]:
    """
    Return the highest tier (threshold, $/hr, description) the tech qualifies for.
    Tiers are checked highest threshold first so the best rate applies.
    """
    qualified = None
    for threshold, dollars_per_hour, description in PROD_BONUS_TIERS:
        if hours >= threshold:
            qualified = (threshold, dollars_per_hour, description)
    return qualified


def prod_tier_label(hours: float) -> str:
    tier = qualifying_prod_tier(hours)
    if not tier:
        return "No bonus (< 80 hrs)"
    threshold, dollars_per_hour, _ = tier
    return f"{threshold}+ hrs → ${dollars_per_hour}/hr on all {hours:.2f} hrs"


def apply_flag_data(rows: List[TechPayrollRow], flag_by_name: Dict[str, tuple]) -> None:
    """Apply PDF hours/dollars to roster rows. flag_by_name: name -> (hours, dollars)."""
    from lib.tech_flag_sync import _name_key, names_match

    for row in rows:
        if row.name in flag_by_name:
            hours, dollars = flag_by_name[row.name]
            row.flat_rate_hours = hours
            row.dollars_earned = dollars
            continue
        name_key = _name_key(row.name)
        if name_key in flag_by_name:
            hours, dollars = flag_by_name[name_key]
            row.flat_rate_hours = hours
            row.dollars_earned = dollars
            continue
        for flag_name, entry in flag_by_name.items():
            if names_match(row.name, flag_name):
                row.flat_rate_hours, row.dollars_earned = entry
                break


def apply_tech_numbers(rows: List[TechPayrollRow], numbers_by_name: Dict[str, str]) -> int:
    """Apply tech numbers from flag sheet PDF. Returns count updated."""
    from lib.tech_flag_sync import _name_key, names_match

    updated = 0
    for row in rows:
        if row.tech_number:
            continue
        tech_number = numbers_by_name.get(row.name)
        if not tech_number:
            tech_number = numbers_by_name.get(_name_key(row.name))
        if not tech_number:
            for name, number in numbers_by_name.items():
                if names_match(row.name, name):
                    tech_number = number
                    break
        if tech_number:
            row.tech_number = tech_number
            updated += 1
    return updated


def apply_cp_metrics(rows: List[TechPayrollRow], cp_by_name: Dict[str, dict]) -> None:
    """Apply CP hrs/RO metrics parsed from the flag sheet."""
    for row in rows:
        metrics = cp_by_name.get(row.name)
        if not metrics:
            continue
        row.cp_hours = float(metrics.get("cp_hours", 0) or 0)
        row.cp_ro_count = int(metrics.get("cp_ro_count", 0) or 0)
        row.cp_hrs_per_ro = float(metrics.get("cp_hrs_per_ro", 0) or 0)


def apply_closing_metrics(rows: List[TechPayrollRow], closing_by_name: Dict[str, float]) -> None:
    """Apply closing % from the Ignite upsell report."""
    for row in rows:
        if row.name in closing_by_name:
            row.closing_pct = float(closing_by_name[row.name] or 0)


def recalc_supplemental_bonuses(rows: List[TechPayrollRow]) -> None:
    """Calculate supplemental bonus from CP hrs/RO and closing % already on each row."""
    from lib.tech_supplemental_bonus import calc_supplemental_bonus

    for row in rows:
        if not supplemental_bonus_eligible(row):
            row.supplemental_bonus = 0.0
            row.supplemental_tier = ""
            continue
        bonus, tier = calc_supplemental_bonus(row.cp_hrs_per_ro, row.closing_pct)
        row.supplemental_bonus = bonus
        row.supplemental_tier = tier


def apply_supplemental_metrics(
    teams: Dict[str, List[TechPayrollRow]],
    cp_by_name: Optional[Dict[str, dict]] = None,
    closing_by_name: Optional[Dict[str, float]] = None,
) -> None:
    """Merge CP and closing metrics, then recalculate supplemental bonuses."""
    cp_by_name = cp_by_name or {}
    closing_by_name = closing_by_name or {}
    for rows in teams.values():
        apply_cp_metrics(rows, cp_by_name)
        apply_closing_metrics(rows, closing_by_name)
        recalc_supplemental_bonuses(rows)


def all_hours_by_name(teams: Dict[str, List[TechPayrollRow]]) -> Dict[str, float]:
    hours: Dict[str, float] = {}
    for rows in teams.values():
        for row in rows:
            hours[row.name] = row.flat_rate_hours
    return hours


def team_total_hours(rows: List[TechPayrollRow]) -> float:
    """Sum every tech on the team — including the foreman's own flag hours."""
    return sum(r.flat_rate_hours for r in rows)


def team_totals(
    rows: List[TechPayrollRow],
    hours_by_name: Optional[Dict[str, float]] = None,
    pay_period_weeks: float = 2.0,
) -> Dict[str, float]:
    team_hrs = team_total_hours(rows)
    hours_by_name = hours_by_name or {r.name: r.flat_rate_hours for r in rows}
    return {
        "hours": team_hrs,
        "dollars": sum(r.flag_base_pay(pay_period_weeks) for r in rows),
        "total_pay": sum(r.total_pay(team_hrs, hours_by_name, pay_period_weeks) for r in rows),
    }

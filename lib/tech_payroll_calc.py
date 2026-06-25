"""Technician payroll calculations — mirrors TECH PAYROLL.xlsx logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
    ) -> float:
        hours_by_name = hours_by_name or {}
        # Column K total — quick lube bonus (col I) is separate for Noah, not included here
        return (
            self.dollars_earned
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
}


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
    for row in rows:
        if row.name in flag_by_name:
            hours, dollars = flag_by_name[row.name]
            row.flat_rate_hours = hours
            row.dollars_earned = dollars


def apply_tech_numbers(rows: List[TechPayrollRow], numbers_by_name: Dict[str, str]) -> int:
    """Apply tech numbers from flag sheet PDF. Returns count updated."""
    updated = 0
    for row in rows:
        tech_number = numbers_by_name.get(row.name)
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
) -> Dict[str, float]:
    team_hrs = team_total_hours(rows)
    hours_by_name = hours_by_name or {r.name: r.flat_rate_hours for r in rows}
    return {
        "hours": team_hrs,
        "dollars": sum(r.dollars_earned for r in rows),
        "total_pay": sum(r.total_pay(team_hrs, hours_by_name) for r in rows),
    }

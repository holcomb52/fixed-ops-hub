"""Advisor roster remove must stick — no hard-coded re-add after Remove."""

from __future__ import annotations

import unittest

from lib.advisor_payroll_calc import PLAN_NEW_ADVISORS_GUARANTEE, PLAN_SEASONED
from lib.advisor_roster import (
    clone_roster,
    default_roster,
    ensure_guarantee_roster_advisors,
    remove_advisor,
    roster_from_saved_data,
    serialize_roster,
)


class AdvisorRosterRemoveTests(unittest.TestCase):
    def test_default_roster_excludes_brady(self):
        names = {row.name for rows in default_roster().values() for row in rows}
        self.assertNotIn("Brady Hatcher", names)
        self.assertIn("Shane Bueschel", names)

    def test_remove_brady_survives_ensure(self):
        roster = roster_from_saved_data(
            {
                PLAN_SEASONED: [],
                "new_advisors": [],
                PLAN_NEW_ADVISORS_GUARANTEE: [
                    {"name": "Brady Hatcher", "advisor_id": "3816"},
                    {"name": "Shane Bueschel", "advisor_id": "3859"},
                ],
            }
        )
        ok, msg = remove_advisor(roster, PLAN_NEW_ADVISORS_GUARANTEE, 0)
        self.assertTrue(ok)
        self.assertIn("Brady", msg)
        self.assertFalse(ensure_guarantee_roster_advisors(roster))
        names = {row.name for rows in roster.values() for row in rows}
        self.assertNotIn("Brady Hatcher", names)
        self.assertIn("Shane Bueschel", names)

    def test_ensure_does_not_insert_missing_brady(self):
        roster = clone_roster(default_roster())
        self.assertFalse(ensure_guarantee_roster_advisors(roster))
        data = serialize_roster(roster)
        self.assertFalse(
            any(row["name"] == "Brady Hatcher" for rows in data.values() for row in rows)
        )


if __name__ == "__main__":
    unittest.main()

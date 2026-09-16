"""Role-based login helpers for Fixed Ops Hub."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from lib.app_auth import (
    PARTS_MANAGER_PAGES,
    ROLE_ADMIN,
    ROLE_PARTS_MANAGER,
    allowed_pages,
    default_page_for_role,
    needs_password_warning,
    resolve_login,
    _secret,
)


class AppAuthTests(unittest.TestCase):
    def test_admin_password_wins_full_access(self):
        role, label = resolve_login(
            "boss",
            admin_password="boss",
            parts_manager_password="parts",
        )
        self.assertEqual(role, ROLE_ADMIN)
        self.assertEqual(label, "Admin")

    def test_parts_manager_password(self):
        role, label = resolve_login(
            "parts-secret",
            admin_password="boss",
            parts_manager_password="parts-secret",
            parts_manager_label="Parts Manager",
        )
        self.assertEqual(role, ROLE_PARTS_MANAGER)
        self.assertEqual(label, "Parts Manager")

    def test_wrong_password(self):
        self.assertIsNone(
            resolve_login(
                "nope",
                admin_password="boss",
                parts_manager_password="parts",
            )
        )

    def test_parts_manager_pages_are_limited(self):
        self.assertEqual(allowed_pages(ROLE_PARTS_MANAGER), PARTS_MANAGER_PAGES)
        self.assertEqual(default_page_for_role(ROLE_PARTS_MANAGER), "Parts")
        self.assertIn("Payroll", allowed_pages(ROLE_ADMIN))
        self.assertNotIn("Payroll", allowed_pages(ROLE_PARTS_MANAGER))

    def test_env_secret_wins_over_empty_streamlit_secrets(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "env-boss"}, clear=False):
            self.assertEqual(_secret("APP_PASSWORD"), "env-boss")

    def test_password_warning_when_database_is_public(self):
        self.assertTrue(needs_password_warning(database_configured=True, auth_on=False))
        self.assertFalse(needs_password_warning(database_configured=True, auth_on=True))
        self.assertFalse(needs_password_warning(database_configured=False, auth_on=False))


if __name__ == "__main__":
    unittest.main()

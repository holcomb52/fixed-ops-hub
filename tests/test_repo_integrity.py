"""Guards for setup-path and packaging issues found in the audit."""

from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path

from lib.page_ui import html_text, status_banner
from lib.supabase_client import jwt_role
from repo_path import LOCAL_LIB_INIT, prepare_local_lib_imports

ROOT = Path(__file__).resolve().parent.parent


class RepoIntegrityTests(unittest.TestCase):
    def test_env_example_is_present_and_not_gitignored(self):
        example = ROOT / ".env.example"
        self.assertTrue(example.exists(), "README tells users to copy .env.example")
        gitignore = (ROOT / ".gitignore").read_text()
        self.assertIn("!.env.example", gitignore)
        text = example.read_text()
        self.assertIn("SUPABASE_URL=", text)
        self.assertIn("SUPABASE_KEY=", text)
        self.assertNotIn("eyJ", text)

    def test_schema_includes_advisor_training_and_rls(self):
        schema = (ROOT / "supabase" / "schema.sql").read_text()
        self.assertIn("create table if not exists advisor_training_logs", schema)
        self.assertIn("alter table advisor_training_logs enable row level security", schema)
        self.assertIn("alter table tech_payroll_runs enable row level security", schema)
        self.assertNotIn("Alex Rivera", schema)
        self.assertTrue((ROOT / "supabase" / "enable_rls.sql").exists())

    def test_macos_scripts_use_repo_relative_paths(self):
        for rel in (
            "scripts/start-fixed-ops-hub.sh",
            "scripts/open-fixed-ops-hub.sh",
            "scripts/install-autostart.sh",
            "scripts/create-macos-app.sh",
            "scripts/com.fixedopshub.streamlit.plist",
        ):
            text = (ROOT / rel).read_text()
            self.assertNotIn("/Users/bigstud", text, rel)
            self.assertNotIn("/Library/Python/3.9/bin/streamlit", text, rel)

    def test_lib_package_does_not_reexport_streamlit_client(self):
        import lib

        self.assertFalse(hasattr(lib, "get_supabase"))
        self.assertFalse(hasattr(lib, "is_configured"))

    def test_jwt_role_reads_claim_without_network(self):
        payload = (
            base64.urlsafe_b64encode(json.dumps({"role": "anon"}).encode("ascii"))
            .decode("ascii")
            .rstrip("=")
        )
        self.assertEqual(jwt_role(f"aaa.{payload}.sig"), "anon")
        self.assertEqual(jwt_role("not-a-jwt"), "")

    def test_html_text_escapes_markup(self):
        self.assertEqual(html_text("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")
        banner = status_banner("failed: <b>nope</b>", "warn")
        self.assertIn("&lt;b&gt;nope&lt;/b&gt;", banner)
        self.assertNotIn("<b>nope</b>", banner)

    def test_prepare_local_lib_wins_over_venv_lib(self):
        """Streamlit Cloud's venv/lib directory must not shadow repo lib.app_auth."""
        import sys
        import types

        fake = types.ModuleType("lib")
        fake.__file__ = "/tmp/fake-venv/lib/not-the-app.py"
        fake.__path__ = ["/tmp/fake-venv/lib"]
        saved = {
            key: sys.modules[key]
            for key in list(sys.modules)
            if key == "lib" or key.startswith("lib.")
        }
        for key in saved:
            del sys.modules[key]
        sys.modules["lib"] = fake
        try:
            with self.assertRaises(ImportError):
                from lib.app_auth import require_login  # noqa: F401

            prepare_local_lib_imports()
            from lib.app_auth import needs_password_warning, require_login

            self.assertTrue(callable(require_login))
            self.assertTrue(callable(needs_password_warning))
            self.assertEqual(
                Path(sys.modules["lib"].__file__).resolve(),
                LOCAL_LIB_INIT.resolve(),
            )
        finally:
            for key in list(sys.modules):
                if key == "lib" or key.startswith("lib."):
                    del sys.modules[key]
            sys.modules.update(saved)

    def test_app_py_imports_current_app_auth_names(self):
        text = (ROOT / "app.py").read_text()
        for name in (
            "allowed_pages",
            "auth_enabled",
            "needs_password_warning",
            "require_login",
            "sign_out",
        ):
            self.assertIn(name, text)
        self.assertIn("prepare_local_lib_imports()", text)
        self.assertNotIn("if _PY >= (3, 13)", text)
        app_auth = (ROOT / "lib" / "app_auth.py").read_text()
        self.assertIn("def needs_password_warning", app_auth)
        self.assertIn("def auth_enabled", app_auth)


if __name__ == "__main__":
    unittest.main()

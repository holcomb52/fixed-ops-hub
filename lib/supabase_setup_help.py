"""User-facing help when Supabase tables are missing."""

from __future__ import annotations

from pathlib import Path

_MIGRATION_PATH = Path(__file__).resolve().parent.parent / "supabase" / "advisor_receptionist_payroll_tables.sql"

_TABLE_FIXES = {
    "advisor_payroll_runs": _MIGRATION_PATH,
    "receptionist_payroll_runs": _MIGRATION_PATH,
}


def payroll_sync_error_message(raw_error: str, table: str = "") -> str:
    """Turn a Supabase sync failure into actionable steps."""
    text = str(raw_error or "")
    missing_table = table
    if "Could not find the table" in text:
        for name in _TABLE_FIXES:
            if name in text:
                missing_table = name
                break

    if missing_table in _TABLE_FIXES or "PGRST205" in text:
        return (
            "Cloud backup failed because a Supabase table is missing. "
            "Payroll still works in this session, but it will not appear in Reports after you close the app.\n\n"
            "Fix (one time): Open your Supabase project → SQL Editor → New query → "
            "paste the SQL from the expander below (or supabase/advisor_receptionist_payroll_tables.sql) → Run → "
            "refresh this app and save payroll again."
        )

    return (
        "Cloud backup failed — this payroll may disappear from Reports after you close the app. "
        f"Details: {text}"
    )


def missing_payroll_tables_sql() -> str:
    if _MIGRATION_PATH.exists():
        return _MIGRATION_PATH.read_text()
    return ""

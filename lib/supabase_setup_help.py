"""User-facing help when Supabase tables are missing."""

from __future__ import annotations

from pathlib import Path

_SCHEMA_FILE = Path(__file__).resolve().parent.parent / "supabase" / "schema.sql"
_MIGRATION_FILES = [
    Path(__file__).resolve().parent.parent / "supabase" / "advisor_receptionist_payroll_tables.sql",
    Path(__file__).resolve().parent.parent / "supabase" / "payroll_rosters_table.sql",
]

_TABLE_FIXES = {
    "advisor_payroll_runs": "advisor",
    "receptionist_payroll_runs": "advisor",
    "payroll_rosters": "roster",
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

    if "payroll_rosters" in text:
        return (
            "Roster changes could not be saved to the cloud. "
            "They will reset when you log out unless the payroll_rosters table exists in Supabase.\n\n"
            "Fix (one time): Open Supabase → SQL Editor → run the SQL in the expander below, "
            "then make your roster change again."
        )

    if missing_table in _TABLE_FIXES or "PGRST205" in text:
        return (
            "Cloud backup failed because a Supabase table is missing. "
            "Payroll still works in this session, but it will not appear in Reports after you close the app.\n\n"
            "Fix (one time): Open your Supabase project → SQL Editor → New query → "
            "paste the SQL from the expander below → Run → refresh this app."
        )

    return (
        "Cloud backup failed — this payroll may disappear from Reports after you close the app. "
        f"Details: {text}"
    )


def missing_payroll_tables_sql() -> str:
    if _SCHEMA_FILE.exists():
        return _SCHEMA_FILE.read_text().strip()
    parts = []
    for path in _MIGRATION_FILES:
        if path.exists():
            parts.append(path.read_text().strip())
    return "\n\n".join(parts)

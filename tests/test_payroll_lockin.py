"""Lock-in regressions for the July 2026 payroll hardening.

These tests guard the bugs that made that payroll slow and painful:
jammed CDK flag lines, NaN cloud backup, CASHIERS roster matching
(Megan Schneider / 22SCHNEIDERM), and draft saves that skip cloud sync.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import openpyxl

from lib.flag_pdf_parser import (
    FlagSheetParseResult,
    PDF_NAME_MAP,
    TechFlagData,
    _parse_detail_line,
    normalize_tech_name,
)
from lib.json_safe import json_safe
from lib.payroll_storage import save_payroll_run
from lib.receptionist_payroll_calc import (
    calculate_recall_pulse_appointment_bonus,
    calculate_receptionist_payroll,
    ReceptionistPayrollRow,
)
from lib.receptionist_payroll_parser import (
    cashiers_appointment_count_for_row,
    last_name_from_taker_code,
    parse_cashiers_report,
    report_by_code,
    report_by_last_name,
    skips_cashiers_appointment_import,
)
from lib.receptionist_roster import (
    default_roster,
    ensure_known_receptionists,
    flatten_roster,
)
from lib.tech_flag_sync import apply_flag_to_teams
from lib.tech_payroll_calc import TechPayrollRow


REQUIRED_TECH_PDF_NAMES = {
    "CHARLES H": "Charles Hinxman",
    "ARMAND LIEBES": "Armand Liebes",
    "OLAN": "Olan Halcomb",
    "DERRICK OPP": "Derrick Opp",
    "QURAN HENRY": "Quran Henry",
    "NOAH IHNKEN": "Noah Ihnken",
}

REQUIRED_RECEPTIONIST_CODES = {
    "Megan Schneider": "22SCHNEIDERM",
    "Brandy Sistrunk": "22SISTRUNKB",
    "Misty Carver": "22CARVERM",
    "Jennifer Cleary": "22CLEARYJ",
    "Kayla Hoffman": "22HOFFMANK",
    "Samantha Rodriguez": "22RODRIGUEZS",
    "Serenity Skinner": "22SKINNERS",
}


def _cashiers_workbook_bytes(rows: list[tuple[str, int]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["APPT-TAKER-DR", "APPT-NO", "RO #", "RO DATE", "CUST NAME", "VIN", "APPT", "WALK IN"])
    for code, flagged in rows:
        ws.append([code, "1", "580000", None, "TEST", "VIN", flagged, None])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class PayrollLockinTests(unittest.TestCase):
    def test_required_tech_pdf_name_map_locked(self):
        for pdf_name, display in REQUIRED_TECH_PDF_NAMES.items():
            self.assertEqual(PDF_NAME_MAP[pdf_name], display)
            self.assertEqual(normalize_tech_name(pdf_name), display)

    def test_july_cdk_jammed_formats_still_parse(self):
        cases = [
            ("352007/15/2...Service 579963 01CHZ-TIRE4 0.00 1.10 22.... 25.03 5 Custo...I", 1.10, 25.03),
            ("352007/18/2...Service 580317 26CHZOILC... 0.30 22.... 6.83 3 InternalI", 0.30, 6.83),
            ("374107/28/2...Service 580462 05CHZZ1 0.00 -0.50 42.... -21.00 1 Warr... I", -0.50, -21.00),
        ]
        for line, hours, extended in cases:
            parsed = _parse_detail_line(line)
            self.assertIsNotNone(parsed, line)
            _, item = parsed
            self.assertEqual(item.booked_hours, hours)
            self.assertEqual(item.extended, extended)

    def test_flag_hours_apply_to_roster_by_name(self):
        teams = {
            "Olan's Team": [
                TechPayrollRow(name="Charles Hinxman", team="Olan's Team", tech_number="3520"),
            ]
        }
        parsed = FlagSheetParseResult(
            technicians=[
                TechFlagData(
                    pdf_name="CHARLES H",
                    display_name="Charles Hinxman",
                    tech_number="3520",
                    flat_rate_hours=119.8,
                    dollars_earned=2719.43,
                )
            ]
        )
        matched = apply_flag_to_teams(teams, parsed)
        self.assertEqual(matched, 1)
        self.assertEqual(teams["Olan's Team"][0].flat_rate_hours, 119.8)

    def test_default_roster_includes_megan_schneider(self):
        by_name = {row.name: row for row in flatten_roster(default_roster())}
        for name, code in REQUIRED_RECEPTIONIST_CODES.items():
            self.assertIn(name, by_name)
            self.assertIn(code, [c.upper() for c in by_name[name].taker_codes])

    def test_ensure_known_adds_megan_when_missing(self):
        roster = {
            "receptionist": [
                row
                for row in flatten_roster(default_roster())
                if row.name != "Megan Schneider"
            ]
        }
        self.assertTrue(ensure_known_receptionists(roster))
        megan = next(r for r in flatten_roster(roster) if "SCHNEIDER" in r.last_name.upper())
        self.assertIn("22SCHNEIDERM", [c.upper() for c in megan.taker_codes])

    def test_cashiers_import_matches_megan_21_appointments(self):
        payload = _cashiers_workbook_bytes(
            [("22SCHNEIDERM", 1)] * 21
            + [("22SISTRUNKB", 1)] * 3
            + [("22UNKNOWNX", 1)] * 2
        )
        rows = parse_cashiers_report(BytesIO(payload))
        by_code = report_by_code(rows)
        by_last = report_by_last_name(rows)
        self.assertEqual(by_code["22SCHNEIDERM"].appointments_set, 21)

        matched = {}
        for row in flatten_roster(default_roster()):
            total = cashiers_appointment_count_for_row(row, by_code, by_last)
            if total:
                matched[row.name] = total
        self.assertEqual(matched["Megan Schneider"], 21)
        self.assertNotIn("Brandy Sistrunk", matched)
        brandy = next(r for r in flatten_roster(default_roster()) if r.name == "Brandy Sistrunk")
        self.assertTrue(skips_cashiers_appointment_import(brandy))

    def test_taker_code_last_name_handles_digit_suffix(self):
        self.assertEqual(last_name_from_taker_code("22SCHNEIDERM"), "SCHNEIDER")
        self.assertEqual(last_name_from_taker_code("22MALDONADO1"), "MALDONADO")
        self.assertEqual(last_name_from_taker_code("22MALDONADOR"), "MALDONADO")

    def test_brandy_recall_pulse_override_math_locked(self):
        self.assertEqual(calculate_recall_pulse_appointment_bonus(50), 750.0)
        self.assertEqual(calculate_recall_pulse_appointment_bonus(67), 1005.0)
        row = ReceptionistPayrollRow(
            name="Brandy Sistrunk",
            has_recall_pulse_plan=True,
            appointments_set=50,
        )
        self.assertEqual(calculate_receptionist_payroll(row).appointment_pay, 750.0)

    def test_draft_payroll_save_skips_cloud_and_is_json_safe(self):
        import lib.payroll_storage as storage

        original_archive = storage.ARCHIVE_DIR
        original_get = storage.get_supabase
        try:
            with tempfile.TemporaryDirectory() as tmp:
                storage.ARCHIVE_DIR = Path(tmp)
                storage.get_supabase = lambda: None

                teams = {
                    "Olan's Team": [
                        TechPayrollRow(
                            name="Charles Hinxman",
                            team="Olan's Team",
                            flat_rate_hours=10.0,
                            dollars_earned=200.0,
                            closing_pct=float("nan"),
                        )
                    ]
                }
                run_id, err = save_payroll_run(
                    teams,
                    "07/15/26-07/28/26",
                    b"%PDF-1.4 draft-flag",
                    "flag.pdf",
                    status="draft",
                    cloud_sync=False,
                )
                self.assertEqual(err, "")
                self.assertTrue(run_id)
                record = (Path(tmp) / run_id / "record.json").read_text()
                self.assertNotIn("NaN", record)
                flag_path = Path(tmp) / run_id / "flag.pdf"
                mtime = flag_path.stat().st_mtime
                save_payroll_run(
                    teams,
                    "07/15/26-07/28/26",
                    b"%PDF-1.4 draft-flag",
                    "flag.pdf",
                    run_id=run_id,
                    status="draft",
                    cloud_sync=False,
                )
                self.assertEqual(flag_path.stat().st_mtime, mtime)
        finally:
            storage.ARCHIVE_DIR = original_archive
            storage.get_supabase = original_get

    def test_json_safe_contract_for_supabase(self):
        cleaned = json_safe({"hours": float("nan"), "nested": {"pct": float("inf")}})
        json.dumps(cleaned, allow_nan=False)

    def test_merge_prefers_completed_over_stale_draft(self):
        from lib.payroll_supabase_sync import merge_run_records

        merged = merge_run_records(
            {"id": "1", "status": "completed", "grand_total": 100, "snapshot": {"ok": True}},
            {"id": "1", "status": "draft", "grand_total": 90, "source": "supabase"},
        )
        self.assertEqual(merged["status"], "completed")
        self.assertEqual(merged["snapshot"], {"ok": True})

    def test_find_run_id_prefers_draft_for_period(self):
        from lib.payroll_supabase_sync import find_run_id_for_pay_period

        runs = [
            {"id": "c1", "pay_period": "07/15/26-07/28/26", "status": "completed"},
            {"id": "d1", "pay_period": "07/15/26-07/28/26", "status": "draft"},
            {"id": "x1", "pay_period": "other", "status": "draft"},
        ]
        self.assertEqual(find_run_id_for_pay_period(runs, "07/15/26-07/28/26"), "d1")


if __name__ == "__main__":
    unittest.main()

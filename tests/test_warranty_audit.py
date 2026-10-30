"""Warranty audit: chunk the manual, cite it, and refuse invented policy."""

from __future__ import annotations

import csv
import io
import json
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from lib.warranty_audit_llm import (
    AUDIT_SYSTEM_PROMPT,
    LlmError,
    build_audit_messages,
    complete_chat,
    extract_repair_order,
    normalize_repair_order,
    parse_json_object,
    prepare_ro_input,
    run_audit,
)
from lib.warranty_audit_manual import (
    ManualExtractError,
    build_manual_record,
    build_summary,
    chunk_pages,
    csv_download_name,
    findings_to_csv,
    retrieve_chunks,
    retrieve_for_repair_order,
    validate_findings,
)
from lib.warranty_audit_storage import (
    cloud_error_message,
    load_active_manual,
    load_warranty_audit_run,
    save_audit_run,
    save_manual_record,
)

ROOT = Path(__file__).resolve().parent.parent

TIME_SENTENCE = (
    "Every warranty repair order must show the technician number and the on and off time punch "
    "for each labor operation."
)
CHARGEBACK = "Claims missing time punches are subject to chargeback."
SIGN_SENTENCE = (
    "The customer must sign the repair order authorizing the warranty repair before the claim is submitted."
)
DEBIT = "Unsigned repair orders will be debited."
PAINT = "Blend panels adjacent to the refinished panel when the color cannot be contained."
INVENTED = "All brake repairs require photographs of the worn parts before the claim is submitted."


def _sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "p1-c0000",
            "chunk_index": 0,
            "page_number": 1,
            "section_label": "Section 4.2 Technician time records",
            "text": f"Section 4.2 Technician time records\n\n{TIME_SENTENCE} {CHARGEBACK}",
        },
        {
            "chunk_id": "p2-c0001",
            "chunk_index": 1,
            "page_number": 2,
            "section_label": "Section 9.1 Paint blending",
            "text": f"Section 9.1 Paint blending\n\n{PAINT}",
        },
        {
            "chunk_id": "p3-c0002",
            "chunk_index": 2,
            "page_number": 3,
            "section_label": "Section 2.4 Customer signature",
            "text": f"Section 2.4 Customer signature\n\n{SIGN_SENTENCE} {DEBIT}",
        },
    ]


def _brake_ro() -> dict:
    return {
        "ro_number": "100245",
        "customer_concern": "Brake noise when stopping",
        "cause": "Worn front pads",
        "correction": "Replaced front brake pads",
        "vin": "1C4RJFBG1LC123456",
        "mileage": "45210",
        "labor_operations": [
            {
                "op_code": "05-01",
                "description": "Replace front pads",
                "hours": "1.2",
                "tech_number": "441",
            }
        ],
        "time_punches": [],
        "parts": [
            {
                "part_number": "68000000AA",
                "description": "Brake pad set",
                "quantity": "1",
                "failed": "yes",
            }
        ],
        "signatures": {"customer": "No", "advisor": "Yes", "technician": "Not visible"},
        "tech_numbers": ["441"],
    }


def _sample_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    pages = [
        [
            "Sample Fixed Ops Warranty Guide",
            "Section 4.2 Technician time records",
            TIME_SENTENCE,
            CHARGEBACK,
        ],
        [
            "Section 9.1 Paint blending",
            PAINT,
        ],
        [
            "Section 2.4 Customer signature",
            SIGN_SENTENCE,
            DEBIT,
        ],
    ]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 10)
    for lines in pages:
        y = 740
        for line in lines:
            pdf.drawString(54, y, line[:110])
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class _Result:
    def __init__(self, data):
        self.data = data


class _MemoryTable:
    def __init__(self, rows):
        self.rows = rows
        self._op = ""
        self._payload = None
        self._filters = []
        self._limit = None

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def eq(self, key, value):
        self._filters.append(lambda row, key=key, value=value: row.get(key) == value)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self._limit = count
        return self

    def execute(self):
        if self._op == "insert":
            self.rows.append(dict(self._payload))
            return _Result([self.rows[-1]])
        matched = [row for row in self.rows if all(check(row) for check in self._filters)]
        if self._op == "update":
            for row in matched:
                row.update(self._payload)
            return _Result(matched)
        if self._op == "delete":
            self.rows[:] = [row for row in self.rows if row not in matched]
            return _Result(matched)
        if self._limit is not None:
            matched = matched[: self._limit]
        return _Result(matched)


class _MemorySupabase:
    def __init__(self):
        self.rows = {"warranty_manuals": [], "warranty_audit_runs": []}

    def table(self, name):
        return _MemoryTable(self.rows.setdefault(name, []))


class ManualRetrievalTests(unittest.TestCase):
    def test_chunks_stay_on_one_page_and_keep_section(self):
        chunks = chunk_pages(
            [
                {
                    "page_number": 4,
                    "text": "Section 4.2 Technician time records\n" + TIME_SENTENCE + "\n" + CHARGEBACK,
                }
            ]
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["page_number"], 4)
        self.assertIn("4.2", chunks[0]["section_label"])
        self.assertIn("time punch", chunks[0]["text"].lower())

    def test_short_scan_is_refused(self):
        with self.assertRaises(ManualExtractError):
            build_manual_record_from_pages_safe()

    def test_time_punch_query_skips_paint_section(self):
        hits = retrieve_chunks(_sample_chunks(), "technician time punch labor operation", limit=5)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["page_number"], 1)
        self.assertNotIn(2, [hit["page_number"] for hit in hits])

    def test_paint_query_finds_paint_section(self):
        hits = retrieve_chunks(_sample_chunks(), "blend panels refinished color", limit=3)
        self.assertEqual(hits[0]["page_number"], 2)

    def test_brake_ro_retrieves_documentation_rules_not_paint(self):
        hits = retrieve_for_repair_order(_brake_ro(), _sample_chunks())
        pages = {hit["page_number"] for hit in hits}
        self.assertIn(1, pages)
        self.assertIn(3, pages)
        self.assertNotIn(2, pages)

    def test_verbatim_quote_counts_and_invented_quote_does_not(self):
        findings = validate_findings(
            [
                {
                    "severity": "critical",
                    "ro_field": "Time punches",
                    "whats_wrong": "Time punches are missing.",
                    "how_to_fix": "=" + "Show the on and off time punch for each labor operation.",
                    "manual_section": "Invented section",
                    "manual_page": 99,
                    "citation_quote": TIME_SENTENCE,
                },
                {
                    "severity": "major",
                    "ro_field": "Customer signature",
                    "whats_wrong": "The customer signature is missing.",
                    "how_to_fix": "Have the customer sign the repair order before the claim is submitted.",
                    "manual_section": "Section 2.4 Customer signature",
                    "manual_page": 3,
                    "citation_quote": SIGN_SENTENCE,
                },
                {
                    "severity": "major",
                    "ro_field": "Photos",
                    "whats_wrong": "Brake photos are missing.",
                    "how_to_fix": "Photograph the worn parts.",
                    "manual_section": "Brakes",
                    "manual_page": 2,
                    "citation_quote": INVENTED,
                },
                {
                    "severity": "minor",
                    "ro_field": "Time punches",
                    "whats_wrong": "Too short to be a citation.",
                    "how_to_fix": "Add punches.",
                    "manual_page": 1,
                    "citation_quote": "time punch",
                },
            ],
            _sample_chunks(),
        )
        required = [item for item in findings if item["counts_as_required_correction"]]
        self.assertEqual(len(required), 2)
        punches = next(item for item in required if item["ro_field"] == "Time punches")
        self.assertEqual(punches["manual_page"], 1)
        self.assertEqual(punches["manual_section"], "Section 4.2 Technician time records")
        self.assertIn("Page corrected", punches["support_note"])
        photos = next(item for item in findings if item["ro_field"] == "Photos")
        self.assertFalse(photos["supported"])
        self.assertFalse(photos["counts_as_required_correction"])
        summary = build_summary("100245", findings)
        self.assertIn("2 items", summary)
        self.assertIn("1 critical", summary)
        self.assertIn("not counted", summary)
        table = list(csv.reader(io.StringIO(findings_to_csv("100245", summary, findings))))
        header = table[0]
        fix_index = header.index("how_to_fix")
        counted_index = header.index("counts_as_required_correction")
        punch_row = next(row for row in table[1:] if row[header.index("ro_field")] == "Time punches")
        self.assertTrue(punch_row[fix_index].startswith("'="))
        self.assertEqual(punch_row[counted_index], "true")
        photo_row = next(row for row in table[1:] if row[header.index("ro_field")] == "Photos")
        self.assertEqual(photo_row[counted_index], "false")

    def test_empty_findings_csv_still_contains_the_summary(self):
        text = findings_to_csv("100245", "Nothing to correct.", [])
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(len(rows), 2)
        self.assertIn("Nothing to correct.", rows[1][-1])
        self.assertTrue(csv_download_name("RO 100245").endswith("warranty_audit_RO_100245.csv"))


def build_manual_record_from_pages_safe():
    from lib.warranty_audit_manual import build_manual_record_from_pages

    return build_manual_record_from_pages(
        "scan.pdf",
        [{"page_number": 1, "text": "no text"}],
        manual_id="x",
        uploaded_at="2026-01-01T00:00:00+00:00",
    )


class AuditPipelineTests(unittest.TestCase):
    def test_prompt_forbids_outside_policy_and_unknown_fields(self):
        self.assertIn("Do not use outside knowledge", AUDIT_SYSTEM_PROMPT)
        self.assertIn("Do not flag an unknown field", AUDIT_SYSTEM_PROMPT)
        self.assertIn("verbatim", AUDIT_SYSTEM_PROMPT.lower())

    def test_messages_include_retrieved_manual_text_only(self):
        chunks = _sample_chunks()
        retrieved = retrieve_for_repair_order(_brake_ro(), chunks)
        messages = build_audit_messages(normalize_repair_order(_brake_ro()), retrieved)
        blob = messages[-1]["content"]
        self.assertIn(TIME_SENTENCE, blob)
        self.assertIn(SIGN_SENTENCE, blob)
        self.assertNotIn(INVENTED, blob)
        self.assertNotIn(PAINT, blob)

    def test_run_audit_drops_invented_policy(self):
        def complete(messages):
            blob = json.dumps(messages)
            if INVENTED in blob or PAINT in blob:
                raise AssertionError("model context included text it should not see")
            return json.dumps(
                {
                    "findings": [
                        {
                            "severity": "critical",
                            "ro_field": "Time punches",
                            "whats_wrong": "Time punches are missing.",
                            "how_to_fix": "Enter the on and off time punch for each labor operation.",
                            "manual_section": "Section 4.2 Technician time records",
                            "manual_page": 1,
                            "citation_quote": TIME_SENTENCE,
                        },
                        {
                            "severity": "critical",
                            "ro_field": "Photos",
                            "whats_wrong": "Photos are required.",
                            "how_to_fix": "Add photographs.",
                            "manual_section": "Brakes",
                            "manual_page": 8,
                            "citation_quote": INVENTED,
                        },
                    ]
                }
            )

        result = run_audit(_brake_ro(), _sample_chunks(), complete=complete)
        required = [item for item in result["findings"] if item["counts_as_required_correction"]]
        self.assertEqual([item["ro_field"] for item in required], ["Time punches"])
        self.assertIn("1 item", result["summary"])
        self.assertEqual(result["ro"]["signatures"]["customer"], False)
        self.assertIsNone(result["ro"]["signatures"]["technician"])
        self.assertTrue(result["ro"]["parts"][0]["failed"])

    def test_unmatched_manual_does_not_call_the_model(self):
        called = {"count": 0}

        def complete(_messages):
            called["count"] += 1
            return "{}"

        chunks = [
            {
                "chunk_id": "p9-c0000",
                "chunk_index": 0,
                "page_number": 9,
                "section_label": "Section 9.1 Paint blending",
                "text": PAINT,
            }
        ]
        result = run_audit(_brake_ro(), chunks, complete=complete)
        self.assertEqual(called["count"], 0)
        self.assertEqual(result["findings"], [])
        self.assertIn("No stored manual section matched", result["summary"])

    def test_extract_keeps_nulls_and_reads_fenced_json(self):
        payload = {
            "ro_number": "100245",
            "vin": None,
            "mileage": "null",
            "customer_concern": "Brake noise",
            "signatures": {"customer": False, "advisor": None, "technician": "yes"},
            "labor_operations": [{"op_code": "05-01", "description": "Pads", "hours": 1.0, "tech_number": "441"}],
            "parts": [{"part_number": "ABC", "description": "Pad", "quantity": "1", "failed": "no"}],
            "unreadable": ["close_date"],
        }

        def complete(_messages):
            return "```json\n" + json.dumps(payload) + "\n```"

        order = extract_repair_order(images=[], document_text="RO 100245 brake noise", complete=complete)
        self.assertEqual(order["ro_number"], "100245")
        self.assertEqual(order["vin"], "")
        self.assertEqual(order["mileage"], "")
        self.assertFalse(order["signatures"]["customer"])
        self.assertIsNone(order["signatures"]["advisor"])
        self.assertTrue(order["signatures"]["technician"])
        self.assertEqual(order["labor_operations"][0]["hours"], "1")
        self.assertNotIn("_source", order["labor_operations"][0])
        self.assertFalse(order["parts"][0]["failed"])
        self.assertEqual(parse_json_object("```json\n{\"a\": 1}\n```"), {"a": 1})

    def test_sample_pdf_round_trip_keeps_page_and_sentence(self):
        record = build_manual_record(
            "sample-warranty-guide.pdf",
            _sample_pdf(),
            manual_id="manual-1",
            uploaded_at="2026-01-01T00:00:00+00:00",
        )
        self.assertGreaterEqual(record["text_characters"], 200)
        self.assertEqual(record["page_count"], 3)
        punch = next(chunk for chunk in record["chunks"] if "time punch" in chunk["text"].lower())
        self.assertEqual(punch["page_number"], 1)
        prepared = prepare_ro_input("ro.pdf", _sample_pdf())
        self.assertTrue(prepared["images"])
        self.assertEqual(prepared["images"][0][1], "image/jpeg")

    def test_png_upload_is_accepted(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (2400, 1800), "white").save(buffer, format="PNG")
        prepared = prepare_ro_input("desk.png", buffer.getvalue())
        self.assertEqual(len(prepared["images"]), 1)
        image = Image.open(io.BytesIO(prepared["images"][0][0]))
        self.assertLessEqual(max(image.size), 1600)


class LlmTransportTests(unittest.TestCase):
    def test_api_key_stays_in_the_header(self):
        seen = {}

        class _Resp:
            def read(self):
                return json.dumps({"choices": [{"message": {"content": "{\"ok\": true}"}}]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(request, timeout=0):
            seen["auth"] = request.get_header("Authorization")
            seen["body"] = request.data.decode()
            seen["url"] = request.full_url
            return _Resp()

        with patch("urllib.request.urlopen", fake_urlopen):
            content = complete_chat(
                [{"role": "user", "content": "Return JSON"}],
                api_key="super-secret-key",
                model="gpt-4o",
            )
        self.assertIn("ok", content)
        self.assertEqual(seen["auth"], "Bearer super-secret-key")
        self.assertNotIn("super-secret-key", seen["body"])
        self.assertEqual(seen["url"], "https://api.openai.com/v1/chat/completions")

    def test_rejected_key_does_not_echo_the_secret(self):
        def fake_urlopen(request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "denied",
                Message(),
                io.BytesIO(b'{"error":"super-secret-key"}'),
            )

        with patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(LlmError) as caught:
                complete_chat([{"role": "user", "content": "hi"}], api_key="super-secret-key", model="gpt-4o")
        self.assertNotIn("super-secret-key", str(caught.exception))
        self.assertIn("OPENAI_API_KEY was rejected", str(caught.exception))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.patches = [
            patch("lib.warranty_audit_storage.MANUAL_DIR", root / "manual"),
            patch("lib.warranty_audit_storage.AUDIT_DIR", root / "audit"),
            patch("lib.warranty_audit_storage.get_supabase", return_value=None),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def _record(self, name: str) -> dict:
        chunks = _sample_chunks()
        return {
            "id": name,
            "filename": f"{name}.pdf",
            "title": name,
            "page_count": 3,
            "chunk_count": len(chunks),
            "text_characters": 500,
            "warnings": [],
            "chunks": chunks,
            "uploaded_at": f"2026-01-0{1 if name == 'first' else 2}T00:00:00+00:00",
        }

    def test_replace_manual_keeps_the_new_chunks_locally(self):
        save_manual_record(self._record("first"))
        save_manual_record(self._record("second"))
        loaded = load_active_manual()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["filename"], "second.pdf")
        self.assertEqual(loaded["chunk_count"], 3)
        self.assertIn("time punch", loaded["chunks"][0]["text"].lower())
        self.assertEqual(loaded["storage_source"], "local")

    def test_audit_history_round_trip(self):
        result = run_audit(
            _brake_ro(),
            _sample_chunks(),
            complete=lambda _messages: json.dumps(
                {
                    "findings": [
                        {
                            "severity": "critical",
                            "ro_field": "Time punches",
                            "whats_wrong": "Time punches are missing.",
                            "how_to_fix": "Enter the on and off time punch.",
                            "manual_page": 1,
                            "citation_quote": TIME_SENTENCE,
                        }
                    ]
                }
            ),
        )
        result["source_name"] = "camera-repair-order.jpg"
        result["manual_id"] = "second"
        result["manual_filename"] = "second.pdf"
        run_id, err = save_audit_run(result)
        self.assertEqual(err, "")
        loaded = load_warranty_audit_run(run_id)
        self.assertEqual(loaded["ro_number"], "100245")
        self.assertEqual(loaded["finding_count"], 1)
        self.assertEqual(loaded["critical_count"], 1)
        self.assertEqual(loaded["snapshot"]["findings"][0]["citation_quote"], TIME_SENTENCE)

    def test_cloud_replace_leaves_one_active_manual(self):
        client = _MemorySupabase()
        with patch("lib.warranty_audit_storage.get_supabase", return_value=client):
            save_manual_record(self._record("first"))
            saved, err = save_manual_record(self._record("second"))
        self.assertEqual(err, "")
        self.assertEqual(saved["storage_source"], "supabase")
        active = [row for row in client.rows["warranty_manuals"] if row.get("is_active") is True]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["filename"], "second.pdf")
        self.assertEqual(len(active[0]["chunks"]), 3)

    def test_missing_table_message_points_at_the_sql_file(self):
        message = cloud_error_message("Could not find the table public.warranty_manuals")
        self.assertIn("warranty_audit_tables.sql", message)
        self.assertIn("supabase/warranty_audit_tables.sql", (ROOT / "supabase" / "warranty_audit_tables.sql").as_posix())


class RepoWiringTests(unittest.TestCase):
    def test_page_is_registered_and_secret_is_documented(self):
        app = (ROOT / "app.py").read_text()
        auth = (ROOT / "lib" / "app_auth.py").read_text()
        self.assertIn('"Warranty Audit": warranty_audit.render', app)
        self.assertIn('"Warranty Audit"', auth)
        for relative in (
            "README.md",
            ".env.example",
            ".streamlit/secrets.toml.example",
            "streamlit-cloud-secrets.example.toml",
            "DEPLOY-CLOUD.md",
        ):
            self.assertIn("OPENAI_API_KEY", (ROOT / relative).read_text(), relative)
        schema = (ROOT / "supabase" / "schema.sql").read_text()
        self.assertIn("create table if not exists warranty_manuals", schema)
        self.assertIn("alter table warranty_manuals enable row level security", schema)
        self.assertIn("alter table warranty_audit_runs enable row level security", schema)
        enable = (ROOT / "supabase" / "enable_rls.sql").read_text()
        self.assertIn("warranty_manuals", enable)
        requirements = (ROOT / "requirements.txt").read_text()
        self.assertIn("pillow", requirements.lower())
        examples = (ROOT / ".env.example").read_text() + (ROOT / "streamlit-cloud-secrets.example.toml").read_text()
        self.assertNotIn("sk-live", examples)
        self.assertNotIn("sk-proj", examples)


if __name__ == "__main__":
    unittest.main()

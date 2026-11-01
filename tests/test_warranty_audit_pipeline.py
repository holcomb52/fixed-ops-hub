"""End-to-end audit checks on synthetic claims. No customer data and no live model."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from lib.warranty_audit_claim import check_claim_criteria
from lib.warranty_audit_llm import LlmError, complete_chat, run_audit
from lib.warranty_audit_manual import (
    build_manual_record_from_pages,
    chunk_pages,
    redact_secrets,
    validate_findings,
)
from lib.warranty_audit_storage import _uuid_or_none

RULE = (
    "Every warranty repair order must show the technician number and the on and off time punch "
    "for each labor operation. Claims missing time punches are subject to chargeback."
)


def _order(**overrides) -> dict:
    order = {
        "document_type": "claim_acknowledgement",
        "ro_number": "100245",
        "claim_number": "100245",
        "dealer_code": "68888",
        "vin": "1C4RJFBG5LC000001",
        "mileage": "45210",
        "in_service_date": "Jun 27, 2021",
        "date_received": "Jan 10, 2026",
        "date_completed": "Jan 16, 2026",
        "customer_concern": "Customer states the rear view camera is inoperative.",
        "cause": "Found a broken wire in the camera harness.",
        "correction": "Replaced the rear view camera. Labor op 08200170. Total time 0.3 hours.",
        "tech_notes": "Tested the camera circuit and found a broken wire. Replaced the camera.",
        "time_punches": [{"tech_number": "20001", "on": "8:00", "off": "8:20", "hours": "0.3"}],
        "signatures": {"service_manager": True},
        "labor_operations": [
            {
                "op_code": "08200170",
                "description": "Park view camera",
                "failure_code": "58",
                "hours": "0.3",
                "tech_number": "20001",
            }
        ],
        "parts": [
            {
                "part_number": "56054158AG",
                "description": "Camera",
                "quantity": "1",
                "failed": True,
            }
        ],
    }
    order.update(overrides)
    return order


def _fields(order: dict) -> set[str]:
    return {item["ro_field"] for item in check_claim_criteria(order) if item.get("counts_as_required_correction")}


def _sample_cases() -> list[dict]:
    clean = _order()
    second_clean = _order(
        customer_concern="Customer states the front brakes grind.",
        cause="Found the front pads worn to the metal.",
        correction="Replaced the front brake pads.",
        tech_notes="Measured the pads and found them worn. Replaced the front brake pads.",
        mileage="38110",
        labor_operations=[
            {
                "op_code": "05010001",
                "description": "Front brake pads",
                "failure_code": "68",
                "hours": "1.2",
                "tech_number": "441",
            }
        ],
        parts=[{"part_number": "68000000AA", "description": "Brake pad", "quantity": "1", "failed": True}],
        time_punches=[{"tech_number": "441", "on": "9:00", "off": "10:12", "hours": "1.2"}],
    )
    missing_story = _order(customer_concern="", cause="", correction="", tech_notes="", other_visible_notes="")
    wrong_labor = _order(
        labor_operations=[
            {
                "op_code": "22000001",
                "description": "Transmission overhaul",
                "failure_code": "11",
                "hours": "0.3",
                "tech_number": "20001",
            }
        ]
    )
    overtime = _order(
        correction="Replaced the rear view camera. Labor op 08200170. Total time 0.3 hours.",
        labor_operations=[
            {
                "op_code": "08200170",
                "description": "Park view camera",
                "failure_code": "58",
                "hours": "4.0",
                "tech_number": "20001",
            }
        ],
    )
    missing_punch = _order(time_punches=[])
    missing_part_story = _order(
        cause="Found the pads worn.",
        correction="Replaced the pads.",
        tech_notes="Found the pads worn and replaced the pads.",
        customer_concern="Customer states the brakes grind.",
    )
    bad_dates = _order(date_received="Jan 16, 2026", date_completed="Jan 2, 2026")
    bad_miles = _order(
        mileage="12000",
        tech_notes="Tested the camera at 45,210 miles and found a broken wire. Replaced the camera.",
    )
    return [
        {"name": "clean camera claim", "order": clean, "expect_any": [], "clean": True},
        {"name": "clean brake claim", "order": second_clean, "expect_any": [], "clean": True},
        {"name": "missing 3C story", "order": missing_story, "expect_any": ["Tech notes"], "clean": False},
        {"name": "wrong labor operation", "order": wrong_labor, "expect_any": ["Tech notes"], "clean": False},
        {"name": "hours do not match the notes", "order": overtime, "expect_any": ["labor hours"], "clean": False},
        {"name": "missing time punches", "order": missing_punch, "expect_any": ["Time punches"], "clean": False},
        {"name": "notes omit the failed part", "order": missing_part_story, "expect_any": ["Tech notes"], "clean": False},
        {"name": "completed before received", "order": bad_dates, "expect_any": ["Date completed"], "clean": False},
        {"name": "mileage does not match the notes", "order": bad_miles, "expect_any": ["Mileage"], "clean": False},
    ]


def score_samples() -> dict:
    detected = 0
    expected = 0
    false_positive_cases = []
    misses = []
    for case in _sample_cases():
        fields = _fields(case["order"])
        if case["clean"]:
            if fields:
                false_positive_cases.append({"name": case["name"], "fields": sorted(fields)})
            continue
        expected += 1
        if any(token in " ".join(fields) for token in case["expect_any"]):
            detected += 1
        else:
            misses.append({"name": case["name"], "fields": sorted(fields), "wanted": case["expect_any"]})
    return {
        "detected": detected,
        "expected": expected,
        "recall": detected / expected if expected else 1,
        "false_positive_cases": false_positive_cases,
        "misses": misses,
    }


class SampleClaimTests(unittest.TestCase):
    def test_known_errors_are_detected_and_clean_claims_stay_clean(self):
        score = score_samples()
        self.assertEqual(score["misses"], [], score)
        self.assertEqual(score["false_positive_cases"], [], score)
        self.assertGreaterEqual(score["recall"], 1)

    def test_hallucinated_quote_does_not_count(self):
        chunks = chunk_pages([
            {"page_number": 4, "text": "Section 4.2 Technician time records\n" + RULE}
        ])
        findings = validate_findings(
            [{
                "severity": "critical",
                "ro_field": "Time punches",
                "whats_wrong": "The manual requires a photo of the odometer.",
                "how_to_fix": "Photograph the odometer.",
                "manual_page": 4,
                "citation_quote": "Every claim must include a photograph of the odometer before the repair.",
            }],
            chunks,
        )
        self.assertEqual(findings[0]["counts_as_required_correction"], False)
        self.assertFalse(findings[0]["supported"])

    def test_heading_only_quote_does_not_count(self):
        chunks = chunk_pages([
            {"page_number": 1, "text": "WARRANTY ADMINISTRATION MANUAL\n" + RULE}
        ])
        findings = validate_findings(
            [{
                "severity": "major",
                "ro_field": "Manual",
                "whats_wrong": "The heading was quoted instead of the rule.",
                "how_to_fix": "Quote the requirement.",
                "manual_page": 1,
                "citation_quote": "WARRANTY ADMINISTRATION MANUAL",
            }],
            chunks,
        )
        self.assertFalse(findings[0]["counts_as_required_correction"])

    def test_real_quote_counts_and_chunks_keep_their_page(self):
        pages = [
            {"page_number": 1, "text": "Section 1 Intro\n" + ("Introduction text. " * 20)},
            {"page_number": 2, "text": "Section 2 Time\n" + RULE},
        ]
        record = build_manual_record_from_pages(
            "sample-manual.pdf",
            pages,
            manual_id="manual-1",
            uploaded_at="2026-11-01T00:00:00+00:00",
        )
        punch = next(chunk for chunk in record["chunks"] if "time punch" in chunk["text"].lower())
        self.assertEqual(punch["page_number"], 2)
        findings = validate_findings(
            [{
                "severity": "critical",
                "ro_field": "Time punches",
                "whats_wrong": "Time punches are missing.",
                "how_to_fix": "Enter the on and off time.",
                "manual_page": 9,
                "citation_quote": RULE,
            }],
            record["chunks"],
        )
        self.assertTrue(findings[0]["counts_as_required_correction"])
        self.assertEqual(findings[0]["manual_page"], 2)

    def test_audit_uses_the_quote_and_ignores_an_invented_one(self):
        chunks = chunk_pages([{"page_number": 2, "text": "Section 2 Time\n" + RULE}])

        def complete(messages):
            self.assertIn(RULE, messages[-1]["content"])
            return json.dumps({"findings": [
                {
                    "severity": "critical",
                    "ro_field": "Time punches",
                    "whats_wrong": "Time punches are missing.",
                    "how_to_fix": "Enter the on and off time.",
                    "manual_page": 2,
                    "citation_quote": RULE,
                },
                {
                    "severity": "critical",
                    "ro_field": "Photos",
                    "whats_wrong": "A photo is required.",
                    "how_to_fix": "Add a photo.",
                    "manual_page": 2,
                    "citation_quote": "Every claim must include a photograph of the odometer before the repair.",
                },
            ]})

        result = run_audit(_order(time_punches=[]), chunks, complete=complete)
        counted = [item for item in result["findings"] if item.get("counts_as_required_correction")]
        self.assertTrue(any(item["ro_field"] == "Time punches" for item in counted))
        self.assertFalse(any(item["ro_field"] == "Photos" and item.get("counts_as_required_correction") for item in result["findings"]))

    def test_secrets_are_removed_from_errors_and_rate_limit_text(self):
        leaked = "sk-proj-supersecretvalue123456"
        self.assertNotIn(leaked, redact_secrets(f"failed with {leaked} and Bearer abc.def.ghi"))
        self.assertNotIn("sb_secret_abcdef123456", redact_secrets("key sb_secret_abcdef123456"))

        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "busy",
                Message(),
                io.BytesIO(f'{{"error":"{leaked}"}}'.encode()),
            )

        with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep"):
            with self.assertRaises(LlmError) as caught:
                complete_chat(
                    [{"role": "user", "content": "hi"}],
                    api_key=leaked,
                    model="gpt-4o",
                )
        self.assertEqual(calls["count"], 2)
        self.assertIn("rate limit", str(caught.exception).lower())
        self.assertNotIn(leaked, str(caught.exception))
        self.assertNotIn("sk-proj", str(caught.exception))

    def test_invalid_manual_id_is_not_sent_as_a_uuid(self):
        self.assertIsNone(_uuid_or_none("second"))
        self.assertIsNone(_uuid_or_none(""))
        self.assertEqual(
            _uuid_or_none("f851e78e-d1f3-5646-9bc7-f876b7e6f8ea"),
            "f851e78e-d1f3-5646-9bc7-f876b7e6f8ea",
        )

    def test_tiny_photo_and_text_pdf_are_prepared(self):
        from PIL import Image

        from lib.warranty_audit_llm import prepare_documents, prepare_ro_input

        image = Image.new("RGB", (30, 20), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        prepared = prepare_documents([("blurry.jpg", buffer.getvalue())])
        self.assertEqual(len(prepared["images"]), 1)

        from reportlab.pdfgen import canvas

        pdf_buffer = io.BytesIO()
        pdf = canvas.Canvas(pdf_buffer)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(54, 720, "Section 2 Time records")
        pdf.drawString(54, 700, RULE[:110])
        pdf.showPage()
        pdf.save()
        ro_pdf = prepare_ro_input("claim.pdf", pdf_buffer.getvalue())
        self.assertTrue(ro_pdf["images"] or ro_pdf["document_text"])


if __name__ == "__main__":
    unittest.main()

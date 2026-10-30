"""Vision read of a repair order and a citation-checked manual comparison.

The model may only quote excerpts passed in the request. Findings that do not
match stored text are marked unsupported by warranty_audit_manual.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional

from lib.warranty_audit_claim import check_claim_criteria
from lib.warranty_audit_manual import (
    SEVERITIES,
    build_summary,
    format_excerpts,
    retrieve_for_repair_order,
    validate_findings,
)

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o"

EXTRACT_SYSTEM_PROMPT = """You read dealership repair orders and Reynolds Ignite printouts.
Reynolds Ignite also prints the FCA US LLC Global Claim Acknowledgement.
Extract only text that is visible. Use null for anything you cannot read.
Never guess VIN characters, dates, mileage, technician numbers, labor operation codes,
failure codes, part numbers, amounts, or whether a signature or Failed Part mark is present.
If a signature line is visible and blank, set that signature to false.
If the signature area is not in the image, use null.
If Failed Part has no X or other mark, set failed to null. If it is marked, set failed to true.
Return JSON only."""

TRANSCRIBE_SYSTEM_PROMPT = """You copy dealership paperwork exactly as printed.
Copy every word you can read. Do not summarize, shorten, or skip lines.
Do not return JSON. Return plain text only.
Never guess a character you cannot see. Mark a hard word as [unclear] and keep going.
The customer narrative and the time punches are required. Copy them in full."""

TRANSCRIBE_USER_PROMPT = """Copy this page exactly. Do not summarize.

Include every one of these when it is on the page:
- The full customer narrative and the technician notes, word for word: concern, cause, correction, tests, and what was found
- Every time punch: technician, time on, time off, and hours
- Every job number. When a small plus sign is printed next to the job number, copy it as "Job +2" or "Job 2 +"
- Every labor line: LOP, description, failure code, hours, and technician
- Every part: part number, description, quantity, and whether Failed Part is marked
- List Number on the claim acknowledgement. Copy the digits exactly, such as 2025123
- Header fields that are visible: VIN, dates, mileage, claim number, dealer, coverage, claim type, submission type, continuation, prior claim, vehicle, advisor, technician name and id, and authorization
- A signature or initials next to an added job

Owner's name and Pre-Tax Total are usually blank. Copy them only when they are printed. Do not fill them in.
Keep the technician notes as full sentences, not a short label. Keep every time punch on its own line.
If a line is hard to read, copy your best reading and mark it [unclear]. Do not leave the notes, the list number, or the time punches out."""

EXTRACT_USER_PROMPT = """Read this Reynolds Ignite repair order or FCA Global Claim Acknowledgement.
Return JSON with exactly these keys:
document_type ("claim_acknowledgement" when the page is a Global Claim Acknowledgement, otherwise "repair_order"),
dms ("reynolds_ignite" when the printout is from Reynolds Ignite, otherwise ""),
ro_number, open_date, close_date, repair_date, vin, mileage,
claim_number, claim_status, dealer_code, in_service_date, warranty_coverage,
claim_type, submission_type, continuation, date_received, date_completed, process_date,
authorization, owner_name, vehicle_description, service_advisor,
list_number, reference_number, prior_claim, technician_name,
customer_concern, cause, correction, tech_notes,
labor_operations (list of objects with ro_number, job_number, op_code, description, failure_code, hours, tech_number, add_on),
tech_numbers (list of strings),
time_punches (list of objects with tech_number, on, off, hours),
parts (list of objects with ro_number, part_number, description, quantity, failed),
repair_orders (list of objects with ro_number, technician_id, technician_name,
total_parts, total_labor, total_special_service, pre_tax_total,
labor_lines, part_lines),
signatures (object with customer, advisor, technician, service_manager; each true, false, or null),
other_visible_notes (string),
unreadable (list of field names you could not read).

On a claim acknowledgement, split Customer Narrative into customer_concern (what the customer stated),
cause (what was found), and correction (the repair performed, including any labor operation and hours the narrative states).
tech_notes is the technician's full story: the tests, the cause, and the correction, word for word. Do not shorten it.
Copy LOP into op_code, Failure Code into failure_code, and Hours into hours.
job_number is the job number on the repair order. add_on is true only when a small plus sign is printed next to that job number. A plus sign inside a part number is not an add-on.
list_number is the List Number on the claim acknowledgement. Copy every digit, such as 2025123.
owner_name is usually blank. Leave it blank. Do not guess a name.
pre_tax_total is usually blank. Leave it blank. Do not calculate it.
signatures.service_manager is true only when a signature or initials are written next to an added job, false when that spot is visible and blank, and null when it is not in the pictures.
A claim can contain more than one repair order. Keep each RO's lines and totals together in repair_orders.
Do not invent values that are not on the page."""

AUDIT_SYSTEM_PROMPT = """You are a warranty-audit checker for an automobile dealership.
You compare one repair order to excerpts from a warranty manual the dealership stored.
You have no other policy source.

Rules:
- Use only the manual excerpts in the user message. Do not use outside knowledge of Stellantis, FCA, OEM, or dealer policy. If a requirement is not written in those excerpts, do not flag it.
- Every finding must include citation_quote: a contiguous verbatim copy of the excerpt sentence or sentences that state the requirement. Do not paraphrase, shorten with ellipses, or merge text from different excerpts.
- manual_page must be the pdf_page number on the excerpt you quoted. manual_section must be the section label on that excerpt.
- If the repair order already satisfies the excerpt, do not file a finding.
- If the excerpts do not address the repair, return an empty findings array.
- Treat null signatures and fields listed as unreadable as unknown. Do not flag an unknown field as missing.
- Flag a signature only when the repair order value is false and an excerpt requires that signature.
- Flag time punches only when time_punches is empty or visibly incomplete and an excerpt requires them.
- how_to_fix must restate the action required by the quoted excerpt, not a new rule.
- severity is critical when the excerpt says the claim will be charged back, debited, or rejected; major when the excerpt says the claim is incomplete or may be denied; minor when the excerpt only states a format or clarity requirement.
- ro_field names the repair-order item that is wrong, such as time punches, customer signature, mileage, VIN, cause, correction, parts, or labor operation.
- Return JSON only, with this shape: {"findings": [{"severity": "", "ro_field": "", "whats_wrong": "", "how_to_fix": "", "manual_section": "", "manual_page": 0, "citation_quote": ""}]}"""


class LlmError(RuntimeError):
    """A model call failed or returned something we will not treat as policy."""


CompleteFn = Callable[[list], str]


def read_llm_settings() -> tuple[str, str]:
    key = _secret("OPENAI_API_KEY")
    model = _secret("OPENAI_MODEL") or DEFAULT_MODEL
    return key, model


def llm_configured() -> bool:
    key, _model = read_llm_settings()
    return bool(key)


def parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, count=1)
    for candidate in (raw, _json_slice(raw), _repair_json(raw)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise LlmError("One picture could not be read. The other pages will still be used.")


def _repair_json(text: str) -> str:
    """Close a JSON object that was cut off at the end of the model reply."""
    start = text.find("{")
    if start < 0:
        return ""
    chunk = text[start:].rstrip().rstrip(",")
    opens = 0
    in_string = False
    escaped = False
    for char in chunk:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            opens += 1
        elif char == "}":
            opens -= 1
    if in_string:
        chunk += '"'
    if opens > 0:
        chunk += "}" * opens
    return chunk if opens > 0 or in_string else ""


def _json_slice(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""


def complete_chat(
    messages: list,
    *,
    api_key: str,
    model: str,
    timeout: int = 180,
    json_mode: bool = True,
    max_tokens: int | None = None,
) -> str:
    """Call the OpenAI chat API. The key is sent only in the Authorization header.

    json_mode is for the field-organizing step. Page transcription leaves it off
    so a long narrative is not forced into a JSON object that gets cut off.
    """
    if not api_key:
        raise LlmError("OPENAI_API_KEY is not set.")
    payload = {
        "model": model or DEFAULT_MODEL,
        "temperature": 0,
        "messages": messages,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400].replace(api_key, "[redacted]")
        if exc.code == 401:
            raise LlmError(
                "OPENAI_API_KEY was rejected. Check the key in Streamlit secrets or .env."
            ) from None
        raise LlmError(f"The model request failed ({exc.code}). {detail}") from None
    except urllib.error.URLError as exc:
        raise LlmError(f"Could not reach the model API. {exc.reason}") from None
    except TimeoutError:
        raise LlmError("The model request timed out. Try a clearer photo or fewer pages.") from None
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LlmError("The model returned an unexpected response.") from None
    if not isinstance(content, str) or not content.strip():
        raise LlmError("The model returned an empty response.")
    return content


def build_transcribe_messages(*, image: tuple[bytes, str], page_number: int) -> list:
    blob, mime = image
    encoded = base64.b64encode(blob).decode("ascii")
    content: list[dict] = [
        {"type": "text", "text": f"Page {page_number}.\n{TRANSCRIBE_USER_PROMPT}"},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
        },
    ]
    return [
        {"role": "system", "content": TRANSCRIBE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def build_structure_messages(transcript: str) -> list:
    user = (
        EXTRACT_USER_PROMPT
        + "\n\nThe page text below was copied from the pictures. Use only that text.\n"
        + "Copy the full customer narrative into customer_concern, cause, and correction. Do not shorten it.\n"
        + "Copy every time punch into time_punches. Copy every labor line and every part.\n"
        + "If the page text contains the notes or the punches, those fields are readable. Do not leave them blank.\n\n"
        + "PAGE TEXT\n"
        + transcript.strip()[:100000]
    )
    return [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_extract_messages(*, images: list[tuple[bytes, str]], document_text: str = "") -> list:
    """Kept for callers that still build one vision request. New reads transcribe first."""
    content: list[dict] = [{"type": "text", "text": EXTRACT_USER_PROMPT}]
    if document_text.strip():
        content.append({"type": "text", "text": "DOCUMENT TEXT\n" + document_text.strip()[:20000]})
    for blob, mime in images:
        encoded = base64.b64encode(blob).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
            }
        )
    return [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def normalize_repair_order(data: dict) -> dict:
    """Coerce model output into a stable repair-order dict. Missing stays null or empty."""
    if not isinstance(data, dict):
        data = {}
    data = _flatten_repair_orders(data)
    signatures = data.get("signatures") if isinstance(data.get("signatures"), dict) else {}
    labor = []
    for row in _rows(
        data.get("labor_operations"),
        ("ro_number", "job_number", "op_code", "description", "failure_code", "hours", "tech_number"),
    ):
        source = row.pop("_source", {})
        row["add_on"] = _add_on_value(source, row.get("job_number"))
        labor.append(row)
    punches = _rows(data.get("time_punches"), ("tech_number", "on", "off", "hours"))
    parts = []
    for row in _rows(data.get("parts"), ("ro_number", "part_number", "description", "quantity")):
        source = row.pop("_source", {})
        row["failed"] = _boolish(source.get("failed"))
        parts.append(row)
    for row in punches:
        row.pop("_source", None)
    tech_numbers = []
    seen = set()
    for value in _as_items(data.get("tech_numbers")) + [
        row.get("tech_number") for row in labor + punches
    ]:
        text = _text(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            tech_numbers.append(text)
    unreadable = []
    for value in _as_list(data.get("unreadable")):
        text = _text(value)
        if text and text not in unreadable:
            unreadable.append(text)
    kind = _text(data.get("document_type")).casefold().replace("-", " ").replace("_", " ")
    if "claim acknowledgement" in kind or kind == "claim":
        document_type = "claim_acknowledgement"
    else:
        document_type = "repair_order"
    dms = _text(data.get("dms")).casefold().replace("-", " ").replace("_", " ")
    return {
        "document_type": document_type,
        "dms": "reynolds_ignite" if "reynolds" in dms else "",
        "ro_number": _text(data.get("ro_number")),
        "open_date": _text(data.get("open_date")),
        "close_date": _text(data.get("close_date")),
        "repair_date": _text(data.get("repair_date")),
        "vin": _text(data.get("vin")),
        "mileage": _text(data.get("mileage")),
        "claim_number": _text(data.get("claim_number")),
        "claim_status": _text(data.get("claim_status")),
        "dealer_code": _text(data.get("dealer_code")),
        "in_service_date": _text(data.get("in_service_date")),
        "warranty_coverage": _text(data.get("warranty_coverage")),
        "claim_type": _text(data.get("claim_type")),
        "submission_type": _text(data.get("submission_type")),
        "continuation": _text(data.get("continuation")),
        "date_received": _text(data.get("date_received")),
        "date_completed": _text(data.get("date_completed")),
        "process_date": _text(data.get("process_date")),
        "authorization": _text(data.get("authorization")),
        "owner_name": _text(data.get("owner_name")),
        "vehicle_description": _text(data.get("vehicle_description")),
        "service_advisor": _text(data.get("service_advisor")),
        "list_number": _text(data.get("list_number")),
        "reference_number": _text(data.get("reference_number")),
        "prior_claim": _text(data.get("prior_claim")),
        "technician_name": _text(data.get("technician_name")),
        "customer_concern": _text(data.get("customer_concern")),
        "cause": _text(data.get("cause")),
        "correction": _text(data.get("correction")),
        "tech_notes": _text(data.get("tech_notes")),
        "labor_operations": labor,
        "tech_numbers": tech_numbers,
        "time_punches": punches,
        "parts": parts,
        "repair_orders": _normalize_repair_blocks(data.get("repair_orders"), labor, parts),
        "total_parts": _text(data.get("total_parts")),
        "total_labor": _text(data.get("total_labor")),
        "total_special_service": _text(data.get("total_special_service")),
        "pre_tax_total": _text(data.get("pre_tax_total")),
        "signatures": {
            "customer": _boolish(signatures.get("customer")),
            "advisor": _boolish(signatures.get("advisor")),
            "technician": _boolish(signatures.get("technician")),
            "service_manager": _boolish(signatures.get("service_manager")),
        },
        "other_visible_notes": _text(data.get("other_visible_notes")),
        "unreadable": unreadable,
    }


def extract_repair_order(
    *,
    images: list[tuple[bytes, str]],
    document_text: str = "",
    complete: Optional[CompleteFn] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> dict:
    if not images and not str(document_text or "").strip():
        raise LlmError("No readable repair-order image or text was provided.")
    try:
        return _extract_prepared(
            images=images,
            document_text=document_text,
            complete=complete,
            on_progress=on_progress,
        )
    except LlmError:
        return normalize_repair_order({"unreadable": ["the pictures"]})


def _extract_prepared(
    *,
    images: list[tuple[bytes, str]],
    document_text: str,
    complete: Optional[CompleteFn],
    on_progress: Optional[Callable[[int, int], None]],
) -> dict:
    """Copy each page as text, then turn that text into claim fields.

    Asking the vision model for the full JSON schema is what cut off the notes
    and the time punches. Plain-text copies do not have that limit.
    """
    prepared = [_smaller_for_model(image) for image in images]
    structure_fn = complete or _bound_complete(json_mode=True, max_tokens=16384)
    transcribe_fn = complete or _bound_complete(json_mode=False, max_tokens=4096)
    pages = _transcribe_pages(prepared, transcribe_fn, on_progress)
    transcript = _join_transcript(pages, document_text)
    if on_progress:
        page_count = max(len(prepared), 1)
        on_progress(page_count + 1, page_count)
    return normalize_repair_order(_structure_transcript(transcript, structure_fn))


def _transcribe_pages(
    images: list[tuple[bytes, str]],
    transcribe_fn: CompleteFn,
    on_progress: Optional[Callable[[int, int], None]],
) -> list[str]:
    if not images:
        return []

    def copy_page(index: int, image: tuple[bytes, str]) -> str:
        messages = build_transcribe_messages(image=image, page_number=index + 1)
        try:
            text = transcribe_fn(messages).strip()
        except LlmError as exc:
            return f"[Page {index + 1} could not be read. {exc}]"
        return text or f"[Page {index + 1} came back blank.]"

    if len(images) == 1:
        if on_progress:
            on_progress(1, 1)
        return [copy_page(0, images[0])]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    pages: list[str] = [""] * len(images)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(copy_page, index, image): index for index, image in enumerate(images)
        }
        finished = 0
        for future in as_completed(futures):
            pages[futures[future]] = future.result()
            finished += 1
            if on_progress:
                on_progress(finished, len(images))
    return pages


def _join_transcript(pages: list[str], document_text: str) -> str:
    chunks = []
    for index, page in enumerate(pages, start=1):
        text = (page or "").strip()
        if text:
            chunks.append(f"PAGE {index}\n{text}")
    extra = (document_text or "").strip()
    if extra:
        chunks.append("DOCUMENT TEXT\n" + extra[:20000])
    return "\n\n".join(chunks).strip()


def _structure_transcript(transcript: str, complete_fn: CompleteFn) -> dict:
    if not transcript:
        return {"unreadable": ["the pictures"]}
    messages = build_structure_messages(transcript)
    try:
        data = parse_json_object(complete_fn(messages))
    except LlmError:
        return _transcript_fallback(transcript)
    return _keep_unread_narrative(data, transcript)


def _transcript_fallback(transcript: str) -> dict:
    """Keep the copied notes when the field list cannot be built."""
    text = transcript.strip()
    return {
        "customer_concern": text[:12000],
        "other_visible_notes": text[:20000],
        "unreadable": ["some fields still need a glance"],
    }


def _keep_unread_narrative(data: dict, transcript: str) -> dict:
    if not isinstance(data, dict):
        return _transcript_fallback(transcript)
    concern = str(data.get("customer_concern") or "").strip()
    cause = str(data.get("cause") or "").strip()
    correction = str(data.get("correction") or "").strip()
    if concern or cause or correction:
        return data
    data["customer_concern"] = transcript.strip()[:12000]
    data["other_visible_notes"] = transcript.strip()[:20000]
    unreadable = data.get("unreadable")
    if not isinstance(unreadable, list):
        unreadable = []
    note = "notes were copied in full; check the fields"
    if note not in unreadable:
        unreadable.append(note)
    data["unreadable"] = unreadable
    return data


def _smaller_for_model(image: tuple[bytes, str]) -> tuple[bytes, str]:
    blob, mime = image
    try:
        return shrink_image(blob, max_edge=1600)
    except Exception:
        return blob, mime


def _merge_extracted(parts: list[dict]) -> dict:
    merged: dict = {}
    list_keys = ("labor_operations", "parts", "repair_orders", "time_punches", "tech_numbers", "unreadable")
    for part in parts:
        for key, value in part.items():
            if key in list_keys and isinstance(value, list):
                merged.setdefault(key, [])
                merged[key].extend(value)
                continue
            if key in ("customer_concern", "cause", "correction", "tech_notes", "other_visible_notes"):
                current = str(merged.get(key) or "")
                extra = str(value or "")
                if extra and extra not in current:
                    merged[key] = (current + "\n" + extra).strip()
                continue
            if not merged.get(key) and value not in (None, "", [], {}):
                merged[key] = value
    return merged


def build_audit_messages(repair_order: dict, excerpts: list[dict]) -> list:
    user = (
        "REPAIR ORDER\n"
        + json.dumps(repair_order, indent=2)
        + "\n\nMANUAL EXCERPTS\n"
        + format_excerpts(excerpts)
    )
    return [
        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def run_audit(
    repair_order: dict,
    chunks: list[dict],
    *,
    complete: Optional[CompleteFn] = None,
) -> dict:
    """Compare a repair order to stored chunks and to the claim-acknowledgement checklist.

    Empty manual retrieval does not call the model. The Reynolds Ignite checklist still runs.
    """
    order = normalize_repair_order(repair_order)
    checklist = check_claim_criteria(order)
    retrieved = retrieve_for_repair_order(order, chunks)
    manual_findings: list[dict] = []
    if retrieved:
        messages = build_audit_messages(order, retrieved)
        try:
            raw = (complete or default_complete)(messages)
            parsed = parse_json_object(raw)
            manual_findings = validate_findings(parsed.get("findings"), retrieved)
        except LlmError:
            manual_findings = []
    findings = _sort_findings(checklist + manual_findings)
    summary = build_summary(order.get("ro_number") or "", findings)
    if not retrieved:
        summary = (
            "No stored manual section matched this document, so no manual policy was added. "
            + summary
        )
    return {
        "ro": order,
        "findings": findings,
        "summary": summary,
        "retrieved": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "page_number": chunk.get("page_number"),
                "section_label": chunk.get("section_label"),
                "text": chunk.get("text"),
            }
            for chunk in retrieved
        ],
        "manual_excerpt_count": len(retrieved),
    }


def _sort_findings(findings: list[dict]) -> list[dict]:
    return sorted(
        findings,
        key=lambda item: (
            0 if item.get("counts_as_required_correction") else 1,
            SEVERITIES.index(item["severity"]) if item.get("severity") in SEVERITIES else 9,
            str(item.get("ro_field") or ""),
        ),
    )


def _flatten_repair_orders(data: dict) -> dict:
    """Copy per-RO lines onto the top-level lists when the model only filled repair_orders."""
    blocks = _as_list(data.get("repair_orders"))
    if not blocks:
        return data
    labor: list[dict] = []
    parts: list[dict] = []
    techs: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        ro_number = block.get("ro_number") or ""
        tech = block.get("technician_id") or ""
        if tech:
            techs.append(str(tech))
        for line in _as_list(block.get("labor_lines")) or _as_list(block.get("labor_operations")):
            if isinstance(line, dict):
                labor.append({**line, "ro_number": line.get("ro_number") or ro_number, "tech_number": line.get("tech_number") or tech})
        for line in _as_list(block.get("part_lines")) or _as_list(block.get("parts")):
            if isinstance(line, dict):
                parts.append({**line, "ro_number": line.get("ro_number") or ro_number})
    if labor:
        data["labor_operations"] = labor
    if parts:
        data["parts"] = parts
    if techs:
        data["tech_numbers"] = techs
    if not data.get("technician_name"):
        for block in blocks:
            if isinstance(block, dict) and block.get("technician_name"):
                data["technician_name"] = block.get("technician_name")
                break
    return data


def _normalize_repair_blocks(raw: object, labor: list[dict], parts: list[dict]) -> list[dict]:
    blocks = []
    for block in _as_list(raw):
        if not isinstance(block, dict):
            continue
        ro_number = _text(block.get("ro_number"))
        job_number = _text(block.get("job_number"))
        blocks.append({
            "ro_number": ro_number,
            "job_number": job_number,
            "add_on": _add_on_value(block, job_number),
            "technician_id": _text(block.get("technician_id")),
            "technician_name": _text(block.get("technician_name")),
            "total_parts": _text(block.get("total_parts")),
            "total_labor": _text(block.get("total_labor")),
            "total_special_service": _text(block.get("total_special_service")),
            "pre_tax_total": _text(block.get("pre_tax_total")),
            "labor_lines": [
                row for row in labor if not ro_number or _text(row.get("ro_number")) in {"", ro_number}
            ] if labor else _copy_lines(block.get("labor_lines") or block.get("labor_operations")),
            "part_lines": [
                row for row in parts if not ro_number or _text(row.get("ro_number")) in {"", ro_number}
            ] if parts else _copy_lines(block.get("part_lines") or block.get("parts")),
        })
    return blocks


def _copy_lines(value: object) -> list[dict]:
    return [dict(row) for row in _as_list(value) if isinstance(row, dict)]


def _bound_complete(*, json_mode: bool = True, max_tokens: int | None = None) -> CompleteFn:
    """Read the API key on the main thread, then allow batch workers to call the model."""
    key, model = read_llm_settings()

    def complete_fn(messages: list) -> str:
        if not key:
            raise LlmError(
                "OPENAI_API_KEY is not set. Add it to .env or Streamlit secrets to check repair orders."
            )
        return complete_chat(
            messages,
            api_key=key,
            model=model,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )

    return complete_fn


def default_complete(messages: list) -> str:
    return _bound_complete()(messages)


MAX_CLAIM_PHOTOS = 20


def append_claim_photos(
    tray: list[dict],
    incoming: list[tuple[str, bytes]],
    *,
    limit: int = MAX_CLAIM_PHOTOS,
) -> tuple[list[dict], list[str]]:
    """Add pictures to a claim. The same shot is not added twice, and the tray stops at the limit."""
    warnings: list[str] = []
    updated = list(tray)
    seen = set()
    for item in updated:
        seen.add(item.get("sha") or "")
        seen.add(item.get("raw_sha") or "")
    for name, raw in incoming:
        if not raw:
            continue
        raw_sha = hashlib.sha256(raw).hexdigest()
        if raw_sha in seen:
            continue
        if len(updated) >= limit:
            warnings.append(
                f"This claim already has {limit} pictures. Remove one before adding another."
            )
            break
        try:
            jpeg, _mime = shrink_image(raw)
        except Exception:
            warnings.append(
                f"{name or 'Picture'} was not added. Take that page again as a JPG, or choose Take Photo."
            )
            continue
        sha = hashlib.sha256(jpeg).hexdigest()
        if sha in seen:
            continue
        seen.add(raw_sha)
        seen.add(sha)
        updated.append(
            {
                "name": name or f"photo-{len(updated) + 1}.jpg",
                "sha": sha,
                "raw_sha": raw_sha,
                "data": jpeg,
            }
        )
    return updated, warnings


def shrink_image(data: bytes, *, max_edge: int = 1600) -> tuple[bytes, str]:
    """Turn a phone photo into an upright JPEG the vision model can read."""
    from PIL import Image, ImageOps

    _register_heif()
    with Image.open(io_bytes(data)) as image:
        upright = ImageOps.exif_transpose(image) or image
        converted = upright.convert("RGB")
        converted.thumbnail((max_edge, max_edge))
        buf = io_bytes()
        converted.save(buf, format="JPEG", quality=80, optimize=True)
        return buf.getvalue(), "image/jpeg"


def prepare_documents(files: list[tuple[str, bytes]], *, max_pages: int = MAX_CLAIM_PHOTOS) -> dict:
    """Prepare one or more phone photos, scans, or PDFs."""
    images: list[tuple[bytes, str]] = []
    texts: list[str] = []
    warnings: list[str] = []
    for name, data in files:
        prepared = prepare_ro_input(name, data, max_pages=max_pages)
        images.extend(prepared["images"])
        if prepared.get("document_text"):
            texts.append(prepared["document_text"])
        warnings.extend(prepared.get("warnings") or [])
    if len(images) > max_pages:
        warnings.append(f"Only the first {max_pages} photos were sent to be read.")
        images = images[:max_pages]
    if not images and not any(text.strip() for text in texts):
        raise LlmError("No readable photo was attached. Take a picture or upload a JPG, PNG, or PDF.")
    return {"images": images, "document_text": "\n\n".join(texts), "warnings": warnings}


def prepare_ro_input(filename: str, data: bytes, *, max_pages: int = MAX_CLAIM_PHOTOS) -> dict:
    """Turn a camera photo, image upload, or PDF into model inputs."""
    name = (filename or "").lower()
    warnings: list[str] = []
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from lib.warranty_audit_manual import extract_pdf_pages, render_pdf_page_images

        images_raw = render_pdf_page_images(data, max_pages=max_pages)
        images = [_safe_shrink(blob) for blob in images_raw]
        document_text = ""
        if not images:
            try:
                pages = extract_pdf_pages(data)
            except Exception as exc:
                raise LlmError(str(exc)) from None
            document_text = "\n\n".join(
                f"PDF page {page['page_number']}\n{page['text']}" for page in pages if page.get("text")
            ).strip()
            if not document_text:
                raise LlmError(
                    "Could not read this PDF. Upload a JPG, PNG, or a PDF with visible pages."
                )
            warnings.append("PDF pages could not be rendered, so the text layer was read instead.")
        else:
            try:
                page_count = len(extract_pdf_pages(data))
            except Exception:
                page_count = len(images)
            if page_count > max_pages:
                warnings.append(
                    f"Only the first {max_pages} of {page_count} PDF pages were sent to be read."
                )
        return {"images": images, "document_text": document_text, "warnings": warnings}

    mime = _image_mime(data, name)
    if not mime:
        raise LlmError("Upload a JPG, PNG, or PDF repair order.")
    return {
        "images": [_safe_shrink(data)],
        "document_text": "",
        "warnings": warnings,
    }


def _safe_shrink(data: bytes) -> tuple[bytes, str]:
    try:
        return shrink_image(data)
    except Exception:
        mime = _image_mime(data, "")
        if mime == "image/heic":
            raise LlmError(
                "This iPhone photo is in HEIC format. Tap Upload a photo, choose Take Photo, "
                "or set the iPhone camera to Most Compatible so pictures save as JPG."
            )
        if mime in {"image/jpeg", "image/png", "image/webp"}:
            return data, mime
        raise LlmError("This picture could not be read. Upload a JPG or PNG.")


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        return


def _image_mime(data: bytes, name: str) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {
        b"heic",
        b"heif",
        b"mif1",
        b"heix",
        b"hevc",
    }:
        return "image/heic"
    lowered = name.lower()
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith((".heic", ".heif")):
        return "image/heic"
    return ""


def _secret(key: str) -> str:
    env = (os.getenv(key) or "").strip()
    if env:
        return env
    try:
        import streamlit as st

        return str(st.secrets.get(key, "") or "").strip()
    except Exception:
        return ""


def _add_on_value(source: dict, job_number: object) -> bool | None:
    """A plus sign printed next to the job number marks a warranty add-on."""
    job = _text(job_number) or _text(source.get("job_number"))
    if "+" in job:
        return True
    flag = _boolish(source.get("add_on"))
    if flag is None:
        flag = _boolish(source.get("warranty_add_on"))
    return flag


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if text.casefold() in {"", "null", "none", "n/a", "na", "unreadable", "unknown"}:
        return ""
    return text


def _boolish(value: object):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"true", "yes", "y", "signed", "present"}:
        return True
    if text in {"false", "no", "n", "unsigned", "missing", "blank"}:
        return False
    return None


def _as_list(value: object) -> list:
    """Model fields that should be lists sometimes come back as one object or a number."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _as_items(value: object) -> list:
    """A technician id may arrive as one number instead of a list of numbers."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [value]
    return []


def _rows(value: object, fields: tuple[str, ...]) -> list[dict]:
    rows = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        row = {field: _text(item.get(field)) for field in fields}
        row["_source"] = item
        visible = [row[field] for field in fields]
        failed = item.get("failed")
        if not any(visible) and _boolish(failed) is None:
            continue
        rows.append(row)
    return rows


def io_bytes(data: bytes | None = None):
    import io

    return io.BytesIO() if data is None else io.BytesIO(data)

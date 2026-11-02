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
import socket
import urllib.error
import urllib.request
from typing import Callable, Optional

from lib.warranty_audit_claim import DEALER_CODE, check_claim_criteria
from lib.warranty_audit_manual import (
    SEVERITIES,
    build_summary,
    format_excerpts,
    redact_secrets,
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

Before any other text, write these lines from what is printed on this page:
VIN: <the 17-character VIN, or leave this blank>
PUNCH: <tech number> | <time on> | <time off> | <hours>
Write one PUNCH line for every time punch. If this page has no punch, write PUNCH: none

The VIN is in the top section of the FCA Global Claim Acknowledgement. It may be labeled VIN or Veh ID. Copy all 17 characters.
Time punches are the rows just above the words Warranty Copy at the bottom of the invoice. Copy every row in that block. A time may use a colon or a dot, such as 8:02 or 08.02. Copy the technician number, the time on, the time off, and the hours.

Then copy the rest of the page. Include every one of these when it is on the page:
- The top section of an FCA Global Claim Acknowledgement: claim number, RO number, in service date, date completed, date received, service advisor number, list number, VIN, coverage, claim type, submission type, and continuation. The RO number and the claim number are the same number. Authorization is usually blank. Do not fill it in.
- The technician name printed with the technician identification. It is on the claim acknowledgement, not in that top section.
- The full customer narrative and the technician notes, word for word: concern, cause, correction, tests, and what was found. If the word Goodwill appears, copy it.
- On that same Warranty Copy, every job number. When a small plus sign is printed beside the job number, copy it as "Job +2" or "Job 2 +" and copy any signature or initials next to that job.
- Every labor line: LOP, description, failure code, hours, and technician
- Every part: part number, description, quantity, and whether Failed Part is marked
- List Number. Copy the digits exactly, such as 2025123

Do not copy the owner's name. Pre-Tax Total is usually blank. Do not fill those in.
The service advisor is the number in the top section, not a person's name.
Keep the technician notes as full sentences. Keep every time punch on its own line.
If a line is hard to read, copy your best reading and mark it [unclear]. Do not leave the VIN, the notes, the dates, the list number, or the time punches out."""

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
The RO number and the claim number are the same number. Both are in the top section of the claim acknowledgement. Copy that number into ro_number and claim_number.
in_service_date, date_completed, date_received, list_number, and service_advisor are in that same top section. service_advisor is the advisor number, not a name. Copy the printed dates. Do not leave a printed date blank.
technician_name is on the claim acknowledgement next to the technician identification. It is not in the top section. Copy the name that is printed there.
job_number is the job number on the Warranty Copy invoice. add_on is true only when a small plus sign is printed beside that job number on the Warranty Copy. A plus sign inside a part number is not an add-on.
time_punches come from the rows just above Warranty Copy at the bottom of the invoice. Copy every punch. A time may use a colon or a dot, such as 8:02 or 08.02. Lines that start with PUNCH: are punches. A line that starts with VIN: is the vin. Do not leave vin or time_punches empty when those lines are in the page text.
list_number is the List Number in the top section. Copy every digit, such as 2025123.
owner_name must be blank. Do not copy an owner name.
authorization is usually blank on the claim acknowledgement. Leave it blank. Do not invent a number.
dealer_code is 68888.
pre_tax_total is usually blank. Leave it blank. Do not calculate it.
signatures.service_manager is true when your signature or initials are on the Warranty Copy next to a job that has a plus sign, or next to a Goodwill job. It is false when that spot is visible and unsigned, and null when the Warranty Copy is not in the pictures.
A claim can contain more than one repair order. Keep each RO's lines and totals together in repair_orders.
Do not invent values that are not on the page."""

AUDIT_SYSTEM_PROMPT = """You are a warranty-audit checker for an automobile dealership.
You compare one repair order to excerpts from the documents the dealership stored.
Those documents are the warranty manual and the dealer audit guide.
You have no other policy source.

Rules:
- Use only the excerpts in the user message. Do not use outside knowledge of Stellantis, FCA, OEM, or dealer policy. If a requirement is not written in those excerpts, do not flag it.
- Every finding must include citation_quote: a contiguous verbatim copy of the excerpt sentence or sentences that state the requirement. Do not paraphrase, shorten with ellipses, or merge text from different excerpts.
- manual_page must be the pdf_page number on the excerpt you quoted. manual_section must be the section label on that excerpt.
- If the repair order already satisfies the excerpt, do not file a finding.
- If the excerpts do not address the repair, return an empty findings array.
- Treat null signatures and fields listed as unreadable as unknown. Do not flag an unknown field as missing.
- Flag a signature only when the repair order value is false and an excerpt requires that signature.
- Flag time punches only when an excerpt requires them for this repair and the punches are missing or incomplete. If the excerpt says time punching is not required for a dealer type, do not flag a missing punch unless the repair order shows that dealer type.
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
    _allow_retry: bool = True,
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
        detail = redact_secrets(exc.read().decode("utf-8", errors="replace")[:400], api_key)
        if exc.code == 429:
            if _allow_retry:
                import time
                time.sleep(1)
                return complete_chat(
                    messages,
                    api_key=api_key,
                    model=model,
                    timeout=timeout,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                    _allow_retry=False,
                )
            raise LlmError(
                "The model is busy because of a rate limit. Wait a moment and read the repair order again."
            ) from None
        if exc.code in {408, 500, 502, 503, 504}:
            raise LlmError(
                f"The model request failed ({exc.code}). Try the repair order again in a moment."
            ) from None
        if exc.code == 401:
            raise LlmError(
                "OPENAI_API_KEY was rejected. Check the key in Streamlit secrets or .env."
            ) from None
        raise LlmError(f"The model request failed ({exc.code}). {detail}") from None
    except urllib.error.URLError as exc:
        raise LlmError(f"Could not reach the model API. {redact_secrets(str(exc.reason), api_key)}") from None
    except (TimeoutError, socket.timeout):
        raise LlmError("The model request timed out. Try a clearer photo or fewer pages.") from None
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LlmError("The model returned an unexpected response.") from None
    if not isinstance(content, str) or not content.strip():
        raise LlmError("The model returned an empty response.")
    return content


def build_transcribe_messages(*, image: tuple[bytes, str], page_number: int) -> list:
    return _transcribe_request([(image, page_number)])


def build_transcribe_batch(images: list[tuple[bytes, str]], *, first_page: int) -> list:
    labeled = [(image, first_page + offset) for offset, image in enumerate(images)]
    return _transcribe_request(labeled)


def _transcribe_request(labeled: list[tuple[tuple[bytes, str], int]]) -> list:
    if len(labeled) == 1:
        page_number = labeled[0][1]
        intro = f"Page {page_number}.\n{TRANSCRIBE_USER_PROMPT}"
    else:
        names = ", ".join(f"PAGE {page}" for _image, page in labeled)
        intro = (
            "Copy these pages in order. Start each page with its own line, exactly "
            f"{names}.\n{TRANSCRIBE_USER_PROMPT}"
        )
    content: list[dict] = [{"type": "text", "text": intro}]
    for (blob, mime), _page in labeled:
        encoded = base64.b64encode(blob).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
            }
        )
    return [
        {"role": "system", "content": TRANSCRIBE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def build_structure_messages(transcript: str) -> list:
    user = (
        EXTRACT_USER_PROMPT
        + "\n\nThe page text below was copied from the pictures. Use only that text.\n"
        + "Copy the full customer narrative into customer_concern, cause, and correction. Do not shorten it.\n"
        + "Copy every time punch from the Warranty Copy into time_punches. A line that starts with PUNCH: is one punch. Copy the VIN: line into vin. Do not leave vin or time_punches empty when that text is present. Copy every labor line and every part.\n"
        + "The top section of the claim acknowledgement has the in service date, date completed, service advisor number, and the RO number, which is the same as the claim number.\n"
        + "If the page text contains the notes, the dates, or the punches, those fields are readable. Do not leave them blank.\n\n"
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
    punches = _punch_rows(data.get("time_punches"))
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
    ro_number, claim_number = _same_ro_and_claim(data.get("ro_number"), data.get("claim_number"))
    kind = _text(data.get("document_type")).casefold().replace("-", " ").replace("_", " ")
    if "claim acknowledgement" in kind or kind == "claim":
        document_type = "claim_acknowledgement"
    else:
        document_type = "repair_order"
    dms = _text(data.get("dms")).casefold().replace("-", " ").replace("_", " ")
    return {
        "document_type": document_type,
        "dms": "reynolds_ignite" if "reynolds" in dms else "",
        "ro_number": ro_number,
        "open_date": _text(data.get("open_date")),
        "close_date": _text(data.get("close_date")),
        "repair_date": _text(data.get("repair_date")),
        "vin": _text(data.get("vin")),
        "mileage": _text(data.get("mileage")),
        "claim_number": claim_number,
        "claim_status": _text(data.get("claim_status")),
        "dealer_code": DEALER_CODE,
        "in_service_date": _text(data.get("in_service_date")),
        "warranty_coverage": _text(data.get("warranty_coverage")),
        "claim_type": _text(data.get("claim_type")),
        "submission_type": _text(data.get("submission_type")),
        "continuation": _text(data.get("continuation")),
        "date_received": _text(data.get("date_received")),
        "date_completed": _text(data.get("date_completed")),
        "process_date": _text(data.get("process_date")),
        "authorization": _text(data.get("authorization")),
        "owner_name": "",
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
    transcribe_fn = complete or _bound_complete(json_mode=False, max_tokens=8192)
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
        words = text.split()
        if len(text) < 12 or (len(text) < 40 and len(words) < 4) or text.count("[unclear]") >= 4:
            return f"[Page {index + 1} is too blurry to read. Take that page again.]"
        return text

    if len(images) == 1:
        if on_progress:
            on_progress(1, 1)
        return [copy_page(0, images[0])]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    batch_size = 2
    groups = [images[start:start + batch_size] for start in range(0, len(images), batch_size)]
    pages: list[str] = [""] * len(images)

    def copy_group(start: int, group: list[tuple[bytes, str]]) -> list[str]:
        messages = build_transcribe_batch(group, first_page=start + 1)
        try:
            text = transcribe_fn(messages).strip()
        except LlmError as exc:
            return [f"[Page {start + offset + 1} could not be read. {exc}]" for offset in range(len(group))]
        return _split_page_copy(text, len(group), first_page=start + 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(copy_group, start, group): start
            for start, group in ((index * batch_size, group) for index, group in enumerate(groups))
        }
        finished = 0
        for future in as_completed(futures):
            start = futures[future]
            copied = future.result()
            for offset, text in enumerate(copied):
                pages[start + offset] = text
            finished += len(copied)
            if on_progress:
                on_progress(min(finished, len(images)), len(images))
    return pages


def _split_page_copy(text: str, count: int, *, first_page: int = 1) -> list[str]:
    """Split a multi-page copy on PAGE N lines. Keep the whole reply if those lines are missing."""
    if count <= 1:
        return [text]
    parts = re.split(r"(?im)^page\s+(\d+)\s*$", text.strip())
    if len(parts) < 3:
        return [text] + [""] * (count - 1)
    pages = [""] * count
    pairs = iter(parts[1:])
    for number, body in zip(pairs, pairs):
        index = int(number) - first_page
        if 0 <= index < count:
            pages[index] = body.strip()
    if not any(pages):
        return [text] + [""] * (count - 1)
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
        data = _transcript_fallback(transcript)
    else:
        data = _keep_unread_narrative(data, transcript)
    return _recover_vin_and_punches(data, transcript)


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


def _recover_vin_and_punches(data: dict, transcript: str) -> dict:
    """Fill a blank VIN or blank punch list from the copied page text.

    The field step often leaves these empty even when the page copy has them.
    """
    if not isinstance(data, dict):
        data = {}
    blob = "\n".join(
        part
        for part in (
            transcript,
            _text(data.get("customer_concern")),
            _text(data.get("cause")),
            _text(data.get("correction")),
            _text(data.get("tech_notes")),
            _text(data.get("other_visible_notes")),
            _text(data.get("vehicle_description")),
        )
        if part
    )
    if not _text(data.get("vin")):
        vin = _vin_from_text(blob)
        if vin:
            data["vin"] = vin
    found = _punches_from_text(blob)
    if found:
        data["time_punches"] = _merge_punch_lists(_punch_rows(data.get("time_punches")), found)
    return data


def _vin_from_text(text: str) -> str:
    """Prefer a VIN that is labeled. Otherwise take a 17-character VIN that checks out."""
    for match in re.finditer(r"(?im)^VIN:\s*(\S.*?)\s*$", text):
        vin = _labeled_vin(match.group(1))
        if vin and vin.casefold() not in {"none", "blank", "n/a"}:
            return vin
    label = re.compile(
        r"(?i)\b(?:v\s*\.?\s*i\s*\.?\s*n\.?|veh(?:icle)?\s*id(?:entification)?(?:\s*number)?)\b"
    )
    for match in label.finditer(text):
        vin = _labeled_vin(text[match.end():match.end() + 48])
        if vin:
            return vin
    for match in re.finditer(r"\b[A-HJ-NPR-Z0-9]{17}\b", text, flags=re.IGNORECASE):
        vin = match.group(0).upper()
        if any(char.isalpha() for char in vin) and any(char.isdigit() for char in vin) and _vin_check_ok(vin):
            return vin
    return ""


def _labeled_vin(raw: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    direct = re.search(r"[A-HJ-NPR-Z0-9]{17}", compact)
    if direct:
        return direct.group(0)
    repaired = compact.translate(str.maketrans({"I": "1", "O": "0", "Q": "0"}))
    match = re.search(r"[A-HJ-NPR-Z0-9]{17}", repaired)
    if match and _vin_check_ok(match.group(0)):
        return match.group(0)
    return ""


def _vin_check_ok(vin: str) -> bool:
    translit = {
        **{str(digit): digit for digit in range(10)},
        "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
        "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
        "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
    }
    weights = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
    if len(vin) != 17:
        return False
    total = 0
    for char, weight in zip(vin, weights):
        value = translit.get(char)
        if value is None:
            return False
        total += value * weight
    check = total % 11
    expected = "X" if check == 10 else str(check)
    return vin[8] == expected


_COLON_TIME = re.compile(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?\b")
_DOT_TIME = re.compile(r"\b(\d{1,2})\.(\d{2})\b")
_PUNCH_REGION = re.compile(
    r"(?i)warranty copy|tech time|time punch|punch time|time clock|actual time|technician time"
)


def _punches_from_text(text: str) -> list[dict]:
    rows: list[dict] = []
    for match in re.finditer(r"(?im)^PUNCH:\s*(.+)$", text):
        payload = match.group(1).strip()
        if payload.casefold() in {"none", "n/a", "na", "blank", "no punches", "no punch"}:
            continue
        row = _punch_from_line(payload)
        if row:
            rows.append(row)
    lines = text.splitlines()
    regions = _punch_regions(lines)
    for index, line in enumerate(lines):
        if re.match(r"(?i)\s*PUNCH:", line):
            continue
        row = _punch_from_line(line)
        if not _line_is_punch(line, row, index in regions):
            continue
        rows.append(row)
    return _merge_punch_lists([], rows)


def _punch_regions(lines: list[str]) -> set[int]:
    indexes: set[int] = set()
    for index, line in enumerate(lines):
        if _PUNCH_REGION.search(line) or re.search(r"(?i)\bpunch\b", line):
            for offset in range(-15, 6):
                neighbor = index + offset
                if 0 <= neighbor < len(lines):
                    indexes.add(neighbor)
        if re.search(r"(?i)\bon\b", line) and re.search(r"(?i)\boff\b", line):
            indexes.add(index)
    return indexes


def _line_is_punch(line: str, row: dict | None, in_region: bool) -> bool:
    if not row:
        return False
    if re.search(r"(?i)\bpunch\b", line):
        return True
    if re.search(r"(?i)\bon\b", line) and re.search(r"(?i)\boff\b", line):
        return True
    return bool(in_region and row.get("tech_number"))


def _punch_from_line(line: str) -> dict | None:
    clocks = _clocks(line)
    if len(clocks) < 2:
        return None
    return {
        "tech_number": _tech_on_line(line),
        "on": clocks[0],
        "off": clocks[1],
        "hours": _hours_on_line(line),
    }


def _clocks(line: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for match in _COLON_TIME.finditer(line):
        found.append((match.start(), _clock_text(match.group(1), match.group(2), match.group(3))))
    if len(found) < 2:
        for match in _DOT_TIME.finditer(line):
            hour = int(match.group(1))
            minute = int(match.group(2))
            if hour > 23 or minute > 59:
                continue
            if len(found) >= 2 and hour < 5:
                continue
            if hour < 5 and not re.search(r"(?i)\bpunch\b|\bon\b|\boff\b", line):
                continue
            found.append((match.start(), _clock_text(match.group(1), match.group(2), "")))
    found.sort(key=lambda item: item[0])
    return [text for _start, text in found]


def _clock_text(hour: str, minute: str, ampm: str) -> str:
    text = f"{int(hour)}:{minute}"
    if ampm:
        text = f"{text} {ampm.upper()}"
    return text


def _tech_on_line(line: str) -> str:
    labeled = re.search(
        r"(?i)\btech(?:nician)?(?:\s*(?:number|#|id|no))?\.?\s*[:#]?\s*(\d{2,6})\b",
        line,
    )
    if labeled:
        return labeled.group(1)
    scrubbed = _COLON_TIME.sub(" ", line)
    scrubbed = _DOT_TIME.sub(" ", scrubbed)
    scrubbed = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", scrubbed)
    for match in re.finditer(r"\b(\d{2,6})\b", scrubbed):
        number = match.group(1)
        if len(number) == 4 and 2015 <= int(number) <= 2039:
            continue
        return number
    return ""


def _hours_on_line(line: str) -> str:
    labeled = re.search(r"(?i)\b(?:hours|hrs)\b[:\s]*(\d{1,2}(?:\.\d{1,2})?)", line)
    if labeled:
        return labeled.group(1)
    if "|" in line:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 4 and re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", parts[-1]):
            return parts[-1]
    clocks = set(_clocks(line))
    for match in reversed(list(re.finditer(r"\b(\d{1,2}\.\d{1,2})\b", line))):
        value = match.group(1)
        hour, minute = value.split(".", 1)
        if len(minute) == 2 and _clock_text(hour, minute, "") in clocks:
            continue
        return value
    return ""


def _merge_punch_lists(current: list[dict], extra: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in list(current) + list(extra):
        key = (
            _text(row.get("tech_number")).casefold(),
            _text(row.get("on")).casefold(),
            _text(row.get("off")).casefold(),
        )
        if key in seen or not any(key):
            continue
        seen.add(key)
        merged.append(
            {
                "tech_number": _text(row.get("tech_number")),
                "on": _text(row.get("on")),
                "off": _text(row.get("off")),
                "hours": _text(row.get("hours")),
            }
        )
    return merged


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
    guide_chunks: Optional[list[dict]] = None,
    manual_name: str = "",
    guide_name: str = "",
    complete: Optional[CompleteFn] = None,
) -> dict:
    """Check one repair order against the warranty manual and the audit guide.

    Empty retrieval for a document does not call the model for that document.
    The Reynolds Ignite checklist still runs.
    """
    order = normalize_repair_order(repair_order)
    checklist = check_claim_criteria(order)
    manual_findings, manual_hits = _audit_document(
        order,
        chunks,
        document_name=manual_name or "Warranty manual",
        complete=complete,
    )
    guide_findings, guide_hits = _audit_document(
        order,
        list(guide_chunks or []),
        document_name=guide_name or "Audit guide",
        complete=complete,
    )
    findings = _sort_findings(checklist + manual_findings + guide_findings)
    summary = _audit_summary(
        order.get("ro_number") or "",
        findings,
        manual_stored=bool(chunks),
        manual_hits=len(manual_hits),
        manual_name=manual_name or "the warranty manual",
        guide_stored=guide_chunks is not None and bool(guide_chunks),
        guide_hits=len(guide_hits),
        guide_name=guide_name or "the audit guide",
    )
    retrieved = manual_hits + guide_hits
    return {
        "ro": order,
        "findings": findings,
        "summary": summary,
        "retrieved": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "page_number": chunk.get("page_number"),
                "section_label": chunk.get("section_label"),
                "document_name": chunk.get("document_name") or "",
                "text": chunk.get("text"),
            }
            for chunk in retrieved
        ],
        "manual_excerpt_count": len(manual_hits),
        "guide_excerpt_count": len(guide_hits),
    }


def _audit_document(
    order: dict,
    chunks: list[dict],
    *,
    document_name: str,
    complete: Optional[CompleteFn],
) -> tuple[list[dict], list[dict]]:
    if not chunks:
        return [], []
    retrieved = [
        {**chunk, "document_name": document_name}
        for chunk in retrieve_for_repair_order(order, chunks)
    ]
    if not retrieved:
        return [], []
    messages = build_audit_messages(order, retrieved)
    try:
        raw = (complete or default_complete)(messages)
        parsed = parse_json_object(raw)
        findings = validate_findings(parsed.get("findings"), retrieved)
    except LlmError:
        findings = []
    return findings, retrieved


def _audit_summary(
    ro_number: str,
    findings: list[dict],
    *,
    manual_stored: bool,
    manual_hits: int,
    manual_name: str,
    guide_stored: bool,
    guide_hits: int,
    guide_name: str,
) -> str:
    notes = []
    if not manual_stored:
        notes.append("No warranty manual is stored, so this repair order was not checked against one.")
    elif not manual_hits:
        notes.append(
            "No stored manual section matched this document, so no manual policy was added."
        )
    else:
        notes.append(f"Checked {manual_hits} section(s) of {manual_name}.")
    if not guide_stored:
        notes.append("No audit guide is stored, so this repair order was not checked against that document.")
    elif not guide_hits:
        notes.append(f"No section of {guide_name} matched this repair order.")
    else:
        notes.append(f"Checked {guide_hits} section(s) of {guide_name}.")
    return " ".join(notes) + " " + build_summary(ro_number, findings)


REFERENCE_PAGE_LIMIT = 40
REFERENCE_TRANSCRIBE_PROMPT = """Copy this page of a warranty manual or dealer audit guide exactly.
Keep headings, reason codes, and bullet points. Do not summarize. Plain text only."""


def transcribe_reference_pdf(data: bytes, *, on_progress: Optional[Callable[[int, int], None]] = None) -> list[dict]:
    """Read a scanned reference PDF into page text that can be cited later."""
    from lib.warranty_audit_manual import ManualExtractError, render_pdf_page_images

    images = render_pdf_page_images(data, max_pages=REFERENCE_PAGE_LIMIT, resolution=120)
    if not images:
        raise ManualExtractError(
            "This PDF has no text layer and its pages could not be read. Upload a text PDF or a clearer scan."
        )
    complete_fn = _bound_complete(json_mode=False, max_tokens=4096)
    prepared = []
    for blob in images:
        try:
            prepared.append(shrink_image(blob, max_edge=1600))
        except Exception:
            prepared.append((blob, "image/png"))

    def copy_page(index: int, image: tuple[bytes, str]) -> str:
        blob, mime = image
        encoded = base64.b64encode(blob).decode("ascii")
        messages = [
            {"role": "system", "content": "You copy printed manual pages exactly. Plain text only."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Page {index}.\n{REFERENCE_TRANSCRIBE_PROMPT}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
                    },
                ],
            },
        ]
        try:
            return complete_fn(messages).strip()
        except LlmError as exc:
            return f"[Page {index} could not be read. {exc}]"

    pages: list[str] = [""] * len(prepared)
    if len(prepared) == 1:
        pages[0] = copy_page(1, prepared[0])
        if on_progress:
            on_progress(1, 1)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(copy_page, index, image): index - 1
                for index, image in enumerate(prepared, start=1)
            }
            finished = 0
            for future in as_completed(futures):
                pages[futures[future]] = future.result()
                finished += 1
                if on_progress:
                    on_progress(finished, len(prepared))
    return [{"page_number": index, "text": text} for index, text in enumerate(pages, start=1) if text.strip()]


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
        converted.save(buf, format="JPEG", quality=85, optimize=True)
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

        images_raw = render_pdf_page_images(data, max_pages=max_pages, resolution=170)
        images = [_safe_shrink(blob) for blob in images_raw]
        document_text = _pdf_text_layer(data, max_pages)
        if not images and not document_text:
            raise LlmError(
                "Could not read this PDF. Upload a JPG, PNG, or a PDF with visible pages."
            )
        if not images:
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


def _pdf_text_layer(data: bytes, max_pages: int) -> str:
    """Keep the PDF's own text so a printed VIN and punch block are not left to the photo."""
    try:
        from lib.warranty_audit_manual import extract_pdf_pages

        pages = extract_pdf_pages(data)
    except Exception:
        return ""
    chunks = []
    for page in pages[:max_pages]:
        text = str(page.get("text") or "").strip()
        if text:
            chunks.append(f"PDF page {page.get('page_number')}\n{text}")
    return "\n\n".join(chunks).strip()


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


def _same_ro_and_claim(ro_value: object, claim_value: object) -> tuple[str, str]:
    """The RO number and the claim number are the same number."""
    ro_number = _text(ro_value)
    claim_number = _text(claim_value)
    if ro_number and not claim_number:
        claim_number = ro_number
    elif claim_number and not ro_number:
        ro_number = claim_number
    return ro_number, claim_number


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


def _punch_rows(value: object) -> list[dict]:
    """Read a punch whether the model named the columns on/off or time_on/time_off."""
    aliases = {
        "tech_number": ("tech_number", "tech", "technician", "technician_number", "technician_id", "tech_id"),
        "on": ("on", "time_on", "on_time", "start", "time_in", "clock_on", "punch_in"),
        "off": ("off", "time_off", "off_time", "stop", "finish", "time_out", "clock_off", "punch_out"),
        "hours": ("hours", "hrs", "elapsed", "actual_hours"),
    }
    rows = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        row = {}
        for field, names in aliases.items():
            text = ""
            for name in names:
                if _text(item.get(name)):
                    text = _text(item.get(name))
                    break
            row[field] = text
        if any(row.values()):
            rows.append(row)
    return rows


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

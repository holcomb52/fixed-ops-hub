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

EXTRACT_USER_PROMPT = """Read this Reynolds Ignite repair order or FCA Global Claim Acknowledgement.
Return JSON with exactly these keys:
document_type ("claim_acknowledgement" when the page is a Global Claim Acknowledgement, otherwise "repair_order"),
dms ("reynolds_ignite" when the printout is from Reynolds Ignite, otherwise ""),
ro_number, open_date, close_date, repair_date, vin, mileage,
claim_number, claim_status, dealer_code, in_service_date, warranty_coverage,
claim_type, submission_type, continuation, date_received, date_completed, process_date,
authorization, owner_name, vehicle_description, service_advisor,
list_number, reference_number, prior_claim, technician_name,
customer_concern, cause, correction,
labor_operations (list of objects with ro_number, op_code, description, failure_code, hours, tech_number),
tech_numbers (list of strings),
time_punches (list of objects with tech_number, on, off, hours),
parts (list of objects with ro_number, part_number, description, quantity, failed),
repair_orders (list of objects with ro_number, technician_id, technician_name,
total_parts, total_labor, total_special_service, pre_tax_total,
labor_lines, part_lines),
signatures (object with customer, advisor, technician; each true, false, or null),
other_visible_notes (string),
unreadable (list of field names you could not read).

On a claim acknowledgement, split Customer Narrative into customer_concern (what the customer stated),
cause (what was found), and correction (the repair performed, including any labor operation and hours the narrative states).
Copy LOP into op_code, Failure Code into failure_code, and Hours into hours.
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
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LlmError("The model did not return valid JSON.") from None
    if not isinstance(data, dict):
        raise LlmError("The model did not return a JSON object.")
    return data


def complete_chat(messages: list, *, api_key: str, model: str, timeout: int = 120) -> str:
    """Call the OpenAI chat API. The key is sent only in the Authorization header."""
    if not api_key:
        raise LlmError("OPENAI_API_KEY is not set.")
    payload = {
        "model": model or DEFAULT_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
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


def build_extract_messages(*, images: list[tuple[bytes, str]], document_text: str = "") -> list:
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
    labor = _rows(
        data.get("labor_operations"),
        ("ro_number", "op_code", "description", "failure_code", "hours", "tech_number"),
    )
    punches = _rows(data.get("time_punches"), ("tech_number", "on", "off", "hours"))
    parts = []
    for row in _rows(data.get("parts"), ("ro_number", "part_number", "description", "quantity")):
        source = row.pop("_source", {})
        row["failed"] = _boolish(source.get("failed"))
        parts.append(row)
    for row in labor + punches:
        row.pop("_source", None)
    tech_numbers = []
    seen = set()
    for value in list(data.get("tech_numbers") or []) + [
        row.get("tech_number") for row in labor + punches
    ]:
        text = _text(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            tech_numbers.append(text)
    unreadable = []
    for value in data.get("unreadable") or []:
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
        },
        "other_visible_notes": _text(data.get("other_visible_notes")),
        "unreadable": unreadable,
    }


def extract_repair_order(
    *,
    images: list[tuple[bytes, str]],
    document_text: str = "",
    complete: Optional[CompleteFn] = None,
) -> dict:
    if not images and not str(document_text or "").strip():
        raise LlmError("No readable repair-order image or text was provided.")
    messages = build_extract_messages(images=images, document_text=document_text)
    raw = (complete or default_complete)(messages)
    return normalize_repair_order(parse_json_object(raw))


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
        raw = (complete or default_complete)(messages)
        parsed = parse_json_object(raw)
        manual_findings = validate_findings(parsed.get("findings"), retrieved)
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
    blocks = data.get("repair_orders")
    if not isinstance(blocks, list):
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
        for line in block.get("labor_lines") or block.get("labor_operations") or []:
            if isinstance(line, dict):
                labor.append({**line, "ro_number": line.get("ro_number") or ro_number, "tech_number": line.get("tech_number") or tech})
        for line in block.get("part_lines") or block.get("parts") or []:
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
    if isinstance(raw, list):
        for block in raw:
            if not isinstance(block, dict):
                continue
            ro_number = _text(block.get("ro_number"))
            blocks.append({
                "ro_number": ro_number,
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
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def default_complete(messages: list) -> str:
    key, model = read_llm_settings()
    if not key:
        raise LlmError(
            "OPENAI_API_KEY is not set. Add it to .env or Streamlit secrets to check repair orders."
        )
    return complete_chat(messages, api_key=key, model=model)


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


def _rows(value: object, fields: tuple[str, ...]) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
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

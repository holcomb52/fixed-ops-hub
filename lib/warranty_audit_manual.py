"""Extract, chunk, retrieve, and citation-check a warranty manual.

Policy checks must quote text that was actually stored. Nothing in this module
invents requirements.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Iterable, Optional

MIN_MANUAL_CHARS = 200
MAX_CHUNK_CHARS = 1400
MAX_MANUAL_PAGES = 400
CHUNK_OVERLAP = 180
MIN_CHUNK_CHARS = 20
MIN_QUOTE_CHARS = 24
MAX_EXCERPTS = 16
# Phrases that appear in the stored warranty manual or the auditor's reason-code guide.
# One stored chunk for each phrase is included when that phrase is actually in the text.
RULE_ANCHORS = (
    "3 c's",
    "time punching",
    "initialed with the date and time by the service manager",
    "tech notes do not support",
    "add on operations",
    "time documentation",
)

SEVERITIES = ("critical", "major", "minor", "info")
REQUIRED_SEVERITIES = ("critical", "major", "minor")

_HEADING_SECTION = re.compile(r"^(section|chapter|part)\s+\d+", re.IGNORECASE)
_HEADING_NUMBERED = re.compile(r"^\d+(?:\.\d+){1,3}\s+\S")
_TOKEN = re.compile(r"[a-z0-9]{4,}")

# Common words that would match almost every warranty page.
_STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "before",
    "claim",
    "claims",
    "each",
    "from",
    "have",
    "into",
    "must",
    "only",
    "order",
    "other",
    "repair",
    "shall",
    "should",
    "that",
    "their",
    "them",
    "then",
    "this",
    "warranty",
    "when",
    "with",
    "your",
}

# Always searched so documentation rules are retrieved even when the
# complaint text is about a specific repair.
DOCUMENTATION_PROBES = (
    "technician time punch labor operation",
    "customer signature authorization",
    "failed part number retention",
    "mileage vehicle identification",
    "cause correction complaint narrative",
    "labor operation hours",
    "tech notes documenting cause complaint",
    "add on operation service manager signature",
    "time documentation chargeback",
)


class ManualExtractError(ValueError):
    """Raised when a PDF cannot be used as the stored manual."""


def extract_pdf_pages(data: bytes) -> list[dict]:
    """Return 1-based PDF pages and their extractable text."""
    import pdfplumber

    pages: list[dict] = []
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise ManualExtractError(f"Could not open this PDF. {exc}") from None
    try:
        total = len(pdf.pages)
        for index, page in enumerate(pdf.pages[:MAX_MANUAL_PAGES], start=1):
            text = page.extract_text() or ""
            pages.append({"page_number": index, "text": _clean_text(text)})
        if pages and total > MAX_MANUAL_PAGES:
            pages[0]["_pdf_page_total"] = total
    finally:
        pdf.close()
    if not pages:
        raise ManualExtractError("This PDF has no pages.")
    return pages


def render_pdf_page_images(data: bytes, *, max_pages: int = 6, resolution: int = 140) -> list[bytes]:
    """Render the first PDF pages to PNG bytes for the vision model."""
    import pdfplumber

    images: list[bytes] = []
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception:
        return []
    try:
        for page in pdf.pages[:max_pages]:
            try:
                rendered = page.to_image(resolution=resolution)
                buf = io.BytesIO()
                rendered.original.save(buf, format="PNG")
                images.append(buf.getvalue())
            except Exception:
                continue
    finally:
        pdf.close()
    return images


def chunk_pages(pages: Iterable[dict]) -> list[dict]:
    """Split extracted pages into citation-sized chunks.

    Every chunk stays on a single PDF page so a quote cannot be matched to
    the wrong page.
    """
    chunks: list[dict] = []
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        paragraphs = _paragraphs(str(page.get("text") or ""))
        if not paragraphs:
            continue
        section = f"PDF page {page_number}"
        parts: list[str] = []
        parts_len = 0

        def emit(*, keep_overlap: bool) -> None:
            nonlocal parts, parts_len
            text = "\n\n".join(part for part in parts if part).strip()
            if len(text) >= MIN_CHUNK_CHARS:
                chunks.append(
                    {
                        "page_number": page_number,
                        "section_label": section,
                        "text": text,
                    }
                )
            if keep_overlap and len(text) > CHUNK_OVERLAP:
                tail = text[-CHUNK_OVERLAP:].lstrip()
                parts = [tail] if tail else []
                parts_len = len(tail)
            else:
                parts = []
                parts_len = 0

        for para in paragraphs:
            if _is_heading(para) and parts:
                emit(keep_overlap=False)
                section = para.strip()
            elif _is_heading(para):
                section = para.strip()
            for piece in _split_long(para, MAX_CHUNK_CHARS):
                if parts and parts_len + len(piece) > MAX_CHUNK_CHARS:
                    emit(keep_overlap=True)
                parts.append(piece)
                parts_len += len(piece) + 2
        emit(keep_overlap=False)

    for index, chunk in enumerate(chunks):
        chunk["chunk_index"] = index
        chunk["chunk_id"] = f"p{chunk['page_number']}-c{index:04d}"
    return chunks


def build_manual_record_from_pages(
    filename: str,
    pages: list[dict],
    *,
    manual_id: str,
    uploaded_at: str,
) -> dict:
    """Chunk extracted pages and refuse a scan that produced almost no text."""
    cleaned_pages = [
        {
            "page_number": int(page.get("page_number") or 0),
            "text": _clean_text(str(page.get("text") or "")),
        }
        for page in pages
    ]
    page_total = 0
    for page in pages:
        if isinstance(page, dict) and page.get("_pdf_page_total"):
            page_total = int(page["_pdf_page_total"])
    text_characters = sum(len(page["text"]) for page in cleaned_pages)
    if text_characters < MIN_MANUAL_CHARS:
        raise ManualExtractError(
            "This PDF has almost no extractable text, so it cannot be cited. "
            "Upload a text-based warranty manual. A photo scan of the manual will not work."
        )
    empty_pages = [page["page_number"] for page in cleaned_pages if not page["text"]]
    warnings: list[str] = []
    if page_total > MAX_MANUAL_PAGES:
        warnings.append(
            f"Only the first {MAX_MANUAL_PAGES} of {page_total} PDF pages were stored. "
            "Split a larger manual before uploading the rest."
        )
    if empty_pages:
        shown = ", ".join(str(number) for number in empty_pages[:20])
        extra = "" if len(empty_pages) <= 20 else f" (+{len(empty_pages) - 20} more)"
        warnings.append(
            f"{len(empty_pages)} PDF page(s) had no extractable text and cannot be cited: {shown}{extra}"
        )
    chunks = chunk_pages(cleaned_pages)
    if not chunks:
        raise ManualExtractError("No usable text chunks were produced from this PDF.")
    return {
        "id": manual_id,
        "filename": filename or "warranty-manual.pdf",
        "title": _title_from_pages(cleaned_pages) or (filename or "Warranty manual"),
        "page_count": len(cleaned_pages),
        "chunk_count": len(chunks),
        "text_characters": text_characters,
        "warnings": warnings,
        "chunks": chunks,
        "uploaded_at": uploaded_at,
    }


def build_manual_record(filename: str, pdf_bytes: bytes, *, manual_id: str, uploaded_at: str) -> dict:
    return build_manual_record_from_pages(
        filename,
        extract_pdf_pages(pdf_bytes),
        manual_id=manual_id,
        uploaded_at=uploaded_at,
    )


def retrieve_chunks(chunks: list[dict], query: str, *, limit: int = 8) -> list[dict]:
    """Rank stored chunks by overlap with the query. No network and no embeddings."""
    terms = _tokens(query)
    phrases = _phrases(terms)
    if not terms or not chunks:
        return []
    ranked: list[tuple[float, int, dict]] = []
    unique_terms = list(dict.fromkeys(terms))
    for chunk in chunks:
        body = str(chunk.get("text") or "").casefold()
        section = str(chunk.get("section_label") or "").casefold()
        score = 0.0
        matched = 0
        for term in unique_terms:
            in_section = term in section
            count = body.count(term)
            if not in_section and count <= 0:
                continue
            matched += 1
            score += min(count, 4) + (3.0 if in_section else 0.0)
        for phrase in phrases:
            if phrase in body or phrase in section:
                score += 6.0
        if matched == 0 or score < 4:
            continue
        score += matched / len(unique_terms)
        ranked.append((score, int(chunk.get("chunk_index") or 0), chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [chunk for _score, _index, chunk in ranked[:limit]]


def repair_order_query_text(repair_order: dict) -> str:
    """Text used to pull manual sections about this specific repair."""
    parts: list[str] = []
    for key in (
        "customer_concern",
        "cause",
        "correction",
        "tech_notes",
        "other_visible_notes",
        "vin",
        "mileage",
    ):
        value = repair_order.get(key)
        if value:
            parts.append(str(value))
    for tech in repair_order.get("tech_numbers") or []:
        if tech:
            parts.append(str(tech))
    for row in repair_order.get("labor_operations") or []:
        if isinstance(row, dict):
            parts.extend(str(row.get(field) or "") for field in ("op_code", "description", "tech_number"))
    for row in repair_order.get("parts") or []:
        if isinstance(row, dict):
            parts.extend(
                str(row.get(field) or "") for field in ("part_number", "description")
            )
    for row in repair_order.get("time_punches") or []:
        if isinstance(row, dict):
            parts.append(str(row.get("tech_number") or ""))
    return " ".join(part for part in parts if part)


def retrieve_for_repair_order(repair_order: dict, chunks: list[dict], *, limit: int = MAX_EXCERPTS) -> list[dict]:
    """Relevant repair sections plus documentation rules the audit should check."""
    selected: list[dict] = []
    seen: set[str] = set()

    def add(hits: list[dict]) -> None:
        for hit in hits:
            chunk_id = str(hit.get("chunk_id") or id(hit))
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            selected.append(hit)
            if len(selected) >= limit:
                return

    add(retrieve_chunks(chunks, repair_order_query_text(repair_order), limit=8))
    for phrase in RULE_ANCHORS:
        matches = [
            chunk for chunk in chunks
            if phrase in str(chunk.get("text") or "").casefold()
            or phrase in str(chunk.get("section_label") or "").casefold()
        ]
        if not matches:
            continue
        matches.sort(key=lambda chunk: (
            0 if phrase in str(chunk.get("section_label") or "").casefold() else 1,
            int(chunk.get("page_number") or 0),
        ))
        add(matches[:1])
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for probe in DOCUMENTATION_PROBES:
            add(retrieve_chunks(chunks, probe, limit=2))
            if len(selected) >= limit:
                break
    return selected


def format_excerpts(chunks: list[dict]) -> str:
    blocks = []
    for chunk in chunks:
        blocks.append(
            "[excerpt pdf_page={page} section={section}]\n{text}".format(
                page=chunk.get("page_number"),
                section=chunk.get("section_label") or "",
                text=chunk.get("text") or "",
            )
        )
    return "\n\n".join(blocks)


def validate_findings(raw_findings: object, retrieved: list[dict]) -> list[dict]:
    """Keep a finding only when its quote is a verbatim stored excerpt.

    Unsupported rows stay in the result so the UI can show they were not
    treated as policy. They never count as required corrections.
    """
    if not isinstance(raw_findings, list):
        return []
    indexed = [(chunk, _norm(str(chunk.get("text") or ""))) for chunk in retrieved]
    findings: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for raw in raw_findings:
        if not isinstance(raw, dict):
            continue
        citation_quote = str(raw.get("citation_quote") or "").strip()
        whats_wrong = _collapse(raw.get("whats_wrong"))
        if not whats_wrong and not citation_quote:
            continue
        severity = str(raw.get("severity") or "major").strip().casefold()
        if severity not in SEVERITIES:
            severity = "major"
        normalized_quote = _norm(citation_quote)
        matches = [
            chunk
            for chunk, text in indexed
            if _quote_is_substantive(normalized_quote) and normalized_quote in text
        ]
        requested_page = _as_int(raw.get("manual_page"))
        finding = {
            "severity": severity,
            "ro_field": _collapse(raw.get("ro_field")) or "Repair order",
            "whats_wrong": whats_wrong or "The model did not describe the issue.",
            "how_to_fix": _collapse(raw.get("how_to_fix")),
            "manual_section": _collapse(raw.get("manual_section")),
            "manual_page": requested_page,
            "citation_quote": citation_quote,
            "supported": False,
            "support_note": (
                "Not backed by a verbatim excerpt from the manual text sent for this audit, "
                "so this is not a required correction."
            ),
            "counts_as_required_correction": False,
        }
        if matches:
            chosen = next(
                (chunk for chunk in matches if chunk.get("page_number") == requested_page),
                matches[0],
            )
            finding["supported"] = True
            finding["manual_page"] = int(chosen.get("page_number") or 0)
            finding["manual_section"] = str(chosen.get("section_label") or finding["manual_section"])
            if requested_page and requested_page != finding["manual_page"]:
                finding["support_note"] = (
                    f"Page corrected to PDF page {finding['manual_page']}, "
                    "where this excerpt is stored."
                )
            else:
                finding["support_note"] = ""
            finding["counts_as_required_correction"] = severity in REQUIRED_SEVERITIES
        dedupe_key = (_norm(finding["ro_field"]), normalized_quote or _norm(finding["whats_wrong"]))
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        findings.append(finding)

    findings.sort(
        key=lambda item: (
            0 if item["counts_as_required_correction"] else 1,
            SEVERITIES.index(item["severity"]) if item["severity"] in SEVERITIES else 9,
            item["ro_field"],
        )
    )
    return findings


def build_summary(ro_number: str, findings: list[dict]) -> str:
    """Authoritative summary derived only from citation-checked findings."""
    required = [item for item in findings if item.get("counts_as_required_correction")]
    rejected = [item for item in findings if not item.get("supported")]
    label = f"RO {ro_number.strip()}: " if str(ro_number or "").strip() else ""
    if not required:
        dropped = ""
        if rejected:
            noun = "suggestion was" if len(rejected) == 1 else "suggestions were"
            dropped = (
                f" {len(rejected)} {noun} not counted because the stored manual "
                "does not contain the quoted text."
            )
        return (
            f"{label}Nothing needs to be corrected based on the stored manual. "
            "No requirement was inferred beyond the excerpts that were retrieved."
            + dropped
        )
    counts = {severity: 0 for severity in REQUIRED_SEVERITIES}
    for item in required:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    detail = ", ".join(
        f"{counts[severity]} {severity}" for severity in REQUIRED_SEVERITIES if counts[severity]
    )
    item_word = "item" if len(required) == 1 else "items"
    dropped = ""
    if len(rejected) == 1:
        dropped = (
            " 1 other suggestion was not counted because it is not backed by "
            "a verbatim excerpt in the stored manual."
        )
    elif rejected:
        dropped = (
            f" {len(rejected)} other suggestions were not counted because they are not "
            "backed by a verbatim excerpt in the stored manual."
        )
    return (
        f"{label}{len(required)} {item_word} need to be corrected before the audit ({detail}). "
        "Each counted item quotes the stored manual."
        + dropped
    )


def findings_to_csv(ro_number: str, summary: str, findings: list[dict]) -> str:
    """Spreadsheet of every finding, including rows that do not count as policy."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ro_number",
            "severity",
            "ro_field",
            "whats_wrong",
            "how_to_fix",
            "manual_section",
            "manual_page",
            "citation_quote",
            "counts_as_required_correction",
            "support_note",
            "summary",
        ]
    )
    if not findings:
        writer.writerow([_csv_cell(ro_number), "", "", "", "", "", "", "", "false", "", _csv_cell(summary)])
    for finding in findings:
        writer.writerow(
            [
                _csv_cell(ro_number),
                _csv_cell(finding.get("severity")),
                _csv_cell(finding.get("ro_field")),
                _csv_cell(finding.get("whats_wrong")),
                _csv_cell(finding.get("how_to_fix")),
                _csv_cell(finding.get("manual_section")),
                finding.get("manual_page") if finding.get("manual_page") is not None else "",
                _csv_cell(finding.get("citation_quote")),
                "true" if finding.get("counts_as_required_correction") else "false",
                _csv_cell(finding.get("support_note")),
                _csv_cell(summary),
            ]
        )
    return buffer.getvalue()


def csv_download_name(ro_number: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(ro_number or "").strip()).strip("_")
    return f"warranty_audit_{cleaned or 'repair_order'}.csv"


def _clean_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _title_from_pages(pages: list[dict]) -> str:
    for page in pages:
        for line in str(page.get("text") or "").splitlines():
            line = " ".join(line.split())
            if line:
                return line[:120]
    return ""


def _paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            paragraphs.append(" ".join(buffer).strip())
            buffer.clear()

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            flush()
            continue
        if _is_heading(line):
            flush()
            paragraphs.append(line)
            continue
        buffer.append(line)
    flush()
    return [paragraph for paragraph in paragraphs if paragraph]


def _is_heading(line: str) -> bool:
    text = " ".join(line.strip().split())
    if not text or len(text) > 90 or text.endswith("."):
        return False
    if _HEADING_SECTION.match(text) or _HEADING_NUMBERED.match(text):
        return True
    letters = [char for char in text if char.isalpha()]
    if len(letters) >= 8 and sum(char.isupper() for char in letters) / len(letters) >= 0.8:
        return True
    return False


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    text = paragraph.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = text.rfind(" ", start + 200, end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end <= start:
            break
        start = end
    return parts


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(str(text or "").casefold()) if token not in _STOPWORDS]


def _phrases(terms: list[str]) -> list[str]:
    return [f"{left} {right}" for left, right in zip(terms, terms[1:])]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def _quote_is_substantive(normalized_quote: str) -> bool:
    """A heading or a short fragment must not count as a policy quote."""
    if len(normalized_quote) < MIN_QUOTE_CHARS:
        return False
    words = [word for word in re.findall(r"[a-z0-9']+", normalized_quote) if word]
    if len(words) < 6:
        return False
    return True


def redact_secrets(text: str, *extra: str) -> str:
    """Strip API keys and tokens before an error is shown or logged."""
    cleaned = "" if text is None else str(text)
    for secret in extra:
        if secret and len(secret) >= 6:
            cleaned = cleaned.replace(secret, "[redacted]")
    patterns = (
        r"sk-[A-Za-z0-9_\-]{8,}",
        r"sb_secret_[A-Za-z0-9_\-]+",
        r"sb_publishable_[A-Za-z0-9_\-]+",
        r"Bearer\s+\S+",
        r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned


def _collapse(value: object, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return text[:limit]


def _as_int(value: object) -> Optional[int]:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group(0)) if match else None


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text

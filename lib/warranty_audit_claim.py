"""Checklist taken from an FCA Global Claim Acknowledgement printed by Reynolds Ignite.

These checks only look at fields that are printed on that acknowledgement.
They do not add Stellantis policy that is not written on the form or in the stored manual.
"""

from __future__ import annotations

import re
from datetime import datetime

DEALER_CODE = "68888"
CLAIM_SECTION = "FCA US LLC Global Claim Acknowledgement"
CLAIM_NOTE = (
    "Reynolds Ignite paid-claim acknowledgement. "
    "This checks a field auditors review on that printout. "
    "It is not a sentence from the warranty manual."
)
SHOP_SECTION = "Repair order documentation"
SHOP_NOTE = (
    "Dealership rule for this audit. A plus sign next to the job number is a warranty add-on "
    "and needs your signature. Tech notes must justify the repair. "
    "This is not a sentence from the warranty manual."
)

_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hr|hrs|hours)\b", re.IGNORECASE)
_MONEY = re.compile(r"-?\d+(?:\.\d+)?")
_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d")


def check_claim_criteria(repair_order: dict) -> list[dict]:
    """Return required corrections for a Reynolds Ignite RO or claim acknowledgement."""
    order = repair_order if isinstance(repair_order, dict) else {}
    claim = _is_claim(order)
    findings: list[dict] = []
    narrative = _narrative(order)

    vin = _clean(order.get("vin"))
    if not vin:
        findings.append(_issue(
            severity="critical",
            ro_field="VIN",
            whats_wrong="VIN is blank.",
            how_to_fix="Enter the 17-character VIN on the repair order and on the claim acknowledgement.",
            citation="VIN",
        ))
    elif not _VIN.match(vin):
        findings.append(_issue(
            severity="critical",
            ro_field="VIN",
            whats_wrong=f"VIN {vin} is not 17 characters.",
            how_to_fix="Correct the VIN so it is 17 characters, with no I, O, or Q.",
            citation="VIN",
        ))

    if not narrative:
        findings.append(_issue(
            severity="critical",
            ro_field="Customer narrative",
            whats_wrong="Customer narrative is blank.",
            how_to_fix="Write the customer concern, the cause that was found, and the correction.",
            citation="Customer Narrative",
        ))
    else:
        if not _clean(order.get("customer_concern")):
            findings.append(_issue(
                severity="major",
                ro_field="Customer concern",
                whats_wrong="The customer concern line is blank.",
                how_to_fix="Start the narrative with what the customer stated.",
                citation="Customer Narrative",
            ))
        if not _clean(order.get("cause")):
            findings.append(_issue(
                severity="major",
                ro_field="Cause",
                whats_wrong="The cause is blank.",
                how_to_fix="State what was found after the concern was verified.",
                citation="Customer Narrative",
            ))
        if not _clean(order.get("correction")):
            findings.append(_issue(
                severity="major",
                ro_field="Correction",
                whats_wrong="The correction is blank.",
                how_to_fix="State the repair that was performed and the labor operation.",
                citation="Customer Narrative",
            ))

    for block in _repair_blocks(order):
        label = _ro_label(block)
        tech_id = _clean(block.get("technician_id"))
        tech_name = _clean(block.get("technician_name"))
        if not tech_id:
            findings.append(_issue(
                severity="major",
                ro_field=f"{label} technician",
                whats_wrong="Technician Identification is blank.",
                how_to_fix="Enter the technician number printed on the claim acknowledgement.",
                citation="Technician Identification",
            ))
        if claim and not tech_name:
            findings.append(_issue(
                severity="major",
                ro_field=f"{label} technician name",
                whats_wrong="Technician name is blank.",
                how_to_fix="Enter the technician name next to Technician Identification.",
                citation="Technician Identification",
            ))

        labor_lines = [row for row in _rows(block.get("labor_lines")) if _line_has_text(row)]
        part_lines = [row for row in _rows(block.get("part_lines")) if _line_has_text(row)]
        if claim and not labor_lines and not part_lines:
            findings.append(_issue(
                severity="critical",
                ro_field=label,
                whats_wrong="This repair order has no labor line and no part line.",
                how_to_fix="Add the LOP line and the part lines that were submitted.",
                citation="Line",
            ))

        for line in labor_lines:
            op_code = _clean(line.get("op_code"))
            if not op_code:
                findings.append(_issue(
                    severity="critical",
                    ro_field=f"{label} labor operation",
                    whats_wrong="A labor line has no LOP.",
                    how_to_fix="Enter the labor operation code on that line.",
                    citation="LOP",
                ))
            if not _clean(line.get("description")):
                findings.append(_issue(
                    severity="major",
                    ro_field=f"{label} labor description",
                    whats_wrong=f"LOP {op_code or '(blank)'} has no description.",
                    how_to_fix="Enter the labor operation description.",
                    citation="Description",
                ))
            if not _clean(line.get("failure_code")):
                findings.append(_issue(
                    severity="critical",
                    ro_field=f"{label} failure code",
                    whats_wrong=f"LOP {op_code or '(blank)'} has no failure code.",
                    how_to_fix="Enter the failure code shown on that labor line.",
                    citation="Failure Code",
                ))
            if _hours(line.get("hours")) is None:
                findings.append(_issue(
                    severity="critical",
                    ro_field=f"{label} labor hours",
                    whats_wrong=f"LOP {op_code or '(blank)'} has no hours.",
                    how_to_fix="Enter the hours on that labor line.",
                    citation="Hours",
                ))
            elif op_code:
                stated = _hours_for_op(narrative, op_code)
                billed = _hours(line.get("hours"))
                if stated is not None and billed is not None and abs(stated - billed) > 0.05:
                    findings.append(_issue(
                        severity="critical",
                        ro_field=f"{label} labor hours",
                        whats_wrong=(
                            f"Customer narrative states {stated:g} hours for LOP {op_code}, "
                            f"and the labor line bills {billed:g} hours."
                        ),
                        how_to_fix="Make the hours in the narrative match the hours on that LOP line.",
                        citation="Hours",
                    ))

        for line in part_lines:
            part_number = _clean(line.get("part_number"))
            if not part_number:
                findings.append(_issue(
                    severity="major",
                    ro_field=f"{label} part",
                    whats_wrong="A part line has no part number.",
                    how_to_fix="Enter the part number on that line.",
                    citation="Part Number",
                ))
            if not _clean(line.get("description")):
                findings.append(_issue(
                    severity="minor",
                    ro_field=f"{label} part description",
                    whats_wrong=f"Part {part_number or '(blank)'} has no description.",
                    how_to_fix="Enter the part description.",
                    citation="Description",
                ))
            if not _clean(line.get("quantity")):
                findings.append(_issue(
                    severity="major",
                    ro_field=f"{label} part quantity",
                    whats_wrong=f"Part {part_number or '(blank)'} has no quantity.",
                    how_to_fix="Enter the quantity on that part line.",
                    citation="Quantity",
                ))
            if line.get("failed") is None:
                findings.append(_issue(
                    severity="critical",
                    ro_field=f"{label} failed part",
                    whats_wrong=f"Failed Part is blank for part {part_number or '(blank)'}.",
                    how_to_fix="Mark Failed Part on the claim acknowledgement for each failed part.",
                    citation="Failed Part",
                ))

    if claim:
        findings.extend(_header_findings(order))
    findings.extend(_add_on_findings(order))
    findings.extend(_goodwill_findings(order))
    findings.extend(_tech_note_findings(order))

    return findings


def _header_findings(order: dict) -> list[dict]:
    required = (
        ("critical", "claim_number", "Claim number", "Claim Number", "Enter the claim number."),
        ("major", "dealer_code", "Dealer", "Dealer", "Enter the dealer code."),
        ("major", "in_service_date", "In service date", "In Service Date", "Enter the in-service date."),
        ("major", "warranty_coverage", "Warranty coverage", "Warranty Coverage", "Enter the warranty coverage code."),
        ("major", "claim_type", "Claim type", "Claim Type", "Enter the claim type."),
        ("major", "submission_type", "Submission type", "Submission Type", "Enter the submission type, such as original or resubmission."),
        ("minor", "continuation", "Continuation", "Continuation", "Enter YES or NO for continuation."),
        ("major", "date_received", "Date received", "Date Received", "Enter the date the claim was received."),
        ("major", "date_completed", "Date completed", "Date Completed", "Enter the date the repair was completed."),
        ("minor", "process_date", "Process date", "Process Date", "Enter the process date."),
        ("critical", "authorization", "Authorization", "Authorization", "Enter the authorization number."),
        ("minor", "vehicle_description", "Vehicle description", "Vehicle Description", "Enter the vehicle description."),
        ("major", "service_advisor", "Service advisor", "Service Advisor", "Enter the service advisor number."),
        ("minor", "list_number", "List number", "List Number", "Enter the list number from the claim acknowledgement."),
        ("minor", "reference_number", "Reference number", "Reference Number", "Enter the reference number."),
    )
    findings = []
    for severity, key, field, citation, fix in required:
        if not _clean(order.get(key)):
            findings.append(_issue(
                severity=severity,
                ro_field=field,
                whats_wrong=f"{citation} is blank on the claim acknowledgement.",
                how_to_fix=fix,
                citation=citation,
            ))
    received = _parse_date(order.get("date_received"))
    completed = _parse_date(order.get("date_completed"))
    if received and completed and completed < received:
        findings.append(_issue(
            severity="major",
            ro_field="Date completed",
            whats_wrong="Date Completed is before Date Received.",
            how_to_fix="Correct Date Received and Date Completed.",
            citation="Date Completed",
        ))
    return findings


def _add_on_findings(order: dict) -> list[dict]:
    """A small plus sign next to the job number is a warranty add-on and needs your signature."""
    signatures = order.get("signatures") if isinstance(order.get("signatures"), dict) else {}
    signed = _signed(signatures.get("service_manager"))
    findings = []
    seen: set[str] = set()
    for block in _repair_blocks(order):
        lines = list(_rows(block.get("labor_lines")))
        if _line_is_add_on(block):
            lines.append(block)
        for line in lines:
            if not _line_is_add_on(line):
                continue
            job = _clean(line.get("job_number")) or _clean(line.get("op_code")) or _ro_label(block)
            key = job.casefold()
            if key in seen:
                continue
            seen.add(key)
            if signed:
                continue
            findings.append(_shop_issue(
                severity="critical",
                ro_field=f"Job {job} add-on",
                whats_wrong=(
                    f"Job {job} has a plus sign next to the job number, so it is a warranty add-on, "
                    "and your signature is missing."
                ),
                how_to_fix="Sign next to that added job on the Warranty Copy.",
                citation="Warranty add-on",
            ))
    return findings


def _goodwill_findings(order: dict) -> list[dict]:
    """Goodwill in the labor or the narrative needs your signature."""
    pieces = [
        order.get("customer_concern"),
        order.get("cause"),
        order.get("correction"),
        order.get("tech_notes"),
        order.get("other_visible_notes"),
    ]
    for line in _all_labor(order):
        pieces.append(line.get("description"))
        pieces.append(line.get("op_code"))
    if not re.search(r"goodwill", " ".join(_clean(piece) for piece in pieces), re.IGNORECASE):
        return []
    signatures = order.get("signatures") if isinstance(order.get("signatures"), dict) else {}
    if _signed(signatures.get("service_manager")):
        return []
    return [_shop_issue(
        severity="critical",
        ro_field="Goodwill",
        whats_wrong="Goodwill is on this repair order, and your signature is missing.",
        how_to_fix="Sign the Goodwill job on the Warranty Copy.",
        citation="Goodwill",
    )]


_CAUSE_WORDS = re.compile(
    r"\b(?:found|tested|test|scan|scanned|code|dtc|reading|readings|measured|measurement|"
    r"inspected|confirmed|verified|broken|cracked|leaking|leak|worn|damaged|corroded|"
    r"seized|shorted|loose|noisy|noise|binding|contaminated|restricted|clogged|torn|"
    r"failed|failure|diagnosis|diagnostic|spec|specs|voltage|pressure|ohms|"
    r"excessive|play)\b",
    re.IGNORECASE,
)
_NO_PROBLEM = re.compile(
    r"no problem found|could not duplicate|operating as designed|no fault found|"
    r"no trouble found|unable to duplicate|operating normally",
    re.IGNORECASE,
)
_NOTE_STOP = {
    "customer", "states", "stated", "says", "said", "with", "that", "this", "from",
    "have", "been", "were", "when", "your", "repair", "repaired", "replace", "replaced",
    "replacement", "performed", "installed", "removed", "labor", "hours", "total",
    "operation", "vehicle", "warranty", "claim", "front", "rear", "left", "right",
}


def _tech_note_findings(order: dict) -> list[dict]:
    """Tech notes must state the cause and match the complaint, the labor, and the failed parts."""
    story = _tech_story(order)
    if not story:
        return [_shop_issue(
            severity="major",
            ro_field="Tech notes",
            whats_wrong="Tech notes are missing, so the repair is not documented.",
            how_to_fix="Write what the customer reported, what you found, the tests, and the repair.",
            citation="Tech notes",
        )]

    findings = []
    labor = _all_labor(order)
    parts = _all_parts(order)
    zero_hour = [line for line in labor if _hours(line.get("hours")) == 0]
    diagnosed = _CAUSE_WORDS.search(_NO_PROBLEM.sub(" ", story))
    if not diagnosed:
        if zero_hour:
            wrong = "Tech notes do not state the diagnosis that supports the 0.0 hour operation."
            fix = "Add the test results and the cause that support that diagnostic time."
        else:
            wrong = "Tech notes do not state the cause of the failure, so they do not justify the repair."
            fix = "State what was found and why the part or operation was needed, not only that it was replaced."
        findings.append(_shop_issue(
            severity="major",
            ro_field="Tech notes",
            whats_wrong=wrong,
            how_to_fix=fix,
            citation="Tech notes",
        ))
    if _NO_PROBLEM.search(story) and (_billed_work(labor, parts)):
        findings.append(_shop_issue(
            severity="critical",
            ro_field="Tech notes",
            whats_wrong="Tech notes say no problem was found, but the claim is for a repair.",
            how_to_fix="Document the fault that was found, or remove the repair that the notes do not support.",
            citation="Tech notes",
        ))

    story_tokens = _note_tokens(story)
    concern_tokens = _note_tokens(order.get("customer_concern"))
    if concern_tokens and not (concern_tokens & story_tokens):
        findings.append(_shop_issue(
            severity="major",
            ro_field="Tech notes",
            whats_wrong="Tech notes do not address the customer's complaint.",
            how_to_fix="Write the notes so they cover the complaint, the cause, and the correction.",
            citation="Tech notes",
        ))

    for line in labor:
        code = _clean(line.get("op_code"))
        if code and code.casefold() in story.casefold():
            continue
        described = _note_tokens(line.get("description"), minimum=3)
        if not described or (described & _note_tokens(story, minimum=3)):
            continue
        label = code or _clean(line.get("description")) or "labor"
        findings.append(_shop_issue(
            severity="major",
            ro_field=f"Tech notes {label}",
            whats_wrong=(
                f"Tech notes do not support {label}"
                + (f" ({_clean(line.get('description'))})." if code and _clean(line.get("description")) else ".")
            ),
            how_to_fix="Describe the repair that was performed for that labor operation.",
            citation="Tech notes",
        ))

    story_compact = re.sub(r"[^a-z0-9]", "", story.casefold())
    for part in parts:
        if not _failed_part(part):
            continue
        number = re.sub(r"[^a-z0-9]", "", _clean(part.get("part_number")).casefold())
        described = _note_tokens(part.get("description"), minimum=3)
        if (described and described & _note_tokens(story, minimum=3)) or (len(number) >= 5 and number in story_compact):
            continue
        name = _clean(part.get("part_number")) or _clean(part.get("description")) or "part"
        findings.append(_shop_issue(
            severity="major",
            ro_field=f"Tech notes {name}",
            whats_wrong=f"Tech notes do not document failed part {name}.",
            how_to_fix="Name that part and the cause of the failure in the tech notes.",
            citation="Tech notes",
        ))
    return findings


def _tech_story(order: dict) -> str:
    story = " ".join(
        piece for piece in (
            _clean(order.get("tech_notes")),
            _clean(order.get("cause")),
            _clean(order.get("correction")),
        ) if piece
    )
    if story:
        return story
    return _clean(order.get("other_visible_notes"))


def _all_labor(order: dict) -> list[dict]:
    lines = []
    for block in _repair_blocks(order):
        lines.extend(row for row in _rows(block.get("labor_lines")) if _line_has_text(row))
    return lines


def _all_parts(order: dict) -> list[dict]:
    lines = []
    for block in _repair_blocks(order):
        lines.extend(row for row in _rows(block.get("part_lines")) if _line_has_text(row))
    return lines


def _billed_work(labor: list[dict], parts: list[dict]) -> bool:
    if any((_hours(line.get("hours")) or 0) > 0 for line in labor):
        return True
    return any(_failed_part(part) or _clean(part.get("part_number")) for part in parts)


def _failed_part(part: dict) -> bool:
    flag = part.get("failed")
    if flag is True:
        return True
    return str(flag).strip().casefold() in {"true", "yes", "y", "x"}


def _line_is_add_on(line: dict) -> bool:
    job = _clean(line.get("job_number"))
    if "+" in job:
        return True
    flag = line.get("add_on")
    if flag is True:
        return True
    return str(flag).strip().casefold() in {"true", "yes", "y", "+"}


def _signed(value: object) -> bool:
    if value is True:
        return True
    return str(value or "").strip().casefold() in {"true", "yes", "y", "signed"}


def _note_tokens(value: object, *, minimum: int = 4) -> set[str]:
    words = re.findall(rf"[a-z0-9]{{{minimum},}}", _clean(value).casefold())
    stops = _NOTE_STOP
    if minimum < 4:
        stops = stops | {"the", "and", "for", "end", "set", "kit", "new", "old"}
    return {word for word in words if word not in stops}


def _repair_blocks(order: dict) -> list[dict]:
    raw = order.get("repair_orders")
    blocks = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    if blocks:
        return blocks
    tech_numbers = [str(item).strip() for item in order.get("tech_numbers") or [] if str(item).strip()]
    return [{
        "ro_number": order.get("ro_number") or "",
        "technician_id": tech_numbers[0] if tech_numbers else "",
        "technician_name": order.get("technician_name") or "",
        "labor_lines": order.get("labor_operations") or [],
        "part_lines": order.get("parts") or [],
        "total_parts": order.get("total_parts") or "",
        "total_labor": order.get("total_labor") or "",
        "total_special_service": order.get("total_special_service") or "",
        "pre_tax_total": order.get("pre_tax_total") or "",
    }]


def _is_claim(order: dict) -> bool:
    kind = _clean(order.get("document_type")).casefold().replace("-", " ").replace("_", " ")
    return "claim acknowledgement" in kind or kind in {"claim", "global claim acknowledgement"}


def _narrative(order: dict) -> str:
    return " ".join(
        piece for piece in (
            _clean(order.get("customer_concern")),
            _clean(order.get("cause")),
            _clean(order.get("correction")),
            _clean(order.get("tech_notes")),
            _clean(order.get("other_visible_notes")),
        ) if piece
    )


def _hours_for_op(narrative: str, op_code: str) -> float | None:
    if not narrative or not op_code:
        return None
    match = re.search(re.escape(op_code), narrative, re.IGNORECASE)
    if not match:
        return None
    window = narrative[match.end(): match.end() + 80]
    found = _HOURS.search(window)
    if not found:
        return None
    return float(found.group(1))


def _hours(value: object) -> float | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    match = _MONEY.search(text)
    if not match:
        return None
    return float(match.group(0))


def _money(value: object) -> float | None:
    text = _clean(value).replace(",", "").replace("$", "")
    if not text:
        return None
    match = _MONEY.search(text)
    if not match:
        return None
    return float(match.group(0))


def _parse_date(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _rows(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _line_has_text(row: dict) -> bool:
    for key in ("op_code", "part_number", "description", "failure_code", "hours", "quantity"):
        if _clean(row.get(key)):
            return True
    return row.get("failed") is not None


def _ro_label(block: dict) -> str:
    number = _clean(block.get("ro_number"))
    return f"RO {number}" if number else "RO"


def _clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _issue(*, severity: str, ro_field: str, whats_wrong: str, how_to_fix: str, citation: str) -> dict:
    return _finding(
        severity=severity,
        ro_field=ro_field,
        whats_wrong=whats_wrong,
        how_to_fix=how_to_fix,
        citation=citation,
        section=CLAIM_SECTION,
        note=CLAIM_NOTE,
        source="claim_acknowledgement",
    )


def _shop_issue(*, severity: str, ro_field: str, whats_wrong: str, how_to_fix: str, citation: str) -> dict:
    return _finding(
        severity=severity,
        ro_field=ro_field,
        whats_wrong=whats_wrong,
        how_to_fix=how_to_fix,
        citation=citation,
        section=SHOP_SECTION,
        note=SHOP_NOTE,
        source="repair_order_documentation",
    )


def _finding(
    *,
    severity: str,
    ro_field: str,
    whats_wrong: str,
    how_to_fix: str,
    citation: str,
    section: str,
    note: str,
    source: str,
) -> dict:
    return {
        "severity": severity,
        "ro_field": ro_field,
        "whats_wrong": whats_wrong,
        "how_to_fix": how_to_fix,
        "manual_section": section,
        "manual_page": None,
        "citation_quote": citation,
        "supported": True,
        "support_note": note,
        "counts_as_required_correction": True,
        "source": source,
    }

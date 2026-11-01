"""Auditor checks for a repair order.

These are the items an auditor reviews on the repair order: tech notes, hours
that do not match the narrative, a plus sign next to a job, and Goodwill.
Time-punch rules come from the stored warranty manual and audit guide.
Blank boxes on the claim acknowledgement are not findings.
"""

from __future__ import annotations

import re

DEALER_CODE = "68888"
SHOP_SECTION = "Repair order documentation"
SHOP_NOTE = (
    "Auditor check. A plus sign next to the job number is a warranty add-on and needs your signature. "
    "Goodwill needs your signature. Tech notes must justify the repair. "
    "Diagnostic, actual-time, and wiring labor need complete time punches and a service manager signature. "
    "This is not a sentence from the warranty manual."
)

_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hr|hrs|hours)\b", re.IGNORECASE)
_MONEY = re.compile(r"-?\d+(?:\.\d+)?")


def check_claim_criteria(repair_order: dict) -> list[dict]:
    """Return what an auditor would flag. Blank claim-acknowledgement boxes are ignored."""
    order = repair_order if isinstance(repair_order, dict) else {}
    findings: list[dict] = []
    findings.extend(_hours_mismatch_findings(order))
    findings.extend(_date_mismatch_findings(order))
    findings.extend(_mileage_mismatch_findings(order))
    findings.extend(_time_punch_findings(order))
    findings.extend(_special_labor_findings(order))
    findings.extend(_add_on_findings(order))
    findings.extend(_goodwill_findings(order))
    findings.extend(_tech_note_findings(order))
    return findings


def _hours_mismatch_findings(order: dict) -> list[dict]:
    narrative = _narrative(order)
    findings = []
    for block in _repair_blocks(order):
        label = _ro_label(block)
        for line in [row for row in _rows(block.get("labor_lines")) if _line_has_text(row)]:
            op_code = _clean(line.get("op_code"))
            stated = _hours_for_op(narrative, op_code)
            billed = _hours(line.get("hours"))
            if not op_code or stated is None or billed is None or abs(stated - billed) <= 0.05:
                continue
            findings.append(_shop_issue(
                severity="critical",
                ro_field=f"{label} labor hours",
                whats_wrong=(
                    f"The notes state {stated:g} hours for LOP {op_code}, "
                    f"and the labor line bills {billed:g} hours."
                ),
                how_to_fix="Make the hours in the notes match the hours on that LOP line.",
                citation="Labor hours",
            ))
    return findings


def _date_mismatch_findings(order: dict) -> list[dict]:
    """Flag a completed date that is before the repair was received. Blank dates are ignored."""
    received = _parse_date(order.get("date_received") or order.get("open_date"))
    completed = _parse_date(order.get("date_completed") or order.get("close_date"))
    if not received or not completed or completed >= received:
        return []
    return [_shop_issue(
        severity="major",
        ro_field="Date completed",
        whats_wrong="Date completed is before the date the repair was received.",
        how_to_fix="Correct the received date and the completed date so the repair is not finished before it started.",
        citation="Repair dates",
    )]


def _mileage_mismatch_findings(order: dict) -> list[dict]:
    """Flag when the notes state a mileage that does not match the mileage box."""
    stated_box = _mileage_number(order.get("mileage"))
    if stated_box is None:
        return []
    narrative = _narrative(order)
    match = re.search(
        r"(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:miles|mileage|odometer)\b",
        narrative,
        re.IGNORECASE,
    )
    if not match:
        return []
    stated_notes = _mileage_number(match.group(1))
    if stated_notes is None or abs(stated_notes - stated_box) <= 100:
        return []
    return [_shop_issue(
        severity="major",
        ro_field="Mileage",
        whats_wrong=(
            f"The mileage box says {stated_box:,} and the notes say {stated_notes:,} miles."
        ),
        how_to_fix="Make the mileage on the repair order match the mileage in the notes.",
        citation="Mileage",
    )]


def _mileage_number(value: object) -> int | None:
    text = _clean(value).replace(",", "")
    if not text or not text.isdigit():
        return None
    number = int(text)
    if number < 100 or number > 999999:
        return None
    return number


def _parse_date(value: object):
    from datetime import datetime

    text = _clean(value)
    if not text:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _lop_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean(value).upper())


def _special_labor_kind(line: dict) -> str:
    """Labor that an auditor checks for time punches and a service manager signature."""
    code = _lop_key(line.get("op_code"))
    description = _clean(line.get("description"))
    if code.startswith("8541"):
        return "operation diagnostics (85-41)"
    if code == "85333333":
        return "sublet processing allowance (85-33-33-33)"
    if code == "8585CG09":
        return "consumer goodwill (85-85-CG-09)"
    if code == "85LOAN00":
        return "back-order rental (85-LO-AN-00)"
    if len(code) >= 8 and code.endswith("00"):
        return "actual time (LOP ending in 00)"
    if re.search(r"\bwir(?:e|ing)\b", description, re.IGNORECASE):
        return "wiring repair"
    return ""


def _time_punch_findings(order: dict) -> list[dict]:
    """Billed labor needs a real on time and a different off time."""
    if not any((_hours(line.get("hours")) or 0) > 0 for line in _all_labor(order)):
        return []
    defects = _punch_defects(order)
    if not defects:
        return []
    return [_shop_issue(
        severity="critical",
        ro_field="Time punches",
        whats_wrong=" ".join(defects),
        how_to_fix="Enter a technician, a time on, and a different time off for the labor on the Warranty Copy.",
        citation="Time punches",
    )]


def _punch_defects(order: dict) -> list[str]:
    rows = [
        row for row in _rows(order.get("time_punches"))
        if any(_clean(row.get(field)) for field in ("on", "off", "hours", "tech_number"))
    ]
    if not rows:
        return ["Time punches are missing for labor that was billed."]
    defects = []
    one_sided = []
    same = []
    complete = 0
    for row in rows:
        on = _clean(row.get("on"))
        off = _clean(row.get("off"))
        if on and off and on.casefold() == off.casefold():
            same.append(row)
        elif on and off:
            complete += 1
        elif on or off:
            one_sided.append(row)
    if one_sided:
        defects.append("A time punch has only one time. On and off are both required.")
    if same:
        defects.append("A time punch uses the same time for on and off.")
    if complete == 0 and not defects:
        defects.append("Time punches do not show both an on time and a different off time.")
    return defects


def _special_labor_findings(order: dict) -> list[dict]:
    """Diagnostic, actual-time, and wiring labor fail without punches and a service manager signature."""
    findings = []
    seen: set[str] = set()
    labor = _all_labor(order)
    signed = _signed((order.get("signatures") or {}).get("service_manager") if isinstance(order.get("signatures"), dict) else None)
    punch_ok = not _punch_defects(order)
    kinds = []
    for line in labor:
        kind = _special_labor_kind(line)
        if not kind:
            continue
        kinds.append((line, kind))
        code = _clean(line.get("op_code")) or kind
        key = f"{_lop_key(code)}:{kind}"
        if key in seen:
            continue
        seen.add(key)
        missing = []
        if not punch_ok:
            missing.append("complete time punches")
        if not signed:
            missing.append("a service manager's signature")
        hours = _hours(line.get("hours")) or 0
        review = kind in {
            "operation diagnostics (85-41)",
            "actual time (LOP ending in 00)",
            "wiring repair",
        } and hours > 0.5
        if not missing and not review:
            continue
        wrong = f"LOP {code} is {kind}."
        if missing:
            wrong += " Missing " + " and ".join(missing) + "."
        if review:
            wrong += (
                f" Actual time is {hours:g} hours. Base dealers need Warranty Contact Center review above 0.5 hours, "
                "Plus above 1.5, and Premium above 2.5."
            )
        findings.append(_shop_issue(
            severity="critical",
            ro_field=f"LOP {code}",
            whats_wrong=wrong,
            how_to_fix=(
                "Put a time on and a different time off on the Warranty Copy, and have service management "
                "initial, date, and sign this labor during or at the time of the repair."
            ),
            citation="Service manager signature",
        ))
    has_wiring = any(kind == "wiring repair" or "wiring" in _clean(line.get("description")).casefold() for line, kind in kinds)
    has_diag = any(_lop_key(line.get("op_code")).startswith("8541") for line, _kind in kinds)
    if has_wiring and has_diag:
        findings.append(_shop_issue(
            severity="critical",
            ro_field="Wiring diagnosis",
            whats_wrong=(
                "This wiring repair also has an 85-41 diagnostic line. "
                "Wiring diagnosis stays on the wiring labor operation."
            ),
            how_to_fix="Remove the separate 85-41 line and keep the diagnosis time on the wiring labor operation.",
            citation="Wiring repair",
        ))
    if _mentions_goodwill(order) and not any(_lop_key(line.get("op_code")) == "8585CG09" for line in labor):
        findings.append(_shop_issue(
            severity="major",
            ro_field="LOP 85-85-CG-09",
            whats_wrong="Goodwill is on this repair order, and LOP 85-85-CG-09 is not.",
            how_to_fix="Add 85-85-CG-09 when this is a consumer goodwill claim.",
            citation="Consumer goodwill",
        ))
    return findings


def _mentions_goodwill(order: dict) -> bool:
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
    return bool(re.search(r"goodwill", " ".join(_clean(piece) for piece in pieces), re.IGNORECASE))


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
    if not _mentions_goodwill(order):
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
    r"inspected|broken|cracked|leaking|leak|worn|damaged|corroded|"
    r"seized|shorted|binding|contaminated|restricted|clogged|torn|"
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
    if any(_lop_key(line.get("op_code")).startswith("8541") for line in labor):
        if not re.search(
            r"\b(?:test|tested|scan|scanned|dtc|reading|readings|measured|voltage|pressure|spec|specs|diagnosis|diagnostic)\b",
            story,
            re.IGNORECASE,
        ):
            findings.append(_shop_issue(
                severity="critical",
                ro_field="Tech notes",
                whats_wrong="Operation diagnostics (85-41) do not state the tests and results.",
                how_to_fix="Write the diagnostic steps and the result. Trouble Not Found still needs the failure or concern code and a complete narrative.",
                citation="Operation diagnostics",
            ))
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
    tokens = set()
    for word in words:
        if word in stops:
            continue
        tokens.add(word)
        if len(word) >= 5 and word.endswith("s") and word[:-1] not in stops:
            tokens.add(word[:-1])
    return tokens


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

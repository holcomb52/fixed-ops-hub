"""Shared helpers for employee notes on payroll PDFs."""

from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer

PAYROLL_PDF_TITLE = "New Smyrna CJDR Payroll"


def payroll_pdf_header(pay_period: str, styles) -> list:
    """Title + pay period dates only — no app branding or generated timestamp."""
    title_style = ParagraphStyle(
        "PayrollTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    date_style = ParagraphStyle(
        "PayrollDates",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=14,
    )
    period = escape(str(pay_period or "—").strip())
    return [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(period, date_style),
    ]


def append_employee_notes(
    story: list,
    entries: list[tuple[str, str]],
    styles,
    *,
    heading: str = "Notes for payroll clerk",
) -> None:
    """Append a notes block when at least one employee has text."""
    filled = [(name.strip(), note.strip()) for name, note in entries if note and str(note).strip()]
    if not filled:
        return

    note_style = ParagraphStyle(
        "PayrollNote",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>{escape(heading)}</b>", styles["Heading3"]))
    story.append(Spacer(1, 4))
    for name, note in filled:
        safe_name = escape(name)
        safe_note = escape(note).replace("\n", "<br/>")
        story.append(Paragraph(f"<b>{safe_name}:</b> {safe_note}", note_style))

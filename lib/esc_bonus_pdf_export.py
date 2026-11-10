"""PDF export for Extended Service Contract claims bonus."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import PAYROLL_PDF_TITLE


def generate_esc_bonus_pdf(snapshot: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EscTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "EscSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "EscBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    month = escape(str(snapshot.get("bonus_month") or "—"))
    name = escape(str(snapshot.get("employee_name") or "—"))
    paid = escape(str(snapshot.get("paid_on_label") or "10th of the following month"))
    rate = float(snapshot.get("bonus_rate", 0.02) or 0.02)

    story = [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(f"Extended Service Contract Claims Bonus · {month}", sub_style),
        Paragraph(f"<b>Employee:</b> {name}", body),
        Paragraph(f"<b>Separate check paid on:</b> {paid}", body),
        Spacer(1, 8),
        Paragraph("<b>Service contract claims paid to the store</b>", styles["Heading3"]),
    ]

    rows = [
        ["Metric", "Amount"],
        ["Parts + labor paid (excl. deductibles / customer-pay)", f"${float(snapshot.get('amount_paid', 0) or 0):,.2f}"],
        ["Chargebacks / reversals", f"${float(snapshot.get('chargebacks', 0) or 0):,.2f}"],
        ["Net paid", f"${float(snapshot.get('net_paid', 0) or 0):,.2f}"],
        [f"Bonus rate ({rate * 100:.0f}% of net paid)", f"{rate * 100:.0f}%"],
        ["Bonus amount (separate check)", f"${float(snapshot.get('bonus_amount', 0) or 0):,.2f}"],
    ]
    table = Table(rows, colWidths=[4.2 * inch, 2.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfdf5")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Pay plan rules</b>", styles["Heading3"]))
    story.append(
        Paragraph(
            "Bonus is <b>2% of parts and labor dollars actually paid</b> to the store by the "
            "service contract company on claims the employee submits. Based on amount paid, "
            "not amount authorized. Deductibles, customer-pay, and denied claims are excluded. "
            "Chargebacks reduce the bonus in the month they occur. "
            "Calculated after month-end close and paid on the <b>10th of the following month</b> "
            "as a separate check.",
            body,
        )
    )

    notes = str(snapshot.get("notes") or "").strip()
    if notes:
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Notes</b>", styles["Heading3"]))
        story.append(Paragraph(escape(notes).replace("\n", "<br/>"), body))

    doc.build(story)
    return buffer.getvalue()

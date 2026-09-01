"""PDF export for CSI / NPS bonus."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import PAYROLL_PDF_TITLE


def generate_csi_bonus_pdf(snapshot: dict) -> bytes:
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
        "CsiTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "CsiSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "CsiBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    month = escape(str(snapshot.get("bonus_month") or "—"))
    name = escape(str(snapshot.get("employee_name") or "—"))
    paid = escape(str(snapshot.get("paid_on_label") or "First payroll of the following month"))
    tier = escape(str(snapshot.get("tier_label") or "—"))

    story = [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(f"CSI / NPS Bonus · {month}", sub_style),
        Paragraph(f"<b>Employee:</b> {name}", body),
        Paragraph(f"<b>Paid on:</b> {paid}", body),
        Spacer(1, 8),
        Paragraph("<b>Stellantis NPS results</b>", styles["Heading3"]),
    ]

    rows = [
        ["Metric", "Score"],
        ["Store NPS", f"{float(snapshot.get('store_nps', 0) or 0):.1f}"],
        ["National average", f"{float(snapshot.get('national_average', 0) or 0):.1f}"],
        ["Business center average", f"{float(snapshot.get('business_center_average', 0) or 0):.1f}"],
        ["Tier earned", tier],
        ["Bonus amount", f"${float(snapshot.get('bonus_amount', 0) or 0):,.2f}"],
    ]
    table = Table(rows, colWidths=[2.8 * inch, 3.4 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Pay plan tiers</b>", styles["Heading3"]))
    story.append(
        Paragraph(
            "At or above National Average → $1,000 · "
            "Between BC Average and National Average → $500 · "
            "Below Business Center Average → $0",
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

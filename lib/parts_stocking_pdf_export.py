"""PDF export for parts stocking plans."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEALERSHIP_TITLE = "New Smyrna CJDR"


def generate_parts_stocking_pdf(snapshot: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StockTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "StockSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "StockBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    cell = ParagraphStyle(
        "StockCell",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    label = escape(str(snapshot.get("label") or "Parts Stocking"))
    story = [
        Paragraph(DEALERSHIP_TITLE, title_style),
        Paragraph(f"Parts Stocking Plan · {label}", sub_style),
        Paragraph(
            "Order recommendations from 6-month sales (6MS). "
            "Target on hand = monthly average × months of supply; "
            "order qty fills the gap when QOH is below target.",
            body,
        ),
    ]

    summary = [
        ["Metric", "Value"],
        ["6MS file", escape(str(snapshot.get("source_file") or "—"))],
        ["Months of supply target", f"{float(snapshot.get('target_months', 0) or 0):.1f}"],
        ["Parts to order", f"{int(snapshot.get('order_count', 0) or 0)}"],
        ["Order dollars", f"${float(snapshot.get('order_total_cost', 0) or 0):,.2f}"],
        ["Adequate stock", f"{int(snapshot.get('ok_count', 0) or 0)}"],
        ["Overstock", f"{int(snapshot.get('overstock_count', 0) or 0)}"],
        ["No sales", f"{int(snapshot.get('no_sales_count', 0) or 0)}"],
        ["Total parts analyzed", f"{int(snapshot.get('candidate_count', 0) or 0)}"],
    ]
    summary_table = Table(summary, colWidths=[2.6 * inch, 4.6 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Parts to order</b>", styles["Heading3"]))

    rows = [
        [
            Paragraph("<b>Part</b>", cell),
            Paragraph("<b>Description</b>", cell),
            Paragraph("<b>QOH</b>", cell),
            Paragraph("<b>Sold 6mo</b>", cell),
            Paragraph("<b>Target</b>", cell),
            Paragraph("<b>Order</b>", cell),
            Paragraph("<b>Order $</b>", cell),
        ]
    ]
    order_lines = snapshot.get("order_lines") or [
        row for row in (snapshot.get("lines") or []) if float(row.get("order_qty", 0) or 0) > 0
    ]
    for item in order_lines:
        rows.append(
            [
                Paragraph(escape(str(item.get("part_number", ""))), cell),
                Paragraph(escape(str(item.get("description", ""))[:38]), cell),
                Paragraph(f"{float(item.get('qoh', 0) or 0):.0f}", cell),
                Paragraph(f"{float(item.get('sold_6mo', 0) or 0):.0f}", cell),
                Paragraph(f"{float(item.get('target_on_hand', 0) or 0):.0f}", cell),
                Paragraph(f"{float(item.get('order_qty', 0) or 0):.0f}", cell),
                Paragraph(f"${float(item.get('order_cost', 0) or 0):,.2f}", cell),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [
                Paragraph("—", cell),
                Paragraph("No parts need ordering", cell),
                Paragraph("", cell),
                Paragraph("", cell),
                Paragraph("", cell),
                Paragraph("", cell),
                Paragraph("", cell),
            ]
        )

    detail = Table(
        rows,
        colWidths=[
            1.15 * inch,
            2.2 * inch,
            0.55 * inch,
            0.65 * inch,
            0.55 * inch,
            0.5 * inch,
            0.8 * inch,
        ],
        repeatRows=1,
    )
    detail.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(detail)

    notes = str(snapshot.get("notes") or "").strip()
    if notes:
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Notes</b>", styles["Heading3"]))
        story.append(Paragraph(escape(notes).replace("\n", "<br/>"), body))

    doc.build(story)
    return buffer.getvalue()

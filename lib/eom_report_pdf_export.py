"""PDF export for Fixed Ops end-of-month controller report."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import PAYROLL_PDF_TITLE


def generate_eom_report_pdf(snapshot: dict) -> bytes:
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
        "EomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "EomSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "EomBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    month = escape(str(snapshot.get("report_month") or "—"))
    story = [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(f"Fixed Ops End-of-Month Report · {month}", sub_style),
        Paragraph("<b>Technician productivity</b>", styles["Heading3"]),
    ]

    tech_rows = [
        ["Metric", "Value"],
        ["Number of techs", f"{float(snapshot.get('tech_count', 0) or 0):.0f}"],
        ["Hours per day", f"{float(snapshot.get('hours_per_day', 0) or 0):.1f}"],
        ["Work days in month", f"{float(snapshot.get('work_days', 0) or 0):.0f}"],
        ["Total available hours", f"{float(snapshot.get('total_available_hours', 0) or 0):,.2f}"],
        ["Total clock time", f"{float(snapshot.get('total_clock_time', 0) or 0):,.2f}"],
        ["Tech flagged hours", f"{float(snapshot.get('tech_flagged_hours', 0) or 0):,.2f}"],
        ["Efficiency (flagged ÷ clock)", f"{float(snapshot.get('efficiency_pct', 0) or 0):.2f}%"],
    ]
    tech_table = Table(tech_rows, colWidths=[4.2 * inch, 2.4 * inch])
    tech_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(tech_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph("<b>Headcount</b>", styles["Heading3"]))

    head_rows = [
        ["Role", "Count"],
        ["Lot porters (incl. Misty)", f"{float(snapshot.get('lot_porters', 0) or 0):.0f}"],
        ["Cashiers (incl. Brandy & Serenity)", f"{float(snapshot.get('cashiers', 0) or 0):.0f}"],
        ["Advisors", f"{float(snapshot.get('advisors', 0) or 0):.0f}"],
        ["Part-time shuttle drivers", f"{float(snapshot.get('shuttle_drivers', 0) or 0):.0f}"],
    ]
    head_table = Table(head_rows, colWidths=[4.2 * inch, 2.4 * inch])
    head_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(head_table)

    notes = str(snapshot.get("notes") or "").strip()
    if notes:
        story.append(Spacer(1, 14))
        story.append(Paragraph("<b>Notes</b>", styles["Heading3"]))
        story.append(Paragraph(escape(notes).replace("\n", "<br/>"), body))

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "Total available hours = techs × hours/day × work days. "
            "Efficiency = tech flagged hours ÷ total clock time.",
            body,
        )
    )

    doc.build(story)
    return buffer.getvalue()

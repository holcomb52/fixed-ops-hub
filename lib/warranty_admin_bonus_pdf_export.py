"""PDF export for Warranty Administrator monthly bonus."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import PAYROLL_PDF_TITLE


def generate_warranty_admin_bonus_pdf(snapshot: dict) -> bytes:
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
        "WabTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "WabSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "WabBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    month = escape(str(snapshot.get("bonus_month") or "—"))
    name = escape(str(snapshot.get("employee_name") or "Warranty Administrator"))
    paid = escape(str(snapshot.get("paid_on_label") or "First payroll of the following month"))

    story = [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(f"Warranty Administrator Monthly Bonus · {month}", sub_style),
        Paragraph(f"<b>Employee:</b> {name}", body),
        Paragraph(f"<b>Paid on:</b> {paid}", body),
        Spacer(1, 8),
        Paragraph("<b>Performance metrics</b>", styles["Heading3"]),
    ]

    recv = snapshot.get("receivables") or {}
    days = snapshot.get("avg_days") or {}
    first = snapshot.get("first_pass") or {}

    rows = [
        ["Metric", "Result", "Tier", "Bonus"],
        [
            "Warranty receivables",
            f"${float(recv.get('input_value', 0) or 0):,.2f}",
            str(recv.get("tier_label") or "—"),
            f"${float(recv.get('amount', 0) or 0):,.2f}",
        ],
        [
            "Avg days to submit",
            f"{float(days.get('input_value', 0) or 0):.1f} days",
            str(days.get("tier_label") or "—"),
            f"${float(days.get('amount', 0) or 0):,.2f}",
        ],
        [
            "First-pass pay rate",
            f"{float(first.get('input_value', 0) or 0):.1f}%",
            str(first.get("tier_label") or "—"),
            f"${float(first.get('amount', 0) or 0):,.2f}",
        ],
        [
            "Stretch bonus (all top tiers)",
            "Earned" if snapshot.get("stretch_earned") else "Not earned",
            "Receivables ≤ $85k · ≤ 2.0 days · ≥ 90%",
            f"${float(snapshot.get('stretch_amount', 0) or 0):,.2f}",
        ],
    ]

    table = Table(rows, colWidths=[2.1 * inch, 1.35 * inch, 2.4 * inch, 0.95 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    reduction = float(snapshot.get("compliance_reduction", 0) or 0)
    total = float(snapshot.get("total_bonus", 0) or 0)
    subtotal = float(snapshot.get("metrics_subtotal", 0) or 0)
    summary = [
        ["Metrics + stretch", f"${subtotal:,.2f}"],
        ["Compliance reduction", f"-${reduction:,.2f}" if reduction else "$0.00"],
        ["TOTAL MONTHLY BONUS", f"${total:,.2f}"],
    ]
    summary_table = Table(summary, colWidths=[4.5 * inch, 2.3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0f172a")),
                ("TOPPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_table)

    notes = str(snapshot.get("notes") or "").strip()
    if notes:
        story.append(Spacer(1, 14))
        story.append(Paragraph("<b>Notes for payroll clerk</b>", styles["Heading3"]))
        story.append(Paragraph(escape(notes).replace("\n", "<br/>"), body))

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "Bonus is earned in addition to hourly pay, measured on a calendar-month basis, "
            "and subject to OEM / Stellantis compliance requirements.",
            body,
        )
    )

    doc.build(story)
    return buffer.getvalue()

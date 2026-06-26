"""Generate employee earnings lookup PDF for print and archive."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import List
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.earnings_report import EarningsLine, EmployeeEarningsSummary
from lib.payroll_pdf_notes import PAYROLL_PDF_TITLE


def _fmt_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def generate_earnings_report_pdf(
    start_date: date,
    end_date: date,
    role_filter: str,
    name_query: str,
    summaries: List[EmployeeEarningsSummary],
    lines: List[EarningsLine],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EarningsTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "EarningsSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )

    filter_bits = [f"Type: {escape(role_filter)}"]
    if name_query.strip():
        filter_bits.append(f"Name: {escape(name_query.strip())}")
    filter_text = " · ".join(filter_bits)

    grand_total = sum(item.total_pay for item in summaries)
    period_count = len({line.pay_period for line in lines})

    story = [
        Paragraph(PAYROLL_PDF_TITLE, title_style),
        Paragraph(
            f"<b>Employee Earnings Report</b><br/>"
            f"{_fmt_date(start_date)} – {_fmt_date(end_date)}<br/>"
            f"{filter_text}",
            subtitle_style,
        ),
        Paragraph(
            f"<b>{len(summaries)}</b> employees · "
            f"<b>{period_count}</b> pay periods · "
            f"<b>${grand_total:,.2f}</b> total paid",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph("<b>Summary by employee</b>", styles["Heading2"]),
        Spacer(1, 4),
    ]

    summary_data = [["Employee", "Type", "Pay periods", "Total earned"]]
    for item in summaries:
        summary_data.append([
            item.name,
            item.role,
            str(len(item.pay_periods)),
            f"${item.total_pay:,.2f}",
        ])
    summary_data.append([
        "",
        "TOTAL",
        "",
        f"${grand_total:,.2f}",
    ])

    summary_table = Table(
        summary_data,
        colWidths=[2.4 * inch, 1.4 * inch, 0.9 * inch, 1.1 * inch],
        repeatRows=1,
    )
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 16))
    story.append(Paragraph("<b>Pay period breakdown</b>", styles["Heading2"]))
    story.append(Spacer(1, 4))

    detail_data = [["Employee", "Type", "Pay period", "Period start", "Period end", "Earned"]]
    for line in lines:
        detail_data.append([
            line.name,
            line.role,
            line.pay_period,
            _fmt_date(line.period_start),
            _fmt_date(line.period_end),
            f"${line.total_pay:,.2f}",
        ])

    detail_table = Table(
        detail_data,
        colWidths=[1.8 * inch, 1.2 * inch, 1.2 * inch, 0.95 * inch, 0.95 * inch, 0.9 * inch],
        repeatRows=1,
    )
    detail_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(detail_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

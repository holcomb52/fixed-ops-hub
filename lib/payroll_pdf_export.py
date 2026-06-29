"""Generate payroll submission PDF."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import append_employee_notes, payroll_pdf_header


def generate_payroll_pdf(snapshot: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )

    styles = getSampleStyleSheet()

    story = payroll_pdf_header(snapshot["pay_period"], styles)

    headers = [
        "Tech #",
        "Technician",
        "Hours",
        "Dollars",
        "Prod Bonus",
        "Suppl Bonus",
        "Foreman / QL",
        "Train Hrs",
        "Training",
        "SPIFF",
        "Total Pay",
    ]

    for i, team in enumerate(snapshot["teams"]):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(f"<b>{team['name']}</b>", styles["Heading2"]))
        story.append(Spacer(1, 4))

        table_data = [headers]
        for t in team["technicians"]:
            bonus_cell = ""
            if t["bonus_amount"]:
                bonus_cell = f"{t['bonus_label']}\n${t['bonus_amount']:,.2f}"
            suppl_cell = ""
            if t.get("supplemental_bonus"):
                tier = t.get("supplemental_tier") or "Bonus"
                suppl_cell = f"{tier}\n${t['supplemental_bonus']:,.0f}"
            dollars_cell = f"${t['dollars']:,.2f}"
            if t.get("guarantee_top_up"):
                dollars_cell = (
                    f"${t['dollars']:,.2f}\n"
                    f"Guar +${t['guarantee_top_up']:,.2f}"
                )
            table_data.append([
                t.get("tech_number") or "—",
                t["name"],
                f"{t['hours']:.2f}",
                dollars_cell,
                f"${t['prod_bonus']:,.2f}",
                suppl_cell,
                bonus_cell,
                f"{t['training_hours']:.1f}" if t["training_hours"] else "—",
                f"${t['training_pay']:,.2f}",
                f"${t['spiff']:,.2f}" if t["spiff"] else "—",
                f"${t['total_pay']:,.2f}",
            ])

        table_data.append([
            "",
            "TEAM TOTAL",
            f"{team['team_hours']:.2f}",
            "", "", "", "", "", "",
            "",
            f"${team['team_total']:,.2f}",
        ])

        col_widths = [0.5 * inch, 1.15 * inch, 0.5 * inch, 0.65 * inch, 0.6 * inch, 0.65 * inch,
                      0.75 * inch, 0.45 * inch, 0.55 * inch, 0.45 * inch, 0.65 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        append_employee_notes(
            story,
            [(t["name"], t.get("notes", "")) for t in team["technicians"]],
            styles,
        )
        story.append(Spacer(1, 16))

    story.append(Paragraph(
        f"<b>GRAND TOTAL:</b> {snapshot['grand_hours']:.2f} hours &nbsp;|&nbsp; "
        f"<b>${snapshot['grand_total']:,.2f}</b> total pay",
        styles["Heading3"],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<i>Note: Noah Ihnken quick lube bonus is shown in Foreman/QL column but paid separately "
        "from column K total per payroll policy.</i>",
        ParagraphStyle("Note", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

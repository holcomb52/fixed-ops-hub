"""Generate service advisor payroll submission PDF."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import append_employee_notes, payroll_pdf_header


def generate_advisor_payroll_pdf(snapshot: dict) -> bytes:
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
        "ID",
        "Advisor",
        "Hours",
        "Labor Pay",
        "Parts",
        "CSI",
        "Alignment",
        "SPIFF",
        "Guarantee",
        "Total Pay",
    ]

    advisors = sorted(snapshot.get("advisors", []), key=lambda r: r["name"].lower())
    table_data = [headers]
    grand_total = 0.0

    for r in advisors:
        grand_total += r["total_pay"]
        guarantee_cell = "—"
        if r.get("guarantee_active"):
            guarantee_cell = f"Top-up\n${r['guarantee_top_up']:,.2f}"
        elif r.get("guarantee_amount", 0) > 0:
            guarantee_cell = f"${r['guarantee_amount']:,.2f}"

        table_data.append([
            r.get("advisor_id") or "—",
            r["name"],
            f"{r['hours_sold']:.1f}",
            f"${r['labor_pay']:,.2f}",
            f"${r['parts_pay']:,.2f}",
            f"${r['csi_pay']:,.2f}",
            f"${r['alignment_pay']:,.2f}" if r["alignment_pay"] else "—",
            f"${r['spiff']:,.2f}" if r["spiff"] else "—",
            guarantee_cell,
            f"${r['total_pay']:,.2f}",
        ])

    table_data.append([
        "", "TOTAL", "", "", "", "", "", "", "",
        f"${grand_total:,.2f}",
    ])

    col_widths = [
        0.5 * inch, 1.35 * inch, 0.55 * inch, 0.75 * inch,
        0.65 * inch, 0.6 * inch, 0.65 * inch, 0.55 * inch, 0.7 * inch, 0.75 * inch,
    ]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 1), (1, -1), "LEFT"),
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
        [(r["name"], r.get("notes", "")) for r in advisors],
        styles,
    )
    story.append(Spacer(1, 16))

    story.append(Paragraph(
        f"<b>GRAND TOTAL:</b> {snapshot.get('advisor_count', len(advisors))} advisors &nbsp;|&nbsp; "
        f"<b>${grand_total:,.2f}</b> total pay",
        styles["Heading3"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

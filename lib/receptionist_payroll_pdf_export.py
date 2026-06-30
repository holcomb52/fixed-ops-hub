"""Generate receptionist payroll submission PDF."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.payroll_pdf_notes import append_employee_notes, payroll_pdf_header



def generate_receptionist_payroll_pdf(snapshot: dict) -> bytes:
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
        "Employee",
        "Appts",
        "Appt Pay",
        "Tires",
        "Tire Pay",
        "Bonus",
        "SPIFF",
        "Total Pay",
    ]

    employees = snapshot.get("employees", [])

    def _append_table(title: str, rows: list):
        if not rows:
            return
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        story.append(Spacer(1, 4))
        table_data = [headers]
        section_total = 0.0
        for r in rows:
            section_total += r["total_pay"]
            bonus_cell = "—"
            bonus_parts = []
            if r.get("warranty_pay"):
                bonus_parts.append(f"Warranty\n${r['warranty_pay']:,.2f}")
            if r.get("csi_pay"):
                bonus_parts.append(f"CSI\n${r['csi_pay']:,.2f}")
            if r.get("bonus_pay"):
                label = r.get("bonus_label") or "Bonus"
                bonus_parts.append(f"{label}\n${r['bonus_pay']:,.2f}")
            if bonus_parts:
                bonus_cell = "\n".join(bonus_parts)
            table_data.append([
                r["name"],
                f"{r['appointments_set']:.0f}" if r["appointments_set"] else "—",
                f"${r['appointment_pay']:,.2f}" if r["appointment_pay"] else "—",
                f"{r['tires_sold']:.0f}" if r["tires_sold"] else "—",
                f"${r['tire_pay']:,.2f}" if r["tire_pay"] else "—",
                bonus_cell,
                f"${r['spiff']:,.2f}" if r["spiff"] else "—",
                f"${r['total_pay']:,.2f}",
            ])
        table_data.append(["", "SECTION TOTAL", "", "", "", "", "", f"${section_total:,.2f}"])

        col_widths = [
            1.35 * inch, 0.45 * inch, 0.7 * inch, 0.45 * inch,
            0.65 * inch, 0.85 * inch, 0.55 * inch, 0.75 * inch,
        ]
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
            [(r["name"], r.get("notes", "")) for r in rows],
            styles,
        )
        story.append(Spacer(1, 16))

    _append_table("Receptionists", employees)

    story.append(Paragraph(
        f"<b>GRAND TOTAL:</b> {snapshot.get('employee_count', 0)} employees &nbsp;|&nbsp; "
        f"<b>${snapshot['grand_total']:,.2f}</b> total pay",
        styles["Heading3"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

"""PDF export for parts return allowance plans."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEALERSHIP_TITLE = "New Smyrna CJDR"


def generate_parts_return_pdf(snapshot: dict) -> bytes:
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
        "PartsTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "PartsSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "PartsBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    cell = ParagraphStyle(
        "PartsCell",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    label = escape(str(snapshot.get("label") or "Parts Return"))
    story = [
        Paragraph(DEALERSHIP_TITLE, title_style),
        Paragraph(f"Parts Return Plan · {label}", sub_style),
        Paragraph(
            "One return allowance covers both MNS (months no sale) and "
            "MNR (months no receipt). Ranked by age × shelf value; "
            "multipack and misc hardware excluded when those filters were on.",
            body,
        ),
    ]

    summary = [
        ["Metric", "Value"],
        ["Return allowance", f"${float(snapshot.get('allowance', 0) or 0):,.2f}"],
        ["Parts selected", f"{int(snapshot.get('selected_count', 0) or 0)}"],
        ["Return dollars", f"${float(snapshot.get('selected_value', 0) or 0):,.2f}"],
        ["Allowance remaining", f"${float(snapshot.get('remaining_allowance', 0) or 0):,.2f}"],
        ["MNS file", escape(str(snapshot.get("mns_name") or "—"))],
        ["MNR file", escape(str(snapshot.get("mnr_name") or "—"))],
        [
            "Candidates / skipped",
            f"{int(snapshot.get('candidate_count', 0) or 0)} / "
            f"{int(snapshot.get('skipped_count', 0) or 0)}",
        ],
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
    story.append(Paragraph("<b>Recommended returns</b>", styles["Heading3"]))

    rows = [
        [
            Paragraph("<b>Part</b>", cell),
            Paragraph("<b>Description</b>", cell),
            Paragraph("<b>Src</b>", cell),
            Paragraph("<b>Age</b>", cell),
            Paragraph("<b>Qty</b>", cell),
            Paragraph("<b>Return $</b>", cell),
            Paragraph("<b>Bin</b>", cell),
        ]
    ]
    for item in snapshot.get("selected") or []:
        rows.append(
            [
                Paragraph(escape(str(item.get("part_number", ""))), cell),
                Paragraph(escape(str(item.get("description", ""))[:42]), cell),
                Paragraph(escape(str(item.get("source", ""))), cell),
                Paragraph(f"{float(item.get('age', 0) or 0):.0f}", cell),
                Paragraph(f"{float(item.get('return_qty', 0) or 0):.0f}", cell),
                Paragraph(f"${float(item.get('return_value', 0) or 0):,.2f}", cell),
                Paragraph(escape(str(item.get("bin_location", "") or "—")), cell),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [
                Paragraph("—", cell),
                Paragraph("No parts selected", cell),
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
            2.35 * inch,
            0.75 * inch,
            0.45 * inch,
            0.45 * inch,
            0.8 * inch,
            0.85 * inch,
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
                ("ALIGN", (3, 1), (5, -1), "RIGHT"),
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

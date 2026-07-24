"""PDF export for customer-pay labor rate grids."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_INK = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#64748b")
_LINE = colors.HexColor("#cbd5e1")
_HEADER_BG = colors.HexColor("#0f172a")
_HEADER_FG = colors.HexColor("#f8fafc")
_ROW_ALT = colors.HexColor("#f1f5f9")
_STRONG = colors.HexColor("#ecfeff")
_FOCUS = colors.HexColor("#e0f2fe")


def build_labor_rate_grid_pdf(
    *,
    title: str,
    subtitle: str = "",
    grid_rows: List[Dict[str, Any]],
    summary: Optional[Sequence[tuple[str, str]]] = None,
    strong_lo: float = 0.0,
    strong_hi: float = 0.0,
    generated_at: Optional[datetime] = None,
) -> bytes:
    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#0891b2"),
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "GridTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=_INK,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "GridSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=_MUTED,
        spaceAfter=6,
    )
    cell = ParagraphStyle(
        "GridCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=_INK,
        alignment=1,
    )
    cell_bold = ParagraphStyle(
        "GridCellBold",
        parent=cell,
        fontName="Helvetica-Bold",
    )
    hint = ParagraphStyle(
        "GridHint",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=_MUTED,
        spaceBefore=8,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.6 * inch,
        title=title,
        author="Fixed Ops Hub",
    )

    when = (generated_at or datetime.now()).astimezone()
    story: list = [
        Paragraph("NEW SMYRNA BEACH CHRYSLER", brand),
        Paragraph("Fixed Ops Hub", title_style),
        Paragraph(title, sub_style),
    ]
    if subtitle:
        story.append(Paragraph(subtitle, sub_style))
    story.append(Paragraph(f"Generated {when.strftime('%m/%d/%Y %I:%M %p')}", sub_style))
    story.append(Spacer(1, 0.1 * inch))

    if summary:
        sum_data = [
            [
                Paragraph(f"<b>{k}</b>", cell),
                Paragraph(str(v), cell_bold),
            ]
            for k, v in summary
        ]
        sum_table = Table(sum_data, colWidths=[2.4 * inch, 2.0 * inch])
        sum_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _FOCUS),
                    ("BOX", (0, 0), (-1, -1), 0.6, _LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, _LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(sum_table)
        story.append(Spacer(1, 0.16 * inch))

    story.append(
        Paragraph(
            f"Customer-pay labor grid · strong band {strong_lo:.1f}–{strong_hi:.1f} hrs",
            cell_bold,
        )
    )
    story.append(Spacer(1, 0.08 * inch))

    header = [
        Paragraph("HOUR", cell_bold),
        Paragraph("+.0", cell_bold),
        Paragraph("+.1", cell_bold),
        Paragraph("+.2", cell_bold),
        Paragraph("+.3", cell_bold),
        Paragraph("+.4", cell_bold),
    ]
    data = [header]
    strong_idxs: List[int] = []
    for idx, row in enumerate(grid_rows, start=1):
        data.append(
            [
                Paragraph(str(row.get("HOUR", "")), cell_bold),
                Paragraph(str(row.get("+.0", "") or "—"), cell),
                Paragraph(str(row.get("+.1", "") or "—"), cell),
                Paragraph(str(row.get("+.2", "") or "—"), cell),
                Paragraph(str(row.get("+.3", "") or "—"), cell),
                Paragraph(str(row.get("+.4", "") or "—"), cell),
            ]
        )
        if row.get("_strong"):
            strong_idxs.append(idx)

    table = Table(
        data,
        colWidths=[0.75 * inch, 1.15 * inch, 1.15 * inch, 1.15 * inch, 1.15 * inch, 1.15 * inch],
        repeatRows=1,
    )
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), _HEADER_FG),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, _LINE),
        ("BOX", (0, 0), (-1, -1), 0.8, _INK),
        ("BACKGROUND", (0, 1), (0, -1), _FOCUS),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (1, i), (-1, i), _ROW_ALT))
    for i in strong_idxs:
        cmds.append(("BACKGROUND", (0, i), (-1, i), _STRONG))
    table.setStyle(TableStyle(cmds))
    story.append(table)
    story.append(
        Paragraph(
            "Highlighted rows intersect the hour range where most of your work falls. "
            "Use this customer-pay schedule to support a Stellantis warranty labor rate request.",
            hint,
        )
    )

    def _footer(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(_LINE)
        canvas.line(0.5 * inch, 0.4 * inch, letter[0] - 0.5 * inch, 0.4 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawString(0.5 * inch, 0.25 * inch, "Fixed Ops Hub · Confidential")
        canvas.drawRightString(letter[0] - 0.5 * inch, 0.25 * inch, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()

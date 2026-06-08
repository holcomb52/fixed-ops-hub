"""Generate warranty labor rate analysis PDFs."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.warranty_labor_calc import (
    ELR_THRESHOLD,
    WarrantyLaborRow,
    WarrantyLaborSummary,
    exclusion_display_label,
)


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _truncate(text: str, limit: int = 28) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text or "—"
    return text[: limit - 1] + "…"


def _base_story(source_name: str, sheet_name: str, title: str) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=15,
        spaceAfter=6,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    return [
        Paragraph(title, title_style),
        Paragraph(
            f"Source: <b>{source_name}</b> &nbsp;|&nbsp; Worksheet: <b>{sheet_name}</b> "
            f"&nbsp;|&nbsp; Generated: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}",
            sub_style,
        ),
    ]


def _original_row_cells(row: WarrantyLaborRow) -> list:
    return [
        row.recid,
        row.ro_date,
        row.cwi_flag,
        _truncate(row.op_code, 18),
        _truncate(row.op_desc, 24),
        f"{row.tech_hrs:.2f}",
        _money(row.lbr_cost),
        _money(row.lbr_sale),
        _money(row.lbr_gross),
        _money(row.sheet_elr) if row.sheet_elr else _money(row.elr),
        _truncate(row.first_name, 12),
        _truncate(row.last_name, 12),
        row.make_code or "—",
        row.misc_code or "—",
        _truncate(row.notes, 20),
    ]


def _analysis_row_cells(row: WarrantyLaborRow) -> list:
    return [
        row.recid,
        row.ro_date,
        _truncate(row.op_code, 16),
        _truncate(row.op_desc, 22),
        f"{row.tech_hrs:.2f}",
        _money(row.lbr_sale),
        _money(row.elr),
        exclusion_display_label(row.exclusion),
    ]


def _build_table(
    headers: list[str],
    data_rows: list[list],
    col_widths: list[float],
    *,
    row_styles: list[dict] | None = None,
) -> Table:
    table_data = [headers] + data_rows
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if row_styles:
        for item in row_styles:
            style_commands.append(item)
    table.setStyle(TableStyle(style_commands))
    return table


def _summary_table(summary: WarrantyLaborSummary) -> Table:
    data = [
        ["Labor Dollars Sold (included)", _money(summary.total_lbr_sale)],
        ["Technician Flagged Hours (included)", f"{summary.total_tech_hrs:.2f}"],
        ["Effective Labor Rate", _money(summary.effective_labor_rate)],
    ]
    table = Table(data, colWidths=[3.2 * inch, 1.6 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf5")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#0f766e")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#99f6e4")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def generate_warranty_original_pdf(
    rows: List[WarrantyLaborRow],
    source_name: str,
    sheet_name: str,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.35 * inch,
        rightMargin=0.35 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    headers = [
        "RECID", "RO Date", "CWI", "Op Code", "Op Description",
        "Tech Hrs", "Lbr Cost", "Lbr Sale", "Lbr Gross", "ELR",
        "First", "Last", "Make", "Misc", "Notes",
    ]
    col_widths = [
        0.45 * inch, 0.55 * inch, 0.3 * inch, 0.75 * inch, 1.05 * inch,
        0.45 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch, 0.45 * inch,
        0.5 * inch, 0.5 * inch, 0.35 * inch, 0.35 * inch, 0.7 * inch,
    ]

    story = _base_story(
        source_name,
        sheet_name,
        "Fixed Ops Hub — Warranty Labor Rate (Original Import)",
    )
    story.append(_build_table(headers, [_original_row_cells(r) for r in rows], col_widths))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"<b>{len(rows)}</b> repair order lines imported · "
        f"ELR threshold reference: <b>{_money(ELR_THRESHOLD)}</b>",
        getSampleStyleSheet()["Normal"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_warranty_analysis_pdf(
    rows: List[WarrantyLaborRow],
    summary: WarrantyLaborSummary,
    source_name: str,
    sheet_name: str,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    headers = [
        "RECID", "RO Date", "Op Code", "Op Description",
        "Tech Hrs", "Labor Sale", "ELR", "Exclusion",
    ]
    col_widths = [
        0.55 * inch, 0.65 * inch, 0.8 * inch, 1.55 * inch,
        0.55 * inch, 0.7 * inch, 0.6 * inch, 1.1 * inch,
    ]

    data_rows = []
    row_styles = []
    for idx, row in enumerate(rows, start=1):
        data_rows.append(_analysis_row_cells(row))
        if row.exclusion:
            row_styles.append(("TEXTCOLOR", (0, idx), (-1, idx), colors.HexColor("#94a3b8")))
            row_styles.append(("FONTNAME", (0, idx), (-1, idx), "Helvetica-Oblique"))
        elif row.elr >= ELR_THRESHOLD:
            row_styles.append(("BACKGROUND", (6, idx), (6, idx), colors.HexColor("#14532d")))
            row_styles.append(("TEXTCOLOR", (6, idx), (6, idx), colors.HexColor("#bbf7d0")))
        elif row.elr > 0:
            row_styles.append(("BACKGROUND", (6, idx), (6, idx), colors.HexColor("#7f1d1d")))
            row_styles.append(("TEXTCOLOR", (6, idx), (6, idx), colors.HexColor("#fecaca")))

    story = _base_story(
        source_name,
        sheet_name,
        "Fixed Ops Hub — Warranty Labor Rate (With Exclusions)",
    )
    story.append(Paragraph(
        f"Excluded lines are removed from the shop ELR. Threshold: <b>{_money(ELR_THRESHOLD)}</b>",
        getSampleStyleSheet()["Normal"],
    ))
    story.append(Spacer(1, 8))
    story.append(_build_table(headers, data_rows, col_widths, row_styles=row_styles))
    story.append(Spacer(1, 18))
    story.append(Paragraph("<b>Effective Labor Rate Summary</b>", getSampleStyleSheet()["Heading3"]))
    story.append(Spacer(1, 6))
    story.append(_summary_table(summary))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"<b>{summary.included_rows}</b> included lines · "
        f"<b>{summary.excluded_rows}</b> excluded · "
        f"Formula: {_money(summary.total_lbr_sale)} labor sale ÷ "
        f"{summary.total_tech_hrs:.2f} tech hours = "
        f"<b>{_money(summary.effective_labor_rate)}</b>",
        getSampleStyleSheet()["Normal"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

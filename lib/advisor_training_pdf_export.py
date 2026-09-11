"""PDF export for Service Advisor daily training logs."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lib.advisor_training_calc import (
    RECOMMENDATION_LABELS,
    RECOMMENDATIONS,
    SKILL_LEVELS,
    SKILLS,
    TOPIC_GROUPS,
    normalize_recommendation,
    normalize_skills,
    normalize_topics,
)

DEALERSHIP_TITLE = "New Smyrna CJDR"


def _checked(on: bool) -> str:
    return "[X]" if on else "[ ]"


def _mark(selected: bool) -> str:
    return "[X]" if selected else "[ ]"


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _format_log_date(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return "—"
    try:
        from datetime import datetime

        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError:
        return value


def generate_advisor_training_pdf(snapshot: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AtTitle",
        parent=styles["Heading1"],
        fontSize=15,
        spaceAfter=2,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a"),
    )
    sub_style = ParagraphStyle(
        "AtSub",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "AtBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "AtSmall",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    section = ParagraphStyle(
        "AtSection",
        parent=styles["Heading3"],
        fontSize=11,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    group_style = ParagraphStyle(
        "AtGroup",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=4,
        spaceAfter=2,
    )

    topics = normalize_topics(snapshot.get("topics"))
    skills = normalize_skills(snapshot.get("skills"))
    trainee = escape(str(snapshot.get("trainee_name") or "—"))
    trainer = escape(str(snapshot.get("trainer_name") or "—"))
    day_num = escape(str(snapshot.get("day_number") or "—"))
    log_date = escape(_format_log_date(str(snapshot.get("log_date") or "")))
    rec = normalize_recommendation(snapshot.get("recommendation"))
    rec_label = escape(
        str(snapshot.get("recommendation_label") or RECOMMENDATION_LABELS.get(rec, "") or "—")
    )

    story = [
        Paragraph(DEALERSHIP_TITLE, title_style),
        Paragraph("Service Advisor Daily Training Log", sub_style),
        Paragraph("To be completed by the training advisor at the end of each shift", sub_style),
    ]

    header = Table(
        [
            [
                Paragraph(f"<b>Trainee:</b> {trainee}", body),
                Paragraph(f"<b>Trainer / Mentor:</b> {trainer}", body),
            ],
            [
                Paragraph(f"<b>Date:</b> {log_date}", body),
                Paragraph(f"<b>Training Day #:</b> {day_num}", body),
            ],
        ],
        colWidths=[3.6 * inch, 3.6 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header)

    story.append(Paragraph("1. Topics Covered Today", section))
    story.append(
        Paragraph(
            "Checked topics were reviewed or practiced with the trainee today.",
            small,
        )
    )

    other_note = str(snapshot.get("other_topic_note") or "").strip()
    for group_name, items in TOPIC_GROUPS:
        story.append(Paragraph(group_name, group_style))
        rows = []
        pair = []
        for tid, label in items:
            mark = _checked(bool(topics.get(tid)))
            cell_label = label
            if tid == "other" and other_note:
                cell_label = f"{label}: {other_note}"
            pair.append(Paragraph(f"{mark} {escape(cell_label)}", small))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            pair.append(Paragraph("", small))
            rows.append(pair)
        if rows:
            topic_table = Table(rows, colWidths=[3.6 * inch, 3.6 * inch])
            topic_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ]
                )
            )
            story.append(topic_table)

    story.append(Paragraph("2. Skill Proficiency Check-In", section))
    skill_header = ["Skill", *[label for _, label in SKILL_LEVELS]]
    skill_rows = [skill_header]
    for sid, label in SKILLS:
        level = skills.get(sid) or ""
        skill_rows.append(
            [
                Paragraph(escape(label), small),
                *[_mark(level == lid) for lid, _ in SKILL_LEVELS],
            ]
        )
    skill_table = Table(
        skill_rows,
        colWidths=[3.2 * inch, 1.3 * inch, 1.3 * inch, 1.3 * inch],
    )
    skill_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(skill_table)

    story.append(Paragraph("3. Trainee Questions / Areas of Confusion", section))
    story.append(_p(snapshot.get("trainee_questions") or "—", body))

    story.append(Paragraph("4. Trainer Notes & Feedback", section))
    story.append(_p(snapshot.get("trainer_notes") or "—", body))

    story.append(Paragraph("5. Focus for Next Session", section))
    story.append(_p(snapshot.get("next_focus") or "—", body))

    story.append(Paragraph("6. Trainer Recommendation", section))
    rec_rows = [["Option", "Selected"]]
    for rid, label in RECOMMENDATIONS:
        rec_rows.append([label, _mark(rec == rid)])
    rec_table = Table(rec_rows, colWidths=[5.5 * inch, 1.2 * inch])
    rec_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(rec_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Selected:</b> {rec_label}", body))
    rec_notes = str(snapshot.get("recommendation_notes") or "").strip()
    if rec_notes:
        story.append(Paragraph(f"<b>Rationale:</b> {escape(rec_notes).replace(chr(10), '<br/>')}", body))

    story.append(Paragraph("7. Sign-Off", section))
    sign = Table(
        [
            [
                Paragraph("<b>Trainer signature</b><br/><br/>_______________________________", body),
                Paragraph("<b>Date</b><br/><br/>____________________", body),
            ],
            [
                Paragraph("<b>Trainee signature</b><br/><br/>_______________________________", body),
                Paragraph("<b>Date</b><br/><br/>____________________", body),
            ],
        ],
        colWidths=[4.4 * inch, 2.4 * inch],
    )
    sign.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(sign)

    doc.build(story)
    return buffer.getvalue()

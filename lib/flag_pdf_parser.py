"""Parse Technician Timecard for Payroll PDF (flag sheets)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, List, Optional, Union

import pdfplumber

PDF_NAME_MAP = {
    "CHARLES H": "Charles Hinxman",
    "DERRICK OPP": "Derrick Opp",
    "OLAN": "Olan Halcomb",
    "QURAN HENRY": "Quran Henry",
    "GEORGE WEBB": "George Webb",
    "KENNETH PETERSON": "Kenneth Peterson",
    "MARVIN GRANICK": "Marvin Granick",
    "NOAH IHNKEN": "Noah Ihnken",
    "DENNIS PINO": "Dennis Pino",
    "THOMAS WYKE": "Thomas Wyke",
    "ARMAND LIEBES": "Armand Liebes",
    "DAX ROSENCRANTZ": "Dax Rosencrantz",
    "ZACKARY DANIELS": "Zachary Daniels",
    "ZIHAIR BUSCH": "Zihair Busch",
    "GARY FREEZE": "Gary Freeze",
    "CARSON LINKER": "Carson Linker",
    "CHRISTOPHER INGRAM": "Christopher Ingram",
    "DAMIAN BLAIR": "Damian Blair",
    "JOHN RICHARDSON": "John Richardson",
}

NAME_RE = re.compile(r"Tech Name:\s+(.+?)\s*\(Items:")
SUMMARY_RE = re.compile(r"Group T[^\d]*([\d.]+)\s+([\d.,]+)\s+([\d.,]+)")
DATE_RANGE_RE = re.compile(r"Date Range:\s*(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})")
LINE_RE = re.compile(
    r"^(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\S+)\s+(\d{6})\s+(\S+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
)


@dataclass
class FlagLineItem:
    date: str
    department: str
    ro_number: str
    operation_code: str
    booked_hours: float
    st_rate: float
    extended: float
    bill_type: str = ""


@dataclass
class TechFlagData:
    pdf_name: str
    display_name: str
    tech_number: str
    flat_rate_hours: float
    dollars_earned: float
    line_items: List[FlagLineItem] = field(default_factory=list)
    cp_hours: float = 0.0
    cp_ro_count: int = 0

    @property
    def effective_rate(self) -> float:
        if self.flat_rate_hours <= 0:
            return 0.0
        return self.dollars_earned / self.flat_rate_hours

    @property
    def cp_hrs_per_ro(self) -> float:
        if self.cp_ro_count <= 0:
            return 0.0
        return self.cp_hours / self.cp_ro_count


@dataclass
class FlagSheetParseResult:
    pay_period_start: Optional[str] = None
    pay_period_end: Optional[str] = None
    technicians: List[TechFlagData] = field(default_factory=list)


def normalize_tech_name(pdf_name: str) -> str:
    key = pdf_name.strip().upper()
    return PDF_NAME_MAP.get(key, pdf_name.strip().title())


def compute_cp_metrics(line_items: List[FlagLineItem]) -> tuple[float, int]:
    """CP hours and unique CP RO count — Customer bill type only."""
    cp_ros: set[str] = set()
    cp_hours = 0.0
    for item in line_items:
        if item.bill_type.lower() != "customer":
            continue
        cp_ros.add(item.ro_number)
        cp_hours += item.booked_hours
    return cp_hours, len(cp_ros)


def _bill_type_from_line(line: str) -> str:
    parts = line.split()
    if len(parts) >= 12:
        return parts[-2]
    return ""


def parse_flag_sheet(source: Union[str, Path, BinaryIO]) -> FlagSheetParseResult:
    result = FlagSheetParseResult()
    current_pdf_name: Optional[str] = None
    current_items: List[FlagLineItem] = []
    tech_buffer: dict = {}

    with pdfplumber.open(source) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    for raw_line in full_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if result.pay_period_start is None:
            dr = DATE_RANGE_RE.search(line)
            if dr:
                result.pay_period_start = dr.group(1)
                result.pay_period_end = dr.group(2)

        nm = NAME_RE.search(line)
        if nm:
            if current_pdf_name and current_pdf_name in tech_buffer:
                tech_buffer[current_pdf_name]["lines"] = current_items
            current_pdf_name = nm.group(1).strip()
            current_items = []
            tech_buffer.setdefault(
                current_pdf_name,
                {"hours": 0.0, "dollars": 0.0, "lines": [], "tech_number": ""},
            )
            continue

        sm = SUMMARY_RE.search(line)
        if sm and current_pdf_name:
            tech_buffer[current_pdf_name]["hours"] = float(sm.group(2))
            tech_buffer[current_pdf_name]["dollars"] = float(sm.group(3).replace(",", ""))
            tech_buffer[current_pdf_name]["lines"] = current_items
            current_pdf_name = None
            current_items = []
            continue

        lm = LINE_RE.match(line)
        if lm and current_pdf_name:
            if not tech_buffer[current_pdf_name]["tech_number"]:
                tech_buffer[current_pdf_name]["tech_number"] = lm.group(1)
            current_items.append(
                FlagLineItem(
                    date=lm.group(2),
                    department=lm.group(3),
                    ro_number=lm.group(4),
                    operation_code=lm.group(5),
                    booked_hours=float(lm.group(7)),
                    st_rate=float(lm.group(8)),
                    extended=float(lm.group(9)),
                    bill_type=_bill_type_from_line(line),
                )
            )

    for pdf_name, data in tech_buffer.items():
        if data["hours"] == 0 and data["dollars"] == 0:
            continue
        lines = data.get("lines", [])
        cp_hours, cp_ro_count = compute_cp_metrics(lines)
        result.technicians.append(
            TechFlagData(
                pdf_name=pdf_name,
                display_name=normalize_tech_name(pdf_name),
                tech_number=data.get("tech_number", ""),
                flat_rate_hours=data["hours"],
                dollars_earned=data["dollars"],
                line_items=lines,
                cp_hours=cp_hours,
                cp_ro_count=cp_ro_count,
            )
        )

    result.technicians.sort(key=lambda t: t.display_name)
    return result

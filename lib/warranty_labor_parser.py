"""Parse warranty labor rate spreadsheets."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import BinaryIO, List, Union

import openpyxl

from lib.warranty_labor_calc import WarrantyLaborRow

HEADER_MAP = {
    "RECID": "recid",
    "RO-DATE": "ro_date",
    "ADV-NO": "advisor_no",
    "CWI-FLAG": "cwi_flag",
    "SVC-OP-CODES": "op_code",
    "OP-DESC": "op_desc",
    "TECH HRS": "tech_hrs",
    "LBR COST": "lbr_cost",
    "LBR SALE": "lbr_sale",
    "LBR-GROSS": "lbr_gross",
    "ELR": "sheet_elr",
    "FIRST-NAME": "first_name",
    "LAST-NAME": "last_name",
    "STD-MK-CODE": "make_code",
    "MISC CODE": "misc_code",
    "NOTES": "notes",
}


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%m/%d/%Y")
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    return str(value).strip()


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def list_sheet_names(source: Union[str, BytesIO, BinaryIO]) -> List[str]:
    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    return wb.sheetnames


def parse_warranty_labor_report(
    source: Union[str, BytesIO, BinaryIO],
    sheet_name: str | None = None,
) -> List[WarrantyLaborRow]:
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    headers = []
    for cell in ws[1]:
        headers.append(str(cell.value or "").strip().upper())

    col_index = {}
    for idx, header in enumerate(headers):
        if header in HEADER_MAP:
            col_index[HEADER_MAP[header]] = idx

    required = {"recid", "tech_hrs", "lbr_sale"}
    if not required.issubset(col_index):
        missing = required - set(col_index)
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows: List[WarrantyLaborRow] = []
    line_index = 0
    for row_cells in ws.iter_rows(min_row=2, values_only=True):
        if not row_cells or row_cells[col_index["recid"]] in (None, ""):
            continue

        def _cell(field: str, default=""):
            idx = col_index.get(field)
            if idx is None:
                return default
            value = row_cells[idx]
            return "" if value is None else value

        recid = str(_cell("recid")).strip()
        rows.append(
            WarrantyLaborRow(
                line_id=f"{line_index:04d}-{recid}",
                recid=recid,
                ro_date=_fmt_date(_cell("ro_date")),
                advisor_no=str(_cell("advisor_no") or "").strip(),
                cwi_flag=str(_cell("cwi_flag") or "").strip(),
                op_code=str(_cell("op_code") or "").strip(),
                op_desc=str(_cell("op_desc") or "").strip(),
                tech_hrs=_float(_cell("tech_hrs")),
                lbr_cost=_float(_cell("lbr_cost")),
                lbr_sale=_float(_cell("lbr_sale")),
                lbr_gross=_float(_cell("lbr_gross")),
                sheet_elr=_float(_cell("sheet_elr")),
                first_name=str(_cell("first_name") or "").strip(),
                last_name=str(_cell("last_name") or "").strip(),
                make_code=str(_cell("make_code") or "").strip(),
                misc_code=str(_cell("misc_code") or "").strip(),
                notes=str(_cell("notes") or "").strip(),
            )
        )
        line_index += 1

    return rows

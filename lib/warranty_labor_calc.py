"""Warranty customer-pay effective labor rate calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

ELR_THRESHOLD = 279.29

EXCLUSION_OPENED_BEFORE_CURRENT_MONTH = "Opened Before Current Month"

EXCLUSION_INCLUDED_LABEL = "Included"

EXCLUSION_OPTIONS = [
    "",
    EXCLUSION_OPENED_BEFORE_CURRENT_MONTH,
    "Service Contract",
    "Fleet Vehicle",
    "Maintenance",
    "Battery",
    "Wipers",
    "Accessory install",
    "Tires",
    "Body Work",
    "Brake pads",
    "Brake pads and Rotors (No calipers)",
    "Aftermarket parts",
]

def get_builtin_exclusion_values() -> list[str]:
    return [option for option in EXCLUSION_OPTIONS if option]


def get_exclusion_select_options(
    custom_exclusions: list[str] | None = None,
    active_exclusions: list[str] | None = None,
) -> list[str]:
    custom = custom_exclusions or []
    active = active_exclusions or []
    seen: set[str] = set()
    options = [""]
    for option in get_builtin_exclusion_values() + list(custom) + list(active):
        key = option.casefold()
        if option and key not in seen:
            options.append(option)
            seen.add(key)
    return options


def is_valid_exclusion_value(value: str, custom_exclusions: list[str] | None = None) -> bool:
    custom = custom_exclusions or []
    return value in EXCLUSION_OPTIONS or value in custom


def exclusion_display_label(exclusion: str) -> str:
    return EXCLUSION_INCLUDED_LABEL if not (exclusion or "").strip() else exclusion


def exclusion_widget_label(exclusion: str) -> str:
    return "" if not (exclusion or "").strip() else exclusion


def label_to_exclusion(label: str, custom_exclusions: list[str] | None = None) -> str:
    if not (label or "").strip() or label == EXCLUSION_INCLUDED_LABEL:
        return ""
    if is_valid_exclusion_value(label, custom_exclusions):
        return label
    return ""


def parse_ro_date(value: str) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def is_ro_opened_before_current_month(ro_date: str, today: Optional[date] = None) -> bool:
    parsed = parse_ro_date(ro_date)
    if not parsed:
        return False
    ref = today or date.today()
    return parsed < ref.replace(day=1)


def apply_import_exclusions(
    rows: List[WarrantyLaborRow],
    existing_exclusions: dict[str, str] | None = None,
    existing_by_index: list[str] | None = None,
    today: Optional[date] = None,
) -> List[WarrantyLaborRow]:
    saved = existing_exclusions or {}
    for index, row in enumerate(rows):
        recid = str(row.recid)
        if existing_by_index is not None and index < len(existing_by_index):
            row.exclusion = existing_by_index[index]
        elif row.line_id and row.line_id in saved:
            row.exclusion = saved[row.line_id]
        elif recid in saved:
            row.exclusion = saved[recid]
        else:
            row.exclusion = ""
    return rows


def _line_id_index(line_id: str) -> int:
    prefix = str(line_id or "").split("-", 1)[0]
    try:
        return int(prefix)
    except ValueError:
        return 0


def build_saved_exclusion_map(rows: List[WarrantyLaborRow]) -> dict[str, str]:
    """Map line_id and recid to saved exclusion choices."""
    saved: dict[str, str] = {}
    for row in rows:
        if row.line_id:
            saved[row.line_id] = row.exclusion
        saved[str(row.recid).strip()] = row.exclusion
    return saved


def merge_warranty_rows(
    existing: List[WarrantyLaborRow],
    incoming: List[WarrantyLaborRow],
) -> tuple[List[WarrantyLaborRow], int, int, List[WarrantyLaborRow]]:
    """Append incoming rows whose RECID is not already in existing.

    Returns (merged_rows, added_recid_count, skipped_recid_count, newly_added_rows).
    """
    if not existing:
        deduped_incoming = _dedupe_incoming_by_recid(incoming)
        return deduped_incoming, _count_recids(deduped_incoming), 0, list(deduped_incoming)

    existing_recids = {str(row.recid).strip() for row in existing}
    skipped_recids: set[str] = set()
    pending: dict[str, list[WarrantyLaborRow]] = {}

    for row in incoming:
        recid = str(row.recid).strip()
        if not recid:
            continue
        if recid in existing_recids:
            skipped_recids.add(recid)
            continue
        pending.setdefault(recid, []).append(row)

    next_index = max((_line_id_index(row.line_id) for row in existing), default=-1) + 1
    added_rows: list[WarrantyLaborRow] = []
    line_counter = 0
    for recid in sorted(pending.keys()):
        for row in pending[recid]:
            row.line_id = f"{next_index + line_counter:04d}-{recid}"
            line_counter += 1
            added_rows.append(row)

    merged = list(existing) + added_rows
    return merged, len(pending), len(skipped_recids), added_rows


def _dedupe_incoming_by_recid(rows: List[WarrantyLaborRow]) -> List[WarrantyLaborRow]:
    """First import — assign stable line_ids; keep all lines per RECID."""
    out: list[WarrantyLaborRow] = []
    for index, row in enumerate(rows):
        recid = str(row.recid).strip()
        row.line_id = f"{index:04d}-{recid}"
        out.append(row)
    return out


def _count_recids(rows: List[WarrantyLaborRow]) -> int:
    return len({str(row.recid).strip() for row in rows if str(row.recid).strip()})


def exclusion_widget_key(row: WarrantyLaborRow) -> str:
    return f"warranty_exc_{row.line_id or row.recid}"


def review_widget_key(recid: str) -> str:
    return f"warranty_ro_reviewed_{recid}"


@dataclass
class WarrantyLaborRow:
    line_id: str
    recid: str
    ro_date: str
    advisor_no: str
    cwi_flag: str
    op_code: str
    op_desc: str
    tech_hrs: float
    lbr_cost: float
    lbr_sale: float
    lbr_gross: float
    sheet_elr: float
    first_name: str
    last_name: str
    make_code: str
    misc_code: str
    notes: str
    exclusion: str = ""

    @property
    def elr(self) -> float:
        if self.tech_hrs <= 0:
            return 0.0
        return self.lbr_sale / self.tech_hrs

    @property
    def included(self) -> bool:
        return not (self.exclusion or "").strip()

    @property
    def meets_threshold(self) -> bool:
        return self.elr >= ELR_THRESHOLD


@dataclass
class WarrantyLaborSummary:
    total_rows: int
    included_rows: int
    excluded_rows: int
    total_lbr_sale: float
    total_tech_hrs: float
    effective_labor_rate: float
    threshold: float = ELR_THRESHOLD

    @property
    def meets_threshold(self) -> bool:
        return self.effective_labor_rate >= self.threshold


def summarize_rows(rows: List[WarrantyLaborRow]) -> WarrantyLaborSummary:
    included = [r for r in rows if r.included]
    total_lbr = sum(r.lbr_sale for r in included)
    total_hrs = sum(r.tech_hrs for r in included)
    elr = total_lbr / total_hrs if total_hrs > 0 else 0.0
    return WarrantyLaborSummary(
        total_rows=len(rows),
        included_rows=len(included),
        excluded_rows=len(rows) - len(included),
        total_lbr_sale=total_lbr,
        total_tech_hrs=total_hrs,
        effective_labor_rate=elr,
    )


def rows_to_display_dicts(rows: List[WarrantyLaborRow]) -> list[dict]:
    out = []
    for row in rows:
        out.append({
            "RECID": row.recid,
            "RO Date": row.ro_date,
            "Op Code": row.op_code,
            "Op Description": row.op_desc,
            "Tech Hrs": row.tech_hrs,
            "Labor Sale": row.lbr_sale,
            "ELR": round(row.elr, 2),
            "Exclusion": exclusion_display_label(row.exclusion),
            "Notes": row.notes,
        })
    return out


def apply_display_edits(rows: List[WarrantyLaborRow], edited: list[dict]) -> List[WarrantyLaborRow]:
    by_recid = {str(r.recid): r for r in rows}
    for item in edited:
        recid = str(item.get("RECID", ""))
        if recid in by_recid:
            exclusion = item.get("Exclusion", "") or ""
            if not is_valid_exclusion_value(exclusion):
                exclusion = ""
            by_recid[recid].exclusion = exclusion
    return list(by_recid.values())

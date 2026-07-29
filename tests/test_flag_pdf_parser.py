"""Unit tests for CDK Technician Timecard (flag sheet) PDF line parsing."""

from __future__ import annotations

from lib.flag_pdf_parser import (
    _finalize_tech_totals,
    _parse_detail_line,
    normalize_tech_name,
)


def test_classic_spaced_line():
    line = (
        "3520 07/15/2026 Service 579963 01CHZ-TIRE4 0.00 1.10 22.75 25.03 5 Customer I"
    )
    parsed = _parse_detail_line(line)
    assert parsed is not None
    tech_number, item = parsed
    assert tech_number == "3520"
    assert item.date == "07/15/2026"
    assert item.department == "Service"
    assert item.ro_number == "579963"
    assert item.booked_hours == 1.10
    assert item.extended == 25.03
    assert item.bill_type == "Customer"


def test_jammed_truncated_line():
    line = "352007/15/2...Service 579963 01CHZ-TIRE4 0.00 1.10 22.... 25.03 5 Custo...I"
    parsed = _parse_detail_line(line)
    assert parsed is not None
    tech_number, item = parsed
    assert tech_number == "3520"
    assert item.date.startswith("07/15/2")
    assert item.department == "Service"
    assert item.ro_number == "579963"
    assert item.booked_hours == 1.10
    assert item.extended == 25.03
    assert item.bill_type == "Customer"


def test_jammed_warranty_and_internal_tokens():
    warranty = _parse_detail_line(
        "352007/16/2...Service 580143 01CHZRECA... 0.00 0.20 22.... 4.55 1 Warr... I"
    )
    internal = _parse_detail_line(
        "352007/16/2...Service 580170 01CHZACC 0.00 1.50 22.... 34.13 1 InternalI"
    )
    assert warranty is not None and warranty[1].bill_type == "Warranty"
    assert internal is not None and internal[1].bill_type == "Internal"


def test_finalize_sums_when_group_total_missing():
    from lib.flag_pdf_parser import FlagLineItem

    data = {
        "hours": 0.0,
        "dollars": 0.0,
        "lines": [
            FlagLineItem("07/15/2026", "Service", "1", "OP", 1.0, 20.0, 20.0, "Customer"),
            FlagLineItem("07/15/2026", "Service", "2", "OP", 0.5, 20.0, 10.0, "Warranty"),
        ],
    }
    _finalize_tech_totals(data)
    assert data["hours"] == 1.5
    assert data["dollars"] == 30.0


def test_normalize_known_pdf_name():
    assert normalize_tech_name("CHARLES H") == "Charles Hinxman"
    assert normalize_tech_name("ARMAND LIEBES") == "Armand Liebes"

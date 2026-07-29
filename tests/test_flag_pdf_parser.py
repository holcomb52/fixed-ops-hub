"""Unit tests for CDK Technician Timecard (flag sheet) PDF line parsing."""

from __future__ import annotations

import unittest

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


def test_jammed_line_missing_actual_column():
    line = "352007/18/2...Service 580317 26CHZOILC... 0.30 22.... 6.83 3 InternalI"
    parsed = _parse_detail_line(line)
    assert parsed is not None
    tech_number, item = parsed
    assert tech_number == "3520"
    assert item.ro_number == "580317"
    assert item.booked_hours == 0.30
    assert item.extended == 6.83
    assert item.bill_type == "Internal"


def test_jammed_negative_booked_adjustment():
    line = "374107/28/2...Service 580462 05CHZZ1 0.00 -0.50 42.... -21.00 1 Warr... I"
    parsed = _parse_detail_line(line)
    assert parsed is not None
    tech_number, item = parsed
    assert tech_number == "3741"
    assert item.booked_hours == -0.50
    assert item.extended == -21.00
    assert item.bill_type == "Warranty"


def test_classic_negative_booked_adjustment():
    line = (
        "3741 07/28/2026 Service 580462 05CHZZ1 0.00 -0.50 42.000 -21.00 1 Warranty I"
    )
    parsed = _parse_detail_line(line)
    assert parsed is not None
    _, item = parsed
    assert item.booked_hours == -0.50
    assert item.extended == -21.00
    assert item.bill_type == "Warranty"


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


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            suite.addTest(unittest.FunctionTestCase(obj))
    return suite

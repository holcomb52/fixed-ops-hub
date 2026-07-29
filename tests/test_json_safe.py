"""Tests for JSON-safe float coercion used by payroll cloud backup."""

from __future__ import annotations

import unittest

import json
import math

from lib.json_safe import json_safe, safe_float
from lib.tech_payroll_calc import TechPayrollRow, apply_closing_metrics
from lib.payroll_storage import serialize_payroll_session


def test_safe_float_rejects_nan_and_inf():
    assert safe_float(float("nan")) == 0.0
    assert safe_float(float("inf")) == 0.0
    assert safe_float("nan") == 0.0
    assert safe_float("52%") == 52.0
    assert safe_float(None) == 0.0
    assert safe_float(12.5) == 12.5


def test_json_safe_makes_payload_strict_json():
    payload = {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": -float("inf")}}
    cleaned = json_safe(payload)
    assert cleaned["a"] == 0.0
    assert cleaned["b"] == [1.0, 0.0]
    assert cleaned["c"]["d"] == 0.0
    json.dumps(cleaned, allow_nan=False)


def test_apply_closing_metrics_clears_nan():
    row = TechPayrollRow(name="Charles Hinxman", team="Olan's Team")
    apply_closing_metrics([row], {"Charles Hinxman": float("nan")})
    assert row.closing_pct == 0.0
    assert math.isfinite(row.closing_pct)


def test_serialize_payroll_session_rejects_nan():
    row = TechPayrollRow(
        name="Charles Hinxman",
        team="Olan's Team",
        flat_rate_hours=10.0,
        dollars_earned=200.0,
        closing_pct=float("nan"),
        cp_hrs_per_ro=float("nan"),
    )
    snapshot = serialize_payroll_session({"Olan's Team": [row]}, "07/15/26-07/28/26")
    json.dumps(snapshot, allow_nan=False)
    tech = snapshot["teams"]["Olan's Team"][0]
    assert tech["closing_pct"] == 0.0
    assert tech["cp_hrs_per_ro"] == 0.0


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            suite.addTest(unittest.FunctionTestCase(obj))
    return suite

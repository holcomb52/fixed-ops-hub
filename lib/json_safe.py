"""Make nested payloads safe for strict JSON (no NaN/Infinity)."""

from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; treat None/blank/NaN/Inf as default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return default if not math.isfinite(number) else number
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text or text.lower() in {"nan", "none", "null", "inf", "-inf", "+inf"}:
        return default
    try:
        number = float(text)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(number) else number


def json_safe(value: Any) -> Any:
    """Recursively replace non-JSON floats and leave other values intact."""
    if isinstance(value, float):
        return 0.0 if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value

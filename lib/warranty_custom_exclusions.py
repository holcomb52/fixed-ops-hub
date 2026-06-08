"""Persist user-defined warranty ELR exclusion categories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "warranty_custom_exclusions.json"


def _normalize(label: str) -> str:
    return " ".join(str(label or "").strip().split())


def load_custom_exclusions() -> List[str]:
    if not STORE_PATH.exists():
        return []
    try:
        data = json.loads(STORE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out: List[str] = []
    seen = set()
    for item in data:
        label = _normalize(item)
        if label and label not in seen:
            out.append(label)
            seen.add(label)
    return out


def save_custom_exclusions(exclusions: List[str]) -> List[str]:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned: List[str] = []
    seen = set()
    for item in exclusions:
        label = _normalize(item)
        if label and label not in seen:
            cleaned.append(label)
            seen.add(label)
    STORE_PATH.write_text(json.dumps(cleaned, indent=2))
    return cleaned


def add_custom_exclusion(
    label: str,
    existing: List[str] | None = None,
    reserved: List[str] | None = None,
) -> tuple[List[str], str | None]:
    cleaned = _normalize(label)
    if not cleaned:
        return list(existing or []), "Enter an exclusion name."
    if cleaned.lower() == "included":
        return list(existing or []), "That name is reserved."

    blocked = {name.lower() for name in (reserved or []) if name}
    if cleaned.lower() in blocked:
        return list(existing or []), "That exclusion already exists."

    current = list(existing or load_custom_exclusions())
    if any(item.lower() == cleaned.lower() for item in current):
        return current, "That custom exclusion is already on your list."

    current.append(cleaned)
    return save_custom_exclusions(current), None


def remove_custom_exclusion(label: str, existing: List[str] | None = None) -> List[str]:
    target = _normalize(label).lower()
    current = [item for item in (existing or load_custom_exclusions()) if item.lower() != target]
    return save_custom_exclusions(current)

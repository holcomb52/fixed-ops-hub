"""Phone camera that can snap every page of a claim before sending them together."""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT = components.declare_component(
    "claim_camera",
    path=str(Path(__file__).resolve().parent.parent / "components" / "claim_camera"),
)


def claim_camera(limit: int) -> list[tuple[str, bytes]]:
    """Return newly snapped pictures as (name, jpeg bytes). Empty when nothing new was sent."""
    value = _COMPONENT(limit=int(limit), default=None, key="warranty_audit_multishot")
    if not isinstance(value, list):
        return []
    return data_urls_to_files(value)


def data_urls_to_files(urls: list) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for index, url in enumerate(urls, start=1):
        if not isinstance(url, str) or "," not in url:
            continue
        encoded = url.split(",", 1)[1]
        try:
            files.append((f"phone-page-{index}.jpg", base64.b64decode(encoded)))
        except Exception:
            continue
    return files

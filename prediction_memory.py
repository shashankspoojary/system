# prediction_memory.py
"""
prediction_memory.py

Simple field-level frequency store for the Prediction Reasoning Layer.

This module keeps track of how many times each canonical dropdown value
has been successfully selected for a given field.

It deliberately does NOT store any OCR strings or screenshots.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict

PREDICTION_MEMORY_FILE = "prediction_memory.json"

# Minimum total selections required for a field before we trust its priors.
MIN_SAMPLES_PER_FIELD = 20

# In-memory cache + lock to avoid excessive disk IO.
_lock = threading.RLock()
_mem_cache: Dict[str, Dict] | None = None


def _load_raw() -> Dict:
    """Internal: load raw dict from disk, or return empty skeleton."""
    if not os.path.exists(PREDICTION_MEMORY_FILE):
        return {"field_stats": {}}
    try:
        with open(PREDICTION_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"field_stats": {}}
        if "field_stats" not in data or not isinstance(data["field_stats"], dict):
            data["field_stats"] = {}
        return data
    except Exception:
        # On any error, start fresh (file might be corrupted)
        return {"field_stats": {}}


def _save_raw(data: Dict) -> None:
    tmp = PREDICTION_MEMORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PREDICTION_MEMORY_FILE)
    except Exception as e:
        print(f"[PREDICTION_MEMORY] Failed to save: {e}")


def load_prediction_memory() -> Dict:
    """Return the full prediction memory dict."""
    global _mem_cache
    with _lock:
        if _mem_cache is None:
            _mem_cache = _load_raw()
        return _mem_cache


def save_prediction_memory(mem: Dict) -> None:
    """Persist the given memory dict and refresh cache."""
    global _mem_cache
    with _lock:
        _mem_cache = mem
        _save_raw(mem)


def _norm_field(field_name: str) -> str:
    return (field_name or "").strip().lower()


def bump_field_value(field_name: str, canonical_value: str) -> None:
    """
    Increment count for this (field, canonical_value) pair.

    Intended to be called only AFTER a field has been successfully filled
    with high confidence (i.e., after the bot actually clicks the dropdown row).
    """
    if not field_name or not canonical_value:
        return

    field_key = _norm_field(field_name)
    value_key = str(canonical_value).strip()

    with _lock:
        mem = load_prediction_memory()
        stats = mem.setdefault("field_stats", {})
        field_stats = stats.setdefault(field_key, {})
        try:
            current = int(field_stats.get(value_key, 0))
        except Exception:
            current = 0
        field_stats[value_key] = current + 1
        save_prediction_memory(mem)


def get_prior(field_name: str, canonical_value: str) -> float:
    """
    Return a prior probability (0..1) that this canonical_value is common
    for the given field, based on historical selections.

    - If there are not enough samples for the field (total < MIN_SAMPLES_PER_FIELD),
      returns 0.0 so that history has no effect yet.
    - Otherwise, returns count(value) / total_count.
    """
    if not field_name or not canonical_value:
        return 0.0

    field_key = _norm_field(field_name)
    value_key = str(canonical_value).strip()

    mem = load_prediction_memory()
    stats = mem.get("field_stats", {})
    field_stats = stats.get(field_key) or {}
    if not field_stats:
        return 0.0

    total = 0
    for _, v in field_stats.items():
        try:
            total += int(v)
        except Exception:
            continue

    if total < MIN_SAMPLES_PER_FIELD or total <= 0:
        return 0.0

    try:
        count_val = int(field_stats.get(value_key, 0))
    except Exception:
        count_val = 0

    if count_val <= 0:
        return 0.0

    return float(count_val) / float(total)

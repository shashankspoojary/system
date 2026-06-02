"""
info_normalizer.py

Snap/normalize *info-panel* OCR values to canonical dropdown labels.

Goal:
- When info panel reads noisy targets like "z1st Pada",
  normalize to "1st Pada" using the dropdown datasets.
- Uses reasoning_core's canonical brain & scoring.
- Pure logic: no clicking/scrolling.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional
import json
import os

from reasoning_core import (
    CANONICAL_BRAIN,
    map_visible_to_canonicals,
    normalize_text,
)
def report_uncovered_fields(extracted: dict):
    covered = set(CANONICAL_BRAIN.keys())
    missing = []
    for k in extracted.keys():
        if k.strip().lower() not in covered:
            missing.append(k)
    print("Uncovered info-panel fields:", missing)
REASONING_PROFILE_FILE = "reasoning_profile.json"
_DEFAULT_SNAP_SCORE = 0.82

# Aliases so info-panel field names map to the same canonical brain keys
_FIELD_ALIASES = {
    "sub cast": "sub cast",
    "subcast": "sub cast",
    "sub caste": "sub cast",
    "subcaste": "sub cast",
    "sub-caste": "sub cast",

    "qualification": "education",
    "edu": "education",

    "caste": "cast",

    # (optional but useful) key-name variations from OCR
    "state name": "state",
    "district name": "district",
}




_PROFILE_CACHE: Optional[Dict[str, Any]] = None


def _load_profile() -> Dict[str, Any]:
    """Load per-field min_score_ok if available (same file reasoning uses)."""
    global _PROFILE_CACHE
    if _PROFILE_CACHE is not None:
        return _PROFILE_CACHE
    try:
        with open(REASONING_PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        # lowercase keys once
        _PROFILE_CACHE = {str(k).strip().lower(): (v or {}) for k, v in data.items()}
    except Exception:
        _PROFILE_CACHE = {}
    return _PROFILE_CACHE


def _field_key(field_name: str) -> str:
    k = (field_name or "").strip().lower()
    return _FIELD_ALIASES.get(k, k)


def snap_value_to_canonical(field_name: str, raw_value: str) -> Tuple[str, float, Optional[str]]:
    """
    Snap a single noisy value to canonical for field_name.

    Returns:
        (snapped_value_raw, score, best_canonical_raw_or_None)
    """
    if not raw_value:
        return raw_value, 0.0, None

    fk = _field_key(field_name)
    canon_list = CANONICAL_BRAIN.get(fk, [])
    if not canon_list:
        # unknown field -> leave as-is
        return raw_value, 0.0, None

    # ✅ If OCR value exactly matches a canonical option, keep it as-is
    rv = str(raw_value)
    for can in canon_list:
        if rv.strip() == str(can).strip():
            return str(can), 1.0, str(can)

    # score noisy value against canonicals using public mapping helper
    mapped = map_visible_to_canonicals(fk, [raw_value])
    if not mapped:
        return raw_value, 0.0, None

    best = mapped[0]
    best_can = best.get("best_canonical_raw")
    score = float(best.get("score", 0.0))

    # threshold: prefer tuned profile if present
    prof = _load_profile().get(fk, {})
    min_ok = float(prof.get("min_score_ok", _DEFAULT_SNAP_SCORE))

    # If already confident, return immediately (so recovery rules never touch correct values)
    if best_can and score >= min_ok:
        return best_can, score, best_can

    # ------------------------------------------------------------
    # CONFUSION-ONLY recovery (runs ONLY when score < min_ok)
    # Works for: Cast/Sub Cast + State + District
    # ------------------------------------------------------------
    RECOVERY_FIELDS = ("cast", "sub cast", "state", "district")

    if best_can and fk in RECOVERY_FIELDS:
        from difflib import SequenceMatcher

        raw_norm = normalize_text(raw_value)
        can_norm = normalize_text(best_can)

        # get 2nd best score to detect ambiguity
        second_score = 0.0
        if isinstance(mapped, list) and len(mapped) > 1:
            try:
                second_score = float(mapped[1].get("score", 0.0))
            except Exception:
                second_score = 0.0

        dominance = score - second_score  # how clearly best beats runner-up

        if raw_norm and can_norm and len(raw_norm) >= 5:
            diff_len = len(can_norm) - len(raw_norm)

            # Case A: Missing 1–2 chars at start/end (e.g., "houdhary" -> "choudhary")
            # Very safe: containment + best is meaningfully better than 2nd best
            if 1 <= abs(diff_len) <= 2 and dominance >= 0.08:
                if can_norm.endswith(raw_norm) or can_norm.startswith(raw_norm):
                    return best_can, max(score, 0.95), best_can

            # Case B: High character similarity even if token logic failed
            if len(raw_norm) >= 6 and dominance >= 0.08:
                r = SequenceMatcher(None, raw_norm, can_norm).ratio()
                if r >= 0.87:
                    return best_can, max(score, 0.90), best_can

            # Case C: Truncation by 3–5 chars (e.g., "chouhay" -> "choudhary")
            # Conservative: strong prefix + clear dominance + moderate similarity
            if 3 <= diff_len <= 5 and len(raw_norm) >= 6 and dominance >= 0.12:
                if can_norm.startswith(raw_norm[:4]):
                    r = SequenceMatcher(None, raw_norm, can_norm).ratio()
                    if r >= 0.78:
                        return best_can, max(score, 0.85), best_can
    # ------------------------------------------------------------

    # ---- Education short-abbrev guard (isolated) ----
    if fk in ("education", "qualification"):
        try:
            from education_normalizer_guard import snap_education_short
            snapped, s2, best2 = snap_education_short(raw_value, min_ok=0.70)
            if best2 and snapped != raw_value:
                return snapped, s2, best2
        except Exception:
            pass
    # -----------------------------------------------

    return raw_value, score, best_can




def normalize_info_panel_targets(mapped_kv: Dict[str, Any],
                                 only_dropdown_fields: bool = True) -> Dict[str, Any]:
    """
    Normalize *all* info-panel mapped values.

    Args:
        mapped_kv: dict from fuzzy_map_kv(), e.g. {"Pada": "z1st Pada", ...}
        only_dropdown_fields:
            True  -> snap only fields that exist in canonical brain
            False -> attempt snap for any field (safe but unnecessary)

    Returns:
        new dict with snapped values where confident.
    """
    if not isinstance(mapped_kv, dict):
        return mapped_kv

    out = dict(mapped_kv)

    for field, val in list(out.items()):
        if val is None:
            continue

        fk = _field_key(field)
        if only_dropdown_fields and fk not in CANONICAL_BRAIN:
            continue

        snapped, score, _ = snap_value_to_canonical(field, str(val))

        # keep original capitalization if snapped matches canon already
        out[field] = snapped

    return out


# Quick manual test:
if __name__ == "__main__":
    sample = {
        "Pada": "z1st Pada",
        "Diet": "Non Veg",
        "District": "Ambela",   # OCR typo
        "Education": "Bsc",     # alias to education list
    }
    print(normalize_info_panel_targets(sample))

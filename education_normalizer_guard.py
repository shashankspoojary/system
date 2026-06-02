# education_normalizer_guard.py
"""
Education-only normalization guard for short abbreviations.
Runs AFTER normal snap, only if Education target is still noisy.

Goal:
- Fix cases like "BC]" / "8CJ" / "BCI" -> "BCJ"
- Without touching other fields.
"""

from __future__ import annotations
from difflib import SequenceMatcher
from typing import Optional, Tuple

try:
    from education_data import EDUCATION_OPTIONS
except Exception:
    EDUCATION_OPTIONS = {"options": []}

from reasoning_core import normalize_text

# extra folds that matter most for short education codes
_EXTRA_FOLDS = str.maketrans({
    "8": "B",
    "I": "J",
    "J": "I",
    "C": "G",
    "G": "C",
    "0": "O",
    "O": "0",
    "H": "E",
    "E": "H",
    "1": "L",
    "5": "S",
    "S": "5",
    "T": "F",
    "F": "T",
    "|": "I",
    "Z": "2",
    "2": "Z",
    "6": "G",
    "]": "J",
    "1": "I",
    "$": "S",
    "1": "I",
    "I": "1"

})

# A small, deterministic list of replacements tried in order (applied to the normalized text).
_ORDERED_REPLACEMENTS = [
    # common OCR noise removal
    (r'[^A-Z0-9/ \-()]', ''),   # remove non-alphanum except a few allowed
    (r'^\W+', ''),              # strip leading punctuation
    (r'\W+$', ''),              # strip trailing punctuation
    # specific messy patterns
    (r'^(?:I|l|1){2,}$', lambda m: m.group(0).replace('l', 'I').replace('1', 'I')),  # normalize II-like to "II"
]

def _variants(norm: str):
    """Generate deterministic OCR-noise variants (small set)."""
    outs = {norm}
    # 1) translated variant
    try:
        outs.add(norm.translate(_EXTRA_FOLDS))
    except Exception:
        pass

    # 2) strip a single leading garbage char (if first char is not alnum)
    if len(norm) >= 2 and not norm[0].isalnum():
        outs.add(norm[1:])

    # 3) simple collapse of repeated non-alphanum
    outs.add(''.join(ch for ch in norm if ch.isalnum() or ch in '/-()'))

    return list(dict.fromkeys(outs))  # preserve insertion order, dedupe

def _apply_ordered_replacements(s: str) -> str:
    import re
    out = s
    for pat, repl in _ORDERED_REPLACEMENTS:
        if callable(repl):
            out = re.sub(pat, repl, out)
        else:
            out = re.sub(pat, repl, out)
    return out

def snap_education_short(raw_value: str, min_ok: float = 0.70) -> Tuple[str, float, Optional[str]]:
    """
    Try to snap short Education abbreviations to canonicals.
    Returns (snapped_raw, score, best_raw_or_None)
    """
    if not raw_value:
        return raw_value, 0.0, None

    canonicals = EDUCATION_OPTIONS.get("options", []) or []
    if not canonicals:
        return raw_value, 0.0, None

    raw_norm = (normalize_text(raw_value) or "")
    raw_norm_u = raw_norm.upper()

    _MANUAL_SHORT_OVERRIDES = {
        # only map noisy reads to canonical short forms (one-way)
        "U": "II",
        "8CJ": "BCJ",
        "IBA": "B.A",

        # FIX: PaddleOCR sometimes reads EDCIL as EDCII (L -> I)
        "EDCII": "EDCIL",
        # add more only as needed
    }

    candidate_override = _MANUAL_SHORT_OVERRIDES.get(raw_norm_u)
    if candidate_override and candidate_override in canonicals:
        return candidate_override, 1.0, candidate_override

    if not raw_norm_u:
        return raw_value, 0.0, None

    # Pre-normalize by applying ordered replacements (strip punctuation, etc.)
    raw_norm_u = _apply_ordered_replacements(raw_norm_u)

    # Special-case: if raw_norm is exactly a canonical (case-insensitive), accept it
    for can in canonicals:
        if normalize_text(can).upper() == raw_norm_u:
            return can, 1.0, can

    # Only attempt this guard for short abbreviations (<= 6 chars)
    if len(raw_norm_u) > 6:
        return raw_value, 0.0, None

    best_raw = None
    best_score = 0.0

    # Try deterministic variants first (translate, clean, strip garbage)
    for v in _variants(raw_norm_u):
        v = v.strip()
        if not v:
            continue
        for can in canonicals:
            can_norm = normalize_text(can).upper()
            # cheap equality check first
            if v == can_norm:
                return can, 1.0, can
            # fallback to SequenceMatcher only if difference is short
            from difflib import SequenceMatcher
            s = SequenceMatcher(None, v, can_norm).ratio()
            if s > best_score:
                best_score = s
                best_raw = can

    # Slightly relax threshold for very short tokens (2-3 chars) to catch OCR noise
    if best_raw and best_score >= (min_ok if len(raw_norm_u) > 3 else max(0.60, min_ok - 0.1)):
        return best_raw, best_score, best_raw

    return raw_value, best_score, best_raw
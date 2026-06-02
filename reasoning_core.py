"""
reasoning_core.py

Core reasoning / normalization engine for MPF dropdown selection.

This module is *pure logic*:
- It does NOT know about screenshots, OCR regions, mouse, or keyboard.
- It just matches a target value + a list of visible OCR strings
  against canonical dropdown datasets (dropdown_data, cast_data, education_data, subcast_data).

Public main entry:
    pick_for_target(field_name: str, target_value: str, visible_texts: list[str]) -> dict
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Any, Tuple

# --- Import canonical datasets -------------------------------------------------

try:
    from dropdown_data import DROPDOWN_OPTIONS
except ImportError:
    DROPDOWN_OPTIONS = {}

try:
    from cast_data import CAST_OPTIONS
except ImportError:
    CAST_OPTIONS = {}

try:
    from subcast_data import SUBCAST_OPTIONS
except ImportError:
    SUBCAST_OPTIONS = {}

try:
    from education_data import EDUCATION_OPTIONS
except ImportError:
    EDUCATION_OPTIONS = {}

import json
import os

REASONING_PROFILE_FILE = "reasoning_profile.json"
_PROFILE_CACHE: Dict[str, Any] = None


def _load_reasoning_profile() -> Dict[str, Any]:
    global _PROFILE_CACHE
    if _PROFILE_CACHE is not None:
        return _PROFILE_CACHE
    try:
        with open(REASONING_PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # normalize keys to lowercase once
        lowered = {}
        for k, v in data.items():
            lowered[(k or "").strip().lower()] = v or {}
        _PROFILE_CACHE = lowered
    except Exception:
        _PROFILE_CACHE = {}
    return _PROFILE_CACHE

# --- Normalization helpers -----------------------------------------------------

_norm_space_re = re.compile(r"\s+")
_norm_punct_re = re.compile(r"[^a-z0-9\s/\.]")


def normalize_text(s: str, *, keep_trailing_dots: bool = False) -> str:
    """
    Basic normalization:
    - Unicode normalize
    - lowercase
    - replace '&' with 'and'
    - strip non-alphanumeric (except space, slash, dot)
    - normalize spaces around slash
    - (optionally) keep trailing dots (Education needs this: "BVSc." != "BVSc")
    - collapse multiple spaces
    """
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.lower().strip()

    # "&" -> "and" (for things like Andaman & Nicobar)
    s = s.replace("&", " and ")

    # remove weird punctuation but keep / and .
    s = _norm_punct_re.sub(" ", s)

    # 🔹 normalize " / " -> "/" (remove spaces around slash)
    s = re.sub(r"\s*/\s*", "/", s)

    # 🔹 remove trailing dots like "hastham." -> "hastham"
    # IMPORTANT: Education must keep "BVSc." distinct from "BVSc"
    if not keep_trailing_dots:
        s = re.sub(r"\.+$", "", s)

    # collapse spaces
    s = _norm_space_re.sub(" ", s).strip()
    return s


def tokenize(s: str, *, keep_trailing_dots: bool = False) -> List[str]:
    s_norm = normalize_text(s, keep_trailing_dots=keep_trailing_dots)
    if not s_norm:
        return []
    return s_norm.split(" ")



# --- Height helpers (special field) --------------------------------------------

_height_inch_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*in\b", re.IGNORECASE)


def extract_inches(s: str) -> Optional[float]:
    if not s:
        return None
    m = _height_inch_pattern.search(s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# --- Canonical brain building --------------------------------------------------

def _build_canonical_entry(
    raw: str,
    is_height: bool = False,
    keep_trailing_dots: bool = False
) -> Dict[str, Any]:
    norm = normalize_text(raw, keep_trailing_dots=keep_trailing_dots)
    tokens = tokenize(raw, keep_trailing_dots=keep_trailing_dots)
    entry = {
        "raw": raw,
        "norm": norm,
        "tokens": tokens,
    }
    if is_height:
        entry["inches"] = extract_inches(raw)
    return entry



def _build_brain() -> Dict[str, List[Dict[str, Any]]]:
    """
    Build master canonical list per normalized field name.
    Keys are lowercase field names.
    """
    brain: Dict[str, List[Dict[str, Any]]] = {}

    # 1) All regular dropdowns from dropdown_data.py
    for key, spec in DROPDOWN_OPTIONS.items():
        options = (spec or {}).get("options") or []
        is_height = key.strip().lower() == "height"
        entries = [_build_canonical_entry(opt, is_height=is_height) for opt in options]
        brain[key.strip().lower()] = entries

    # 2) Cast / Sub Cast / Education style fields
    cast_entries = [_build_canonical_entry(o) for o in CAST_OPTIONS.get("options", [])]
    subcast_entries = [_build_canonical_entry(o) for o in SUBCAST_OPTIONS.get("options", [])]
    edu_entries = [_build_canonical_entry(o, keep_trailing_dots=True) for o in EDUCATION_OPTIONS.get("options", [])]

    # Many fields may point to same dataset
    if cast_entries:
        brain["cast"] = cast_entries
    if subcast_entries:
        brain["sub cast"] = subcast_entries
        brain["subcast"] = subcast_entries
    if edu_entries:
        brain["education"] = edu_entries
        brain["qualification"] = edu_entries

    return brain


CANONICAL_BRAIN: Dict[str, List[Dict[str, Any]]] = _build_brain()


# --- Similarity scoring --------------------------------------------------------

# Common OCR confusions, mapped to a canonical form
_OCR_CHAR_FOLDS = {
    "0": "o",   # 0 <-> o
    "1": "l",   # 1 <-> l / i
    "5": "s",   # 5 <-> s
    "8": "b",   # 8 <-> b
}

_OCR_PAIR_PATTERNS = [
    # "rn" often read as "m" or vice versa
    (re.compile(r"rn"), "m"),
    (re.compile(r"m"), "rn"),
    # "cl" <-> "d"
    (re.compile(r"cl"), "d"),
    (re.compile(r"d"), "cl"),
]


def _fold_ocr_noise(s: str) -> str:
    if not s:
        return s
    # character-level folds
    chars = []
    for ch in s:
        chars.append(_OCR_CHAR_FOLDS.get(ch, ch))
    out = "".join(chars)
    # pair-level folds (very lightweight)
    for pat, repl in _OCR_PAIR_PATTERNS:
        out = pat.sub(repl, out)
    return out


def _char_similarity(a_norm: str, b_norm: str) -> float:
    """
    Character similarity with OCR-noise awareness.

    - First apply normalization (already done before calling this)
    - Then fold typical OCR confusions (0/o, 1/l, rn/m, cl/d, ...)
    - Finally compute SequenceMatcher ratio.
    """
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0

    a_fold = _fold_ocr_noise(a_norm)
    b_fold = _fold_ocr_noise(b_norm)

    return SequenceMatcher(None, a_fold, b_fold).ratio()



def _token_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return inter / union


def _combined_score(ocr_norm: str,
                    ocr_tokens: List[str],
                    canonical: Dict[str, Any],
                    is_height: bool = False) -> float:
    """
    Weighted combination of:
    - character similarity
    - token overlap
    - (for height) inches closeness
    """
    base_char = _char_similarity(ocr_norm, canonical.get("norm", ""))
    base_tok = _token_similarity(ocr_tokens, canonical.get("tokens", []))
    score = 0.7 * base_char + 0.3 * base_tok

    if is_height:
        want_in = extract_inches(ocr_norm)
        can_in = canonical.get("inches")
        if want_in is not None and can_in is not None:
            diff = abs(want_in - can_in)
            # Map diff (0 -> 1.0, 4 inches -> 0 or less)
            inches_bonus = max(0.0, 1.0 - (diff / 4.0))
            # weight inches heavily for height fields
            score = 0.2 * score + 0.8 * inches_bonus

    return score


# --- Mapping visible options to canonical -------------------------------------

def map_visible_to_canonicals(field_name: str,
                              visible_texts: List[str]) -> List[Dict[str, Any]]:
    """
    For each visible OCR text:
        - normalize
        - compare against all canonical options for that field
        - pick best canonical + score

    Returns a list of dicts (one per visible entry):
        {
          "visible_raw": "...",
          "visible_norm": "...",
          "best_canonical_raw": "...",
          "best_canonical_norm": "...",
          "score": 0.0-1.0,
        }
    """
    field_key = (field_name or "").strip().lower()
    canon_list = CANONICAL_BRAIN.get(field_key, [])
    is_height = field_key == "height"

    results: List[Dict[str, Any]] = []

    if not canon_list:
        # No canonical data found for this field
        for txt in visible_texts:
            keep_dots = field_key in ("education", "qualification")
            txt_norm = normalize_text(txt, keep_trailing_dots=keep_dots)
            results.append({
                "visible_raw": txt,
                "visible_norm": txt_norm,
                "best_canonical_raw": None,
                "best_canonical_norm": None,
                "score": 0.0,
            })
        return results

    for txt in visible_texts:
        keep_dots = field_key in ("education", "qualification")
        txt_norm = normalize_text(txt, keep_trailing_dots=keep_dots)
        txt_tokens = tokenize(txt, keep_trailing_dots=keep_dots)


        best_score = -1.0
        best_canonical = None

        if not txt_norm:
            # empty / garbage line
            results.append({
                "visible_raw": txt,
                "visible_norm": txt_norm,
                "best_canonical_raw": None,
                "best_canonical_norm": None,
                "score": 0.0,
            })
            continue

        for can in canon_list:
            sc = _combined_score(txt_norm, txt_tokens, can, is_height=is_height)
            if sc > best_score:
                best_score = sc
                best_canonical = can

        if best_canonical is None:
            results.append({
                "visible_raw": txt,
                "visible_norm": txt_norm,
                "best_canonical_raw": None,
                "best_canonical_norm": None,
                "score": 0.0,
            })
        else:
            results.append({
                "visible_raw": txt,
                "visible_norm": txt_norm,
                "best_canonical_raw": best_canonical["raw"],
                "best_canonical_norm": best_canonical["norm"],
                "score": float(best_score),
            })

    return results
def _snap_target_to_canonical(field_key: str,
                              target_value: str,
                              canon_list: List[Dict[str, Any]],
                              min_snap_score: float = 0.82) -> Tuple[str, str]:
    """
    Take any noisy target_value for a dropdown field and, if it is clearly close
    to one of the canonical options, snap it to that canonical.

    Returns:
        (new_target_value_raw, new_target_norm)
    """
    # No data or empty target -> nothing to do
    if not target_value or not canon_list:
        keep_dots = field_key in ("education", "qualification")
        return target_value, normalize_text(target_value, keep_trailing_dots=keep_dots)


    keep_dots = field_key in ("education", "qualification")
    t_norm = normalize_text(target_value, keep_trailing_dots=keep_dots)

    if not t_norm:
        return target_value, t_norm

    t_tokens = tokenize(target_value, keep_trailing_dots=keep_dots)

    is_height = (field_key == "height")

    best_can = None
    best_score = -1.0

    for can in canon_list:
        sc = _combined_score(t_norm, t_tokens, can, is_height=is_height)
        if sc > best_score:
            best_score = sc
            best_can = can

    # Only snap if we are *clearly* confident
    if best_can is not None and best_score >= min_snap_score:
        # Use the canonical raw + norm
        return best_can["raw"], best_can["norm"]

    # Otherwise keep original
    return target_value, t_norm


# --- Pick the best visible option for a given target --------------------------

def pick_for_target(field_name: str,
                    target_value: str,
                    visible_texts: List[str],
                    min_score_ok: float = 0.55,
                    ambiguity_margin: float = 0.04) -> Dict[str, Any]:
    """
    Core reasoning:

    1. Normalize/snap target into canonical form (we assume it's one of the canonical options).
    2. Map each visible OCR text -> best canonical + score.
    3. Keep only visible entries whose best_canonical_norm equals target_norm.
    4. If exactly one strong candidate -> OK.
       If multiple candidates but one is clearly best -> OK.
       If none or too ambiguous -> no_match / ambiguous.

    Returns:
        {
          "status": "ok" | "no_match" | "ambiguous" | "no_canonical",
          "selected_index": int or None,   # index into visible_texts
          "selected_visible": str or None,
          "canonical": str or None,
          "confidence": float,
          "candidates": [ . same structure as map_visible_to_canonicals . ]
        }
    """
    field_key = (field_name or "").strip().lower()
    canon_list = CANONICAL_BRAIN.get(field_key, [])

    # 🔹 NEW: snap noisy target like "z1st Pada" → nearest canonical for ANY field
    target_value, target_norm = _snap_target_to_canonical(
        field_key,
        target_value,
        canon_list,
    )

    # --- Per-field tuning overrides via reasoning_profile.json ---
    profile = _load_reasoning_profile().get(field_key, {})
    if "min_score_ok" in profile:
        try:
            min_score_ok = float(profile["min_score_ok"])
        except Exception:
            pass
    if "ambiguity_margin" in profile:
        try:
            ambiguity_margin = float(profile["ambiguity_margin"])
        except Exception:
            pass

    if not canon_list:
        # No canonical data for this field (fallback to simple equality)
        return {
            "status": "no_canonical",
            "selected_index": None,
            "selected_visible": None,
            "canonical": None,
            "confidence": 0.0,
            "candidates": [],
        }

    # Compute mapping
    mapped = map_visible_to_canonicals(field_name, visible_texts)

    # Filter entries that map to the same canonical as target
    candidates: List[Dict[str, Any]] = []
    for idx, entry in enumerate(mapped):
        if not entry.get("best_canonical_norm"):
            continue
        if entry["best_canonical_norm"] != target_norm:
            continue
        if entry["score"] < min_score_ok:
            continue
        e = dict(entry)
        e["index"] = idx   # index in visible_texts
        candidates.append(e)

    if not candidates:
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": mapped,
        }

    # Sort by score descending
    candidates.sort(key=lambda e: e["score"], reverse=True)
    best = candidates[0]
    if len(candidates) == 1:
        return {
            "status": "ok",
            "selected_index": best["index"],
            "selected_visible": best["visible_raw"],
            "canonical": best["best_canonical_raw"],
            "confidence": float(best["score"]),
            "candidates": mapped,
        }

    # Compare best vs second best
    second = candidates[1]
    if (best["score"] - second["score"]) < ambiguity_margin:
        return {
            "status": "ambiguous",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": float(best["score"]),
            "candidates": mapped,
        }

    return {
        "status": "ok",
        "selected_index": best["index"],
        "selected_visible": best["visible_raw"],
        "canonical": best["best_canonical_raw"],
        "confidence": float(best["score"]),
        "candidates": mapped,
    }


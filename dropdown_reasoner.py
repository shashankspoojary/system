"""
dropdown_reasoner.py

Dropdown-specific reasoning façade for MPF_BOT_V7.3.

This module connects:
    - reasoning_core.pick_for_target(...)
    - OCR line structures from MPF_BOT (list of dicts with 'text', 'left', 'top', etc.)

It does NOT perform mouse clicks. It only decides:
    "Which visible OCR line should be clicked for this field + target?"
"""

from __future__ import annotations
from typing import List, Dict, Any,Tuple

from reasoning_core import pick_for_target, normalize_text
try:
    from prediction_layer import predict_with_indices
except ImportError:  # prediction layer is optional
    predict_with_indices = None

try:
    from dropdown_data import DROPDOWN_OPTIONS
except ImportError:
    DROPDOWN_OPTIONS = {}


# --- Debug logger for reasoning ----------------------------------------------

import os
from datetime import datetime



# --- Debug logger disabled (no files are written) ----------------------------

def _log_reasoning(*_args, **_kwargs) -> None:
    return



# --- Field-level reasoning rules ----------------------------------------------

from dropdown_data import DROPDOWN_OPTIONS

def _norm_field_name(name: str) -> str:
    return (name or "").strip().lower()


def _is_non_scrollable(field_name: str) -> bool:
    """
    Heuristic: if the number of options is <= the configured 'visible' count,
    then the dropdown effectively shows everything at once (no vertical scroll).

    This works for *all* dropdowns defined in DROPDOWN_OPTIONS, regardless of
    whether they are 'special' or not.
    """
    fn = _norm_field_name(field_name)

    # Find matching config in DROPDOWN_OPTIONS (case / spacing tolerant)
    for key, cfg in DROPDOWN_OPTIONS.items():
        if _norm_field_name(key) == fn:
            options = cfg.get("options") or []
            visible = cfg.get("visible") or len(options)
            return len(options) <= visible

    # If we don't know, it's safer to assume "scrollable"
    return False




def should_activate_reasoning(field_name: str, phase: str) -> bool:
    """
    Decide if reasoning should run now.

    Args:
        field_name: Display name from bot_memory, e.g. "State", "Diet", "Height".
        phase: One of:
            - "open":    immediately after dropdown is opened
            - "precise": when bot has switched to precise mode (slow scroll, OCR)

    New rules (your requirement):

        - For *non-scrollable* dropdowns:
              → reasoning runs in the OPEN phase (first OCR snapshot),
                and there is no need to run it again in precise mode.

        - For *scrollable* dropdowns:
              → reasoning runs in PRECISE mode only (while slowly scrolling),
                not in the open phase.

    This is completely generic and applies to every dropdown that the bot fills.
    """

    fn = _norm_field_name(field_name)
    non_scrollable = _is_non_scrollable(fn)

    phase = (phase or "").strip().lower()
    if phase == "open":
        # Non-scrollable: use reasoning immediately when dropdown opens.
        # Scrollable: do NOT run here, we wait until precise mode.
        return non_scrollable

    if phase == "precise":
        # Scrollable: reasoning *only* in precise mode.
        # Non-scrollable: no need to run again.
        return not non_scrollable

    # Unknown phase: be conservative and do nothing.
    return False



# --- OCR lines helper ---------------------------------------------------------

def _lines_to_visible_texts(
    ocr_lines: List[Dict[str, Any]],
    field_name: str = ""
) -> Tuple[List[str], List[int]]:
    """
    Convert raw OCR line dicts into:
        - visible_texts: list of unique (normalized) texts for reasoning_core
        - indices:       mapping back into original ocr_lines

    We deduplicate by reasoning_core.normalize_text() so that multiple engines
    or multiple passes that see the *same* logical row do NOT create
    artificial ambiguity.
    """
    visible_texts: List[str] = []
    indices: List[int] = []
    seen_norm = set()

    for idx, ln in enumerate(ocr_lines):
        txt = (ln.get("text") or "").strip()
        if not txt:
            continue

        # Use the same normalization as reasoning_core
        field_key = (field_name or "").strip().lower()
        keep_dots = field_key in ("education", "qualification")
        txt_norm = normalize_text(txt, keep_trailing_dots=keep_dots)

        if not txt_norm:
            continue

        # Skip duplicates of the same logical text (even if spacing/punct differ)
        if txt_norm in seen_norm:
            continue
        seen_norm.add(txt_norm)

        visible_texts.append(txt)
        indices.append(idx)

    return visible_texts, indices



# --- Main reasoning façade -----------------------------------------------------

def reason_over_dropdown_page(field_name: str,
                              target_value: str,
                              ocr_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Joint (ensemble) dropdown reasoning.

    Runs reasoning_core AND prediction_layer side-by-side every time,
    then fuses results to reduce wrong "ok" picks.

    Returns dict with keys compatible with existing bot:
      status: "ok" | "no_match" | "ambiguous"
      line_index, line_dict, visible_text, canonical, confidence, raw_core
    """

    visible_texts, indices = _lines_to_visible_texts(ocr_lines, field_name)


    if not visible_texts:
        return {
            "status": "no_match",
            "line_index": None,
            "line_dict": None,
            "visible_text": None,
            "canonical": None,
            "confidence": 0.0,
            "raw_core": None,
        }

    # ---------------- 1) Run BOTH brains ----------------
    core_result = pick_for_target(field_name, target_value, visible_texts)

    pred_result = None
    if predict_with_indices is not None:
        try:
            pred_result = predict_with_indices(
                field_name, target_value, visible_texts, core_result
            )
        except Exception as e:
            print(f"[PREDICTION-LAYER ERROR] {e}")

    # Log both traces for debugging
    _log_reasoning(field_name, target_value, visible_texts, core_result, phase="core")
    if pred_result is not None:
        _log_reasoning(field_name, target_value, visible_texts, pred_result, phase="prediction")

    # Helper: convert core/pred into a click-pick
    def _to_pick(res: Dict[str, Any] | None):
        if not res or res.get("status") != "ok":
            return None
        si = res.get("selected_index")
        if si is None or si < 0 or si >= len(indices):
            return None

        line_index = indices[si]
        line_dict = ocr_lines[line_index]
        visible_text = (line_dict.get("text") or "").strip()

        return {
            "line_index": line_index,
            "line_dict": line_dict,
            "visible_text": visible_text,
            "canonical": res.get("canonical"),
            "confidence": float(res.get("confidence", 0.0)),
            "raw_core": res,
        }

    core_pick = _to_pick(core_result)
    pred_pick = _to_pick(pred_result)

    # ---------------- 2) Agreement = strongest signal ----------------
    if core_pick and pred_pick:
        if core_pick["line_index"] == pred_pick["line_index"]:
            return {"status": "ok", **core_pick}

        # ---------------- 3) Conflict resolution ----------------
        c_conf = core_pick["confidence"]
        p_conf = pred_pick["confidence"]

        # minimum "win" gap to avoid close-call misclicks
        margin = 0.06

        if c_conf >= p_conf + margin:
            return {"status": "ok", **core_pick}
        if p_conf >= c_conf + margin:
            return {"status": "ok", **pred_pick}

        # Too close -> ambiguous, let caller re-check / micro-verify
        best = core_pick if c_conf >= p_conf else pred_pick
        best["status"] = "ambiguous"
        best["raw_core"] = {"core": core_result, "pred": pred_result}
        return best

    # ---------------- 4) Only one brain found a match ----------------
    if core_pick:
        return {"status": "ok", **core_pick}
    if pred_pick:
        return {"status": "ok", **pred_pick}

    # ---------------- 5) Neither found anything ----------------
    return {
        "status": core_result.get("status", "no_match"),
        "line_index": None,
        "line_dict": None,
        "visible_text": None,
        "canonical": core_result.get("canonical"),
        "confidence": float(core_result.get("confidence", 0.0)),
        "raw_core": {"core": core_result, "pred": pred_result},
    }



def choose_visible_option(field_name: str,
                          target_value: str,
                          ocr_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Public wrapper used by MPF_BOT.

    Now includes ambiguous micro-verify:
    - If reason_over_dropdown_page returns "ambiguous",
      we test BOTH core & prediction candidates against the target
      and return a safe "ok" only when verified.
    """

    reason = reason_over_dropdown_page(field_name, target_value, ocr_lines)

    # Normal case
    if not reason or reason.get("status") == "ok":
        return reason

    # ---------- Ambiguous micro-verify ----------
    if reason.get("status") == "ambiguous":
        raw = reason.get("raw_core", {})
        core_res = raw.get("core")
        pred_res = raw.get("pred")

        visible_texts, indices = _lines_to_visible_texts(ocr_lines, field_name)
        if not visible_texts:
            return {"status": "no_match"}

        field_key = (field_name or "").strip().lower()
        keep_dots = field_key in ("education", "qualification")

        norm_target = normalize_text(target_value, keep_trailing_dots=keep_dots)

        candidates = []

        if core_res and core_res.get("status") == "ok":
            si = core_res.get("selected_index")
            if si is not None:
                candidates.append(("core", si, float(core_res.get("confidence", 0.0))))

        if pred_res and pred_res.get("status") == "ok":
            si = pred_res.get("selected_index")
            if si is not None:
                candidates.append(("pred", si, float(pred_res.get("confidence", 0.0))))

        if not candidates:
            return {"status": "no_match"}

        # Higher confidence first
        candidates.sort(key=lambda x: x[2], reverse=True)

        import difflib

        for tag, si, conf in candidates:
            if si < 0 or si >= len(indices):
                continue

            line_index = indices[si]
            line_dict = ocr_lines[line_index]
            visible = (line_dict.get("text") or "").strip()
            norm_visible = normalize_text(visible, keep_trailing_dots=keep_dots)

            score = difflib.SequenceMatcher(None, norm_visible, norm_target).ratio() * 100

            # strict micro-verify threshold
            if score >= 90:
                return {
                    "status": "ok",
                    "line_index": line_index,
                    "line_dict": line_dict,
                    "visible_text": visible,
                    "canonical": norm_target,
                    "confidence": conf,
                    "raw_core": raw,
                }

        # both candidates failed verification → keep scrolling
        return {"status": "no_match"}

    # Any other non-ok status → pass through
    return reason


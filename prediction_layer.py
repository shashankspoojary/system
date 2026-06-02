# prediction_layer.py
"""
prediction_layer.py

Prediction Reasoning Layer built on top of reasoning_core.

This module does NOT replace the existing reasoning_core logic.
Instead, it activates *only* when pick_for_target(...) fails to find a
high-confidence match ("no_match", "ambiguous", etc.).

It uses:
    - Canonical list order (indices) for each field.
    - Visible OCR mappings (score + best canonical).
    - Index-based prediction using neighbour anchors.
    - Optional field-level priors from prediction_memory.
"""

from __future__ import annotations

from typing import List, Dict, Any
from collections import Counter

from reasoning_core import (
    CANONICAL_BRAIN,
    normalize_text,
    map_visible_to_canonicals,
)

from prediction_memory import get_prior


# --- Tuning constants (can be tweaked if needed) --------------------------------

ANCHOR_THRESHOLD = 0.75          # similarity >= this to be considered an anchor
MAX_CANONICAL_DISTANCE = 8       # max distance in canonical indices to trust as neighbour
INDEX_PREDICTION_BONUS = 0.5     # bonus added if index is predicted position
PRIOR_WEIGHT = 0.05              # multiplier for field prior (0..1) → max +0.05
PREDICTIVE_THRESHOLD = 0.75      # minimum final_score to accept prediction
AMBIGUITY_MARGIN_PRED = 0.05     # require at least this gap over second-best


def _field_key(field_name: str) -> str:
    return (field_name or "").strip().lower()


def predict_with_indices(
    field_name: str,
    target_value: str,
    visible_texts: List[str],
    core_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Try to salvage a selection when normal reasoning_core.pick_for_target(...)
    was not confident enough.

    Args:
        field_name:  e.g. "District", "State", "Diet", "Height"
        target_value: canonical value we want to select
        visible_texts: list of OCR strings visible in the current dropdown view
        core_result:  raw dict returned by pick_for_target(...), or None

    Returns:
        A pick_for_target-like dict:
            {
              "status": "ok" | "no_match" | "ambiguous",
              "selected_index": int | None,
              "selected_visible": str | None,
              "canonical": str | None,
              "confidence": float,
              "candidates": [ ... extended mapping info ... ],
            }
    """
    # Basic sanity
    if not visible_texts or not target_value:
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": [],
        }

    field_key = _field_key(field_name)
    keep_dots = field_key in ("education", "qualification")
    target_norm = normalize_text(target_value, keep_trailing_dots=keep_dots)

    canon_list = CANONICAL_BRAIN.get(field_key, [])

    # If we don't know canonical options for this field, nothing to do.
    if not canon_list or not target_norm:
        return {
            "status": "no_canonical",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": [],
        }

    # Find canonical index of the target in this field
    target_idx = None
    for i, c in enumerate(canon_list):
        if c.get("norm") == target_norm:
            target_idx = i
            break

    if target_idx is None:
        # Target is NOT part of this field's canonical list
        return {
            "status": "no_canonical",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": [],
        }

    # Map visible OCR texts to best canonical entries + scores
    mapped = map_visible_to_canonicals(field_name, visible_texts)

    # Build a fast lookup: canonical_norm -> canonical_index
    canon_index_by_norm = {
        c.get("norm"): idx for idx, c in enumerate(canon_list)
    }

    # --- 1) Find anchors ---------------------------------------------------------

    anchors: List[Dict[str, Any]] = []
    for vis_idx, entry in enumerate(mapped):
        score = float(entry.get("score", 0.0))
        can_norm = entry.get("best_canonical_norm")
        if not can_norm:
            continue
        if score < ANCHOR_THRESHOLD:
            continue

        canon_idx = canon_index_by_norm.get(can_norm)
        if canon_idx is None:
            continue

        anchors.append(
            {
                "visible_index": vis_idx,
                "canonical_index": canon_idx,
                "score": score,
            }
        )

    # If we have zero anchors, we can't do index prediction.
    if not anchors:
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": mapped,
        }

    # --- 2) Predict visible indices using canonical index deltas -----------------

    predicted_indices: List[int] = []
    for a in anchors:
        delta = target_idx - a["canonical_index"]
        if abs(delta) > MAX_CANONICAL_DISTANCE:
            continue
        vis_pred = a["visible_index"] + delta
        if 0 <= vis_pred < len(visible_texts):
            predicted_indices.append(vis_pred)

    if not predicted_indices:
        # Anchors exist but too far from target → no reliable prediction
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": mapped,
        }

    counts = Counter(predicted_indices)
    predicted_index_set = set(predicted_indices)
    # strongest_index, votes = counts.most_common(1)[0]  # available for debugging

    # --- 3) Combine similarity, index prediction, and history --------------------

    prior_prob = get_prior(field_name, target_value)
    prior_bonus = PRIOR_WEIGHT * max(0.0, min(1.0, prior_prob))

    candidates: List[Dict[str, Any]] = []
    for vis_idx, entry in enumerate(mapped):
        score = float(entry.get("score", 0.0))
        can_norm = entry.get("best_canonical_norm")

        # We only consider:
        #   - entries already mapped to the *target* canonical, OR
        #   - entries that sit on a predicted index
        if can_norm != target_norm and vis_idx not in predicted_index_set:
            continue

        # Base similarity:
        #   - if mapped to target → use score as-is
        #   - if only predicted by index (not mapped to target) → treat base similarity as 0
        base_sim = score if can_norm == target_norm else 0.0

        idx_bonus = INDEX_PREDICTION_BONUS if vis_idx in predicted_index_set else 0.0

        final_score = base_sim + idx_bonus + prior_bonus

        c = dict(entry)
        c["index"] = vis_idx
        c["predicted_hit"] = vis_idx in predicted_index_set
        c["prior_prob"] = prior_prob
        c["final_score"] = final_score
        candidates.append(c)

    if not candidates:
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": 0.0,
            "candidates": mapped,
        }

    candidates.sort(key=lambda e: e.get("final_score", 0.0), reverse=True)
    best = candidates[0]
    best_score = float(best.get("final_score", 0.0))

    second_score = 0.0
    if len(candidates) > 1:
        second_score = float(candidates[1].get("final_score", 0.0))

    # Decide if prediction is strong enough
    if best_score < PREDICTIVE_THRESHOLD or (best_score - second_score) < AMBIGUITY_MARGIN_PRED:
        return {
            "status": "no_match",
            "selected_index": None,
            "selected_visible": None,
            "canonical": target_value,
            "confidence": best_score,
            "candidates": candidates,
        }

    sel_idx = int(best["index"])
    return {
        "status": "ok",
        "selected_index": sel_idx,
        "selected_visible": visible_texts[sel_idx],
        "canonical": target_value,
        "confidence": best_score,
        "candidates": candidates,
    }

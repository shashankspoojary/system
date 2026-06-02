# reverse_precise_tracker.py
"""
Reverse-aware precise scan for dropdowns.

Goal:
- When in precise phase, if we overshoot past the "next neighbors" of target
  without selecting, reverse scroll.
- If reverse scroll overshoots past "previous neighbors", flip forward again.
- Never re-enter fast phase once precise starts.
"""

from typing import List, Optional, Dict, Any
import time

from MPF_BOT_V7_3 import (
    ocr_region_lines_dropdown,
    should_activate_reasoning,
    choose_visible_option,
    reasoning_click_option,
    verified_click_option,
    hardware_scroll_at,
    safe_sleep,
    _norm_option_text,
    _extract_inches,            # height helper
    DROPDOWN_PRECISE_PULSES
)

def precise_dropdown_scan_with_reverse(
    field_name: str,
    region,
    scroll_anchor_abs,
    target: str,
    prev_neighbors: Optional[List[str]] = None,
    next_neighbors: Optional[List[str]] = None,
    forward: bool = True,
    max_attempts: int = 240,
    vanish_threshold: int = 3,   # how many consecutive pages w/out neighbors -> "passed block"
) -> bool:
    """
    Reverse-aware precise scan.

    Args:
        prev_neighbors / next_neighbors:
            lists of canonical neighbor strings around target.
            If None, module falls back to normal one-way precise scan.
        forward:
            initial direction from fast-trigger (True=down, False=up)
    """

    target = (target or "").strip()
    if not target:
        return False

    is_height = (field_name or "").strip().lower() == "height"
    target_norm = _norm_option_text(target)

    prev_set = set(_norm_option_text(x) for x in (prev_neighbors or []))
    next_set = set(_norm_option_text(x) for x in (next_neighbors or []))

    direction_forward = bool(forward)   # mutable direction state

    # Overshoot tracking flags
    seen_next_block = False
    seen_prev_block = False
    miss_next_count = 0
    miss_prev_count = 0

    last_joined = None
    stable_count = 0

    for attempt in range(max_attempts):
        lines = ocr_region_lines_dropdown(region, debug_name=f"rev_precise_{field_name}_{attempt}")
        visible = [
            _norm_option_text(ln.get("text", ""))
            for ln in lines
            if ln.get("text", "").strip()
        ]

        # --- Reasoning first (same as your precise) ---
        if should_activate_reasoning(field_name, phase="precise"):
            reason = choose_visible_option(field_name, target, lines)
            if reasoning_click_option(region, reason):
                return True

        # --- Exact normalized match fallback ---
        for ln in lines:
            if _norm_option_text(ln.get("text", "")) == target_norm:
                if verified_click_option(region, ln, target):
                    return True

        # --- Height inches fallback (keep your behavior) ---
        if is_height:
            want_in = _extract_inches(target)
            if want_in is not None:
                for ln in lines:
                    got_in = _extract_inches(ln.get("text", ""))
                    if got_in is not None and abs(got_in - want_in) < 0.01:
                        if verified_click_option(region, ln, ln.get("text", "").strip()):
                            return True

        # ---------------- Overshoot detection ----------------
        if prev_set or next_set:
            vis_set = set(visible)

            has_prev = bool(prev_set & vis_set)
            has_next = bool(next_set & vis_set)

            if direction_forward:
                # moving down towards next items
                if has_next:
                    seen_next_block = True
                    miss_next_count = 0
                else:
                    if seen_next_block:
                        miss_next_count += 1

                # if we've seen next window and now it's vanished for a few pages => overshoot
                if seen_next_block and miss_next_count >= vanish_threshold:
                    direction_forward = False  # reverse
                    seen_prev_block = False
                    miss_prev_count = 0
                    seen_next_block = False
                    miss_next_count = 0
                    # don't scroll this loop; re-OCR after flip
                    continue

            else:
                # moving up towards prev items
                if has_prev:
                    seen_prev_block = True
                    miss_prev_count = 0
                else:
                    if seen_prev_block:
                        miss_prev_count += 1

                # if prev window vanished while reverse-tracking => overshoot upward, flip forward
                if seen_prev_block and miss_prev_count >= vanish_threshold:
                    direction_forward = True
                    seen_next_block = False
                    miss_next_count = 0
                    seen_prev_block = False
                    miss_prev_count = 0
                    continue

        # ------------- dead-end / end-plateau guard -------------
        joined = " ".join(visible)
        if joined == last_joined:
            stable_count += 1
            if stable_count >= 2:
                # tiny nudge opposite to break plateaus
                nudge_dir = +1 if direction_forward else -1
                hardware_scroll_at(scroll_anchor_abs, steps=nudge_dir,
                                   pulses=max(1, int(DROPDOWN_PRECISE_PULSES)),
                                   fast=False)
                safe_sleep(0.12)
                stable_count = 0
        else:
            stable_count = 0
            last_joined = joined

        # ------- Step scroll in current direction -------
        steps = -1 if direction_forward else +1
        hardware_scroll_at(
            scroll_anchor_abs,
            steps=steps,
            pulses=max(1, int(DROPDOWN_PRECISE_PULSES)),
            fast=False
        )
        safe_sleep(0.35)

    return False

# heavy_dropdown_guard.py
"""
Edge-Guard for heavy dropdowns (District/Cast/Sub Cast).

Problem:
Targets near the top/bottom can be missed because fast phase
doesn't use reasoning and OCR can be noisy on first visible page.

Solution:
If target index is within TOP_EDGE_GUARD or BOTTOM_EDGE_GUARD,
force a reasoning-based selection immediately after opening
(before any fast scroll).
"""

from typing import Optional
from dropdown_reasoner import reason_over_dropdown_page  # uses reasoning_core internally
from MPF_BOT_V7_3 import (
    ocr_region_lines_dropdown,
    reasoning_click_option,
    verified_click_option,
    _norm_option_text,
    speak,
    safe_sleep,
    check_pause,
)

def heavy_dropdown_edge_guard(
    field_name: str,
    region,
    desired_value: str,
    scroll_anchor_abs,
    target_index: int,
    total_options: int,
    profile: dict,
) -> bool:
    """
    Try to select heavy-dropdown targets near start/end using forced reasoning
    right after opening dropdown.

    Returns True if selected, else False to continue normal heavy flow.
    """
    top_guard = profile.get("TOP_EDGE_GUARD", 12)
    

    at_top_edge = target_index <= top_guard
    

    if not (at_top_edge):
        return False  # not an edge case

    speak(f"{field_name}: Edge-guard active for '{desired_value}' (idx={target_index}).")

    # Take 2 stable OCR snapshots before any scrolling
    for snap in range(2):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"{field_name}_EDGE_{snap}")

        # 1) Forced reasoning on open page (even though scrollable)
        reason = reason_over_dropdown_page(field_name, desired_value, lines)
        if reason and reason.get("line_dict"):
            if reasoning_click_option(region, reason):
                speak(f"{field_name}: Selected '{desired_value}' via edge-guard reasoning.")
                return True

        # 2) Fallback exact normalized match
        n_desired = _norm_option_text(desired_value)
        for ln in lines:
            if _norm_option_text(ln.get("text", "")) == n_desired:
                if verified_click_option(region, ln, desired_value):
                    speak(f"{field_name}: Selected '{desired_value}' via edge-guard exact match.")
                    return True

        safe_sleep(0.25)

    # If edge-guard failed, allow normal heavy flow to continue
    speak(f"{field_name}: Edge-guard couldn't confirm '{desired_value}'. Falling back.")
    return False
# heavy_dropdown_guard.py (add this below existing function)

def heavy_dropdown_edge_plan(
    field_name: str,
    region,
    desired_value: str,
    scroll_anchor_abs,
    target_index: int,
    total_options: int,
    profile: dict,
):
    """
    Edge-aware planner.

    Returns:
        (activated, selected, forward)

    activated: True if target is within TOP/BOTTOM edge guard.
    selected: True if we already clicked it on open page.
    forward:  direction to use for precise phase if not selected.
              True = forward/down, False = reverse/up
    """
    top_guard = profile.get("TOP_EDGE_GUARD", 12)
   

    at_top_edge = target_index <= top_guard
    

    if not (at_top_edge):
        return (False, False, True)  # not an edge case

    speak(f"{field_name}: Edge-guard active for '{desired_value}' (idx={target_index}).")

    # Direction hint:
    # - top edge -> scan forward (down) precisely
    # - bottom edge -> scan reverse (up) precisely
    forward = True if at_top_edge else False

    # Try to select immediately on open page (reasoning + exact backup)
    for snap in range(2):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"{field_name}_EDGE_{snap}")

        reason = reason_over_dropdown_page(field_name, desired_value, lines)
        if reason and reason.get("line_dict"):
            if reasoning_click_option(region, reason):
                speak(f"{field_name}: Selected '{desired_value}' via edge-guard reasoning.")
                return (True, True, forward)

        n_desired = _norm_option_text(desired_value)
        for ln in lines:
            if _norm_option_text(ln.get("text", "")) == n_desired:
                if verified_click_option(region, ln, desired_value):
                    speak(f"{field_name}: Selected '{desired_value}' via edge-guard exact match.")
                    return (True, True, forward)

        safe_sleep(0.25)

    # Edge case confirmed, but not found on first screen.
    # Still skip FAST phase and go PRECISE directly.
    speak(f"{field_name}: Edge-guard couldn't confirm on open page. Going precise directly.")
    return (True, False, forward)

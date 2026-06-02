# heavy_dropdown_jump.py
"""
heavy_dropdown_jump.py

Mid/Bottom "single big jump" rule for heavy dropdowns:
    District / Cast / Sub Cast

Inspired by jump.py's thresholding:
    - Above 50% but below/equal 70%
    - Above 70%

Flow:
    1) After opening dropdown, do ONE big jump scroll (single call).
    2) OCR the page once (or few snapshots if configured).
    3) If target is confidently selectable now -> click.
    4) Else:
         - if any PREVIOUS neighbors visible -> go PRECISE forward
         - elif any NEXT neighbors visible -> go PRECISE reverse
         - else -> continue FAST (your existing fast-phase will detect previous later)
"""

from __future__ import annotations
from typing import List, Tuple, Optional
def _jump_scroll_at(point, steps, pulses, profile):
    """
    Jump-only wheel scroller (does NOT affect other fields).
    Fixes MPF dropdown ignoring very fast wheel pulses.

    pulses = number of wheel notches (same meaning as hardware_scroll_at)
    """
    import time
    import platform
    import pyautogui

    sign = 1 if steps > 0 else -1
    pulses = max(1, int(abs(pulses)))

    # Tunables (safe defaults)
    prewait = float(profile.get("JUMP_PREWAIT", 0.04))
    event_sleep = float(profile.get("JUMP_EVENT_SLEEP", 0.015))   # key fix: slower than 0.008
    burst_every = int(profile.get("JUMP_BURST_EVERY", 35))
    burst_sleep = float(profile.get("JUMP_BURST_SLEEP", 0.06))
    final_sleep = float(profile.get("JUMP_FINAL_SLEEP", 0.03))

    try:
        pyautogui.moveTo(point[0], point[1])
    except Exception:
        pass

    time.sleep(prewait)

    is_windows = platform.system().lower().startswith("win")
    if is_windows:
        try:
            import ctypes
            MOUSEEVENTF_WHEEL = 0x0800

            for i in range(pulses):
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, sign * 120, 0)

                # slower per-notch pacing so MPF actually processes every notch
                time.sleep(event_sleep)

                # burst pause: lets MPF UI catch up on huge jumps
                if burst_every > 0 and (i + 1) % burst_every == 0:
                    time.sleep(burst_sleep)

        except Exception:
            # fallback (rare)
            try:
                pyautogui.scroll(sign * pulses)
            except Exception:
                pass
    else:
        try:
            pyautogui.scroll(sign * pulses)
        except Exception:
            pass

    time.sleep(final_sleep)


def _position_flags(total: int, index: int) -> Tuple[bool, bool, int, int]:
    """
    Same idea as jump.py:
      fifty_percent_position  = total//2 - 1   (last element in top 50%)
      seventy_percent_position= int(total*0.7) - 1 (last element in top 70%)

    Returns:
      (is_above_50, is_above_70, fifty_pos, seventy_pos)
    """
    fifty_pos = total // 2 - 1
    seventy_pos = int(total * 0.7) - 1
    is_above_50 = index > fifty_pos
    is_above_70 = index > seventy_pos
    return is_above_50, is_above_70, fifty_pos, seventy_pos


def heavy_dropdown_midbottom_jump(
    field_name: str,
    region,
    desired_value: str,
    scroll_anchor_abs,
    target_index: int,
    options: List[str],
    neighbors_prev: List[str],
    neighbors_next: List[str],
    profile: dict,
):
    """
    Returns:
        ("none", None)         -> no jump rule applied
        ("done", True/False)   -> selected (True) or hard-failed (False)
        ("precise", forward)   -> jump applied and we decided direction
        ("fast", None)         -> jump applied but no anchor seen, continue fast phase
    """
    # Allow turning off easily while testing
    if not profile.get("JUMP_ENABLE", True):
        return ("none", None)

    total = len(options or [])
    if total <= 1 or target_index is None or target_index < 0 or target_index >= total:
        return ("none", None)

        # % position in list (1..total). Example: idx=0 => ~0.01, last => 1.0
    pct = (target_index + 1) / float(total)

    # ---------------- lazy imports to avoid circular import ----------------
    from MPF_BOT_V7_3 import (
        ocr_region_lines_dropdown,
        verified_click_option,
        reasoning_click_option,
        speak,
        safe_sleep,
        check_pause,
    )
    from dropdown_reasoner import reason_over_dropdown_page

    # Pick pulses for ONE big jump based on where target sits in the dataset.
    # NOTE:
    # - 30-40 and 40-50 only activate if you define those keys in the profile
    #   (so existing behavior won’t change unless you add the keys).
    bucket = None
    pulses = None

    if 0.30 < pct <= 0.40 and "JUMP_30_40_PULSES" in profile:
        pulses = float(profile["JUMP_30_40_PULSES"])
        bucket = "30-40%"

    elif 0.40 < pct <= 0.50 and "JUMP_40_50_PULSES" in profile:
        pulses = float(profile["JUMP_40_50_PULSES"])
        bucket = "40-50%"

    elif 0.50 < pct <= 0.60:
        pulses = float(profile.get("JUMP_50_60_PULSES",
                     profile.get("JUMP_50_70_PULSES", profile["FAST_PULSES"] * 8.0)))
        bucket = "50-60%"

    elif 0.60 < pct <= 0.70:
        pulses = float(profile.get("JUMP_60_70_PULSES",
                     profile.get("JUMP_50_70_PULSES", profile["FAST_PULSES"] * 8.0)))
        bucket = "60-70%"

    elif 0.70 < pct <= 0.80:
        pulses = float(profile.get("JUMP_70_80_PULSES",
                     profile.get("JUMP_GT70_PULSES", profile["FAST_PULSES"] * 12.0)))
        bucket = "70-80%"

    elif 0.80 < pct <= 0.90:
        pulses = float(profile.get("JUMP_80_90_PULSES",
                     profile.get("JUMP_GT70_PULSES", profile["FAST_PULSES"] * 12.0)))
        bucket = "80-90%"

    elif pct > 0.90:
        pulses = float(profile.get("JUMP_GT90_PULSES",
                     profile.get("JUMP_GT70_PULSES", profile["FAST_PULSES"] * 12.0)))
        bucket = ">90%"

    else:
        return ("none", None)

    speak(f"{field_name}: Jump rule ({bucket}) active. idx={target_index}/{total-1} -> one big jump.")


    # One jump only (IMPORTANT)
    check_pause()
    _jump_scroll_at(scroll_anchor_abs, steps=-1, pulses=pulses, profile=profile)
    safe_sleep(float(profile.get("JUMP_SLEEP", max(0.25, profile.get("FAST_SLEEP", 0.5)))))

    # After jump: OCR snapshot(s)
    snaps = int(profile.get("JUMP_SNAPSHOTS", 1))
    prev_watch_n = int(profile.get("JUMP_PREV_WATCH", 8))
    next_watch_n = int(profile.get("JUMP_NEXT_WATCH", 8))

    prev_watch = (neighbors_prev or [])[-prev_watch_n:]  # closest previous items
    next_watch = (neighbors_next or [])[:next_watch_n]   # closest next items

    for s in range(max(1, snaps)):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"{field_name}_JUMP_{s}")

        # (Optional) reasoning click if very confident
        if profile.get("JUMP_USE_REASONING", True):
            reason = reason_over_dropdown_page(field_name, desired_value, lines)
            min_conf = float(profile.get("JUMP_REASONING_MIN", 0.88))
            if reason and reason.get("line_dict") and float(reason.get("confidence", 0.0)) >= min_conf:
                if reasoning_click_option(region, reason):
                    speak(f"{field_name}: Selected '{desired_value}' using jump reasoning.")
                    return ("done", True)

        # Fallback: exact page match (kept strict to avoid wrong clicks)
        for ln in lines:
            txt = (ln.get("text") or "").strip()
            if txt and txt.lower() == desired_value.lower():
                if verified_click_option(region, ln, desired_value):
                    speak(f"{field_name}: Selected '{desired_value}' directly after jump.")
                    return ("done", True)

        # Decide direction based on neighbor visibility
        vis_lower = [(ln.get("text") or "").strip().lower() for ln in lines if (ln.get("text") or "").strip()]
        vis_set = set(vis_lower)

        if any(p in vis_set for p in prev_watch):
            speak(f"{field_name}: After jump, PREV anchor seen -> go precise forward.")
            return ("precise", True)

        if any(n in vis_set for n in next_watch):
            speak(f"{field_name}: After jump, NEXT anchor seen -> go precise reverse.")
            return ("precise", False)

        safe_sleep(0.15)

    # No anchor found on the post-jump page -> continue fast phase
    speak(f"{field_name}: After jump, no anchor visible -> continue fast phase.")
    return ("fast", None)

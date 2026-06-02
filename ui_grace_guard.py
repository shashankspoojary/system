# ui_grace_guard.py
"""
Wait for a UI button using the existing wait_for_button_and_click().
If not found within initial timeout -> send telegram alert -> grace wait.
"""

from __future__ import annotations
from typing import Callable, Optional, Sequence, Tuple

Region = Sequence[int]  # (x1, y1, x2, y2)
Point = Tuple[int, int]


def wait_button_with_grace(
    *,
    label: str,
    region: Region,
    wait_for_button_and_click: Callable[..., bool],
    click_pos: Optional[Point] = None,
    initial_timeout: float = 40.0,
    grace_timeout: float = 7 * 60.0,
    poll_interval: float = 0.7,
    debug_prefix: str = "flow",
    notify: Optional[Callable[[str], None]] = None,
    notify_reason: Optional[str] = None,
) -> bool:
    ok = wait_for_button_and_click(
        label,
        tuple(region),
        timeout=initial_timeout,
        poll_interval=poll_interval,
        debug_prefix=debug_prefix,
        click_pos=click_pos,
    )
    if ok:
        return True

    # Enter grace wait
    reason = notify_reason or f"{label} not visible after {int(initial_timeout)}s (grace wait started)"
    if notify:
        try:
            notify(reason)
        except Exception:
            pass

    ok = wait_for_button_and_click(
        label,
        tuple(region),
        timeout=grace_timeout,
        poll_interval=poll_interval,
        debug_prefix=f"{debug_prefix}_grace",
        click_pos=click_pos,
    )
    return bool(ok)

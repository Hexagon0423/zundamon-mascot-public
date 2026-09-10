"""Window placement maths, kept Qt-free so it can be tested without a screen."""

from __future__ import annotations


def clamp_onto_screen(
    x: int,
    y: int,
    width: int,
    height: int,
    screen: tuple[int, int, int, int],
) -> tuple[int, int]:
    """Nudge a window position so the window stays on its screen.

    Positions are remembered as a fraction of the screen (see config.py), but
    the fraction locates the window's *top-left corner*, so a remembered
    fraction near 1.0 puts the whole mascot past the right edge -- it then
    starts up invisible and looks exactly like a mascot that failed to launch
    (2026-09-10: a stored x_fraction of 0.998 cost an hour of debugging).

    A window larger than the screen can't fit, so it is clamped the other way:
    it stays covering the screen rather than being pushed off it.

    `screen` is (x, y, width, height).
    """
    screen_x, screen_y, screen_width, screen_height = screen
    slack_x = screen_width - width
    slack_y = screen_height - height
    x = min(max(x, screen_x + min(0, slack_x)), screen_x + max(0, slack_x))
    y = min(max(y, screen_y + min(0, slack_y)), screen_y + max(0, slack_y))
    return x, y

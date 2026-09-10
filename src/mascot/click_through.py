"""Letting clicks fall through the window to whatever is behind it.

Qt's `WA_TransparentForMouseEvents` only covers child widgets; on a top-level
window it does not stop the OS routing clicks to it, so the mascot's window --
a rectangle around a mostly transparent drawing -- swallowed clicks over
roughly twice the area the mascot occupies (2026-09-11, reported twice: the Qt
attribute alone looked like a fix and wasn't).

On Windows the real switch is the WS_EX_TRANSPARENT extended style. It can be
flipped on a live window, which matters here: the window has to take clicks
again the moment the cursor moves back onto the drawing, and re-creating the
window (which changing Qt's window flags would do) loses its position.

Everything else falls back to the Qt attribute, which is at least correct for
the cases it covers.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000


def is_supported() -> bool:
    return sys.platform == "win32"


def apply_style(current: int, transparent: bool) -> int:
    """The extended style `current` should become.

    WS_EX_LAYERED goes on alongside: WS_EX_TRANSPARENT is only honoured for
    hit-testing on a layered window, and Qt has already made this one layered
    for the translucent background, so setting it is a no-op in practice and
    insurance if that ever changes.
    """
    if transparent:
        return current | WS_EX_TRANSPARENT | WS_EX_LAYERED
    return current & ~WS_EX_TRANSPARENT


def set_click_through(window_id: int, transparent: bool) -> bool:
    """Flip click-through on the native window. Returns whether it was applied."""
    if not is_supported() or not window_id:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_long.restype = ctypes.c_ssize_t
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]

        handle = ctypes.c_void_p(int(window_id))
        current = get_long(handle, GWL_EXSTYLE)
        wanted = apply_style(current, transparent)
        if wanted != current:
            set_long(handle, GWL_EXSTYLE, wanted)
        return True
    except Exception:  # noqa: BLE001 -- a failure here is cosmetic, not fatal
        logger.exception("クリック透過の切り替えに失敗したのだ")
        return False

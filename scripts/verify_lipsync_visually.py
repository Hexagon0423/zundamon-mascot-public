"""Capture the mascot window while it speaks, to check the mouth actually moves.

This environment's normal desktop screenshot doesn't include always-on-top
windows (see PLAN.md), so this grabs the window directly via PrintWindow --
the one capture method confirmed to work here. Saves a strip of frames and
reports how many distinct mouth shapes appeared.

Usage: python scripts/verify_lipsync_visually.py [out_dir]
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

from PIL import Image

TEXT = "あいうえお、ずんだもんなのだ。おはようからおやすみまで、口が動いているか確かめるのだ。"
SPEAK_URL = "http://127.0.0.1:50022/speak"
CAPTURE_COUNT = 24
CAPTURE_INTERVAL_S = 0.15

# Must be DPI-aware before any window call, or Windows hands back virtualised
# logical coordinates and we capture only the top-left corner of the window.
ctypes.windll.shcore.SetProcessDpiAwareness(2)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 2
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


SIZE_TOLERANCE_PX = 4  # logical->physical rounding can shift the size by a pixel


def find_mascot_window() -> int | None:
    """Find our window by size: it matches the art's pixel dimensions."""
    sets_dir = Path(__file__).resolve().parent.parent / "assets" / "sets"
    manifest_path = next(sets_dir.glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    want_w, want_h = manifest["canvas"]["width"], manifest["canvas"]["height"]

    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if (
            abs(width - want_w) <= SIZE_TOLERANCE_PX
            and abs(height - want_h) <= SIZE_TOLERANCE_PX
        ):
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def capture_window(hwnd: int) -> tuple[bytes, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)

    user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)
    return buffer.raw, width, height


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("lipsync_frames")
    out_dir.mkdir(parents=True, exist_ok=True)

    hwnd = find_mascot_window()
    if hwnd is None:
        print("マスコットのウィンドウが見つからないのだ。起動しているか確認するのだ。")
        return 1
    print(f"found mascot window hwnd={hwnd}")

    body = json.dumps({"text": TEXT}).encode("utf-8")
    request = urllib.request.Request(
        SPEAK_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=5) as resp:
        print("POST /speak ->", resp.status)

    frames: list[tuple[float, str]] = []
    start = time.monotonic()
    for i in range(CAPTURE_COUNT):
        pixels, width, height = capture_window(hwnd)
        digest = hashlib.sha1(pixels).hexdigest()[:12]
        elapsed = time.monotonic() - start
        frames.append((elapsed, digest))

        blue, green, red, _alpha = Image.frombytes("RGBA", (width, height), pixels).split()
        Image.merge("RGB", (red, green, blue)).save(out_dir / f"frame_{i:02d}_{digest}.png")
        time.sleep(CAPTURE_INTERVAL_S)

    distinct = {digest for _, digest in frames}
    print(f"\ncaptured {len(frames)} frames, {len(distinct)} distinct images")
    for elapsed, digest in frames:
        print(f"  t={elapsed:5.2f}s  {digest}")
    if len(distinct) == 1:
        print("\n口が一度も変化していないのだ。口パクが動いていない可能性が高いのだ。")
        return 1
    print("\n口の形が変化しているのだ。口パクは動いているのだ。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Watch a silent mascot and check that it blinks on its own.

Blinking must be driven by its own timer, independent of speech, so this
captures the window while sending nothing and reports how many distinct
images appear. Silence + more than one image = it blinked.

Usage: python scripts/verify_blink.py [seconds]
"""

from __future__ import annotations

import collections
import hashlib
import sys
import time

from verify_lipsync_visually import capture_window, find_mascot_window

INTERVAL_S = 0.04  # a blink's closed phase is ~90ms, so sample faster than that


def main() -> int:
    watch_seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

    hwnd = find_mascot_window()
    if hwnd is None:
        print("マスコットのウィンドウが見つからないのだ。")
        return 1

    counts: collections.Counter[str] = collections.Counter()
    deadline = time.monotonic() + watch_seconds
    while time.monotonic() < deadline:
        pixels, _, _ = capture_window(hwnd)
        counts[hashlib.sha1(pixels).hexdigest()[:12]] += 1
        time.sleep(INTERVAL_S)

    total = sum(counts.values())
    print(f"{watch_seconds:.0f}秒間 無言で観察: {total}回撮影、{len(counts)}種類の画像")
    for digest, count in counts.most_common():
        print(f"  {digest}  {count:4d}回 ({count / total:5.1%})")

    if len(counts) < 2:
        print("\nまばたきしていないのだ。")
        return 1
    print("\n無言でも画像が変化しているのだ = まばたきしているのだ。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

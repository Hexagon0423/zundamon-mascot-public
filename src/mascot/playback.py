"""WAV playback via the stdlib `winsound` module.

Windows-only (this whole project is), so no extra audio dependency is
needed. Playback is fire-and-forget async; lipsync timing is driven from a
QElapsedTimer started at the same moment (see speaker.py), not from actual
playback position feedback -- see PLAN.md for why that's an acceptable
first pass.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
import winsound
from pathlib import Path

logger = logging.getLogger(__name__)

TEMP_PREFIX = "zundamon_mascot_"

# winsound plays straight from the file, so it can't be deleted while it is
# still playing. Each new utterance cleans up the previous one instead.
_previous_path: Path | None = None


def play_wav_async(wav_bytes: bytes) -> Path:
    global _previous_path

    tmp_path = Path(tempfile.gettempdir()) / f"{TEMP_PREFIX}{uuid.uuid4().hex}.wav"
    tmp_path.write_bytes(wav_bytes)
    winsound.PlaySound(str(tmp_path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    if _previous_path is not None:
        _delete_quietly(_previous_path)
    _previous_path = tmp_path
    return tmp_path


def stop() -> None:
    winsound.PlaySound(None, winsound.SND_PURGE)


def cleanup_leftovers() -> None:
    """Delete stale temp WAVs from previous runs (e.g. after a crash)."""
    for path in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*.wav"):
        if path != _previous_path:
            _delete_quietly(path)


def _delete_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Still held by the audio device; the next cleanup pass will get it.
        logger.debug("一時ファイルを消せなかった: %s", path)

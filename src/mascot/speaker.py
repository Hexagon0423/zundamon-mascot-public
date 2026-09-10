"""Ties everything together: queue -> VOICEVOX -> playback -> lipsync.

Lives on the GUI thread. Runs one utterance at a time; when one finishes
(or the timeline runs out) it checks the queue for the next one.

The VOICEVOX round-trip is the one thing that doesn't happen here: it runs on
a worker thread and comes back through a signal. Synthesis takes longer the
more text there is, and doing it inline froze the mascot mid-pose for the
duration -- the window's own paint timer can't run while the GUI thread is
blocked on a socket (2026-09-11, reported as "一瞬立ち絵がフリーズする").
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal

from mascot.config import Config
from mascot.lipsync import (
    DEFAULT_MIN_HOLD_SECONDS,
    apply_min_hold,
    build_timeline,
    vowel_at,
)
from mascot.playback import play_wav_async
from mascot.speech_queue import SpeechQueue
from mascot.voicevox import VoicevoxClient
from mascot.window import MascotWindow

logger = logging.getLogger(__name__)

FRAME_INTERVAL_MS = 33  # ~30fps
POST_SPEECH_SILENCE_BUFFER_S = 0.3  # margin so audio finishes before we go idle


class Speaker(QObject):
    # Emitted when an utterance can't be spoken (VOICEVOX down etc.), so the
    # app can surface it -- otherwise the only symptom is silence.
    speech_failed = Signal(str)
    # Internal: carries a finished synthesis back from the worker thread. Qt
    # queues it onto the GUI thread, which is the only place the timeline,
    # playback and window may be touched.
    _synthesis_finished = Signal(object, object, object)

    def __init__(
        self,
        window: MascotWindow,
        speech_queue: SpeechQueue,
        voicevox: VoicevoxClient,
        config: Config,
    ):
        super().__init__()
        self._window = window
        self._speech_queue = speech_queue
        self._voicevox = voicevox
        self._config = config

        self._timeline = []
        self._end_time = 0.0
        self._elapsed = QElapsedTimer()
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_tick)
        self._speaking = False
        self._pending_expression = None

        self._speech_queue.new_item.connect(self._maybe_start_next)
        self._synthesis_finished.connect(self._on_synthesis_finished)

    def _maybe_start_next(self) -> None:
        if self._speaking:
            return
        request = self._speech_queue.pop()
        if request is None:
            return
        self._start_utterance(request)

    def _start_utterance(self, request) -> None:
        text = request.text
        # Held until the audio is ready rather than applied now: the window
        # lets an expression go a short while after the mouth stops moving, and
        # synthesis can outlast that, so applying it up front made the mascot
        # strike the pose, drop out of it, and only then start talking
        # (2026-09-11).
        self._pending_expression = request.expression
        # Claimed before the worker starts, so a second request arriving mid
        # synthesis waits in the queue instead of starting a parallel one.
        self._speaking = True
        threading.Thread(target=self._synthesize, args=(text,), daemon=True).start()

    def _synthesize(self, text: str) -> None:
        """Worker thread: talk to VOICEVOX, hand the result back via the signal.

        Nothing here may touch the window, the timeline or the timers -- the
        signal connection is what moves the result onto the GUI thread.
        """
        try:
            query = self._voicevox.audio_query(text, self._config.voice)
            wav_bytes = self._voicevox.synthesis(query, self._config.voice)
        except Exception as exc:  # noqa: BLE001 -- reported to the user as-is
            logger.exception("VOICEVOX synthesis failed for text=%r", text)
            self._synthesis_finished.emit(None, None, exc)
            return
        self._synthesis_finished.emit(query, wav_bytes, None)

    def _on_synthesis_finished(self, query, wav_bytes, error) -> None:
        if error is not None:
            self._speaking = False
            self._pending_expression = None
            self.speech_failed.emit(f"音声合成に失敗したのだ: {error}")
            self._maybe_start_next()
            return

        timeline = build_timeline(query)
        self._timeline = apply_min_hold(timeline, DEFAULT_MIN_HOLD_SECONDS)
        post_phoneme = query.get("postPhonemeLength", 0.0) / (query.get("speedScale", 1.0) or 1.0)
        self._end_time = (self._timeline[-1].end if self._timeline else 0.0) + post_phoneme

        if self._pending_expression is not None:
            self._window.apply_expression(self._pending_expression)
            self._pending_expression = None
        play_wav_async(wav_bytes)
        self._elapsed.start()
        self._frame_timer.start()

    def _on_tick(self) -> None:
        t = self._elapsed.elapsed() / 1000.0
        if t >= self._end_time + POST_SPEECH_SILENCE_BUFFER_S:
            self._frame_timer.stop()
            # Not the silent mouth directly: if the active expression has a
            # mouth of its own (seihuku's art has 真顔/あんぐり/うぜぇ口 etc),
            # the mascot should settle back into *that* rather than a generic
            # closed mouth, since it then sits silent far longer than it speaks.
            self._window.restore_resting_mouth()
            self._speaking = False
            self._maybe_start_next()
            return
        self._window.set_mouth_for_vowel(vowel_at(self._timeline, t))

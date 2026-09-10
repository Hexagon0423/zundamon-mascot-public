import json
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mascot.config import Config  # noqa: E402
from mascot.speaker import Speaker  # noqa: E402
from mascot.speech_queue import SpeechQueue  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audio_query_sample.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeWindow:
    def __init__(self):
        self.expressions = []

    def apply_expression(self, name):
        self.expressions.append(name)

    def set_mouth_for_vowel(self, vowel):
        pass

    def restore_resting_mouth(self):
        pass


class SlowVoicevox:
    """Stands in for a VOICEVOX that takes a noticeable moment to answer."""

    def __init__(self, delay: float):
        self._delay = delay
        self.thread_names: list[str] = []

    def audio_query(self, text, voice):
        self.thread_names.append(threading.current_thread().name)
        time.sleep(self._delay)
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def synthesis(self, query, voice):
        return b"RIFF....WAVEfmt "


def _speak(app, voicevox, monkeypatch):
    monkeypatch.setattr("mascot.speaker.play_wav_async", lambda data: None)
    queue = SpeechQueue()
    speaker = Speaker(FakeWindow(), queue, voicevox, Config())
    queue.push("こんにちはなのだ", expression="happy")
    return speaker, queue


def test_synthesis_does_not_run_on_the_gui_thread(app, monkeypatch):
    """The window's paint timer can't tick while this thread blocks on a socket.

    Doing the round-trip inline froze the mascot for as long as VOICEVOX took,
    which was visible on any reply of a few sentences (2026-09-11).
    """
    voicevox = SlowVoicevox(delay=0.2)
    _speak(app, voicevox, monkeypatch)

    gui_thread = threading.current_thread().name
    deadline = time.monotonic() + 5.0
    while not voicevox.thread_names and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert voicevox.thread_names, "合成が始まらなかったのだ"
    assert voicevox.thread_names[0] != gui_thread


def test_the_gui_stays_responsive_while_synthesis_runs(app, monkeypatch):
    voicevox = SlowVoicevox(delay=0.4)
    _speak(app, voicevox, monkeypatch)

    ticks = 0
    deadline = time.monotonic() + 0.35
    while time.monotonic() < deadline:
        app.processEvents()
        ticks += 1
        time.sleep(0.01)

    # Inline synthesis would have blocked this loop entirely.
    assert ticks > 10


def test_a_failure_frees_the_speaker_for_the_next_utterance(app, monkeypatch):
    """A stuck _speaking flag would silence every later utterance, and the
    only symptom would be the mascot never talking again."""

    class Broken:
        def audio_query(self, text, voice):
            raise RuntimeError("VOICEVOXが落ちてるのだ")

        def synthesis(self, query, voice):  # pragma: no cover - never reached
            raise AssertionError

    failures = []
    speaker, _queue = _speak(app, Broken(), monkeypatch)
    speaker.speech_failed.connect(failures.append)

    deadline = time.monotonic() + 5.0
    while not failures and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert failures, "失敗が通知されなかったのだ"
    assert speaker._speaking is False

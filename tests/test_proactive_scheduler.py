import random
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mascot import proactive  # noqa: E402
from mascot.proactive_scheduler import ProactiveSpeechScheduler  # noqa: E402
from mascot.speech_queue import SpeechQueue  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeClock:
    """A manually-advanced monotonic clock, so tests don't need real sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AlwaysFire(random.Random):
    def random(self):
        return 0.0  # always < FIRE_PROBABILITY

    def uniform(self, a, b):
        return a  # shortest possible re-arm delay, so tests don't wait long


class NeverFire(random.Random):
    def random(self):
        return 1.0  # never < FIRE_PROBABILITY

    def uniform(self, a, b):
        return a


def _pump(app, seconds=0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def test_does_not_fire_before_minimum_silence_elapses(app):
    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, lambda: 0, rng=AlwaysFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS - 1)
    scheduler._on_check()  # invoke directly: the real QTimer interval is minutes long

    assert queue.pop() is None


def test_fires_after_the_silence_threshold_when_the_roll_succeeds(app):
    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, lambda: 0, rng=AlwaysFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS + 1)
    scheduler._on_check()

    request = queue.pop()
    assert request is not None
    assert (request.text, request.expression) in proactive.IDLE_CHATTER_BY_TIER["new"]


def test_never_fires_when_the_roll_fails(app):
    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, lambda: 0, rng=NeverFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS + 100)
    scheduler._on_check()

    assert queue.pop() is None


def test_activity_resets_the_silence_clock(app):
    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, lambda: 0, rng=AlwaysFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS + 1)
    queue.push("こんにちはなのだ", expression="happy")  # simulates an unrelated real utterance
    _pump(app)  # let the queued Qt signal actually reach the scheduler
    queue.pop()  # drain that push so it doesn't get mistaken for the scheduler's own

    scheduler._on_check()  # clock was just reset by the push above, so this must not fire
    assert queue.pop() is None


def test_uses_the_days_together_provider_to_pick_the_tier(app):
    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, lambda: 50, rng=AlwaysFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS + 1)
    scheduler._on_check()

    request = queue.pop()
    assert request is not None
    assert (request.text, request.expression) in proactive.IDLE_CHATTER_BY_TIER["close"]


def test_a_broken_provider_does_not_crash_the_check(app):
    def broken():
        raise RuntimeError("companion state unavailable")

    queue = SpeechQueue()
    clock = FakeClock()
    scheduler = ProactiveSpeechScheduler(queue, broken, rng=AlwaysFire(), clock=clock)

    clock.advance(proactive.MIN_SILENCE_SECONDS + 1)
    scheduler._on_check()  # must not raise

    assert queue.pop() is not None  # still speaks, just falls back to days=0

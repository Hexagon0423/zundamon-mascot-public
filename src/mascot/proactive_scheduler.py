"""Drives proactive.py off a randomized QTimer.

Listens to speech_queue's own new_item signal as the sole source of "did
anything just make it talk" -- no dependency on Speaker's internal _speaking
flag, and no change to speaker.py at all. Pushing a proactive line simply
queues like any other push; if the queue is busy or full (SpeechQueue caps at
3), it either waits its turn or silently drops, same as any other push racing
the cap. That's the desired behavior, not a gap to work around: a proactive
line should never compete with or delay something the user is actually
watching for.

Not gated on "is the mascot currently speaking" either. By construction that
almost never coincides with the idle check firing -- the utterance itself
just reset the silence clock via new_item, so MIN_SILENCE_SECONDS won't have
elapsed. In the rare case it does coincide, it just queues and waits, no
observable bug.

Also drives the companion/relationship check (morning greeting, welcome-back,
milestones -- see app.py's `_companion_check`) on the same recurring timer,
not just once at startup. A process that never restarts (survives a
sleep/wake, or simply stays open for days) would otherwise never notice a new
morning or a newly-reached milestone, since nothing else re-checks those
while it keeps running.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from mascot import proactive
from mascot.speech_queue import SpeechQueue

logger = logging.getLogger(__name__)


class ProactiveSpeechScheduler(QObject):
    def __init__(
        self,
        speech_queue: SpeechQueue,
        days_together_provider: Callable[[], int],
        companion_check: Callable[[], bool] | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__()
        self._speech_queue = speech_queue
        self._days_together_provider = days_together_provider
        self._companion_check = companion_check
        self._rng = rng or random.Random()
        self._clock = clock
        self._last_activity = clock()

        # Any push -- from the Claude Code hook, a click reaction, an hourly
        # chime, or this scheduler's own line -- counts as activity and
        # restarts the silence clock. That's intentional: it just means the
        # next idle check measures from whenever the mascot last actually
        # said something, proactive or not.
        self._speech_queue.new_item.connect(self._on_activity)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_check)
        self._arm_next_check()

    def _on_activity(self) -> None:
        self._last_activity = self._clock()

    def _arm_next_check(self) -> None:
        self._timer.start(int(proactive.next_check_delay(self._rng) * 1000))

    def _on_check(self) -> None:
        # The companion check (morning / welcome-back / milestone) runs every
        # tick, not just at startup -- a process that never restarts (survives
        # a sleep/wake, or just stays open for days) would otherwise never
        # notice any of those. It takes priority: if it spoke, the idle-chatter
        # roll for this tick is skipped, so the two don't stack in one moment.
        companion_fired = False
        if self._companion_check is not None:
            try:
                companion_fired = self._companion_check()
            except Exception:  # noqa: BLE001 -- a broken check shouldn't kill the timer
                logger.exception("companion_check が失敗したのだ")

        if not companion_fired:
            silence = self._clock() - self._last_activity
            if silence >= proactive.MIN_SILENCE_SECONDS and proactive.should_fire(self._rng):
                try:
                    days = self._days_together_provider()
                except Exception:  # noqa: BLE001 -- a broken provider shouldn't kill the timer
                    logger.exception("days_together_provider が失敗したのだ")
                    days = 0
                line, expression = proactive.pick_idle_chatter(days, self._rng)
                self._speech_queue.push(line, expression=expression)
        self._arm_next_check()

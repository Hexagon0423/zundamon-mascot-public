"""Thread-safe queue between the HTTP handler thread and the GUI thread.

The HTTP server thread calls push(); the GUI thread calls pop() to consume.
new_item is a Qt signal so the GUI thread wakes up without polling -- Qt
auto-queues signal emissions across threads for a QObject that lives on the
GUI thread's event loop, so this is safe to call from any thread.
"""

from __future__ import annotations

import collections
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

DEFAULT_MAX_QUEUED = 3


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    expression: str | None = None


class SpeechQueue(QObject):
    new_item = Signal()

    def __init__(self, max_queued: int = DEFAULT_MAX_QUEUED):
        super().__init__()
        self._queue: collections.deque[SpeechRequest] = collections.deque(maxlen=max_queued)
        self._lock = threading.Lock()

    def push(self, text: str, expression: str | None = None) -> None:
        with self._lock:
            self._queue.append(SpeechRequest(text=text, expression=expression))
        self.new_item.emit()

    def pop(self) -> SpeechRequest | None:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.popleft()

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

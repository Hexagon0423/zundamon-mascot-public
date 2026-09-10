from mascot.speech_queue import SpeechQueue


def test_pop_empty_queue_returns_none():
    queue = SpeechQueue()
    assert queue.pop() is None


def test_push_then_pop_returns_in_fifo_order():
    queue = SpeechQueue()
    queue.push("first")
    queue.push("second")
    assert queue.pop().text == "first"
    assert queue.pop().text == "second"
    assert queue.pop() is None


def test_overflow_drops_oldest_item():
    queue = SpeechQueue(max_queued=3)
    queue.push("a")
    queue.push("b")
    queue.push("c")
    queue.push("d")  # "a" should be dropped
    assert [r.text for r in queue._queue] == ["b", "c", "d"]


def test_new_item_signal_fires_on_push():
    queue = SpeechQueue()
    received = []
    queue.new_item.connect(lambda: received.append(True))
    queue.push("hello")
    assert received == [True]

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from mascot import server as server_module
from mascot.server import start_server
from mascot.speech_queue import SpeechQueue


@pytest.fixture
def running_server():
    queue = SpeechQueue()
    server = start_server(queue, port=0)  # port=0 -> OS picks a free port
    port = server.server_address[1]
    yield queue, port
    server.shutdown()
    server.server_close()


def _post(port, payload_bytes, content_type="application/json"):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/speak",
        data=payload_bytes,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_speak_valid_text_is_queued(running_server):
    queue, port = running_server
    status, body = _post(port, json.dumps({"text": "こんにちはなのだ"}).encode("utf-8"))
    assert status == 200
    assert body == {"queued": True}
    assert queue.pop().text == "こんにちはなのだ"


def test_speak_missing_text_field_returns_400(running_server):
    _, port = running_server
    status, body = _post(port, json.dumps({}).encode("utf-8"))
    assert status == 400
    assert "error" in body


def test_speak_invalid_json_returns_400(running_server):
    _, port = running_server
    status, body = _post(port, b"not json")
    assert status == 400
    assert "error" in body


def test_start_server_raises_when_port_is_taken(running_server, monkeypatch):
    """app.py relies on this to show an error dialog instead of dying silently."""
    monkeypatch.setattr(server_module, "BIND_RETRY_SECONDS", 0.1)
    _, port = running_server
    with pytest.raises(OSError):
        start_server(SpeechQueue(), port)


def test_start_server_waits_for_the_previous_instance_to_let_go(monkeypatch):
    """Switching art sets starts the successor while the old one is still exiting.

    The port is held with SO_EXCLUSIVEADDRUSE, so without this wait the new
    mascot dies on bind and simply never appears (WinError 10048, 2026-09-10).
    """
    monkeypatch.setattr(server_module, "BIND_RETRY_SECONDS", 5.0)
    monkeypatch.setattr(server_module, "BIND_RETRY_INTERVAL_SECONDS", 0.05)

    old_server = start_server(SpeechQueue(), port=0)
    port = old_server.server_address[1]

    def release_shortly():
        time.sleep(0.4)
        old_server.shutdown()
        old_server.server_close()

    threading.Thread(target=release_shortly, daemon=True).start()

    new_server = start_server(SpeechQueue(), port)
    try:
        assert new_server.server_address[1] == port
    finally:
        new_server.shutdown()
        new_server.server_close()


def test_speak_empty_text_returns_400(running_server):
    _, port = running_server
    status, body = _post(port, json.dumps({"text": ""}).encode("utf-8"))
    assert status == 400
    assert "error" in body

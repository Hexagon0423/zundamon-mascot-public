"""Local HTTP server: POST /speak {"text": "..."} -> pushes onto SpeechQueue.

Runs in a background daemon thread (started from app.py). Deliberately
minimal (stdlib http.server, no Flask) since this only ever needs to accept
one simple endpoint from localhost.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mascot.speech_queue import SpeechQueue

logger = logging.getLogger(__name__)

# How long to keep retrying the bind before giving up. Long enough to cover
# the hand-off from a mascot that is on its way out, short enough that a
# genuinely running second instance still fails quickly and visibly.
BIND_RETRY_SECONDS = 3.0
BIND_RETRY_INTERVAL_SECONDS = 0.2


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """HTTP server that refuses to share its port.

    ThreadingHTTPServer sets SO_REUSEADDR by default, which on Windows means
    a second process can bind a port that is already in use and quietly steal
    part of the traffic -- so a second mascot instance would start "fine" and
    the two would fight over incoming speech requests. SO_EXCLUSIVEADDRUSE is
    the Windows-specific opposite: bind fails loudly if anyone holds the port.
    """

    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_handler(speech_queue: SpeechQueue) -> type[BaseHTTPRequestHandler]:
    class SpeakHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            logger.info("%s - %s", self.address_string(), format % args)

        def do_POST(self):
            if self.path != "/speak":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            try:
                data = json.loads(body or b"{}")
                text = data["text"]
                if not isinstance(text, str) or not text:
                    raise ValueError("text must be a non-empty string")
                expression = data.get("expression")
                if expression is not None and not isinstance(expression, str):
                    raise ValueError("expression must be a string")
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
                return

            speech_queue.push(text, expression)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"queued": True}).encode("utf-8"))

    return SpeakHandler


def start_server(speech_queue: SpeechQueue, port: int) -> ExclusiveHTTPServer:
    """Start the server on a background thread.

    Retries the bind for a few seconds first. Switching art sets replaces the
    running mascot with a fresh process, and the newcomer can reach for the
    port while the outgoing one still holds it -- with SO_EXCLUSIVEADDRUSE
    that bind fails outright, so the mascot would simply vanish on switch
    (WinError 10048; seen intermittently until 2026-09-10). The outgoing
    process now closes its socket first, and this retry covers whatever else
    can hold the port for a moment.

    Raises OSError if the port is still taken when the window closes -- app.py
    turns that into a visible error dialog rather than letting a second
    instance start.
    """
    handler_cls = make_handler(speech_queue)
    deadline = time.monotonic() + BIND_RETRY_SECONDS
    while True:
        try:
            server = ExclusiveHTTPServer(("127.0.0.1", port), handler_cls)
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            logger.info("ポート %d がまだ塞がっているので待つのだ", port)
            time.sleep(BIND_RETRY_INTERVAL_SECONDS)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

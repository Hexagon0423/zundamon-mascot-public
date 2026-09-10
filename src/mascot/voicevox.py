"""Thin wrapper around the local VOICEVOX HTTP API.

Takes an injectable `requests`-like session so the HTTP calls can be
mocked in tests without a running VOICEVOX instance.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from mascot.config import VoiceParams


@dataclass
class VoicevoxClient:
    base_url: str
    session: requests.Session

    def audio_query(self, text: str, voice: VoiceParams) -> dict:
        resp = self.session.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": voice.speaker},
            timeout=10,
        )
        resp.raise_for_status()
        query = resp.json()
        query["speedScale"] = voice.speed_scale
        query["pitchScale"] = voice.pitch_scale
        query["intonationScale"] = voice.intonation_scale
        query["volumeScale"] = voice.volume_scale
        return query

    def synthesis(self, audio_query: dict, voice: VoiceParams) -> bytes:
        resp = self.session.post(
            f"{self.base_url}/synthesis",
            params={"speaker": voice.speaker},
            json=audio_query,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content

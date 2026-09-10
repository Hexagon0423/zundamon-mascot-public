"""Checks against a real running VOICEVOX. Skipped if it isn't up.

The lipsync timeline is computed from audio_query metadata, but the mouth is
supposed to line up with the WAV that /synthesis returns. Nothing in the unit
tests proves those two agree -- if the timeline model were wrong (a missing
prePhonemeLength, a mishandled speedScale), the unit tests would still pass
and the mouth would simply drift out of sync with the voice. These compare
the computed timeline against the actual audio.
"""

from __future__ import annotations

import io
import wave

import pytest
import requests

from mascot.config import VoiceParams
from mascot.lipsync import build_timeline
from mascot.voicevox import VoicevoxClient

BASE_URL = "http://127.0.0.1:50021"
TEXT = "こんにちはなのだ、ずんだもんなのだ。今日はいい天気なのだ。"


def _voicevox_available() -> bool:
    try:
        return requests.get(f"{BASE_URL}/version", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(
    not _voicevox_available(), reason="VOICEVOX が起動していないのでスキップ"
)


@pytest.fixture(scope="module")
def client():
    return VoicevoxClient(base_url=BASE_URL, session=requests.Session())


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        return wav.getnframes() / wav.getframerate()


@pytest.mark.parametrize("speed_scale", [1.0, 1.5])
def test_timeline_end_matches_actual_audio_length(client, speed_scale):
    voice = VoiceParams(speaker=1, speed_scale=speed_scale)
    query = client.audio_query(TEXT, voice)
    wav_bytes = client.synthesis(query, voice)

    timeline = build_timeline(query)
    expected = timeline[-1].end + query["postPhonemeLength"] / speed_scale
    actual = _wav_duration_seconds(wav_bytes)

    # Within 50ms: at ~30fps redraw that's under two frames of drift.
    assert actual == pytest.approx(expected, abs=0.05), (
        f"timeline predicts {expected:.3f}s but the audio is {actual:.3f}s "
        "-- the mouth would drift out of sync with the voice"
    )


def test_synthesized_audio_is_not_silent(client):
    """A silent WAV would still 'play' fine and look correct in the logs."""
    voice = VoiceParams(speaker=1)
    query = client.audio_query(TEXT, voice)
    wav_bytes = client.synthesis(query, voice)

    with wave.open(io.BytesIO(wav_bytes)) as wav:
        assert wav.getsampwidth() == 2, "16bit PCM を想定している"
        frames = wav.readframes(wav.getnframes())

    peak = max(
        abs(int.from_bytes(frames[i : i + 2], "little", signed=True))
        for i in range(0, len(frames), 2)
    )
    assert peak > 1000, f"音声がほぼ無音なのだ (peak={peak})"

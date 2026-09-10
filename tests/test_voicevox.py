from unittest.mock import MagicMock

from mascot.config import VoiceParams
from mascot.voicevox import VoicevoxClient


def _make_response(json_data=None, content=b""):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    resp.content = content
    return resp


def test_audio_query_applies_voice_params_and_hits_correct_url():
    session = MagicMock()
    session.post.return_value = _make_response(
        json_data={"speedScale": 1.0, "pitchScale": 0.0, "intonationScale": 1.0, "volumeScale": 1.0}
    )
    client = VoicevoxClient(base_url="http://127.0.0.1:50021", session=session)
    voice = VoiceParams(speaker=3, speed_scale=1.3, pitch_scale=0.1, intonation_scale=1.2, volume_scale=0.9)

    result = client.audio_query("こんにちは", voice)

    session.post.assert_called_once_with(
        "http://127.0.0.1:50021/audio_query",
        params={"text": "こんにちは", "speaker": 3},
        timeout=10,
    )
    assert result["speedScale"] == 1.3
    assert result["pitchScale"] == 0.1
    assert result["intonationScale"] == 1.2
    assert result["volumeScale"] == 0.9


def test_synthesis_posts_query_and_returns_wav_bytes():
    session = MagicMock()
    session.post.return_value = _make_response(content=b"RIFF....WAVEfmt ")
    client = VoicevoxClient(base_url="http://127.0.0.1:50021", session=session)
    voice = VoiceParams(speaker=1)
    query = {"speedScale": 1.0}

    wav = client.synthesis(query, voice)

    session.post.assert_called_once_with(
        "http://127.0.0.1:50021/synthesis",
        params={"speaker": 1},
        json=query,
        timeout=30,
    )
    assert wav == b"RIFF....WAVEfmt "

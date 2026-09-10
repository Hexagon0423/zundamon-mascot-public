import json
from pathlib import Path

import pytest

from mascot.lipsync import (
    TimelineSegment,
    apply_min_hold,
    build_timeline,
    vowel_at,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "audio_query_sample.json"


@pytest.fixture
def audio_query():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_build_timeline_starts_after_pre_phoneme_length(audio_query):
    timeline = build_timeline(audio_query)
    assert timeline[0].start == pytest.approx(audio_query["prePhonemeLength"])


def test_build_timeline_covers_every_mora_and_pause(audio_query):
    timeline = build_timeline(audio_query)
    expected_count = sum(
        len(phrase["moras"]) + (1 if phrase.get("pause_mora") else 0)
        for phrase in audio_query["accent_phrases"]
    )
    assert len(timeline) == expected_count


def test_build_timeline_segments_are_contiguous(audio_query):
    timeline = build_timeline(audio_query)
    for prev, nxt in zip(timeline, timeline[1:]):
        assert prev.end == pytest.approx(nxt.start)


def test_build_timeline_keeps_n_and_pause_as_vowels(audio_query):
    """Vowels stay raw here; mapping them to mouth images is the art set's job."""
    timeline = build_timeline(audio_query)
    # first phrase's 2nd mora is "ン" (N), and its pause_mora is "、" (pau)
    assert timeline[1].vowel == "N"
    first_phrase_mora_count = len(audio_query["accent_phrases"][0]["moras"])
    assert timeline[first_phrase_mora_count].vowel == "pau"


def test_build_timeline_uses_the_raw_vowel():
    audio_query = {
        "prePhonemeLength": 0.0,
        "speedScale": 1.0,
        "accent_phrases": [
            {
                "moras": [
                    {"consonant": "k", "consonant_length": 0.1, "vowel": "a", "vowel_length": 0.2},
                ],
                "pause_mora": None,
            }
        ],
    }
    timeline = build_timeline(audio_query)
    assert len(timeline) == 1
    assert timeline[0].start == pytest.approx(0.0)
    assert timeline[0].end == pytest.approx(0.3)
    assert timeline[0].vowel == "a"


def test_speed_scale_shrinks_durations():
    audio_query = {
        "prePhonemeLength": 0.2,
        "speedScale": 2.0,
        "accent_phrases": [
            {
                "moras": [
                    {"consonant": None, "consonant_length": None, "vowel": "a", "vowel_length": 0.4},
                ],
                "pause_mora": None,
            }
        ],
    }
    timeline = build_timeline(audio_query)
    assert timeline[0].start == pytest.approx(0.1)
    assert timeline[0].end == pytest.approx(0.3)


def test_apply_min_hold_merges_short_segment_into_previous():
    timeline = [
        TimelineSegment(0.0, 0.2, "a"),
        TimelineSegment(0.2, 0.22, "i"),  # 20ms, shorter than default hold
        TimelineSegment(0.22, 0.4, "u"),
    ]
    merged = apply_min_hold(timeline, min_hold_seconds=0.06)
    assert merged == [
        TimelineSegment(0.0, 0.22, "a"),
        TimelineSegment(0.22, 0.4, "u"),
    ]


def test_apply_min_hold_keeps_first_segment_even_if_short():
    timeline = [TimelineSegment(0.0, 0.01, "a"), TimelineSegment(0.01, 0.2, "i")]
    merged = apply_min_hold(timeline, min_hold_seconds=0.06)
    assert merged[0].vowel == "a"


def test_vowel_at_before_and_after_timeline_is_closed():
    timeline = [TimelineSegment(0.1, 0.3, "a")]
    assert vowel_at(timeline, 0.0) == "pau"
    assert vowel_at(timeline, 0.05) == "pau"
    assert vowel_at(timeline, 1.0) == "pau"


def test_vowel_at_within_segment():
    timeline = [TimelineSegment(0.1, 0.3, "a"), TimelineSegment(0.3, 0.5, "i")]
    assert vowel_at(timeline, 0.1) == "a"
    assert vowel_at(timeline, 0.29) == "a"
    assert vowel_at(timeline, 0.3) == "i"


def test_vowel_at_empty_timeline_is_closed():
    assert vowel_at([], 0.5) == "pau"

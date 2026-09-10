"""Pure functions: VOICEVOX audio_query -> a timeline of vowels.

No audio playback and no Qt here on purpose, so the timing math (the part
most likely to be subtly wrong) can be tested without a speaker or a GUI.

The timeline stays in terms of *vowels*, not image names. Which mouth image
a vowel corresponds to depends on the art set and lives in its manifest --
see assets.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# VOICEVOX vowel codes. Lowercase ones are the five Japanese vowels; "N" is
# ん, "pau" a pause, "cl" a glottal stop (っ).
SILENT_VOWEL = "pau"

DEFAULT_MIN_HOLD_SECONDS = 0.06


@dataclass(frozen=True)
class TimelineSegment:
    start: float
    end: float
    vowel: str


def build_timeline(audio_query: dict) -> list[TimelineSegment]:
    """Turn an /audio_query response into a vowel timeline.

    Each mora's segment starts at the beginning of its consonant (mouth
    already shaping up) and lasts through its vowel. speedScale divides all
    durations since it scales actual playback speed.
    """
    speed_scale = audio_query.get("speedScale", 1.0) or 1.0
    t = audio_query.get("prePhonemeLength", 0.0) / speed_scale

    segments: list[TimelineSegment] = []
    for phrase in audio_query["accent_phrases"]:
        for mora in phrase["moras"]:
            consonant_length = mora.get("consonant_length") or 0.0
            vowel_length = mora.get("vowel_length") or 0.0
            duration = (consonant_length + vowel_length) / speed_scale
            if duration > 0:
                segments.append(TimelineSegment(t, t + duration, mora.get("vowel") or SILENT_VOWEL))
                t += duration

        pause_mora = phrase.get("pause_mora")
        if pause_mora is not None:
            duration = (pause_mora.get("vowel_length") or 0.0) / speed_scale
            if duration > 0:
                segments.append(TimelineSegment(t, t + duration, SILENT_VOWEL))
                t += duration

    return segments


def apply_min_hold(
    timeline: list[TimelineSegment], min_hold_seconds: float = DEFAULT_MIN_HOLD_SECONDS
) -> list[TimelineSegment]:
    """Merge segments shorter than min_hold_seconds into the previous one.

    Without this, short morae flash the mouth open and shut for a couple of
    frames, which reads as flicker rather than speech. The first segment is
    never merged away (nothing to extend).
    """
    result: list[TimelineSegment] = []
    for seg in timeline:
        if result and (seg.end - seg.start) < min_hold_seconds:
            result[-1] = replace(result[-1], end=seg.end)
        else:
            result.append(seg)
    return result


def vowel_at(timeline: list[TimelineSegment], elapsed_seconds: float) -> str:
    """Which vowel is being spoken at a given elapsed time.

    Silent before the timeline starts and after it ends.
    """
    if not timeline or elapsed_seconds < timeline[0].start:
        return SILENT_VOWEL
    for seg in timeline:
        if seg.start <= elapsed_seconds < seg.end:
            return seg.vowel
    return SILENT_VOWEL

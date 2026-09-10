import random

from mascot.live2d_gestures import GESTURES, IDLE_SCHEDULE, available_at, duration
from mascot.live2d_motions import (
    EXPRESSION_HOLD_SECONDS,
    IDLE_GESTURE_MAX_SECONDS,
    IDLE_GESTURE_MIN_SECONDS,
    next_idle_delay,
)

SCHEDULED = {name for _, _, names in IDLE_SCHEDULE for name in names}


def test_idle_delay_stays_inside_its_range():
    rng = random.Random(0)
    delays = [next_idle_delay(rng) for _ in range(200)]
    assert all(IDLE_GESTURE_MIN_SECONDS <= d <= IDLE_GESTURE_MAX_SECONDS for d in delays)


def test_idle_delay_is_not_a_fixed_interval():
    """A metronome is what got the PNG backend's idle animation rejected."""
    rng = random.Random(0)
    assert len({round(next_idle_delay(rng), 3) for _ in range(20)}) > 1


def test_expression_is_released_promptly_after_speech():
    """The clock only starts once the mouth stops, so this is the pause after
    an utterance, not its length. Long enough to not cut the last syllable,
    short enough that the pose reads as part of the sentence."""
    assert 0.3 <= EXPRESSION_HOLD_SECONDS <= 5.0


def test_idle_gestures_are_rare_compared_to_how_long_they_last():
    """Gesture time has to stay a small fraction of idle time.

    Back-to-back gestures would be continuous idle animation by another name,
    which this mascot's owner has rejected three times.
    """
    longest = max(duration(GESTURES[name]) for name in SCHEDULED)
    assert IDLE_GESTURE_MIN_SECONDS > longest * 5


def test_schedule_covers_every_hour_exactly_once():
    """A gap would silently switch idling off; an overlap would make the band
    that happens to be listed first win, which is not obvious from reading it.
    """
    covered = [hour for start, end, _ in IDLE_SCHEDULE for hour in range(start, end)]
    assert sorted(covered) == list(range(24))


def test_every_band_offers_something():
    for start, end, names in IDLE_SCHEDULE:
        assert names, f"{start}時台から{end}時台が空なのだ"


def test_scheduled_gestures_are_all_defined():
    unknown = SCHEDULED - set(GESTURES)
    assert not unknown, f"中身の無い仕草があるのだ: {sorted(unknown)}"


def test_sleepy_gestures_keep_to_their_hours():
    """The yawn is the morning one and the doze the night one; neither should
    show up in the middle of the working day."""
    assert "yawn" in available_at(8)
    assert "doze" in available_at(3)
    assert "doze" in available_at(14)
    assert "doze" in available_at(23)
    for hour in (10, 11, 12, 16, 20):
        assert "yawn" not in available_at(hour), hour
        assert "doze" not in available_at(hour), hour


def test_the_yawn_and_the_doze_never_share_an_hour():
    for hour in range(24):
        allowed = available_at(hour)
        assert not ("yawn" in allowed and "doze" in allowed), hour

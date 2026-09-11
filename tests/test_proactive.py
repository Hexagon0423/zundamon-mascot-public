import random

import pytest

from mascot import proactive
from mascot.window import EXPRESSION_PRESETS

ALL_TIER_LINES = [
    line for pool in proactive.IDLE_CHATTER_BY_TIER.values() for line in pool
]
ALL_LINES = ALL_TIER_LINES + list(proactive.WELCOME_BACK) + list(proactive.MORNING_GREETING)


def test_every_line_uses_a_real_expression():
    unknown = {expression for _, expression in ALL_LINES} - set(EXPRESSION_PRESETS)
    assert not unknown, f"存在しない表情名なのだ: {sorted(unknown)}"


def test_lines_are_short_enough_to_be_spoken_whole():
    for line, _ in ALL_LINES:
        assert len(line) <= 20, line


def test_lines_stay_in_character():
    for line, _ in ALL_LINES:
        assert "のだ" in line, line


@pytest.mark.parametrize("tier", sorted(proactive.IDLE_CHATTER_BY_TIER))
def test_each_tier_has_no_duplicate_lines(tier):
    pool = proactive.IDLE_CHATTER_BY_TIER[tier]
    lines = [line for line, _ in pool]
    assert len(lines) == len(set(lines)), tier


@pytest.mark.parametrize("tier", sorted(proactive.IDLE_CHATTER_BY_TIER))
def test_each_tier_has_enough_variety(tier):
    """A single canned line per tier would read as a broken loop."""
    assert len(proactive.IDLE_CHATTER_BY_TIER[tier]) >= 6, tier


def test_welcome_back_has_no_duplicate_lines():
    lines = [line for line, _ in proactive.WELCOME_BACK]
    assert len(lines) == len(set(lines))


def test_morning_greeting_has_no_duplicate_lines():
    lines = [line for line, _ in proactive.MORNING_GREETING]
    assert len(lines) == len(set(lines))


def test_morning_greeting_hours_are_actually_morning():
    """Sanity bound: a misconfigured range here would fire "おはよう" at
    an hour that clearly isn't morning."""
    assert proactive.MORNING_GREETING_HOURS <= set(range(4, 12))


def test_pick_morning_greeting_returns_a_pair_from_the_table():
    rng = random.Random(0)
    assert proactive.pick_morning_greeting(rng) in proactive.MORNING_GREETING


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "new"),
        (6, "new"),
        (7, "settling_in"),
        (29, "settling_in"),
        (30, "close"),
        (99, "close"),
        (100, "old_friends"),
        (10000, "old_friends"),
    ],
)
def test_familiarity_tier_boundaries(days, expected):
    assert proactive.familiarity_tier(days) == expected


def test_pick_idle_chatter_returns_something_from_the_right_tier():
    rng = random.Random(0)
    for days, tier in ((0, "new"), (10, "settling_in"), (50, "close"), (200, "old_friends")):
        chosen = proactive.pick_idle_chatter(days, rng)
        assert chosen in proactive.IDLE_CHATTER_BY_TIER[tier]


def test_pick_welcome_back_returns_a_pair_from_the_table():
    rng = random.Random(0)
    assert proactive.pick_welcome_back(rng) in proactive.WELCOME_BACK


def test_check_delay_stays_inside_its_range():
    rng = random.Random(0)
    delays = [proactive.next_check_delay(rng) for _ in range(200)]
    lo, hi = proactive.CHECK_INTERVAL_RANGE_S
    assert all(lo <= d <= hi for d in delays)


def test_check_delay_is_not_a_fixed_interval():
    """A metronome is what got the PNG backend's idle animation rejected."""
    rng = random.Random(0)
    assert len({round(proactive.next_check_delay(rng), 3) for _ in range(20)}) > 1


def test_should_fire_is_probabilistic_not_always_or_never():
    rng = random.Random(0)
    results = {proactive.should_fire(rng) for _ in range(200)}
    assert results == {True, False}


def test_min_silence_is_generously_long():
    """A typo here could turn this into a near-metronome -- the failure mode
    this project has explicitly rejected three times for continuous idle
    motion (see live2d_gestures.py)."""
    assert proactive.MIN_SILENCE_SECONDS >= 5 * 60


def test_welcome_back_threshold_is_hours_not_minutes():
    """A screen lock or a quick reboot shouldn't count as a real absence."""
    assert proactive.WELCOME_BACK_THRESHOLD_SECONDS >= 60 * 60

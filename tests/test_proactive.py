import random
from datetime import datetime

import pytest

from mascot import proactive
from mascot.window import EXPRESSION_PRESETS

# A Tuesday: no entry in WEEKDAY_LINES, so tests that don't care about weekday
# flavor can hold that variable still without it silently depending on
# whatever day the test suite happens to run on (2026-09-11 is a Friday,
# which does have lines -- this bit a first draft of these tests).
A_WEEKDAY_WITH_NO_SPECIAL_LINES = datetime(2026, 9, 8, 14, 0, 0)  # Tue

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
        chosen = proactive.pick_idle_chatter(days, rng, now=A_WEEKDAY_WITH_NO_SPECIAL_LINES)
        assert chosen in proactive.IDLE_CHATTER_BY_TIER[tier]


def test_pick_idle_chatter_defaults_to_now_when_not_given():
    """No now= means "whatever day it actually is" -- exercised for coverage
    only; the deterministic tier-selection test above pins the day instead."""
    proactive.pick_idle_chatter(0, random.Random(0))  # must not raise


@pytest.mark.parametrize("tier", sorted(proactive.SILENCE_TEMPLATES_BY_TIER))
def test_silence_templates_fit_once_a_plausible_duration_is_filled_in(tier):
    for template, expression in proactive.SILENCE_TEMPLATES_BY_TIER[tier]:
        for minutes in (1, 20, 45, 90, 120):
            line = template.format(minutes=minutes)
            assert len(line) <= 20, line
            assert "のだ" in line, line
        assert expression in EXPRESSION_PRESETS, expression


def test_pick_idle_chatter_can_state_the_real_silence_duration():
    """With the roll forced to succeed and no weekday line in the way, the
    duration-stating branch is what actually gets used."""
    rng = random.Random(0)
    line, expression = proactive.pick_idle_chatter(
        0,
        rng,
        now=A_WEEKDAY_WITH_NO_SPECIAL_LINES,
        silence_seconds=42 * 60,
    )
    formatted = {t.format(minutes=42) for t, _ in proactive.SILENCE_TEMPLATES_BY_TIER["new"]}
    # Not guaranteed to land in the silence branch every single call (it's
    # probabilistic) -- draw enough times that at least one does.
    lines = {
        proactive.pick_idle_chatter(
            0, random.Random(i), now=A_WEEKDAY_WITH_NO_SPECIAL_LINES, silence_seconds=42 * 60
        )[0]
        for i in range(50)
    }
    assert lines & formatted, "40回試して一度も無音時間を言わなかったのだ"


def test_pick_idle_chatter_rounds_silence_down_to_whole_minutes():
    rng = random.Random(0)
    for i in range(50):
        line, _ = proactive.pick_idle_chatter(
            0, random.Random(i), now=A_WEEKDAY_WITH_NO_SPECIAL_LINES, silence_seconds=125
        )
        assert "3分" not in line  # 125s = 2分5秒, must not round up to 3


@pytest.mark.parametrize("weekday", sorted(proactive.WEEKDAY_LINES))
def test_weekday_lines_fit_and_stay_in_character(weekday):
    for line, expression in proactive.WEEKDAY_LINES[weekday]:
        assert len(line) <= 20, line
        assert "のだ" in line, line
        assert expression in EXPRESSION_PRESETS, expression


def test_weekdays_without_special_lines_have_nothing_to_say():
    """Deliberate: forcing content on an ordinary Tuesday would be worse than
    just falling through to the tier line."""
    ordinary_weekdays = set(range(7)) - set(proactive.WEEKDAY_LINES)
    assert ordinary_weekdays, "曜日フレーバーが全曜日を埋めてしまっているのだ"


def test_pick_idle_chatter_can_use_a_weekday_line():
    friday = datetime(2026, 9, 11, 14, 0, 0)
    lines = {
        proactive.pick_idle_chatter(0, random.Random(i), now=friday, silence_seconds=None)[0]
        for i in range(50)
    }
    friday_lines = {line for line, _ in proactive.WEEKDAY_LINES[4]}
    assert lines & friday_lines, "50回試して一度も金曜日の台詞が出なかったのだ"


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

import random

from mascot import reactions
from mascot.window import EXPRESSION_PRESETS

ALL_LINES = reactions.REACTIONS + reactions.MORNING_ONLY + reactions.NIGHT_ONLY


def test_every_reaction_uses_a_real_expression():
    """An unknown name fails silently -- the mascot just doesn't change face."""
    unknown = {expression for _, expression in ALL_LINES} - set(EXPRESSION_PRESETS)
    assert not unknown, f"存在しない表情名なのだ: {sorted(unknown)}"


def test_lines_are_short_enough_to_be_spoken_whole():
    """say.sh truncates at 70 characters; a reaction should be nowhere near."""
    for line, _ in ALL_LINES:
        assert len(line) <= 20, line


def test_reactions_stay_in_character():
    for line, _ in ALL_LINES:
        assert "のだ" in line, line


def test_no_line_is_written_twice():
    lines = [line for line, _ in ALL_LINES]
    assert len(lines) == len(set(lines))


def test_the_time_bound_lines_only_show_up_in_their_hours():
    morning = set(reactions.MORNING_ONLY)
    night = set(reactions.NIGHT_ONLY)
    assert morning <= set(reactions.available_at(8))
    assert night <= set(reactions.available_at(23))
    for hour in (12, 15, 19):
        assert not (morning & set(reactions.available_at(hour))), hour
        assert not (night & set(reactions.available_at(hour))), hour


def test_the_anytime_lines_are_available_at_every_hour():
    for hour in range(24):
        assert set(reactions.REACTIONS) <= set(reactions.available_at(hour)), hour


def test_pick_returns_a_pair_suitable_for_the_hour():
    rng = random.Random(0)
    for hour in (3, 8, 14):
        assert reactions.pick(hour, rng) in reactions.available_at(hour)


def test_there_is_enough_variety_to_not_repeat_obviously():
    assert len(reactions.REACTIONS) >= 20
    assert len({expression for _, expression in reactions.REACTIONS}) >= 10

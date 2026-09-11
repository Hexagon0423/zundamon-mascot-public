from datetime import date

import pytest

from mascot.companion import (
    CompanionState,
    MILESTONES,
    days_together,
    due_milestone,
    load_companion_state,
    save_companion_state,
)
from mascot.window import EXPRESSION_PRESETS


def test_load_missing_file_returns_defaults(tmp_path):
    state = load_companion_state(tmp_path / "does_not_exist.json")
    assert state == CompanionState()


def test_load_corrupt_file_falls_back_to_defaults(tmp_path):
    """A pythonw autostart with no console must never crash on a bad file."""
    path = tmp_path / "companion.json"
    path.write_text("{not valid json", encoding="utf-8")
    state = load_companion_state(path)
    assert state == CompanionState()


def test_load_file_with_wrong_shape_falls_back_to_defaults(tmp_path):
    path = tmp_path / "companion.json"
    path.write_text('"just a string, not an object"', encoding="utf-8")
    state = load_companion_state(path)
    assert state == CompanionState()


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "companion.json"
    original = CompanionState(
        first_seen="2026-09-11", last_seen_at="2026-09-11T10:00:00", celebrated_milestones=[1, 7]
    )
    save_companion_state(original, path)
    loaded = load_companion_state(path)
    assert loaded == original


def test_days_together_counts_from_first_seen():
    state = CompanionState(first_seen="2026-09-11")
    assert days_together(state, today=date(2026, 9, 20)) == 9


def test_days_together_is_zero_on_the_first_day():
    state = CompanionState(first_seen="2026-09-11")
    assert days_together(state, today=date(2026, 9, 11)) == 0


def test_days_together_is_zero_with_no_first_seen():
    assert days_together(CompanionState()) == 0


def test_milestones_use_real_expressions():
    unknown = {expression for _, _, expression in MILESTONES} - set(EXPRESSION_PRESETS)
    assert not unknown, f"存在しない表情名なのだ: {sorted(unknown)}"


def test_milestones_are_short_and_in_character():
    for _, line, _ in MILESTONES:
        assert len(line) <= 20, line
        assert "のだ" in line, line


def test_milestone_days_are_strictly_increasing():
    days = [day for day, _, _ in MILESTONES]
    assert days == sorted(days)
    assert len(days) == len(set(days))


def test_due_milestone_fires_once_then_not_again():
    """day1 is the first unreached milestone at 7 days together (day7 exists
    too, but due_milestone always returns the earliest not-yet-celebrated
    one -- see test_due_milestone_skips_ahead_without_stacking)."""
    state = CompanionState(first_seen="2026-09-01")
    today = date(2026, 9, 8)  # 7 days together
    milestone = due_milestone(state, today)
    assert milestone is not None
    day, _, _ = milestone
    assert day == 1
    state.celebrated_milestones.append(day)
    second = due_milestone(state, today)
    assert second is not None
    assert second[0] == 7
    state.celebrated_milestones.append(second[0])
    assert due_milestone(state, today) is None


def test_due_milestone_skips_ahead_without_stacking():
    """A long gap between runs shouldn't announce every skipped milestone at
    once -- that would read as spam."""
    state = CompanionState(first_seen="2025-01-01")
    today = date(2026, 6, 1)  # well past every milestone
    first = due_milestone(state, today)
    assert first is not None
    day, _, _ = first
    assert day == MILESTONES[0][0]
    state.celebrated_milestones.append(day)
    second = due_milestone(state, today)
    assert second is not None
    assert second[0] == MILESTONES[1][0]


def test_due_milestone_returns_none_before_any_milestone_is_reached():
    state = CompanionState(first_seen="2026-09-11")
    assert due_milestone(state, today=date(2026, 9, 11)) is None

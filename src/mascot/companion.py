"""Persisted sense of 'how long we've been together' and milestone lines.

Mirrors config.py's load/save idiom (JSON, graceful fallback on any read
error) because this file is read on every pythonw autostart and a corrupt or
missing file must never crash startup -- it should just look like day 1.

`first_seen` semantics (read this before changing anything): it's the date
this file was first created, not the mascot's actual install/creation date.
There is no reliable runtime signal for the latter (file mtimes get touched
by reinstalls, git clone, asset-set switches), and guessing would risk a
wrong number being worse than an honest "day 1." Existing users will restart
their day count from whenever this feature ships -- documented in CLAUDE.md
so it isn't a surprise.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_COMPANION_PATH = Path(__file__).resolve().parent.parent.parent / "companion.json"


@dataclass
class CompanionState:
    first_seen: str | None = None  # ISO date, e.g. "2026-09-11"
    last_seen_at: str | None = None  # ISO datetime, for the welcome-back gap check
    celebrated_milestones: list[int] = field(default_factory=list)  # day-counts already shown


def load_companion_state(path: Path = DEFAULT_COMPANION_PATH) -> CompanionState:
    if not path.exists():
        return CompanionState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CompanionState(
            first_seen=data.get("first_seen"),
            last_seen_at=data.get("last_seen_at"),
            celebrated_milestones=list(data.get("celebrated_milestones", [])),
        )
    except (json.JSONDecodeError, TypeError, ValueError, OSError, AttributeError):
        logger.exception("%s を読めなかったので初回起動として扱う", path)
        return CompanionState()


def save_companion_state(state: CompanionState, path: Path = DEFAULT_COMPANION_PATH) -> None:
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")


def is_new_calendar_day(state: CompanionState, now: datetime | None = None) -> bool:
    """True the first time this is checked on a given calendar day.

    Used to tell a routine overnight gap (PC off, back on the next morning)
    apart from a real absence: both can be several hours, but only one of
    them crosses into a new day. `state.last_seen_at` being None (never run
    before) is not "a new day" -- there's no previous day to have crossed
    from, and the very-first-run case is handled separately.
    """
    if state.last_seen_at is None:
        return False
    last = datetime.fromisoformat(state.last_seen_at)
    return last.date() < (now or datetime.now()).date()


def days_together(state: CompanionState, today: date | None = None) -> int:
    """0 on the day first_seen is recorded, counting up from there."""
    if state.first_seen is None:
        return 0
    first = date.fromisoformat(state.first_seen)
    return ((today or date.today()) - first).days


# Milestone day-counts and their lines. Curated, not a formula: round numbers
# a person actually notices ("a week", "a month") read as intentional; an
# arbitrary sequence (powers of two: 1, 2, 4, 8, 16, 32, 64...) would land on
# meaningless days like day 16. Chosen to span first-week novelty through
# long-term companionship without ever repeating -- append more rows to add
# tiers later, everything below already generalizes to any list length.
MILESTONES: tuple[tuple[int, str, str], ...] = (
    (1, "一緒に1日なのだ!", "happy"),
    (7, "一緒に1週間なのだ!", "delighted"),
    (30, "一緒に1ヶ月なのだ!", "celebrating"),
    (100, "一緒に100日なのだ!", "celebrating"),
    (365, "一緒に1年なのだ!", "celebrating"),
)


def due_milestone(
    state: CompanionState, today: date | None = None
) -> tuple[int, str, str] | None:
    """The first not-yet-celebrated milestone whose day-count has been
    reached, or None. Only one is returned per call even if several were
    skipped (e.g. the app wasn't run for a while) -- catching up on all of
    them at once would read as spam, and the caller is expected to record
    the returned day in `celebrated_milestones` so a later call moves on to
    the next one rather than repeating this one.
    """
    reached = days_together(state, today)
    for day, line, expression in MILESTONES:
        if day <= reached and day not in state.celebrated_milestones:
            return (day, line, expression)
    return None

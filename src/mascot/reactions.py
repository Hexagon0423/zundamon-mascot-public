"""What the mascot says when it's poked.

Clicking the mascot while it is quiet makes it react: a short line, spoken
through the ordinary speech path, with an expression to match. The lines are
deliberately content-free -- the mascot has no idea why it was clicked, so
anything specific would be wrong.

Kept out of the window class so the table is testable without a GL context,
and so adding a line stays a one-line edit.
"""

from __future__ import annotations

import random

# (line, expression). Every expression name here has to exist in both
# backends' preset tables; a test holds that. Spread across moods on purpose:
# one canned response reads as a broken loop, not a character.
REACTIONS: tuple[tuple[str, str], ...] = (
    # 驚き・とまどい
    ("なんなのだ?", "confused"),
    ("わわっ、びっくりしたのだ!", "shock"),
    ("えっと、どうしたのだ?", "thinking"),
    ("ボクに何か用なのだ?", "skeptical"),
    ("うーんと、なんだったのだ…?", "dazed"),
    # 照れ・じゃれあい
    ("くすぐったいのだ!", "shy"),
    ("そ、そんなに見つめないでほしいのだ", "shy"),
    ("つついても何も出ないのだ", "casual"),
    ("ボクはずんだ餅じゃないのだ!", "warning_no"),
    ("いたずらはだめなのだ!", "warning_no"),
    ("こら、仕事に戻るのだ!", "angry"),
    # 元気・喜び
    ("呼んだのだ?", "greeting"),
    ("ボクはここにいるのだ!", "happy"),
    ("元気にしてるのだ!", "delighted"),
    ("今日もいい感じなのだ!", "proud"),
    ("なでてくれてもいいのだ", "casual_lean"),
    ("ボク、ちゃんと働いてるのだ!", "confident"),
    # 相手を気づかう
    ("休憩するのだ?", "casual"),
    ("無理はよくないのだ", "worried"),
    ("水分とったほうがいいのだ", "explaining"),
    ("肩、こってないのだ?", "worried"),
    ("いい姿勢で座るのだ!", "explaining"),
    # 待機・ひまつぶし
    ("ひまなのだ〜", "patient_wait"),
    ("ボクのこと忘れてないのだ?", "disappointed"),
    ("何か手伝えることあるのだ?", "greeting"),
    ("画面の前にいるのだ", "normal"),
    # 自己言及
    ("ボクの中身はPythonなのだ", "explaining"),
    ("ちゃんと動いてるのだ、たぶん", "relieved"),
    ("バグじゃないのだ、仕様なのだ", "confident"),
)

# Reactions that only suit part of the day, same idea as the idle gestures:
# being told the mascot is sleepy at 2pm reads as a non-sequitur.
MORNING_ONLY: tuple[tuple[str, str], ...] = (
    ("おはようなのだ!", "greeting"),
    ("今日もがんばるのだ!", "effort"),
    ("ふぁ…まだ眠いのだ…", "patient_wait"),
    ("朝ごはん食べたのだ?", "thinking"),
)

NIGHT_ONLY: tuple[tuple[str, str], ...] = (
    ("ふぁ…眠いのだ…", "patient_wait"),
    ("もう寝たほうがいいのだ", "worried"),
    ("夜更かしはだめなのだ!", "warning_no"),
    ("ボクも眠くなってきたのだ", "patient_wait"),
    ("おつかれさまなのだ", "relieved"),
)

MORNING_HOURS = frozenset({7, 8, 9})
NIGHT_HOURS = frozenset({22, 23, 0, 1, 2, 3, 4, 5, 6})

# How often, during morning/night hours, the time-bound pool wins over a plain
# anytime line. Weighted deliberately rather than left to a uniform choice
# over the merged pool: 4 morning lines (or 5 night lines) sitting among 29
# anytime ones would only come up ~12-15% of the time by chance, which reads
# as a rare easter egg rather than the mascot actually noticing the time of
# day (2026-09-11, raised after seeing it in practice).
TIME_BOUND_PROBABILITY = 0.3


def available_at(hour: int) -> tuple[tuple[str, str], ...]:
    """The lines that suit `hour` (0-23): the anytime ones plus the time-bound
    ones for that part of the day. Describes what's *possible*, not how often
    each is picked -- see pick() for the actual weighting."""
    special = _special_pool(hour)
    return REACTIONS + special if special else REACTIONS


def _special_pool(hour: int) -> tuple[tuple[str, str], ...] | None:
    if hour in MORNING_HOURS:
        return MORNING_ONLY
    if hour in NIGHT_HOURS:
        return NIGHT_ONLY
    return None


def pick(hour: int, rng: random.Random | None = None) -> tuple[str, str]:
    """A (line, expression) pair suitable for `hour`.

    During morning/night hours, the time-bound pool is favored at
    TIME_BOUND_PROBABILITY rather than merged evenly into one big pool --
    otherwise, being a small handful of lines among dozens of anytime ones,
    it would rarely come up at all.
    """
    rng = rng or random
    special = _special_pool(hour)
    if special and rng.random() < TIME_BOUND_PROBABILITY:
        return rng.choice(special)
    return rng.choice(REACTIONS)

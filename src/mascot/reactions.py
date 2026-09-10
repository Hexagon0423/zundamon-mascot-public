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


def available_at(hour: int) -> tuple[tuple[str, str], ...]:
    """The lines that suit `hour` (0-23): the anytime ones plus the time-bound
    ones for that part of the day."""
    if hour in MORNING_HOURS:
        return REACTIONS + MORNING_ONLY
    if hour in NIGHT_HOURS:
        return REACTIONS + NIGHT_ONLY
    return REACTIONS


def pick(hour: int, rng: random.Random | None = None) -> tuple[str, str]:
    """A (line, expression) pair suitable for `hour`."""
    return (rng or random).choice(available_at(hour))

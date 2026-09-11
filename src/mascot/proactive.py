"""What the mascot says when nobody made it. Two flavors: routine idle
chatter, and a one-off "welcome back" line after a real absence.

Everything here is a canned line, no `claude -p` call -- this runs inside the
mascot's own always-running process on a randomized QTimer (proactive_scheduler.py),
not through a Claude Code session, so there is no session cost or context
bloat to guard against (see CLAUDE.md's 機能追加時の設計方針). It's the same
category of thing as the existing idle-gesture timers in window.py /
live2d_window.py, just speaking instead of moving.

Content is deliberately generic: none of these lines reference what the user
is actually doing, since the mascot has no way to know. They're grouped
loosely (bored / wants attention / watching over you / checking in), matching
the categories discussed when this was designed.

Idle chatter is additionally split by how long the mascot and the user have
been "together" (companion.py's day count) into four familiarity tiers, each
with its own tone -- the newer the relationship, the more reserved; the older,
the more casual and teasing. This is a deliberate design choice: the same
"ひまなのだ〜"-shaped content read every day forever would feel static, and a
relationship that never changes undercuts the whole point of tracking days
together in the first place.

Two more pieces of real (if modest) context get folded in, both mechanical --
neither needs an LLM or any data beyond what the mascot's own process already
has:

- **How long the silence actually was.** Sometimes, instead of a generic
  line, the mascot states the real elapsed minutes ("もう40分くらい静かな
  のだ"). Requires the caller to pass how long it's been quiet; falls back to
  a generic tier line if that isn't known.
- **What day it is.** Monday and Friday (start/end of a work week) and the
  weekend get their own occasional lines; the middle of the week doesn't,
  since there's nothing distinct to say about a Wednesday.

Explicitly out of scope for now (discussed and deferred, not forgotten):
reading anything from the user's actual accounts (Gmail etc.) to speak about.
That's a materially bigger feature -- it needs its own explicit consent flow,
a decision about what's even appropriate to surface unprompted, and doesn't
fit the "no personal data, ships in the public template too" shape everything
else in this file has. Worth revisiting deliberately, not folding in here.
"""

from __future__ import annotations

import random
from datetime import datetime

# How the mascot's chatter register loosens up over time. Boundaries are
# round numbers a person actually thinks in (a week, a month, ~3 months),
# matching companion.py's MILESTONES reasoning.
FAMILIARITY_TIERS: tuple[tuple[int, str], ...] = (
    (7, "new"),
    (30, "settling_in"),
    (100, "close"),
    (10**9, "old_friends"),
)


def familiarity_tier(days: int) -> str:
    for threshold, tier in FAMILIARITY_TIERS:
        if days < threshold:
            return tier
    return "old_friends"  # unreachable given the 10**9 sentinel above, kept for clarity


# (line, expression) pairs, grouped by familiarity tier. Each pool mixes the
# four content categories (bored / wants attention / watching over you /
# checking in) at that tier's register -- reserved and a little formal in
# `new`, unmistakably teasing by `old_friends`.
IDLE_CHATTER_BY_TIER: dict[str, tuple[tuple[str, str], ...]] = {
    "new": (
        ("よろしくなのだ、まだ探り探りなのだ", "shy"),
        ("使い方、分かりにくくないのだ?", "worried"),
        ("ボクのこと、覚えてくれてるのだ?", "confused"),
        ("邪魔になってないのだ?", "worried"),
        ("そばにいてもいいのだ?", "shy"),
        ("まだ人見知り中なのだ", "shy"),
        ("よろしくお願いするのだ", "greeting"),
        ("ゆっくり慣れていくのだ", "normal"),
    ),
    "settling_in": (
        ("もうすっかり見慣れたのだ?", "casual"),
        ("そろそろタメ口でもいいのだ?", "casual"),
        ("今日も一緒なのだ、悪い気しないのだ", "happy"),
        ("ひまなのだ〜", "patient_wait"),
        ("何してるのだ?", "thinking"),
        ("たまには話しかけてほしいのだ", "casual"),
        ("ボクも慣れてきたのだ", "confident"),
        ("画面の隅から見てるのだ", "normal"),
    ),
    "close": (
        ("サボってるのだ?お見通しなのだ", "skeptical"),
        ("もう長い付き合いなのだ、遠慮しないのだ", "confident"),
        ("たまにはボクの話も聞くのだ", "casual_lean"),
        ("集中してるのだ?邪魔しちゃったのだ?", "shy"),
        ("なんとなく声かけてみたのだ", "casual"),
        ("根を詰めすぎなのだ、休むのだ", "worried"),
        ("ボク、退屈してないのだ", "proud"),
        ("今日もよろしく頼むのだ", "confident"),
    ),
    "old_friends": (
        ("この日数、ボクらもうベテランなのだ", "proud"),
        ("今さら硬い話し方はしないのだ", "confident"),
        ("ずっとこの調子でいくのだ、よろしくなのだ", "happy"),
        ("またサボってるのだ、いつものことなのだ", "skeptical"),
        ("ボクがいないと物足りないのだ?", "confident"),
        ("長すぎず短すぎず、いい距離感なのだ", "relieved"),
        ("今日も付き合ってやるのだ", "proud"),
        ("いい加減、ボクの扱いにも慣れたのだ?", "casual_lean"),
    ),
}

# Format strings (not plain lines): `{minutes}` is substituted with the real
# elapsed silence, rounded down to a whole minute. Kept per-tier so stating an
# actual duration still carries that tier's register, same as the plain lines
# above. A length/format-validity check runs against a representative value in
# tests, not the raw template, since "≤20 chars" only means something once
# the placeholder is filled in.
SILENCE_TEMPLATES_BY_TIER: dict[str, tuple[tuple[str, str], ...]] = {
    "new": (
        ("もう{minutes}分くらい経ったのだ", "worried"),
        ("{minutes}分、静かに見てたのだ", "shy"),
    ),
    "settling_in": (
        ("もう{minutes}分くらい静かなのだ", "patient_wait"),
        ("{minutes}分もひまなのだ", "casual"),
    ),
    "close": (
        ("もう{minutes}分放置なのだ", "skeptical"),
        ("{minutes}分、ひとりの時間だったのだ", "casual_lean"),
    ),
    "old_friends": (
        ("もう{minutes}分なのだ、薄情なのだ", "disappointed"),
        ("{minutes}分放っておくとはいい度胸なのだ", "proud"),
    ),
}

# How often pick_idle_chatter states the real duration instead of a generic
# line, when it's given one to state. Not every time -- constantly narrating
# the exact minute count would read as a countdown timer, not a character.
SILENCE_TEMPLATE_PROBABILITY = 0.4

# Occasional day-of-week flavor. Only Monday/Friday/weekend get lines: the
# middle of the work week has nothing distinct to say, and forcing content
# where there isn't any would be worse than just falling through to the
# ordinary tier line (which is exactly what happens on Tue-Thu).
WEEKDAY_LINES: dict[int, tuple[tuple[str, str], ...]] = {
    0: (("月曜日なのだ、ぼちぼちいくのだ", "effort"),),  # Monday
    4: (
        ("もう金曜日なのだ、あと少しなのだ!", "delighted"),
        ("週末が見えてきたのだ", "happy"),
    ),  # Friday
    5: (("土曜日なのだ、休むのも仕事なのだ", "relieved"),),  # Saturday
    6: (("日曜日なのだ、のんびりするのだ", "casual"),),  # Sunday
}

# Checked before the silence template and before the plain tier line -- a
# "it's Friday" observation is worth surfacing more readily than a duration
# callout, since it's rarer (fires on 4 of 7 days at most, once per check).
WEEKDAY_LINE_PROBABILITY = 0.3

# Fired once per app run when it's been a long time since the process was
# last ticking (see companion.py's last_seen_at) -- independent of the
# familiarity tier, since "I missed you" reads the same at any relationship
# length.
WELCOME_BACK: tuple[tuple[str, str], ...] = (
    ("ひさしぶりなのだ!", "delighted"),
    ("おかえりなのだ!", "greeting"),
    ("待ってたのだ!", "happy"),
    ("やっと会えたのだ", "relieved"),
)

# Fired instead of WELCOME_BACK when the gap crossing into a new calendar day
# also happens to land in the morning -- a normal "turned the PC off overnight,
# turned it back on" cycle is not a "long time no see," and greeting the most
# routine gap of all with "ひさしぶり" every single morning would cheapen the
# phrase for when it's actually earned (a real multi-day absence). Checked
# separately from WELCOME_BACK_THRESHOLD_SECONDS on purpose: this can fire even
# on a short gap (e.g. restarted the app right after waking the PC) as long as
# it's the first time today and it's morning.
MORNING_GREETING_HOURS = frozenset({5, 6, 7, 8, 9, 10})

MORNING_GREETING: tuple[tuple[str, str], ...] = (
    ("おはようなのだ!", "greeting"),
    ("今日も一日がんばるのだ!", "effort"),
    ("よく眠れたのだ?", "worried"),
    ("今日も元気にいくのだ!", "delighted"),
    ("朝から動いてえらいのだ!", "proud"),
    ("今日はどんな一日になるのだ?", "thinking"),
)

# Below this, the idle-chatter check never fires -- a hard floor, not just a
# low probability, so a typo in the probability constant can't turn this into
# a near-metronome (the failure mode this project has rejected three times
# for continuous PNG-backend idle motion; see live2d_gestures.py).
MIN_SILENCE_SECONDS = 20 * 60

# The check re-arms itself after a random delay in this range each time,
# rather than a fixed interval, for the same reason next_idle_delay() in
# live2d_motions.py is randomized: a fixed cadence reads as mechanical.
CHECK_INTERVAL_RANGE_S = (10 * 60, 25 * 60)

# Even once eligible (silent long enough) and due (the timer fired), only
# fire this often. Combined with MIN_SILENCE_SECONDS and the check interval,
# expected real cadence during continuous silence is roughly once every
# 45-70 minutes -- occasional, never naggy. Tune here if that's off in
# practice (see PLAN.md's 調整したくなったら).
FIRE_PROBABILITY = 0.35

# How long the process must have gone un-ticked before a return counts as a
# real absence rather than a screen lock or a quick reboot.
WELCOME_BACK_THRESHOLD_SECONDS = 4 * 60 * 60


def pick_idle_chatter(
    days_together: int,
    rng: random.Random | None = None,
    *,
    now: datetime | None = None,
    silence_seconds: float | None = None,
) -> tuple[str, str]:
    """A line to speak while idle.

    `now` and `silence_seconds` are both optional context, not required
    inputs -- omitting either just means that flavor of line can't be picked
    this time, falling back to a plain tier line. Priority when more than one
    could apply: weekday flavor first (rarer, so worth surfacing when it's
    there), then a stated duration, then the ordinary tier line.
    """
    rng = rng or random
    tier = familiarity_tier(days_together)

    weekday_lines = WEEKDAY_LINES.get((now or datetime.now()).weekday())
    if weekday_lines and rng.random() < WEEKDAY_LINE_PROBABILITY:
        return rng.choice(weekday_lines)

    if silence_seconds is not None and rng.random() < SILENCE_TEMPLATE_PROBABILITY:
        minutes = max(1, int(silence_seconds // 60))
        template, expression = rng.choice(SILENCE_TEMPLATES_BY_TIER[tier])
        return template.format(minutes=minutes), expression

    return rng.choice(IDLE_CHATTER_BY_TIER[tier])


def pick_welcome_back(rng: random.Random | None = None) -> tuple[str, str]:
    return (rng or random).choice(WELCOME_BACK)


def pick_morning_greeting(rng: random.Random | None = None) -> tuple[str, str]:
    return (rng or random).choice(MORNING_GREETING)


def next_check_delay(rng: random.Random | None = None) -> float:
    lo, hi = CHECK_INTERVAL_RANGE_S
    return (rng or random).uniform(lo, hi)


def should_fire(rng: random.Random | None = None) -> bool:
    return (rng or random).random() < FIRE_PROBABILITY

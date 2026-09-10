"""Hand-authored idle gestures, for movements the model doesn't ship.

The zundamon model comes with 23 motions, but they're all *reactions* --
waving, pointing, refusing, laughing. None of them is the sort of unprompted
thing a character does when nobody is talking to it, which is exactly what an
idle gesture needs (a yawn was the first ask, 2026-09-10).

A gesture here is a set of parameter tracks sampled by elapsed time, applied
the same way lipsync applies ParamMouthOpenY: written straight onto the model
each frame before Update(). That keeps them out of Cubism's motion system
entirely, so they can't fight a real motion for priority -- the window just
won't start one while a gesture is running.

Kept Qt- and Live2D-free so the shapes can be tested without a GL context.
"""

from __future__ import annotations

# name -> [(seconds, value), ...], each track keyframed independently and
# linearly interpolated between points. Values are in the model's own units:
# eye open 0..1, mouth open 0..1, ParamAngleY in degrees (+ is looking up).
Track = tuple[tuple[float, float], ...]
Gesture = dict[str, Track]

YAWN: Gesture = {
    # Eyes squeeze shut as the mouth opens, then reopen a beat later --
    # closing them at the same moment the mouth peaks is what makes it read as
    # a yawn rather than surprise.
    "ParamEyeLOpen": ((0.0, 1.0), (0.6, 0.5), (1.1, 0.0), (2.0, 0.0), (2.5, 0.4), (3.2, 1.0)),
    "ParamEyeROpen": ((0.0, 1.0), (0.6, 0.5), (1.1, 0.0), (2.0, 0.0), (2.5, 0.4), (3.2, 1.0)),
    "ParamMouthOpenY": ((0.0, 0.0), (0.5, 0.35), (1.1, 1.0), (1.9, 0.95), (2.4, 0.2), (3.0, 0.0)),
    # A small chin lift; anything more looked like it was staring at the
    # ceiling rather than yawning.
    "ParamAngleY": ((0.0, 0.0), (1.1, 7.0), (1.9, 7.0), (3.0, 0.0)),
}

# Eyes sag shut, hang there, then snap open -- the snap is the whole gesture,
# so the recovery is much faster than the drift into it.
DOZE: Gesture = {
    "ParamEyeLOpen": ((0.0, 1.0), (1.6, 0.35), (2.6, 0.15), (2.9, 1.0), (4.0, 1.0)),
    "ParamEyeROpen": ((0.0, 1.0), (1.6, 0.35), (2.6, 0.15), (2.9, 1.0), (4.0, 1.0)),
    # The head nods down with them and comes back up on the same snap.
    "ParamAngleY": ((0.0, 0.0), (2.6, -6.0), (2.9, 1.0), (4.0, 0.0)),
}

# A slow tilt, a pause at the far side, then back. The pause is what reads as
# "hm?" -- tilting straight back looks like a twitch.
TILT_HEAD: Gesture = {
    "ParamAngleZ": ((0.0, 0.0), (0.7, 13.0), (1.9, 13.0), (2.8, 0.0)),
    "ParamAngleX": ((0.0, 0.0), (0.7, 4.0), (1.9, 4.0), (2.8, 0.0)),
}

# Eyes wander without the head following. Deliberately small: this one is
# meant to be barely noticed, the way a person's eyes move when they aren't
# doing anything in particular.
GLANCE_AROUND: Gesture = {
    "ParamEyeBallX": ((0.0, 0.0), (0.8, -0.7), (1.6, -0.7), (2.4, 0.6), (3.2, 0.6), (4.0, 0.0)),
    "ParamEyeBallY": ((0.0, 0.0), (0.8, 0.2), (2.4, -0.2), (4.0, 0.0)),
}

# Shoulders up and straight back down: "さあ?". Short, because a held shrug
# stops reading as a shrug.
SHRUG: Gesture = {
    "ParamShrug": ((0.0, 0.0), (0.5, 1.0), (1.2, 1.0), (2.0, 0.0)),
    "ParamAngleZ": ((0.0, 0.0), (0.5, -6.0), (1.2, -6.0), (2.0, 0.0)),
}

# One slow inhale and release. Uses the model's own breath parameter, so the
# automatic breathing has to be paused for the duration or the two add up.
DEEP_BREATH: Gesture = {
    "ParamBreath": ((0.0, 0.0), (1.5, 1.0), (2.2, 1.0), (3.8, 0.0)),
    "ParamBodyAngleY": ((0.0, 0.0), (1.5, 3.0), (2.2, 3.0), (3.8, 0.0)),
}

GESTURES: dict[str, Gesture] = {
    "yawn": YAWN,
    "doze": DOZE,
    "tilt_head": TILT_HEAD,
    "glance_around": GLANCE_AROUND,
    "shrug": SHRUG,
    "deep_breath": DEEP_BREATH,
}

GESTURE_LABELS: dict[str, str] = {
    "yawn": "あくび",
    "doze": "うとうと",
    "tilt_head": "首をかしげる",
    "glance_around": "きょろきょろ",
    "shrug": "肩をすくめる",
    "deep_breath": "深呼吸",
}

# Which gestures may fire in which part of the day, as (start hour, end hour,
# gestures) bands covering all 24 hours; the end hour is exclusive and the last
# band wraps to midnight.
#
# Written as a timetable rather than as per-gesture hour ranges because that is
# how it gets reviewed -- the question asked of it is always "what happens at
# 3pm", never "when does the yawn happen". Sleepiness is the spine of it: the
# night and the early morning get only the sleepy pair, the working day only
# the alert ones, and a yawn at 11am would read as a bug where the same yawn at
# 8am reads as character (2026-09-11, set by the user after watching them).
#
# A gesture defined here but absent from every band still works from the
# right-click 仕草 menu; it just never fires on its own.
IDLE_SCHEDULE: tuple[tuple[int, int, tuple[str, ...]], ...] = (
    # Only sleepy movement at night: looking alert at 3am reads as the mascot
    # being livelier than the person watching it.
    (0, 7, ("doze", "yawn")),
    (7, 10, ("yawn", "glance_around")),
    (10, 13, ("glance_around", "tilt_head", "deep_breath", "shrug")),
    (13, 15, ("glance_around", "tilt_head", "deep_breath")),
    (15, 22, ("glance_around", "tilt_head", "deep_breath")),
    (22, 24, ("doze", "yawn")),
)


EYE_OPEN_PARAMS = ("ParamEyeLOpen", "ParamEyeROpen")
BREATH_PARAM = "ParamBreath"


def available_at(hour: int) -> tuple[str, ...]:
    """The gestures that may fire at `hour` (0-23), per IDLE_SCHEDULE."""
    for start, end, names in IDLE_SCHEDULE:
        if start <= hour < end:
            return names
    return ()


def duration(gesture: Gesture) -> float:
    return max(track[-1][0] for track in gesture.values())


def touches_eyes(gesture: Gesture) -> bool:
    """Whether auto-blink has to be paused while this gesture plays.

    Only the gestures that drive the eyelids themselves conflict with it --
    pausing blinking through a four-second glance would just make the mascot
    stare.
    """
    return any(param in gesture for param in EYE_OPEN_PARAMS)


def touches_breath(gesture: Gesture) -> bool:
    """Whether auto-breathing has to be paused; it writes the same parameter."""
    return BREATH_PARAM in gesture


def sample(gesture: Gesture, elapsed: float) -> dict[str, float]:
    """Parameter values for `elapsed` seconds in, linearly interpolated.

    Past the end every track holds its last value, so a caller that stops one
    frame late doesn't snap.
    """
    return {name: _sample_track(track, elapsed) for name, track in gesture.items()}


def _sample_track(track: Track, elapsed: float) -> float:
    if elapsed <= track[0][0]:
        return track[0][1]
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if elapsed <= t1:
            span = t1 - t0
            if span <= 0:
                return v1
            return v0 + (v1 - v0) * (elapsed - t0) / span
    return track[-1][1]

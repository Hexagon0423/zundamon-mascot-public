"""Named expression -> body/face motion, for the Live2D backend.

A motion is a short one-shot gesture played when the expression changes: the
mascot waves as it greets, folds its arms as it starts thinking, then settles
into the expression's own pose. Unlike the PNG backend, continuous movement is
fine here -- the model's own blink/breath were shown to the user and approved
as "natural" (2026-09-10); what was rejected three times was faking motion by
translating/scaling a flat PNG.

Motions and arm-pose expressions fight over the same parameters, so
live2d_window.py plays the motion against the *face only* and applies the full
preset (face + `pose_*`) once the motion finishes. See EXPRESSION_PRESETS in
live2d_expressions.py for the other half of the table.

The mapping was built by rendering each motion as a filmstrip and watching it
(`python scripts/verify_live2d_motions.py`), not from the file names -- and
that mattered, because several names lie:
  - `mtnBody_point` is a peace sign; the actual index-finger point is `point3`
  - `mtnBody_yes` folds the arms and nods -- agreement, not a plain "yes"
  - `mtnBody_no3` is a both-palms-up shrug, i.e. "search me", not a refusal

`mtnFace_talk` is deliberately unused: it animates the mouth open/closed, which
would fight the vowel-driven ParamMouthOpenY lipsync writes every frame.

`mtnBody_angry` is unused for a different reason: it ends by turning the head
away (ParamAngleX/Z reach -30/-28 and hold), so whatever it was attached to
looked like it was sulking a few seconds in. A gesture that ends facing away
from the user doesn't work for a desktop mascot, whatever it's called.
"""

from __future__ import annotations

# Index into the model's single (unnamed) motion group, in model3.json order --
# that is what LAppModel.StartMotion takes. Names are kept alongside so this
# table stays readable and so the tests can assert the two agree.
EXPRESSION_MOTIONS: dict[str, tuple[int, str]] = {
    "greeting": (15, "mtnBody_wave2"),
    "celebrating": (14, "mtnBody_wave"),
    "delighted": (16, "mtnBody_wave3"),
    "happy": (18, "mtnFace_laugh"),
    "confident": (17, "mtnBody_yes"),
    "thinking": (11, "mtnBody_think2"),
    "confused": (6, "mtnBody_no3"),
    "warning_no": (5, "mtnBody_no2"),
    "explaining": (8, "mtnBody_point2"),
    "eureka": (9, "mtnBody_point3"),
    "panic": (13, "mtnBody_tremble"),
    "scared": (13, "mtnBody_tremble"),
    "shock": (21, "mtnFace_surprise"),
    "dazed": (21, "mtnFace_surprise"),
    "sad": (19, "mtnFace_sad"),
    "disappointed": (19, "mtnFace_sad"),
    "shy": (20, "mtnFace_shy"),
}

# Motions that only drive the face. The arm-pose half of a preset can stay on
# while these play, since they don't touch the arms.
FACE_ONLY_PREFIX = "mtnFace_"

# Idle behaviour lives in live2d_gestures.py: the gestures themselves are
# hand-authored parameter tracks, and IDLE_SCHEDULE says which may fire when.
#
# The model's own motions were tried for this first and dropped: every one of
# them is a *reaction* -- waving, pointing, refusing -- and firing one
# unprompted looked like the mascot was answering someone who wasn't there.
# The three mild enough to survive that filter (think2, think3, yes) all
# crossed the arms, so they read as the same gesture three times over
# (2026-09-10).

IDLE_GESTURE_MIN_SECONDS = 45.0
IDLE_GESTURE_MAX_SECONDS = 120.0

# How long an expression stays up after the mascot stops speaking. Without
# this, whatever was last set persists indefinitely -- a "celebrating" turn
# left it standing with both arms raised for hours (2026-09-10).
#
# Short on purpose: the expression belongs to the utterance, and the clock only
# starts once the mouth stops moving (speaker.py drives set_mouth_for_vowel
# every frame until the audio ends), so a long reply still keeps its pose all
# the way through. Went 60s -> 5s -> 0.5s over one evening of watching it; the
# expression should feel like part of the sentence, not like a state the mascot
# is left sitting in.
EXPRESSION_HOLD_SECONDS = 0.5


def motion_for(name: str) -> tuple[int, str] | None:
    return EXPRESSION_MOTIONS.get(name)


def is_face_only(motion_name: str) -> bool:
    return motion_name.startswith(FACE_ONLY_PREFIX)


def next_idle_delay(rng) -> float:
    """Seconds to wait before the next idle gesture.

    Randomised so the mascot doesn't twitch on a visible metronome -- a fixed
    interval is exactly the mechanical feel that got the PNG backend's idle
    animation rejected three times.
    """
    return rng.uniform(IDLE_GESTURE_MIN_SECONDS, IDLE_GESTURE_MAX_SECONDS)

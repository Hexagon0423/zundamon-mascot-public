import pytest

from mascot.live2d_gestures import (
    DOZE,
    GESTURE_LABELS,
    GESTURES,
    YAWN,
    duration,
    sample,
    touches_breath,
    touches_eyes,
)

# Parameters whose neutral value is 0; the eye-open pair rests at 1 instead.
RESTS_AT_ONE = ("ParamEyeLOpen", "ParamEyeROpen")


def test_every_gesture_has_a_japanese_label():
    assert set(GESTURE_LABELS) == set(GESTURES)


def test_sample_interpolates_between_keyframes():
    track = {"p": ((0.0, 0.0), (2.0, 10.0))}
    assert sample(track, 0.0)["p"] == 0.0
    assert sample(track, 1.0)["p"] == pytest.approx(5.0)
    assert sample(track, 2.0)["p"] == 10.0


def test_sample_holds_the_ends():
    """A caller a frame early or late shouldn't make the model snap."""
    track = {"p": ((1.0, 3.0), (2.0, 7.0))}
    assert sample(track, 0.0)["p"] == 3.0
    assert sample(track, 99.0)["p"] == 7.0


@pytest.mark.parametrize("name", sorted(GESTURES))
def test_gestures_start_and_end_at_rest(name):
    """They fire unprompted, so each has to leave no trace behind it.

    Ending anywhere else would strand the model in a half-gesture until
    something else happened to reset the parameter.
    """
    gesture = GESTURES[name]
    for at in (sample(gesture, 0.0), sample(gesture, duration(gesture))):
        for param, value in at.items():
            expected = 1.0 if param in RESTS_AT_ONE else 0.0
            assert value == pytest.approx(expected, abs=0.05), f"{name}: {param} が {value}"


@pytest.mark.parametrize("name", sorted(GESTURES))
def test_gestures_are_short_enough_to_not_block_speech(name):
    assert duration(GESTURES[name]) <= 4.0


def test_yawn_closes_the_eyes_while_the_mouth_is_widest():
    """Open mouth with open eyes is surprise, not a yawn."""
    peak = max(YAWN["ParamMouthOpenY"], key=lambda kf: kf[1])[0]
    at_peak = sample(YAWN, peak)
    assert at_peak["ParamMouthOpenY"] > 0.9
    assert at_peak["ParamEyeLOpen"] < 0.1
    assert at_peak["ParamEyeROpen"] < 0.1


def test_doze_recovers_faster_than_it_droops():
    """The snap awake is the point; a symmetric fade would read as a slow blink."""
    track = DOZE["ParamEyeLOpen"]
    lowest = min(track, key=lambda kf: kf[1])[0]
    droop = lowest - track[0][0]
    recovery = next(t for t, v in track if t > lowest and v >= 1.0) - lowest
    assert recovery < droop / 2


def test_only_the_breathing_gesture_pauses_auto_breathing():
    assert touches_breath(GESTURES["deep_breath"])
    assert not touches_breath(GESTURES["yawn"])


def test_only_eyelid_gestures_pause_auto_blink():
    assert touches_eyes(GESTURES["yawn"])
    assert touches_eyes(GESTURES["doze"])
    assert not touches_eyes(GESTURES["tilt_head"])
    assert not touches_eyes(GESTURES["glance_around"])

import pytest

from mascot.lipsync import SILENT_VOWEL

pytest.importorskip("PySide6")

from mascot.live2d_window import VOWEL_MOUTH  # noqa: E402

VOWELS = ("a", "i", "u", "e", "o", "N", "cl", SILENT_VOWEL)


def test_every_vowel_the_timeline_can_emit_has_a_shape():
    assert set(VOWEL_MOUTH) == set(VOWELS)


@pytest.mark.parametrize("vowel", sorted(VOWEL_MOUTH))
def test_shapes_stay_inside_the_models_parameter_ranges(vowel):
    open_y, form = VOWEL_MOUTH[vowel]
    assert 0.0 <= open_y <= 1.0
    assert -1.0 <= form <= 1.0


def test_silence_closes_the_mouth():
    assert VOWEL_MOUTH[SILENT_VOWEL] == (0.0, 0.0)
    assert VOWEL_MOUTH["cl"] == (0.0, 0.0)


def test_a_is_the_widest_opening():
    """Every other vowel is judged relative to あ, so it has to be the extreme."""
    assert VOWEL_MOUTH["a"][0] == max(open_y for open_y, _ in VOWEL_MOUTH.values())


def test_i_and_u_are_told_apart_by_shape_rather_than_opening():
    """Both are nearly closed; without the form parameter they were identical,
    which is what made the lipsync read as generic (2026-09-11)."""
    i_open, i_form = VOWEL_MOUTH["i"]
    u_open, u_form = VOWEL_MOUTH["u"]
    assert abs(i_open - u_open) < 0.25
    assert i_form > 0.5 and u_form < -0.5


def test_the_vowels_are_not_all_the_same_shape():
    assert len({form for _, form in VOWEL_MOUTH.values()}) >= 5

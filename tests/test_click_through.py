from mascot.click_through import (
    WS_EX_LAYERED,
    WS_EX_TRANSPARENT,
    apply_style,
    set_click_through,
)


def test_turning_it_on_sets_both_bits():
    """WS_EX_TRANSPARENT is only honoured for hit-testing on a layered window."""
    style = apply_style(0, True)
    assert style & WS_EX_TRANSPARENT
    assert style & WS_EX_LAYERED


def test_turning_it_off_clears_only_the_transparency_bit():
    """Clearing WS_EX_LAYERED would break the translucent background."""
    style = apply_style(WS_EX_TRANSPARENT | WS_EX_LAYERED, False)
    assert not style & WS_EX_TRANSPARENT
    assert style & WS_EX_LAYERED


def test_other_style_bits_are_left_alone():
    other = 0x00000008  # WS_EX_TOPMOST -- the mascot depends on staying on top
    for transparent in (True, False):
        assert apply_style(other, transparent) & other


def test_toggling_twice_returns_to_where_it_started():
    for start in (0, WS_EX_LAYERED, 0x00000008):
        assert apply_style(apply_style(start, True), False) == start | WS_EX_LAYERED


def test_a_missing_window_handle_is_not_an_error():
    """Called before the window is shown; failing loudly would kill startup."""
    assert set_click_through(0, True) is False

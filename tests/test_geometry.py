from mascot.geometry import clamp_onto_screen

SCREEN = (0, 0, 1920, 1080)


def test_a_position_already_on_screen_is_left_alone():
    assert clamp_onto_screen(100, 200, 300, 400, SCREEN) == (100, 200)


def test_a_window_pushed_off_the_right_edge_is_pulled_back():
    """A remembered x_fraction near 1.0 put the whole mascot off-screen, which
    looked exactly like a mascot that had failed to start (2026-09-10)."""
    x, y = clamp_onto_screen(1915, 40, 400, 600, SCREEN)
    assert x == 1920 - 400
    assert y == 40


def test_a_negative_position_is_pulled_back_onto_the_screen():
    assert clamp_onto_screen(-500, -300, 400, 600, SCREEN) == (0, 0)


def test_a_window_bigger_than_the_screen_is_left_where_it_covers_the_screen():
    assert clamp_onto_screen(0, 0, 2400, 1600, SCREEN) == (0, 0)


def test_a_window_bigger_than_the_screen_is_pulled_back_until_it_covers_it():
    """Clamping the other way round: an oversized window is allowed to hang off
    both edges, but not to be dragged so far that the screen shows a gap."""
    x, y = clamp_onto_screen(-1000, -900, 2400, 1600, SCREEN)
    assert x == 1920 - 2400
    assert y == 1080 - 1600


def test_screen_offset_is_respected_for_a_second_monitor():
    second_monitor = (1920, 0, 1280, 720)
    x, y = clamp_onto_screen(3200, 700, 400, 600, second_monitor)
    assert x == 1920 + 1280 - 400
    assert y == 720 - 600

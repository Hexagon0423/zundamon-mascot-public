"""Frameless, transparent, always-on-top mascot window backed by Live2D
instead of PNG part compositing.

Speaker only calls apply_expression / set_mouth_for_vowel / restore_resting_mouth
on whatever window it's given (see speaker.py), so this class is a drop-in
alternative to MascotWindow -- window management (drag, position persistence,
scale, click-through, context menu, multi-monitor) is duplicated from
window.py rather than shared, since the two backends draw fundamentally
differently (GL widget vs QLabel pixmap).
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMenu

import live2d.v3 as live2d

from mascot import click_through
from mascot.config import Config, WindowPosition, save_config
from mascot.geometry import clamp_onto_screen
from mascot.lipsync import SILENT_VOWEL
from mascot.live2d_expressions import EXPRESSION_LABELS, EXPRESSION_PRESETS
from mascot.live2d_gestures import (
    GESTURE_LABELS,
    GESTURES,
    available_at,
    duration,
    sample,
    touches_breath,
    touches_eyes,
)
from mascot.live2d_motion_cache import lipsync_safe_model
from mascot.live2d_motions import (
    EXPRESSION_HOLD_SECONDS,
    is_face_only,
    motion_for,
    next_idle_delay,
)

logger = logging.getLogger(__name__)

FRAME_INTERVAL_MS = 33  # ~30fps, matches speaker.py's tick rate

# Per-vowel mouth shape: (how far open, how wide). Open runs 0 (shut) to 1
# (fully open); form runs -1 (pursed and small) through 0 (round) to +1 (wide
# and flat). Read off a rendered grid of the two parameters, since neither is
# obvious from the numbers: form is what separates い from う at the same
# opening, and without it every vowel was the same round mouth at a different
# height (2026-09-11 -- the first version set the opening only).
VOWEL_MOUTH: dict[str, tuple[float, float]] = {
    "a": (1.0, 0.3),  # 大きく開く。少しだけ横に広い
    "i": (0.2, 1.0),  # ほとんど閉じたまま、横いっぱい
    "u": (0.3, -1.0),  # すぼめて小さく
    "e": (0.5, 0.6),  # 中くらい + 横広め
    "o": (0.75, -0.4),  # 縦に開いて、やや丸め
    "N": (0.1, 0.0),  # ん。ほぼ閉じ
    "cl": (0.0, 0.0),  # 促音。閉じる
    SILENT_VOWEL: (0.0, 0.0),
}

# How long the model takes to drift back to its rest pose when a motion or an
# expression is cleared. ResetParameters() on its own is a hard cut, which read
# as the mascot snapping between poses (2026-09-10, reported).
#
# Two speeds, because the two cases want opposite things: swapping to another
# expression has to be crisp or the new gesture starts underneath the old
# pose, while letting go at the end of a turn is the mascot relaxing and looks
# better slow.
SWITCH_FADE_SECONDS = 0.45
RELEASE_FADE_SECONDS = 1.0

# Written every frame by the lipsync path, so nothing else may replay stale
# values over them.
LIPSYNC_PARAMS = ("ParamMouthOpenY", "ParamMouthForm")

# This model keeps all its motions in one unnamed group; the index into it is
# what StartMotion takes (see live2d_motions.py).
MOTION_GROUP = ""

# How often the cursor is tested against the model to decide whether this
# window should be catching clicks at all. The window is a rectangle around a
# mostly-transparent drawing, so without this it swallows clicks over roughly
# twice the area the mascot actually occupies (2026-09-11, reported).
HIT_TEST_INTERVAL_MS = 80

# A press and release within this many pixels is a click; more than that was a
# drag, and dragging the mascot around shouldn't set it talking.
CLICK_SLOP_PX = 4

SCALE_PRESETS = (0.25, 0.375, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

DEFAULT_WINDOW_SIZE = (400, 500)


class Live2DWindow(QOpenGLWidget):
    # Emitted when the mascot itself is clicked (not dragged, not the
    # transparent margin around it). app.py turns this into a spoken reaction.
    clicked = Signal()

    def __init__(self, model_path: str, config: Config, config_path=None):
        super().__init__()
        self._model_path = model_path
        self._config = config
        self._config_path = config_path
        self._model: live2d.LAppModel | None = None
        self._drag_offset: QPoint | None = None
        self._current_vowel = SILENT_VOWEL
        self._screen_changed_connected = False
        # Set while a motion from the model is playing; idle gestures hold off
        # until it finishes.
        self._motion_active = False
        # Idle handling: how long since the mascot last spoke or changed
        # expression, so the pose can drop back to neutral and the occasional
        # idle gesture only fires when nothing else is going on.
        self._rng = random.Random()
        self._current_expression = "normal"
        self._last_activity = time.monotonic()
        self._next_idle_at = self._last_activity + next_idle_delay(self._rng)
        # (gesture name, started at) while a hand-authored gesture is playing.
        self._gesture: tuple[str, float] | None = None
        # (started at, fade length, [(param index, value it had, its default)])
        # while easing back to rest.
        self._reset_fade: tuple[float, float, list[tuple[int, float, float]]] | None = None
        # Set once the model has loaded and reports its true canvas size (see
        # initializeGL) -- unknown before that, unlike window.py which gets
        # this from the PNG manifest up front.
        self._natural_size_px: tuple[int, int] | None = None
        # Parameter id -> index, so the reset fade can leave alone whatever
        # lipsync and gestures are driving this frame.
        self._param_index: dict[str, int] = {}
        # Where the left button went down, to tell a click from a drag.
        self._press_at = QPoint()
        # Last value pushed to the OS, so the style is only poked on a change.
        self._click_through_state: bool | None = None

        screen = QGuiApplication.primaryScreen()
        self._raw_device_pixel_ratio = screen.devicePixelRatio() if screen else 1.0

        self.resize(*DEFAULT_WINDOW_SIZE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, config.click_through)
        # The native style needs a window handle, so it is applied from
        # showEvent once there is one.

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(FRAME_INTERVAL_MS)

        self._hit_timer = QTimer(self)
        self._hit_timer.timeout.connect(self._follow_cursor)
        self._hit_timer.start(HIT_TEST_INTERVAL_MS)

        self._restore_position()

    # -- GL lifecycle ----------------------------------------------------------

    def initializeGL(self) -> None:
        live2d.glInit()
        self._model = live2d.LAppModel()
        # Not the model as shipped: a copy whose motions have had the mouth
        # curves removed, so lipsync keeps the mouth while a gesture plays.
        # See live2d_motion_cache for why this is a whole patched model3.json.
        self._model.LoadModelJson(str(lipsync_safe_model(Path(self._model_path))))
        self._model.SetAutoBlinkEnable(True)
        self._model.SetAutoBreathEnable(True)
        self._param_index = {name: i for i, name in enumerate(self._model.GetParamIds())}
        w, h = self._model.GetCanvasSizePixel()
        self._natural_size_px = (round(w), round(h))
        # Model just loaded with the window still at its pre-load placeholder
        # size (DEFAULT_WINDOW_SIZE); now that the true canvas size is known,
        # size the window for real. This triggers resizeGL again with the
        # correct pixel size.
        self._apply_geometry()

    def resizeGL(self, w: int, h: int) -> None:
        if self._model is not None:
            self._model.Resize(w, h)

    # -- size --------------------------------------------------------------

    def _apply_geometry(self) -> None:
        """Size the window so the model's full canvas fits without cropping.

        Live2D's Resize(w, h) fits the whole model into whatever pixel box
        it's given -- there is no separate "zoom" needed. Growing/shrinking
        the mascot is therefore just resizing this widget (mirrors
        window.py's _apply_geometry, using the model's own reported canvas
        size in place of the PNG manifest's). Calling SetScale on top of a
        *fixed-size* window was the earlier bug here: it zoomed into the
        model within an unchanged viewport instead of growing the window,
        which read as "just a face" at scale > ~1 (2026-09-10).
        """
        if self._natural_size_px is None:
            return
        device_pixel_ratio = self._raw_device_pixel_ratio / (
            self._config.scale if self._config.scale > 0 else 1.0
        )
        natural_w, natural_h = self._natural_size_px
        logical_width = round(natural_w / device_pixel_ratio)
        logical_height = round(natural_h / device_pixel_ratio)
        self.resize(logical_width, logical_height)

    def paintGL(self) -> None:
        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
        if self._model is None:
            return
        self._note_motion_finished()
        self._tick_idle()
        gesture_values = self._tick_gesture()
        open_y, form = VOWEL_MOUTH.get(self._current_vowel, VOWEL_MOUTH[SILENT_VOWEL])
        for param, value in zip(LIPSYNC_PARAMS, (open_y, form)):
            # A gesture that shapes the mouth itself (the yawn) wins for its
            # few seconds; it only runs when nothing is being said anyway.
            if param not in gesture_values:
                self._model.SetParameterValue(param, value, 1.0)
        for param, value in gesture_values.items():
            self._model.SetParameterValue(param, value, 1.0)
        self._tick_reset_fade(skip=gesture_values.keys())
        self._model.Update()
        self._model.Draw()

    def _reset_parameters_smoothly(self, fade_seconds: float = SWITCH_FADE_SECONDS) -> None:
        """Return to the rest pose over `fade_seconds` instead of instantly.

        Cubism crossfades its own expressions, but nothing fades the raw
        parameters a finished motion leaves behind, so clearing them with
        ResetParameters() alone snapped the model into place. This records what
        those parameters were, resets, and then eases from the recorded values
        back down over the next few frames.
        """
        if self._model is None:
            return
        # The mouth parameters are excluded outright rather than per-frame:
        # lipsync owns them for the whole utterance, and an expression change
        # lands right as speech starts.
        mouth = {self._param_index[p] for p in LIPSYNC_PARAMS if p in self._param_index}
        held = []
        for index in range(self._model.GetParameterCount()):
            if index in mouth:
                continue
            parameter = self._model.GetParameter(index)
            if abs(parameter.value - parameter.default) > 1e-3:
                held.append((index, parameter.value, parameter.default))
        self._model.ResetParameters()
        self._reset_fade = (time.monotonic(), fade_seconds, held) if held else None

    def _tick_reset_fade(self, skip=()) -> None:
        """Write this frame's step of the fade started by the method above.

        Anything being driven live this frame is left alone: the fade runs
        after lipsync and gestures have written their values, so replaying a
        recorded value over the mouth desynced it from the audio for the
        length of the fade (2026-09-11, reported as 口が連動していない).
        """
        if self._model is None or self._reset_fade is None:
            return
        held_back = {self._param_index[name] for name in skip if name in self._param_index}
        started, fade_seconds, held = self._reset_fade
        elapsed = time.monotonic() - started
        if elapsed >= fade_seconds:
            self._reset_fade = None
            return
        # The value is computed here rather than passed as a blend weight:
        # Update() writes each frame's result back, so a weight would blend
        # against the previous frame's output and creep the wrong way.
        remaining = 1.0 - elapsed / fade_seconds
        for index, value, default in held:
            if index in held_back:
                continue
            self._model.SetIndexParamValue(index, default + (value - default) * remaining, 1.0)

    def _tick_gesture(self) -> dict[str, float]:
        """Parameter values for the running hand-authored gesture, if any.

        Auto-blink is switched off for the duration: it and the gesture both
        write the eye-open parameters, and a blink landing mid-yawn reads as a
        glitch rather than as breathing.
        """
        if self._model is None or self._gesture is None:
            return {}
        name, started = self._gesture
        gesture = GESTURES[name]
        elapsed = time.monotonic() - started
        if elapsed >= duration(gesture):
            self._end_gesture()
            return {}
        return sample(gesture, elapsed)

    def _note_motion_finished(self) -> None:
        """Clear the motion flag so idle gestures may start again.

        Nothing else happens here on purpose. An earlier version reset the
        parameters and re-applied the preset's arm pose at this point, to undo
        the motion and land on the still picture -- but that plays as three
        movements instead of one: the gesture runs, everything relaxes, and the
        pose then fades in on its own. It looked like the mascot changed its
        mind halfway through (2026-09-11, reported). A body gesture *is* the
        pose; letting its last frame stand is the whole point of choosing
        motions that end somewhere worth standing.
        """
        if self._model is None or not self._motion_active:
            return
        if self._model.IsMotionFinished():
            self._motion_active = False

    # -- click ----------------------------------------------------------------

    def _follow_cursor(self) -> None:
        """Catch clicks only where the mascot is actually drawn.

        Qt can only make the whole widget transparent to the mouse, so the
        transparency is toggled as the cursor moves: over the drawing the
        window takes clicks, over the empty margin it lets them through to
        whatever is behind. Polled rather than event-driven precisely because
        a widget that isn't receiving mouse events can't tell us the cursor
        has arrived.
        """
        if self._model is None or self._drag_offset is not None:
            return
        if self._config.click_through:
            self._set_click_through(True)
            return
        local = self.mapFromGlobal(QCursor.pos())
        inside = self.rect().contains(local)
        on_model = bool(inside and self._model.HitPart(local.x(), local.y(), False))
        self._set_click_through(not on_model)

    def _set_click_through(self, transparent: bool) -> None:
        """Both switches, because neither is enough on its own.

        The Qt attribute is what the rest of Qt reads; the native extended
        style is what actually makes Windows route the click past this window.
        """
        if self._click_through_state == transparent:
            return
        self._click_through_state = transparent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, transparent)
        click_through.set_click_through(int(self.winId()), transparent)

    # -- idle ------------------------------------------------------------------

    def _tick_idle(self) -> None:
        """Let go of the expression, then gesture now and then, while idle.

        Driven off the paint loop rather than its own timers: the two rules
        both key off "time since the mascot last did anything", and one clock
        is easier to reason about than three interacting ones.
        """
        if self._model is None or self._motion_active or self._gesture is not None:
            return
        now = time.monotonic()
        idle_for = now - self._last_activity

        if self._current_expression != "normal" and idle_for >= EXPRESSION_HOLD_SECONDS:
            self.apply_expression("normal", fade_seconds=RELEASE_FADE_SECONDS)
            return

        if self._current_expression == "normal" and now >= self._next_idle_at:
            # Some gestures only suit certain hours (a yawn at 3pm reads as a
            # bug), so the pool is filtered before choosing -- and can be empty.
            allowed = available_at(datetime.now().hour)
            if allowed:
                self.play_gesture(self._rng.choice(allowed))
            self._next_idle_at = now + next_idle_delay(self._rng)

    def _note_activity(self) -> None:
        """Push back both idle behaviours; called whenever the mascot acts."""
        self._last_activity = time.monotonic()
        self._next_idle_at = self._last_activity + next_idle_delay(self._rng)

    def play_gesture(self, name: str) -> None:
        """Start a hand-authored gesture now, whatever the idle timer thinks."""
        if self._model is None or name not in GESTURES:
            return
        gesture = GESTURES[name]
        if touches_eyes(gesture):
            self._model.SetAutoBlinkEnable(False)
        if touches_breath(gesture):
            self._model.SetAutoBreathEnable(False)
        self._gesture = (name, time.monotonic())

    def _cancel_gesture(self) -> None:
        """Drop a running idle gesture -- speaking mid-yawn beats finishing it."""
        self._end_gesture()

    def _end_gesture(self) -> None:
        """Clear the running gesture and hand blink/breath back to the model."""
        if self._gesture is None:
            return
        self._gesture = None
        if self._model is not None:
            self._model.SetAutoBlinkEnable(True)
            self._model.SetAutoBreathEnable(True)

    # -- Speaker-facing interface (mirrors MascotWindow) ------------------------

    def set_mouth_for_vowel(self, vowel: str) -> None:
        self._current_vowel = vowel
        # Called every frame of speech, so this doubles as "still talking".
        self._note_activity()
        if vowel != SILENT_VOWEL:
            self._cancel_gesture()

    def restore_resting_mouth(self) -> None:
        self._current_vowel = SILENT_VOWEL

    def apply_expression(self, name: str, fade_seconds: float = SWITCH_FADE_SECONDS) -> None:
        """Apply a named preset: a face expression plus, usually, an arm pose.

        Presets are stacked with AddExpression rather than SetExpression
        because each preset is a whole picture (see live2d_expressions.py).
        An unknown name clears back to the neutral rest pose, which is also
        what "normal" (an empty preset) does.

        Where the preset has a gesture (live2d_motions.py), the motion plays
        first and the *arm pose* half of the preset is withheld until it
        finishes -- both drive the arms, so applying them together makes the
        gesture fight a pose that's pinning the same limbs. Face-only motions
        don't have that problem and let the pose stay on throughout.
        """
        if self._model is None:
            return
        self._current_expression = name if name in EXPRESSION_PRESETS else "normal"
        self._note_activity()
        self._cancel_gesture()
        self._model.ResetExpressions()
        self._motion_active = False
        # A finished (or stopped) motion leaves its last frame in the model's
        # parameters -- Cubism carries them over between Update()s rather than
        # reverting to the rest pose -- so without this the previous gesture
        # bleeds into the next expression: after "eureka" the raised finger
        # stayed up under "patient_wait", and "proud" kept the hip-lean's
        # turned-away head once its motion ended (2026-09-10, reported).
        self._model.StopAllMotions()
        self._reset_parameters_smoothly(fade_seconds)
        expression_ids = EXPRESSION_PRESETS.get(name, ())
        motion = motion_for(name)

        if motion is not None:
            index, motion_name = motion
            self._motion_active = True
            if not is_face_only(motion_name):
                # Faces are `exp_*`, arm poses `pose_*` -- see
                # live2d_expressions.py for why the ids are split that way.
                # The pose is dropped rather than played alongside: both drive
                # the arms, and the motion is the better picture of the two.
                expression_ids = tuple(i for i in expression_ids if not i.startswith("pose_"))
            self._model.StartMotion(MOTION_GROUP, index, live2d.MotionPriority.FORCE)

        for expression_id in expression_ids:
            self._model.AddExpression(expression_id)

    # -- size --------------------------------------------------------------

    def set_scale(self, scale: float) -> None:
        self._config.scale = scale
        self._apply_geometry()
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    # -- position persistence -------------------------------------------------

    def _restore_position(self) -> None:
        pos = self._config.window_position
        screen = QGuiApplication.primaryScreen()
        for candidate in QGuiApplication.screens():
            if pos and candidate.name() == pos.screen_name:
                screen = candidate
                break
        geo = screen.geometry()
        if pos is not None:
            x = geo.x() + int(pos.x_fraction * geo.width())
            y = geo.y() + int(pos.y_fraction * geo.height())
        else:
            x = geo.x() + geo.width() - self.width() - 40
            y = geo.y() + geo.height() - self.height() - 80
        x, y = clamp_onto_screen(
            x, y, self.width(), self.height(), (geo.x(), geo.y(), geo.width(), geo.height())
        )
        self.move(x, y)

    def _save_position(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        pos = self.pos()
        self._config.window_position = WindowPosition(
            screen_name=screen.name(),
            x_fraction=(pos.x() - geo.x()) / geo.width(),
            y_fraction=(pos.y() - geo.y()) / geo.height(),
        )
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    # -- drag to move ---------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_at = event.globalPosition().toPoint()
            self._drag_offset = self._press_at - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            moved = (event.globalPosition().toPoint() - self._press_at).manhattanLength()
            self._drag_offset = None
            self._save_position()
            # Only when it's quiet: a reaction queued mid-answer would arrive
            # after it, with nothing left to react to.
            if moved <= CLICK_SLOP_PX and self._current_vowel == SILENT_VOWEL:
                self.clicked.emit()

    # -- multi-monitor dragging -------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._set_click_through(self._config.click_through)
        handle = self.windowHandle()
        if handle is not None and not self._screen_changed_connected:
            handle.screenChanged.connect(lambda _screen: self.update())
            self._screen_changed_connected = True

    # -- right-click menu -----------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        size_menu = menu.addMenu("サイズ")
        for preset in SCALE_PRESETS:
            percent = preset * 100
            label = f"{percent:g}%"
            action = QAction(label, self, checkable=True)
            action.setChecked(preset == self._config.scale)
            action.triggered.connect(lambda _checked, s=preset: self.set_scale(s))
            size_menu.addAction(action)

        expression_menu = menu.addMenu("表情")
        for name in EXPRESSION_PRESETS:
            label = EXPRESSION_LABELS.get(name, name)
            action = QAction(label, self)
            action.triggered.connect(lambda _checked, n=name: self.apply_expression(n))
            expression_menu.addAction(action)

        # Idle gestures fire on their own after a minute or two of quiet, which
        # makes them awkward to look at while working on them -- this plays one
        # on demand.
        gesture_menu = menu.addMenu("仕草")
        for gesture_name in GESTURES:
            label = GESTURE_LABELS.get(gesture_name, gesture_name)
            action = QAction(label, self)
            action.triggered.connect(lambda _checked, g=gesture_name: self.play_gesture(g))
            gesture_menu.addAction(action)

        toggle_click_through = QAction(
            "クリック透過を無効にする" if self._config.click_through else "クリック透過を有効にする",
            self,
        )
        toggle_click_through.triggered.connect(self._toggle_click_through)
        menu.addAction(toggle_click_through)

        quit_action = QAction("終了", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def _toggle_click_through(self) -> None:
        self._config.click_through = not self._config.click_through
        self._set_click_through(self._config.click_through)
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    def closeEvent(self, event):
        self._save_position()
        super().closeEvent(event)

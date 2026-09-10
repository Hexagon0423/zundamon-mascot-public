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

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMenu

import live2d.v3 as live2d

from mascot.config import Config, WindowPosition, save_config
from mascot.geometry import clamp_onto_screen
from mascot.lipsync import SILENT_VOWEL
from mascot.live2d_expressions import EXPRESSION_LABELS, EXPRESSION_PRESETS

logger = logging.getLogger(__name__)

FRAME_INTERVAL_MS = 33  # ~30fps, matches speaker.py's tick rate

# Per-vowel mouth-open amount (0=closed, 1=fully open). Rough initial guess
# carried over from the live2d_poc PoC -- not yet tuned against real audio.
VOWEL_OPEN_Y: dict[str, float] = {
    "a": 1.0,
    "i": 0.4,
    "u": 0.5,
    "e": 0.6,
    "o": 0.8,
    "N": 0.2,
    "cl": 0.0,
    SILENT_VOWEL: 0.0,
}

SCALE_PRESETS = (0.25, 0.375, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

DEFAULT_WINDOW_SIZE = (400, 500)


class Live2DWindow(QOpenGLWidget):
    def __init__(self, model_path: str, config: Config, config_path=None):
        super().__init__()
        self._model_path = model_path
        self._config = config
        self._config_path = config_path
        self._model: live2d.LAppModel | None = None
        self._drag_offset: QPoint | None = None
        self._current_vowel = SILENT_VOWEL
        self._screen_changed_connected = False
        # Set once the model has loaded and reports its true canvas size (see
        # initializeGL) -- unknown before that, unlike window.py which gets
        # this from the PNG manifest up front.
        self._natural_size_px: tuple[int, int] | None = None

        screen = QGuiApplication.primaryScreen()
        self._raw_device_pixel_ratio = screen.devicePixelRatio() if screen else 1.0

        self.resize(*DEFAULT_WINDOW_SIZE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, config.click_through)

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(FRAME_INTERVAL_MS)

        self._restore_position()

    # -- GL lifecycle ----------------------------------------------------------

    def initializeGL(self) -> None:
        live2d.glInit()
        self._model = live2d.LAppModel()
        self._model.LoadModelJson(self._model_path)
        self._model.SetAutoBlinkEnable(True)
        self._model.SetAutoBreathEnable(True)
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
        open_y = VOWEL_OPEN_Y.get(self._current_vowel, 0.0)
        self._model.SetParameterValue("ParamMouthOpenY", open_y, 1.0)
        self._model.Update()
        self._model.Draw()

    # -- Speaker-facing interface (mirrors MascotWindow) ------------------------

    def set_mouth_for_vowel(self, vowel: str) -> None:
        self._current_vowel = vowel

    def restore_resting_mouth(self) -> None:
        self._current_vowel = SILENT_VOWEL

    def apply_expression(self, name: str) -> None:
        """Apply a named preset: a face expression plus, usually, an arm pose.

        Presets are stacked with AddExpression rather than SetExpression
        because each preset is a whole picture (see live2d_expressions.py).
        An unknown name clears back to the neutral rest pose, which is also
        what "normal" (an empty preset) does.
        """
        if self._model is None:
            return
        self._model.ResetExpressions()
        for expression_id in EXPRESSION_PRESETS.get(name, ()):
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
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()

    # -- multi-monitor dragging -------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
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
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._config.click_through)
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    def closeEvent(self, event):
        self._save_position()
        super().closeEvent(event)

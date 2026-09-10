"""Render every expression the Live2D model ships and lay them out as one
labelled contact sheet, so the name->expression mapping can be decided (and
re-checked) by actually looking at the art instead of guessing from the
exp3.json parameter deltas.

The ids are opaque (exp_01, exp_angry2, pose_Upper3...) and the parameter
names alone turned out to be a poor guide: a first mapping built that way
read as "not matching at all" on screen (2026-09-10).

    python scripts/verify_live2d_expressions.py [model_name]

Writes one PNG per expression plus contact_sheet.png under
`live2d_expression_shots/` at the repo root.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtOpenGLWidgets import QOpenGLWidget

import live2d.v3 as live2d
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mascot.live2d_assets import live2d_model_path  # noqa: E402
from mascot.live2d_expressions import EXPRESSION_PRESETS  # noqa: E402

OUT_DIR = REPO_ROOT / "live2d_expression_shots"
SHOT_SIZE = (541, 797)  # half the model's 1082x1594 canvas
# Cubism fades an expression in over time, so let real time pass rather than
# spinning frames: a tight loop advances the blend by microseconds per tick.
SETTLE_SECONDS = 1.2
COLUMNS = 6


class Capturer(QOpenGLWidget):
    def __init__(self, model_path: str):
        super().__init__()
        self._model_path = model_path
        self.model: live2d.LAppModel | None = None
        self.expression_ids: list[str] = []
        self.resize(*SHOT_SIZE)

    def initializeGL(self) -> None:
        live2d.glInit()
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(self._model_path)
        # Blinking/breathing would make shots of the same expression differ.
        self.model.SetAutoBlinkEnable(False)
        self.model.SetAutoBreathEnable(False)
        self.model.Resize(self.width(), self.height())
        self.expression_ids = list(self.model.GetExpressionIds())

    def paintGL(self) -> None:
        live2d.clearBuffer(1.0, 1.0, 1.0, 1.0)  # white, so shapes read on the sheet
        if self.model is not None:
            self.model.Update()
            self.model.Draw()

    def capture(self, expression_ids: tuple[str, ...], path: Path) -> None:
        assert self.model is not None
        self.model.ResetExpressions()
        for expression_id in expression_ids:
            self.model.AddExpression(expression_id)
        deadline = time.monotonic() + SETTLE_SECONDS
        while time.monotonic() < deadline:
            self.repaint()
            QApplication.processEvents()
            time.sleep(0.02)
        self.grabFramebuffer().save(str(path))


def build_contact_sheet(shots: list[tuple[str, Path]], out_path: Path) -> None:
    thumb_w = SHOT_SIZE[0] // 3
    thumb_h = SHOT_SIZE[1] // 3
    label_h = 22
    rows = (len(shots) + COLUMNS - 1) // COLUMNS
    sheet = Image.new("RGB", (COLUMNS * thumb_w, rows * (thumb_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (expression_id, path) in enumerate(shots):
        with Image.open(path) as shot:
            thumb = shot.convert("RGB").resize((thumb_w, thumb_h))
        x = (index % COLUMNS) * thumb_w
        y = (index // COLUMNS) * (thumb_h + label_h)
        sheet.paste(thumb, (x, y))
        draw.rectangle([x, y + thumb_h, x + thumb_w, y + thumb_h + label_h], fill="black")
        draw.text((x + 4, y + thumb_h + 5), expression_id, fill="white")
    sheet.save(out_path)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    presets_mode = "--presets" in sys.argv
    model_name = args[0] if args else "zundamon"
    OUT_DIR.mkdir(exist_ok=True)

    live2d.init()
    app = QApplication(sys.argv)
    widget = Capturer(str(live2d_model_path(model_name)))
    widget.show()
    widget.repaint()  # forces initializeGL
    QApplication.processEvents()

    if presets_mode:
        # What the mascot will actually show: our named presets, composed.
        jobs = [(name, ids) for name, ids in EXPRESSION_PRESETS.items()]
        sheet_name = "presets_sheet.png"
        prefix = "preset_"
    else:
        # Every raw expression the model ships, to build the mapping from.
        jobs = [(expression_id, (expression_id,)) for expression_id in widget.expression_ids]
        sheet_name = "contact_sheet.png"
        prefix = ""

    shots: list[tuple[str, Path]] = []
    for label, expression_ids in jobs:
        path = OUT_DIR / f"{prefix}{label}.png"
        widget.capture(expression_ids, path)
        print(f"captured {label}", flush=True)
        shots.append((label, path))

    build_contact_sheet(shots, OUT_DIR / sheet_name)
    print(f"contact sheet: {OUT_DIR / sheet_name}", flush=True)

    widget.close()
    live2d.dispose()
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())

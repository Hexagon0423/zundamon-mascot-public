import json
from pathlib import Path

import pytest

from mascot.live2d_expressions import EXPRESSION_LABELS, EXPRESSION_PRESETS
from mascot.window import EXPRESSION_PRESETS as PNG_EXPRESSION_PRESETS

MODEL_DIR = Path(__file__).resolve().parent.parent / "assets" / "live2d" / "zundamon" / "runtime"
MODEL_JSON = MODEL_DIR / "zundamon.model3.json"


def _shipped_expression_ids() -> set[str]:
    """The ids the model actually offers, read from its model3.json."""
    data = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    return {entry["Name"] for entry in data["FileReferences"]["Expressions"]}


# モデル本体はこのリポジトリに同梱しない(README参照)ので、無い環境ではskipする。
@pytest.mark.skipif(not MODEL_JSON.exists(), reason="assets/live2d/zundamon/ が無い(README参照、各自入手)")
def test_every_preset_uses_ids_the_model_ships():
    shipped = _shipped_expression_ids()
    for name, expression_ids in EXPRESSION_PRESETS.items():
        for expression_id in expression_ids:
            assert expression_id in shipped, f"{name}: {expression_id!r} はモデルに無いのだ"


def test_normal_resets_rather_than_setting_an_expression():
    """The model's rest pose already reads as neutral; see live2d_expressions."""
    assert EXPRESSION_PRESETS["normal"] == ()


def test_expression_names_match_the_png_backend():
    """Both backends must answer to the same names.

    `POST /speak`'s `expression` field (and say.sh's second argument) is
    written without knowing which backend is running, so a name that works on
    the PNG art has to work on Live2D too.
    """
    assert set(EXPRESSION_PRESETS) == set(PNG_EXPRESSION_PRESETS)


def test_every_preset_has_a_japanese_label():
    assert set(EXPRESSION_LABELS) == set(EXPRESSION_PRESETS)

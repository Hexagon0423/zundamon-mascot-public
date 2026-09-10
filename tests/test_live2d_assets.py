import pytest

from mascot.live2d_assets import (
    LIVE2D_PREFIX,
    available_live2d_models,
    live2d_icon_path,
    live2d_model_path,
)

# Live2Dモデルはこのリポジトリに同梱しない(ライセンス上、各自が公式配布元から
# 個別に同意して入手するもののため。README参照)。よってCIやまっさらな
# clone直後はassets/live2d/が空でもよく、モデル依存のテストはskipする。
_HAS_ZUNDAMON_MODEL = "zundamon" in available_live2d_models()


@pytest.mark.skipif(not _HAS_ZUNDAMON_MODEL, reason="assets/live2d/zundamon/ が無い(README参照、各自入手)")
def test_the_zundamon_model_is_installed():
    assert "zundamon" in available_live2d_models()
    assert live2d_model_path("zundamon").exists()


def test_every_model_ships_a_tray_icon():
    """A model without icon.png gets a blank tray icon, which hides the
    立ち絵 switcher -- the only way back to the PNG art (2026-09-10)."""
    for model_name in available_live2d_models():
        assert live2d_icon_path(model_name) is not None, f"{model_name}/icon.png が無いのだ"


def test_prefix_distinguishes_live2d_models_from_png_sets():
    assert LIVE2D_PREFIX == "live2d:"

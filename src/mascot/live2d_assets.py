"""Lists installed Live2D models under assets/live2d/<name>/runtime/<name>.model3.json.

Mirrors assets.py's available_sets()/load path convention for the PNG asset
sets, but there's no manifest.json/Part structure to parse here -- a Live2D
model is just a directory whose model3.json path we hand to LAppModel.
"""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
LIVE2D_DIR = ASSETS_DIR / "live2d"

# Prefix used in config.asset_set to select a Live2D model instead of a PNG
# asset set (e.g. "live2d:zundamon").
LIVE2D_PREFIX = "live2d:"


def available_live2d_models(live2d_dir: Path = LIVE2D_DIR) -> list[str]:
    if not live2d_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in live2d_dir.iterdir()
        if (p / "runtime" / f"{p.name}.model3.json").exists()
    )


def live2d_icon_path(model_name: str, live2d_dir: Path = LIVE2D_DIR) -> Path | None:
    """A flat image to use as the tray icon, if the model ships one.

    A Live2D model has no single still image to point at (its textures are
    atlases), so an icon is rendered from it once and saved alongside as
    icon.png. Without one the tray icon comes out blank -- and a blank tray
    icon is not just ugly, it hides the 立ち絵 switcher, which is the only way
    back to the PNG art (2026-09-10).
    """
    path = live2d_dir / model_name / "icon.png"
    return path if path.exists() else None


def live2d_model_path(model_name: str, live2d_dir: Path = LIVE2D_DIR) -> Path:
    path = live2d_dir / model_name / "runtime" / f"{model_name}.model3.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} が無いのだ。Live2Dモデルを assets/live2d/{model_name}/ に置くのだ。")
    return path

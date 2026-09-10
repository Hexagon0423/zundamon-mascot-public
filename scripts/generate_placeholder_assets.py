"""Generate placeholder asset sets, split into parts like real 立ち絵 art is.

Two sets are produced on purpose, because real art doesn't agree on what
mouth shapes exist:

  vowel_5    - one mouth per vowel (あいうえお), like Live2D-oriented art
  aperture_3 - openness levels only (closed/half/open), which is how
               坂本アヒル's Zundamon art is built (むふ / ほー / ほあー)

Keeping both around means the engine's vowel->mouth mapping is exercised in
each direction before any real art shows up.

Run: python scripts/generate_placeholder_assets.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

SETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sets"

WIDTH, HEIGHT = 300, 400
BODY_COLOR = (126, 211, 33, 255)
BODY_OUTLINE = (60, 140, 10, 255)
FACE_COLOR = (255, 235, 205, 255)
MOUTH_COLOR = (139, 0, 0, 255)
EYE_COLOR = (30, 30, 30, 255)
BROW_COLOR = (70, 50, 20, 255)

FACE_CENTER = (WIDTH // 2, 150)
MOUTH_CENTER = (WIDTH // 2, 195)
EYE_Y = FACE_CENTER[1] - 5
EYE_DX = 35
BROW_Y = EYE_Y - 32

# (half_width, half_height) of the mouth ellipse
VOWEL_MOUTHS = {
    "closed": (18, 2),
    "a": (22, 24),
    "i": (25, 6),
    "u": (11, 11),
    "e": (26, 13),
    "o": (15, 19),
}
APERTURE_MOUTHS = {
    "closed": (18, 2),
    "half": (20, 11),
    "open": (23, 24),
}

# How each set's vowels map onto the mouth layers it actually has.
VOWEL_MAP_5 = {"a": "a", "i": "i", "u": "u", "e": "e", "o": "o"}
# With only three openness levels, vowels collapse by how open the mouth is.
VOWEL_MAP_3 = {"a": "open", "o": "open", "e": "half", "i": "half", "u": "half"}
SILENT_VOWELS = {"N": "closed", "pau": "closed", "cl": "closed"}


def _blank() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _body() -> Image.Image:
    img, draw = _blank()
    draw.ellipse([40, 60, WIDTH - 40, HEIGHT - 40], fill=BODY_COLOR, outline=BODY_OUTLINE, width=4)
    draw.ellipse(
        [
            FACE_CENTER[0] - 90,
            FACE_CENTER[1] - 70,
            FACE_CENTER[0] + 90,
            FACE_CENTER[1] + 70,
        ],
        fill=FACE_COLOR,
    )
    return img


def _eyes(openness: float) -> Image.Image:
    """openness: 1.0 fully open, 0.5 half, 0.0 shut (drawn as a line)."""
    img, draw = _blank()
    for dx in (-EYE_DX, EYE_DX):
        cx = FACE_CENTER[0] + dx
        half_height = max(1, round(9 * openness))
        draw.ellipse([cx - 8, EYE_Y - half_height, cx + 8, EYE_Y + half_height], fill=EYE_COLOR)
    return img


def _brows(shape: str) -> Image.Image:
    img, draw = _blank()
    for side, dx in (("left", -EYE_DX), ("right", EYE_DX)):
        cx = FACE_CENTER[0] + dx
        inner_lift, outer_lift = {
            "normal": (0, 0),
            "angry": (7, -5),
            "sad": (-7, 5),
        }[shape]
        if side == "left":
            start, end = (cx - 16, BROW_Y + outer_lift), (cx + 16, BROW_Y + inner_lift)
        else:
            start, end = (cx - 16, BROW_Y + inner_lift), (cx + 16, BROW_Y + outer_lift)
        draw.line([start, end], fill=BROW_COLOR, width=5)
    return img


def _mouth(size: tuple[int, int]) -> Image.Image:
    img, draw = _blank()
    half_w, half_h = size
    cx, cy = MOUTH_CENTER
    draw.ellipse([cx - half_w, cy - half_h, cx + half_w, cy + half_h], fill=MOUTH_COLOR)
    return img


def _write_set(set_name: str, mouths: dict, vowel_map: dict) -> dict:
    set_dir = SETS_DIR / set_name
    set_dir.mkdir(parents=True, exist_ok=True)

    images: dict[str, dict[str, Image.Image]] = {
        "body": {"normal": _body()},
        "brow": {shape: _brows(shape) for shape in ("normal", "angry", "sad")},
        "eyes": {"open": _eyes(1.0), "half": _eyes(0.45), "closed": _eyes(0.0)},
        "mouth": {key: _mouth(size) for key, size in mouths.items()},
    }

    parts = {}
    for part_name, layers in images.items():
        filenames = {}
        for layer_name, image in layers.items():
            filename = f"{part_name}_{layer_name}.png"
            image.save(set_dir / filename)
            filenames[layer_name] = filename
        parts[part_name] = {
            "default": {"body": "normal", "brow": "normal", "eyes": "open", "mouth": "closed"}[
                part_name
            ],
            "layers": filenames,
        }

    manifest = {
        "name": set_name,
        "placeholder": True,
        "canvas": {"width": WIDTH, "height": HEIGHT},
        "layer_order": ["body", "brow", "eyes", "mouth"],
        "parts": parts,
        "vowel_mouth_map": {**vowel_map, **SILENT_VOWELS},
    }
    (set_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def generate() -> list[str]:
    _write_set("vowel_5", VOWEL_MOUTHS, VOWEL_MAP_5)
    _write_set("aperture_3", APERTURE_MOUTHS, VOWEL_MAP_3)
    return ["vowel_5", "aperture_3"]


if __name__ == "__main__":
    for name in generate():
        print(f"generated placeholder set: {SETS_DIR / name}")

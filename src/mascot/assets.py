"""Loads an asset set's manifest.json and resolves its layer images.

The model mirrors how Japanese 立ち絵 PSDs are actually built (and how
PSDTool reads them): the art is split into *parts* (body, brows, eyes,
mouth...), each part offers several mutually exclusive *layers*, and a frame
is drawn by picking one layer per part and compositing them in order.

Flat per-mouth-shape images would not survive contact with real art: with
separate eye and mouth parts you'd need every mouth x eye x expression
combination as its own file.

Which mouth layer a vowel maps to is data, not code (`vowel_mouth_map`),
because artists don't agree on what mouth shapes to provide. Some sets have
one per vowel; 坂本アヒル's Zundamon art instead has openness levels
(むふ / ほー / ほあー), so several vowels map onto one layer there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
SETS_DIR = ASSETS_DIR / "sets"

CLOSED_MOUTH_KEY = "closed"


@dataclass(frozen=True)
class Part:
    """One switchable part of the art (e.g. "mouth"), and its options."""

    name: str
    layers: dict[str, Path]
    default: str

    def layer_path(self, key: str) -> Path:
        return self.layers.get(key, self.layers[self.default])

    def has(self, key: str) -> bool:
        return key in self.layers


@dataclass(frozen=True)
class AssetManifest:
    name: str
    width: int
    height: int
    parts: dict[str, Part]
    layer_order: list[str]
    vowel_mouth_map: dict[str, str]
    # Some art is drawn facing the opposite way from others (artist's
    # choice, not something the code can infer). window.py's left/right
    # auto-flip assumes unflipped art already faces correctly when the
    # mascot sits on the right half of the screen; a set drawn the other
    # way sets this to invert that assumption instead of relying on the
    # user to always drag it to the "wrong" half.
    mirror_default: bool = False

    @property
    def mouth(self) -> Part | None:
        return self.parts.get("mouth")

    @property
    def eyes(self) -> Part | None:
        return self.parts.get("eyes")

    def default_selection(self) -> dict[str, str]:
        return {name: part.default for name, part in self.parts.items()}

    def mouth_layer_for_vowel(self, vowel: str) -> str:
        """Map a VOICEVOX vowel onto a mouth layer this art actually has."""
        mapped = self.vowel_mouth_map.get(vowel)
        mouth = self.mouth
        if mouth is None:
            return CLOSED_MOUTH_KEY
        if mapped is not None and mouth.has(mapped):
            return mapped
        return mouth.default


def _is_placeholder(manifest_path: Path) -> bool:
    try:
        return bool(json.loads(manifest_path.read_text(encoding="utf-8")).get("placeholder", False))
    except (json.JSONDecodeError, OSError):
        return False


def available_sets(sets_dir: Path = SETS_DIR, include_placeholders: bool = True) -> list[str]:
    """The art sets on disk.

    `include_placeholders=False` drops the generated stand-in sets (the ones
    whose manifest says `"placeholder": true`). They exist to exercise both
    vowel->mouth mapping styles, which is worth keeping for the tests, but
    they are just clutter in the 立ち絵 switcher now that there's real art.
    """
    if not sets_dir.is_dir():
        return []
    names = []
    for path in sorted(sets_dir.iterdir()):
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            continue
        if not include_placeholders and _is_placeholder(manifest_path):
            continue
        names.append(path.name)
    return names


def load_manifest(set_name: str, sets_dir: Path = SETS_DIR) -> AssetManifest:
    set_dir = sets_dir / set_name
    manifest_path = set_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} が無いのだ。先に "
            "`python scripts/generate_placeholder_assets.py` を実行するのだ。"
        )

    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    parts: dict[str, Part] = {}
    for part_name, part_data in data["parts"].items():
        layers = {key: set_dir / filename for key, filename in part_data["layers"].items()}
        for key, path in layers.items():
            if not path.exists():
                raise FileNotFoundError(
                    f"manifest.jsonが参照している画像が無いのだ: {path} ({part_name}/{key})"
                )
        default = part_data["default"]
        if default not in layers:
            raise ValueError(f"{part_name} の default '{default}' がlayersに無いのだ")
        parts[part_name] = Part(name=part_name, layers=layers, default=default)

    layer_order = data["layer_order"]
    unknown = [name for name in layer_order if name not in parts]
    if unknown:
        raise ValueError(f"layer_orderに未定義のパーツがあるのだ: {unknown}")
    missing = [name for name in parts if name not in layer_order]
    if missing:
        raise ValueError(f"layer_orderに載っていないパーツがあるのだ: {missing}")

    return AssetManifest(
        name=data.get("name", set_name),
        width=data["canvas"]["width"],
        height=data["canvas"]["height"],
        parts=parts,
        layer_order=layer_order,
        vowel_mouth_map=data.get("vowel_mouth_map", {}),
        mirror_default=bool(data.get("mirror_default", False)),
    )

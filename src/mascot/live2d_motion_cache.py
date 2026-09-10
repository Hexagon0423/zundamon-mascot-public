"""A copy of the model whose motions leave the mouth alone.

Every one of this model's 23 motions animates ParamMouthOpenY, and Cubism
applies motions inside Update() -- after anything written from here. So while
a gesture played, the motion drove the mouth and the vowel timeline did not:
the mascot's mouth moved, but not with the audio (2026-09-11, reported as
「口が連動していない」). Writing the parameter after Update() doesn't help
either; by then the mesh has been deformed. Measured, with the mouth held at
0.7 and a gesture running: the original motion leaves it anywhere between 0.0
and 1.0, the stripped copy leaves it at 0.7.

So the mouth curves come out of the motions instead, and a patched model3.json
pointing at the stripped copies is what gets loaded. Motion order is preserved,
so the indices in live2d_motions.py still mean what they say.

Two things here are not obvious and were each found by measurement:

- `LAppModel.LoadExtraMotion` looked like the tidier route (load extras into
  their own group, no patched model3.json) but it does not work: whatever index
  it returns, StartMotion on that group plays the *first* motion loaded into
  it. A test that "passed" this way was really playing the original motion.

- **Cubism's JSON reader needs tab indentation and LF newlines.** A compact
  `json.dumps` loads without any error and then animates nothing at all; so
  does the same content with CRLF. Byte-identical copies work, tab-indented
  copies work (movement 5615), compact and CRLF copies do not (0). Keep
  `_dump` as it is, and don't reformat these files.
"""

from __future__ import annotations

import json
from pathlib import Path

CACHE_DIR_NAME = "motions_lipsync_safe"
PATCHED_MODEL_SUFFIX = ".lipsync_safe.model3.json"

# ParamMouthOpenY is the one lipsync writes; the other two decide the mouth's
# shape, and leaving them animated made the vowel's opening land on a mouth the
# motion had already reshaped. The eye curves stay -- a gesture closing its eyes
# is part of the gesture.
MOUTH_CURVE_IDS = frozenset({"ParamMouthOpenY", "ParamMouthForm", "ParamPatternMouth"})

# Values per segment by type, and how many curve points each contributes.
# Meta's counts have to match the curves that remain, since the loader sizes
# its buffers from them.
_SEGMENT_SHAPE = {0: (2, 1), 1: (6, 3), 2: (2, 1), 3: (2, 1)}


def _count(segments: list[float]) -> tuple[int, int]:
    """(segment count, point count) for one curve's flat Segments array."""
    index = 2  # the first pair is the curve's starting point
    points = 1
    segment_count = 0
    while index < len(segments):
        values, added = _SEGMENT_SHAPE[int(segments[index])]
        index += 1 + values
        points += added
        segment_count += 1
    return segment_count, points


def _dump(data: dict, path: Path) -> None:
    """Write the way Cubism's reader expects: tab indented, LF newlines."""
    path.write_text(json.dumps(data, indent="\t", ensure_ascii=False), encoding="utf-8", newline="\n")


def strip_mouth_curves(motion: dict) -> dict:
    curves = [c for c in motion["Curves"] if c.get("Id") not in MOUTH_CURVE_IDS]
    segments = 0
    points = 0
    for curve in curves:
        curve_segments, curve_points = _count(curve["Segments"])
        segments += curve_segments
        points += curve_points
    meta = dict(motion["Meta"])
    meta["CurveCount"] = len(curves)
    meta["TotalSegmentCount"] = segments
    meta["TotalPointCount"] = points
    return {**motion, "Meta": meta, "Curves": curves}


def lipsync_safe_model(model_json_path: Path) -> Path:
    """Path to a copy of the model whose motions don't touch the mouth.

    Built beside the original (and rebuilt when the original is newer), so the
    relative paths to the moc3, textures and physics still resolve.
    """
    model_json_path = Path(model_json_path)
    patched = model_json_path.with_name(model_json_path.name.split(".model3.json")[0] + PATCHED_MODEL_SUFFIX)
    if patched.exists() and patched.stat().st_mtime >= model_json_path.stat().st_mtime:
        return patched

    model = json.loads(model_json_path.read_text(encoding="utf-8"))
    groups = model.get("FileReferences", {}).get("Motions", {})
    for entries in groups.values():
        for entry in entries:
            source = model_json_path.parent / entry["File"]
            entry["File"] = str(_stripped_copy(source).relative_to(model_json_path.parent)).replace(
                "\\", "/"
            )
    _dump(model, patched)
    return patched


def _stripped_copy(motion_path: Path) -> Path:
    cache_dir = motion_path.parent / CACHE_DIR_NAME
    cached = cache_dir / motion_path.name
    if cached.exists() and cached.stat().st_mtime >= motion_path.stat().st_mtime:
        return cached
    cache_dir.mkdir(exist_ok=True)
    _dump(strip_mouth_curves(json.loads(motion_path.read_text(encoding="utf-8"))), cached)
    return cached

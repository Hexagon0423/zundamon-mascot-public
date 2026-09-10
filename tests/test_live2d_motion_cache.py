import json
from pathlib import Path

import pytest

from mascot.live2d_motion_cache import (
    MOUTH_CURVE_IDS,
    _count,
    _stripped_copy,
    lipsync_safe_model,
    strip_mouth_curves,
)

MOTIONS_DIR = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "live2d"
    / "zundamon"
    / "runtime"
    / "motions"
)

needs_model = pytest.mark.skipif(
    not MOTIONS_DIR.exists(), reason="Live2Dモデルは同梱していないのだ(各自で入手する素材)"
)


@needs_model
def test_the_segment_counter_agrees_with_the_original_metadata():
    """The counts have to be right: the loader sizes its buffers from Meta,
    and a motion whose Meta doesn't match its curves silently doesn't play.
    """
    for path in sorted(MOTIONS_DIR.glob("*.motion3.json")):
        motion = json.loads(path.read_text(encoding="utf-8"))
        segments = points = 0
        for curve in motion["Curves"]:
            curve_segments, curve_points = _count(curve["Segments"])
            segments += curve_segments
            points += curve_points
        meta = motion["Meta"]
        assert (len(motion["Curves"]), segments, points) == (
            meta["CurveCount"],
            meta["TotalSegmentCount"],
            meta["TotalPointCount"],
        ), path.name


@needs_model
def test_stripping_removes_the_mouth_and_keeps_everything_else():
    path = MOTIONS_DIR / "mtnBody_point2.motion3.json"
    motion = json.loads(path.read_text(encoding="utf-8"))
    stripped = strip_mouth_curves(motion)

    original_ids = [c["Id"] for c in motion["Curves"]]
    kept_ids = [c["Id"] for c in stripped["Curves"]]
    assert set(original_ids) & MOUTH_CURVE_IDS, "元から口カーブが無いのだ"
    assert not set(kept_ids) & MOUTH_CURVE_IDS
    assert kept_ids == [i for i in original_ids if i not in MOUTH_CURVE_IDS]


@needs_model
def test_stripped_metadata_matches_the_curves_that_remain():
    motion = json.loads((MOTIONS_DIR / "mtnBody_wave2.motion3.json").read_text(encoding="utf-8"))
    stripped = strip_mouth_curves(motion)
    segments = points = 0
    for curve in stripped["Curves"]:
        curve_segments, curve_points = _count(curve["Segments"])
        segments += curve_segments
        points += curve_points
    meta = stripped["Meta"]
    assert meta["CurveCount"] == len(stripped["Curves"])
    assert meta["TotalSegmentCount"] == segments
    assert meta["TotalPointCount"] == points


@needs_model
def test_the_cached_copy_is_reused_rather_than_rewritten():
    source = MOTIONS_DIR / "mtnBody_yes.motion3.json"
    first = _stripped_copy(source)
    assert first.exists()
    stamp = first.stat().st_mtime_ns
    assert _stripped_copy(source) == first
    assert first.stat().st_mtime_ns == stamp, "毎回書き直してるのだ"


@needs_model
def test_the_patched_model_keeps_motion_order_and_points_at_the_copies():
    """The indices in live2d_motions.py are positions in this list."""
    original = json.loads((MOTIONS_DIR.parent / "zundamon.model3.json").read_text(encoding="utf-8"))
    patched = json.loads(lipsync_safe_model(MOTIONS_DIR.parent / "zundamon.model3.json").read_text(encoding="utf-8"))
    before = [Path(e["File"]).name for e in original["FileReferences"]["Motions"][""]]
    after = [Path(e["File"]).name for e in patched["FileReferences"]["Motions"][""]]
    assert before == after
    assert all(
        "motions_lipsync_safe" in e["File"] for e in patched["FileReferences"]["Motions"][""]
    )


@needs_model
def test_the_copies_are_written_the_way_cubism_can_read_them():
    """Tab indentation and LF newlines, measured -- a compact dump or CRLF
    loads without error and then animates nothing at all (2026-09-11)."""
    raw = _stripped_copy(MOTIONS_DIR / "mtnBody_wave2.motion3.json").read_bytes()
    assert b"\r\n" not in raw, "CRLFだと読めないのだ"
    assert b"\n\t" in raw, "タブ字下げでないと読めないのだ"

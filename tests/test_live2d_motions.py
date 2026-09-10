import json
from pathlib import Path

import pytest

from mascot.live2d_expressions import EXPRESSION_PRESETS
from mascot.live2d_motions import EXPRESSION_MOTIONS, is_face_only, motion_for

MODEL_DIR = Path(__file__).resolve().parent.parent / "assets" / "live2d" / "zundamon" / "runtime"
MODEL_JSON = MODEL_DIR / "zundamon.model3.json"

needs_model = pytest.mark.skipif(
    not MODEL_JSON.exists(), reason="Live2Dモデルは同梱していないのだ(各自で入手する素材)"
)


def _shipped_motion_names() -> list[str]:
    """Motion file stems in model3.json order -- the order StartMotion indexes."""
    data = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    entries = data["FileReferences"]["Motions"][""]
    return [Path(entry["File"]).stem.removesuffix(".motion3") for entry in entries]


@needs_model
def test_every_motion_index_matches_the_name_beside_it():
    """The index is what actually plays; the name is only there to be read.

    They can silently drift apart when the table is edited, and a wrong index
    plays a plausible-looking but wrong gesture -- exactly the failure the
    filmstrip pass was meant to end.
    """
    shipped = _shipped_motion_names()
    for preset, (index, motion_name) in EXPRESSION_MOTIONS.items():
        assert 0 <= index < len(shipped), f"{preset}: {index} は範囲外なのだ"
        assert shipped[index] == motion_name, (
            f"{preset}: {index} は {shipped[index]!r} で、表の {motion_name!r} と違うのだ"
        )


def test_every_motion_belongs_to_a_real_expression_preset():
    unknown = set(EXPRESSION_MOTIONS) - set(EXPRESSION_PRESETS)
    assert not unknown, f"表情プリセットに無い名前があるのだ: {sorted(unknown)}"


def test_face_only_motions_are_recognised_by_prefix():
    assert is_face_only("mtnFace_laugh")
    assert not is_face_only("mtnBody_wave2")


def test_lipsync_talking_motion_is_not_used():
    """mtnFace_talk animates the mouth, which lipsync writes every frame."""
    assert all(name != "mtnFace_talk" for _, name in EXPRESSION_MOTIONS.values())


def test_motion_for_returns_none_for_presets_without_a_gesture():
    assert motion_for("normal") is None
    assert motion_for("greeting") is not None

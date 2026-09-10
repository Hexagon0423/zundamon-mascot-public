from pathlib import Path

import pytest

from mascot.assets import available_sets, load_manifest

SETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sets"


def test_both_placeholder_sets_are_available():
    assert set(available_sets(SETS_DIR)) >= {"vowel_5", "aperture_3"}


@pytest.mark.skipif(
    not (SETS_DIR / "zundamon_kai" / "manifest.json").exists(),
    reason="assets/sets/zundamon_kai/ が無い(README参照、各自入手)",
)
def test_placeholder_sets_can_be_left_out():
    """The 立ち絵 switcher hides them; they're only there for the tests."""
    names = available_sets(SETS_DIR, include_placeholders=False)
    assert "vowel_5" not in names
    assert "aperture_3" not in names
    assert "zundamon_kai" in names


@pytest.mark.parametrize("set_name", ["vowel_5", "aperture_3"])
def test_every_declared_layer_image_exists(set_name):
    manifest = load_manifest(set_name, SETS_DIR)
    for part in manifest.parts.values():
        for path in part.layers.values():
            assert path.exists()


@pytest.mark.parametrize("set_name", ["vowel_5", "aperture_3"])
def test_every_vowel_maps_to_a_layer_the_set_actually_has(set_name):
    """The point of the mapping layer: art doesn't have to provide あいうえお."""
    manifest = load_manifest(set_name, SETS_DIR)
    for vowel in ("a", "i", "u", "e", "o", "N", "pau", "cl"):
        layer = manifest.mouth_layer_for_vowel(vowel)
        assert manifest.mouth.has(layer), f"{set_name}: {vowel} -> {layer} が存在しない"


def test_vowel_set_maps_each_vowel_to_its_own_mouth():
    manifest = load_manifest("vowel_5", SETS_DIR)
    assert manifest.mouth_layer_for_vowel("a") == "a"
    assert manifest.mouth_layer_for_vowel("i") == "i"
    assert manifest.mouth_layer_for_vowel("pau") == "closed"


def test_aperture_set_collapses_vowels_onto_openness_levels():
    """Mirrors 坂本アヒル's art, which has むふ/ほー/ほあー rather than vowels."""
    manifest = load_manifest("aperture_3", SETS_DIR)
    assert manifest.mouth_layer_for_vowel("a") == "open"
    assert manifest.mouth_layer_for_vowel("i") == "half"
    assert manifest.mouth_layer_for_vowel("N") == "closed"


def test_unknown_vowel_falls_back_to_the_default_mouth():
    manifest = load_manifest("vowel_5", SETS_DIR)
    assert manifest.mouth_layer_for_vowel("???") == manifest.mouth.default


def test_layer_path_falls_back_to_default_for_unknown_layer():
    manifest = load_manifest("vowel_5", SETS_DIR)
    eyes = manifest.parts["eyes"]
    assert eyes.layer_path("nonexistent") == eyes.layer_path(eyes.default)


def test_missing_set_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest("does_not_exist", tmp_path)


@pytest.mark.parametrize("set_name", ["vowel_5", "aperture_3"])
def test_layer_order_covers_every_part(set_name):
    manifest = load_manifest(set_name, SETS_DIR)
    assert set(manifest.layer_order) == set(manifest.parts)


def test_mirror_default_defaults_to_false_when_absent():
    manifest = load_manifest("vowel_5", SETS_DIR)
    assert manifest.mirror_default is False


@pytest.mark.skipif(
    not (SETS_DIR / "seihuku" / "manifest.json").exists(),
    reason="assets/sets/seihuku/ が無い(README参照、各自入手)",
)
def test_seihuku_declares_mirror_default():
    """seihuku's source art faces the opposite way from zundamon_kai's, so
    it opts into window.py's auto-flip inversion (see AssetManifest.mirror_default)."""
    manifest = load_manifest("seihuku", SETS_DIR)
    assert manifest.mirror_default is True

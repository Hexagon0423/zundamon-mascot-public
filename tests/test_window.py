from pathlib import Path

import pytest

from mascot.assets import load_manifest
from mascot.window import (
    CROSSED_LEFT_ARM_KEY,
    EXPRESSION_LABELS,
    EXPRESSION_PRESETS,
    HIDDEN_RIGHT_ARM_KEY,
    IDLE_POSE_CHOICES,
    SEIHUKU_EXPRESSION_PRESETS,
)

SETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sets"

# zundamon_kai/seihuku はライセンス上このリポジトリに同梱しない実素材(README参照)。
# 無い環境(clone直後やCI)では、それらを読み込むテストだけskipする。
# EXPRESSION_PRESETS/SEIHUKU_EXPRESSION_PRESETSの中身そのものを検証するテスト
# (辞書の形だけを見るもの)は素材が無くても常に実行する。
_needs_zundamon_kai = pytest.mark.skipif(
    not (SETS_DIR / "zundamon_kai" / "manifest.json").exists(),
    reason="assets/sets/zundamon_kai/ が無い(README参照、各自入手)",
)
_needs_seihuku = pytest.mark.skipif(
    not (SETS_DIR / "seihuku" / "manifest.json").exists(),
    reason="assets/sets/seihuku/ が無い(README参照、各自入手)",
)


def test_every_expression_preset_is_a_full_pose():
    """See the big comment above EXPRESSION_PRESETS: every preset must set
    all five parts, or switching between presets can leave a stale part
    (e.g. an arm) from whatever was set before."""
    expected_parts = {"brow", "eyes", "body", "right_arm", "left_arm"}
    for name, preset in EXPRESSION_PRESETS.items():
        assert set(preset) == expected_parts, f"{name} does not set exactly {expected_parts}"


@_needs_zundamon_kai
def test_every_expression_preset_resolves_on_zundamon_kai():
    manifest = load_manifest("zundamon_kai", SETS_DIR)
    for name, preset in EXPRESSION_PRESETS.items():
        for part_name, layer_key in preset.items():
            part = manifest.parts.get(part_name)
            assert part is not None, f"{name}: part {part_name!r} does not exist"
            assert part.has(layer_key), f"{name}: {part_name}={layer_key!r} does not exist"


def test_no_zundamon_kai_preset_sets_mouth():
    """zundamon_kai の口は開き具合3段階しか無く感情を表せないので、
    プリセットで指定しても意味が無い(seihukuは口が表情ベースなので別扱い)。"""
    for name, preset in EXPRESSION_PRESETS.items():
        assert "mouth" not in preset, f"{name} sets mouth, which this art can't express"


def test_every_expression_preset_has_a_japanese_label():
    assert set(EXPRESSION_PRESETS) == set(EXPRESSION_LABELS)


def test_no_expression_preset_shows_the_right_arm_under_crossed_left_arm():
    """腕組み(crossed)'s art already draws both arms; leaving the right arm
    at anything but "none" makes it look like a third arm is sticking out
    from behind the crossed pose."""
    for name, preset in EXPRESSION_PRESETS.items():
        if preset["left_arm"] == CROSSED_LEFT_ARM_KEY:
            assert preset["right_arm"] == HIDDEN_RIGHT_ARM_KEY, (
                f"{name}: left_arm=crossed but right_arm={preset['right_arm']!r}"
            )


def test_every_preset_is_visually_distinct():
    """zundamon_kai の眉は前髪に隠れて画面上ほぼ見えない(2026-09-09の目視精査で判明)。
    そのため眉だけが違うプリセットは実機で完全に同じ絵になる -- 実際に
    sad/patient_wait と confident/skeptical がこの状態だった。
    見える部分(目・両腕・体)の組み合わせが一意であることを強制する。"""
    seen: dict[tuple[str, ...], str] = {}
    for name, preset in EXPRESSION_PRESETS.items():
        visible = tuple(preset[part] for part in ("eyes", "body", "right_arm", "left_arm"))
        assert visible not in seen, f"{name} は {seen.get(visible)} と見た目が同じになる: {visible}"
        seen[visible] = name


def test_every_idle_pose_choice_is_a_real_expression_preset():
    for name in IDLE_POSE_CHOICES:
        assert name in EXPRESSION_PRESETS, f"idle pose {name!r} is not in EXPRESSION_PRESETS"


# -- seihuku: its own preset vocabulary (no arms, has effect/decoration) ----


def test_seihuku_presets_use_the_same_names_as_zundamon_kai():
    """say.sh's expression argument doesn't know which art set is active, so
    every preset name must exist in every set's table (or it silently does
    nothing on whichever set doesn't define it)."""
    assert set(SEIHUKU_EXPRESSION_PRESETS) == set(EXPRESSION_PRESETS)


def test_every_seihuku_preset_is_a_full_pose():
    # zundamon_kai と違い mouth も含む -- この素材の口は開き具合ではなく
    # 表情そのもの(真顔/あんぐり/うぜぇ口...)なので、感情表現の主役の一つ。
    expected_parts = {"brow", "eyes", "mouth", "body", "effect", "decoration"}
    for name, preset in SEIHUKU_EXPRESSION_PRESETS.items():
        assert set(preset) == expected_parts, f"{name} does not set exactly {expected_parts}"


@_needs_seihuku
def test_every_seihuku_preset_resolves_on_seihuku():
    manifest = load_manifest("seihuku", SETS_DIR)
    for name, preset in SEIHUKU_EXPRESSION_PRESETS.items():
        for part_name, layer_key in preset.items():
            part = manifest.parts.get(part_name)
            assert part is not None, f"{name}: part {part_name!r} does not exist"
            assert part.has(layer_key), f"{name}: {part_name}={layer_key!r} does not exist"


@_needs_seihuku
def test_every_seihuku_preset_mouth_resolves():
    """seihuku は逆に mouth を必ず指定する(発話終了後に戻る「静止時の口」になる)。"""
    manifest = load_manifest("seihuku", SETS_DIR)
    for name, preset in SEIHUKU_EXPRESSION_PRESETS.items():
        key = preset["mouth"]
        assert manifest.parts["mouth"].has(key), f"{name}: mouth={key!r} does not exist"


def test_every_seihuku_preset_has_a_japanese_label():
    assert set(SEIHUKU_EXPRESSION_PRESETS) == set(EXPRESSION_LABELS)


def test_every_seihuku_preset_is_visually_distinct():
    """zundamon_kaiと同じ理由(眉が前髪に隠れて見えない)で、seihukuでも眉だけが違う
    プリセットは実機で同じ絵になる -- 精査前は thinking/patient_wait と
    determined/normal がこの状態だった。mouthはseihukuでは(zundamon_kaiと違い)
    はっきり見えるので、判定対象に含める。"""
    seen: dict[tuple[str, ...], str] = {}
    for name, preset in SEIHUKU_EXPRESSION_PRESETS.items():
        visible = tuple(preset[part] for part in ("eyes", "mouth", "body", "effect", "decoration"))
        assert visible not in seen, f"{name} は {seen.get(visible)} と見た目が同じになる: {visible}"
        seen[visible] = name


@_needs_seihuku
def test_seihuku_mouth_returns_to_the_expression_after_speech(qapp):
    """発話中はlipsyncが口を奪うが、黙っている間は表情プリセットの口に戻る
    (でないと怒っていても悲しんでいても笑顔の口のままになる)。"""
    from mascot.config import Config
    from mascot.window import MascotWindow

    window = MascotWindow(load_manifest("seihuku", SETS_DIR), Config(), config_path=None)
    window.apply_expression("angry")
    resting = window._selection["mouth"]
    assert resting == SEIHUKU_EXPRESSION_PRESETS["angry"]["mouth"]

    window.set_mouth_for_vowel("a")  # 発話中: lipsyncが上書きする
    assert window._selection["mouth"] != resting

    window.restore_resting_mouth()  # 発話終了
    assert window._selection["mouth"] == resting


@_needs_zundamon_kai
def test_zundamon_kai_mouth_returns_to_silence_after_speech(qapp):
    """口が開き具合しか無いセットでは従来どおり閉じ口に戻るだけ。"""
    from mascot.config import Config
    from mascot.window import MascotWindow

    window = MascotWindow(load_manifest("zundamon_kai", SETS_DIR), Config(), config_path=None)
    window.apply_expression("angry")
    window.set_mouth_for_vowel("a")
    window.restore_resting_mouth()
    assert window._selection["mouth"] == "closed"


@_needs_seihuku
def test_every_seihuku_effect_and_decoration_is_used_at_least_once():
    """A previous version left effect/decoration at "none" almost everywhere,
    which read as flat/boring (2026-09-09 feedback). Every non-"none" option
    the art actually has must appear in at least one preset.

    Exception: "blush2" (頬の濃いめ版). shy originally paired it with
    red_cheeks, but the two together looked darkened/dirty rather than
    rosy, so per user feedback (2026-09-09) shy now uses red_cheeks alone
    and blush2 is deliberately unused for now."""
    manifest = load_manifest("seihuku", SETS_DIR)
    INTENTIONALLY_UNUSED = {"effect": {"blush2"}}
    for part_name in ("effect", "decoration"):
        available = set(manifest.parts[part_name].layers) - {"none"}
        available -= INTENTIONALLY_UNUSED.get(part_name, set())
        used = {preset[part_name] for preset in SEIHUKU_EXPRESSION_PRESETS.values()} - {"none"}
        missing = available - used
        assert not missing, f"{part_name}: never used by any preset: {missing}"


@_needs_seihuku
def test_composite_cache_stays_within_budget_while_talking(qapp):
    """組み合わせをキーにしたキャッシュは上限が無いと積み上がり続ける
    (2026-09-09: seihukuは合成1枚が約49MB・組み合わせ62万通りあり、
    口パク×まばたき×表情の掛け算でプロセスが1.5GBまで膨らんだ)。"""
    from mascot.config import Config
    from mascot.window import COMPOSITE_CACHE_BYTES, FLIPPED_CACHE_BYTES, MascotWindow

    window = MascotWindow(load_manifest("seihuku", SETS_DIR), Config(), config_path=None)

    # 全組み合わせを試す必要は無く、予算を超える数だけ違うフレームを描ければ
    # 十分(seihukuは1枚が重いので回す数は控えめにする)。
    eyes_layers = list(window.manifest.parts["eyes"].layers)
    for i in range(24):
        window.set_part("eyes", eyes_layers[i % len(eyes_layers)])
        window.set_mouth_for_vowel("aiueo"[i % 5])

    assert window._composite_cache.nbytes <= COMPOSITE_CACHE_BYTES
    assert window._flipped_cache.nbytes <= FLIPPED_CACHE_BYTES


@_needs_seihuku
def test_layer_cache_stays_within_budget(qapp):
    from mascot.config import Config
    from mascot.window import LAYER_CACHE_BYTES, MascotWindow

    window = MascotWindow(load_manifest("seihuku", SETS_DIR), Config(), config_path=None)
    for part_name, part in window.manifest.parts.items():
        for layer_key in part.layers:
            window.set_part(part_name, layer_key)

    assert window._layer_cache.nbytes <= LAYER_CACHE_BYTES


@_needs_seihuku
def test_layers_are_cropped_to_their_opaque_area(qapp):
    """フル画角のまま持つと seihuku の80レイヤーで3.9GBになる。不透明部分だけ
    切り出せば同じ絵を93MB程度で描ける(切り出し位置はoffsetで補う)。"""
    from mascot.config import Config
    from mascot.window import MascotWindow

    window = MascotWindow(load_manifest("seihuku", SETS_DIR), Config(), config_path=None)
    manifest = window.manifest

    mouth_key = next(iter(manifest.parts["mouth"].layers))
    mouth = window._layer("mouth", mouth_key)
    assert mouth.pixmap.width() < manifest.width
    assert mouth.pixmap.height() < manifest.height
    assert mouth.offset.x() > 0 and mouth.offset.y() > 0


def test_lru_cache_evicts_least_recently_used():
    from mascot.window import _LruBudgetedCache

    cache = _LruBudgetedCache(max_bytes=20)
    cache.put("a", 1, 10)
    cache.put("b", 2, 10)
    assert cache.get("a") == 1  # "a" を触ったので "b" が最古になる
    cache.put("c", 3, 10)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.nbytes == 20


def test_lru_cache_keeps_an_entry_bigger_than_the_whole_budget():
    """次に描くフレームを捨ててしまうと毎フレーム作り直しになる。"""
    from mascot.window import _LruBudgetedCache

    cache = _LruBudgetedCache(max_bytes=10)
    cache.put("huge", "x", 999)
    assert cache.get("huge") == "x"
    assert len(cache) == 1

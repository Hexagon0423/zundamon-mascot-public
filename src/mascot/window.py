"""Frameless, transparent, always-on-top mascot window.

Draws the art by compositing one layer per part (body/right_arm/left_arm/
head_base/brow/eyes/mouth for the zundamon_kai set -- the exact part list is
whatever the manifest declares) and runs the blink timer. Speech logic lives
in speaker.py -- this class only knows how to show a given selection of
parts.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QGuiApplication,
    QImage,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QLabel, QMenu, QWidget

from mascot.assets import AssetManifest
from mascot.config import Config, WindowPosition, save_config
from mascot.geometry import clamp_onto_screen
from mascot.lipsync import SILENT_VOWEL

# Cache budgets, in bytes of raster.
#
# Counting *entries* would not bound anything useful here: one composited
# frame is 0.5MB for the placeholder sets and 49MB for seihuku (2800x4600),
# so any entry count that keeps seihuku affordable throws away every useful
# frame of the small sets, and vice versa. Budgeting bytes gives both sets
# the same footprint and lets each keep as many frames as it can afford.
#
# Bounding this at all is the point: keyed by a *combination* of layers,
# these caches grow with the product of the part counts, not their sum.
# seihuku has 625,152 combinations; left unbounded, ordinary use (口パクで
# mouth、まばたきで eyes、表情で brow が入れ替わる) walked that product and
# pushed the process past 1.5GB (2026-09-09).
#
# The composite budget is the one that matters for smoothness -- it wants to
# hold a whole vowel cycle plus the resting frame, or lipsync recomposites
# every frame -- so it gets the largest share.
MB = 1024 * 1024
COMPOSITE_CACHE_BYTES = 320 * MB
FLIPPED_CACHE_BYTES = 96 * MB
# Layers are stored cropped to their opaque area (see _load_layer), which
# takes all 80 seihuku layers together from 3.9GB down to ~93MB -- so this
# budget holds every layer of every set we ship, and exists only to keep a
# hypothetical huge set from growing without limit.
LAYER_CACHE_BYTES = 128 * MB


def _pixmap_bytes(pixmap: QPixmap) -> int:
    return pixmap.width() * pixmap.height() * pixmap.depth() // 8


@dataclass(frozen=True)
class _Layer:
    """One part's image, cropped to its opaque area, and where it belongs.

    立ち絵 layers are exported at full canvas size with everything outside
    the part transparent, so a mouth ships as a 2800x4600 image that is
    empty except for a few hundred pixels. Keeping the crop plus its offset
    draws identically while costing a fraction of the memory.
    """

    pixmap: QPixmap
    offset: QPoint

    @property
    def nbytes(self) -> int:
        return _pixmap_bytes(self.pixmap)


def _load_layer(path: Path) -> _Layer:
    with Image.open(path) as image:
        image = image.convert("RGBA")
        bbox = image.getbbox()
        if bbox is None:  # fully transparent (e.g. an "none" effect layer)
            return _Layer(QPixmap(), QPoint(0, 0))
        cropped = image.crop(bbox)
        # Copy out of the PIL buffer: QImage does not own the bytes it is
        # handed, and `cropped` dies at the end of this function.
        qimage = QImage(
            cropped.tobytes("raw", "RGBA"),
            cropped.width,
            cropped.height,
            QImage.Format_RGBA8888,
        ).copy()
    return _Layer(QPixmap.fromImage(qimage), QPoint(bbox[0], bbox[1]))


class _LruBudgetedCache:
    """Least-recently-used cache bounded by the total bytes it holds.

    functools.lru_cache would do the same job, but attaching it to a method
    keyed on self would tie every cached pixmap's lifetime to the class
    rather than the window, it counts entries rather than bytes, and it
    can't be cleared per-instance (set_scale needs that).
    """

    def __init__(self, max_bytes: int):
        self._max_bytes = max_bytes
        self._entries: OrderedDict = OrderedDict()
        self._sizes: dict = {}
        self._nbytes = 0

    def get(self, key):
        value = self._entries.get(key)
        if value is not None:
            self._entries.move_to_end(key)
        return value

    def put(self, key, value, nbytes: int):
        evicted = self._entries.pop(key, None)
        if evicted is not None:
            self._nbytes -= self._sizes.pop(key)
        self._entries[key] = value
        self._sizes[key] = nbytes
        self._nbytes += nbytes
        # Always keep the entry just stored, even if it alone busts the
        # budget: the caller is about to draw it, and evicting it would mean
        # rebuilding it on the very next frame.
        while len(self._entries) > 1 and self._nbytes > self._max_bytes:
            oldest, _ = self._entries.popitem(last=False)
            self._nbytes -= self._sizes.pop(oldest)
        return value

    def clear(self) -> None:
        self._entries.clear()
        self._sizes.clear()
        self._nbytes = 0

    @property
    def nbytes(self) -> int:
        return self._nbytes

    def __len__(self) -> int:
        return len(self._entries)


# Blink timing. Humans blink every few seconds; the closed phase is brief,
# with a half-open frame either side so it doesn't look like a hard cut.
BLINK_INTERVAL_RANGE_MS = (2500, 6500)
BLINK_HALF_MS = 40
BLINK_CLOSED_MS = 90

# Idle pose: every so often, settle into one of these full EXPRESSION_PRESETS
# at random. Deliberately mild/neutral presets only (not "angry"/"shock"/etc,
# which are for POST /speak and would read as a mood swing if they appeared
# unprompted) and deliberately infrequent (a full pose+expression change is a
# bigger visual event than the old brow-only flicker this replaced, so it
# needs more breathing room between switches to still read as "natural" idling
# rather than restless fidgeting). User-proposed set (2026-09-08).
IDLE_POSE_INTERVAL_RANGE_MS = (45_000, 90_000)
IDLE_POSE_CHOICES = ("normal", "casual", "casual_lean", "thinking", "patient_wait")

# Right-click menu presets for the "サイズ" submenu. 0.25 added 2026-09-09
# for seihuku, whose canvas (2800x4600) is much larger than zundamon_kai's
# (1082x1552) so the same scale reads far bigger on screen.
SCALE_PRESETS = (0.25, 0.375, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

# Right-click "ポーズ" submenus: which parts to expose, their Japanese label,
# and Japanese labels for each layer key (falls back to the raw key for a set
# that has the part but not that particular key, e.g. a future art set).
POSE_PART_MENUS: tuple[tuple[str, str], ...] = (
    ("body", "体"),
    ("right_arm", "右腕"),
    ("left_arm", "左腕"),
    ("effect", "エフェクト"),
    ("decoration", "装飾"),
)
POSE_LAYER_LABELS: dict[str, str] = {
    "upright": "直立",
    "lean": "前傾",
    "default": "基本",
    "down": "下",
    "down_diagonal": "斜め下",
    "side": "横",
    "point_side": "指さし横",
    "raise": "手を挙げる",
    "point_up": "指さし上",
    "chop": "チョップ",
    "mouth": "口元",
    "pocket_lean": "ポケット(前傾用)",
    "pocket_upright": "ポケット(直立用)",
    "crossed": "腕組み",
    "chin": "あごに指",
    "fist": "ぐっ",
    "pocket": "ポケット",
    "none": "なし",
    # seihuku: body
    "1": "腕組み",
    "2": "手を広げる",
    # seihuku: effect
    "vein": "青筋",
    "shadow": "影",
    "sweat2": "汗(大)",
    "sweat": "汗",
    "pale": "青ざめ",
    "blush2": "頬(濃)",
    "blush": "頬",
    # seihuku: decoration
    "antenna": "触角ピコピコ",
    "dot_sunglasses": "ドットサングラス",
    "sunglasses": "サングラス",
    "glasses": "めがね",
    "red_cheeks": "赤丸ほっぺ",
    "sparkle": "キラキラ",
    "anger_mark": "怒りマーク",
    "now_loading": "Now Loading",
    "sweat_drop": "汗マーク",
    "surprise_mark": "驚きマーク",
}

# 腕組み(crossed)の絵は左腕側に両腕分をまとめて描いてあり、PSD側も右腕を
# 専用の空レイヤー「(非表示)」に切り替える前提になっている(そのままだと
# 右腕の「基本」が下から透けて見えて、腕が3本あるように見えてしまう)。
# 手動メニューでもプリセットでも、左腕を"crossed"にしたら右腕を自動で
# "none"に揃える。
CROSSED_LEFT_ARM_KEY = "crossed"
HIDDEN_RIGHT_ARM_KEY = "none"

# Named expressions for POST /speak's `expression` field (and the right-click
# "表情" menu). Each preset is a *full pose*: every entry explicitly sets
# brow/eyes/body/right_arm/left_arm, even to "normal"/"open"/"upright"/
# "default" where the expression has no opinion about that part. This is
# deliberate -- presets used to only override the parts they cared about,
# but that meant switching from e.g. "shock" (which points a hand at the
# mouth) to "angry" left the hand stuck in place, since "angry" never said
# anything about right_arm. A full pose means every switch is a clean,
# intentional picture instead of an accumulating mix of past presets.
#
# zundamon_kaiのプリセットは`mouth`を指定しない。この素材の口は開き具合3段階
# (closed/half/open)しか無く、感情を表せないため指定する意味が無いからである。
# (口が表情ベースで揃っているseihukuでは事情が違う -- SEIHUKU_EXPRESSION_PRESETS参照)
#
# A name not listed here falls back to being treated as a brow key directly
# (see `apply_expression`), which is how single-part expressions worked
# before this table existed -- old callers keep working unchanged.
#
# 2026-09-09、全31プリセットをレンダリングして精査したときの重要な発見:
# **zundamon_kaiでは眉(brow)は前髪にほぼ完全に隠れて見えない**(angry2だけ額の端に
# わずかに線が出る程度)。つまり表情の識別は事実上 eyes + 腕・体のポーズだけで決まる。
# 精査前は眉頼みの区別が複数あり、`sad`と`patient_wait`、`confident`と`skeptical`が
# 画面上まったく同じ絵になっていた(眉しか違わなかったため)。`angry`も「普通の目で
# 腕組み」なだけで怒って見えなかった。
# そのため **eyes/right_arm/left_arm の組み合わせが全プリセットで一意** になるよう
# 組み直してある(test_every_preset_is_visually_distinctで担保)。プリセットを増減
# するときは、眉の違いだけで区別しようとしないこと。
EXPRESSION_PRESETS: dict[str, dict[str, str]] = {
    "normal": {"brow": "normal", "eyes": "open", "body": "upright", "right_arm": "default", "left_arm": "default"},
    "happy": {"brow": "normal", "eyes": "happy", "body": "upright", "right_arm": "default", "left_arm": "default"},
    "delighted": {"brow": "raised", "eyes": "happy", "body": "upright", "right_arm": "raise", "left_arm": "raise"},
    "celebrating": {"brow": "raised", "eyes": "happy", "body": "upright", "right_arm": "raise", "left_arm": "fist"},
    "proud": {"brow": "raised", "eyes": "flat", "body": "upright", "right_arm": "side", "left_arm": "fist"},
    "relieved": {"brow": "normal", "eyes": "closed", "body": "upright", "right_arm": "default", "left_arm": "mouth"},
    "shy": {"brow": "sad", "eyes": "squint", "body": "upright", "right_arm": "mouth", "left_arm": "default"},
    "greeting": {"brow": "normal", "eyes": "happy", "body": "upright", "right_arm": "raise", "left_arm": "default"},
    "casual": {"brow": "normal", "eyes": "open", "body": "upright", "right_arm": "pocket_upright", "left_arm": "pocket"},
    "casual_lean": {"brow": "normal", "eyes": "gentle", "body": "lean", "right_arm": "pocket_lean", "left_arm": "pocket"},
    "confident": {"brow": "normal", "eyes": "flat", "body": "upright", "right_arm": "none", "left_arm": "crossed"},
    "skeptical": {"brow": "raised", "eyes": "flat", "body": "upright", "right_arm": "side", "left_arm": "default"},
    "suspicious": {"brow": "raised", "eyes": "flat", "body": "upright", "right_arm": "default", "left_arm": "chin"},
    "serious": {"brow": "normal", "eyes": "intense", "body": "upright", "right_arm": "default", "left_arm": "default"},
    "angry": {"brow": "angry2", "eyes": "squint", "body": "upright", "right_arm": "none", "left_arm": "crossed"},
    "furious": {"brow": "angry2", "eyes": "squint", "body": "upright", "right_arm": "chop", "left_arm": "down_diagonal"},
    "warning_no": {"brow": "angry", "eyes": "wide", "body": "upright", "right_arm": "chop", "left_arm": "default"},
    "sad": {"brow": "sad", "eyes": "closed", "body": "upright", "right_arm": "mouth", "left_arm": "down"},
    "disappointed": {"brow": "sad", "eyes": "flat", "body": "upright", "right_arm": "down_diagonal", "left_arm": "default"},
    "worried": {"brow": "sad", "eyes": "flat", "body": "upright", "right_arm": "default", "left_arm": "mouth"},
    "panic": {"brow": "sad", "eyes": "wide", "body": "upright", "right_arm": "mouth", "left_arm": "mouth"},
    "shock": {"brow": "raised", "eyes": "wide", "body": "upright", "right_arm": "mouth", "left_arm": "default"},
    "scared": {"brow": "sad", "eyes": "wide", "body": "upright", "right_arm": "down", "left_arm": "down"},
    "dazed": {"brow": "normal", "eyes": "dazed", "body": "upright", "right_arm": "down", "left_arm": "down"},
    "thinking": {"brow": "normal", "eyes": "gentle", "body": "upright", "right_arm": "default", "left_arm": "chin"},
    "confused": {"brow": "raised", "eyes": "dazed", "body": "upright", "right_arm": "side", "left_arm": "chin"},
    "explaining": {"brow": "normal", "eyes": "open", "body": "upright", "right_arm": "point_side", "left_arm": "default"},
    "eureka": {"brow": "raised", "eyes": "happy", "body": "upright", "right_arm": "point_up", "left_arm": "default"},
    "patient_wait": {"brow": "normal", "eyes": "closed", "body": "upright", "right_arm": "default", "left_arm": "default"},
    "effort": {"brow": "angry", "eyes": "squint", "body": "upright", "right_arm": "default", "left_arm": "fist"},
}

# seihuku(2026-09-09追加、制服姿の別立ち絵セット)向けの表情プリセット。zundamon_kaiと
# 違い右腕・左腕は無いが、bodyには"1"(腕組み、既定)と"2"(片手を開いたジェスチャー)という
# 2種類の意味あるポーズがある(right_arm/left_armが無いだけでbodyは無意味ではないので、
# zundamon_kaiと同じくフルポーズとして明示する)。effect(汗・青筋等)とdecoration
# (サングラス・キラキラ等)という2つの新しいパーツも持つ。キー名の語彙もzundamon_kaiと
# 非互換(例: eyesは"open"ではなく"normal_look1")なので、同じプリセット名(normal/happy/
# shock等)でもセットごとに別の辞書として持つ。全パーツ明示のフルポーズという
# ルールはzundamon_kaiと同じ。
#
# ただしzundamon_kaiと違い、**mouthも指定する**(2026-09-09の精査で変更)。
# この素材の口は開き具合ではなく表情そのもの(真顔・ω・あんぐり・うぜぇ口・涎...)で
# 揃っているため、口を固定にすると怒っても悲しんでも笑顔の口のままになってしまい、
# それが「表情が合っていない」最大の原因になっていた。発話中はlipsyncが口を
# 奪うが、マスコットが黙って立っている時間の方が圧倒的に長いので、発話終了時に
# ここで指定した口へ戻す(speaker.py→MascotWindow.restore_resting_mouth)。
#
# 初版はeffect/decorationをほとんど"none"のまま残していて「表情のバリエーションが
# しょぼい」と指摘された(2026-09-09)。作り直す際、実在する7種のeffectと10種の
# decoration(noneを除く)を全部どこかのプリセットで最低1回は使うようにした
# (test_every_seihuku_effect_and_decoration_is_used_at_least_onceで担保)。
SEIHUKU_EXPRESSION_PRESETS: dict[str, dict[str, str]] = {
    "normal": {"brow": "normal", "mouth": "smile", "eyes": "normal_look1", "body": "1", "effect": "none", "decoration": "none"},
    "happy": {"brow": "normal", "mouth": "smile", "eyes": "smile", "body": "1", "effect": "blush", "decoration": "none"},
    "delighted": {"brow": "proud", "mouth": "smile_open", "eyes": "heart_look1", "body": "2", "effect": "blush", "decoration": "sparkle"},
    "celebrating": {"brow": "proud", "mouth": "smile_teeth", "eyes": "smile", "body": "2", "effect": "blush", "decoration": "antenna"},
    "proud": {"brow": "proud", "mouth": "omega", "eyes": "half_look1", "body": "1", "effect": "blush", "decoration": "dot_sunglasses"},
    "relieved": {"brow": "normal", "mouth": "smile", "eyes": "closed2", "body": "1", "effect": "blush", "decoration": "none"},
    "shy": {"brow": "sad", "mouth": "smile", "eyes": "closed", "body": "1", "effect": "none", "decoration": "red_cheeks"},
    "greeting": {"brow": "normal", "mouth": "smile_open", "eyes": "smile", "body": "2", "effect": "none", "decoration": "none"},
    "casual": {"brow": "normal", "mouth": "neutral", "eyes": "narrow_look1", "body": "1", "effect": "none", "decoration": "glasses"},
    "casual_lean": {"brow": "normal", "mouth": "smile", "eyes": "narrow_look1", "body": "1", "effect": "none", "decoration": "none"},
    "confident": {"brow": "proud", "mouth": "smile", "eyes": "half_look1", "body": "1", "effect": "none", "decoration": "sunglasses"},
    "skeptical": {"brow": "furrowed", "mouth": "neutral_teeth", "eyes": "narrow_look2", "body": "1", "effect": "none", "decoration": "none"},
    "suspicious": {"brow": "asymmetric", "mouth": "neutral", "eyes": "half_noshine_look1", "body": "1", "effect": "shadow", "decoration": "none"},
    "serious": {"brow": "furrowed", "mouth": "neutral", "eyes": "narrow_look1", "body": "1", "effect": "none", "decoration": "none"},
    "angry": {"brow": "angry", "mouth": "annoyed", "eyes": "angry", "body": "1", "effect": "none", "decoration": "anger_mark"},
    "furious": {"brow": "angry", "mouth": "agape", "eyes": "angry", "body": "1", "effect": "vein", "decoration": "anger_mark"},
    "warning_no": {"brow": "angry", "mouth": "neutral", "eyes": "half_look1", "body": "2", "effect": "none", "decoration": "anger_mark"},
    "sad": {"brow": "sad", "mouth": "neutral", "eyes": "tears_look1", "body": "1", "effect": "none", "decoration": "none"},
    "disappointed": {"brow": "sad", "mouth": "neutral", "eyes": "half_look1", "body": "1", "effect": "shadow", "decoration": "none"},
    "worried": {"brow": "sad", "mouth": "neutral", "eyes": "normal_look1", "body": "1", "effect": "sweat", "decoration": "sweat_drop"},
    "panic": {"brow": "sad", "mouth": "agape2", "eyes": "surprised_look1", "body": "2", "effect": "sweat2", "decoration": "surprise_mark"},
    "shock": {"brow": "normal", "mouth": "agape", "eyes": "surprised_look1", "body": "1", "effect": "pale", "decoration": "surprise_mark"},
    "scared": {"brow": "sad", "mouth": "neutral", "eyes": "surprised_look1", "body": "1", "effect": "pale", "decoration": "sweat_drop"},
    "dazed": {"brow": "normal", "mouth": "drool", "eyes": "white", "body": "1", "effect": "none", "decoration": "none"},
    "thinking": {"brow": "normal", "mouth": "neutral", "eyes": "normal_look2", "body": "1", "effect": "none", "decoration": "now_loading"},
    "confused": {"brow": "asymmetric", "mouth": "neutral", "eyes": "dizzy", "body": "1", "effect": "sweat", "decoration": "sweat_drop"},
    "explaining": {"brow": "normal", "mouth": "smile_open", "eyes": "normal_look1", "body": "2", "effect": "none", "decoration": "none"},
    "eureka": {"brow": "proud", "mouth": "smile_open", "eyes": "surprised_look1", "body": "2", "effect": "none", "decoration": "sparkle"},
    "patient_wait": {"brow": "normal", "mouth": "smile", "eyes": "closed", "body": "1", "effect": "none", "decoration": "none"},
    "effort": {"brow": "furrowed", "mouth": "neutral_teeth", "eyes": "squint", "body": "1", "effect": "sweat", "decoration": "sweat_drop"},
}

# セット名(manifestのnameフィールド) → そのセット専用のプリセット辞書。
# 無いセット(zundamon_kai等)はEXPRESSION_PRESETSにフォールバックする。
EXPRESSION_PRESETS_BY_SET: dict[str, dict[str, dict[str, str]]] = {
    "seihuku": SEIHUKU_EXPRESSION_PRESETS,
}

# Japanese labels for the right-click "表情" submenu.
EXPRESSION_LABELS: dict[str, str] = {
    "normal": "ノーマル",
    "happy": "うれしい",
    "delighted": "はしゃぐ",
    "celebrating": "お祝い",
    "proud": "どや顔",
    "relieved": "ホッと",
    "shy": "照れ",
    "greeting": "あいさつ",
    "casual": "カジュアル",
    "casual_lean": "リラックス",
    "confident": "自信",
    "skeptical": "うたがい",
    "suspicious": "あやしむ",
    "serious": "真剣",
    "angry": "怒り",
    "furious": "激怒",
    "warning_no": "だめ",
    "sad": "悲しい",
    "disappointed": "がっかり",
    "worried": "不安",
    "panic": "パニック",
    "shock": "ガーン",
    "scared": "こわい",
    "dazed": "放心",
    "thinking": "考え中",
    "confused": "困惑",
    "explaining": "説明",
    "eureka": "ひらめき",
    "patient_wait": "待機",
    "effort": "踏ん張り",
}


class MascotWindow(QWidget):
    def __init__(self, manifest: AssetManifest, config: Config, config_path=None):
        super().__init__()
        self._manifest = manifest
        self._config = config
        self._config_path = config_path
        self._drag_offset: QPoint | None = None
        self._current_expression: str | None = None
        self._resting_mouth: str | None = None
        self._screen_changed_connected = False
        self._layer_cache = _LruBudgetedCache(LAYER_CACHE_BYTES)
        self._composite_cache = _LruBudgetedCache(COMPOSITE_CACHE_BYTES)
        self._flipped_cache = _LruBudgetedCache(FLIPPED_CACHE_BYTES)
        self._facing_flipped = False
        self._selection = manifest.default_selection()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # keeps it off the taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Treat the art's pixels as physical screen pixels. Qt sizes windows in
        # logical pixels, so on a scaled display (this machine runs at 150%)
        # giving it the art's pixel size would stretch the image and make it
        # blurry. Dividing by the ratio keeps the art pixel-perfect instead.
        #
        # The user-facing "size" setting (config.scale) is folded into this
        # same ratio rather than handled separately: dividing by a *smaller*
        # ratio makes the logical (on-screen) size larger for the same art,
        # which is exactly what "bigger" should mean. No raster rescaling
        # needed -- Qt scales the pixmap for display from the ratio metadata.
        screen = QGuiApplication.primaryScreen()
        self._raw_device_pixel_ratio = screen.devicePixelRatio() if screen else 1.0
        self._scale = config.scale if config.scale > 0 else 1.0
        self._device_pixel_ratio = self._raw_device_pixel_ratio / self._scale

        self._label = QLabel(self)
        self._apply_geometry()
        self._redraw()

        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._blink)
        self._schedule_blink()

        self._idle_pose_timer = QTimer(self)
        self._idle_pose_timer.setSingleShot(True)
        self._idle_pose_timer.timeout.connect(self._play_idle_pose)
        self._schedule_idle_pose()

        self._restore_position()

    @property
    def manifest(self) -> AssetManifest:
        return self._manifest

    # -- size -----------------------------------------------------------------

    def _apply_geometry(self) -> None:
        """Size the window (and label) for the current scale."""
        logical_width = round(self._manifest.width / self._device_pixel_ratio)
        logical_height = round(self._manifest.height / self._device_pixel_ratio)
        self.resize(logical_width, logical_height)
        self._label.setGeometry(0, 0, logical_width, logical_height)

    def set_scale(self, scale: float) -> None:
        if scale == self._scale:
            return
        self._scale = scale
        self._device_pixel_ratio = self._raw_device_pixel_ratio / self._scale
        # Cached composites carry the *old* ratio baked into their pixmap
        # metadata; regenerating them is cheap (a handful of combinations at
        # most), so just drop them rather than patching each one in place.
        self._composite_cache.clear()
        self._flipped_cache.clear()
        self._apply_geometry()
        self._update_facing()
        self._redraw()
        self._config.scale = scale
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    # -- drawing -------------------------------------------------------------

    def set_part(self, part_name: str, layer_key: str) -> None:
        part = self._manifest.parts.get(part_name)
        if part is None or self._selection.get(part_name) == layer_key:
            return
        self._selection[part_name] = layer_key if part.has(layer_key) else part.default
        self._redraw()
        if part_name == "left_arm" and layer_key == CROSSED_LEFT_ARM_KEY:
            self.set_part("right_arm", HIDDEN_RIGHT_ARM_KEY)

    def set_mouth_for_vowel(self, vowel: str) -> None:
        self.set_part("mouth", self._manifest.mouth_layer_for_vowel(vowel))

    def restore_resting_mouth(self) -> None:
        """Put the mouth back to whatever the current expression wants.

        Called when an utterance ends (see speaker.py). Lipsync owns the
        mouth *while speaking*, but the mascot then sits silent for minutes
        at a time, so the resting mouth is what the user actually looks at
        most. A set whose mouths are pure openness levels (zundamon_kai:
        closed/half/open) has nothing expressive to rest on and falls back
        to the silent mouth, exactly as before.
        """
        key = self._resting_mouth
        mouth = self._manifest.mouth
        if mouth is not None and key is not None and mouth.has(key):
            self.set_part("mouth", key)
        else:
            self.set_mouth_for_vowel(SILENT_VOWEL)

    def _expression_presets(self) -> dict[str, dict[str, str]]:
        """The preset table for the currently loaded art set.

        Different sets can use incompatible layer-key vocabularies (e.g.
        zundamon_kai's eyes="wide" vs seihuku's eyes="surprised_look1"), so
        each set that needs its own wording gets its own table in
        EXPRESSION_PRESETS_BY_SET; anything else falls back to the original
        EXPRESSION_PRESETS (harmless no-ops for parts the set doesn't have).
        """
        return EXPRESSION_PRESETS_BY_SET.get(self._manifest.name, EXPRESSION_PRESETS)

    def apply_expression(self, name: str) -> None:
        """Apply a named expression (see `EXPRESSION_PRESETS`).

        Falls back to treating `name` as a brow layer key directly, which is
        how `POST /speak`'s `expression` field behaved before presets existed
        -- callers passing "angry"/"sad" keep working unchanged.
        """
        preset = self._expression_presets().get(name, {"brow": name})
        for part_name, layer_key in preset.items():
            self.set_part(part_name, layer_key)
        self._current_expression = name
        self._resting_mouth = preset.get("mouth")

    def _redraw(self) -> None:
        key = tuple(self._selection[name] for name in self._manifest.layer_order)
        composite = self._composite_cache.get(key)
        if composite is None:
            composite = self._compose(key)
            self._composite_cache.put(key, composite, _pixmap_bytes(composite))
        if not self._facing_flipped:
            self._label.setPixmap(composite)
            return
        flipped = self._flipped_cache.get(key)
        if flipped is None:
            # Mirroring the flattened composite (rather than each layer
            # individually) keeps this a single cheap transform regardless of
            # how many parts the manifest has.
            flipped = composite.transformed(QTransform().scale(-1, 1))
            flipped.setDevicePixelRatio(self._device_pixel_ratio)
            self._flipped_cache.put(key, flipped, _pixmap_bytes(flipped))
        self._label.setPixmap(flipped)

    def _compose(self, selection: tuple[str, ...]) -> QPixmap:
        canvas = QPixmap(self._manifest.width, self._manifest.height)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        for part_name, layer_key in zip(self._manifest.layer_order, selection):
            layer = self._layer(part_name, layer_key)
            if not layer.pixmap.isNull():
                painter.drawPixmap(layer.offset, layer.pixmap)
        painter.end()
        canvas.setDevicePixelRatio(self._device_pixel_ratio)
        return canvas

    def _layer(self, part_name: str, layer_key: str) -> _Layer:
        cache_key = f"{part_name}/{layer_key}"
        layer = self._layer_cache.get(cache_key)
        if layer is None:
            path = self._manifest.parts[part_name].layer_path(layer_key)
            layer = _load_layer(path)
            self._layer_cache.put(cache_key, layer, layer.nbytes)
        return layer

    # -- blinking ------------------------------------------------------------

    def _schedule_blink(self) -> None:
        if self._manifest.eyes is None:
            return
        self._blink_timer.start(random.randint(*BLINK_INTERVAL_RANGE_MS))

    def _blink(self) -> None:
        """Run one blink: half -> closed -> half -> resting, then reschedule.

        Driven by its own timer and unrelated to speech, which is how blinking
        is conventionally handled. "Resting" is whatever `eyes` is set to
        right now -- not hardcoded to "open" -- so blinking doesn't stomp an
        active expression's eyes (e.g. "scared"'s `wide`) back to normal a
        few seconds after it was set.
        """
        eyes = self._manifest.eyes
        if eyes is None:
            return
        resting = self._selection.get("eyes", eyes.default)
        steps: list[tuple[int, str]] = [
            (0, "half"),
            (BLINK_HALF_MS, "closed"),
            (BLINK_HALF_MS + BLINK_CLOSED_MS, "half"),
            (BLINK_HALF_MS + BLINK_CLOSED_MS + BLINK_HALF_MS, resting),
        ]
        for delay_ms, layer in steps:
            if not eyes.has(layer):
                continue
            QTimer.singleShot(delay_ms, lambda key=layer: self.set_part("eyes", key))
        QTimer.singleShot(steps[-1][0], self._schedule_blink)

    # -- idle pose --------------------------------------------------------------

    def _schedule_idle_pose(self) -> None:
        if self._manifest.parts.get("brow") is None:
            return
        self._idle_pose_timer.start(random.randint(*IDLE_POSE_INTERVAL_RANGE_MS))

    def _play_idle_pose(self) -> None:
        """Settle into a random mild resting pose from IDLE_POSE_CHOICES.

        Independent of speech and blinking, same as the blink timer. Unlike
        blinking this doesn't revert afterward -- each choice (including
        "normal") is already a complete resting stance, not a transient
        flicker, so it just stays until the next tick (or a real expression
        from POST /speak takes over).
        """
        self.apply_expression(random.choice(IDLE_POSE_CHOICES))
        self._schedule_idle_pose()

    # -- facing (left/right mirror) --------------------------------------------

    def _update_facing(self) -> None:
        """Mirror the art when the window sits left of its screen's center.

        The composited art always faces the same way; on the left side of
        the screen that means facing off-screen, away from whatever the user
        is looking at. Flipping the whole flattened composite (rather than
        each part) is a single cheap transform and keeps every part in sync
        automatically -- there's no separate "flip" state to track per part.
        """
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        screen_center_x = geo.x() + geo.width() / 2
        window_center_x = self.pos().x() + self.width() / 2
        should_flip = window_center_x < screen_center_x
        if self._manifest.mirror_default:
            # This set's unflipped art faces the opposite way from the
            # assumption baked into the line above (see AssetManifest.mirror_default).
            should_flip = not should_flip
        if should_flip != self._facing_flipped:
            self._facing_flipped = should_flip
            self._redraw()

    # -- position persistence -------------------------------------------------

    def _restore_position(self) -> None:
        pos = self._config.window_position
        screen = QGuiApplication.primaryScreen()
        for candidate in QGuiApplication.screens():
            if pos and candidate.name() == pos.screen_name:
                screen = candidate
                break
        geo = screen.geometry()
        if pos is not None:
            x = geo.x() + int(pos.x_fraction * geo.width())
            y = geo.y() + int(pos.y_fraction * geo.height())
        else:
            x = geo.x() + geo.width() - self.width() - 40
            y = geo.y() + geo.height() - self.height() - 80
        x, y = clamp_onto_screen(
            x, y, self.width(), self.height(), (geo.x(), geo.y(), geo.width(), geo.height())
        )
        self.move(x, y)
        self._update_facing()

    def _save_position(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        pos = self.pos()
        self._config.window_position = WindowPosition(
            screen_name=screen.name(),
            x_fraction=(pos.x() - geo.x()) / geo.width(),
            y_fraction=(pos.y() - geo.y()) / geo.height(),
        )
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    # -- drag to move ---------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._update_facing()
            # A translucent frameless window on Windows doesn't always get a
            # full repaint from move() alone -- without this, dragging can
            # leave stale rectangles of the old position behind (the art
            # appears to "split" into quadrants as it's dragged). Crossing
            # onto a different monitor is the worst case of this (Qt
            # migrates the native backing store mid-drag), which is why
            # `_on_screen_changed` below forces a second repaint once that
            # migration actually lands.
            self.repaint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()

    # -- multi-monitor dragging -------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        # windowHandle() only exists once the native window has been created,
        # which happens on/after the first show -- connect here, once.
        handle = self.windowHandle()
        if handle is not None and not self._screen_changed_connected:
            handle.screenChanged.connect(self._on_screen_changed)
            self._screen_changed_connected = True

    def _on_screen_changed(self, _screen) -> None:
        """Force a full redraw once Qt has migrated to a new monitor.

        Dragging across a monitor boundary makes Qt recreate the native
        backing store mid-drag; a stale frame can be left showing until
        something forces a repaint, which is the "謎分割" (the art appears
        split/torn at the boundary) reported when moving the mascot between
        screens.
        """
        self._update_facing()
        self._redraw()
        self.repaint()

    # -- right-click menu -----------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        size_menu = menu.addMenu("サイズ")
        for preset in SCALE_PRESETS:
            percent = preset * 100
            label = f"{percent:g}%"  # e.g. 37.5% stays 37.5, whole numbers drop the decimal
            action = QAction(label, self, checkable=True)
            action.setChecked(preset == self._scale)
            action.triggered.connect(lambda _checked, s=preset: self.set_scale(s))
            size_menu.addAction(action)

        for part_name, part_label in POSE_PART_MENUS:
            part = self._manifest.parts.get(part_name)
            if part is None:
                continue
            part_menu = menu.addMenu(part_label)
            for layer_key in part.layers:
                label = POSE_LAYER_LABELS.get(layer_key, layer_key)
                action = QAction(label, self, checkable=True)
                action.setChecked(self._selection.get(part_name) == layer_key)
                action.triggered.connect(
                    lambda _checked, p=part_name, k=layer_key: self.set_part(p, k)
                )
                part_menu.addAction(action)

        if self._manifest.parts.get("brow") is not None:
            expression_menu = menu.addMenu("表情")
            for name in self._expression_presets():
                label = EXPRESSION_LABELS.get(name, name)
                action = QAction(label, self, checkable=True)
                action.setChecked(self._current_expression == name)
                action.triggered.connect(
                    lambda _checked, n=name: self.apply_expression(n)
                )
                expression_menu.addAction(action)

        toggle_click_through = QAction(
            "クリック透過を無効にする" if self._config.click_through else "クリック透過を有効にする",
            self,
        )
        toggle_click_through.triggered.connect(self._toggle_click_through)
        menu.addAction(toggle_click_through)

        quit_action = QAction("終了", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def _toggle_click_through(self) -> None:
        self._config.click_through = not self._config.click_through
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._config.click_through)
        if self._config_path is not None:
            save_config(self._config, self._config_path)

    def closeEvent(self, event):
        self._save_position()
        super().closeEvent(event)

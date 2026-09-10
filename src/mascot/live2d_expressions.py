"""Named expressions for the Live2D backend: each is a *combination* of the
model's own exp3.json entries (a face, plus an arm pose where one helps).

The model ships two kinds of expression file, distinguishable only by looking
at them (the ids themselves say nothing):
  - `exp_*` -- faces (eyes/brows/mouth/blush/tears), a few of which also pin
    the arms and so are used on their own here
  - `pose_*` -- arm poses only, with a neutral face

They all use "Add" blending, so stacking a face and a pose with
AddExpression composes cleanly. That lets this table mirror the PNG art's
philosophy (see window.py's EXPRESSION_PRESETS): a preset is a whole picture,
face and stance together, not just a face.

This mapping was built by rendering every expression and looking at the
result -- `python scripts/verify_live2d_expressions.py` regenerates those
shots, and `--presets` renders these combinations. An earlier attempt to
infer the mapping from the exp3.json parameter deltas alone produced
expressions that didn't match their names at all (2026-09-10).

An empty tuple means "no expression": the model's rest pose already reads as
neutral, so "normal" just resets.
"""

from __future__ import annotations

EXPRESSION_PRESETS: dict[str, tuple[str, ...]] = {
    # 素の立ち姿がそのまま自然な「普通」なので、リセットするだけ。
    "normal": (),
    "happy": ("exp_smile",),
    "delighted": ("exp_laugh", "pose_Upper"),
    # exp_02 は顔(>< 目 + 開口)と万歳の腕がひとつのファイルに入っている。
    "celebrating": ("exp_02",),
    # 両手を腰に当てた立ち方の方が「どや」に見えるのでpose_Waist(両手)側。
    "proud": ("exp_smile", "pose_Waist"),
    "relieved": ("exp_03",),
    "shy": ("exp_shy2",),
    "greeting": ("exp_smile", "pose_Upper2"),
    "casual": ("exp_smile", "pose_Waist2"),
    "casual_lean": ("exp_03", "pose_Waist2"),
    "confident": ("exp_smile", "pose_cross"),
    # exp_05 は半目(呆れ・うたがい)で、腕も一緒に指定している。
    "skeptical": ("exp_05",),
    "suspicious": ("exp_angry", "pose_mouth2"),
    "serious": ("exp_angry",),
    "angry": ("exp_angry3", "pose_Waist2"),
    "furious": ("exp_angry3", "pose_chop"),
    "warning_no": ("exp_angry", "pose_chop"),
    "sad": ("exp_sad",),
    "disappointed": ("exp_sad", "pose_Middle"),
    "worried": ("exp_sad3", "pose_mouth2"),
    # exp_01 は青ざめ+汗+焦り顔で、両手を口元にやる腕まで含んでいる。
    "panic": ("exp_01",),
    "shock": ("exp_sad2",),
    "scared": ("exp_angry2",),
    "dazed": ("exp_surprise2",),
    # exp_04 は伏し目 + 顎に手をやるポーズを兼ねている。
    "thinking": ("exp_04",),
    "confused": ("exp_surprise2", "pose_Middle"),
    "explaining": ("exp_smile", "pose_Middle2"),
    "eureka": ("exp_surprise", "pose_Upper3"),
    "patient_wait": ("exp_sleep",),
    "effort": ("exp_laugh2", "pose_Waist2"),
}

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

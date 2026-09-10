"""App configuration: port, VOICEVOX voice params, remembered window position.

Window position is stored as a fraction (0..1) of the screen size, keyed by
screen name, so a monitor-configuration change doesn't strand the window
off-screen (an absolute-pixel position would).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"

DEFAULT_PORT = 50022
DEFAULT_ASSET_SET = "vowel_5"


@dataclass
class VoiceParams:
    speaker: int = 1
    # 2026-09-09、抑揚を上げるだけでは不自然という調査結果(話速も一緒に上げるのが定石、
    # 「話速120% + 抑揚1.33」がよく紹介される組み合わせ)を踏まえ、speed_scaleも合わせて調整。
    speed_scale: float = 1.2
    pitch_scale: float = 0.0
    # 1.0(VOICEVOXの素の抑揚)だと平坦で棒読み気味に聞こえたため、2026-09-09に強めた。
    # 実際に2.0/1.6/1.3と聞き比べ、最終的に上のspeed_scaleとセットで1.33に落ち着いた。
    intonation_scale: float = 1.33
    volume_scale: float = 1.0


@dataclass
class WindowPosition:
    screen_name: str
    x_fraction: float
    y_fraction: float


@dataclass
class Config:
    port: int = DEFAULT_PORT
    voicevox_base_url: str = "http://127.0.0.1:50021"
    voice: VoiceParams = field(default_factory=VoiceParams)
    window_position: WindowPosition | None = None
    click_through: bool = False
    # Whether clicking the mascot makes it say something (Live2D backend only).
    click_reaction: bool = True
    asset_set: str = DEFAULT_ASSET_SET
    scale: float = 1.0


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config, falling back to defaults if the file is unusable.

    A hand-edited or truncated config must not stop the mascot from
    starting: under autostart (pythonw, no console) that would look like the
    app is simply broken, with the actual cause invisible.
    """
    if not path.exists():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        voice_data = data.get("voice", {})
        pos_data = data.get("window_position")
        return Config(
            port=data.get("port", DEFAULT_PORT),
            voicevox_base_url=data.get("voicevox_base_url", "http://127.0.0.1:50021"),
            voice=VoiceParams(**voice_data) if voice_data else VoiceParams(),
            window_position=WindowPosition(**pos_data) if pos_data else None,
            click_through=data.get("click_through", False),
            click_reaction=data.get("click_reaction", True),
            asset_set=data.get("asset_set", DEFAULT_ASSET_SET),
            scale=data.get("scale", 1.0),
        )
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        logger.exception("%s を読めなかったので既定値で起動する", path)
        return Config()


def save_config(config: Config, path: Path = DEFAULT_CONFIG_PATH) -> None:
    data = asdict(config)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

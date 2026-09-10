"""Entry point: launches the mascot window, tray icon, HTTP server, speaker."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import requests
from PySide6.QtCore import QProcess
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

# live2d-py must be imported after PySide6 -- importing it first crashes the
# process (segfault) the moment PySide6.QtWidgets is subsequently imported,
# apparently an OpenGL/DLL loading order issue on Windows (2026-09-10).
import live2d.v3 as live2d

from mascot import playback
from mascot.assets import available_sets, load_manifest
from mascot.config import DEFAULT_CONFIG_PATH, Config, load_config, save_config
from mascot.live2d_assets import (
    LIVE2D_PREFIX,
    available_live2d_models,
    live2d_icon_path,
    live2d_model_path,
)
from mascot.live2d_window import Live2DWindow
from mascot.server import ExclusiveHTTPServer, start_server
from mascot.speaker import Speaker
from mascot.speech_queue import SpeechQueue
from mascot.voicevox import VoicevoxClient
from mascot.window import MascotWindow

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "mascot.log"

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Log to a file as well as stderr.

    Autostart runs this under pythonw.exe, which has no console -- without a
    file, any startup failure leaves no trace at all and the only symptom is
    that the mascot never appears.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


def _tray_icon_path(window: MascotWindow | Live2DWindow, config: Config) -> str | None:
    if isinstance(window, Live2DWindow):
        icon = live2d_icon_path(config.asset_set[len(LIVE2D_PREFIX):])
        return str(icon) if icon else None
    body = window.manifest.parts["body"]
    return str(body.layer_path(body.default))


def build_tray_icon(
    app: QApplication,
    window: MascotWindow | Live2DWindow,
    config: Config,
    server: ExclusiveHTTPServer,
) -> QSystemTrayIcon:
    icon_path = _tray_icon_path(window, config)
    tray = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon())
    tray.setToolTip(f"ずんだもん ({config.asset_set})")

    menu = QMenu()
    show_action = QAction("表示/最前面に戻す", menu)
    show_action.triggered.connect(lambda: (window.show(), window.raise_()))
    menu.addAction(show_action)

    # PNG合成セットはそのままの名前、Live2Dモデルは"live2d:"を付けて区別する
    # (どちらもconfig.asset_setという1つの値空間を共有しているため)。
    choices = list(available_sets(include_placeholders=False)) + [
        f"{LIVE2D_PREFIX}{name}" for name in available_live2d_models()
    ]
    if len(choices) > 1:
        submenu = menu.addMenu("立ち絵を切り替え")
        for choice in choices:
            label = f"Live2D: {choice[len(LIVE2D_PREFIX):]}" if choice.startswith(LIVE2D_PREFIX) else choice
            action = QAction(label, submenu)
            action.setCheckable(True)
            action.setChecked(choice == config.asset_set)
            action.triggered.connect(
                lambda _checked=False, name=choice: _switch_asset_set(
                    app, config, tray, name, server
                )
            )
            submenu.addAction(action)

    quit_action = QAction("終了", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()
    return tray


def _switch_asset_set(
    app: QApplication,
    config: Config,
    tray: QSystemTrayIcon,
    set_name: str,
    server: ExclusiveHTTPServer,
) -> None:
    """Persist the choice and restart.

    Rebuilding the window in place would mean re-deriving its size, position
    and part selection mid-flight; relaunching is simpler and the app starts
    in well under a second.

    The server is closed *before* the successor is launched: it binds with
    SO_EXCLUSIVEADDRUSE, so if this process were still holding the port the
    newcomer would die on bind and the mascot would just disappear (WinError
    10048, seen intermittently on switch until 2026-09-10).
    """
    if set_name == config.asset_set:
        return
    config.asset_set = set_name
    save_config(config, DEFAULT_CONFIG_PATH)
    logger.info("立ち絵を %s に切り替えて再起動する", set_name)
    tray.hide()
    server.shutdown()
    server.server_close()
    QProcess.startDetached(sys.executable, ["-m", "mascot.app"])
    app.quit()


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config(DEFAULT_CONFIG_PATH)
    speech_queue = SpeechQueue()

    # Bind the port before showing anything, so a failure doesn't leave a
    # mascot on screen that silently can't be spoken to.
    try:
        server = start_server(speech_queue, config.port)
    except OSError:
        logger.exception("ポート %d を使用できないため起動を中止した", config.port)
        QMessageBox.critical(
            None,
            "ずんだもんマスコット",
            f"ポート {config.port} が使用できないため起動できないのだ。\n\n"
            "すでにマスコットが起動しているか、他のアプリがそのポートを使っているのだ。\n"
            f"詳細は {LOG_PATH} を見てほしいのだ。",
        )
        return 1

    logger.info("Listening on http://127.0.0.1:%d/speak", config.port)

    if config.asset_set.startswith(LIVE2D_PREFIX):
        model_name = config.asset_set[len(LIVE2D_PREFIX):]
        model_path = live2d_model_path(model_name)
        live2d.init()
        window = Live2DWindow(str(model_path), config, config_path=DEFAULT_CONFIG_PATH)
    else:
        manifest = load_manifest(config.asset_set)
        window = MascotWindow(manifest, config, config_path=DEFAULT_CONFIG_PATH)
    window.show()

    tray = build_tray_icon(app, window, config, server)
    voicevox = VoicevoxClient(base_url=config.voicevox_base_url, session=requests.Session())
    speaker = Speaker(window, speech_queue, voicevox, config)
    speaker.speech_failed.connect(
        lambda message: tray.showMessage("ずんだもん", message, QSystemTrayIcon.Warning, 5000)
    )

    playback.cleanup_leftovers()

    exit_code = app.exec()
    server.shutdown()
    if config.asset_set.startswith(LIVE2D_PREFIX):
        live2d.dispose()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

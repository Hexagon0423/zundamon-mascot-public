import os

# ウィジェットを実際に作るテスト(表情→口の戻り先など)を、画面もXサーバも無い
# 環境で動かすため。QApplicationを作る前に設定されている必要があるので、
# pytestが最初に読むこのファイルで指定する。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])

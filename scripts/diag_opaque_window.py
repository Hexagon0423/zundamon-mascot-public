"""Diagnostic: does a plain opaque frameless always-on-top window render at
all in this environment? Used to isolate whether WA_TranslucentBackground
specifically is the problem, or something more fundamental."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
w = QLabel("DIAG WINDOW")
w.setStyleSheet("background-color: red; color: white; font-size: 30px;")
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
w.resize(300, 200)
w.move(940, 240)
w.show()
sys.exit(app.exec())

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class TrackerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Application tracking is coming in a future phase.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

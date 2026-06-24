from PyQt6.QtWidgets import QMainWindow, QTabWidget

from app.db.repositories import ProfileRepository
from app.ui.resumes_tab import ResumesTab
from app.ui.search_tab import SearchTab
from app.ui.settings_tab import SettingsTab
from app.ui.tracker_tab import TrackerTab
from app.utils.constants import APP_TITLE, MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH

DARK_STYLESHEET = """
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-size: 14px;
}
QMainWindow, QTabWidget::pane {
    background-color: #1e1e1e;
}
QTabBar::tab {
    background: #2d2d2d;
    color: #e0e0e0;
    padding: 8px 16px;
    border: 1px solid #3a3a3a;
}
QTabBar::tab:selected {
    background: #3a3a3a;
    border-bottom: 2px solid #5a9fd4;
}
QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QLineEdit, QComboBox, QSpinBox, QListWidget {
    background-color: #2d2d2d;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 4px;
    color: #e0e0e0;
}
QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:pressed {
    background-color: #5a9fd4;
}
QLabel {
    color: #e0e0e0;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.setStyleSheet(DARK_STYLESHEET)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.search_tab = SearchTab()
        self.tracker_tab = TrackerTab()
        self.resumes_tab = ResumesTab()
        self.settings_tab = SettingsTab()

        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.tracker_tab, "Tracker")
        self.resumes_tab_index = self.tabs.addTab(self.resumes_tab, "Resumes")
        self.settings_tab_index = self.tabs.addTab(self.settings_tab, "Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._show_settings_if_incomplete()

    def _on_tab_changed(self, index: int) -> None:
        if index == self.resumes_tab_index:
            self.resumes_tab.refresh()
        elif index == self.settings_tab_index:
            self.settings_tab.refresh_resume_display()

    def _show_settings_if_incomplete(self) -> None:
        profile = ProfileRepository().get()
        if not profile.is_complete():
            self.tabs.setCurrentIndex(self.settings_tab_index)

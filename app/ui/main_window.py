from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QPushButton, QTabWidget

from app.db.repositories import ProfileRepository, SearchPreferencesRepository
from app.ui.resumes_tab import ResumesTab
from app.ui.search_tab import SearchTab
from app.ui.settings_tab import SettingsTab
from app.ui.theme import build_stylesheet
from app.ui.tracker_tab import TrackerTab
from app.utils.constants import APP_TITLE, MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self._current_theme = SearchPreferencesRepository().get().theme or "dark"
        self.setStyleSheet(build_stylesheet(self._current_theme))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.search_tab = SearchTab()
        self.tracker_tab = TrackerTab()
        self.resumes_tab = ResumesTab()
        self.settings_tab = SettingsTab()

        self.search_tab_index = self.tabs.addTab(self.search_tab, "Search")
        self.tracker_tab_index = self.tabs.addTab(self.tracker_tab, "Tracker")
        self.resumes_tab_index = self.tabs.addTab(self.resumes_tab, "Resumes")
        self.settings_tab_index = self.tabs.addTab(self.settings_tab, "Settings")

        self.theme_toggle_button = QPushButton()
        self.theme_toggle_button.setMinimumWidth(110)
        self.theme_toggle_button.setMinimumHeight(28)
        self._update_theme_button_text()
        self.theme_toggle_button.clicked.connect(self._on_toggle_theme)
        self.tabs.setCornerWidget(self.theme_toggle_button, Qt.Corner.TopRightCorner)

        self.search_tab.preferences_panel.set_theme(self._current_theme)

        self.tracker_tab.overdue_count_changed.connect(self._on_overdue_count_changed)
        self._on_overdue_count_changed(
            self.tracker_tab._compute_overdue_count(self.tracker_tab.all_applications)
        )

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._show_settings_if_incomplete()

    def _on_tab_changed(self, index: int) -> None:
        if index == self.search_tab_index:
            self.search_tab.preferences_panel.refresh_titles()
        elif index == self.tracker_tab_index:
            self.tracker_tab.refresh()
        elif index == self.resumes_tab_index:
            self.resumes_tab.refresh()
        elif index == self.settings_tab_index:
            self.settings_tab.refresh_resume_display()

    def _on_overdue_count_changed(self, count: int) -> None:
        label = f"Tracker ({count})" if count else "Tracker"
        self.tabs.setTabText(self.tracker_tab_index, label)

    def _update_theme_button_text(self) -> None:
        self.theme_toggle_button.setText("☀️ Light" if self._current_theme == "dark" else "🌙 Dark")

    def _on_toggle_theme(self) -> None:
        self._current_theme = "light" if self._current_theme == "dark" else "dark"
        self.setStyleSheet(build_stylesheet(self._current_theme))
        self._update_theme_button_text()
        self.search_tab.preferences_panel.set_theme(self._current_theme)

    def _show_settings_if_incomplete(self) -> None:
        profile = ProfileRepository().get()
        if not profile.is_complete():
            self.tabs.setCurrentIndex(self.settings_tab_index)

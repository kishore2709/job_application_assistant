from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QPushButton, QTabWidget

from app.db.repositories import ProfileRepository, SearchPreferencesRepository
from app.services.notification_service import get_reminder_count
from app.services.system_tray_manager import SystemTrayManager
from app.ui.resumes_tab import ResumesTab
from app.ui.search_tab import SearchTab
from app.ui.settings_tab import SettingsTab
from app.ui.theme import build_stylesheet
from app.ui.tracker_tab import TrackerTab
from app.utils.constants import APP_TITLE, MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH

_REMINDER_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes
_STALE_SEARCH_HOURS = 12


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

        self.search_tab_index = self.tabs.addTab(self.search_tab, "🔍 Search")
        self.tracker_tab_index = self.tabs.addTab(self.tracker_tab, "📋 Tracker")
        self.resumes_tab_index = self.tabs.addTab(self.resumes_tab, "📄 Resumes")
        self.settings_tab_index = self.tabs.addTab(self.settings_tab, "⚙️ Settings")

        self.theme_toggle_button = QPushButton()
        self.theme_toggle_button.setMinimumWidth(110)
        self.theme_toggle_button.setMinimumHeight(28)
        self._update_theme_button_text()
        self.theme_toggle_button.clicked.connect(self._on_toggle_theme)
        self.tabs.setCornerWidget(self.theme_toggle_button, Qt.Corner.TopRightCorner)

        self.search_tab.preferences_panel.set_theme(self._current_theme)

        # Tracker badge + dismiss refresh
        self.tracker_tab.overdue_count_changed.connect(self._on_overdue_count_changed)
        self._on_overdue_count_changed(
            self.tracker_tab._compute_overdue_count(self.tracker_tab.all_applications)
        )

        # Refresh tracker stats after an application is logged from Search tab
        self.search_tab.application_logged.connect(self.tracker_tab.refresh)

        # Wire API key banner "Go to Settings" button
        self.search_tab.go_to_settings.connect(
            lambda: self.tabs.setCurrentIndex(self.settings_tab_index)
        )

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Keyboard shortcuts (Ctrl → Cmd on macOS via Qt)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(
            lambda: self.tabs.setCurrentIndex(self.search_tab_index)
        )
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(
            lambda: self.tabs.setCurrentIndex(self.tracker_tab_index)
        )
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(
            lambda: self.tabs.setCurrentIndex(self.resumes_tab_index)
        )
        QShortcut(QKeySequence("Ctrl+4"), self).activated.connect(
            lambda: self.tabs.setCurrentIndex(self.settings_tab_index)
        )
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._run_search)
        self._show_settings_if_incomplete()

        # System tray
        self.tray_manager = SystemTrayManager(self)

        # Auto-refresh timer (every 30 minutes)
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(_REMINDER_INTERVAL_MS)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()

        # Startup check after event loop is running (500 ms delay)
        QTimer.singleShot(500, self._on_startup)

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if index == self.search_tab_index:
            self.search_tab.preferences_panel.refresh_titles()
            self.search_tab.refresh_banners()
        elif index == self.tracker_tab_index:
            self.tracker_tab.refresh()
        elif index == self.resumes_tab_index:
            self.resumes_tab.refresh()
        elif index == self.settings_tab_index:
            self.settings_tab.refresh_resume_display()

    # ------------------------------------------------------------------
    # Overdue badge
    # ------------------------------------------------------------------

    def _on_overdue_count_changed(self, count: int) -> None:
        label = f"📋 Tracker ({count})" if count else "📋 Tracker"
        self.tabs.setTabText(self.tracker_tab_index, label)
        if hasattr(self, "tray_manager"):
            self.tray_manager.update_followup_count(count)

    # ------------------------------------------------------------------
    # Background reminder check
    # ------------------------------------------------------------------

    def _check_reminders(self) -> None:
        count = get_reminder_count()
        self._on_overdue_count_changed(count)
        if count > 0:
            self.tray_manager.show_notification(
                "Follow-up Reminders",
                f"{count} application{'s' if count != 1 else ''} need follow-up",
            )

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    def _on_startup(self) -> None:
        # Follow-up reminders
        count = get_reminder_count()
        self._on_overdue_count_changed(count)
        if count > 0:
            self.tray_manager.show_notification(
                "Follow-up Reminders",
                f"{count} application{'s' if count != 1 else ''} need follow-up",
            )

        # Stale search hint
        last_search = SearchPreferencesRepository().get_last_search_time()
        stale = last_search is None or (
            datetime.now() - last_search > timedelta(hours=_STALE_SEARCH_HOURS)
        )
        if stale:
            self.tray_manager.show_notification(
                "Job Hunt Assistant",
                "You haven't searched for jobs recently. New jobs may be available.",
            )

    # ------------------------------------------------------------------
    # Minimize to tray
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        self.tray_manager.show_notification(
            "Job Hunt Assistant",
            "Running in background. Click the menu bar icon to restore.",
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _update_theme_button_text(self) -> None:
        self.theme_toggle_button.setText("☀️ Light" if self._current_theme == "dark" else "🌙 Dark")

    def _on_toggle_theme(self) -> None:
        self._current_theme = "light" if self._current_theme == "dark" else "dark"
        self.setStyleSheet(build_stylesheet(self._current_theme))
        self._update_theme_button_text()
        self.search_tab.preferences_panel.set_theme(self._current_theme)

    # ------------------------------------------------------------------
    # Keyboard shortcut helpers
    # ------------------------------------------------------------------

    def _focus_search(self) -> None:
        self.tabs.setCurrentIndex(self.search_tab_index)
        self.search_tab.preferences_panel.new_title_input.setFocus()

    def _run_search(self) -> None:
        self.tabs.setCurrentIndex(self.search_tab_index)
        self.search_tab._on_search_clicked()

    def _show_settings_if_incomplete(self) -> None:
        profile = ProfileRepository().get()
        if not profile.is_complete():
            self.tabs.setCurrentIndex(self.settings_tab_index)

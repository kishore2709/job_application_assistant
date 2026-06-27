from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import ProfileRepository, SearchPreferencesRepository, TargetRoleRepository
from app.models.search_preferences import SearchPreferences
from app.services.job_search_service import SOURCE_BOTH, SOURCE_JSEARCH, SOURCE_LINKEDIN
from app.utils.constants import DATE_POSTED_OPTIONS, US_STATES

LOCATION_SCOPE_ALL = "all"
LOCATION_SCOPE_STATES = "states"

_PILL_STYLE = """
QCheckBox {
    background-color: #1F3148;
    color: #E6EDF3;
    padding: 4px 8px;
    border: 1px solid #2F81F7;
    border-radius: 12px;
    spacing: 4px;
    font-family: Arial;
    font-size: 9pt;
}
QCheckBox:checked {
    background-color: #2F81F7;
    color: white;
}
QCheckBox::indicator {
    width: 12px;
    height: 12px;
}
"""


class SearchPreferencesPanel(QWidget):
    """Compact collapsible search-preferences bar — 3 rows, ~100px tall when expanded."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_role_repository = TargetRoleRepository()
        self.profile_repository = ProfileRepository()
        self.preferences_repository = SearchPreferencesRepository()

        self._title_checkboxes: dict[str, QCheckBox] = {}
        self._state_checkboxes: dict[str, QCheckBox] = {}
        self._loading = False
        self._current_theme = "dark"

        self._build_ui()
        self._load_preferences()
        self._wire_autosave()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(2)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.toggle_button = QPushButton("► Search Preferences")
        self.toggle_button.setStyleSheet("text-align: left; font-weight: bold;")
        self.toggle_button.clicked.connect(self._on_toggle_collapsed)
        outer_layout.addWidget(self.toggle_button)

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setSpacing(5)
        content_layout.setContentsMargins(6, 5, 6, 5)

        content_layout.addLayout(self._build_titles_row())
        content_layout.addLayout(self._build_location_posted_source_row())
        content_layout.addWidget(self._build_states_section())
        content_layout.addLayout(self._build_filters_row())

        self.content_widget.setVisible(False)
        outer_layout.addWidget(self.content_widget)

    def _on_toggle_collapsed(self) -> None:
        currently_visible = self.content_widget.isVisible()
        self.content_widget.setVisible(not currently_visible)
        self.toggle_button.setText(
            "► Search Preferences" if currently_visible else "▼ Search Preferences"
        )

    def _build_titles_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        lbl = QLabel("Titles:")
        lbl.setFixedWidth(44)
        row.addWidget(lbl)

        self.titles_container = QWidget()
        self.titles_layout = QHBoxLayout(self.titles_container)
        self.titles_layout.setSpacing(5)
        self.titles_layout.setContentsMargins(0, 0, 0, 0)

        self.titles_scroll = QScrollArea()
        self.titles_scroll.setWidgetResizable(True)
        self.titles_scroll.setFixedHeight(30)
        self.titles_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.titles_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.titles_scroll.setWidget(self.titles_container)
        row.addWidget(self.titles_scroll, 1)

        self.new_title_input = QLineEdit()
        self.new_title_input.setPlaceholderText("Add title…")
        self.new_title_input.setFixedWidth(130)
        self.new_title_input.setFixedHeight(26)
        self.new_title_input.returnPressed.connect(self._on_add_title)
        row.addWidget(self.new_title_input)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(26)
        add_btn.clicked.connect(self._on_add_title)
        row.addWidget(add_btn)

        self._rebuild_title_checkboxes()
        return row

    def _build_location_posted_source_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        row.addWidget(QLabel("Location:"))
        self.location_all_radio = QRadioButton("All US")
        self.location_states_radio = QRadioButton("States")
        self.location_scope_group = QButtonGroup(self)
        self.location_scope_group.addButton(self.location_all_radio)
        self.location_scope_group.addButton(self.location_states_radio)
        self.location_all_radio.setChecked(True)
        self.location_all_radio.toggled.connect(self._on_location_scope_toggled)
        row.addWidget(self.location_all_radio)
        row.addWidget(self.location_states_radio)

        def _sep() -> QLabel:
            s = QLabel("│")
            s.setStyleSheet("color: #484F58; padding: 0 4px;")
            return s

        row.addWidget(_sep())

        row.addWidget(QLabel("Posted:"))
        self.posted_combo = QComboBox()
        for value, label in DATE_POSTED_OPTIONS:
            self.posted_combo.addItem(label, value)
        self.posted_combo.setFixedHeight(26)
        row.addWidget(self.posted_combo)

        row.addWidget(_sep())

        row.addWidget(QLabel("Source:"))
        self.source_both_radio = QRadioButton("Both")
        self.source_linkedin_radio = QRadioButton("LinkedIn")
        self.source_jsearch_radio = QRadioButton("JSearch")
        self.source_group = QButtonGroup(self)
        for radio in (self.source_both_radio, self.source_linkedin_radio, self.source_jsearch_radio):
            self.source_group.addButton(radio)
            row.addWidget(radio)
        self.source_both_radio.setChecked(True)

        row.addStretch()
        return row

    def _build_states_section(self) -> QWidget:
        self.states_section = QWidget()
        states_layout = QVBoxLayout(self.states_section)
        states_layout.setContentsMargins(0, 0, 0, 0)
        states_layout.setSpacing(4)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(140)
        states_grid_widget = QWidget()
        states_grid = QGridLayout(states_grid_widget)
        states_grid.setSpacing(2)
        for index, state in enumerate(US_STATES):
            checkbox = QCheckBox(state)
            checkbox.setMinimumHeight(20)
            checkbox.stateChanged.connect(self._on_state_checkbox_changed)
            self._state_checkboxes[state] = checkbox
            states_grid.addWidget(checkbox, index // 5, index % 5)
        scroll_area.setWidget(states_grid_widget)
        states_layout.addWidget(scroll_area)

        self.selected_states_pills_container = QWidget()
        self.selected_states_pills_layout = QHBoxLayout(self.selected_states_pills_container)
        self.selected_states_pills_layout.setContentsMargins(0, 0, 0, 0)
        states_layout.addWidget(self.selected_states_pills_container)

        clear_states_btn = QPushButton("Clear all states")
        clear_states_btn.setFixedHeight(24)
        clear_states_btn.clicked.connect(self._on_clear_states)
        states_layout.addWidget(clear_states_btn)

        self.states_section.setVisible(False)
        return self.states_section

    def _build_filters_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self.remote_only_checkbox = QCheckBox("Remote")
        self.full_time_only_checkbox = QCheckBox("Full-time")
        self.easy_apply_only_checkbox = QCheckBox("Easy Apply")
        self.hide_sponsorship_checkbox = QCheckBox("Hide sponsorship")
        self.hide_sponsorship_checkbox.setToolTip(
            "H-1B transfer ≠ new sponsorship. Review flagged jobs before skipping."
        )
        self.hide_clearance_checkbox = QCheckBox("Hide clearance")
        self.hide_clearance_checkbox.setChecked(True)
        self.hide_clearance_checkbox.setToolTip(
            "Hide jobs that require security clearance (Top Secret, TS/SCI, etc.)"
        )

        for cb in (
            self.remote_only_checkbox,
            self.full_time_only_checkbox,
            self.easy_apply_only_checkbox,
            self.hide_sponsorship_checkbox,
            self.hide_clearance_checkbox,
        ):
            row.addWidget(cb)

        self.sponsorship_hidden_count_label = QLabel("")
        self.sponsorship_hidden_count_label.setStyleSheet("color: #7D8590; font-size: 11px;")
        row.addWidget(self.sponsorship_hidden_count_label)

        self.clearance_hidden_count_label = QLabel("")
        self.clearance_hidden_count_label.setStyleSheet("color: #7D8590; font-size: 11px;")
        row.addWidget(self.clearance_hidden_count_label)

        row.addStretch()
        return row

    # ------------------------------------------------------------------
    # Titles
    # ------------------------------------------------------------------

    def refresh_titles(self) -> None:
        previously_checked = set(self.get_selected_titles())
        self._rebuild_title_checkboxes()
        for title, checkbox in self._title_checkboxes.items():
            checkbox.setChecked(title in previously_checked)

    def _rebuild_title_checkboxes(self) -> None:
        while self.titles_layout.count():
            item = self.titles_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._title_checkboxes.clear()

        active_roles = self.target_role_repository.list_active()
        for role in active_roles:
            checkbox = QCheckBox(role.role_title)
            checkbox.setStyleSheet(_PILL_STYLE)
            checkbox.stateChanged.connect(self._on_changed)
            self._title_checkboxes[role.role_title] = checkbox
            self.titles_layout.addWidget(checkbox)
        self.titles_layout.addStretch()

    def _set_all_titles(self, checked: bool) -> None:
        for checkbox in self._title_checkboxes.values():
            checkbox.setChecked(checked)

    def _on_add_title(self) -> None:
        title = self.new_title_input.text().strip()
        if not title:
            return
        self.target_role_repository.add(title)
        self.new_title_input.clear()
        previously_checked = set(self.get_selected_titles())
        previously_checked.add(title)
        self._rebuild_title_checkboxes()
        for checked_title, checkbox in self._title_checkboxes.items():
            checkbox.setChecked(checked_title in previously_checked)
        self._on_changed()

    def get_selected_titles(self) -> list[str]:
        return [title for title, checkbox in self._title_checkboxes.items() if checkbox.isChecked()]

    # ------------------------------------------------------------------
    # Location
    # ------------------------------------------------------------------

    def _on_location_scope_toggled(self, _checked: bool) -> None:
        self.states_section.setVisible(self.location_states_radio.isChecked())
        self._on_changed()

    def _on_state_checkbox_changed(self) -> None:
        self._rebuild_state_pills()
        self._on_changed()

    def _rebuild_state_pills(self) -> None:
        while self.selected_states_pills_layout.count():
            item = self.selected_states_pills_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for state in self.get_selected_states():
            pill = QWidget()
            pill_layout = QHBoxLayout(pill)
            pill_layout.setContentsMargins(6, 2, 2, 2)
            pill_layout.addWidget(QLabel(state))
            remove_button = QPushButton("✕")
            remove_button.setFixedSize(18, 18)
            remove_button.clicked.connect(lambda _checked, s=state: self._remove_state(s))
            pill_layout.addWidget(remove_button)
            pill.setStyleSheet(
                "background-color: #21262D; border: 1px solid #30363D; border-radius: 10px;"
            )
            self.selected_states_pills_layout.addWidget(pill)
        self.selected_states_pills_layout.addStretch()

    def _remove_state(self, state: str) -> None:
        checkbox = self._state_checkboxes.get(state)
        if checkbox is not None:
            checkbox.setChecked(False)

    def _on_clear_states(self) -> None:
        for checkbox in self._state_checkboxes.values():
            checkbox.setChecked(False)

    def get_selected_states(self) -> list[str]:
        return [state for state, checkbox in self._state_checkboxes.items() if checkbox.isChecked()]

    def get_location_text(self) -> str:
        if self.location_states_radio.isChecked():
            selected = self.get_selected_states()
            if selected:
                return ", ".join(selected)
        return "United States"

    # ------------------------------------------------------------------
    # Date posted / filters / source getters
    # ------------------------------------------------------------------

    def get_date_posted_filter(self) -> str:
        return self.posted_combo.currentData() or "7days"

    def get_filters(self) -> dict:
        return {
            "remote_only": self.remote_only_checkbox.isChecked(),
            "full_time_only": self.full_time_only_checkbox.isChecked(),
            "easy_apply_only": self.easy_apply_only_checkbox.isChecked(),
            "date_posted_filter": self.get_date_posted_filter(),
            "hide_sponsorship_restricted": self.hide_sponsorship_checkbox.isChecked(),
            "hide_clearance_jobs": self.hide_clearance_checkbox.isChecked(),
        }

    def show_sponsorship_hidden_count(self, count: int) -> None:
        if count:
            self.sponsorship_hidden_count_label.setText(f"{count} hidden (sponsorship)")
        else:
            self.sponsorship_hidden_count_label.setText("")

    def show_clearance_hidden_count(self, count: int) -> None:
        if count:
            self.clearance_hidden_count_label.setText(f"{count} hidden (clearance)")
        else:
            self.clearance_hidden_count_label.setText("")

    def get_source(self) -> str:
        if self.source_linkedin_radio.isChecked():
            return SOURCE_LINKEDIN
        if self.source_jsearch_radio.isChecked():
            return SOURCE_JSEARCH
        return SOURCE_BOTH

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _wire_autosave(self) -> None:
        self.posted_combo.currentIndexChanged.connect(self._on_changed)
        self.remote_only_checkbox.stateChanged.connect(self._on_changed)
        self.full_time_only_checkbox.stateChanged.connect(self._on_changed)
        self.easy_apply_only_checkbox.stateChanged.connect(self._on_changed)
        self.hide_sponsorship_checkbox.stateChanged.connect(self._on_changed)
        self.hide_clearance_checkbox.stateChanged.connect(self._on_changed)
        self.source_linkedin_radio.toggled.connect(self._on_changed)
        self.source_jsearch_radio.toggled.connect(self._on_changed)
        self.source_both_radio.toggled.connect(self._on_changed)

    def _on_changed(self) -> None:
        if self._loading:
            return
        self._save_preferences()

    def _save_preferences(self) -> None:
        preferences = SearchPreferences(
            location_scope=LOCATION_SCOPE_STATES if self.location_states_radio.isChecked() else LOCATION_SCOPE_ALL,
            selected_states=self.get_selected_states(),
            selected_titles=self.get_selected_titles(),
            date_posted_filter=self.get_date_posted_filter(),
            remote_only=self.remote_only_checkbox.isChecked(),
            fulltime_only=self.full_time_only_checkbox.isChecked(),
            easy_apply_only=self.easy_apply_only_checkbox.isChecked(),
            hide_sponsorship_restricted=self.hide_sponsorship_checkbox.isChecked(),
            hide_clearance_jobs=self.hide_clearance_checkbox.isChecked(),
            source=self.get_source(),
            theme=self._current_theme,
        )
        self.preferences_repository.save(preferences)

    def get_theme(self) -> str:
        return self._current_theme

    def set_theme(self, theme: str) -> None:
        self._current_theme = theme
        if not self._loading:
            self._save_preferences()

    def _load_preferences(self) -> None:
        self._loading = True
        is_first_launch = False
        titles_were_empty = False
        try:
            preferences = self.preferences_repository.get()
            is_first_launch = not preferences.updated_at
            titles_were_empty = not preferences.selected_titles
            self._current_theme = preferences.theme
            self.hide_sponsorship_checkbox.setChecked(preferences.hide_sponsorship_restricted)
            self.hide_clearance_checkbox.setChecked(preferences.hide_clearance_jobs)

            if preferences.location_scope == LOCATION_SCOPE_STATES:
                self.location_states_radio.setChecked(True)
                self.states_section.setVisible(True)
            else:
                self.location_all_radio.setChecked(True)

            for state in preferences.selected_states:
                checkbox = self._state_checkboxes.get(state)
                if checkbox is not None:
                    checkbox.setChecked(True)
            self._rebuild_state_pills()

            if not preferences.selected_titles:
                self._set_all_titles(True)
            else:
                selected_titles = set(preferences.selected_titles)
                for title, checkbox in self._title_checkboxes.items():
                    checkbox.setChecked(title in selected_titles)

            for i in range(self.posted_combo.count()):
                if self.posted_combo.itemData(i) == preferences.date_posted_filter:
                    self.posted_combo.setCurrentIndex(i)
                    break

            self.remote_only_checkbox.setChecked(preferences.remote_only)
            self.full_time_only_checkbox.setChecked(preferences.fulltime_only)
            self.easy_apply_only_checkbox.setChecked(preferences.easy_apply_only)

            if preferences.source == SOURCE_LINKEDIN:
                self.source_linkedin_radio.setChecked(True)
            elif preferences.source == SOURCE_JSEARCH:
                self.source_jsearch_radio.setChecked(True)
            else:
                self.source_both_radio.setChecked(True)
        finally:
            self._loading = False

        if is_first_launch or titles_were_empty:
            self._save_preferences()

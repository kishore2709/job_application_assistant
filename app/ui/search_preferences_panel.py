from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
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


class SearchPreferencesPanel(QWidget):
    """Collapsible search-preferences box: job titles, location, date
    posted, filters, and source. Every change auto-saves to the
    search_preferences table — there is no Save button.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_role_repository = TargetRoleRepository()
        self.profile_repository = ProfileRepository()
        self.preferences_repository = SearchPreferencesRepository()

        self._title_checkboxes: dict[str, QCheckBox] = {}
        self._state_checkboxes: dict[str, QCheckBox] = {}
        self._loading = False

        self._build_ui()
        self._load_preferences()
        self._wire_autosave()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        self.toggle_button = QPushButton("▼ Search Preferences")
        self.toggle_button.setStyleSheet("text-align: left; font-weight: bold;")
        self.toggle_button.clicked.connect(self._on_toggle_collapsed)
        outer_layout.addWidget(self.toggle_button)

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.addWidget(self._build_titles_group())
        content_layout.addWidget(self._build_location_group())

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._build_date_posted_group())
        bottom_row.addWidget(self._build_filters_group())
        bottom_row.addWidget(self._build_source_group())
        content_layout.addLayout(bottom_row)

        outer_layout.addWidget(self.content_widget)

    def _on_toggle_collapsed(self) -> None:
        collapsed = self.content_widget.isVisible()
        self.content_widget.setVisible(not collapsed)
        self.toggle_button.setText(
            "► Search Preferences" if collapsed else "▼ Search Preferences"
        )

    def _build_titles_group(self) -> QGroupBox:
        group = QGroupBox("Job Titles")
        layout = QVBoxLayout()

        self.titles_container = QWidget()
        self.titles_layout = QVBoxLayout(self.titles_container)
        self.titles_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.titles_container)

        select_row = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(lambda: self._set_all_titles(True))
        deselect_all_button = QPushButton("Deselect All")
        deselect_all_button.clicked.connect(lambda: self._set_all_titles(False))
        select_row.addWidget(select_all_button)
        select_row.addWidget(deselect_all_button)
        layout.addLayout(select_row)

        add_row = QHBoxLayout()
        self.new_title_input = QLineEdit()
        self.new_title_input.setPlaceholderText("Add a custom job title")
        add_title_button = QPushButton("Add")
        add_title_button.clicked.connect(self._on_add_title)
        add_row.addWidget(self.new_title_input)
        add_row.addWidget(add_title_button)
        layout.addLayout(add_row)

        self._rebuild_title_checkboxes()

        group.setLayout(layout)
        return group

    def _build_location_group(self) -> QGroupBox:
        group = QGroupBox("Location")
        layout = QVBoxLayout()

        country_row = QHBoxLayout()
        country_row.addWidget(QLabel("Country:"))
        country_row.addWidget(QLabel("USA"))
        country_row.addStretch()
        layout.addLayout(country_row)

        self.location_all_radio = QRadioButton("All United States")
        self.location_states_radio = QRadioButton("Specific States")
        self.location_scope_group = QButtonGroup(self)
        self.location_scope_group.addButton(self.location_all_radio)
        self.location_scope_group.addButton(self.location_states_radio)
        self.location_all_radio.setChecked(True)
        self.location_all_radio.toggled.connect(self._on_location_scope_toggled)

        scope_row = QHBoxLayout()
        scope_row.addWidget(self.location_all_radio)
        scope_row.addWidget(self.location_states_radio)
        layout.addLayout(scope_row)

        self.states_section = QWidget()
        states_layout = QVBoxLayout(self.states_section)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(160)
        states_grid_widget = QWidget()
        states_grid = QGridLayout(states_grid_widget)
        for index, state in enumerate(US_STATES):
            checkbox = QCheckBox(state)
            checkbox.stateChanged.connect(self._on_state_checkbox_changed)
            self._state_checkboxes[state] = checkbox
            states_grid.addWidget(checkbox, index // 5, index % 5)
        scroll_area.setWidget(states_grid_widget)
        states_layout.addWidget(scroll_area)

        self.selected_states_pills_container = QWidget()
        self.selected_states_pills_layout = QHBoxLayout(self.selected_states_pills_container)
        self.selected_states_pills_layout.setContentsMargins(0, 0, 0, 0)
        states_layout.addWidget(self.selected_states_pills_container)

        clear_states_button = QPushButton("Clear all states")
        clear_states_button.clicked.connect(self._on_clear_states)
        states_layout.addWidget(clear_states_button)

        self.states_section.setVisible(False)
        layout.addWidget(self.states_section)

        group.setLayout(layout)
        return group

    def _build_date_posted_group(self) -> QGroupBox:
        group = QGroupBox("Posted")
        layout = QVBoxLayout()

        self.date_posted_group = QButtonGroup(self)
        self.date_posted_radios: dict[str, QRadioButton] = {}
        for value, label in DATE_POSTED_OPTIONS:
            radio = QRadioButton(label)
            self.date_posted_group.addButton(radio)
            self.date_posted_radios[value] = radio
            layout.addWidget(radio)

        group.setLayout(layout)
        return group

    def _build_filters_group(self) -> QGroupBox:
        group = QGroupBox("Filters")
        layout = QVBoxLayout()

        self.remote_only_checkbox = QCheckBox("Remote")
        self.full_time_only_checkbox = QCheckBox("Full-time")
        self.easy_apply_only_checkbox = QCheckBox("Easy Apply")
        for checkbox in (
            self.remote_only_checkbox,
            self.full_time_only_checkbox,
            self.easy_apply_only_checkbox,
        ):
            layout.addWidget(checkbox)

        group.setLayout(layout)
        return group

    def _build_source_group(self) -> QGroupBox:
        group = QGroupBox("Source")
        layout = QVBoxLayout()

        self.source_linkedin_radio = QRadioButton("LinkedIn")
        self.source_jsearch_radio = QRadioButton("JSearch")
        self.source_both_radio = QRadioButton("Both")
        self.source_group = QButtonGroup(self)
        for radio in (self.source_linkedin_radio, self.source_jsearch_radio, self.source_both_radio):
            self.source_group.addButton(radio)
            layout.addWidget(radio)
        self.source_both_radio.setChecked(True)

        group.setLayout(layout)
        return group

    # ------------------------------------------------------------------
    # Titles
    # ------------------------------------------------------------------

    def refresh_titles(self) -> None:
        """Call when Settings target roles may have changed."""
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
            checkbox.stateChanged.connect(self._on_changed)
            self._title_checkboxes[role.role_title] = checkbox
            self.titles_layout.addWidget(checkbox)

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
                "background-color: #3a3a3a; border-radius: 10px;"
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
        for value, radio in self.date_posted_radios.items():
            if radio.isChecked():
                return value
        return "7days"

    def get_filters(self) -> dict:
        return {
            "remote_only": self.remote_only_checkbox.isChecked(),
            "full_time_only": self.full_time_only_checkbox.isChecked(),
            "easy_apply_only": self.easy_apply_only_checkbox.isChecked(),
            "date_posted_filter": self.get_date_posted_filter(),
        }

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
        for radio in self.date_posted_radios.values():
            radio.toggled.connect(self._on_changed)
        self.remote_only_checkbox.stateChanged.connect(self._on_changed)
        self.full_time_only_checkbox.stateChanged.connect(self._on_changed)
        self.easy_apply_only_checkbox.stateChanged.connect(self._on_changed)
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
            source=self.get_source(),
        )
        self.preferences_repository.save(preferences)

    def _load_preferences(self) -> None:
        self._loading = True
        is_first_launch = False
        try:
            preferences = self.preferences_repository.get()
            is_first_launch = not preferences.updated_at

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

            if is_first_launch:
                self._set_all_titles(True)
            else:
                selected_titles = set(preferences.selected_titles)
                for title, checkbox in self._title_checkboxes.items():
                    checkbox.setChecked(title in selected_titles)

            date_radio = self.date_posted_radios.get(preferences.date_posted_filter)
            if date_radio is not None:
                date_radio.setChecked(True)

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

        if is_first_launch:
            self._save_preferences()

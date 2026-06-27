import re

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import ProfileRepository
from app.models.profile import BlacklistCompany, ProfileSettings, TargetRole
from app.services.llm_service import (
    PROVIDER_ANTHROPIC,
    PROVIDER_GOOGLE,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    list_ollama_models,
    scoring_cost_for_model,
    tailoring_cost_for_model,
    test_connection,
)
from app.services.resume_service import InvalidResumeFileError, ResumeCopyError, ResumeService
from app.utils.constants import DEFAULT_VISA_STATUS, WORK_PREFERENCE_OPTIONS

SCORING_MODEL_OPTIONS = [
    ("Claude Haiku (Anthropic) — ~$0.002/score", PROVIDER_ANTHROPIC, "claude-haiku-4-5-20251001"),
    ("GPT-4o Mini (OpenAI) — ~$0.0003/score", PROVIDER_OPENAI, "gpt-4o-mini"),
    ("Gemini Flash (Google) — free tier available", PROVIDER_GOOGLE, "gemini-1.5-flash"),
    ("Ollama (Local) — free, runs locally", PROVIDER_OLLAMA, ""),
]
TAILORING_MODEL_OPTIONS = [
    ("Claude Sonnet (Anthropic) — best quality", PROVIDER_ANTHROPIC, "claude-sonnet-4-6"),
    ("GPT-4o (OpenAI) — similar quality", PROVIDER_OPENAI, "gpt-4o"),
    ("Gemini Pro (Google) — good quality", PROVIDER_GOOGLE, "gemini-1.5-pro"),
    ("Ollama (Local) — free, runs locally", PROVIDER_OLLAMA, ""),
]


class ConnectionTestWorker(QThread):
    finished_test = pyqtSignal(str, bool, float, str)

    def __init__(self, provider: str, model: str, key_or_url: str, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.model = model
        self.key_or_url = key_or_url

    def run(self) -> None:
        success, elapsed, error = test_connection(self.provider, self.model, self.key_or_url)
        self.finished_test.emit(self.provider, success, elapsed, error)


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.repository = ProfileRepository()
        self.resume_service = ResumeService()
        self._default_resume_path = ""
        self._editing_role_item = None
        self._test_workers: list[ConnectionTestWorker] = []
        self._build_ui()
        self.load_settings()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        form_group = QGroupBox("Profile")
        form_layout = QFormLayout()

        self.full_name_input = QLineEdit()
        self.email_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.linkedin_input = QLineEdit()
        self.linkedin_input.setPlaceholderText("https://linkedin.com/in/yourprofile")
        self.github_input = QLineEdit()
        self.github_input.setPlaceholderText("https://github.com/yourusername")
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Sacramento, CA")

        self.visa_status_input = QLineEdit()
        self.visa_status_input.setText(DEFAULT_VISA_STATUS)

        for field in (
            self.full_name_input,
            self.email_input,
            self.phone_input,
            self.linkedin_input,
            self.github_input,
            self.location_input,
            self.visa_status_input,
        ):
            field.setMinimumWidth(400)
            field.setMinimumHeight(28)

        self.salary_min_input = QSpinBox()
        self.salary_min_input.setRange(0, 1_000_000)
        self.salary_min_input.setSingleStep(5000)
        self.salary_min_input.setMinimumHeight(28)

        self.salary_max_input = QSpinBox()
        self.salary_max_input.setRange(0, 1_000_000)
        self.salary_max_input.setSingleStep(5000)
        self.salary_max_input.setMinimumHeight(28)

        self.work_preference_input = QComboBox()
        self.work_preference_input.addItems(WORK_PREFERENCE_OPTIONS)
        self.work_preference_input.setMinimumHeight(28)

        self.default_resume_label = QLabel("No resume uploaded")
        self.default_resume_date_label = QLabel("")
        upload_resume_button = QPushButton("Upload / Replace Default Resume (DOCX)")
        upload_resume_button.clicked.connect(self._on_upload_resume)
        resume_row = QHBoxLayout()
        resume_row.addWidget(self.default_resume_label)
        resume_row.addWidget(self.default_resume_date_label)
        resume_row.addWidget(upload_resume_button)

        _ERR_STYLE = "color: #F85149; font-size: 10px;"
        self.email_error = QLabel("")
        self.email_error.setStyleSheet(_ERR_STYLE)
        self.linkedin_error = QLabel("")
        self.linkedin_error.setStyleSheet(_ERR_STYLE)
        self.github_error = QLabel("")
        self.github_error.setStyleSheet(_ERR_STYLE)
        self.salary_error = QLabel("")
        self.salary_error.setStyleSheet(_ERR_STYLE)

        form_layout.addRow("Full Name", self.full_name_input)
        form_layout.addRow("Email", self.email_input)
        form_layout.addRow("", self.email_error)
        form_layout.addRow("Phone", self.phone_input)
        form_layout.addRow("LinkedIn URL", self.linkedin_input)
        form_layout.addRow("", self.linkedin_error)
        form_layout.addRow("GitHub URL", self.github_input)
        form_layout.addRow("", self.github_error)
        form_layout.addRow("Location", self.location_input)
        form_layout.addRow("Visa Status", self.visa_status_input)
        form_layout.addRow("Salary Min", self.salary_min_input)
        form_layout.addRow("Salary Max", self.salary_max_input)
        form_layout.addRow("", self.salary_error)
        form_layout.addRow("Work Preference", self.work_preference_input)
        form_layout.addRow("Default Resume", resume_row)

        form_group.setLayout(form_layout)
        content_layout.addWidget(form_group)

        content_layout.addWidget(self._build_target_roles_group())
        content_layout.addWidget(self._build_blacklist_group())

        save_button = QPushButton("Save")
        save_button.setProperty("primary", True)
        save_button.setFixedSize(160, 36)
        save_button.clicked.connect(self.save_settings)
        save_button_row = QHBoxLayout()
        save_button_row.addStretch()
        save_button_row.addWidget(save_button)
        save_button_row.addStretch()
        content_layout.addLayout(save_button_row)

        content_layout.addWidget(self._build_ai_provider_group())
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)

    def _build_target_roles_group(self) -> QGroupBox:
        group = QGroupBox("Target Roles")
        layout = QVBoxLayout()

        self.target_roles_list = QListWidget()
        self.target_roles_list.setMinimumHeight(110)
        self.target_roles_list.currentItemChanged.connect(self._on_role_selected)
        layout.addWidget(self.target_roles_list)

        self.role_title_input = QLineEdit()
        self.role_title_input.setPlaceholderText("e.g. Lead Java Developer")
        self.role_description_input = QLineEdit()
        self.role_description_input.setPlaceholderText("e.g. Senior backend Java role...")

        input_row = QHBoxLayout()
        input_row.addWidget(self.role_title_input)
        input_row.addWidget(self.role_description_input)
        layout.addLayout(input_row)

        button_row = QHBoxLayout()
        self.add_role_button = QPushButton("Add Role")
        self.add_role_button.clicked.connect(self._on_add_role)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._on_remove_role)
        button_row.addWidget(self.add_role_button)
        button_row.addWidget(remove_button)
        layout.addLayout(button_row)

        group.setLayout(layout)
        return group

    def _build_blacklist_group(self) -> QGroupBox:
        group = QGroupBox("Blacklisted Companies")
        layout = QVBoxLayout()

        self.blacklist_list = QListWidget()
        self.blacklist_list.setMinimumHeight(110)
        layout.addWidget(self.blacklist_list)

        self.blacklist_company_input = QLineEdit()
        self.blacklist_company_input.setPlaceholderText("Company name")
        layout.addWidget(self.blacklist_company_input)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add Company")
        add_button.clicked.connect(self._on_add_blacklist_company)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._on_remove_blacklist_company)
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        layout.addLayout(button_row)

        group.setLayout(layout)
        return group

    def _build_ai_provider_group(self) -> QGroupBox:
        group = QGroupBox("AI Provider")
        layout = QVBoxLayout()

        layout.addWidget(
            self._build_model_choice_group(
                "Scoring Model (fast — used for every job)", SCORING_MODEL_OPTIONS, "scoring"
            )
        )
        layout.addWidget(
            self._build_model_choice_group(
                "Tailoring Model (quality — used per application)", TAILORING_MODEL_OPTIONS, "tailoring"
            )
        )
        layout.addWidget(self._build_api_keys_group())

        self.cost_estimate_label = QLabel("")
        layout.addWidget(self.cost_estimate_label)

        button_row = QHBoxLayout()
        test_all_button = QPushButton("Test All")
        test_all_button.setFixedSize(140, 36)
        test_all_button.clicked.connect(self._on_test_all)
        save_provider_button = QPushButton("Save Provider Settings")
        save_provider_button.setProperty("primary", True)
        save_provider_button.setFixedSize(220, 36)
        save_provider_button.clicked.connect(self._on_save_provider_settings)
        button_row.addStretch()
        button_row.addWidget(test_all_button)
        button_row.addWidget(save_provider_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        group.setLayout(layout)
        return group

    def _build_model_choice_group(self, title: str, options: list, purpose: str) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout()

        button_group = QButtonGroup(self)
        radios = []
        for label, provider, model in options:
            radio = QRadioButton(label)
            radio.setMinimumHeight(24)
            button_group.addButton(radio)
            radio.toggled.connect(self._update_cost_estimate)
            radios.append((radio, provider, model))
            layout.addWidget(radio)

        ollama_widget = QWidget()
        ollama_layout = QVBoxLayout(ollama_widget)
        ollama_layout.setContentsMargins(0, 0, 0, 0)
        ollama_row = QHBoxLayout()
        ollama_combo = QComboBox()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(lambda: self._refresh_ollama_models(purpose))
        ollama_row.addWidget(ollama_combo)
        ollama_row.addWidget(refresh_button)
        ollama_layout.addLayout(ollama_row)
        ollama_status_label = QLabel("")
        ollama_status_label.setWordWrap(True)
        ollama_layout.addWidget(ollama_status_label)
        ollama_widget.setVisible(False)
        layout.addWidget(ollama_widget)

        if purpose == "scoring":
            self.scoring_radios = radios
            self.scoring_button_group = button_group
            self.scoring_ollama_widget = ollama_widget
            self.scoring_ollama_combo = ollama_combo
            self.scoring_ollama_status_label = ollama_status_label
        else:
            self.tailoring_radios = radios
            self.tailoring_button_group = button_group
            self.tailoring_ollama_widget = ollama_widget
            self.tailoring_ollama_combo = ollama_combo
            self.tailoring_ollama_status_label = ollama_status_label

        for radio, provider, _model in radios:
            if provider == PROVIDER_OLLAMA:
                radio.toggled.connect(
                    lambda checked, w=ollama_widget, p=purpose: self._on_ollama_radio_toggled(checked, w, p)
                )

        group.setMinimumHeight(150)
        group.setLayout(layout)
        return group

    def _on_ollama_radio_toggled(self, checked: bool, ollama_widget: QWidget, purpose: str) -> None:
        ollama_widget.setVisible(checked)
        if checked:
            self._refresh_ollama_models(purpose)

    def _refresh_ollama_models(self, purpose: str) -> None:
        base_url = self.ollama_url_input.text().strip() or "http://localhost:11434"
        combo = self.scoring_ollama_combo if purpose == "scoring" else self.tailoring_ollama_combo
        status_label = (
            self.scoring_ollama_status_label if purpose == "scoring" else self.tailoring_ollama_status_label
        )
        models = list_ollama_models(base_url)
        combo.clear()
        if models is None:
            status_label.setText(
                "Ollama not running.\nStart with: ollama serve\nPull model:  ollama pull llama3.2"
            )
            return
        if not models:
            status_label.setText("Ollama is running but no models are pulled yet.\nRun: ollama pull llama3.2")
            return
        status_label.setText("")
        combo.addItems(models)

    def _build_api_keys_group(self) -> QGroupBox:
        group = QGroupBox("API Keys")
        layout = QFormLayout()

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key_input.setMinimumHeight(28)
        self.anthropic_test_label = QLabel("")
        self.anthropic_test_button = QPushButton("Test")
        self.anthropic_test_button.setMinimumHeight(28)
        layout.addRow(
            "Anthropic",
            self._key_row(self.anthropic_key_input, self.anthropic_test_button, self.anthropic_test_label),
        )
        self.anthropic_test_button.clicked.connect(
            lambda: self._on_test_clicked(
                PROVIDER_ANTHROPIC, self.anthropic_key_input, self.anthropic_test_label, self.anthropic_test_button
            )
        )

        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_input.setMinimumHeight(28)
        self.openai_test_label = QLabel("")
        self.openai_test_button = QPushButton("Test")
        self.openai_test_button.setMinimumHeight(28)
        layout.addRow(
            "OpenAI", self._key_row(self.openai_key_input, self.openai_test_button, self.openai_test_label)
        )
        self.openai_test_button.clicked.connect(
            lambda: self._on_test_clicked(
                PROVIDER_OPENAI, self.openai_key_input, self.openai_test_label, self.openai_test_button
            )
        )

        self.google_key_input = QLineEdit()
        self.google_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_key_input.setMinimumHeight(28)
        self.google_test_label = QLabel("")
        self.google_test_button = QPushButton("Test")
        self.google_test_button.setMinimumHeight(28)
        layout.addRow(
            "Google", self._key_row(self.google_key_input, self.google_test_button, self.google_test_label)
        )
        self.google_test_button.clicked.connect(
            lambda: self._on_test_clicked(
                PROVIDER_GOOGLE, self.google_key_input, self.google_test_label, self.google_test_button
            )
        )

        self.ollama_url_input = QLineEdit()
        self.ollama_url_input.setPlaceholderText("http://localhost:11434")
        self.ollama_url_input.setMinimumHeight(28)
        self.ollama_test_label = QLabel("")
        self.ollama_test_button = QPushButton("Test")
        self.ollama_test_button.setMinimumHeight(28)
        layout.addRow(
            "Ollama URL", self._key_row(self.ollama_url_input, self.ollama_test_button, self.ollama_test_label)
        )
        self.ollama_test_button.clicked.connect(
            lambda: self._on_test_clicked(
                PROVIDER_OLLAMA, self.ollama_url_input, self.ollama_test_label, self.ollama_test_button
            )
        )

        group.setMinimumHeight(220)
        group.setLayout(layout)
        return group

    @staticmethod
    def _key_row(line_edit: QLineEdit, test_button: QPushButton, status_label: QLabel) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(line_edit)
        row.addWidget(test_button)
        outer.addLayout(row)
        status_label.setWordWrap(True)
        outer.addWidget(status_label)
        return container

    def _test_model_for_provider(self, provider: str) -> str:
        if provider == PROVIDER_OLLAMA:
            return self.scoring_ollama_combo.currentText() or "llama3.2"
        return {
            PROVIDER_ANTHROPIC: "claude-haiku-4-5-20251001",
            PROVIDER_OPENAI: "gpt-4o-mini",
            PROVIDER_GOOGLE: "gemini-1.5-flash",
        }.get(provider, "")

    def _on_test_clicked(
        self, provider: str, line_edit: QLineEdit, status_label: QLabel, test_button: QPushButton
    ) -> None:
        key_or_url = line_edit.text().strip()
        if not key_or_url:
            status_label.setText("Enter a value first.")
            return

        model = self._test_model_for_provider(provider)
        test_button.setEnabled(False)
        status_label.setText("Testing...")

        worker = ConnectionTestWorker(provider, model, key_or_url)
        worker.finished_test.connect(
            lambda p, success, elapsed, error: self._on_test_finished(
                success, elapsed, error, status_label, test_button
            )
        )
        self._test_workers.append(worker)
        worker.start()

    def _on_test_finished(
        self, success: bool, elapsed: float, error: str, status_label: QLabel, test_button: QPushButton
    ) -> None:
        test_button.setEnabled(True)
        if success:
            status_label.setText(f"✓ Connected ({elapsed:.1f}s)")
        else:
            status_label.setText(f"✗ {error}")
        self._test_workers = [worker for worker in self._test_workers if worker.isRunning()]

    def _on_test_all(self) -> None:
        self._on_test_clicked(
            PROVIDER_ANTHROPIC, self.anthropic_key_input, self.anthropic_test_label, self.anthropic_test_button
        )
        self._on_test_clicked(
            PROVIDER_OPENAI, self.openai_key_input, self.openai_test_label, self.openai_test_button
        )
        self._on_test_clicked(
            PROVIDER_GOOGLE, self.google_key_input, self.google_test_label, self.google_test_button
        )
        self._on_test_clicked(
            PROVIDER_OLLAMA, self.ollama_url_input, self.ollama_test_label, self.ollama_test_button
        )

    def _selected_scoring(self) -> tuple[str, str]:
        for radio, provider, model in self.scoring_radios:
            if radio.isChecked():
                if provider == PROVIDER_OLLAMA:
                    return provider, self.scoring_ollama_combo.currentText()
                return provider, model
        return PROVIDER_ANTHROPIC, "claude-haiku-4-5-20251001"

    def _selected_tailoring(self) -> tuple[str, str]:
        for radio, provider, model in self.tailoring_radios:
            if radio.isChecked():
                if provider == PROVIDER_OLLAMA:
                    return provider, self.tailoring_ollama_combo.currentText()
                return provider, model
        return PROVIDER_ANTHROPIC, "claude-sonnet-4-6"

    def _update_cost_estimate(self) -> None:
        _scoring_provider, scoring_model = self._selected_scoring()
        _tailoring_provider, tailoring_model = self._selected_tailoring()
        total = 100 * scoring_cost_for_model(scoring_model) + 20 * tailoring_cost_for_model(tailoring_model)
        self.cost_estimate_label.setText(f"100 scorings + 20 tailorings ≈ ${total:.2f}/month")

    def _select_radio_for(self, radios: list, provider: str, model: str) -> None:
        for radio, candidate_provider, candidate_model in radios:
            if candidate_provider == provider and (candidate_provider == PROVIDER_OLLAMA or candidate_model == model):
                radio.setChecked(True)
                return
        radios[0][0].setChecked(True)

    def _on_save_provider_settings(self) -> None:
        profile = self.repository.get()
        scoring_provider, scoring_model = self._selected_scoring()
        tailoring_provider, tailoring_model = self._selected_tailoring()
        profile.scoring_provider = scoring_provider
        profile.scoring_model = scoring_model
        profile.tailoring_provider = tailoring_provider
        profile.tailoring_model = tailoring_model
        profile.anthropic_api_key = self.anthropic_key_input.text().strip()
        profile.openai_api_key = self.openai_key_input.text().strip()
        profile.google_api_key = self.google_key_input.text().strip()
        profile.ollama_base_url = self.ollama_url_input.text().strip() or "http://localhost:11434"

        self.repository.save_llm_settings(profile)
        QMessageBox.information(
            self, "Provider Settings Saved", "AI provider settings have been saved."
        )

    def _on_upload_resume(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Default Resume", "", "Word Documents (*.docx)"
        )
        if not file_path:
            return

        try:
            resume = self.resume_service.upload_resume(file_path)
        except InvalidResumeFileError as error:
            QMessageBox.critical(self, "Invalid File", str(error))
            return
        except ResumeCopyError as error:
            QMessageBox.critical(self, "Upload Failed", str(error))
            return

        self._default_resume_path = resume.file_path
        self.default_resume_label.setText(resume.file_name)
        self.default_resume_date_label.setText(f"(uploaded {resume.uploaded_at})")

    def _on_role_selected(self, current, _previous) -> None:
        self._editing_role_item = current
        if current is None:
            self.role_title_input.clear()
            self.role_description_input.clear()
            self.add_role_button.setText("Add Role")
            return

        data = current.data(1) or {}
        self.role_title_input.setText(data.get("role_title", ""))
        self.role_description_input.setText(data.get("role_description", ""))
        self.add_role_button.setText("Update Role")

    def _on_add_role(self) -> None:
        title = self.role_title_input.text().strip()
        if not title:
            return
        description = self.role_description_input.text().strip()
        label = f"{title} — {description}" if description else title

        if self._editing_role_item is not None:
            self._editing_role_item.setText(label)
            self._editing_role_item.setData(1, {"role_title": title, "role_description": description})
        else:
            item = QListWidgetItem(label)
            item.setData(1, {"role_title": title, "role_description": description})
            self.target_roles_list.addItem(item)

        self.role_title_input.clear()
        self.role_description_input.clear()
        self.target_roles_list.clearSelection()
        self.target_roles_list.setCurrentItem(None)
        self._editing_role_item = None
        self.add_role_button.setText("Add Role")

    def _on_remove_role(self) -> None:
        for item in self.target_roles_list.selectedItems():
            self.target_roles_list.takeItem(self.target_roles_list.row(item))
        self._editing_role_item = None
        self.role_title_input.clear()
        self.role_description_input.clear()
        self.add_role_button.setText("Add Role")

    def _on_add_blacklist_company(self) -> None:
        name = self.blacklist_company_input.text().strip()
        if not name:
            return
        self.blacklist_list.addItem(QListWidgetItem(name))
        self.blacklist_company_input.clear()

    def _on_remove_blacklist_company(self) -> None:
        for item in self.blacklist_list.selectedItems():
            self.blacklist_list.takeItem(self.blacklist_list.row(item))

    def load_settings(self) -> None:
        profile = self.repository.get()

        self.full_name_input.setText(profile.full_name)
        self.email_input.setText(profile.email)
        self.phone_input.setText(profile.phone)
        self.linkedin_input.setText(profile.linkedin_url)
        self.github_input.setText(profile.github_url)
        self.location_input.setText(profile.location)
        self.visa_status_input.setText(profile.visa_status or DEFAULT_VISA_STATUS)
        self.salary_min_input.setValue(profile.salary_min or 0)
        self.salary_max_input.setValue(profile.salary_max or 0)

        index = self.work_preference_input.findText(profile.work_preference)
        self.work_preference_input.setCurrentIndex(index if index >= 0 else 0)

        self.refresh_resume_display()

        self.target_roles_list.clear()
        for role in profile.target_roles:
            text = f"{role.role_title} — {role.role_description}" if role.role_description else role.role_title
            item = QListWidgetItem(text)
            item.setData(
                1, {"role_title": role.role_title, "role_description": role.role_description}
            )
            self.target_roles_list.addItem(item)

        self.blacklist_list.clear()
        for company in profile.blacklist_companies:
            self.blacklist_list.addItem(QListWidgetItem(company.company_name))

        self.anthropic_key_input.setText(profile.anthropic_api_key)
        self.openai_key_input.setText(profile.openai_api_key)
        self.google_key_input.setText(profile.google_api_key)
        self.ollama_url_input.setText(profile.ollama_base_url)

        if profile.scoring_provider == PROVIDER_OLLAMA and profile.scoring_model:
            self.scoring_ollama_combo.addItem(profile.scoring_model)
        self._select_radio_for(self.scoring_radios, profile.scoring_provider, profile.scoring_model)

        if profile.tailoring_provider == PROVIDER_OLLAMA and profile.tailoring_model:
            self.tailoring_ollama_combo.addItem(profile.tailoring_model)
        self._select_radio_for(self.tailoring_radios, profile.tailoring_provider, profile.tailoring_model)

        self._update_cost_estimate()

    def save_settings(self) -> None:
        # --- Validation ---
        has_error = False

        email = self.email_input.text().strip()
        if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            self.email_error.setText("Enter a valid email address (e.g. name@example.com)")
            has_error = True
        else:
            self.email_error.setText("")

        linkedin = self.linkedin_input.text().strip()
        if linkedin and "linkedin.com" not in linkedin:
            self.linkedin_error.setText("Must be a linkedin.com URL")
            has_error = True
        else:
            self.linkedin_error.setText("")

        github = self.github_input.text().strip()
        if github and "github.com" not in github:
            self.github_error.setText("Must be a github.com URL")
            has_error = True
        else:
            self.github_error.setText("")

        sal_min = self.salary_min_input.value()
        sal_max = self.salary_max_input.value()
        if sal_min > 0 and sal_max > 0 and sal_min > sal_max:
            self.salary_error.setText("Min salary must be ≤ max salary")
            has_error = True
        else:
            self.salary_error.setText("")

        if has_error:
            return

        # --- Save ---
        profile = ProfileSettings(
            full_name=self.full_name_input.text().strip(),
            email=email,
            phone=self.phone_input.text().strip(),
            linkedin_url=linkedin,
            github_url=github,
            location=self.location_input.text().strip(),
            visa_status=self.visa_status_input.text().strip() or DEFAULT_VISA_STATUS,
            salary_min=sal_min or None,
            salary_max=sal_max or None,
            work_preference=self.work_preference_input.currentText(),
            default_resume_path=self._default_resume_path,
        )

        for index in range(self.target_roles_list.count()):
            data = self.target_roles_list.item(index).data(1)
            profile.target_roles.append(
                TargetRole(role_title=data["role_title"], role_description=data["role_description"])
            )

        for index in range(self.blacklist_list.count()):
            profile.blacklist_companies.append(
                BlacklistCompany(company_name=self.blacklist_list.item(index).text())
            )

        self.repository.save(profile)
        QMessageBox.information(self, "Settings Saved", "Your settings have been saved successfully.")

    def refresh_resume_display(self) -> None:
        default_resume = self.resume_service.get_default_resume()
        if default_resume:
            self._default_resume_path = default_resume.file_path
            self.default_resume_label.setText(default_resume.file_name)
            self.default_resume_date_label.setText(f"(uploaded {default_resume.uploaded_at})")
        else:
            self._default_resume_path = ""
            self.default_resume_label.setText("No resume uploaded")
            self.default_resume_date_label.setText("")

    def is_profile_complete(self) -> bool:
        return bool(self.full_name_input.text().strip() and self.email_input.text().strip())

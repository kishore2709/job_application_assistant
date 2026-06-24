from PyQt6.QtWidgets import (
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import ProfileRepository
from app.models.profile import BlacklistCompany, ProfileSettings, TargetRole
from app.services.resume_service import InvalidResumeFileError, ResumeCopyError, ResumeService
from app.utils.constants import DEFAULT_VISA_STATUS, WORK_PREFERENCE_OPTIONS


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.repository = ProfileRepository()
        self.resume_service = ResumeService()
        self._default_resume_path = ""
        self._build_ui()
        self.load_settings()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        form_group = QGroupBox("Profile")
        form_layout = QFormLayout()

        self.full_name_input = QLineEdit()
        self.email_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.linkedin_input = QLineEdit()
        self.github_input = QLineEdit()
        self.location_input = QLineEdit()

        self.visa_status_input = QLineEdit()
        self.visa_status_input.setText(DEFAULT_VISA_STATUS)

        self.salary_min_input = QSpinBox()
        self.salary_min_input.setRange(0, 1_000_000)
        self.salary_min_input.setSingleStep(5000)

        self.salary_max_input = QSpinBox()
        self.salary_max_input.setRange(0, 1_000_000)
        self.salary_max_input.setSingleStep(5000)

        self.work_preference_input = QComboBox()
        self.work_preference_input.addItems(WORK_PREFERENCE_OPTIONS)

        self.default_resume_label = QLabel("No resume uploaded")
        self.default_resume_date_label = QLabel("")
        upload_resume_button = QPushButton("Upload / Replace Default Resume (DOCX)")
        upload_resume_button.clicked.connect(self._on_upload_resume)
        resume_row = QHBoxLayout()
        resume_row.addWidget(self.default_resume_label)
        resume_row.addWidget(self.default_resume_date_label)
        resume_row.addWidget(upload_resume_button)

        form_layout.addRow("Full Name", self.full_name_input)
        form_layout.addRow("Email", self.email_input)
        form_layout.addRow("Phone", self.phone_input)
        form_layout.addRow("LinkedIn URL", self.linkedin_input)
        form_layout.addRow("GitHub URL", self.github_input)
        form_layout.addRow("Location", self.location_input)
        form_layout.addRow("Visa Status", self.visa_status_input)
        form_layout.addRow("Salary Min", self.salary_min_input)
        form_layout.addRow("Salary Max", self.salary_max_input)
        form_layout.addRow("Work Preference", self.work_preference_input)
        form_layout.addRow("Default Resume", resume_row)

        form_group.setLayout(form_layout)
        outer_layout.addWidget(form_group)

        outer_layout.addWidget(self._build_target_roles_group())
        outer_layout.addWidget(self._build_blacklist_group())

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        outer_layout.addWidget(save_button)
        outer_layout.addStretch()

    def _build_target_roles_group(self) -> QGroupBox:
        group = QGroupBox("Target Roles")
        layout = QVBoxLayout()

        self.target_roles_list = QListWidget()
        layout.addWidget(self.target_roles_list)

        self.role_title_input = QLineEdit()
        self.role_title_input.setPlaceholderText("Role title")
        self.role_description_input = QLineEdit()
        self.role_description_input.setPlaceholderText("Role description")

        input_row = QHBoxLayout()
        input_row.addWidget(self.role_title_input)
        input_row.addWidget(self.role_description_input)
        layout.addLayout(input_row)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add Role")
        add_button.clicked.connect(self._on_add_role)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._on_remove_role)
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        layout.addLayout(button_row)

        group.setLayout(layout)
        return group

    def _build_blacklist_group(self) -> QGroupBox:
        group = QGroupBox("Blacklisted Companies")
        layout = QVBoxLayout()

        self.blacklist_list = QListWidget()
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

    def _on_add_role(self) -> None:
        title = self.role_title_input.text().strip()
        if not title:
            return
        description = self.role_description_input.text().strip()
        item = QListWidgetItem(f"{title} — {description}" if description else title)
        item.setData(1, {"role_title": title, "role_description": description})
        self.target_roles_list.addItem(item)
        self.role_title_input.clear()
        self.role_description_input.clear()

    def _on_remove_role(self) -> None:
        for item in self.target_roles_list.selectedItems():
            self.target_roles_list.takeItem(self.target_roles_list.row(item))

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

    def save_settings(self) -> None:
        profile = ProfileSettings(
            full_name=self.full_name_input.text().strip(),
            email=self.email_input.text().strip(),
            phone=self.phone_input.text().strip(),
            linkedin_url=self.linkedin_input.text().strip(),
            github_url=self.github_input.text().strip(),
            location=self.location_input.text().strip(),
            visa_status=self.visa_status_input.text().strip() or DEFAULT_VISA_STATUS,
            salary_min=self.salary_min_input.value() or None,
            salary_max=self.salary_max_input.value() or None,
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

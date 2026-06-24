from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.db.repositories import ApplicationRepository, ResumeRepository
from app.models.application import Application
from app.utils.constants import APPLICATION_SOURCE_OPTIONS, APPLICATION_STATUS_OPTIONS


class ApplicationDialog(QDialog):
    """'Add Application' form — a modal dialog for manually creating a new
    tracker entry not tied to a scraped job.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.application_repository = ApplicationRepository()
        self.resume_repository = ResumeRepository()
        self.created_application_id: int | None = None

        self.setWindowTitle("Add Application")
        self.setMinimumWidth(450)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.company_input = QLineEdit()
        self.job_title_input = QLineEdit()
        self.job_url_input = QLineEdit()

        self.source_combo = QComboBox()
        self.source_combo.addItems(APPLICATION_SOURCE_OPTIONS)

        self.date_applied_input = QDateEdit()
        self.date_applied_input.setCalendarPopup(True)
        self.date_applied_input.setDate(QDate.currentDate())

        self.status_combo = QComboBox()
        self.status_combo.addItems(APPLICATION_STATUS_OPTIONS)

        self.resume_combo = QComboBox()
        self.resume_combo.addItem("None", None)
        for resume in self.resume_repository.list_all():
            self.resume_combo.addItem(resume.file_name, resume.id)

        self.salary_input = QLineEdit()
        self.recruiter_name_input = QLineEdit()
        self.recruiter_contact_input = QLineEdit()
        self.recruiter_contact_input.setPlaceholderText("email or phone")

        self.notes_input = QTextEdit()
        self.notes_input.setMinimumHeight(80)

        follow_up_row = QHBoxLayout()
        self.follow_up_enabled_checkbox = QCheckBox("Set follow-up date")
        self.follow_up_date_input = QDateEdit()
        self.follow_up_date_input.setCalendarPopup(True)
        self.follow_up_date_input.setDate(QDate.currentDate())
        self.follow_up_date_input.setVisible(False)
        self.follow_up_enabled_checkbox.toggled.connect(self.follow_up_date_input.setVisible)
        follow_up_row.addWidget(self.follow_up_enabled_checkbox)
        follow_up_row.addWidget(self.follow_up_date_input)

        form.addRow("Company name *", self.company_input)
        form.addRow("Job title *", self.job_title_input)
        form.addRow("Job URL", self.job_url_input)
        form.addRow("Source", self.source_combo)
        form.addRow("Date applied", self.date_applied_input)
        form.addRow("Status", self.status_combo)
        form.addRow("Resume used", self.resume_combo)
        form.addRow("Salary offered", self.salary_input)
        form.addRow("Recruiter name", self.recruiter_name_input)
        form.addRow("Recruiter contact", self.recruiter_contact_input)
        form.addRow("Notes", self.notes_input)
        form.addRow("Follow-up date", follow_up_row)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.setProperty("primary", True)
        save_button.clicked.connect(self._on_save_clicked)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

    def _on_save_clicked(self) -> None:
        company = self.company_input.text().strip()
        job_title = self.job_title_input.text().strip()
        if not company or not job_title:
            QMessageBox.warning(self, "Missing Fields", "Company name and job title are required.")
            return

        resume_id = self.resume_combo.currentData()
        resume_path = ""
        if resume_id:
            resume = self.resume_repository.get_by_id(resume_id)
            resume_path = resume.file_path if resume else ""

        application = Application(
            company_name=company,
            job_title=job_title,
            job_url=self.job_url_input.text().strip(),
            source=self.source_combo.currentText(),
            date_applied=self.date_applied_input.date().toString("yyyy-MM-dd"),
            status=self.status_combo.currentText(),
            resume_id=resume_id,
            resume_path=resume_path,
            salary_offered=self.salary_input.text().strip(),
            recruiter_name=self.recruiter_name_input.text().strip(),
            recruiter_contact=self.recruiter_contact_input.text().strip(),
            notes=self.notes_input.toPlainText().strip(),
            follow_up_date=(
                self.follow_up_date_input.date().toString("yyyy-MM-dd")
                if self.follow_up_enabled_checkbox.isChecked()
                else ""
            ),
        )
        self.created_application_id = self.application_repository.create(application)
        self.accept()

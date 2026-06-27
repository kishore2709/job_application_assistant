from datetime import date

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import ApplicationRepository, ResumeRepository
from app.ui.application_dialog import ApplicationDialog
from app.utils.constants import (
    APPLICATION_SOURCE_OPTIONS,
    APPLICATION_STATUS_COLORS,
    APPLICATION_STATUS_OPTIONS,
)
from app.utils.file_utils import EXPORTS_DIR, ensure_app_directories

TRACKER_COLUMNS = [
    "Company", "Job Title", "Status", "Date Applied",
    "Resume Used", "Recruiter", "Follow-up", "Notes",
]

INTERVIEW_STATUSES = {"Phone Screen", "Technical", "Final Round"}
RESPONSE_STATUSES = {"Phone Screen", "Technical", "Final Round", "Offer", "Rejected"}
TERMINAL_STATUSES = {"Offer", "Rejected", "Ghosted"}

EXPORT_COLUMNS = [
    "Company", "Job Title", "Job URL", "Source", "Date Applied", "Status",
    "Resume Used", "Salary Offered", "Recruiter Name", "Recruiter Contact",
    "Notes", "Follow-up Date", "Created At",
]


class TrackerTab(QWidget):
    overdue_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.application_repository = ApplicationRepository()
        self.resume_repository = ResumeRepository()
        self.all_applications: list = []
        self.current_applications: list = []
        self.selected_application = None

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.addWidget(self._build_top_row())
        outer_layout.addWidget(self._build_stats_bar())
        outer_layout.addWidget(self._build_filter_row())

        splitter = QSplitter()
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        outer_layout.addWidget(splitter, 1)

    def _build_top_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        add_button = QPushButton("Add Application")
        add_button.setProperty("primary", True)
        add_button.clicked.connect(self._on_add_application_clicked)
        layout.addWidget(add_button)
        layout.addStretch()

        export_csv_button = QPushButton("Export CSV")
        export_csv_button.clicked.connect(self._on_export_csv_clicked)
        export_excel_button = QPushButton("Export Excel")
        export_excel_button.clicked.connect(self._on_export_excel_clicked)
        layout.addWidget(export_csv_button)
        layout.addWidget(export_excel_button)
        return widget

    def _build_stats_bar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.stat_value_labels = {}
        stat_specs = [
            ("total_saved", "Total Saved", "#757575"),
            ("total_applied", "Total Applied", "#1e88e5"),
            ("response_rate", "Response Rate", "#00897b"),
            ("interviews", "Interviews", "#f9a825"),
            ("offers", "Offers", "#2e7d32"),
            ("rejections", "Rejections", "#c62828"),
        ]
        for key, title, color in stat_specs:
            container = QWidget()
            container.setMaximumHeight(80)
            container_layout = QVBoxLayout(container)
            value_label = QLabel("0")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setStyleSheet(
                f"background-color: {color}; color: white; font-size: 28px; "
                "font-weight: bold; padding: 6px; border-radius: 8px;"
            )
            title_label = QLabel(title)
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(value_label)
            container_layout.addWidget(title_label)
            self.stat_value_labels[key] = value_label
            layout.addWidget(container)

        return widget

    def _build_filter_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem("All")
        self.status_filter_combo.addItems(APPLICATION_STATUS_OPTIONS)
        self.status_filter_combo.currentTextChanged.connect(self._apply_filters)

        self.date_from_input = QDateEdit()
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDate(QDate.currentDate().addDays(-30))
        self.date_from_input.dateChanged.connect(self._apply_filters)

        self.date_to_input = QDateEdit()
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDate(QDate.currentDate())
        self.date_to_input.dateChanged.connect(self._apply_filters)

        self.company_search_input = QLineEdit()
        self.company_search_input.setPlaceholderText("Search company...")
        self.company_search_input.textChanged.connect(self._apply_filters)

        clear_button = QPushButton("Clear Filters")
        clear_button.clicked.connect(self._on_clear_filters)

        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.status_filter_combo)
        layout.addWidget(QLabel("From:"))
        layout.addWidget(self.date_from_input)
        layout.addWidget(QLabel("To:"))
        layout.addWidget(self.date_to_input)
        layout.addWidget(self.company_search_input, 1)
        layout.addWidget(clear_button)
        return widget

    def _build_table(self) -> QStackedWidget:
        self.table = QTableWidget(0, len(TRACKER_COLUMNS))
        self.table.setHorizontalHeaderLabels(TRACKER_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(lambda *_: self._on_row_selected())

        self.empty_state_label = QLabel()
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setStyleSheet("color: #7D8590; font-size: 13px;")
        self.empty_state_label.setWordWrap(True)

        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)         # index 0
        self.table_stack.addWidget(self.empty_state_label)  # index 1
        return self.table_stack

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        outer_layout = QVBoxLayout(panel)

        self.detail_placeholder_label = QLabel(
            "Select an application, or click Add Application to create one."
        )
        self.detail_placeholder_label.setWordWrap(True)
        self.detail_placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(self.detail_placeholder_label)

        self.detail_content_widget = QWidget()
        layout = QVBoxLayout(self.detail_content_widget)
        form = QFormLayout()

        self.detail_company_input = QLineEdit()
        self.detail_job_title_input = QLineEdit()
        self.detail_job_url_input = QLineEdit()

        self.detail_source_combo = QComboBox()
        self.detail_source_combo.addItems(APPLICATION_SOURCE_OPTIONS)

        self.detail_date_applied_input = QDateEdit()
        self.detail_date_applied_input.setCalendarPopup(True)

        self.detail_status_combo = QComboBox()
        self.detail_status_combo.addItems(APPLICATION_STATUS_OPTIONS)

        self.detail_resume_combo = QComboBox()

        self.detail_salary_input = QLineEdit()
        self.detail_recruiter_name_input = QLineEdit()
        self.detail_recruiter_contact_input = QLineEdit()
        self.detail_notes_input = QTextEdit()
        self.detail_notes_input.setMinimumHeight(80)

        follow_up_row = QHBoxLayout()
        self.detail_follow_up_enabled_checkbox = QCheckBox("Set follow-up date")
        self.detail_follow_up_date_input = QDateEdit()
        self.detail_follow_up_date_input.setCalendarPopup(True)
        self.detail_follow_up_date_input.setVisible(False)
        self.detail_follow_up_enabled_checkbox.toggled.connect(
            self.detail_follow_up_date_input.setVisible
        )
        follow_up_row.addWidget(self.detail_follow_up_enabled_checkbox)
        follow_up_row.addWidget(self.detail_follow_up_date_input)

        form.addRow("Company", self.detail_company_input)
        form.addRow("Job title", self.detail_job_title_input)
        form.addRow("Job URL", self.detail_job_url_input)
        form.addRow("Source", self.detail_source_combo)
        form.addRow("Date applied", self.detail_date_applied_input)
        form.addRow("Status", self.detail_status_combo)
        form.addRow("Resume used", self.detail_resume_combo)
        form.addRow("Salary offered", self.detail_salary_input)
        form.addRow("Recruiter name", self.detail_recruiter_name_input)
        form.addRow("Recruiter contact", self.detail_recruiter_contact_input)
        form.addRow("Notes", self.detail_notes_input)
        form.addRow("Follow-up date", follow_up_row)

        layout.addLayout(form)

        save_changes_button = QPushButton("Save Changes")
        save_changes_button.setProperty("primary", True)
        save_changes_button.clicked.connect(self._on_save_changes_clicked)
        layout.addWidget(save_changes_button)

        self.dismiss_reminder_button = QPushButton("Dismiss Reminder")
        self.dismiss_reminder_button.setStyleSheet("color: #f9a825;")
        self.dismiss_reminder_button.clicked.connect(self._on_dismiss_reminder_clicked)
        self.dismiss_reminder_button.setVisible(False)
        layout.addWidget(self.dismiss_reminder_button)

        self.remove_application_button = QPushButton("Remove Application")
        self.remove_application_button.setStyleSheet("color: #F85149;")
        self.remove_application_button.clicked.connect(self._on_remove_application_clicked)
        self.remove_application_button.setVisible(False)
        layout.addWidget(self.remove_application_button)

        layout.addStretch()

        outer_layout.addWidget(self.detail_content_widget)
        self.detail_content_widget.setVisible(False)
        return panel

    # ------------------------------------------------------------------
    # Data loading / filtering
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self.all_applications = self.application_repository.list_all()
        self._apply_filters()
        self._update_stats(self.all_applications)
        self.overdue_count_changed.emit(self._compute_overdue_count(self.all_applications))

    def _apply_filters(self) -> None:
        status = self.status_filter_combo.currentText()
        company_query = self.company_search_input.text().strip().lower()
        date_from = self.date_from_input.date().toPyDate()
        date_to = self.date_to_input.date().toPyDate()

        filtered = []
        for application in self.all_applications:
            if status != "All" and application.status != status:
                continue
            if company_query and company_query not in application.company_name.lower():
                continue
            if application.date_applied:
                try:
                    applied_date = date.fromisoformat(application.date_applied)
                    if not (date_from <= applied_date <= date_to):
                        continue
                except ValueError:
                    pass
            filtered.append(application)

        self.current_applications = filtered
        self._populate_table(filtered)

    def _on_clear_filters(self) -> None:
        self.status_filter_combo.setCurrentText("All")
        self.company_search_input.clear()
        self.date_from_input.setDate(QDate.currentDate().addDays(-30))
        self.date_to_input.setDate(QDate.currentDate())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats(self, applications: list) -> None:
        total_saved = len(applications)
        total_applied = sum(1 for a in applications if a.status != "Saved")
        interviews = sum(1 for a in applications if a.status in INTERVIEW_STATUSES)
        offers = sum(1 for a in applications if a.status == "Offer")
        rejections = sum(1 for a in applications if a.status == "Rejected")
        responded = sum(1 for a in applications if a.status in RESPONSE_STATUSES)
        response_rate = (responded / total_applied * 100) if total_applied else 0

        self.stat_value_labels["total_saved"].setText(str(total_saved))
        self.stat_value_labels["total_applied"].setText(str(total_applied))
        self.stat_value_labels["response_rate"].setText(f"{response_rate:.0f}%")
        self.stat_value_labels["interviews"].setText(str(interviews))
        self.stat_value_labels["offers"].setText(str(offers))
        self.stat_value_labels["rejections"].setText(str(rejections))

    @staticmethod
    def _is_overdue(application) -> bool:
        if not application.follow_up_date:
            return False
        if application.status in TERMINAL_STATUSES:
            return False
        if getattr(application, "is_dismissed", False):
            return False
        try:
            follow_up = date.fromisoformat(application.follow_up_date)
        except ValueError:
            return False
        return follow_up <= date.today()

    def _compute_overdue_count(self, applications: list) -> int:
        return sum(1 for application in applications if self._is_overdue(application))

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_table(self, applications: list) -> None:
        self.table.setRowCount(0)
        resumes = {resume.id: resume.file_name for resume in self.resume_repository.list_all()}

        for application in applications:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                application.company_name,
                application.job_title,
                application.status,
                application.date_applied,
                resumes.get(application.resume_id, ""),
                application.recruiter_name,
                application.follow_up_date,
                application.notes,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value or ""))
            self._colorize_row(row, application)

        if not applications:
            if not self.all_applications:
                msg = "No applications yet — search for jobs and save them to start tracking."
            else:
                msg = "No results match your current filters."
            self.empty_state_label.setText(msg)
            self.table_stack.setCurrentIndex(1)
        else:
            self.table_stack.setCurrentIndex(0)

    def _colorize_row(self, row: int, application) -> None:
        if self._is_overdue(application):
            background, text_color = "#ffb300", "#1e1e1e"
            tooltip = f"Follow-up overdue since {application.follow_up_date}"
        else:
            background = APPLICATION_STATUS_COLORS.get(application.status, "#757575")
            text_color = "#ffffff"
            tooltip = ""
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item is not None:
                item.setBackground(QColor(background))
                item.setForeground(QColor(text_color))
                if tooltip:
                    item.setToolTip(tooltip)

    # ------------------------------------------------------------------
    # Selection / detail panel
    # ------------------------------------------------------------------

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.current_applications):
            self.selected_application = None
            self.detail_content_widget.setVisible(False)
            self.detail_placeholder_label.setVisible(True)
            return
        self.selected_application = self.current_applications[row]
        self._show_application_detail(self.selected_application)

    def _show_application_detail(self, application) -> None:
        self.detail_placeholder_label.setVisible(False)
        self.detail_content_widget.setVisible(True)
        self.detail_company_input.setText(application.company_name)
        self.detail_job_title_input.setText(application.job_title)
        self.detail_job_url_input.setText(application.job_url)

        index = self.detail_source_combo.findText(application.source)
        self.detail_source_combo.setCurrentIndex(index if index >= 0 else 0)

        if application.date_applied:
            self.detail_date_applied_input.setDate(QDate.fromString(application.date_applied, "yyyy-MM-dd"))
        else:
            self.detail_date_applied_input.setDate(QDate.currentDate())

        status_index = self.detail_status_combo.findText(application.status)
        self.detail_status_combo.setCurrentIndex(status_index if status_index >= 0 else 0)

        self.detail_resume_combo.clear()
        self.detail_resume_combo.addItem("None", None)
        selected_resume_index = 0
        for resume in self.resume_repository.list_all():
            self.detail_resume_combo.addItem(resume.file_name, resume.id)
            if resume.id == application.resume_id:
                selected_resume_index = self.detail_resume_combo.count() - 1
        self.detail_resume_combo.setCurrentIndex(selected_resume_index)

        self.detail_salary_input.setText(application.salary_offered)
        self.detail_recruiter_name_input.setText(application.recruiter_name)
        self.detail_recruiter_contact_input.setText(application.recruiter_contact)
        self.detail_notes_input.setPlainText(application.notes)

        if application.follow_up_date:
            self.detail_follow_up_enabled_checkbox.setChecked(True)
            self.detail_follow_up_date_input.setDate(
                QDate.fromString(application.follow_up_date, "yyyy-MM-dd")
            )
        else:
            self.detail_follow_up_enabled_checkbox.setChecked(False)
            self.detail_follow_up_date_input.setDate(QDate.currentDate())

        self.dismiss_reminder_button.setVisible(self._is_overdue(application))
        self.remove_application_button.setVisible(True)

    def _on_save_changes_clicked(self) -> None:
        if not self.selected_application:
            return

        application = self.selected_application
        application.company_name = self.detail_company_input.text().strip()
        application.job_title = self.detail_job_title_input.text().strip()
        application.job_url = self.detail_job_url_input.text().strip()
        application.source = self.detail_source_combo.currentText()
        application.date_applied = self.detail_date_applied_input.date().toString("yyyy-MM-dd")
        application.status = self.detail_status_combo.currentText()
        application.resume_id = self.detail_resume_combo.currentData()
        application.salary_offered = self.detail_salary_input.text().strip()
        application.recruiter_name = self.detail_recruiter_name_input.text().strip()
        application.recruiter_contact = self.detail_recruiter_contact_input.text().strip()
        application.notes = self.detail_notes_input.toPlainText().strip()
        application.follow_up_date = (
            self.detail_follow_up_date_input.date().toString("yyyy-MM-dd")
            if self.detail_follow_up_enabled_checkbox.isChecked()
            else ""
        )

        self.application_repository.update(application)
        self.refresh()
        self._select_application_by_id(application.id)
        QMessageBox.information(self, "Saved", "Application updated.")

    def _select_application_by_id(self, application_id: int) -> None:
        for row, application in enumerate(self.current_applications):
            if application.id == application_id:
                self.table.setCurrentCell(row, 0)
                return

    def _on_dismiss_reminder_clicked(self) -> None:
        if not self.selected_application or not self.selected_application.id:
            return
        self.application_repository.dismiss_reminder(self.selected_application.id)
        self.refresh()

    def _on_remove_application_clicked(self) -> None:
        if not self.selected_application or not self.selected_application.id:
            return
        company = self.selected_application.company_name
        reply = QMessageBox.question(
            self,
            "Remove Application",
            f"Remove {company} from tracker? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.application_repository.delete(self.selected_application.id)
            self.selected_application = None
            self.detail_content_widget.setVisible(False)
            self.detail_placeholder_label.setVisible(True)
            self.remove_application_button.setVisible(False)
            self.refresh()

    # ------------------------------------------------------------------
    # Add application
    # ------------------------------------------------------------------

    def _on_add_application_clicked(self) -> None:
        dialog = ApplicationDialog(parent=self)
        if dialog.exec():
            self.refresh()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _applications_to_dataframe(self):
        import pandas as pd

        resumes = {resume.id: resume.file_name for resume in self.resume_repository.list_all()}
        applications = self.application_repository.list_all()
        rows = [
            {
                "Company": application.company_name,
                "Job Title": application.job_title,
                "Job URL": application.job_url,
                "Source": application.source,
                "Date Applied": application.date_applied,
                "Status": application.status,
                "Resume Used": resumes.get(application.resume_id, ""),
                "Salary Offered": application.salary_offered,
                "Recruiter Name": application.recruiter_name,
                "Recruiter Contact": application.recruiter_contact,
                "Notes": application.notes,
                "Follow-up Date": application.follow_up_date,
                "Created At": application.created_at,
            }
            for application in applications
        ]
        return pd.DataFrame(rows, columns=EXPORT_COLUMNS)

    def _on_export_csv_clicked(self) -> None:
        ensure_app_directories()
        default_path = str(EXPORTS_DIR / f"JobApplications_{date.today().isoformat()}.csv")
        target, _ = QFileDialog.getSaveFileName(self, "Export CSV", default_path, "CSV Files (*.csv)")
        if not target:
            return
        self._applications_to_dataframe().to_csv(target, index=False)
        QMessageBox.information(self, "Exported", f"Exported to {target}")

    def _on_export_excel_clicked(self) -> None:
        ensure_app_directories()
        default_path = str(EXPORTS_DIR / f"JobApplications_{date.today().isoformat()}.xlsx")
        target, _ = QFileDialog.getSaveFileName(self, "Export Excel", default_path, "Excel Files (*.xlsx)")
        if not target:
            return
        self._applications_to_dataframe().to_excel(target, index=False, engine="openpyxl")
        QMessageBox.information(self, "Exported", f"Exported to {target}")

from PyQt6.QtCore import QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import ApplicationRepository, JobRepository, ProfileRepository
from app.models.score import JobScore
from app.services.claude_service import (
    ClaudeNotConfiguredError,
    ClaudeRequestError,
    ClaudeService,
    ClaudeTimeoutError,
)
from app.services.job_search_service import (
    SOURCE_BOTH,
    SOURCE_JSEARCH,
    SOURCE_LINKEDIN,
    SearchOutcome,
    search_jobs,
)
from app.services.resume_service import ResumeService
from app.services.scoring_service import EmptyJobDescriptionError, get_cached_score, score_job
from automation.browser_manager import BrowserLaunchError, BrowserManager

RESULT_COLUMNS = ["Title", "Company", "Location", "Source", "Posted", "Match Score", "Status"]


class JobSearchWorker(QThread):
    progress = pyqtSignal(str)
    manual_step_required = pyqtSignal(str)
    manual_step_resolved = pyqtSignal()
    finished_search = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, title: str, location: str, source: str, filters: dict, parent=None):
        super().__init__(parent)
        self.title = title
        self.location = location
        self.source = source
        self.filters = filters
        self.browser_manager = BrowserManager()

    def run(self) -> None:
        try:
            outcome = search_jobs(
                self.title,
                self.location,
                self.source,
                self.filters,
                browser_manager=self.browser_manager,
                on_progress=self.progress.emit,
                on_manual_step_required=self.manual_step_required.emit,
                on_manual_step_resolved=self.manual_step_resolved.emit,
            )
            self.finished_search.emit(outcome)
        except BrowserLaunchError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"Something went wrong during the search: {error}")
        finally:
            self.browser_manager.close()


class SearchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.job_repository = JobRepository()
        self.application_repository = ApplicationRepository()
        self.profile_repository = ProfileRepository()
        self.resume_service = ResumeService()

        self.worker: JobSearchWorker | None = None
        self.current_jobs: list = []
        self.selected_job = None
        self._current_page = 0
        self._append_mode = False

        self._build_ui()
        self._prefill_from_target_roles()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        outer_layout.addWidget(self._build_search_bar())
        outer_layout.addWidget(self._build_filters_row())
        outer_layout.addWidget(self._build_status_row())
        outer_layout.addWidget(self._build_manual_step_banner())

        splitter = QSplitter()
        splitter.addWidget(self._build_results_table())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        outer_layout.addWidget(splitter, 1)

        self.load_more_button = QPushButton("Load More Results")
        self.load_more_button.clicked.connect(self._on_load_more_clicked)
        outer_layout.addWidget(self.load_more_button)

    def _build_search_bar(self) -> QGroupBox:
        group = QGroupBox("Search")
        layout = QHBoxLayout()

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Job title")

        self.location_input = QLineEdit()
        self.location_input.setText("Remote")

        self.source_linkedin = QRadioButton("LinkedIn")
        self.source_jsearch = QRadioButton("JSearch")
        self.source_both = QRadioButton("Both")
        self.source_both.setChecked(True)
        self.source_group = QButtonGroup(self)
        for button in (self.source_linkedin, self.source_jsearch, self.source_both):
            self.source_group.addButton(button)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search_clicked)

        layout.addWidget(QLabel("Title"))
        layout.addWidget(self.title_input, 2)
        layout.addWidget(QLabel("Location"))
        layout.addWidget(self.location_input, 1)
        layout.addWidget(self.source_linkedin)
        layout.addWidget(self.source_jsearch)
        layout.addWidget(self.source_both)
        layout.addWidget(self.search_button)

        group.setLayout(layout)
        return group

    def _build_filters_row(self) -> QGroupBox:
        group = QGroupBox("Filters")
        layout = QHBoxLayout()

        self.remote_only_checkbox = QCheckBox("Remote only")
        self.full_time_only_checkbox = QCheckBox("Full-time only")
        self.posted_within_7_days_checkbox = QCheckBox("Posted within 7 days")
        self.easy_apply_only_checkbox = QCheckBox("Easy Apply only")

        for checkbox in (
            self.remote_only_checkbox,
            self.full_time_only_checkbox,
            self.posted_within_7_days_checkbox,
            self.easy_apply_only_checkbox,
        ):
            layout.addWidget(checkbox)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _build_status_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.status_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        self.results_count_label = QLabel("")

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
        layout.addWidget(self.results_count_label)
        return widget

    def _build_manual_step_banner(self) -> QWidget:
        self.manual_step_banner = QWidget()
        layout = QHBoxLayout(self.manual_step_banner)
        self.manual_step_label = QLabel("")
        continue_button = QPushButton("Continue")
        continue_button.clicked.connect(self._on_continue_clicked)
        layout.addWidget(self.manual_step_label, 1)
        layout.addWidget(continue_button)
        self.manual_step_banner.hide()
        return self.manual_step_banner

    def _build_results_table(self) -> QTableWidget:
        self.results_table = QTableWidget(0, len(RESULT_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.currentCellChanged.connect(lambda *_: self._on_row_selected())
        return self.results_table

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.detail_title_label = QLabel("Select a job to see details")
        self.detail_title_label.setWordWrap(True)
        self.detail_company_label = QLabel("")
        self.detail_meta_label = QLabel("")

        self.detail_description = QTextEdit()
        self.detail_description.setReadOnly(True)

        button_row = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._on_apply_clicked)

        self.score_button = QPushButton("Score")
        self.score_button.setEnabled(False)
        self.score_button.clicked.connect(self._on_score_clicked)

        self.save_to_tracker_button = QPushButton("Save to Tracker")
        self.save_to_tracker_button.setEnabled(False)
        self.save_to_tracker_button.clicked.connect(self._on_save_to_tracker_clicked)

        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.score_button)
        button_row.addWidget(self.save_to_tracker_button)

        layout.addWidget(self.detail_title_label)
        layout.addWidget(self.detail_company_label)
        layout.addWidget(self.detail_meta_label)
        layout.addWidget(self.detail_description, 1)
        layout.addLayout(button_row)
        return panel

    def _prefill_from_target_roles(self) -> None:
        profile = self.profile_repository.get()
        active_roles = [role for role in profile.target_roles if role.is_active]
        if active_roles:
            self.title_input.setText(active_roles[0].role_title)

    def _selected_source(self) -> str:
        if self.source_linkedin.isChecked():
            return SOURCE_LINKEDIN
        if self.source_jsearch.isChecked():
            return SOURCE_JSEARCH
        return SOURCE_BOTH

    def _collect_filters(self) -> dict:
        return {
            "remote_only": self.remote_only_checkbox.isChecked(),
            "full_time_only": self.full_time_only_checkbox.isChecked(),
            "posted_within_7_days": self.posted_within_7_days_checkbox.isChecked(),
            "easy_apply_only": self.easy_apply_only_checkbox.isChecked(),
        }

    def _on_search_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Job Title", "Please enter a job title to search for.")
            return

        location = self.location_input.text().strip() or "Remote"
        filters = self._collect_filters()
        self._current_page = 0
        filters["page"] = self._current_page

        self.current_jobs = []
        self.results_table.setRowCount(0)
        self._start_search(title, location, self._selected_source(), filters, append=False)

    def _on_load_more_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        title = self.title_input.text().strip()
        if not title:
            return

        location = self.location_input.text().strip() or "Remote"
        filters = self._collect_filters()
        self._current_page += 1
        filters["page"] = self._current_page

        self._start_search(title, location, self._selected_source(), filters, append=True)

    def _start_search(self, title: str, location: str, source: str, filters: dict, append: bool) -> None:
        self._append_mode = append
        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")
        self.load_more_button.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("Starting search...")

        self.worker = JobSearchWorker(title, location, source, filters)
        self.worker.progress.connect(self._on_progress)
        self.worker.manual_step_required.connect(self._on_manual_step_required)
        self.worker.manual_step_resolved.connect(self._on_manual_step_resolved)
        self.worker.finished_search.connect(self._on_search_finished)
        self.worker.failed.connect(self._on_search_failed)
        self.worker.start()

    def _on_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_manual_step_required(self, message: str) -> None:
        self.manual_step_label.setText(message)
        self.manual_step_banner.show()
        self.status_label.setText(message)

    def _on_manual_step_resolved(self) -> None:
        self.manual_step_banner.hide()

    def _on_continue_clicked(self) -> None:
        if self.worker is not None:
            self.worker.browser_manager.resume()
        self.manual_step_banner.hide()

    def _on_search_finished(self, outcome: SearchOutcome) -> None:
        self._reset_search_buttons()

        if outcome.notice:
            QMessageBox.information(self, "JSearch Not Configured", outcome.notice)

        if outcome.error and not outcome.jobs:
            QMessageBox.warning(
                self, "Search Error", f"Something went wrong during the search: {outcome.error}"
            )

        self._populate_results(outcome.jobs, append=self._append_mode)

        if not self.current_jobs:
            self.status_label.setText("No jobs found. Try different search terms.")

        self.results_count_label.setText(
            f"Showing {len(self.current_jobs)} results "
            f"({outcome.total_found} found this page, {outcome.filtered_out} filtered out)"
        )

    def _on_search_failed(self, message: str) -> None:
        self._reset_search_buttons()
        QMessageBox.critical(self, "Search Failed", message)

    def _reset_search_buttons(self) -> None:
        self.search_button.setEnabled(True)
        self.search_button.setText("Search")
        self.load_more_button.setEnabled(True)
        self.progress_bar.hide()
        self.manual_step_banner.hide()

    def _populate_results(self, jobs: list, append: bool) -> None:
        if not append:
            self.current_jobs = []
            self.results_table.setRowCount(0)

        for job in jobs:
            self.current_jobs.append(job)
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            score_text = "Pending" if job.score is None else f"{job.score:.1f}"
            for column, value in enumerate(
                [job.title, job.company, job.location, job.source, job.posted_date, score_text, job.status]
            ):
                self.results_table.setItem(row, column, QTableWidgetItem(value))

    def _on_row_selected(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self.current_jobs):
            return
        self._show_job_detail(self.current_jobs[row])

    def _show_job_detail(self, job) -> None:
        self.selected_job = job
        self.detail_title_label.setText(job.title)
        self.detail_company_label.setText(job.company)
        self.detail_meta_label.setText(f"{job.location}  •  Posted {job.posted_date or 'unknown'}")
        self.detail_description.setPlainText(job.description or "(No description available.)")
        self.apply_button.setEnabled(bool(job.url))
        self.score_button.setEnabled(True)
        self.save_to_tracker_button.setEnabled(bool(job.id))

    def _on_apply_clicked(self) -> None:
        if self.selected_job and self.selected_job.url:
            QDesktopServices.openUrl(QUrl(self.selected_job.url))

    def _on_score_clicked(self) -> None:
        QMessageBox.information(
            self, "Coming Soon", "Claude-based job scoring will be available in Phase 4."
        )

    def _on_save_to_tracker_clicked(self) -> None:
        if not self.selected_job or not self.selected_job.id:
            return

        default_resume = self.resume_service.get_default_resume()
        if default_resume is None:
            QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
            return

        self.application_repository.save_to_tracker(self.selected_job.id, default_resume.id)
        self.selected_job.status = "Saved"
        row = self.results_table.currentRow()
        if row >= 0:
            self.results_table.setItem(row, 6, QTableWidgetItem("Saved"))
        QMessageBox.information(self, "Saved", "Job saved to your application tracker.")

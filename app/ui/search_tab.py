import shutil
import time
from datetime import date

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import (
    ApplicationRepository,
    JobRepository,
    ProfileRepository,
    TailoredResumeRepository,
)
from app.models.score import JobScore
from app.services.job_search_service import SearchOutcome, detect_sponsorship_restriction, search_jobs
from app.services.llm_service import (
    LLMNotConfiguredError,
    LLMRequestError,
    LLMService,
    LLMTimeoutError,
    scoring_cost_for_model,
)
from app.services.resume_service import ResumeService
from app.services.scoring_service import EmptyJobDescriptionError, get_cached_score, score_job
from app.ui.search_preferences_panel import SearchPreferencesPanel
from app.ui.tailoring_dialog import TailoringDialog
from app.ui.theme import SCORE_COLORS
from automation.browser_manager import BrowserLaunchError, BrowserManager

RESULT_COLUMNS = ["Title", "Company", "Location", "Source", "Posted", "Match Score", "Status"]
RESULT_COLUMN_WIDTHS = [200, 150, 130, 80, 100, 90, 80]


class JobSearchWorker(QThread):
    progress = pyqtSignal(str)
    manual_step_required = pyqtSignal(str)
    manual_step_resolved = pyqtSignal()
    finished_search = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, titles: list[str], location: str, source: str, filters: dict, parent=None):
        super().__init__(parent)
        self.titles = titles
        self.location = location
        self.source = source
        self.filters = filters
        self.browser_manager = BrowserManager()

    def run(self) -> None:
        all_jobs = []
        total_found = 0
        filtered_out = 0
        sponsorship_hidden_count = 0
        errors = []
        notice = None

        try:
            for index, title in enumerate(self.titles):
                self.progress.emit(f"Searching {title} ({index + 1} of {len(self.titles)})...")
                outcome = search_jobs(
                    title,
                    self.location,
                    self.source,
                    self.filters,
                    browser_manager=self.browser_manager,
                    on_progress=self.progress.emit,
                    on_manual_step_required=self.manual_step_required.emit,
                    on_manual_step_resolved=self.manual_step_resolved.emit,
                )
                all_jobs.extend(outcome.jobs)
                total_found += outcome.total_found
                filtered_out += outcome.filtered_out
                sponsorship_hidden_count += outcome.sponsorship_hidden_count
                if outcome.error:
                    errors.append(outcome.error)
                if outcome.notice and notice is None:
                    notice = outcome.notice

            deduped = {}
            for job in all_jobs:
                key = job.id if job.id else job.url
                deduped[key] = job

            combined_outcome = SearchOutcome(
                jobs=list(deduped.values()),
                total_found=total_found,
                filtered_out=filtered_out,
                sponsorship_hidden_count=sponsorship_hidden_count,
                error="; ".join(errors) if errors else None,
                notice=notice,
            )
            self.finished_search.emit(combined_outcome)
        except BrowserLaunchError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"Something went wrong during the search: {error}")
        finally:
            self.browser_manager.close()


class ScoreWorker(QThread):
    finished_scoring = pyqtSignal(object)
    failed = pyqtSignal(str, bool)

    def __init__(self, job_id: int, resume_text: str, job_description: str, job_title: str, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.resume_text = resume_text
        self.job_description = job_description
        self.job_title = job_title

    def run(self) -> None:
        try:
            score = score_job(self.job_id, self.resume_text, self.job_description, self.job_title)
            self.finished_scoring.emit(score)
        except LLMNotConfiguredError as error:
            self.failed.emit(str(error), False)
        except EmptyJobDescriptionError as error:
            self.failed.emit(str(error), False)
        except LLMTimeoutError as error:
            self.failed.emit(str(error), True)
        except LLMRequestError as error:
            self.failed.emit(str(error), True)
        except Exception as error:
            self.failed.emit(f"Scoring failed: {error}", True)


class ScoreAllWorker(QThread):
    progress = pyqtSignal(str)
    job_scored = pyqtSignal(object)
    finished_all = pyqtSignal()

    def __init__(self, jobs: list, resume_text: str, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.resume_text = resume_text

    def run(self) -> None:
        total = len(self.jobs)
        for index, job in enumerate(self.jobs):
            self.progress.emit(f"Scoring {index + 1} of {total}...")
            try:
                score = score_job(job.id, self.resume_text, job.description, job.title)
                self.job_scored.emit(score)
            except Exception:
                pass
            if index < total - 1:
                time.sleep(1)
        self.finished_all.emit()


class SearchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.job_repository = JobRepository()
        self.application_repository = ApplicationRepository()
        self.profile_repository = ProfileRepository()
        self.resume_service = ResumeService()
        self.llm_service = LLMService()

        self.worker: JobSearchWorker | None = None
        self.score_worker: ScoreWorker | None = None
        self.score_all_worker: ScoreAllWorker | None = None
        self.current_jobs: list = []
        self.selected_job = None
        self.current_application = None
        self._current_page = 0
        self._append_mode = False

        self._build_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        self.preferences_panel = SearchPreferencesPanel()
        outer_layout.addWidget(self.preferences_panel)

        self.search_button = QPushButton("Search")
        self.search_button.setFixedSize(200, 36)
        self.search_button.setStyleSheet(
            "QPushButton { background-color: #2F81F7; color: white; border: none;"
            " border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388BFD; }"
            "QPushButton:disabled { background-color: #30363D; color: #7D8590; }"
        )
        self.search_button.clicked.connect(self._on_search_clicked)
        search_button_row = QHBoxLayout()
        search_button_row.addStretch()
        search_button_row.addWidget(self.search_button)
        search_button_row.addStretch()
        outer_layout.addLayout(search_button_row)

        outer_layout.addWidget(self._build_status_row())
        outer_layout.addWidget(self._build_manual_step_banner())

        splitter = QSplitter()
        splitter.addWidget(self._build_results_table())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        outer_layout.addWidget(splitter, 1)

        bottom_row = QHBoxLayout()
        self.load_more_button = QPushButton("Load More Results")
        self.load_more_button.clicked.connect(self._on_load_more_clicked)
        self.score_all_button = QPushButton("Score All")
        self.score_all_button.clicked.connect(self._on_score_all_clicked)
        bottom_row.addWidget(self.load_more_button)
        bottom_row.addWidget(self.score_all_button)
        outer_layout.addLayout(bottom_row)

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
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(RESULT_COLUMN_WIDTHS):
            self.results_table.setColumnWidth(column, width)
        header.setStretchLastSection(False)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.currentCellChanged.connect(lambda *_: self._on_row_selected())
        return self.results_table

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        outer_layout = QVBoxLayout(panel)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 2)
        panel.setGraphicsEffect(shadow)

        self.detail_placeholder_label = QLabel("Select a job from the list to see details")
        self.detail_placeholder_label.setWordWrap(True)
        self.detail_placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(self.detail_placeholder_label)

        self.detail_content_widget = QWidget()
        layout = QVBoxLayout(self.detail_content_widget)

        self.detail_title_label = QLabel("")
        self.detail_title_label.setWordWrap(True)
        self.detail_company_label = QLabel("")
        self.detail_meta_label = QLabel("")

        layout.addWidget(self.detail_title_label)
        layout.addWidget(self.detail_company_label)
        layout.addWidget(self.detail_meta_label)
        layout.addWidget(self._build_score_panel())

        self.detail_description = QTextEdit()
        self.detail_description.setReadOnly(True)
        self.detail_description.setAcceptRichText(False)
        self.detail_description.setStyleSheet(
            "font-size: 10px; color: #E6EDF3; line-height: normal;"
        )

        self.resume_indicator_label = QLabel("")
        self.resume_indicator_label.setWordWrap(True)

        tailoring_row = QHBoxLayout()
        self.tailor_resume_button_main = QPushButton("Tailor Resume")
        self.tailor_resume_button_main.setEnabled(False)
        self.tailor_resume_button_main.clicked.connect(self._on_tailor_resume_clicked)

        self.view_tailored_button = QPushButton("View Tailored Resume")
        self.view_tailored_button.setEnabled(False)
        self.view_tailored_button.clicked.connect(self._on_view_tailored_resume_clicked)

        self.download_resume_button = QPushButton("Download Resume")
        self.download_resume_button.setEnabled(False)
        self.download_resume_button.clicked.connect(self._on_download_resume_clicked)

        tailoring_row.addWidget(self.tailor_resume_button_main)
        tailoring_row.addWidget(self.view_tailored_button)
        tailoring_row.addWidget(self.download_resume_button)

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

        self.mark_applied_button = QPushButton("Mark as Applied")
        self.mark_applied_button.setEnabled(False)
        self.mark_applied_button.clicked.connect(self._on_mark_applied_clicked)

        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.score_button)
        button_row.addWidget(self.save_to_tracker_button)
        button_row.addWidget(self.mark_applied_button)

        layout.addWidget(self.detail_description, 1)
        layout.addWidget(self.resume_indicator_label)
        layout.addLayout(tailoring_row)
        layout.addLayout(button_row)

        outer_layout.addWidget(self.detail_content_widget)
        self.detail_content_widget.setVisible(False)
        return panel

    def _build_score_panel(self) -> QGroupBox:
        group = QGroupBox("Match Score")
        layout = QVBoxLayout()

        self.score_value_label = QLabel("")
        self.score_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_value_label.setStyleSheet("font-size: 28px; font-weight: bold; padding: 6px;")
        self.score_value_label.hide()

        self.score_status_label = QLabel("")
        self.score_status_label.setWordWrap(True)
        self.score_status_label.setTextFormat(Qt.TextFormat.PlainText)

        self.score_progress_bar = QProgressBar()
        self.score_progress_bar.setRange(0, 0)
        self.score_progress_bar.setMaximumHeight(50)
        self.score_progress_bar.setTextVisible(False)
        self.score_progress_bar.hide()

        self.retry_score_button = QPushButton("Retry")
        self.retry_score_button.clicked.connect(self._on_retry_score_clicked)
        self.retry_score_button.hide()

        self.matched_keywords_header = QLabel("Matched Keywords")
        self.matched_keywords_header.setStyleSheet("font-weight: bold;")
        self.matched_keywords_label = QLabel("")
        self.matched_keywords_label.setWordWrap(True)
        self.matched_keywords_label.setTextFormat(Qt.TextFormat.RichText)

        self.missing_keywords_header = QLabel("Missing Keywords")
        self.missing_keywords_header.setStyleSheet("font-weight: bold;")
        self.missing_keywords_label = QLabel("")
        self.missing_keywords_label.setWordWrap(True)
        self.missing_keywords_label.setTextFormat(Qt.TextFormat.RichText)

        self.reasoning_header = QLabel("Reasoning")
        self.reasoning_header.setStyleSheet("font-weight: bold;")
        self.reasoning_label = QLabel("")
        self.reasoning_label.setWordWrap(True)
        self.reasoning_label.setTextFormat(Qt.TextFormat.PlainText)

        self.recommendation_header = QLabel("Recommendation")
        self.recommendation_header.setStyleSheet("font-weight: bold;")
        self.recommendation_label = QLabel("")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setTextFormat(Qt.TextFormat.PlainText)

        self.tailor_resume_button = QPushButton("Tailor Resume")
        self.tailor_resume_button.setStyleSheet("font-weight: bold; padding: 6px;")
        self.tailor_resume_button.clicked.connect(self._on_tailor_resume_clicked)
        self.tailor_resume_button.hide()

        self.good_resume_label = QLabel("Resume looks good for this job — apply with default resume")
        self.good_resume_label.setWordWrap(True)
        self.good_resume_label.setStyleSheet("font-weight: bold; color: #66bb6a;")
        self.good_resume_label.hide()

        for widget in (
            self.score_value_label,
            self.score_status_label,
            self.score_progress_bar,
            self.retry_score_button,
            self.matched_keywords_header,
            self.matched_keywords_label,
            self.missing_keywords_header,
            self.missing_keywords_label,
            self.reasoning_header,
            self.reasoning_label,
            self.recommendation_header,
            self.recommendation_label,
            self.tailor_resume_button,
            self.good_resume_label,
        ):
            layout.addWidget(widget)

        self._set_score_detail_visible(False)
        group.setLayout(layout)
        self.score_group = group
        return group

    def _on_search_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        titles = self.preferences_panel.get_selected_titles()
        if not titles:
            QMessageBox.warning(
                self, "No Titles Selected", "Please select at least one job title to search for."
            )
            return

        location = self.preferences_panel.get_location_text()
        filters = self.preferences_panel.get_filters()
        source = self.preferences_panel.get_source()
        self._current_page = 0
        filters["page"] = self._current_page

        self.current_jobs = []
        self.results_table.setRowCount(0)
        self._start_search(titles, location, source, filters, append=False)

    def _on_load_more_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        titles = self.preferences_panel.get_selected_titles()
        if not titles:
            return

        location = self.preferences_panel.get_location_text()
        filters = self.preferences_panel.get_filters()
        source = self.preferences_panel.get_source()
        self._current_page += 1
        filters["page"] = self._current_page

        self._start_search(titles, location, source, filters, append=True)

    def _start_search(self, titles: list[str], location: str, source: str, filters: dict, append: bool) -> None:
        self._append_mode = append
        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")
        self.load_more_button.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("Starting search...")

        self.worker = JobSearchWorker(titles, location, source, filters)
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
            f"({outcome.total_found} found across title searches, {outcome.filtered_out} filtered out)"
        )
        self.preferences_panel.show_sponsorship_hidden_count(outcome.sponsorship_hidden_count)

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

        existing_ids = {job.id for job in self.current_jobs if job.id}
        for job in jobs:
            if job.id and job.id in existing_ids:
                continue
            existing_ids.add(job.id)
            self.current_jobs.append(job)
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            score_text = "Pending" if job.score is None else str(int(job.score))
            title_text = job.title
            if detect_sponsorship_restriction(job.description):
                title_text = f"⚠️ {job.title}"
            for column, value in enumerate(
                [title_text, job.company, job.location, job.source, job.posted_date, score_text, job.status]
            ):
                item = QTableWidgetItem(value)
                if column == 0 and title_text != job.title:
                    item.setToolTip("Review visa requirements before applying")
                self.results_table.setItem(row, column, item)
            if job.score is not None:
                self._colorize_score_cell(row, int(job.score))

    def _on_row_selected(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self.current_jobs):
            self.selected_job = None
            self.detail_content_widget.setVisible(False)
            self.detail_placeholder_label.setVisible(True)
            return
        self._show_job_detail(self.current_jobs[row])

    def _show_job_detail(self, job) -> None:
        self.detail_placeholder_label.setVisible(False)
        self.detail_content_widget.setVisible(True)
        self.selected_job = job
        self.detail_title_label.setText(job.title)
        self.detail_company_label.setText(job.company)
        self.detail_meta_label.setText(f"{job.location}  •  Posted {job.posted_date or 'unknown'}")
        self.detail_description.setPlainText(job.description or "(No description available.)")
        self.apply_button.setEnabled(bool(job.url))
        self.score_button.setEnabled(True)
        self.tailor_resume_button_main.setEnabled(True)
        self.download_resume_button.setEnabled(True)
        self._update_tracker_buttons(job)
        self._update_tailoring_buttons(job)

        self._reset_score_panel()
        cached_score = get_cached_score(job.id) if job.id else None
        if cached_score is not None:
            self._render_score(cached_score)
        elif job.description and job.description.strip():
            self._trigger_scoring(job)

    def _update_tailoring_buttons(self, job) -> None:
        tailored = TailoredResumeRepository().get_by_job_id(job.id) if job.id else None
        if tailored is not None:
            self.view_tailored_button.setEnabled(True)
            self.resume_indicator_label.setText(f"Resume: {tailored.file_name}")
            return

        self.view_tailored_button.setEnabled(False)
        default_resume = self.resume_service.get_default_resume()
        if default_resume is not None:
            self.resume_indicator_label.setText(f"Resume: Default ({default_resume.file_name})")
        else:
            self.resume_indicator_label.setText("Resume: None (upload a default resume in Settings)")

    def _update_tracker_buttons(self, job) -> None:
        self.current_application = (
            self.application_repository.get_by_job_id(job.id) if job.id else None
        )
        if self.current_application is not None:
            self.save_to_tracker_button.setText("Saved ✓")
            self.save_to_tracker_button.setEnabled(False)
            self.mark_applied_button.setEnabled(self.current_application.status == "Saved")
        else:
            self.save_to_tracker_button.setText("Save to Tracker")
            self.save_to_tracker_button.setEnabled(bool(job.id))
            self.mark_applied_button.setEnabled(False)

    def _on_apply_clicked(self) -> None:
        if self.selected_job and self.selected_job.url:
            QDesktopServices.openUrl(QUrl(self.selected_job.url))

    def _on_score_clicked(self) -> None:
        if not self.selected_job:
            return
        cached_score = get_cached_score(self.selected_job.id) if self.selected_job.id else None
        if cached_score is not None:
            self._render_score(cached_score)
            return
        self._trigger_scoring(self.selected_job)

    def _on_retry_score_clicked(self) -> None:
        if self.selected_job:
            self._trigger_scoring(self.selected_job)

    def _on_tailor_resume_clicked(self) -> None:
        if not self.selected_job:
            return

        default_resume = self.resume_service.get_default_resume()
        if default_resume is None:
            QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
            return

        job = self.selected_job
        if not job.description or len(job.description.strip()) < 100:
            QMessageBox.warning(
                self,
                "Job Description Too Short",
                "This job's description is too short to tailor a resume against "
                "(needs at least 100 characters).",
            )
            return

        profile = self.profile_repository.get()
        role_description = self._matching_role_description(profile, job.title)

        dialog = TailoringDialog(
            job, default_resume.file_path, role_description, profile, job.score, parent=self
        )
        dialog.exec()
        self._update_tailoring_buttons(job)

    def _on_view_tailored_resume_clicked(self) -> None:
        if not self.selected_job:
            return

        tailored = TailoredResumeRepository().get_by_job_id(self.selected_job.id)
        if tailored is None:
            return

        profile = self.profile_repository.get()
        role_description = self._matching_role_description(profile, self.selected_job.title)
        dialog = TailoringDialog(
            self.selected_job,
            tailored.source_resume_path,
            role_description,
            profile,
            self.selected_job.score,
            parent=self,
            existing_tailored_resume=tailored,
        )
        dialog.exec()
        self._update_tailoring_buttons(self.selected_job)

    def _on_download_resume_clicked(self) -> None:
        if not self.selected_job:
            return

        tailored = TailoredResumeRepository().get_by_job_id(self.selected_job.id)
        if tailored is not None:
            source_path, suggested_name = tailored.file_path, tailored.file_name
        else:
            default_resume = self.resume_service.get_default_resume()
            if default_resume is None:
                QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
                return
            source_path, suggested_name = default_resume.file_path, default_resume.file_name

        target, _ = QFileDialog.getSaveFileName(
            self, "Download Resume", suggested_name, "Word Documents (*.docx)"
        )
        if target:
            shutil.copy2(source_path, target)

    @staticmethod
    def _matching_role_description(profile, job_title: str) -> str:
        active_roles = [role for role in profile.target_roles if role.is_active]
        job_title_lower = job_title.lower()
        for role in active_roles:
            if role.role_title.lower() in job_title_lower or job_title_lower in role.role_title.lower():
                return role.role_description
        return active_roles[0].role_description if active_roles else ""

    def _trigger_scoring(self, job) -> None:
        if self.score_worker is not None and self.score_worker.isRunning():
            return

        if not job.description or not job.description.strip():
            QMessageBox.information(
                self, "No Description", "No job description available to score against"
            )
            return

        default_resume = self.resume_service.get_default_resume()
        if default_resume is None:
            QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
            return

        if not self.llm_service.is_configured("scoring"):
            QMessageBox.warning(
                self,
                "AI Provider Not Configured",
                "Configure an API key for your selected scoring provider in Settings → AI Provider",
            )
            return

        resume_text = self.resume_service.get_resume_text(default_resume.file_path)
        self._show_scoring_state()

        self.score_worker = ScoreWorker(job.id, resume_text, job.description, job.title)
        self.score_worker.finished_scoring.connect(self._on_score_finished)
        self.score_worker.failed.connect(self._on_score_failed)
        self.score_worker.start()

    def _show_scoring_state(self) -> None:
        self._set_score_detail_visible(False)
        self.score_value_label.hide()
        self.retry_score_button.hide()
        self.tailor_resume_button.hide()
        self.good_resume_label.hide()
        self.score_progress_bar.show()
        self.score_status_label.setText("Scoring...")

    def _on_score_finished(self, score: JobScore) -> None:
        self.score_progress_bar.hide()
        self._render_score(score)
        self._update_table_score_cell(score)

    def _on_score_failed(self, message: str, retryable: bool) -> None:
        self.score_progress_bar.hide()
        self.score_value_label.hide()
        self.score_status_label.setText(message)
        self.retry_score_button.setVisible(retryable)

    def _reset_score_panel(self) -> None:
        self.score_progress_bar.hide()
        self.retry_score_button.hide()
        self.score_value_label.hide()
        self.tailor_resume_button.hide()
        self.good_resume_label.hide()
        self.score_status_label.setText("")
        self._set_score_detail_visible(False)

    def _set_score_detail_visible(self, visible: bool) -> None:
        for widget in (
            self.matched_keywords_header,
            self.matched_keywords_label,
            self.missing_keywords_header,
            self.missing_keywords_label,
            self.reasoning_header,
            self.reasoning_label,
            self.recommendation_header,
            self.recommendation_label,
        ):
            widget.setVisible(visible)

    def _render_score(self, score: JobScore) -> None:
        self.score_progress_bar.hide()
        self.retry_score_button.hide()
        self.score_status_label.setText("")

        background, text_color = self._score_colors(score.score)
        self.score_value_label.setText(f"{score.score}")
        self.score_value_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; padding: 6px; "
            f"background-color: {background}; color: {text_color}; border-radius: 6px;"
        )
        self.score_value_label.show()

        self.matched_keywords_label.setText(
            self._render_keyword_pills(score.matched_keywords, "#1A7F37", "#3FB950")
        )
        self.missing_keywords_label.setText(
            self._render_keyword_pills(score.missing_keywords, "#6E1C1C", "#F85149")
        )
        self.reasoning_label.setText(score.reasoning or "(No reasoning provided.)")
        self.recommendation_label.setText(score.recommendation or "(No recommendation provided.)")
        self._set_score_detail_visible(True)

        if score.score >= 90:
            self.tailor_resume_button.hide()
            self.good_resume_label.show()
        else:
            self.good_resume_label.hide()
            self.tailor_resume_button.show()

    @staticmethod
    def _score_colors(score: int) -> tuple[str, str]:
        if score >= 90:
            return SCORE_COLORS["high"]
        if score >= 70:
            return SCORE_COLORS["medium"]
        return SCORE_COLORS["low"]

    @staticmethod
    def _render_keyword_pills(keywords: list[str], background: str, text_color: str) -> str:
        if not keywords:
            return "<i>None</i>"
        style = (
            f"background-color:{background}; color:{text_color}; "
            "padding:2px 8px; border-radius:10px;"
        )
        return "&nbsp;".join(f'<span style="{style}">{keyword}</span>' for keyword in keywords)

    def _update_table_score_cell(self, score: JobScore) -> None:
        for row, job in enumerate(self.current_jobs):
            if job.id == score.job_id:
                job.score = score.score
                self.results_table.setItem(row, 5, QTableWidgetItem(str(score.score)))
                self._colorize_score_cell(row, score.score)
                break

    def _colorize_score_cell(self, row: int, score: int) -> None:
        background, text_color = self._score_colors(score)
        item = self.results_table.item(row, 5)
        if item is not None:
            item.setBackground(QColor(background))
            item.setForeground(QColor(text_color))

    def _on_score_all_clicked(self) -> None:
        if self.score_all_worker is not None and self.score_all_worker.isRunning():
            return

        unscored_jobs = [job for job in self.current_jobs if job.id and job.score is None]
        if not unscored_jobs:
            QMessageBox.information(self, "Score All", "All jobs already have a score.")
            return

        default_resume = self.resume_service.get_default_resume()
        if default_resume is None:
            QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
            return

        if not self.llm_service.is_configured("scoring"):
            QMessageBox.warning(
                self,
                "AI Provider Not Configured",
                "Configure an API key for your selected scoring provider in Settings → AI Provider",
            )
            return

        estimated_cost = len(unscored_jobs) * scoring_cost_for_model(self.profile_repository.get().scoring_model)
        confirmation = QMessageBox.question(
            self,
            "Score All",
            f"Score {len(unscored_jobs)} unscored jobs?\n"
            f"Estimated cost: ~${estimated_cost:.2f} for {len(unscored_jobs)} jobs",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        resume_text = self.resume_service.get_resume_text(default_resume.file_path)
        self.score_all_button.setEnabled(False)
        self.score_all_worker = ScoreAllWorker(unscored_jobs, resume_text)
        self.score_all_worker.progress.connect(self._on_progress)
        self.score_all_worker.job_scored.connect(self._update_table_score_cell)
        self.score_all_worker.finished_all.connect(self._on_score_all_finished)
        self.score_all_worker.start()

    def _on_score_all_finished(self) -> None:
        self.score_all_button.setEnabled(True)
        self.status_label.setText("Done scoring all jobs.")

    def _on_save_to_tracker_clicked(self) -> None:
        if not self.selected_job or not self.selected_job.id:
            return

        default_resume = self.resume_service.get_default_resume()
        if default_resume is None:
            QMessageBox.warning(self, "No Resume", "Please upload your resume in Settings first")
            return

        self.application_repository.save_to_tracker(
            self.selected_job, default_resume.id, default_resume.file_path
        )
        self.selected_job.status = "Saved"
        row = self.results_table.currentRow()
        if row >= 0:
            self.results_table.setItem(row, 6, QTableWidgetItem("Saved"))
        self._update_tracker_buttons(self.selected_job)
        QMessageBox.information(self, "Saved", "Job saved to your application tracker.")

    def _on_mark_applied_clicked(self) -> None:
        if not self.current_application:
            return

        self.application_repository.mark_applied(self.current_application.id, date.today().isoformat())
        self.selected_job.status = "Applied"
        row = self.results_table.currentRow()
        if row >= 0:
            self.results_table.setItem(row, 6, QTableWidgetItem("Applied"))
        self._update_tracker_buttons(self.selected_job)
        QMessageBox.information(self, "Marked as Applied", "Application status updated to Applied.")

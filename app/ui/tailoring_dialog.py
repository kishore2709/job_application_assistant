import difflib
import html
import shutil

from docx import Document
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import JobRepository, TailoredResumeRepository
from app.services.claude_service import ClaudeNotConfiguredError, ClaudeRequestError, ClaudeTimeoutError
from app.services.tailoring_service import ShortJobDescriptionError, rebuild_tailored_docx, tailor_resume


class TailorWorker(QThread):
    finished_tailoring = pyqtSignal(object)
    failed = pyqtSignal(str, bool)

    def __init__(self, job, resume_path: str, role_description: str, profile, score, parent=None):
        super().__init__(parent)
        self.job = job
        self.resume_path = resume_path
        self.role_description = role_description
        self.profile = profile
        self.score = score

    def run(self) -> None:
        try:
            result = tailor_resume(
                job_id=self.job.id,
                company=self.job.company,
                resume_path=self.resume_path,
                jd_text=self.job.description,
                job_title=self.job.title,
                role_description=self.role_description,
                profile=self.profile,
                score=self.score,
            )
            self.finished_tailoring.emit(result)
        except ShortJobDescriptionError as error:
            self.failed.emit(str(error), False)
        except ClaudeNotConfiguredError as error:
            self.failed.emit(str(error), False)
        except ClaudeTimeoutError as error:
            self.failed.emit(str(error), True)
        except ClaudeRequestError as error:
            self.failed.emit(str(error), True)
        except Exception as error:
            self.failed.emit(f"Tailoring failed: {error}", True)


def _escape(line: str) -> str:
    return html.escape(line) or "&nbsp;"


def build_diff_html(original_lines: list[str], tailored_lines: list[str]) -> tuple[str, str]:
    matcher = difflib.SequenceMatcher(None, original_lines, tailored_lines)
    left_parts: list[str] = []
    right_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in original_lines[i1:i2]:
                left_parts.append(_escape(line))
                right_parts.append(_escape(line))
        elif tag == "delete":
            for line in original_lines[i1:i2]:
                left_parts.append(
                    f'<span style="color:#ef5350; text-decoration: line-through;">{_escape(line)}</span>'
                )
        elif tag == "insert":
            for line in tailored_lines[j1:j2]:
                right_parts.append(f'<span style="color:#66bb6a;">{_escape(line)}</span>')
        elif tag == "replace":
            for line in original_lines[i1:i2]:
                left_parts.append(
                    f'<span style="color:#ef5350; text-decoration: line-through;">{_escape(line)}</span>'
                )
            for line in tailored_lines[j1:j2]:
                right_parts.append(f'<span style="color:#66bb6a;">{_escape(line)}</span>')

    left_html = "<br>".join(left_parts) or "(empty)"
    right_html = "<br>".join(right_parts) or "(empty)"
    return left_html, right_html


class TailoringDialog(QDialog):
    def __init__(self, job, resume_path: str, role_description: str, profile, score, parent=None):
        super().__init__(parent)
        self.job = job
        self.resume_path = resume_path
        self.role_description = role_description
        self.profile = profile
        self.score = score
        self.tailored_resume = None
        self.worker: TailorWorker | None = None

        self.setWindowTitle(f"Tailor Resume — {job.title} at {job.company}")
        self.setMinimumSize(1000, 650)

        self.outer_layout = QVBoxLayout(self)
        self._build_loading_state()
        self._build_diff_view()
        self._build_button_row()

        self._start_tailoring()

    def _build_loading_state(self) -> None:
        self.loading_widget = QWidget()
        layout = QVBoxLayout(self.loading_widget)

        self.loading_label = QLabel("Tailoring resume with Claude...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.loading_eta_label = QLabel("This takes about 15-20 seconds")
        self.loading_eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)

        self.loading_error_label = QLabel("")
        self.loading_error_label.setWordWrap(True)
        self.loading_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self._start_tailoring)
        self.retry_button.hide()

        layout.addStretch()
        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_eta_label)
        layout.addWidget(self.loading_progress)
        layout.addWidget(self.loading_error_label)
        layout.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self.outer_layout.addWidget(self.loading_widget)

    def _build_diff_view(self) -> None:
        self.diff_widget = QWidget()
        layout = QVBoxLayout(self.diff_widget)

        splitter = QSplitter()
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.tailored_text_edit = QTextEdit()
        self.tailored_text_edit.setReadOnly(True)

        splitter.addWidget(self._wrap_with_label("Original Resume", self.original_text))
        splitter.addWidget(self._wrap_with_label("Tailored Resume", self.tailored_text_edit))
        layout.addWidget(splitter)

        self.diff_widget.hide()
        self.outer_layout.addWidget(self.diff_widget, 1)

    @staticmethod
    def _wrap_with_label(title: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        label = QLabel(title)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        layout.addWidget(widget)
        return container

    def _build_button_row(self) -> None:
        self.button_row = QWidget()
        layout = QHBoxLayout(self.button_row)

        self.edit_button = QPushButton("Edit Tailored Resume")
        self.edit_button.clicked.connect(self._on_edit_clicked)

        self.save_final_button = QPushButton("Save Final Resume")
        self.save_final_button.setEnabled(False)
        self.save_final_button.clicked.connect(self._on_save_final_clicked)

        self.download_button = QPushButton("Download DOCX")
        self.download_button.clicked.connect(self._on_download_clicked)

        self.use_to_apply_button = QPushButton("Use This Resume to Apply")
        self.use_to_apply_button.clicked.connect(self._on_use_to_apply_clicked)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        for button in (
            self.edit_button,
            self.save_final_button,
            self.download_button,
            self.use_to_apply_button,
            close_button,
        ):
            layout.addWidget(button)

        self.button_row.hide()
        self.outer_layout.addWidget(self.button_row)

    def _show_loading(self) -> None:
        self.loading_error_label.setText("")
        self.retry_button.hide()
        self.loading_progress.show()
        self.diff_widget.hide()
        self.button_row.hide()
        self.loading_widget.show()

    def _start_tailoring(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self._show_loading()
        self.worker = TailorWorker(self.job, self.resume_path, self.role_description, self.profile, self.score)
        self.worker.finished_tailoring.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_finished(self, tailored_resume) -> None:
        self.tailored_resume = tailored_resume
        self.loading_widget.hide()

        original_lines = [paragraph.text for paragraph in Document(self.resume_path).paragraphs]
        tailored_lines = tailored_resume.tailored_text.splitlines()
        left_html, right_html = build_diff_html(original_lines, tailored_lines)

        self.original_text.setHtml(f"<pre style='white-space: pre-wrap; font-family: inherit;'>{left_html}</pre>")
        self.tailored_text_edit.setHtml(
            f"<pre style='white-space: pre-wrap; font-family: inherit;'>{right_html}</pre>"
        )

        self.diff_widget.show()
        self.button_row.show()

    def _on_failed(self, message: str, retryable: bool) -> None:
        self.loading_progress.hide()
        self.loading_error_label.setText(message)
        self.retry_button.setVisible(retryable)

    def _on_edit_clicked(self) -> None:
        if not self.tailored_resume:
            return
        self.tailored_text_edit.setReadOnly(False)
        self.tailored_text_edit.setPlainText(self.tailored_resume.tailored_text)
        self.save_final_button.setEnabled(True)

    def _on_save_final_clicked(self) -> None:
        if not self.tailored_resume:
            return
        new_text = self.tailored_text_edit.toPlainText()
        rebuild_tailored_docx(
            self.tailored_resume.source_resume_path, new_text, self.tailored_resume.file_path
        )
        TailoredResumeRepository().update_text_and_file(
            self.tailored_resume.id, new_text, self.tailored_resume.file_path
        )
        self.tailored_resume.tailored_text = new_text
        self.tailored_text_edit.setReadOnly(True)
        QMessageBox.information(self, "Saved", "Final resume saved.")

    def _on_download_clicked(self) -> None:
        if not self.tailored_resume:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Save Resume As", self.tailored_resume.file_name, "Word Documents (*.docx)"
        )
        if target:
            shutil.copy2(self.tailored_resume.file_path, target)

    def _on_use_to_apply_clicked(self) -> None:
        if not self.tailored_resume or not self.tailored_resume.resume_id:
            return
        JobRepository().set_preferred_resume(self.job.id, self.tailored_resume.resume_id)
        QMessageBox.information(
            self, "Set", "This tailored resume will be used when you apply to this job."
        )

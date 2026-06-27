import webbrowser
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from automation.browser_manager import BrowserLaunchError, BrowserManager
from automation.easy_apply_helper import (
    attempt_easy_apply,
    copy_to_clipboard,
    show_in_finder,
)

_DIRECT_ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "taleo.net",
    "icims.com",
    "jobvite.com",
    "smartrecruiters.com",
    "successfactors.com",
    "myworkdayjobs.com",
]


def detect_apply_method(job_url: str, job_source: str = "") -> str:
    """Return 'linkedin' only for direct LinkedIn job-view URLs; 'browser' for all else."""
    if not job_url:
        return "browser"
    url_lower = job_url.lower()
    # Only attempt Easy Apply for a direct job-view URL — redirect/search URLs won't have the button
    if "linkedin.com/jobs/view/" in url_lower:
        return "linkedin"
    # linkedin.com but not a direct job view (redirect, search, etc.) — open in browser
    if "linkedin.com" in url_lower:
        return "browser"
    # JSearch apply_link goes to company site or a LinkedIn redirect, not Easy Apply
    if job_source == "JSearch":
        return "browser"
    return "browser"


class ApplyOptionsDialog(QDialog):
    """Step 1: Choose which resume to use. Application method is auto-detected."""

    def __init__(self, job, tailored_resume=None, default_resume=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.tailored_resume = tailored_resume
        self.default_resume = default_resume
        self.selected_resume = None
        self._detected_method = detect_apply_method(
            job.url or "", getattr(job, "source", "")
        )

        self.setWindowTitle(f"Apply to {job.company}")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"<b>Job:</b> {self.job.title}"))

        # ── Resume section ────────────────────────────────────────────────
        resume_lbl = QLabel("Resume to use:")
        resume_lbl.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(resume_lbl)

        self.resume_group = QButtonGroup(self)

        self.radio_tailored = None
        if self.tailored_resume:
            name = Path(self.tailored_resume.file_path).name
            self.radio_tailored = QRadioButton(f"{name}\n  (tailored — recommended)")
            self.radio_tailored.setChecked(True)
            self.resume_group.addButton(self.radio_tailored)
            layout.addWidget(self.radio_tailored)

        self.radio_default = None
        if self.default_resume:
            name = Path(self.default_resume.file_path).name
            self.radio_default = QRadioButton(f"{name}\n  (default)")
            if self.tailored_resume is None:
                self.radio_default.setChecked(True)
            self.resume_group.addButton(self.radio_default)
            layout.addWidget(self.radio_default)

        if not self.tailored_resume and not self.default_resume:
            layout.addWidget(QLabel("⚠  No resume found — upload one in Settings first."))

        # ── Auto-detected method info ──────────────────────────────────────
        if self._detected_method == "linkedin":
            method_text = "Will attempt LinkedIn Easy Apply (auto-fill)"
        else:
            method_text = "Will open company website in your browser"

        method_info = QLabel(method_text)
        method_info.setStyleSheet("color: #7D8590; font-size: 11px; margin-top: 8px;")
        layout.addWidget(method_info)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        proceed_btn = QPushButton("Proceed")
        proceed_btn.setProperty("primary", "true")
        proceed_btn.clicked.connect(self._on_proceed)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(proceed_btn)
        layout.addLayout(btn_row)

    def _on_proceed(self) -> None:
        if self.radio_tailored and self.radio_tailored.isChecked():
            self.selected_resume = self.tailored_resume
        elif self.radio_default:
            self.selected_resume = self.default_resume
        self.accept()

    def get_resume_path(self) -> str:
        if self.selected_resume is None:
            return ""
        return getattr(self.selected_resume, "file_path", "") or ""

    def get_resume_id(self) -> int | None:
        if self.selected_resume is None:
            return None
        return getattr(self.selected_resume, "id", None)

    def get_method(self) -> str:
        return self._detected_method


class ManualApplyReminderDialog(QDialog):
    """Step 2 (manual path): profile quick-fill + confirm dialog."""

    applied = pyqtSignal()

    def __init__(self, job, resume_path: str, profile, parent=None):
        super().__init__(parent)
        self.job = job
        self.resume_path = resume_path
        self.profile = profile

        self.setWindowTitle(f"Apply to {job.company}")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(f"Opening <b>{self.job.company}</b> application page…"))

        if self.resume_path:
            resume_name = Path(self.resume_path).name
            layout.addWidget(QLabel(f"Upload this resume: <b>{resume_name}</b>"))

            file_row = QHBoxLayout()
            finder_btn = QPushButton("Show in Finder")
            finder_btn.clicked.connect(lambda: show_in_finder(self.resume_path))
            copy_path_btn = QPushButton("Copy file path")
            copy_path_btn.clicked.connect(lambda: copy_to_clipboard(self.resume_path))
            file_row.addWidget(finder_btn)
            file_row.addWidget(copy_path_btn)
            file_row.addStretch()
            layout.addLayout(file_row)

        # Quick-fill section
        qf_lbl = QLabel("Profile quick-fill (click to copy):")
        qf_lbl.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(qf_lbl)

        for label_text, value in [
            ("Name", self.profile.full_name),
            ("Email", self.profile.email),
            ("Phone", self.profile.phone),
        ]:
            if not value:
                continue
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label_text}:  {value}"))
            copy_btn = QPushButton("Copy")
            copy_btn.setFixedWidth(60)
            copy_btn.clicked.connect(
                lambda _checked=False, v=value: copy_to_clipboard(v)
            )
            row.addWidget(copy_btn)
            row.addStretch()
            layout.addLayout(row)

        hint = QLabel("Click 'I Have Applied' when the application is submitted.")
        hint.setStyleSheet("margin-top: 8px; color: #7D8590;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        applied_btn = QPushButton("I Have Applied")
        applied_btn.setProperty("primary", "true")
        applied_btn.clicked.connect(self._on_applied)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(applied_btn)
        layout.addLayout(btn_row)

    def _on_applied(self) -> None:
        self.applied.emit()
        self.accept()


class EasyApplyProgressDialog(QDialog):
    """Step 2 (LinkedIn path): shows automation progress + I Have Submitted button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LinkedIn Easy Apply")
        self.setMinimumWidth(420)
        self.setModal(False)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.status_label = QLabel("Launching browser…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.submit_btn = QPushButton("I Have Submitted")
        self.submit_btn.setProperty("primary", "true")
        self.submit_btn.hide()
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.submit_btn)
        layout.addLayout(btn_row)

    def set_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def show_manual_step(self, message: str) -> None:
        self.status_label.setText(message)
        self.submit_btn.show()

    def lock_buttons(self) -> None:
        self.submit_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Finishing up…")


class EasyApplyWorker(QThread):
    """Runs LinkedIn Easy Apply automation in a background thread."""

    progress = pyqtSignal(str)
    manual_step_required = pyqtSignal(str)
    finished_apply = pyqtSignal(str)  # "easy_apply_started" | "easy_apply_not_found" | "error"

    def __init__(self, job_url: str, profile, resume_path: str):
        super().__init__()
        self.job_url = job_url
        self.profile = profile
        self.resume_path = resume_path
        self.browser_manager = BrowserManager()

    def run(self) -> None:
        try:
            self.browser_manager.launch()
            result = attempt_easy_apply(
                self.browser_manager,
                self.job_url,
                self.profile,
                self.resume_path,
                on_progress=self.progress.emit,
                on_manual_step_required=self._handle_manual_step,
            )
            self.finished_apply.emit(result)
        except BrowserLaunchError as exc:
            self.progress.emit(f"Could not open browser: {exc}")
            self.finished_apply.emit("error")
        except Exception as exc:
            self.progress.emit(f"Unexpected error: {exc}")
            self.finished_apply.emit("error")

    def _handle_manual_step(self, message: str) -> None:
        """Emit the signal (UI thread shows button) then block until user resumes."""
        self.manual_step_required.emit(message)
        self.browser_manager._resume_event.clear()
        self.browser_manager._resume_event.wait(timeout=600)  # 10-minute max

    def resume(self) -> None:
        self.browser_manager.resume()

    def close_browser(self) -> None:
        self.browser_manager.close()

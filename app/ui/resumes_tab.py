import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.repositories import TailoredResumeRepository
from app.services.resume_service import InvalidResumeFileError, ResumeService

NO_RESUME_MESSAGE = "Please upload your resume in Settings first"


class ResumesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resume_service = ResumeService()
        self.tailored_resume_repository = TailoredResumeRepository()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.addWidget(self._build_default_resume_section(), 1)
        outer_layout.addWidget(self._build_tailored_resumes_section(), 1)

    def _build_default_resume_section(self) -> QGroupBox:
        group = QGroupBox("Default Resume")
        layout = QHBoxLayout()

        list_column = QVBoxLayout()
        self.resume_list = QListWidget()
        self.resume_list.currentItemChanged.connect(self._on_selection_changed)
        list_column.addWidget(self.resume_list)

        button_row = QHBoxLayout()
        self.set_default_button = QPushButton("Set as Default")
        self.set_default_button.clicked.connect(self._on_set_default)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(self.set_default_button)
        button_row.addWidget(self.delete_button)
        list_column.addLayout(button_row)

        preview_column = QVBoxLayout()
        preview_column.addWidget(QLabel("Preview"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_column.addWidget(self.preview_text)

        layout.addLayout(list_column, 1)
        layout.addLayout(preview_column, 2)
        group.setLayout(layout)
        return group

    def _build_tailored_resumes_section(self) -> QGroupBox:
        group = QGroupBox("Tailored Resumes")
        layout = QVBoxLayout()

        self.tailored_list = QListWidget()
        self.tailored_list.currentItemChanged.connect(self._on_tailored_selection_changed)
        layout.addWidget(self.tailored_list)

        button_row = QHBoxLayout()
        self.tailored_download_button = QPushButton("Download")
        self.tailored_download_button.clicked.connect(self._on_tailored_download)
        self.tailored_set_default_button = QPushButton("Set as Default")
        self.tailored_set_default_button.clicked.connect(self._on_tailored_set_default)
        self.tailored_delete_button = QPushButton("Delete")
        self.tailored_delete_button.clicked.connect(self._on_tailored_delete)
        button_row.addWidget(self.tailored_download_button)
        button_row.addWidget(self.tailored_set_default_button)
        button_row.addWidget(self.tailored_delete_button)
        layout.addLayout(button_row)

        group.setLayout(layout)
        return group

    def refresh(self) -> None:
        self._refresh_default_resumes()
        self._refresh_tailored_resumes()

    def _refresh_default_resumes(self) -> None:
        self.resume_list.clear()
        tailored_resume_ids = {
            tailored.resume_id for tailored in self.tailored_resume_repository.list_all()
        }
        resumes = [
            resume
            for resume in self.resume_service.list_resumes()
            if resume.id not in tailored_resume_ids
        ]

        if not resumes:
            self.preview_text.setPlainText(NO_RESUME_MESSAGE)
            self.set_default_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        self.set_default_button.setEnabled(True)
        self.delete_button.setEnabled(True)

        for resume in resumes:
            label = f"{resume.file_name}  ({resume.uploaded_at})"
            if resume.is_default:
                label += "  ★ DEFAULT"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, resume.id)
            if resume.is_default:
                item.setBackground(Qt.GlobalColor.darkGreen)
            self.resume_list.addItem(item)

        self.resume_list.setCurrentRow(0)

    def _refresh_tailored_resumes(self) -> None:
        self.tailored_list.clear()
        tailored_resumes = self.tailored_resume_repository.list_all()

        if not tailored_resumes:
            self.tailored_download_button.setEnabled(False)
            self.tailored_set_default_button.setEnabled(False)
            self.tailored_delete_button.setEnabled(False)
            return

        self.tailored_download_button.setEnabled(True)
        self.tailored_set_default_button.setEnabled(True)
        self.tailored_delete_button.setEnabled(True)

        default_resume = self.resume_service.get_default_resume()
        default_resume_id = default_resume.id if default_resume else None

        for tailored in tailored_resumes:
            score_text = f"score {tailored.score}" if tailored.score is not None else "unscored"
            label = f"{tailored.company} — {tailored.job_title}  ({score_text}, {tailored.created_at})"
            if tailored.resume_id == default_resume_id:
                label += "  ★ DEFAULT"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tailored.id)
            self.tailored_list.addItem(item)

    def _selected_resume_id(self) -> int | None:
        item = self.resume_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_tailored_resume_id(self) -> int | None:
        item = self.tailored_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection_changed(self) -> None:
        resume_id = self._selected_resume_id()
        if resume_id is None:
            self.preview_text.clear()
            return

        resumes = {resume.id: resume for resume in self.resume_service.list_resumes()}
        resume = resumes.get(resume_id)
        if resume is None:
            return

        try:
            text = self.resume_service.get_resume_text(resume.file_path)
        except InvalidResumeFileError as error:
            self.preview_text.setPlainText(str(error))
            return

        self.preview_text.setPlainText(text or "(This resume has no extractable text.)")

    def _on_tailored_selection_changed(self) -> None:
        tailored_id = self._selected_tailored_resume_id()
        if tailored_id is None:
            return
        tailored = self.tailored_resume_repository.get_by_id(tailored_id)
        if tailored is not None:
            self.preview_text.setPlainText(tailored.tailored_text)

    def _on_set_default(self) -> None:
        resume_id = self._selected_resume_id()
        if resume_id is None:
            return
        self.resume_service.set_default_resume(resume_id)
        self.refresh()

    def _on_delete(self) -> None:
        resume_id = self._selected_resume_id()
        if resume_id is None:
            return

        confirmation = QMessageBox.question(
            self,
            "Delete Resume",
            "Are you sure you want to delete this resume? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self.resume_service.delete_resume(resume_id)
        self.refresh()

    def _on_tailored_download(self) -> None:
        tailored_id = self._selected_tailored_resume_id()
        if tailored_id is None:
            return
        tailored = self.tailored_resume_repository.get_by_id(tailored_id)
        if tailored is None:
            return

        target, _ = QFileDialog.getSaveFileName(
            self, "Save Resume As", tailored.file_name, "Word Documents (*.docx)"
        )
        if target:
            shutil.copy2(tailored.file_path, target)

    def _on_tailored_set_default(self) -> None:
        tailored_id = self._selected_tailored_resume_id()
        if tailored_id is None:
            return
        tailored = self.tailored_resume_repository.get_by_id(tailored_id)
        if tailored is None or tailored.resume_id is None:
            return

        self.resume_service.set_default_resume(tailored.resume_id)
        self.refresh()

    def _on_tailored_delete(self) -> None:
        tailored_id = self._selected_tailored_resume_id()
        if tailored_id is None:
            return

        confirmation = QMessageBox.question(
            self,
            "Delete Tailored Resume",
            "Are you sure you want to delete this tailored resume? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        tailored = self.tailored_resume_repository.get_by_id(tailored_id)
        if tailored is not None and tailored.resume_id is not None:
            self.resume_service.delete_resume(tailored.resume_id)
        self.tailored_resume_repository.delete(tailored_id)
        self.refresh()

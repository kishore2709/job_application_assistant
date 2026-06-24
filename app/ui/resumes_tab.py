from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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

from app.services.resume_service import InvalidResumeFileError, ResumeService

NO_RESUME_MESSAGE = "Please upload your resume in Settings first"


class ResumesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resume_service = ResumeService()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)

        list_column = QVBoxLayout()
        list_column.addWidget(QLabel("Uploaded Resumes"))

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

    def refresh(self) -> None:
        self.resume_list.clear()
        resumes = self.resume_service.list_resumes()

        if not resumes:
            self.preview_text.setPlainText(NO_RESUME_MESSAGE)
            self.set_default_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

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

    def _selected_resume_id(self) -> int | None:
        item = self.resume_list.currentItem()
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

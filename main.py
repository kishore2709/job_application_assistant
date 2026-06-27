import sys

from dotenv import load_dotenv
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from app.db.database import init_db
from app.db.repositories import BlacklistRepository
from app.ui.main_window import MainWindow
from app.utils.file_utils import ensure_app_directories


def _make_splash() -> QSplashScreen:
    pix = QPixmap(400, 160)
    pix.fill(QColor("#0D1117"))
    painter = QPainter(pix)
    painter.setFont(QFont("Arial", 24, QFont.Weight.Bold))
    painter.setPen(QColor("#E6EDF3"))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "Job Hunt Assistant")
    painter.end()
    return QSplashScreen(pix)


def main() -> None:
    load_dotenv()
    ensure_app_directories()

    app = QApplication(sys.argv)
    app.setApplicationName("Job Hunt Assistant")
    app.setQuitOnLastWindowClosed(False)  # keep running in tray when window is closed

    splash = _make_splash()
    splash.show()
    app.processEvents()

    init_db()
    BlacklistRepository().seed_defaults_if_empty()
    BlacklistRepository().seed_additional_defaults()

    window = MainWindow()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

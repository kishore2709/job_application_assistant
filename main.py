import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from app.db.database import init_db
from app.db.repositories import BlacklistRepository
from app.ui.main_window import MainWindow
from app.utils.file_utils import ensure_app_directories


def main() -> None:
    load_dotenv()
    ensure_app_directories()
    init_db()
    BlacklistRepository().seed_defaults_if_empty()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

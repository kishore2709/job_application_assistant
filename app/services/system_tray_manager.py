from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def _make_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#2F81F7"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont("Arial", size // 3, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "JH")
    painter.end()
    return QIcon(pixmap)


class SystemTrayManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self._icon = _make_icon()
        self.tray = QSystemTrayIcon(self._icon, main_window)
        self._followups_action = None
        self._build_menu()
        self.tray.activated.connect(self._on_activated)
        self.tray.setVisible(True)

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.addAction("Open Job Hunt Assistant", self._show_main)
        menu.addSeparator()
        self._followups_action = menu.addAction("No overdue follow-ups", self._show_tracker)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(menu)

    def update_followup_count(self, count: int) -> None:
        if self._followups_action is None:
            return
        if count:
            self._followups_action.setText(f"Follow-ups: {count} overdue")
        else:
            self._followups_action.setText("No overdue follow-ups")

    def show_notification(self, title: str, message: str) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def _show_main(self) -> None:
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _show_tracker(self) -> None:
        self._show_main()
        self.main_window.tabs.setCurrentIndex(self.main_window.tracker_tab_index)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_main()

    def _quit(self) -> None:
        from PyQt6.QtWidgets import QApplication
        self.tray.setVisible(False)
        QApplication.quit()

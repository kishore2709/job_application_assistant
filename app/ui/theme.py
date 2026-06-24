DARK_THEME = {
    "background": "#0D1117",
    "surface": "#161B22",
    "card": "#1C2128",
    "border": "#30363D",
    "primary": "#2F81F7",
    "primary_hover": "#388BFD",
    "text": "#E6EDF3",
    "subtext": "#7D8590",
    "muted": "#484F58",
    "button_primary": "#238636",
    "button_primary_hover": "#2EA043",
    "button_secondary": "#21262D",
    "button_secondary_hover": "#30363D",
    "table_row_hover": "#1C2128",
    "table_row_selected": "#1F3148",
    "table_header": "#161B22",
    "scrollbar": "#30363D",
    "scrollbar_hover": "#484F58",
}

LIGHT_THEME = {
    "background": "#FFFFFF",
    "surface": "#F6F8FA",
    "card": "#FFFFFF",
    "border": "#D0D7DE",
    "primary": "#0969DA",
    "primary_hover": "#0969DA",
    "text": "#1F2328",
    "subtext": "#636C76",
    "muted": "#8C959F",
    "button_primary": "#1F883D",
    "button_primary_hover": "#1A7F37",
    "button_secondary": "#F6F8FA",
    "button_secondary_hover": "#EAEEF2",
    "table_row_hover": "#F6F8FA",
    "table_row_selected": "#DDF4FF",
    "table_header": "#F6F8FA",
    "scrollbar": "#D0D7DE",
    "scrollbar_hover": "#AFB8C1",
}

# Score badge colors — kept separate from the theme dicts since they're
# semantic (score quality), not theme-dependent; same in both themes.
SCORE_COLORS = {
    "high": ("#1A7F37", "#3FB950"),  # 90+
    "medium": ("#9E6A03", "#D29922"),  # 70-89
    "low": ("#6E1C1C", "#F85149"),  # below 70
}


def build_stylesheet(theme_name: str) -> str:
    """Builds the app-wide QSS for the given theme ("dark" or "light").

    Note: Qt's stylesheet engine has no `transition`/animation support, so
    the "smooth 200ms theme transition" from the design spec isn't achievable
    purely via QSS — switching themes is an instant swap, not a fade.
    """
    colors = LIGHT_THEME if theme_name == "light" else DARK_THEME

    return f"""
QWidget {{
    background-color: {colors['background']};
    color: {colors['text']};
    font-size: 14px;
}}
QMainWindow, QTabWidget::pane {{
    background-color: {colors['background']};
    border: 1px solid {colors['border']};
}}
QTabBar::tab {{
    background: {colors['surface']};
    color: {colors['subtext']};
    padding: 8px 16px;
    border: 1px solid {colors['border']};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background: {colors['card']};
    color: {colors['text']};
    border-bottom: 3px solid {colors['primary']};
}}
QTabBar::tab:hover {{
    background: {colors['card']};
}}
QGroupBox {{
    background-color: {colors['card']};
    border: 1px solid {colors['border']};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px 0 3px;
    color: {colors['primary']};
    border-left: 3px solid {colors['primary']};
}}
QGroupBox[sectionStyle="minor"]::title {{
    color: {colors['subtext']};
    font-size: 10px;
    font-weight: normal;
    border-left: none;
    padding-left: 6px;
}}
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTextEdit, QListWidget {{
    background-color: {colors['card']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 5px;
    color: {colors['text']};
}}
QPushButton {{
    background-color: {colors['button_secondary']};
    border: 1px solid {colors['border']};
    border-radius: 6px;
    padding: 6px 14px;
    color: {colors['text']};
}}
QPushButton:hover {{
    background-color: {colors['button_secondary_hover']};
}}
QPushButton:pressed {{
    background-color: {colors['border']};
}}
QPushButton[primary="true"] {{
    background-color: {colors['button_primary']};
    border: 1px solid {colors['button_primary']};
    color: #ffffff;
    font-weight: bold;
}}
QPushButton[primary="true"]:hover {{
    background-color: {colors['button_primary_hover']};
}}
QTableWidget {{
    background-color: {colors['surface']};
    border: 1px solid {colors['border']};
    border-radius: 8px;
    gridline-color: {colors['border']};
}}
QTableWidget::item:hover {{
    background-color: {colors['table_row_hover']};
}}
QTableWidget::item:selected {{
    background-color: {colors['table_row_selected']};
    color: {colors['text']};
}}
QHeaderView::section {{
    background-color: {colors['table_header']};
    color: {colors['subtext']};
    padding: 6px;
    border: 1px solid {colors['border']};
}}
QProgressBar {{
    border: 1px solid {colors['border']};
    border-radius: 8px;
    background-color: {colors['card']};
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {colors['primary']};
    border-radius: 8px;
}}
QLabel {{
    color: {colors['text']};
}}
QScrollArea {{
    border: none;
}}
QSplitter::handle {{
    background-color: {colors['border']};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {colors['surface']};
    border: none;
    width: 12px;
    height: 12px;
    margin: 0px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {colors['scrollbar']};
    border-radius: 6px;
    min-height: 20px;
    min-width: 20px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {colors['scrollbar_hover']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
"""

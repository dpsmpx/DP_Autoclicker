"""Тёмная «стеклянная» тема оформления."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str = "#101219"
    surface: str = "#171A23"
    surface_alt: str = "#1E2230"
    surface_hi: str = "#262B3B"
    border: str = "#2C3244"
    border_soft: str = "#232839"
    text: str = "#E8EBF5"
    muted: str = "#98A1B8"
    faint: str = "#6C7590"
    accent: str = "#5B8CFF"
    success: str = "#4ED6A1"
    warning: str = "#FFC46B"
    danger: str = "#FF6B7A"
    purple: str = "#B48CFF"

    def with_accent(self, accent: str) -> "Palette":
        return Palette(**{**self.__dict__, "accent": accent})


PALETTE = Palette()

#: цвета для точек — по умолчанию раздаются по кругу
POINT_COLORS = (
    "#5B8CFF", "#4ED6A1", "#FFC46B", "#FF6B7A",
    "#B48CFF", "#5BD6E0", "#F58CC8", "#9FD356",
)

#: цвета блоков в визуальном конструкторе по типу инструкции
BLOCK_COLORS = {
    "action": "#5B8CFF",
    "wait": "#5BD6E0",
    "loop": "#B48CFF",
    "branch": "#FFC46B",
    "flow": "#FF6B7A",
    "note": "#6C7590",
}


def rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def stylesheet(palette: Palette = PALETTE) -> str:
    """Единая таблица стилей приложения."""
    p = palette
    return f"""
    * {{
        font-family: "Segoe UI", "Inter", "SF Pro Text", "Noto Sans", sans-serif;
        font-size: 13px;
        color: {p.text};
        outline: none;
    }}
    QWidget#Root {{ background: transparent; }}

    QLabel[role="title"]    {{ font-size: 15px; font-weight: 600; }}
    QLabel[role="section"]  {{ font-size: 11px; font-weight: 700; color: {p.faint};
                               letter-spacing: 1px; text-transform: uppercase; }}
    QLabel[role="muted"]    {{ color: {p.muted}; }}
    QLabel[role="hint"]     {{ color: {p.faint}; font-size: 12px; }}
    QLabel[role="value"]    {{ color: {p.accent}; font-weight: 600; }}
    QLabel[role="mono"]     {{ font-family: "JetBrains Mono", "Cascadia Mono", "Consolas",
                               "DejaVu Sans Mono", monospace; }}

    QFrame#Card {{
        background: {p.surface};
        border: 1px solid {p.border_soft};
        border-radius: 12px;
    }}
    QFrame#Divider {{ background: {p.border_soft}; border: none; max-height: 1px; }}

    QPushButton {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 9px;
        padding: 7px 14px;
        color: {p.text};
    }}
    QPushButton:hover  {{ background: {p.surface_hi}; border-color: {rgba(p.accent, 0.45)}; }}
    QPushButton:pressed {{ background: {p.border}; }}
    QPushButton:disabled {{ color: {p.faint}; background: {p.surface}; border-color: {p.border_soft}; }}
    QPushButton[variant="primary"] {{
        background: {p.accent}; border: none; color: #0B1020; font-weight: 650;
    }}
    QPushButton[variant="primary"]:hover  {{ background: {rgba(p.accent, 0.85)}; }}
    QPushButton[variant="danger"] {{ background: {rgba(p.danger, 0.16)};
        border-color: {rgba(p.danger, 0.5)}; color: {p.danger}; }}
    QPushButton[variant="danger"]:hover {{ background: {rgba(p.danger, 0.26)}; }}
    QPushButton[variant="success"] {{ background: {p.success}; border: none;
        color: #06261B; font-weight: 650; }}
    QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent;
        color: {p.muted}; padding: 5px 8px; }}
    QPushButton[variant="ghost"]:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton:checked {{ border-color: {p.accent}; color: {p.accent}; }}

    QToolButton {{ background: transparent; border: 1px solid transparent;
        border-radius: 8px; padding: 4px; }}
    QToolButton:hover {{ background: {p.surface_hi}; }}
    QToolButton:checked {{ background: {rgba(p.accent, 0.18)}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {p.bg};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px 9px;
        selection-background-color: {rgba(p.accent, 0.45)};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {p.accent}; }}
    QLineEdit[state="error"], QPlainTextEdit[state="error"] {{ border-color: {p.danger}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_alt}; border: 1px solid {p.border};
        border-radius: 8px; selection-background-color: {rgba(p.accent, 0.28)};
        padding: 4px;
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 14px; border: none;
        background: transparent; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid {p.border}; background: {p.bg};
    }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
    QCheckBox::indicator:disabled {{ border-color: {p.border_soft}; }}

    QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
        background: {p.text}; border: 2px solid {p.accent};
    }}
    QSlider::handle:horizontal:disabled {{ background: {p.faint}; border-color: {p.border}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QTreeView::branch {{ background: transparent; }}

    QPushButton[nav="1"] {{
        background: transparent; border: 1px solid transparent;
        padding: 5px 2px; font-size: 12px; color: {p.muted};
    }}
    QPushButton[nav="1"]:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton[nav="1"]:checked {{
        background: {rgba(p.accent, 0.16)}; border-color: {rgba(p.accent, 0.45)};
        color: {p.accent};
    }}

    QTreeWidget, QListWidget, QTableWidget {{
        background: {p.bg}; border: 1px solid {p.border_soft};
        border-radius: 10px; padding: 4px;
        alternate-background-color: {p.surface};
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 5px 4px; border-radius: 6px; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {rgba(p.accent, 0.22)}; color: {p.text};
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {p.surface_alt}; }}
    QHeaderView::section {{
        background: {p.surface}; color: {p.muted}; border: none;
        border-bottom: 1px solid {p.border_soft}; padding: 6px;
    }}

    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.faint}; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 28px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QToolTip {{
        background: {p.surface_hi}; color: {p.text};
        border: 1px solid {p.border}; border-radius: 7px; padding: 5px 8px;
    }}
    QMenu {{ background: {p.surface_alt}; border: 1px solid {p.border};
        border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {rgba(p.accent, 0.25)}; }}
    QMenu::separator {{ height: 1px; background: {p.border_soft}; margin: 5px 8px; }}

    QSplitter::handle {{ background: transparent; }}
    QProgressBar {{ background: {p.bg}; border: 1px solid {p.border};
        border-radius: 7px; text-align: center; height: 14px; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 6px; }}
    """

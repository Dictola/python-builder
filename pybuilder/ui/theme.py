"""Thèmes sombre et clair de l'interface (feuille de style Qt)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """Jeu de couleurs d'un thème."""

    name: str
    bg: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    error: str
    console_bg: str


DARK = Palette(
    name="dark",
    bg="#0d1117",
    surface="#151b24",
    surface_alt="#1b2330",
    surface_hover="#212b3a",
    border="#262e3b",
    border_strong="#38424f",
    text="#e6edf5",
    muted="#8b98ab",
    accent="#4f8cff",
    accent_hover="#6ba0ff",
    accent_text="#ffffff",
    success="#3fb950",
    warning="#d29922",
    error="#f85149",
    console_bg="#0a0e14",
)

LIGHT = Palette(
    name="light",
    bg="#f2f5f9",
    surface="#ffffff",
    surface_alt="#f7f9fc",
    surface_hover="#eef2f8",
    border="#dde4ed",
    border_strong="#c3cede",
    text="#131920",
    muted="#5d6b7c",
    accent="#2f6fe4",
    accent_hover="#1f5ecf",
    accent_text="#ffffff",
    success="#1a7f37",
    warning="#9a6700",
    error="#cf222e",
    console_bg="#0f141c",
)

THEMES = {"dark": DARK, "light": LIGHT}


def palette(name: str) -> Palette:
    return THEMES.get(name, DARK)


def stylesheet(colors: Palette, check_icon: str = "", caret: str = "") -> str:
    """Feuille de style complète de l'application.

    `check_icon` est le chemin d'une image de coche ; Qt ne sait pas dessiner de
    coche en CSS, il faut lui fournir un fichier.
    """
    check = f"image: url({check_icon});" if check_icon else "image: none;"
    arrow = (
        f"image: url({caret}); width: 12px; height: 12px; margin-right: 8px;"
        if caret
        else "image: none;"
    )
    return f"""
* {{
    font-family: "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {colors.text};
    background: transparent;
}}

QMainWindow, QDialog, #Root {{
    background: {colors.bg};
}}

QToolTip {{
    background: {colors.surface_alt};
    color: {colors.text};
    border: 1px solid {colors.border_strong};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------- En-tête ---------- */
#Header {{
    background: {colors.surface};
    border-bottom: 1px solid {colors.border};
}}
#AppTitle {{
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
#AppSubtitle {{
    color: {colors.muted};
    font-size: 12px;
}}
#Logo {{
    background: {colors.accent};
    color: {colors.accent_text};
    border-radius: 10px;
    font-size: 20px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}}

/* ---------- Navigation ---------- */
#Nav {{
    background: {colors.surface};
    border: none;
    border-right: 1px solid {colors.border};
    outline: none;
    padding: 10px 8px;
}}
#Nav::item {{
    color: {colors.muted};
    border-radius: 8px;
    padding: 10px 12px;
    margin: 2px 4px;
}}
#Nav::item:hover {{
    background: {colors.surface_hover};
    color: {colors.text};
}}
#Nav::item:selected {{
    background: {colors.surface_alt};
    color: {colors.text};
    border-left: 3px solid {colors.accent};
}}

/* ---------- Cartes ---------- */
#Card {{
    background: {colors.surface};
    border: 1px solid {colors.border};
    border-radius: 12px;
}}
#CardTitle {{
    font-size: 14px;
    font-weight: 600;
}}
#CardSubtitle, .muted, #Muted {{
    color: {colors.muted};
    font-size: 12px;
}}
#SectionTitle {{
    font-size: 20px;
    font-weight: 600;
}}
#SectionHint {{
    color: {colors.muted};
}}
#FieldLabel {{
    color: {colors.muted};
    font-size: 12px;
}}

/* ---------- Zone de dépôt ---------- */
#DropZone {{
    background: {colors.surface_alt};
    border: 2px dashed {colors.border_strong};
    border-radius: 12px;
}}
#DropZone[hover="true"] {{
    border-color: {colors.accent};
    background: {colors.surface_hover};
}}
#DropTitle {{
    font-size: 15px;
    font-weight: 600;
}}

/* ---------- Champs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget {{
    background: {colors.surface_alt};
    border: 1px solid {colors.border};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {colors.accent};
    selection-color: {colors.accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus, QListWidget:focus {{
    border-color: {colors.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {colors.muted};
    background: {colors.surface};
}}
QLineEdit[readOnly="true"] {{
    color: {colors.muted};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    {arrow}
}}
QComboBox QAbstractItemView {{
    background: {colors.surface_alt};
    border: 1px solid {colors.border_strong};
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: {colors.accent};
    selection-color: {colors.accent_text};
}}
QListWidget::item {{
    padding: 5px 6px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background: {colors.accent};
    color: {colors.accent_text};
}}

/* ---------- Boutons ---------- */
QPushButton {{
    background: {colors.surface_alt};
    border: 1px solid {colors.border_strong};
    border-radius: 8px;
    padding: 8px 14px;
    color: {colors.text};
}}
QPushButton:hover {{
    background: {colors.surface_hover};
    border-color: {colors.accent};
}}
QPushButton:pressed {{
    background: {colors.surface};
}}
QPushButton:disabled {{
    color: {colors.muted};
    border-color: {colors.border};
    background: {colors.surface};
}}
QPushButton#Primary {{
    background: {colors.accent};
    border: 1px solid {colors.accent};
    color: {colors.accent_text};
    font-weight: 600;
    padding: 11px 22px;
}}
QPushButton#Primary:hover {{
    background: {colors.accent_hover};
    border-color: {colors.accent_hover};
}}
QPushButton#Primary:disabled {{
    background: {colors.border};
    border-color: {colors.border};
    color: {colors.muted};
}}
QPushButton#Danger {{
    border-color: {colors.error};
    color: {colors.error};
}}
QPushButton#Danger:hover {{
    background: {colors.error};
    color: #ffffff;
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {colors.muted};
    padding: 6px 10px;
}}
QPushButton#Ghost:hover {{
    background: {colors.surface_hover};
    color: {colors.text};
}}
QPushButton#Chip {{
    background: transparent;
    border: 1px solid {colors.border_strong};
    border-radius: 14px;
    padding: 5px 12px;
    color: {colors.muted};
}}
QPushButton#Chip:checked {{
    background: {colors.accent};
    border-color: {colors.accent};
    color: {colors.accent_text};
}}

/* ---------- Cases et boutons radio ---------- */
QCheckBox, QRadioButton {{
    spacing: 9px;
    padding: 3px 0;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {colors.border_strong};
    background: {colors.surface_alt};
}}
QCheckBox::indicator {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {colors.accent};
}}
QCheckBox::indicator:checked {{
    background: {colors.accent};
    border-color: {colors.accent};
    {check}
}}
QRadioButton::indicator:checked {{
    /* Un dégradé radial dessine la pastille : une bordure épaisse ferait perdre l'arrondi. */
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0.45 {colors.accent}, stop:0.5 {colors.surface_alt});
    border: 1px solid {colors.accent};
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {colors.muted};
}}

/* ---------- Onglets ---------- */
QTabWidget::pane {{
    border: 1px solid {colors.border};
    border-radius: 10px;
    top: -1px;
    background: {colors.surface};
}}
QTabBar::tab {{
    background: transparent;
    color: {colors.muted};
    padding: 8px 16px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    color: {colors.text};
    background: {colors.surface};
    border-color: {colors.border};
    border-bottom-color: {colors.surface};
}}
QTabBar::tab:hover:!selected {{
    color: {colors.text};
}}

/* ---------- Console ---------- */
#Console {{
    background: {colors.console_bg};
    border: 1px solid {colors.border};
    border-radius: 10px;
    font-family: "Cascadia Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    color: #c9d4e3;
    padding: 10px;
}}
#SpecView {{
    font-family: "Cascadia Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}

/* ---------- Barre de progression ---------- */
QProgressBar {{
    background: {colors.surface_alt};
    border: 1px solid {colors.border};
    border-radius: 7px;
    height: 14px;
    text-align: center;
    color: {colors.muted};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: {colors.accent};
    border-radius: 6px;
}}

/* ---------- Barres de défilement ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {colors.border_strong};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {colors.muted};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {colors.border_strong};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}

/* ---------- Divers ---------- */
QSplitter::handle {{
    background: {colors.border};
    height: 1px;
}}
#Separator {{
    background: {colors.border};
    max-height: 1px;
    border: none;
}}
#Footer {{
    background: {colors.surface};
    border-top: 1px solid {colors.border};
}}
#StatusLabel {{
    color: {colors.muted};
}}
QMenu {{
    background: {colors.surface_alt};
    border: 1px solid {colors.border_strong};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px 7px 14px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {colors.accent};
    color: {colors.accent_text};
}}
QMenu::separator {{
    height: 1px;
    background: {colors.border};
    margin: 5px 8px;
}}
"""

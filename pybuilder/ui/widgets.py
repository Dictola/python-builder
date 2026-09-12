"""Composants réutilisables de l'interface PyBuilder."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

#: Couleurs d'affichage du journal selon le niveau du message.
LOG_COLORS = {
    "info": "#c9d4e3",
    "muted": "#7b8798",
    "warn": "#d29922",
    "error": "#f85149",
    "success": "#3fb950",
    "accent": "#4f8cff",
}

#: Pastille colorée précédant chaque constat de l'analyse.
FINDING_STYLE = {
    "ok": ("#3fb950", "✓"),
    "info": ("#4f8cff", "i"),
    "warn": ("#d29922", "!"),
    "error": ("#f85149", "✕"),
}


def muted(text: str) -> QLabel:
    """Petit texte explicatif gris.

    Le format est forcé en texte brut : sans cela, un mot comme « <script> » serait
    interprété par Qt comme une balise HTML et le reste du texte disparaîtrait.
    """
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class ElidedLabel(QLabel):
    """QLabel qui tronque proprement les textes trop longs (chemins de fichiers)."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 - API Qt
        self._full = text
        self.setToolTip(text)
        super().setText(text)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width() - 2)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(self.alignment()), elided)


class SectionHeader(QWidget):
    """Titre de page avec sa phrase d'explication."""

    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)
        if hint:
            subtitle = QLabel(hint)
            subtitle.setObjectName("SectionHint")
            subtitle.setWordWrap(True)
            subtitle.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(subtitle)


class Card(QFrame):
    """Bloc encadré regroupant des réglages liés."""

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(12)

        if title:
            header = QLabel(title)
            header.setObjectName("CardTitle")
            header.setTextFormat(Qt.TextFormat.PlainText)
            outer.addWidget(header)
        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("CardSubtitle")
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.PlainText)
            outer.addWidget(note)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)

    def add_field(self, label: str, widget: QWidget, hint: str = "") -> QWidget:
        """Ajoute un champ étiqueté (libellé au-dessus, aide en dessous)."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        if label:
            caption = QLabel(label)
            caption.setObjectName("FieldLabel")
            caption.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(caption)
        layout.addWidget(widget)
        if hint:
            layout.addWidget(muted(hint))
        self.body.addWidget(holder)
        return widget

    def add_row(self, *widgets: QWidget, spacing: int = 10) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(spacing)
        for widget in widgets:
            row.addWidget(widget)
        self.body.addLayout(row)
        return row


class DropZone(QFrame):
    """Zone de dépôt (ou de sélection) du script Python à convertir."""

    selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("hover", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title = QLabel("Glissez votre script Python ici")
        self.title.setObjectName("DropTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.detail = QLabel("ou cliquez pour parcourir — fichiers .py et .pyw")
        self.detail.setObjectName("Muted")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.title)
        layout.addWidget(self.detail)

    def show_file(self, path: str) -> None:
        target = Path(path)
        self.title.setText(target.name)
        self.detail.setText(str(target.parent))

    def clear_file(self) -> None:
        self.title.setText("Glissez votre script Python ici")
        self.detail.setText("ou cliquez pour parcourir — fichiers .py et .pyw")

    def _repaint(self, hover: bool) -> None:
        self.setProperty("hover", "true" if hover else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    # --- Interactions ---------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choisir le script Python", "", "Scripts Python (*.py *.pyw);;Tous les fichiers (*)"
            )
            if path:
                self.selected.emit(path)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self._python_file(event) is not None:
            event.acceptProposedAction()
            self._repaint(True)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - API Qt
        self._repaint(False)

    def dropEvent(self, event) -> None:  # noqa: N802 - API Qt
        path = self._python_file(event)
        self._repaint(False)
        if path:
            event.acceptProposedAction()
            self.selected.emit(path)

    @staticmethod
    def _python_file(event) -> str | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            local = url.toLocalFile()
            if local.lower().endswith((".py", ".pyw")):
                return local
        return None


class PathEdit(QWidget):
    """Champ de chemin avec bouton « Parcourir » (fichier, dossier ou enregistrement)."""

    changed = Signal(str)

    def __init__(
        self,
        mode: str = "open_file",
        placeholder: str = "",
        filters: str = "Tous les fichiers (*)",
        caption: str = "Choisir",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.filters = filters
        self.caption = caption

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        self.button = QPushButton("Parcourir…")
        self.button.setFixedWidth(110)
        self.button.clicked.connect(self._browse)

        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:  # noqa: N802 - cohérence avec Qt
        self.edit.setText(value or "")

    def _browse(self) -> None:
        start = self.text() or str(Path.home())
        if self.mode == "open_dir":
            path = QFileDialog.getExistingDirectory(self, self.caption, start)
        elif self.mode == "save_file":
            path, _ = QFileDialog.getSaveFileName(self, self.caption, start, self.filters)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.caption, start, self.filters)
        if path:
            self.setText(path)


class ListEditor(QWidget):
    """Liste modifiable de valeurs texte (imports cachés, exclusions…)."""

    changed = Signal()

    def __init__(self, prompt: str = "Valeur", height: int = 110, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prompt = prompt

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.list = QListWidget()
        self.list.setFixedHeight(height)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self.buttons_layout = buttons = QVBoxLayout()
        buttons.setSpacing(6)
        self.add_button = QPushButton("Ajouter")
        self.remove_button = QPushButton("Retirer")
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)

        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)

    def values(self) -> list[str]:
        return [self.list.item(row).text() for row in range(self.list.count())]

    def set_values(self, values) -> None:
        self.list.clear()
        for value in values or []:
            self.list.addItem(str(value))

    def append(self, value: str) -> None:
        if value and value not in self.values():
            self.list.addItem(value)
            self.changed.emit()

    def extend(self, values) -> None:
        added = False
        for value in values or []:
            if value and value not in self.values():
                self.list.addItem(str(value))
                added = True
        if added:
            self.changed.emit()

    def _add(self) -> None:
        value, ok = QInputDialog.getText(self, self.prompt, f"{self.prompt} :")
        if ok and value.strip():
            self.append(value.strip())

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self.changed.emit()


class DataPairEditor(ListEditor):
    """Liste de ressources à embarquer : couple (fichier source, dossier cible)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(prompt="Ressource", height=130, parent=parent)
        self.add_button.setText("Fichier…")
        self.folder_button = QPushButton("Dossier…")
        self.folder_button.clicked.connect(self._add_folder)
        self.buttons_layout.insertWidget(1, self.folder_button)

    def pairs(self) -> list[list[str]]:
        result: list[list[str]] = []
        for text in self.values():
            source, _, destination = text.partition(" → ")
            result.append([source, destination or "."])
        return result

    def set_pairs(self, pairs) -> None:
        self.set_values([f"{source} → {destination or '.'}" for source, destination in pairs or []])

    def _add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Fichiers à embarquer dans l'exe", str(Path.home()))
        for path in paths:
            self._append_pair(path)

    def _add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Dossier à embarquer dans l'exe", str(Path.home()))
        if path:
            self._append_pair(path, default=Path(path).name)

    def _append_pair(self, path: str, default: str = ".") -> None:
        destination, ok = QInputDialog.getText(
            self,
            "Destination dans l'exe",
            f"Dossier de destination pour « {Path(path).name} » :\n(« . » = racine de l'exe)",
            text=default,
        )
        if ok:
            self.append(f"{path} → {destination.strip() or '.'}")


class ColorPicker(QPushButton):
    """Bouton affichant une pastille de couleur et ouvrant le sélecteur Qt."""

    colorChanged = Signal(str)

    def __init__(self, color: str = "#4f8cff", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.clicked.connect(self._pick)
        self.setFixedWidth(140)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, value: str) -> None:
        if value and QColor.isValidColorName(value):
            self._color = value
            self._refresh()

    def _refresh(self) -> None:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(self._color))
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(14, 14))
        self.setText(self._color.upper())

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, "Couleur d'accent")
        if chosen.isValid():
            self._color = chosen.name()
            self._refresh()
            self.colorChanged.emit(self._color)


class FindingRow(QFrame):
    """Une ligne de résultat d'analyse : pastille, titre, explication."""

    def __init__(self, level: str, title: str, detail: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        color, glyph = FINDING_STYLE.get(level, FINDING_STYLE["info"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(11)

        bullet = QLabel(glyph)
        bullet.setFixedSize(20, 20)
        bullet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bullet.setStyleSheet(
            f"background: {color}; color: #ffffff; border-radius: 10px; font-weight: 700; font-size: 11px;"
        )
        layout.addWidget(bullet, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        heading = QLabel(title)
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        font = heading.font()
        font.setWeight(QFont.Weight.DemiBold)
        heading.setFont(font)
        text_layout.addWidget(heading)
        if detail:
            text_layout.addWidget(muted(detail))
        layout.addLayout(text_layout, 1)


class LogConsole(QPlainTextEdit):
    """Journal coloré de la construction."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(6000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def log(self, text: str, level: str = "info") -> None:
        color = LOG_COLORS.get(level, LOG_COLORS["info"])
        weight = "600" if level in ("success", "error") else "400"
        self.appendHtml(
            f'<span style="color:{color}; font-weight:{weight}; white-space:pre">{html.escape(text)}</span>'
        )
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def rule(self, title: str) -> None:
        self.log("─" * 4 + f" {title} " + "─" * max(4, 62 - len(title)), "muted")


def scroll_page(content: QWidget) -> QScrollArea:
    """Enveloppe une page dans une zone défilante sans bordure."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return area

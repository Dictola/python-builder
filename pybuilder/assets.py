"""Génération des visuels de l'exécutable : splash screen PNG et icône ICO.

Tout est dessiné avec Qt : aucune dépendance supplémentaire (ni Pillow ni ImageMagick).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

#: Tailles de frames écrites dans le fichier .ico (Windows choisit la plus adaptée).
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Familles de polices essayées dans l'ordre pour le rendu du splash.
FONT_FAMILIES = ["Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial"]

SPLASH_SIZE = (520, 300)


@dataclass
class SplashInfo:
    """Image de splash générée et position du texte d'état pour PyInstaller."""

    path: Path
    width: int
    height: int
    text_pos: tuple[int, int]
    text_size: int
    text_color: str
    generated: bool = True


#: Application Qt créée à la demande hors IHM ; la référence doit survivre au GC.
_HEADLESS_APP: QGuiApplication | None = None


def _require_qt_app() -> None:
    """QPainter exige une application Qt : on en crée une hors IHM (tests, CLI)."""
    global _HEADLESS_APP
    if QGuiApplication.instance() is None:  # pragma: no cover - dépend du contexte
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _HEADLESS_APP = QGuiApplication(["pybuilder"])


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _elide(text: str, font: QFont, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


def render_splash(
    title: str,
    subtitle: str,
    accent: str = "#4f8cff",
    dark: bool = True,
    size: tuple[int, int] = SPLASH_SIZE,
) -> tuple[QImage, tuple[int, int]]:
    """Dessine le splash screen et renvoie l'image et la position du texte d'état."""
    _require_qt_app()
    width, height = size
    accent_color = QColor(accent if QColor.isValidColorName(accent) else "#4f8cff")
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    if dark:
        top, bottom = QColor("#151b26"), QColor("#0b0f16")
        title_color, sub_color, track = QColor("#f5f7fa"), QColor("#93a1b5"), QColor(255, 255, 255, 28)
        border = QColor(255, 255, 255, 34)
    else:
        top, bottom = QColor("#ffffff"), QColor("#eef1f6")
        title_color, sub_color, track = QColor("#12161d"), QColor("#5c6a7e"), QColor(0, 0, 0, 26)
        border = QColor(0, 0, 0, 38)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # Fond dégradé.
    gradient = QLinearGradient(0, 0, width * 0.35, height)
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)
    painter.fillRect(0, 0, width, height, QBrush(gradient))

    # Halo d'accent en haut à gauche.
    halo = QRadialGradient(QPointF(width * 0.16, height * 0.1), width * 0.6)
    glow = QColor(accent_color)
    glow.setAlpha(90 if dark else 60)
    halo.setColorAt(0.0, glow)
    glow_end = QColor(accent_color)
    glow_end.setAlpha(0)
    halo.setColorAt(1.0, glow_end)
    painter.fillRect(0, 0, width, height, QBrush(halo))

    margin = 38
    # Pastille avec l'initiale du programme.
    badge = QRectF(margin, margin, 56, 56)
    badge_path = QPainterPath()
    badge_path.addRoundedRect(badge, 16, 16)
    badge_gradient = QLinearGradient(badge.topLeft(), badge.bottomRight())
    badge_gradient.setColorAt(0.0, accent_color.lighter(125))
    badge_gradient.setColorAt(1.0, accent_color.darker(115))
    painter.fillPath(badge_path, QBrush(badge_gradient))

    initial = (title.strip() or "A")[0].upper()
    painter.setPen(QPen(QColor("#ffffff")))
    painter.setFont(_font(30, QFont.Weight.DemiBold))
    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, initial)

    # Titre et sous-titre.
    text_left = margin
    text_width = width - 2 * margin
    title_font = _font(34, QFont.Weight.DemiBold)
    painter.setFont(title_font)
    painter.setPen(QPen(title_color))
    title_rect = QRect(text_left, margin + 78, text_width, 46)
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     _elide(title or "Application", title_font, text_width))

    subtitle_font = _font(15)
    painter.setFont(subtitle_font)
    painter.setPen(QPen(sub_color))
    subtitle_rect = QRect(text_left, margin + 124, text_width, 24)
    painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     _elide(subtitle or "", subtitle_font, text_width))

    # Rail de progression décoratif.
    bar_y = height - margin - 26
    bar_rect = QRectF(margin, bar_y, width - 2 * margin, 5)
    bar_path = QPainterPath()
    bar_path.addRoundedRect(bar_rect, 3, 3)
    painter.fillPath(bar_path, QBrush(track))

    fill_rect = QRectF(bar_rect.left(), bar_rect.top(), bar_rect.width() * 0.42, bar_rect.height())
    fill_path = QPainterPath()
    fill_path.addRoundedRect(fill_rect, 3, 3)
    fill_gradient = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
    fill_gradient.setColorAt(0.0, accent_color)
    fill_gradient.setColorAt(1.0, accent_color.lighter(150))
    painter.fillPath(fill_path, QBrush(fill_gradient))

    # Liseré du cadre.
    painter.setPen(QPen(border, 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(0.5, 0.5, width - 1, height - 1))
    painter.end()

    text_pos = (margin, int(bar_y) - 30)
    return image, text_pos


def make_splash(
    destination: Path,
    title: str,
    subtitle: str,
    accent: str = "#4f8cff",
    dark: bool = True,
) -> SplashInfo:
    """Génère le PNG du splash et renvoie les métadonnées utiles au fichier .spec."""
    image, text_pos = render_splash(title, subtitle, accent, dark)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(destination), "PNG")
    return SplashInfo(
        path=destination,
        width=image.width(),
        height=image.height(),
        text_pos=text_pos,
        text_size=12,
        text_color="#93a1b5" if dark else "#5c6a7e",
    )


def describe_splash(image_path: Path, dark: bool = True) -> SplashInfo:
    """Décrit une image fournie par l'utilisateur (position du texte déduite de la taille)."""
    _require_qt_app()
    image = QImage(str(image_path))
    if image.isNull():
        raise ValueError(f"Image de splash illisible : {image_path}")
    margin = max(16, int(image.width() * 0.07))
    return SplashInfo(
        path=image_path,
        width=image.width(),
        height=image.height(),
        text_pos=(margin, max(10, image.height() - margin - 24)),
        text_size=12,
        text_color="#93a1b5" if dark else "#5c6a7e",
        generated=False,
    )


def render_icon(title: str, accent: str = "#4f8cff", size: int = 256) -> QImage:
    """Dessine une icône carrée avec l'initiale du programme."""
    _require_qt_app()
    accent_color = QColor(accent if QColor.isValidColorName(accent) else "#4f8cff")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    radius = size * 0.22
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, accent_color.lighter(130))
    gradient.setColorAt(1.0, accent_color.darker(125))
    painter.fillPath(path, QBrush(gradient))

    painter.setPen(QPen(QColor("#ffffff")))
    painter.setFont(_font(int(size * 0.52), QFont.Weight.DemiBold))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (title.strip() or "A")[0].upper())
    painter.end()
    return image


def write_ico(image: QImage, destination: Path, sizes: tuple[int, ...] = ICO_SIZES) -> Path:
    """Écrit un vrai fichier .ico multi-résolutions (frames PNG, compatibles Vista+)."""
    frames: list[bytes] = []
    kept: list[int] = []
    for size in sizes:
        scaled = image.scaled(
            size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        # QBuffer sans argument gère son propre QByteArray : pas de tampon libéré sous nos pieds.
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        encoded = scaled.save(buffer, "PNG")
        data = bytes(buffer.data())
        buffer.close()
        if not encoded:
            continue
        frames.append(data)
        kept.append(size)

    if not frames:
        raise RuntimeError("Impossible d'encoder les images de l'icône.")

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    directory = b""
    for size, data in zip(kept, frames):
        dimension = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset)
        offset += len(data)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + directory + b"".join(frames))
    return destination


def make_icon(destination: Path, source: str | Path | None, title: str, accent: str = "#4f8cff") -> Path:
    """Fournit une icône .ico : conversion de l'image donnée, ou icône générée."""
    _require_qt_app()
    if source:
        source = Path(source)
        if source.suffix.lower() == ".ico":
            return source
        image = QImage(str(source))
        if image.isNull():
            raise ValueError(f"Icône illisible : {source}")
    else:
        image = render_icon(title, accent)
    return write_ico(image, destination)


def _icon_cache_dir() -> Path:
    from PySide6.QtCore import QStandardPaths

    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    folder = Path(base or Path.home() / ".cache") / "pybuilder"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _stroke_icon(name: str, color: str, size: int, points: list[tuple[float, float]], width: float) -> str:
    """Dessine (et met en cache) une icône au trait : Qt ne sait pas les faire en CSS."""
    _require_qt_app()
    destination = _icon_cache_dir() / f"{name}-{color.lstrip('#')}-{size}.png"
    if destination.is_file():
        return destination.as_posix()

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(size * width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(size * points[0][0], size * points[0][1])
    for x, y in points[1:]:
        path.lineTo(size * x, size * y)
    painter.drawPath(path)
    painter.end()
    image.save(str(destination), "PNG")
    return destination.as_posix()


def checkmark_icon(color: str = "#ffffff", size: int = 16) -> str:
    """Coche blanche des cases cochées."""
    return _stroke_icon("check", color, size, [(0.24, 0.52), (0.43, 0.71), (0.77, 0.30)], 0.14)


def caret_icon(color: str = "#8b98ab", size: int = 12) -> str:
    """Chevron vers le bas des listes déroulantes."""
    return _stroke_icon("caret", color, size, [(0.25, 0.40), (0.50, 0.65), (0.75, 0.40)], 0.13)

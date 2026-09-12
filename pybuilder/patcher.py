"""Injection dans le script cible du code nécessaire à un exe PyInstaller réussi.

Le bloc injecté est délimité par des marqueurs : il est retiré puis réécrit à
chaque construction, et n'a aucun effet quand le script tourne hors exe.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .analyzer import ScriptReport
from .models import BuildConfig

BEGIN = "# >>> PyBuilder — bloc injecté automatiquement, ne pas éditer >>>"
END = "# <<< PyBuilder — fin du bloc injecté <<<"
INLINE = "# PyBuilder:auto"

#: Bindings Qt testés par le hook de fermeture du splash, par ordre de préférence.
QT_BINDINGS = ("PySide6", "PyQt6", "PySide2", "PyQt5")

_CORE = '''
import os as _pb_os
import sys as _pb_sys

PYBUILDER_FROZEN = bool(getattr(_pb_sys, "frozen", False))


class _PyBuilderSplash:
    """Pilote le splash screen PyInstaller. Sans effet quand on lance le .py."""

    _closed = False
    _module = None

    @classmethod
    def _api(cls):
        if cls._module is None:
            # Sans cette variable, le splash n'a pas démarré (exe sans splash, session
            # distante, écran indisponible) : importer pyi_splash afficherait une trace.
            if not _pb_os.environ.get("_PYI_SPLASH_IPC"):
                cls._module = False
                return None
            try:
                import pyi_splash
            except Exception:
                cls._module = False
            else:
                cls._module = pyi_splash
        return cls._module or None

    @classmethod
    def text(cls, message):
        api = cls._api()
        if api is None or cls._closed:
            return
        try:
            api.update_text(str(message))
        except Exception:
            pass

    @classmethod
    def close(cls):
        if cls._closed:
            return
        cls._closed = True
        api = cls._api()
        if api is None:
            return
        try:
            api.close()
        except Exception:
            pass


def pybuilder_splash_text(message):
    """Affiche un message d'état sur le splash screen."""
    _PyBuilderSplash.text(message)


def pybuilder_close_splash():
    """Ferme le splash screen (appelable plusieurs fois sans risque)."""
    _PyBuilderSplash.close()
'''

_RESOURCES = '''

def pybuilder_resource_path(*parts):
    """Chemin absolu d'une ressource embarquée, en mode script comme en .exe."""
    base = getattr(_pb_sys, "_MEIPASS", None)
    if base is None:
        try:
            base = _pb_os.path.dirname(_pb_os.path.abspath(__file__))
        except NameError:
            base = _pb_os.getcwd()
    return _pb_os.path.join(base, *parts)


def pybuilder_app_dir():
    """Dossier de l'exécutable (ou du script) : pour lire/écrire à côté de l'application."""
    if PYBUILDER_FROZEN:
        return _pb_os.path.dirname(_pb_os.path.abspath(_pb_sys.executable))
    try:
        return _pb_os.path.dirname(_pb_os.path.abspath(__file__))
    except NameError:
        return _pb_os.getcwd()
'''

_EXCEPTHOOK = '''

def _pb_error_log_path():
    name = "@@LOGNAME@@"
    try:
        candidate = _pb_os.path.join(pybuilder_app_dir(), name)
        with open(candidate, "a", encoding="utf-8"):
            pass
        return candidate
    except Exception:
        import tempfile
        return _pb_os.path.join(tempfile.gettempdir(), name)


def _pb_report_error(text, log_path):
    """Affiche l'erreur à l'utilisateur : boîte Qt si possible, sinon boîte Windows."""
    message = "L'application a rencontré une erreur.\\n\\nJournal : %s\\n\\n%s" % (log_path, text[-1200:])
    for binding in (@@BINDINGS@@):
        widgets = _pb_sys.modules.get(binding + ".QtWidgets")
        if widgets is None:
            continue
        try:
            if widgets.QApplication.instance() is not None:
                widgets.QMessageBox.critical(None, "@@TITLE@@", message)
                return
        except Exception:
            pass
    if _pb_sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "@@TITLE@@", 0x10)
        except Exception:
            pass


def _pb_install_excepthook():
    import traceback

    def _hook(exc_type, exc_value, exc_tb):
        pybuilder_close_splash()
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_path = _pb_error_log_path()
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("\\n===== %s =====\\n%s" % (@@DATETIME@@, text))
        except Exception:
            pass
        try:
            _pb_sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass
        if PYBUILDER_FROZEN:
            _pb_report_error(text, log_path)

    _pb_sys.excepthook = _hook


_pb_install_excepthook()
'''

_TIMEOUT = '''

def _pb_arm_splash_timeout(delay):
    """Filet de sécurité : le splash ne doit jamais rester affiché indéfiniment."""
    try:
        import threading
        timer = threading.Timer(delay, pybuilder_close_splash)
        timer.daemon = True
        timer.start()
    except Exception:
        pass


_pb_arm_splash_timeout(@@TIMEOUT@@)
'''

_MAINLOOP = '''

def _pb_hook_event_loop():
    """Ferme le splash dès que la boucle d'évènements démarre (fenêtre affichée)."""
    import inspect

    for binding in (@@BINDINGS@@):
        try:
            widgets = __import__(binding + ".QtWidgets", fromlist=["QtWidgets"])
            core = __import__(binding + ".QtCore", fromlist=["QtCore"])
        except Exception:
            continue
        patched = False
        for name in ("exec", "exec_"):
            original = getattr(widgets.QApplication, name, None)
            if original is None:
                continue

            def make(original=original, timer=core.QTimer):
                def wrapper(*args, **kwargs):
                    # singleShot(0) : le splash se ferme après le premier affichage.
                    timer.singleShot(0, pybuilder_close_splash)
                    return original(*args, **kwargs)

                return wrapper

            try:
                raw = inspect.getattr_static(widgets.QApplication, name, None)
                wrapper = make()
                setattr(widgets.QApplication, name, staticmethod(wrapper) if isinstance(raw, staticmethod) else wrapper)
                patched = True
            except Exception:
                continue
        if patched:
            return True

    try:
        import tkinter
    except Exception:
        return False
    try:
        original_loop = tkinter.Misc.mainloop

        def _pb_mainloop(self, *args, **kwargs):
            try:
                self.after(0, pybuilder_close_splash)
            except Exception:
                pybuilder_close_splash()
            return original_loop(self, *args, **kwargs)

        tkinter.Misc.mainloop = _pb_mainloop
        return True
    except Exception:
        return False


_pb_hook_event_loop()
'''

_FREEZE = '''

# multiprocessing : sans freeze_support(), chaque processus fils relance l'application.
try:
    import multiprocessing as _pb_multiprocessing

    _pb_multiprocessing.freeze_support()
except Exception:
    pass
'''


@dataclass
class PatchResult:
    """Ce qui a été écrit sur le disque et ce qu'il faudra nettoyer après la construction."""

    entry_point: Path
    original: Path
    backup: Path | None = None
    temporary: bool = False
    notes: list[str] = field(default_factory=list)


def strip_block(source: str) -> str:
    """Retire un bloc PyBuilder déjà présent (et ses lignes marquées)."""
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(BEGIN):
            inside = True
            continue
        if inside:
            if stripped.startswith(END):
                inside = False
            continue
        if stripped.endswith(INLINE):
            continue
        out.append(line)
    return "".join(out)


def build_header(config: BuildConfig, report: ScriptReport) -> str:
    """Construit le bloc à injecter en fonction des options choisies."""
    bindings = ", ".join(f'"{name}"' for name in QT_BINDINGS)
    stamp = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")

    parts = [
        BEGIN,
        f"# Généré par PyBuilder {__version__} le {stamp}.",
        "# Ce bloc est réécrit à chaque construction et reste inerte hors exécutable.",
        _CORE.strip("\n"),
    ]

    if config.add_resource_helper:
        parts.append(_RESOURCES.strip("\n"))

    if config.add_freeze_support and report.uses_multiprocessing and not report.has_main_guard:
        parts.append(_FREEZE.strip("\n"))

    if config.add_excepthook:
        block = (
            _EXCEPTHOOK.replace("@@LOGNAME@@", f"{config.exe_name}-erreurs.log")
            .replace("@@TITLE@@", config.exe_name)
            .replace("@@BINDINGS@@", bindings)
            .replace("@@DATETIME@@", '__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")')
        )
        parts.append(block.strip("\n"))

    if config.splash_enabled:
        if config.splash_strategy == "mainloop":
            parts.append(_MAINLOOP.replace("@@BINDINGS@@", bindings).strip("\n"))
        if config.splash_strategy != "manual":
            delay = max(1.0, float(config.splash_timeout))
            parts.append(_TIMEOUT.replace("@@TIMEOUT@@", f"{delay:g}").strip("\n"))

    parts.append(END)
    return "\n".join(parts) + "\n"


def patch_source(config: BuildConfig, report: ScriptReport) -> str:
    """Renvoie le code source patché, prêt à être passé à PyInstaller."""
    source = strip_block(report.source)
    if source != report.source:
        report = _reanalyze(report, source)

    lines = source.splitlines()
    insertions: list[tuple[int, list[str]]] = []

    # Fermeture du splash à la fin des imports.
    if config.splash_enabled and config.splash_strategy == "imports":
        insertions.append((report.last_import_line, [f"pybuilder_close_splash()  {INLINE}"]))

    # freeze_support() doit être la première instruction du bloc __main__.
    if config.add_freeze_support and report.uses_multiprocessing and report.has_main_guard:
        indent = report.main_guard_indent
        insertions.append(
            (report.main_guard_body_line - 1, [f'{indent}__import__("multiprocessing").freeze_support()  {INLINE}'])
        )

    header = build_header(config, report).splitlines()
    insertions.append((report.insertion_line, ["", *header, ""]))

    # Insertion des plus grandes lignes vers les plus petites : les index restent valides.
    for line_no, block in sorted(insertions, key=lambda item: item[0], reverse=True):
        index = max(0, min(line_no, len(lines)))
        lines[index:index] = block

    return "\n".join(lines) + "\n"


def _reanalyze(report: ScriptReport, source: str) -> ScriptReport:
    """Recalcule les numéros de ligne sur une source nettoyée d'un ancien bloc injecté."""
    import ast
    import copy

    from .analyzer import _compute_insertion, _scan_tree

    fresh = copy.copy(report)
    fresh.source = source
    fresh.lines = source.splitlines()
    fresh.imports = set()
    fresh.last_import_line = 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return fresh
    _scan_tree(tree, fresh)
    _compute_insertion(tree, fresh)
    return fresh


def write_patched(config: BuildConfig, report: ScriptReport, workdir: Path) -> PatchResult:
    """Écrit le script patché et renvoie le point d'entrée à donner à PyInstaller.

    En mode « copie », le fichier patché est écrit *à côté* de l'original afin que
    les imports de modules voisins continuent de fonctionner.
    """
    original = Path(config.script)
    patched = patch_source(config, report)
    result = PatchResult(entry_point=original, original=original)

    if config.patch_mode == "inplace":
        backup = original.with_suffix(original.suffix + ".bak")
        backup.write_text(report.source, encoding="utf-8")
        original.write_text(patched, encoding="utf-8")
        result.backup = backup
        result.notes.append(f"Sauvegarde du script d'origine : {backup.name}")
        return result

    target = original.with_name(f"_pybuilder_{original.stem}.py")
    target.write_text(patched, encoding="utf-8")
    result.entry_point = target
    result.temporary = not config.keep_patched
    result.notes.append(f"Script patché écrit à côté de l'original : {target.name}")
    return result

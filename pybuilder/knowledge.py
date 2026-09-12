"""Base de connaissances : options PyInstaller à appliquer selon les modules importés.

Chaque entrée associe un module racine aux options qui evitent les erreurs les plus
courantes au premier lancement de l'exe (données manquantes, imports dynamiques...).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hint:
    """Conseils PyInstaller pour un paquet donné."""

    collect_all: tuple[str, ...] = ()
    collect_data: tuple[str, ...] = ()
    collect_submodules: tuple[str, ...] = ()
    hidden_imports: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    gui: bool = False
    note: str = ""


#: Bindings graphiques -> l'application doit être construite en mode fenêtré.
GUI_MODULES = ("PySide6", "PySide2", "PyQt6", "PyQt5", "tkinter", "wx", "kivy", "pygame", "customtkinter")

#: Modules déclenchant un mode console obligatoire (l'app lit/écrit le terminal).
CONSOLE_HINT_MODULES = ("curses", "readline", "click", "typer", "argparse", "rich", "prompt_toolkit")

KNOWLEDGE: dict[str, Hint] = {
    "PySide6": Hint(
        gui=True,
        excludes=("PyQt5", "PyQt6", "PySide2"),
        note="Qt est volumineux : excluez les bindings concurrents pour alléger l'exe.",
    ),
    "PySide2": Hint(gui=True, excludes=("PyQt5", "PyQt6", "PySide6")),
    "PyQt6": Hint(gui=True, excludes=("PyQt5", "PySide2", "PySide6")),
    "PyQt5": Hint(gui=True, excludes=("PyQt6", "PySide2", "PySide6")),
    "customtkinter": Hint(collect_all=("customtkinter",), gui=True, note="Thèmes .json à embarquer."),
    "tkinter": Hint(gui=True),
    "wx": Hint(gui=True),
    "kivy": Hint(collect_all=("kivy",), gui=True),
    "pygame": Hint(gui=True),
    "matplotlib": Hint(
        collect_data=("matplotlib",),
        hidden_imports=("matplotlib.backends.backend_agg",),
        note="Les polices et styles matplotlib ne sont pas détectés automatiquement.",
    ),
    "numpy": Hint(),
    "scipy": Hint(collect_submodules=("scipy",), note="scipy charge des sous-modules dynamiquement."),
    "pandas": Hint(hidden_imports=("pandas._libs.tslibs.timedeltas",)),
    "skrf": Hint(collect_data=("skrf",), note="scikit-rf embarque des données de calibration."),
    "sklearn": Hint(collect_submodules=("sklearn",)),
    "requests": Hint(collect_data=("certifi",), hidden_imports=("certifi",), note="Certificats TLS requis."),
    "httpx": Hint(collect_data=("certifi",), hidden_imports=("certifi",)),
    "certifi": Hint(collect_data=("certifi",)),
    "serial": Hint(hidden_imports=("serial.tools.list_ports",)),
    "pyvisa": Hint(collect_all=("pyvisa",), note="pyvisa charge ses backends dynamiquement."),
    "PIL": Hint(hidden_imports=("PIL._tkinter_finder",)),
    "cv2": Hint(collect_all=("cv2",)),
    "openpyxl": Hint(collect_data=("openpyxl",)),
    "docx": Hint(collect_data=("docx",)),
    "pptx": Hint(collect_data=("pptx",)),
    "reportlab": Hint(collect_data=("reportlab",)),
    "pyqtgraph": Hint(collect_submodules=("pyqtgraph",)),
    "plotly": Hint(collect_data=("plotly",)),
    "dash": Hint(collect_data=("dash",)),
    "flask": Hint(collect_data=("flask",)),
    "jinja2": Hint(collect_data=("jinja2",)),
    "win32com": Hint(hidden_imports=("win32timezone",)),
    "pythoncom": Hint(hidden_imports=("win32timezone",)),
    "sqlalchemy": Hint(collect_submodules=("sqlalchemy",)),
    "babel": Hint(collect_data=("babel",)),
    "pydantic": Hint(collect_submodules=("pydantic",)),
    "tqdm": Hint(),
    "yaml": Hint(),
}

#: Modules dont l'exclusion allège fortement l'exe quand ils ne sont pas utilisés.
COMMON_EXCLUDES = ("tkinter", "test", "unittest", "pydoc_data", "setuptools", "pip")


def hints_for(modules: set[str]) -> list[tuple[str, Hint]]:
    """Renvoie les conseils connus pour les modules importés, triés par nom."""
    found = [(mod, KNOWLEDGE[mod]) for mod in sorted(modules) if mod in KNOWLEDGE]
    return found


def aggregate(modules: set[str]) -> dict[str, list[str]]:
    """Fusionne les conseils de tous les modules détectés en listes d'options."""
    out: dict[str, list[str]] = {
        "collect_all": [],
        "collect_data": [],
        "collect_submodules": [],
        "hidden_imports": [],
        "excludes": [],
    }
    for _mod, hint in hints_for(modules):
        for key in out:
            for value in getattr(hint, key):
                if value not in out[key]:
                    out[key].append(value)
    # Ne jamais exclure un module réellement importé par le script.
    out["excludes"] = [name for name in out["excludes"] if name.split(".")[0] not in modules]
    return out


def is_gui(modules: set[str]) -> str | None:
    """Nom du binding graphique détecté, ou None pour une application console."""
    for name in GUI_MODULES:
        if name in modules:
            return name
    return None

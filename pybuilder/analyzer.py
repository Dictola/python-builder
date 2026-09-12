"""Analyse statique du script cible : imports, point d'entrée, ressources, pièges.

L'analyse repose uniquement sur l'AST (aucune exécution du script cible).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import knowledge

#: Extensions considérées comme des ressources à embarquer dans l'exe.
DATA_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".ui", ".qss", ".qrc", ".css", ".html", ".htm", ".md",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml",
    ".csv", ".txt", ".tsv", ".db", ".sqlite", ".sqlite3",
    ".ttf", ".otf", ".woff", ".woff2", ".wav", ".mp3", ".ogg",
    ".s1p", ".s2p", ".s3p", ".s4p", ".ts", ".npy", ".npz", ".pkl", ".xlsx",
}

LEVELS = ("ok", "info", "warn", "error")


@dataclass
class Finding:
    """Un constat de l'analyse, affiché tel quel dans l'IHM."""

    level: str  # ok | info | warn | error
    title: str
    detail: str = ""


@dataclass
class ScriptReport:
    """Résultat complet de l'analyse d'un script."""

    path: Path
    source: str = ""
    lines: list[str] = field(default_factory=list)
    syntax_error: str | None = None

    imports: set[str] = field(default_factory=set)
    third_party: set[str] = field(default_factory=set)
    gui: str | None = None

    has_main_guard: bool = False
    main_guard_body_line: int = 0  # 1-based, 1re instruction du bloc __main__
    main_guard_indent: str = "    "
    has_toplevel_code: bool = False

    uses_multiprocessing: bool = False
    uses_input: bool = False
    uses_file_attr: bool = False
    uses_relative_paths: bool = False
    uses_pyi_splash: bool = False
    already_patched: bool = False

    insertion_line: int = 0  # index 0-based où injecter l'en-tête
    last_import_line: int = 0  # 1-based, dernière ligne d'import de premier niveau

    data_files: list[Path] = field(default_factory=list)
    missing_data_refs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    suggestions: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.syntax_error is None

    def counts(self) -> dict[str, int]:
        out = {level: 0 for level in LEVELS}
        for finding in self.findings:
            out[finding.level] = out.get(finding.level, 0) + 1
        return out


def _stdlib_names() -> set[str]:
    names = set(getattr(sys, "stdlib_module_names", ()))
    return names or {"os", "sys", "re", "json", "math", "time", "pathlib", "typing"}


def _module_root(name: str | None) -> str:
    return (name or "").split(".")[0]


def analyze(path: str | Path) -> ScriptReport:
    """Analyse un script Python et renvoie un rapport prêt à afficher."""
    path = Path(path).expanduser()
    report = ScriptReport(path=path)

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="latin-1")
        report.findings.append(
            Finding("warn", "Encodage non UTF-8", "Le fichier a été relu en latin-1 ; le patch sera écrit en UTF-8.")
        )
    except OSError as exc:
        report.syntax_error = f"Lecture impossible : {exc}"
        report.findings.append(Finding("error", "Fichier illisible", str(exc)))
        return report

    report.source = source
    report.lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        report.syntax_error = f"Ligne {exc.lineno} : {exc.msg}"
        report.findings.append(
            Finding("error", "Erreur de syntaxe", f"{report.syntax_error}\nPyInstaller ne pourra pas compiler ce script.")
        )
        return report

    _scan_tree(tree, report)
    _compute_insertion(tree, report)
    _collect_data_files(tree, report)
    _build_findings(report)
    return report


def _scan_tree(tree: ast.Module, report: ScriptReport) -> None:
    stdlib = _stdlib_names()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                report.imports.add(_module_root(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:  # ignore les imports relatifs (.module)
                report.imports.add(_module_root(node.module))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "input":
                report.uses_input = True
        elif isinstance(node, ast.Name) and node.id == "__file__":
            report.uses_file_attr = True

    report.imports.discard("")
    report.third_party = {name for name in report.imports if name not in stdlib}
    report.gui = knowledge.is_gui(report.imports)
    report.uses_multiprocessing = bool({"multiprocessing", "concurrent"} & report.imports)
    report.uses_pyi_splash = "pyi_splash" in report.imports
    report.already_patched = "PyBuilder" in report.source and "pybuilder_close_splash" in report.source

    # Dernier import de premier niveau et présence du garde __main__.
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            report.last_import_line = max(report.last_import_line, node.end_lineno or node.lineno)
        elif isinstance(node, ast.If) and _is_main_guard(node):
            report.has_main_guard = True
            if node.body:
                first = node.body[0]
                report.main_guard_body_line = first.lineno
                report.main_guard_indent = " " * first.col_offset
        elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Expr)):
            report.has_toplevel_code = True
        elif isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            report.has_toplevel_code = True


def _is_main_guard(node: ast.If) -> bool:
    """Vrai pour `if __name__ == "__main__":` (et ses variantes d'écriture)."""
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    pairs = ((left, right), (right, left))
    for name_node, const_node in pairs:
        if (
            isinstance(name_node, ast.Name)
            and name_node.id == "__name__"
            and isinstance(const_node, ast.Constant)
            and const_node.value == "__main__"
        ):
            return True
    return False


def _compute_insertion(tree: ast.Module, report: ScriptReport) -> None:
    """Détermine la ligne d'injection : après shebang, encodage, docstring et __future__."""
    line = 0
    lines = report.lines

    if lines and lines[0].startswith("#!"):
        line = 1
    # Ligne de déclaration d'encodage (PEP 263) : dans les deux premières lignes.
    for index in range(line, min(line + 2, len(lines))):
        if "coding" in lines[index] and lines[index].lstrip().startswith("#"):
            line = index + 1
            break

    for node in tree.body:
        is_docstring = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_docstring or is_future:
            line = max(line, node.end_lineno or node.lineno)
        else:
            break

    report.insertion_line = line
    report.last_import_line = max(report.last_import_line, line)


def _collect_data_files(tree: ast.Module, report: ScriptReport) -> None:
    """Repère les chaînes qui ressemblent à des fichiers de ressources."""
    base = report.path.parent
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.strip()
        if not text or len(text) > 260 or "://" in text or "\n" in text:
            continue
        suffix = Path(text).suffix.lower()
        if suffix not in DATA_SUFFIXES or text in seen:
            continue
        seen.add(text)
        candidate = Path(text)
        resolved = candidate if candidate.is_absolute() else base / candidate
        if resolved.is_file():
            report.data_files.append(resolved)
            if not candidate.is_absolute():
                report.uses_relative_paths = True
        else:
            report.missing_data_refs.append(text)


def _build_findings(report: ScriptReport) -> None:
    """Traduit l'analyse en constats lisibles et en suggestions d'options."""
    add = report.findings.append

    if report.gui:
        add(Finding("ok", f"Application graphique détectée ({report.gui})",
                    "Construction en mode fenêtré : pas de console noire derrière l'application."))
    else:
        add(Finding("info", "Aucune interface graphique détectée",
                    "Le mode console sera proposé pour garder les messages visibles."))

    if report.uses_input and report.gui:
        add(Finding("warn", "Appel à input() dans une application fenêtrée",
                    "En mode fenêtré il n'y a pas d'entrée standard : input() lèvera une erreur."))

    if report.has_main_guard:
        add(Finding("ok", "Garde `if __name__ == \"__main__\"` présente", "Point d'entrée clairement identifié."))
    elif report.has_toplevel_code:
        add(Finding("info", "Pas de garde `__main__`",
                    "Le code s'exécute au niveau du module : c'est accepté, mais la garde est recommandée."))
    else:
        add(Finding("warn", "Aucun code exécutable détecté",
                    "Ce fichier ressemble à une bibliothèque : l'exe se fermera immédiatement."))

    if report.uses_multiprocessing:
        add(Finding("warn", "multiprocessing utilisé",
                    "Sans freeze_support(), l'exe relance une fenêtre à l'infini. Le patch l'ajoute automatiquement."))

    if report.uses_file_attr or report.uses_relative_paths:
        add(Finding("info", "Chemins relatifs ou __file__ utilisés",
                    "Dans un exe onefile, les fichiers sont extraits dans un dossier temporaire : "
                    "utilisez le helper pybuilder_resource_path() ajouté par le patch."))

    if report.data_files:
        listing = "\n".join(f"• {path.name}" for path in report.data_files[:8])
        more = f"\n… et {len(report.data_files) - 8} autre(s)" if len(report.data_files) > 8 else ""
        add(Finding("info", f"{len(report.data_files)} ressource(s) trouvée(s) à côté du script",
                    f"Elles seront proposées à l'embarquement :\n{listing}{more}"))

    if report.missing_data_refs:
        add(Finding("info", f"{len(report.missing_data_refs)} chemin(s) non résolu(s)",
                    "Ces fichiers sont cités dans le code mais absents du dossier : "
                    + ", ".join(report.missing_data_refs[:6])))

    if report.uses_pyi_splash:
        add(Finding("info", "Le script utilise déjà pyi_splash",
                    "Le patch reste compatible : les deux fermetures du splash sont sans effet l'une sur l'autre."))

    if report.already_patched:
        add(Finding("warn", "Script déjà patché par PyBuilder",
                    "L'ancien bloc injecté sera remplacé par le nouveau."))

    for module, hint in knowledge.hints_for(report.imports):
        if hint.note:
            add(Finding("info", f"Paquet « {module} »", hint.note))

    report.suggestions = knowledge.aggregate(report.imports)

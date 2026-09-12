"""Préparation et exécution de la construction PyInstaller."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import assets, spec as spec_module
from .analyzer import ScriptReport
from .models import BuildConfig
from .patcher import PatchResult, write_patched

#: Étapes reconnues dans le journal PyInstaller -> avancement affiché (%).
PROGRESS_STEPS: tuple[tuple[re.Pattern, int, str], ...] = (
    (re.compile(r"PyInstaller: \d"), 3, "Démarrage de PyInstaller"),
    (re.compile(r"Python: \d"), 5, "Interpréteur détecté"),
    (re.compile(r"Analyzing .*hook", re.I), 12, "Analyse des hooks"),
    (re.compile(r"Analyzing (?:base_library|module|the SCRIPT|\S+\.py)", re.I), 20, "Analyse du script"),
    (re.compile(r"Processing (?:module hooks|pre-safe|pre-find)", re.I), 35, "Traitement des modules"),
    (re.compile(r"Looking for ctypes DLLs", re.I), 48, "Recherche des bibliothèques"),
    (re.compile(r"Analyzing run-time hooks", re.I), 55, "Hooks d'exécution"),
    (re.compile(r"Looking for dynamic libraries", re.I), 62, "Bibliothèques dynamiques"),
    (re.compile(r"Checking PYZ|Building PYZ", re.I), 72, "Archive Python"),
    (re.compile(r"Checking PKG|Building PKG", re.I), 82, "Assemblage du paquet"),
    (re.compile(r"Bootloader", re.I), 88, "Bootloader"),
    (re.compile(r"Building EXE", re.I), 90, "Construction de l'exécutable"),
    (re.compile(r"Appending (?:PKG archive|archive)", re.I), 95, "Intégration des données"),
    (re.compile(r"Building COLLECT", re.I), 96, "Copie des dépendances"),
    # « completed successfully » apparaît à chaque sous-étape : seul « Build complete! »
    # marque la fin réelle de la construction.
    (re.compile(r"Build complete!", re.I), 99, "Finalisation"),
)

WARNING_PATTERN = re.compile(r"^\s*\d+ WARNING:|WARNING:", re.I)
ERROR_PATTERN = re.compile(r"^\s*\d+ ERROR:|ERROR:|Traceback \(most recent call last\)", re.I)


@dataclass
class BuildPlan:
    """Tout ce qui a été préparé sur le disque avant de lancer PyInstaller."""

    config: BuildConfig
    work_dir: Path
    spec_path: Path
    entry_point: Path
    command: list[str]
    dist_dir: Path
    patch: PatchResult
    splash: assets.SplashInfo | None = None
    icon: Path | None = None
    version_file: Path | None = None
    cleanup: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def command_line(self) -> str:
        return " ".join(shlex.quote(part) for part in self.command)

    def expected_output(self) -> Path:
        """Chemin attendu de l'exécutable produit."""
        suffix = ".exe" if sys.platform == "win32" else ""
        name = self.config.exe_name + suffix
        if self.config.onefile:
            return self.dist_dir / name
        return self.dist_dir / self.config.exe_name / name


def default_work_dir(config: BuildConfig) -> Path:
    """Dossier de travail : à côté du script, sinon dans le dossier de destination."""
    if config.work_dir:
        return Path(config.work_dir)
    script = config.script_path
    base = script.parent if script.name else Path.cwd()
    if os.access(base, os.W_OK):
        return base / ".pybuilder"
    return Path(config.dist_dir or Path.cwd()) / ".pybuilder"


def python_candidates(script: str | Path | None = None) -> list[str]:
    """Interpréteurs proposés : celui de PyBuilder, puis les venv voisins du script."""
    found: list[str] = [sys.executable]
    if script:
        base = Path(script).expanduser().parent
        for folder in (".venv", "venv", "env"):
            for relative in ("bin/python", "bin/python3", "Scripts/python.exe"):
                candidate = base / folder / relative
                if candidate.is_file():
                    found.append(str(candidate))
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            found.append(path)
    unique: list[str] = []
    for item in found:
        resolved = str(Path(item))
        if resolved not in unique:
            unique.append(resolved)
    return unique


def pyinstaller_version(python_exe: str) -> tuple[bool, str]:
    """Vérifie que PyInstaller est disponible dans l'interpréteur choisi."""
    try:
        result = subprocess.run(
            [python_exe, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip().splitlines()
        return False, details[-1] if details else "PyInstaller n'est pas installé dans cet interpréteur."
    return True, result.stdout.strip()


def compose_command(
    config: BuildConfig,
    spec_path: Path,
    dist_dir: Path,
    work_dir: Path,
    extra: list[str] | None = None,
) -> list[str]:
    """Ligne de commande PyInstaller pilotée par le .spec généré."""
    command = [
        config.python_exe or sys.executable,
        "-m", "PyInstaller",
        str(spec_path),
        "--noconfirm",
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir / "build"),
        "--log-level", config.log_level,
    ]
    if config.clean:
        command.append("--clean")
    if config.upx_dir:
        command += ["--upx-dir", config.upx_dir]
    return command + list(extra or [])


def preview_texts(config: BuildConfig, report: ScriptReport | None) -> tuple[str, str]:
    """Renvoie (commande, contenu du .spec) sans rien écrire sur le disque.

    Utilisé par l'aperçu de l'IHM : les chemins sont ceux qui *seront* produits.
    """
    work_dir = default_work_dir(config)
    dist_dir = Path(config.dist_dir or work_dir / "dist").expanduser()
    name = config.exe_name

    script = config.script_path
    if config.patch_mode == "inplace" or not config.script:
        entry_point = script
    else:
        entry_point = script.with_name(f"_pybuilder_{script.stem}.py")

    splash_info = None
    if config.splash_enabled:
        if config.splash_image:
            path = Path(config.splash_image)
            splash_info = assets.SplashInfo(path, 0, 0, (38, 244), 12, "#93a1b5", generated=False)
            try:
                splash_info = assets.describe_splash(path, config.splash_dark)
            except (ValueError, OSError):
                pass
        else:
            _image, text_pos = assets.render_splash(
                config.splash_title or name, config.splash_subtitle, config.splash_accent, config.splash_dark
            )
            splash_info = assets.SplashInfo(
                work_dir / f"{name}-splash.png",
                assets.SPLASH_SIZE[0],
                assets.SPLASH_SIZE[1],
                text_pos,
                12,
                "#93a1b5" if config.splash_dark else "#5c6a7e",
            )

    icon_path = None
    if config.icon:
        icon_path = Path(config.icon) if Path(config.icon).suffix.lower() == ".ico" else work_dir / f"{name}.ico"
    elif config.icon_generate:
        icon_path = work_dir / f"{name}.ico"

    version_file = work_dir / f"{name}-version.txt" if config.version_enabled else None
    spec_text = spec_module.render_spec(config, entry_point, splash_info, icon_path, version_file)

    extra = shlex.split(config.extra_args) if config.extra_args.strip() else []
    extra = _drop_flags(extra, spec_module.incompatible_flags(extra))
    command = compose_command(config, work_dir / f"{name}.spec", dist_dir, work_dir, extra)
    return " ".join(shlex.quote(part) for part in command), spec_text


def prepare(config: BuildConfig, report: ScriptReport) -> BuildPlan:
    """Écrit le script patché, les visuels et le .spec, puis compose la commande."""
    work_dir = default_work_dir(config)
    work_dir.mkdir(parents=True, exist_ok=True)
    dist_dir = Path(config.dist_dir).expanduser()
    dist_dir.mkdir(parents=True, exist_ok=True)

    patch = write_patched(config, report, work_dir)
    notes = list(patch.notes)
    warnings: list[str] = []
    cleanup: list[Path] = []
    if patch.temporary:
        cleanup.append(patch.entry_point)

    splash_info: assets.SplashInfo | None = None
    if config.splash_enabled:
        if sys.platform == "darwin":
            warnings.append("PyInstaller ne gère pas le splash screen sous macOS : il sera ignoré.")
        if config.splash_image:
            splash_info = assets.describe_splash(Path(config.splash_image), config.splash_dark)
            notes.append(f"Splash screen fourni : {Path(config.splash_image).name}")
        else:
            splash_info = assets.make_splash(
                work_dir / f"{config.exe_name}-splash.png",
                config.splash_title or config.exe_name,
                config.splash_subtitle,
                config.splash_accent,
                config.splash_dark,
            )
            notes.append(f"Splash screen généré : {splash_info.path.name}")

    icon_path: Path | None = None
    if config.icon:
        icon_path = assets.make_icon(work_dir / f"{config.exe_name}.ico", config.icon, config.exe_name, config.splash_accent)
        if Path(config.icon).suffix.lower() != ".ico":
            notes.append(f"Icône convertie en .ico : {icon_path.name}")
    elif config.icon_generate:
        icon_path = assets.make_icon(work_dir / f"{config.exe_name}.ico", None, config.exe_name, config.splash_accent)
        notes.append(f"Icône générée : {icon_path.name}")

    version_file: Path | None = None
    if config.version_enabled:
        version_file = spec_module.write_version_file(config, work_dir / f"{config.exe_name}-version.txt")
        notes.append(f"Informations de version : {version_file.name}")

    spec_text = spec_module.render_spec(config, patch.entry_point, splash_info, icon_path, version_file)
    spec_path = work_dir / f"{config.exe_name}.spec"
    spec_path.write_text(spec_text, encoding="utf-8")
    if not config.keep_spec:
        cleanup.append(spec_path)

    extra = shlex.split(config.extra_args) if config.extra_args.strip() else []
    bad_flags = spec_module.incompatible_flags(extra)
    if bad_flags:
        warnings.append(
            "Options ignorées car incompatibles avec un .spec : "
            + ", ".join(bad_flags)
            + " (à régler dans les onglets de l'IHM)."
        )
        extra = _drop_flags(extra, bad_flags)

    command = compose_command(config, spec_path, dist_dir, work_dir, extra)

    return BuildPlan(
        config=config,
        work_dir=work_dir,
        spec_path=spec_path,
        entry_point=patch.entry_point,
        command=command,
        dist_dir=dist_dir,
        patch=patch,
        splash=splash_info,
        icon=icon_path,
        version_file=version_file,
        cleanup=cleanup,
        notes=notes,
        warnings=warnings,
    )


def _drop_flags(tokens: list[str], bad: list[str]) -> list[str]:
    """Retire les options refusées (et leur valeur éventuelle)."""
    out: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        flag = token.split("=", 1)[0]
        if flag in bad:
            skip_next = "=" not in token
            continue
        out.append(token)
    return out


def cleanup_plan(plan: BuildPlan) -> None:
    """Supprime les fichiers temporaires générés pour la construction."""
    for path in plan.cleanup:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
        except OSError:
            pass


class BuildRunner(QObject):
    """Exécute PyInstaller dans un processus séparé et diffuse son journal."""

    line = Signal(str, str)  # texte, niveau (info/warn/error/success)
    progress = Signal(int, str)  # pourcentage, étape
    started = Signal()
    finished = Signal(bool, str)  # succès, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._plan: BuildPlan | None = None
        self._buffer = ""
        self._cancelled = False
        self._progress = 0

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    def start(self, plan: BuildPlan) -> None:
        if self.running:
            raise RuntimeError("Une construction est déjà en cours.")
        self._plan = plan
        self._buffer = ""
        self._cancelled = False
        self._progress = 0

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(str(plan.work_dir))

        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)

        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._process = process
        self.started.emit()
        self.progress.emit(1, "Lancement de PyInstaller")
        process.start(plan.command[0], plan.command[1:])

    def cancel(self) -> None:
        if not self.running or self._process is None:
            return
        self._cancelled = True
        self.line.emit("Annulation demandée…", "warn")
        self._process.terminate()
        QTimer.singleShot(3000, self._kill_if_needed)

    def _kill_if_needed(self) -> None:
        if self.running and self._process is not None:
            self._process.kill()

    def _on_output(self) -> None:
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
        *lines, self._buffer = self._buffer.split("\n")
        for text in lines:
            self._emit_line(text)

    def _emit_line(self, text: str) -> None:
        if not text.strip():
            return
        level = "info"
        if ERROR_PATTERN.search(text):
            level = "error"
        elif WARNING_PATTERN.search(text):
            level = "warn"
        self.line.emit(text, level)

        for pattern, percent, label in PROGRESS_STEPS:
            if percent > self._progress and pattern.search(text):
                self._progress = percent
                self.progress.emit(percent, label)
                break

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            command = self._plan.command[0] if self._plan else "python"
            self.line.emit(f"Impossible de lancer « {command} ».", "error")

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._buffer.strip():
            self._emit_line(self._buffer)
        self._buffer = ""
        plan = self._plan
        self._process = None

        if plan is None:
            self.finished.emit(False, "Construction interrompue.")
            return

        cleanup_plan(plan)

        if self._cancelled:
            self.finished.emit(False, "Construction annulée.")
            return
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            self.finished.emit(False, f"PyInstaller s'est arrêté avec le code {code}.")
            return

        output = plan.expected_output()
        if not output.exists():
            matches = sorted(plan.dist_dir.glob(f"{plan.config.exe_name}*"))
            output = matches[0] if matches else output
        if output.exists():
            size = _folder_size(output) if output.is_dir() else output.stat().st_size
            self.progress.emit(100, "Terminé")
            self.finished.emit(True, f"{output}|{size}")
        else:
            self.finished.emit(False, "La construction s'est terminée mais l'exécutable est introuvable.")


def _folder_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

"""Modèle de configuration d'une construction (sérialisable en JSON)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

#: Stratégies de fermeture du splash screen, dans l'ordre d'affichage de l'IHM.
SPLASH_STRATEGIES: dict[str, str] = {
    "mainloop": "À l'ouverture de la fenêtre (Qt / tkinter)",
    "imports": "Quand les imports sont terminés",
    "timer": "Après un délai fixe",
    "manual": "Manuellement (appel de pybuilder_close_splash)",
}

#: Modes d'application du patch sur le script source.
PATCH_MODES: dict[str, str] = {
    "copy": "Travailler sur une copie (le script d'origine n'est pas touché)",
    "inplace": "Modifier le script d'origine (sauvegarde .bak)",
}


@dataclass
class BuildConfig:
    """Tous les réglages d'une construction, tels que saisis dans l'IHM."""

    # --- Source -------------------------------------------------------
    script: str = ""
    python_exe: str = ""

    # --- Exécutable ---------------------------------------------------
    name: str = ""
    dist_dir: str = ""
    onefile: bool = True
    windowed: bool = True
    icon: str = ""
    icon_generate: bool = True
    clean: bool = True
    strip_debug: bool = False
    uac_admin: bool = False
    upx_dir: str = ""

    # --- Splash screen ------------------------------------------------
    splash_enabled: bool = True
    splash_image: str = ""
    splash_title: str = ""
    splash_subtitle: str = "Chargement en cours…"
    splash_accent: str = "#4f8cff"
    splash_dark: bool = True
    splash_strategy: str = "mainloop"
    splash_timeout: float = 30.0
    splash_show_text: bool = True
    splash_always_on_top: bool = True

    # --- Patch du script ----------------------------------------------
    patch_mode: str = "copy"
    add_resource_helper: bool = True
    add_freeze_support: bool = True
    add_excepthook: bool = True
    keep_patched: bool = False

    # --- Options PyInstaller ------------------------------------------
    hidden_imports: list[str] = field(default_factory=list)
    collect_all: list[str] = field(default_factory=list)
    collect_data: list[str] = field(default_factory=list)
    collect_submodules: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    add_data: list[list[str]] = field(default_factory=list)  # [[source, destination], ...]
    add_binary: list[list[str]] = field(default_factory=list)
    extra_args: str = ""
    log_level: str = "INFO"
    work_dir: str = ""
    keep_spec: bool = True

    # --- Informations de version (Windows) ----------------------------
    version_enabled: bool = False
    version_number: str = "1.0.0.0"
    version_company: str = ""
    version_product: str = ""
    version_description: str = ""
    version_copyright: str = ""

    # ------------------------------------------------------------------
    @property
    def script_path(self) -> Path:
        return Path(self.script).expanduser()

    @property
    def exe_name(self) -> str:
        """Nom de l'exécutable : celui saisi, sinon celui du script."""
        if self.name.strip():
            return self.name.strip()
        if self.script:
            return self.script_path.stem
        return "application"

    def validate(self) -> list[str]:
        """Renvoie la liste des problèmes bloquants avant construction."""
        problems: list[str] = []
        if not self.script:
            problems.append("Aucun script Python sélectionné.")
        elif not self.script_path.is_file():
            problems.append(f"Le script est introuvable : {self.script}")
        elif self.script_path.suffix.lower() not in (".py", ".pyw"):
            problems.append("Le fichier source doit être un .py ou .pyw.")
        if not self.dist_dir:
            problems.append("Aucun dossier de destination choisi pour l'exe.")
        if self.icon and not Path(self.icon).is_file():
            problems.append(f"Icône introuvable : {self.icon}")
        if self.splash_enabled and self.splash_image and not Path(self.splash_image).is_file():
            problems.append(f"Image de splash introuvable : {self.splash_image}")
        for source, _dest in self.add_data + self.add_binary:
            if not Path(source).exists():
                problems.append(f"Fichier à embarquer introuvable : {source}")
        if self.splash_strategy not in SPLASH_STRATEGIES:
            problems.append(f"Stratégie de splash inconnue : {self.splash_strategy}")
        if self.patch_mode not in PATCH_MODES:
            problems.append(f"Mode de patch inconnu : {self.patch_mode}")
        return problems

    # --- Sérialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BuildConfig":
        known = {f.name for f in fields(cls)}
        clean = {key: value for key, value in data.items() if key in known}
        # Les listes chargées depuis JSON peuvent contenir des tuples/valeurs nulles.
        for key in ("add_data", "add_binary"):
            if key in clean:
                clean[key] = [list(item)[:2] for item in clean[key] if item]
        return cls(**clean)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "BuildConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

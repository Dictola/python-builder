"""Génération du fichier .spec PyInstaller.

Passer par un .spec plutôt que par la seule ligne de commande permet de régler le
splash screen finement (position, taille et couleur du texte d'état), ce que les
options `--splash` de la ligne de commande ne permettent pas.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .assets import SplashInfo
from .models import BuildConfig

#: Options acceptées par PyInstaller lorsqu'on lui passe un .spec.
SPEC_COMPATIBLE_FLAGS = {
    "--noconfirm", "-y", "--clean", "--distpath", "--workpath", "--log-level",
    "--upx-dir", "--noupx", "--upx-exclude",
}

VERSION_TEMPLATE = '''# Informations de version Windows générées par PyBuilder.
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={numbers},
        prodvers={numbers},
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable('040C04B0', [
                StringStruct('CompanyName', {company}),
                StringStruct('FileDescription', {description}),
                StringStruct('FileVersion', {version}),
                StringStruct('InternalName', {name}),
                StringStruct('LegalCopyright', {copyright}),
                StringStruct('OriginalFilename', {filename}),
                StringStruct('ProductName', {product}),
                StringStruct('ProductVersion', {version}),
            ]),
        ]),
        VarFileInfo([VarStruct('Translation', [1036, 1200])]),
    ],
)
'''


def _q(value: str | Path | None) -> str:
    """Littéral Python pour un chemin (en / pour rester valide sous Windows)."""
    if value is None or value == "":
        return "None"
    if isinstance(value, Path):
        value = value.as_posix()
    else:
        value = str(value).replace("\\", "/")
    return repr(value)


def _block(items: list[str], indent: str = "") -> str:
    """Liste Python : sur une ligne si elle est courte, sinon une entrée par ligne."""
    if not items:
        return "[]"
    single = "[" + ", ".join(items) + "]"
    if len(single) + len(indent) <= 76:
        return single
    inner = f",\n{indent}    ".join(items)
    return f"[\n{indent}    {inner},\n{indent}]"


def _list(values, indent: str = "") -> str:
    return _block([_q(item) for item in values or []], indent)


def _pairs(pairs, indent: str = "") -> str:
    return _block([f"({_q(src)}, {_q(dest or '.')})" for src, dest in pairs or []], indent)


def version_numbers(text: str) -> tuple[int, int, int, int]:
    """Convertit « 1.2.3 » en (1, 2, 3, 0), tolérant aux saisies libres."""
    parts: list[int] = []
    for chunk in str(text).replace(",", ".").split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    parts = (parts + [0, 0, 0, 0])[:4]
    return tuple(parts)  # type: ignore[return-value]


def write_version_file(config: BuildConfig, destination: Path) -> Path:
    """Écrit le fichier d'informations de version lisible par PyInstaller."""
    numbers = version_numbers(config.version_number)
    text = VERSION_TEMPLATE.format(
        numbers=numbers,
        company=repr(config.version_company or config.exe_name),
        description=repr(config.version_description or config.exe_name),
        version=repr(config.version_number),
        name=repr(config.exe_name),
        copyright=repr(config.version_copyright or ""),
        filename=repr(f"{config.exe_name}.exe"),
        product=repr(config.version_product or config.exe_name),
    )
    destination.write_text(text, encoding="utf-8")
    return destination


def render_spec(
    config: BuildConfig,
    entry_point: Path,
    splash: SplashInfo | None,
    icon: Path | None,
    version_file: Path | None,
) -> str:
    """Construit le contenu du fichier .spec."""
    name = config.exe_name
    search_path = [entry_point.parent]

    lines: list[str] = [
        "# -*- mode: python ; coding: utf-8 -*-",
        f"# Fichier généré par PyBuilder {__version__}.",
        "# Il peut être modifié à la main puis relancé avec : pyinstaller ce_fichier.spec",
        "",
        "from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules",
        "",
        f"datas = {_pairs(config.add_data)}",
        f"binaries = {_pairs(config.add_binary)}",
        f"hiddenimports = {_list(config.hidden_imports)}",
        "",
        f"for _package in {_list(config.collect_all)}:",
        "    _datas, _binaries, _hidden = collect_all(_package)",
        "    datas += _datas",
        "    binaries += _binaries",
        "    hiddenimports += _hidden",
        "",
        f"for _package in {_list(config.collect_data)}:",
        "    datas += collect_data_files(_package)",
        "",
        f"for _package in {_list(config.collect_submodules)}:",
        "    hiddenimports += collect_submodules(_package)",
        "",
        "a = Analysis(",
        f"    [{_q(entry_point)}],",
        f"    pathex={_list(search_path, chr(32) * 4)},",
        "    binaries=binaries,",
        "    datas=datas,",
        "    hiddenimports=hiddenimports,",
        "    hookspath=[],",
        "    hooksconfig={},",
        "    runtime_hooks=[],",
        f"    excludes={_list(config.excludes, chr(32) * 4)},",
        "    noarchive=False,",
        ")",
        "",
        "pyz = PYZ(a.pure)",
        "",
    ]

    if splash is not None:
        lines += [
            "splash = Splash(",
            f"    {_q(splash.path)},",
            "    binaries=a.binaries,",
            "    datas=a.datas,",
            f"    text_pos={splash.text_pos if config.splash_show_text else None},",
            f"    text_size={splash.text_size},",
            f"    text_color={_q(splash.text_color)},",
            f"    always_on_top={bool(config.splash_always_on_top)},",
            ")",
            "",
        ]

    exe_args = [
        "    pyz,",
        "    a.scripts,",
    ]
    if splash is not None:
        exe_args.append("    splash,")

    if config.onefile:
        if splash is not None:
            exe_args.append("    splash.binaries,")
        exe_args += ["    a.binaries,", "    a.datas,", "    [],"]
    else:
        exe_args += ["    [],", "    exclude_binaries=True,"]

    exe_args += [
        f"    name={_q(name)},",
        "    debug=False,",
        "    bootloader_ignore_signals=False,",
        f"    strip={bool(config.strip_debug)},",
        "    upx=True,",
        "    upx_exclude=[],",
        "    runtime_tmpdir=None,",
        f"    console={not config.windowed},",
        "    disable_windowed_traceback=False,",
        "    argv_emulation=False,",
        "    target_arch=None,",
        "    codesign_identity=None,",
        "    entitlements_file=None,",
        f"    icon={_q(icon)},",
    ]
    if version_file is not None:
        exe_args.append(f"    version={_q(version_file)},")
    if config.uac_admin:
        exe_args.append("    uac_admin=True,")

    lines += ["exe = EXE(", *exe_args, ")", ""]

    if not config.onefile:
        collect_args = ["    exe,"]
        if splash is not None:
            collect_args.append("    splash.binaries,")
        collect_args += [
            "    a.binaries,",
            "    a.datas,",
            f"    strip={bool(config.strip_debug)},",
            "    upx=True,",
            "    upx_exclude=[],",
            f"    name={_q(name)},",
        ]
        lines += ["coll = COLLECT(", *collect_args, ")", ""]

    return "\n".join(lines)


def incompatible_flags(extra_args: list[str]) -> list[str]:
    """Repère les options incompatibles avec une construction pilotée par .spec."""
    bad: list[str] = []
    for token in extra_args:
        if not token.startswith("-"):
            continue
        flag = token.split("=", 1)[0]
        if flag not in SPEC_COMPATIBLE_FLAGS:
            bad.append(flag)
    return bad

"""Tests unitaires de PyBuilder : python -m unittest discover -s tests

Ils couvrent l'analyse, le patch injecté et la génération du .spec. Aucun appel à
PyInstaller : la construction complète est vérifiée à part (voir le README).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pybuilder import patcher, spec  # noqa: E402
from pybuilder.analyzer import analyze  # noqa: E402
from pybuilder.models import BuildConfig  # noqa: E402

SCRIPT_QT = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application de test."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel

LOGO = "images/logo.png"


def main():
    app = QApplication(sys.argv)
    QLabel("bonjour").show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
'''

SCRIPT_MP = '''import multiprocessing


def travail(valeur):
    return valeur * 2


if __name__ == "__main__":
    with multiprocessing.Pool(2) as pool:
        print(pool.map(travail, [1, 2, 3]))
'''


class BaseTempScript(unittest.TestCase):
    """Écrit les scripts de test dans un dossier temporaire."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, source: str) -> Path:
        path = self.folder / name
        path.write_text(source, encoding="utf-8")
        return path


class TestAnalyzer(BaseTempScript):
    def test_detecte_application_qt(self) -> None:
        report = analyze(self.write("app.py", SCRIPT_QT))
        self.assertTrue(report.ok)
        self.assertEqual(report.gui, "PySide6")
        self.assertTrue(report.has_main_guard)
        self.assertIn("PySide6", report.imports)
        self.assertIn("PyQt5", report.suggestions["excludes"])

    def test_point_d_injection_apres_shebang_et_future(self) -> None:
        report = analyze(self.write("app.py", SCRIPT_QT))
        # Les 4 premières lignes : shebang, encodage, docstring, __future__.
        self.assertEqual(report.insertion_line, 4)
        self.assertGreater(report.last_import_line, report.insertion_line)

    def test_detecte_multiprocessing(self) -> None:
        report = analyze(self.write("calcul.py", SCRIPT_MP))
        self.assertTrue(report.uses_multiprocessing)
        self.assertTrue(report.has_main_guard)
        self.assertTrue(any(f.level == "warn" for f in report.findings))

    def test_ressource_existante_proposee(self) -> None:
        (self.folder / "images").mkdir()
        (self.folder / "images" / "logo.png").write_bytes(b"\x89PNG")
        report = analyze(self.write("app.py", SCRIPT_QT))
        self.assertEqual([p.name for p in report.data_files], ["logo.png"])

    def test_erreur_de_syntaxe(self) -> None:
        report = analyze(self.write("casse.py", "def f(:\n    pass\n"))
        self.assertFalse(report.ok)
        self.assertTrue(any(f.level == "error" for f in report.findings))


class TestPatcher(BaseTempScript):
    def config(self, script: Path, **kwargs) -> BuildConfig:
        options = dict(script=str(script), dist_dir=str(self.folder / "dist"), name="Demo")
        options.update(kwargs)
        return BuildConfig(**options)

    def test_bloc_injecte_et_code_valide(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        report = analyze(script)
        patched = patcher.patch_source(self.config(script), report)
        compile(patched, "app.py", "exec")  # le résultat doit rester du Python valide
        self.assertIn("pybuilder_close_splash", patched)
        self.assertIn("pybuilder_resource_path", patched)
        self.assertEqual(patched.count(patcher.BEGIN), 1)

    def test_shebang_et_future_restent_en_tete(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        patched = patcher.patch_source(self.config(script), analyze(script))
        lignes = patched.splitlines()
        self.assertTrue(lignes[0].startswith("#!"))
        self.assertIn("from __future__ import annotations", lignes[:5])

    def test_patch_idempotent(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        config = self.config(script)
        premier = patcher.patch_source(config, analyze(script))
        script.write_text(premier, encoding="utf-8")
        second = patcher.patch_source(config, analyze(script))
        self.assertEqual(second.count(patcher.BEGIN), 1)
        compile(second, "app.py", "exec")

    def test_strategie_mainloop_pose_le_hook(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        patched = patcher.patch_source(self.config(script, splash_strategy="mainloop"), analyze(script))
        self.assertIn("_pb_hook_event_loop", patched)
        self.assertIn("_pb_arm_splash_timeout", patched)

    def test_strategie_imports_ferme_apres_les_imports(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        patched = patcher.patch_source(self.config(script, splash_strategy="imports"), analyze(script))
        lignes = patched.splitlines()
        appel = next(i for i, ligne in enumerate(lignes) if ligne.startswith("pybuilder_close_splash()"))
        dernier_import = max(i for i, ligne in enumerate(lignes) if ligne.startswith("from PySide6"))
        self.assertGreater(appel, dernier_import)

    def test_strategie_manuelle_sans_minuteur(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        patched = patcher.patch_source(self.config(script, splash_strategy="manual"), analyze(script))
        self.assertNotIn("_pb_arm_splash_timeout", patched)

    def test_freeze_support_dans_le_bloc_main(self) -> None:
        script = self.write("calcul.py", SCRIPT_MP)
        patched = patcher.patch_source(self.config(script), analyze(script))
        compile(patched, "calcul.py", "exec")
        lignes = patched.splitlines()
        garde = next(i for i, ligne in enumerate(lignes) if ligne.startswith("if __name__"))
        self.assertIn("freeze_support()", lignes[garde + 1])

    def test_copie_ecrite_a_cote_de_l_original(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        report = analyze(script)
        result = patcher.write_patched(self.config(script), report, self.folder / "work")
        self.assertEqual(result.entry_point.parent, script.parent)
        self.assertEqual(result.entry_point.name, "_pybuilder_app.py")
        self.assertEqual(script.read_text(encoding="utf-8"), SCRIPT_QT)  # original intact
        self.assertTrue(result.temporary)

    def test_mode_sur_place_cree_une_sauvegarde(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        report = analyze(script)
        result = patcher.write_patched(self.config(script, patch_mode="inplace"), report, self.folder / "work")
        self.assertEqual(result.entry_point, script)
        self.assertIsNotNone(result.backup)
        self.assertEqual(result.backup.read_text(encoding="utf-8"), SCRIPT_QT)
        self.assertIn(patcher.BEGIN, script.read_text(encoding="utf-8"))

    def test_sans_splash_pas_de_hook(self) -> None:
        script = self.write("app.py", SCRIPT_QT)
        patched = patcher.patch_source(self.config(script, splash_enabled=False), analyze(script))
        self.assertNotIn("_pb_hook_event_loop", patched)
        self.assertIn("pybuilder_close_splash", patched)  # la fonction reste disponible


class TestSpec(unittest.TestCase):
    def config(self, **kwargs) -> BuildConfig:
        options = dict(script="/projet/app.py", dist_dir="/projet/dist", name="Demo")
        options.update(kwargs)
        return BuildConfig(**options)

    def test_spec_fichier_unique(self) -> None:
        text = spec.render_spec(self.config(), Path("/projet/app.py"), None, None, None)
        self.assertIn("a = Analysis(", text)
        self.assertIn("exe = EXE(", text)
        self.assertNotIn("COLLECT(", text)
        self.assertIn("console=False", text)

    def test_spec_dossier_ajoute_collect(self) -> None:
        text = spec.render_spec(self.config(onefile=False), Path("/projet/app.py"), None, None, None)
        self.assertIn("coll = COLLECT(", text)
        self.assertIn("exclude_binaries=True", text)

    def test_spec_splash(self) -> None:
        from pybuilder.assets import SplashInfo

        info = SplashInfo(Path("/projet/splash.png"), 520, 300, (38, 206), 12, "#93a1b5")
        text = spec.render_spec(self.config(), Path("/projet/app.py"), info, None, None)
        self.assertIn("splash = Splash(", text)
        self.assertIn("text_pos=(38, 206)", text)
        self.assertIn("splash.binaries", text)

    def test_spec_splash_sans_texte(self) -> None:
        from pybuilder.assets import SplashInfo

        info = SplashInfo(Path("/projet/splash.png"), 520, 300, (38, 206), 12, "#93a1b5")
        text = spec.render_spec(self.config(splash_show_text=False), Path("/projet/app.py"), info, None, None)
        self.assertIn("text_pos=None", text)

    def test_chemins_en_slash(self) -> None:
        text = spec.render_spec(self.config(), Path("C:/Users/felix/app.py"), None, None, None)
        self.assertIn("'C:/Users/felix/app.py'", text)

    def test_options_incompatibles_detectees(self) -> None:
        self.assertEqual(spec.incompatible_flags(["--onefile", "--clean"]), ["--onefile"])
        self.assertEqual(spec.incompatible_flags(["--distpath=/tmp"]), [])

    def test_numeros_de_version(self) -> None:
        self.assertEqual(spec.version_numbers("1.2.3"), (1, 2, 3, 0))
        self.assertEqual(spec.version_numbers("2.0"), (2, 0, 0, 0))
        self.assertEqual(spec.version_numbers("v1.4.2-beta"), (1, 4, 2, 0))


class TestConfig(unittest.TestCase):
    def test_aller_retour_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profil.json"
            config = BuildConfig(script="/a/b.py", name="X", add_data=[["/a/x.png", "img"]])
            config.save(path)
            self.assertEqual(BuildConfig.load(path).add_data, [["/a/x.png", "img"]])

    def test_nom_par_defaut(self) -> None:
        self.assertEqual(BuildConfig(script="/a/mon_outil.py").exe_name, "mon_outil")
        self.assertEqual(BuildConfig(script="/a/mon_outil.py", name=" Autre ").exe_name, "Autre")

    def test_validation(self) -> None:
        problems = BuildConfig().validate()
        self.assertTrue(any("script" in p.lower() for p in problems))
        self.assertTrue(any("destination" in p.lower() for p in problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)

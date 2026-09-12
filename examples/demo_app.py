"""Application PySide6 de démonstration, à convertir en exécutable avec PyBuilder.

Elle illustre les deux besoins classiques d'une application gelée :
lire une ressource embarquée et écrire un réglage à côté de l'exécutable.
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

FICHIER_REGLAGES = "reglages.json"


def dossier_donnees() -> Path:
    """Dossier où écrire les réglages.

    PyBuilder injecte pybuilder_app_dir() : dans l'exe, il renvoie le dossier de
    l'exécutable ; hors exe, la fonction n'existe pas et on retombe sur le script.
    """
    try:
        return Path(pybuilder_app_dir())  # noqa: F821 - fourni par le bloc injecté
    except NameError:
        return Path(__file__).parent


def charger_compteur() -> int:
    fichier = dossier_donnees() / FICHIER_REGLAGES
    try:
        return int(json.loads(fichier.read_text(encoding="utf-8"))["clics"])
    except (OSError, ValueError, KeyError):
        return 0


def enregistrer_compteur(valeur: int) -> None:
    fichier = dossier_donnees() / FICHIER_REGLAGES
    try:
        fichier.write_text(json.dumps({"clics": valeur}), encoding="utf-8")
    except OSError:
        pass


class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Démo PyBuilder")
        self.resize(420, 240)
        self.compteur = charger_compteur()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(f"Clics enregistrés : {self.compteur}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bouton = QPushButton("Cliquer")
        bouton.clicked.connect(self.incrementer)

        layout.addWidget(self.label)
        layout.addWidget(bouton)
        self.setCentralWidget(central)

    def incrementer(self) -> None:
        self.compteur += 1
        self.label.setText(f"Clics enregistrés : {self.compteur}")
        enregistrer_compteur(self.compteur)


def main() -> int:
    app = QApplication(sys.argv)
    fenetre = Fenetre()
    fenetre.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

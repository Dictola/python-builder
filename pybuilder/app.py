"""Point d'entrée de l'application PyBuilder."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__


def main(argv: list[str] | None = None) -> int:
    """Lance l'interface graphique. Un chemin de script peut être passé en argument."""
    argv = list(sys.argv if argv is None else argv)

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("PyBuilder")

    from .ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    for argument in argv[1:]:
        if argument.lower().endswith((".py", ".pyw")):
            window._select_script(argument)
            break

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

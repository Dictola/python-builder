"""Fenêtre principale de PyBuilder."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, assets, builder, patcher, settings
from ..analyzer import ScriptReport, analyze
from ..models import PATCH_MODES, SPLASH_STRATEGIES, BuildConfig
from . import theme
from .widgets import (
    Card,
    ColorPicker,
    DataPairEditor,
    DropZone,
    ElidedLabel,
    FindingRow,
    ListEditor,
    LogConsole,
    PathEdit,
    SectionHeader,
    muted,
    scroll_page,
)

#: Pages de l'assistant : (libellé du menu, méthode de construction).
PAGES = (
    ("1  Script source", "_page_source"),
    ("2  Exécutable", "_page_executable"),
    ("3  Splash screen", "_page_splash"),
    ("4  Modifications", "_page_patch"),
    ("5  Options avancées", "_page_advanced"),
    ("6  Récapitulatif", "_page_summary"),
)

#: Explication affichée sous le choix de la stratégie de fermeture du splash.
STRATEGY_HELP = {
    "mainloop": "Le splash disparaît quand la fenêtre de l'application s'affiche. "
                "Recommandé pour les applications Qt et tkinter.",
    "imports": "Le splash disparaît dès que les imports du script sont terminés. "
               "Convient aux scripts console ou sans boucle d'évènements.",
    "timer": "Le splash disparaît après le délai de sécurité indiqué ci-dessous.",
    "manual": "Le splash reste affiché jusqu'à votre appel à pybuilder_close_splash() "
              "dans le code (le délai de sécurité est désactivé).",
}


class MainWindow(QMainWindow):
    """Assistant complet : analyse du script, réglages, puis construction."""

    def __init__(self) -> None:
        super().__init__()
        self.config = settings.load_config()
        self.report: ScriptReport | None = None
        self.plan: builder.BuildPlan | None = None
        self.runner = builder.BuildRunner(self)
        self.theme_name = settings.load_theme()
        self._loading = False
        self._last_output: Path | None = None
        self._pip_process = None

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self.setWindowTitle(f"{APP_NAME} — du script Python à l'exécutable")
        self.resize(1180, 820)
        self.setMinimumSize(QSize(940, 640))

        self._build_ui()
        self._connect_signals()
        self._apply_theme(self.theme_name)
        self._apply_config(self.config)
        self._restore_geometry()

        if self.config.script and Path(self.config.script).is_file():
            self._select_script(self.config.script, keep_settings=True)
        else:
            self._refresh_interpreters()
        self._schedule_preview()

    # ==================================================================
    # Construction de l'interface
    # ==================================================================
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_body())
        splitter.addWidget(self._build_console())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 220])
        layout.addWidget(splitter, 1)

        layout.addWidget(self._build_footer())
        self.setCentralWidget(root)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(74)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(14)

        logo = QLabel("P")
        logo.setObjectName("Logo")
        logo.setFixedSize(42, 42)
        layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        self.header_subtitle = QLabel("Aucun script sélectionné")
        self.header_subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.header_subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.profile_button = QPushButton("Profil")
        self.profile_button.setObjectName("Ghost")
        menu = QMenu(self)
        menu.addAction("Enregistrer le profil…", self._save_profile)
        menu.addAction("Charger un profil…", self._load_profile)
        menu.addSeparator()
        menu.addAction("Réinitialiser les réglages", self._reset_config)
        self.profile_button.setMenu(menu)

        self.theme_button = QPushButton("Thème clair")
        self.theme_button.setObjectName("Ghost")
        self.theme_button.clicked.connect(self._toggle_theme)

        self.help_button = QPushButton("Aide")
        self.help_button.setObjectName("Ghost")
        self.help_button.clicked.connect(self._show_help)

        for button in (self.profile_button, self.theme_button, self.help_button):
            layout.addWidget(button)
        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(200)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.pages = QStackedWidget()
        for label, factory in PAGES:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(0, 42))
            self.nav.addItem(item)
            self.pages.addWidget(getattr(self, factory)())
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        return body

    def _build_console(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 8)
        layout.setSpacing(8)

        row = QHBoxLayout()
        title = QLabel("Journal de construction")
        title.setObjectName("CardTitle")
        row.addWidget(title)
        row.addStretch(1)

        self.copy_log_button = QPushButton("Copier")
        self.copy_log_button.setObjectName("Ghost")
        self.copy_log_button.clicked.connect(self._copy_log)
        self.save_log_button = QPushButton("Enregistrer…")
        self.save_log_button.setObjectName("Ghost")
        self.save_log_button.clicked.connect(self._save_log)
        self.clear_log_button = QPushButton("Effacer")
        self.clear_log_button.setObjectName("Ghost")
        self.clear_log_button.clicked.connect(lambda: self.console.clear())
        for button in (self.copy_log_button, self.save_log_button, self.clear_log_button):
            row.addWidget(button)
        layout.addLayout(row)

        self.console = LogConsole()
        layout.addWidget(self.console, 1)
        return panel

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(78)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(16)

        status_box = QVBoxLayout()
        status_box.setSpacing(6)
        self.status_label = QLabel("Prêt.")
        self.status_label.setObjectName("StatusLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        status_box.addWidget(self.status_label)
        status_box.addWidget(self.progress)
        layout.addLayout(status_box, 1)

        self.open_button = QPushButton("Ouvrir le dossier")
        self.open_button.clicked.connect(self._open_output)
        self.open_button.setEnabled(False)

        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self.runner.cancel)
        self.cancel_button.setVisible(False)

        self.build_button = QPushButton("Construire l'exécutable")
        self.build_button.setObjectName("Primary")
        self.build_button.setMinimumWidth(220)
        self.build_button.clicked.connect(self._start_build)

        for button in (self.open_button, self.cancel_button, self.build_button):
            layout.addWidget(button)
        return footer

    # ==================================================================
    # Pages
    # ==================================================================
    def _page_source(self) -> QWidget:
        page, layout = self._page_shell(
            "Script source",
            "Choisissez le script Python à transformer en exécutable. "
            "PyBuilder l'analyse pour proposer les bonnes options.",
        )

        self.platform_card = Card(
            "Plateforme de construction",
            "PyInstaller ne fait pas de compilation croisée : l'exécutable produit correspond "
            "au système sur lequel PyBuilder tourne. Pour un .exe Windows, lancez PyBuilder sous Windows.",
        )
        self.platform_card.setVisible(sys.platform != "win32")
        layout.addWidget(self.platform_card)

        source_card = Card("Fichier à convertir")
        self.drop_zone = DropZone()
        source_card.add(self.drop_zone)
        self.script_label = ElidedLabel("Aucun fichier sélectionné")
        self.script_label.setObjectName("Muted")
        source_card.add(self.script_label)
        layout.addWidget(source_card)

        python_card = Card(
            "Interpréteur Python",
            "C'est cet interpréteur qui exécutera PyInstaller : il doit contenir les dépendances de votre script.",
        )
        self.interpreter_combo = QComboBox()
        self.interpreter_combo.setEditable(True)
        python_card.add_field("Interpréteur", self.interpreter_combo)

        row = QHBoxLayout()
        self.pyinstaller_label = QLabel("Vérification…")
        self.pyinstaller_label.setObjectName("Muted")
        self.install_button = QPushButton("Installer PyInstaller")
        self.install_button.clicked.connect(self._install_pyinstaller)
        self.install_button.setVisible(False)
        self.browse_python_button = QPushButton("Autre interpréteur…")
        self.browse_python_button.setObjectName("Ghost")
        self.browse_python_button.clicked.connect(self._browse_interpreter)
        row.addWidget(self.pyinstaller_label, 1)
        row.addWidget(self.install_button)
        row.addWidget(self.browse_python_button)
        python_card.add_layout(row)
        layout.addWidget(python_card)

        self.analysis_card = Card("Analyse du script", "Les constats ci-dessous guident les réglages proposés.")
        self.findings_box = QVBoxLayout()
        self.findings_box.setSpacing(4)
        self.analysis_card.add_layout(self.findings_box)
        self.suggest_button = QPushButton("Appliquer les options suggérées")
        self.suggest_button.clicked.connect(self._apply_suggestions)
        self.suggest_button.setEnabled(False)
        self.analysis_card.add(self.suggest_button)
        layout.addWidget(self.analysis_card)

        layout.addStretch(1)
        return scroll_page(page)

    def _page_executable(self) -> QWidget:
        page, layout = self._page_shell(
            "Exécutable",
            "Nom, destination et forme du fichier produit.",
        )

        card = Card("Identité")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("MonApplication")
        card.add_field("Nom de l'exécutable", self.name_edit, "Sans extension : « .exe » est ajouté sous Windows.")

        self.dist_edit = PathEdit("open_dir", "Dossier où sera écrit l'exécutable", caption="Dossier de destination")
        card.add_field("Dossier de destination", self.dist_edit)
        layout.addWidget(card)

        form_card = Card("Forme du programme")
        self.onefile_radio = QRadioButton("Un seul fichier (.exe autonome)")
        self.onedir_radio = QRadioButton("Un dossier (démarrage plus rapide)")
        form_card.add(self.onefile_radio)
        form_card.add(muted("Tout est embarqué dans un fichier unique, extrait dans un dossier temporaire au lancement."))
        form_card.add(self.onedir_radio)
        form_card.add(muted("L'exécutable est accompagné de ses bibliothèques dans un dossier à distribuer entier."))

        self.windowed_radio = QRadioButton("Application fenêtrée (sans console)")
        self.console_radio = QRadioButton("Application console (fenêtre de terminal visible)")
        form_card.add(self.windowed_radio)
        form_card.add(self.console_radio)

        # Sans groupes explicites, les quatre boutons partageraient la même exclusivité
        # (ils ont le même widget parent) et se décocheraient mutuellement.
        self.shape_group = QButtonGroup(self)
        self.shape_group.addButton(self.onefile_radio)
        self.shape_group.addButton(self.onedir_radio)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.windowed_radio)
        self.mode_group.addButton(self.console_radio)
        layout.addWidget(form_card)

        icon_card = Card("Icône")
        self.icon_edit = PathEdit(
            "open_file",
            "Fichier .ico, .png ou .jpg (facultatif)",
            "Images (*.ico *.png *.jpg *.jpeg *.bmp);;Tous les fichiers (*)",
            "Choisir une icône",
        )
        icon_card.add_field("Fichier d'icône", self.icon_edit, "Les images non .ico sont converties automatiquement.")
        self.icon_generate_check = QCheckBox("Générer une icône si aucun fichier n'est fourni")
        icon_card.add(self.icon_generate_check)

        preview_row = QHBoxLayout()
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(72, 72)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.icon_preview)
        preview_row.addWidget(muted("Aperçu de l'icône qui sera intégrée à l'exécutable."), 1)
        icon_card.add_layout(preview_row)
        layout.addWidget(icon_card)

        layout.addStretch(1)
        return scroll_page(page)

    def _page_splash(self) -> QWidget:
        page, layout = self._page_shell(
            "Splash screen",
            "L'écran affiché pendant le démarrage de l'exécutable, le temps que Python et les "
            "bibliothèques se chargent.",
        )

        self.splash_check = QCheckBox("Afficher un splash screen au lancement de l'exécutable")
        enable_card = Card()
        enable_card.add(self.splash_check)
        layout.addWidget(enable_card)

        self.splash_design_card = Card("Visuel", "Laissez le champ image vide pour que PyBuilder dessine le splash.")
        self.splash_image_edit = PathEdit(
            "open_file",
            "Image personnalisée (facultatif)",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;Tous les fichiers (*)",
            "Choisir l'image du splash",
        )
        self.splash_design_card.add_field("Image", self.splash_image_edit)

        self.splash_title_edit = QLineEdit()
        self.splash_title_edit.setPlaceholderText("Nom affiché (par défaut : nom de l'exécutable)")
        self.splash_design_card.add_field("Titre", self.splash_title_edit)

        self.splash_subtitle_edit = QLineEdit()
        self.splash_design_card.add_field("Sous-titre", self.splash_subtitle_edit)

        colors = QHBoxLayout()
        self.splash_color = ColorPicker()
        self.splash_dark_check = QCheckBox("Fond sombre")
        colors.addWidget(QLabel("Couleur d'accent"))
        colors.addWidget(self.splash_color)
        colors.addWidget(self.splash_dark_check)
        colors.addStretch(1)
        self.splash_design_card.add_layout(colors)

        self.splash_preview = QLabel()
        self.splash_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splash_preview.setMinimumHeight(200)
        self.splash_design_card.add(self.splash_preview)
        layout.addWidget(self.splash_design_card)

        self.splash_behaviour_card = Card("Comportement")
        self.splash_strategy_combo = QComboBox()
        for key, label in SPLASH_STRATEGIES.items():
            self.splash_strategy_combo.addItem(label, key)
        self.splash_behaviour_card.add_field("Fermeture du splash", self.splash_strategy_combo)
        self.strategy_hint = muted("")
        self.splash_behaviour_card.add(self.strategy_hint)

        timeout_row = QHBoxLayout()
        self.splash_timeout_spin = QDoubleSpinBox()
        self.splash_timeout_spin.setRange(1.0, 300.0)
        self.splash_timeout_spin.setSingleStep(5.0)
        self.splash_timeout_spin.setDecimals(0)
        self.splash_timeout_spin.setSuffix(" s")
        self.splash_timeout_spin.setFixedWidth(110)
        timeout_row.addWidget(QLabel("Délai de sécurité"))
        timeout_row.addWidget(self.splash_timeout_spin)
        timeout_row.addWidget(muted("Fermeture forcée du splash passé ce délai, pour ne jamais bloquer l'utilisateur."), 1)
        self.splash_behaviour_card.add_layout(timeout_row)

        self.splash_text_check = QCheckBox("Autoriser les messages d'état sur le splash (pybuilder_splash_text)")
        self.splash_top_check = QCheckBox("Garder le splash au premier plan")
        self.splash_behaviour_card.add(self.splash_text_check)
        self.splash_behaviour_card.add(self.splash_top_check)
        layout.addWidget(self.splash_behaviour_card)

        layout.addStretch(1)
        return scroll_page(page)

    def _page_patch(self) -> QWidget:
        page, layout = self._page_shell(
            "Modifications apportées au script",
            "PyBuilder injecte un bloc de code délimité par des marqueurs. Il est sans effet quand "
            "le script est lancé normalement, et réécrit à chaque construction.",
        )

        mode_card = Card("Mode d'application")
        self.patch_mode_combo = QComboBox()
        for key, label in PATCH_MODES.items():
            self.patch_mode_combo.addItem(label, key)
        mode_card.add_field("Fichier modifié", self.patch_mode_combo)
        mode_card.add(muted(
            "En mode copie, un fichier « _pybuilder_<script>.py » est créé à côté de l'original "
            "(pour que les imports voisins continuent de fonctionner) puis supprimé après la construction."
        ))
        self.keep_patched_check = QCheckBox("Conserver le script patché après la construction")
        mode_card.add(self.keep_patched_check)
        layout.addWidget(mode_card)

        options_card = Card("Code injecté")
        self.resource_check = QCheckBox("Helpers de chemins : pybuilder_resource_path() et pybuilder_app_dir()")
        self.freeze_check = QCheckBox("multiprocessing.freeze_support() si le script utilise multiprocessing")
        self.excepthook_check = QCheckBox("Journal et boîte de dialogue en cas d'erreur non rattrapée")
        for widget in (self.resource_check, self.freeze_check, self.excepthook_check):
            options_card.add(widget)
        layout.addWidget(options_card)

        preview_card = Card("Aperçu du bloc injecté")
        self.patch_preview = QPlainTextEdit()
        self.patch_preview.setObjectName("SpecView")
        self.patch_preview.setReadOnly(True)
        self.patch_preview.setMinimumHeight(260)
        self.patch_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        preview_card.add(self.patch_preview)
        layout.addWidget(preview_card)

        layout.addStretch(1)
        return scroll_page(page)

    def _page_advanced(self) -> QWidget:
        page, layout = self._page_shell(
            "Options avancées",
            "À utiliser quand l'exécutable se plaint d'un module ou d'un fichier manquant.",
        )

        modules_card = Card(
            "Modules",
            "« Imports cachés » pour les modules chargés dynamiquement ; « collect » pour embarquer "
            "tout un paquet (code, données, binaires).",
        )
        self.hidden_list = ListEditor("Import caché")
        self.collect_all_list = ListEditor("Paquet à embarquer entièrement")
        self.collect_data_list = ListEditor("Paquet dont il faut les données")
        self.collect_sub_list = ListEditor("Paquet dont il faut les sous-modules")
        self.excludes_list = ListEditor("Module à exclure")
        modules_card.add_field("Imports cachés (--hidden-import)", self.hidden_list)
        modules_card.add_field("Collecte complète (--collect-all)", self.collect_all_list)
        modules_card.add_field("Données de paquets (--collect-data)", self.collect_data_list)
        modules_card.add_field("Sous-modules (--collect-submodules)", self.collect_sub_list)
        modules_card.add_field("Modules exclus (--exclude-module)", self.excludes_list)
        layout.addWidget(modules_card)

        data_card = Card("Ressources embarquées", "Fichiers copiés dans l'exécutable et retrouvés avec pybuilder_resource_path().")
        self.data_editor = DataPairEditor()
        data_card.add_field("Fichiers de données (--add-data)", self.data_editor)
        self.binary_editor = DataPairEditor()
        data_card.add_field("Binaires (--add-binary)", self.binary_editor)
        layout.addWidget(data_card)

        build_card = Card("Construction")
        self.clean_check = QCheckBox("Nettoyer le cache PyInstaller avant de construire (--clean)")
        self.strip_check = QCheckBox("Retirer les symboles de débogage (--strip)")
        self.uac_check = QCheckBox("Demander les droits administrateur au lancement (Windows)")
        self.keep_spec_check = QCheckBox("Conserver le fichier .spec généré")
        for widget in (self.clean_check, self.strip_check, self.uac_check, self.keep_spec_check):
            build_card.add(widget)

        self.loglevel_combo = QComboBox()
        self.loglevel_combo.addItems(["TRACE", "DEBUG", "INFO", "WARN", "ERROR"])
        build_card.add_field("Niveau de journal PyInstaller", self.loglevel_combo)

        self.workdir_edit = PathEdit("open_dir", "Par défaut : dossier .pybuilder à côté du script", caption="Dossier de travail")
        build_card.add_field("Dossier de travail", self.workdir_edit)

        self.upx_edit = PathEdit("open_dir", "Dossier contenant upx (facultatif)", caption="Dossier UPX")
        build_card.add_field("Compression UPX", self.upx_edit, "Réduit la taille de l'exe ; certains antivirus s'en méfient.")

        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText("--noupx --upx-exclude vcruntime140.dll")
        build_card.add_field(
            "Arguments PyInstaller supplémentaires", self.extra_edit,
            "Seules les options compatibles avec un fichier .spec sont transmises."
        )
        layout.addWidget(build_card)

        version_card = Card("Informations de version (Windows)", "Visibles dans les propriétés du fichier .exe.")
        self.version_check = QCheckBox("Ajouter les informations de version")
        version_card.add(self.version_check)
        self.version_number_edit = QLineEdit()
        self.version_number_edit.setPlaceholderText("1.0.0.0")
        version_card.add_field("Version", self.version_number_edit)
        self.version_product_edit = QLineEdit()
        version_card.add_field("Nom du produit", self.version_product_edit)
        self.version_company_edit = QLineEdit()
        version_card.add_field("Société", self.version_company_edit)
        self.version_description_edit = QLineEdit()
        version_card.add_field("Description", self.version_description_edit)
        self.version_copyright_edit = QLineEdit()
        version_card.add_field("Copyright", self.version_copyright_edit)
        layout.addWidget(version_card)

        layout.addStretch(1)
        return scroll_page(page)

    def _page_summary(self) -> QWidget:
        page, layout = self._page_shell(
            "Récapitulatif",
            "Ce qui sera exécuté. Le fichier .spec peut être conservé et relancé sans PyBuilder.",
        )

        summary_card = Card("Résumé")
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_card.add(self.summary_label)
        layout.addWidget(summary_card)

        command_card = Card("Commande PyInstaller")
        self.command_view = QPlainTextEdit()
        self.command_view.setObjectName("SpecView")
        self.command_view.setReadOnly(True)
        self.command_view.setFixedHeight(90)
        command_card.add(self.command_view)
        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        copy_command = QPushButton("Copier la commande")
        copy_command.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.command_view.toPlainText()))
        copy_row.addWidget(copy_command)
        command_card.add_layout(copy_row)
        layout.addWidget(command_card)

        spec_card = Card("Fichier .spec généré")
        self.spec_view = QPlainTextEdit()
        self.spec_view.setObjectName("SpecView")
        self.spec_view.setReadOnly(True)
        self.spec_view.setMinimumHeight(300)
        self.spec_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        spec_card.add(self.spec_view)
        layout.addWidget(spec_card)

        layout.addStretch(1)
        return scroll_page(page)

    @staticmethod
    def _page_shell(title: str, hint: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        layout.addWidget(SectionHeader(title, hint))
        return page, layout

    # ==================================================================
    # Connexions
    # ==================================================================
    def _connect_signals(self) -> None:
        self.drop_zone.selected.connect(self._select_script)
        self.interpreter_combo.currentTextChanged.connect(self._on_interpreter_changed)
        self.splash_strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        self.splash_check.toggled.connect(self._on_splash_toggled)
        self.name_edit.textChanged.connect(self._schedule_preview)

        for widget in (
            self.name_edit, self.extra_edit, self.version_number_edit, self.version_product_edit,
            self.version_company_edit, self.version_description_edit, self.version_copyright_edit,
            self.splash_title_edit, self.splash_subtitle_edit,
        ):
            widget.textChanged.connect(self._schedule_preview)

        for widget in (
            self.dist_edit, self.icon_edit, self.splash_image_edit, self.workdir_edit, self.upx_edit,
        ):
            widget.changed.connect(self._schedule_preview)

        for widget in (
            self.onefile_radio, self.onedir_radio, self.windowed_radio, self.console_radio,
            self.icon_generate_check, self.splash_check, self.splash_dark_check, self.splash_text_check,
            self.splash_top_check, self.resource_check, self.freeze_check, self.excepthook_check,
            self.keep_patched_check, self.clean_check, self.strip_check, self.uac_check,
            self.keep_spec_check, self.version_check,
        ):
            widget.toggled.connect(self._schedule_preview)

        for widget in (self.splash_strategy_combo, self.patch_mode_combo, self.loglevel_combo):
            widget.currentIndexChanged.connect(self._schedule_preview)

        for widget in (
            self.hidden_list, self.collect_all_list, self.collect_data_list, self.collect_sub_list,
            self.excludes_list, self.data_editor, self.binary_editor,
        ):
            widget.changed.connect(self._schedule_preview)

        self.splash_color.colorChanged.connect(self._schedule_preview)
        self.splash_timeout_spin.valueChanged.connect(self._schedule_preview)

        self.runner.line.connect(self.console.log)
        self.runner.progress.connect(self._on_progress)
        self.runner.finished.connect(self._on_build_finished)

    # ==================================================================
    # Configuration <-> widgets
    # ==================================================================
    def _collect_config(self) -> BuildConfig:
        config = BuildConfig()
        config.script = self.config.script
        config.python_exe = self.interpreter_combo.currentText().strip()
        config.name = self.name_edit.text().strip()
        config.dist_dir = self.dist_edit.text()
        config.onefile = self.onefile_radio.isChecked()
        config.windowed = self.windowed_radio.isChecked()
        config.icon = self.icon_edit.text()
        config.icon_generate = self.icon_generate_check.isChecked()
        config.clean = self.clean_check.isChecked()
        config.strip_debug = self.strip_check.isChecked()
        config.uac_admin = self.uac_check.isChecked()
        config.upx_dir = self.upx_edit.text()

        config.splash_enabled = self.splash_check.isChecked()
        config.splash_image = self.splash_image_edit.text()
        config.splash_title = self.splash_title_edit.text()
        config.splash_subtitle = self.splash_subtitle_edit.text()
        config.splash_accent = self.splash_color.color()
        config.splash_dark = self.splash_dark_check.isChecked()
        config.splash_strategy = self.splash_strategy_combo.currentData() or "mainloop"
        config.splash_timeout = float(self.splash_timeout_spin.value())
        config.splash_show_text = self.splash_text_check.isChecked()
        config.splash_always_on_top = self.splash_top_check.isChecked()

        config.patch_mode = self.patch_mode_combo.currentData() or "copy"
        config.add_resource_helper = self.resource_check.isChecked()
        config.add_freeze_support = self.freeze_check.isChecked()
        config.add_excepthook = self.excepthook_check.isChecked()
        config.keep_patched = self.keep_patched_check.isChecked()

        config.hidden_imports = self.hidden_list.values()
        config.collect_all = self.collect_all_list.values()
        config.collect_data = self.collect_data_list.values()
        config.collect_submodules = self.collect_sub_list.values()
        config.excludes = self.excludes_list.values()
        config.add_data = self.data_editor.pairs()
        config.add_binary = self.binary_editor.pairs()
        config.extra_args = self.extra_edit.text()
        config.log_level = self.loglevel_combo.currentText()
        config.keep_spec = self.keep_spec_check.isChecked()
        config.work_dir = self.workdir_edit.text()

        config.version_enabled = self.version_check.isChecked()
        config.version_number = self.version_number_edit.text() or "1.0.0.0"
        config.version_product = self.version_product_edit.text()
        config.version_company = self.version_company_edit.text()
        config.version_description = self.version_description_edit.text()
        config.version_copyright = self.version_copyright_edit.text()
        return config

    def _apply_config(self, config: BuildConfig) -> None:
        self._loading = True
        try:
            self.name_edit.setText(config.name)
            self.dist_edit.setText(config.dist_dir)
            self.onefile_radio.setChecked(config.onefile)
            self.onedir_radio.setChecked(not config.onefile)
            self.windowed_radio.setChecked(config.windowed)
            self.console_radio.setChecked(not config.windowed)
            self.icon_edit.setText(config.icon)
            self.icon_generate_check.setChecked(config.icon_generate)
            self.clean_check.setChecked(config.clean)
            self.strip_check.setChecked(config.strip_debug)
            self.uac_check.setChecked(config.uac_admin)
            self.upx_edit.setText(config.upx_dir)

            self.splash_check.setChecked(config.splash_enabled)
            self.splash_image_edit.setText(config.splash_image)
            self.splash_title_edit.setText(config.splash_title)
            self.splash_subtitle_edit.setText(config.splash_subtitle)
            self.splash_color.set_color(config.splash_accent)
            self.splash_dark_check.setChecked(config.splash_dark)
            index = self.splash_strategy_combo.findData(config.splash_strategy)
            self.splash_strategy_combo.setCurrentIndex(max(0, index))
            self.splash_timeout_spin.setValue(config.splash_timeout)
            self.splash_text_check.setChecked(config.splash_show_text)
            self.splash_top_check.setChecked(config.splash_always_on_top)

            index = self.patch_mode_combo.findData(config.patch_mode)
            self.patch_mode_combo.setCurrentIndex(max(0, index))
            self.resource_check.setChecked(config.add_resource_helper)
            self.freeze_check.setChecked(config.add_freeze_support)
            self.excepthook_check.setChecked(config.add_excepthook)
            self.keep_patched_check.setChecked(config.keep_patched)

            self.hidden_list.set_values(config.hidden_imports)
            self.collect_all_list.set_values(config.collect_all)
            self.collect_data_list.set_values(config.collect_data)
            self.collect_sub_list.set_values(config.collect_submodules)
            self.excludes_list.set_values(config.excludes)
            self.data_editor.set_pairs(config.add_data)
            self.binary_editor.set_pairs(config.add_binary)
            self.extra_edit.setText(config.extra_args)
            self.loglevel_combo.setCurrentText(config.log_level)
            self.keep_spec_check.setChecked(config.keep_spec)
            self.workdir_edit.setText(config.work_dir)

            self.version_check.setChecked(config.version_enabled)
            self.version_number_edit.setText(config.version_number)
            self.version_product_edit.setText(config.version_product)
            self.version_company_edit.setText(config.version_company)
            self.version_description_edit.setText(config.version_description)
            self.version_copyright_edit.setText(config.version_copyright)

            if config.python_exe:
                self.interpreter_combo.setCurrentText(config.python_exe)
        finally:
            self._loading = False
        self._on_splash_toggled(config.splash_enabled)
        self._on_strategy_changed()

    # ==================================================================
    # Script : sélection et analyse
    # ==================================================================
    def _select_script(self, path: str, keep_settings: bool = False) -> None:
        script = Path(path)
        if not script.is_file():
            QMessageBox.warning(self, APP_NAME, f"Fichier introuvable :\n{path}")
            return

        self.config = self._collect_config()
        self.config.script = str(script)
        self.drop_zone.show_file(str(script))
        self.script_label.setText(str(script))
        self.header_subtitle.setText(script.name)
        settings.push_recent(str(script))

        if not keep_settings or not self.name_edit.text().strip():
            self.name_edit.setText(script.stem)
        if not self.dist_edit.text().strip():
            self.dist_edit.setText(str(script.parent / "dist"))
        if not self.splash_title_edit.text().strip():
            self.splash_title_edit.setText(script.stem)

        self._refresh_interpreters()
        self._run_analysis()
        self._schedule_preview()

    def _run_analysis(self) -> None:
        if not self.config.script:
            return
        self.report = analyze(self.config.script)
        while self.findings_box.count():
            item = self.findings_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for finding in self.report.findings:
            self.findings_box.addWidget(FindingRow(finding.level, finding.title, finding.detail))
        if not self.report.findings:
            self.findings_box.addWidget(muted("Rien à signaler."))

        self.suggest_button.setEnabled(self.report.ok)
        if self.report.gui and not self._loading:
            self.windowed_radio.setChecked(True)
        elif self.report.ok and not self.report.gui:
            self.console_radio.setChecked(True)

        strategy = "mainloop" if self.report.gui else "imports"
        index = self.splash_strategy_combo.findData(strategy)
        if index >= 0:
            self.splash_strategy_combo.setCurrentIndex(index)

        counts = self.report.counts()
        self.console.rule(f"Analyse de {Path(self.config.script).name}")
        for finding in self.report.findings:
            level = {"ok": "success", "info": "info", "warn": "warn", "error": "error"}[finding.level]
            self.console.log(f"  {finding.title}", level)
        self.status_label.setText(
            f"Analyse terminée : {counts['ok']} point(s) conforme(s), "
            f"{counts['info']} information(s), {counts['warn']} avertissement(s), {counts['error']} erreur(s)."
        )

    def _apply_suggestions(self) -> None:
        if self.report is None:
            return
        suggestions = self.report.suggestions
        self.hidden_list.extend(suggestions.get("hidden_imports", []))
        self.collect_all_list.extend(suggestions.get("collect_all", []))
        self.collect_data_list.extend(suggestions.get("collect_data", []))
        self.collect_sub_list.extend(suggestions.get("collect_submodules", []))
        self.excludes_list.extend(suggestions.get("excludes", []))

        base = Path(self.config.script).parent
        pairs = self.data_editor.pairs()
        known = {source for source, _ in pairs}
        for resource in self.report.data_files:
            if str(resource) in known:
                continue
            try:
                relative = resource.parent.relative_to(base)
                destination = str(relative) if str(relative) != "." else "."
            except ValueError:
                destination = "."
            pairs.append([str(resource), destination])
        self.data_editor.set_pairs(pairs)

        self.console.log("Options suggérées appliquées.", "success")
        self._schedule_preview()

    # ==================================================================
    # Interpréteur
    # ==================================================================
    def _refresh_interpreters(self) -> None:
        current = self.interpreter_combo.currentText().strip()
        candidates = builder.python_candidates(self.config.script or None)
        if current and current not in candidates:
            candidates.insert(0, current)
        self._loading = True
        self.interpreter_combo.clear()
        self.interpreter_combo.addItems(candidates)
        if current:
            self.interpreter_combo.setCurrentText(current)
        self._loading = False
        self._check_pyinstaller()

    def _browse_interpreter(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un interpréteur Python", "", "Exécutables (*)")
        if path:
            self.interpreter_combo.insertItem(0, path)
            self.interpreter_combo.setCurrentIndex(0)

    def _on_interpreter_changed(self) -> None:
        if self._loading:
            return
        self._check_pyinstaller()
        self._schedule_preview()

    def _check_pyinstaller(self) -> None:
        python_exe = self.interpreter_combo.currentText().strip() or sys.executable
        if not Path(python_exe).exists():
            self.pyinstaller_label.setText(f"Interpréteur introuvable : {python_exe}")
            self.install_button.setVisible(False)
            return
        ok, message = builder.pyinstaller_version(python_exe)
        if ok:
            self.pyinstaller_label.setText(f"PyInstaller {message} détecté.")
            self.install_button.setVisible(False)
        else:
            self.pyinstaller_label.setText("PyInstaller n'est pas installé dans cet interpréteur.")
            self.install_button.setVisible(True)

    def _install_pyinstaller(self) -> None:
        from PySide6.QtCore import QProcess

        python_exe = self.interpreter_combo.currentText().strip() or sys.executable
        self.console.rule("Installation de PyInstaller")
        self.install_button.setEnabled(False)

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda: self.console.log(bytes(process.readAllStandardOutput()).decode("utf-8", "replace").rstrip())
        )
        process.finished.connect(lambda code, _status: self._on_pip_finished(code))
        self._pip_process = process
        process.start(python_exe, ["-m", "pip", "install", "--upgrade", "pyinstaller"])

    def _on_pip_finished(self, code: int) -> None:
        self.install_button.setEnabled(True)
        self.console.log(
            "PyInstaller installé." if code == 0 else f"L'installation a échoué (code {code}).",
            "success" if code == 0 else "error",
        )
        self._check_pyinstaller()

    # ==================================================================
    # Aperçus
    # ==================================================================
    def _schedule_preview(self) -> None:
        if not self._loading:
            self._preview_timer.start()

    def _refresh_preview(self) -> None:
        config = self._collect_config()
        self.config = config

        if config.splash_enabled and not config.splash_image:
            image, _pos = assets.render_splash(
                config.splash_title or config.exe_name,
                config.splash_subtitle,
                config.splash_accent,
                config.splash_dark,
            )
            pixmap = QPixmap.fromImage(image).scaledToWidth(420, Qt.TransformationMode.SmoothTransformation)
            self.splash_preview.setPixmap(pixmap)
        elif config.splash_enabled and Path(config.splash_image).is_file():
            pixmap = QPixmap(config.splash_image)
            if not pixmap.isNull():
                self.splash_preview.setPixmap(pixmap.scaledToWidth(420, Qt.TransformationMode.SmoothTransformation))
        else:
            self.splash_preview.clear()
            self.splash_preview.setText("Splash screen désactivé.")

        icon_image = None
        if config.icon and Path(config.icon).is_file() and Path(config.icon).suffix.lower() != ".ico":
            icon_pixmap = QPixmap(config.icon)
            self.icon_preview.setPixmap(icon_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        elif config.icon and Path(config.icon).is_file():
            self.icon_preview.setPixmap(QIcon(config.icon).pixmap(64, 64))
        elif config.icon_generate:
            icon_image = assets.render_icon(config.exe_name, config.splash_accent, 128)
            self.icon_preview.setPixmap(QPixmap.fromImage(icon_image).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_preview.clear()

        if self.report is not None:
            self.patch_preview.setPlainText(patcher.build_header(config, self.report))
        else:
            self.patch_preview.setPlainText("Sélectionnez un script pour voir le code qui sera injecté.")

        try:
            command, spec_text = builder.preview_texts(config, self.report)
        except (OSError, ValueError) as exc:
            command, spec_text = f"# Aperçu indisponible : {exc}", ""
        self.command_view.setPlainText(command)
        self.spec_view.setPlainText(spec_text)
        self.summary_label.setText(self._summary_html(config))

    def _summary_html(self, config: BuildConfig) -> str:
        def row(label: str, value: str) -> str:
            return f"<tr><td style='padding:3px 18px 3px 0; color:#8b98ab'>{label}</td><td>{value}</td></tr>"

        script = config.script or "—"
        target = "fichier unique" if config.onefile else "dossier"
        mode = "fenêtrée" if config.windowed else "console"
        splash = "désactivé"
        if config.splash_enabled:
            source = Path(config.splash_image).name if config.splash_image else "généré par PyBuilder"
            splash = f"{source} — {SPLASH_STRATEGIES.get(config.splash_strategy, '')}"
        rows = [
            row("Script", script),
            row("Exécutable", f"{config.exe_name} ({target}, application {mode})"),
            row("Destination", config.dist_dir or "—"),
            row("Splash screen", splash),
            row("Patch", PATCH_MODES.get(config.patch_mode, "")),
            row("Interpréteur", config.python_exe or sys.executable),
        ]
        return "<table>" + "".join(rows) + "</table>"

    # ==================================================================
    # Construction
    # ==================================================================
    def _start_build(self) -> None:
        if self.runner.running:
            return
        config = self._collect_config()
        self.config = config

        problems = config.validate()
        if problems:
            QMessageBox.warning(self, APP_NAME, "Corrigez d'abord :\n\n• " + "\n• ".join(problems))
            return
        if self.report is None or not self.report.ok:
            self._run_analysis()
        if self.report is not None and not self.report.ok:
            QMessageBox.critical(self, APP_NAME, f"Le script contient une erreur de syntaxe :\n{self.report.syntax_error}")
            return

        ok, message = builder.pyinstaller_version(config.python_exe or sys.executable)
        if not ok:
            QMessageBox.warning(self, APP_NAME, f"PyInstaller n'est pas utilisable :\n{message}")
            return

        settings.save_config(config)
        self.console.rule("Préparation")
        try:
            self.plan = builder.prepare(config, self.report)
        except (OSError, ValueError, RuntimeError) as exc:
            self.console.log(f"Préparation impossible : {exc}", "error")
            QMessageBox.critical(self, APP_NAME, f"Préparation impossible :\n{exc}")
            return

        for note in self.plan.notes:
            self.console.log(f"  {note}", "muted")
        for warning in self.plan.warnings:
            self.console.log(f"  {warning}", "warn")
        self.console.log(f"  Fichier .spec : {self.plan.spec_path}", "muted")
        self.console.rule("PyInstaller")
        self.console.log(self.plan.command_line, "accent")

        self._set_building(True)
        self.runner.start(self.plan)

    def _set_building(self, building: bool) -> None:
        self.build_button.setEnabled(not building)
        self.build_button.setText("Construction en cours…" if building else "Construire l'exécutable")
        self.cancel_button.setVisible(building)
        self.nav.setEnabled(not building)
        self.pages.setEnabled(not building)
        if building:
            self.open_button.setEnabled(False)
            self.progress.setValue(0)
            # L'avancement se déduit du journal : sans les lignes INFO, on affiche
            # une barre indéterminée plutôt qu'une progression figée.
            if self.config.log_level not in ("TRACE", "DEBUG", "INFO"):
                self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def _on_progress(self, percent: int, label: str) -> None:
        if self.progress.maximum() != 0:
            self.progress.setValue(percent)
        self.status_label.setText(f"{label}… {percent} %")

    def _on_build_finished(self, success: bool, message: str) -> None:
        self._set_building(False)
        if not success:
            self.progress.setValue(0)
            self.status_label.setText(message)
            self.console.log(message, "error")
            self.console.log(
                "Conseil : relancez avec le niveau de journal DEBUG, ou construisez en mode console "
                "pour lire l'erreur au démarrage de l'exe.",
                "muted",
            )
            return

        path_text, _, size_text = message.partition("|")
        output = Path(path_text)
        self._last_output = output
        size_mb = int(size_text or 0) / (1024 * 1024)
        self.progress.setValue(100)
        self.status_label.setText(f"Terminé : {output.name} ({size_mb:.1f} Mo)")
        self.console.log(f"Exécutable créé : {output}  ({size_mb:.1f} Mo)", "success")
        self.open_button.setEnabled(True)
        settings.save_config(self.config)

    def _open_output(self) -> None:
        target = self._last_output or Path(self.dist_edit.text())
        folder = target if target.is_dir() else target.parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ==================================================================
    # Réglages d'affichage et profils
    # ==================================================================
    def _on_splash_toggled(self, enabled: bool) -> None:
        self.splash_design_card.setEnabled(enabled)
        self.splash_behaviour_card.setEnabled(enabled)

    def _on_strategy_changed(self) -> None:
        strategy = self.splash_strategy_combo.currentData() or "mainloop"
        self.strategy_hint.setText(STRATEGY_HELP.get(strategy, ""))
        self.splash_timeout_spin.setEnabled(strategy != "manual")

    def _apply_theme(self, name: str) -> None:
        self.theme_name = name
        colors = theme.palette(name)
        self.setStyleSheet(
            theme.stylesheet(colors, assets.checkmark_icon(colors.accent_text), assets.caret_icon(colors.muted))
        )
        self.theme_button.setText("Thème clair" if name == "dark" else "Thème sombre")
        icon = assets.render_icon("P", colors.accent, 128)
        self.setWindowIcon(QIcon(QPixmap.fromImage(icon)))
        settings.save_theme(name)

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self.theme_name == "dark" else "dark")

    def _save_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le profil", "pybuilder.json", "Profil JSON (*.json)")
        if not path:
            return
        config = self._collect_config()
        config.save(path)
        self.console.log(f"Profil enregistré : {path}", "success")

    def _load_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger un profil", "", "Profil JSON (*.json)")
        if not path:
            return
        try:
            config = BuildConfig.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Profil illisible :\n{exc}")
            return
        self.config = config
        self._apply_config(config)
        if config.script and Path(config.script).is_file():
            self._select_script(config.script, keep_settings=True)
        self.console.log(f"Profil chargé : {path}", "success")
        self._schedule_preview()

    def _reset_config(self) -> None:
        answer = QMessageBox.question(self, APP_NAME, "Réinitialiser tous les réglages ?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        script = self.config.script
        self.config = BuildConfig(script=script)
        self._apply_config(self.config)
        self._schedule_preview()

    def _copy_log(self) -> None:
        QGuiApplication.clipboard().setText(self.console.toPlainText())
        self.console.log("Journal copié dans le presse-papiers.", "muted")

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le journal", "pybuilder.log", "Journal (*.log *.txt)")
        if path:
            Path(path).write_text(self.console.toPlainText(), encoding="utf-8")

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            f"{APP_NAME} {__version__}",
            "<b>PyBuilder</b> prépare un script Python pour PyInstaller, puis construit l'exécutable.<br><br>"
            "<b>Fonctions ajoutées à votre script :</b><br>"
            "• <code>pybuilder_close_splash()</code> — ferme le splash screen<br>"
            "• <code>pybuilder_splash_text(\"…\")</code> — affiche un message d'état sur le splash<br>"
            "• <code>pybuilder_resource_path(\"data\", \"fichier.csv\")</code> — chemin d'une ressource embarquée<br>"
            "• <code>pybuilder_app_dir()</code> — dossier de l'exécutable, pour lire ou écrire à côté<br><br>"
            "Le bloc injecté est entouré de marqueurs et ne gêne pas l'exécution normale du script.",
        )

    # ==================================================================
    # Fenêtre
    # ==================================================================
    def _restore_geometry(self) -> None:
        geometry = settings.load_geometry()
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self.runner.running:
            answer = QMessageBox.question(self, APP_NAME, "Une construction est en cours. L'interrompre et quitter ?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.cancel()
        settings.save_geometry(self.saveGeometry())
        settings.save_config(self._collect_config())
        super().closeEvent(event)

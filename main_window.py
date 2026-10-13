import os
import sys
import json
import time
import random
import webbrowser
from urllib.parse import unquote

from PySide6.QtCore import Qt, Slot, QTimer, QUrl
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
    QLabel, QSplitter, QMessageBox, QFrame, QComboBox, QSpinBox,
    QStackedWidget, QTabWidget, QSizePolicy, QStatusBar, QMenuBar, QMenu
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from database_manager import verify_and_update_db, check_all_databases_status, get_nmrexp_path
from nmrexp_manager import NMRexpManager
from search_worker import SearchWorker
from viewer_3d import Molecule3DWidget, Molecule3DDialog
from viewer_spectrum import SpectrumViewerWidget
from viewer_ms import MSViewerWidget
from logbook_widget import LogbookWidget
from logbook_manager import logbook_manager
from mona_manager import MonaManager
from auto_assignment_engine import auto_assignment_engine
from i18n import t, get_current_language, set_current_language
from settings_dialog import SettingsDialog
from config_manager import (
    get_search_nucleus, set_search_nucleus,
    get_search_mode, set_search_mode,
    get_max_hits, set_max_hits
)


ACTION_INTERCEPTOR_SCRIPT = """
    <script>
    function hgttdAction(cmd, param) {
        console.log("HGTTD_ACTION:" + cmd + (param !== undefined ? ":" + param : ""));
    }
    function setupHgttdListeners() {
        document.addEventListener("click", function(e) {
            let el = e.target.closest("a");
            if (el) {
                let href = el.getAttribute("href");
                if (href) {
                    if (href.startsWith("action:")) {
                        e.preventDefault();
                        console.log("HGTTD_ACTION:" + href.substring(7));
                    } else if (href.startsWith("http://") || href.startsWith("https://")) {
                        e.preventDefault();
                        console.log("HGTTD_ACTION:open_external_url:" + href);
                    }
                }
            }
        });
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupHgttdListeners);
    } else {
        setupHgttdListeners();
    }
    </script>
"""

class CustomWebEnginePage(QWebEnginePage):
    """
    Custom WebEnginePage to intercept navigation and UI actions:
    - action:... schemes trigger Python callbacks via console message.
    - external http/https links (like DOIs) open in the user's default browser.
    """
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if message.startswith("HGTTD_ACTION:"):
            action = message[len("HGTTD_ACTION:"):]
            self.parent_window.handle_web_action(action)
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        url_str = url.toString()
        if url_str.startswith("action:"):
            self.parent_window.handle_web_action(url_str)
            return False
        elif url_str.startswith("http://") or url_str.startswith("https://"):
            if "localhost" not in url_str and "127.0.0.1" not in url_str:
                self.parent_window.handle_web_action("open_external_url:" + url_str)
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, window_type):
        class ExternalLinkPage(QWebEnginePage):
            def __init__(self, parent_page):
                super().__init__(parent_page)
                self.parent_page = parent_page
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                url_str = url.toString()
                if url_str and (url_str.startswith("http://") or url_str.startswith("https://")):
                    if "localhost" not in url_str and "127.0.0.1" not in url_str:
                        self.parent_page.parent_window.handle_web_action("open_external_url:" + url_str)
                return False
        return ExternalLinkPage(self)


class ModernMainWindow(QMainWindow):
    def __init__(self, ketcher_url):
        super().__init__()
        self.ketcher_url = ketcher_url
        self.db_path = None
        self.parquet_path = get_nmrexp_path()
        self.search_worker = None
        
        # Managers
        self.nmrexp_mgr = NMRexpManager(self.parquet_path)
        
        # State
        self.current_mode = "search" # "search" or "browse"
        self.current_page_type = "welcome"
        self.current_nucleus_filter = "all"
        self.current_browse_index = 0
        self.current_browse_total = self.nmrexp_mgr.get_count_for_nucleus("all")
        self.current_record = None
        self.last_results = None
        self.last_search_mode = "exact"
        self.last_search_nucleus = "all"

        # Polling timer for Ketcher async JS Promise
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self.poll_smiles_variable)
        self.poll_attempts = 0
        
        # Window setup
        self.setWindowTitle("HGTTD")
        self.resize(1500, 950)
        
        # Window Icon
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ico_file = os.path.join(base_dir, "assets", "hgttd_icon.ico")
        png_file = os.path.join(base_dir, "assets", "hgttd_icon.png")
        if os.path.exists(ico_file):
            self.setWindowIcon(QIcon(ico_file))
        elif os.path.exists(png_file):
            self.setWindowIcon(QIcon(png_file))
        
        self.setup_ui()
        self.retranslate_ui()
        self.check_database()

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.setup_menu_bar()

        # Header / Control Bar (clean streamlined action bar)
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Main Splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1e293b;
                width: 3px;
            }
        """)
        
        # Left pane: Ketcher View
        self.ketcher_view = QWebEngineView()
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.ketcher_view.setUrl(QUrl(self.ketcher_url))
        self.main_splitter.addWidget(self.ketcher_view)
        
        # Right pane: Tabbed Results & 3D Viewer
        self.right_tabs = QTabWidget()
        self.right_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #0b1120;
            }
            QTabBar::tab {
                background: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-bottom: none;
                padding: 8px 20px;
                font-weight: 600;
                font-size: 13px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0f172a;
                color: #38bdf8;
                border-color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
            }
            QTabBar::tab:hover:!selected {
                background: #334155;
                color: #f1f5f9;
            }
        """)
        
        # Tab 0: Results / Browser View
        self.results_view = QWebEngineView()
        self.custom_page = CustomWebEnginePage(self)
        self.results_view.setPage(self.custom_page)
        self.right_tabs.addTab(self.results_view, t("tab_details"))

        # Tab 1: Embedded 3D Molecule Viewer with Force Field Minimization
        self.viewer_3d_widget = Molecule3DWidget(self)
        self.viewer_3d_widget.load_to_ketcher_requested.connect(self.send_smiles_to_ketcher)
        self.viewer_3d_widget.switch_to_details_requested.connect(lambda: self.right_tabs.setCurrentIndex(0))
        self.right_tabs.addTab(self.viewer_3d_widget, t("tab_3d"))

        # Tab 2: Embedded Synthesized NMR Spectrum Viewer
        self.viewer_spectrum_widget = SpectrumViewerWidget(self)
        self.viewer_spectrum_widget.switch_to_details_requested.connect(lambda: self.right_tabs.setCurrentIndex(0))
        self.viewer_spectrum_widget.highlight_atoms_requested.connect(self.on_spectrum_highlight_atoms)
        self.right_tabs.addTab(self.viewer_spectrum_widget, t("tab_spectrum"))

        # Tab 3: Embedded MS Stick Spectrum Viewer (MoNa)
        self.viewer_ms_widget = MSViewerWidget(self)
        self.viewer_ms_widget.switch_to_details_requested.connect(lambda: self.right_tabs.setCurrentIndex(0))
        self.right_tabs.addTab(self.viewer_ms_widget, t("tab_ms_spectrum"))

        # Tab 4: Persistent Research Logbook & Bookmarks
        self.logbook_widget = LogbookWidget(self)
        self.logbook_widget.load_to_ketcher_requested.connect(self.send_smiles_to_ketcher)
        self.logbook_widget.open_3d_requested.connect(self.show_molecule_in_3d)
        self.logbook_widget.open_spectrum_requested.connect(self.show_spectrum)
        self.right_tabs.addTab(self.logbook_widget, t("tab_logbook"))
        
        self.right_tabs.currentChanged.connect(self.on_tab_changed)

        self.show_welcome_page()
        self.main_splitter.addWidget(self.right_tabs)
        
        # Splitter behavior: allow both sides to resize nicely, right side gets stretch factor
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 6)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        
        # Initial sizing: 45% Ketcher, 55% Details/Viewers
        initial_w = self.width() if self.width() > 0 else 1500
        min_ketcher_w = int(initial_w / 3)
        self.ketcher_view.setMinimumWidth(min_ketcher_w)
        self.right_tabs.setMinimumWidth(400)
        self.main_splitter.setSizes([int(initial_w * 0.45), int(initial_w * 0.55)])
        self.main_splitter.splitterMoved.connect(self.on_splitter_moved)
        main_layout.addWidget(self.main_splitter)

        # Setup modern dark status bar (footer)
        self.setup_status_bar()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._enforce_splitter_proportions()

    def on_splitter_moved(self, pos, index):
        self._enforce_splitter_proportions()

    def _enforce_splitter_proportions(self):
        if hasattr(self, 'ketcher_view') and hasattr(self, 'main_splitter'):
            total_w = self.main_splitter.width()
            if total_w <= 0:
                total_w = self.width()
            min_ketcher_w = max(350, int(total_w / 3))
            self.ketcher_view.setMinimumWidth(min_ketcher_w)
            sizes = self.main_splitter.sizes()
            if len(sizes) == 2 and total_w > min_ketcher_w + 300:
                if sizes[0] < min_ketcher_w:
                    diff = min_ketcher_w - sizes[0]
                    self.main_splitter.setSizes([min_ketcher_w, max(300, sizes[1] - diff)])

    def setup_menu_bar(self):
        """Creates a classic, elegant menu bar (Datei, Ansicht, Extras, Hilfe)."""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #0b1120;
                color: #e2e8f0;
                border-bottom: 1px solid #1e293b;
                font-size: 13px;
                padding: 2px 8px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 5px 12px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: #1e293b;
                color: #38bdf8;
            }
            QMenu {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 0;
            }
            QMenu::item {
                padding: 6px 24px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
                margin: 4px 10px;
            }
        """)

        # Menu: Datei (File)
        self.menu_file = menubar.addMenu(t("menu_file"))
        
        self.action_home = QAction(t("btn_home"), self)
        self.action_home.setShortcut("Ctrl+H")
        self.action_home.triggered.connect(self.show_welcome_page)
        self.menu_file.addAction(self.action_home)

        self.action_settings = QAction(t("btn_settings"), self)
        self.action_settings.setShortcut("Ctrl+,")
        self.action_settings.triggered.connect(self.open_settings)
        self.menu_file.addAction(self.action_settings)

        self.menu_file.addSeparator()

        self.action_exit = QAction(f"❌ {t('menu_exit')}", self)
        self.action_exit.setShortcut("Ctrl+Q")
        self.action_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.action_exit)

        # Menu: Ansicht (View)
        self.menu_view = menubar.addMenu(t("menu_view"))
        
        self.action_mode_search = QAction(t("btn_search_mode"), self)
        self.action_mode_search.setShortcut("Ctrl+F")
        self.action_mode_search.triggered.connect(self.set_search_mode)
        self.menu_view.addAction(self.action_mode_search)

        self.action_mode_browse = QAction(t("btn_browse_mode"), self)
        self.action_mode_browse.setShortcut("Ctrl+B")
        self.action_mode_browse.triggered.connect(self.set_browse_mode)
        self.menu_view.addAction(self.action_mode_browse)

        self.menu_view.addSeparator()

        self.action_tab_details = QAction(t("tab_details"), self)
        self.action_tab_details.setShortcut("Alt+1")
        self.action_tab_details.triggered.connect(lambda: self.right_tabs.setCurrentIndex(0))
        self.menu_view.addAction(self.action_tab_details)

        self.action_tab_3d = QAction(t("tab_3d"), self)
        self.action_tab_3d.setShortcut("Alt+2")
        self.action_tab_3d.triggered.connect(lambda: self.right_tabs.setCurrentIndex(1))
        self.menu_view.addAction(self.action_tab_3d)

        self.action_tab_spec = QAction(t("tab_spectrum"), self)
        self.action_tab_spec.setShortcut("Alt+3")
        self.action_tab_spec.triggered.connect(lambda: self.right_tabs.setCurrentIndex(2))
        self.menu_view.addAction(self.action_tab_spec)

        self.action_tab_ms = QAction(t("tab_ms_spectrum"), self)
        self.action_tab_ms.setShortcut("Alt+4")
        self.action_tab_ms.triggered.connect(lambda: self.right_tabs.setCurrentIndex(3))
        self.menu_view.addAction(self.action_tab_ms)

        self.action_tab_logbook = QAction(t("tab_logbook"), self)
        self.action_tab_logbook.setShortcut("Alt+5")
        self.action_tab_logbook.triggered.connect(lambda: self.right_tabs.setCurrentIndex(4))
        self.menu_view.addAction(self.action_tab_logbook)

        # Menu: Extras (Database & Tools)
        self.menu_tools = menubar.addMenu(t("db_status_btn"))
        self.action_check_db = QAction(f"🔄 {t('menu_check_db')}", self)
        self.action_check_db.setShortcut("F5")
        self.action_check_db.triggered.connect(self.check_database)
        self.menu_tools.addAction(self.action_check_db)

        # Menu: Hilfe (Help)
        self.menu_help = menubar.addMenu(t("menu_help"))
        self.action_guide = QAction(t("btn_home"), self)
        self.action_guide.triggered.connect(self.show_welcome_page)
        self.menu_help.addAction(self.action_guide)

        self.action_about = QAction(f"ℹ️ {t('menu_about')}", self)
        self.action_about.triggered.connect(self.show_about_dialog)
        self.menu_help.addAction(self.action_about)

    def show_about_dialog(self):
        QMessageBox.about(
            self,
            "HGTTD • Hitchhiker's Guide through the database",
            "<h3>🌌 HGTTD</h3>"
            "<p><strong>Hitchhiker's Guide through the database</strong></p>"
            "<p>Ein modernes Werkzeug zur Erforschung experimenteller NMR- und MS-Spektren "
            "(NMRexp, nmrshiftdb2 und MoNa MassBank) mit interaktiver Struktur- und Substruktursuche, "
            "3D-Kraftfeldminimierung und est-NMR Auto-Zuordnung.</p>"
            "<p style='color:#38bdf8;'><em>Don't Panic! • Die Antwort ist 42</em></p>"
        )

    def setup_status_bar(self):
        """Sets up an informative, clean bottom status bar (footer)."""
        status_bar = self.statusBar()
        status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #070b14;
                color: #94a3b8;
                border-top: 1px solid #1e293b;
                font-size: 12px;
                min-height: 28px;
                max-height: 28px;
                padding: 0 8px;
            }
            QStatusBar::item {
                border: none;
            }
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: 1px solid transparent;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #334155;
                color: #38bdf8;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 12px;
            }
        """)

        # Left: Main status message (e.g. database status, search progress)
        self.status_label = QLabel(t("db_checking"))
        self.status_label.setStyleSheet("color: #cbd5e1; padding-left: 6px;")
        status_bar.addWidget(self.status_label, stretch=1)

        # Right: Quick DB refresh icon button
        self.update_db_btn = QPushButton("🔄 DB")
        self.update_db_btn.setToolTip(t("footer_db_tip"))
        self.update_db_btn.clicked.connect(self.check_database)
        status_bar.addPermanentWidget(self.update_db_btn)

        # Right: Language switch button
        lang_code = get_current_language()
        self.btn_lang = QPushButton("🇩🇪 DE" if lang_code == "de" else "🇬🇧 EN")
        self.btn_lang.setToolTip(t("footer_lang_tip"))
        self.btn_lang.clicked.connect(self.toggle_language)
        status_bar.addPermanentWidget(self.btn_lang)

        # Right: Settings button
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setToolTip(t("footer_settings_tip"))
        self.btn_settings.clicked.connect(self.open_settings)
        status_bar.addPermanentWidget(self.btn_settings)

    def create_header(self):
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setStyleSheet("""
            QFrame#HeaderBar {
                background-color: #0b1120;
                border-bottom: 2px solid #1e293b;
                min-height: 52px;
                max-height: 52px;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton.active-mode {
                background-color: #38bdf8;
                color: #041426;
                border-color: #7dd3fc;
                font-weight: bold;
            }
            QPushButton#SearchBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
            }
            QPushButton#SearchBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#HomeBtn {
                background-color: #0f172a;
                color: #38bdf8;
                border: 1px solid #0284c7;
                font-weight: bold;
            }
            QPushButton#HomeBtn:hover {
                background-color: #1e293b;
            }
            QPushButton#StopBtn {
                background-color: #dc2626;
                color: #ffffff;
                border: 1px solid #ef4444;
                font-weight: bold;
            }
            QPushButton#StopBtn:hover {
                background-color: #b91c1c;
            }
            QComboBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                min-width: 95px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #2563eb;
                border: 1px solid #334155;
            }
            QSpinBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
                min-width: 80px;
            }
        """)
        
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(10)
        
        # Compact Brand Icon / Title
        brand_box = QHBoxLayout()
        brand_box.setSpacing(8)
        brand_box.setContentsMargins(0, 4, 0, 4)
        
        title_label = QLabel("HGTTD")
        title_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #38bdf8; letter-spacing: 1px;")
        brand_box.addWidget(title_label)
        header_layout.addLayout(brand_box)
        
        header_layout.addSpacing(6)
        
        # Navigation / Mode Buttons
        self.btn_home = QPushButton(t("btn_home"), objectName="HomeBtn")
        self.btn_home.clicked.connect(self.show_welcome_page)
        header_layout.addWidget(self.btn_home)

        self.btn_search_mode = QPushButton("🔍 Struktursuche")
        self.btn_search_mode.clicked.connect(self.set_search_mode)
        header_layout.addWidget(self.btn_search_mode)
        
        self.btn_browse_mode = QPushButton("🌌 NMRexp Blättern")
        self.btn_browse_mode.clicked.connect(self.set_browse_mode)
        header_layout.addWidget(self.btn_browse_mode)

        header_layout.addSpacing(10)

        # Mode Specific Stack
        self.mode_stack = QStackedWidget()
        
        # Page 0: Search Controls
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        
        # 1. Source Combo
        self.label_source = QLabel(t("source_label"))
        search_layout.addWidget(self.label_source)
        self.source_combo = QComboBox()
        self.source_combo.setStyleSheet("min-width: 110px;")
        self.source_combo.addItem(t("source_both"), "both")
        self.source_combo.addItem(t("source_nmrexp"), "nmrexp")
        self.source_combo.addItem(t("source_nmrshiftdb2"), "nmrshiftdb2")
        self.source_combo.addItem(t("source_mona"), "mona")
        self.source_combo.addItem(t("source_all"), "all")
        search_layout.addWidget(self.source_combo)

        # 2. Nucleus Filter Combo
        self.label_search_nucleus = QLabel(t("search_nucleus_label"))
        search_layout.addWidget(self.label_search_nucleus)
        self.search_nucleus_combo = QComboBox()
        self.search_nucleus_combo.setStyleSheet("min-width: 95px;")
        self.search_nucleus_combo.addItem(t("nuc_all"), "all")
        self.search_nucleus_combo.addItem(t("nuc_1h"), "1H")
        self.search_nucleus_combo.addItem(t("nuc_13c"), "13C")
        self.search_nucleus_combo.addItem(t("nuc_19f"), "19F")
        self.search_nucleus_combo.addItem(t("nuc_31p"), "31P")
        self.search_nucleus_combo.addItem(t("nuc_11b"), "11B")
        self.search_nucleus_combo.addItem(t("nuc_29si"), "29Si")
        cfg_nucleus = get_search_nucleus()
        idx_nuc = self.search_nucleus_combo.findData(cfg_nucleus)
        if idx_nuc >= 0:
            self.search_nucleus_combo.setCurrentIndex(idx_nuc)
        self.search_nucleus_combo.currentIndexChanged.connect(self.on_search_nucleus_changed)
        search_layout.addWidget(self.search_nucleus_combo)

        # 3. Search Mode Combo (Exact / Substructure / Similarity)
        self.label_search_mode = QLabel(t("search_mode_label"))
        search_layout.addWidget(self.label_search_mode)
        self.search_mode_combo = QComboBox()
        self.search_mode_combo.setStyleSheet("min-width: 105px;")
        self.search_mode_combo.addItem(t("mode_exact"), "exact")
        self.search_mode_combo.addItem(t("mode_substructure"), "substructure")
        self.search_mode_combo.addItem(t("mode_similarity"), "similarity")
        cfg_mode = get_search_mode()
        idx_mode = self.search_mode_combo.findData(cfg_mode)
        if idx_mode >= 0:
            self.search_mode_combo.setCurrentIndex(idx_mode)
        self.search_mode_combo.currentIndexChanged.connect(self.on_search_mode_changed)
        search_layout.addWidget(self.search_mode_combo)

        # 3b. Similarity Threshold Combo (Only for similarity mode)
        self.label_sim_threshold = QLabel(t("sim_threshold_label"))
        search_layout.addWidget(self.label_sim_threshold)
        self.sim_threshold_combo = QComboBox()
        self.sim_threshold_combo.setStyleSheet("min-width: 75px;")
        self.sim_threshold_combo.addItem(t("sim_threshold_60"), 0.60)
        self.sim_threshold_combo.addItem(t("sim_threshold_70"), 0.70)
        self.sim_threshold_combo.addItem(t("sim_threshold_80"), 0.80)
        self.sim_threshold_combo.addItem(t("sim_threshold_90"), 0.90)
        self.sim_threshold_combo.setCurrentIndex(1) # Default 70%
        search_layout.addWidget(self.sim_threshold_combo)

        # 4. Max Hits Combo (Active for substructure & similarity modes)
        self.label_max_hits = QLabel(t("max_hits_label"))
        search_layout.addWidget(self.label_max_hits)
        self.search_max_hits_combo = QComboBox()
        self.search_max_hits_combo.setStyleSheet("min-width: 85px;")
        self.search_max_hits_combo.addItem(t("max_hits_50"), 50)
        self.search_max_hits_combo.addItem(t("max_hits_100"), 100)
        self.search_max_hits_combo.addItem(t("max_hits_250"), 250)
        self.search_max_hits_combo.addItem(t("max_hits_500"), 500)
        self.search_max_hits_combo.addItem(t("max_hits_all"), 0)
        cfg_max = get_max_hits()
        idx_max = self.search_max_hits_combo.findData(cfg_max)
        if idx_max >= 0:
            self.search_max_hits_combo.setCurrentIndex(idx_max)
        else:
            self.search_max_hits_combo.setCurrentIndex(1)
        self.search_max_hits_combo.currentIndexChanged.connect(self.on_search_max_hits_changed)
        search_layout.addWidget(self.search_max_hits_combo)
        
        # 5. Action Buttons
        self.search_btn = QPushButton(t("search_btn"), objectName="SearchBtn")
        self.search_btn.clicked.connect(self.start_search)
        search_layout.addWidget(self.search_btn)

        self.btn_stop_search = QPushButton(t("btn_stop_search"), objectName="StopBtn")
        self.btn_stop_search.setToolTip(t("btn_stop_search_tip"))
        self.btn_stop_search.clicked.connect(self.cancel_search)
        self.btn_stop_search.setVisible(False)
        search_layout.addWidget(self.btn_stop_search)
        
        self.mode_stack.addWidget(search_widget)
        self.update_max_hits_visibility()

        # Page 1: Browse Controls
        browse_widget = QWidget()
        browse_layout = QHBoxLayout(browse_widget)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(8)
        
        self.label_nucleus = QLabel(t("nucleus_label"))
        browse_layout.addWidget(self.label_nucleus)
        self.nucleus_combo = QComboBox()
        self.nucleus_combo.addItem(t("nuc_all"), "all")
        self.nucleus_combo.addItem(t("nuc_1h"), "1H")
        self.nucleus_combo.addItem(t("nuc_13c"), "13C")
        self.nucleus_combo.addItem(t("nuc_19f"), "19F")
        self.nucleus_combo.addItem(t("nuc_31p"), "31P")
        self.nucleus_combo.addItem(t("nuc_11b"), "11B")
        self.nucleus_combo.addItem(t("nuc_29si"), "29Si")
        self.nucleus_combo.currentIndexChanged.connect(self.on_nucleus_filter_changed)
        browse_layout.addWidget(self.nucleus_combo)
        
        self.btn_first = QPushButton("⏮")
        self.btn_first.setToolTip(t("first_tip"))
        self.btn_first.clicked.connect(self.browse_first)
        browse_layout.addWidget(self.btn_first)
        
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip(t("prev_tip"))
        self.btn_prev.clicked.connect(self.browse_prev)
        browse_layout.addWidget(self.btn_prev)
        
        self.spin_index = QSpinBox()
        self.spin_index.setMinimum(1)
        self.spin_index.setMaximum(self.current_browse_total)
        self.spin_index.setValue(1)
        self.spin_index.editingFinished.connect(self.on_spin_index_changed)
        browse_layout.addWidget(self.spin_index)
        
        self.total_label = QLabel(t("of_total", total=self.current_browse_total))
        self.total_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        browse_layout.addWidget(self.total_label)
        
        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip(t("next_tip"))
        self.btn_next.clicked.connect(self.browse_next)
        browse_layout.addWidget(self.btn_next)
        
        self.btn_last = QPushButton("⏭")
        self.btn_last.setToolTip(t("last_tip"))
        self.btn_last.clicked.connect(self.browse_last)
        browse_layout.addWidget(self.btn_last)
        
        self.btn_random = QPushButton(t("random_btn"))
        self.btn_random.setToolTip(t("random_tip"))
        self.btn_random.clicked.connect(self.browse_random)
        browse_layout.addWidget(self.btn_random)
        
        self.btn_load_ketcher = QPushButton(t("btn_load_ketcher"))
        self.btn_load_ketcher.setToolTip(t("btn_load_ketcher_tip"))
        self.btn_load_ketcher.clicked.connect(self.load_current_mol_to_ketcher)
        browse_layout.addWidget(self.btn_load_ketcher)

        self.btn_open_3d = QPushButton(t("btn_open_3d"))
        self.btn_open_3d.setToolTip(t("btn_open_3d_tip"))
        self.btn_open_3d.clicked.connect(self.open_current_mol_in_3d)
        browse_layout.addWidget(self.btn_open_3d)

        self.btn_open_spectrum = QPushButton(t("btn_open_spectrum"))
        self.btn_open_spectrum.setToolTip(t("btn_open_spectrum_tip"))
        self.btn_open_spectrum.clicked.connect(self.open_current_mol_spectrum)
        browse_layout.addWidget(self.btn_open_spectrum)
        
        self.mode_stack.addWidget(browse_widget)
        header_layout.addWidget(self.mode_stack)

        header_layout.addStretch()

        self.update_mode_buttons()
        return header

    def update_mode_buttons(self):
        if self.current_mode == "search":
            self.btn_search_mode.setProperty("class", "active-mode")
            self.btn_browse_mode.setProperty("class", "")
            self.mode_stack.setCurrentIndex(0)
        else:
            self.btn_search_mode.setProperty("class", "")
            self.btn_browse_mode.setProperty("class", "active-mode")
            self.mode_stack.setCurrentIndex(1)
        self.btn_search_mode.style().unpolish(self.btn_search_mode)
        self.btn_search_mode.style().polish(self.btn_search_mode)
        self.btn_browse_mode.style().unpolish(self.btn_browse_mode)
        self.btn_browse_mode.style().polish(self.btn_browse_mode)

    def toggle_language(self):
        cur = get_current_language()
        new_lang = "en" if cur == "de" else "de"
        set_current_language(new_lang)
        self.retranslate_ui()

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.settings_saved.connect(self.on_settings_saved)
        dlg.exec()

    def on_settings_saved(self):
        self.retranslate_ui()
        self.check_database()

    def retranslate_ui(self):
        lang = get_current_language()
        self.btn_lang.setText("🇩🇪 DE" if lang == "de" else "🇬🇧 EN")
        self.btn_lang.setToolTip(t("settings_lang_label"))

        self.btn_home.setText(t("btn_home"))
        self.btn_search_mode.setText(t("btn_search_mode"))
        self.btn_browse_mode.setText(t("btn_browse_mode"))
        # Search controls
        self.label_source.setText(t("source_label"))
        self.source_combo.blockSignals(True)
        self.source_combo.setItemText(0, t("source_both"))
        self.source_combo.setItemText(1, t("source_nmrexp"))
        self.source_combo.setItemText(2, t("source_nmrshiftdb2"))
        if self.source_combo.count() > 3:
            self.source_combo.setItemText(3, t("source_mona"))
            self.source_combo.setItemText(4, t("source_all"))
        self.source_combo.blockSignals(False)

        self.label_search_nucleus.setText(t("search_nucleus_label"))
        self.search_nucleus_combo.blockSignals(True)
        self.search_nucleus_combo.setItemText(0, t("nuc_all"))
        self.search_nucleus_combo.setItemText(1, t("nuc_1h"))
        self.search_nucleus_combo.setItemText(2, t("nuc_13c"))
        self.search_nucleus_combo.setItemText(3, t("nuc_19f"))
        self.search_nucleus_combo.setItemText(4, t("nuc_31p"))
        self.search_nucleus_combo.setItemText(5, t("nuc_11b"))
        self.search_nucleus_combo.setItemText(6, t("nuc_29si"))
        self.search_nucleus_combo.blockSignals(False)

        self.label_search_mode.setText(t("search_mode_label"))
        self.search_mode_combo.blockSignals(True)
        self.search_mode_combo.setItemText(0, t("mode_exact"))
        self.search_mode_combo.setItemText(1, t("mode_substructure"))
        if self.search_mode_combo.count() > 2:
            self.search_mode_combo.setItemText(2, t("mode_similarity"))
        self.search_mode_combo.blockSignals(False)

        if hasattr(self, 'label_sim_threshold'):
            self.label_sim_threshold.setText(t("sim_threshold_label"))
            self.sim_threshold_combo.blockSignals(True)
            self.sim_threshold_combo.setItemText(0, t("sim_threshold_60"))
            self.sim_threshold_combo.setItemText(1, t("sim_threshold_70"))
            self.sim_threshold_combo.setItemText(2, t("sim_threshold_80"))
            self.sim_threshold_combo.setItemText(3, t("sim_threshold_90"))
            self.sim_threshold_combo.blockSignals(False)

        self.label_max_hits.setText(t("max_hits_label"))
        self.search_max_hits_combo.blockSignals(True)
        self.search_max_hits_combo.setItemText(0, t("max_hits_50"))
        self.search_max_hits_combo.setItemText(1, t("max_hits_100"))
        self.search_max_hits_combo.setItemText(2, t("max_hits_250"))
        self.search_max_hits_combo.setItemText(3, t("max_hits_500"))
        self.search_max_hits_combo.setItemText(4, t("max_hits_all"))
        self.search_max_hits_combo.blockSignals(False)

        self.search_btn.setText(t("search_btn"))
        self.btn_stop_search.setText(t("btn_stop_search"))
        self.btn_stop_search.setToolTip(t("btn_stop_search_tip"))

        self.label_nucleus.setText(t("nucleus_label"))

        self.nucleus_combo.blockSignals(True)
        self.nucleus_combo.setItemText(0, t("nuc_all"))
        self.nucleus_combo.setItemText(1, t("nuc_1h"))
        self.nucleus_combo.setItemText(2, t("nuc_13c"))
        self.nucleus_combo.setItemText(3, t("nuc_19f"))
        self.nucleus_combo.setItemText(4, t("nuc_31p"))
        self.nucleus_combo.setItemText(5, t("nuc_11b"))
        self.nucleus_combo.setItemText(6, t("nuc_29si"))
        self.nucleus_combo.blockSignals(False)

        self.btn_first.setToolTip(t("first_tip"))
        self.btn_prev.setToolTip(t("prev_tip"))
        self.total_label.setText(t("of_total", total=self.current_browse_total))
        self.btn_next.setToolTip(t("next_tip"))
        self.btn_last.setToolTip(t("last_tip"))
        self.btn_random.setText(t("random_btn"))
        self.btn_random.setToolTip(t("random_tip"))
        self.btn_load_ketcher.setText(t("btn_load_ketcher"))
        self.btn_load_ketcher.setToolTip(t("btn_load_ketcher_tip"))
        self.btn_open_3d.setText(t("btn_open_3d"))
        self.btn_open_3d.setToolTip(t("btn_open_3d_tip"))
        self.btn_open_spectrum.setText(t("btn_open_spectrum"))
        self.btn_open_spectrum.setToolTip(t("btn_open_spectrum_tip"))

        # Footer widgets
        self.update_db_btn.setText("🔄 DB")
        self.update_db_btn.setToolTip(t("footer_db_tip"))
        self.btn_lang.setToolTip(t("footer_lang_tip"))
        self.btn_settings.setToolTip(t("footer_settings_tip"))

        # Menus & Actions
        if hasattr(self, 'menu_file'):
            self.menu_file.setTitle(t("menu_file"))
            self.action_home.setText(t("btn_home"))
            self.action_settings.setText(t("btn_settings"))
            self.action_exit.setText(f"❌ {t('menu_exit')}")

            self.menu_view.setTitle(t("menu_view"))
            self.action_mode_search.setText(t("btn_search_mode"))
            self.action_mode_browse.setText(t("btn_browse_mode"))
            self.action_tab_details.setText(t("tab_details"))
            self.action_tab_3d.setText(t("tab_3d"))
            self.action_tab_spec.setText(t("tab_spectrum"))
            self.action_tab_ms.setText(t("tab_ms_spectrum"))
            if hasattr(self, 'action_tab_logbook'):
                self.action_tab_logbook.setText(t("tab_logbook"))

            self.menu_tools.setTitle(t("db_status_btn"))
            self.action_check_db.setText(f"🔄 {t('menu_check_db')}")

            self.menu_help.setTitle(t("menu_help"))
            self.action_guide.setText(t("btn_home"))
            self.action_about.setText(f"ℹ️ {t('menu_about')}")

        self.right_tabs.setTabText(0, t("tab_details"))
        self.right_tabs.setTabText(1, t("tab_3d"))
        self.right_tabs.setTabText(2, t("tab_spectrum"))
        if self.right_tabs.count() > 3:
            self.right_tabs.setTabText(3, t("tab_ms_spectrum"))
        if self.right_tabs.count() > 4:
            self.right_tabs.setTabText(4, t("tab_logbook"))

        # Retranslate 3D Viewer widget
        self.viewer_3d_widget.retranslate_ui()
        # Retranslate Spectrum Viewer widget
        self.viewer_spectrum_widget.retranslate_ui()
        # Retranslate MS Viewer widget
        if hasattr(self, 'viewer_ms_widget'):
            self.viewer_ms_widget.retranslate_ui()
        # Retranslate Logbook widget
        if hasattr(self, 'logbook_widget'):
            self.logbook_widget.retranslate_ui()

        # Update currently active view
        if hasattr(self, 'current_page_type'):
            if self.current_page_type == "welcome":
                self.show_welcome_page()
            elif self.current_page_type == "browse" and self.current_record:
                self.render_browse_view(self.current_record, self.current_browse_index, self.current_browse_total)
            elif self.current_page_type == "results" and self.last_results is not None:
                self.render_results(self.last_results)

    def set_search_mode(self):
        self.current_mode = "search"
        self.update_mode_buttons()
        self.right_tabs.setCurrentIndex(0)
        self.status_label.setText(t("search_mode_active"))

    def set_browse_mode(self):
        self.current_mode = "browse"
        self.update_mode_buttons()
        self.load_browse_record(self.current_browse_index)

    def check_database(self):
        self.status_label.setText(t("db_checking"))
        self.update_db_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        
        try:
            self.db_path = verify_and_update_db(progress_callback=self.status_label.setText)
            nmrexp_ok = self.nmrexp_mgr.is_available()
            
            if self.db_path and nmrexp_ok:
                self.status_label.setText(t("db_ready_both"))
            elif nmrexp_ok:
                self.status_label.setText(t("db_ready_nmrexp"))
            elif self.db_path:
                self.status_label.setText(t("db_ready_sdf"))
            else:
                self.status_label.setText(t("db_none"))
            self.search_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, t("error_title"), f"{t('db_check_error')}:\n{e}")
            self.status_label.setText(t("db_check_error"))
        finally:
            self.update_db_btn.setEnabled(True)

    # -------------------------------------------------------------
    # WEB ENGINE ACTION HANDLER
    # -------------------------------------------------------------
    def handle_web_action(self, action_url):
        if action_url.startswith("action:"):
            action_url = action_url[len("action:"):]
        parts = action_url.split(":", 1)
        if not parts or not parts[0]:
            return
        cmd = parts[0]
        param = parts[1] if len(parts) > 1 else ""

        if cmd == "open_3d_current":
            if self.current_record and self.current_record.get("smiles"):
                self.show_molecule_in_3d(self.current_record["smiles"])
            else:
                QMessageBox.information(self, t("info_title"), t("no_structure_msg"))
        elif cmd == "load_ketcher_current":
            if self.current_record and self.current_record.get("smiles"):
                self.send_smiles_to_ketcher(self.current_record["smiles"])
            else:
                QMessageBox.information(self, t("info_title"), t("no_structure_msg"))
        elif cmd == "open_3d_result":
            try:
                idx = int(param)
                if hasattr(self, 'last_results') and self.last_results and 0 <= idx < len(self.last_results):
                    res = self.last_results[idx]
                    self.current_record = res
                    smiles = res.get("smiles")
                    if smiles:
                        self.show_molecule_in_3d(smiles)
            except Exception as e:
                print(f"[HGTTD] Fehler bei open_3d_result: {e}")
        elif cmd == "open_spectrum_current":
            self.open_current_mol_spectrum()
        elif cmd == "open_spectrum_result":
            try:
                idx = int(param)
                if hasattr(self, 'last_results') and self.last_results and 0 <= idx < len(self.last_results):
                    res = self.last_results[idx]
                    self.current_record = res
                    self.show_spectrum(res)
            except Exception as e:
                print(f"[HGTTD] Fehler bei open_spectrum_result: {e}")
        elif cmd == "open_ms_spectrum":
            try:
                idx = int(param)
                if hasattr(self, 'last_results') and self.last_results and 0 <= idx < len(self.last_results):
                    res = self.last_results[idx]
                    self.current_record = res
                    self.show_ms_spectrum(res)
            except Exception as e:
                print(f"[HGTTD] Fehler bei open_ms_spectrum: {e}")
        elif cmd == "open_spectrum":
            self.open_current_mol_spectrum()
        elif cmd == "export_report_current":
            if hasattr(self, 'current_record') and self.current_record:
                from report_generator import export_report_dialog
                export_report_dialog(self, self.current_record)
        elif cmd == "load_ketcher_result":
            try:
                idx = int(param)
                if hasattr(self, 'last_results') and self.last_results and 0 <= idx < len(self.last_results):
                    res = self.last_results[idx]
                    self.current_record = res
                    smiles = res.get("smiles")
                    if smiles:
                        self.send_smiles_to_ketcher(smiles)
            except Exception as e:
                print(f"[HGTTD] Fehler bei load_ketcher_result: {e}")
        elif cmd == "mode":
            if param == "search":
                self.set_search_mode()
            elif param == "browse":
                self.set_browse_mode()
        elif cmd == "browse":
            if param == "random":
                self.set_browse_mode()
                self.browse_random()
        elif cmd == "toggle_bookmark":
            if self.current_record and self.current_record.get("smiles"):
                sm = self.current_record["smiles"]
                new_state = logbook_manager.toggle_favorite(sm)
                logbook_manager.touch_molecule(self.current_record, mark_favorite=new_state)
                # Re-render browse view to reflect star
                if self.current_page_type == "browse":
                    self.render_browse_view(self.current_record, self.current_browse_index, self.current_browse_total)
                self.status_label.setText(f"⭐ {t('logbook_saved_title') if new_state else 'Entfernt'}")
                if hasattr(self, 'logbook_widget'):
                    self.logbook_widget.refresh_data()
        elif cmd == "toggle_bookmark_result":
            try:
                idx = int(param)
                if hasattr(self, 'last_results') and self.last_results and 0 <= idx < len(self.last_results):
                    res = self.last_results[idx]
                    sm = res.get("smiles")
                    if sm:
                        new_state = logbook_manager.toggle_favorite(sm)
                        logbook_manager.touch_molecule(res, mark_favorite=new_state)
                        self.render_results(self.last_results)
                        if hasattr(self, 'logbook_widget'):
                            self.logbook_widget.refresh_data()
            except Exception as e:
                print(f"[HGTTD] Fehler bei toggle_bookmark_result: {e}")
        elif cmd == "load_ketcher":
            smiles = unquote(param)
            self.send_smiles_to_ketcher(smiles)
        elif cmd == "open_3d":
            smiles = unquote(param)
            self.show_molecule_in_3d(smiles)
        elif cmd in ("open_external_url", "open_url"):
            target_url = param
            if target_url and (target_url.startswith("http://") or target_url.startswith("https://")):
                now = time.time()
                last_url = getattr(self, "_last_opened_url", None)
                last_time = getattr(self, "_last_opened_time", 0.0)
                # Ignore duplicate calls within 1.0 second
                if target_url == last_url and (now - last_time) < 1.0:
                    return
                self._last_opened_url = target_url
                self._last_opened_time = now
                try:
                    webbrowser.open(target_url)
                except Exception as e:
                    print(f"[HGTTD] Fehler beim Öffnen der URL im Browser: {e}")

    def send_smiles_to_ketcher(self, smiles):
        if not smiles:
            return
        js = f"""
        (function() {{
            function getK() {{
                if (typeof window.ketcher !== 'undefined') return window.ketcher;
                for (var i = 0; i < window.frames.length; i++) {{
                    try {{
                        if (typeof window.frames[i].ketcher !== 'undefined') return window.frames[i].ketcher;
                    }} catch(e) {{}}
                }}
                return null;
            }}
            var k = getK();
            if (k && k.setMolecule) {{
                k.setMolecule({json.dumps(smiles)}).catch(function(err) {{
                    console.error("Fehler beim Setzen von SMILES:", err);
                }});
            }}
        }})();
        """
        self.ketcher_view.page().runJavaScript(js)
        self.status_label.setText(t("mol_loaded_ketcher"))

    def on_spectrum_highlight_atoms(self, atom_indices):
        """Cross-highlights atoms in 3D viewer when hovering peaks in spectrum."""
        if hasattr(self, 'viewer_3d_widget'):
            if atom_indices and len(atom_indices) > 0:
                self.viewer_3d_widget.highlight_atoms(atom_indices)
            else:
                self.viewer_3d_widget.clear_highlight()

    def load_current_mol_to_ketcher(self):
        if self.current_record and self.current_record.get("smiles"):
            self.send_smiles_to_ketcher(self.current_record["smiles"])
        else:
            QMessageBox.information(self, t("info_title"), t("no_structure_msg"))

    def open_current_mol_in_3d(self):
        if self.current_record and self.current_record.get("smiles"):
            self.show_molecule_in_3d(self.current_record["smiles"])
        else:
            QMessageBox.information(self, t("info_title"), t("no_structure_msg"))

    def show_molecule_in_3d(self, smiles):
        if not smiles:
            return
        self.right_tabs.blockSignals(True)
        self.right_tabs.setCurrentIndex(1)
        self.right_tabs.blockSignals(False)
        self.viewer_3d_widget.set_molecule(smiles)
        self.status_label.setText(t("3d_loaded_status"))

    def open_3d_viewer(self, smiles):
        self.show_molecule_in_3d(smiles)

    def open_current_mol_spectrum(self):
        if self.current_record:
            self.show_spectrum(self.current_record)
        else:
            QMessageBox.information(self, t("info_title"), t("spectrum_no_data"))

    def show_spectrum(self, record):
        if not record:
            return
        self.right_tabs.blockSignals(True)
        self.right_tabs.setCurrentIndex(2)
        self.right_tabs.blockSignals(False)
        self.viewer_spectrum_widget.set_record(record)
        self.status_label.setText(t("spectrum_loaded_status"))

    def show_ms_spectrum(self, record):
        if not record:
            return
        self.right_tabs.blockSignals(True)
        self.right_tabs.setCurrentIndex(3)
        self.right_tabs.blockSignals(False)
        self.viewer_ms_widget.load_record(record)
        name = record.get("name") or "MS"
        self.status_label.setText(f"MoNa: Massenspektrum geladen ({name})")

    def on_tab_changed(self, index):
        if index == 1:
            if self.current_record and self.current_record.get("smiles"):
                if self.viewer_3d_widget.current_smiles != self.current_record["smiles"]:
                    self.viewer_3d_widget.set_molecule(self.current_record["smiles"])
        elif index == 2:
            if self.current_record:
                if self.viewer_spectrum_widget.current_record != self.current_record:
                    self.viewer_spectrum_widget.set_record(self.current_record)
        elif index == 3:
            if self.current_record:
                if self.viewer_ms_widget.current_record != self.current_record:
                    self.viewer_ms_widget.load_record(self.current_record)
        elif index == 4:
            if hasattr(self, 'logbook_widget'):
                self.logbook_widget.refresh_data()

    # -------------------------------------------------------------
    # BROWSER LOGIC
    # -------------------------------------------------------------
    def on_nucleus_filter_changed(self):
        filter_key = self.nucleus_combo.currentData()
        self.current_nucleus_filter = filter_key
        self.current_browse_total = self.nmrexp_mgr.get_count_for_nucleus(filter_key)
        self.current_browse_index = 0
        
        self.spin_index.blockSignals(True)
        self.spin_index.setMaximum(max(1, self.current_browse_total))
        self.spin_index.setValue(1)
        self.spin_index.blockSignals(False)
        
        self.total_label.setText(f"von {self.current_browse_total:,}")
        self.load_browse_record(0)

    def on_spin_index_changed(self):
        val = self.spin_index.value() - 1
        if 0 <= val < self.current_browse_total:
            self.load_browse_record(val)

    def browse_first(self):
        self.load_browse_record(0)

    def browse_prev(self):
        if self.current_browse_index > 0:
            self.load_browse_record(self.current_browse_index - 1)

    def browse_next(self):
        if self.current_browse_index < self.current_browse_total - 1:
            self.load_browse_record(self.current_browse_index + 1)

    def browse_last(self):
        if self.current_browse_total > 0:
            self.load_browse_record(self.current_browse_total - 1)

    def browse_random(self):
        if self.current_browse_total > 0:
            rnd = random.randint(0, self.current_browse_total - 1)
            self.load_browse_record(rnd)

    def load_browse_record(self, record_idx):
        if not (0 <= record_idx < self.current_browse_total):
            return

        self.current_browse_index = record_idx
        self.spin_index.blockSignals(True)
        self.spin_index.setValue(record_idx + 1)
        self.spin_index.blockSignals(False)

        row_idx = self.nmrexp_mgr.get_row_index_for_record(self.current_nucleus_filter, record_idx)
        if row_idx is None:
            return

        record = self.nmrexp_mgr.get_record_by_row_index(row_idx)
        if not record:
            return

        self.current_page_type = "browse"
        self.current_record = record
        self.render_browse_view(record, record_idx, self.current_browse_total)
        self.status_label.setText(f"NMRexp: {t('record_label', idx=record_idx + 1, total=self.current_browse_total)} ({record['nmr_type']})")

        # Record in persistent logbook
        try:
            logbook_manager.touch_molecule(record)
            logbook_manager.log_activity("browse", query_info=f"Index {record_idx+1}", smiles=record.get("smiles", ""), title=record.get("filename", ""))
        except Exception:
            pass

        # If user is currently viewing the 3D tab, update the 3D model automatically
        if self.right_tabs.currentIndex() == 1 and record.get("smiles"):
            self.viewer_3d_widget.set_molecule(record["smiles"])

    # -------------------------------------------------------------
    # SEARCH LOGIC
    # -------------------------------------------------------------
    def start_search(self):
        self.status_label.setText(t("fetching_ketcher"))
        self.search_btn.setEnabled(False)
        
        js_trigger = """
        (function() {
            window.current_smiles = undefined;
            function getK() {
                if (typeof window.ketcher !== 'undefined') return window.ketcher;
                for (var i = 0; i < window.frames.length; i++) {
                    try {
                        if (typeof window.frames[i].ketcher !== 'undefined') return window.frames[i].ketcher;
                    } catch(e) {}
                }
                return null;
            }
            var k = getK();
            if (k) {
                k.getSmiles()
                    .then(function(s) { window.current_smiles = s || "EMPTY_CANVAS"; })
                    .catch(function(err) { window.current_smiles = "ERROR: " + err; });
                return "TRIGGERED";
            } else {
                return "ERROR_NOT_FOUND";
            }
        })()
        """
        self.ketcher_view.page().runJavaScript(js_trigger, self.on_search_triggered)

    def on_search_triggered(self, status):
        if status == "ERROR_NOT_FOUND":
            self.status_label.setText("Ketcher...")
            self.search_btn.setEnabled(True)
            QMessageBox.warning(self, t("info_title"), "Ketcher wurde noch nicht vollständig initialisiert / Ketcher not fully initialized.")
            return
        
        self.poll_attempts = 0
        self.poll_timer.start()

    def poll_smiles_variable(self):
        self.poll_attempts += 1
        if self.poll_attempts > 50:
            self.poll_timer.stop()
            self.search_btn.setEnabled(True)
            self.status_label.setText(t("search_mode_active"))
            QMessageBox.warning(self, "Timeout", "Zeitüberschreitung beim Abrufen der Struktur aus Ketcher.")
            return
            
        js_get = "window.current_smiles;"
        self.ketcher_view.page().runJavaScript(js_get, self.on_poll_result)

    def on_poll_result(self, val):
        if val is None or val == "":
            return
            
        self.poll_timer.stop()
        smiles = val
        
        if smiles == "EMPTY_CANVAS":
            self.status_label.setText(t("search_mode_active"))
            self.search_btn.setEnabled(True)
            QMessageBox.warning(self, t("empty_mol_title"), t("empty_mol_msg"))
            return
            
        if smiles.startswith("ERROR:"):
            self.status_label.setText(t("error_title"))
            self.search_btn.setEnabled(True)
            QMessageBox.critical(self, t("ketcher_error_title"), t("ketcher_error_msg", err=smiles))
            return

        source_choice = self.source_combo.currentData()
        nucleus_choice = self.search_nucleus_combo.currentData()
        search_mode = self.search_mode_combo.currentData()
        max_hits = self.search_max_hits_combo.currentData()
        if max_hits is None:
            max_hits = 100

        self.last_search_mode = search_mode
        self.last_search_nucleus = nucleus_choice

        min_sim = self.sim_threshold_combo.currentData() if hasattr(self, 'sim_threshold_combo') else 0.70
        if min_sim is None:
            min_sim = 0.70

        if search_mode == "substructure":
            loading_label = f"{t('searching_substructure')} ({source_choice.upper()} • {nucleus_choice})"
        elif search_mode == "similarity":
            loading_label = f"{t('searching_similarity')} (≥ {int(min_sim*100)}%)"
        else:
            loading_label = f"{t('loading_default')} ({source_choice.upper()} • {nucleus_choice})"
        self.show_loading_page(loading_label)
        
        self.search_btn.setEnabled(False)
        self.btn_stop_search.setVisible(True)

        self.search_worker = SearchWorker(
            query_smiles=smiles,
            sdf_path=self.db_path,
            parquet_path=self.parquet_path,
            source_choice=source_choice,
            nucleus_filter=nucleus_choice,
            search_mode=search_mode,
            max_results=max_hits,
            min_similarity=min_sim
        )
        self.search_worker.progress_signal.connect(self.update_loading_status)
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.start()

    def cancel_search(self):
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.cancel()
            self.status_label.setText(t("substructure_cancelled", count=0))

    def on_search_mode_changed(self):
        mode = self.search_mode_combo.currentData()
        set_search_mode(mode)
        self.update_max_hits_visibility()

    def update_max_hits_visibility(self):
        mode = self.search_mode_combo.currentData()
        is_sub = (mode == "substructure")
        is_sim = (mode == "similarity")
        if hasattr(self, 'label_sim_threshold'):
            self.label_sim_threshold.setVisible(is_sim)
            self.sim_threshold_combo.setVisible(is_sim)
        self.label_max_hits.setVisible(is_sub or is_sim)
        self.search_max_hits_combo.setVisible(is_sub or is_sim)

    def on_search_nucleus_changed(self):
        nuc = self.search_nucleus_combo.currentData()
        set_search_nucleus(nuc)
        if nuc not in ("all", "13C") and self.source_combo.currentData() == "nmrshiftdb2":
            self.status_label.setText(t("nmrshiftdb2_13c_only_hint"))

    def on_search_max_hits_changed(self):
        hits = self.search_max_hits_combo.currentData()
        if hits is not None:
            set_max_hits(int(hits))

    def update_loading_status(self, status):
        js = f"if(document.getElementById('status-title')) document.getElementById('status-title').innerText = {json.dumps(status)};"
        self.results_view.page().runJavaScript(js)
        self.status_label.setText(status)

    def on_search_finished(self, results, error):
        self.search_btn.setEnabled(True)
        self.btn_stop_search.setVisible(False)
        if error:
            self.status_label.setText(t("search_error_status"))
            self.show_error_page(error)
            return

        self.current_page_type = "results"
        self.last_results = results
        is_substructure = getattr(self, 'last_search_mode', 'exact') == 'substructure'
        if is_substructure and self.search_worker and self.search_worker.is_cancelled:
            self.status_label.setText(t("substructure_cancelled", count=len(results)))
        else:
            self.status_label.setText(t("search_finished_status", count=len(results)))
        self.right_tabs.setCurrentIndex(0)
        try:
            self.render_results(results)
            # Log search in logbook
            query_str = getattr(self.search_worker, 'query_smiles', '')
            logbook_manager.log_activity(
                "search",
                query_info=f"{self.last_search_mode.capitalize()} • {len(results)} Treffer",
                smiles=query_str,
                title=f"Suche: {query_str[:25]}..." if len(query_str) > 25 else f"Suche: {query_str}"
            )
        except Exception as e:
            print(f"[ModernMainWindow] Fehler beim Rendern der Suchergebnisse: {e}")
            import traceback
            traceback.print_exc()
            self.show_error_page(f"Fehler beim Rendern der Suchergebnisse: {e}")

    # -------------------------------------------------------------
    # HTML RENDERING & PAGES
    # -------------------------------------------------------------
    def show_welcome_page(self):
        self.current_page_type = "welcome"
        self.right_tabs.setCurrentIndex(0)
        welcome_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
                    background: radial-gradient(circle at 50% 20%, #111827 0%, #070b14 100%);
                    color: #f1f5f9;
                    margin: 0;
                    padding: 24px 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    min-height: 100vh;
                    overflow-x: hidden;
                }}
                .hero {{
                    text-align: center;
                    max-width: 820px;
                    width: 100%;
                    margin-top: 10px;
                }}
                .dont-panic-badge {{
                    display: inline-block;
                    background: linear-gradient(135deg, #f59e0b, #d97706);
                    color: #000;
                    font-size: 24px;
                    font-weight: 900;
                    letter-spacing: 4px;
                    padding: 8px 28px;
                    border-radius: 9999px;
                    box-shadow: 0 0 25px rgba(245, 158, 11, 0.45);
                    text-transform: uppercase;
                    margin-bottom: 15px;
                    animation: pulse 2.5s infinite;
                }}
                @keyframes pulse {{
                    0% {{ box-shadow: 0 0 20px rgba(245, 158, 11, 0.3); }}
                    50% {{ box-shadow: 0 0 35px rgba(245, 158, 11, 0.65); transform: scale(1.02); }}
                    100% {{ box-shadow: 0 0 20px rgba(245, 158, 11, 0.3); }}
                }}
                h1 {{
                    color: #38bdf8;
                    font-size: clamp(28px, 4vw, 38px);
                    margin: 5px 0 10px 0;
                    font-weight: 800;
                    letter-spacing: 1px;
                }}
                .subtitle {{
                    font-size: clamp(15px, 2vw, 19px);
                    color: #94a3b8;
                    margin-bottom: 8px;
                    font-weight: 500;
                }}
                .lore {{
                    font-size: 13px;
                    color: #64748b;
                    font-style: italic;
                    margin-bottom: 25px;
                    padding: 0 10px;
                }}
                .actions {{
                    display: flex;
                    justify-content: center;
                    flex-wrap: wrap;
                    gap: 12px;
                    margin-bottom: 30px;
                    width: 100%;
                }}
                .btn {{
                    display: inline-block;
                    padding: 10px 20px;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: 700;
                    font-size: 13px;
                    transition: all 0.2s;
                    cursor: pointer;
                    white-space: nowrap;
                }}
                .btn-primary {{
                    background: #2563eb;
                    color: #fff;
                    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
                }}
                .btn-primary:hover {{ background: #1d4ed8; transform: translateY(-1px); }}
                .btn-secondary {{
                    background: #0ea5e9;
                    color: #032030;
                    box-shadow: 0 4px 14px rgba(14, 165, 233, 0.35);
                }}
                .btn-secondary:hover {{ background: #38bdf8; transform: translateY(-1px); }}
                .btn-accent {{
                    background: #10b981;
                    color: #02261d;
                    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);
                }}
                .btn-accent:hover {{ background: #34d399; transform: translateY(-1px); }}

                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 16px;
                    max-width: 860px;
                    width: 100%;
                    text-align: left;
                }}
                .card {{
                    background: rgba(30, 41, 59, 0.65);
                    border: 1px solid #334155;
                    border-radius: 12px;
                    padding: 18px 20px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
                }}
                .card h3 {{
                    margin-top: 0;
                    font-size: 15px;
                    color: #38bdf8;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                .card p {{
                    font-size: 13px;
                    color: #cbd5e1;
                    line-height: 1.5;
                    margin-bottom: 0;
                }}
                .badge-stat {{
                    display: inline-block;
                    background: #0f172a;
                    border: 1px solid #334155;
                    color: #38bdf8;
                    padding: 2px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    margin-top: 8px;
                }}
                .quote-42 {{
                    margin-top: 25px;
                    font-size: 12px;
                    color: #64748b;
                    text-align: center;
                    padding: 0 10px;
                }}

                @media (max-width: 680px) {{
                    .grid {{
                        grid-template-columns: 1fr;
                    }}
                    .actions {{
                        flex-direction: column;
                        align-items: stretch;
                    }}
                    .btn {{
                        text-align: center;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="hero">
                <div class="dont-panic-badge">DON'T PANIC</div>
                <h1>HGTTD</h1>
                <div class="subtitle">{t('welcome_hero_sub')}</div>
                <div class="lore">{t('welcome_hero_lore')}</div>
                
                <div class="actions">
                    <a href="action:mode:search" onclick="hgttdAction('mode', 'search'); return false;" class="btn btn-primary">{t('welcome_btn_search')}</a>
                    <a href="action:mode:browse" onclick="hgttdAction('mode', 'browse'); return false;" class="btn btn-secondary">{t('welcome_btn_browse')}</a>
                    <a href="action:browse:random" onclick="hgttdAction('browse', 'random'); return false;" class="btn btn-accent">{t('welcome_btn_random')}</a>
                </div>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>{t('welcome_card1_title')}</h3>
                    <p>{t('welcome_card1_text')}</p>
                    <div class="badge-stat">{t('welcome_card1_badge')}</div>
                </div>

                <div class="card">
                    <h3>{t('welcome_card2_title')}</h3>
                    <p>{t('welcome_card2_text')}</p>
                    <div class="badge-stat">{t('welcome_card2_badge')}</div>
                </div>

                <div class="card">
                    <h3>{t('welcome_card_mona_title')}</h3>
                    <p>{t('welcome_card_mona_text')}</p>
                    <div class="badge-stat">{t('welcome_card_mona_badge')}</div>
                </div>

                <div class="card">
                    <h3>{t('welcome_card3_title')}</h3>
                    <p>{t('welcome_card3_text')}</p>
                </div>

                <div class="card">
                    <h3>{t('welcome_card4_title')}</h3>
                    <p>{t('welcome_card4_text')}</p>
                </div>
            </div>

            <div class="quote-42">
                {t('welcome_quote')}
            </div>
        </body>
        </html>
        """
        self.results_view.setHtml(welcome_html.replace("<head>", f"<head>{ACTION_INTERCEPTOR_SCRIPT}"))

    def show_loading_page(self, status=None):
        if status is None:
            status = t("loading_default")
        self.right_tabs.setCurrentIndex(0)
        loading_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background-color: #070b14;
                    color: #f8fafc;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    text-align: center;
                }}
                .spinner {{
                    border: 4px solid #1e293b;
                    border-top: 4px solid #38bdf8;
                    border-radius: 50%;
                    width: 50px;
                    height: 50px;
                    animation: spin 0.9s linear infinite;
                    margin-bottom: 25px;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                h3 {{
                    color: #38bdf8;
                    margin: 0;
                    font-size: 20px;
                    font-weight: 600;
                }}
                p {{
                    color: #94a3b8;
                    margin-top: 10px;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="spinner"></div>
            <h3 id="status-title">{status}</h3>
            <p>{t('loading_subtitle')}</p>
        </body>
        </html>
        """
        self.results_view.setHtml(loading_html)

    def show_error_page(self, error):
        self.right_tabs.setCurrentIndex(0)
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background-color: #070b14;
                    color: #f8fafc;
                    padding: 40px;
                }}
                .card {{
                    background: #1e1b2e;
                    border: 1px solid #dc2626;
                    border-radius: 12px;
                    padding: 30px;
                    max-width: 650px;
                    margin: 40px auto;
                    box-shadow: 0 4px 20px rgba(220, 38, 38, 0.2);
                }}
                h2 {{ margin-top: 0; color: #f87171; }}
                p {{ color: #cbd5e1; line-height: 1.6; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>{t('query_error_title')}</h2>
                <p>{error}</p>
            </div>
        </body>
        </html>
        """
        self.results_view.setHtml(error_html)

    def render_browse_view(self, record, current_idx, total_count):
        self.current_page_type = "browse"
        nucleus_color = record.get("nucleus_color", "#38bdf8")
        nmr_type = record.get("nmr_type", "NMR")
        doi_url = record.get("doi_url", "")
        filename = record.get("filename", "")
        smiles = record.get("smiles", "")
        
        # Auto-Assignment calculation
        spectrum = record.get("spectrum", [])
        is_1h = "1H" in nmr_type
        is_13c = "13C" in nmr_type

        assign_res = None
        assign_map = {}
        if spectrum and smiles and (is_1h or is_13c) and auto_assignment_engine.is_available:
            try:
                assign_res = auto_assignment_engine.assign_peaks(smiles, spectrum, nucleus=nmr_type)
                if assign_res and assign_res.get("assigned_peaks"):
                    for ap in assign_res["assigned_peaks"]:
                        assign_map[ap["exp_idx"]] = ap
            except Exception as e:
                print(f"[HGTTD] Auto-Assignment Fehler: {e}")

        has_assignment = bool(assign_map)
        
        # Build spectrum table
        if spectrum:
            rows_html = []
            for idx, row in enumerate(spectrum):
                assign_td = ""
                if has_assignment:
                    ap = assign_map.get(idx)
                    if ap:
                        conf = ap["confidence"]
                        conf_class = f"assign-badge assign-{conf}"
                        sign = "+" if ap["delta_ppm"] > 0 else ""
                        assign_td = f"""
                        <td><span class="{conf_class}" title="Konfidenz: {t('assign_' + conf + '_conf')}">{ap['calc_label']}</span></td>
                        <td class="calc-shift-cell">{ap['calc_shift']:.2f}</td>
                        <td class="delta-cell delta-{conf}">{sign}{ap['delta_ppm']:.2f}</td>
                        """
                    else:
                        assign_td = """
                        <td><span class="assign-badge assign-none">–</span></td>
                        <td class="calc-shift-cell">–</td>
                        <td class="delta-cell">–</td>
                        """

                if is_1h:
                    rows_html.append(f"""
                    <tr>
                        <td class="shift-cell">{row.get('shift', '-')}</td>
                        <td><span class="mult-badge">{row.get('multiplicity', '-')}</span></td>
                        <td>{row.get('j_coupling', '-')}</td>
                        <td><strong>{row.get('integral', '-')}</strong></td>
                        {assign_td}
                    </tr>
                    """)
                else:
                    rows_html.append(f"""
                    <tr>
                        <td class="shift-cell">{row.get('shift', '-')}</td>
                        <td><span class="mult-badge">{row.get('multiplicity', '-')}</span></td>
                        <td>{row.get('j_coupling', '-')}</td>
                        {assign_td}
                    </tr>
                    """)
            
            table_body = "".join(rows_html)
            
            assign_headers = f"""
            <th>{t('col_assignment_est')}</th>
            <th>{t('col_calc_shift')}</th>
            <th>{t('col_deviation')}</th>
            """ if has_assignment else ""

            if is_1h:
                table_header = f"""
                <tr>
                    <th>{t('shift_ppm')}</th>
                    <th>{t('multiplicity')}</th>
                    <th>{t('coupling_j')}</th>
                    <th>{t('integrals')}</th>
                    {assign_headers}
                </tr>
                """
            else:
                table_header = f"""
                <tr>
                    <th>{t('shift_ppm')}</th>
                    <th>{t('multiplicity')}</th>
                    <th>{t('coupling_j')}</th>
                    {assign_headers}
                </tr>
                """
                
            spectrum_html = f"""
            <div class="table-container">
                <table class="spec-table">
                    <thead>{table_header}</thead>
                    <tbody>{table_body}</tbody>
                </table>
            </div>
            """
        else:
            spectrum_html = f"<p class='no-spec'>{t('no_peaks')}</p>"

        shift_text = record.get("shift_text", "")
        shift_text_html = ""
        if shift_text:
            shift_text_html = f"""
            <div class="raw-text-card">
                <strong>{t('raw_text_heading')}</strong><br>
                <code>{shift_text}</code>
            </div>
            """

        doi_link_html = f'<a href="{doi_url}" target="_blank" class="doi-link">📄 {filename} ↗</a>' if doi_url else filename

        page_info = []
        if record.get("page_mol"):
            page_info.append(f"{t('doc_page')} (Mol): {int(record['page_mol'])}")
        if record.get("page_para"):
            page_info.append(f"{t('doc_page')} (Para): {int(record['page_para'])}")
        page_str = " • ".join(page_info) if page_info else ""

        # Determine molecule SVG (use assigned version if available)
        svg_display = record.get("svg", "")
        if has_assignment and smiles:
            try:
                assigned_svg = auto_assignment_engine.render_assigned_molecule_svg(
                    smiles, assign_res["assigned_peaks"], nucleus=nmr_type, width=380, height=280
                )
                if assigned_svg:
                    svg_display = assigned_svg
            except Exception:
                pass

        assign_chip = ""
        if has_assignment and assign_res:
            n_assigned = len(assign_res.get("assigned_peaks", []))
            n_total = len(spectrum)
            mae_str = f"{assign_res.get('mae', 0.0):.2f}"
            assign_chip = f'<div class="chip chip-assign"><strong>🤖 est-NMR:</strong> {n_assigned}/{n_total} {t("col_assignment")} (MAE: {mae_str} ppm)</div>'

        is_fav = logbook_manager.is_favorite(smiles)
        bookmark_btn_class = "btn-bookmark-active" if is_fav else ""
        bookmark_btn_text = f"⭐ {t('btn_toggle_bookmark_active') if is_fav else t('btn_toggle_bookmark')}"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                    background-color: #0b1120;
                    color: #f1f5f9;
                    margin: 0;
                    padding: 20px;
                }}
                .header-card {{
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 10px;
                    padding: 16px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }}
                .record-title {{
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }}
                .record-badge {{
                    background: #0f172a;
                    border: 1px solid #334155;
                    color: #cbd5e1;
                    padding: 5px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                .nucleus-badge {{
                    background: {nucleus_color};
                    color: #000;
                    padding: 5px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 800;
                }}
                .doi-link {{
                    color: #38bdf8;
                    text-decoration: none;
                    background: #0f172a;
                    border: 1px solid #0284c7;
                    padding: 6px 14px;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                .doi-link:hover {{
                    background: #0284c7;
                    color: #fff;
                }}
                .content-grid {{
                    display: flex;
                    gap: 20px;
                }}
                .left-col {{
                    flex: 1;
                    max-width: 440px;
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }}
                .mol-card {{
                    background: #ffffff;
                    border-radius: 10px;
                    padding: 15px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                }}
                .mol-card svg {{
                    width: 100%;
                    height: auto;
                    display: block;
                }}
                .mol-info {{
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 12px 15px;
                    font-size: 13px;
                }}
                .btn-bookmark {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #1e293b;
                    color: #fef08a;
                    border: 1px solid #ca8a04;
                    padding: 9px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                    cursor: pointer;
                    margin-top: 10px;
                    box-sizing: border-box;
                    transition: all 0.15s;
                }}
                .btn-bookmark:hover {{ background: #854d0e; color: #fff; }}
                .btn-bookmark-active {{
                    background: #ca8a04;
                    color: #000;
                    border-color: #facc15;
                }}
                .btn-ketcher {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #2563eb;
                    color: white;
                    border: 1px solid #3b82f6;
                    padding: 10px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                    cursor: pointer;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-ketcher:hover {{ background: #1d4ed8; }}
                .btn-3d {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #059669;
                    color: #ffffff;
                    border: 1px solid #10b981;
                    padding: 10px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                    cursor: pointer;
                    margin-top: 8px;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-3d:hover {{
                    background: #10b981;
                    color: #022c22;
                }}
                .btn-spectrum {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #7c3aed;
                    color: #ffffff;
                    border: 1px solid #8b5cf6;
                    padding: 10px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                    cursor: pointer;
                    margin-top: 8px;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-spectrum:hover {{
                    background: #6d28d9;
                }}
                .right-col {{
                    flex: 1.3;
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }}
                .meta-chips {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 10px;
                }}
                .chip {{
                    background: #1e293b;
                    border: 1px solid #334155;
                    padding: 6px 12px;
                    border-radius: 6px;
                    font-size: 12px;
                    color: #cbd5e1;
                }}
                .chip strong {{ color: #f8fafc; }}
                .chip-assign {{
                    background: #0f172a;
                    border: 1px solid #10b981;
                    color: #34d399;
                }}
                .table-container {{
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    max-height: 480px;
                    overflow-y: auto;
                }}
                .spec-table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                    text-align: left;
                }}
                .spec-table th {{
                    background: #0f172a;
                    color: #94a3b8;
                    padding: 10px 14px;
                    position: sticky;
                    top: 0;
                    border-bottom: 2px solid #334155;
                }}
                .spec-table td {{
                    padding: 8px 14px;
                    border-bottom: 1px solid #334155;
                    color: #e2e8f0;
                }}
                .spec-table tr:hover td {{
                    background: #334155;
                }}
                .shift-cell {{
                    font-family: 'Consolas', monospace;
                    font-weight: bold;
                    color: #38bdf8;
                }}
                .mult-badge {{
                    background: #0f172a;
                    padding: 2px 6px;
                    border-radius: 4px;
                    border: 1px solid #475569;
                    font-family: monospace;
                }}
                .assign-badge {{
                    padding: 2px 7px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 700;
                    display: inline-block;
                }}
                .assign-high {{
                    background: #064e3b;
                    color: #34d399;
                    border: 1px solid #059669;
                }}
                .assign-medium {{
                    background: #78350f;
                    color: #fcd34d;
                    border: 1px solid #d97706;
                }}
                .assign-low {{
                    background: #7c2d12;
                    color: #fdba74;
                    border: 1px solid #ea580c;
                }}
                .assign-none {{
                    background: #1e293b;
                    color: #64748b;
                    border: 1px solid #334155;
                }}
                .calc-shift-cell {{
                    font-family: 'Consolas', monospace;
                    color: #a5b4fc;
                    font-size: 12px;
                }}
                .delta-cell {{
                    font-family: 'Consolas', monospace;
                    font-size: 11px;
                    font-weight: 600;
                }}
                .delta-high {{ color: #34d399; }}
                .delta-medium {{ color: #fcd34d; }}
                .delta-low {{ color: #fdba74; }}
                .raw-text-card {{
                    background: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 12px 15px;
                    font-size: 12px;
                    color: #94a3b8;
                    line-height: 1.5;
                }}
                .raw-text-card code {{
                    color: #f1f5f9;
                    display: block;
                    margin-top: 6px;
                    word-break: break-all;
                }}
                @media (max-width: 820px) {{
                    .content-grid {{
                        flex-direction: column;
                    }}
                    .left-col {{
                        max-width: 100%;
                    }}
                    .header-card {{
                        flex-direction: column;
                        align-items: flex-start;
                        gap: 10px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header-card">
                <div class="record-title">
                    <span class="record-badge">{t('record_label', idx=current_idx + 1, total=total_count)}</span>
                    <span class="nucleus-badge">{nmr_type}</span>
                </div>
                <div>{doi_link_html}</div>
            </div>

            <div class="content-grid">
                <div class="left-col">
                    <div class="mol-card">
                        {svg_display}
                    </div>
                    <div class="mol-info">
                        <strong>{t('formula')}</strong> {record.get('formula', '-')}<br>
                        <strong>{t('mw')}</strong> {record.get('mw', '-')} g/mol<br>
                        {f'<strong>{t("doc_page")}</strong> {page_str}<br>' if page_str else ''}
                        <strong>{t('smiles')}</strong> <code style="word-break:break-all; font-size:11px;">{smiles}</code>
                    </div>
                    <button type="button" class="btn-bookmark {bookmark_btn_class}" onclick="hgttdAction('toggle_bookmark')">{bookmark_btn_text}</button>
                    <button type="button" class="btn-ketcher" onclick="hgttdAction('load_ketcher_current')">{t('btn_to_ketcher')}</button>
                    <button type="button" class="btn-3d" onclick="hgttdAction('open_3d_current')">{t('btn_to_3d')}</button>
                    <button type="button" class="btn-spectrum" onclick="hgttdAction('open_spectrum_current')">{t('btn_view_spectrum')}</button>
                    <button type="button" class="btn-report" style="display:block; width:100%; text-align:center; background:#059669; color:#fff; border:1px solid #10b981; padding:9px; border-radius:6px; font-weight:bold; font-size:12px; cursor:pointer; margin-top:8px; box-sizing:border-box;" onclick="hgttdAction('export_report_current')">{t('btn_export_report')}</button>
                </div>

                <div class="right-col">
                    <div class="meta-chips">
                        <div class="chip"><strong>{t('solvent')}</strong> {record.get('solvent', '-')}</div>
                        <div class="chip"><strong>{t('frequency')}</strong> {record.get('frequency', '-')}</div>
                        {f'<div class="chip"><strong>{t("atoms")}</strong> {record["atom_number"]}</div>' if record.get('atom_number') else ''}
                        {assign_chip}
                    </div>

                    {spectrum_html}
                    {shift_text_html}
                </div>
            </div>
        </body>
        </html>
        """
        self.results_view.setHtml(html.replace("<head>", f"<head>{ACTION_INTERCEPTOR_SCRIPT}"))

    def render_results(self, results):
        self.current_page_type = "results"
        self.last_results = results

        if not results:
            no_results_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', sans-serif;
                        background-color: #0b1120;
                        color: #f8fafc;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                    }}
                    .card {{
                        text-align: center;
                        padding: 40px;
                        background: #1e293b;
                        border: 1px solid #334155;
                        border-radius: 12px;
                        max-width: 440px;
                    }}
                    h3 {{ color: #f87171; margin-top: 0; font-size: 20px; }}
                    p {{ color: #94a3b8; font-size: 14px; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h3>{t('no_hits_title')}</h3>
                    <p>{t('no_hits_desc')}</p>
                </div>
            </body>
            </html>
            """
            self.results_view.setHtml(no_results_html)
            return

        cards_html = []
        for i, res in enumerate(results):
            db_source = res.get("source_db", "DB")
            nmr_type = res.get("nmr_type", "NMR")
            nucleus_color = res.get("nucleus_color", "#38bdf8")
            smiles = res.get("smiles", "")
            doi_url = res.get("doi_url", "")
            
            if db_source == "MoNa":
                source_badge = '<span class="badge-db" style="background:#7c3aed; color:#f3e8ff;">⚡ MoNa MassBank</span>'
                nucleus_badge = f'<span class="badge-nuc" style="background:#0284c7;">{res.get("ion_mode", "MS")} • {res.get("instrument_type", "MS")}</span>'
                doi_link = ""
                has_assignment = False

                # Top 8 peaks table for MS
                top_peaks = sorted(res.get('normalized_peaks', []), key=lambda p: p[1], reverse=True)[:8]
                peak_rows = []
                for pk_mz, pk_int in top_peaks:
                    peak_rows.append(f"""
                    <tr>
                        <td class="shift-cell" style="color:#38bdf8; font-weight:600;">{pk_mz:.4f}</td>
                        <td><strong>{pk_int:.1f} %</strong></td>
                    </tr>
                    """)
                ms_table_body = "".join(peak_rows) if peak_rows else f"<tr><td colspan='2'>{t('no_spec_data')}</td></tr>"
                spectrum_html = f"""
                <div class="table-container">
                    <table class="spec-table">
                        <thead><tr><th>Fragment m/z</th><th>Rel. Intensität (%)</th></tr></thead>
                        <tbody>{ms_table_body}</tbody>
                    </table>
                </div>
                """
                raw_text_html = ""
                pmz_str = f"m/z {res.get('precursor_mz', 0.0):.4f}" if res.get('precursor_mz') else "-"
                meta_info_html = f"""
                <div class="meta-info">
                    <strong>Precursor:</strong> {pmz_str} ({res.get('adduct', '-')})<br>
                    <strong>Modus:</strong> {res.get('ion_mode', '-')} • MS{res.get('ms_level', 2)}<br>
                    <strong>Gerät:</strong> {res.get('instrument_type', '')} {res.get('instrument', '')}<br>
                    <strong>Kollisionsenergie:</strong> {res.get('collision_energy', '-')}<br>
                </div>
                <h3 class="section-title">Charakteristische Fragmente ({res.get('peaks_count', len(top_peaks))} Peaks)</h3>
                """
                spec_btn_html = f'<button type="button" class="btn-load-spectrum" style="background:#7c3aed; border-color:#a855f7;" onclick="hgttdAction(\'open_ms_spectrum\', {i})">⚡ {t("btn_view_ms_spectrum")}</button>'
            else:
                source_badge = f'<span class="badge-db">{db_source}</span>'
                nucleus_badge = f'<span class="badge-nuc" style="background:{nucleus_color};">{nmr_type}</span>'
                btn_label = "📄 nmrshiftdb2 ↗" if db_source == "nmrshiftdb2" else "📄 DOI ↗"
                doi_link = f'<a href="{doi_url}" target="_blank" class="doi-link">{btn_label}</a>' if doi_url else ""
                
                # Format spectrum with Auto-Assignment
                spec_rows = []
                assign_res = None
                assign_map = {}
                if res.get("spectrum") and res.get("smiles") and ("1H" in nmr_type or "13C" in nmr_type) and auto_assignment_engine.is_available:
                    try:
                        assign_res = auto_assignment_engine.assign_peaks(res["smiles"], res["spectrum"], nucleus=nmr_type)
                        if assign_res and assign_res.get("assigned_peaks"):
                            for ap in assign_res["assigned_peaks"]:
                                assign_map[ap["exp_idx"]] = ap
                    except Exception as e:
                        pass

                has_assignment = bool(assign_map)

                if res.get("spectrum"):
                    is_1h = "1H" in nmr_type
                    for idx, row in enumerate(res["spectrum"]):
                        assign_td = ""
                        if has_assignment:
                            ap = assign_map.get(idx)
                            if ap:
                                conf = ap["confidence"]
                                conf_class = f"assign-badge assign-{conf}"
                                sign = "+" if ap["delta_ppm"] > 0 else ""
                                assign_td = f"""
                                <td><span class="{conf_class}" title="Konfidenz: {t('assign_' + conf + '_conf')}">{ap['calc_label']}</span></td>
                                <td class="calc-shift-cell">{ap['calc_shift']:.2f}</td>
                                <td class="delta-cell delta-{conf}">{sign}{ap['delta_ppm']:.2f}</td>
                                """
                            else:
                                assign_td = """
                                <td><span class="assign-badge assign-none">–</span></td>
                                <td class="calc-shift-cell">–</td>
                                <td class="delta-cell">–</td>
                                """
                        elif not is_1h and "atom_index" in row:
                            try:
                                extra_val = f"C{int(row['atom_index']) + 1}" if str(row['atom_index']) != "-" else "-"
                            except ValueError:
                                extra_val = str(row['atom_index'])
                            assign_td = f"<td>{extra_val}</td>"

                        if is_1h:
                            spec_rows.append(f"""
                            <tr>
                                <td class="shift-cell">{row.get('shift', '-')}</td>
                                <td><span class="mult-badge">{row.get('multiplicity', '-')}</span></td>
                                <td>{row.get('j_coupling', '-')}</td>
                                <td><strong>{row.get('integral', '-')}</strong></td>
                                {assign_td}
                            </tr>
                            """)
                        else:
                            spec_rows.append(f"""
                            <tr>
                                <td class="shift-cell">{row.get('shift', '-')}</td>
                                <td><span class="mult-badge">{row.get('multiplicity', '-')}</span></td>
                                <td>{row.get('j_coupling', '-')}</td>
                                {assign_td}
                            </tr>
                            """)
                    
                    table_body = "".join(spec_rows)
                    
                    if has_assignment:
                        assign_headers = f"""
                        <th>{t('col_assignment_est')}</th>
                        <th>{t('col_calc_shift')}</th>
                        <th>{t('col_deviation')}</th>
                        """
                    elif not is_1h and any("atom_index" in r and r["atom_index"] != "-" for r in res["spectrum"]):
                        assign_headers = f"<th>{t('col_assignment')}</th>"
                    else:
                        assign_headers = ""

                    col_header = f"""
                    <tr>
                        <th>{t('shift_ppm')}</th>
                        <th>{t('multiplicity')}</th>
                        <th>{t('coupling_j')}</th>
                        {('<th>' + t('integrals') + '</th>' if is_1h else '')}
                        {assign_headers}
                    </tr>
                    """
                    
                    spectrum_html = f"""
                    <div class="table-container">
                        <table class="spec-table">
                            <thead>{col_header}</thead>
                            <tbody>{table_body}</tbody>
                        </table>
                    </div>
                    """
                else:
                    spectrum_html = f"<p class='no-spec'>{t('no_spec_data')}</p>"

                raw_text = res.get("shift_text", "")
                raw_text_html = f'<div class="raw-box"><code>{raw_text}</code></div>' if raw_text else ""
                meta_info_html = f"""
                <div class="meta-info">
                    <strong>{t('solvent')}</strong> {res.get('solvent', 'Unbekannt')}<br>
                    <strong>{t('frequency')}</strong> {res.get('frequency', 'Nicht angegeben')}<br>
                    {f'<strong>{t("nmr_validated")}</strong> {res.get("validated")}<br>' if res.get("validated") and res.get("validated") != "N/A" else ''}
                    {f'<strong>{t("nmr_corrected")}</strong> {res.get("corrected")}<br>' if res.get("corrected") and res.get("corrected") != "N/A" else ''}
                </div>
                <h3 class="section-title">{t('spectral_data', nmr_type=nmr_type)}</h3>
                """
                spec_btn_html = f'<button type="button" class="btn-load-spectrum" onclick="hgttdAction(\'open_spectrum_result\', {i})">{t("btn_search_spectrum")}</button>'

            # Check for assigned SVG
            hit_svg = res.get('svg', '')
            if has_assignment and res.get('smiles'):
                try:
                    assigned_svg = auto_assignment_engine.render_assigned_molecule_svg(
                        res['smiles'], assign_res["assigned_peaks"], nucleus=nmr_type, width=320, height=220
                    )
                    if assigned_svg:
                        hit_svg = assigned_svg
                except Exception:
                    pass

            sim_badge = ""
            if "similarity" in res and res["similarity"] is not None:
                sim_score = res["similarity"]
                sim_badge = f'<span class="badge-sim" style="background: linear-gradient(135deg, #8b5cf6, #6366f1); color: #fff; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: bold;">🔮 {sim_score}%</span>'

            hit_name = res.get('name') or res.get('id', '-')
            hit_title_text = t('hit_title', i=i + 1, name=hit_name)

            cards_html.append(f"""
            <div class="card">
                <div class="card-header">
                    <div class="title-left">
                        <h2>{hit_title_text}</h2>
                        <span class="id-badge">ID: {res.get('id', '-')}</span>
                        {source_badge}
                        {nucleus_badge}
                        {sim_badge}
                    </div>
                    <div>{doi_link}</div>
                </div>
                <div class="card-body">
                    <div class="mol-column">
                        <div class="svg-container">
                            {hit_svg}
                        </div>
                        <div class="mol-details">
                            <strong>{t('formula')}</strong> {res.get('formula', '-')}<br>
                            <strong>{t('mw')}</strong> {res.get('mw', '-')} g/mol<br>
                            <button type="button" class="btn-load-bookmark {'btn-bookmark-active' if logbook_manager.is_favorite(smiles) else ''}" onclick="hgttdAction('toggle_bookmark_result', {i})">{'⭐ ' + t('btn_toggle_bookmark_active') if logbook_manager.is_favorite(smiles) else '⭐ ' + t('btn_toggle_bookmark')}</button>
                            <button type="button" class="btn-load-ketcher" onclick="hgttdAction('load_ketcher_result', {i})">{t('btn_search_ketcher')}</button>
                            <button type="button" class="btn-load-3d" onclick="hgttdAction('open_3d_result', {i})">{t('btn_search_3d')}</button>
                            {spec_btn_html}
                        </div>
                    </div>
                    <div class="info-column">
                        {meta_info_html}
                        {spectrum_html}
                        {raw_text_html}
                    </div>
                </div>
            </div>
            """)

        is_substructure = getattr(self, 'last_search_mode', 'exact') == 'substructure'
        is_similarity = getattr(self, 'last_search_mode', 'exact') == 'similarity'
        
        if is_substructure:
            header_text = t('results_header_substructure', count=len(results))
            sub_badge = f'<span class="badge-sub">{t("substructure_highlight_badge")}</span>'
        elif is_similarity:
            min_thresh = int(getattr(self.search_worker, 'min_similarity', 0.7) * 100) if hasattr(self, 'search_worker') and self.search_worker else 70
            header_text = t('results_header_similarity', count=len(results), threshold=min_thresh)
            sub_badge = f'<span class="badge-sub" style="background:#6366f1;">🔮 Morgan Fingerprints (ECFP4)</span>'
        else:
            header_text = t('results_header', count=len(results))
            sub_badge = ''

        results_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                    background-color: #0b1120;
                    margin: 0;
                    padding: 20px;
                    color: #f1f5f9;
                }}
                .results-header {{
                    margin-bottom: 20px;
                    font-size: 15px;
                    color: #94a3b8;
                    display: flex;
                    justify-content: space-between;
                }}
                .card {{
                    background: #1e293b;
                    border-radius: 12px;
                    margin-bottom: 25px;
                    border: 1px solid #334155;
                    overflow: hidden;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                }}
                .card-header {{
                    background-color: #0f172a;
                    padding: 14px 20px;
                    border-bottom: 1px solid #334155;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .title-left {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    flex-wrap: wrap;
                }}
                .card-header h2 {{
                    margin: 0;
                    font-size: 16px;
                    color: #f8fafc;
                }}
                .id-badge {{
                    background-color: #334155;
                    color: #cbd5e1;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                .badge-db {{
                    background: #2563eb;
                    color: #fff;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                .badge-nuc {{
                    color: #000;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                .doi-link {{
                    color: #38bdf8;
                    text-decoration: none;
                    background: #1e293b;
                    border: 1px solid #0284c7;
                    padding: 4px 10px;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                .doi-link:hover {{ background: #0284c7; color: white; }}
                .card-body {{
                    display: flex;
                    padding: 20px;
                    gap: 20px;
                }}
                .mol-column {{
                    flex: 1;
                    max-width: 420px;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }}
                .svg-container {{
                    background: #ffffff;
                    border-radius: 8px;
                    padding: 10px;
                }}
                .svg-container svg {{
                    width: 100%;
                    height: auto;
                    display: block;
                }}
                .mol-details {{
                    background: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 10px 12px;
                    font-size: 12px;
                    color: #cbd5e1;
                }}
                .btn-load-bookmark {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #1e293b;
                    color: #fef08a;
                    border: 1px solid #ca8a04;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                    margin-top: 8px;
                    cursor: pointer;
                    box-sizing: border-box;
                    transition: all 0.15s;
                }}
                .btn-load-bookmark:hover {{ background: #854d0e; color: #fff; }}
                .btn-load-bookmark.btn-bookmark-active {{
                    background: #ca8a04;
                    color: #000;
                    border-color: #facc15;
                }}
                .btn-load-ketcher {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #2563eb;
                    color: white;
                    border: 1px solid #3b82f6;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                    margin-top: 8px;
                    cursor: pointer;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-load-ketcher:hover {{ background: #1d4ed8; }}
                .btn-load-3d {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #059669;
                    color: #ffffff;
                    border: 1px solid #10b981;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                    margin-top: 6px;
                    cursor: pointer;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-load-3d:hover {{
                    background: #10b981;
                    color: #022c22;
                }}
                .btn-load-spectrum {{
                    display: block;
                    width: 100%;
                    text-align: center;
                    background: #7c3aed;
                    color: #ffffff;
                    border: 1px solid #8b5cf6;
                    padding: 8px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                    margin-top: 6px;
                    cursor: pointer;
                    box-sizing: border-box;
                    transition: background 0.15s;
                }}
                .btn-load-spectrum:hover {{
                    background: #6d28d9;
                }}
                .info-column {{
                    flex: 1.3;
                    display: flex;
                    flex-direction: column;
                }}
                .meta-info {{
                    font-size: 13px;
                    line-height: 1.6;
                    color: #cbd5e1;
                    margin-bottom: 12px;
                    background: #0f172a;
                    padding: 10px 14px;
                    border-radius: 6px;
                    border: 1px solid #334155;
                }}
                .section-title {{
                    margin-top: 0;
                    margin-bottom: 10px;
                    font-size: 14px;
                    color: #38bdf8;
                }}
                .table-container {{
                    background: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    max-height: 380px;
                    overflow-y: auto;
                }}
                .spec-table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                }}
                .spec-table th {{
                    background: #1e293b;
                    color: #94a3b8;
                    padding: 8px 12px;
                    text-align: left;
                    position: sticky;
                    top: 0;
                    border-bottom: 1px solid #334155;
                }}
                .spec-table td {{
                    padding: 7px 12px;
                    border-bottom: 1px solid #1e293b;
                    color: #e2e8f0;
                }}
                .spec-table tr:hover td {{
                    background: #334155;
                }}
                .shift-cell {{
                    font-family: monospace;
                    font-weight: bold;
                    color: #38bdf8;
                }}
                .mult-badge {{
                    background: #1e293b;
                    padding: 2px 5px;
                    border-radius: 4px;
                    border: 1px solid #475569;
                    font-family: monospace;
                }}
                .assign-badge {{
                    padding: 2px 7px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 700;
                    display: inline-block;
                }}
                .assign-high {{
                    background: #064e3b;
                    color: #34d399;
                    border: 1px solid #059669;
                }}
                .assign-medium {{
                    background: #78350f;
                    color: #fcd34d;
                    border: 1px solid #d97706;
                }}
                .assign-low {{
                    background: #7c2d12;
                    color: #fdba74;
                    border: 1px solid #ea580c;
                }}
                .assign-none {{
                    background: #1e293b;
                    color: #64748b;
                    border: 1px solid #334155;
                }}
                .calc-shift-cell {{
                    font-family: 'Consolas', monospace;
                    color: #a5b4fc;
                    font-size: 12px;
                }}
                .delta-cell {{
                    font-family: 'Consolas', monospace;
                    font-size: 11px;
                    font-weight: 600;
                }}
                .delta-high {{ color: #34d399; }}
                .delta-medium {{ color: #fcd34d; }}
                .delta-low {{ color: #fdba74; }}
                .badge-sub {{
                    background: #0284c7;
                    color: #ffffff;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    margin-left: 10px;
                }}
                .raw-box {{
                    margin-top: 10px;
                    background: #0f172a;
                    border: 1px solid #334155;
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 11px;
                    color: #94a3b8;
                    word-break: break-all;
                }}
                @media (max-width: 820px) {{
                    .card-body {{
                        flex-direction: column;
                    }}
                    .mol-column {{
                        max-width: 100%;
                    }}
                    .card-header {{
                        flex-direction: column;
                        align-items: flex-start;
                        gap: 8px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="results-header">
                <div><strong>{header_text}</strong>{sub_badge}</div>
                <div>{t('results_brand')}</div>
            </div>
            {"".join(cards_html)}
        </body>
        </html>
        """
        self.set_results_html(results_html.replace("<head>", f"<head>{ACTION_INTERCEPTOR_SCRIPT}"))

    def set_results_html(self, html):
        """
        Loads HTML into results_view. For large documents (e.g. 100+ SVG molecule cards, >2MB),
        Chromium's internal data: URL limit causes setHtml() to fail silently.
        Writing to a local cache file bypasses this limitation cleanly and reliably.
        """
        try:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nmr_exp", ".cache")
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, "results_view.html")
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(html)
            self.results_view.load(QUrl.fromLocalFile(cache_file))
        except Exception as e:
            print(f"[ModernMainWindow] Warnung beim Speichern des HTML-Caches: {e}. Verwende setHtml-Fallback.")
            self.results_view.setHtml(html)

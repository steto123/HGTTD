import os
import json
from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QTabWidget, QFrame, QMessageBox, QMenu
)
from PySide6.QtGui import QIcon, QColor, QFont

from logbook_manager import logbook_manager
from i18n import t

class LogbookWidget(QWidget):
    """
    Dedicated persistent logbook and research notebook panel:
    - View Bookmarks / Favorites with tags, notes, and direct actions.
    - View recent browsing & search history.
    - Add/Edit personal notes and tags per molecule.
    - Jump directly to Ketcher (2D), 3D Viewer, or Spectrum Viewer.
    """
    load_to_ketcher_requested = Signal(str)
    open_3d_requested = Signal(str)
    open_spectrum_requested = Signal(dict)
    open_record_in_details_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_smiles = None
        self.selected_mol_data = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Header toolbar
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        self.lbl_title = QLabel(f"📔 {t('logbook_title')}")
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        self.btn_refresh = QPushButton(f"🔄 {t('logbook_refresh')}")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                padding: 5px 12px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #334155;
                color: #38bdf8;
            }
        """)
        self.btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.btn_refresh)

        self.btn_clear_history = QPushButton(f"🗑️ {t('logbook_clear_history')}")
        self.btn_clear_history.setCursor(Qt.PointingHandCursor)
        self.btn_clear_history.setStyleSheet("""
            QPushButton {
                background: #3f1d1d;
                color: #fca5a5;
                border: 1px solid #7f1d1d;
                padding: 5px 12px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #7f1d1d;
                color: #ffffff;
            }
        """)
        self.btn_clear_history.clicked.connect(self.clear_history_prompt)
        header_layout.addWidget(self.btn_clear_history)

        main_layout.addWidget(header_frame)

        # Splitter: Left list (Favorites / History) & Right details/notes editor
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1e293b;
                width: 3px;
            }
        """)

        # Left panel: Sub-tabs (Bookmarks ⭐ vs. History ⏱️)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Search bar for bookmarks
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(t("logbook_search_placeholder"))
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #0b1120;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.search_input.textChanged.connect(self.on_search_changed)
        left_layout.addWidget(self.search_input)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background: #0b1120;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #1e293b;
                color: #94a3b8;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #0b1120;
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
            }
        """)

        # Table: Bookmarks
        self.table_bookmarks = self._create_table(["⭐", t("logbook_col_name"), t("logbook_col_formula"), t("logbook_col_tags"), t("logbook_col_date")])
        self.table_bookmarks.itemSelectionChanged.connect(self.on_bookmark_selected)
        self.sub_tabs.addTab(self.table_bookmarks, f"⭐ {t('logbook_tab_bookmarks')}")

        # Table: Recent History
        self.table_history = self._create_table([t("logbook_col_type"), t("logbook_col_info"), t("logbook_col_time")])
        self.table_history.itemSelectionChanged.connect(self.on_history_selected)
        self.sub_tabs.addTab(self.table_history, f"⏱️ {t('logbook_tab_history')}")

        left_layout.addWidget(self.sub_tabs)
        splitter.addWidget(left_widget)

        # Right panel: Note editor & molecule preview/actions
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Selected molecule info box
        self.info_box = QFrame()
        self.info_box.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        info_layout = QVBoxLayout(self.info_box)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(6)

        self.lbl_selected_title = QLabel(t("logbook_no_selection"))
        self.lbl_selected_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f1f5f9;")
        self.lbl_selected_title.setWordWrap(True)
        info_layout.addWidget(self.lbl_selected_title)

        self.lbl_selected_meta = QLabel("")
        self.lbl_selected_meta.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self.lbl_selected_meta.setWordWrap(True)
        info_layout.addWidget(self.lbl_selected_meta)

        self.lbl_selected_smiles = QLabel("")
        self.lbl_selected_smiles.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; color: #38bdf8;")
        self.lbl_selected_smiles.setWordWrap(True)
        self.lbl_selected_smiles.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(self.lbl_selected_smiles)

        # Quick action buttons for selected molecule
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)

        self.btn_fav_toggle = QPushButton("⭐ " + t("logbook_toggle_fav"))
        self.btn_fav_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_fav_toggle.setStyleSheet("""
            QPushButton {
                background: #854d0e;
                color: #fef08a;
                border: 1px solid #ca8a04;
                padding: 6px 10px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background: #ca8a04; color: #000; }
        """)
        self.btn_fav_toggle.clicked.connect(self.toggle_selected_favorite)
        actions_layout.addWidget(self.btn_fav_toggle)

        self.btn_action_ketcher = QPushButton("📥 Ketcher")
        self.btn_action_ketcher.setCursor(Qt.PointingHandCursor)
        self.btn_action_ketcher.setStyleSheet("""
            QPushButton {
                background: #1d4ed8;
                color: #ffffff;
                border: 1px solid #3b82f6;
                padding: 6px 10px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background: #2563eb; }
        """)
        self.btn_action_ketcher.clicked.connect(self.load_selected_to_ketcher)
        actions_layout.addWidget(self.btn_action_ketcher)

        self.btn_action_3d = QPushButton("🔬 3D")
        self.btn_action_3d.setCursor(Qt.PointingHandCursor)
        self.btn_action_3d.setStyleSheet("""
            QPushButton {
                background: #047857;
                color: #ffffff;
                border: 1px solid #10b981;
                padding: 6px 10px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background: #059669; }
        """)
        self.btn_action_3d.clicked.connect(self.load_selected_to_3d)
        actions_layout.addWidget(self.btn_action_3d)

        self.btn_action_spec = QPushButton("📈 NMR/MS")
        self.btn_action_spec.setCursor(Qt.PointingHandCursor)
        self.btn_action_spec.setStyleSheet("""
            QPushButton {
                background: #6d28d9;
                color: #ffffff;
                border: 1px solid #8b5cf6;
                padding: 6px 10px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background: #7c3aed; }
        """)
        self.btn_action_spec.clicked.connect(self.load_selected_to_spectrum)
        actions_layout.addWidget(self.btn_action_spec)

        info_layout.addLayout(actions_layout)
        right_layout.addWidget(self.info_box)

        # Tags input
        lbl_tags = QLabel(f"🏷️ {t('logbook_tags_label')}")
        lbl_tags.setStyleSheet("font-size: 13px; font-weight: 600; color: #cbd5e1;")
        right_layout.addWidget(lbl_tags)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText(t("logbook_tags_placeholder"))
        self.tags_input.setStyleSheet("""
            QLineEdit {
                background: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
        """)
        right_layout.addWidget(self.tags_input)

        # Research Notes input
        lbl_notes = QLabel(f"📝 {t('logbook_notes_label')}")
        lbl_notes.setStyleSheet("font-size: 13px; font-weight: 600; color: #cbd5e1;")
        right_layout.addWidget(lbl_notes)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText(t("logbook_notes_placeholder"))
        self.notes_edit.setStyleSheet("""
            QTextEdit {
                background: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                line-height: 1.5;
            }
            QTextEdit:focus {
                border-color: #38bdf8;
            }
        """)
        right_layout.addWidget(self.notes_edit)

        # Save Notes Button
        self.btn_save_notes = QPushButton(f"💾 {t('logbook_save_notes')}")
        self.btn_save_notes.setCursor(Qt.PointingHandCursor)
        self.btn_save_notes.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: #ffffff;
                border: 1px solid #38bdf8;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #0369a1;
            }
        """)
        self.btn_save_notes.clicked.connect(self.save_notes_and_tags)
        right_layout.addWidget(self.btn_save_notes)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)

        # Load initial data
        self.refresh_data()

    def _create_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setStyleSheet("""
            QTableWidget {
                background: #0b1120;
                color: #e2e8f0;
                border: none;
                gridline-color: #1e293b;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #1e293b;
            }
            QTableWidget::item:selected {
                background: #1e293b;
                color: #38bdf8;
            }
            QHeaderView::section {
                background: #0f172a;
                color: #94a3b8;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #334155;
                font-weight: 600;
            }
        """)
        return table

    def refresh_data(self):
        self.load_bookmarks()
        self.load_history()

    def load_bookmarks(self):
        search_query = self.search_input.text().strip()
        favs = logbook_manager.get_favorites(search_query)

        self.table_bookmarks.blockSignals(True)
        self.table_bookmarks.setRowCount(len(favs))
        
        # Configure column sizes
        self.table_bookmarks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_bookmarks.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_bookmarks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_bookmarks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_bookmarks.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

        for row, item in enumerate(favs):
            star_item = QTableWidgetItem("⭐")
            star_item.setTextAlignment(Qt.AlignCenter)
            self.table_bookmarks.setItem(row, 0, star_item)

            name = item.get("name") or "Unbekannt"
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, item)
            self.table_bookmarks.setItem(row, 1, name_item)

            formula_item = QTableWidgetItem(item.get("formula", "-"))
            self.table_bookmarks.setItem(row, 2, formula_item)

            tags_item = QTableWidgetItem(item.get("tags", ""))
            self.table_bookmarks.setItem(row, 3, tags_item)

            ts = item.get("last_seen_ts") or item.get("first_seen_ts")
            date_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else "-"
            date_item = QTableWidgetItem(date_str)
            self.table_bookmarks.setItem(row, 4, date_item)

        self.table_bookmarks.blockSignals(False)

    def load_history(self):
        acts = logbook_manager.get_recent_activities(50)
        self.table_history.blockSignals(True)
        self.table_history.setRowCount(len(acts))

        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        type_icons = {
            "search": "🔍 Suche",
            "browse": "🌌 Blättern",
            "view_3d": "🔬 3D",
            "view_spectrum": "📈 Spektrum",
            "bookmark": "⭐ Favorit"
        }

        for row, item in enumerate(acts):
            act_type = item.get("activity_type", "event")
            type_label = type_icons.get(act_type, act_type.capitalize())
            type_item = QTableWidgetItem(type_label)
            self.table_history.setItem(row, 0, type_item)

            info = item.get("title") or item.get("query_info") or item.get("smiles") or "-"
            info_item = QTableWidgetItem(info)
            info_item.setData(Qt.UserRole, item)
            self.table_history.setItem(row, 1, info_item)

            ts = item.get("timestamp")
            time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S (%d.%m.)") if ts else "-"
            time_item = QTableWidgetItem(time_str)
            self.table_history.setItem(row, 2, time_item)

        self.table_history.blockSignals(False)

    def on_search_changed(self):
        self.load_bookmarks()

    def on_bookmark_selected(self):
        rows = self.table_bookmarks.selectedItems()
        if not rows:
            return
        item_data = self.table_bookmarks.item(self.table_bookmarks.currentRow(), 1).data(Qt.UserRole)
        self.display_molecule_details(item_data)

    def on_history_selected(self):
        rows = self.table_history.selectedItems()
        if not rows:
            return
        item_data = self.table_history.item(self.table_history.currentRow(), 1).data(Qt.UserRole)
        smiles = item_data.get("smiles")
        if smiles:
            meta = logbook_manager.get_molecule_meta(smiles)
            if meta:
                self.display_molecule_details(meta)
            else:
                self.display_molecule_details({"smiles": smiles, "name": item_data.get("title", "")})

    def display_molecule_details(self, mol_dict):
        if not mol_dict:
            return
        self.selected_mol_data = mol_dict
        self.selected_smiles = mol_dict.get("smiles", "")
        
        name = mol_dict.get("name") or "Molekül"
        formula = mol_dict.get("formula", "")
        db = mol_dict.get("source_db", "")
        nmr_type = mol_dict.get("nmr_type", "")

        self.lbl_selected_title.setText(f"{name}")
        meta_parts = []
        if formula: meta_parts.append(f"Formel: {formula}")
        if db: meta_parts.append(f"DB: {db}")
        if nmr_type: meta_parts.append(f"Kern: {nmr_type}")
        self.lbl_selected_meta.setText(" • ".join(meta_parts))
        self.lbl_selected_smiles.setText(f"SMILES: {self.selected_smiles}")

        # Update bookmark toggle button text
        is_fav = bool(mol_dict.get("is_favorite", 0))
        self.btn_fav_toggle.setText("⭐ Entfernen" if is_fav else "⭐ Als Favorit merken")

        # Load notes and tags
        self.tags_input.setText(mol_dict.get("tags", ""))
        self.notes_edit.setText(mol_dict.get("notes", ""))

    def toggle_selected_favorite(self):
        if not self.selected_smiles:
            return
        new_fav = logbook_manager.toggle_favorite(self.selected_smiles)
        if self.selected_mol_data:
            self.selected_mol_data["is_favorite"] = 1 if new_fav else 0
        self.btn_fav_toggle.setText("⭐ Entfernen" if new_fav else "⭐ Als Favorit merken")
        self.refresh_data()

    def save_notes_and_tags(self):
        if not self.selected_smiles:
            return
        tags = self.tags_input.text().strip()
        notes = self.notes_edit.toPlainText().strip()
        logbook_manager.update_notes_tags(self.selected_smiles, notes=notes, tags=tags)
        QMessageBox.information(self, t("logbook_saved_title"), t("logbook_saved_msg"))
        self.refresh_data()

    def load_selected_to_ketcher(self):
        if self.selected_smiles:
            self.load_to_ketcher_requested.emit(self.selected_smiles)

    def load_selected_to_3d(self):
        if self.selected_smiles:
            self.open_3d_requested.emit(self.selected_smiles)

    def load_selected_to_spectrum(self):
        if not self.selected_mol_data:
            return
        data_json = self.selected_mol_data.get("data_json")
        rec = None
        if data_json:
            try:
                rec = json.loads(data_json)
            except Exception:
                pass
        if not rec:
            rec = {
                "smiles": self.selected_smiles,
                "name": self.selected_mol_data.get("name", ""),
                "formula": self.selected_mol_data.get("formula", ""),
                "source_db": self.selected_mol_data.get("source_db", "NMRexp"),
                "nmr_type": self.selected_mol_data.get("nmr_type", "1H"),
                "spectrum": []
            }
        self.open_spectrum_requested.emit(rec)

    def clear_history_prompt(self):
        reply = QMessageBox.question(
            self,
            t("logbook_clear_confirm_title"),
            t("logbook_clear_confirm_msg"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logbook_manager.clear_history()
            self.refresh_data()

    def retranslate_ui(self):
        self.lbl_title.setText(f"📔 {t('logbook_title')}")
        self.btn_refresh.setText(f"🔄 {t('logbook_refresh')}")
        self.btn_clear_history.setText(f"🗑️ {t('logbook_clear_history')}")
        self.search_input.setPlaceholderText(t("logbook_search_placeholder"))
        self.sub_tabs.setTabText(0, f"⭐ {t('logbook_tab_bookmarks')}")
        self.sub_tabs.setTabText(1, f"⏱️ {t('logbook_tab_history')}")
        self.btn_save_notes.setText(f"💾 {t('logbook_save_notes')}")

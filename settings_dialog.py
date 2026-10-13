import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QComboBox, QFrame, QGroupBox
)

import config_manager
from i18n import t, set_current_language, get_current_language
from mona_manager import mona_manager, PARQUET_FILE as MONA_PARQUET_FILE

class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("settings_title"))
        self.resize(720, 520)
        self.setMinimumSize(600, 440)

        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                color: #f1f5f9;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: bold;
                color: #38bdf8;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }
            QLineEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QComboBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                min-width: 140px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #2563eb;
                border: 1px solid #334155;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton#SaveBtn {
                background-color: #10b981;
                color: #022c22;
                border: 1px solid #34d399;
                font-weight: bold;
            }
            QPushButton#SaveBtn:hover {
                background-color: #059669;
            }
            QPushButton#BrowseBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
            }
            QPushButton#BrowseBtn:hover {
                background-color: #1d4ed8;
            }
        """)

        self.setup_ui()
        self.load_values()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title banner
        header = QLabel(t("settings_title"))
        header.setStyleSheet("font-size: 18px; font-weight: 800; color: #38bdf8;")
        main_layout.addWidget(header)

        # 1. Language Group
        lang_group = QGroupBox("🌐 " + t("settings_lang_label"))
        lang_layout = QHBoxLayout(lang_group)
        lang_layout.setContentsMargins(14, 14, 14, 14)
        
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("🇩🇪 Deutsch (German)", "de")
        self.combo_lang.addItem("🇬🇧 English (Englisch)", "en")
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        main_layout.addWidget(lang_group)

        # 2. Database Paths Group
        db_group = QGroupBox("🗄️ Datenbank-Pfade / Database Locations")
        db_layout = QVBoxLayout(db_group)
        db_layout.setContentsMargins(14, 14, 14, 14)
        db_layout.setSpacing(12)

        # NMRShiftDB2 Source Path
        db_layout.addWidget(QLabel(t("settings_source_sdf")))
        source_row = QHBoxLayout()
        self.edit_source = QLineEdit()
        self.edit_source.textChanged.connect(self.update_status_labels)
        source_row.addWidget(self.edit_source)

        btn_browse_source = QPushButton(t("settings_browse"), objectName="BrowseBtn")
        btn_browse_source.clicked.connect(self.browse_source_sdf)
        source_row.addWidget(btn_browse_source)
        db_layout.addLayout(source_row)

        self.label_source_status = QLabel("")
        self.label_source_status.setStyleSheet("font-size: 11px; margin-bottom: 6px;")
        db_layout.addWidget(self.label_source_status)

        # NMRShiftDB2 Local Fallback (informative)
        db_layout.addWidget(QLabel(t("settings_local_sdf")))
        self.edit_local = QLineEdit()
        self.edit_local.setReadOnly(True)
        self.edit_local.setStyleSheet("background-color: #0f172a; color: #94a3b8;")
        db_layout.addWidget(self.edit_local)

        self.label_local_status = QLabel("")
        self.label_local_status.setStyleSheet("font-size: 11px; margin-bottom: 6px;")
        db_layout.addWidget(self.label_local_status)

        # NMRexp Parquet Path
        db_layout.addWidget(QLabel(t("settings_nmrexp_path")))
        parquet_row = QHBoxLayout()
        self.edit_parquet = QLineEdit()
        self.edit_parquet.textChanged.connect(self.update_status_labels)
        parquet_row.addWidget(self.edit_parquet)

        btn_browse_parquet = QPushButton(t("settings_browse"), objectName="BrowseBtn")
        btn_browse_parquet.clicked.connect(self.browse_nmrexp_parquet)
        parquet_row.addWidget(btn_browse_parquet)
        db_layout.addLayout(parquet_row)

        self.label_parquet_status = QLabel("")
        self.label_parquet_status.setStyleSheet("font-size: 11px; margin-bottom: 6px;")
        db_layout.addWidget(self.label_parquet_status)

        # MoNa MassBank MS Path / Status
        db_layout.addWidget(QLabel("⚡ MoNa MassBank (MS) Parquet-Datenbank"))
        self.label_mona_status = QLabel("")
        self.label_mona_status.setStyleSheet("font-size: 11px;")
        db_layout.addWidget(self.label_mona_status)

        main_layout.addWidget(db_group)

        main_layout.addStretch()

        # Dialog Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton(t("settings_cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton(t("settings_save"), objectName="SaveBtn")
        btn_save.clicked.connect(self.save_settings)
        btn_row.addWidget(btn_save)

        main_layout.addLayout(btn_row)

    def load_values(self):
        cfg = config_manager.load_config()
        
        # Language
        current_lang = cfg.get("language", "de")
        idx = self.combo_lang.findData(current_lang)
        if idx >= 0:
            self.combo_lang.setCurrentIndex(idx)

        # Paths
        self.edit_source.setText(cfg.get("source_db_path", ""))
        self.edit_local.setText(cfg.get("local_sdf_name", "nmrshiftdb2_3D_OPTIMIZED_with_props.sdf"))
        self.edit_parquet.setText(cfg.get("nmrexp_parquet_path", ""))

        self.update_status_labels()

    def update_status_labels(self):
        # Check source
        source_path = self.edit_source.text().strip()
        if source_path and os.path.exists(source_path):
            self.label_source_status.setText(f"<span style='color:#34d399;'>{t('settings_source_status_ok')}</span> ({os.path.getsize(source_path):,} Bytes)")
        else:
            self.label_source_status.setText(f"<span style='color:#f59e0b;'>{t('settings_source_status_missing')}</span>")

        # Check local
        local_name = self.edit_local.text().strip()
        local_full = os.path.abspath(local_name)
        if os.path.exists(local_full):
            self.label_local_status.setText(f"<span style='color:#34d399;'>{t('settings_local_status_ok')}</span> ({os.path.getsize(local_full):,} Bytes)")
        else:
            self.label_local_status.setText(f"<span style='color:#ef4444;'>{t('settings_local_status_missing')}</span>")

        # Check parquet
        parq_path = self.edit_parquet.text().strip()
        if parq_path and os.path.exists(parq_path):
            self.label_parquet_status.setText(f"<span style='color:#34d399;'>✓ Parquet gefunden</span> ({os.path.getsize(parq_path):,} Bytes)")
        else:
            self.label_parquet_status.setText("<span style='color:#ef4444;'>⚠ Parquet-Datei nicht gefunden</span>")

        # Check MoNa
        if mona_manager.is_database_available():
            sz_mb = os.path.getsize(MONA_PARQUET_FILE) / (1024 * 1024)
            self.label_mona_status.setText(
                f"<span style='color:#34d399;'>✓ MoNa bereit</span>: {mona_manager.total_records:,} Spektren ({sz_mb:.1f} MB Parquet)"
            )
        else:
            self.label_mona_status.setText("<span style='color:#ef4444;'>⚠ MoNa-Datenbank nicht kompiliert</span>")

    def browse_source_sdf(self):
        cur_file = self.edit_source.text()
        start_dir = os.path.dirname(cur_file) if cur_file and os.path.exists(os.path.dirname(cur_file)) else "."
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "NMRShiftDB2 Quell-Datei (SDF) auswählen",
            start_dir,
            "SDF / Molfile (*.sdf *.mol);;Alle Dateien (*.*)"
        )
        if file_path:
            self.edit_source.setText(file_path)

    def browse_nmrexp_parquet(self):
        cur_file = self.edit_parquet.text()
        start_dir = os.path.dirname(cur_file) if cur_file and os.path.exists(os.path.dirname(cur_file)) else "."
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "NMRexp Parquet-Datei auswählen",
            start_dir,
            "Parquet Datei (*.parquet);;Alle Dateien (*.*)"
        )
        if file_path:
            self.edit_parquet.setText(file_path)

    def save_settings(self):
        new_lang = self.combo_lang.currentData()
        source_path = self.edit_source.text().strip()
        local_name = self.edit_local.text().strip()
        parquet_path = self.edit_parquet.text().strip()

        cfg = {
            "language": new_lang,
            "source_db_path": source_path,
            "local_sdf_name": local_name,
            "nmrexp_parquet_path": parquet_path
        }

        success = config_manager.save_config(cfg)
        if success:
            set_current_language(new_lang)
            self.settings_saved.emit()
            QMessageBox.information(self, t("settings_title"), t("settings_saved_msg"))
            self.accept()
        else:
            QMessageBox.critical(self, "Fehler", "Konnte config.json nicht speichern.")

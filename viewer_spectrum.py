"""
viewer_spectrum.py
Interactive high-performance NMR Spectrum Viewer Widget for HGTTD.
Synthesizes continuous Lorentzian NMR spectra from experimental peak data
(NMRexp 6 nuclei: 1H, 13C, 19F, 31P, 11B, 29Si and nmrshiftdb2 13C),
provides real-time linewidth adjustment, smooth 60 FPS zoom/pan,
cumulative integral curves, peak picking tags, and standard IUPAC JCAMP-DX export.
"""

import os
import sys
import json
import re
from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QSlider, QDoubleSpinBox, QComboBox, QCheckBox, QFileDialog, 
    QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage

from spectrum_generator import (
    parse_spectrum_peaks,
    expand_multiplet_components,
    calculate_spectrum_grid,
    export_jcamp_dx,
    DEFAULT_FREQUENCIES,
    DEFAULT_RANGES,
    NMRPeak
)
from auto_assignment_engine import auto_assignment_engine
from report_generator import generate_html_report
from i18n import t


def detect_nucleus(record):
    """Detects nucleus key from record dict."""
    if not record:
        return "1H"
    nmr_type = record.get("nmr_type", "")
    for nuc in ["1H", "13C", "19F", "31P", "11B", "29Si"]:
        if nuc in nmr_type:
            return nuc
    if "1H" in str(record.get("nucleus", "")):
        return "1H"
    if "13C" in str(record.get("nucleus", "")):
        return "13C"
    return "1H"


def detect_frequency(record, nucleus="1H"):
    """Extracts observe frequency in MHz from record, or defaults to nucleus standard."""
    if not record:
        return DEFAULT_FREQUENCIES.get(nucleus, 400.13)
    freq_raw = record.get("frequency", "")
    match = re.search(r"[-+]?\d*\.\d+|\d+", str(freq_raw))
    if match:
        try:
            val = float(match.group(0))
            if 10.0 <= val <= 2000.0:
                return val
        except ValueError:
            pass
    return DEFAULT_FREQUENCIES.get(nucleus, 400.13)


def get_cache_dir():
    """Returns local HTML cache directory path."""
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nmr_exp", ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


class CustomSpectrumPage(QWebEnginePage):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if message.startswith("HGTTD_HIGHLIGHT:"):
            payload = message[len("HGTTD_HIGHLIGHT:"):]
            try:
                indices = json.loads(payload)
                self.parent_widget.highlight_atoms_requested.emit(indices)
            except Exception:
                pass
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)


class SpectrumViewerWidget(QWidget):
    """
    Embedded NMR Spectrum Synthesizer & Interactive Viewer Widget.
    """
    switch_to_details_requested = Signal()
    highlight_atoms_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_record = None
        self.current_peaks = []
        self.current_nucleus = "1H"
        self.current_freq = 400.13
        self.current_fwhm = 1.2
        self.current_grid = None
        self.current_assignment = None
        self.is_page_loaded = False

        # Split / Mirror Comparison Reference
        self.reference_record = None
        self.reference_peaks = []
        self.reference_grid = None
        
        self.setStyleSheet("""
            SpectrumViewerWidget {
                background-color: #0b1120;
                color: #f1f5f9;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #f1f5f9;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton#PrimaryBtn {
                background-color: #2563eb;
                color: white;
                border: 1px solid #3b82f6;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#ExportBtn {
                background-color: #059669;
                color: white;
                border: 1px solid #10b981;
                font-weight: bold;
            }
            QPushButton#ExportBtn:hover {
                background-color: #10b981;
                color: #022c22;
            }
            QDoubleSpinBox, QComboBox {
                background-color: #0f172a;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 14px;
                background: #1e293b;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 600;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0f172a;
            }
            QCheckBox::indicator:checked {
                background-color: #38bdf8;
                border-color: #7dd3fc;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #1e293b;
                border-radius: 3px;
                border: 1px solid #334155;
            }
            QSlider::sub-page:horizontal {
                background: #0284c7;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #38bdf8;
                border: 1px solid #e0f2fe;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #7dd3fc;
            }
        """)

        self.setup_ui()
        self.show_placeholder()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Bar: Info Chips & Actions
        top_bar = QFrame()
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.setSpacing(10)

        # Info Title & Subtitle
        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        
        self.title_label = QLabel(t("spectrum_title"))
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        self.info_label = QLabel(t("spectrum_no_data"))
        self.info_label.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        info_box.addWidget(self.title_label)
        info_box.addWidget(self.info_label)
        top_layout.addLayout(info_box)

        top_layout.addStretch()

        # Top Buttons
        self.btn_set_ref = QPushButton(t("spectrum_btn_set_ref"))
        self.btn_set_ref.setToolTip("Aktuelles Spektrum als Vergleichs-Referenz merken")
        self.btn_set_ref.clicked.connect(self.pin_current_as_reference)
        top_layout.addWidget(self.btn_set_ref)

        self.btn_clear_ref = QPushButton(t("spectrum_btn_clear_ref"))
        self.btn_clear_ref.setToolTip("Vergleichs-Referenz entfernen")
        self.btn_clear_ref.clicked.connect(self.clear_reference)
        self.btn_clear_ref.setVisible(False)
        top_layout.addWidget(self.btn_clear_ref)

        self.btn_details = QPushButton(t("btn_back_details"))
        self.btn_details.setToolTip("Zurück zur tabellarischen Ansicht")
        self.btn_details.clicked.connect(self.switch_to_details_requested.emit)
        top_layout.addWidget(self.btn_details)

        self.btn_reset_zoom = QPushButton(t("spectrum_reset_zoom"))
        self.btn_reset_zoom.setToolTip("Zoom und Verschiebung auf Vollspektrum zurücksetzen")
        self.btn_reset_zoom.clicked.connect(self.reset_zoom)
        top_layout.addWidget(self.btn_reset_zoom)

        self.btn_export_jcamp = QPushButton(t("spectrum_export_jcamp"), objectName="ExportBtn")
        self.btn_export_jcamp.setToolTip("Spektrum als IUPAC JCAMP-DX 5.01 (.jdx) Datei exportieren")
        self.btn_export_jcamp.clicked.connect(self.export_jcamp)
        top_layout.addWidget(self.btn_export_jcamp)

        self.btn_export_report = QPushButton(t("btn_export_report"), objectName="ExportBtn")
        self.btn_export_report.setToolTip("Vollständigen Laborbericht & Analysenzertifikat als druckbares HTML/PDF exportieren")
        self.btn_export_report.clicked.connect(self.export_report)
        top_layout.addWidget(self.btn_export_report)

        layout.addWidget(top_bar)

        # Control Toolbar: Linewidth, Frequency, Options
        ctrl_bar = QFrame()
        ctrl_bar.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(6, 4, 6, 4)
        ctrl_layout.setSpacing(14)

        # Linewidth (FWHM) Controls
        self.lbl_fwhm = QLabel(t("spectrum_fwhm_label"))
        self.lbl_fwhm.setStyleSheet("font-weight: 600; color: #94a3b8;")
        ctrl_layout.addWidget(self.lbl_fwhm)

        self.slider_fwhm = QSlider(Qt.Horizontal)
        self.slider_fwhm.setMinimum(2)      # 0.2 Hz
        self.slider_fwhm.setMaximum(150)    # 15.0 Hz
        self.slider_fwhm.setValue(12)       # 1.2 Hz
        self.slider_fwhm.setFixedWidth(140)
        self.slider_fwhm.valueChanged.connect(self.on_slider_fwhm_changed)
        ctrl_layout.addWidget(self.slider_fwhm)

        self.spin_fwhm = QDoubleSpinBox()
        self.spin_fwhm.setRange(0.1, 30.0)
        self.spin_fwhm.setSingleStep(0.1)
        self.spin_fwhm.setDecimals(1)
        self.spin_fwhm.setSuffix(" Hz")
        self.spin_fwhm.setValue(1.2)
        self.spin_fwhm.setFixedWidth(80)
        self.spin_fwhm.valueChanged.connect(self.on_spin_fwhm_changed)
        ctrl_layout.addWidget(self.spin_fwhm)

        # Frequency Controls
        self.lbl_freq = QLabel(t("spectrum_freq_label"))
        self.lbl_freq.setStyleSheet("font-weight: 600; color: #94a3b8; margin-left: 10px;")
        ctrl_layout.addWidget(self.lbl_freq)

        self.combo_freq = QComboBox()
        self.combo_freq.addItems(["100 MHz", "200 MHz", "300 MHz", "400 MHz", "500 MHz", "600 MHz", "800 MHz"])
        self.combo_freq.setCurrentText("400 MHz")
        self.combo_freq.setFixedWidth(100)
        self.combo_freq.currentTextChanged.connect(self.on_freq_combo_changed)
        ctrl_layout.addWidget(self.combo_freq)

        # Checkbox Options
        self.chk_labels = QCheckBox(t("spectrum_toggle_labels"))
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self.on_toggle_labels)
        ctrl_layout.addWidget(self.chk_labels)

        self.chk_integrals = QCheckBox(t("spectrum_toggle_integrals"))
        self.chk_integrals.setChecked(True)
        self.chk_integrals.toggled.connect(self.on_toggle_integrals)
        ctrl_layout.addWidget(self.chk_integrals)

        self.chk_assignment = QCheckBox(t("spectrum_toggle_assignment"))
        self.chk_assignment.setChecked(True)
        self.chk_assignment.toggled.connect(self.on_toggle_assignment)
        ctrl_layout.addWidget(self.chk_assignment)

        self.chk_calc_trace = QCheckBox(t("spectrum_toggle_calc_trace"))
        self.chk_calc_trace.setChecked(False)
        self.chk_calc_trace.toggled.connect(self.on_toggle_calc_trace)
        ctrl_layout.addWidget(self.chk_calc_trace)

        self.chk_mirror = QCheckBox(t("spectrum_toggle_mirror"))
        self.chk_mirror.setChecked(True)
        self.chk_mirror.toggled.connect(self.on_toggle_mirror)
        self.chk_mirror.setEnabled(False)
        ctrl_layout.addWidget(self.chk_mirror)

        ctrl_layout.addStretch()

        # Mouse Navigation Hint
        lbl_hint = QLabel(t("spectrum_mouse_hint"))
        lbl_hint.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")
        ctrl_layout.addWidget(lbl_hint)

        layout.addWidget(ctrl_bar)

        # WebEngine View for Canvas Renderer
        self.web_view = QWebEngineView()
        self.custom_page = CustomSpectrumPage(self)
        self.web_view.setPage(self.custom_page)
        self.web_view.setStyleSheet("border-radius: 8px; border: 1px solid #334155; background-color: #070b14;")
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self.web_view.loadFinished.connect(self.on_web_load_finished)
        layout.addWidget(self.web_view)

    def retranslate_ui(self):
        self.btn_details.setText(t("btn_back_details"))
        self.btn_reset_zoom.setText(t("spectrum_reset_zoom"))
        self.btn_export_jcamp.setText(t("spectrum_export_jcamp"))
        self.lbl_fwhm.setText(t("spectrum_fwhm_label"))
        self.lbl_freq.setText(t("spectrum_freq_label"))
        self.chk_labels.setText(t("spectrum_toggle_labels"))
        self.chk_integrals.setText(t("spectrum_toggle_integrals"))
        self.chk_assignment.setText(t("spectrum_toggle_assignment"))
        self.chk_calc_trace.setText(t("spectrum_toggle_calc_trace"))

        if not self.current_record:
            self.show_placeholder()
        else:
            self.update_header_info()

    def show_placeholder(self):
        self.title_label.setText(t("spectrum_title"))
        self.info_label.setText(t("spectrum_no_data"))
        self.btn_reset_zoom.setEnabled(False)
        self.btn_export_jcamp.setEnabled(False)

        placeholder_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: radial-gradient(circle at center, #111827 0%, #030712 100%);
            color: #94a3b8;
            font-family: 'Segoe UI', Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            text-align: center;
        }}
        .icon {{
            font-size: 50px;
            margin-bottom: 16px;
            filter: drop-shadow(0 0 14px rgba(56, 189, 248, 0.4));
        }}
        h2 {{
            color: #38bdf8;
            margin: 0 0 8px 0;
            font-size: 20px;
        }}
        p {{
            font-size: 14px;
            max-width: 480px;
            line-height: 1.6;
            color: #cbd5e1;
            margin: 0;
        }}
        .hint {{
            margin-top: 22px;
            font-size: 12px;
            color: #94a3b8;
            background: #0f172a;
            border: 1px solid #1e293b;
            padding: 12px 20px;
            border-radius: 8px;
            max-width: 520px;
            line-height: 1.5;
        }}
        .hint strong {{
            color: #38bdf8;
        }}
    </style>
</head>
<body>
    <div class="icon">📈</div>
    <h2>{t('spectrum_placeholder_title')}</h2>
    <p>{t('spectrum_placeholder_desc')}</p>
    <div class="hint">
        {t('spectrum_placeholder_hint')}
    </div>
</body>
</html>
"""
        self.web_view.setHtml(placeholder_html)

    def set_record(self, record):
        """Sets active record, parses peaks, and renders synthesized spectrum."""
        if not record or not record.get("spectrum"):
            self.current_record = None
            self.current_peaks = []
            self.show_placeholder()
            return

        self.current_record = record
        self.current_nucleus = detect_nucleus(record)
        self.current_freq = detect_frequency(record, self.current_nucleus)
        
        # Update combo freq
        self.combo_freq.blockSignals(True)
        closest_text = f"{int(round(self.current_freq))} MHz"
        idx = self.combo_freq.findText(closest_text)
        if idx >= 0:
            self.combo_freq.setCurrentIndex(idx)
        else:
            self.combo_freq.setEditText(f"{self.current_freq:.1f} MHz")
        self.combo_freq.blockSignals(False)

        # Parse peaks
        self.current_peaks = parse_spectrum_peaks(record.get("spectrum", []), self.current_nucleus)
        
        # Compute Auto-Assignment if structure and 1H/13C
        self.current_assignment = None
        if self.current_record and self.current_record.get("smiles") and self.current_nucleus in ("1H", "13C") and auto_assignment_engine.is_available:
            try:
                self.current_assignment = auto_assignment_engine.assign_peaks(
                    self.current_record["smiles"], self.current_peaks, self.current_nucleus
                )
            except Exception as e:
                print(f"[viewer_spectrum] Auto-Assignment Fehler: {e}")

        # Checkbox enable/disable
        self.chk_integrals.setEnabled(self.current_nucleus == "1H")
        has_assignment_support = (self.current_nucleus in ("1H", "13C")) and bool(self.current_assignment)
        self.chk_assignment.setEnabled(has_assignment_support)
        self.chk_calc_trace.setEnabled(has_assignment_support)

        self.btn_reset_zoom.setEnabled(True)
        self.btn_export_jcamp.setEnabled(True)

        self.update_header_info()
        self.render_canvas_view()

    def update_header_info(self):
        if not self.current_record:
            return
        
        formula = self.current_record.get("formula", "-")
        mw = self.current_record.get("mw", "-")
        solvent = self.current_record.get("solvent", "Unbekannt")
        nuc_color = self.current_record.get("nucleus_color", "#38bdf8")
        n_peaks = len(self.current_peaks)

        total_int = sum(p.integral for p in self.current_peaks) if self.current_nucleus == "1H" else 0
        int_str = f" • Gesamtintegral: <strong>{total_int:.0f}H</strong>" if self.current_nucleus == "1H" and total_int > 0 else ""

        self.title_label.setText(
            f"{formula} • {mw} g/mol • "
            f"<span style='color:{nuc_color}; font-weight:800;'>{self.current_nucleus}-NMR</span>"
        )
        self.info_label.setText(
            f"Lösungsmittel: <strong>{solvent}</strong> • "
            f"Frequenz: <strong>{self.current_freq:.1f} MHz</strong> • "
            f"Signale: <strong>{n_peaks} Peaks</strong>{int_str}"
        )

    def render_canvas_view(self):
        """Generates spectrum data and loads interactive HTML5 Canvas viewer."""
        if not self.current_peaks:
            self.show_placeholder()
            return

        # Calculate initial grid via NumPy
        self.current_grid = calculate_spectrum_grid(
            peaks=self.current_peaks,
            nucleus_key=self.current_nucleus,
            spec_freq_mhz=self.current_freq,
            fwhm_hz=self.current_fwhm,
            num_points=4096
        )

        # Expand all subpeaks for client-side instant slider re-synthesis
        all_subpeaks = []
        for p in self.current_peaks:
            lines = expand_multiplet_components(p, self.current_freq)
            for pos, amp in lines:
                all_subpeaks.append({"pos": float(pos), "amp": float(amp)})

        # Prepare JSON payload
        x_list = [round(float(v), 5) for v in self.current_grid["x"]]
        y_list = [round(float(v), 2) for v in self.current_grid["y"]]
        int_list = [round(float(v), 2) for v in self.current_grid["integral"]] if self.current_grid["integral"] is not None else None
        
        assign_map = {}
        if self.current_assignment and self.current_assignment.get("assigned_peaks"):
            for ap in self.current_assignment["assigned_peaks"]:
                assign_map[ap["exp_idx"]] = ap

        peak_details = []
        for idx, p in enumerate(self.current_peaks):
            ap = assign_map.get(idx)
            peak_details.append({
                "ppm": float(p.shift_ppm),
                "mult": str(p.multiplicity),
                "j": ", ".join(f"{j:.1f}" for j in p.j_couplings) if p.j_couplings else "-",
                "integral": float(p.integral),
                "range": p.shift_range,
                "assignment": ap["calc_label"] if ap else None,
                "calc_ppm": ap["calc_shift"] if ap else None,
                "delta_ppm": ap["delta_ppm"] if ap else None,
                "confidence": ap["confidence"] if ap else None,
                "atom_indices": ap.get("parent_heavy_indices") or ap.get("atom_indices") or [] if ap else []
            })

        calc_markers = []
        if self.current_assignment and self.current_assignment.get("groups"):
            for g in self.current_assignment["groups"]:
                calc_markers.append({
                    "ppm": float(g["calc_shift"]),
                    "label": g["atom_label"],
                    "count": g["count"]
                })

        assign_summary = None
        if self.current_assignment and self.current_assignment.get("assigned_peaks"):
            n_ass = len(self.current_assignment["assigned_peaks"])
            n_tot = len(self.current_peaks)
            mae_val = self.current_assignment.get("mae", 0.0)
            assign_summary = f"{n_ass}/{n_tot} zugeordnet (MAE: {mae_val:.2f} ppm)"

        ref_data = None
        if self.reference_record and self.reference_peaks and self.chk_mirror.isChecked():
            try:
                ref_nuc = detect_nucleus(self.reference_record)
                ref_freq = detect_frequency(self.reference_record, ref_nuc)
                ref_grid = calculate_spectrum_grid(
                    peaks=self.reference_peaks,
                    nucleus_key=ref_nuc,
                    spec_freq_mhz=ref_freq,
                    fwhm_hz=self.current_fwhm,
                    num_points=4096
                )
                ref_data = {
                    "name": self.reference_record.get("name") or self.reference_record.get("filename") or "Referenz",
                    "formula": self.reference_record.get("formula", ""),
                    "nucleus": ref_nuc,
                    "x": [round(float(v), 5) for v in ref_grid["x"]],
                    "y": [round(float(v), 2) for v in ref_grid["y"]]
                }
            except Exception as e:
                print(f"[viewer_spectrum] Fehler beim Berechnen des Referenzspektrums: {e}")

        spectrum_data = {
            "x": x_list,
            "y": y_list,
            "integral": int_list,
            "labels": self.current_grid["labels"],
            "peaks": peak_details,
            "subpeaks": all_subpeaks,
            "calcMarkers": calc_markers,
            "nucleus": self.current_nucleus,
            "specFreq": float(self.current_freq),
            "fwhmHz": float(self.current_fwhm),
            "showLabels": self.chk_labels.isChecked(),
            "showIntegrals": self.chk_integrals.isChecked() and self.current_nucleus == "1H",
            "showAssignment": self.chk_assignment.isChecked() and (self.current_nucleus in ("1H", "13C")),
            "showCalcTrace": self.chk_calc_trace.isChecked() and (self.current_nucleus in ("1H", "13C")),
            "showMirror": self.chk_mirror.isChecked() and (ref_data is not None),
            "refData": ref_data,
            "assignmentSummary": assign_summary
        }

        html_content = self.generate_canvas_html(spectrum_data)
        
        # Write to cache file and load via QUrl
        cache_file = os.path.join(get_cache_dir(), "spectrum_viewer.html")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            self.web_view.load(QUrl.fromLocalFile(cache_file))
        except Exception as e:
            print(f"[viewer_spectrum] Fehler beim Cachen: {e}")
            self.web_view.setHtml(html_content)

    def generate_canvas_html(self, data):
        data_json = json.dumps(data)
        
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; }}
        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background-color: #070b14;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            user-select: none;
            -webkit-user-select: none;
        }}
        #canvas-container {{
            position: relative;
            width: 100%;
            height: 100%;
        }}
        canvas {{
            display: block;
            width: 100%;
            height: 100%;
            cursor: crosshair;
        }}
        .hud-overlay {{
            position: absolute;
            top: 12px;
            right: 14px;
            display: flex;
            gap: 8px;
            pointer-events: none;
        }}
        .hud-chip {{
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #334155;
            backdrop-filter: blur(8px);
            padding: 5px 10px;
            border-radius: 6px;
            color: #38bdf8;
            font-size: 11px;
            font-weight: 600;
            font-family: 'Consolas', monospace;
        }}
        .tooltip {{
            position: absolute;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid #38bdf8;
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 12px;
            color: #f1f5f9;
            pointer-events: none;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            display: none;
            z-index: 100;
            line-height: 1.5;
        }}
        .tooltip strong {{
            color: #38bdf8;
        }}
        .tooltip .tag {{
            background: #1e293b;
            padding: 2px 6px;
            border-radius: 4px;
            color: #cbd5e1;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div id="canvas-container">
        <canvas id="specCanvas"></canvas>
        <div class="hud-overlay">
            <div id="hud-coords" class="hud-chip">δ: --- ppm | Int: ---</div>
            ${f'<div id="hud-assign" class="hud-chip" style="border-color:#10b981; color:#34d399;">🤖 {data["assignmentSummary"]}</div>' if data.get("assignmentSummary") else ''}
        </div>
        <div id="tooltip" class="tooltip"></div>
    </div>

    <script>
    (function() {{
        let specData = {data_json};

        const canvas = document.getElementById('specCanvas');
        const ctx = canvas.getContext('2d');
        const hudCoords = document.getElementById('hud-coords');
        const tooltip = document.getElementById('tooltip');

        let pointsX = specData.x;
        let pointsY = specData.y;
        let pointsInt = specData.integral;
        let labels = specData.labels || [];
        let subpeaks = specData.subpeaks || [];
        let rawPeaks = specData.peaks || [];
        let calcMarkers = specData.calcMarkers || [];

        let nucleus = specData.nucleus || '1H';
        let specFreq = specData.specFreq || 400.13;
        let currentFwhmHz = specData.fwhmHz || 1.2;
        let showLabels = specData.showLabels !== false;
        let showIntegrals = specData.showIntegrals !== false;
        let showAssignment = specData.showAssignment !== false;
        let showCalcTrace = specData.showCalcTrace === true;
        let showMirror = specData.showMirror === true;
        let refData = specData.refData || null;

        // Determine default range
        let defaultMaxX = pointsX[0];
        let defaultMinX = pointsX[pointsX.length - 1];
        let defaultMaxY = 1000.0;

        // Current View State (NMR descending: left is maxX, right is minX)
        let viewMaxX = defaultMaxX;
        let viewMinX = defaultMinX;
        let viewMaxY = defaultMaxY;

        // Layout Margins
        const MARGIN_LEFT = 50;
        const MARGIN_RIGHT = 30;
        const MARGIN_TOP = 40;
        const MARGIN_BOTTOM = 50;

        let width = 0;
        let height = 0;
        let plotWidth = 0;
        let plotHeight = 0;
        let baselineY = 0;

        let isDragging = false;
        let dragMode = 'pan'; // 'pan' or 'yscale'
        let dragStartX = 0;
        let dragStartY = 0;
        let dragStartMinX = 0;
        let dragStartMaxX = 0;
        let dragStartMaxY = 0;

        let mouseX = -1;
        let mouseY = -1;

        function resize() {{
            const dpr = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            width = rect.width;
            height = rect.height;

            canvas.width = width * dpr;
            canvas.height = height * dpr;
            ctx.scale(dpr, dpr);

            plotWidth = Math.max(10, width - MARGIN_LEFT - MARGIN_RIGHT);
            baselineY = height - MARGIN_BOTTOM;
            plotHeight = Math.max(10, baselineY - MARGIN_TOP);

            render();
        }}

        window.addEventListener('resize', resize);

        // Coordinate transforms
        function ppmToCanvasX(ppm) {{
            return MARGIN_LEFT + ((viewMaxX - ppm) / (viewMaxX - viewMinX)) * plotWidth;
        }}

        function canvasXToPpm(cx) {{
            return viewMaxX - ((cx - MARGIN_LEFT) / plotWidth) * (viewMaxX - viewMinX);
        }}

        function yToCanvasY(yVal) {{
            return baselineY - (yVal / viewMaxY) * plotHeight;
        }}

        function canvasYToVal(cy) {{
            return ((baselineY - cy) / plotHeight) * viewMaxY;
        }}

        // Dynamic tick calculation
        function calculateNiceTicks(minPpm, maxPpm) {{
            const span = maxPpm - minPpm;
            if (span <= 0) return {{ step: 1, minorStep: 0.2 }};

            const targetTicks = Math.max(4, Math.floor(plotWidth / 80));
            const rawStep = span / targetTicks;
            const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
            const residual = rawStep / magnitude;

            let step;
            if (residual < 1.5) step = 1.0 * magnitude;
            else if (residual < 3.5) step = 2.0 * magnitude;
            else if (residual < 7.5) step = 5.0 * magnitude;
            else step = 10.0 * magnitude;

            const minorStep = step / 5.0;
            return {{ step, minorStep }};
        }}

        function render() {{
            ctx.clearRect(0, 0, width, height);

            // 1. Background Grid & Axis
            ctx.fillStyle = '#070b14';
            ctx.fillRect(0, 0, width, height);

            const ticks = calculateNiceTicks(viewMinX, viewMaxX);
            const step = ticks.step;
            const minorStep = ticks.minorStep;

            const firstTick = Math.ceil(viewMinX / step) * step;
            const lastTick = Math.floor(viewMaxX / step) * step;

            // Minor ticks
            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            const firstMinor = Math.ceil(viewMinX / minorStep) * minorStep;
            ctx.beginPath();
            for (let t = firstMinor; t <= viewMaxX; t += minorStep) {{
                let cx = ppmToCanvasX(t);
                if (cx >= MARGIN_LEFT && cx <= MARGIN_LEFT + plotWidth) {{
                    ctx.moveTo(cx, baselineY);
                    ctx.lineTo(cx, baselineY + 4);
                }}
            }}
            ctx.stroke();

            // Major grid lines & ticks
            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            ctx.beginPath();
            for (let t = firstTick; t <= lastTick; t += step) {{
                let cx = ppmToCanvasX(t);
                if (cx >= MARGIN_LEFT && cx <= MARGIN_LEFT + plotWidth) {{
                    ctx.moveTo(cx, MARGIN_TOP);
                    ctx.lineTo(cx, baselineY);
                }}
            }}
            ctx.stroke();

            // Baseline
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(MARGIN_LEFT, baselineY);
            ctx.lineTo(MARGIN_LEFT + plotWidth, baselineY);
            ctx.stroke();

            // Tick labels
            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px Segoe UI, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';

            let decimals = 1;
            if (step < 0.1) decimals = 3;
            else if (step < 1.0) decimals = 2;
            else if (step >= 10.0) decimals = 0;

            for (let t = firstTick; t <= lastTick; t += step) {{
                let cx = ppmToCanvasX(t);
                if (cx >= MARGIN_LEFT - 5 && cx <= MARGIN_LEFT + plotWidth + 5) {{
                    // Major tick mark
                    ctx.strokeStyle = '#475569';
                    ctx.beginPath();
                    ctx.moveTo(cx, baselineY);
                    ctx.lineTo(cx, baselineY + 6);
                    ctx.stroke();

                    ctx.fillText(t.toFixed(decimals), cx, baselineY + 9);
                }}
            }}

            // Unit Label
            ctx.fillStyle = '#38bdf8';
            ctx.font = 'bold 11px Segoe UI, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText('ppm (δ)', MARGIN_LEFT + plotWidth, baselineY + 28);

            // Clip plot area for data drawing
            ctx.save();
            ctx.beginPath();
            ctx.rect(MARGIN_LEFT, MARGIN_TOP - 10, plotWidth, plotHeight + 10);
            ctx.clip();

            // 2. Translucent Area Fill beneath spectrum
            ctx.beginPath();
            let firstPoint = true;
            for (let i = 0; i < pointsX.length; i++) {{
                let px = pointsX[i];
                if (px > viewMaxX + (viewMaxX - viewMinX) * 0.1 || px < viewMinX - (viewMaxX - viewMinX) * 0.1) continue;
                let cx = ppmToCanvasX(px);
                let cy = yToCanvasY(pointsY[i]);
                if (firstPoint) {{
                    ctx.moveTo(cx, baselineY);
                    ctx.lineTo(cx, cy);
                    firstPoint = false;
                }} else {{
                    ctx.lineTo(cx, cy);
                }}
            }}
            ctx.lineTo(ppmToCanvasX(pointsX[pointsX.length - 1]), baselineY);
            ctx.closePath();

            let grad = ctx.createLinearGradient(0, MARGIN_TOP, 0, baselineY);
            grad.addColorStop(0, 'rgba(56, 189, 248, 0.15)');
            grad.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
            ctx.fillStyle = grad;
            ctx.fill();

            // 3. Main Spectrum Line (Neon Cyan)
            ctx.beginPath();
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 1.6;
            ctx.lineJoin = 'round';
            firstPoint = true;
            for (let i = 0; i < pointsX.length; i++) {{
                let px = pointsX[i];
                if (px > viewMaxX + (viewMaxX - viewMinX) * 0.1 || px < viewMinX - (viewMaxX - viewMinX) * 0.1) continue;
                let cx = ppmToCanvasX(px);
                let cy = yToCanvasY(pointsY[i]);
                if (firstPoint) {{
                    ctx.moveTo(cx, cy);
                    firstPoint = false;
                }} else {{
                    ctx.lineTo(cx, cy);
                }}
            }}
            ctx.stroke();

            // 4. Cumulative Integral Curve (for 1H NMR, Gold/Amber)
            if (showIntegrals && pointsInt && pointsInt.length === pointsX.length) {{
                let maxInt = pointsInt[0]; // descending: 0 index is left/high ppm
                if (maxInt > 0) {{
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(245, 158, 11, 0.85)';
                    ctx.lineWidth = 1.4;
                    ctx.setLineDash([4, 2]);

                    // Map integral to top 40% of plot
                    let intBaseY = baselineY - plotHeight * 0.35;
                    let intHeight = plotHeight * 0.55;

                    firstPoint = true;
                    for (let i = 0; i < pointsX.length; i++) {{
                        let px = pointsX[i];
                        if (px > viewMaxX + (viewMaxX - viewMinX) * 0.1 || px < viewMinX - (viewMaxX - viewMinX) * 0.1) continue;
                        let cx = ppmToCanvasX(px);
                        let normVal = pointsInt[i] / maxInt;
                        let cy = intBaseY - normVal * intHeight;
                        if (firstPoint) {{
                            ctx.moveTo(cx, cy);
                            firstPoint = false;
                        }} else {{
                            ctx.lineTo(cx, cy);
                        }}
                    }}
                    ctx.stroke();
                    ctx.setLineDash([]);
                }}
            }}

            // 4c. Inverted Mirror / Comparison Plot (Coral / Pink curve below baseline)
            if (showMirror && refData && refData.x && refData.y) {{
                let rx = refData.x;
                let ry = refData.y;
                let mirrorHeight = Math.min(plotHeight * 0.45, 120);

                // Find max y of reference for normalization
                let refMaxY = 1.0;
                for (let k = 0; k < ry.length; k++) {{
                    if (ry[k] > refMaxY) refMaxY = ry[k];
                }}

                ctx.beginPath();
                ctx.strokeStyle = '#f43f5e'; // Bright Rose/Coral
                ctx.lineWidth = 1.6;
                firstPoint = true;
                for (let i = 0; i < rx.length; i++) {{
                    let px = rx[i];
                    if (px > viewMaxX + (viewMaxX - viewMinX) * 0.1 || px < viewMinX - (viewMaxX - viewMinX) * 0.1) continue;
                    let cx = ppmToCanvasX(px);
                    let cy = baselineY + (ry[i] / refMaxY) * mirrorHeight;
                    if (firstPoint) {{
                        ctx.moveTo(cx, cy);
                        firstPoint = false;
                    }} else {{
                        ctx.lineTo(cx, cy);
                    }}
                }}
                ctx.stroke();

                // Fill area of mirror plot
                ctx.lineTo(ppmToCanvasX(rx[rx.length - 1]), baselineY);
                ctx.closePath();
                let mGrad = ctx.createLinearGradient(0, baselineY, 0, baselineY + mirrorHeight);
                mGrad.addColorStop(0, 'rgba(244, 63, 94, 0.12)');
                mGrad.addColorStop(1, 'rgba(244, 63, 94, 0.00)');
                ctx.fillStyle = mGrad;
                ctx.fill();

                // Reference Legend Tag
                ctx.font = 'bold 10px Segoe UI, sans-serif';
                ctx.fillStyle = '#f43f5e';
                ctx.textAlign = 'left';
                ctx.fillText(`🪞 ${{refData.name || 'Referenz'}} (${{refData.formula || ''}})`, MARGIN_LEFT + 8, baselineY + mirrorHeight - 6);
            }}

            // 4b. Theoretical Positions (est-NMR Calculation Markers)
            if (showCalcTrace && calcMarkers && calcMarkers.length > 0) {{
                for (let i = 0; i < calcMarkers.length; i++) {{
                    let cm = calcMarkers[i];
                    if (cm.ppm < viewMinX || cm.ppm > viewMaxX) continue;
                    let cx = ppmToCanvasX(cm.ppm);

                    // Dashed vertical marker line
                    ctx.strokeStyle = 'rgba(192, 132, 252, 0.65)';
                    ctx.lineWidth = 1.2;
                    ctx.setLineDash([3, 3]);
                    ctx.beginPath();
                    ctx.moveTo(cx, MARGIN_TOP);
                    ctx.lineTo(cx, baselineY);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Top tag for theoretical position
                    let tagTxt = `${{cm.label}} (${{cm.ppm.toFixed(1)}})`;
                    ctx.font = 'bold 9px Consolas, monospace';
                    let tagW = ctx.measureText(tagTxt).width;
                    ctx.fillStyle = 'rgba(88, 28, 135, 0.9)';
                    ctx.fillRect(cx - tagW / 2 - 3, MARGIN_TOP + 2, tagW + 6, 12);
                    ctx.fillStyle = '#f3e8ff';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(tagTxt, cx, MARGIN_TOP + 7);
                }}
            }}

            // 5. Peak Pick Labels
            if (showLabels && labels) {{
                for (let i = 0; i < labels.length; i++) {{
                    let lbl = labels[i];
                    if (lbl.ppm < viewMinX || lbl.ppm > viewMaxX) continue;

                    let cx = ppmToCanvasX(lbl.ppm);
                    let cy = yToCanvasY(lbl.height || 0);

                    // Drop line
                    ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([2, 3]);
                    ctx.beginPath();
                    ctx.moveTo(cx, cy);
                    ctx.lineTo(cx, baselineY);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    // Apex diamond
                    ctx.fillStyle = '#38bdf8';
                    ctx.beginPath();
                    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
                    ctx.fill();

                    // Text Badge
                    let txt = lbl.text || lbl.ppm.toFixed(2);
                    ctx.font = 'bold 10px Consolas, monospace';
                    let txtWidth = ctx.measureText(txt).width;

                    let badgeY = Math.max(MARGIN_TOP - 4, cy - 8);
                    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                    ctx.fillRect(cx - txtWidth / 2 - 3, badgeY - 10, txtWidth + 6, 12);
                    
                    ctx.fillStyle = '#f1f5f9';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(txt, cx, badgeY - 4);

                    // Assignment Badge above ppm badge
                    if (showAssignment && rawPeaks) {{
                        let matched = rawPeaks.find(p => Math.abs(p.ppm - lbl.ppm) < 0.05);
                        if (matched && matched.assignment) {{
                            let assignTxt = matched.assignment;
                            ctx.font = 'bold 10px Segoe UI, sans-serif';
                            let aWidth = ctx.measureText(assignTxt).width;
                            let aY = badgeY - 14;
                            let confBg = matched.confidence === 'high' ? '#064e3b' : (matched.confidence === 'medium' ? '#78350f' : '#7c2d12');
                            let confCol = matched.confidence === 'high' ? '#34d399' : (matched.confidence === 'medium' ? '#fcd34d' : '#fdba74');
                            ctx.fillStyle = confBg;
                            ctx.fillRect(cx - aWidth / 2 - 4, aY - 6, aWidth + 8, 13);
                            ctx.strokeStyle = confCol;
                            ctx.lineWidth = 1;
                            ctx.strokeRect(cx - aWidth / 2 - 4, aY - 6, aWidth + 8, 13);
                            
                            ctx.fillStyle = confCol;
                            ctx.fillText(assignTxt, cx, aY);
                        }}
                    }}
                }}
            }}

            ctx.restore(); // restore clipping

            // 6. Interactive Crosshair Cursor
            if (mouseX >= MARGIN_LEFT && mouseX <= MARGIN_LEFT + plotWidth && mouseY >= MARGIN_TOP && mouseY <= baselineY) {{
                ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                
                // Vertical crosshair
                ctx.beginPath();
                ctx.moveTo(mouseX, MARGIN_TOP);
                ctx.lineTo(mouseX, baselineY);
                ctx.stroke();

                // Horizontal crosshair
                ctx.beginPath();
                ctx.moveTo(MARGIN_LEFT, mouseY);
                ctx.lineTo(MARGIN_LEFT + plotWidth, mouseY);
                ctx.stroke();
                ctx.setLineDash([]);

                let curPpm = canvasXToPpm(mouseX);
                let curVal = canvasYToVal(mouseY);
                hudCoords.textContent = `δ: ${{curPpm.toFixed(3)}} ppm | Int: ${{curVal.toFixed(1)}}`;
            }} else {{
                hudCoords.textContent = `δ: --- ppm | Int: ---`;
            }}
        }}

        // Client-side real-time Lorentzian re-synthesis (< 1ms execution)
        function recalculateLorentzian() {{
            if (!subpeaks || subpeaks.length === 0) return;
            const fwhmPpm = Math.max(0.005, currentFwhmHz) / specFreq;
            const halfFwhm = fwhmPpm / 2.0;
            const halfFwhm2 = halfFwhm * halfFwhm;
            const n = pointsX.length;
            
            let maxY = 0;
            for (let i = 0; i < n; i++) {{
                const px = pointsX[i];
                let sum = 0;
                for (let j = 0; j < subpeaks.length; j++) {{
                    const dx = px - subpeaks[j].pos;
                    sum += subpeaks[j].amp * halfFwhm2 / (dx * dx + halfFwhm2);
                }}
                pointsY[i] = sum;
                if (sum > maxY) maxY = sum;
            }}

            if (maxY > 0) {{
                for (let i = 0; i < n; i++) {{
                    pointsY[i] = (pointsY[i] / maxY) * 1000.0;
                }}
            }}

            // Update label heights
            for (let i = 0; i < labels.length; i++) {{
                let target = labels[i].ppm;
                let ratio = (defaultMaxX - target) / (defaultMaxX - defaultMinX);
                let idx = Math.min(n - 1, Math.max(0, Math.round(ratio * (n - 1))));
                labels[i].height = pointsY[idx];
            }}
        }}

        // Mouse Events
        canvas.addEventListener('wheel', function(e) {{
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;

            if (e.shiftKey) {{
                // Shift+Wheel: Vertical intensity gain/scale
                const zoomY = e.deltaY > 0 ? 1.2 : 0.833;
                viewMaxY = Math.max(50.0, Math.min(50000.0, viewMaxY * zoomY));
            }} else {{
                // Wheel: Horizontal zoom centered at cursor PPM
                if (cx >= MARGIN_LEFT && cx <= MARGIN_LEFT + plotWidth) {{
                    const mousePpm = canvasXToPpm(cx);
                    const zoomFactor = e.deltaY > 0 ? 1.2 : 0.833;
                    const newMin = mousePpm - (mousePpm - viewMinX) * zoomFactor;
                    const newMax = mousePpm + (viewMaxX - mousePpm) * zoomFactor;

                    if (newMax - newMin > 0.05 && newMax - newMin < 500.0) {{
                        viewMinX = newMin;
                        viewMaxX = newMax;
                    }}
                }}
            }}
            render();
            checkPeakHover(cx, cy);
        }}, {{ passive: false }});

        canvas.addEventListener('mousedown', function(e) {{
            const rect = canvas.getBoundingClientRect();
            dragStartX = e.clientX - rect.left;
            dragStartY = e.clientY - rect.top;
            dragStartMinX = viewMinX;
            dragStartMaxX = viewMaxX;
            dragStartMaxY = viewMaxY;
            isDragging = true;
            dragMode = (e.button === 2) ? 'yscale' : 'pan';
            tooltip.style.display = 'none';
        }});

        window.addEventListener('mousemove', function(e) {{
            const rect = canvas.getBoundingClientRect();
            mouseX = e.clientX - rect.left;
            mouseY = e.clientY - rect.top;

            if (isDragging) {{
                const dx = mouseX - dragStartX;
                const dy = mouseY - dragStartY;

                if (dragMode === 'pan') {{
                    const deltaPpm = (dx / plotWidth) * (dragStartMaxX - dragStartMinX);
                    viewMinX = dragStartMinX + deltaPpm;
                    viewMaxX = dragStartMaxX + deltaPpm;
                }} else if (dragMode === 'yscale') {{
                    const scaleFactor = Math.exp(dy * 0.005);
                    viewMaxY = Math.max(50.0, Math.min(50000.0, dragStartMaxY * scaleFactor));
                }}
                render();
            }} else {{
                render();
                checkPeakHover(mouseX, mouseY);
            }}
        }});

        window.addEventListener('mouseup', function() {{
            isDragging = false;
        }});

        canvas.addEventListener('contextmenu', function(e) {{
            e.preventDefault(); // disable context menu for right-drag yscale
        }});

        canvas.addEventListener('dblclick', function() {{
            resetZoom();
        }});

        function resetZoom() {{
            viewMaxX = defaultMaxX;
            viewMinX = defaultMinX;
            viewMaxY = defaultMaxY;
            render();
        }}

        function checkPeakHover(cx, cy) {{
            if (!rawPeaks || rawPeaks.length === 0) return;
            let closest = null;
            let minDist = 18;

            for (let i = 0; i < rawPeaks.length; i++) {{
                let p = rawPeaks[i];
                let px = ppmToCanvasX(p.ppm);
                // find y
                let ratio = (defaultMaxX - p.ppm) / (defaultMaxX - defaultMinX);
                let idx = Math.min(pointsY.length - 1, Math.max(0, Math.round(ratio * (pointsY.length - 1))));
                let py = yToCanvasY(pointsY[idx] || 0);

                let dist = Math.hypot(cx - px, cy - py);
                if (dist < minDist) {{
                    minDist = dist;
                    closest = p;
                }}
            }}

            if (closest) {{
                let intTag = closest.integral ? ` • <span class="tag">${{closest.integral}}H</span>` : '';
                let jTag = (closest.j && closest.j !== '-') ? `<br>Kopplung: <strong>J = ${{closest.j}} Hz</strong>` : '';
                let multName = closest.mult || 's';
                let assignInfo = '';
                if (closest.assignment) {{
                    let confColor = closest.confidence === 'high' ? '#34d399' : (closest.confidence === 'medium' ? '#fcd34d' : '#fdba74');
                    let sign = closest.delta_ppm > 0 ? '+' : '';
                    assignInfo = `
                        <div style="margin-top:6px; padding-top:6px; border-top:1px solid #334155; font-size:11px;">
                            <span style="color:#94a3b8;">Zuordnung:</span> <strong style="color:${{confColor}};">${{closest.assignment}}</strong><br>
                            <span style="color:#94a3b8;">est-NMR:</span> <strong>${{closest.calc_ppm.toFixed(2)}} ppm</strong> (Δδ: ${{sign}}${{closest.delta_ppm.toFixed(2)}} ppm)
                        </div>
                    `;
                }}

                tooltip.innerHTML = `
                    <strong>δ ${{closest.ppm.toFixed(2)}} ppm</strong> (${{multName}})${{intTag}}
                    ${{jTag}}
                    ${{assignInfo}}
                `;
                tooltip.style.left = Math.min(width - 220, Math.max(10, cx + 15)) + 'px';
                tooltip.style.top = Math.max(10, cy - 45) + 'px';
                tooltip.style.display = 'block';

                if (closest.atom_indices && closest.atom_indices.length > 0) {{
                    console.log("HGTTD_HIGHLIGHT:" + JSON.stringify(closest.atom_indices));
                }}
            }} else {{
                tooltip.style.display = 'none';
                console.log("HGTTD_HIGHLIGHT:[]");
            }}
        }}

        // Public API for Python IPC
        window.setLinewidth = function(fwhmHz) {{
            currentFwhmHz = fwhmHz;
            recalculateLorentzian();
            render();
        }};

        window.setFrequency = function(freqMhz) {{
            specFreq = freqMhz;
            recalculateLorentzian();
            render();
        }};

        window.toggleLabels = function(visible) {{
            showLabels = visible;
            render();
        }};

        window.toggleIntegrals = function(visible) {{
            showIntegrals = visible;
            render();
        }};

        window.toggleAssignment = function(visible) {{
            showAssignment = visible;
            render();
        }};

        window.toggleCalcTrace = function(visible) {{
            showCalcTrace = visible;
            render();
        }};

        window.toggleMirror = function(visible) {{
            showMirror = visible;
            render();
        }};

        window.resetView = function() {{
            resetZoom();
        }};

        // Initial setup
        resize();
    }})();
    </script>
</body>
</html>
"""

    def on_web_load_finished(self, ok):
        self.is_page_loaded = ok

    @Slot(int)
    def on_slider_fwhm_changed(self, val):
        fwhm_hz = val / 10.0
        self.spin_fwhm.blockSignals(True)
        self.spin_fwhm.setValue(fwhm_hz)
        self.spin_fwhm.blockSignals(False)
        self.current_fwhm = fwhm_hz
        self.web_view.page().runJavaScript(f"if (window.setLinewidth) window.setLinewidth({fwhm_hz});")

    @Slot(float)
    def on_spin_fwhm_changed(self, fwhm_hz):
        slider_val = int(round(fwhm_hz * 10))
        self.slider_fwhm.blockSignals(True)
        self.slider_fwhm.setValue(slider_val)
        self.slider_fwhm.blockSignals(False)
        self.current_fwhm = fwhm_hz
        self.web_view.page().runJavaScript(f"if (window.setLinewidth) window.setLinewidth({fwhm_hz});")

    @Slot(str)
    def on_freq_combo_changed(self, text):
        match = re.search(r"[-+]?\d*\.\d+|\d+", text)
        if match:
            try:
                freq_val = float(match.group(0))
                if 10.0 <= freq_val <= 2000.0:
                    self.current_freq = freq_val
                    self.update_header_info()
                    self.web_view.page().runJavaScript(f"if (window.setFrequency) window.setFrequency({freq_val});")
            except ValueError:
                pass

    @Slot(bool)
    def on_toggle_labels(self, checked):
        js_val = "true" if checked else "false"
        self.web_view.page().runJavaScript(f"if (window.toggleLabels) window.toggleLabels({js_val});")

    @Slot(bool)
    def on_toggle_integrals(self, checked):
        js_val = "true" if checked else "false"
        self.web_view.page().runJavaScript(f"if (window.toggleIntegrals) window.toggleIntegrals({js_val});")

    @Slot(bool)
    def on_toggle_assignment(self, checked):
        js_val = "true" if checked else "false"
        self.web_view.page().runJavaScript(f"if (window.toggleAssignment) window.toggleAssignment({js_val});")

    @Slot(bool)
    def on_toggle_calc_trace(self, checked):
        js_val = "true" if checked else "false"
        self.web_view.page().runJavaScript(f"if (window.toggleCalcTrace) window.toggleCalcTrace({js_val});")

    @Slot(bool)
    def on_toggle_mirror(self, checked):
        js_val = "true" if checked else "false"
        self.web_view.page().runJavaScript(f"if (window.toggleMirror) window.toggleMirror({js_val});")

    @Slot()
    def pin_current_as_reference(self):
        """Pins the current record as mirror comparison reference."""
        if not self.current_record or not self.current_peaks:
            return
        self.reference_record = self.current_record
        self.reference_peaks = list(self.current_peaks)
        self.btn_set_ref.setVisible(False)
        self.btn_clear_ref.setVisible(True)
        self.chk_mirror.setEnabled(True)
        self.chk_mirror.setChecked(True)
        self.render_canvas_view()

    @Slot()
    def clear_reference(self):
        """Clears mirror comparison reference."""
        self.reference_record = None
        self.reference_peaks = []
        self.reference_grid = None
        self.btn_set_ref.setVisible(True)
        self.btn_clear_ref.setVisible(False)
        self.chk_mirror.setEnabled(False)
        self.render_canvas_view()

    @Slot()
    def reset_zoom(self):
        self.web_view.page().runJavaScript("if (window.resetView) window.resetView();")

    @Slot()
    def export_jcamp(self):
        """Exports currently synthesized spectrum to IUPAC JCAMP-DX 5.01 file."""
        if not self.current_record or not self.current_peaks:
            QMessageBox.warning(self, "Export", "Keine Spektrendaten zum Exportieren vorhanden.")
            return

        # Recalculate grid with current FWHM & Frequency
        spectrum_grid = calculate_spectrum_grid(
            peaks=self.current_peaks,
            nucleus_key=self.current_nucleus,
            spec_freq_mhz=self.current_freq,
            fwhm_hz=self.current_fwhm,
            num_points=4096
        )

        metadata = {
            "title": f"{self.current_record.get('name', 'Compound')} {self.current_nucleus} NMR",
            "formula": self.current_record.get("formula", ""),
            "solvent": self.current_record.get("solvent", "Unknown"),
            "doi_url": self.current_record.get("doi_url", ""),
            "spec_freq": self.current_freq
        }

        jcamp_content = export_jcamp_dx(spectrum_grid, metadata)

        # File Dialog
        formula_clean = re.sub(r"[^\w\-]", "", self.current_record.get("formula", "spectrum"))
        default_filename = f"{formula_clean}_{self.current_nucleus}_{int(round(self.current_freq))}MHz.jdx"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            t("jcamp_export_title"),
            default_filename,
            "JCAMP-DX Spectrum (*.jdx *.dx);;Alle Dateien (*.*)"
        )

        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(jcamp_content)
                QMessageBox.information(
                    self, 
                    "Erfolg", 
                    t("jcamp_export_success", path=filepath)
                )
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "Fehler", 
                    t("jcamp_export_error", err=str(e))
                )

    @Slot()
    def export_report(self):
        """Exports laboratory report and analysis certificate as printable PDF or HTML."""
        from report_generator import export_report_dialog
        export_report_dialog(self, self.current_record)


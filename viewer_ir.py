"""
viewer_ir.py — High-Performance 60-FPS HTML5 Canvas Infrared (IR) Spectrum Viewer
HGTTD — Hitchhiker's Guide through the Database 🌌🪐
"""

import json
import re
import math
import urllib.request
import numpy as np
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox, QInputDialog
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from ir_manager import IR_CHARACTERISTIC_BANDS

class NistIRFetchWorker(QThread):
    finished = Signal(dict, str)  # data_dict, error_msg

    def __init__(self, smiles="", cas=""):
        super().__init__()
        self.smiles = smiles
        self.cas = cas

    def run(self):
        try:
            inchi = ""
            if self.smiles:
                try:
                    from rdkit import Chem
                    mol = Chem.MolFromSmiles(self.smiles)
                    if mol:
                        inchi = Chem.MolToInchi(mol)
                except Exception:
                    pass

            nid = ""
            if inchi:
                url_resolve = f"https://webbook.nist.gov/cgi/cbook.cgi?InChI={inchi}"
                req = urllib.request.Request(url_resolve, headers={"User-Agent": "Mozilla/5.0"})
                html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
                m = re.search(r'ID=(C\d+)&amp;Mask=80', html)
                if not m:
                    m = re.search(r'ID=(C\d+)', html)
                if m:
                    nid = m.group(1)

            if not nid and self.cas:
                clean_cas = self.cas.replace("-", "").strip()
                nid = f"C{clean_cas}"

            if not nid:
                self.finished.emit({}, "Verbindung konnte im NIST Chemistry WebBook nicht identifiziert werden.")
                return

            # Check IR mask
            url_ir = f"https://webbook.nist.gov/cgi/cbook.cgi?ID={nid}&Mask=80"
            req_ir = urllib.request.Request(url_ir, headers={"User-Agent": "Mozilla/5.0"})
            html_ir = urllib.request.urlopen(req_ir, timeout=10).read().decode("utf-8", errors="ignore")

            indices = re.findall(r'Index=(\d+)#IR-SPEC', html_ir)
            if not indices:
                self.finished.emit({}, f"NIST-Eintrag ({nid}) gefunden, enthält jedoch keine Infrarotspektren.")
                return

            # Find best index: gas phase (e.g. index '0' or '1' or '2')
            target_idx = "0" if "0" in indices else indices[0]

            jcamp_url = f"https://webbook.nist.gov/cgi/cbook.cgi?JCAMP={nid}&Index={target_idx}&Type=IR"
            req_jcamp = urllib.request.Request(jcamp_url, headers={"User-Agent": "Mozilla/5.0"})
            jcamp_text = urllib.request.urlopen(req_jcamp, timeout=10).read().decode("utf-8", errors="ignore")

            # Parse JCAMP
            lines = jcamp_text.splitlines()
            title = "NIST Referenzspektrum"
            xunits, yunits = "1/CM", "ABSORBANCE"
            xfactor, yfactor = 1.0, 1.0
            firstx, lastx = None, None
            state = ""

            for l in lines:
                if l.startswith("##TITLE="): title = l.split("=", 1)[1].strip()
                elif l.startswith("##STATE="): state = l.split("=", 1)[1].strip()
                elif l.startswith("##XUNITS="): xunits = l.split("=", 1)[1].strip().upper()
                elif l.startswith("##YUNITS="): yunits = l.split("=", 1)[1].strip().upper()
                elif l.startswith("##FIRSTX="): firstx = float(l.split("=", 1)[1].strip())
                elif l.startswith("##LASTX="): lastx = float(l.split("=", 1)[1].strip())
                elif l.startswith("##XFACTOR="): xfactor = float(l.split("=", 1)[1].strip())
                elif l.startswith("##YFACTOR="): yfactor = float(l.split("=", 1)[1].strip())

            xy_idx = -1
            for i, l in enumerate(lines):
                if l.startswith("##XYDATA="):
                    xy_idx = i
                    break

            if xy_idx == -1:
                self.finished.emit({}, "Kein gültiges JCAMP-XYDATA im NIST-Spektrum gefunden.")
                return

            all_y = []
            for l in lines[xy_idx+1:]:
                if l.startswith("##END="):
                    break
                parts = l.strip().split()
                if not parts:
                    continue
                for p in parts[1:]:
                    try:
                        all_y.append(float(p) * yfactor)
                    except ValueError:
                        pass

            if not all_y or firstx is None or lastx is None:
                self.finished.emit({}, "Konnte Datenpunkte des NIST-Spektrums nicht dekodieren.")
                return

            dx = (lastx - firstx) / (len(all_y) - 1)
            all_x = [firstx + i * dx for i in range(len(all_y))]

            if "MICROMETER" in xunits or "UM" in xunits:
                all_x = [10000.0 / x if x > 0 else 0.0 for x in all_x]

            if "TRANSMITTANCE" in yunits:
                max_y = max(all_y) if all_y else 1.0
                scale = 100.0 if max_y <= 1.05 else 1.0
                y_trans = [y * scale for y in all_y]
                y_abs = [-np.log10(max(1e-4, yt / 100.0)) for yt in y_trans]
            else:
                y_abs = all_y
                y_trans = [100.0 * (10.0 ** (-min(5.0, y))) for y in all_y]

            # Downsample to at most 1200 points for smooth Canvas 60 FPS rendering
            if len(all_x) > 1200:
                stride = len(all_x) // 1000
                all_x = all_x[::stride]
                y_trans = y_trans[::stride]
                y_abs = y_abs[::stride]

            res = {
                "nid": nid,
                "title": title,
                "state": state,
                "wavenumbers": [round(x, 2) for x in all_x],
                "transmittance": [round(y, 3) for y in y_trans],
                "absorbance": [round(y, 4) for y in y_abs],
                "raw_jcamp": jcamp_text
            }
            self.finished.emit(res, "")
        except Exception as e:
            self.finished.emit({}, f"Netzwerk- oder Abfragefehler beim NIST WebBook: {e}")


class ModernIRViewer(QWidget):
    """
    Interactive 60 FPS HTML5-Canvas IR Spectrum Viewer:
    - Standard IR Wavenumber Axis: 4000 cm^-1 down to 400 cm^-1
    - Toggle between Transmittance % (0-100%, dips down) and Absorbance (peaks up)
    - Characteristic Functional Group Absorption Bands (C=O, O-H, C-H, Fingerprint, etc.)
    - Real-time Zoom & Pan
    - JCAMP-DX 5.01 Export (##DATA TYPE= INFRARED SPECTRUM)
    """

    exportRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wavenumbers = []
        self.intensities = []
        self.compound_name = "IR Spectrum"
        self.source_label = "IR"
        self.current_mode = "transmittance"  # or "absorbance"

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Control Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # Mode Selector
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("📉 Transmittanz (%T)", "transmittance")
        self.mode_combo.addItem("📈 Extinktion (Absorbance)", "absorbance")
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background: #1e293b; color: #f8fafc; border: 1px solid #334155;
                padding: 4px 10px; border-radius: 6px; font-weight: 500;
            }
        """)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_combo)

        # Linewidth FWHM Slider
        fwhm_label = QLabel("Linienbreite:")
        fwhm_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        toolbar.addWidget(fwhm_label)

        self.fwhm_slider = QSlider(Qt.Horizontal)
        self.fwhm_slider.setRange(4, 30)  # 4 to 30 cm^-1
        self.fwhm_slider.setValue(16)
        self.fwhm_slider.setFixedWidth(100)
        self.fwhm_slider.valueChanged.connect(self._on_fwhm_changed)
        toolbar.addWidget(self.fwhm_slider)

        self.fwhm_val_lbl = QLabel("16 cm⁻¹")
        self.fwhm_val_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; width: 45px;")
        toolbar.addWidget(self.fwhm_val_lbl)

        # Characteristic Bands Checkbox
        self.cb_bands = QCheckBox("🏷️ Funktionelle Gruppen")
        self.cb_bands.setChecked(True)
        self.cb_bands.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        self.cb_bands.toggled.connect(self._on_toggle_bands)
        toolbar.addWidget(self.cb_bands)

        toolbar.addStretch()

        # NIST WebBook Button
        self.btn_nist = QPushButton("🌐 NIST IR laden")
        self.btn_nist.setToolTip("Experimentelles Referenzspektrum direkt vom NIST Chemistry WebBook abrufen & einblenden")
        self.btn_nist.setStyleSheet("""
            QPushButton {
                background: #1e1b4b; color: #a5b4fc; border: 1px solid #6366f1;
                border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #312e81; color: #c7d2fe; }
        """)
        self.btn_nist.clicked.connect(self._fetch_nist_spectrum)
        toolbar.addWidget(self.btn_nist)

        # Clear NIST Overlay Button (Hidden until loaded)
        self.btn_clear_nist = QPushButton("✕ NIST")
        self.btn_clear_nist.setVisible(False)
        self.btn_clear_nist.setToolTip("NIST-Referenzkurve ausblenden")
        self.btn_clear_nist.setStyleSheet("""
            QPushButton {
                background: #3f1d2e; color: #f472b6; border: 1px solid #db2777;
                border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #500724; }
        """)
        self.btn_clear_nist.clicked.connect(self._clear_nist_spectrum)
        toolbar.addWidget(self.btn_clear_nist)

        # Reset Zoom Button
        btn_reset = QPushButton("🔍 Reset Zoom")
        btn_reset.setStyleSheet("""
            QPushButton {
                background: #0f172a; color: #38bdf8; border: 1px solid #38bdf8;
                border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #1e293b; color: #7dd3fc; }
        """)
        btn_reset.clicked.connect(self._reset_zoom)
        toolbar.addWidget(btn_reset)

        # Export JCAMP Button
        btn_export = QPushButton("💾 JCAMP-DX")
        btn_export.setStyleSheet("""
            QPushButton {
                background: #047857; color: #ecfdf5; border: 1px solid #059669;
                border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #059669; }
        """)
        btn_export.clicked.connect(self._export_jcamp)
        toolbar.addWidget(btn_export)

        layout.addLayout(toolbar)

        # WebEngine Canvas
        self.webview = QWebEngineView()
        self.webview.setStyleSheet("background: #020617; border-radius: 8px;")
        layout.addWidget(self.webview)

        self._render_html()

    def set_spectrum_data(self, wavenumbers, intensities, compound_name="Compound", source="IR", smiles="", cas=""):
        self.wavenumbers = [float(x) for x in wavenumbers]
        self.intensities = [float(x) for x in intensities]
        self.compound_name = compound_name
        self.source_label = source
        self.current_smiles = smiles
        self.current_cas = cas
        self.nist_data = None
        self.btn_clear_nist.setVisible(False)
        self._update_canvas_data()

    def clear(self):
        self.wavenumbers = []
        self.intensities = []
        self._update_canvas_data()

    def _on_mode_changed(self):
        self.current_mode = self.mode_combo.currentData()
        self._run_js(f"setMode('{self.current_mode}');")

    def _on_fwhm_changed(self, val):
        self.fwhm_val_lbl.setText(f"{val} cm⁻¹")
        self._run_js(f"setFWHM({val});")

    def _on_toggle_bands(self, checked):
        val = "true" if checked else "false"
        self._run_js(f"toggleBands({val});")

    def _reset_zoom(self):
        self._run_js("resetZoom();")

    def _fetch_nist_spectrum(self):
        smiles = getattr(self, "current_smiles", "")
        cas = getattr(self, "current_cas", "")
        if not smiles and not cas:
            text, ok = QInputDialog.getText(
                self, "NIST WebBook Suche",
                "SMILES oder CAS-Nummer eingeben (z. B. 'CCO' oder '64-17-5'):"
            )
            if not ok or not text.strip():
                return
            query = text.strip()
            if "-" in query:
                cas = query
            else:
                smiles = query

        self.btn_nist.setEnabled(False)
        self.btn_nist.setText("⏳ Lädt NIST...")

        self.nist_worker = NistIRFetchWorker(smiles=smiles, cas=cas)
        self.nist_worker.finished.connect(self._on_nist_fetched)
        self.nist_worker.start()

    def _on_nist_fetched(self, data, error):
        self.btn_nist.setEnabled(True)
        self.btn_nist.setText("🌐 NIST IR laden")
        if error or not data:
            QMessageBox.warning(self, "NIST Chemistry WebBook", error or "Keine Daten gefunden.")
            return

        self.nist_data = data
        self.btn_clear_nist.setVisible(True)
        self._update_canvas_data()

    def _clear_nist_spectrum(self):
        self.nist_data = None
        self.btn_clear_nist.setVisible(False)
        self._update_canvas_data()

    def _export_jcamp(self):
        if not self.wavenumbers:
            QMessageBox.warning(self, "Export", "Keine IR-Spektrendaten zum Exportieren vorhanden.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "IR-Spektrum als JCAMP-DX exportieren",
            f"{self.compound_name.replace(' ', '_')}_FTIR.jdx",
            "JCAMP-DX (*.jdx *.dx);;Alle Dateien (*.*)"
        )
        if not file_path:
            return

        try:
            content = self._generate_jcamp_dx()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Export erfolgreich", f"JCAMP-DX Datei gespeichert:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Fehler", f"Fehler beim Speichern:\n{e}")

    def _generate_jcamp_dx(self):
        lines = [
            "##TITLE=" + self.compound_name,
            "##JCAMP-DX=5.01",
            "##DATA TYPE=INFRARED SPECTRUM",
            "##ORIGIN=HGTTD Spectroscopy Suite",
            f"##OWNER={self.source_label}",
            "##XUNITS=1/CM",
            "##YUNITS=TRANSMITTANCE",
            "##PEAK TABLE=(XY..XY)"
        ]
        pairs = sorted(zip(self.wavenumbers, self.intensities), key=lambda x: x[0], reverse=True)
        for wn, inten in pairs:
            lines.append(f"{wn:.2f}, {inten:.4f}")
        lines.append("##END=")
        return "\n".join(lines)

    def _run_js(self, script):
        self.webview.page().runJavaScript(script)

    def _update_canvas_data(self):
        payload = {
            "wavenumbers": self.wavenumbers,
            "intensities": self.intensities,
            "title": f"{self.compound_name} ({self.source_label})",
            "mode": self.current_mode,
            "fwhm": self.fwhm_slider.value(),
            "bands": IR_CHARACTERISTIC_BANDS,
            "nist": self.nist_data
        }
        json_str = json.dumps(payload)
        self._run_js(f"loadSpectrumData({json_str});")

    def _render_html(self):
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            background-color: #020617; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none;
        }
        #irCanvas {
            width: 100%; height: 100%; display: block; cursor: crosshair;
        }
        #tooltip {
            position: absolute; display: none; background: rgba(15, 23, 42, 0.95);
            border: 1px solid #38bdf8; border-radius: 6px; color: #f8fafc;
            padding: 6px 10px; font-size: 11px; pointer-events: none;
            box-shadow: 0 4px 14px rgba(0,0,0,0.5); z-index: 10;
        }
    </style>
</head>
<body>
    <div id="tooltip"></div>
    <canvas id="irCanvas"></canvas>
    <script>
        const canvas = document.getElementById('irCanvas');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('tooltip');

        let data = {
            wavenumbers: [],
            intensities: [],
            title: "Kein IR-Spektrum geladen",
            mode: "transmittance",
            fwhm: 16,
            bands: []
        };

        // Viewing window in cm^-1
        let minX = 400.0;
        let maxX = 4000.0;
        let defaultMinX = 400.0;
        let defaultMaxX = 4000.0;
        let showBands = true;

        let isDragging = false;
        let startX = 0;

        function resize() {
            canvas.width = window.innerWidth * window.devicePixelRatio;
            canvas.height = window.innerHeight * window.devicePixelRatio;
            draw();
        }
        window.addEventListener('resize', resize);

        function resetZoom() {
            minX = defaultMinX;
            maxX = defaultMaxX;
            draw();
        }

        function setMode(mode) {
            data.mode = mode;
            draw();
        }

        function setFWHM(fwhm) {
            data.fwhm = fwhm;
            draw();
        }

        function toggleBands(val) {
            showBands = val;
            draw();
        }

        function loadSpectrumData(newData) {
            data = newData;
            resetZoom();
        }

        // Coordinate transforms
        function xToPixel(wn) {
            // IR convention: 4000 on left (padding), 400 on right
            const padL = 60 * window.devicePixelRatio;
            const padR = 25 * window.devicePixelRatio;
            const width = canvas.width - padL - padR;
            const fraction = (maxX - wn) / (maxX - minX);
            return padL + fraction * width;
        }

        function pixelToX(px) {
            const padL = 60 * window.devicePixelRatio;
            const padR = 25 * window.devicePixelRatio;
            const width = canvas.width - padL - padR;
            const fraction = (px - padL) / width;
            return maxX - fraction * (maxX - minX);
        }

        function yToPixel(val, mode) {
            const padT = 40 * window.devicePixelRatio;
            const padB = 45 * window.devicePixelRatio;
            const height = canvas.height - padT - padB;
            if (mode === "transmittance") {
                // 100% on top (padT), 0% on bottom
                return padT + (1.0 - val / 100.0) * height;
            } else {
                // Absorbance: 0 on bottom, 1.0 (or max) on top
                return canvas.height - padB - (val * height);
            }
        }

        // Lorentzian synthesis
        function evalSpectrum(wn) {
            if (!data.wavenumbers || data.wavenumbers.length === 0) {
                return data.mode === "transmittance" ? 100.0 : 0.0;
            }
            let maxI = 1.0;
            for (let i = 0; i < data.intensities.length; i++) {
                if (data.intensities[i] > maxI) maxI = data.intensities[i];
            }

            const gamma = data.fwhm / 2.0;
            const gamma2 = gamma * gamma;
            let sumAbs = 0.0;

            for (let i = 0; i < data.wavenumbers.length; i++) {
                const diff = wn - data.wavenumbers[i];
                const normI = data.intensities[i] / maxI;
                sumAbs += normI * (gamma2 / (diff * diff + gamma2));
            }

            if (data.mode === "transmittance") {
                return 100.0 * Math.exp(-sumAbs * 1.6);
            } else {
                return sumAbs;
            }
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const dpr = window.devicePixelRatio;
            const padL = 60 * dpr;
            const padR = 25 * dpr;
            const padT = 40 * dpr;
            const padB = 45 * dpr;
            const w = canvas.width - padL - padR;
            const h = canvas.height - padT - padB;

            // Background & Grid
            ctx.fillStyle = "#020617";
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw Functional Group Bands
            if (showBands && data.bands) {
                data.bands.forEach(b => {
                    const xStart = xToPixel(Math.min(maxX, Math.max(minX, b.max_wn)));
                    const xEnd = xToPixel(Math.min(maxX, Math.max(minX, b.min_wn)));
                    if (xEnd > xStart) {
                        ctx.fillStyle = b.color;
                        ctx.fillRect(xStart, padT, xEnd - xStart, h);

                        ctx.fillStyle = "rgba(226, 232, 240, 0.4)";
                        ctx.font = `${10 * dpr}px sans-serif`;
                        ctx.fillText(b.label, xStart + 4, padT + 14 * dpr);
                    }
                });
            }

            // Draw Grid Lines (Wavenumbers every 500 cm^-1)
            ctx.strokeStyle = "#1e293b";
            ctx.lineWidth = 1 * dpr;
            ctx.fillStyle = "#64748b";
            ctx.font = `${11 * dpr}px monospace`;

            for (let wn = 500; wn <= 4000; wn += 500) {
                if (wn >= minX && wn <= maxX) {
                    const x = xToPixel(wn);
                    ctx.beginPath();
                    ctx.moveTo(x, padT);
                    ctx.lineTo(x, canvas.height - padB);
                    ctx.stroke();
                    ctx.fillText(`${wn}`, x - 14 * dpr, canvas.height - padB + 16 * dpr);
                }
            }

            // Title
            ctx.fillStyle = "#f8fafc";
            ctx.font = `bold ${13 * dpr}px sans-serif`;
            ctx.fillText(data.title, padL + 10, padT - 15 * dpr);

            // Y-Axis Labels
            ctx.fillStyle = "#94a3b8";
            ctx.font = `${10 * dpr}px sans-serif`;
            if (data.mode === "transmittance") {
                [0, 25, 50, 75, 100].forEach(val => {
                    const y = yToPixel(val, "transmittance");
                    ctx.fillText(`${val}%`, 10 * dpr, y + 4 * dpr);
                });
            } else {
                ctx.fillText("Abs", 15 * dpr, padT);
            }

            // Draw Continuous IR Spectrum Curve
            if (data.wavenumbers && data.wavenumbers.length > 0) {
                ctx.strokeStyle = "#ef4444"; // Crimson/Rose red for IR
                ctx.lineWidth = 2 * dpr;
                ctx.beginPath();

                const steps = Math.min(canvas.width, 1400);
                for (let i = 0; i <= steps; i++) {
                    const px = padL + (i / steps) * w;
                    const wn = pixelToX(px);
                    const val = evalSpectrum(wn);
                    const py = yToPixel(val, data.mode);

                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }
                ctx.stroke();

                // Peak markers / annotations
                ctx.fillStyle = "#38bdf8";
                data.wavenumbers.forEach((wn, idx) => {
                    if (wn >= minX && wn <= maxX) {
                        const px = xToPixel(wn);
                        const val = evalSpectrum(wn);
                        const py = yToPixel(val, data.mode);

                        ctx.beginPath();
                        ctx.arc(px, py, 3 * dpr, 0, Math.PI * 2);
                        ctx.fill();

                        // Label intense peaks
                        if (data.intensities[idx] > 20) {
                            ctx.font = `${10 * dpr}px sans-serif`;
                            ctx.fillText(`${wn.toFixed(0)}`, px - 10 * dpr, py + (data.mode === "transmittance" ? 14 * dpr : -8 * dpr));
                        }
                    }
                });
            } else {
                ctx.fillStyle = "#475569";
                ctx.font = `${14 * dpr}px sans-serif`;
                ctx.fillText("Keine Infrarotspektren-Daten für diese Verbindung vorhanden.", canvas.width / 2 - 180 * dpr, canvas.height / 2);
            }

            // Draw NIST Experimental Overlay Curve (if loaded)
            if (data.nist && data.nist.wavenumbers && data.nist.wavenumbers.length > 0) {
                const nistWn = data.nist.wavenumbers;
                const nistVals = data.mode === "transmittance" ? data.nist.transmittance : data.nist.absorbance;

                ctx.strokeStyle = "#38bdf8"; // Cyan for NIST experimental
                ctx.lineWidth = 1.8 * dpr;
                ctx.beginPath();

                let first = true;
                for (let i = 0; i < nistWn.length; i++) {
                    const wn = nistWn[i];
                    if (wn >= minX && wn <= maxX) {
                        const px = xToPixel(wn);
                        const py = yToPixel(nistVals[i], data.mode);
                        if (first) {
                            ctx.moveTo(px, py);
                            first = false;
                        } else {
                            ctx.lineTo(px, py);
                        }
                    }
                }
                ctx.stroke();

                // NIST Overlay Legend
                const legX = canvas.width - 240 * dpr;
                const legY = padT - 15 * dpr;
                ctx.fillStyle = "#38bdf8";
                ctx.fillRect(legX, legY - 6 * dpr, 16 * dpr, 3 * dpr);
                ctx.font = `bold ${10 * dpr}px sans-serif`;
                ctx.fillText(`NIST WebBook (${data.nist.state || 'Exp.'})`, legX + 22 * dpr, legY);

                // Theory Legend
                ctx.fillStyle = "#ef4444";
                ctx.fillRect(legX - 110 * dpr, legY - 6 * dpr, 16 * dpr, 3 * dpr);
                ctx.font = `bold ${10 * dpr}px sans-serif`;
                ctx.fillText("SQuIRL (DFT)", legX - 88 * dpr, legY);
            }
        }

        // Mouse Controls: Zoom & Pan
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const mouseX = e.clientX * window.devicePixelRatio;
            const focusWN = pixelToX(mouseX);
            const zoomFactor = e.deltaY > 0 ? 1.15 : 0.85;

            const span = (maxX - minX) * zoomFactor;
            if (span > 80 && span < 4500) {
                const ratio = (maxX - focusWN) / (maxX - minX);
                maxX = focusWN + ratio * span;
                minX = maxX - span;
                draw();
            }
        });

        canvas.addEventListener('mousedown', (e) => {
            if (e.button === 0) {
                isDragging = true;
                startX = e.clientX;
            }
        });

        window.addEventListener('mouseup', () => { isDragging = false; });

        canvas.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const dx = e.clientX - startX;
                startX = e.clientX;
                const dwn = (dx / (canvas.width / window.devicePixelRatio)) * (maxX - minX);
                minX += dwn;
                maxX += dwn;
                draw();
            } else {
                // Tooltip
                const mouseX = e.clientX * window.devicePixelRatio;
                const wn = pixelToX(mouseX);
                if (wn >= minX && wn <= maxX && data.wavenumbers.length > 0) {
                    const val = evalSpectrum(wn);
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 14) + 'px';
                    tooltip.style.top = (e.clientY + 14) + 'px';
                    tooltip.innerHTML = `<strong>${wn.toFixed(1)} cm⁻¹</strong><br>${data.mode === 'transmittance' ? 'Transmittanz: ' + val.toFixed(1) + '%' : 'Extinktion: ' + val.toFixed(3)}`;
                } else {
                    tooltip.style.display = 'none';
                }
            }
        });

        canvas.addEventListener('mouseleave', () => {
            tooltip.style.display = 'none';
        });

        // Initialize
        resize();
    </script>
</body>
</html>
"""
        self.webview.setHtml(html_content)

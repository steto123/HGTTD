"""
viewer_ir.py — High-Performance 60-FPS HTML5 Canvas Infrared (IR) Spectrum Viewer
HGTTD — Hitchhiker's Guide through the Database 🌌🪐
"""

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from ir_manager import IR_CHARACTERISTIC_BANDS

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

    def set_spectrum_data(self, wavenumbers, intensities, compound_name="Compound", source="IR"):
        self.wavenumbers = [float(x) for x in wavenumbers]
        self.intensities = [float(x) for x in intensities]
        self.compound_name = compound_name
        self.source_label = source
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
            "bands": IR_CHARACTERISTIC_BANDS
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

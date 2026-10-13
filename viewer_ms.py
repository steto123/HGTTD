"""
viewer_ms.py
============
Interactive high-performance Mass Spectrometry (MS) Stick-Spectrum Viewer Widget for HGTTD.
Renders centroided stick spectra for MoNa records (LC-MS/MS & GC-MS EI),
provides smooth 60 FPS Canvas zoom/pan, dynamic peak labeling,
neutral-loss measurement tool, and NIST MSP / IUPAC JCAMP-DX export.
"""

from __future__ import annotations

import os
import sys
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QSlider, QDoubleSpinBox, QComboBox, QCheckBox, QFileDialog, 
    QMessageBox, QFrame, QSizePolicy, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QApplication
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from i18n import t

# Common Neutral Losses Library (Da -> Formula / Description)
COMMON_NEUTRAL_LOSSES = [
    (15.0235, "-CH₃ (Methyl)"),
    (17.0265, "-NH₃ (Ammoniak)"),
    (18.0106, "-H₂O (Wasser)"),
    (27.9949, "-CO (Kohlenmonoxid)"),
    (28.0313, "-C₂H₄ (Ethen)"),
    (31.0184, "-OCH₃ (Methoxy)"),
    (32.0262, "-CH₃OH (Methanol)"),
    (35.9767, "-HCl (Chlorwasserstoff)"),
    (42.0106, "-CH₂CO (Keten)"),
    (43.0184, "-C₂H₃O (Acetyl)"),
    (43.0548, "-C₃H₇ (Propyl)"),
    (43.9898, "-CO₂ (Kohlendioxid)"),
    (45.0215, "-COOH (Carboxyl)"),
    (46.0055, "-NO₂ (Nitro)"),
    (56.0626, "-C₄H₈ (Isobuten)"),
    (60.0211, "-CH₃COOH (Essigsäure)"),
    (79.9568, "-SO₃ (Sulfat)"),
    (79.9663, "-HPO₃ (Phosphat)"),
    (97.9769, "-H₃PO₄ (Phosphorsäure)"),
]


class MSViewerWidget(QWidget):
    """Modern Interactive Mass Spectrum Stick Viewer Widget."""

    switch_to_details_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_record: Optional[Dict[str, Any]] = None
        self.peaks: List[Tuple[float, float]] = []  # [(m/z, rel_intensity)]
        self.raw_peaks: List[Tuple[float, float]] = []

        self.setStyleSheet("""
            QWidget {
                background-color: #0b1120;
                color: #f1f5f9;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
                color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton#ExportBtn {
                background-color: #0369a1;
                border-color: #0284c7;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#ExportBtn:hover {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QCheckBox {
                color: #e2e8f0;
                font-size: 12px;
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
        """)

        self.setup_ui()
        self.show_placeholder()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Bar: Info Title & Actions
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

        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        self.title_label = QLabel(t("ms_spectrum_title"))
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        self.info_label = QLabel(t("spectrum_no_data"))
        self.info_label.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        info_box.addWidget(self.title_label)
        info_box.addWidget(self.info_label)
        top_layout.addLayout(info_box)

        top_layout.addStretch()

        # Action Buttons
        self.btn_details = QPushButton(t("btn_back_details"))
        self.btn_details.clicked.connect(self.switch_to_details_requested.emit)
        top_layout.addWidget(self.btn_details)

        self.btn_reset_zoom = QPushButton(t("spectrum_reset_zoom"))
        self.btn_reset_zoom.clicked.connect(self.reset_zoom)
        top_layout.addWidget(self.btn_reset_zoom)

        self.btn_peak_table = QPushButton(t("btn_ms_peak_table"))
        self.btn_peak_table.setToolTip(t("btn_ms_peak_table_tip"))
        self.btn_peak_table.clicked.connect(self.show_peak_table_dialog)
        top_layout.addWidget(self.btn_peak_table)

        self.btn_export_csv = QPushButton(f"💾 {t('btn_ms_export_csv')}", objectName="ExportBtn")
        self.btn_export_csv.setToolTip(t("btn_ms_export_csv_tip"))
        self.btn_export_csv.clicked.connect(self.export_csv)
        top_layout.addWidget(self.btn_export_csv)

        self.btn_export_msp = QPushButton("💾 NIST MSP", objectName="ExportBtn")
        self.btn_export_msp.setToolTip("Spektrum im NIST MSP-Format exportieren")
        self.btn_export_msp.clicked.connect(self.export_msp)
        top_layout.addWidget(self.btn_export_msp)

        self.btn_export_jcamp = QPushButton("💾 JCAMP-DX", objectName="ExportBtn")
        self.btn_export_jcamp.setToolTip("Spektrum als IUPAC JCAMP-DX 5.01 Massenspektrum exportieren")
        self.btn_export_jcamp.clicked.connect(self.export_jcamp)
        top_layout.addWidget(self.btn_export_jcamp)

        layout.addWidget(top_bar)

        # Control Toolbar
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
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        ctrl_layout.setSpacing(16)

        # Cutoff Slider
        cutoff_box = QHBoxLayout()
        cutoff_box.setSpacing(6)
        self.cutoff_lbl = QLabel(t("ms_cutoff_label"))
        self.cutoff_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        cutoff_box.addWidget(self.cutoff_lbl)

        self.slider_cutoff = QSlider(Qt.Orientation.Horizontal)
        self.slider_cutoff.setRange(0, 25)  # 0% to 25%
        self.slider_cutoff.setValue(1)      # 1% default
        self.slider_cutoff.setFixedWidth(100)
        self.slider_cutoff.valueChanged.connect(self.on_cutoff_changed)
        cutoff_box.addWidget(self.slider_cutoff)

        self.lbl_cutoff_val = QLabel("1 %")
        self.lbl_cutoff_val.setStyleSheet("color: #38bdf8; font-size: 12px; min-width: 32px;")
        cutoff_box.addWidget(self.lbl_cutoff_val)
        ctrl_layout.addLayout(cutoff_box)

        # Peak Labels Toggle
        self.chk_labels = QCheckBox(t("spectrum_toggle_labels"))
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self.toggle_labels)
        ctrl_layout.addWidget(self.chk_labels)

        # Neutral Loss Tool
        self.chk_neutral_loss = QCheckBox(t("ms_neutral_loss_tool"))
        self.chk_neutral_loss.setChecked(True)
        self.chk_neutral_loss.setToolTip("Klicken Sie nacheinander auf zwei Peaks, um die Massendifferenz Δm/z zu ermitteln.")
        self.chk_neutral_loss.toggled.connect(self.toggle_neutral_loss)
        ctrl_layout.addWidget(self.chk_neutral_loss)

        # Status Chip for Neutral Loss
        self.nl_chip = QLabel("")
        self.nl_chip.setStyleSheet("background-color: #3b0764; color: #f472b6; border: 1px solid #a855f7; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;")
        self.nl_chip.setVisible(False)
        ctrl_layout.addWidget(self.nl_chip)

        ctrl_layout.addStretch()
        layout.addWidget(ctrl_bar)

        # WebEngine Canvas
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #0b1120; border: 1px solid #1e293b; border-radius: 8px;")
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        layout.addWidget(self.web_view, stretch=1)

    def load_record(self, record: Dict[str, Any]):
        """Loads and visualizes a MoNa spectrum record."""
        self.current_record = record
        self.raw_peaks = record.get("peak_list", [])
        self.peaks = record.get("normalized_peaks", [])

        # Update Info Title
        name = record.get("name") or "Unbenannt"
        self.title_label.setText(f"⚡ {name}")

        pmz = record.get("precursor_mz", 0.0)
        adduct = record.get("adduct", "")
        mode = record.get("ion_mode", "")
        inst = record.get("instrument_type") or record.get("instrument") or ""
        ce = record.get("collision_energy", "")
        peaks_cnt = len(self.peaks)

        parts = []
        if pmz > 0.0:
            parts.append(f"Precursor: m/z {pmz:.4f} ({adduct})")
        if mode:
            parts.append(f"Modus: {mode}")
        if inst:
            parts.append(f"Gerät: {inst}")
        if ce:
            parts.append(f"CE: {ce}")
        parts.append(f"{peaks_cnt} Peaks")

        self.info_label.setText(" | ".join(parts))
        self.nl_chip.setVisible(False)

        self.render_spectrum_canvas()

    def show_placeholder(self):
        """Displays friendly empty state placeholder."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background-color: #0b1120;
                    color: #64748b;
                    font-family: 'Segoe UI', system-ui, sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    text-align: center;
                }
                .icon { font-size: 54px; margin-bottom: 16px; opacity: 0.6; }
                .title { font-size: 18px; font-weight: 600; color: #94a3b8; margin-bottom: 8px; }
                .subtitle { font-size: 13px; max-width: 420px; line-height: 1.5; color: #475569; }
            </style>
        </head>
        <body>
            <div class="icon">⚡</div>
            <div class="title">Kein Massenspektrum ausgewählt</div>
            <div class="subtitle">Wählen Sie einen Datensatz aus MoNa oder starten Sie eine Precursor m/z / Substruktursuche, um das Stick-Spektrum anzuzeigen.</div>
        </body>
        </html>
        """
        self.web_view.setHtml(html)

    def retranslate_ui(self):
        """Aktualisiert alle UI-Texte bei Sprachwechsel."""
        self.btn_details.setText(t("btn_back_details"))
        self.btn_reset_zoom.setText(t("spectrum_reset_zoom"))
        self.btn_peak_table.setText(t("btn_ms_peak_table"))
        self.btn_peak_table.setToolTip(t("btn_ms_peak_table_tip"))
        self.btn_export_csv.setText(f"💾 {t('btn_ms_export_csv')}")
        self.btn_export_csv.setToolTip(t("btn_ms_export_csv_tip"))
        self.cutoff_lbl.setText(t("ms_cutoff_label"))
        self.chk_labels.setText(t("spectrum_toggle_labels"))
        self.chk_neutral_loss.setText(t("ms_neutral_loss_tool"))
        if not self.current_record:
            self.title_label.setText(t("ms_spectrum_title"))
            self.info_label.setText(t("spectrum_no_data"))
            self.show_placeholder()
        else:
            self.load_record(self.current_record)

    def render_spectrum_canvas(self):
        """Renders interactive HTML5 Canvas with stick spectrum."""
        if not self.peaks:
            self.show_placeholder()
            return

        min_mz = max(0.0, min((p[0] for p in self.peaks), default=0.0) - 10.0)
        max_mz = max((p[0] for p in self.peaks), default=500.0) + 15.0
        precursor_mz = self.current_record.get("precursor_mz", 0.0) if self.current_record else 0.0

        peaks_json = json.dumps(self.peaks)
        losses_json = json.dumps(COMMON_NEUTRAL_LOSSES)

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    * {{ box-sizing: border-box; user-select: none; margin: 0; padding: 0; }}
    body {{
        background: #0b1120;
        color: #f1f5f9;
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        overflow: hidden;
        height: 100vh;
        width: 100vw;
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
    #tooltip {{
        position: absolute;
        display: none;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid #38bdf8;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
        color: #f8fafc;
        pointer-events: none;
        box-shadow: 0 4px 16px rgba(0,0,0,0.5);
        backdrop-filter: blur(4px);
        z-index: 10;
        white-space: nowrap;
    }}
    #nl-banner {{
        position: absolute;
        top: 10px;
        right: 14px;
        background: rgba(88, 28, 135, 0.85);
        border: 1px solid #ec4899;
        color: #fbcfe8;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        display: none;
        backdrop-filter: blur(4px);
    }}
</style>
</head>
<body>
<div id="canvas-container">
    <canvas id="msCanvas"></canvas>
    <div id="tooltip"></div>
    <div id="nl-banner"></div>
</div>

<script>
    const canvas = document.getElementById('msCanvas');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('tooltip');
    const nlBanner = document.getElementById('nl-banner');

    const rawPeaks = {peaks_json};
    const commonLosses = {losses_json};
    const precursorMZ = {precursor_mz};

    let showLabels = true;
    let cutoffPercent = 1.0;
    let neutralLossEnabled = true;

    // View boundaries
    let origMinX = {min_mz};
    let origMaxX = {max_mz};
    let minX = origMinX;
    let maxX = origMaxX;
    let maxY = 105.0; // 0 to 105%

    // Interaction state
    let isDragging = false;
    let dragStartX = 0;
    let dragStartMinX = 0;
    let dragStartMaxX = 0;
    let hoverPeak = null;
    let selectedPeaks = []; // For neutral loss measurement

    function resize() {{
        const dpr = window.devicePixelRatio || 1;
        canvas.width = canvas.parentElement.clientWidth * dpr;
        canvas.height = canvas.parentElement.clientHeight * dpr;
        ctx.scale(dpr, dpr);
        draw();
    }}

    window.addEventListener('resize', resize);

    function toScreenX(mz, w, padL, padR) {{
        return padL + ((mz - minX) / (maxX - minX)) * (w - padL - padR);
    }}

    function toScreenY(intensity, h, padT, padB) {{
        return padT + (1.0 - (intensity / maxY)) * (h - padT - padB);
    }}

    function fromScreenX(px, w, padL, padR) {{
        return minX + ((px - padL) / (w - padL - padR)) * (maxX - minX);
    }}

    function draw() {{
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.width / dpr;
        const h = canvas.height / dpr;

        ctx.clearRect(0, 0, w, h);

        const padL = 60;
        const padR = 30;
        const padT = 35;
        const padB = 40;

        // Draw Axes & Grids
        ctx.strokeStyle = '#1e293b';
        ctx.lineWidth = 1;

        // Y-axis grid (0%, 25%, 50%, 75%, 100%)
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';

        [0, 25, 50, 75, 100].forEach(val => {{
            const y = toScreenY(val, h, padT, padB);
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(w - padR, y);
            ctx.stroke();
            ctx.fillText(val + ' %', padL - 8, y);
        }});

        // X-axis baseline
        const baseY = toScreenY(0, h, padT, padB);
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(padL, baseY);
        ctx.lineTo(w - padR, baseY);
        ctx.stroke();

        // X-axis ticks (m/z)
        const range = maxX - minX;
        let step = 10;
        if (range > 600) step = 100;
        else if (range > 300) step = 50;
        else if (range > 150) step = 20;
        else if (range > 50) step = 10;
        else if (range > 20) step = 5;
        else step = 1;

        const startTick = Math.ceil(minX / step) * step;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        for (let t = startTick; t <= maxX; t += step) {{
            const x = toScreenX(t, w, padL, padR);
            if (x >= padL && x <= w - padR) {{
                ctx.strokeStyle = '#1e293b';
                ctx.beginPath();
                ctx.moveTo(x, padT);
                ctx.lineTo(x, baseY);
                ctx.stroke();

                ctx.strokeStyle = '#475569';
                ctx.beginPath();
                ctx.moveTo(x, baseY);
                ctx.lineTo(x, baseY + 4);
                ctx.stroke();

                ctx.fillStyle = '#94a3b8';
                ctx.fillText(t.toFixed(0), x, baseY + 8);
            }}
        }}

        // Axis Titles
        ctx.fillStyle = '#cbd5e1';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText('m/z (Masse / Ladung)', (w + padL - padR) / 2, h - 16);

        ctx.save();
        ctx.translate(16, (h + padT - padB) / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Relative Intensität (%)', 0, 0);
        ctx.restore();

        // Draw Sticks
        const filteredPeaks = rawPeaks.filter(p => p[1] >= cutoffPercent && p[0] >= minX && p[0] <= maxX);

        filteredPeaks.forEach(peak => {{
            const mz = peak[0];
            const intens = peak[1];

            const x = toScreenX(mz, w, padL, padR);
            const y = toScreenY(intens, h, padT, padB);

            const isHover = (hoverPeak && Math.abs(hoverPeak[0] - mz) < 0.0001);
            const isSelected = selectedPeaks.some(sp => Math.abs(sp[0] - mz) < 0.0001);
            const isPrecursor = (precursorMZ > 0 && Math.abs(precursorMZ - mz) < 0.05);
            const isBasePeak = (intens >= 99.9);

            // Stick color & width
            if (isSelected) {{
                ctx.strokeStyle = '#ec4899'; // Selected pink
                ctx.lineWidth = 3.5;
            }} else if (isHover) {{
                ctx.strokeStyle = '#ffffff'; // White glow
                ctx.lineWidth = 3;
            }} else if (isBasePeak) {{
                ctx.strokeStyle = '#f59e0b'; // Amber base peak
                ctx.lineWidth = 2.5;
            }} else if (isPrecursor) {{
                ctx.strokeStyle = '#10b981'; // Emerald precursor
                ctx.lineWidth = 2.5;
            }} else {{
                ctx.strokeStyle = '#38bdf8'; // Standard cyan
                ctx.lineWidth = 1.8;
            }}

            ctx.beginPath();
            ctx.moveTo(x, baseY);
            ctx.lineTo(x, y);
            ctx.stroke();

            // Head circle
            ctx.fillStyle = ctx.strokeStyle;
            ctx.beginPath();
            ctx.arc(x, y, isHover || isSelected ? 3.5 : 2, 0, Math.PI * 2);
            ctx.fill();

            // Peak Label
            if (showLabels && (intens >= 5.0 || isPrecursor || isHover || isSelected)) {{
                ctx.fillStyle = isSelected ? '#f472b6' : (isPrecursor ? '#34d399' : (isBasePeak ? '#fbbf24' : '#e2e8f0'));
                ctx.font = isHover || isSelected ? 'bold 11px sans-serif' : '10px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText(mz.toFixed(2), x, y - 3);
            }}
        }});

        // Draw Neutral Loss Connection Line if 2 peaks are selected
        if (selectedPeaks.length === 2) {{
            const p1 = selectedPeaks[0];
            const p2 = selectedPeaks[1];
            const x1 = toScreenX(p1[0], w, padL, padR);
            const y1 = toScreenY(p1[1], h, padT, padB);
            const x2 = toScreenX(p2[0], w, padL, padR);
            const y2 = toScreenY(p2[1], h, padT, padB);

            const topY = Math.min(y1, y2) - 15;

            ctx.strokeStyle = '#ec4899';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 4]);

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x1, topY);
            ctx.lineTo(x2, topY);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.setLineDash([]);

            const deltaMZ = Math.abs(p1[0] - p2[0]);
            let matchText = '';
            for (let loss of commonLosses) {{
                if (Math.abs(deltaMZ - loss[0]) < 0.15) {{
                    matchText = ' (' + loss[1] + ')';
                    break;
                }}
            }}

            ctx.fillStyle = '#fbcfe8';
            ctx.font = 'bold 11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Δm/z ' + deltaMZ.toFixed(3) + matchText, (x1 + x2) / 2, topY - 4);
        }}
    }}

    // Mouse Interactions
    canvas.addEventListener('wheel', e => {{
        e.preventDefault();
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.width / dpr;
        const padL = 60, padR = 30;

        const mouseX = e.offsetX;
        const centerMZ = fromScreenX(mouseX, w, padL, padR);

        const zoomFactor = e.deltaY < 0 ? 0.8 : 1.25;
        const currentSpan = maxX - minX;
        const newSpan = Math.max(5.0, currentSpan * zoomFactor);

        const ratio = (centerMZ - minX) / currentSpan;
        minX = centerMZ - ratio * newSpan;
        maxX = minX + newSpan;

        draw();
    }});

    canvas.addEventListener('mousedown', e => {{
        if (e.button === 0) {{
            isDragging = true;
            dragStartX = e.offsetX;
            dragStartMinX = minX;
            dragStartMaxX = maxX;
        }}
    }});

    window.addEventListener('mouseup', () => {{
        isDragging = false;
    }});

    canvas.addEventListener('mousemove', e => {{
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.width / dpr;
        const h = canvas.height / dpr;
        const padL = 60, padR = 30, padT = 35, padB = 40;

        if (isDragging) {{
            const dx = e.offsetX - dragStartX;
            const mzDelta = (dx / (w - padL - padR)) * (dragStartMaxX - dragStartMinX);
            minX = dragStartMinX - mzDelta;
            maxX = dragStartMaxX - mzDelta;
            draw();
            return;
        }}

        // Hover Peak Detection
        const mouseMZ = fromScreenX(e.offsetX, w, padL, padR);
        const hitRadius = (maxX - minX) * 0.015; // 1.5% of range

        let closest = null;
        let minDist = Infinity;

        rawPeaks.forEach(p => {{
            if (p[1] >= cutoffPercent) {{
                const d = Math.abs(p[0] - mouseMZ);
                if (d < hitRadius && d < minDist) {{
                    minDist = d;
                    closest = p;
                }}
            }}
        }});

        if (closest !== hoverPeak) {{
            hoverPeak = closest;
            draw();
        }}

        if (hoverPeak) {{
            tooltip.style.display = 'block';
            tooltip.style.left = (e.clientX + 14) + 'px';
            tooltip.style.top = (e.clientY - 28) + 'px';
            tooltip.innerHTML = '<strong>m/z:</strong> ' + hoverPeak[0].toFixed(4) + '<br><strong>Intensität:</strong> ' + hoverPeak[1].toFixed(1) + ' %';
        }} else {{
            tooltip.style.display = 'none';
        }}
    }});

    canvas.addEventListener('click', e => {{
        if (hoverPeak && neutralLossEnabled) {{
            if (selectedPeaks.length >= 2) {{
                selectedPeaks = [hoverPeak];
            }} else if (selectedPeaks.length === 1) {{
                if (Math.abs(selectedPeaks[0][0] - hoverPeak[0]) > 0.001) {{
                    selectedPeaks.push(hoverPeak);
                }} else {{
                    selectedPeaks = []; // Deselect
                }}
            }} else {{
                selectedPeaks.push(hoverPeak);
            }}

            updateNeutralLossBanner();
            draw();
        }}
    }});

    canvas.addEventListener('dblclick', () => {{
        minX = origMinX;
        maxX = origMaxX;
        selectedPeaks = [];
        updateNeutralLossBanner();
        draw();
    }});

    function updateNeutralLossBanner() {{
        if (selectedPeaks.length === 2) {{
            const deltaMZ = Math.abs(selectedPeaks[0][0] - selectedPeaks[1][0]);
            let match = '';
            for (let loss of commonLosses) {{
                if (Math.abs(deltaMZ - loss[0]) < 0.15) {{
                    match = ' ➔ ' + loss[1];
                    break;
                }}
            }}
            nlBanner.style.display = 'block';
            nlBanner.innerText = 'Neutral-Loss: Δm/z ' + deltaMZ.toFixed(3) + match;
        }} else {{
            nlBanner.style.display = 'none';
        }}
    }}

    // API calls from Qt
    window.setCutoff = function(val) {{
        cutoffPercent = val;
        draw();
    }};

    window.toggleLabels = function(show) {{
        showLabels = show;
        draw();
    }};

    window.toggleNeutralLoss = function(enabled) {{
        neutralLossEnabled = enabled;
        if (!enabled) {{
            selectedPeaks = [];
            updateNeutralLossBanner();
        }}
        draw();
    }};

    window.resetZoom = function() {{
        minX = origMinX;
        maxX = origMaxX;
        selectedPeaks = [];
        updateNeutralLossBanner();
        draw();
    }};

    setTimeout(resize, 50);
</script>
</body>
</html>
        """
        self.web_view.setHtml(html)

    def on_cutoff_changed(self, val: int):
        self.lbl_cutoff_val.setText(f"{val} %")
        self.web_view.page().runJavaScript(f"window.setCutoff({val});")

    def toggle_labels(self, checked: bool):
        self.web_view.page().runJavaScript(f"window.toggleLabels({json.dumps(checked)});")

    def toggle_neutral_loss(self, checked: bool):
        self.web_view.page().runJavaScript(f"window.toggleNeutralLoss({json.dumps(checked)});")

    def reset_zoom(self):
        self.web_view.page().runJavaScript("window.resetZoom();")

    def export_msp(self):
        """Exports the active spectrum as a NIST MSP file."""
        if not self.current_record or not self.raw_peaks:
            QMessageBox.warning(self, "Export", "Keine Spektrendaten zum Exportieren vorhanden.")
            return

        name = self.current_record.get("name", "spectrum")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:30]
        fname, _ = QFileDialog.getSaveFileName(
            self, "NIST MSP Export", f"{safe_name}.msp", "NIST MSP Files (*.msp)"
        )
        if not fname:
            return

        lines = [
            f"NAME: {name}",
            f"DB#: {self.current_record.get('id', '')}",
            f"INCHIKEY: {self.current_record.get('inchikey', '')}",
            f"SMILES: {self.current_record.get('smiles', '')}",
            f"FORMULA: {self.current_record.get('formula', '')}",
            f"EXACTMASS: {self.current_record.get('exact_mass', 0.0)}",
            f"PRECURSORMZ: {self.current_record.get('precursor_mz', 0.0)}",
            f"PRECURSORTYPE: {self.current_record.get('adduct', '')}",
            f"IONMODE: {self.current_record.get('ion_mode', '')}",
            f"INSTRUMENTTYPE: {self.current_record.get('instrument_type', '')}",
            f"INSTRUMENT: {self.current_record.get('instrument', '')}",
            f"COLLISIONENERGY: {self.current_record.get('collision_energy', '')}",
            f"Num Peaks: {len(self.raw_peaks)}"
        ]
        for mz, intens in self.raw_peaks:
            lines.append(f"{mz:.4f} {intens:.1f}")

        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n\n")
            QMessageBox.information(self, "Export erfolgreich", f"Spektrum erfolgreich als NIST MSP exportiert:\n{fname}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern: {e}")

    def export_jcamp(self):
        """Exports the active spectrum as an IUPAC JCAMP-DX 5.01 Mass Spectrum."""
        if not self.current_record or not self.raw_peaks:
            QMessageBox.warning(self, "Export", "Keine Spektrendaten zum Exportieren vorhanden.")
            return

        name = self.current_record.get("name", "spectrum")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:30]
        fname, _ = QFileDialog.getSaveFileName(
            self, "JCAMP-DX Export", f"{safe_name}.jdx", "JCAMP-DX Files (*.jdx *.dx)"
        )
        if not fname:
            return

        lines = [
            "##TITLE= " + name,
            "##JCAMP-DX= 5.01",
            "##DATA TYPE= MASS SPECTRUM",
            "##ORIGIN= MoNa - MassBank of North America / HGTTD",
            "##OWNER= UC Davis Oliver Fiehn Lab",
            "##CAS REGISTRY NO= " + self.current_record.get("id", ""),
            "##MOLFORM= " + self.current_record.get("formula", ""),
            "##MW= " + str(self.current_record.get("exact_mass", 0.0)),
            "##XUNITS= M/Z",
            "##YUNITS= RELATIVE ABUNDANCE",
            "##NPOINTS= " + str(len(self.raw_peaks)),
            "##PEAK TABLE= (XY..XY)"
        ]
        for mz, intens in self.raw_peaks:
            lines.append(f"{mz:.4f}, {intens:.1f}")
        lines.append("##END=")

        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            QMessageBox.information(self, "Export erfolgreich", f"Spektrum erfolgreich als JCAMP-DX exportiert:\n{fname}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern: {e}")

    def export_csv(self):
        """Exports the active spectrum peak list as a CSV file."""
        if not self.current_record or not self.raw_peaks:
            QMessageBox.warning(self, "Export", "Keine Spektrendaten zum Exportieren vorhanden.")
            return

        name = self.current_record.get("name", "spectrum")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:30]
        fname, _ = QFileDialog.getSaveFileName(
            self, "CSV Peaklisten-Export", f"{safe_name}_peaks.csv", "CSV Files (*.csv)"
        )
        if not fname:
            return

        # Prepare normalized map
        norm_map = {}
        for p in self.peaks:
            norm_map[round(p[0], 4)] = p[1]

        lines = ["# " + f"Name: {name}", f"# Precursor: {self.current_record.get('precursor_mz', '')}", "mz,relative_intensity_percent,raw_intensity"]
        for mz, intens in self.raw_peaks:
            rel_i = norm_map.get(round(mz, 4), 0.0)
            lines.append(f"{mz:.4f},{rel_i:.2f},{intens:.2f}")

        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            QMessageBox.information(self, "Export erfolgreich", f"Peakliste erfolgreich als CSV exportiert:\n{fname}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern: {e}")

    def show_peak_table_dialog(self):
        """Opens a modal, searchable dialog with the full peak list."""
        if not self.current_record or not self.raw_peaks:
            QMessageBox.warning(self, "Peakliste", "Keine Spektrendaten zum Anzeigen vorhanden.")
            return

        dlg = MSPeakTableDialog(self.current_record, self.raw_peaks, self.peaks, parent=self)
        dlg.exec()


class MSPeakTableDialog(QDialog):
    """
    Searchable, sortable modal dialog displaying complete peak list for mass spectra.
    Allows filtering by m/z and quick CSV export or clipboard copy.
    """
    def __init__(self, record: Dict[str, Any], raw_peaks: List[Tuple[float, float]], norm_peaks: List[Tuple[float, float]], parent=None):
        super().__init__(parent)
        self.record = record
        self.raw_peaks = raw_peaks
        self.norm_peaks = norm_peaks
        
        # Build combined list sorted by m/z ascending
        norm_map = {round(p[0], 4): p[1] for p in self.norm_peaks}
        self.all_peaks = []
        for mz, intens in self.raw_peaks:
            rel = norm_map.get(round(mz, 4), 0.0)
            self.all_peaks.append((mz, rel, intens))
        self.all_peaks.sort(key=lambda x: x[0])

        self.setWindowTitle(t("ms_peak_dialog_title") + f" – {record.get('name', 'MS')}")
        self.resize(650, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                color: #f1f5f9;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
                color: #38bdf8;
            }
            QPushButton#ActionBtn {
                background-color: #0369a1;
                border-color: #0284c7;
                color: #ffffff;
            }
            QPushButton#ActionBtn:hover {
                background-color: #0284c7;
            }
            QTableWidget {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                padding: 6px 8px;
                border: none;
                border-right: 1px solid #334155;
                border-bottom: 2px solid #38bdf8;
                font-weight: 600;
                font-size: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Info
        header_layout = QHBoxLayout()
        title_lbl = QLabel(f"⚡ <strong>{record.get('name', 'MS')}</strong> ({len(self.all_peaks)} Peaks)")
        title_lbl.setStyleSheet("font-size: 15px; color: #38bdf8;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        self.btn_copy_clipboard = QPushButton("📋 In Zwischenablage")
        self.btn_copy_clipboard.setToolTip("Gefilterte Peakliste in Zwischenablage kopieren (Tab-getrennt)")
        self.btn_copy_clipboard.clicked.connect(self.copy_to_clipboard)
        header_layout.addWidget(self.btn_copy_clipboard)

        self.btn_export = QPushButton("💾 CSV Export", objectName="ActionBtn")
        self.btn_export.clicked.connect(self.export_csv)
        header_layout.addWidget(self.btn_export)

        layout.addLayout(header_layout)

        # Search / Filter Bar
        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(t("ms_search_peak_placeholder"))
        self.search_input.textChanged.connect(self.filter_peaks)
        filter_layout.addWidget(self.search_input)

        self.lbl_count = QLabel(t("ms_peak_count_info", count=len(self.all_peaks)))
        self.lbl_count.setStyleSheet("color: #94a3b8; font-size: 12px;")
        filter_layout.addWidget(self.lbl_count)

        layout.addLayout(filter_layout)

        # Peak Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            t("ms_col_rank"),
            t("ms_col_mz"),
            t("ms_col_rel_int"),
            t("ms_col_abs_int")
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)

        layout.addWidget(self.table)

        self.populate_table(self.all_peaks)

    def populate_table(self, peaks: List[Tuple[float, float, float]]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(peaks))
        for row, (mz, rel_i, abs_i) in enumerate(peaks):
            item_rank = QTableWidgetItem()
            item_rank.setData(Qt.ItemDataRole.DisplayRole, row + 1)
            item_rank.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_mz = QTableWidgetItem()
            item_mz.setData(Qt.ItemDataRole.DisplayRole, round(mz, 4))
            item_mz.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_mz.setForeground(Qt.GlobalColor.cyan)

            item_rel = QTableWidgetItem()
            item_rel.setData(Qt.ItemDataRole.DisplayRole, round(rel_i, 2))
            item_rel.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            item_abs = QTableWidgetItem()
            item_abs.setData(Qt.ItemDataRole.DisplayRole, round(abs_i, 2))
            item_abs.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(row, 0, item_rank)
            self.table.setItem(row, 1, item_mz)
            self.table.setItem(row, 2, item_rel)
            self.table.setItem(row, 3, item_abs)

        self.table.setSortingEnabled(True)
        self.lbl_count.setText(t("ms_peak_count_info", count=len(peaks)))

    def filter_peaks(self, text: str):
        text = text.strip()
        if not text:
            self.populate_table(self.all_peaks)
            return

        try:
            # Check if query is numeric for range / prefix matching
            val = float(text.replace(",", "."))
            # match peaks within +/- 1.0 Da or whose string representation starts with text
            filtered = [
                p for p in self.all_peaks 
                if abs(p[0] - val) <= 1.0 or f"{p[0]:.4f}".startswith(text)
            ]
        except ValueError:
            filtered = [
                p for p in self.all_peaks 
                if text.lower() in f"{p[0]:.4f}".lower()
            ]

        self.populate_table(filtered)

    def copy_to_clipboard(self):
        rows = []
        rows.append("m/z\tRel. Intensität (%)\tAbs. Intensität")
        for r in range(self.table.rowCount()):
            mz = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            rel = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            abs_i = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            rows.append(f"{mz}\t{rel}\t{abs_i}")

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(rows))
        QMessageBox.information(self, "Kopiert", f"{self.table.rowCount()} Peaks in die Zwischenablage kopiert.")

    def export_csv(self):
        name = self.record.get("name", "spectrum")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:30]
        fname, _ = QFileDialog.getSaveFileName(
            self, "CSV Peaklisten-Export", f"{safe_name}_peaks.csv", "CSV Files (*.csv)"
        )
        if not fname:
            return

        lines = ["# " + f"Name: {name}", "mz,relative_intensity_percent,raw_intensity"]
        for r in range(self.table.rowCount()):
            mz = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            rel = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            abs_i = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            lines.append(f"{mz},{rel},{abs_i}")

        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            QMessageBox.information(self, "Export erfolgreich", f"Peakliste erfolgreich als CSV exportiert:\n{fname}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern: {e}")

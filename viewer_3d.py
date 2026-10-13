import os
import sys
import json
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from rdkit import RDLogger

from i18n import t

RDLogger.DisableLog('rdApp.*')

JS_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ketcher", "standalone", "3Dmol-min.js")
_3DMOL_JS_CACHE = None

def get_3dmol_js():
    global _3DMOL_JS_CACHE
    if _3DMOL_JS_CACHE is None:
        try:
            with open(JS_FILE_PATH, "r", encoding="utf-8") as f:
                _3DMOL_JS_CACHE = f.read()
        except Exception as e:
            print(f"[viewer_3d] Fehler beim Laden von 3Dmol-min.js: {e}")
            _3DMOL_JS_CACHE = ""
    return _3DMOL_JS_CACHE


def generate_3d_coordinates(smiles, optimize=True, max_iters=500):
    """
    Generates 3D coordinates for a SMILES string and performs force field minimization.
    Tries MMFF94 first, falls back to UFF.
    Returns:
        dict with keys: molblock, method, energy, atoms_count, heavy_atoms, formula, mw, error
    """
    if not smiles:
        return None, "Kein SMILES angegeben."

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "Ungültiges SMILES-Molekül."

        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = Descriptors.MolWt(mol)

        # Add explicit hydrogens for accurate 3D geometry
        mol_3d = Chem.AddHs(mol)

        # 3D Embedding using ETKDGv3
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        embed_status = AllChem.EmbedMolecule(mol_3d, params)
        if embed_status != 0:
            # Fallback embedding with random coordinates
            embed_status = AllChem.EmbedMolecule(mol_3d, useRandomCoords=True)
            if embed_status != 0:
                return None, "Konnte keine 3D-Konformation einbetten."

        method = "Keine Minimierung"
        energy_val = None

        if optimize:
            if AllChem.MMFFHasAllMoleculeParams(mol_3d):
                mp = AllChem.MMFFGetMoleculeProperties(mol_3d)
                ff = AllChem.MMFFGetMoleculeForceField(mol_3d, mp)
                ff.Minimize(maxIts=max_iters)
                energy_val = ff.CalcEnergy()
                method = "MMFF94"
            elif AllChem.UFFHasAllMoleculeParams(mol_3d):
                ff = AllChem.UFFGetMoleculeForceField(mol_3d)
                ff.Minimize(maxIts=max_iters)
                energy_val = ff.CalcEnergy()
                method = "UFF"

        molblock = Chem.MolToMolBlock(mol_3d)
        
        return {
            "molblock": molblock,
            "method": method,
            "energy": f"{energy_val:.2f} kcal/mol" if energy_val is not None else "N/A",
            "atoms_count": mol_3d.GetNumAtoms(),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "formula": formula,
            "mw": f"{mw:.2f}",
            "smiles": smiles
        }, None

    except Exception as e:
        return None, f"Fehler bei 3D-Generierung: {str(e)}"


class Molecule3DWidget(QWidget):
    """
    Embedded 3D Molecule Viewer Widget with force-field minimization and 3Dmol.js rendering.
    Can be used inside QTabWidget or QDialog.
    """
    load_to_ketcher_requested = Signal(str)
    switch_to_details_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.smiles = None
        self.current_smiles = None
        self.current_data = None
        
        # Dark cosmic styling
        self.setStyleSheet("""
            Molecule3DWidget {
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
            QPushButton#AccentBtn {
                background-color: #10b981;
                color: #02261d;
                border: 1px solid #34d399;
                font-weight: bold;
            }
            QPushButton#AccentBtn:hover {
                background-color: #059669;
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

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        
        self.title_label = QLabel(t("3d_title"))
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        self.info_label = QLabel(t("3d_no_molecule"))
        self.info_label.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        info_box.addWidget(self.title_label)
        info_box.addWidget(self.info_label)
        top_layout.addLayout(info_box)

        top_layout.addStretch()

        self.btn_details = QPushButton(t("3d_btn_details"))
        self.btn_details.setToolTip("Zurück zur Details- und Spektrenansicht wechseln")
        self.btn_details.clicked.connect(self.switch_to_details_requested.emit)
        top_layout.addWidget(self.btn_details)

        self.btn_reopt = QPushButton(t("3d_btn_reopt"))
        self.btn_reopt.setToolTip("Erneute MMFF94/UFF Konformationsoptimierung durchführen")
        self.btn_reopt.clicked.connect(self.load_molecule)
        top_layout.addWidget(self.btn_reopt)

        self.btn_export = QPushButton(t("3d_btn_export"))
        self.btn_export.setToolTip("3D-Koordinaten als .sdf/.mol Datei speichern")
        self.btn_export.clicked.connect(self.export_sdf)
        top_layout.addWidget(self.btn_export)

        self.btn_ketcher = QPushButton(t("3d_btn_ketcher"), objectName="PrimaryBtn")
        self.btn_ketcher.setToolTip("Struktur zurück in Ketcher-Editor übertragen")
        self.btn_ketcher.clicked.connect(self.on_load_to_ketcher)
        top_layout.addWidget(self.btn_ketcher)

        layout.addWidget(top_bar)

        # WebEngine View for 3Dmol.js
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("border-radius: 8px; border: 1px solid #334155; background-color: #070b14;")
        
        # Configure WebEngine Settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        layout.addWidget(self.web_view)

    def retranslate_ui(self):
        self.btn_details.setText(t("3d_btn_details"))
        self.btn_reopt.setText(t("3d_btn_reopt"))
        self.btn_export.setText(t("3d_btn_export"))
        self.btn_ketcher.setText(t("3d_btn_ketcher"))

        if not self.smiles:
            self.show_placeholder()
        elif self.current_data:
            data = self.current_data
            self.title_label.setText(f"{data['formula']} • {data['mw']} g/mol")
            info_text = (
                f"{t('3d_atoms')}: <strong>{data['atoms_count']}</strong> ({data['heavy_atoms']} {t('3d_heavy_atoms')}) • "
                f"{t('3d_method')}: <span style='color:#34d399; font-weight:bold;'>{data['method']}</span> • "
                f"{t('3d_energy')}: <span style='color:#f59e0b; font-weight:bold;'>{data['energy']}</span>"
            )
            self.info_label.setText(info_text)
            self.render_3d_view(data['molblock'])

    def show_placeholder(self):
        self.title_label.setText(t("3d_title"))
        self.info_label.setText(t("3d_no_molecule"))
        self.btn_reopt.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_ketcher.setEnabled(False)

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
            filter: drop-shadow(0 0 12px rgba(56, 189, 248, 0.4));
        }}
        h2 {{
            color: #38bdf8;
            margin: 0 0 8px 0;
            font-size: 20px;
        }}
        p {{
            font-size: 14px;
            max-width: 440px;
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
            padding: 10px 18px;
            border-radius: 8px;
            max-width: 500px;
        }}
        .hint strong {{
            color: #34d399;
        }}
    </style>
</head>
<body>
    <div class="icon">🔬</div>
    <h2>{t('3d_placeholder_title')}</h2>
    <p>{t('3d_placeholder_desc')}</p>
    <div class="hint">
        {t('3d_placeholder_hint')}
    </div>
</body>
</html>
"""
        self.web_view.setHtml(placeholder_html)

    def set_molecule(self, smiles):
        if not smiles:
            self.smiles = None
            self.current_smiles = None
            self.show_placeholder()
            return

        self.smiles = smiles
        self.current_smiles = smiles
        self.btn_reopt.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_ketcher.setEnabled(True)
        self.load_molecule()

    def load_molecule(self):
        if not self.smiles:
            return

        self.info_label.setText(t("3d_calculating"))
        data, err = generate_3d_coordinates(self.smiles, optimize=True, max_iters=500)
        
        if err:
            self.info_label.setText(f"<span style='color:#ef4444;'>Fehler: {err}</span>")
            return

        self.current_data = data
        
        self.title_label.setText(f"{data['formula']} • {data['mw']} g/mol")
        info_text = (
            f"{t('3d_atoms')}: <strong>{data['atoms_count']}</strong> ({data['heavy_atoms']} {t('3d_heavy_atoms')}) • "
            f"{t('3d_method')}: <span style='color:#34d399; font-weight:bold;'>{data['method']}</span> • "
            f"{t('3d_energy')}: <span style='color:#f59e0b; font-weight:bold;'>{data['energy']}</span>"
        )
        self.info_label.setText(info_text)

        self.render_3d_view(data['molblock'])

    def highlight_atoms(self, atom_indices):
        """Highlights specific atoms in the 3D viewer."""
        js_indices = json.dumps(atom_indices or [])
        self.web_view.page().runJavaScript(f"if (window.highlightAtoms) window.highlightAtoms({js_indices});")

    def clear_highlight(self):
        """Resets highlighting in 3D viewer."""
        self.web_view.page().runJavaScript("if (window.clearHighlight) window.clearHighlight();")

    def render_3d_view(self, molblock):
        js_library = get_3dmol_js()
        molblock_escaped = json.dumps(molblock)

        label_style = t("3d_style_label")
        btn_ballstick = t("3d_style_ballstick")
        btn_stick = t("3d_style_stick")
        btn_sphere = t("3d_style_sphere")
        btn_line = t("3d_style_line")
        btn_surf = t("3d_surface")
        btn_spin = t("3d_spin")
        btn_center = t("3d_center")
        hint_mouse = t("3d_mouse_hint")

        part_header = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 0;
            background-color: #070b14;
            color: #f1f5f9;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            overflow: hidden;
            height: 100vh;
            width: 100vw;
            display: flex;
            flex-direction: column;
        }}
        #controls-bar {{
            background: #0f172a;
            border-bottom: 1px solid #1e293b;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            z-index: 100;
            flex-wrap: wrap;
        }}
        .ctrl-btn {{
            background: #1e293b;
            border: 1px solid #334155;
            color: #cbd5e1;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .ctrl-btn:hover {{
            background: #334155;
            color: #ffffff;
            border-color: #475569;
        }}
        .ctrl-btn.active {{
            background: #2563eb;
            color: #ffffff;
            border-color: #3b82f6;
        }}
        .sep {{
            width: 1px;
            height: 20px;
            background: #334155;
            margin: 0 4px;
        }}
        .label-tag {{
            font-size: 11px;
            color: #94a3b8;
            font-weight: bold;
            margin-right: 2px;
        }}
        #viewer-container {{
            flex: 1;
            position: relative;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at center, #111827 0%, #030712 100%);
        }}
        #hint-overlay {{
            position: absolute;
            bottom: 12px;
            left: 16px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 11px;
            color: #94a3b8;
            pointer-events: none;
            backdrop-filter: blur(4px);
        }}
    </style>
    <script>
"""

        part_middle = f"""
    </script>
</head>
<body>
    <div id="controls-bar">
        <span class="label-tag">{label_style}</span>
        <button class="ctrl-btn active" id="btn-ballstick" onclick="setStyle('ballstick')">{btn_ballstick}</button>
        <button class="ctrl-btn" id="btn-stick" onclick="setStyle('stick')">{btn_stick}</button>
        <button class="ctrl-btn" id="btn-sphere" onclick="setStyle('sphere')">{btn_sphere}</button>
        <button class="ctrl-btn" id="btn-line" onclick="setStyle('line')">{btn_line}</button>

        <div class="sep"></div>

        <button class="ctrl-btn" id="btn-surf" onclick="toggleSurface()">{btn_surf}</button>

        <div class="sep"></div>

        <button class="ctrl-btn" id="btn-spin" onclick="toggleSpin()">{btn_spin}</button>
        <button class="ctrl-btn" onclick="resetCamera()">{btn_center}</button>
    </div>

    <div id="viewer-container">
        <div id="hint-overlay">{hint_mouse}</div>
    </div>

    <script>
        let viewer = null;
        let currentModel = null;
        let surfaceObj = null;
        let isSpinning = false;
        let currentStyle = 'ballstick';

        const molData = {molblock_escaped};

        function initViewer() {{
            try {{
                let container = document.getElementById('viewer-container');
                viewer = $3Dmol.createViewer(container, {{
                    backgroundColor: '#070b14'
                }});

                currentModel = viewer.addModel(molData, "sdf");
                applyCurrentStyle();
                viewer.zoomTo();
                viewer.render();
            }} catch(e) {{
                console.error("Fehler beim Initialisieren des 3D-Viewers:", e);
                document.getElementById('viewer-container').innerHTML = 
                    '<p style="color:#ef4444; padding:20px;">Fehler beim Laden des WebGL 3D-Viewers: ' + e + '</p>';
            }}
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initViewer);
        }} else {{
            initViewer();
        }}

        function setStyle(styleName) {{
            currentStyle = styleName;
            ['ballstick', 'stick', 'sphere', 'line'].forEach(s => {{
                let btn = document.getElementById('btn-' + s);
                if (btn) btn.classList.remove('active');
            }});
            let target = document.getElementById('btn-' + styleName);
            if (target) target.classList.add('active');

            applyCurrentStyle();
        }}

        function applyCurrentStyle() {{
            if (!viewer) return;
            viewer.setStyle({{}}, {{}});

            if (currentStyle === 'ballstick') {{
                viewer.setStyle({{}}, {{
                    stick: {{ radius: 0.15, colorscheme: 'Jmol' }},
                    sphere: {{ radius: 0.35, colorscheme: 'Jmol' }}
                }});
            }} else if (currentStyle === 'stick') {{
                viewer.setStyle({{}}, {{
                    stick: {{ radius: 0.22, colorscheme: 'Jmol' }}
                }});
            }} else if (currentStyle === 'sphere') {{
                viewer.setStyle({{}}, {{
                    sphere: {{ colorscheme: 'Jmol' }}
                }});
            }} else if (currentStyle === 'line') {{
                viewer.setStyle({{}}, {{
                    line: {{ colorscheme: 'Jmol' }}
                }});
            }}

            viewer.render();
        }}

        function toggleSurface() {{
            let btn = document.getElementById('btn-surf');
            if (surfaceObj) {{
                viewer.removeSurface(surfaceObj);
                surfaceObj = null;
                btn.classList.remove('active');
            }} else {{
                surfaceObj = viewer.addSurface($3Dmol.SurfaceType.VDW, {{
                    opacity: 0.65,
                    colorscheme: 'Jmol'
                }});
                btn.classList.add('active');
            }}
            viewer.render();
        }}

        function toggleSpin() {{
            let btn = document.getElementById('btn-spin');
            isSpinning = !isSpinning;
            if (isSpinning) {{
                viewer.spin("y", 1);
                btn.classList.add('active');
            }} else {{
                viewer.spin(false);
                btn.classList.remove('active');
            }}
        }}

        function resetCamera() {{
            if (viewer) {{
                viewer.zoomTo();
                viewer.render();
            }}
        }}

        window.highlightAtoms = function(atomIndices) {{
            if (!viewer || !currentModel) return;
            applyCurrentStyle();
            if (!atomIndices || atomIndices.length === 0) return;
            // 3Dmol atom selection by serial / index (0-based)
            for (let i = 0; i < atomIndices.length; i++) {{
                let idx = atomIndices[i];
                viewer.setStyle({{ serial: idx }}, {{
                    sphere: {{ radius: 0.75, color: '#38bdf8' }},
                    stick: {{ radius: 0.35, color: '#38bdf8' }}
                }});
            }}
            viewer.render();
        }};

        window.clearHighlight = function() {{
            if (!viewer) return;
            applyCurrentStyle();
        }};
    </script>
</body>
</html>
"""

        full_html = part_header + js_library + part_middle
        self.web_view.setHtml(full_html)

    def export_sdf(self):
        if not self.current_data or not self.current_data.get("molblock"):
            QMessageBox.warning(self, "Export", "Keine 3D-Daten zum Exportieren vorhanden.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "3D Molekül als SDF speichern",
            f"{self.current_data.get('formula', 'molecule')}_3d.sdf",
            "SDF / Molfile (*.sdf *.mol);;Alle Dateien (*.*)"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.current_data["molblock"])
                QMessageBox.information(self, "Erfolg", f"3D-Struktur erfolgreich gespeichert unter:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Konnte Datei nicht speichern:\n{e}")

    def on_load_to_ketcher(self):
        if self.smiles:
            self.load_to_ketcher_requested.emit(self.smiles)


class Molecule3DDialog(QDialog):
    """
    Optional standalone dialog wrapping Molecule3DWidget.
    """
    load_to_ketcher_requested = Signal(str)

    def __init__(self, smiles=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HGTTD • 3D Molekül-Viewer & Kraftfeldminimierung")
        self.resize(1100, 780)
        self.setMinimumSize(850, 600)

        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.widget = Molecule3DWidget(self)
        self.widget.load_to_ketcher_requested.connect(self._handle_ketcher)
        self.widget.switch_to_details_requested.connect(self.close)
        layout.addWidget(self.widget)

        if smiles:
            self.widget.set_molecule(smiles)

    def _handle_ketcher(self, smiles):
        self.load_to_ketcher_requested.emit(smiles)
        self.accept()

import os
import json
import time
from datetime import datetime
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

from logbook_manager import logbook_manager
from auto_assignment_engine import auto_assignment_engine
from i18n import t

def generate_molecule_svg(smiles, width=400, height=300):
    if not smiles:
        return ""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        tm = Chem.RemoveHs(mol)
        for i, atom in enumerate(tm.GetAtoms()):
            atom.SetProp("atomNote", str(i + 1))
        from rdkit.Chem import AllChem
        AllChem.Compute2DCoords(tm)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        opts = drawer.drawOptions()
        opts.addAtomIndices = False
        opts.annotationFontScale = 0.65
        drawer.DrawMolecule(tm)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return ""

def generate_html_report(record, title=None):
    """
    Builds a professional, clean, self-contained HTML/PDF printable analysis certificate.
    """
    if not record:
        return "<html><body><h1>Kein Datensatz vorhanden</h1></body></html>"

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    smiles = record.get("smiles", "")
    name = record.get("name") or record.get("filename") or "Analysenprobe"
    formula = record.get("formula", "-")
    mw = record.get("mw", "-")
    source_db = record.get("source_db", "HGTTD")
    nmr_type = record.get("nmr_type", "NMR")
    solvent = record.get("solvent", "Unbekannt")
    freq = record.get("frequency", "Standard")
    doc_id = record.get("id") or record.get("filename") or "-"
    doi_url = record.get("doi_url", "")

    # Mol SVG
    svg_mol = record.get("svg") or generate_molecule_svg(smiles)

    # Personal notes from logbook
    meta = logbook_manager.get_molecule_meta(smiles) if smiles else None
    user_notes = meta.get("notes", "") if meta else ""
    user_tags = meta.get("tags", "") if meta else ""

    # Peak list rows
    peaks = record.get("spectrum", [])
    peak_rows = []
    for i, p in enumerate(peaks):
        shift = p.get("shift", "-")
        mult = p.get("multiplicity", "-")
        j = p.get("j_coupling", "-")
        integ = p.get("integral", "-")
        atom_idx = p.get("atom_index", "-")
        peak_rows.append(f"""
        <tr>
            <td style="text-align:center; color:#64748b;">{i+1}</td>
            <td style="font-weight:bold; color:#0284c7; font-family:monospace;">{shift}</td>
            <td style="text-align:center;">{mult}</td>
            <td style="text-align:center;">{j}</td>
            <td style="text-align:center;">{integ}</td>
            <td style="text-align:center;">{atom_idx}</td>
        </tr>
        """)

    table_body = "".join(peak_rows) if peak_rows else "<tr><td colspan='6' style='text-align:center;'>Keine Peaks tabelliert</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <title>HGTTD Laborbericht – {name}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 18mm 15mm;
        }}
        body {{
            font-family: 'Segoe UI', -apple-system, Helvetica, Arial, sans-serif;
            color: #1e293b;
            background: #ffffff;
            margin: 0;
            padding: 20px;
            font-size: 13px;
            line-height: 1.5;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #0284c7;
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            color: #0369a1;
            font-size: 24px;
        }}
        .header .subtitle {{
            color: #64748b;
            font-size: 12px;
            margin-top: 4px;
        }}
        .header .meta-right {{
            text-align: right;
            font-size: 11px;
            color: #64748b;
        }}
        .section-title {{
            font-size: 15px;
            font-weight: bold;
            color: #0f172a;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 4px;
            margin-top: 20px;
            margin-bottom: 12px;
        }}
        .grid {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .col-mol {{
            flex: 1;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #f8fafc;
        }}
        .col-mol svg {{
            max-width: 100%;
            height: auto;
        }}
        .col-props {{
            flex: 1.2;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .prop-row {{
            display: flex;
            justify-content: space-between;
            padding: 5px 8px;
            background: #f8fafc;
            border-radius: 4px;
            font-size: 12px;
        }}
        .prop-label {{
            font-weight: 600;
            color: #475569;
        }}
        .prop-val {{
            color: #0f172a;
            font-weight: 500;
        }}
        .notes-box {{
            background: #f1f5f9;
            border-left: 4px solid #38bdf8;
            padding: 10px 14px;
            border-radius: 0 6px 6px 0;
            font-size: 12px;
            margin-bottom: 16px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 8px;
        }}
        th {{
            background: #f1f5f9;
            color: #334155;
            padding: 7px 10px;
            border: 1px solid #cbd5e1;
            font-weight: 600;
        }}
        td {{
            padding: 6px 10px;
            border: 1px solid #e2e8f0;
        }}
        tr:nth-child(even) td {{
            background: #f8fafc;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 10px;
            border-top: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            color: #94a3b8;
        }}
        @media print {{
            body {{ padding: 0; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>HGTTD Analysenbericht</h1>
            <div class="subtitle">Hitchhiker's Guide through the database • Spektroskopie & Struktur-Suite</div>
        </div>
        <div class="meta-right">
            <strong>Datum:</strong> {now_str}<br>
            <strong>Quelle:</strong> {source_db} • ID: {doc_id}
        </div>
    </div>

    <div class="section-title">Chemische Identifikation</div>
    <div class="grid">
        <div class="col-mol">
            {svg_mol}
        </div>
        <div class="col-props">
            <div class="prop-row"><span class="prop-label">Substanz / Name:</span><span class="prop-val"><strong>{name}</strong></span></div>
            <div class="prop-row"><span class="prop-label">Summenformel:</span><span class="prop-val">{formula}</span></div>
            <div class="prop-row"><span class="prop-label">Molmasse:</span><span class="prop-val">{mw} g/mol</span></div>
            <div class="prop-row"><span class="prop-label">Spektroskopie-Typ:</span><span class="prop-val">{nmr_type}</span></div>
            <div class="prop-row"><span class="prop-label">Lösungsmittel:</span><span class="prop-val">{solvent}</span></div>
            <div class="prop-row"><span class="prop-label">Spektrometer-Frequenz:</span><span class="prop-val">{freq}</span></div>
            <div class="prop-row"><span class="prop-label">SMILES:</span><span class="prop-val" style="font-family:monospace; word-break:break-all; font-size:10px;">{smiles}</span></div>
            {f'<div class="prop-row"><span class="prop-label">Kollektionen / Tags:</span><span class="prop-val">{user_tags}</span></div>' if user_tags else ''}
        </div>
    </div>

    {f'''
    <div class="section-title">Labor-Notizen & Bemerkungen</div>
    <div class="notes-box">
        {user_notes}
    </div>
    ''' if user_notes else ''}

    <div class="section-title">Spektrale Signaldaten ({len(peaks)} Peaks)</div>
    <table>
        <thead>
            <tr>
                <th style="width:40px;">#</th>
                <th>Chem. Verschiebung δ (ppm)</th>
                <th>Multiplizität</th>
                <th>Kopplung J (Hz)</th>
                <th>Integral</th>
                <th>Atom-Nr.</th>
            </tr>
        </thead>
        <tbody>
            {table_body}
        </tbody>
    </table>

    <div class="footer">
        <div>HGTTD • Generiert mit automatischer RDKit & est-NMR Zuordnung</div>
        <div>Don't Panic! • Die Antwort ist 42</div>
    </div>
</body>
</html>
"""
    return html


def generate_molecule_png_bytes(smiles, width=420, height=320):
    """Renders molecule to PNG bytes using RDKit Cairo."""
    if not smiles:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        tm = Chem.RemoveHs(mol)
        for i, atom in enumerate(tm.GetAtoms()):
            atom.SetProp("atomNote", str(i + 1))
        from rdkit.Chem import AllChem
        AllChem.Compute2DCoords(tm)
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        opts = drawer.drawOptions()
        opts.addAtomIndices = False
        opts.annotationFontScale = 0.65
        drawer.DrawMolecule(tm)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return None


def export_pdf_report(record, output_path):
    """
    Exports a clean, high-resolution PDF report using Qt's QPdfWriter and QTextDocument.
    """
    from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize, QPdfWriter, QImage
    from PySide6.QtCore import QMarginsF, QUrl

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    smiles = record.get("smiles", "")
    name = record.get("name") or record.get("filename") or "Analysenprobe"
    formula = record.get("formula", "-")
    mw = record.get("mw", "-")
    source_db = record.get("source_db", "HGTTD")
    nmr_type = record.get("nmr_type", "NMR")
    solvent = record.get("solvent", "Unbekannt")
    freq = record.get("frequency", "Standard")
    doc_id = record.get("id") or record.get("filename") or "-"

    meta = logbook_manager.get_molecule_meta(smiles) if smiles else None
    user_notes = meta.get("notes", "") if meta else ""
    user_tags = meta.get("tags", "") if meta else ""

    peaks = record.get("spectrum", [])
    peak_rows = []
    for i, p in enumerate(peaks):
        shift = p.get("shift", "-")
        mult = p.get("multiplicity", "-")
        j = p.get("j_coupling", "-")
        integ = p.get("integral", "-")
        atom_idx = p.get("atom_index", "-")
        bg = "#f8fafc" if i % 2 == 1 else "#ffffff"
        peak_rows.append(f"""
        <tr bgcolor="{bg}">
            <td align="center" style="color:#64748b; padding:4px 6px;">{i+1}</td>
            <td align="center" style="font-weight:bold; color:#0284c7; padding:4px 6px;">{shift}</td>
            <td align="center" style="padding:4px 6px;">{mult}</td>
            <td align="center" style="padding:4px 6px;">{j}</td>
            <td align="center" style="padding:4px 6px;">{integ}</td>
            <td align="center" style="padding:4px 6px;">{atom_idx}</td>
        </tr>
        """)

    table_body = "".join(peak_rows) if peak_rows else "<tr><td colspan='6' align='center'>Keine Peaks tabelliert</td></tr>"

    doc = QTextDocument()
    png_bytes = generate_molecule_png_bytes(smiles)
    if png_bytes:
        qimg = QImage()
        if qimg.loadFromData(png_bytes):
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("mol_preview.png"), qimg)
            mol_img_html = '<img src="mol_preview.png" width="280" height="210">'
        else:
            mol_img_html = '<div style="color:#64748b;">(Struktur nicht gerendert)</div>'
    else:
        mol_img_html = '<div style="color:#64748b;">(Keine Strukturformel verfügbar)</div>'

    tags_html = f'<tr><td style="color:#475569; font-weight:bold; padding:3px 6px;">Kollektionen / Tags:</td><td style="padding:3px 6px;">{user_tags}</td></tr>' if user_tags else ''
    notes_html = f'''
    <h3 style="font-size:14px; color:#0f172a; margin-top:16px; margin-bottom:6px; border-bottom:1px solid #cbd5e1; padding-bottom:3px;">Labor-Notizen & Bemerkungen</h3>
    <table width="100%" bgcolor="#f1f5f9" cellpadding="8" cellspacing="0" style="border-left:4px solid #38bdf8; margin-bottom:12px;">
        <tr><td>{user_notes}</td></tr>
    </table>
    ''' if user_notes else ''

    pdf_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family:'Segoe UI', Arial, sans-serif; color:#1e293b; font-size:11pt;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid #0284c7; padding-bottom:8px; margin-bottom:14px;">
        <tr>
            <td valign="top">
                <h1 style="margin:0; color:#0369a1; font-size:20pt;">HGTTD Analysenbericht</h1>
                <div style="color:#64748b; font-size:9pt; margin-top:2px;">Hitchhiker's Guide through the database • Spektroskopie & Struktur-Suite</div>
            </td>
            <td valign="top" align="right" style="color:#64748b; font-size:9pt;">
                <b>Datum:</b> {now_str}<br>
                <b>Quelle:</b> {source_db} • <b>ID:</b> {doc_id}
            </td>
        </tr>
    </table>

    <h3 style="font-size:14px; color:#0f172a; margin-top:14px; margin-bottom:8px; border-bottom:1px solid #cbd5e1; padding-bottom:3px;">Chemische Identifikation</h3>
    <table width="100%" cellpadding="6" cellspacing="0">
        <tr>
            <td width="42%" valign="middle" align="center" bgcolor="#f8fafc" style="border:1px solid #e2e8f0; border-radius:6px;">
                {mol_img_html}
            </td>
            <td width="3%">&nbsp;</td>
            <td width="55%" valign="top">
                <table width="100%" cellpadding="3" cellspacing="0" style="font-size:10pt;">
                    <tr bgcolor="#f8fafc"><td style="color:#475569; font-weight:bold; padding:3px 6px;">Substanz / Name:</td><td style="padding:3px 6px;"><b>{name}</b></td></tr>
                    <tr><td style="color:#475569; font-weight:bold; padding:3px 6px;">Summenformel:</td><td style="padding:3px 6px;">{formula}</td></tr>
                    <tr bgcolor="#f8fafc"><td style="color:#475569; font-weight:bold; padding:3px 6px;">Molmasse:</td><td style="padding:3px 6px;">{mw} g/mol</td></tr>
                    <tr><td style="color:#475569; font-weight:bold; padding:3px 6px;">Spektroskopie-Typ:</td><td style="padding:3px 6px;">{nmr_type}</td></tr>
                    <tr bgcolor="#f8fafc"><td style="color:#475569; font-weight:bold; padding:3px 6px;">Lösungsmittel:</td><td style="padding:3px 6px;">{solvent}</td></tr>
                    <tr><td style="color:#475569; font-weight:bold; padding:3px 6px;">Spektrometer-Frequenz:</td><td style="padding:3px 6px;">{freq}</td></tr>
                    <tr bgcolor="#f8fafc"><td style="color:#475569; font-weight:bold; padding:3px 6px;">SMILES:</td><td style="font-family:monospace; font-size:8pt; padding:3px 6px;">{smiles}</td></tr>
                    {tags_html}
                </table>
            </td>
        </tr>
    </table>

    {notes_html}

    <h3 style="font-size:14px; color:#0f172a; margin-top:16px; margin-bottom:8px; border-bottom:1px solid #cbd5e1; padding-bottom:3px;">Spektrale Signaldaten ({len(peaks)} Peaks)</h3>
    <table width="100%" cellpadding="4" cellspacing="0" border="1" style="border-collapse:collapse; border-color:#cbd5e1; font-size:10pt;">
        <thead>
            <tr bgcolor="#f1f5f9">
                <th width="35" align="center" style="padding:5px 6px; color:#334155;">#</th>
                <th align="center" style="padding:5px 6px; color:#334155;">Chem. Verschiebung δ (ppm)</th>
                <th align="center" style="padding:5px 6px; color:#334155;">Multiplizität</th>
                <th align="center" style="padding:5px 6px; color:#334155;">Kopplung J (Hz)</th>
                <th align="center" style="padding:5px 6px; color:#334155;">Integral</th>
                <th align="center" style="padding:5px 6px; color:#334155;">Atom-Nr.</th>
            </tr>
        </thead>
        <tbody>
            {table_body}
        </tbody>
    </table>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px; border-top:1px solid #e2e8f0; padding-top:6px; color:#94a3b8; font-size:8pt;">
        <tr>
            <td>HGTTD • Generiert mit automatischer RDKit & est-NMR Zuordnung</td>
            <td align="right">Don't Panic! • Die Antwort ist 42</td>
        </tr>
    </table>
</body>
</html>
"""
    doc.setHtml(pdf_html)
    writer = QPdfWriter(output_path)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(15, 15, 15, 15)))
    doc.print_(writer)


def export_report_dialog(parent, record):
    """
    Unified export dialog offering saving as PDF document (*.pdf) or HTML report (*.html, *.htm).
    """
    import re
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    if not record:
        QMessageBox.warning(parent, "Export", "Kein Datensatz für einen Laborbericht geladen.")
        return

    formula_clean = re.sub(r"[^\w\-]", "", record.get("formula", "analyse"))
    nuc = record.get("nmr_type", "NMR")
    nuc_clean = re.sub(r"[^\w\-]", "", nuc)
    default_filename = f"Laborbericht_{formula_clean}_{nuc_clean}.pdf"

    filter_str = (
        "PDF Dokument (*.pdf);;"
        "HTML Laborbericht (*.html *.htm);;"
        "Alle Dateien (*.*)"
    )

    filepath, selected_filter = QFileDialog.getSaveFileName(
        parent,
        t("report_filter_title"),
        default_filename,
        filter_str
    )

    if not filepath:
        return

    try:
        lower_path = filepath.lower()
        if lower_path.endswith(".pdf") or "pdf" in selected_filter.lower():
            if not lower_path.endswith(".pdf"):
                filepath += ".pdf"
            export_pdf_report(record, filepath)
        else:
            if not (lower_path.endswith(".html") or lower_path.endswith(".htm")):
                filepath += ".html"
            html_content = generate_html_report(record)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)

        QMessageBox.information(parent, "Erfolg", t("report_success", path=filepath))
    except Exception as e:
        QMessageBox.critical(parent, "Fehler", f"Fehler beim Speichern des Laborberichts: {str(e)}")


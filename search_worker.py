import os
import sys
from PySide6.QtCore import QThread, Signal
from rdkit import Chem
from rdkit import RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

from nmrexp_manager import NMRexpManager
from ir_manager import IRManager

# Suppress RDKit logs
RDLogger.DisableLog('rdApp.*')

class SearchWorker(QThread):
    progress_signal = Signal(str)
    finished_signal = Signal(list, str) # (results, error_message)

    def __init__(self, query_smiles, sdf_path=None, parquet_path=None, source_choice="both", nucleus_filter="all", search_mode="exact", max_results=100, min_similarity=0.7):
        super().__init__()
        self.query_smiles = query_smiles
        self.sdf_path = sdf_path
        self.parquet_path = parquet_path
        self.source_choice = source_choice # "nmrshiftdb2", "nmrexp", "mona", "ir", "both", or "all"
        self.nucleus_filter = nucleus_filter # "all", "1H", "13C", "19F", "31P", "11B", "29Si"
        self.search_mode = search_mode # "exact", "substructure", or "similarity"
        self.max_results = max_results # 50, 100, 250, 500, or 0 (all)
        self.min_similarity = min_similarity # float 0.6 .. 0.9
        self.is_cancelled = False
        self.nmrexp_mgr = NMRexpManager(parquet_path=parquet_path)
        self.ir_mgr = IRManager()

    def cancel(self):
        """Signals the worker to abort search gracefully."""
        self.is_cancelled = True

    def draw_annotated_mol(self, mol, highlight_atoms=None, highlight_bonds=None):
        """Draw molecule without H atoms and with 1-based atom indices, with optional substructure highlighting."""
        try:
            tm = Chem.RemoveHs(mol)
            for i, atom in enumerate(tm.GetAtoms()):
                atom.SetProp("atomNote", str(i + 1))

            AllChem.Compute2DCoords(tm)
            drawer = rdMolDraw2D.MolDraw2DSVG(450, 350)
            opts = drawer.drawOptions()
            opts.addAtomIndices = False
            opts.annotationFontScale = 0.65
            if highlight_atoms or highlight_bonds:
                opts.setHighlightColour((0.22, 0.74, 0.97, 0.65))
                drawer.DrawMolecule(
                    tm,
                    highlightAtoms=list(highlight_atoms) if highlight_atoms else [],
                    highlightBonds=list(highlight_bonds) if highlight_bonds else []
                )
            else:
                drawer.DrawMolecule(tm)
            drawer.FinishDrawing()
            return drawer.GetDrawingText()
        except Exception as e:
            return f"<p>Fehler beim Zeichnen des Moleküls: {e}</p>"

    def parse_sdf_spectrum(self, spec_str):
        """Parse SDF spectrum string to unified list of peak dictionaries."""
        rows = []
        if not spec_str:
            return rows
        entries = [e for e in spec_str.split('|') if e.strip()]
        for entry in entries:
            parts = entry.split(';')
            if len(parts) >= 3:
                try:
                    rows.append({
                        "shift": f"{float(parts[0]):.2f}",
                        "multiplicity": parts[1] if parts[1] else "-",
                        "atom_index": int(parts[2]),
                        "j_coupling": "-",
                        "integral": "-"
                    })
                except ValueError:
                    pass
        return rows

    def search_sdf(self, query_mol, query_inchikey, query_smiles_canon):
        """Searches nmrshiftdb2 SDF file."""
        if not self.sdf_path or not os.path.exists(self.sdf_path):
            return []

        # nmrshiftdb2 only contains 13C NMR spectra!
        if self.nucleus_filter not in ("all", "13C"):
            return []

        supplier = Chem.SDMolSupplier(self.sdf_path, removeHs=False)
        results = []

        if self.search_mode == "substructure":
            self.progress_signal.emit("Durchsuche nmrshiftdb2 (Substruktur, SDF)...")
            clean_query = Chem.RemoveHs(query_mol)
            heteros = [atom.GetSymbol() for atom in clean_query.GetAtoms() if atom.GetSymbol() not in ('C', 'H')]

            for idx, mol in enumerate(supplier):
                if self.is_cancelled:
                    break

                if mol is None:
                    continue

                if idx > 0 and idx % 2500 == 0:
                    self.progress_signal.emit(f"SDF durchsucht: {idx} Verbindungen ({len(results)} Treffer)...")

                try:
                    clean_mol = Chem.RemoveHs(mol)
                    # Check heteroatoms
                    if heteros:
                        target_heteros = {atom.GetSymbol() for atom in clean_mol.GetAtoms()}
                        if not all(h in target_heteros for h in heteros):
                            continue

                    match = clean_mol.GetSubstructMatch(clean_query)
                    if match:
                        bonds = []
                        for b in clean_query.GetBonds():
                            b1 = match[b.GetBeginAtomIdx()]
                            b2 = match[b.GetEndAtomIdx()]
                            bond_obj = clean_mol.GetBondBetweenAtoms(b1, b2)
                            if bond_obj:
                                bonds.append(bond_obj.GetIdx())

                        props = mol.GetPropsAsDict()
                        id_tag = next((k for k in props if 'nmrshiftdb2 ID' in k), None)
                        spec_tag = next((k for k in props if 'Spectrum 13C' in k), None)
                        solvent_tag = next((k for k in props if 'Solvent' in k), None)

                        svg_text = self.draw_annotated_mol(mol, highlight_atoms=list(match), highlight_bonds=bonds)
                        spec_data = self.parse_sdf_spectrum(props.get(spec_tag, "") if spec_tag else "")

                        formula = rdMolDescriptors.CalcMolFormula(mol)
                        mw = Descriptors.MolWt(mol)

                        id_val = str(props.get(id_tag, "N/A")) if id_tag else "N/A"
                        nmr_url = f"https://nmrshiftdb.nmr.uni-koeln.de/portal?action=show&id={id_val}" if id_val and id_val != "N/A" else None

                        results.append({
                            "source_db": "nmrshiftdb2",
                            "name": mol.GetProp("_Name") if mol.HasProp("_Name") else "Unbekannt",
                            "id": id_val,
                            "doi_url": nmr_url,
                            "solvent": props.get(solvent_tag, "Unbekannt") if solvent_tag else "Unbekannt",
                            "frequency": "Nicht angegeben",
                            "validated": props.get('>  <NMR_Validiert>', props.get('NMR_Validiert', 'False')),
                            "corrected": props.get('>  <NMR_korrigiert>', props.get('NMR_korrigiert', 'False')),
                            "nmr_type": "13C NMR",
                            "nucleus_key": "13C",
                            "nucleus_color": "#3b82f6",
                            "svg": svg_text,
                            "smiles": Chem.MolToSmiles(clean_mol, canonical=True),
                            "formula": formula,
                            "mw": f"{mw:.2f}",
                            "shift_text": "",
                            "spectrum": spec_data,
                            "props": props
                        })

                        if self.max_results and self.max_results > 0 and len(results) >= self.max_results:
                            break
                except Exception:
                    continue
        else:
            # Exact search
            self.progress_signal.emit("Durchsuche nmrshiftdb2 (Exakt, SDF)...")
            for idx, mol in enumerate(supplier):
                if self.is_cancelled:
                    break

                if mol is None:
                    continue

                if idx > 0 and idx % 2500 == 0:
                    self.progress_signal.emit(f"SDF durchsucht: {idx} Verbindungen...")

                match = False
                try:
                    if query_inchikey:
                        mol_inchikey = Chem.MolToInchiKey(mol)
                        if mol_inchikey == query_inchikey:
                            match = True

                    if not match:
                        mol_canon = Chem.MolToSmiles(Chem.RemoveHs(mol), canonical=True)
                        if mol_canon == query_smiles_canon:
                            match = True
                except Exception:
                    pass

                if match:
                    props = mol.GetPropsAsDict()
                    id_tag = next((k for k in props if 'nmrshiftdb2 ID' in k), None)
                    spec_tag = next((k for k in props if 'Spectrum 13C' in k), None)
                    solvent_tag = next((k for k in props if 'Solvent' in k), None)

                    svg_text = self.draw_annotated_mol(mol)
                    spec_data = self.parse_sdf_spectrum(props.get(spec_tag, "") if spec_tag else "")

                    formula = rdMolDescriptors.CalcMolFormula(mol)
                    mw = Descriptors.MolWt(mol)

                    id_val = str(props.get(id_tag, "N/A")) if id_tag else "N/A"
                    nmr_url = f"https://nmrshiftdb.nmr.uni-koeln.de/portal?action=show&id={id_val}" if id_val and id_val != "N/A" else None

                    results.append({
                        "source_db": "nmrshiftdb2",
                        "name": mol.GetProp("_Name") if mol.HasProp("_Name") else "Unbekannt",
                        "id": id_val,
                        "doi_url": nmr_url,
                        "solvent": props.get(solvent_tag, "Unbekannt") if solvent_tag else "Unbekannt",
                        "frequency": "Nicht angegeben",
                        "validated": props.get('>  <NMR_Validiert>', props.get('NMR_Validiert', 'False')),
                        "corrected": props.get('>  <NMR_korrigiert>', props.get('NMR_korrigiert', 'False')),
                        "nmr_type": "13C NMR",
                        "nucleus_key": "13C",
                        "nucleus_color": "#3b82f6",
                        "svg": svg_text,
                        "smiles": Chem.MolToSmiles(Chem.RemoveHs(mol), canonical=True),
                        "formula": formula,
                        "mw": f"{mw:.2f}",
                        "shift_text": "",
                        "spectrum": spec_data,
                        "props": props
                    })

                    if self.max_results and self.max_results > 0 and len(results) >= self.max_results:
                        break

        return results

    def search_nmrexp(self):
        """Searches NMRexp parquet database via NMRexpManager."""
        if not self.nmrexp_mgr.is_available():
            return []

        if self.search_mode == "substructure":
            self.progress_signal.emit("Durchsuche NMRexp (Substruktur, 3.37M Spektren)...")
            nmrexp_hits = self.nmrexp_mgr.search_substructure(
                self.query_smiles,
                nucleus_filter=self.nucleus_filter,
                max_results=self.max_results,
                progress_callback=self.progress_signal.emit,
                cancel_callback=lambda: self.is_cancelled
            )
        elif self.search_mode == "similarity":
            self.progress_signal.emit(f"Durchsuche NMRexp (Ähnlichkeit ≥ {int(self.min_similarity*100)}%, Morgan FP)...")
            nmrexp_hits = self.nmrexp_mgr.search_similarity(
                self.query_smiles,
                min_similarity=self.min_similarity,
                nucleus_filter=self.nucleus_filter,
                max_results=self.max_results,
                progress_callback=self.progress_signal.emit,
                cancel_callback=lambda: self.is_cancelled
            )
        else:
            self.progress_signal.emit("Durchsuche NMRexp (Exakt, 3.37M Spektren)...")
            nmrexp_hits = self.nmrexp_mgr.search_by_smiles(
                self.query_smiles,
                nucleus_filter=self.nucleus_filter
            )

        results = []
        for r in nmrexp_hits:
            if self.is_cancelled:
                break
            results.append({
                "source_db": "NMRexp",
                "name": f"NMRexp ({r['nmr_type']})",
                "id": r["filename"],
                "doi_url": r["doi_url"],
                "solvent": r["solvent"],
                "frequency": r["frequency"],
                "validated": "N/A",
                "corrected": "N/A",
                "nmr_type": r["nmr_type"],
                "nucleus_key": r["nucleus_key"],
                "nucleus_color": r["nucleus_color"],
                "svg": r["svg"],
                "smiles": r["smiles"],
                "formula": r["formula"],
                "mw": r["mw"],
                "shift_text": r["shift_text"],
                "spectrum": r["spectrum"],
                "page_mol": r.get("page_mol"),
                "page_para": r.get("page_para"),
                "similarity": r.get("similarity"),
                "props": {}
            })
            if self.max_results and self.max_results > 0 and len(results) >= self.max_results:
                break

        return results

    def search_mona(self, query_mol):
        """Search MoNa MassBank for exact or substructure matches."""
        try:
            from mona_manager import MonaManager
            mona_mgr = MonaManager()
            if not mona_mgr.is_database_available():
                return []

            results = []
            rec_count_str = f"{mona_mgr.total_records:,} " if mona_mgr.total_records > 0 else ""
            if self.search_mode == "substructure":
                self.progress_signal.emit(f"Durchsuche MoNa MassBank (Substruktur, {rec_count_str}Spektren)...")
                hits, highlights = mona_mgr.search_substructure(
                    self.query_smiles,
                    limit=self.max_results if (self.max_results and self.max_results > 0) else 100,
                    progress_callback=lambda cur, tot, m: not self.is_cancelled
                )
                for r in hits:
                    if self.is_cancelled:
                        break
                    smi = r.get("smiles", "")
                    hl_atoms = highlights.get(smi, [])
                    mol = Chem.MolFromSmiles(smi) if smi else None
                    r["svg"] = self.draw_annotated_mol(mol, highlight_atoms=hl_atoms) if mol else ""
                    results.append(r)
            else:
                self.progress_signal.emit(f"Durchsuche MoNa MassBank (Exakt, {rec_count_str}Spektren)...")
                hits = mona_mgr.search_exact(self.query_smiles)
                for r in hits:
                    if self.is_cancelled:
                        break
                    smi = r.get("smiles", "")
                    mol = Chem.MolFromSmiles(smi) if smi else None
                    r["svg"] = self.draw_annotated_mol(mol) if mol else ""
                    results.append(r)

            return results
        except Exception as e:
            print(f"[SearchWorker] Fehler bei MoNa-Suche: {e}")
            return []

    def search_ir(self, query_mol):
        """Search SQuIRL & NIST IR database for exact or substructure matches."""
        try:
            if not self.ir_mgr.is_available():
                return []
            results = []
            if self.search_mode == "substructure":
                self.progress_signal.emit("Durchsuche IR-Datenbank (SQuIRL/NIST Substruktur)...")
                hits = self.ir_mgr.search_substructure(
                    self.query_smiles,
                    max_hits=self.max_results if (self.max_results and self.max_results > 0) else 100
                )
            else:
                self.progress_signal.emit("Durchsuche IR-Datenbank (SQuIRL/NIST Exakt)...")
                hits = self.ir_mgr.search_exact(self.query_smiles)

            for r in hits:
                if self.is_cancelled:
                    break
                smi = r.get("smiles", "")
                mol = Chem.MolFromSmiles(smi) if smi else None
                r["svg"] = self.draw_annotated_mol(mol) if mol else ""
                r["source_db"] = "IR"
                results.append(r)
            return results
        except Exception as e:
            print(f"[SearchWorker] Fehler bei IR-Suche: {e}")
            return []

    def run(self):
        try:
            query_mol = Chem.MolFromSmiles(self.query_smiles)
            if query_mol is None:
                try:
                    query_mol = Chem.MolFromSmarts(self.query_smiles)
                except Exception:
                    query_mol = None

            if query_mol is None:
                self.finished_signal.emit([], "Ungültiger SMILES-Code.")
                return

            try:
                query_inchikey = Chem.MolToInchiKey(query_mol)
            except Exception:
                query_inchikey = None

            try:
                query_smiles_canon = Chem.MolToSmiles(Chem.RemoveHs(query_mol), canonical=True)
            except Exception:
                query_smiles_canon = self.query_smiles

            all_results = []

            # 1. Search NMRexp if selected
            if not self.is_cancelled and self.source_choice in ("nmrexp", "both", "all"):
                nmrexp_results = self.search_nmrexp()
                all_results.extend(nmrexp_results)

            # 2. Search nmrshiftdb2 if selected (only if limit not yet reached)
            if not self.is_cancelled and self.source_choice in ("nmrshiftdb2", "both", "all"):
                if not self.max_results or self.max_results <= 0 or len(all_results) < self.max_results:
                    remaining = (self.max_results - len(all_results)) if (self.max_results and self.max_results > 0) else 0
                    orig_max = self.max_results
                    self.max_results = remaining
                    try:
                        sdf_results = self.search_sdf(query_mol, query_inchikey, query_smiles_canon)
                        all_results.extend(sdf_results)
                    finally:
                        self.max_results = orig_max

            # 3. Search MoNa MassBank if selected
            if not self.is_cancelled and self.source_choice in ("mona", "all"):
                if not self.max_results or self.max_results <= 0 or len(all_results) < self.max_results:
                    mona_results = self.search_mona(query_mol)
                    all_results.extend(mona_results)

            # 4. Search IR (SQuIRL & NIST) if selected
            if not self.is_cancelled and self.source_choice in ("ir", "all"):
                if not self.max_results or self.max_results <= 0 or len(all_results) < self.max_results:
                    ir_results = self.search_ir(query_mol)
                    all_results.extend(ir_results)

            # Cap results if max_results is set
            if self.max_results and self.max_results > 0 and len(all_results) > self.max_results:
                all_results = all_results[:self.max_results]

            self.finished_signal.emit(all_results, "")
        except Exception as e:
            self.finished_signal.emit([], f"Fehler bei der Suche: {str(e)}")

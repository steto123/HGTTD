import os
import ast
import time
import numpy as np
import pyarrow.parquet as pq
import pyarrow.compute as pc
import pyarrow as pa
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit import RDLogger

RDLogger.DisableLog('rdApp.*')

class NMRexpManager:
    """
    High-performance manager for the NMRexp dataset (3.37M experimental spectra).
    Supports fast nucleus filtering, record browsing, SMILES searching,
    and structured spectrum extraction.
    """
    
    DEFAULT_PARQUET_NAME = "NMRexp_10to24_1_1004.parquet"
    CACHE_INDEX_NAME = "nuclei_index.npz"
    UNIQUE_SMILES_INDEX_NAME = "unique_smiles_index.parquet"

    NUCLEUS_LABELS = {
        "all": "Alle Kerne",
        "1H": "1H NMR",
        "13C": "13C NMR",
        "19F": "19F NMR",
        "31P": "31P NMR",
        "11B": "11B NMR",
        "29Si": "29Si NMR"
    }

    NUCLEUS_COLORS = {
        "1H": "#10b981",    # Emerald green
        "13C": "#3b82f6",   # Blue
        "19F": "#8b5cf6",   # Purple
        "31P": "#f59e0b",   # Amber / Orange
        "11B": "#ef4444",   # Red
        "29Si": "#06b6d4",  # Cyan / Teal
        "other": "#64748b"  # Slate
    }

    def __init__(self, parquet_path=None):
        if parquet_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            parquet_path = os.path.join(base_dir, "nmr_exp", self.DEFAULT_PARQUET_NAME)
        
        self.parquet_path = os.path.abspath(parquet_path)
        self.cache_index_path = os.path.join(os.path.dirname(self.parquet_path), self.CACHE_INDEX_NAME)
        self.unique_smiles_index_path = os.path.join(os.path.dirname(self.parquet_path), self.UNIQUE_SMILES_INDEX_NAME)
        
        self._parquet_file = None
        self._total_rows = 0
        self._nuclei_indices = {}
        self._cached_smiles_col = None

        if os.path.exists(self.parquet_path):
            self._init_parquet()

    def is_available(self):
        return os.path.exists(self.parquet_path)

    def _init_parquet(self):
        self._parquet_file = pq.ParquetFile(self.parquet_path)
        self._total_rows = self._parquet_file.metadata.num_rows
        self._load_or_build_index()

    def _load_or_build_index(self):
        """Loads cached nucleus index or computes it if missing."""
        if os.path.exists(self.cache_index_path):
            try:
                data = np.load(self.cache_index_path)
                self._nuclei_indices = {
                    "1H": data["idx_1H"],
                    "13C": data["idx_13C"],
                    "19F": data["idx_19F"],
                    "31P": data["idx_31P"],
                    "11B": data["idx_11B"],
                    "29Si": data["idx_29Si"],
                }
                return
            except Exception as e:
                print(f"[NMRexpManager] Warnung beim Laden des Index-Caches: {e}")

        # Compute index from parquet
        self._build_index()

    def _build_index(self):
        """Builds and caches the nucleus index arrays."""
        if not self._parquet_file:
            return

        types_arr = self._parquet_file.read(columns=['NMR_type'])['NMR_type'].to_numpy(zero_copy_only=False)

        idx_1h = np.where(types_arr == '1H NMR')[0].astype(np.int32)
        idx_13c = np.where(types_arr == '13C NMR')[0].astype(np.int32)
        idx_19f = np.where(types_arr == '19F NMR')[0].astype(np.int32)
        idx_31p = np.where(
            (types_arr == '31P NMR') | (types_arr == 'P NMR') | (types_arr == '{1H}31P NMR')
        )[0].astype(np.int32)
        idx_11b = np.where(
            (types_arr == '11B NMR') | (types_arr == 'B NMR') | (types_arr == '10B NMR')
        )[0].astype(np.int32)
        idx_29si = np.where(
            (types_arr == '29Si NMR') | (types_arr == 'Si NMR')
        )[0].astype(np.int32)

        self._nuclei_indices = {
            "1H": idx_1h,
            "13C": idx_13c,
            "19F": idx_19f,
            "31P": idx_31p,
            "11B": idx_11b,
            "29Si": idx_29si,
        }

        try:
            np.savez_compressed(
                self.cache_index_path,
                idx_1H=idx_1h,
                idx_13C=idx_13c,
                idx_19F=idx_19f,
                idx_31P=idx_31p,
                idx_11B=idx_11b,
                idx_29Si=idx_29si
            )
        except Exception as e:
            print(f"[NMRexpManager] Warnung beim Speichern des Index-Caches: {e}")

    def get_stats(self):
        """Returns overview statistics of records per nucleus."""
        stats = {
            "total": self._total_rows,
            "1H": len(self._nuclei_indices.get("1H", [])),
            "13C": len(self._nuclei_indices.get("13C", [])),
            "19F": len(self._nuclei_indices.get("19F", [])),
            "31P": len(self._nuclei_indices.get("31P", [])),
            "11B": len(self._nuclei_indices.get("11B", [])),
            "29Si": len(self._nuclei_indices.get("29Si", []))
        }
        return stats

    def get_count_for_nucleus(self, nucleus_key):
        """Returns count of records for a given nucleus filter."""
        if nucleus_key == "all":
            return self._total_rows
        return len(self._nuclei_indices.get(nucleus_key, []))

    def get_row_index_for_record(self, nucleus_key, record_number):
        """
        Translates a 0-based record number within a nucleus filter to the absolute row index.
        """
        if nucleus_key == "all":
            if 0 <= record_number < self._total_rows:
                return record_number
            return None

        indices = self._nuclei_indices.get(nucleus_key)
        if indices is not None and 0 <= record_number < len(indices):
            return int(indices[record_number])
        return None

    def get_record_by_row_index(self, row_idx):
        """
        Fetches the complete formatted record for a specific parquet row index.
        """
        if not self._parquet_file or row_idx < 0 or row_idx >= self._total_rows:
            return None

        cols = [
            'Filename', 'SMILES', 'Page_in_file_mol', 'Page_in_file_para',
            'NMR_type', 'NMR_frequency', 'NMR_solvent', 'NMR_shift_text',
            'NMR_note', 'NMR_processed', 'Atom_number', 'Atom_number_diff_env'
        ]

        # Calculate Row Group
        rg_size = 1048576
        rg_idx = row_idx // rg_size
        offset_in_rg = row_idx % rg_size

        try:
            tbl = self._parquet_file.read_row_group(rg_idx, columns=cols).slice(offset_in_rg, 1)
            row_dict = {col: tbl[col][0].as_py() for col in cols}
            return self._format_record(row_dict, row_idx)
        except Exception as e:
            print(f"[NMRexpManager] Fehler beim Lesen von Zeile {row_idx}: {e}")
            return None

    def _format_record(self, raw, row_idx, highlight_atoms=None, highlight_bonds=None):
        """Formats raw parquet record dictionary into a rich data dictionary."""
        smiles = raw.get('SMILES', '')
        svg_content, mol_props = self.draw_mol_svg(
            smiles,
            highlight_atoms=highlight_atoms,
            highlight_bonds=highlight_bonds
        )

        filename = raw.get('Filename', '')
        doi_url = self.format_doi_url(filename)

        nmr_type = raw.get('NMR_type', 'Unbekannt')
        norm_type = self.normalize_nucleus_type(nmr_type)
        color = self.NUCLEUS_COLORS.get(norm_type, self.NUCLEUS_COLORS["other"])

        parsed_spectrum = self.parse_spectrum(nmr_type, raw.get('NMR_processed'), raw.get('NMR_shift_text'))

        record = {
            "row_index": row_idx,
            "filename": filename,
            "doi_url": doi_url,
            "smiles": smiles,
            "svg": svg_content,
            "formula": mol_props.get("formula", "") if isinstance(mol_props, dict) else "",
            "mw": mol_props.get("mw", "") if isinstance(mol_props, dict) else "",
            "page_mol": raw.get('Page_in_file_mol'),
            "page_para": raw.get('Page_in_file_para'),
            "nmr_type": nmr_type,
            "nucleus_key": norm_type,
            "nucleus_color": color,
            "frequency": raw.get('NMR_frequency') or 'Nicht angegeben',
            "solvent": raw.get('NMR_solvent') or 'Nicht angegeben',
            "shift_text": raw.get('NMR_shift_text') or '',
            "note": raw.get('NMR_note') or '',
            "atom_number": raw.get('Atom_number'),
            "atom_number_diff_env": raw.get('Atom_number_diff_env'),
            "spectrum": parsed_spectrum
        }
        return record

    @staticmethod
    def normalize_nucleus_type(nmr_type):
        """Categorizes raw NMR_type string into standard keys (1H, 13C, 19F, 31P, 11B, 29Si)."""
        if not nmr_type:
            return "other"
        if "1H" in nmr_type:
            return "1H"
        if "13C" in nmr_type:
            return "13C"
        if "19F" in nmr_type:
            return "19F"
        if "31P" in nmr_type or "P NMR" in nmr_type:
            return "31P"
        if "11B" in nmr_type or "10B" in nmr_type or "B NMR" in nmr_type:
            return "11B"
        if "29Si" in nmr_type or "Si NMR" in nmr_type:
            return "29Si"
        return "other"

    @staticmethod
    def format_doi_url(filename):
        """Converts Filename (e.g. 10.1021_acs.orglett.3c00718) to official DOI URL."""
        if not filename:
            return None
        parts = filename.split('_', 1)
        if len(parts) == 2 and parts[0].startswith('10.'):
            doi = f"{parts[0]}/{parts[1]}"
            return f"https://doi.org/{doi}"
        return f"https://doi.org/{filename}"

    @classmethod
    def parse_spectrum(cls, nmr_type, proc_str, shift_text=""):
        """
        Parses NMR_processed string into a structured list of peak entries.
        """
        if not proc_str:
            return []
        
        try:
            data = ast.literal_eval(proc_str)
            if not isinstance(data, list):
                return []
        except Exception:
            return []

        is_1h = "1H" in (nmr_type or "")
        rows = []

        if is_1h:
            for item in data:
                if isinstance(item, (tuple, list)) and len(item) >= 5:
                    mult, j_vals, h_count, max_s, min_s = item[0], item[1], item[2], item[3], item[4]
                    
                    if max_s is not None and min_s is not None:
                        if abs(max_s - min_s) < 0.005:
                            shift_display = f"{max_s:.2f}"
                        else:
                            shift_display = f"{min_s:.2f} – {max_s:.2f}"
                    elif max_s is not None:
                        shift_display = f"{max_s:.2f}"
                    elif min_s is not None:
                        shift_display = f"{min_s:.2f}"
                    else:
                        shift_display = "-"

                    if isinstance(j_vals, list) and j_vals:
                        j_str = ", ".join(str(j) for j in j_vals)
                    elif j_vals:
                        j_str = str(j_vals)
                    else:
                        j_str = "-"

                    rows.append({
                        "shift": shift_display,
                        "multiplicity": str(mult) if mult else "-",
                        "j_coupling": j_str,
                        "integral": str(h_count) if h_count else "-"
                    })
        else:
            for item in data:
                if isinstance(item, (tuple, list)) and len(item) >= 3:
                    shift, mult, j_val = item[0], item[1], item[2]
                    
                    try:
                        if isinstance(shift, (list, tuple)):
                            if len(shift) >= 2 and shift[0] is not None and shift[1] is not None:
                                s_min, s_max = float(shift[0]), float(shift[1])
                                if abs(s_max - s_min) < 0.005:
                                    shift_display = f"{s_max:.2f}"
                                else:
                                    shift_display = f"{s_min:.2f} – {s_max:.2f}"
                            elif len(shift) == 1 and shift[0] is not None:
                                shift_display = f"{float(shift[0]):.2f}"
                            else:
                                shift_display = "-"
                        elif shift is not None:
                            shift_display = f"{float(shift):.2f}"
                        else:
                            shift_display = "-"
                    except Exception:
                        shift_display = str(shift) if shift is not None else "-"

                    mult_display = str(mult) if mult else "-"

                    if isinstance(j_val, (list, tuple)):
                        j_display = ", ".join(str(j) if 'Hz' in str(j) else f"{j} Hz" for j in j_val if j is not None)
                        if not j_display:
                            j_display = "-"
                    elif j_val is not None:
                        try:
                            j_display = f"{float(j_val):.1f} Hz"
                        except Exception:
                            j_str = str(j_val)
                            j_display = j_str if 'Hz' in j_str else f"{j_str} Hz"
                    else:
                        j_display = "-"

                    rows.append({
                        "shift": shift_display,
                        "multiplicity": mult_display,
                        "j_coupling": j_display,
                        "integral": "-"
                    })

        return rows

    @classmethod
    def draw_mol_svg(cls, smiles, width=420, height=320, highlight_atoms=None, highlight_bonds=None):
        """Draws 2D molecule as clean SVG and extracts formula and weight, with optional substructure highlighting."""
        if not smiles:
            return "<p>Keine Struktur angegeben</p>", {}
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return "<p>Ungültiger SMILES-Code</p>", {}

            formula = rdMolDescriptors.CalcMolFormula(mol)
            mw = Descriptors.MolWt(mol)

            clean_mol = Chem.RemoveHs(mol)
            for i, atom in enumerate(clean_mol.GetAtoms()):
                atom.SetProp("atomNote", str(i + 1))
            AllChem.Compute2DCoords(clean_mol)
            drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
            opts = drawer.drawOptions()
            opts.addAtomIndices = False
            opts.annotationFontScale = 0.65
            opts.addStereoAnnotation = True
            if highlight_atoms or highlight_bonds:
                opts.setHighlightColour((0.22, 0.74, 0.97, 0.65))
                drawer.DrawMolecule(
                    clean_mol,
                    highlightAtoms=list(highlight_atoms) if highlight_atoms else [],
                    highlightBonds=list(highlight_bonds) if highlight_bonds else []
                )
            else:
                drawer.DrawMolecule(clean_mol)
            drawer.FinishDrawing()
            svg = drawer.GetDrawingText()
            return svg, {"formula": formula, "mw": f"{mw:.2f}"}
        except Exception as e:
            return f"<p>Fehler beim Zeichnen: {e}</p>", {}

    def search_by_smiles(self, query_smiles, nucleus_filter="all"):
        """
        Searches the NMRexp database for matching molecules using multiple SMILES variants.
        Optionally filters results by nucleus (1H, 13C, 19F, etc.).
        Returns list of matching formatted records.
        """
        if not self._parquet_file or not query_smiles:
            return []

        try:
            mol = Chem.MolFromSmiles(query_smiles)
            if mol is None:
                return []
        except Exception:
            return []

        candidates = set()
        candidates.add(query_smiles)
        try:
            candidates.add(Chem.MolToSmiles(mol, canonical=True))
            candidates.add(Chem.MolToSmiles(mol, isomericSmiles=True, canonical=True))
            candidates.add(Chem.MolToSmiles(mol, isomericSmiles=False, canonical=True))
            no_h = Chem.RemoveHs(mol)
            candidates.add(Chem.MolToSmiles(no_h, canonical=True))
            candidates.add(Chem.MolToSmiles(no_h, isomericSmiles=True, canonical=True))
            candidates.add(Chem.MolToSmiles(no_h, isomericSmiles=False, canonical=True))
        except Exception:
            pass

        candidate_list = [s for s in candidates if s]
        
        try:
            tbl = pq.read_table(
                self.parquet_path,
                filters=[('SMILES', 'in', candidate_list)]
            )
            
            if len(tbl) == 0:
                return []

            results = []
            cols = [
                'Filename', 'SMILES', 'Page_in_file_mol', 'Page_in_file_para',
                'NMR_type', 'NMR_frequency', 'NMR_solvent', 'NMR_shift_text',
                'NMR_note', 'NMR_processed', 'Atom_number', 'Atom_number_diff_env'
            ]
            
            pydict = tbl.select(cols).to_pydict()
            num_rows = len(tbl)

            for i in range(num_rows):
                row_raw = {c: pydict[c][i] for c in cols}
                record = self._format_record(row_raw, row_idx=-1)
                if nucleus_filter != "all" and record.get("nucleus_key") != nucleus_filter:
                    continue
                record["source_db"] = "NMRexp"
                results.append(record)

            return results
        except Exception as e:
            print(f"[NMRexpManager] Fehler bei SMILES-Suche: {e}")
            return []

    def search_substructure(self, query_smiles, nucleus_filter="all", max_results=100, progress_callback=None, cancel_callback=None):
        """
        Searches the NMRexp database for substructure matches.
        Highlights matched substructure on 2D SVG cards.
        Supports nucleus filtering (1H, 13C, 19F, etc.) and max hit limiting.
        """
        if not self._parquet_file or not query_smiles:
            return []

        try:
            query_mol = Chem.MolFromSmiles(query_smiles)
            if query_mol is None:
                try:
                    query_mol = Chem.MolFromSmarts(query_smiles)
                except Exception:
                    query_mol = None
            if query_mol is None:
                return []
            clean_query = Chem.RemoveHs(query_mol)
        except Exception as e:
            print(f"[NMRexpManager] Fehler beim Parsen der Substruktur-Anfrage: {e}")
            return []

        # Heteroatom pre-screening set
        heteros = [atom.GetSymbol() for atom in clean_query.GetAtoms() if atom.GetSymbol() not in ('C', 'H')]

        # Fast candidate SMILES retrieval from unique_smiles_index.parquet if available
        candidate_smiles = None
        if os.path.exists(self.unique_smiles_index_path):
            try:
                if nucleus_filter != "all":
                    col_name = f"is_{nucleus_filter}"
                    tbl = pq.read_table(
                        self.unique_smiles_index_path,
                        filters=[(col_name, '=', True)],
                        columns=['SMILES']
                    )
                else:
                    tbl = pq.read_table(
                        self.unique_smiles_index_path,
                        columns=['SMILES']
                    )
                candidate_smiles = tbl['SMILES'].to_numpy(zero_copy_only=False)
            except Exception as e:
                print(f"[NMRexpManager] Hinweis: Fehler beim Laden von unique_smiles_index.parquet: {e}")
                candidate_smiles = None

        if candidate_smiles is None:
            # Fallback to reading and caching full SMILES column from parquet
            if self._cached_smiles_col is None:
                if progress_callback:
                    progress_callback("Lade SMILES-Index für NMRexp...")
                try:
                    self._cached_smiles_col = self._parquet_file.read(columns=['SMILES'])['SMILES'].to_numpy(zero_copy_only=False)
                except Exception as e:
                    print(f"[NMRexpManager] Fehler beim Laden der SMILES-Spalte: {e}")
                    return []

            if nucleus_filter != "all":
                indices = self._nuclei_indices.get(nucleus_filter)
                if indices is None or len(indices) == 0:
                    return []
                candidate_smiles = np.unique(self._cached_smiles_col[indices])
            else:
                candidate_smiles = np.unique(self._cached_smiles_col)

        matched_smiles = []
        matched_atoms_map = {}
        matched_bonds_map = {}

        total_candidates = len(candidate_smiles)
        last_progress_time = time.time()

        for idx, s in enumerate(candidate_smiles):
            if cancel_callback and cancel_callback():
                break

            if not s:
                continue

            if idx % 10000 == 0 and progress_callback and (time.time() - last_progress_time > 0.4):
                progress_callback(f"Substruktursuche: {idx:,} / {total_candidates:,} geprüft ({len(matched_smiles)} Treffer)...")
                last_progress_time = time.time()

            # Fast heteroatom pre-filter
            if heteros and not all(h in s for h in heteros):
                continue

            try:
                m = Chem.MolFromSmiles(s)
                if m is None:
                    continue
                clean_m = Chem.RemoveHs(m)
                match = clean_m.GetSubstructMatch(clean_query)
                if match:
                    matched_smiles.append(s)
                    matched_atoms_map[s] = list(match)

                    # Map matched bonds
                    bonds = []
                    for b in clean_query.GetBonds():
                        b1 = match[b.GetBeginAtomIdx()]
                        b2 = match[b.GetEndAtomIdx()]
                        bond_obj = clean_m.GetBondBetweenAtoms(b1, b2)
                        if bond_obj:
                            bonds.append(bond_obj.GetIdx())
                    matched_bonds_map[s] = bonds

                    if max_results and max_results > 0 and len(matched_smiles) >= max_results:
                        break
            except Exception:
                continue

        if not matched_smiles:
            return []

        if progress_callback:
            progress_callback(f"Lade {len(matched_smiles)} passende Spektren...")

        cols = [
            'Filename', 'SMILES', 'Page_in_file_mol', 'Page_in_file_para',
            'NMR_type', 'NMR_frequency', 'NMR_solvent', 'NMR_shift_text',
            'NMR_note', 'NMR_processed', 'Atom_number', 'Atom_number_diff_env'
        ]

        try:
            tbl = pq.read_table(
                self.parquet_path,
                filters=[('SMILES', 'in', matched_smiles)]
            )

            pydict = tbl.select(cols).to_pydict()
            num_rows = len(tbl)
            results = []

            for i in range(num_rows):
                if cancel_callback and cancel_callback():
                    break
                row_raw = {c: pydict[c][i] for c in cols}
                s = row_raw.get('SMILES', '')
                record = self._format_record(
                    row_raw,
                    row_idx=-1,
                    highlight_atoms=matched_atoms_map.get(s),
                    highlight_bonds=matched_bonds_map.get(s)
                )
                if nucleus_filter != "all" and record.get("nucleus_key") != nucleus_filter:
                    continue
                record["source_db"] = "NMRexp"
                results.append(record)
                if max_results and max_results > 0 and len(results) >= max_results:
                    break

            return results
        except Exception as e:
            print(f"[NMRexpManager] Fehler beim Laden der Substruktur-Ergebnisse: {e}")
            return []

    def search_similarity(self, query_smiles, min_similarity=0.7, nucleus_filter="all", max_results=100, progress_callback=None, cancel_callback=None):
        """
        Searches the NMRexp database for molecules similar to query_smiles
        using Morgan Fingerprints (ECFP4, radius=2, 2048 bits) and Tanimoto coefficient.
        Returns sorted list of records by descending similarity score.
        """
        if not self._parquet_file or not query_smiles:
            return []

        try:
            from rdkit import DataStructs
            from rdkit.Chem import rdFingerprintGenerator
            gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
            query_mol = Chem.MolFromSmiles(query_smiles)
            if query_mol is None:
                return []
            query_fp = gen.GetFingerprint(query_mol)
        except Exception as e:
            print(f"[NMRexpManager] Fehler beim Generieren des Anfrage-Fingerprints: {e}")
            return []

        # Retrieve unique candidate SMILES
        candidate_smiles = None
        if os.path.exists(self.unique_smiles_index_path):
            try:
                if nucleus_filter != "all":
                    col_name = f"is_{nucleus_filter}"
                    tbl = pq.read_table(
                        self.unique_smiles_index_path,
                        filters=[(col_name, '=', True)],
                        columns=['SMILES']
                    )
                else:
                    tbl = pq.read_table(
                        self.unique_smiles_index_path,
                        columns=['SMILES']
                    )
                candidate_smiles = tbl['SMILES'].to_numpy(zero_copy_only=False)
            except Exception as e:
                candidate_smiles = None

        if candidate_smiles is None:
            if self._cached_smiles_col is None:
                if progress_callback:
                    progress_callback("Lade SMILES-Index für Ähnlichkeitssuche...")
                try:
                    self._cached_smiles_col = self._parquet_file.read(columns=['SMILES'])['SMILES'].to_numpy(zero_copy_only=False)
                except Exception as e:
                    return []
            if nucleus_filter != "all":
                indices = self._nuclei_indices.get(nucleus_filter)
                if indices is None or len(indices) == 0:
                    return []
                candidate_smiles = np.unique(self._cached_smiles_col[indices])
            else:
                candidate_smiles = np.unique(self._cached_smiles_col)

        scored_smiles = [] # tuples: (similarity, smiles)
        total_candidates = len(candidate_smiles)
        last_progress_time = time.time()

        for idx, s in enumerate(candidate_smiles):
            if cancel_callback and cancel_callback():
                break
            if not s:
                continue

            if idx % 10000 == 0 and progress_callback and (time.time() - last_progress_time > 0.4):
                progress_callback(f"Ähnlichkeitssuche: {idx:,} / {total_candidates:,} geprüft ({len(scored_smiles)} Treffer)...")
                last_progress_time = time.time()

            try:
                m = Chem.MolFromSmiles(s)
                if m is None:
                    continue
                fp = gen.GetFingerprint(m)
                sim = DataStructs.TanimotoSimilarity(query_fp, fp)
                if sim >= min_similarity:
                    scored_smiles.append((sim, s))
            except Exception:
                continue

        if not scored_smiles:
            return []

        # Sort by similarity descending
        scored_smiles.sort(key=lambda x: x[0], reverse=True)
        if max_results and max_results > 0:
            scored_smiles = scored_smiles[:max_results]

        sim_map = {s: score for score, s in scored_smiles}
        top_smiles = list(sim_map.keys())

        if progress_callback:
            progress_callback(f"Lade {len(top_smiles)} ähnliche Spektren...")

        cols = [
            'Filename', 'SMILES', 'Page_in_file_mol', 'Page_in_file_para',
            'NMR_type', 'NMR_frequency', 'NMR_solvent', 'NMR_shift_text',
            'NMR_note', 'NMR_processed', 'Atom_number', 'Atom_number_diff_env'
        ]

        try:
            tbl = pq.read_table(
                self.parquet_path,
                filters=[('SMILES', 'in', top_smiles)]
            )
            pydict = tbl.select(cols).to_pydict()
            num_rows = len(tbl)
            results = []

            for i in range(num_rows):
                if cancel_callback and cancel_callback():
                    break
                row_raw = {c: pydict[c][i] for c in cols}
                s = row_raw.get('SMILES', '')
                record = self._format_record(row_raw, row_idx=-1)
                if nucleus_filter != "all" and record.get("nucleus_key") != nucleus_filter:
                    continue
                record["source_db"] = "NMRexp"
                sim_val = sim_map.get(s, 0.0)
                record["similarity"] = round(sim_val * 100, 1)
                results.append(record)

            # Re-sort results by similarity descending
            results.sort(key=lambda r: r.get("similarity", 0.0), reverse=True)
            if max_results and max_results > 0:
                results = results[:max_results]

            return results
        except Exception as e:
            print(f"[NMRexpManager] Fehler beim Laden der Ähnlichkeitsergebnisse: {e}")
            return []


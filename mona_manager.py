"""
mona_manager.py
===============
High-Performance Data Manager & Search Engine for MassBank of North America (MoNa).

Features:
1. Automated download & extraction of MoNa spectral libraries via REST API.
2. Streaming MSP parser for high-speed conversion to Apache Parquet.
3. Pre-indexed structures:
   - mona_spectra.parquet: Complete metadata and peak tables.
   - unique_smiles_index.parquet: Pre-filtered unique SMILES for rapid substructure matching.
   - mz_index.npz: Sorted precursor m/z index for O(log N) binary search mass queries.
4. Multimodal Search Engine:
   - Exact Structure Search (SMILES / InChIKey)
   - Chemical Substructure Search with RDKit Cyan Highlight Indices
   - Precursor m/z Search with flexible ppm / Da tolerances
   - Ion Mode & Instrument Filters
5. Spectrum Retrieval & Neutral-Loss Extraction for MS Viewer
"""

from __future__ import annotations

import os
import re
import io
import time
import zipfile
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from rdkit import Chem
from rdkit.Chem import AllChem

# Directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONA_DIR = os.path.join(BASE_DIR, "mona")
DOWNLOADS_DIR = os.path.join(MONA_DIR, "downloads")
CACHE_DIR = os.path.join(MONA_DIR, ".cache")

PARQUET_FILE = os.path.join(MONA_DIR, "mona_spectra.parquet")
SMILES_INDEX_FILE = os.path.join(MONA_DIR, "unique_smiles_index.parquet")
MZ_INDEX_FILE = os.path.join(MONA_DIR, "mz_index.npz")

PRESETS = {
    "starter": {
        "title": "Starter Pack (GC-MS EI + Agilent QTOF)",
        "description": "Kompaktes Paket für schnellen Start: ~44.700 Spektren, ~50 MB Download",
        "files": [
            {
                "name": "MoNA-export-GC-MS_Spectra-msp.zip",
                "id": "a09f9652-c7bc-48b2-9dd9-0dc4343bb360",
                "type": "GC-MS"
            },
            {
                "name": "MoNA-export-All_LC-MS-MS_Agilent_QTOF-msp.zip",
                "id": "d35d2f3e-8a38-4e73-8b8d-ebd90a8cef81",
                "type": "LC-MS/MS"
            }
        ]
    },
    "orbitrap": {
        "title": "High-Res Orbitrap LC-MS/MS",
        "description": "Hochauflösende Orbitrap-Tandem-Spektren: ~160.000 Spektren, ~207 MB Download",
        "files": [
            {
                "name": "MoNA-export-All_LC-MS-MS_Orbitrap-msp.zip",
                "id": "a2f5bc9e-0542-429f-b042-5ff77fbffea1",
                "type": "LC-MS/MS"
            }
        ]
    },
    "experimental": {
        "title": "All Experimental Spectra",
        "description": "Alle experimentellen GC-MS & LC-MS/MS Spektren: ~1,75 Mio. Spektren, ~3,07 GB Download",
        "files": [
            {
                "name": "MoNA-export-Experimental_Spectra-msp.zip",
                "id": "ab8dc037-14e9-416f-a663-8607d16f3d39",
                "type": "All-Exp"
            }
        ]
    },
    "all_spectra": {
        "title": "All Spectra (Exp + In-Silico)",
        "description": "Vollständiger Datenbestand inkl. LipidBlast: ~3,60 Mio. Spektren, ~3,55 GB Download",
        "files": [
            {
                "name": "MoNA-export-All_Spectra-msp.zip",
                "id": "03d5a22c-c1e1-4101-ac70-9a4eae437ef5",
                "type": "All-Spectra"
            }
        ]
    }
}


class MonaManager:
    """Singleton Manager for the MoNa Mass Spectrometry database."""

    _instance: Optional[MonaManager] = None

    def __new__(cls) -> MonaManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        os.makedirs(MONA_DIR, exist_ok=True)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

        self.parquet_table: Optional[pa.Table] = None
        self.smiles_index: Optional[pa.Table] = None
        self.mz_array: Optional[np.ndarray] = None
        self.mz_indices: Optional[np.ndarray] = None
        self.total_records: int = 0

        self.reload_database()

    def is_database_available(self) -> bool:
        """Checks if the compiled Parquet database is available."""
        return os.path.exists(PARQUET_FILE) and os.path.getsize(PARQUET_FILE) > 1024

    def reload_database(self) -> bool:
        """Loads or reloads the compiled database and indices into memory."""
        if not self.is_database_available():
            self.total_records = 0
            return False

        try:
            # Memory-map the parquet file
            self.parquet_table = pq.read_table(PARQUET_FILE, memory_map=True)
            self.total_records = self.parquet_table.num_rows

            if os.path.exists(SMILES_INDEX_FILE):
                self.smiles_index = pq.read_table(SMILES_INDEX_FILE, memory_map=True)

            if os.path.exists(MZ_INDEX_FILE):
                data = np.load(MZ_INDEX_FILE)
                self.mz_array = data["mz"]
                self.mz_indices = data["indices"]

            return True
        except Exception as e:
            print(f"[MonaManager] Error loading database: {e}")
            return False

    def build_database_from_downloads(self, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> int:
        """
        Parses all .msp.zip archives found in the downloads directory
        and compiles mona_spectra.parquet, unique_smiles_index.parquet, and mz_index.npz.
        Uses streaming Parquet batches and in-memory caches to handle > 1.75M records seamlessly.
        """
        zip_files = [
            os.path.join(DOWNLOADS_DIR, f)
            for f in os.listdir(DOWNLOADS_DIR)
            if f.endswith(".zip") and ("msp" in f.lower() or "mona" in f.lower())
        ]

        if not zip_files:
            raise FileNotFoundError(f"Keine MoNa .zip-Dateien in {DOWNLOADS_DIR} gefunden.")

        # If Experimental_Spectra is present, prioritize it and avoid re-reading smaller overlapping archives
        has_all_exp = any("experimental" in os.path.basename(z).lower() for z in zip_files)
        if has_all_exp:
            zip_files = [z for z in zip_files if "experimental" in os.path.basename(z).lower()]

        schema = pa.schema([
            ("id", pa.string()),
            ("name", pa.string()),
            ("inchikey", pa.string()),
            ("smiles", pa.string()),
            ("formula", pa.string()),
            ("exact_mass", pa.float32()),
            ("precursor_mz", pa.float32()),
            ("adduct", pa.string()),
            ("ion_mode", pa.string()),
            ("ms_level", pa.int8()),
            ("instrument_type", pa.string()),
            ("instrument", pa.string()),
            ("collision_energy", pa.string()),
            ("retention_time", pa.float32()),
            ("peaks_count", pa.int32()),
            ("peaks", pa.string()),
        ])

        from collections import defaultdict
        smiles_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "inchikey": "",
            "has_gcms": False,
            "has_lcms": False
        })
        smiles_canon_cache: Dict[str, Tuple[str, str]] = {}
        mz_pairs: List[Tuple[float, int]] = []
        seen_ids = set()

        BATCH_SIZE = 25000
        batch: Dict[str, list] = {col: [] for col in schema.names}
        total_parsed = 0
        global_row_idx = 0

        temp_parquet = PARQUET_FILE + ".tmp"
        if os.path.exists(temp_parquet):
            try:
                os.remove(temp_parquet)
            except Exception:
                pass

        writer = pq.ParquetWriter(temp_parquet, schema=schema, compression="snappy")

        def flush_batch():
            nonlocal batch
            if not batch["id"]:
                return
            t = pa.Table.from_arrays(
                [pa.array(batch[col], type=schema.field(col).type) for col in schema.names],
                schema=schema
            )
            writer.write_table(t)
            batch = {col: [] for col in schema.names}

        for z_idx, zpath in enumerate(zip_files):
            zname = os.path.basename(zpath)
            if progress_callback:
                progress_callback(f"Lese {zname}...", z_idx, len(zip_files))

            with zipfile.ZipFile(zpath, "r") as zf:
                msp_members = [m for m in zf.namelist() if m.endswith(".msp")]
                if not msp_members:
                    continue

                for member in msp_members:
                    with zf.open(member, "r") as mf:
                        curr: Dict[str, str] = {}
                        peaks_str_list: List[str] = []
                        in_peaks = False

                        for line_b in mf:
                            line = line_b.decode("utf-8", errors="ignore").strip()
                            if not line:
                                if curr and peaks_str_list:
                                    rec = self._normalize_record(curr, peaks_str_list, smiles_canon_cache)
                                    if rec and rec["id"] not in seen_ids:
                                        seen_ids.add(rec["id"])
                                        total_parsed += 1

                                        for col in schema.names:
                                            batch[col].append(rec.get(col))

                                        s = rec["smiles"]
                                        if s:
                                            item = smiles_map[s]
                                            item["count"] += 1
                                            if not item["inchikey"]:
                                                item["inchikey"] = rec["inchikey"]
                                            if rec["ion_mode"] == "EI":
                                                item["has_gcms"] = True
                                            else:
                                                item["has_lcms"] = True

                                        pmz = rec["precursor_mz"]
                                        if pmz > 0.0:
                                            mz_pairs.append((pmz, global_row_idx))

                                        global_row_idx += 1

                                        if len(batch["id"]) >= BATCH_SIZE:
                                            flush_batch()
                                            if progress_callback:
                                                progress_callback(f"{total_parsed:,} Spektren verarbeitet...", z_idx, len(zip_files))

                                curr = {}
                                peaks_str_list = []
                                in_peaks = False
                                continue

                            if line.lower().startswith("num peaks:"):
                                in_peaks = True
                                continue

                            if in_peaks:
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        mz_val = float(parts[0])
                                        int_val = float(parts[1])
                                        peaks_str_list.append(f"{mz_val:.4f}:{int_val:.1f}")
                                    except ValueError:
                                        pass
                            else:
                                c_idx = line.find(":")
                                if c_idx > 0:
                                    k = line[:c_idx].strip().lower()
                                    v = line[c_idx + 1:].strip()
                                    curr[k] = v

                        # Process last record in file
                        if curr and peaks_str_list:
                            rec = self._normalize_record(curr, peaks_str_list, smiles_canon_cache)
                            if rec and rec["id"] not in seen_ids:
                                seen_ids.add(rec["id"])
                                total_parsed += 1
                                for col in schema.names:
                                    batch[col].append(rec.get(col))
                                s = rec["smiles"]
                                if s:
                                    item = smiles_map[s]
                                    item["count"] += 1
                                    if not item["inchikey"]:
                                        item["inchikey"] = rec["inchikey"]
                                    if rec["ion_mode"] == "EI":
                                        item["has_gcms"] = True
                                    else:
                                        item["has_lcms"] = True
                                pmz = rec["precursor_mz"]
                                if pmz > 0.0:
                                    mz_pairs.append((pmz, global_row_idx))
                                global_row_idx += 1

        if total_parsed == 0:
            writer.close()
            if os.path.exists(temp_parquet):
                os.remove(temp_parquet)
            raise ValueError("Keine gültigen Spektrendatensätze in den Archiven gefunden.")

        flush_batch()
        writer.close()

        # Atomic rename temp parquet to PARQUET_FILE
        if os.path.exists(PARQUET_FILE):
            try:
                os.remove(PARQUET_FILE)
            except Exception:
                pass
        os.rename(temp_parquet, PARQUET_FILE)

        # Build unique SMILES index
        if progress_callback:
            progress_callback("Erstelle SMILES-Substrukturindex...", len(zip_files), len(zip_files))
        smiles_list = list(smiles_map.keys())
        counts = [smiles_map[s]["count"] for s in smiles_list]
        inchikeys = [smiles_map[s]["inchikey"] for s in smiles_list]
        has_gcms = [smiles_map[s]["has_gcms"] for s in smiles_list]
        has_lcms = [smiles_map[s]["has_lcms"] for s in smiles_list]

        smi_table = pa.Table.from_arrays([
            pa.array(smiles_list, type=pa.string()),
            pa.array(counts, type=pa.int32()),
            pa.array(inchikeys, type=pa.string()),
            pa.array(has_gcms, type=pa.bool_()),
            pa.array(has_lcms, type=pa.bool_())
        ], names=["smiles", "record_count", "inchikey", "has_gcms", "has_lcms"])
        pq.write_table(smi_table, SMILES_INDEX_FILE, compression="snappy")

        # Build m/z binary search index
        if progress_callback:
            progress_callback("Erstelle Vorläuferion m/z-Index...", len(zip_files), len(zip_files))
        if mz_pairs:
            mz_pairs.sort(key=lambda x: x[0])
            sorted_mz = np.array([p[0] for p in mz_pairs], dtype=np.float32)
            sorted_indices = np.array([p[1] for p in mz_pairs], dtype=np.int32)
        else:
            sorted_mz = np.array([], dtype=np.float32)
            sorted_indices = np.array([], dtype=np.int32)
        np.savez_compressed(MZ_INDEX_FILE, mz=sorted_mz, indices=sorted_indices)

        # Reload newly built database
        self.reload_database()
        return total_parsed

    def _normalize_record(self, raw: Dict[str, str], peaks: List[str],
                          smiles_canon_cache: Optional[Dict[str, Tuple[str, str]]] = None) -> Optional[Dict[str, Any]]:
        """Extracts and normalizes fields from raw MSP key-value dictionary."""
        db_id = raw.get("db#") or raw.get("accession") or raw.get("id") or "MoNA_UNK"
        name = raw.get("name") or "Unbenannt"
        inchikey = raw.get("inchikey") or ""
        formula = raw.get("formula") or ""

        # Extract SMILES from fields or Comments
        smiles = raw.get("smiles") or ""
        comments = raw.get("comments") or ""
        if not smiles and comments:
            m = re.search(r'(?:computed\s+)?SMILES=([^\s"]+)', comments)
            if m:
                smiles = m.group(1).strip()
        smiles = smiles.rstrip(";, \t\r\n\"'")

        if not inchikey and comments:
            m = re.search(r'(?:computed\s+)?InChIKey=([^\s"]+)', comments)
            if m:
                inchikey = m.group(1).strip()

        # Parse numerical properties
        exact_mass = 0.0
        try:
            if "exactmass" in raw:
                exact_mass = float(raw["exactmass"])
            elif "mw" in raw:
                exact_mass = float(raw["mw"])
        except ValueError:
            pass

        precursor_mz = 0.0
        try:
            if "precursormz" in raw:
                precursor_mz = float(raw["precursormz"])
        except ValueError:
            pass

        adduct = raw.get("precursor_type") or raw.get("adduct") or ""
        if not adduct and comments:
            m = re.search(r'ion type=([^\s"]+)', comments)
            if m:
                adduct = m.group(1).strip()

        # Ion mode normalization
        raw_mode = (raw.get("ion_mode") or raw.get("ionmode") or "").upper()
        if raw_mode in ("P", "POS", "POSITIVE"):
            ion_mode = "Positive"
        elif raw_mode in ("N", "NEG", "NEGATIVE"):
            ion_mode = "Negative"
        elif "EI" in (raw.get("instrument_type") or "").upper() or "EI" in (raw.get("instrument") or "").upper():
            ion_mode = "EI"
        else:
            ion_mode = "EI" if precursor_mz == 0.0 else "Positive"

        ms_level = 2
        spec_type = (raw.get("spectrum_type") or "").upper()
        if "MS1" in spec_type:
            ms_level = 1

        inst_type = raw.get("instrument_type") or ""
        inst = raw.get("instrument") or ""
        ce = raw.get("collision_energy") or ""

        ret_time = 0.0
        try:
            if "retention_time" in raw:
                ret_time = float(raw["retention_time"].replace("min", "").strip())
            elif comments:
                m = re.search(r'retention time=([0-9.]+)', comments)
                if m:
                    ret_time = float(m.group(1))
        except ValueError:
            pass

        # Canonicalize SMILES if RDKit is available with memoization cache
        canon_smiles = smiles
        if smiles:
            if smiles_canon_cache is not None and smiles in smiles_canon_cache:
                canon_smiles, cached_ik = smiles_canon_cache[smiles]
                if not inchikey:
                    inchikey = cached_ik
            else:
                try:
                    mol = Chem.MolFromSmiles(smiles)
                    if mol:
                        canon_smiles = Chem.MolToSmiles(mol)
                        if not inchikey:
                            inchikey = Chem.MolToInchiKey(mol)
                        if smiles_canon_cache is not None:
                            smiles_canon_cache[smiles] = (canon_smiles, inchikey)
                    else:
                        if smiles_canon_cache is not None:
                            smiles_canon_cache[smiles] = (smiles, inchikey)
                except Exception:
                    if smiles_canon_cache is not None:
                        smiles_canon_cache[smiles] = (smiles, inchikey)

        return {
            "id": db_id,
            "name": name,
            "inchikey": inchikey,
            "smiles": canon_smiles,
            "formula": formula,
            "exact_mass": float(exact_mass),
            "precursor_mz": float(precursor_mz),
            "adduct": adduct,
            "ion_mode": ion_mode,
            "ms_level": int(ms_level),
            "instrument_type": inst_type,
            "instrument": inst,
            "collision_energy": ce,
            "retention_time": float(ret_time),
            "peaks_count": len(peaks),
            "peaks": " ".join(peaks),
        }

    # -----------------------------------------------------------------------
    # High-Performance Search Capabilities
    # -----------------------------------------------------------------------

    def search_exact(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches for exact matches by Canonical SMILES or InChIKey.
        Returns all matching records in MoNa.
        """
        if not self.is_database_available():
            return []

        # Determine if query is InChIKey or SMILES
        clean_q = query.strip()
        is_inchikey = bool(re.match(r'^[A-Z]{14}-[A-Z]{10}-[A-Z]$', clean_q))

        canon_smiles = ""
        if not is_inchikey:
            mol = Chem.MolFromSmiles(clean_q)
            if mol:
                canon_smiles = Chem.MolToSmiles(mol)
                clean_q = Chem.MolToInchiKey(mol)
                is_inchikey = True

        results: List[Dict[str, Any]] = []
        if is_inchikey:
            # Filter by InChIKey column
            expr = pa.compute.equal(self.parquet_table["inchikey"], clean_q)
            filtered = self.parquet_table.filter(expr)
            for row in filtered.to_pylist():
                results.append(self._format_result_row(row))
        elif canon_smiles:
            expr = pa.compute.equal(self.parquet_table["smiles"], canon_smiles)
            filtered = self.parquet_table.filter(expr)
            for row in filtered.to_pylist():
                results.append(self._format_result_row(row))

        return results

    def search_substructure(
        self,
        query_smiles: str,
        limit: int = 100,
        ion_mode: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, int], bool]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[int]]]:
        """
        Performs substructure search against the MoNa unique SMILES index with RDKit.
        Returns matching records and atom highlight dictionaries.
        """
        if not self.is_database_available() or self.smiles_index is None:
            return [], {}

        query_mol = Chem.MolFromSmiles(query_smiles)
        if not query_mol:
            return [], {}

        # Pre-filter SMILES list
        smiles_col = self.smiles_index["smiles"].to_pylist()
        total_unique = len(smiles_col)

        matched_smiles_set = set()
        matched_highlights: Dict[str, List[int]] = {}

        # Check substructures
        for idx, smi in enumerate(smiles_col):
            if idx % 1000 == 0 and progress_callback:
                if not progress_callback(idx, total_unique, len(matched_smiles_set)):
                    break  # User cancelled

            if not smi or len(smi) < len(query_smiles) // 2:
                continue

            try:
                target_mol = Chem.MolFromSmiles(smi)
                if target_mol and target_mol.HasSubstructMatch(query_mol):
                    matched_smiles_set.add(smi)
                    match_atoms = list(target_mol.GetSubstructMatch(query_mol))
                    matched_highlights[smi] = match_atoms

                    if len(matched_smiles_set) >= limit:
                        break
            except Exception:
                pass

        if not matched_smiles_set:
            return [], {}

        # Fetch records matching the found SMILES
        expr = pa.compute.is_in(self.parquet_table["smiles"], value_set=pa.array(list(matched_smiles_set)))
        if ion_mode and ion_mode != "Alle":
            expr = pa.compute.and_(expr, pa.compute.equal(self.parquet_table["ion_mode"], ion_mode))

        filtered = self.parquet_table.filter(expr)
        results = [self._format_result_row(r) for r in filtered.to_pylist()[:limit]]
        return results, matched_highlights

    def search_precursor_mz(
        self,
        target_mz: float,
        tolerance_ppm: float = 10.0,
        tolerance_da: Optional[float] = None,
        ion_mode: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fast binary interval search on the sorted precursor m/z index.
        Tolerance can be specified in ppm or absolute Da.
        """
        if self.mz_array is None or len(self.mz_array) == 0:
            return []

        if tolerance_da is not None and tolerance_da > 0:
            delta = tolerance_da
        else:
            delta = target_mz * (tolerance_ppm * 1e-6)

        min_mz = target_mz - delta
        max_mz = target_mz + delta

        left_idx = int(np.searchsorted(self.mz_array, min_mz, side="left"))
        right_idx = int(np.searchsorted(self.mz_array, max_mz, side="right"))

        if left_idx >= right_idx:
            return []

        matched_row_indices = self.mz_indices[left_idx:right_idx]

        # Extract rows from parquet table
        # Sort by closest delta m/z
        row_list = []
        for r_idx in matched_row_indices:
            row = self.parquet_table.slice(int(r_idx), 1).to_pylist()[0]
            if ion_mode and ion_mode != "Alle" and row.get("ion_mode") != ion_mode:
                continue
            diff = abs(row.get("precursor_mz", 0.0) - target_mz)
            row["delta_mz"] = diff
            row["delta_ppm"] = (diff / target_mz) * 1e6 if target_mz > 0 else 0.0
            row_list.append(row)

        row_list.sort(key=lambda x: x["delta_mz"])
        return [self._format_result_row(r) for r in row_list[:limit]]

    def get_spectrum(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete spectrum details and parsed (m/z, intensity) peak list by MoNa ID."""
        if not self.is_database_available():
            return None

        expr = pa.compute.equal(self.parquet_table["id"], record_id)
        filtered = self.parquet_table.filter(expr)
        if filtered.num_rows == 0:
            return None

        row = filtered.to_pylist()[0]
        return self._format_result_row(row)

    def _format_result_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Formats a table row dictionary into a rich result structure."""
        # Parse peaks
        raw_peaks = row.get("peaks", "")
        parsed_peaks: List[Tuple[float, float]] = []
        if raw_peaks:
            for item in raw_peaks.split():
                if ":" in item:
                    p = item.split(":")
                    try:
                        parsed_peaks.append((float(p[0]), float(p[1])))
                    except ValueError:
                        pass

        # Normalize intensities to 0-100% relative base peak
        max_int = max((p[1] for p in parsed_peaks), default=1.0)
        norm_peaks = [
            (mz, (intens / max_int) * 100.0)
            for mz, intens in parsed_peaks
        ]

        row["peak_list"] = parsed_peaks
        row["normalized_peaks"] = norm_peaks
        row["source_db"] = "MoNa"
        return row


# Global singleton instance
mona_manager = MonaManager()
MoNaManager = MonaManager


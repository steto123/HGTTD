"""
ir_manager.py — High-Performance Manager for Infrared (IR) Spectra (SQuIRL & NIST)
HGTTD — Hitchhiker's Guide through the Database 🌌🪐
"""

import os
import re
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from rdkit import Chem
from rdkit.Chem import AllChem

IR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir")
IR_PARQUET_PATH = os.path.join(IR_DIR, "ir_spectra.parquet")
IR_SMILES_INDEX_PATH = os.path.join(IR_DIR, "unique_smiles_index.parquet")

# Common IR functional group absorption bands (cm^-1)
IR_CHARACTERISTIC_BANDS = [
    {"label": "O-H (Alkohol, frei)", "min_wn": 3584, "max_wn": 3700, "color": "rgba(56, 189, 248, 0.25)"},
    {"label": "O-H / N-H (Wasserstoffbrücken)", "min_wn": 3200, "max_wn": 3550, "color": "rgba(14, 165, 233, 0.25)"},
    {"label": "O-H (Carbonsäure, breit)", "min_wn": 2500, "max_wn": 3300, "color": "rgba(6, 182, 212, 0.18)"},
    {"label": "C-H (Aromat/Alken)", "min_wn": 3000, "max_wn": 3100, "color": "rgba(168, 85, 247, 0.22)"},
    {"label": "C-H (Aliphat)", "min_wn": 2840, "max_wn": 3000, "color": "rgba(192, 132, 252, 0.20)"},
    {"label": "C≡C / C≡N (Dreifachbindung)", "min_wn": 2100, "max_wn": 2260, "color": "rgba(244, 63, 94, 0.25)"},
    {"label": "C=O (Carbonyl / Ester / Säure)", "min_wn": 1670, "max_wn": 1820, "color": "rgba(239, 68, 68, 0.28)"},
    {"label": "C=C (Alken / Aromat)", "min_wn": 1500, "max_wn": 1680, "color": "rgba(249, 115, 22, 0.22)"},
    {"label": "N-O (Nitro)", "min_wn": 1300, "max_wn": 1550, "color": "rgba(234, 179, 8, 0.20)"},
    {"label": "C-O (Ether / Alkohol / Ester)", "min_wn": 1000, "max_wn": 1300, "color": "rgba(34, 197, 94, 0.22)"},
    {"label": "Fingerprint-Region", "min_wn": 400, "max_wn": 1000, "color": "rgba(100, 116, 139, 0.15)"}
]

class IRManager:
    def __init__(self, parquet_path=IR_PARQUET_PATH, smiles_index_path=IR_SMILES_INDEX_PATH):
        self.parquet_path = parquet_path
        self.smiles_index_path = smiles_index_path
        self.df_index = None
        self._load_smiles_index()

    def is_available(self):
        return os.path.exists(self.parquet_path)

    def _load_smiles_index(self):
        if os.path.exists(self.smiles_index_path):
            try:
                self.df_index = pd.read_parquet(self.smiles_index_path)
            except Exception as e:
                print(f"[IRManager] Index-Ladefehler: {e}")
                self.df_index = None

    def search_exact(self, smiles):
        """Exact structure search via canonical SMILES."""
        if not self.is_available():
            return []
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return []
            can_smi = Chem.MolToSmiles(mol, canonical=True)
            inchikey = Chem.MolToInchiKey(mol) if hasattr(Chem, 'MolToInchiKey') else ""

            # Read table filtered by smiles
            table = pq.read_table(self.parquet_path, filters=[[('smiles', '=', can_smi)]])
            df = table.to_pandas()
            if df.empty and inchikey:
                table = pq.read_table(self.parquet_path, filters=[[('inchikey', '=', inchikey)]])
                df = table.to_pandas()

            results = []
            for _, row in df.iterrows():
                results.append(self._format_hit(row))
            return results
        except Exception as e:
            print(f"[IRManager] Fehler bei Exaktsuche: {e}")
            return []

    def search_substructure(self, query_smiles, max_hits=100):
        """Substructure search across indexed molecules."""
        if not self.is_available() or self.df_index is None:
            return []
        try:
            query_mol = Chem.MolFromSmiles(query_smiles)
            if not query_mol:
                return []

            matched_smiles = []
            for smi in self.df_index['smiles']:
                target_mol = Chem.MolFromSmiles(smi)
                if target_mol and target_mol.HasSubstructMatch(query_mol):
                    matched_smiles.append(smi)
                    if len(matched_smiles) >= max_hits:
                        break

            if not matched_smiles:
                return []

            # Retrieve records
            table = pq.read_table(self.parquet_path, filters=[[('smiles', 'in', matched_smiles)]])
            df = table.to_pandas()
            return [self._format_hit(r) for _, r in df.iterrows()]
        except Exception as e:
            print(f"[IRManager] Substruktursuche Fehler: {e}")
            return []

    def get_spectrum_by_id(self, record_id):
        """Fetch a single record by record ID."""
        if not self.is_available():
            return None
        try:
            table = pq.read_table(self.parquet_path, filters=[[('id', '=', str(record_id))]])
            df = table.to_pandas()
            if not df.empty:
                return self._format_hit(df.iloc[0])
            return None
        except Exception as e:
            print(f"[IRManager] get_spectrum_by_id error: {e}")
            return None

    def synthesize_continuous_ir(self, wavenumbers, intensities, grid_min=400.0, grid_max=4000.0, step=2.0, fwhm=16.0, as_transmittance=True):
        """
        Convolves stick vibrational frequencies with Gaussian/Lorentzian profiles.
        Returns:
            grid_x: ndarray (from 4000 down to 400)
            grid_y: ndarray (Transmittance % 0-100 or Absorbance)
        """
        w_arr = np.array(wavenumbers, dtype=np.float64)
        i_arr = np.array(intensities, dtype=np.float64)

        # Standard IR axis goes from high wavenumber (4000) down to low (400)
        grid_x = np.arange(grid_max, grid_min - step/2, -step, dtype=np.float64)
        if len(w_arr) == 0:
            grid_y = np.full_like(grid_x, 100.0 if as_transmittance else 0.0)
            return grid_x, grid_y

        # Normalize intensities
        max_i = np.max(i_arr) if np.max(i_arr) > 0 else 1.0
        norm_i = i_arr / max_i

        # Lorentzian convolution: A(x) = sum( I_k * (gamma^2 / ((x - x_k)^2 + gamma^2)) )
        gamma = fwhm / 2.0
        gamma2 = gamma ** 2

        # Vectorized outer diff
        # shape: (len(grid_x), len(w_arr))
        diff = grid_x[:, np.newaxis] - w_arr[np.newaxis, :]
        lorentz_matrix = gamma2 / (diff ** 2 + gamma2)
        absorbance = np.dot(lorentz_matrix, norm_i)

        if as_transmittance:
            # Beer-Lambert: T = 10^(-absorbance * factor), scale to % (0-100)
            # scale so maximum peak absorbs to ~10-20% T
            scaled_abs = absorbance * 1.5
            transmittance = 100.0 * np.exp(-scaled_abs)
            return grid_x, np.clip(transmittance, 0.0, 100.0)
        else:
            return grid_x, absorbance

    def _format_hit(self, row):
        # Extract wavenumbers and intensities
        wn = row.get('wavenumbers')
        intens = row.get('intensities')
        if isinstance(wn, str):
            try: wn = json.loads(wn)
            except: wn = []
        elif isinstance(wn, np.ndarray):
            wn = wn.tolist()

        if isinstance(intens, str):
            try: intens = json.loads(intens)
            except: intens = []
        elif isinstance(intens, np.ndarray):
            intens = intens.tolist()

        return {
            "id": str(row.get("id", "")),
            "source": str(row.get("source", "IR")),
            "source_type": str(row.get("source_type", "experimental")),
            "name": str(row.get("name", "Unknown Molecule")),
            "formula": str(row.get("formula", "")),
            "mw": float(row.get("mw", 0.0)),
            "smiles": str(row.get("smiles", "")),
            "inchikey": str(row.get("inchikey", "")),
            "cas": str(row.get("cas", "")),
            "state": str(row.get("state", "")),
            "wavenumbers": wn or [],
            "intensities": intens or [],
            "n_peaks": len(wn) if wn else 0,
            "theory_level": str(row.get("theory_level", "")),
            "db_source": "IR"
        }

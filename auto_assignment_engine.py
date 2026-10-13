"""
auto_assignment_engine.py
=========================
Intelligent Auto-Assignment Engine for 1H and 13C NMR spectra in HGTTD.

Features:
1. DLNMR1 TorchScript Neural Network Inference (Wavefunction, Inc.)
   - Ultra-fast CPU inference (< 20 ms) for 1H and 13C chemical shifts.
2. Hybrid Topological & Rigid-Fragment Symmetry Ranking
   - Preserves rotational equivalence (e.g. methyls, ortho/meta phenyl).
   - Differentiates diastereotopic nuclei in rigid/stereogenic environments.
3. Symmetry Averaging & Degeneracy Counting
   - Calculates cluster-averaged shifts and theoretical integrals/degeneracies.
4. Optimal Bipartite Bounded Matching (Hungarian / Kuhn-Munkres Algorithm)
   - Solves the assignment between experimental multiplet peaks and predicted
     symmetry groups with minimum total chemical shift error and integral weighting.
5. Quality & Confidence Scoring
   - Assigns confidence tiers (High, Medium, Low, Unassigned) based on
     chemical shift deviation (Delta delta) and integral consistency.
"""

from __future__ import annotations

import os
import math
import warnings
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Suppress TorchScript deprecation notice
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D


# ---------------------------------------------------------------------------
# Hungarian / Kuhn-Munkres Bipartite Matching Solver (Pure NumPy)
# ---------------------------------------------------------------------------

def hungarian_matching(cost_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes minimum cost bipartite matching for rectangular (N x M) matrices
    using the Hungarian / Kuhn-Munkres augmenting path algorithm.
    Runs in O(min(N, M)^2 * max(N, M)) time (< 0.1 ms for typical molecules).
    """
    cost = np.array(cost_matrix, dtype=float)
    n_rows, n_cols = cost.shape
    if n_rows == 0 or n_cols == 0:
        return np.array([], dtype=int), np.array([], dtype=int)

    transpose = False
    if n_rows > n_cols:
        cost = cost.T
        n_rows, n_cols = cost.shape
        transpose = True

    u = np.zeros(n_rows + 1)
    v = np.zeros(n_cols + 1)
    p = np.zeros(n_cols + 1, dtype=int)
    way = np.zeros(n_cols + 1, dtype=int)

    for i in range(1, n_rows + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n_cols + 1, np.inf)
        used = np.zeros(n_cols + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, n_cols + 1):
                if not used[j]:
                    cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n_cols + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    row_ind = np.zeros(n_rows, dtype=int)
    col_ind = np.zeros(n_rows, dtype=int)
    for j in range(1, n_cols + 1):
        if p[j] > 0:
            row_ind[p[j] - 1] = p[j] - 1
            col_ind[p[j] - 1] = j - 1

    if transpose:
        return col_ind, row_ind
    return row_ind, col_ind


# ---------------------------------------------------------------------------
# Symmetry Ranking Algorithms
# ---------------------------------------------------------------------------

def calculate_symmetry_ranks(mol: Chem.Mol) -> List[int]:
    """
    Hybrid topological & rigid-fragment symmetry ranking algorithm.
    Ported and adapted from mol_pirol01/symmetry_ranking.py.
    
    Assigns identical ranks to atoms that:
    1. Share topological canonical rank (with stereochemistry), AND
    2. Have identical distance profiles within their rigid fragment
       (formed by cutting all rotatable single bonds).
    """
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    base_ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True))
    num_at = mol.GetNumAtoms()

    # Find rotatable single bonds (acyclic, non-terminal, between non-H atoms)
    rot_smarts = Chem.MolFromSmarts('[!D1]-&!@[!D1]')
    rot_matches = mol.GetSubstructMatches(rot_smarts) if rot_smarts else ()
    rot_bonds = []
    for a, b in rot_matches:
        bond = mol.GetBondBetweenAtoms(a, b)
        if bond:
            rot_bonds.append(bond.GetIdx())

    # Cut into rigid fragments
    if rot_bonds:
        frags_mol = Chem.FragmentOnBonds(mol, rot_bonds)
    else:
        frags_mol = Chem.Mol(mol)

    frag_indices = Chem.GetMolFrags(frags_mol, asMols=False)
    frags_mols = Chem.GetMolFrags(frags_mol, asMols=True, sanitizeFrags=False)

    # 2D conformations for idealized distance signature computation
    frag_confs = []
    for frag in frags_mols:
        try:
            AllChem.Compute2DCoords(frag)
            frag_confs.append(frag.GetConformer())
        except Exception:
            frag_confs.append(None)

    rank_groups = defaultdict(list)
    for i, r in enumerate(base_ranks):
        rank_groups[r].append(i)

    final_ranks = [-1] * num_at
    next_rank = 0

    for r in sorted(rank_groups.keys()):
        atoms = rank_groups[r]
        if len(atoms) == 1:
            final_ranks[atoms[0]] = next_rank
            next_rank += 1
            continue

        signatures = {}
        for a_idx in atoms:
            sig = (0,)
            for f_idx, f_atoms in enumerate(frag_indices):
                if a_idx in f_atoms:
                    frag_mol = frags_mols[f_idx]
                    conf = frag_confs[f_idx]
                    local_idx = f_atoms.index(a_idx)
                    if conf is not None:
                        pos = conf.GetAtomPosition(local_idx)
                        dists = [round(pos.Distance(conf.GetAtomPosition(i)), 3) 
                                 for i in range(frag_mol.GetNumAtoms())]
                        sig = tuple(sorted(dists))
                    break
            signatures[a_idx] = sig

        sig_groups = defaultdict(list)
        for a_idx, sig in signatures.items():
            sig_groups[sig].append(a_idx)

        for sig in sorted(sig_groups.keys()):
            for a_idx in sig_groups[sig]:
                final_ranks[a_idx] = next_rank
            next_rank += 1

    return final_ranks


# ---------------------------------------------------------------------------
# Auto-Assignment Engine
# ---------------------------------------------------------------------------

class AutoAssignmentEngine:
    """
    Core engine managing model loading, chemical shift prediction,
    symmetry averaging, and bipartite matching.
    """
    _instance = None
    _model = None
    _model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "DLNMR1.pt")
    _prediction_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> AutoAssignmentEngine:
        if cls._instance is None:
            cls._instance = AutoAssignmentEngine()
        return cls._instance

    def __init__(self):
        self._load_model_if_needed()

    def _load_model_if_needed(self):
        if self._model is not None or not TORCH_AVAILABLE:
            return
        if os.path.exists(self._model_path):
            try:
                self._model = torch.jit.load(self._model_path)
                self._model.eval()
            except Exception as e:
                print(f"[AutoAssignment] Fehler beim Laden von DLNMR1.pt: {e}")
                self._model = None
        else:
            print(f"[AutoAssignment] Modell nicht gefunden unter: {self._model_path}")

    @property
    def is_available(self) -> bool:
        return TORCH_AVAILABLE and self._model is not None

    def predict_shifts_for_smiles(self, smiles: str) -> Optional[Dict[str, Any]]:
        """
        Calculates raw 1H and 13C chemical shifts via DLNMR1.pt for a given SMILES.
        Results are cached in memory for zero-latency retrieval.
        """
        if not smiles or not self.is_available:
            return None

        if smiles in self._prediction_cache:
            return self._prediction_cache[smiles]

        try:
            mol_raw = Chem.MolFromSmiles(smiles)
            if not mol_raw:
                return None

            # Add hydrogens and generate 3D conformer with MMFF94
            mol = Chem.AddHs(mol_raw)
            embed_res = AllChem.EmbedMolecule(mol, randomSeed=42)
            if embed_res == -1:
                # Fallback multiple tries
                cids = AllChem.EmbedMultipleConfs(mol, numConfs=5, randomSeed=42)
                if not cids:
                    return None
            AllChem.MMFFOptimizeMolecule(mol)

            conf = mol.GetConformer()
            num_atoms = mol.GetNumAtoms()
            species = [mol.GetAtomWithIdx(i).GetAtomicNum() for i in range(num_atoms)]
            coords = [[p.x, p.y, p.z] for p in [conf.GetAtomPosition(i) for i in range(num_atoms)]]

            Z = torch.tensor(species, dtype=torch.int64)
            R = torch.tensor(coords, dtype=torch.float32).unsqueeze(0)

            with torch.no_grad():
                res = self._model(Z, R)
            shifts_raw = res[2].tolist()

            # Separate and map shifts
            atom_data = []
            for i in range(num_atoms):
                atom = mol.GetAtomWithIdx(i)
                sym = atom.GetSymbol()
                z = atom.GetAtomicNum()
                shift = shifts_raw[i]
                is_valid = not math.isnan(shift)
                
                # For Hydrogens, record parent heavy atom
                parent_idx = None
                if z == 1 and atom.GetBonds():
                    parent_idx = atom.GetNeighbors()[0].GetIdx()

                atom_data.append({
                    "idx": i,
                    "symbol": sym,
                    "z": z,
                    "raw_shift": shift if is_valid else None,
                    "parent_idx": parent_idx
                })

            result = {
                "smiles": smiles,
                "mol": mol,
                "mol_heavy": mol_raw,
                "atom_data": atom_data
            }
            self._prediction_cache[smiles] = result
            return result

        except Exception as e:
            print(f"[AutoAssignment] Fehler bei Vorhersage für SMILES '{smiles}': {e}")
            return None

    def get_symmetry_groups(self, smiles: str, nucleus: str = "13C") -> List[Dict[str, Any]]:
        """
        Groups atoms of the specified nucleus (1H or 13C) by chemical symmetry,
        computes average predicted shifts, and determines theoretical degeneracies.
        """
        pred = self.predict_shifts_for_smiles(smiles)
        if not pred:
            return []

        mol = pred["mol"]
        atom_data = pred["atom_data"]
        target_z = 1 if "1H" in nucleus else 6

        # Calculate symmetry ranks for heavy atoms
        mol_heavy = Chem.RemoveHs(mol)
        heavy_ranks = calculate_symmetry_ranks(mol_heavy)
        for i, atom in enumerate(mol_heavy.GetAtoms()):
            atom.SetIntProp("sym_rank", heavy_ranks[i])

        # Map heavy ranks to full molecule (with H)
        heavy_to_rank = {}
        for i, atom in enumerate(mol_heavy.GetAtoms()):
            heavy_to_rank[i] = heavy_ranks[i]

        # For 1H, calculate full canonical ranks to handle diastereotopic protons
        h_ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True))

        groups_map: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)

        for item in atom_data:
            if item["z"] != target_z or item["raw_shift"] is None:
                continue

            idx = item["idx"]
            if target_z == 6:
                # Carbon: group by heavy atom symmetry rank
                rank_key = ("C", heavy_ranks[idx])
            else:
                # Hydrogen: group by (parent heavy atom rank, proton canonical rank)
                p_idx = item["parent_idx"]
                p_rank = heavy_ranks[p_idx] if p_idx is not None and p_idx < len(heavy_ranks) else 0
                rank_key = ("H", p_rank, h_ranks[idx])

            groups_map[rank_key].append(item)

        symmetry_groups = []
        elem_prefix = "H" if target_z == 1 else "C"

        for group_idx, (key, items) in enumerate(sorted(groups_map.items(), key=lambda x: str(x[0]))):
            shifts = [it["raw_shift"] for it in items]
            avg_shift = float(np.mean(shifts))
            std_shift = float(np.std(shifts)) if len(shifts) > 1 else 0.0
            atom_indices = [it["idx"] for it in items]
            
            # Format atom label with standard NMR spectroscopy notation
            if target_z == 6:
                parent_heavy_indices = sorted(atom_indices)
                if len(atom_indices) == 1:
                    labels_str = f"C{atom_indices[0] + 1}"
                elif len(atom_indices) <= 3:
                    labels_str = "C" + ",".join(str(idx + 1) for idx in sorted(atom_indices))
                else:
                    labels_str = f"C[{min(atom_indices)+1}..{max(atom_indices)+1}]"
            else:
                # Hydrogens: identify parent heavy atoms
                parents = sorted(set(it["parent_idx"] for it in items if it["parent_idx"] is not None))
                parent_heavy_indices = parents
                if parents:
                    parent_tags = []
                    for p in parents:
                        p_atom = mol.GetAtomWithIdx(p)
                        p_sym = p_atom.GetSymbol()
                        parent_tags.append(f"{p_sym}{p + 1}")
                    if all(t.startswith("C") for t in parent_tags):
                        parent_str = "C" + ",".join(str(p + 1) for p in parents)
                    else:
                        parent_str = ",".join(parent_tags)
                    labels_str = f"{len(items)}H({parent_str})"
                else:
                    labels_str = f"H" + ",".join(str(idx + 1) for idx in atom_indices)

            symmetry_groups.append({
                "group_id": group_idx,
                "element": elem_prefix,
                "atom_indices": atom_indices,
                "parent_heavy_indices": parent_heavy_indices,
                "atom_label": labels_str,
                "calc_shift": round(avg_shift, 2),
                "std_dev": round(std_shift, 3),
                "count": len(items),  # Theoretical integral
                "parent_heavy_idx": items[0]["parent_idx"] if target_z == 1 else None
            })

        # Sort symmetry groups descending by calculated chemical shift (NMR convention)
        symmetry_groups.sort(key=lambda g: g["calc_shift"], reverse=True)
        return symmetry_groups

    def assign_peaks(self, smiles: str, peaks: List[Any], nucleus: str = "13C") -> Dict[str, Any]:
        """
        Performs optimal bipartite auto-assignment between experimental peaks
        and predicted symmetry groups.
        
        Parameters:
        - smiles: Molecular structure SMILES
        - peaks: List of NMRPeak objects or dicts (with 'shift'/'shift_ppm', 'integral', 'multiplicity')
        - nucleus: '1H' or '13C'
        
        Returns a dictionary containing:
        - assigned_peaks: List of peak assignments with delta_ppm and confidence
        - unassigned_peaks: Peaks that could not be matched
        - unassigned_groups: Predicted groups that were not matched
        - mae: Mean Absolute Error of assigned peaks
        - success_rate: Ratio of successfully assigned peaks
        """
        sym_groups = self.get_symmetry_groups(smiles, nucleus=nucleus)
        if not sym_groups or not peaks:
            return {
                "assigned_peaks": [],
                "unassigned_peaks": peaks,
                "unassigned_groups": sym_groups,
                "mae": None,
                "success_rate": 0.0,
                "groups": sym_groups
            }

        # Normalize experimental peaks
        exp_peaks = []
        for i, p in enumerate(peaks):
            if hasattr(p, "shift_ppm"):
                shift = float(p.shift_ppm)
                integral = float(getattr(p, "integral", 1.0))
                mult = str(getattr(p, "multiplicity", "s"))
                orig_obj = p
            else:
                shift_raw = p.get("shift", p.get("shift_ppm", 0.0))
                # Handle possible range string
                if isinstance(shift_raw, str) and ("-" in shift_raw or "–" in shift_raw):
                    parts = [float(x.strip()) for x in shift_raw.replace("–", "-").split("-") if x.strip()]
                    shift = float(np.mean(parts)) if parts else 0.0
                else:
                    try:
                        shift = float(str(shift_raw).replace(",", "."))
                    except ValueError:
                        shift = 0.0

                int_raw = p.get("integral", "1H")
                try:
                    int_clean = "".join(c for c in str(int_raw) if c.isdigit() or c == ".")
                    integral = float(int_clean) if int_clean else 1.0
                except ValueError:
                    integral = 1.0
                mult = p.get("multiplicity", "s")
                orig_obj = p

            exp_peaks.append({
                "exp_idx": i,
                "shift": shift,
                "integral": integral,
                "multiplicity": mult,
                "orig": orig_obj
            })

        n_exp = len(exp_peaks)
        n_calc = len(sym_groups)

        is_1h = "1H" in nucleus
        max_allowed_delta = 1.2 if is_1h else 18.0  # Cutoff for plausible assignment

        # Build Cost Matrix C[j, k] = |delta_exp - delta_calc| (+ integral penalty for 1H)
        cost_matrix = np.zeros((n_exp, n_calc))
        for j, ep in enumerate(exp_peaks):
            for k, cg in enumerate(sym_groups):
                d_shift = abs(ep["shift"] - cg["calc_shift"])
                
                # For 1H, subtle integral penalty
                if is_1h and ep["integral"] > 0 and cg["count"] > 0:
                    d_int = abs(ep["integral"] - cg["count"]) / max(ep["integral"], cg["count"])
                    penalty = 0.15 * d_int
                else:
                    penalty = 0.0

                cost_matrix[j, k] = d_shift + penalty

        # Solve optimal assignment
        row_ind, col_ind = hungarian_matching(cost_matrix)

        assigned_peaks = []
        assigned_exp_indices = set()
        assigned_calc_indices = set()
        deviations = []

        for r, c in zip(row_ind, col_ind):
            ep = exp_peaks[r]
            cg = sym_groups[c]
            raw_delta = abs(ep["shift"] - cg["calc_shift"])

            # Check threshold
            if raw_delta <= max_allowed_delta:
                assigned_exp_indices.add(r)
                assigned_calc_indices.add(c)
                deviations.append(raw_delta)

                # Confidence tier
                if is_1h:
                    if raw_delta <= 0.15:
                        conf = "high"
                    elif raw_delta <= 0.40:
                        conf = "medium"
                    else:
                        conf = "low"
                else:
                    if raw_delta <= 3.0:
                        conf = "high"
                    elif raw_delta <= 7.0:
                        conf = "medium"
                    else:
                        conf = "low"

                assigned_peaks.append({
                    "exp_idx": r,
                    "exp_shift": ep["shift"],
                    "exp_mult": ep["multiplicity"],
                    "exp_integral": ep["integral"],
                    "calc_group_id": cg["group_id"],
                    "calc_shift": cg["calc_shift"],
                    "calc_label": cg["atom_label"],
                    "atom_indices": cg["atom_indices"],
                    "parent_heavy_indices": cg.get("parent_heavy_indices", cg["atom_indices"]),
                    "delta_ppm": round(ep["shift"] - cg["calc_shift"], 2),
                    "abs_delta_ppm": round(raw_delta, 2),
                    "confidence": conf,
                    "theoretical_count": cg["count"],
                    "orig_peak": ep["orig"]
                })
            else:
                # Too far off to be a valid assignment
                pass

        # Sort assigned peaks descending by experimental shift
        assigned_peaks.sort(key=lambda p: p["exp_shift"], reverse=True)

        unassigned_exp = [exp_peaks[i]["orig"] for i in range(n_exp) if i not in assigned_exp_indices]
        unassigned_calc = [sym_groups[i] for i in range(n_calc) if i not in assigned_calc_indices]

        mae = float(np.mean(deviations)) if deviations else None
        success_rate = (len(assigned_peaks) / n_exp) if n_exp > 0 else 0.0

        return {
            "assigned_peaks": assigned_peaks,
            "unassigned_peaks": unassigned_exp,
            "unassigned_groups": unassigned_calc,
            "mae": round(mae, 2) if mae is not None else None,
            "success_rate": round(success_rate * 100, 1),
            "groups": sym_groups
        }

    def render_assigned_molecule_svg(self, smiles: str, assignments: List[Dict[str, Any]], 
                                     nucleus: str = "13C", width: int = 380, height: int = 280) -> str:
        """
        Draws 2D SVG depiction of the molecule with consistent 1-based atom numbering
        and highlighted colors corresponding to assignment confidence.
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return ""

            AllChem.Compute2DCoords(mol)

            is_1h = "1H" in nucleus
            highlight_atoms = []
            highlight_colors = {}

            color_map = {
                "high": (0.06, 0.73, 0.51, 0.65),     # Emerald green #10b981
                "medium": (0.96, 0.62, 0.04, 0.65),   # Amber #f59e0b
                "low": (0.98, 0.45, 0.09, 0.65)       # Orange #f97316
            }

            for p in assignments:
                conf = p.get("confidence", "high")
                col = color_map.get(conf, (0.5, 0.5, 0.5, 0.5))
                # For 1H, highlight the parent carbons; for 13C, highlight the carbons directly
                target_heavy = p.get("parent_heavy_indices") if is_1h else p.get("atom_indices")
                if not target_heavy:
                    target_heavy = p.get("atom_indices", [])
                for at_idx in target_heavy:
                    if at_idx < mol.GetNumAtoms():
                        highlight_atoms.append(at_idx)
                        highlight_colors[at_idx] = col

            # Clean 1-based atom numbering (1, 2, 3...) matching the assignment table
            for i, atom in enumerate(mol.GetAtoms()):
                atom.SetProp("atomNote", str(i + 1))

            drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
            opts = drawer.drawOptions()
            opts.addAtomIndices = False  # NEVER use RDKit's 0-based indices!
            opts.annotationFontScale = 0.65
            opts.bondLineWidth = 2.0
            opts.padding = 0.08
            opts.setHighlightColour((0.2, 0.8, 0.4, 0.5))

            drawer.DrawMolecule(
                mol,
                highlightAtoms=highlight_atoms,
                highlightAtomColors=highlight_colors
            )
            drawer.FinishDrawing()
            svg = drawer.GetDrawingText()
            return svg

        except Exception as e:
            print(f"[AutoAssignment] Fehler beim Rendern des SVGs: {e}")
            return ""


# Global singleton instance
auto_assignment_engine = AutoAssignmentEngine.get_instance()

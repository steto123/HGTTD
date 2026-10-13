"""
spectrum_generator.py
High-performance NMR spectrum synthesizer and JCAMP-DX exporter for HGTTD.
Converts peak lists (chemical shifts, multiplicities, J-couplings, integrals)
into continuous Lorentzian NMR spectra with real-time linewidth adjustment
and generates IUPAC-compliant JCAMP-DX 5.01 files.
"""

import re
import numpy as np


DEFAULT_FREQUENCIES = {
    "1H": 400.13,
    "13C": 100.61,
    "19F": 376.50,
    "31P": 161.98,
    "11B": 128.38,
    "29Si": 79.49,
    "other": 400.0
}

DEFAULT_RANGES = {
    "1H": (-1.0, 14.0),
    "13C": (-10.0, 230.0),
    "19F": (-250.0, 50.0),
    "31P": (-150.0, 150.0),
    "11B": (-100.0, 100.0),
    "29Si": (-150.0, 50.0),
    "other": (-10.0, 200.0)
}


class NMRPeak:
    """Represents a single parsed NMR signal with its splitting parameters."""
    def __init__(self, shift_ppm, multiplicity="s", j_couplings=None, integral=1.0, atom_index=None, shift_range=None):
        self.shift_ppm = float(shift_ppm)
        self.multiplicity = (multiplicity or "s").lower().strip()
        self.j_couplings = j_couplings or []  # List of floats in Hz
        self.integral = float(integral) if integral not in (None, "-", "") else 1.0
        self.atom_index = atom_index
        self.shift_range = shift_range  # tuple (min_ppm, max_ppm) for broad multiplets

    def __repr__(self):
        return f"NMRPeak(shift={self.shift_ppm:.2f}, mult={self.multiplicity}, J={self.j_couplings}, int={self.integral})"


def parse_j_couplings(j_str):
    """Parses J-coupling string like '8.5', '7.2, 1.8 Hz', 'J = 6.4 Hz' into list of floats."""
    if not j_str or j_str.strip() in ("-", "None", ""):
        return []
    # Find all float patterns
    matches = re.findall(r"[-+]?\d*\.\d+|\d+", str(j_str))
    couplings = []
    for m in matches:
        try:
            val = float(m)
            if 0.1 <= val <= 3000.0:  # Sensible NMR J-coupling range
                couplings.append(val)
        except ValueError:
            pass
    return couplings


def parse_integral(int_str):
    """Parses integral string like '3', '3H', '1.5' into float."""
    if not int_str or str(int_str).strip() in ("-", "None", ""):
        return 1.0
    match = re.search(r"[-+]?\d*\.\d+|\d+", str(int_str))
    if match:
        try:
            val = float(match.group(0))
            return val if val > 0 else 1.0
        except ValueError:
            pass
    return 1.0


def parse_spectrum_peaks(spectrum_data, nucleus_key="1H"):
    """
    Parses unified spectrum dictionary list (from NMRexp or nmrshiftdb2)
    into a structured list of NMRPeak objects.
    """
    peaks = []
    if not spectrum_data:
        return peaks

    for entry in spectrum_data:
        shift_raw = entry.get("shift", "")
        if not shift_raw or shift_raw == "-":
            continue

        mult_raw = entry.get("multiplicity", "s")
        j_raw = entry.get("j_coupling", "-")
        int_raw = entry.get("integral", "1.0")
        atom_idx = entry.get("atom_index")

        j_list = parse_j_couplings(j_raw)
        integral_val = parse_integral(int_raw)

        # Check for range pattern (e.g. '7.20 – 7.35' or '7.20 - 7.35')
        range_match = re.search(r"([-+]?\d*\.\d+|\d+)\s*[–\-–]\s*([-+]?\d*\.\d+|\d+)", str(shift_raw))
        if range_match:
            try:
                s1 = float(range_match.group(1))
                s2 = float(range_match.group(2))
                center = (s1 + s2) / 2.0
                p = NMRPeak(
                    shift_ppm=center,
                    multiplicity=mult_raw or "m",
                    j_couplings=j_list,
                    integral=integral_val,
                    atom_index=atom_idx,
                    shift_range=(min(s1, s2), max(s1, s2))
                )
                peaks.append(p)
                continue
            except ValueError:
                pass

        # Single shift float
        single_match = re.search(r"[-+]?\d*\.\d+|\d+", str(shift_raw))
        if single_match:
            try:
                shift_val = float(single_match.group(0))
                p = NMRPeak(
                    shift_ppm=shift_val,
                    multiplicity=mult_raw or "s",
                    j_couplings=j_list,
                    integral=integral_val,
                    atom_index=atom_idx
                )
                peaks.append(p)
            except ValueError:
                pass

    return peaks


def expand_multiplet_components(peak, spec_freq_mhz):
    """
    Splits a single NMR peak into its individual line components (frequencies in ppm, relative intensities)
    based on first-order coupling rules.
    Returns: list of tuples (ppm_position, amplitude)
    """
    ppm_center = peak.shift_ppm
    total_area = peak.integral
    mult = peak.multiplicity.lower().replace("br ", "").replace("br", "").strip()
    couplings = list(peak.j_couplings)

    # 1. Broad multiplet / specified range
    if peak.shift_range:
        min_ppm, max_ppm = peak.shift_range
        width = max_ppm - min_ppm
        if width > 0.005:
            # Distribute over 7 envelope points (binomial-like weights)
            weights = np.array([1, 3, 6, 8, 6, 3, 1], dtype=float)
            weights /= weights.sum()
            offsets = np.linspace(min_ppm, max_ppm, 7)
            return [(pos, w * total_area) for pos, w in zip(offsets, weights)]

    # 2. No couplings or singlet
    if not couplings or mult in ("s", "singlet", ""):
        return [(ppm_center, total_area)]

    # 3. Recursive first-order splitting tree
    # Base: single line at ppm_center with intensity 1.0
    lines = [(ppm_center, 1.0)]

    for J in couplings:
        j_ppm = J / spec_freq_mhz
        new_lines = []
        for pos, amp in lines:
            # Doublet split for each coupling
            new_lines.append((pos - j_ppm / 2.0, amp * 0.5))
            new_lines.append((pos + j_ppm / 2.0, amp * 0.5))
        lines = new_lines

    # If multiplicity indicates triplet/quartet with only 1 J given:
    if len(couplings) == 1:
        J = couplings[0]
        j_ppm = J / spec_freq_mhz
        if mult in ("t", "triplet"):
            lines = [
                (ppm_center - j_ppm, 0.25),
                (ppm_center, 0.50),
                (ppm_center + j_ppm, 0.25)
            ]
        elif mult in ("q", "quartet"):
            lines = [
                (ppm_center - 1.5 * j_ppm, 0.125),
                (ppm_center - 0.5 * j_ppm, 0.375),
                (ppm_center + 0.5 * j_ppm, 0.375),
                (ppm_center + 1.5 * j_ppm, 0.125)
            ]
        elif mult in ("quint", "quintet"):
            lines = [
                (ppm_center - 2.0 * j_ppm, 1 / 16),
                (ppm_center - 1.0 * j_ppm, 4 / 16),
                (ppm_center, 6 / 16),
                (ppm_center + 1.0 * j_ppm, 4 / 16),
                (ppm_center + 2.0 * j_ppm, 1 / 16)
            ]

    # Normalize total area to peak.integral
    total_weights = sum(a for _, a in lines)
    if total_weights > 0:
        lines = [(p, (a / total_weights) * total_area) for p, a in lines]

    return lines


def calculate_spectrum_grid(peaks, nucleus_key="1H", spec_freq_mhz=None, fwhm_hz=1.2, num_points=4096, padding_ppm=1.0):
    """
    Calculates synthesized NMR spectrum (x_ppm, y_intensity, integral_curve, peak_labels)
    using vectorized Lorentzian line shape convolution.
    
    Args:
        peaks: list of NMRPeak objects
        nucleus_key: "1H", "13C", "19F", "31P", "11B", "29Si"
        spec_freq_mhz: Spectrometer frequency in MHz (defaults to nucleus standard)
        fwhm_hz: Full Width at Half Maximum in Hz
        num_points: Number of discrete data points along the spectrum
        padding_ppm: Margin around outermost peaks
        
    Returns:
        dict with:
            x: array of chemical shifts (descending order, e.g. 12 -> -1 ppm)
            y: array of intensities (normalized, peak max ~ 1000)
            integral: array of cumulative integrals (or None for non-1H)
            labels: list of dicts {'ppm': float, 'text': str, 'height': float}
            fwhm_hz: float
            spec_freq: float
            nucleus: str
    """
    if spec_freq_mhz is None:
        spec_freq_mhz = DEFAULT_FREQUENCIES.get(nucleus_key, DEFAULT_FREQUENCIES["other"])

    fwhm_ppm = max(0.01, fwhm_hz) / spec_freq_mhz
    half_fwhm = fwhm_ppm / 2.0

    # Determine ppm range
    std_min, std_max = DEFAULT_RANGES.get(nucleus_key, DEFAULT_RANGES["other"])
    if peaks:
        all_shifts = [p.shift_ppm for p in peaks]
        peak_min = min(all_shifts) - padding_ppm
        peak_max = max(all_shifts) + padding_ppm
        x_min = min(std_min, peak_min)
        x_max = max(std_max, peak_max)
    else:
        x_min, x_max = std_min, std_max

    # NMR convention: descending x axis (downfield on left, upfield on right)
    x = np.linspace(x_max, x_min, num_points, dtype=np.float64)

    if not peaks:
        return {
            "x": x,
            "y": np.zeros_like(x),
            "integral": None,
            "labels": [],
            "fwhm_hz": fwhm_hz,
            "spec_freq": spec_freq_mhz,
            "nucleus": nucleus_key
        }

    # Expand all subpeaks
    all_subpeaks = []
    labels = []
    for p in peaks:
        sub_list = expand_multiplet_components(p, spec_freq_mhz)
        all_subpeaks.extend(sub_list)
        
        # Primary label for peak center
        mult_tag = f" ({p.multiplicity})" if p.multiplicity and p.multiplicity != "s" else ""
        int_tag = f", {int(p.integral)}H" if (nucleus_key == "1H" and p.integral) else ""
        labels.append({
            "ppm": p.shift_ppm,
            "text": f"{p.shift_ppm:.2f}{mult_tag}",
            "integral": p.integral,
            "multiplicity": p.multiplicity
        })

    sub_pos = np.array([p for p, _ in all_subpeaks], dtype=np.float64)
    sub_amp = np.array([a for _, a in all_subpeaks], dtype=np.float64)

    # Vectorized Lorentzian line shape synthesis
    # dx shape: (num_points, num_subpeaks)
    dx = x[:, None] - sub_pos[None, :]
    lorentz_matrix = sub_amp[None, :] * (half_fwhm**2) / (dx**2 + half_fwhm**2)
    y = np.sum(lorentz_matrix, axis=1)

    # Scale y to convenient display height (max = 1000.0)
    max_y = float(np.max(y))
    if max_y > 0:
        y_scaled = (y / max_y) * 1000.0
    else:
        y_scaled = y

    # Compute label heights at peak positions
    for lbl in labels:
        target_ppm = lbl["ppm"]
        idx = np.argmin(np.abs(x - target_ppm))
        lbl["height"] = float(y_scaled[idx])

    # Cumulative integral curve (for 1H NMR)
    integral_curve = None
    if nucleus_key == "1H":
        # Integrate right-to-left (from TMS 0 ppm towards high ppm)
        # Flip to ascend, cumsum, flip back
        flipped_y = np.flip(y_scaled)
        flipped_int = np.cumsum(flipped_y)
        max_int = flipped_int[-1] if len(flipped_int) > 0 and flipped_int[-1] > 0 else 1.0
        total_h = sum(p.integral for p in peaks)
        norm_int = (flipped_int / max_int) * total_h
        integral_curve = np.flip(norm_int)

    return {
        "x": x,
        "y": y_scaled,
        "integral": integral_curve,
        "labels": labels,
        "fwhm_hz": fwhm_hz,
        "spec_freq": spec_freq_mhz,
        "nucleus": nucleus_key
    }


def export_jcamp_dx(spectrum_grid, metadata=None):
    """
    Exports synthesized spectrum grid to official IUPAC JCAMP-DX 5.01 format.
    
    Args:
        spectrum_grid: dict returned by calculate_spectrum_grid
        metadata: optional dict with title, solvent, compound name, formula, doi, etc.
        
    Returns:
        str: Valid JCAMP-DX file content
    """
    if metadata is None:
        metadata = {}

    title = metadata.get("title") or metadata.get("name") or "Simulated Spectrum"
    nucleus = spectrum_grid.get("nucleus", "1H")
    nucleus_jcamp = f"^{nucleus}" if not nucleus.startswith("^") else nucleus
    spec_freq = spectrum_grid.get("spec_freq", 400.13)
    solvent = metadata.get("solvent", "Unknown")
    doi = metadata.get("doi_url", "")
    formula = metadata.get("formula", "")

    x = spectrum_grid["x"]
    y = spectrum_grid["y"]
    num_points = len(x)

    first_x = float(x[0])
    last_x = float(x[-1])
    min_x = min(first_x, last_x)
    max_x = max(first_x, last_x)
    min_y = float(np.min(y))
    max_y = float(np.max(y))
    first_y = float(y[0])

    lines = [
        "##TITLE=" + title,
        "##JCAMP-DX=5.01",
        "##DATA TYPE=NMR SPECTRUM",
        "##DATA CLASS=XYDATA",
        "##ORIGIN=HGTTD (Hitchhiker's Guide through the database)",
        "##OWNER=Public Domain",
        "##SPECTROMETER/DATA SYSTEM=HGTTD Synthetic Spectrum Generator",
        f"##.OBSERVE FREQUENCY={spec_freq:.4f}",
        f"##.OBSERVE NUCLEUS={nucleus_jcamp}",
        f"##.SOLVENT={solvent}",
    ]

    if formula:
        lines.append(f"##MOLFORM={formula}")
    if doi:
        lines.append(f"##COMMENT=Literature DOI: {doi}")

    lines.extend([
        "##XUNITS=PPM",
        "##YUNITS=ARBITRARY UNITS",
        f"##FIRSTX={first_x:.6f}",
        f"##LASTX={last_x:.6f}",
        f"##MAXX={max_x:.6f}",
        f"##MINX={min_x:.6f}",
        f"##MAXY={max_y:.4f}",
        f"##MINY={min_y:.4f}",
        "##XFACTOR=1.0",
        "##YFACTOR=1.0",
        f"##NPOINTS={num_points}",
        f"##FIRSTY={first_y:.4f}",
        "##XYDATA=(X++(Y..Y))"
    ])

    # Pack data lines (1 X followed by up to 5 Y values per line)
    chunk_size = 5
    for i in range(0, num_points, chunk_size):
        chunk_x = x[i]
        chunk_y = y[i:i + chunk_size]
        y_str = " ".join(f"{val:.2f}" for val in chunk_y)
        lines.append(f"{chunk_x:.6f} {y_str}")

    # Optional peak table
    labels = spectrum_grid.get("labels", [])
    if labels:
        lines.append("##PEAK TABLE=(XY..XY)")
        for lbl in labels:
            lines.append(f"{lbl['ppm']:.4f}, {lbl.get('height', 100.0):.2f}")

    lines.append("##END=")
    return "\n".join(lines)

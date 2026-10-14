import os
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

def create_presentation_en():
    prs = Presentation()
    # 16:9 widescreen format
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # Professional Modern Color Palette (Dark Theme matching HGTTD)
    BG_DARK = RGBColor(15, 23, 42)        # Slate 900
    CARD_BG = RGBColor(30, 41, 59)        # Slate 800
    CARD_BORDER = RGBColor(51, 65, 85)    # Slate 700
    ACCENT_CYAN = RGBColor(56, 189, 248)  # Sky 400
    ACCENT_BLUE = RGBColor(96, 165, 250)  # Blue 400
    ACCENT_PURPLE = RGBColor(168, 85, 247)# Purple 500
    ACCENT_AMBER = RGBColor(245, 158, 11) # Amber 500
    ACCENT_GREEN = RGBColor(34, 197, 94)  # Emerald 500
    TEXT_WHITE = RGBColor(248, 250, 252)  # Slate 50
    TEXT_MUTED = RGBColor(148, 163, 184)  # Slate 400
    TEXT_BODY = RGBColor(203, 213, 225)   # Slate 300

    icon_path = os.path.abspath("assets/hgttd_icon.png")
    has_icon = os.path.exists(icon_path)

    def set_slide_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_DARK
        bg.line.fill.background()
        return bg

    def add_header(slide, title, category=None):
        set_slide_background(slide)
        
        # Subtle top accent bar
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.04))
        bar.fill.solid()
        bar.fill.fore_color.rgb = ACCENT_CYAN
        bar.line.fill.background()

        # Category pill/text
        if category:
            cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(9.0), Inches(0.35))
            tf_c = cat_box.text_frame
            tf_c.word_wrap = True
            p_c = tf_c.paragraphs[0]
            p_c.text = category.upper()
            p_c.font.size = Pt(10)
            p_c.font.bold = True
            p_c.font.color.rgb = ACCENT_CYAN

        # Title
        t_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(10.5), Inches(0.8))
        tf = t_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        # Logo on header right
        if has_icon:
            slide.shapes.add_picture(icon_path, Inches(12.0), Inches(0.55), width=Inches(0.75))

        # Footer
        footer_box = slide.shapes.add_textbox(Inches(0.8), Inches(7.0), Inches(11.733), Inches(0.35))
        tf_f = footer_box.text_frame
        p_f = tf_f.paragraphs[0]
        p_f.text = "HGTTD — Hitchhiker's Guide through the Database | Spectroscopy, Structure Elucidation & Cheminformatics"
        p_f.font.size = Pt(9)
        p_f.font.color.rgb = TEXT_MUTED

    def add_card(slide, left, top, width, height, title, items, badge_text=None, accent_color=ACCENT_CYAN):
        # Card Background
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = CARD_BORDER
        card.line.width = Pt(1.2)

        # Card Title Box
        title_box = slide.shapes.add_textbox(Inches(left + 0.2), Inches(top + 0.2), Inches(width - 0.4), Inches(0.6))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(15)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        if badge_text:
            p_badge = tf.add_paragraph()
            p_badge.text = f"● {badge_text}"
            p_badge.font.size = Pt(9)
            p_badge.font.bold = True
            p_badge.font.color.rgb = accent_color

        # Card Content
        content_box = slide.shapes.add_textbox(Inches(left + 0.2), Inches(top + 0.8), Inches(width - 0.4), Inches(height - 0.9))
        tf_body = content_box.text_frame
        tf_body.word_wrap = True
        
        for idx, item in enumerate(items):
            p_item = tf_body.paragraphs[0] if idx == 0 else tf_body.add_paragraph()
            p_item.text = f"• {item}"
            p_item.font.size = Pt(11)
            p_item.font.color.rgb = TEXT_BODY
            p_item.space_before = Pt(4)
            p_item.space_after = Pt(2)

    # =========================================================================
    # SLIDE 1: TITLE SLIDE
    # =========================================================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide1)

    # Glow decorative shape
    glow = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.2), Inches(10.33), Inches(5.1))
    glow.fill.solid()
    glow.fill.fore_color.rgb = CARD_BG
    glow.line.color.rgb = ACCENT_CYAN
    glow.line.width = Pt(2)

    if has_icon:
        slide1.shapes.add_picture(icon_path, Inches(6.166), Inches(1.6), width=Inches(1.0))

    title_box = slide1.shapes.add_textbox(Inches(2.0), Inches(2.7), Inches(9.333), Inches(1.8))
    tf1 = title_box.text_frame
    tf1.word_wrap = True
    
    p_main = tf1.paragraphs[0]
    p_main.alignment = PP_ALIGN.CENTER
    p_main.text = "HGTTD"
    p_main.font.size = Pt(44)
    p_main.font.bold = True
    p_main.font.color.rgb = ACCENT_CYAN

    p_sub = tf1.add_paragraph()
    p_sub.alignment = PP_ALIGN.CENTER
    p_sub.text = "Hitchhiker's Guide through the Database 🌌🪐"
    p_sub.font.size = Pt(22)
    p_sub.font.bold = True
    p_sub.font.color.rgb = TEXT_WHITE

    p_desc = tf1.add_paragraph()
    p_desc.alignment = PP_ALIGN.CENTER
    p_desc.text = "The Interactive Multimodal Desktop Companion for Spectroscopy, Structure Elucidation & Chemical AI\nNMR (3.37M) • MS (1.75M) • IR (133k) • DLNMR1 AI Auto-Assignment • 3D Conformers"
    p_desc.font.size = Pt(13)
    p_desc.font.color.rgb = TEXT_MUTED
    p_desc.space_before = Pt(12)

    meta_box = slide1.shapes.add_textbox(Inches(2.0), Inches(5.1), Inches(9.333), Inches(0.8))
    tf_meta = meta_box.text_frame
    p_meta = tf_meta.paragraphs[0]
    p_meta.alignment = PP_ALIGN.CENTER
    p_meta.text = "Python 3.11 • PySide6 / Qt6 • RDKit • PyTorch CPU • Ketcher • 3Dmol.js\n» DON'T PANIC «"
    p_meta.font.size = Pt(11)
    p_meta.font.bold = True
    p_meta.font.color.rgb = ACCENT_AMBER

    # =========================================================================
    # SLIDE 2: MOTIVATION & PROBLEM STATEMENT
    # =========================================================================
    slide2 = prs.slides.add_slide(blank_layout)
    add_header(slide2, "Challenges in Spectroscopy & Structure Elucidation", "Motivation & Vision")

    add_card(slide2, 0.8, 1.8, 3.7, 4.8, "Fragmented Data Silos", [
        "NMR, MS, and IR spectra have historically been isolated in disconnected repositories.",
        "Incompatible formats (JCAMP, MSP, SDF, Parquet) obstruct cross-method analytics.",
        "High manual effort required to correlate experimental data with scientific literature.",
        "Commercial spectroscopy suites are costly, monolithic, and increasingly cloud-locked."
    ], "The Modern Lab Dilemma", ACCENT_AMBER)

    add_card(slide2, 4.8, 1.8, 3.7, 4.8, "Manual Peak Assignment", [
        "Assigning NMR peaks to specific atom positions is tedious, complex, and prone to human error.",
        "Stereochemistry, diastereotopicity, and conformational averaging require expert insight.",
        "Quantum-chemical DFT shift calculations (e.g. ωB97X-D) take hours to days per molecule.",
        "Urgent need for fast, on-device chemical shift inference directly at the benchtop."
    ], "Analytical Bottleneck", ACCENT_PURPLE)

    add_card(slide2, 8.8, 1.8, 3.7, 4.8, "The HGTTD Solution", [
        "Fully standalone, self-contained desktop suite with native dark UI — zero cloud dependency.",
        "Over 5.2 million curated spectra stored locally with lightning-fast query indices.",
        "Deep-learning NMR inference (DLNMR1) in < 20 ms with bipartite Kuhn-Munkres matching.",
        "Seamless unified workflow: 2D Ketcher editor, 3D viewer, NMR, MS, IR & automated lab reports."
    ], "Integrated Ecosystem", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 3: DATA FOUNDATION & SCIENTIFIC SOURCES
    # =========================================================================
    slide3 = prs.slides.add_slide(blank_layout)
    add_header(slide3, "Vast Multimodal Data Foundation (5.2+ Million Spectra)", "Scientific Foundation")

    add_card(slide3, 0.8, 1.8, 2.75, 4.8, "NMRexp (Nature 2025)", [
        "3,372,987 NMR spectra datasets.",
        "Mined from ~200,000 publications (2010–2024).",
        "6 Nuclei: 1H, 13C, 19F, 31P, 11B, 29Si.",
        "Direct DOI link to peer-reviewed source literature.",
        "High-performance Apache Parquet storage."
    ], "3.37M NMR Spectra", ACCENT_CYAN)

    add_card(slide3, 3.75, 1.8, 2.75, 4.8, "MoNa MassBank (UC Davis)", [
        "1,756,800 mass spectra.",
        "271,982 unique chemical entities.",
        "GC-MS (EI 70 eV) & high-res LC-MS/MS (QTOF, Orbitrap).",
        "Precursor m/z index with binary O(log N) lookup.",
        "Positive & Negative ionization modes."
    ], "1.75M Mass Spectra", ACCENT_PURPLE)

    add_card(slide3, 6.7, 1.8, 2.75, 4.8, "SQuIRL & NIST (IR)", [
        "133,883 vibrational spectra.",
        "High-precision DFT frequencies (ωB97X-D/aug-cc-pVTZ).",
        "Experimental NIST WebBook gas & condensed phase IR spectra.",
        "Transmittance & Absorbance modes.",
        "Sub-millisecond substructure filtering."
    ], "133k IR Spectra", ACCENT_AMBER)

    add_card(slide3, 9.65, 1.8, 2.75, 4.8, "nmrshiftdb2 & 3D", [
        "54,000+ organic molecules.",
        "DFT-optimized 3D Cartesian coordinates.",
        "Experimental assigned 13C chemical shifts.",
        "University of Cologne / Chemnitz.",
        "Open Data under CC-BY-SA 4.0 license."
    ], "54k 3D Structures", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 4: WORKSPACE & 2D KETCHER INTEGRATION
    # =========================================================================
    slide4 = prs.slides.add_slide(blank_layout)
    add_header(slide4, "Intuitive Workspace & Embedded Ketcher 2D Editor", "User Interface & Experience")

    add_card(slide4, 0.8, 1.8, 5.7, 4.8, "Embedded EPAM Ketcher Chemical Editor", [
        "Full-fledged web-based chemical sketcher hosted via local Qt6 HTTP server (QWebEngine).",
        "Guaranteed split-screen minimum width (>= 33.3%) for effortless complex molecule drawing.",
        "Comprehensive support: stereochemistry, R-groups, charges, isotopes, and structure templates.",
        "One-click transfer: 'Load into Ketcher' directly from search hits, NMRexp browser, or logbook.",
        "Instant bidirectional sync: SMILES, InChI, and Molfile V2000/V3000 generation in real time."
    ], "Central Drawing Canvas", ACCENT_CYAN)

    add_card(slide4, 6.8, 1.8, 5.7, 4.8, "Ergonomics & Cosmic Design", [
        "Sleek modern Slate Dark theme designed to reduce eye strain during prolonged research sessions.",
        "Dual-language localization: Instant toggle between German and English via centralized i18n.",
        "Dedicated productivity shortcuts (e.g. Alt+1 to Alt+5 for tabs, fast canvas zoom & pan).",
        "Cohesive layout: Structure drawing on the left, tabbed spectrum viewers and results on the right.",
        "Asynchronous non-blocking background search worker with instant emergency cancel (🛑 Stop)."
    ], "Productivity & Ergonomics", ACCENT_BLUE)

    # =========================================================================
    # SLIDE 5: MULTIMODAL STRUCTURE SEARCH
    # =========================================================================
    slide5 = prs.slides.add_slide(blank_layout)
    add_header(slide5, "High-Performance Multimodal Structure Search", "Chemical Search Engine")

    add_card(slide5, 0.8, 1.8, 3.7, 4.8, "🎯 Exact Structure Search", [
        "Instant identification of identical chemical isomers via canonical RDKit SMILES / InChIKey.",
        "Lightning-fast in-memory hash table lookup across millions of records in < 5 ms.",
        "Ideal for immediate verification of newly synthesized target molecules and compounds.",
        "Aggregates available NMR, MS, and IR spectra simultaneously in a single hit card."
    ], "Exact Lookup (< 5 ms)", ACCENT_CYAN)

    add_card(slide5, 4.8, 1.8, 3.7, 4.8, "🧬 Substructure Search", [
        "Discovers specific scaffolds, functional groups, and pharmacophores in complex structures.",
        "Precompiled RDKit fingerprint indices achieve query response times in milliseconds.",
        "Precise atom- and bond-level cyan highlighting (#38bdf8) on all matched result cards.",
        "Filter results by detected nucleus (1H, 13C, 19F, 31P, 11B, 29Si)."
    ], "Cyan Atom Highlighting", ACCENT_PURPLE)

    add_card(slide5, 8.8, 1.8, 3.7, 4.8, "🔮 Tanimoto Similarity Search", [
        "ECFP4 Morgan circular fingerprints (Radius 2, 2048-bit) to identify structural analogs.",
        "Configurable similarity cutoff thresholds: >= 60%, >= 70%, >= 80%, or >= 90%.",
        "Prominent purple relevance score badges (e.g. 🔮 88.5%) displayed on each match.",
        "Essential for estimating spectral properties of novel chemical derivatives and bioisosteres."
    ], "ECFP4 Morgan (2048-bit)", ACCENT_AMBER)

    # =========================================================================
    # SLIDE 6: INTERACTIVE NMR SPECTRUM VIEWER & SYNTHESIS
    # =========================================================================
    slide6 = prs.slides.add_slide(blank_layout)
    add_header(slide6, "Interactive 60-FPS NMR Synthesizer & Mirror Plot", "Nuclear Magnetic Resonance (NMR)")

    add_card(slide6, 0.8, 1.8, 3.7, 4.8, "Real-Time Physical Spectrum Synthesis", [
        "Continuous NumPy-vectorized Lorentzian peak convolution at a fluid 60 FPS HTML5 canvas.",
        "1st-order Pascal splitting trees for authentic multiplets (s, d, t, q, quint, sext, dd, dt, m).",
        "Adjustable FWHM linewidth (0.2 to 15.0 Hz) simulating real-world sample relaxation.",
        "Tunable spectrometer frequency (100 to 800 MHz) for field-dependent multiplet dispersion."
    ], "Vectorized Lorentzian Convolution", ACCENT_CYAN)

    add_card(slide6, 4.8, 1.8, 3.7, 4.8, "🪞 Spectrum Comparison & Mirror Plot", [
        "'Pin as Reference' locks any active spectrum in place for comparative studies.",
        "Inverted mirror plot displayed below baseline for direct 1:1 isomer and impurity validation.",
        "Cumulative amber step integral curve for accurate quantitative 1H peak area assessment.",
        "Dynamic interactive crosshair tooltip displaying chemical shift (δ), J-coupling, and integral."
    ], "Comparative Mirror Analysis", ACCENT_AMBER)

    add_card(slide6, 8.8, 1.8, 3.7, 4.8, "Cross-Highlighting & JCAMP Export", [
        "Peak ↔ 3D Atom linking: Hovering or clicking a peak highlights corresponding 3D atoms in gold.",
        "Full IUPAC JCAMP-DX 5.01 compliance (##XYDATA and ##PEAK TABLE blocks).",
        "Seamless interoperability with third-party tools: MestReNova, TopSpin, and Spekwin32.",
        "Native multi-nucleus support: 1H, 13C, 19F, 31P, 11B, 29Si."
    ], "Interactivity & JCAMP-DX", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 7: DEEP LEARNING AUTO-ASSIGNMENT (est-NMR & DLNMR1)
    # =========================================================================
    slide7 = prs.slides.add_slide(blank_layout)
    add_header(slide7, "AI-Driven Peak Auto-Assignment: DLNMR1 & Bipartite Solver", "Artificial Intelligence")

    add_card(slide7, 0.8, 1.8, 3.7, 4.8, "DLNMR1 Deep Learning Inference", [
        "Wavefunction, Inc. / JOC 2025: On-device PyTorch TorchScript model (DLNMR1.pt).",
        "Accurately reproduces quantum-chemical ωB97X-D/6-31G* DFT chemical shifts.",
        "Blazing fast desktop CPU execution in < 20 ms per molecule — no GPU or cloud required.",
        "Provides theoretical 1H and 13C chemical shifts with quantum accuracy."
    ], "Wavefunction Inc. (JOC 2025)", ACCENT_PURPLE)

    add_card(slide7, 4.8, 1.8, 3.7, 4.8, "Hybrid Symmetry & Bipartite Matching", [
        "Topological symmetry ranking systematically decomposes rotatable bonds.",
        "Preserves free rotational equivalence (e.g. -CH3) while identifying true diastereotopicity.",
        "Kuhn-Munkres (Hungarian algorithm) minimum-cost bipartite matching in pure NumPy (< 0.1 ms).",
        "Mathematically guarantees globally optimal mapping of experiment to theoretical atoms."
    ], "Kuhn-Munkres Matcher", ACCENT_CYAN)

    add_card(slide7, 8.8, 1.8, 3.7, 4.8, "Visual Assignment & Metrics", [
        "Direct peak tags rendered above signals (e.g. 'C1', 'C2,6', '2H(C2,6)', '9H(C5,6,7)').",
        "Theoretical est-NMR drop-lines for immediate visual verification of calculated vs. observed.",
        "2D structure SVG atom highlighting color-coded with matched spectrum peaks.",
        "Confidence traffic-light status chip with Mean Absolute Error (MAE) and Δδ metrics."
    ], "Confidence & Visual Validation", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 8: MASS SPECTROMETRY (MoNa & NEUTRAL-LOSS)
    # =========================================================================
    slide8 = prs.slides.add_slide(blank_layout)
    add_header(slide8, "MoNa Mass Spectrometry & Interactive Neutral-Loss Calculator", "Mass Spectrometry (MS)")

    add_card(slide8, 0.8, 1.8, 3.7, 4.8, "1.75M MoNa Mass Spectra", [
        "Comprehensive MassBank of North America library (UC Davis, Oliver Fiehn Lab).",
        "High-performance Apache Parquet storage with unique SMILES index for 270,000 compounds.",
        "Precursor m/z interval search (± ppm / Da) powered by a binary O(log N) index.",
        "Includes high-resolution LC-MS/MS (QTOF, Orbitrap) and GC-MS standard EI (70 eV)."
    ], "Optimized Parquet Engine", ACCENT_PURPLE)

    add_card(slide8, 4.8, 1.8, 3.7, 4.8, "60-FPS MS Stick Viewer", [
        "Ascending m/z axis from left to right with relative intensity normalization (0–100%).",
        "Smart color-coding: Amber-gold (base peak), emerald-green (precursor/adduct), neon-cyan (fragments).",
        "Real-time noise cutoff slider (0–25%) eliminates background noise and matrix artifacts.",
        "Smooth mousewheel zoom, horizontal pan, interactive tooltips, and top-stick peak labels."
    ], "Color-Coded Stick Viewer", ACCENT_CYAN)

    add_card(slide8, 8.8, 1.8, 3.7, 4.8, "Interactive Neutral-Loss Calculator", [
        "Two-click delta measurement: Clicking precursor and fragment computes exact Δm/z in real time.",
        "Automated pattern recognition against standard biochemical neutral losses:",
        "- 18.01 Da → -H2O (water loss) | 27.99 Da → -CO (carbon monoxide)",
        "- 17.03 Da → -NH3 (ammonia) | 43.99 Da → -CO2 (decarboxylation)",
        "- 15.02 Da → -CH3 | 60.02 Da → -CH3COOH (acetic acid).",
        "Standardized export in NIST MSP and IUPAC JCAMP-DX 5.01 formats."
    ], "Automated Loss Identification", ACCENT_AMBER)

    # =========================================================================
    # SLIDE 9: INFRARED SPECTROSCOPY (SQuIRL & NIST)
    # =========================================================================
    slide9 = prs.slides.add_slide(blank_layout)
    add_header(slide9, "SQuIRL & NIST: FT-IR Spectra & Functional Group Annotation", "Infrared Spectroscopy (IR)")

    add_card(slide9, 0.8, 1.8, 3.7, 4.8, "133k DFT & NIST IR Spectra", [
        "SQuIRL: Anharmonic & harmonic DFT quantum chemistry (ωB97X-D/aug-cc-pVTZ).",
        "NIST WebBook SRD 69: Authentic experimental gas-phase and liquid condensed-phase IR spectra.",
        "Fast Parquet-based substructure prefilter for sub-second query responses.",
        "Standard spectroscopic wavenumber range spanning 4000 to 400 cm⁻¹."
    ], "Quantum & Experimental", ACCENT_AMBER)

    add_card(slide9, 4.8, 1.8, 3.7, 4.8, "Transmittance & Absorbance Viewer", [
        "Interactive 60-FPS HTML5 canvas honoring classic spectroscopic graphing conventions.",
        "Instant toggle between Transmittance (%T, inverted valleys) and Absorbance (positive peaks).",
        "Live Lorentzian convolution with adjustable FWHM bandwidth (4 to 30 cm⁻¹).",
        "Mouse-centered zoom, smooth panning, and vertical dynamic range scaling."
    ], "Dual Mode (%T / Abs)", ACCENT_CYAN)

    add_card(slide9, 8.8, 1.8, 3.7, 4.8, "Functional Group Band Annotation", [
        "Automated diagnostic band overlay for key organic functional groups:",
        "- 3600–3200 cm⁻¹: O-H / N-H stretching vibrations",
        "- 3100–2850 cm⁻¹: C-H aliphatic / aromatic stretches",
        "- 1750–1680 cm⁻¹: C=O carbonyl stretching band",
        "- 2260–2100 cm⁻¹: Triple bonds (C≡C, C≡N)",
        "- < 1500 cm⁻¹: Fingerprint diagnostic region.",
        "Full IUPAC JCAMP-DX 5.01 Infrared export."
    ], "Band Zones & JCAMP Export", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 10: 3D CONFORMERS & FORCE FIELD OPTIMIZATION
    # =========================================================================
    slide10 = prs.slides.add_slide(blank_layout)
    add_header(slide10, "3D Conformers & Interactive Molecular Mechanics", "3D Molecule Viewer (WebGL)")

    add_card(slide10, 0.8, 1.8, 5.7, 4.8, "3Dmol.js WebGL Integration", [
        "Hardware-accelerated 3D molecular visualization rendered natively in the Qt tab.",
        "Direct loading of DFT-optimized coordinates from nmrshiftdb2.",
        "Instant RDKit ETKDGv3 conformer generation from arbitrary 2D SMILES.",
        "Fluid 3D rotation, translation, and zooming with intuitive mouse controls.",
        "Real-time cross-highlighting: Selecting NMR peaks renders corresponding atoms as glowing gold spheres."
    ], "Hardware-Accelerated WebGL", ACCENT_CYAN)

    add_card(slide10, 6.8, 1.8, 5.7, 4.8, "⚡ MMFF94 Force Field Energy Minimization", [
        "Integrated RDKit MMFF94 (Merck Molecular Force Field) optimization engine.",
        "One-click trigger: '⚡ MMFF94 Optimize' relaxes bond lengths, angles, and torsional strain.",
        "Live animated relaxation: Watch the molecule dynamically fold and relieve steric clashes.",
        "Calculation and real-time display of total conformational strain energy in kcal/mol.",
        "Generates clean, physically sound 3D geometries for accurate spatial inspection."
    ], "Molecular Mechanics (MMFF94)", ACCENT_PURPLE)

    # =========================================================================
    # SLIDE 11: RESEARCH LOGBOOK & AUTOMATED LAB REPORTS
    # =========================================================================
    slide11 = prs.slides.add_slide(blank_layout)
    add_header(slide11, "Persistent Research Logbook & Automated Lab Reports", "Documentation & Reporting")

    add_card(slide11, 0.8, 1.8, 5.7, 4.8, "📔 Persistent Research Logbook (SQLite)", [
        "Local relational SQLite database (user_logbook.db) permanently saves your research state.",
        "Dedicated Logbook tab (Alt+5) featuring Starred Bookmarks (⭐) and History (🕒).",
        "One-click bookmarking on every search result card and NMRexp browse view.",
        "Custom experimental notes editor and multi-tag system for structured sample management.",
        "Fast-action shortcuts: Send bookmarked entries directly to Ketcher, 3D, or NMR view."
    ], "Local SQLite Database", ACCENT_AMBER)

    add_card(slide11, 6.8, 1.8, 5.7, 4.8, "📑 Automated Certificate of Analysis (HTML / PDF)", [
        "One-click generation of publication-ready, print-formatted A4 analytical certificates.",
        "Includes high-resolution 2D structure diagram with numbered atom labels and properties.",
        "Comprehensive peak assignment tables (multiplicity, J-coupling, integrals, DLNMR1 shifts).",
        "Seamlessly embeds user research notes, project tags, and custom timestamps.",
        "Exportable as clean, responsive HTML and standalone vector-rendered PDF documents."
    ], "Publication-Ready A4 PDF", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 12: SYSTEM ARCHITECTURE & CODEBASE
    # =========================================================================
    slide12 = prs.slides.add_slide(blank_layout)
    add_header(slide12, "Modular System Architecture & Robust Engineering", "Tech Stack & Architecture")

    add_card(slide12, 0.8, 1.8, 3.7, 4.8, "Presentation & UI Layer", [
        "PySide6 / Qt6 delivering native desktop responsiveness on Windows 10/11.",
        "QWebEngineView hosting Ketcher 2D, 3Dmol.js, and HTML5 canvas spectrum engines.",
        "Bi-directional internationalization engine (i18n.py) with live language toggle.",
        "Robust JSON-backed persistent configuration management (config_manager.py)."
    ], "PySide6 / Qt6 Desktop GUI", ACCENT_CYAN)

    add_card(slide12, 4.8, 1.8, 3.7, 4.8, "Asynchronous Workers & AI", [
        "SearchWorker background thread isolates heavy database querying from UI thread.",
        "PyTorch TorchScript (CPU) executing DLNMR1 deep-learning models in < 20 ms.",
        "Pure NumPy Kuhn-Munkres bipartite matching solver executing in < 0.1 ms.",
        "RDKit cheminformatics core for fingerprinting, MMFF94, and 3D coordinate generation."
    ], "Asynchronous & Multithreaded", ACCENT_PURPLE)

    add_card(slide12, 8.8, 1.8, 3.7, 4.8, "High-Speed Data Layer", [
        "Apache Parquet with Snappy compression for scanning millions of spectra in seconds.",
        "Binary NumPy npz indices for instant precursor m/z and NMR nuclei filtering.",
        "Embedded SQLite relational database for user logbooks, notes, and favorites.",
        "Standard export pipeline: IUPAC JCAMP-DX 5.01, NIST MSP, CSV, SDF, HTML & PDF."
    ], "Parquet, SQLite & Standards", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 13: REAL-WORLD USE CASES & AUDIENCE
    # =========================================================================
    slide13 = prs.slides.add_slide(blank_layout)
    add_header(slide13, "Real-World Workflows & Applications", "Practical Use Cases")

    add_card(slide13, 0.8, 1.8, 3.7, 4.8, "Synthetic Chemistry & QC", [
        "Rapidly benchmark synthesized compounds against 3.37M experimental literature spectra.",
        "Verify isomeric purity and detect side-products using inverted mirror plots.",
        "Deconvolute ambiguous peak signals with instant AI predictions, eliminating DFT delays.",
        "Generate instant A4 PDF laboratory certificates for documentation and project handovers."
    ], "Organic & MedChem Lab", ACCENT_CYAN)

    add_card(slide13, 4.8, 1.8, 3.7, 4.8, "Bioanalytics & Metabolomics", [
        "Identify unknown metabolites and trace impurities in complex biological matrices.",
        "Query 1.75 million MoNa mass spectra via high-speed precursor m/z tolerance search.",
        "Elucidate fragmentation mechanisms using the interactive Neutral-Loss Calculator.",
        "Correlate MS, IR, and NMR evidence for incontrovertible structure proof."
    ], "Metabolomics & Impurity ID", ACCENT_AMBER)

    add_card(slide13, 8.8, 1.8, 3.7, 4.8, "Academic Teaching & Education", [
        "Highly engaging educational tool for university chemistry and pharmacy courses.",
        "Visually demonstrates coupling patterns, Pascal trees, and multiplet collapse across MHz.",
        "Hands-on experience with modern chemical AI and multimodal scientific databases.",
        "Completely free, portable, and unrestricted by expensive proprietary licensing."
    ], "University & Education", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 14: SUMMARY & OUTLOOK
    # =========================================================================
    slide14 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide14)

    add_header(slide14, "Summary & Future Roadmap: What Lies Ahead", "Conclusion & Roadmap")

    add_card(slide14, 0.8, 1.8, 5.7, 4.8, "Key Strengths of HGTTD", [
        "✓ 5.2+ Million Curated Spectra: NMR (3.37M), MS (1.75M), IR (133k) & 54k 3D conformers.",
        "✓ Fully Offline & Private: Zero cloud dependency; absolute data confidentiality for IP.",
        "✓ AI-Powered Elucidation: Sub-20ms DLNMR1 inference combined with Kuhn-Munkres matching.",
        "✓ Maximum Interactivity: 60-FPS canvas, 3D cross-highlighting, mirror plots, neutral losses.",
        "✓ Unified Chemical Workflow: Integrated Ketcher, 3Dmol.js, SQLite logbook, and PDF reports."
    ], "HGTTD at a Glance", ACCENT_CYAN)

    add_card(slide14, 6.8, 1.8, 5.7, 4.8, "Development Roadmap", [
        "• Deep-learning shift prediction expansion to 19F and 31P heteroatom nuclei.",
        "• 2D-NMR physical simulation & interactive contour plots (COSY, HSQC, HMBC).",
        "• Automated peak deconvolution algorithms for resolving crowded overlapping multiplet zones.",
        "• Direct integration with Electronic Lab Notebooks (ELN) and laboratory LIMS systems.",
        "• Community plugin framework for custom spectrometer file formats and processing scripts."
    ], "Upcoming Innovations", ACCENT_PURPLE)

    # Save presentation
    output_filename = "HGTTD_Presentation_EN.pptx"
    prs.save(output_filename)
    print(f"English presentation saved successfully as {output_filename}")

if __name__ == "__main__":
    create_presentation_en()

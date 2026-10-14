import os
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

def create_presentation():
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
        p_f.text = "HGTTD — Hitchhiker's Guide through the Database | Spektroskopie, Strukturaufklärung & Cheminformatik"
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
    # SLIDE 1: TITELFOLIE
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
    p_desc.text = "Der interaktive Multimodal-Begleiter für Spektroskopie, Strukturaufklärung & Chemische KI\nNMR (3,37 Mio) • MS (1,75 Mio) • IR (133k) • DLNMR1 KI-Zuordnung • 3D-Konformere"
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
    # SLIDE 2: MOTIVATION & PROBLEMSTELLUNG
    # =========================================================================
    slide2 = prs.slides.add_slide(blank_layout)
    add_header(slide2, "Herausforderungen in der Spektroskopie & Strukturaufklärung", "Motivation & Vision")

    add_card(slide2, 0.8, 1.8, 3.7, 4.8, "Fragmentierte Dateninseln", [
        "NMR-, MS- und IR-Daten liegen historisch in getrennten Silos vor.",
        "Unterschiedliche Formate (JCAMP, MSP, SDF, Parquet) erschweren parallele Analysen.",
        "Hoher manueller Aufwand beim Abgleich experimenteller Spektren mit Literaturdaten.",
        "Kommerzielle Software-Suiten sind teuer, schwerfällig und cloudgebunden."
    ], "Problem in Labor & Forschung", ACCENT_AMBER)

    add_card(slide2, 4.8, 1.8, 3.7, 4.8, "Manuelle Peak-Zuordnung", [
        "Die Zuordnung von NMR-Signalen zu Atompositionen ist zeitintensiv und fehleranfällig.",
        "Stereochemie, Diastereotopie und Rotationssymmetrien erfordern komplexe Betrachtungen.",
        "Theoretische DFT-Rechnungen (z.B. ωB97X-D) dauern Stunden bis Tage pro Molekül.",
        "Bedarf an schneller In-situ-Inferenz direkt am Spektrometer oder Arbeitsplatz."
    ], "Flaschenhals der Analytik", ACCENT_PURPLE)

    add_card(slide2, 8.8, 1.8, 3.7, 4.8, "Die HGTTD-Lösung", [
        "Vollständig autarke Desktop-Suite ohne Cloud-Zwang mit nativem Dark Theme.",
        "Über 5,2 Millionen Spektren direkt auf der Festplatte in optimierten Indexen.",
        "Deep-Learning-Vorhersage (DLNMR1) in < 20 ms mit automatischem Bipartite-Matching.",
        "Nahtlose Integration: 2D-Editor, 3D-Viewer, NMR, MS, IR & automatische Laborberichte."
    ], "Ganzheitlicher Ansatz", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 3: DATENBASIS & WISSENSCHAFTLICHE QUELLEN
    # =========================================================================
    slide3 = prs.slides.add_slide(blank_layout)
    add_header(slide3, "Gigantische Multimodale Datenbasis (5,2+ Millionen Spektren)", "Wissenschaftliche Fundierung")

    add_card(slide3, 0.8, 1.8, 2.75, 4.8, "NMRexp (Nature 2025)", [
        "3.372.987 NMR-Datensätze",
        "Extrahiert aus knapp 200.000 Publikationen (2010–2024).",
        "6 Kerne: 1H, 13C, 19F, 31P, 11B, 29Si.",
        "Direkte DOI-Verlinkung zur Originalarbeit.",
        "Optimiertes Apache Parquet-Speicherformat."
    ], "3,37 Mio. NMR", ACCENT_CYAN)

    add_card(slide3, 3.75, 1.8, 2.75, 4.8, "MoNa MassBank (UC Davis)", [
        "1.756.800 Massenspektren",
        "271.982 chemische Verbindungen.",
        "GC-MS (EI 70 eV) & hochauflösendes LC-MS/MS (QTOF, Orbitrap).",
        "Precursor m/z-Index mit binärer O(log N) Suche.",
        "Positive & Negative Ionisation."
    ], "1,75 Mio. MS", ACCENT_PURPLE)

    add_card(slide3, 6.7, 1.8, 2.75, 4.8, "SQuIRL & NIST (IR)", [
        "133.883 Schwingungsspektren",
        "Hochpräzise DFT-Frequenzen (ωB97X-D/aug-cc-pVTZ).",
        "Experimentelle NIST WebBook Gas- und Flüssig-Infrarotspektren.",
        "Transmittanz & Extinktion.",
        "Substruktur-Index in Millisekunden."
    ], "133k IR", ACCENT_AMBER)

    add_card(slide3, 9.65, 1.8, 2.75, 4.8, "nmrshiftdb2 & 3D", [
        "54.000+ organische Moleküle",
        "DFT-optimierte 3D-Koordinaten.",
        "Experimentelle 13C-Verschiebungen.",
        "Universität zu Köln / Chemnitz.",
        "Strukturaufklärung mit CC-BY-SA 4.0 Open Data."
    ], "54k 3D-Strukturen", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 4: BENUTZEROBERFLÄCHE & 2D-KETCHER INTEGRATION
    # =========================================================================
    slide4 = prs.slides.add_slide(blank_layout)
    add_header(slide4, "Intuitive Arbeitsumgebung & Integrierter Ketcher 2D-Editor", "Benutzeroberfläche & Bedienung")

    add_card(slide4, 0.8, 1.8, 5.7, 4.8, "Eingebetteter EPAM Ketcher Moleküleditor", [
        "Vollwertiger Web-basierter chemischer Editor direkt in Qt6 (QWebEngine / lokaler HTTP-Server).",
        "Garantierte Mindestbreite (>= 33,3 %) für ermüdungsfreies Zeichnen komplexer Naturstoffe.",
        "Unterstützt Stereochemie, R-Gruppen, Reaktionen, Ladungen, Isotope und Vorlagen.",
        "1-Klick-Übernahme: 'In Ketcher laden' aus Suchtreffern, NMRexp-Browser oder Logbuch.",
        "Export/Import: SMILES, InChI, Molfile V2000/V3000 in Echtzeit synchronisiert."
    ], "Zentraler Zeichenbereich", ACCENT_CYAN)

    add_card(slide4, 6.8, 1.8, 5.7, 4.8, "Ergonomie & Kosmisches Design", [
        "Modernes 'Slate Dark'-Design (reduziert Augenbelastung bei langen Labor-Sessions).",
        "Zweisprachige Lokalisierung: Vollständiges Umschalten zwischen Deutsch und Englisch via i18n.",
        "Tastaturkürzel für Workflows (z.B. Alt+1 bis Alt+5 für Tabs, Schnelltasten für Zoom).",
        "Geteilte Ansicht: Zeichnen links, Suchergebnisse & Spektren-Tabs rechts.",
        "Asynchrone Hintergrundsuche via Worker-Thread mit rotem Sofort-Abbruch-Button (🛑 Stopp)."
    ], "Workflow & Usability", ACCENT_BLUE)

    # =========================================================================
    # SLIDE 5: MULTIMODALE STRUKTURSUCHE
    # =========================================================================
    slide5 = prs.slides.add_slide(blank_layout)
    add_header(slide5, "Multimodale Hochleistungs-Struktursuche", "Chemische Such-Engine")

    add_card(slide5, 0.8, 1.8, 3.7, 4.8, "🎯 Exakte Struktursuche", [
        "Identifiziert exakt übereinstimmende chemische Isomere via kanonischem RDKit SMILES / InChIKey.",
        "Ultraschneller Hash-Lookup über Millionen Einträge in < 5 Millisekunden.",
        "Ideal zur schnellen Überprüfung von Syntheseprodukten und literaturbekannten Verbindungen.",
        "Zeigt sofort verfügbare NMR-, MS- und IR-Datensätze parallel an."
    ], "Exakter Abgleich (< 5 ms)", ACCENT_CYAN)

    add_card(slide5, 4.8, 1.8, 3.7, 4.8, "🧬 Substruktursuche", [
        "Findet beliebige Leitstrukturen und Kernfragmente in komplexen Molekülen.",
        "Vorkompilierte RDKit-Fingerprint-Indizes für Substrukturen in Millisekunden.",
        "Atom- und bindungsgenaues Cyan-Highlighting (#38bdf8) in den Trefferkarten.",
        "Filtermöglichkeit nach Messkernen (1H, 13C, 19F, 31P, 11B, 29Si)."
    ], "Cyan-Highlighting", ACCENT_PURPLE)

    add_card(slide5, 8.8, 1.8, 3.7, 4.8, "🔮 Tanimoto-Ähnlichkeitssuche", [
        "ECFP4-Morgan-Fingerprints (Radius 2, 2048 Bit) zur Entdeckung struktureller Verwandter.",
        "Einstellbarer Schwellenwert: >= 60 %, >= 70 %, >= 80 % oder >= 90 % Ähnlichkeit.",
        "Farbige Relevanz-Badges (z.B. 🔮 88.5 %) direkt auf jeder Ergebniskarte.",
        "Perfekt zur Spektren-Abschätzung neuartiger Derivate und Bioisostere."
    ], "ECFP4 Morgan (2048-Bit)", ACCENT_AMBER)

    # =========================================================================
    # SLIDE 6: INTERAKTIVER NMR-SPEKTREN-VIEWER & SYNTHESE
    # =========================================================================
    slide6 = prs.slides.add_slide(blank_layout)
    add_header(slide6, "Interaktiver 60-FPS NMR-Synthesizer & Mirror-Plot", "Kernspinresonanz (NMR)")

    add_card(slide6, 0.8, 1.8, 3.7, 4.8, "Physikalische Spektren-Synthese", [
        "Kontinuierliche NumPy-vektorisierte Lorentz-Faltung in Echtzeit (60 FPS Canvas).",
        "Pascal-Aufspaltungsbäume 1. Ordnung für Multipletts (s, d, t, q, quint, sext, dd, dt, dq, m).",
        "Stufenlose FWHM-Linienbreite (0.2 bis 15.0 Hz) zur Simulation realer Relaxation.",
        "Variable Spektrometerfrequenz (100 bis 800 MHz) für feldabhängige Kopplungsauflösung."
    ], "Echtzeit-Lorentz-Faltung", ACCENT_CYAN)

    add_card(slide6, 4.8, 1.8, 3.7, 4.8, "🪞 Spektrenvergleich & Mirror-Plot", [
        "Funktion 'Als Referenz merken' fixiert das aktuelle Spektrum in der Anzeige.",
        "Gespiegelter Invert-Plot unter der Basislinie für direkten 1:1-Isomerenvergleich.",
        "Kumulative bernsteinfarbene Integralkurve für quantitative 1H-Peak-Flächen.",
        "Fadenkreuz mit dynamischem Tooltip für chemische Verschiebung (δ), J und Integral."
    ], "Direkter Isomeren-Vergleich", ACCENT_AMBER)

    add_card(slide6, 8.8, 1.8, 3.7, 4.8, "Cross-Highlighting & Export", [
        "Peak ↔ 3D-Atom-Verknüpfung: Hover/Klick auf Peak färbt Atom in 3D-Struktur golden.",
        "Volle IUPAC JCAMP-DX 5.01 Kompatibilität (##XYDATA und ##PEAK TABLE).",
        "Nahtloser Transfer exportierter Dateien in MestReNova, TopSpin oder Spekwin32.",
        "Unterstützt alle 6 Kerne: 1H, 13C, 19F, 31P, 11B, 29Si."
    ], "Interaktion & JCAMP-DX", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 7: DEEP LEARNING AUTO-ASSIGNMENT (est-NMR & DLNMR1)
    # =========================================================================
    slide7 = prs.slides.add_slide(blank_layout)
    add_header(slide7, "KI-gestützte Peak-Zuordnung: DLNMR1 & Bipartites Matching", "Künstliche Intelligenz")

    add_card(slide7, 0.8, 1.8, 3.7, 4.8, "DLNMR1 Deep Learning Inferenz", [
        "Wavefunction, Inc. / JOC 2025: Lokales PyTorch TorchScript-Modell (DLNMR1.pt).",
        "Reproduziert quantenchemische ωB97X-D/6-31G* DFT-Verschiebungen.",
        "Ultraschnelle Inferenz auf Standard-Desktop-CPUs (< 20 ms pro Molekül).",
        "Berechnung von 1H- und 13C-Verschiebungen ohne Cloud oder externe Server."
    ], "Wavefunction Inc. (JOC 2025)", ACCENT_PURPLE)

    add_card(slide7, 4.8, 1.8, 3.7, 4.8, "Hybrid-Symmetrie & Bipartite Solver", [
        "Topologisches Symmetrie-Ranking zerlegt rotierbare Bindungen.",
        "Erhält freie Rotationsäquivalenzen (z.B. CH3) bei gleichzeitiger Detektion von Diastereotopie.",
        "Kuhn-Munkres (Ungarischer Algorithmus) Solver in reinem NumPy (< 0.1 ms).",
        "Findet die mathematisch globale Minimal-Kosten-Zuordnung Experiment ↔ Theorie."
    ], "Kuhn-Munkres Algorithmus", ACCENT_CYAN)

    add_card(slide7, 8.8, 1.8, 3.7, 4.8, "Visuelle Zuordnungs-Ergebnisse", [
        "Peak-Tags direkt im Spektrum (z.B. 'C1', 'C2,6', '2H(C2,6)', '9H(C5,6,7)').",
        "Theoretische est-NMR Drop-Lines zum visuellen Abweichungs-Vergleich.",
        "2D-SVG-Hervorhebung der zugeordneten Atome in korrespondierenden Signalfarben.",
        "Konfidenz-Ampel (Sehr gut / Mäßig / Gering) mit Mean Absolute Error (MAE) und Δδ."
    ], "Metriken & Konfidenz", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 8: MASSENSPEKTROMETRIE (MoNa & NEUTRAL-LOSS)
    # =========================================================================
    slide8 = prs.slides.add_slide(blank_layout)
    add_header(slide8, "MoNa Massenspektrometrie & Interaktiver Neutral-Loss-Rechner", "Massenspektrometrie (MS)")

    add_card(slide8, 0.8, 1.8, 3.7, 4.8, "1,75 Mio. MoNa Massenspektren", [
        "Vollständige MassBank of North America Datenbank (UC Davis, Oliver Fiehn Lab).",
        "High-Speed Apache Parquet Engine mit Vorfilter-Index für 270.000 Substanzen.",
        "Precursor m/z-Intervallsuche (± ppm / Da) via binärem O(log N) Index.",
        "Umfasst hochauflösende LC-MS/MS (QTOF, Orbitrap) sowie GC-MS EI (70 eV)."
    ], "High-Speed Parquet Engine", ACCENT_PURPLE)

    add_card(slide8, 4.8, 1.8, 3.7, 4.8, "60-FPS MS-Stick-Viewer", [
        "Aufsteigende m/z-Achse von links nach rechts mit relativen Intensitäten (0–100 %).",
        "Intelligente Farbcodierung: Gold (Basispeak), Grün (Precursor/Addukt), Cyan (Fragmente).",
        "Echtzeit Cutoff-Slider (0–25 %) zur Ausblendung von Rauschen und Matrixpeaks.",
        "Zoom, Pan, Tooltip mit Intensität und Peak-Beschriftung oberhalb der Sticks."
    ], "Farbcodierter Stick-Viewer", ACCENT_CYAN)

    add_card(slide8, 8.8, 1.8, 3.7, 4.8, "Interaktiver Neutral-Loss-Rechner", [
        "2-Klick-Messung: Klick auf Precursor und Fragment ermittelt exakte Massendifferenz Δm/z.",
        "Automatische chemische Interpretation typischer Neutralabspaltungen:",
        "- 18.01 Da → -H2O (Wasserabspaltung) | 27.99 Da → -CO",
        "- 17.03 Da → -NH3 (Ammoniak) | 43.99 Da → -CO2",
        "- 15.02 Da → -CH3 | 60.02 Da → -CH3COOH (Essigsäure).",
        "Export in standardisierte Formate: NIST MSP & IUPAC JCAMP-DX 5.01."
    ], "Automatischer Verlust-Abgleich", ACCENT_AMBER)

    # =========================================================================
    # SLIDE 9: INFRAROTSPEKTROSKOPIE (SQuIRL & NIST)
    # =========================================================================
    slide9 = prs.slides.add_slide(blank_layout)
    add_header(slide9, "SQuIRL & NIST: FT-IR Spektren & Banden-Annotation", "Infrarotspektroskopie (IR)")

    add_card(slide9, 0.8, 1.8, 3.7, 4.8, "133.883 DFT & NIST IR-Spektren", [
        "SQuIRL: Anharmonische & harmonische DFT-Quantenchemie (ωB97X-D/aug-cc-pVTZ).",
        "NIST WebBook SRD 69: Experimentelle Gas- und Flüssigphasen-Infrarotspektren.",
        "Parquet-basierter Substruktur-Vorfilter für blitzschnelle IR-Abfragen.",
        "Standard-Wellenzahlenbereich von 4000 bis 400 cm⁻¹."
    ], "DFT & Experimentell", ACCENT_AMBER)

    add_card(slide9, 4.8, 1.8, 3.7, 4.8, "Transmittanz- & Extinktions-Viewer", [
        "Interaktiver 60-FPS HTML5-Canvas mit klassischer Spektroskopie-Darstellung.",
        "Umschaltbar zwischen Transmittanz (%T, Täler) und Extinktion (Absorbance, Peaks).",
        "Echtzeit-Lorentz-Faltung mit stufenloser Linienbreite (FWHM 4 bis 30 cm⁻¹).",
        "Mausrad-Zoom auf Peak-Details, horizontales Panning und Intensitätsskalierung."
    ], "Umschaltbare Optik (%T / Abs)", ACCENT_CYAN)

    add_card(slide9, 8.8, 1.8, 3.7, 4.8, "Funktionelle Gruppen Annotation", [
        "Automatische Banden-Zonierung für funktionelle Gruppen:",
        "- 3600–3200 cm⁻¹: O-H / N-H Valenzschwingungen",
        "- 3100–2850 cm⁻¹: C-H aliphatisch / aromatisch",
        "- 1750–1680 cm⁻¹: C=O Carbonyl-Bande",
        "- 2260–2100 cm⁻¹: Dreifachbindungen (C≡C, C≡N)",
        "- < 1500 cm⁻¹: Fingerprint-Region.",
        "Vollständiger IUPAC JCAMP-DX 5.01 Infrarot-Export."
    ], "Banden-Zonen & JCAMP-DX", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 10: 3D-KONFORMERE & KRAFTFELD-OPTIMIERUNG
    # =========================================================================
    slide10 = prs.slides.add_slide(blank_layout)
    add_header(slide10, "3D-Konformere & Interaktive Kraftfeld-Minimierung", "3D-Molekülbetrachter (WebGL)")

    add_card(slide10, 0.8, 1.8, 5.7, 4.8, "3Dmol.js WebGL-Integration", [
        "Hochperformante dreidimensionale Darstellung direkt im GUI-Tab.",
        "Vorgefertigte quantenmechanisch optimierte 3D-Koordinaten aus nmrshiftdb2.",
        "Automatische Generierung plausibler 3D-Startkonformere via RDKit ETKDGv3 aus beliebigen SMILES.",
        "Freies Drehen, Schwenken und Zoomen mit Maussteuerung.",
        "Echtzeit-Cross-Highlighting: Peak-Auswahl färbt das korrespondierende Atom als goldene Sphäre."
    ], "Hardwarebeschleunigtes WebGL", ACCENT_CYAN)

    add_card(slide10, 6.8, 1.8, 5.7, 4.8, "⚡ MMFF94-Kraftfeld Energieminimierung", [
        "Integrierte RDKit MMFF94 (Merck Molecular Force Field) Optimierungs-Engine.",
        "1-Klick-Aktivierung: '⚡ MMFF94 Optimieren' relaxiert Bindungslängen, Valenz- und Torsionswinkel.",
        "Animierte Konformations-Relaxation: Der Anwender sieht dem Molekül bei der Faltung zu.",
        "Berechnung und Ausgabe der konformativen Gesamtenergie in kcal/mol.",
        "Beseitigt sterische Überlappungen für realistische Geometrie-Vergleiche."
    ], "Molekülmechanik (MMFF94)", ACCENT_PURPLE)

    # =========================================================================
    # SLIDE 11: FORSCHUNGS-LOGBUCH & AUTOMATISIERTER LABORBERICHT
    # =========================================================================
    slide11 = prs.slides.add_slide(blank_layout)
    add_header(slide11, "Persistentes Logbuch & Automatisierte Laborberichte", "Dokumentation & Export")

    add_card(slide11, 0.8, 1.8, 5.7, 4.8, "📔 Persistentes Forschungs-Logbuch (SQLite)", [
        "Lokale relationale Datenbank (user_logbook.db) überdauert Neustarts zuverlässig.",
        "Tab 'Logbuch' (Alt+5) mit Lesezeichen (⭐ Favoriten) und lückenlosem Verlauf (🕒 Historie).",
        "Ein-Klick-Lesezeichen auf jeder Suchtrefferkarte und im NMRexp-Browser.",
        "Labor-Notizen-Editor und Schlagwort/Tag-Verwaltung für strukturiertes Forschungsmanagement.",
        "Schnellaktionen: Moleküle direkt nach Ketcher, in 3D oder in den NMR-Viewer übertragen."
    ], "Persistente SQLite-Engine", ACCENT_AMBER)

    add_card(slide11, 6.8, 1.8, 5.7, 4.8, "📑 Automatisierter Laborbericht (HTML / PDF)", [
        "Generierung druckfertiger A4-Analysenzertifikate mit einem Klick.",
        "Enthält nummerierte hochauflösende 2D-Strukturformel und chemische Kenndaten.",
        "Vollständige Peakzuordnungstabelle (Multiplizität, Kopplungskonstanten, Integrale, DLNMR1-Werte).",
        "Automatische Einbindung von Labor-Notizen und Tags aus dem persönlichen Logbuch.",
        "Export als formatierte HTML-Seite und vektorbasiertes druckfertiges PDF."
    ], "Druckfertiger A4-Report", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 12: SYSTEMARCHITEKTUR & CODEBASIS
    # =========================================================================
    slide12 = prs.slides.add_slide(blank_layout)
    add_header(slide12, "Modulare Software-Architektur & Robuste Pipeline", "Technologie-Stack & Architektur")

    add_card(slide12, 0.8, 1.8, 3.7, 4.8, "Präsentation & UI-Schicht", [
        "PySide6 / Qt6 für native Desktop-Performance auf Windows 10/11.",
        "QWebEngineView für Ketcher 2D-Editor, 3Dmol.js und HTML5-Canvas Spektren.",
        "Zweisprachige Lokalisierungs-Engine (i18n.py) mit Echtzeit-Sprachwechsel.",
        "Persistentes Konfigurationsmanagement via config_manager.py (JSON)."
    ], "PySide6 / Qt6 Desktop GUI", ACCENT_CYAN)

    add_card(slide12, 4.8, 1.8, 3.7, 4.8, "Asynchrone Inferenz & Worker", [
        "SearchWorker-Thread entkoppelt rechenintensive Suchen von der GUI.",
        "PyTorch TorchScript (CPU) für sub-20ms DLNMR1 Deep-Learning-Vorhersagen.",
        "Reiner NumPy Kuhn-Munkres Bipartite Matching Solver (< 0.1 ms).",
        "RDKit Cheminformatik-Pipeline für Fingerprints, MMFF94 und SMILES/InChI."
    ], "Asynchron & Multithreaded", ACCENT_PURPLE)

    add_card(slide12, 8.8, 1.8, 3.7, 4.8, "Daten-Engine & Formate", [
        "Apache Parquet mit Snappy-Kompression für Millionen Spektren in Sekundenbruchteilen.",
        "Binäre NumPy npz-Indizes für Precursor-m/z und Kernspin-Vorfilterung.",
        "Lokale SQLite-Datenbank für das Forschungs-Logbuch.",
        "Standard-Exporte: IUPAC JCAMP-DX 5.01, NIST MSP, CSV, SDF, HTML & PDF."
    ], "Parquet, SQLite & JCAMP", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 13: ANWENDUNGSSZENARIEN & ZIELGRUPPEN
    # =========================================================================
    slide13 = prs.slides.add_slide(blank_layout)
    add_header(slide13, "Typische Workflows & Zielgruppen in Labor & Lehre", "Anwendungsbereiche")

    add_card(slide13, 0.8, 1.8, 3.7, 4.8, "Synthesechemie & Qualitätskontrolle", [
        "Schneller Abgleich von Reaktionsprodukten mit über 3,37 Mio. Literatur-NMR-Spektren.",
        "Validierung von Isomerenreinheit via gespiegeltem Mirror-Plot.",
        "Zuordnung unbekannter Signale durch KI-Vorhersage ohne lange DFT-Rechenzeiten.",
        "Sofortiger PDF-Laborbericht zur Ablage in Laborjournalen und Veröffentlichungen."
    ], "Organische Synthese", ACCENT_CYAN)

    add_card(slide13, 4.8, 1.8, 3.7, 4.8, "Analytik & Metabolomics", [
        "Identifizierung unbekannter Metaboliten und Verunreinigungen in komplexen Proben.",
        "Durchmusterung von 1,75 Mio. MoNa Massenspektren nach Precursor-m/z.",
        "Interaktive Aufklärung von Spaltmustern durch den Neutral-Loss-Rechner.",
        "Kombination von MS-, IR- und NMR-Evidenzen für lückenlose Strukturbelege."
    ], "Bioanalytik & Spurenanalytik", ACCENT_AMBER)

    add_card(slide13, 8.8, 1.8, 3.7, 4.8, "Universitäre Lehre & Ausbildung", [
        "Didaktisch wertvolles Werkzeug für Studierende der Chemie, Pharmazie und Biochemie.",
        "Veranschaulicht physikalische Kopplungsmuster (Pascal-Bäume, Multipletts) stufenlos.",
        "Hands-on Erfahrung mit modernster chemischer KI und multimodalen Datenbanken.",
        "Völlig kostenfrei, portabel und ohne Lizenzbarrieren einsetzbar."
    ], "Didaktik & Hochschule", ACCENT_GREEN)

    # =========================================================================
    # SLIDE 14: FAZIT & AUSBLICK
    # =========================================================================
    slide14 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide14)

    # Header on slide 14
    add_header(slide14, "Zusammenfassung & Ausblick: Die Zukunft von HGTTD", "Fazit & Roadmap")

    add_card(slide14, 0.8, 1.8, 5.7, 4.8, "Highlights auf einen Blick", [
        "✓ 5,2+ Millionen Spektren: NMR (3,37M), MS (1,75M), IR (133k) & 54k 3D-Strukturen.",
        "✓ Autark & Lokal: Keine Cloud-Abhängigkeit, volle Datensicherheit für Forschung & Industrie.",
        "✓ KI-gestützte Strukturaufklärung: DLNMR1-Inferenz (< 20 ms) mit Kuhn-Munkres Matching.",
        "✓ Maximale Interaktivität: 60-FPS Canvas-Viewer, Cross-Highlighting, Mirror-Plot, Neutral-Loss.",
        "✓ Workflow-orientiert: Integriertes Ketcher, 3Dmol.js, SQLite-Logbuch & A4-PDF-Report."
    ], "Stärken von HGTTD", ACCENT_CYAN)

    add_card(slide14, 6.8, 1.8, 5.7, 4.8, "Ausblick & Zukünftige Entwicklungen", [
        "• Erweiterung der Deep-Learning-Modelle auf 19F- und 31P-Kerne.",
        "• 2D-NMR Spektren-Synthese (COSY, HSQC, HMBC) mit interaktiver Konturplot-Darstellung.",
        "• Automatisierte Spektren-Entfaltung (Peak-Deconvolution) für überlappende Signale.",
        "• Direkte Schnittstelle zu elektronischen Laborjournalen (ELN) und LIMS-Systemen.",
        "• Community-Plugins für anwenderspezifische Spektrometer-Treiber."
    ], "Roadmap", ACCENT_PURPLE)

    # Save presentation
    output_filename = "HGTTD_Praesentation.pptx"
    prs.save(output_filename)
    print(f"Presentation saved successfully as {output_filename}")

if __name__ == "__main__":
    create_presentation()

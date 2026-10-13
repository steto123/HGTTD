# 8.10.2026

## 4) Integration der MassBank of North America (MoNa)

Der **Implementierungsplan** für die freie Massenspektren-Datenbank **MassBank of North America (MoNa)** wurde erstellt und Phase 1 mit dem **Starter-Paket (44.696 Spektren)** vollständig umgesetzt.

Der vollständige Implementierungsplan ist als Dokument verfügbar:
📄 [implementation_plan_mona_integration.md](file:///C:/Users/wotan/.gemini/antigravity-ide/brain/32c46065-72b7-414c-b57e-fc6092d3ef3a/implementation_plan_mona_integration.md)

---

### Was wurde umgesetzt?

#### 1. Download- & High-Speed-Parquet-Pipeline ([mona_manager.py](file:///f:/projekte26/HGTTD/mona_manager.py))
* **Direkte REST-Schnittstelle:** Automatischer Bezug der Archive von der UC Davis API (`/rest/downloads/retrieve/{id}`).
* **Heruntergeladene Bibliotheken (Starter-Paket, ~50 MB ZIP):**
  * `MoNA-export-GC-MS_Spectra-msp.zip` (19.735 Spektren, Elektronenstoß-Ionisation EI 70 eV)
  * `MoNA-export-All_LC-MS-MS_Agilent_QTOF-msp.zip` (24.961 hochauflösende Tandem-MS Spektren)
  * **Gesamtumfang: 44.696 Spektren**.
* **Streaming-Parser:** Entpackt und parst NIST-MSP-Dateien direkt im Speicher (~5.000 Spektren/Sekunde), bereinigt SMILES/InChIKeys und standardisiert Addukte.
* **Kompakte Indizierung:**
  * `mona/mona_spectra.parquet` (50,0 MB Hauptdatenbank)
  * `mona/unique_smiles_index.parquet` (459 KB Vorfilter für RDKit-Substruktursuche)
  * `mona/mz_index.npz` (60 KB binärer Precursor-$m/z$-Index für $O(\log N)$ Intervallsuchen).

---

#### 2. Neuer interaktiver MS-Stick-Spektren-Viewer ([viewer_ms.py](file:///f:/projekte26/HGTTD/viewer_ms.py))
Massenspektren unterscheiden sich physikalisch und in der Darstellung von NMR-Spektren (diskrete Sticks/Balken statt kontinuierlicher Lorentz-Kurven, aufsteigende $m/z$-Achse von links nach rechts):
* **60 FPS HTML5-Canvas:**
  * Vertikale Signal-Balken mit relativer Intensität (0–100 %).
  * Farbcodierung: Neon-Cyan für Fragmente, Bernstein-Gold für den Basispeak (100 %) und Smaragdgrün für das Vorläuferion (Precursor $m/z$).
  * Schieberegler für **Cutoff-Schwelle** (0–25 %) zur Ausblendung von Rauschen.
  * Dynamische Beschriftung der Hauptsignale mit exaktem $m/z$.
* **Neutral-Loss Rechner (Werkzeug für Chemiker):**
  * Bei aktivierter Option `🔍 Neutral-Loss Messung` können zwei Peaks im Spektrum nacheinander angeklickt werden.
  * Das Werkzeug berechnet sofort $\Delta m/z$ und gleicht die Massendifferenz mit typischen Neutralverlusten ab:
    * $-18.0106\text{ Da} \rightarrow -\text{H}_2\text{O}$
    * $-27.9949\text{ Da} \rightarrow -\text{CO}$
    * $-17.0265\text{ Da} \rightarrow -\text{NH}_3$
    * $-43.9898\text{ Da} \rightarrow -\text{CO}_2$
    * $-15.0235\text{ Da} \rightarrow -\text{CH}_3$
    * $-60.0211\text{ Da} \rightarrow -\text{CH}_3\text{COOH}$ (Essigsäure) u. v. m.
* **Export-Funktionen:**
  * Export als standardkonformes **NIST `.msp`**.
  * Export als **IUPAC JCAMP-DX 5.01** (`##DATA TYPE= MASS SPECTRUM`).

---

#### 3. Multimodale Such- & UI-Integration ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py), [search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))
* **Quellenauswahl in der Suchleiste:**
  * `Beide Datenbanken (NMRexp + SDF)` (bisherig)
  * `NMRexp (3.37M)`
  * `nmrshiftdb2 (54k)`
  * **`MoNa MassBank (MS, 45k+ Spektren)`** *(Neu)*
  * **`Alle Quellen (NMRexp + SDF + MoNa)`** *(Neu: multimodale Gesamtsuche!)*
* **Ergebnisdarstellung für MoNa:**
  * Eigene Trefferkarten mit lila MoNa-Badge (`⚡ MoNa MassBank`), Ionisationsmodus (`Positive`, `Negative`, `EI`), Gerätetyp (`QTOF`, `EI-B`), Kollisionsenergie und Addukt (`[M+H]+`).
  * Tabelle der 8 intensivsten Fragment-Peaks.
  * Schaltfläche **`⚡ MS-Spektrum anzeigen`** öffnet direkt das Spektrum.
* **Rechtes Panel (Tab 3):**
  * Tab 0: `📋 Details`
  * Tab 1: `🔬 3D-Ansicht` (mit Kraftfeld-Minimierung)
  * Tab 2: `📈 NMR-Spektrum` (Lorentz-Synthese & est-NMR Auto-Assignment)
  * **Tab 3: `⚡ MS-Spektrum`** *(Neu: Interaktiver Stick-Viewer)*

---

#### 4. Dokumentation & Lizenznachweise ([README.md](file:///f:/projekte26/HGTTD/README.md), [protokoll.md](file:///f:/projekte26/HGTTD/protokoll.md))
* [README.md](file:///f:/projekte26/HGTTD/README.md) wurde um die formale Zitation und Lizenzbedingungen für **MoNa** (Oliver Fiehn Lab, UC Davis Genome Center, lizenziert unter **Creative Commons Attribution 4.0 International — CC BY 4.0**) erweitert.
* Das Entwicklungs- und Testprotokoll [protokoll.md](file:///f:/projekte26/HGTTD/protokoll.md) wurde auf den aktuellen Stand gebracht.

---

### Testen der neuen Funktion

Sie können die Anwendung wie gewohnt über [run.bat](file:///f:/projekte26/HGTTD/run.bat) starten:
1. Zeichnen Sie beispielsweise **Coffein** (`Cn1cnc2c1c(=O)n(c(=O)n2C)C`) oder ein Pyridinderivat im Ketcher-Editor.
2. Wählen Sie als Quelle **`MoNa MassBank (MS, 45k+)`** oder **`Alle Quellen`**.
3. Klicken Sie auf **`Struktur suchen`**.
4. In der Ergebnisliste sehen Sie die MoNa-Treffer mit $m/z$, Addukt und Fragmenttabelle.
5. Ein Klick auf **`⚡ MS-Spektrum anzeigen`** öffnet den interaktiven Stick-Viewer in Tab 3 mit Zoom und Neutral-Loss-Finder.


### 3)Implementierung Spektrenviewer

#### 1. Spektren-Synthese-Engine ([spectrum_generator.py](file:///f:/projekte26/HGTTD/spectrum_generator.py))
- **Signal-Parser:** Extrahiert chemische Verschiebungen ($\delta$), Multiplizitäten ($s, d, t, q, \text{quint}, dd, m$), Kopplungskonstanten ($J$) und Integrale für alle 6 Kerne der NMRexp-Datenbank (**¹H, ¹³C, ¹⁹F, ³¹P, ¹¹B, ²⁹Si**) sowie **¹³C** aus nmrshiftdb2.
- **Multiplett-Aufspaltung:** Erste-Ordnung-Pascal-Aufspaltungsbäume und Multiplett-Hüllkurven.
- **Lorentz-Faltung (Vektorisiert):** NumPy-basierte Vektor-Faltung für $N = 4096$ Datenpunkte in $< 2\text{ ms}$.
- **Integralkurve:** Stufenförmige kumulative Integralkurve für ¹H-NMR.
- **IUPAC JCAMP-DX 5.01 Exporter:** Erzeugt valide Standard-Dateien (`##XYDATA=(X++(Y..Y))`, `##PEAK TABLE`, Frequenzen, Kerne, Lösungsmittel).

#### 2. Spektren-Viewer-Widget ([viewer_spectrum.py](file:///f:/projekte26/HGTTD/viewer_spectrum.py))
- **Toolbar & Steuerelemente:**
  - **Linienbreiten-Regler (FWHM):** Slider ($0.2\text{ bis } 15.0\text{ Hz}$) und Spinbox für kontinuierliche Einstellung.
  - **Spektrometer-Frequenz:** Auswahl ($100 \dots 800\text{ MHz}$) zur Beobachtung feldabhängiger Multiplettaufspaltungen.
  - **Toggles:** `Peak-Labels` und `Integrale (¹H)` ein-/ausschaltbar.
  - **Aktionsbuttons:** `🎯 Reset Zoom`, `💾 JCAMP-DX Export` und `📋 Zurück zu Details`.
- **Interaktiver HTML5-Canvas-Renderer:**
  - **NMR-Konvention:** Absteigende X-Achse (hohe ppm links, tiefe/TMS 0 ppm rechts).
  - **Trace:** Neon-Cyan (`#38bdf8`) mit feinem Transparenzverlauf unter der Kurve.
  - **Integrale:** Bernstein-Gold (`#f59e0b`) mit Stufenhöhe.
  - **Interaktive Steuerung:**
    - **Mausrad:** Zoom horizontal zentriert auf Mauszeiger-Position.
    - **Shift + Mausrad / Rechtsklick-Ziehen:** Vertikale Intensitätsskalierung (Höhe der Peaks anpassen).
    - **Linksklick-Ziehen:** Spektrum horizontal verschieben (Pan).
    - **Doppelklick:** Zoom auf Vollansicht zurücksetzen.
    - **Fadenkreuz & Tooltip:** Anzeige von $\delta\text{ (ppm)}$, Signalform, $J$-Kopplung und Integral beim Überfahren von Peaks.
  - **60 FPS Client-Side Synthesis:** Slider-Bewegungen berechnen die Lorentz-Kurve sofort im Canvas ohne Verzögerung neu.

#### 3. Integration in die Benutzeroberfläche ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py) & [i18n.py](file:///f:/projekte26/HGTTD/i18n.py))
- **Tab 3 hinzugefügt:** `right_tabs` besitzt nun Tab 0 (`📋 Details`), Tab 1 (`🔬 3D-Ansicht`) und Tab 2 (`📈 Spektrum (Synthese)`).
- **Aktionsbuttons:**
  - Button `📈 Spektrum anzeigen` auf jeder Molekülkarte im NMRexp-Browser und in den Suchergebnissen.
  - Button `📈 Spektrum` in der oberen Browser-Leiste.
- **Zweisprachige Lokalisierung:** Vollständige deutsche und englische Übersetzungen für alle Bedienelemente und Tooltips.

### 2) Das Problem wurde analysiert und behoben.

---

### Ursache des Problems

1. **Chromiums 2-MB-Limitierung in `QWebEngineView.setHtml()`**:
   - Bei 100 Treffern mit vollständigen 2D-Molekül-SVGs und Spektrentabellen erreichte das generierte HTML ca. **2,68 MB**.
   - Die Qt-Methode `setHtml()` übergibt den Code intern als `data:`-URI an den Chromium-Renderer.
   - **Chromium verwirft `data:`-URIs > 2 MB stillschweigend.** Die Navigation schlug intern fehl und die Ladeseite mit dem Spinner blieb unverändert stehen, obwohl die Suche im Hintergrund bereits alle 100 Treffer ermittelt hatte.
2. **Attribut-Zugriff bei NMRexp-Ergebnissen**:
   - NMRexp-Treffer besitzen keine SDF-Validierungsflags (`validated`, `corrected`). Beim Zugriff konnte dies in bestimmten Fällen zu einem `KeyError` führen, der die Darstellung zusätzlich blockierte.

---

### Durchgeführte Behebungen

1. **Streaming über lokalen Cache ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py))**:
   - Neue Methode [set_results_html()](file:///f:/projekte26/HGTTD/main_window.py#L1997-L2015): Das HTML wird bei der Ergebnisdarstellung in `nmr_exp/.cache/results_view.html` abgelegt und über `self.results_view.load(QUrl.fromLocalFile(...))` gestreamt.
   - Dies umgeht das 2-MB-Limit von Chromium vollständig; auch Dokumente mit 100+ hochauflösenden Molekülkarten (> 2,68 MB) werden nun flüssig geladen.
2. **Sicherer Attributzugriff & Fehlerbehandlung ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py#L1742-L1743))**:
   - Absicherung durch `res.get("validated")` und `res.get("corrected")`.
   - Zusätzlicher Try-Catch-Block in [on_search_finished()](file:///f:/projekte26/HGTTD/main_window.py#L988-L994).
3. **Optimierte Dual-Suche ([search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py#L313-L323))**:
   - Wenn bei der Auswahl *„Beide Datenbanken“* das Trefferlimit (100) bereits durch NMRexp erreicht wurde, wird die Durchsuchung der 54.000 SDF-Verbindungen automatisch übersprungen. Das spart bis zu 5 Sekunden Rechenzeit.

---

### Test mit Ihrer Struktur

Die Suche mit der Struktur aus Ihrem Screenshot (`CC(C)=Cc1ccccc1`, Isobutenylbenzol) wurde im automatisierten End-to-End-Test geprüft:
- **Ergebnis:** Alle 100 Treffer (2,68 MB HTML) rendern nun vollständig, die Teilstrukturen leuchten in Cyan und der Ladespinner verschwindet sauber.

Bitte starten Sie das Programm neu (`run.bat`) und wiederholen Sie die Suche.

------------------------

### 1) Umgesetzte Kernfunktionen

#### 1. Kern-Beschränkung bei der Struktursuche
- **Such-Steuerung in der Kopfzeile ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py))**:
  - Neues Dropdown **`[Kern: Alle Kerne / 1H / 13C / 19F / 31P / 11B / 29Si]`** direkt in den Suchsteuerungen.
  - Intelligente Vorfilterung: Wird ein Kern gewählt, der nicht in **nmrshiftdb2** vorkommt (z. B. 19F, 31P, 11B, 29Si, 1H), wird der SDF-Suchlauf automatisch übersprungen, was Rechenzeit spart.
  - Bevorzugte Voreinstellungen werden automatisch in `config.json` über [config_manager.py](file:///f:/projekte26/HGTTD/config_manager.py) persistiert.

#### 2. Schnelle Substruktursuche & Trefferlimit
- **Suchmodus-Umschaltung**:
  - Umschaltung zwischen **`[🎯 Exakt]`** und **`[🧬 Substruktur]`**.
  - Wählbares Trefferlimit: **`[Limit: 50 / 100 / 250 / 500 / Alle]`** (Standard: 100 Treffer).
- **Index-Beschleunigung ([nmrexp_manager.py](file:///f:/projekte26/HGTTD/nmrexp_manager.py))**:
  - Erstellung des optimierten Vorfilter-Index `nmr_exp/unique_smiles_index.parquet` (14,8 MB) mit Bool-Flags für alle 6 Kerne.
  - Blitzschnelle Vorfilterung bei Substruktursuchen:
    - **²⁹Si NMR**: ~2.300 Moleküle (< 0,02 s)
    - **¹¹B NMR**: ~15.700 Moleküle (~0,05 s)
    - **³¹P NMR**: ~31.500 Moleküle (~0,10 s)
    - **¹⁹F NMR**: ~185.000 Moleküle (~0,50 s)
  - Zusätzlicher String-Vorfilter für Heteroatome (F, P, B, Si, S, Cl, Br, etc.) und Schweratom-Mindestanzahl.

#### 3. Visuelles Substruktur-Highlighting
- Übereinstimmende Teilstrukturen werden sowohl bei **NMRexp** als auch bei **nmrshiftdb2** in der 2D-Molekülansicht atom- und bindungsgenau in leuchtendem Cyan (`#38bdf8`) optisch hervorgehoben.
- In der Ergebnisliste signalisiert ein blaues Badge **`[🧬 Substruktur hervorgehoben (Cyan)]`** den Substrukturmodus.

#### 4. Asynchrone Suche & Sofort-Abbruch ([search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))
- Live-Fortschrittsmeldungen während des Suchlaufs (*„Substruktursuche: X / Y geprüft (Z Treffer)...“*).
- Roter **`[🛑 Stopp]`**-Button: Ermöglicht das sofortige saubere Abbrechen der Suche; alle bis dahin gefundenen Treffer werden unmittelbar dargestellt.

---

### Geänderte & erweiterte Dateien

- [main_window.py](file:///f:/projekte26/HGTTD/main_window.py): Einbindung der Kern-, Modus- und Limit-Auswahl, Stopp-Button, Substruktur-Ergebnisdarstellung und Zweisprachigkeit.
- [nmrexp_manager.py](file:///f:/projekte26/HGTTD/nmrexp_manager.py): Parquet- und Index-gestützte Substruktursuche mit RDKit-Highlighting und Kernfiltern.
- [search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py): Asynchroner Thread für exakte & Substruktursuche über beide Datenquellen mit Abbruchfunktion.
- [config_manager.py](file:///f:/projekte26/HGTTD/config_manager.py): Persistierung der Suchoptionen.
- [protokoll.md](file:///f:/projekte26/HGTTD/protokoll.md): Dokumentation der Tests und Ergebnisse.

---



# 7.10.2026

Die Integration der **NMRexp**-Datenbank und die Neugestaltung zu **HGTTD** (**Hitchhiker's Guide through the database**) wurden erfolgreich umgesetzt und getestet.

---

### Was wurde umgesetzt?

1. **Hauptfenster & Hitchhiker's Guide Startbildschirm ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py), [app.py](file:///f:/projekte26/HGTTD/app.py))**:
   - Das Hauptfenster trägt nun den Titel **HGTTD**.
   - Der neue Startbildschirm präsentiert den vollen Namen ***"Hitchhiker's Guide through the database"*** mit passender kosmischer Symbolik:
     - Prominentes goldenes **"DON'T PANIC"**-Badge mit sanfter Leuchtanimation.
     - Kosmisches Raum- und Sternen-Design mit 42-Lore.
     - Übersichtskarten für **NMRexp** (3,37 Mio. Spektren, 6 Kerne) und **nmrshiftdb2** (~54k Verbindungen mit 3D-Geometrien).
     - Direkte Schnellstart-Buttons: *Struktur zeichnen & suchen*, *Durch NMRexp blättern*, *Zufälliges Spektrum*.

2. **Hochleistungs-Engine für NMRexp ([nmrexp_manager.py](file:///f:/projekte26/HGTTD/nmrexp_manager.py))**:
   - Blitzschneller Zugriff auf die 3.372.987 Spektren der Datei `nmr_exp/NMRexp_10to24_1_1004.parquet`.
   - Vorkompilierter Kern-Index (`nuclei_index.npz`, 4,7 MB) für Ladezeiten von unter 3 ms bei Kernfiltern.
   - Vollständige Erfassung und Aufbereitung aller enthaltenen Kerne:
     - **¹H NMR** (1.667.135 Spektren): chemische Verschiebung, Multiplizität, Kopplungskonstanten $J$ (Hz) und Protonen-Integrale ($H$-Count).
     - **¹³C NMR** (1.455.670 Spektren): Verschiebung, Multiplizität und Kopplungskonstanten $J$.
     - **¹⁹F NMR** (197.186 Spektren)
     - **³¹P NMR** (33.456 Spektren inkl. `{1H}31P` und `P NMR`)
     - **¹¹B NMR** (17.143 Spektren inkl. `10B` und `B NMR`)
     - **²⁹Si NMR** (2.397 Spektren inkl. `Si NMR`)
   - Automatische DOI-Generierung (z. B. `https://doi.org/10.1021/acs.orglett.3c00718`) mit direkter Öffnung im Browser per Klick.

3. **Kern-gefilterter Datenbank-Browser ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py))**:
   - Umschaltbar über die Kopfzeile (`[ 🌌 NMRexp Blättern ]`).
   - Kernfilter-Auswahl (*Alle Kerne*, *¹H*, *¹³C*, *¹⁹F*, *³¹P*, *¹¹B*, *²⁹Si*).
   - Navigation: `⏮ Erste`, `◀ Vorherige`, Direkteingabe der Datensatznummer, `▶ Nächste`, `⏭ Letzte` sowie `🎲 Zufall` (Zufälliger Datensatz).
   - **`📥 In Ketcher laden`**: Überträgt das aktuell betrachtete Molekül per Klick direkt in den Ketcher-Editor.

4. **Wählbare Datenquelle bei der Struktursuche ([search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))**:
   - Der Anwender kann vor dem Suchlauf wählen:
     - `Beide Datenbanken (NMRexp + SDF)`
     - `NMRexp (Parquet, 3.37M Spektren)`
     - `nmrshiftdb2 (SDF, 54k Verbindungen)`
   - Einheitliche Darstellung der Treffer mit farbigen Badges für Quelle und Kern sowie tabellarischen Spektrendaten.

---

### Start der Anwendung:
Das Programm kann wie gewohnt über die Batch-Datei gestartet werden:
```cmd
run.bat
```

---

## Erweiterung: Kern-Beschränkung & Substruktursuche

Die Erweiterungen gemäß dem Implementierungsplan wurden vollständig umgesetzt und validiert:

### 1. Kern-Beschränkung bei der Struktursuche
- **Such-Header ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py))**:
  - Neues Dropdown `[Kern: Alle Kerne / 1H / 13C / 19F / 31P / 11B / 29Si]`.
  - Intelligente Vorfilterung: nmrshiftdb2 wird bei reinen Heterokern-Suchen (19F, 31P, 11B, 29Si, 1H) automatisch übersprungen.
  - Voreinstellungen werden persistent in `config.json` via [config_manager.py](file:///f:/projekte26/HGTTD/config_manager.py) gespeichert.

### 2. Schnelle Substruktursuche & Trefferbegrenzung
- **Suchmodus-Auswahl**:
  - Umschaltung zwischen `[🎯 Exakt]` und `[🧬 Substruktur]`.
  - Trefferlimit `[Limit: 50 / 100 / 250 / 500 / Alle]`.
- **Performance-Architektur ([nmrexp_manager.py](file:///f:/projekte26/HGTTD/nmrexp_manager.py))**:
  - Vorkompilierter, ultrakompakter Index `nmr_exp/unique_smiles_index.parquet` (14,8 MB) mit Bool-Flags für alle 6 Kerne.
  - Ladezeiten für Substruktursuche:
    - 29Si (~2.300 Moleküle): ~0,01 s
    - 11B (~15.700 Moleküle): ~0,05 s
    - 31P (~31.500 Moleküle): ~0,10 s
    - 19F (~185.000 Moleküle): ~0,50 s
  - Schneller Heteroatom- und Atomanzahl-Vorfilter schließt unpassende SMILES in Millisekunden aus.
- **Asynchrone Suche & Abbruch ([search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))**:
  - Live-Statusmeldungen: `Substruktursuche: X / Y geprüft (Z Treffer)...`
  - Roter `[🛑 Stopp]`-Button im Header zum sofortigen Abbrechen laufender Suchen; bisher gefundene Treffer werden sofort angezeigt.

### 3. Visuelle Substruktur-Hervorhebung
- In allen 2D-Molekülkarten (NMRexp und nmrshiftdb2 SDF) werden gefundene Teilstrukturen atom- und bindungsgenau in leuchtendem Cyan (`#38bdf8`) optisch hervorgehoben.
- Eindeutiges Kennzeichnungs-Badge `[🧬 Substruktur hervorgehoben (Cyan)]` im Kopf der Ergebnisliste.

---

## Fehlerbehebung: Ergebnisdarstellung bei 100 Treffern (Chromium 2-MB-Limit)

### Ursache des Problems
1. **Chromium IPC- / Data-URL-Limitierung in QWebEngineView**:
   - Bei 100 Treffern mit vollständigen 2D-SVGs, chemischen Verschiebungen und Spektrentabellen erreichte das generierte HTML ca. **2,68 MB**.
   - Die Qt-Standardmethode `setHtml(html)` kodiert das Dokument intern als `data:text/html;charset=UTF-8,...` Data-URI.
   - Chromium besitzt eine harte Obergrenze von 2 MB für Data-URLs bzw. Mojo-IPC-Meldungen. Dokumente > 2 MB wurden von Chromium lautlos verworfen, wodurch die vorherige Lade-Ansicht mit Spinner unverändert stehenblieb, obwohl der Worker 100 Treffer meldete.
2. **KeyError bei `res["validated"]` / `res["corrected"]`**:
   - NMRexp-Treffer enthalten nativ keine SDF-Validierungsflags; `res.get("validated") != "N/A"` war `True` für `None`, was beim direkten Indexzugriff zu einem KeyError führte.

### Behebung
1. **Dedizierter HTML-Cache-Loader (`set_results_html`)**:
   - In [main_window.py](file:///f:/projekte26/HGTTD/main_window.py) wird das HTML bei großen Datenmengen über eine lokale Cache-Datei (`nmr_exp/.cache/results_view.html`) via `self.results_view.load(QUrl.fromLocalFile(...))` gestreamt.
   - Dies umgeht das 2-MB-Data-URL-Limit von Chromium vollständig und lädt selbst hunderte Molekülkarten blitzschnell.
2. **Sicherer Attributzugriff & Fehlerbehandlung**:
   - Zugriff auf optionale Properties mit `res.get("validated")` und `res.get("corrected")` abgesichert.
   - `render_results` in `on_search_finished` in einen Try-Except-Block gekapselt, sodass bei Fehlern eine aussagekräftige Fehlerseite statt eines ewigen Spinners erscheint.
3. **Optimierte Dual-Suche ([search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))**:
   - Wurde das Trefferlimit (z. B. 100) bereits durch NMRexp erreicht, wird die Durchsuchung der 54.000 SDF-Verbindungen automatisch übersprungen, was mehrere Sekunden Rechenzeit spart.


---

## Interaktiver Spektren-Synthesizer & JCAMP-DX Exporter ([viewer_spectrum.py](file:///f:/projekte26/HGTTD/viewer_spectrum.py))

1. **Physikalische Lorentz-Synthese ([spectrum_generator.py](file:///f:/projekte26/HGTTD/spectrum_generator.py))**:
   - Echtzeit-Synthese physikalisch kontinuierlicher NMR-Spektren aus chemischen Verschiebungen, Multiplizitäten, J-Kopplungsmustern (d, t, q, m usw.) und Integralen für alle 6 Kerngruppen (¹H, ¹³C, ¹⁹F, ³¹P, ¹¹B, ²⁹Si).
   - Hardwarebeschleunigte 60-FPS-Darstellung auf HTML5-Canvas mit Schiebereglern für Linienbreite (FWHM in Hz), Spektrometerfrequenz (MHz) und kumulativer Integralkurve.
2. **Standardkonformer JCAMP-DX 5.01 Export**:
   - Export aller synthetisierten Spektren in IUPAC JCAMP-DX mit korrekten Header-Tags (AFFX, DELTAX, NPOINTS, PEAK TABLE) zur Weiterverarbeitung in Drittsoftware (MestReNova, TopSpin, Spekwin32).

---

## Standalone Auto-Assignment für ¹H- und ¹³C-NMR (est-NMR & DLNMR1)

1. **Lokale PyTorch-Umgebung & Standalone-Modell**:
   - `torch` (CPU-Build, Version 2.14.1+cpu) direkt in die lokale python-portable-Umgebung von HGTTD integriert.
   - TorchScript-Deep-Learning-Modell DLNMR1.pt (Wavefunction, Inc.) nach HGTTD/models/DLNMR1.pt kopiert. Das Modell läuft unabhängig ohne externe Projektpfade.
2. **Auto-Assignment Engine ([auto_assignment_engine.py](file:///f:/projekte26/HGTTD/auto_assignment_engine.py))**:
   - **Hybrid-Fragment Symmetrie-Ranking**: Zerlegung rotierbarer Bindungen und topologisch-geometrische Abstandssignaturen zur Unterscheidung echter Diastereotopie bei Erhalt rotierender Äquivalenzen.
   - **Symmetrie-Averaging**: Berechnung von Clustermittelwerten und theoretischen Entartungen/Integralen für ¹H und ¹³C.
   - **Kuhn-Munkres Bipartites Matching**: Exakter ungarischer Algorithmus (reines NumPy, Laufzeit < 0,1 ms) mit Shift- und Integral-Abstandsfunktion.
   - **Konfidenzbewertung**: Einstufung in *Sehr gut* (grün, z. B. Delta-Delta <= 3 ppm bei ¹³C / <= 0,15 ppm bei ¹H), *Mäßig* (gelb) und *Gering* (orange).
3. **UI- und Tabellen-Integration**:
   - **Details & Suchergebnisse ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py))**: Neue Spalten [Zuordnung (est-NMR)], [δcalc] und [Δδ] mit Farb-Badges sowie Status-Chips mit Signalquote und MAE (Mean Absolute Error). 2D-Moleküldarstellung zeigt farbcodierte Zuordnungs-Highlights.
   - **Spektren-Viewer ([viewer_spectrum.py](file:///f:/projekte26/HGTTD/viewer_spectrum.py))**: Checkboxen [🏷️ Auto-Zuordnung] (Kennzeichnung der Peaks mit Atom-Tags C1, 2H(C2,6)) und [📐 est-NMR Positionen] (theoretische Signalmarker zum direkten visuellen Vergleich). Rich-Tooltip bei Maus-Hover über Peaks.

---

## Projektdokumentation & Lizenznachweise ([README.md](file:///f:/projekte26/HGTTD/README.md))

- **Erstellung einer umfassenden Projektdokumentation** inklusive Architektur, Funktionsübersicht und Schnellstart.
- **Wissenschaftliche Zitate & Lizenzbedingungen**:
  - **NMRexp**: Formale Zitation des *Nature Scientific Data* Artikels (Wang et al., 2025, DOI: 10.1038/s41597-025-06245-5) unter CC BY-NC-ND 4.0.
  - **est-NMR & DLNMR1**: Formale Zitation des *J. Org. Chem.* Artikels (Hehre et al., 2025, DOI: 10.1021/acs.joc.4c02914) sowie Copyright- und Herkunftsnachweis für Wavefunction, Inc.
  - **nmrshiftdb2**: Zitation von Steinbeck et al. (JCICS 2003, DOI: 10.1021/ci0341527) unter CC BY-SA 4.0.
  - **MassBank of North America (MoNa)**: Formale Zitation des *J. Mass Spectrom.* Artikels (Horai et al., 2010, DOI: 10.1002/jms.1777) sowie UC Davis Genome Center / Fiehn Lab unter CC BY 4.0.
  - Übersicht aller Open-Source-Komponenten (RDKit, PySide6, PyTorch, Ketcher, 3Dmol.js, PyArrow, NumPy).

---

## Integration der MassBank of North America (MoNa)

1. **Implementierungsplan & Download-Pipeline ([mona_manager.py](file:///f:/projekte26/HGTTD/mona_manager.py))**:
   - Live-Abfrage der REST-Schnittstelle von UC Davis (`/rest/downloads/predefined` und `/rest/downloads/retrieve/{id}`).
   - Erfolgreicher Bezug des **Starter-Packs (~50 MB ZIP)**:
     - GC-MS EI-Spektren (19.735 Datensätze)
     - Agilent QTOF LC-MS/MS Spektren (24.961 Datensätze)
     - **Gesamt: 44.696 Spektren**.
   - Streaming-Parser für MSP-Archive: Direktes Parsen aus dem ZIP-Stream ohne Speicherüberlauf (~5.000 Spektren/Sekunde).
   - Generierung der optimierten Parquet-Datenbank `mona/mona_spectra.parquet` (50,0 MB).
   - Erstellung des Substruktur-Index `mona/unique_smiles_index.parquet` (459 KB) und des binären Massen-Index `mona/mz_index.npz` (60 KB).

2. **Interaktiver MS Stick-Spektren-Viewer ([viewer_ms.py](file:///f:/projekte26/HGTTD/viewer_ms.py))**:
   - 60-FPS HTML5-Canvas Renderer mit aufsteigender $m/z$-Achse und relativer Intensität (0–100 %).
   - Dynamische Peakbeschriftung der Hauptsignale, stufenloser Cutoff-Slider (0–25 %).
   - **Neutral-Loss Rechner**: Per Klick auf zwei Signale wird die Massendifferenz $\Delta m/z$ gemessen und mit einer Bibliothek typischer Neutralverluste ($-\text{H}_2\text{O}, -\text{CO}, -\text{NH}_3, -\text{CO}_2, -\text{SO}_3$ etc.) abgeglichen.
   - Standardkonformer Export nach **NIST MSP** und **IUPAC JCAMP-DX 5.01**.

3. **Multimodale Such- und UI-Integration ([main_window.py](file:///f:/projekte26/HGTTD/main_window.py), [search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py))**:
   - Neues Auswahlfeld in der Kopfzeile: `MoNa MassBank (MS, 45k+)` und `Alle Quellen (NMRexp + SDF + MoNa)`.
   - Schnelle Exakt- und Substruktursuche über MoNa mit RDKit-Highlighting im 2D-SVG.
   - Neuer Tab 3 `[⚡ MS-Spektrum]` in der rechten Ansicht.
   - Vollständige Zweisprachigkeit (DE/EN) in [i18n.py](file:///f:/projekte26/HGTTD/i18n.py).
   - Aktualisierung der [README.md](file:///f:/projekte26/HGTTD/README.md) mit MoNa-Quellennachweis (UC Davis, CC BY 4.0).

4. **Fehlerbehebung: Start-Absturz (TypeError in i18n-Signatur)**:
   - **Ursache:** Die Übersetzungsfunktion `t(key, **kwargs)` in [i18n.py](file:///f:/projekte26/HGTTD/i18n.py) akzeptierte bisher nur 1 positionales Argument (`key`), während in [viewer_ms.py](file:///f:/projekte26/HGTTD/viewer_ms.py) Aufrufe mit Default-String `t("key", "Standardwert")` stattfanden.
   - **Behebung:** Signatur von [t()](file:///f:/projekte26/HGTTD/i18n.py#L463-L478) auf `def t(key, default=None, **kwargs)` erweitert, Fallback-Handling implementiert, UI-Aufrufe in [viewer_ms.py](file:///f:/projekte26/HGTTD/viewer_ms.py) bereinigt und `retranslate_ui()` für den MS-Viewer integriert.

5. **Behebung der inkonsistenten Nummerierung bei der Auto-Zuordnung**:
   - **Ursache:** Das 2D-Molekülrendering verwendete 0-basierte RDKit-Indizes (`0, 1, ..., 9`), während die Zuordnungstabelle und die berechneten Symmetriegruppen nach chemischer Konvention 1-basiert nummerierten (`C1, C2, ..., C10`, `3H(C1)`, `2H(C6,10)`). Dadurch war Atom 0 im Bild in der Tabelle als C1 deklariert, Atom 3 als C4, Atom 9 als C10 etc. Bei ¹H-NMR fehlten zudem die visuellen Atom-Highlights, weil die Wasserstoffindizes (10..21) nicht auf das reine Schweratom-Gerüst abgebildet wurden.
   - **Behebung:**
     1. [auto_assignment_engine.py](file:///f:/projekte26/HGTTD/auto_assignment_engine.py):
        - Speicherung von `parent_heavy_indices` für alle Symmetriegruppen und Zuordnungen.
        - Deaktivierung der 0-basierten RDKit-Standardnummerierung (`addAtomIndices = False`) und explizite Vergabe konsistenter 1-basierter Atom-Labels (`1, 2, ..., N`).
        - Abbildung der ¹H-NMR-Signal-Highlights auf die korrekten Trägeratome (z. B. C1 für `3H(C1)`, C6/C10 für `2H(C6,10)`).
     2. [search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py) & [nmrexp_manager.py](file:///f:/projekte26/HGTTD/nmrexp_manager.py):
        - Umstellung von `draw_annotated_mol` und `draw_mol_svg` auf einheitliche 1-basierte Schweratom-Nummerierung (`i + 1`).
     3. [main_window.py](file:///f:/projekte26/HGTTD/main_window.py):
        - Anpassung des Fallback-Renderings für nmrshiftdb2-Atomindizes auf `C{idx+1}`.

6. **Integration der großen MoNa-Datenbank (All Experimental Spectra, ~1,75 Mio. Spektren)**:
   - **Datenumfang:** Vollständiger experimenteller Bestand der *MassBank of North America* (`MoNA-export-Experimental_Spectra-msp.zip`, 3,00 GiB / 3,22 GB, 1.756.800 Spektren).
   - **Streaming-Parquet-Pipeline ([mona_manager.py](file:///f:/projekte26/HGTTD/mona_manager.py)):**
     - Umstellung von der speicherintensiven Gesamtlisten-Konvertierung auf inkrementelle `pq.ParquetWriter`-Batches (25.000 Spektren pro Block). Der Arbeitsspeicherbedarf bleibt konstant unter 200 MB RAM.
     - Memoization-Cache für RDKit-SMILES-Kanonisierung und InChIKey-Generierung (`smiles_canon_cache`), wodurch redundante Strukturanalysen um > 95 % reduziert werden.
     - Live-Deduplizierung über ein In-Memory-ID-Set (`seen_ids`).
     - Parallele Erstellung des kompakten Substruktur-Indexes (`unique_smiles_index.parquet`) und des sortierten Vorläuferionen-Index (`mz_index.npz`).
   - **Automatischer Downloader & Compiler ([download_and_compile_mona.py](file:///f:/projekte26/HGTTD/download_and_compile_mona.py)):**
     - Streaming-Download mit 2-MB-Puffern, Live-Bandbreitenberechnung (MB/s), Restzeitanzeige (ETA) und ZIP-Integritätsprüfung.
     - Start als stabiler Hintergrund-Daemon.
   - **UI- & Einstellungs-Aktualisierung ([settings_dialog.py](file:///f:/projekte26/HGTTD/settings_dialog.py), [search_worker.py](file:///f:/projekte26/HGTTD/search_worker.py), [i18n.py](file:///f:/projekte26/HGTTD/i18n.py)):**
     - Dynamische Anzeige der installierten MoNa-Spektrenanzahl und Parquet-Dateigröße im Einstellungsdialog.
     - Dynamische Fortschrittsmeldungen bei der Suche (`Durchsuche MoNa MassBank (Substruktur, X Spektren)...`).
     - Bereinigung der Quellenauswahl auf `MoNa MassBank (MS-Datenbank)`.
   - **Fertigstellung & Validierung:**
     - Download erfolgreich in 26m 36s abgeschlossen (3,00 GiB / 3.219.805.004 Bytes).
     - Streaming-Kompilierung aller **1.756.800 Spektren** in 17m 53s abgeschlossen (`mona_spectra.parquet`: 2,31 GB; `unique_smiles_index.parquet`: 9,93 MB; `mz_index.npz`: 3,49 MB).
     - Exakt- und Substruktursuchen über die 1,75 Mio. Datensätze erfolgreich validiert (< 2 s).


---

# 9.10.2026

## 5) Benutzeroberflächen-, Layout- & Darstellungsoptimierungen

1. **Ketcher-Fenster Mindestbreite & Splitter-Dynamik (`main_window.py`):**
   - Feste Verankerung der Mindestbreite für den Ketcher-Editor: Das Ketcher-Fenster nimmt jetzt niemals weniger als ein Drittel (≥ 33,3 %) der gesamten Fensterbreite ein.
   - Intelligente Größenverteilung im `main_splitter` (Verhältnis 38 % Editor zu 62 % Arbeitsbereich).

2. **Multi-DPI- & Multi-Monitor-Stabilität:**
   - Qt-Attribute für High-DPI-Skalierung aktiviert (`AA_EnableHighDpiScaling`, `AA_UseHighDpiPixmaps`, Rounding-Policy `PassThrough`).
   - Beseitigung von Darstellungs- und Renderfehlern beim Umschalten virtueller Windows-Desktops oder beim Wechsel zwischen Monitoren unterschiedlicher Auflösung und DPI-Skalierung.

3. **MS-Spektren Peak-Tabellen & CSV-Export (`viewer_ms.py`):**
   - Aufklappbare, scrollbare tabellarische Übersicht aller MS-Peaks (auch bei sehr langen Peaklisten mit hunderten Fragmenten).
   - Zusätzlicher Ein-Klick-Export aller m/z- und Intensitätswerte als strukturierte **CSV-Datei** für externe Auswertungen (z. B. Excel, Origin, Python).

4. **Anwendungs-Icon & Titelleisten-/Menü-Aufräumung:**
   - Erstellung und Einbindung eines hochauflösenden kosmischen Anwendungs-Icons (`icon.ico` / `icon.png`).
   - Bereinigung der Kopfzeile: Einführung einer schlanken, professionellen Menüleiste (`Datei`, `Ansicht`, `Werkzeuge`, `Hilfe`) und Auslagerung von DB-Status sowie Einstellungs-Shortcuts in die moderne Fußzeile (Statusleiste).
   - Beseitigung redundanter/doppelter Icons in Menüs und Toolbars.

---

## 6) Implementierung der 5 großen Funktionserweiterungen

Alle 5 aufeinander aufbauenden Funktionen wurden erfolgreich und modular implementiert:

### 1. Persistentes Forschungs-Logbuch & Lesezeichen (`logbook_manager.py`, `logbook_widget.py`)
- **Lokale SQLite-Datenbank (`user_logbook.db`):**
  - Persistente Tabellen `molecules` (Lesezeichen, Notizen, Tags, Spektren-Metadaten) und `activity_log` (Suchen, Durchblättern, Spektrenansichten).
  - Daten überdauern das Schließen und Neustarten des Programms zuverlässig.
- **Neuer Tab `📔 Logbuch` (Shortcut `Alt+5`):**
  - Ansichten für Lesezeichen (`⭐ Favoriten`), Historie (`🕒 Verlauf`) und kombinierte Suche.
  - Notizen- und Tag-Editor direkt im Interface.
  - Direkte Aktionsbuttons zur Übergabe an Ketcher (`✏️ Ketcher`), den 3D-Viewer (`🔬 3D`) oder den Spektren-Synthesizer (`📈 NMR`).
- **Nahtlose Integration:** Lesezeichen-Toggle-Buttons (`⭐ Merken` / `★ Gemerkt`) in der Durchblättern-Ansicht und auf jeder Suchergebniskarte.

### 2. Tanimoto-Ähnlichkeitssuche mit ECFP4-Fingerprints (`nmrexp_manager.py`, `search_worker.py`)
- **Morgan Fingerprints:** Generierung von ECFP4-Fingerprints (Radius 2, 2048 Bit) via RDKit `rdFingerprintGenerator`.
- **Ultraschneller Ähnlichkeitsvergleich:** `BulkTanimotoSimilarity` über alle einzigartigen Moleküle des Index.
- **UI-Erweiterung:**
  - Neuer Suchmodus **`🔮 Ähnlichkeit`** im Modus-Dropdown der Hauptsuche.
  - Wählbarer Ähnlichkeits-Schwellenwert (≥60 %, ≥70 %, ≥80 %, ≥90 %).
  - Farbkodierte Badges (z. B. `🔮 86.4 %`) auf den Ergebniskarten mit absteigender Sortierung nach Relevanz.

### 3. Spektren-Vergleich & Split-View / Mirror-Plot (`viewer_spectrum.py`)
- **Referenz-Spektrum pinnen:** Mit `📌 Als Referenz merken` wird das aktuelle Spektrum im Speicher fixiert.
- **Spiegelbild-Vergleich (Mirror-Plot):** Bei aktivierter Checkbox `🪞 Vergleich (Mirror-Plot)` wird das Referenzspektrum invertiert unter der Basislinie in eleganter Korall-/Rosenfarbe (`#f43f5e`) eingeblendet.
- **Vergleichende Analyse:** Ermöglicht den direkten visuellen Struktur-Spektren-Abgleich von Isomeren, Derivaten oder experimentellen vs. berechneten Daten bei identischer Frequenz- und FWHM-Skalierung.

### 4. Interaktives Cross-Highlighting (NMR-Peak ↔ 3D- & 2D-Atom) (`viewer_spectrum.py`, `viewer_3d.py`, `main_window.py`)
- **Bidirektionales Hover & Click:** Beim Überfahren oder Anklicken eines Peaks im kontinuierlichen Canvas des NMR-Viewers wird ein JavaScript-Event `HGTTD_HIGHLIGHT:[indices]` über ein angepasstes `QWebEnginePage`-Routing ausgelöst.
- **3Dmol.js Live-Hervorhebung:** Die entsprechenden Atomzentren im 3D-Viewer werden in Echtzeit als goldene Sphären (`#f59e0b`) hervorgehoben und das Molekül automatisch passend zentriert.

### 5. Automatisierter Laborbericht (HTML/PDF-Export) (`report_generator.py`, `viewer_spectrum.py`, `main_window.py`)
- **Druckoptimiertes A4-Laborzertifikat:** Erzeugt ein professionelles, autarkes HTML-Dokument mit CSS `@page { size: A4 portrait; }`.
- **Inhalt des Berichts:**
  - Dokumentenkopf mit Zeitstempel, Probenbezeichnung, Datenbank-ID und DOI-Referenz.
  - Hochauflösende 2D-Strukturformel mit 1-basierter chemischer Atomnummerierung.
  - Physiko-chemische Kenndaten (Summenformel, Molekulargewicht, Lösungsmittel, Frequenz).
  - Vollständige Signal- und Zuordnungstabelle mit Verschiebungen, Multiplizität, Kopplungskonstanten, Integralen und Atomzuordnung.
  - Automatisch übernommene persönliche Notizen und Tags aus dem persistenten Logbuch.
- **Export-Schaltflächen:** `📑 Laborbericht (HTML/PDF)` direkt in der Molekül-Durchblättern-Ansicht sowie im NMR-Spektren-Viewer.

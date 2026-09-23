# 3D-Entwurf / Projektstudie — Gesamtkonzept

> **Die Produktregel.** Ein GIS beantwortet: *Was befindet sich auf diesem
> Grundstück?* Unser Produkt beantwortet: *Was könnte man hier entwickeln,
> wie sähe es räumlich aus, welche Flächen entstehen, und wie verändert
> sich die Wirtschaftlichkeit?* Deshalb ist die 3D-Ansicht nicht ansehbar,
> sondern entwickelbar.

Dieses Papier ist Bestandsaufnahme, Architekturentscheid und Bauplan. Es
beschreibt nichts, was nicht am Code geprüft wurde; wo etwas unklar ist,
steht das ausdrücklich da.

Stand: 23.09.2026, Code bei `8d80e0d`.

---

## A — Bestandsaufnahme: was schon da ist

Der wichtigste Befund zuerst, weil er die Planung umdreht: **es fehlt
sehr viel weniger, als der Auftrag vermuten lässt.** Fast jede Fähigkeit
einer Massing-Umgebung steckt bereits im Code. Sie arbeitet heute nur für
die Messung und für Szenarienkörper statt für einen eigenen Entwurf.

### Direkt weiterverwendbar, ohne Änderung

| Baustein | Wo | Wofür in B–K |
|---|---|---|
| `THREE.Scene` / `PerspectiveCamera` / `WebGLRenderer` | 3D-Modul, `bereitMachen()` | Bühne. `preserveDrawingBuffer` ist gesetzt — Bildexport funktioniert. |
| Eigene Orbitsteuerung mit verschiebbarem `blickpunkt` | `pointerdown/move/up`, `BLICK`-Vorgaben | Orbit, Neigen, Zoom 0.12–6.0, fünf feste Blickrichtungen. **Erledigt.** |
| `THREE.Raycaster` + `strahlSetzen()` + `szenenPunkt()` | Messmodul | Auswahl, Ziehen, Sofortprüfung — dieselbe Mechanik. |
| `griffAnfassen()` / `griffZiehen()` | Messmodul | Ziehmechanik für Körper. Schiebt nur einen anderen Wert. |
| `koerper(ring, mx, my, hoehe, farbe, deckkraft)` | 3D-Modul | Extrudat mit Kanten aus jedem Ring. |
| `szeneRahmen {mx, my, basis, spanne}` + `nachLv95()` | `zeichneSzene()` | Lokaler Meterrahmen ↔ LV95. Einmal hergeleitet, nirgends doppelt. |
| `terrainHoeheAn(t, e, n)` | 3D-Modul | Körper auf das Gelände setzen. |
| HTML-Beschriftungsschicht, je Bild projiziert | `messSchilderZeichnen()` | Live-Kennzahlen an der Geometrie, scharf bei jedem Zoom. |
| `u3dGruppen` + `setze3DSicht()` + `d3schalter()` | 3D-Modul | Ebenen einzeln schalten. |
| `ansichtLesen()` / `ansichtSetzen()` | 3D-Modul | Kamera, Ebenen, Sonne, Messungen speichern. |
| `verdrahte3DSteuerung()` | global | Einmal-Verdrahtung, übersteht `renderDossier()`. |
| `/umgebung` mit `umgebungFuerJob`-Bindung | Datenschicht | Terrain-Raster, Nachbargebäude mit Höhen, Strassen, Nachbarparzellen. |
| **Tabelle `variante`** mit `stand`, `variante_verlauf`, `basiert_auf_variante_id`, `ansicht_json` | `Crawler/kern/projekt.py` | **Variante A/B/C ist serverseitig fertig gebaut.** |
| Szenarienarten der Engine | `potenzial_engine/szenarien.py` | `bestand`, `sanierung`, `anbau`, `aufstockung`, `dachausbau`, `ersatzneubau`, `bestand_neubau` — alle sieben existieren. |

### Bereits erweitert (Schritte A, D, E der neuen Reihenfolge sind teilweise erledigt)

| Was | Stand |
|---|---|
| Eigener Reiter „3D-Entwurf" nach Potenzial, Bühne `clamp(460px, 64vh, 800px)` | `1b29632` |
| Dynamische Messwerkzeuge (live, Streckenzug, editierbare Stützpunkte) | `b08edea` |
| `+ Baukörper`: Rechteck erzeugen, auswählen, löschen, Drahtmodell-Darstellung | `8d80e0d` |
| Zweispaltige Tafel Projektstudie ↔ fachliche Prüfung | `8d80e0d` |

### Was wirklich fehlt

Nur fünf Dinge — und vier davon sind klein:

1. **Verschieben und Drehen ganzer Körper.** Die Ziehmechanik existiert,
   sie bewegt heute einen Punkt statt einen Körper.
2. **Masseingaben** (Breite, Tiefe, Geschosse, Geschosshöhe) als Felder
   und als Ziehgriffe an den Kanten.
3. **Abstand Punkt-zu-Strecke.** Die einzige noch fehlende Geometrie­funktion.
   `imPolygon()` ist seit `8d80e0d` da.
4. **Grenzabstandskorridor als Fläche.** Die Engine liefert die
   *Ergebnis*fläche (`baubereich_koordinaten`), nicht den Korridor
   dazwischen. Siehe C.
5. **`entwurf_json`** auf der Variante — die Studiengeometrie überlebt
   heute keinen Seitenwechsel.

### Was eine unnötige Neuentwicklung wäre

- **`OrbitControls` / `TransformControls`.** Die eigene Steuerung rechnet
  im Meterrahmen der Szene (Verschiebegeschwindigkeit aus
  `szeneRahmen.spanne`). Ein zugekaufter Griff müsste dieselbe Umrechnung
  ein zweites Mal machen — zwei Wahrheiten über dieselbe Geometrie.
- **Eine eigene Variantenverwaltung.** Ist gebaut, inklusive Verlauf.
- **Ein zweites Flächenmodell im Browser.** Siehe G.
- **Eine zweite Sonnenformel.** Steht getestet in `sonnenstand.py`.

---

## B — Die neue Ansicht

**Name.** Ich bleibe bei **„3D-Entwurf"**. „Projektstudie" ist die
*Eigenschaft* des Ergebnisses (und steht als Marke im Kopf des Reiters),
„3D-Entwurf" ist die *Tätigkeit*. Reiter heissen nach Tätigkeiten:
Übersicht, Baurecht, Karte, Potenzial, **3D-Entwurf**, Markt,
Wirtschaftlichkeit, Daten & Quellen.

**Aufteilung.** Von oben nach unten, Bühne im Mittelpunkt:

```
┌──────────────────────────────────────────────────────────┐
│ 3D-ENTWURF                              [Projektstudie]  │
│ Ein Satz: realer Bestand + Ihr Projektkörper             │
├──────────────────────────────────────────────────────────┤
│ SZENARIO   [Bestand][Sanierung][Anbau][Aufstockung][ENB] │  ← Engine-Szenarien
├──────────────────────────────────────────────────────────┤
│ UMGEBUNG  Terrain ▣ Gebäude ▣ Strassen ▣                 │
│ BAURECHT  Parzelle ▣ Grenzabstand ▣ Baubereich ▣ Baulin. │  ← neue Gruppe
│ PROJEKT   Szenarienkörper ▣ Projektstudie ▣              │
│ ENTWERFEN [+ Baukörper]                                  │
│ BLICK     Süd West Nord Ost Aufsicht Zurücksetzen        │
│ ANALYSE   ☐Sonne  Distanz Fläche Höhe Punkt              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│              3 D - B Ü H N E   (64vh)                    │
│         Beschriftungen liegen in der Szene               │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ Baukörper 1  14.0 × 22.0 m · 3 G · 9.00 m   [erfüllt] ×  │  ← Liste
├───────────────────────────┬──────────────────────────────┤
│ PROJEKTSTUDIE             │ FACHLICHE PRÜFUNG            │
│ aus der Geometrie         │ aus der Engine               │
│ Breite    [14.0] m        │ Baubereich    ✓ innerhalb    │  ← links Eingabe,
│ Tiefe     [22.0] m        │ Grenzabstand  ✓ 4.2 / 4.0 m  │    rechts Befund
│ Drehung   [ 18°]          │ Geschosse     ✓ 3 von 3      │
│ Geschosse [  3 ]          │ Gebäudehöhe   — n. bestimmbar│
│ Gesch.höhe[3.00] m        │ Ausnützung    — Engine       │
│ ─────────────────         │                              │
│ Grundfläche    308 m²     │                              │
│ Geschossfläche 924 m²     │                              │
│ Höhe          9.00 m      │                              │
├───────────────────────────┴──────────────────────────────┤
│ Messtafel · Legende · Navigationshinweis                 │
└──────────────────────────────────────────────────────────┘
```

Die **linke Spalte ist Eingabe und Projektion**, die **rechte ist
Befund**. Diese Trennung ist die wichtigste Gestaltungsentscheidung des
ganzen Reiters — sie darf nie verwischen, auch nicht durch eine
hilfreiche Zwischenzeile.

**Die Karte bleibt die Analysekarte.** Kein Projektierungswerkzeug dort.
Die einzige Verbindung ist ein Verweis in beide Richtungen.

### Darstellungssprache

Aus der Referenz (weisses Drahtmodell über dem realen Bestand):

| Element | Darstellung | Warum |
|---|---|---|
| Gelände | Fläche, 55 % deckend, Drahtnetz | Kontext, nicht Hauptsache |
| Nachbargebäude | Körper, stumpf, neutralgrau | Umfeld |
| Bestand auf der Parzelle | Körper, kräftiger grau | „das steht heute" |
| Parzelle | Rot, flach, Umriss stark | amtliche Grenze |
| Baubereich | Grün, flache Platte 0.25 m | Rechenergebnis |
| **Projektkörper** | **Drahtmodell**: Kanten voll, Füllung 13 %, Geschossebenen, **ohne Tiefenprüfung** | Man sieht den Bestand hindurch. Genau das macht ihn zum Vorschlag statt zum Gebäude. |
| Verletzung | dieselbe Geometrie in `--stop` | keine versteckte Korrektur, nur eine andere Farbe |

Ohne Tiefenprüfung heisst: das Drahtmodell liegt wie eine Folie über der
Szene. Nur so lässt sich eine **Aufstockung** zeigen, ohne den Bestand
auszublenden — und genau das tut die Referenz.

---

## C — Datenfluss: woher jeder Wert kommt

Drei Klassen, nie vermischt.

### 1 Aus der Engine (amtlich / berechnet) — wird gelesen, nie nachgerechnet

| Wert | Pfad im Ergebnis | heute in 3D? |
|---|---|---|
| Parzellenring | `modul1_geodaten.kataster.parzellengeometrie` | ja |
| Terrain-Raster, Nachbargebäude, Strassen | `/umgebung` | ja |
| Baubereich | `g1_ergebnis.ergebnis.baubereich_koordinaten` | ja |
| Zulässige Geschosszahl | `g1_ergebnis.ergebnis.geschosszahl` | ja |
| Geschosshöhe | `flaechen_und_wohnungen.…hoehenmodell.geschosshoehe_m.wert` | ja |
| Grenzabstände je Kante | `abstandsgeometrie` | **nein — fehlt in 3D** |
| Baulinien | `restriktionen.baulinien_gefunden[].geometrie_koordinaten` | **nein — fehlt in 3D** |
| Gewässerraum, Wald | `restriktionsflaechen_fuer_g1` | **nein — fehlt in 3D** |
| aGF, AZ, NWF, Wohnfläche, Reserve | `flaechen_und_wohnungen` | bewusst nicht |
| Szenarienkörper | `szenarien.szenarien[id].baukoerper` | ja |

### 2 Aus Entwurfsparametern gerechnet (Projektstudie) — darf im Browser laufen

Grundfläche = Breite × Tiefe. Geschossfläche = Grundfläche × Geschosse.
Höhe = Geschosse × Geschosshöhe. Volumen = Grundfläche × Höhe. Das ist
Arithmetik auf der eigenen Geometrie, kein Normwert — und wird als
**Projektstudie** gekennzeichnet.

### 3 Geometrische Sofortprüfung — die schmale dritte Klasse

Nur Aussagen, die aus **zwei vorliegenden Geometrien** eindeutig folgen:

- Punkt-in-Polygon: liegen alle Ecken im Baubereich? *(gebaut)*
- Abstand Ecke ↔ Parzellenkante, verglichen mit dem geforderten Wert
  aus `abstandsgeometrie` *(fehlt)*
- Schnitt Körper ↔ Baulinie / Gewässerraum *(fehlt)*
- Geschosszahl gegen `geschosszahl` *(gebaut)*

**Nicht** in dieser Klasse und deshalb im Browser verboten: anrechenbare
Geschossfläche nach SIA 416, Ausnützungsziffer, Gebäudehöhe nach
kantonaler Messweise, alles Reglementsabhängige.

### Der Grenzabstandskorridor — ein offener Punkt

Der Auftrag will die Kette *Parzelle → Korridor → Baubereich → Körper*
räumlich sehen. Die Engine liefert heute **Anfang und Ende**, nicht die
Zwischenstufe: `baubereich_koordinaten` ist das Ergebnis nach Abzug
aller Abstände.

Zwei Wege, und die Wahl gehört ausdrücklich nicht mir:

- **(a) Rein visuell.** Der Korridor ist die Differenzfläche Parzelle
  minus Baubereich. Die ist ohne neue Fachlogik zeichenbar und **exakt**,
  weil sie aus beiden Engine-Geometrien folgt. Sie zeigt aber nicht,
  *welcher* Abstand wo gilt.
- **(b) Je Kante beschriftet.** `abstandsgeometrie` kennt den Abstand je
  Kante. Der Korridor würde dann pro Kante eingefärbt und beschriftet.
  Das braucht ein zusätzliches Feld im Ergebnis — eine **Engine-Änderung**,
  die einen eigenen Auftrag verlangt.

Empfehlung: (a) jetzt, (b) später als eigener Block.

---

## D — Interaktionen nach Reifegrad

| | Zustand |
|---|---|
| **Heute möglich** | Orbit/Neigen/Zoom/Blickpunkt · feste Blickrichtungen · Ebenen schalten · vier Messwerkzeuge live und editierbar · Sonne & Schatten · Ansicht speichern · Körper erzeugen, auswählen, löschen · Prüfung Baubereich + Geschosse |
| **Technisch einfach erweiterbar** | Körper verschieben/drehen (Ziehmechanik da) · Masse ändern · Abstand zur Parzellenkante · Baulinien und Restriktionen als Ebene · Korridor als Differenzfläche · `entwurf_json` speichern |
| **Erst nach fachlicher Prüfung** | Geforderter Grenzabstand je Kante in 3D · Aufstockung auf dem Bestandsvolumen · Höhenrestriktionen · Server-Rückrechnung der aGF |
| **Derzeit nicht belastbar** | Gebäudehöhe nach kantonaler Messweise am freien Körper · Ausnützung im Browser · alles, was mehrere Reglementsauslegungen zulässt |

---

## E — Messwerkzeuge

**Ist bereits umgesetzt** (`b08edea`), live geprüft. Der Vollständigkeit
halber, weil der Auftrag es verlangt:

- Nach dem ersten Klick läuft das Mass mit der Maus mit und steht **an
  der Geometrie** — Segmentlängen an jeder Kante, Summe am Ende, Fläche
  in der Mitte. Gemessen live: `39.02 + 51.32 + 37.18 = Σ 127.52 m`;
  Fläche `3872 → 2714 m²` während der Bewegung.
- Distanz ist ein Streckenzug. Doppelklick beendet; der dabei doppelt
  gesetzte Punkt fällt weg.
- Stützpunkte sind greifbar, verschiebbar, einfügbar (halbe Kugeln auf
  den Kanten), löschbar (Alt + Klick).
- **Eine Rechenstelle:** `messWerte(art, punkte)`. Vorschau, Abschluss
  und Nachbearbeitung können nicht auseinanderlaufen.

**Leistung** — der Punkt aus Ziffer 15:

| Frage | Antwort im Code |
|---|---|
| Was passiert je `pointermove`? | Nur `messZeiger = {clientX, clientY}`. Sonst nichts. |
| Wann wird gestrahlt? | Einmal je Bild in `messTakt()`, aus der Bildschleife. Nie öfter. |
| Werden Geometrien unnötig erzeugt? | Die Messzeichnung entsteht neu, gibt aber die alten Geometrien frei (`messMuell`). Bei ~30 Objekten vertretbar. |
| DOM-Overlay? | Ein `innerHTML` je Bild für alle Schilder. Bei > 50 Schildern lohnt ein Wechsel auf feste Knoten mit `transform` — heute nicht nötig. |

**Für die Projektierung gilt dasselbe Prinzip.** Beim Ziehen eines
Körpers: ein Strahl je Bild, Neuzeichnen nur des Entwurfs (eigene
Gruppe), Kennzahlen aus reiner Arithmetik. Kein Serveraufruf während der
Bewegung.

---

## F — Vom Anschauen zum Entwickeln

Der Sprung besteht aus vier Dingen, nicht aus vielen:

1. **Ein Körper, der einem gehört.** Nicht aus dem Szenario abgeleitet,
   sondern selbst gesetzt — mit eigener Kennung, eigener Ebene, eigener
   Darstellung. *(gebaut)*
2. **Anfassen.** Auswählen, greifen, verschieben, drehen. Die Szene
   folgt sofort. *(Auswahl gebaut, Rest offen)*
3. **Folgen sehen.** Jede Änderung ändert sofort die linke *und* die
   rechte Spalte. Nicht: Klick → warten → Ergebnis.
4. **Die Grenze sehen, ohne von ihr korrigiert zu werden.** Verlässt der
   Körper den Baubereich, bleibt er stehen und wird rot. Kein Einrasten,
   kein Zurückspringen. Wer bewusst ausserhalb prüft, muss das dürfen.

### Szenarienabhängige Parameter

Der Auftrag verlangt, je Szenario nur sinnvolle Steuerungen zu zeigen.
Auf die vorhandenen Szenarienarten abgebildet:

| Szenario | `+ Baukörper` | Bestand | Zeigt zusätzlich |
|---|---|---|---|
| `bestand` | aus | sichtbar, voll | nichts — Betrachtung |
| `sanierung` | aus | sichtbar, voll | keine zusätzliche GF erzeugbar |
| `anbau` | an | bleibt sichtbar | Abstand Neubau ↔ Bestand |
| `aufstockung` | an, Sockel = Bestandshöhe | bleibt sichtbar | nur Geschosse/Höhe, Grundriss vom Bestand |
| `dachausbau` | aus | sichtbar | Hinweis: Volumen unverändert |
| `ersatzneubau` | an | durchscheinend als „heute" | volle Parameter |
| `bestand_neubau` | an | bleibt sichtbar | volle Parameter + Abstand |

### Varianten

**Keine neue Architektur.** Eine `variante` trägt eine Studiengeometrie:

```json
entwurf_json = {
  "rahmen": { "mx": 2754713.4, "my": 1260724.15, "basis": 398.0 },
  "koerper": [{ "id": "k1", "name": "Baukörper 1",
                "mitte": [-4.2, 11.8], "breite": 14.0, "tiefe": 22.0,
                "drehung_grad": 18.0, "geschosse": 3,
                "geschosshoehe_m": 3.0, "herkunft": "benutzer" }]
}
```

Gespeichert wie `ansicht_json`, **nicht** wie `eingaben_json`: wer einen
Körper zehn Zentimeter verschiebt, soll keinen Stand im Verlauf erzeugen.
Die Begründung steht schon bei `speichere_ansicht()`. Einen Stand erzeugt
erst „Entwurf festhalten" oder eine neue Variante daraus. Der Rahmen
gehört dazu, sonst läge der Körper beim nächsten Öffnen verschoben —
`pruefeRahmen()` gibt es bereits.

Variante A/B/C = drei Zeilen in der vorhandenen Tabelle, verbunden über
`basiert_auf_variante_id`.

---

## G — Wirtschaftlichkeit: 3D → Mengen → BKP → Ergebnis

### Was die Referenzunterlagen zeigen

Die beiden Beispiele wurden auf **Struktur** gelesen, nicht auf Inhalte;
keine Namen, Adressen, Parzellen oder projektspezifischen Werte werden
übernommen.

Die Architektenstudie ist ein Dreisatz, der genau unsere Kette ist:
*Kubatur → Verkaufsflächen → Ausnützungsziffer*, und am Ende steht ein
Satz der Form „AZ × Landfläche = zulässig, tatsächlich = x, übernutzt um
y m²". Das ist exakt die Aussage, die unsere 3D-Studie erzeugen soll.

Die Kalkulation ist nach BKP gegliedert und zeigt vier übertragbare
Konstruktionsprinzipien:

1. **Kostentreiber ist das Volumen, nicht die Fläche.** BKP 2 wird über
   m³ gerechnet, getrennt nach ober-/unterirdisch und „kalt".
2. **Nachgelagerte Gruppen sind Prozentsätze**, keine eigenen Schätzungen:
   Anschlussgebühren und Baunebenkosten als % von BKP 2+3, Reserve als %
   von BKP 2, Bauzinsen als % × Bauzeit × ½.
3. **Zwei Spalten nebeneinander** = zwei Varianten im selben Blatt.
4. **Im Kopf steht die Genauigkeit** (±25 %) und je Zeile, ob es eine
   Annahme ist. Genau diese Ehrlichkeit braucht unser Modell.

### Der Anschluss ohne doppelte Logik

```
3D-Projektkörper          Fussabdruck, Geschosse, Geschosshöhe, Drehung
        │                 → reine Projektionsgeometrie
        ▼
Flächenmodell (Engine)    GF, aGF nach SIA 416, NWF, Wohnfläche,
  sia416_flaechen.py      Ausnützung, Reserve
        │                 → EINZIGE Quelle dieser Zahlen
        ▼
Mengengerüst              GV oberirdisch = Fussabdruck × Höhe
                          GV unterirdisch = Annahme × Fussabdruck
                          Umgebungsfläche = Parzelle − Fussabdruck
                          Einstellplätze = f(GF)
        │
        ▼
Kostenmodell (neu)        BKP 1 / 2 / 4 / 5 / 6-7 / 8 aus Kennwerten
        │                 → Bandbreite, nie eine Zahl
        ▼
Wirtschaftlichkeit        vorhandenes Modul wirtschaftlichkeit.py
  (vorhanden)             Erlös, Anlagekosten, Gewinn, Marge, Landwert
```

**Die entscheidende Regel:** der Browser liefert dem Server
`{fussabdruck_m2, geschosse, geschosshoehe_m, drehung, ring}` — und
bekommt aGF, NWF und Ausnützung **aus dem vorhandenen Flächenmodell**
zurück. Es entsteht kein zweites SIA-416 im Browser. Das ist Schritt I
(Server-Rückrechnung) und der Grund, warum er vor K kommen muss.

Das Kostenmodell ist **neu**, aber es ist keine zweite Engine: es
verbraucht nur Mengen und Kennwerte und produziert keine baurechtliche
Aussage.

### Herkunft bleibt sichtbar

Fünf Stufen, wie im Marktreiter bereits etabliert:

| Stufe | Beispiel | Marke |
|---|---|---|
| Engine-Wert | aGF 924 m² nach SIA 416 | berechnet |
| Externe Benchmark | BKP 1–5 Median 974 CHF/m³ GV | Referenz + Quelle + Preisstand |
| Benutzereingabe | „wir rechnen mit 1'100" | Benutzerannahme |
| Annahme | Geschosshöhe 3.00 m mangels Angabe | angenommen |
| Reine Projektion | Geschossfläche 924 m² = 308 × 3 | Projektstudie |

Die Regel aus dem Marktblock gilt unverändert: **Systemvorschlag →
verwendet, solange keine eigene Annahme da ist; eigene Annahme hat
Vorrang.**

---

## H — Schweizer Baukosten: Quellen und Kennwerte

### Was gilt, was nicht

**SIA 116 ist seit 2003 ausser Kraft.** Kubaturen gehören nach **SIA 416**
gerechnet (`Flächen und Volumen von Gebäuden`). Ältere Kennwerte aus der
SIA-116-Zeit weichen ab und dürfen nicht ohne Umrechnung mit
SIA-416-Volumen verwendet werden. Unser Flächenmodell arbeitet bereits
nach SIA 416 — das ist die richtige Seite.

**CRB** (Zentralstelle für Baurationalisierung) führt mit dem
Objektartenkatalog die methodisch beste Schweizer Kennwertsammlung. Sie
ist **kostenpflichtig**. Solange nichts gekauft wird, fällt sie aus.

### Verwendbare Quellen

| Quelle | Art | Preisstand | Region | Stärke / Schwäche |
|---|---|---|---|---|
| **Wüest Partner / Lignum / BAFU, „Holzbaukennzahlen für Investoren — Wohnbauten"** (2025) | Studie, frei, PDF | **indexiert per 04.2023** | CH, nach Grossregion indexiert | **Beste freie Quelle**: 17 Holz- + Referenz-Massivbauten, **Quantile statt Mittelwerte**, Methodik offengelegt, inkl. MwSt, Tiefgarage getrennt. Schwäche: MFH ab 15 Wohnungen, kein EFH. |
| **BFS Schweizerischer Baupreisindex** | amtlich, frei | halbjährlich April/Oktober, publiziert Juni/Dezember | 7 Grossregionen | Der **Teuerungsschlüssel**, um jeden Kennwert auf heute zu bringen. Liefert keine absoluten Kosten. |
| aktiva.swiss Benchmarks | Zusammenstellung, frei | **kein Preisstand angegeben** | CH gesamt | Deckt EFH, MFH Miete/STWE, Büro, Tiefgarage, Rückbau, Sanierung. Schwäche: undatiert, keine Methodik → nur als grobe Plausibilisierung. |
| Kantonale Gebäudeversicherungen | amtlich | laufend | je Kanton | Neuwertkennzahlen. Für Bestand/Rückbau brauchbar. Noch nicht geprüft. |
| CRB Objektartenkatalog | Fachstelle | laufend | CH | Methodisch führend, **kostenpflichtig — nicht beschafft** |

### Kennwerte aus der belastbarsten freien Quelle

**Wohnbauten Neubau, Massivbau, Preisstand April 2023, inkl. MwSt, exkl.
Tiefgarage.** Quelle: Wüest Partner für Lignum/BAFU, 2025.

| Bezug | 10 % | 30 % | **Median** | 70 % | 90 % |
|---|---|---|---|---|---|
| **BKP 1–5 / m³ GV** | 701 | 846 | **974** | 1'137 | 1'548 |
| **BKP 1–5 / m² GF** | 1'994 | 2'666 | **3'043** | 3'354 | 4'413 |
| **BKP 1–5 / m² HNF** | 3'100 | 3'894 | **4'492** | 5'002 | 6'900 |
| **BKP 2 / m³ GV** | 640 | 808 | **898** | 1'047 | 1'474 |
| **BKP 2 / m² GF** | 1'834 | 2'390 | **2'801** | 3'188 | 4'215 |
| **BKP 2 / m² HNF** | 2'848 | 3'649 | **4'023** | 4'811 | 6'355 |

Zum Vergleich Holzbau 2023, BKP 1–5 / m³ GV: Median 1'066 (unteres
Preissegment 958, oberes 1'100).

**Umrechnungsfaktoren aus derselben Quelle** — wichtiger als die
Absolutwerte, weil unsere 3D-Studie GF erzeugt und die Kennwerte HNF
verlangen:

- Flächeneffizienz MFH: **HNF / GF oberirdisch ≈ 0.75**, Spanne 0.70–0.80;
  über 0.79 nur mit grossem Planungsaufwand.
- `GV := GV_oi + GV_ui − GV_Tiefgarage`, `GF := GF_oi + GF_ui − GF_Tiefgarage`.
- Tiefgarage, wenn nicht separat ausgewiesen: **BKP 2 ≈ 35'000, BKP 1–5 ≈
  42'000 je Einstellplatz**; Volumen ≈ GF × 2.70 m.
- Stellplatzbedarf ≈ **1 Platz je 100 m² GF oberirdisch**, **30 m² GF je
  Platz** (angelehnt an VSS-Parkierungsnorm 2022).
- **Bruttoanfangsrendite** Wohnliegenschaften, Transaktionen 2022–2023:
  10 % 2.58 · 30 % 3.25 · **Median 3.71** · 70 % 4.21 · 90 % 5.01 %.
- **Landanteil** an den Erstellungskosten BKP 1–9: bei den Fallbeispielen
  10–90 %. Diese Spannweite ist selbst das Ergebnis — ein fester
  Landanteil wäre eine Erfindung.

### Wie das Modell damit umgehen muss

1. **Nie eine einzelne Zahl.** Immer Median plus 30/70-Quantil als
   Bandbreite. Die Spannweite ist die Aussage.
2. **Immer auf heute indexieren**, über den BFS-Baupreisindex der
   passenden Grossregion, ausgehend vom dokumentierten Preisstand.
3. **Bezugsgrösse mitführen.** CHF/m³ GV, CHF/m² GF und CHF/m² HNF sind
   drei verschiedene Zahlen für dasselbe Gebäude.
4. **Jede Zeile trägt ihre Quelle**, ihr Jahr und ihren Einschluss
   (mit/ohne Tiefgarage, mit/ohne MwSt).
5. **Genauigkeit in den Kopf**, wie im Referenzblatt: eine frühe
   Machbarkeit ist ±25 %, und das soll dastehen.

Noch offen und zu beschaffen: EFH-Kennwerte aus einer datierten Quelle,
Sanierung/Umbau, Rückbau, Umgebung BKP 4, Honorare nach SIA 102/103.

---

## I — Der erste Prototyp

Der Beweis der Grundidee ist ein einziger Durchlauf, den man in zwei
Minuten vorführen kann:

> Adresse eingeben → Reiter 3D-Entwurf → reales Gelände mit Nachbarn,
> Parzelle, Baubereich → `+ Baukörper` → Körper **greifen und auf dem
> Grundstück verschieben** → er wird rot, sobald er den Baubereich
> verlässt → Breite und Geschosse ändern → Grundfläche, Geschossfläche
> und Höhe laufen mit → rechts steht, was die Engine dazu sagt und was
> sie nicht sagen kann.

Davon fehlt heute nur noch das **Greifen und Verschieben** und die
**Masseingaben** — beides Schritte F und G der Reihenfolge. Der Prototyp
ist damit **zwei Blöcke entfernt**, nicht elf.

---

## Reihenfolge

Ihre Reihenfolge ist fachlich richtig. Nach der Codeanalyse verschiebe
ich drei Dinge, jeweils mit Begründung:

| | Block | Stand | Änderung gegenüber Ihrem Vorschlag |
|---|---|---|---|
| A | 3D-Bühne / Navigation | **erledigt** | — |
| B | Dynamische Messwerkzeuge | **erledigt** | — |
| D | Baukörper auswählen | **erledigt** | **vorgezogen** — Auswahl fällt beim Erzeugen ohnehin an |
| E | Baukörper erzeugen | **erledigt** | **vorgezogen** — ohne Körper lässt sich Auswahl nicht prüfen |
| **F** | **Verschieben / drehen** | **als Nächstes** | — |
| **G** | **Breite / Tiefe / Geschosse / Höhe** | mit F zusammen | **zusammengelegt** — ein Körper, den man nur schieben, aber nicht bemassen kann, ist eine halbe Geste |
| **H** | Geometrische Sofortprüfung | danach | **teilweise vorgezogen**: Baubereich und Geschosse sind gebaut, Grenzabstand und Baulinie folgen hier |
| **C** | Räumliche Baurechtsgrenzen | **nach H** | **zurückgestellt** — der Korridor ist erst dann mehr als Dekoration, wenn ein Körper dagegen geprüft wird |
| I | Server-Rückrechnung | danach | — |
| J | Varianten | danach | — |
| K | Wirtschaftlichkeit / BKP | zuletzt | — |

Der Kern der Verschiebung: **F+G vor C.** Ein verschiebbarer, bemassbarer
Körper ist der Moment, in dem aus Anschauen Entwickeln wird. Der
Abstandskorridor ist eine Verfeinerung derselben Idee — er wird dadurch
wertvoll, dass etwas dagegen stösst.

---

## Offene Befunde

Drei Dinge aus dem Auftrag, geprüft, aber **nicht geändert**.

### Baulinien: zwei Zustände fallen zusammen

**Befund, am Code bestätigt.** `restriktionsgeometrie.py` liefert
`baulinien_gefunden: []` in **beiden** Fällen:

- Abfrage lief, es gibt keine Baulinie
- Abfrage ist fehlgeschlagen (nur ein deutscher Satz landet in `hinweise`)

Die Oberfläche ruft dann `setLayerVerfuegbar("baulinie", 0)` — die Ebene
wird ausgegraut und deaktiviert. Für den Benutzer sieht „hier gibt es
keine Baulinie" genauso aus wie „wir konnten nicht nachsehen". Das ist
genau der Fehler, den Sie beschreiben.

**Lösungsvorschlag.** Ein ausdrückliches Statusfeld in der Engine
(`baulinien_status: "geprueft_keine" | "gefunden" | "abfrage_fehlgeschlagen"
| "nicht_geprueft"`), und drei Darstellungen in der Leiste statt zwei.
Eine Engine-Änderung, also ein eigener Auftrag. Bis dahin liesse sich der
Fehlschlag notfalls am `hinweise`-Text erkennen — das wäre aber eine
Auswertung deutscher Prosa und damit selbst eine Fehlerquelle.

### Luftbild: die Verdachtsdiagnose trägt nicht

**Was der Code ausschliesst.** `setzeAnsicht()` tauscht ausschliesslich
Leaflet-Ebenen. Es fasst weder Containergrösse noch Layout noch
`invalidateSize` an. **Das Umschalten auf Luftbild kann die Kartenfläche
technisch nicht verkleinern.**

**Zwei verbleibende Erklärungen**, beide plausibel, keine bestätigt:

1. **Kachelabdeckung.** `ch.swisstopo.swissimage` läuft mit
   `maxZoom: 21, maxNativeZoom: 19`. Ab Zoom 20 werden Kacheln
   hochskaliert; fehlen sie, entstehen leere Bereiche — was wie
   „abgeschnitten" aussieht.
2. **Ein Grössenproblem, das nur auf dem Luftbild auffällt.** `#map` ist
   `position:absolute; inset:0` in einer Bühne, die beim Reiterwechsel
   wandert. Misst Leaflet zu früh, laden Kacheln für den Rest nie nach.
   Auf der grauen Grundkarte ist der Hintergrund `var(--panel-2)` —
   ebenfalls hellgrau, der Fehler fällt nicht auf. Auf einem Foto schon.
   **Das erklärt auch, warum ich den Fehler in drei Zuständen nicht
   reproduzieren konnte.**

**Vorgeschlagene Messung**, bevor irgendetwas umgebaut wird: direkt nach
dem Umschalten `map.getSize()` mit dem Containerrechteck vergleichen und
die geladenen Kacheln zählen, auf Zoom 17, 19, 20 und 21, in beiden
Bühnen. Erst das Ergebnis entscheidet zwischen (1) und (2) — die Fixe
sind verschieden.

### `/umgebung` hängt an der Reglementsauswertung

**Befund, bestätigt.** `webapp.py::_handle_umgebung()` verlangt
`job["status"] == "done"`. Schlägt die Gemini-Auswertung fehl, ist der
Job `teilweise` — und der Endpunkt antwortet 404, obwohl Gelände,
Nachbargebäude und Strassen aus swisstopo kommen und mit dem Reglement
nichts zu tun haben.

**Architektonische Bewertung.** Das ist dieselbe Kopplung, die Sie beim
Teilfehler-Block schon abgelehnt haben, eine Schicht tiefer. Die
3D-Umgebung ist fachlich unabhängig von der Reglementsauswertung: sie
braucht nur `parzellengeometrie` und die LV95-Koordinaten, und beide
liegen im Teilergebnis vor. Die Prüfung müsste also nicht auf den
Jobstatus zielen, sondern auf das Vorhandensein dieser beiden Felder.

**Nicht geändert.** `webapp.py`, Backend und Deploy bleiben unberührt,
bis Sie dafür einen eigenen Auftrag geben.

---

## Was bewusst offen bleibt

- **Kein CAD.** Keine Freiformgrundrisse, Dachformen, Fassaden,
  Geschossgrundrisse. Ein Massing beantwortet „passt das hierhin und wie
  wirkt es" — mehr soll es nicht.
- **Kein zweites Flächenmodell.** NWF, Wohnfläche, aGF und Reserve
  bleiben in der Engine, auch wenn die Versuchung gross ist.
- **Keine automatische Optimierung.** Kein „bestmöglicher Baukörper" auf
  Knopfdruck — das wäre eine fachliche Aussage, die niemand geprüft hat.
- **Keine gekaufte Kostenquelle**, solange nichts beschafft ist.

---

## Quellen

- [Wüest Partner für Lignum/BAFU: Holzbaukennzahlen für Investoren — Wohnbauten (2025)](https://timberfinance.ch/wp-content/uploads/2025/07/202504-Abschlussbericht_Holzbaukennzahlen_Wust-Partner.pdf)
- [BFS: Schweizerischer Baupreisindex](https://www.bfs.admin.ch/bfs/de/home/statistiken/preise/baupreise/baupreisindex.html)
- [aktiva.swiss: Kosten-Benchmarks Neubaukosten Immobilien Schweiz](https://aktiva.swiss/immobilien-benchmarks/)
- [ETH Zürich, Bauprozess: Kostenplanung](https://map.arch.ethz.ch/artikel/30/kostenplanung)
- [Espazium: Holzbau und sein ungleicher mineralischer Zwilling](https://www.espazium.ch/de/aktuelles/holzbau-wuest-partner-studie-kostenkennwerte)

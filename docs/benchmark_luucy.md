# LUUCY-Benchmark und Gap-Analyse

**Stand:** 12.09.2026 · **Status:** Grundlage für alle weiteren UI-Entscheidungen
**Vorgabe:** LUUCY = Mindeststandard, nicht Zielgrenze

## Wie diese Analyse zustande kam

Recherchiert wurden Produktseiten, Release-Notes, Preisseite, Hilfe-Center-Struktur
und Marktplatz-Ankündigungen von LUUCY. Das Hilfe-Center ist eine Single-Page-App;
einzelne Artikel liessen sich nicht direkt abrufen, ihre Inhalte stammen deshalb
teils aus Suchergebnis-Auszügen. Wo eine Angabe nicht belegt werden konnte, steht
das ausdrücklich dabei — geraten wurde nichts.

Quellen am Ende des Dokuments.

---

## Der zentrale Befund

**LUUCY ist eine 3D-Digital-Twin- und Modellierungsplattform. Die Wirtschaftlichkeit
kauft sie zu.**

Kosten, Marktdaten und Baupublikationen kommen bei LUUCY aus Marktplatz-Apps
**Dritter**: keeValue (Baukosten), Fahrländer Partner (Gemeindechecks, Lagerating),
Bindexis (Bauprojekte). Eigenentwickelt sind Bauziffern-Rechner, Kennzahlen-App und
ein einfacher Kostenrechner mit frei definierbaren Preisen.

Daraus folgt die strategische Lage in einem Satz:

> **Wir sind tief, wo LUUCY zukauft. LUUCY ist breit, wo wir fast nichts haben.**

Unsere Baurechts-, Geometrie-, Flächen- und Wirtschaftlichkeitskette ist
substanziell tiefer als das, was LUUCY selbst rechnet. Unsere Lücke liegt fast
vollständig im **Raum-, Projekt- und Arbeitsumfeld**: 3D-Umgebung, Modellierung,
Projektverwaltung, Präsentation, Export, Zusammenarbeit.

---

## Benchmark-Matrix

**A** vorhanden · **B** vorhanden, aber schwächer · **C** fehlt · **D** können wir besser

### 1 Einstieg, Navigation, Projektverwaltung

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Adress-/Ortssuche | **A** | Adresse → Geocoding → Parzelle, mit Punkt-in-Polygon-Auswahl |
| Parzelle auf Karte wählen | **A** | `/pick`-Endpunkt, Klick auf Karte |
| Projekte anlegen, benennen, verwalten | **C** | Wir haben Analysen je EGRID in `kern`, aber kein Projekt-Objekt und keine Projektübersicht |
| Projektübersicht / zuletzt bearbeitet | **C** | fehlt vollständig |
| Vorlagen (Templates) | **C** | fehlt |
| Arbeitsumgebungen / Workspaces | **C** | fehlt |
| Projekt löschen / archivieren | **C** | fehlt |
| Undo / Redo | **C** | fehlt (im Code kein einziger Treffer) |

### 2 Karte, Ebenen, Kartenmodi

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Pixelkarte / Grau / Luftbild | **A** | drei Basiskarten via swisstopo WMTS |
| Katasterplan als Ebene | **A** | `ch.kantone.cadastralwebmap-farbe` |
| Gebäudedaten als Ebene | **A** | GWR-Layer |
| Ebenen ein-/ausblenden, gruppieren | **B** | wir haben 6 schaltbare Gruppen, aber keine frei sortierbare/kombinierbare Ebenenverwaltung |
| Ebenen aus einem Marktplatz beziehen | **C** | kein Marktplatz, keine installierbaren Datensätze |
| Eigene Karten/Datensätze importieren | **C** | fehlt |
| Messen: Distanz, Höhendifferenz, Höhe über Terrain | **C** | fehlt vollständig |
| Koordinaten abgreifen (LV95/WGS84) | **B** | intern vorhanden, in der Oberfläche nicht abrufbar |
| Fussgängerperspektive | **C** | fehlt |
| Kameraansichten speichern | **C** | fehlt |

### 3 3D-Umgebung

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| 3D-Zwilling der ganzen Schweiz (Gelände, Gebäude, Vegetation) | **C** | wir zeigen nur Parzelle, Baubereich und Baukörper auf leerer Fläche |
| Terrain / Topografie | **C** | Höhenmodell wird für die Analyse abgefragt, aber nicht dargestellt |
| Nachbargebäude | **C** | Daten teilweise vorhanden (Katasterpolygone), nicht dargestellt |
| Strassen in 3D | **C** | TLM3D-Achsen werden für die Kantenklassifikation geholt, nicht gezeigt |
| Photorealistisches Terrain (Google 3D) | **C** | Premium-Funktion bei LUUCY |
| Navigation unter Terrain | **C** | fehlt |
| Schatten / Sonnenstand mit Zeitsteuerung | **C** | fehlt |
| Eigener Baukörper in 3D | **A** | aus berechneter Geometrie, nicht frei erfunden |
| 3D-Ansicht drehen/zoomen | **A** | Three.js, Drag und Scroll |

### 4 Modellierung

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Gebäude von Hand modellieren | **C** | unsere Körper entstehen ausschliesslich aus der Rechnung |
| Dachneigung frei einstellen | **C** | fehlt |
| Geschosse stapeln, Höhen anpassen | **B** | rechnerisch ja (Geschosszahl, Höhen), nicht interaktiv |
| Flächen / Polygone zeichnen | **C** | fehlt |
| Marker und Text setzen | **C** | fehlt |
| Objektbibliothek (Bäume, Bus, Bänke …) | **C** | fehlt |
| Objekte kopieren zwischen Varianten | **C** | fehlt |
| Style-Manager / Darstellung anpassen | **C** | fehlt |

### 5 Varianten und Szenarien

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Varianten innerhalb eines Projekts | **B** | wir haben **6 fachlich abgeleitete** Szenarien, aber keine frei benennbaren, gespeicherten Nutzer-Varianten |
| Varianten vergleichen | **A** | Szenariovergleich mit Machbarkeit, Flächen, Wohnungen, Kosten, Gewinn, Marge, Residualwert |
| Variantenvergleich exportieren (CSV) | **C** | fehlt |
| Variante duplizieren / abwandeln | **C** | fehlt |
| Baulich abgeleitete Szenarien | **D** | LUUCY modelliert von Hand — wir leiten Anbau, Aufstockung, Ersatzneubau **aus Bestand, Baurecht und Geometrie** ab, samt Konflikten und Begründung |

### 6 Baurecht und Kennzahlen

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Bauziffern automatisch rechnen, Grenzwert-Warnung | **A** | G1-Kaskade mit AZ/aBGF/ÜZ/BMZ und limitierender Grösse |
| Kennzahlen-App mit Detailansicht | **B** | wir zeigen mehr Kennzahlen, aber ohne Gebäude-für-Gebäude-Vergleich |
| Baulinien-Datensatz | **B** | wir holen Baulinien, weisen sie aber nur als Vorbehalt aus |
| Amtliche Vermessung | **A** | inkl. Punkt-in-Polygon-Parzellenauswahl |
| ÖREB, Schutz, Sondernutzung | **D** | 9 Kantone live, Sondernutzungsplan-Priorisierung, Rechtsvorschriften mit Zitat und Artikel |
| Reglement tatsächlich lesen | **D** | LUUCY nutzt Datensätze; wir werten das kommunale Reglement per LLM aus, mit Confidence und Fundstelle je Kennzahl |
| Kantenklassifikation je Grundstückskante | **D** | bei LUUCY nicht gefunden |
| SIA-416-Kette GF→NGF→NF→HNF→NNF→NWF | **D** | mit editierbaren, begründeten Annahmen statt Pauschalfaktoren |

### 7 Wirtschaftlichkeit und Markt

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Kostenrechner mit eigenen Preisen | **A** | BKP 1–6 plus Finanzierung und Vermarktung, jede Position mit sichtbarer Basis |
| Baukosten aus Partner-App (keeValue) | **D** | wir rechnen selbst, mit editierbaren Richtwerten |
| Marktdaten aus Partner-App (Fahrländer) | **B/D** | Struktur steht (Referenz / Systemvorschlag / Benutzerannahme, Sicherheitsgrad), **Datenbasis fehlt** |
| Lagerating | **C** | fehlt |
| Gemeindechecks | **C** | fehlt |
| Wohnungsmix, Wohnungszahl | **D** | bei LUUCY nicht gefunden |
| Verkauf / Miete / Rendite | **D** | bei LUUCY nicht gefunden |
| Gewinn, Marge, Zielmarge | **D** | bei LUUCY nicht gefunden |
| Residualwert / max. tragbarer Landpreis | **D** | **bei LUUCY nicht gefunden — unser stärkstes Alleinstellungsmerkmal** |

### 8 Zusammenarbeit

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Mehrere Nutzer, Rollen, Berechtigungen | **C** | fehlt |
| Gäste / Betrachter einladen | **C** | fehlt |
| Organisationen / zentrale Konten | **C** | fehlt |
| Projekt teilen (Link) | **C** | fehlt |

### 9 Präsentation und Bericht

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Präsentationen mit Folien bauen | **C** | fehlt |
| Präsentation als PDF exportieren | **C** | fehlt |
| Präsentation teilen | **C** | fehlt |
| Bericht / Dossier als PDF | **C** | fehlt (im Code kein einziger PDF-Treffer) |
| Bilder / Screenshots exportieren | **C** | fehlt |

### 10 Export und Import

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Projekt exportieren (Varianten wählbar) | **C** | fehlt |
| 3D-Daten exportieren (Ausschnitt wählbar) | **C** | fehlt |
| Kennzahlen als CSV | **C** | fehlt |
| Eigene Modelle importieren (DAE, OBJ, SHP, DXF, 3DS, IFC2x3) | **C** | fehlt |
| Eigene Datensätze/Karten importieren | **C** | fehlt |
| Marktdaten-Import (CSV, anbieterneutral) | **D** | haben wir seit Block A — LUUCY importiert Modelle, nicht Marktdaten |

### 11 Datenzugriff und Erweiterbarkeit

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| REST API | **B** | wir haben Endpunkte, aber keine dokumentierte, stabile API |
| SDK für Dritt-Apps | **C** | fehlt |
| Marktplatz für Apps und Datensätze | **C** | fehlt |
| Quellennachweis je Wert | **D** | Wert → Quelle → Dokument → Artikel → Zitat → Confidence; bei LUUCY nicht gefunden |

### 12 Bedienlogik

| LUUCY-Funktion | Wir | Bemerkung |
|---|---|---|
| Tastaturnavigation in 3D | **C** | fehlt |
| Mehrsprachigkeit (DE/FR/EN) | **C** | nur Deutsch |
| Ladezustände, Fehlerzustände | **B** | Job-Status vorhanden, aber ohne Fortschritt und ohne einheitliche Fehlerdarstellung |
| Reaktionszeit bei Änderungen | **D** | Markt-, Mix- und BKP-Änderungen in 7–90 ms, ohne erneute Geo-/LLM-Abfrage |

---

## Die vier Schlussfolgerungen

### 1 · Was unsere Engine mindestens können muss

Damit wir funktional nicht hinter LUUCY zurückfallen, braucht es **sieben Blöcke**,
von denen keiner die Rechenlogik betrifft — sie liegen alle im Arbeitsumfeld:

1. **Projekte** — Grundstücke als benennbare, wiederauffindbare Projekte mit
   Übersicht, nicht nur als Analyse je EGRID.
2. **Varianten** — frei benennbare, gespeicherte, duplizierbare Nutzer-Varianten
   **zusätzlich** zu unseren abgeleiteten Szenarien.
3. **Räumlicher Kontext in 3D** — Terrain, Nachbargebäude, Strassen. Ohne das
   bleibt unser Baukörper ein Würfel auf weisser Fläche.
4. **Sonne und Schatten** mit Zeitsteuerung.
5. **Messwerkzeuge** — Distanz, Höhendifferenz, Höhe über Terrain, Koordinaten.
6. **Export** — Projekt, Kennzahlen als CSV, 3D-Daten, Bilder.
7. **Bericht und Teilen** — Dossier als PDF, Link zum Weitergeben.

### 2 · Was unserem Crawler dafür konkret fehlt

Nachgeprüft im Code, nicht geschätzt:

* **Kein Projekt-Objekt.** `kern` kennt Grundstück, Auflösung und Analyse — aber
  keinen benannten Arbeitsstand, den ein Nutzer wiederfindet.
* **Keine gespeicherten Varianten.** Szenarien werden bei jedem Aufruf neu
  gerechnet; eine vom Nutzer abgewandelte und benannte Variante gibt es nicht.
* **Keine PDF-, Export- oder Download-Funktion.** Null Treffer im gesamten Dossier.
* **Keine Messwerkzeuge, kein Undo, kein Screenshot.** Ebenfalls null Treffer.
* **3D ohne Umgebung.** Die Geometrie stimmt, der Kontext fehlt: kein Terrain,
  keine Nachbarn, keine Strassen — obwohl wir die Daten für Nachbarparzellen und
  Strassenachsen bereits abfragen (Kantenklassifikation) und das Höhenmodell für
  die Topografie bereits nutzen. **Das ist der billigste grosse Sprung.**
* **Keine Mehrbenutzerfähigkeit.** Kein Teilen, keine Gäste, keine Rollen.
* **Nur Deutsch.**

### 3 · Was wir besser oder einfacher lösen sollten als LUUCY

* **Der Baukörper entsteht aus der Rechnung, nicht aus der Hand.** Bei LUUCY
  modelliert der Nutzer Volumen und bekommt danach Kennzahlen. Bei uns fällt der
  Baukörper aus Baurecht, Kantenabständen und Restriktionen heraus. Das ist
  weniger Arbeit **und** näher am rechtlich Zulässigen. Wir sollten trotzdem
  eine Hand-Korrektur zulassen — aber als Abweichung vom berechneten Vorschlag,
  mit sichtbarem Vergleich.
* **Ein Klick statt eines Werkzeugkastens.** LUUCY setzt Modellierkompetenz
  voraus. Unser Einstieg muss „Adresse → Ergebnis" bleiben; alles Weitere ist
  Vertiefung.
* **Nachvollziehbarkeit als sichtbares Merkmal.** Jede Zahl mit Quelle, Artikel,
  Zitat und Confidence — bei LUUCY nirgends gefunden. Das gehört nach vorn,
  nicht in einen Anhang.
* **Unsicherheit statt Scheingenauigkeit.** Unsere Sicherheitsgrade,
  Bandbreiten und „nicht bestimmbar"-Befunde sind ein Qualitätsmerkmal — sie
  müssen in der Oberfläche als solches erscheinen, nicht als Mangel.
* **Der Vergleich ist die Hauptansicht, nicht eine Unteransicht.** Sechs
  Szenarien nebeneinander mit Machbarkeit, Fläche, Wohnungen, Gewinn, Marge und
  Landwert — das beantwortet die eigentliche Frage.

### 4 · Was daraus einen echten Vorsprung macht

Aus der Master-Spezifikation, und bei LUUCY durchweg **nicht gefunden**:

| Funktion | Warum das ein Vorsprung ist |
|---|---|
| **Residualwert / max. tragbarer Landpreis** | beantwortet die Frage, die über den Kauf entscheidet |
| **Rückwärtsrechnung** „Was müsste sich ändern?" | macht aus einer Absage eine Verhandlungsgrundlage |
| **Wohnungsmix → Wohnungen → Verkauf/Miete** | LUUCY endet beim Volumen |
| **Sanierung als eigene Variante** | Bestandsentwicklung ist der grössere Markt |
| **Parzellenkombination A vs. A+B** | erkennt Zukaufschancen, die niemand von Hand sucht |
| **Grundstückssuche und Massensuche** | LUUCY analysiert ein bekanntes Grundstück; wir finden die unbekannten |
| **Abrissliste / Unternutzung** | der eigentliche Akquise-Hebel |
| **Anomalieprüfung** | „AZ = 20.0" wurde von uns bereits real gemeldet |
| **Risiko je Szenario mit Begründung** | keine Blackbox-Score |
| **Highest & Best Use** | verbindet alles zu einer Empfehlung |
| **Akquise-Signale auf EGRID** | Inserat, Preisänderung, Baupublikation am selben Schlüssel |

---

## Empfohlene Reihenfolge

Nach Wirkung je Aufwand, nicht nach Vollständigkeit:

1. **3D-Umgebung** (Terrain, Nachbargebäude, Strassen) — grösster sichtbarer
   Sprung, und die Daten liegen bereits vor.
2. **Projekte und benannte Varianten** — ohne sie ist alles Weitere flüchtig.
3. **Export und Dossier-PDF** — das erste, was ein Nutzer weitergeben will.
4. **Sonne/Schatten und Messwerkzeuge** — erwartete Selbstverständlichkeiten.
5. **Teilen und Mehrbenutzer** — sobald Projekte existieren.
6. **Marktdatenbasis füllen** — Struktur steht seit Block A, es fehlen Daten.

Die Punkte 1–4 schliessen die sichtbare Lücke zu LUUCY. Alles unter
Schlussfolgerung 4 baut den Vorsprung — **erst danach**, und nur auf dieser Basis.

---

## Quellen

* [LUUCY Product](https://www.luucy.ch/en/product/)
* [LUUCY Pricing](https://www.luucy.ch/en/pricing/)
* [LUUCY 2.6 Release](https://www.luucy.ch/en/erfahre-alles-ueber-luucy-2-6/)
* [Neuerungen in LUUCY](https://www.luucy.ch/neuerungen-in-luucy/)
* [App-Tipp Machbarkeitsstudien](https://www.luucy.ch/en/app-tipp-machbarkeitsstudien/)
* [Spatial Development](https://www.luucy.ch/en/solutions/spatial-development/)
* [LUUCY Hilfe-Center](https://help.luucy.ch/)
* [Fahrländer-Partner-Apps auf LUUCY](https://realestatemove.ch/2022/06/25/neue-apps-von-fahrlaender-partner-und-luucy/)

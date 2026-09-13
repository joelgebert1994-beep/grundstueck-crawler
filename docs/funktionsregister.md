# Funktionsregister — was das Werkzeug kann, was fehlt, was kommt

**Führende Übersicht. Bei jedem Block zu aktualisieren.**
**Stand:** 12.09.2026 · nach Block 5

Dieses Dokument ist die **eine** Stelle, an der der Gesamtstand steht. Die
technischen Block-Dokumentationen (`block1_*.md` … `block5_*.md`,
`stufe2_*.md` … `stufe5_*.md`) bleiben daneben bestehen und gehen ins Detail;
sie ersetzen dieses Register nicht und es ersetzt sie nicht.

Verwandte Dokumente:
* [`zielbild.md`](zielbild.md) — die verbindliche Produktspezifikation (65 Abschnitte)
* [`benchmark_luucy.md`](benchmark_luucy.md) — die LUUCY-Analyse mit Quellen

## Legende

| Zeichen | Bedeutung |
|---|---|
| ✅ | **implementiert** — gebaut, getestet, im Browser geprüft |
| 🟡 | **teilweise** — nutzbar, aber ein benannter Teil fehlt |
| 📋 | **geplant** — vorgesehen, noch nicht gebaut |
| ⏸️ | **bewusst zurückgestellt** — mit Begründung, kommt später |
| ❌ | **nicht sinnvoll** — mit Begründung, kommt nicht |

---

## Architekturprinzipien — nicht verhandelbar

Diese Regeln sind mehrfach teuer erkauft worden. Wer sie bricht, macht
Bestehendes kaputt.

1. **Eine Kette, keine Parallelwelten.**
   `EGRID → amtliche Basis → Analyse → Szenario → Variante → Berechnung → Visualisierung`
   Keine zweite Engine, keine zweite Wirtschaftlichkeitslogik, kein paralleles
   Datenmodell.

2. **Drei Herkunftsstufen, immer sichtbar.**
   `Referenzdaten → Systemvorschlag → Benutzerannahme`. Die Benutzerannahme
   gewinnt, aber sie wird als solche gekennzeichnet — auch im Bericht.

3. **Niemals eine Zahl erfinden.** Nicht verfügbar → „nicht verfügbar".
   Mehrdeutig → „unsicher". Prüfung nötig → „manuelle Prüfung". Eine 0 statt
   eines fehlenden Werts ist eine Behauptung.

4. **Eine Variante ist ein Delta, keine Kopie.** Gespeichert wird nur, was der
   Benutzer gesetzt hat. Was fehlt, kommt vom System — dadurch bleibt die
   Herkunft ohne Zusatzaufwand erhalten.

5. **Amtliche Basisdaten werden nicht dupliziert.** Sie sind über den EGRID
   reproduzierbar. Eine mitgespeicherte Momentaufnahme veraltet still.

6. **Die Ansicht ist keine Annahme.** Kamera, Ebenen, Sonnenstand und
   Messungen ändern keine Zahl. Sie stehen in einem eigenen Feld, zählen nicht
   als Benutzerwert und erzeugen keinen Verlaufsstand — sonst wäre der Verlauf
   nach einer Minute Arbeit unbrauchbar.

7. **Rechnen an einer Stelle, darstellen an einer anderen.** Der Bericht liest
   Ergebnisse, er rechnet sie nicht nach. Der Browser stellt den Sonnenstand
   dar, er berechnet ihn nicht.

8. **Nichts wird still überschrieben.** Jeder Speichervorgang legt einen Stand
   an; der Ausgangszustand ist selbst ein Stand.

9. **Unbekannte Eingabe → Fehler. Unbekannte Ansicht → verwerfen.** Eine
   verlorene Benutzerannahme ist Datenverlust; eine verworfene Kameraposition
   kostet nichts und hält ältere Versionen lesefähig.

---

## Teil 1 — Der Workflow

Das Ziel: **finden → analysieren → Varianten → visualisieren → vergleichen →
rechnen → speichern → exportieren → teilen**

| Schritt | Stand | Bemerkung |
|---|---|---|
| **finden** | 🟡 | Adresse und Kartenklick ✅ · Grundstückssuche und Screening 📋 |
| **analysieren** | ✅ | Baurecht, Geometrie, Flächen, Wohnungen vollständig |
| **Varianten** | ✅ | anlegen, benennen, duplizieren, umbenennen, löschen, Deltas |
| **visualisieren** | ✅ | 2D-Karte, 3D mit Terrain/Nachbarn/Strassen, Sonne, Schatten |
| **vergleichen** | ✅ | Variantenvergleich mit 9 Kennzahlen |
| **rechnen** | ✅ | BKP, Erlös, Gewinn, Marge, Residualwert |
| **speichern** | ✅ | Projekt, Varianten, Verlauf, Arbeitsstand der Ansicht |
| **exportieren** | ✅ | PDF, PNG, CSV, JSON (wieder importierbar) |
| **teilen** | 🟡 | Datei-Weitergabe ✅ · Link/Mehrbenutzer ⏸️ |

---

## Teil 2 — LUUCY-Matrix als Checkliste

Die Nummerierung folgt [`benchmark_luucy.md`](benchmark_luucy.md).
Die Spalte **Damals** ist die Einstufung der Erstanalyse (vor Block 1).

### 1 Einstieg, Navigation, Projektverwaltung

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Adress-/Ortssuche | A | ✅ | Geocoding → Parzelle, Punkt-in-Polygon |
| Parzelle auf Karte wählen | A | ✅ | `/pick` |
| Projekte anlegen, benennen, verwalten | C | ✅ | Block 2 |
| Projektübersicht / zuletzt bearbeitet | C | ✅ | „Meine Projekte", nach Änderung sortiert |
| Projekt löschen | C | ✅ | Block 2 |
| Projekt archivieren | C | ⏸️ | Löschen genügt bei der aktuellen Projektzahl |
| Vorlagen (Templates) | C | ⏸️ | Die fünf Standardvarianten sind faktisch die Vorlage |
| Arbeitsumgebungen / Workspaces | C | ❌ | Setzt Mehrbenutzerbetrieb voraus — ohne Organisationen sinnlos |
| **Undo / Redo** | C | 🟡 | Verlauf und Wiederherstellung ✅ · Bedienung fehlt 📋 |

### 2 Karte, Ebenen, Kartenmodi

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Pixelkarte / Grau / Luftbild | A | ✅ | swisstopo WMTS |
| Katasterplan als Ebene | A | ✅ | |
| Gebäudedaten (GWR) als Ebene | A | ✅ | |
| Ebenen ein-/ausblenden | B | ✅ | drei Gruppen in 3D, Ebenenliste in 2D |
| Ebenen frei sortieren/kombinieren | B | ⏸️ | Feste Reihenfolge ist fachlich richtig sortiert |
| Ebenen aus einem Marktplatz | C | ❌ | Kein Marktplatz — siehe Abschnitt 11 |
| Eigene Karten importieren | C | 📋 | |
| **Messen: Distanz** | C | ✅ | Block 4, waagrecht und schräg |
| **Messen: Fläche** | C | ✅ | Block 4, waagrechte Projektion |
| **Messen: Höhe** | C | ✅ | Block 4 |
| **Koordinaten abgreifen** | B | ✅ | Block 4, LV95 und m ü. M. |
| **Messungen speichern** | – | ✅ | Block 5, je Variante |
| Fussgängerperspektive | C | 📋 | |
| **Kameraansichten speichern** | C | ✅ | Block 5, je Variante ein Arbeitsstand |
| Mehrere benannte Kameraansichten | – | 📋 | Ein Stand je Variante deckt den Alltag |

### 3 3D-Umgebung

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Terrain / Topografie | C | ✅ | Block 1, Höhenmodell, 16 statt 256 Abfragen |
| Nachbargebäude | C | ✅ | Block 1, aus dem Gebäuderegister |
| Strassen in 3D | C | ✅ | Block 1, TLM3D |
| Nachbarparzellen | C | ✅ | Block 1 |
| Eigener Baukörper in 3D | A | ✅ | aus der Rechnung, nicht aus der Hand |
| 3D drehen/zoomen | A | ✅ | |
| **Schatten mit Zeitsteuerung** | C | ✅ | Block 4, echtes Datum und echte Uhrzeit |
| Vegetation | C | 📋 | |
| Photorealistisches Terrain (Google 3D) | C | ❌ | Lizenzkosten ohne fachlichen Gewinn |
| Navigation unter Terrain | C | ❌ | Kein Anwendungsfall im Hochbau |

### 4 Modellierung

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Gebäude von Hand modellieren | C | ⏸️ | **Bewusst:** unsere Körper entstehen aus der Rechnung. Geplant als *Abweichung vom berechneten Vorschlag* mit sichtbarem Vergleich — nicht als freies Modellieren |
| Dachneigung frei einstellen | C | 📋 | |
| Geschosse stapeln, Höhen anpassen | B | 🟡 | rechnerisch ✅, interaktiv 📋 |
| Flächen / Polygone zeichnen | C | 🟡 | Messfläche ✅, als Entwurfsfläche 📋 |
| Marker und Text setzen | C | 📋 | |
| Objektbibliothek (Bäume, Bänke) | C | ❌ | Ausstattung ändert keine Kennzahl |
| Style-Manager | C | ⏸️ | UI-Polish, nach dem Funktionsumfang |

### 5 Varianten und Szenarien

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Varianten im Projekt | B | ✅ | Block 2, frei benennbar |
| Varianten vergleichen | A | ✅ | 9 Kennzahlen nebeneinander |
| Variantenvergleich als CSV | C | ✅ | Block 3 |
| **Variante duplizieren** | C | ✅ | Block 2, mit Herkunftsbezug |
| **Variante umbenennen** | – | ✅ | Block 5 |
| **Variante löschen** | – | ✅ | Block 5, letzte Variante geschützt |
| Baulich abgeleitete Szenarien | D | ✅ | unser Vorsprung |
| **Sanierung als Szenario** | – | ✅ | Block 8 · einziges Szenario ohne Ausnützungsverbrauch — bleibt möglich, wo das Budget überschritten ist |
| Objekte zwischen Varianten kopieren | C | 🟡 | Ansicht und Annahmen ✅ beim Duplizieren |

### 6 Baurecht und Kennzahlen — durchgehend ✅ oder Vorsprung

| Funktion | Damals | Heute |
|---|---|---|
| Bauziffern, Grenzwertwarnung | A | ✅ |
| Amtliche Vermessung | A | ✅ |
| ÖREB, Schutz, Sondernutzung | D | ✅ 9 Kantone |
| Reglement per LLM auswerten | D | ✅ mit Fundstelle und Confidence |
| Kantenklassifikation | D | ✅ Stufe 2 |
| SIA-416-Kette | D | ✅ Stufe 3 |
| Baulinien | B | 🟡 geholt, als Vorbehalt ausgewiesen — nicht geometrisch verschnitten 📋 |
| Kennzahlen Gebäude für Gebäude | B | 📋 |

### 7 Wirtschaftlichkeit und Markt

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Kostenrechner BKP 1–6 | A | ✅ | Stufe 5 |
| Wohnungsmix, Wohnungszahl | D | ✅ | Stufe 3, ohne Bruchteilwohnungen · Herkunft Vorschlag/Annahme getrennt (Block 6) |
| Verkauf / Miete / Rendite | D | ✅ | Stufe 5 |
| Gewinn, Marge, Zielmarge | D | ✅ | Stufe 5 |
| **Residualwert** | D | ✅ | stärkstes Alleinstellungsmerkmal |
| Marktmodell (3 Ebenen) | B/D | ✅ | Struktur Block A · **Erfassung in der Oberfläche (Block 7)** — die Endpunkte gab es seit Block A, sie wurden nie aufgerufen |
| Eigene Vergleichsobjekte | – | ✅ | Block A + Block 7: Einzelerfassung, CSV-Einfügen, Liste, Löschen — Quelle und Datenstand Pflicht |
| Lagerating | C | 📋 | |
| Gemeindechecks | C | 📋 | |
| **Rückwärtsrechnung** | – | ✅ | Block 9 · vier Stellschrauben, Einordnung gegen erfasste Vergleichsobjekte |
| **Highest & Best Use** | – | 📋 | verbindet alles zu einer Empfehlung |

### 8 Zusammenarbeit

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Projekt weitergeben | C | ✅ | als JSON-Datei, wieder importierbar |
| Projekt teilen (Link) | C | ⏸️ | Braucht Server mit Konten — als lokales Werkzeug kein Adressat |
| Mehrere Nutzer, Rollen | C | ⏸️ | dito |
| Gäste / Betrachter | C | ⏸️ | dito |
| Organisationen | C | ⏸️ | dito |

> **Begründung:** Das Werkzeug läuft heute lokal ohne Anmeldung. Ein „Teilen"
> ohne Konten wäre entweder wirkungslos oder ein offener Zugang. Die
> Weitergabe läuft deshalb bewusst über Datei und PDF — beides vollständig.
> Sobald ein Serverbetrieb ansteht, wird dies der erste Block.

### 9 Präsentation und Bericht

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Bericht / Dossier als PDF | C | ✅ | Block 3, 12 Abschnitte |
| Bilder exportieren | C | ✅ | Block 3, 3D als PNG |
| Präsentation mit Folien | C | ⏸️ | Das Dossier erfüllt den Zweck |
| Präsentation teilen | C | ⏸️ | siehe Abschnitt 8 |
| **Investment-Memo** | – | 📋 | Verdichtung des Dossiers auf eine Entscheidungsvorlage |

### 10 Export und Import

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Projekt exportieren | C | ✅ | Block 3 |
| **Projekt importieren** | – | ✅ | Block 5, Dateiwähler in der Oberfläche |
| Kennzahlen als CSV | C | ✅ | Block 3 |
| Marktdaten-Import (CSV) | D | ✅ | Block A |
| 3D-Daten exportieren | C | 📋 | |
| Modelle importieren (IFC, DXF …) | C | ⏸️ | Erst wenn Handmodellierung kommt |

### 11 Datenzugriff und Erweiterbarkeit

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| REST API | B | 🟡 | 14 Endpunkte, nicht als stabile API dokumentiert 📋 |
| Quellennachweis je Wert | D | ✅ | Wert → Quelle → Artikel → Zitat → Confidence |
| SDK für Dritt-Apps | C | ❌ | Setzt eine Plattform mit Drittanbietern voraus |
| Marktplatz | C | ❌ | LUUCYs Geschäftsmodell, nicht unseres — wir rechnen selbst |

### 12 Bedienlogik

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Reaktionszeit bei Änderungen | D | ✅ | 7–90 ms ohne erneute Geo-/LLM-Abfrage |
| Ladezustände, Fehlerzustände | B | 🟡 | Job-Status ✅, Fortschritt und einheitliche Fehleranzeige 📋 |
| Tastaturnavigation in 3D | C | 📋 | |
| Mehrsprachigkeit DE/FR/EN | C | ⏸️ | Erst wenn ausserhalb der Deutschschweiz eingesetzt |

---

## Teil 3 — Vorsprung-Funktionen (Master-Spezifikation)

Bei LUUCY durchweg **nicht gefunden**. Reihenfolge = Wirkung je Aufwand.

| Funktion | Stand | Warum |
|---|---|---|
| Residualwert / max. Landpreis | ✅ | beantwortet die Kaufentscheidung |
| Wohnungsmix → Verkauf/Miete | ✅ | LUUCY endet beim Volumen |
| Risiko je Szenario mit Begründung | 🟡 | Konflikte und Unsicherheiten ✅, keine Gesamtbewertung 📋 |
| Anomalieprüfung | 🟡 | „AZ = 20.0" wurde real gemeldet — ohne systematische Prüfung 📋 |
| **Rückwärtsrechnung** | ✅ | Block 9 — macht aus einer Absage eine Verhandlungsgrundlage |
| **Highest & Best Use** | 📋 | verbindet alles zu einer Empfehlung |
| **Sanierung als Szenario** | ✅ | Block 8 |
| **Parzellenkombination A vs. A+B** | 📋 | erkennt Zukaufschancen |
| **Parzellenteilung** | 📋 | |
| **Grundstückssuche** | 📋 | LUUCY analysiert Bekanntes, wir finden Unbekanntes |
| **Massensuche / Screening** | 📋 | |
| **Abrisskandidaten / Unternutzung** | 📋 | der eigentliche Akquise-Hebel |
| **Akquise-Signale auf EGRID** | 🟡 | AkquiseRadar existiert getrennt — Verbindung über EGRID 📋 |
| **Parkierung** | 📋 | Pflichtplätze, Nachweis, Kosten |
| **Erschliessung** | 📋 | Anschlusskosten, Zufahrt |
| **Investment-Memo** | 📋 | |

---

## Teil 4 — Sonne, Schatten, Analysewerkzeuge

| Funktion | Stand | Bemerkung |
|---|---|---|
| Sonnenstand (Datum, Uhrzeit, Sommerzeit) | ✅ | Block 4, NOAA/Meeus, 74 Tests |
| Schattenwurf Bestand und Projekt | ✅ | Block 4 |
| Zeitschieber, Ablauf, freie Datumswahl | ✅ | Block 4 |
| Schattenlänge je Meter Bauhöhe | ✅ | Block 4 |
| **Besonnungsdauer je Fassade/Fenster** | 📋 | Geometrie trägt es, Auswertung fehlt |
| **Kantonaler Verschattungsnachweis (2-Stunden-Regel)** | 📋 | je Kanton verschieden — braucht Regelwerk |
| Verschattung durch Nachbarn auf das eigene Projekt | 📋 | |
| Sichtanalyse / Aussicht | 📋 | |
| Lärm | 📋 | ÖREB-Empfindlichkeitsstufe ✅ ausgewiesen |

---

## Teil 5 — UI/UX-Ideen (nach dem Funktionsumfang)

Alle ⏸️ bis der Funktionsumfang steht — ausdrückliche Vorgabe.

* Deckblatt und Logo im Dossier
* Abschnittsauswahl vor dem Druck
* Undo/Redo-Bedienung (Verlauf trägt es bereits)
* Fortschrittsanzeige statt Wartebalken
* Einheitliche Fehlerdarstellung
* Der Vergleich als Hauptansicht statt Unteransicht
* Unsicherheit als Qualitätsmerkmal darstellen, nicht als Mangel
* Messungen ins Dossier übernehmen
* Messen auch im Kartenbild, nicht nur in 3D

---

## Teil 6 — Was als Nächstes kommt

1. **Marktdatenbasis füllen** — die Struktur steht seit Block A, es fehlen
   Vergleichsobjekte. Ohne sie bleibt jede Wirtschaftlichkeit eine Annahme.
2. **Rückwärtsrechnung und Highest & Best Use** — verbinden das Vorhandene
   zu einer Empfehlung, ohne neue Datenquellen.
3. **Sanierung als Szenario** — die einzige Lücke in der Szenarienreihe.
4. **Parzellenkombination** — nutzt die vorhandene Nachbarparzellen-Geometrie.
5. **Grundstückssuche / Screening** — der Sprung von „ein Grundstück prüfen"
   zu „Grundstücke finden".

---

## Änderungsverlauf dieses Registers

| Datum | Block | Was dazukam |
|---|---|---|
| 13.09.2026 | Block 9 | Rückwärtsrechnung „Was müsste sich ändern?" — plus zwei Fehler gefunden, die nur über den Endpunkt auftraten |
| 12.09.2026 | Block 8 | Sanierung als eigenes Szenario — ohne erfundene Bestandsflächen oder Sanierungskosten |
| 12.09.2026 | Block 7 | Marktpreis: Vergleichsobjekte lassen sich erfassen — der Systemvorschlag entsteht jetzt aus echten Referenzen mit Sicherheitsgrad |
| 12.09.2026 | Lokal | Ein Startbefehl (start.bat), Oberfläche vom Backend, unabhängig von Gerüsten |
| 12.09.2026 | Betrieb | Oracle-Deployment: docker-compose, Caddy/TLS, systemd, taegliche Sicherung, Zugangsschluessel, Einrichtungsanleitung |
| 12.09.2026 | Block 6 | SIA 416 abgeschlossen: Wohnungsmix wird als Systemvorschlag oder Benutzerannahme gefuehrt statt pauschal als Annahme |
| 12.09.2026 | Block 5 | Register angelegt · Ansicht/Messungen/Arbeitsstand speichern, Variante umbenennen/löschen, Projekt-Import in der Oberfläche |
| 12.09.2026 | Block 4 | Sonne, Schatten, Messwerkzeuge |
| 12.09.2026 | Block 3 | Dossier-PDF, Export PDF/PNG/CSV/JSON |
| 12.09.2026 | Block 2 | Projekte und Varianten |
| 12.09.2026 | Block 1 | 3D-Umgebung |
| 12.09.2026 | Block A | Marktmodell mit drei Herkunftsebenen |

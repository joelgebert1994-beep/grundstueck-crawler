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
| **finden** | ✅ | Adresse, Kartenklick und Gebietsscreening (Block 13) |
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
| Marktmodell (3 Ebenen) | B/D | ✅ | Struktur Block A · Erfassung in der Oberfläche (Block 7) · **Systemvorschlag erst ab 3 Referenzen, Preisart Angebot/Abschluss getrennt (Block 11)** |
| Eigene Vergleichsobjekte | – | ✅ | Block A + Block 7: Einzelerfassung, CSV-Einfügen, Liste, Löschen — Quelle und Datenstand Pflicht · von Hand erfasste Referenzen behalten Vorrang vor jeder Eignungsregel (Block 11) |
| **Marktdatenbasis gefüllt** | – | ✅ | Block 11 · 1'385 Vergleichsobjekte aus dem AkquiseRadar (nur lesend), mit Quelle, Beobachtungsdatum, Preisart und Datenqualität — siehe 7a |
| **Ausreisser- und Plausibilitätsprüfung** | – | ✅ | Block 11 · Quartilsabstand ab 5 Werten, feste Plausibilitätsgrenzen, jeder Ausschluss mit Grund |
| **Referenzgebiet mit Ausweitung** | – | ✅ | Block 11 · PLZ → PLZ-Region, ausgewiesen statt stillschweigend |
| Lagerating | C | 📋 | |
| Gemeindechecks | C | 📋 | |
| **Rückwärtsrechnung** | – | ✅ | Block 9 · vier Stellschrauben, Einordnung gegen erfasste Vergleichsobjekte |
| **Highest & Best Use** | – | ✅ | Block 10 · vier Filterstufen statt Score · Kriterium Residualwert · „nicht bestimmbar" statt Scheinrangfolge |


#### 7a Marktdatenbasis — welche Quellen taugen wofür (Block 11)

Die Struktur stand seit Block A, die Daten fehlten (3 Testobjekte). Gefüllt
wurde sie aus der einzigen Quelle, die wirklich vorhanden ist: dem
AkquiseRadar. **Gelesen wird ausschliesslich schreibgeschützt; der Radar
bleibt unverändert.**

| Marktgrösse | Radar geeignet? | Begründung |
|---|---|---|
| **Bodenpreis** CHF/m² | ✅ mit Vorbehalt | Bauland-Inserate nennen den Preis für genau die Fläche, um die es geht. Vorbehalt: Angebot ≠ Abschluss. |
| **Verkaufspreis** Neubau CHF/m² | ❌ | Der Radar sammelt Akquisitionsziele (Häuser, Grundstücke), nicht Eigentumswohnungen: **1 Wohnungsinserat in 1'982 Objekten**. Ein Angebotspreis für ein ganzes Bestandshaus, geteilt durch die Wohnfläche, beantwortet „was kostet dieses Haus" — nicht „für wie viel lassen sich hier neu gebaute Wohnungen verkaufen". Das ist ein Methodenfehler, kein Datenmangel. |
| **Mietzins** CHF/m²/Jahr | ❌ | 1 Objekt von 1'982 führt einen Mietzins. Der Radar sammelt Kaufinserate. |
| **Bestandspreis** MFH/EFH | 🟡 vorhanden, nicht verwendet | 1'312 Objekte mit Preis und Wohnfläche. Als eigene Grösse („was kostet der Bestand heute") fachlich brauchbar, aber heute nirgends gebraucht — bewusst zurückgestellt statt zweckentfremdet. |

**Für den Verkaufspreis geeignet wären:** eigene beurkundete Abschlüsse,
Neubau-Vermarktungslisten, Auswertungen von Wüest Partner / IAZI /
Fahrländer. Alle drei sind über die bestehende Einzelerfassung und den
CSV-Import erfassbar — dafür braucht es keinen neuen Code, sondern Daten.

**Bewusst nicht eingeführt:** kantonale Handänderungsstatistiken (nicht
flächendeckend und nicht objektscharf), BFS-Preisindizes (Index, keine
Niveaus), amtliche Schätzungen und Steuerwerte (keine Marktwerte).

| Regel | Wert | Warum |
|---|---|---|
| Systemvorschlag ab | 3 Referenzen | Bei zwei Beobachtungen sagt der Median nur, was zufällig zwischen ihnen lag. Darunter: Bandbreite statt Punktwert. |
| Sicherheit `hoch` ab | 6 Referenzen **und** mindestens ein beurkundeter Abschluss | Reine Angebotsdaten tragen einen systematischen, unbezifferbaren Aufschlag. |
| Sicherheit `mittel` ab | 3 Referenzen, Streuung ≤ 45 % | |
| Ausreisser | Quartilsabstand × 1.5, erst ab 5 Werten | Bei vier Beobachtungen ist nicht zu unterscheiden, ob eine falsch ist oder der Markt streut. |
| Plausibilitätsgrenzen | Verkauf 1'000–30'000 · Miete 60–900 · Boden 50–20'000 | Keine Marktaussage, sondern Datenhygiene: real importiert wurden 0 CHF/m² („Preis auf Anfrage") und 30'333 CHF/m² (Gebäude- statt Parzellenfläche). |
| Ortsschlüssel | PLZ vor Gemeindename | Es gibt vier Gemeinden namens Buchs. |
| Ausweitung | PLZ → PLZ-Region (2 Stellen), dann Schluss | Wird ausgewiesen, nie stillschweigend. Eine gesamtschweizerische Auswertung gibt es nicht — Bodenpreise von 82 bis 4'956 CHF/m² in einem Median wären eine Zahl ohne Gegenstand. |

**Was bei zu wenigen Daten passiert:** kein Systemvorschlag, die Bandbreite
bleibt sichtbar, der Grund steht beziffert daneben („1 von 3 nötigen
Referenzen"), und die Rückwärtsrechnung wie der HBU bekommen keine
Unterscheidungsschwelle — die Rangfolge gilt dann als nicht marktseitig
belegt.


#### 7b Parzellenkombination A vs. A+B (Block 12)

Die Nachbarparzelle wird auf der Karte gewählt. Danach läuft **dieselbe
Kette zweimal** — einmal auf A, einmal auf der vereinigten Kontur:
G1 → SIA 416 → Szenarien → Wirtschaftlichkeit → HBU. Keine zweite
Rechenlogik; `/entwicklung` und `/kombination` lesen Markt-, Kosten- und
Szenarioeingaben über dieselben zwei Hilfsfunktionen, damit die Differenz
den Unterschied der **Parzellen** misst und nicht den der Annahmen.

**Prüfstufen in fester Reihenfolge** (Abbruch mit Grund, wie beim HBU):

| Stufe | Bedingung | Sonst |
|---|---|---|
| 0 | B ist keine Strassenparzelle | `nicht_zulaessig` |
| 1 | A und B grenzen aneinander (≥ 1 m gemeinsame Grenze, kein Loch dazwischen) | `nicht_zulaessig` |
| 2 | dieselbe Bauzone | `nicht_bestimmbar` — rechtlich ginge es, aber es müsste je Zonenanteil gerechnet werden |
| 3 | kein Sondernutzungsplan auf B | `nicht_bestimmbar` |
| 4 | G1 auf der vereinigten Kontur rechenbar | `nicht_bestimmbar` |

**Mehr Land ist nicht automatisch mehr Potenzial.** Gemessen wird die
**Ausbeute**: `(ΔGF / Fläche B) ÷ (GF A / Fläche A)`. Der Massstab ist A
selbst, keine gesetzte Schwelle.

| Einstufung | Bedingung |
|---|---|
| `zusatzpotenzial` | Ausbeute ≥ 1.0 — B trägt mindestens so viel wie A |
| `wenig_zusatzpotenzial` | 0 < Ausbeute < 1.0 — **beziffert** („B wird zu 34 % so gut ausgenutzt wie A") statt in viel/wenig eingeteilt |
| `kein_zusatzpotenzial` | ΔGF ≤ 0 |
| `nicht_bestimmbar` | eine Seite liefert nur eine Bandbreite |

Warum das auseinandergeht, steht dabei: `geschossflaeche_limitiert_durch`
sagt je Seite, ob die Ausnützungsziffer, die Geometrie oder die
Vollgeschosszahl bindet.

**Wirtschaftlicher Zusatznutzen** — ohne erfundenen Bodenwert:

```
Residualwert(A+B) − Residualwert(A) = Höchstpreis für B
                                    − Kaufpreis B      (Benutzerannahme)
                                    − Zusatzkosten     (Benutzerannahme)
                                    = wirtschaftlicher Zusatznutzen
```

Fehlt der Kaufpreis, steht der Mehrwert und der Zusatznutzen bleibt offen.

**Am echten Fall (Rosenweg 4 + Parzelle 316, Buchs AG):** Fläche 599 → 1'443 m²,
Baubereich **117 → 683 m²** (der Grenzabstand an der 29.8 m langen gemeinsamen
Grenze entfällt), Geschossfläche 299 → 721 m², tragbarer Landwert
511'494 → 1'232'696 CHF. Die Aufstockung gewinnt dabei nur 78'651 CHF, der
Anbau 721'795 — sie nutzt die zusätzliche Fläche schlicht nicht.

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
| Risiko je Szenario mit Begründung | 🟡 | Konflikte und Unsicherheiten ✅ · seit Block 10 zusätzlich je Szenario, welche Prüfstufe erreicht wurde und woran es scheitert ✅ · eine Risikokennzahl (Bauzeit, Bewilligungsrisiko, Marktrisiko) fehlt weiterhin 📋 |
| Anomalieprüfung | 🟡 | „AZ = 20.0" wurde real gemeldet — ohne systematische Prüfung 📋 |
| **Rückwärtsrechnung** | ✅ | Block 9 — macht aus einer Absage eine Verhandlungsgrundlage |
| **Highest & Best Use** | ✅ | Block 10 — führt Szenarien, Wirtschaftlichkeit und Marktreferenz zu einer Empfehlung zusammen, ohne neue Rechnung |
| **Sanierung als Szenario** | ✅ | Block 8 |
| **Parzellenkombination A vs. A+B** | ✅ | Block 12 · dieselbe Kette zweimal · Ausbeute statt blosser Flächenaddition · Strassenparzellen gesperrt — siehe 7b |
| **Parzellenteilung** | 📋 | |
| **Grundstückssuche** | ✅ | Block 13 · dreistufig, Sortierung nach Ausnutzungsreserve statt nach Fläche · kein Score |
| **Massensuche / Screening** | 🟡 | Block 13 · 431 Parzellen in 33 s mit 16 amtlichen Abfragen · Gemeindegrenze und Namenssuche fehlen noch 📋 |
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

1. **Grundstückssuche / Screening** — der Sprung von „ein Grundstück prüfen"
   zu „Grundstücke finden".
2. **Anomalieprüfung** — „AZ = 20.0" wurde real gemeldet und lief durch.
3. **Baugesuche / Referenzprojekte in der Umgebung.**
4. **Verkaufspreis-Referenzen beschaffen** — der einzige echte Datenmangel,
   der übrig bleibt (siehe 7a). Kein Code-, sondern ein Datenthema.
5. **Parzellenteilung** — die Gegenrichtung zur Kombination.

Erledigt seit der letzten Fassung: Sanierung als Szenario (Block 8),
Rückwärtsrechnung (Block 9), Highest & Best Use (Block 10),
Marktdatenbasis (Block 11), Parzellenkombination (Block 12).

---

## Änderungsverlauf dieses Registers

| Datum | Block | Was dazukam |
|---|---|---|
| 13.09.2026 | Block 17 | Nutzerfluss geprueft: Umlaute aus geodienste.ch waren im ganzen Dossier zerstoert (fehlender Zeichensatz) · Uebersicht wiederholte den Dossierkopf · "Was ist baulich moeglich" verschwand statt sich zu begruenden · Uebersicht und Hierarchie widersprachen sich bei den Ueberlagerungen · Dossierkopf behauptete "Zone nicht zugeordnet", waehrend die Pruefung lief · Karte zoomte auf eine leere Flaeche |
| 13.09.2026 | Block 16 | Modul 1 fragt nebenlaeufig ab: 14 s -> 5.9 s, erste Ansicht 11 s -> 5.6 s, warmer Lauf 5 s end to end · Abhaengigkeiten in zwei Wellen, HTTP-Sitzung je Thread · Ergebnis zeichenweise identisch zur sequenziellen Fassung |
| 13.09.2026 | Block 15 | Ladezeit gemessen und zerlegt: 109 von 126 s (87 %) entfielen auf das Sprachmodell. Erste Ansicht jetzt nach rund 11 s, echte Ladezustaende statt geschaetzter Prozente, BZO-Zwischenspeicher je Gemeinde (zweite Adresse in Buchs: 10.6 s statt 126 s), Reglementsauswertung einzeln wiederholbar |
| 13.09.2026 | Block 14 | Oberflaeche: Zonenhierarchie A Grundnutzung - B Sondernutzung - C Ueberlagerungen - D Restriktionen · Karte mit verstaendlichen Namen statt Layerbezeichnungen · "Zonen 68" entfernt · Markt als eigener Reiter mit getrennten Ebenen |
| 13.09.2026 | Block 13 | Grundstueckssuche: dreistufiges Screening · Modul 2 einmal je Gemeinde statt je Parzelle · Sortierung nach Ausnutzungsreserve, kein Score · drei Fehler am echten Fall gefunden (Randparzellen, Gebaeude ohne EGRID, Strassenparzellen) |
| 13.09.2026 | Block 12 | Parzellenkombination A vs. A+B: dieselbe Kette zweimal statt einer zweiten Rechenlogik · Ausbeute als Massstab statt blosser Flächenaddition · Strassenparzellen gesperrt (die Zonenprüfung fing sie nicht ab) · Kaufpreis B und Zusatzkosten als eigene Annahmen |
| 13.09.2026 | Block 11 | Marktdatenbasis: 1'385 Vergleichsobjekte aus dem AkquiseRadar (nur lesend) · Preisart Angebot/Abschluss · Eignungsregel je Marktgrösse · Plausibilitäts- und Ausreisserprüfung · Systemvorschlag erst ab 3 Referenzen · Referenzgebiet mit ausgewiesener Ausweitung · eine zweite Stelle, die denselben Systemvorschlag bildete, aufgelöst |
| 13.09.2026 | Block 10 | Highest & Best Use: vier Filterstufen statt gewichteter Punktzahl · „praktisch gleichwertig" aus der Streuung der Vergleichsobjekte abgeleitet · am echten Fall zwei eigene Fehler gefunden: „nicht bestimmbar" wurde als rechtliches Scheitern gefuehrt, und gleiche Landwerte bekamen verschiedene Plaetze |
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

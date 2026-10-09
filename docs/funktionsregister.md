# Funktionsregister — was das Werkzeug kann, was fehlt, was kommt

**Führende Übersicht. Bei jedem Block zu aktualisieren.**
**Stand:** 09.10.2026 · nach A3 (Code `main` `ba839dc`, Betrieb `a3b9909`)

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
| 🟢 | **live verifiziert** — implementiert, getestet **und** in einer dokumentierten Live-Abnahme am echten Fall geprüft (Fall und Datum stehen dabei) |
| ✅ | **implementiert und getestet** — gebaut, durch Regressionstests abgesichert; ältere Einträge (bis Block 24) zusätzlich damals im Browser geprüft. **Nicht** automatisch live verifiziert |
| 🟡 | **teilweise** — nutzbar, aber ein benannter Teil fehlt |
| ⭕ | **offen** — erkannte Lücke oder Befund, noch nicht behoben |
| 📋 | **geplant** — vorgesehen, noch nicht gebaut |
| ❔ | **nicht abschliessend beurteilbar** — Prüfung mangels verlässlicher Daten oder wegen eines technischen Fehlers nicht möglich; weder bestanden noch Fehler |
| ⏸️ | **bewusst zurückgestellt** — mit Begründung, kommt später |
| ❌ | **nicht sinnvoll** — mit Begründung, kommt nicht |

Belege: Commit-Kürzel (`e69d728`), Testsuite (`test_kanten_manuell`, JS-Tests unter
`tests/js/`), Live-Abnahme mit Fall und Datum. Die Python-Suiten laufen über
`python tests/alle.py`, die JS-Tests einzeln mit `node tests/js/<name>.test.js`.

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
| Adress-/Ortssuche | A | 🟢 | Geocoding → Parzelle, Punkt-in-Polygon · seit `341785a`/`dec6cc2` (01.10.2026): nur ein Treffer mit passender Strasse, Hausnummer und PLZ, sonst „nicht gefunden"/„mehrdeutig" mit Kandidaten; angeklickter Vorschlag über seine Kennung (EGID_EDID) aufgelöst und gegen die Koordinate geprüft; nie still ein anderes Grundstück · Tests `test_adresswahl`, `adresssuche.test.js` · live: Hogerwiesstrasse 1, Weiningen (Live-Abnahme 01.10.2026, `5ef670e`; vorher Fehllauf auf Püntenstrasse 2b) |
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
| **Bestand aus der amtlichen Vermessung** | – | 🟢 | `5cb70b7` · Gebäudegrundriss aus der AV (geodienste.ch, Bodenbedeckung Gebäude) für die 21 frei gegebenen Kantone; Bestand, Karte, 3D und Rechnung aus derselben Quelle · VEC25 (1:25'000) nur als gekennzeichneter Ersatz „vereinfacht" mit Grund (Kanton nicht frei, AV nicht erreichbar); eine leere AV wird nicht aufgefüllt · Test `test_bestand_av` (eingefrorene echte Antworten) · live 07./08.10.2026: Weiningen 150.0 m² (GWR 150, vorher VEC25 264.1), Rheineck 107.6 (GWR 108), Buchs AG drei Gebäude 20.8/67.7/9.1 (GWR 21/68/9) |
| **Geplant (projektiert) als eigene Ebene** | – | 🟢 | `5cb70b7` · amtlich projektierte Gebäude aus der AV, dunkelblau, in 3D flach (Höhe unbekannt); gehen in keine Fläche, kein Budget und kein Szenario ein · Test `test_bestand_av`, `kanten_karte.test.js` · live 07./08.10.2026: Weiningen 3, Buchs AG 1 (nicht auf der Parzelle), Rheineck 0 |
| **Kartensemantik Bestand / bebaubare Fläche / möglicher Baukörper** | – | 🟢 | `e69d728`, `296da47`, `662ac1a` · Bestand grau, bebaubare Fläche grün gestrichelt (errechnet), möglicher Baukörper je Szenario (Neubau/Ersatzneubau gold gestrichelt, Anbau orange, Aufstockung violett); ein nicht mögliches Szenario zeigt den Ist-Zustand, keinen neuen Körper · Test `kanten_karte.test.js` · live 07./08.10.2026 Weiningen, Rheineck, Buchs AG |
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
| Eigener Baukörper in 3D | A | 🟢 | aus der Rechnung, nicht aus der Hand · Szenario-Darstellung seit `01c3f27`/`662ac1a`: Ersatzneubau ohne Bestand, Bestand + Neubau mit Bestand, Anbau/Aufstockung zeigen den Bestand, das Zusatzgeschoss sitzt auf Bestandshöhe, ohne berechnetes Szenario bleibt der eigene Bestand sichtbar · Test `kanten_karte.test.js` · live 08.10.2026 Buchs AG, Weiningen, Rheineck |
| Bestandshöhen bei „Bestand + Neubau" | – | ⭕ | Live-Befund Buchs AG (08.10.2026): die Engine gibt jedem „Bestand (bleibt)"-Körper die Höhe des Hauptgebäudes — die Garage erscheint 6 m hoch. Bestehende Szenariologik, nicht behoben |
| **3D-Entwurf als eigener Reiter** | – | ✅ | `1b29632` · dieselbe Szene, an einer auffindbaren Stelle; auch ohne berechenbares Szenario und bei Sondernutzungsplan |
| 3D drehen/zoomen | A | ✅ | |
| **Schatten mit Zeitsteuerung** | C | ✅ | Block 4, echtes Datum und echte Uhrzeit |
| Vegetation | C | 📋 | |
| Photorealistisches Terrain (Google 3D) | C | ❌ | Lizenzkosten ohne fachlichen Gewinn |
| Navigation unter Terrain | C | ❌ | Kein Anwendungsfall im Hochbau |

### 4 Modellierung

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Gebäude von Hand modellieren | C | 🟡 | **Bewusst:** unsere Körper entstehen aus der Rechnung. Seit der Projektstudie (`8d80e0d`, `485c230`) als *Abweichung vom berechneten Vorschlag*: Baukörper setzen, schieben, drehen, bemassen, Geschosse und Geschosshöhe setzen; Prüfstatus gegen Baubereich und Grenzabstand · freies Modellieren beliebiger Formen weiterhin nicht |
| **Flächen des gezeichneten Körpers** | – | ✅ | `3f2c55a` · `/projektstudie/flaechen` rechnet durch das vorhandene Flächenmodell (aGF → NGF → HNF → NWF), keine zweite Rechnung · Test `test_projektstudie_flaechen` |
| **Wirtschaftlichkeit am gezeichneten Körper** | – | 📋 | Konzept K ([`machbarkeit_kosten.md`](machbarkeit_kosten.md)), nicht implementiert |
| Dachneigung frei einstellen | C | 📋 | |
| Geschosse stapeln, Höhen anpassen | B | ✅ | rechnerisch ✅ · interaktiv über die Projektstudie (Geschosse, Geschosshöhe) |
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
| **Varianten tragen den Projektkörper** | – | ✅ | `c1cdf70` · „Entwurf sichern" / „Als neue Variante", Wechsel stellt den gezeichneten Körper wieder her · Test `test_variante_entwurf` |
| **Variante umbenennen** | – | ✅ | Block 5 |
| **Variante löschen** | – | ✅ | Block 5, letzte Variante geschützt |
| Baulich abgeleitete Szenarien | D | ✅ | unser Vorsprung |
| **Sanierung als Szenario** | – | ✅ | Block 8 · einziges Szenario ohne Ausnützungsverbrauch — bleibt möglich, wo das Budget überschritten ist |
| **Begründung nicht bestimmbarer Szenarien** | – | ✅ | `e69d728` (A2) · statt des irreführenden „in Vorbereitung, wird als nächster fachlicher Block ergänzt" steht „Geometrie nicht eindeutig" mit Verweis auf das Kantenprotokoll — die Szenariologik besteht, ihr fehlt eine eindeutige Geometrie · Test `kanten_karte.test.js` · eine eigene Live-Abnahme des Texts ist nicht dokumentiert |
| Szenarien bei Bandbreite | – | 🟡 | Liefert G1 nur eine Bandbreite (keine eindeutige Abstandsanordnung), bleiben die Szenarien „nicht bestimmbar" — z. B. Rheineck, Buhofstrasse 55 (09.10.2026). Bewusst kein Einzelwert; Abhilfe heute über den manuellen Abstand je Kante, wo Kanten offen sind |
| Objekte zwischen Varianten kopieren | C | 🟡 | Ansicht und Annahmen ✅ beim Duplizieren |

### 6 Baurecht und Kennzahlen

| Funktion | Damals | Heute |
|---|---|---|
| Bauziffern, Grenzwertwarnung | A | ✅ |
| Amtliche Vermessung | A | ✅ |
| ÖREB, Schutz, Sondernutzung | D | 🟢 9 Kantone (ZH, BS, TG, BL, AG, LU, SG, BE, SO) · Zonenhierarchie A–D · Lärmempfindlichkeitsstufe als „Stufe II gilt" statt „betroffen" (`5ef670e`) · ÖREB-Einträge „Hinweis.…" (laufende Planung) als „gilt noch nicht, nicht in der Berechnung" (`e69d728`) · live: Weiningen 01.10.2026, Rheineck 07.10.2026 (Zone „BauG Wohnzone W2", Status inForce) |
| Reglement per LLM auswerten | D | ✅ mit Fundstelle und Confidence · Zwischenspeicher je Gemeinde und Dokumentensatz (Block 24) · Selbstprüfung auf widersprüchliche Antworten (`ee25ab1`) · Fehlerart, begrenzter Retry, eigener Status „vorübergehend nicht verfügbar"/„fehlgeschlagen" (`8010f96`, `bfe8bc8`) · Tests `test_reglement_stabilitaet`, `test_reglement_zwischenspeicher` |
| **Plausibilitätsprüfung der Reglementwerte (A3)** | – | ✅ `ba839dc` · jede Zonenkennzahl gegen ihren eigenen Beleg (Einheit, Originaltext), keine pauschalen Wertebereiche · erkannt: unpassende Einheit, Prozent/Zentimeter nicht umgerechnet, verrutschtes Komma, Widerspruch zum Originaltext, „Prozent" ohne Beleg, negative Werte, halbe Vollgeschosse, gross < klein, Gesamt- < Gebäudehöhe, Wert trotz „nicht bestimmbar" · auffällige Werte werden nicht korrigiert, sondern zurückgehalten (nicht in der Rechnung, Beleg und ausgelesener Wert bleiben) · Tests `test_reglement_plausibilitaet`, `reglement_plausibilitaet.test.js` · live 09.10.2026: Weiningen (AZ 0.30 aus „max. 30 %") und Rheineck (AZ 0.45, Art. 8 BauR) rechnen unverändert, kein Prüfhinweis; 478 gespeicherte Werte der Produktion ohne Befund. **Die Erkennung selbst** ist nur an gespeicherten Auswertungen belegt (Birmensdorf, Russikon: AZ 70/20 statt 0.70/0.20) — live ist noch kein auffälliger Fall durchgelaufen |
| Geltende AZ aus altrechtlichem Reglement | – | 🟢 Rheineck: AZ 0.45 aus dem Baureglement 2013, Art. 8, im Übergang weiterhin in Kraft (ÖREB „BauG …", inForce) · live 07.10. und 09.10.2026 |
| AZ im Potenzial bei nicht zugeordneten Kanten | – | 🟢 `85db512` · Weiningen: die AZ-Geschossfläche (0.30 × 1'168.1 = 350.42 m²) geht im Rückfallmodus nicht mehr verloren · Tests `test_weiningen_az`, `potenzial_eindeutig.test.js` · live Weiningen 07.10. und 09.10.2026 |
| Geltendes Recht ohne AZ | – | 🟡 Anzeige „von der Bau- und Nutzungsordnung nicht geführt" statt Fehler, belegt an der Rheineck-Kernzone („gilt keine AZ") · ❔ **Widnau** (neue Ortsplanung nach PBG, z. B. „Kernzone K 20" ohne BauG-Präfix) nicht abschliessend geprüft: Gemini war bei drei Versuchen überlastet — weder bestanden noch Fehler |
| Kantenklassifikation | D | ✅ Stufe 2 |
| **Manueller Abstand je Grundstückskante (Zielbild §16)** | – | 🟢 `e69d728` (A1) · Eingabe nur an Kanten ohne amtlichen Wert; ein amtlicher Wert wird nie ersetzt („nicht übernommen"), nichts auf andere Kanten übertragen, kein Standardwert · gekennzeichnet als „meine Annahme" (Kantenprotokoll, Kopfhinweis, Quellenobjekt `manuelle_eingabe`) · eine solche Rechnung kommt nie in den Analyse-Zwischenspeicher · Test `test_kanten_manuell` · live Weiningen 07.10.2026: 6 m an Kante 4/5 → Szenarien berechnet; danach normale Analyse aus dem Speicher unverändert amtlich |
| SIA-416-Kette | D | ✅ Stufe 3 |
| Baulinien | B | 🟡 geholt (ÖREB, föderale Kategorie 71) und geometrisch als Restriktionsfläche verschnitten (`restriktionsgeometrie.py`) — welche Seite Baugebiet ist, ist eine ausgewiesene Annahme (flächenmässige Mehrheitsseite) · die Zuordnung Baulinie ↔ Kante ist nicht automatisiert 📋 (an der Strassenkante bleibt der Strassenabstand stehen, mit sichtbarem Vorbehalt „Baulinie kann strenger sein") · eine Live-Abnahme an einer Parzelle mit Baulinie ist nicht dokumentiert |
| Kennzahlen Gebäude für Gebäude | B | 📋 |

### 7 Wirtschaftlichkeit und Markt

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Kostenrechner BKP 1–6 | A | ✅ | Stufe 5 · Aushub hängt am Fussabdruck, nicht an der Geschossfläche (`9d7174d`, `aa14bb1`) |
| Wirtschaftlichkeit als eigener Reiter | – | ✅ | `2fb61b8` · nach dem Markt, damit die Rendite mit den gesetzten Marktannahmen erscheint |
| Wohnungsmix, Wohnungszahl | D | ✅ | Stufe 3, ohne Bruchteilwohnungen · Herkunft Vorschlag/Annahme getrennt (Block 6) |
| Verkauf / Miete / Rendite | D | ✅ | Stufe 5 |
| Gewinn, Marge, Zielmarge | D | ✅ | Stufe 5 |
| **Residualwert** | D | ✅ | stärkstes Alleinstellungsmerkmal |
| Marktmodell (3 Ebenen) | B/D | ✅ | Struktur Block A · Erfassung in der Oberfläche (Block 7) · **Systemvorschlag erst ab 3 Referenzen, Preisart Angebot/Abschluss getrennt (Block 11)** |
| Eigene Vergleichsobjekte | – | ✅ | Block A + Block 7: Einzelerfassung, CSV-Einfügen, Liste, Löschen — Quelle und Datenstand Pflicht · von Hand erfasste Referenzen behalten Vorrang vor jeder Eignungsregel (Block 11) |
| **Marktdatenbasis gefüllt** | – | ✅ | Block 11 · 1'385 Vergleichsobjekte aus dem AkquiseRadar (nur lesend), mit Quelle, Beobachtungsdatum, Preisart und Datenqualität — siehe 7a · seit 18.09.2026 auch auf der Produktion (1'857 Vergleichsobjekte, schreibgeschützt eingehängt, `d058eab`) |
| **Markt MVP 1** | – | ✅ | `37d6837`, `c89e9fa`, `f5188a1`, `a2769ab`, `fee2741` (29./30.09.2026) · Bodenpreis-Systemvorschlag ist kein stiller Rechenwert mehr — er zählt erst nach „Systemvorschlag übernehmen" und ist dann als „meine Annahme" gekennzeichnet · neue Analyse übernimmt nicht mehr die PLZ der vorigen · offene Variante wird bei Adresswechsel nicht mehr überschrieben (EGRID-Schutz, Projekt verlässt den Kontext) · Tests `markt_mvp1.test.js`, `markt_plz.test.js`, `variante_egrid_schutz.test.js`, `test_oberflaeche` · Befunde stammen aus Live-Tests (Variante 15); die Nachprüfung lief im Browser mit den echten Funktionen, aber mit nachgebildeten Serverantworten — eine End-to-End-Live-Abnahme nach `fee2741` ist nicht dokumentiert |
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

> **Begründung:** Seit 18.09.2026 läuft das Backend auf dem Oracle-Server
> (Zugangsschlüssel, siehe [`betrieb.md`](betrieb.md)), Benutzerkonten gibt es
> aber nicht. Ein „Teilen" ohne Konten wäre entweder wirkungslos oder ein
> offener Zugang. Die Weitergabe läuft deshalb bewusst über Datei und PDF —
> beides vollständig. Konten und Teilen per Link sind weiterhin nicht gebaut.

### 9 Präsentation und Bericht

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Bericht / Dossier als PDF | C | ✅ | Block 3, 12 Abschnitte |
| **Dossier-Oberfläche** | – | 🟢 | `11f73ba`, `aab7209` · ein Dossier statt geteilter Arbeitsfläche, Reiter nach Bereichen (Grundstück & Bestand, Baurecht & Planung, Standort & Umwelt, Markt, Entwicklung, Karte, Quellen & Herleitung) · „Was zu beachten ist": eine Zeile je Befund mit Status und Quelle, kein Eignungsscore · Soll/Ist im Dossier getrennt (`341785a`) · live: Abnahme Weiningen 01.10.2026 (`5ef670e`, drei Befunde behoben) |
| **Standort und Solar** | – | 🟢 | `aab7209` · ÖV-Güteklasse (ARE), Bahnhof, Schule, Kindergarten (Luftlinie), Solareignung des Dachs (BFE-Modell) getrennt von der installierten Anlage · Tests `test_standort_energie`, `standort_hinweise.test.js` · live Weiningen 01.10.2026 |
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
| REST API | B | 🟡 | rund 20 Endpunkte (u. a. `/analyze`, `/umgebung`, `/wirtschaftlichkeit`, `/projektstudie/flaechen`, `/analyse/reglement`), nicht als stabile API dokumentiert 📋 |
| Quellennachweis je Wert | D | ✅ | Wert → Quelle → Artikel → Zitat → Confidence · Bestand mit tatsächlicher Quelle (amtliche Vermessung oder VEC25), manuelle Werte als Benutzerannahme (`manuelle_eingabe`), auffällige Reglementwerte mit Prüfbefund |
| SDK für Dritt-Apps | C | ❌ | Setzt eine Plattform mit Drittanbietern voraus |
| Marktplatz | C | ❌ | LUUCYs Geschäftsmodell, nicht unseres — wir rechnen selbst |

### 12 Bedienlogik

| Funktion | Damals | Heute | Bemerkung |
|---|---|---|---|
| Reaktionszeit bei Änderungen | D | ✅ | 7–90 ms ohne erneute Geo-/LLM-Abfrage |
| Ladezustände, Fehlerzustände | B | 🟡 | Fortschrittsanzeige ✅ (Schrittliste je Abfrage mit echtem Stand statt geschätzter Prozente, Teilergebnis nach Modul 1, Block 15/16 · Test `test_phasen`) · Reglement-Status unterschieden: läuft / vorübergehend nicht verfügbar / fehlgeschlagen, Wiederholen nur wo sinnvoll (`8010f96`, `bfe8bc8`) · ein Teilfehler leert keinen Reiter (`d2351d5`) · eine einheitliche Fehlerdarstellung über alle Reiter fehlt 📋 |
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
| Anomalieprüfung | ✅ | Reglementwerte: Plausibilitätsprüfung gegen den eigenen Beleg (A3, `ba839dc`) — „AZ = 20.0" (Russikon) wird jetzt als „Prozent nicht umgerechnet" zurückgehalten · Reglementantwort: Selbstprüfung auf Widersprüche (`ee25ab1`) · Marktdaten: Ausreisser- und Plausibilitätsprüfung (Block 11) · siehe Abschnitt 6 zum Live-Stand |
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
* ~~Fortschrittsanzeige statt Wartebalken~~ — erledigt (Block 15/16, siehe Abschnitt 12)
* Einheitliche Fehlerdarstellung
* Der Vergleich als Hauptansicht statt Unteransicht
* Unsicherheit als Qualitätsmerkmal darstellen, nicht als Mangel
* Messungen ins Dossier übernehmen
* Messen auch im Kartenbild, nicht nur in 3D

---

## Teil 6 — Was als Nächstes kommt

1. **Baugesuche / Referenzprojekte in der Umgebung.** Die Datenstruktur ist
   vorbereitet (`referenzprojekte.py`, Test `test_referenzprojekte`), Daten
   gibt es keine.
2. **Verkaufspreis-Referenzen beschaffen** — der einzige echte Datenmangel,
   der übrig bleibt (siehe 7a). Kein Code-, sondern ein Datenthema.
3. **Parzellenteilung** — die Gegenrichtung zur Kombination.

Diese Reihenfolge ist keine neue Planung; sie ist die bisherige ohne die
erledigten Punkte.

**Offen aus Prüfungen und Abnahmen** (nicht eingeplant, nur festgehalten):

| Punkt | Stand |
|---|---|
| Widnau: geltendes Recht ohne AZ (neue PBG-Ortsplanung) | ❔ live nicht abschliessend geprüft — Gemini dreimal überlastet; weder bestanden noch Fehler |
| Bestandshöhen bei „Bestand + Neubau" | ⭕ Buchs AG: alle Bestandskörper tragen die Hauptgebäudehöhe (Abschnitt 3) |
| Erkennung auffälliger Reglementwerte live | ❔ an gespeicherten Auswertungen belegt, live noch kein auffälliger Fall durchgelaufen (Abschnitt 6) |
| Markt MVP 1 | ❔ getestet, End-to-End-Live-Abnahme nach `fee2741` nicht dokumentiert (Abschnitt 7) |
| Baulinie ↔ Kante | 📋 Zuordnung nicht automatisiert, keine Live-Abnahme an einer Parzelle mit Baulinie (Abschnitt 6) |
| Wirtschaftlichkeit am gezeichneten Körper | 📋 Konzept K, nicht implementiert (Abschnitt 4) |
| Einheitliche Fehlerdarstellung | 📋 (Abschnitt 12) |

Erledigt seit der letzten Fassung (12.09.2026): Grundstückssuche/Screening
(Block 13), Anomalieprüfung der Reglementwerte (A3) sowie alles, was im
Änderungsverlauf ab Block 13 steht.

---

## Änderungsverlauf dieses Registers

| Datum | Block | Was dazukam |
|---|---|---|
| 09.10.2026 | A4 | Register mit dem Code abgeglichen (dieser Stand). Legende trennt „implementiert und getestet" von „live verifiziert", dazu „offen" und „nicht abschliessend beurteilbar". Korrigiert: Baulinien werden seit Phase 0.3 (11.09.2026) geometrisch verschnitten (stand als „nicht verschnitten"), Screening und Anomalieprüfung standen noch unter „als Nächstes", Fortschrittsanzeige als geplant, Betrieb als „lokal ohne Anmeldung" |
| 09.10.2026 | A3 | Plausibilitätsprüfung der Reglementwerte gegen den eigenen Beleg, ohne pauschale Grenzen; auffällige Werte zurückgehalten, nie korrigiert (`ba839dc`) · live Weiningen und Rheineck unverändert |
| 07.–08.10.2026 | A1, A2, Bestand | Manueller Abstand je Kante (§16), Szenariotext „Geometrie nicht eindeutig", Kartensemantik, ÖREB-Hinweise auf laufende Planung (`e69d728`, `296da47`) · Bestand aus der amtlichen Vermessung, VEC25 nur gekennzeichneter Ersatz, „Geplant (projektiert)" als eigene Ebene, 3D-Darstellung der Szenarien (`5cb70b7`, `01c3f27`, `662ac1a`) · live Weiningen, Rheineck, Buchs AG |
| 01.–02.10.2026 | Adresse, Dossier | Adresswahl ohne stilles Ausweichen (`341785a`, `dec6cc2`) · Dossier nach Bereichen, Hinweise mit Status und Quelle, Standort und Solar (`aab7209`) · Live-Abnahme Weiningen (`5ef670e`) · AZ im Potenzial bei nicht zugeordneten Kanten (`85db512`) |
| 29.–30.09.2026 | Markt MVP 1, Reglement | Bodenpreis-Systemvorschlag nur nach Übernahme, Variantenschutz bei Adresswechsel, PLZ-Fehler (`37d6837` … `fee2741`) · Reglement-Status mit Fehlerart und begrenztem Retry (`8010f96`, `bfe8bc8`) · BKP-Aushub am Fussabdruck (`9d7174d`, `aa14bb1`) |
| 19.–24.09.2026 | 3D-Entwurf | 3D als eigener Reiter, Projektstudie (Körper setzen, schieben, drehen, bemassen), räumliche Kette, Flächen-Rückrechnung, Varianten tragen den Körper (`1b29632` … `a015756`) · Konzepte [`3d_projektstudie.md`](3d_projektstudie.md), [`machbarkeit_kosten.md`](machbarkeit_kosten.md) |
| 17.–18.09.2026 | Betrieb, Oberfläche | Backend auf Oracle in Betrieb (`f155a0d`, `d4d7882`) · AkquiseRadar auf der Produktion (`d058eab`) · Dossier statt geteilter Arbeitsfläche (`11f73ba`) · Wirtschaftlichkeit als eigener Reiter (`2fb61b8`) · Selbstprüfung der Reglementantwort (`ee25ab1`) |
| 17.09.2026 | Block 24 | Reglementsauswertung vom Engine-Stand entkoppelt. Der Schluessel trug einen SHA-256 ueber ALLE potenzial_engine/*.py -- ein Komma in sia416_flaechen.py entwertete jede gespeicherte Auswertung (real: 4 Gemeinden auf 3 Engine-Fassungen verstreut). Neuer Schluessel: Gemeinde + Kanton + tatsaechlich ausgewertete Dokumente mit SHA-256 ueber den INHALT + modul2_version (Prompt + Schema + Modell + AUSWERTUNG_VERSION). Modul 1 steht bewusst nicht darin: seine Wirkung IST der Dokumentensatz. Dokumente werden vor dem Nachschlagen geladen und gehasht (gemessen 1.26 s fuer 8.1 MB = 1 % des Gemini-Aufrufs). Vertragspruefung beim Lesen ersetzt das grobe Sicherheitsnetz. Rueckfall bei nicht erreichbaren Dokumenten mit sichtbarem Vermerk und Datum. Live belegt: ENGINE_VERSION b89a997a -> a2811286, Analyse trotzdem in 42 s aus dem Speicher, bei Gemini 503 |
| 17.09.2026 | Block 23 | Die beiden Sensitivitaets-Randfaelle liegen ineinander (0.7 m² als Splitter im 96.4-m²-Rand); ihre beiden dauerhaften Etiketten standen uebereinander und das obere zusaetzlich auf "Parzelle 160". Jetzt ein Etikett fuer das Paar -- "Randfaelle 0.7-96.4 m² · keine belastbare Flaeche", um 24 px versetzt -- und zwei unterschiedliche Striche: aussen weit gestrichelt und blass, innen dicht gepunktet und kraeftiger, sonst waere der Splitter unsichtbar. Der einzelne Rand steht beim Ueberfahren und im Popup. Geometrie unveraendert |
| 17.09.2026 | Block 22 | Konsistenz der Oberflaeche am Rheineck-Fall. (1) Das Baurecht zeigte unter dem gruenen "Zone eindeutig zugeordnet" noch die Warnung "laut Klassifikation mehrdeutig -- Kennzahlen unter Vorbehalt". Sie stammte aus dem Zwischenbefund von Modul 1b; massgebend ist jetzt ueberall der Abschluss der Kette. Die Herleitung nennt beides getrennt: "Punktabfrage ergab" und "Daraus zugeordnet". (2) Die Karte zeichnete beide Rechenraender als "Bebaubare Flaeche" mit "Baubereich 0.7 m²" im Popup -- die Zahl, die der Potenzial-Reiter bewusst nicht als Ergebnis ausgibt. Jetzt eigene Ebene "Bebaubare Flaeche -- Randfaelle", gestrichelt, je eigenes Etikett, Popup "Randfall -- keine belastbare Flaeche". Auch die Kaskaden- und SIA-Ueberschriften nennen den Randfall. (3) Karten-Popups durch dieselbe Anzeigeschicht; "limitiert durch geometrie" und der Abzug {'geometrie': 0.69} lesbar gesetzt. (4) "(betroffen)" stand doppelt; Ziffernschrift nur noch fuer Zahlenwerte |
| 17.09.2026 | Block 21 | test_phasen entschaerft: die feste Laufzeitgrenze (`gesamt < 1.6 s`) mass die Auslastung der Maschine, nicht den Code -- unter Last 1.29 bis 6.97 s, allein gelaufen gruen. Sie ist raus. Geblieben und neu dazu: jede Quelle genau einmal abgefragt, jede Antwort im Ergebnis angekommen, hoechste Zahl gleichzeitig offener Abfragen statt Uhrzeit, Abhaengigkeiten als Vorher/Nachher, Nebenlaeufigkeit als Ueberlappung von Zeitfenstern. Die Messung steht als Diagnose in miss_modul1_laufzeit() und kann nicht durchfallen (`--messen` fuer fuenf Laeufe). Unter voller CPU-Last sechsmal gruen |
| 17.09.2026 | Block 20 | Oberflaeche in drei Phasen aufgeraeumt, nur Anzeigeschicht. (1) Interne Schluessel uebersetzt -- "nicht_bestimmbar" stand 62x sichtbar, die Bedingungen einer Kennzahl kamen als roher JSON-Abzug; dazu ASCII-Schreibweisen (fuer, Gebaeude, m2, --). Geschuetzt bleiben Layerkennungen (ch.bfs.gebaeude_wohnungs_register) und Kuerzel (OeZ, OeBA, UeG). (2) Kompakter: Kennzahlen der Zone als Raster statt elf Karten untereinander, kvRows drei Paare je Zeile statt eines ueber 44 % Breite, Abschnittsnummern raus (sie liefen 05-07-06-09-08), zwei Abschnitte hiessen "Entwicklungsszenarien". Bildschirmhoehen: Baurecht 4.3->3.0, Potenzial 3.1->2.4, Markt 2.5->1.3, Quellen 3.3->1.6. (3) Markt-Reiter in drei Datenarten getrennt: externe Marktdaten (keine angebunden) | eigene Vergleichsobjekte (intern) | eigene Annahmen. "59 gefunden, 0 verwertbar" steht jetzt da, mit der Begruendung der Engine je Objekt. "Radar 5806d79bef" wird nie mehr als Name gezeigt, die Kennung steht im Nachweis. Objekte ohne Ortszuordnung (27) sind als solche gekennzeichnet |
| 17.09.2026 | Block 19 | Zonenzuordnung repariert. Rheineck: "BauG_Wohnzone W2" gegen "Wohnzone, 2 Vollgeschosse (W2)" ergab 0.51 und blieb unsicher -- von diesen 0.51 entfielen auf das entscheidende "W2" ganze 0.09. Zwei Brueche behoben: (1) die Nutzungsklassifikation wurde als mehrdeutig verworfen, obwohl die Wohnzone die Parzelle zu 99.8 % deckt und die Landwirtschaftszone zu 0.1 % -- jetzt ueber den Flaechenanteil aufgeloest; (2) der Abgleich vergleicht zuerst das Zonenkuerzel (exakt, nur mit Ziffer: W2, W2H, WG3, ZE4), erst dann den Text. Schwelle unveraendert bei 0.55 -- in Rorschach erreicht "G - Gruenzone" gegen "BauG_Wohnzone W2" 0.54, ein Senken haette dort eine Gruenzone zugeordnet |
| 17.09.2026 | Block 18c | Potenzial-Reiter auf die drei Ebenen umgestellt: Bestand | heutiger Rechtsrahmen | zusaetzliches Potenzial als gleichwertige Cards, darunter sechs eingeklappte Detailbereiche (Herleitung, SIA 416, Flaechen & Wohnungen, Geschosse, Annahmen, Rechenweg). Die Sensitivitaetsbandbreite 0.7-96.4 m2 erscheint nur noch in der Herleitung, nie als Ergebnis · Bericht nutzt ausserhalb des Kartenreiters die Bildschirmbreite · aktiver Reiter war weiss auf weiss (--bg ist nirgends definiert) · Engine-ASCII ("GENAEHERT", "m2") wird fuer die Anzeige uebersetzt, interne Schluessel wie "fussabdruck_x_geschosse" in Nutzersprache |
| 17.09.2026 | Block 18b | Derselbe Fehler eine Ebene weiter hinten: die abgeleitete Bestands-GF (Grundflaeche x Geschosse) wurde wie ein gemessener Wert ausgegeben, und die Differenz zum theoretischen Zonenwert als "-224 m2 Potenzial". Jetzt Grundflaeche, Geschosse und abgeleitete GF getrennt mit Quelle und Status · "zulaessige Gesamtentwicklung" ersetzt durch "GF nach aktueller Ausnuetzungsziffer" · keine Differenz aus theoretischem Wert und Naeherung |
| 17.09.2026 | Block 18 | Grundregel: bestimmen die Eingangsdaten die Gebaeudegeometrie nicht eindeutig, erzeugt die Engine keine exakte Potenzialzahl. Anlass Buhofstrasse 55 Rheineck: der grosse Grenzabstand lag auf ALLEN Nachbarkanten, die Huelle fiel auf 0.69 m2 zusammen, daraus wurde "Potenzial 1 m2" -- auf einer Parzelle mit dreigeschossigem Wohnhaus. Jetzt Bandbreite statt Einzelwert, AZ getrennt belastbar, und Bestand / Neubaugeometrie / Zusatzpotenzial als drei Groessen |
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

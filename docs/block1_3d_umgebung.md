# Block 1 — 3D-Umgebung

**Stand:** 12.09.2026 · **umgesetzt und an echten Daten verifiziert**
**Grundlage:** [LUUCY-Benchmark](benchmark_luucy.md), Schlussfolgerung 1, Punkt 3

## Was sich geändert hat

Vorher: Parzelle, Baubereich und Projektkörper auf leerer Fläche — geometrisch
richtig, räumlich nichtssagend. Ein farbiger Würfel auf Weiss.

Jetzt: **Grundstück + Bestand + Nachbarschaft + Terrain + Strassen +
Projektvolumen** in einem gemeinsamen Höhenbezug.

## Vier von fünf Quellen waren schon da

Der neue Code beschafft fast nichts Neues — er holt vorhandene Abfragen für das
**Umfeld** statt nur für die Parzelle:

| Ebene | Quelle | schon vorhanden für |
|---|---|---|
| Nachbarparzellen | `ch.kantone.cadastralwebmap-farbe` | Kantenklassifikation |
| Gebäudegrundrisse | `ch.swisstopo.vec25-gebaeude` | Bestand |
| Gebäudemerkmale | GWR (`gastw`, `gbauj`, …) | Bestand |
| Strassen | `ch.swisstopo.swisstlm3d-strassen` | Kantenklassifikation |
| **Terrain** | swissALTI3D (DTM2) | **neu** |

Die Auswertung der Gebäudetreffer läuft über dieselben Helfer wie `bestand.py`
(`_polygone_aus_treffer`, `_ring`, `_ganzzahl`) — es gibt keine zweite
Geometrie-Implementierung.

## Terrain ohne 256 Anfragen

Der swisstopo-Höhenprofil-Dienst liefert eine **ganze Linie** je Anfrage. Ein
16×16-Raster kostet damit 16 Anfragen statt 256 — nebenläufig geholt in unter
einer Sekunde. Gemessen an Buchs AG: **die vollständige Szene in 1.2 s.**

```
Terrain:  16×16 Punkte, 383.8–393.1 m ü. M., Maschenweite 16 m
Gebäude:  91 (1 eigenes, 90 Nachbarn), davon 20 ohne bekannte Höhe
Parzellen: 116 Nachbarn
Strassen: 47 Abschnitte (Rosenweg, Bahnstrasse, Jakob Bächlistrasse …)
```

## Höhen werden nicht geraten

Ein Gebäude bekommt seine Höhe aus der GWR-Geschosszahl mal der
Geschosshöhen-Annahme. Gibt es keinen GWR-Eintrag im Grundriss, bleibt die Höhe
`None` mit `hoehe_quelle = "nicht_bestimmbar"` — die Ansicht stellt solche
Gebäude flach dar und **sagt es in der Legende**: *„20 ohne bekannte Höhe —
flach dargestellt."*

Bei mehreren GWR-Einträgen im selben Grundriss gilt die **grösste**
Geschosszahl: das Gebäude ist so hoch wie sein höchster Teil.

## Der gemeinsame Höhenbezug

Die Szene rechnet in Metern in einem lokalen Rahmen: Nullpunkt ist der
Parzellenmittelpunkt, Höhe 0 die Terrainhöhe genau dort. Alles andere sitzt
relativ dazu. Damit passen reale Geländeunterschiede und berechnete Bauhöhen
ohne Umrechnung zusammen — und die Erweiterungen aus dem Benchmark
(Luftbildboden, Sonnenstand, Schnitt) setzen später auf demselben Rahmen auf.

Jedes Objekt trägt seine Terrainhöhe bereits vom Server (`terrain_hoehe_m`),
bilinear aus dem Raster. Fehlt ein Rasterpunkt, wird aus den vorhandenen Ecken
gemittelt; fehlen alle, gibt es **keine** Höhe statt einer erfundenen.

## Bedienung: drei Gruppen statt einer Layerliste

```
UMGEBUNG   [x] Terrain  [x] Gebäude  [x] Strassen
PROJEKT    [x] Grundstück  [x] Baukörper
ANALYSE    Sonne · Schatten · Abstände · Sicht — folgen
```

Die Schalter wirken direkt auf die Szenengruppen — kein Neuaufbau, nur
Sichtbarkeit, also ohne Verzögerung. Die Analyse-Gruppe steht schon da und
nennt, was kommt, statt später eine neue Leiste einzuführen.

**Darstellung:** Nachbargebäude neutral und zurückhaltend (mattes Grau),
Gebäude ohne bekannte Höhe heller und durchscheinend, das eigene Grundstück rot
umrissen, der Baubereich grün, der Projektkörper nach Szenario eingefärbt. Das
Projekt steht damit sichtbar im Mittelpunkt, ohne dass die Umgebung fehlt.

## Auf Abruf, nicht in der Analyse

Eigener Endpunkt `GET /umgebung?job_id=…`, Ergebnis am Job zwischengespeichert.
Die Szene kostet rund eine Sekunde und wird nur gebraucht, wenn jemand die
3D-Ansicht öffnet; ein zweites Öffnen lädt nichts nach. Die Analyse selbst
bleibt schlank — wichtig, weil ihr Ergebnis gespeichert wird.

## Zwei Befunde aus dem Bau

**1 · Ein selbstschneidendes Katasterpolygon kippte die Szene.** `buffer(0)`
repariert es, kann dabei aber ein `MultiPolygon` liefern — das hat kein
`exterior`. Jetzt gilt der grösste Teil. Als Regressionstest abgesichert.

**2 · Die Job-Id hiess anders.** Die neue Abfrage griff auf `jobId` statt
`jobIdAktuell` und lief in einen `ReferenceError` — im Browser gefunden, nicht
im Test, weil die Testsuite offline läuft. Beides gefixt, die Szene lädt.

## Tests

`tests/test_umgebung.py`, 45 Zusicherungen, vollständig offline über Doubles:
Terrain-Interpolation (bilinear, randfest, mit Löchern, ohne jeden Wert),
Gebäudehöhen (nur aus Geschossen, eigen/fremd getrennt, Splitter verworfen),
Rasteraufbau (eine Anfrage je Zeile) und die Gesamtszene.

**13/13 Suiten, 880 Zusicherungen**, kern 2/2.

## Im Browser geprüft

Steuerleiste mit allen drei Gruppen, Canvas gerendert, Legende:
*Baubereich 9 m · 1 eigenes + 90 Nachbargebäude · 20 ohne bekannte Höhe —
flach dargestellt · Terrain 383.8–393.1 m ü. M.*

Umgebung ausgeschaltet → nur Parzelle und Projektkörper (der alte Stand).
Umgebung eingeschaltet → die Nachbarschaft. Genau der Unterschied, um den es
ging.

## Was als Nächstes darauf aufsetzt

Nach dem Benchmark: **Projekte und benannte Varianten**. Die Szene aktualisiert
sich bereits mit dem gewählten Szenario (Bestand → Anbau → Aufstockung →
Ersatzneubau); was fehlt, ist das Speichern und Wiederfinden.

Später auf demselben Höhenbezug, ohne Umbau: Luftbild als Boden, Sonnenstand
(das `DirectionalLight` steht bereits), Schnittansicht (Clipping-Ebene),
Messwerkzeuge.

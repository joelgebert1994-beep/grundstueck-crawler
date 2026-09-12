# Block 3 — Export und Dossier

**Stand:** 12.09.2026 · **umgesetzt und im Browser verifiziert**
**Grundlage:** [LUUCY-Benchmark](benchmark_luucy.md), Schlussfolgerung 1, Punkt 3

## Der Bericht rechnet nicht

Das Dossier ist eine **Darstellung**, keine zweite Rechenstelle. `dossierBauen()`
liest ausschliesslich, was Engine und Wirtschaftlichkeit bereits ermittelt
haben: `ergebnisAktuell`, `wErgebnis`, `variantenVergleich`. Es gibt keine
Formel im Berichtscode.

Das ist keine Stilfrage. Sobald ein Export selbst rechnet, hat man zwei
Wahrheiten, und die auseinanderlaufende ist immer die, die beim Kunden
auf dem Tisch liegt.

## Bestehendes weiterverwendet

Vor dem Bau geprüft, was schon da ist:

| vorhanden | wiederverwendet für |
|---|---|
| `kartenbild()` (WMTS-Kacheln) | Katasterplan und Luftbild im Bericht |
| `bild3D()` (Three.js `toDataURL`) | 3D-Ansicht im Bericht und PNG-Export |
| `quellenobjekt`-Kette | Abschnitt 12 und die Herkunftsvermerke |
| `_rechne_variante()` (Block 2) | Kennzahlen im CSV und im Vergleich |
| `kern/projekt.py` | JSON-Export und -Import |

Neu ist nur der Zusammenbau und der Druckstil. **Kein** serverseitiger
PDF-Renderer: der Browser druckt. Das spart eine Abhängigkeit, die sonst auf
jedem Zielsystem installiert und gepflegt sein müsste, und druckt genau das,
was am Bildschirm steht.

## Die zwölf Abschnitte

```
1  Ergebnis            ← Ergebnisseite zuerst, nicht zuletzt
2  Ausgangslage
3  Baurecht
4  Geometrie und Baukörper
5  Flächen nach SIA 416
6  Wohnungen und Wohnungsmix
7  Markt
8  Kosten nach BKP
9  Wirtschaftlichkeit
10 Szenarienvergleich
11 Risiken und Hinweise
12 Quellen und Belege
```

Abschnitt 1 trägt acht Kennzahlen, die Begründung des Szenarios und die
3D-Ansicht. Wer nur eine Seite liest, hat das Wesentliche.

**Ein Abschnitt ohne Inhalt verschwindet nicht.** Er nennt den Grund:

> **5 · Flächen nach SIA 416**
> Nicht berechnet — für dieses Grundstück liegt keine durchgerechnete
> Variante vor, aus der sich die Flächenkette ableiten liesse.

Vorher fiel er still heraus, und die Nummerierung sprang von 4 auf 6. Eine
Lücke liest sich als Fehler im Dokument; das Fehlen einer Rechnung ist
dagegen selbst eine Aussage und gehört hingeschrieben.

## Herkunft bleibt sichtbar

Jeder Wert trägt seinen Vermerk, im Bericht wie am Bildschirm:

| Vermerk | Bedeutung |
|---|---|
| aus dem Reglement gelesen | amtliche Vorschrift, mit Fundstelle |
| Systemvorschlag | von der Engine hergeleitet |
| eigene Annahme | vom Benutzer gesetzt |
| nicht bestimmbar | keine Grundlage vorhanden |

Im geprüften Bericht: 5 × Reglement, 8 × Systemvorschlag, 3 × eigene Annahme,
1 × nicht bestimmbar. Der Fuss wiederholt es, weil ein Bericht auch
weitergereicht wird:

> Werte mit dem Vermerk „eigene Annahme" sind Kalkulationsannahmen, keine
> amtlichen Tatsachen.

Abschnitt 12 listet alle 26 Belege mit Wert, Inhalt, Quelle, Abrufdatum,
Fundstelle und Sicherheit. Die Quellen sind Links und bleiben im PDF klickbar.

## Vier Formate

| Format | Endpunkt / Weg | Zweck |
|---|---|---|
| PDF | Browser-Druck des Berichtsfensters | der Bericht |
| PNG | `bild3D()` | die 3D-Ansicht einzeln |
| CSV | `GET /projekt/export?format=csv&job_id=` | Kennzahlen nach Excel |
| JSON | `GET /projekt/export?format=json` | Wiederherstellung |

Das CSV nutzt **Semikolon**; mit Komma legt Excel im deutschsprachigen Raum
alles in eine Spalte. Ein nicht berechenbarer Wert bleibt **leer**, nicht 0 —
eine 0 wäre eine Behauptung.

Ohne abgeschlossene Analyse verweigert der CSV-Export die Auskunft, statt eine
leere Tabelle zu liefern:

```
Für den CSV-Export ist eine abgeschlossene Analyse nötig
(job_id fehlt oder abgelaufen).
```

## Der JSON-Export ist wieder importierbar

Enthalten sind EGRID, Projektangaben, alle Varianten mit ihren Deltas und die
aktive Variante. **Nicht** enthalten sind die amtlichen Basisdaten — Parzelle,
ÖREB, Reglement, Geometrie. Die sind über den EGRID reproduzierbar; sie
mitzuschreiben hiesse, eine Momentaufnahme zu konservieren, die beim Import
schon veraltet sein kann. Die Datei bleibt dadurch bei **2.2 kB**.

Ein Import legt **immer ein neues Projekt** an. Er darf keine vorhandene
Arbeit still verdrängen.

Eine unbrauchbare Datei wird abgelehnt, nicht halb eingelesen:

```
leeres Objekt  → Unbekanntes Format None -- erwartet 'gebimo.projekt/1'.
fremdes Format → Unbekanntes Format 'luucy/1' -- erwartet 'gebimo.projekt/1'.
ohne EGRID     → Ohne EGRID lässt sich das Projekt nicht wiederherstellen.
```

## Druckqualität

```
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-right { content: counter(page) " / " counter(pages); } }
.dtab thead { display: table-header-group; }   /* Kopfzeile auf jeder Seite */
.dsec.umbruch { break-before: page; }
.dkzgrid, .dkz, .dbild, .dbildpaar { break-inside: avoid; }
```

Eigenes Stylesheet, getrennt von der Arbeitsoberfläche: der Bericht soll auf
Papier funktionieren, nicht auf einem dunklen Bildschirm. Es liegt als
`<script type="text/plain" id="dossier-stil">` in der Seite — so beeinflusst
es die Anwendung nicht und geht unverändert ins Berichtsfenster.

8 erzwungene Seitenumbrüche, Kennzahlenkacheln und Bilder brechen nie
mittendrin.

## Drei Befunde aus dem Browsertest

**1 · `[object Object]` in der Quellentabelle.** Ein Quellenwert kann Zahl,
Text, Liste oder verschachteltes Objekt sein. `oereb.umweltrisiken` ist eine
Themenkarte mit `{status, details}` je Thema und landete als
`belastete_standorte [object Object], …` im Bericht. `dwert()` löst das jetzt
rekursiv auf und liest bei einem ÖREB-Thema den `status`:

> belastete standorte: nicht betroffen, grundwasserschutz: nicht betroffen,
> gewaesserraum: nicht betroffen, **laermempfindlichkeitsstufen: betroffen**

**2 · Die Kürzungsgrenze schnitt die einzige Auflage ab.** Bei 110 Zeichen
fiel genau das letzte Thema weg — dasjenige, das *betroffen* ist. Die Grenze
liegt jetzt über dem längsten real vorkommenden Wert (144 Zeichen), und wo
doch gekürzt wird, steht ein „…". Keine Kürzung ohne sichtbares Zeichen.

**3 · Ein Konflikt wurde verschluckt.** Abschnitt 11 las `k.text`; ein
Konflikt trägt seine Aussage aber in `k.meldung`. Der Bericht druckte
`ausnuetzung: [object Object]` statt:

> Die Geometrie liesse 351 m² zu, die Nutzungsziffern begrenzen auf 299 m² —
> das Baurecht ist hier die engere Schranke.

Der sichtbarste Fehler war der harmloseste. Der teure war, dass ein Satz über
die eigentliche Schranke des Projekts nicht im Bericht stand.

## Geprüft

**Export → Datei → Import → gerechnet**, über die echten HTTP-Endpunkte:

| | Original (7) | Import (8) |
|---|---|---|
| EGRID | CH975272732334 | CH975272732334 |
| aktive Variante | Ersatzneubau | Ersatzneubau |
| eigene Annahmen | boden, miete, verkauf, mix | boden, miete, verkauf, mix |
| Wohnfläche NWF | 197 m² | 197 m² |
| Wohnungen | 2 | 2 |
| Verkaufserlös | 1'425'000 CHF | 1'425'000 CHF |
| Gesamtinvestition | 1'648'206 CHF | 1'648'206 CHF |
| Gewinn | −223'206 CHF | −223'206 CHF |
| Marge | −15.66 % | −15.66 % |
| Max. Landwert | 191'889 CHF | 191'889 CHF |

Die CSV-Ausgabe beider Projekte ist **zeichengleich**. Das importierte Projekt
wurde anschliessend in der Oberfläche geöffnet und ergab denselben Bericht:
12 Abschnitte, 3 echte Bilder, 26 Belege, 5 Vergleichszeilen, kein
`[object Object]`, kein `undefined`, kein `NaN`.

## Endpunkte

| Endpunkt | Zweck |
|---|---|
| `GET /projekt/export?id=&format=json[&verlauf=1]` | Projektdatei |
| `GET /projekt/export?id=&format=csv&job_id=` | Kennzahlen aller Varianten |
| `POST /projekt/import` | Wiederherstellung als neues Projekt |

## Tests

`kern/tests/test_projekt.py` — **90 Zusicherungen** (vorher 54), davon neu:
Export vollständig und ohne amtliche Basisdaten, Deltas erhalten, aktive
Variante als Name statt ID, Rundlauf Export → Import → Export, Import als
neues Projekt ohne Verdrängung, fünf Abweisungsfälle ohne halbe Projekte,
CSV-Trennzeichen, Zeilenenden, Spaltenzahl, Leerwerte.

**Engine 13/13 Suiten (880 Zusicherungen), kern 3/3.**

## Was noch fehlt

* **Import in der Oberfläche** — der Endpunkt ist da, ein Dateiwähler fehlt.
* **Eigenes Deckblatt / Logo** — kommt, wenn die Gestaltung steht.
* **Auswahl der Abschnitte** vor dem Druck.
* **Serverseitiges PDF** für den unbeaufsichtigten Versand — erst nötig, wenn
  Berichte automatisch verschickt werden.

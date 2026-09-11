# Stufe 2 — Kantenklassifikation (G2)

**Stand:** 11.09.2026 · **umgesetzt und live verifiziert**
**Voraussetzung:** Stufe 1 abgeschlossen (Commit `96514f1`)

## Problem

`baubereich.py` (G1) rechnet die Baubereich-Kaskade mit **kantenspezifischen**
Grenzabständen — genau dafür wurde die Mitre-Konstruktion gebaut. Geliefert wird
ihm heute aber nur eine Bandbreite: `alle_kanten_klein` gegen `alle_kanten_gross`
(siehe `g1_verdrahtung.py`, `_grenzabstand_bandbreite_pro_kante`). Der Grund steht
seit jeher im Docstring: niemand weiss automatisch, welche Kante zur Strasse zeigt.

Solange das so bleibt, ist der teuerste Teil der Engine (die Geometrie) auf eine
Spannweite reduziert, die für eine Investitionsentscheidung zu breit ist.

## Entscheid: geometrischer Nachweis statt geratener Schwellenwert

Der naheliegende Weg — "Strasse, wenn eine Strassenachse innerhalb der Toleranz
liegt" — ist **nicht** belastbar: die `tolerance` von `_identify()` ist in
**Pixeln** angegeben, nicht in Metern (bei `mapExtent` 2000 m auf 1000 px sind
das 2 m je Pixel). `tolerance=8` heisst also ~16 m — damit wird jeder Nachbargarten
zur Strasse.

Stattdessen entscheidet ein Schnitt-Test, der keinen Schwellenwert braucht:

| Was liegt hinter der Kante? | Strassenachse verläuft durch dieses Polygon? | Ergebnis |
|---|---|---|
| Katasterpolygon (nicht das eigene) | ja | `strasse` (Strassenparzelle) |
| Katasterpolygon (nicht das eigene) | nein | `nachbarparzelle` |
| kein Katasterpolygon | Achse in der Nähe | `strasse` (nicht parzellierter Strassenraum) |
| kein Katasterpolygon | keine Achse | `unbestimmt` |

Das ist zugleich die in der Machbarkeitsprüfung offene Verfeinerung: **Strassen-
parzellen sind echte Parzellen** und erscheinen sonst als Nachbar.

## Live verifiziert (Buchs AG, Parzelle 1145, `CH975272732334`)

```
Kante  0   13.8 m  nachbarparzelle  Parzelle 1144 (CH867223527363)
Kante  1   41.0 m  strasse          Parzelle 1143 -- Strassenachse verlaeuft durch
Kante 42    9.8 m  strasse          Parzelle 303  -- Strassenachse verlaeuft durch
Kante 43   28.9 m  nachbarparzelle  Parzelle 316
Kante 44   12.7 m  nachbarparzelle  Parzelle 1762
```

5 von 5 relevanten Kanten (≥ 3 m) zugeordnet, 0 unbestimmt. Umfeld: 97 Kataster-
polygone, davon 18 von einer Strassenachse durchquert.

## Layer-Befund (geprüft, nicht angenommen)

| Layer | Status |
|---|---|
| `ch.swisstopo.swisstlm3d-strassen` | **funktioniert**, liefert `strassenname` + `objektart` |
| `ch.kantone.cadastralwebmap-farbe` | **funktioniert**, liefert `number` + `egris_egrid` |
| `ch.swisstopo.vec25-strassennetz` | HTTP-Fehler |
| `ch.bafu.wald-wald_lebensraum`, `ch.swisstopo.swisstlm3d-wald` | HTTP-Fehler |
| `ch.swisstopo.vec25-gewaessernetz_referenz`, `ch.swisstopo.swisstlm3d-gewaessernetz` | 0 Treffer |

Wald und Gewässer brauchen hier **keinen** eigenen Layer: `restriktionsgeometrie.py`
liefert Waldabstand und Gewässerraum bereits als Flächen, die G1 abzieht. Die
Kantenklassifikation beschränkt sich deshalb bewusst auf `strasse` /
`nachbarparzelle` / `unbestimmt` — das ist genau die Unterscheidung, die den
Abstandswert bestimmt.

## Der Strassenabstand (bei der Analyse offen, inzwischen umgesetzt)

Modul 2 extrahierte `grenzabstand_klein_m` und `grenzabstand_gross_m` — **keinen
Strassenabstand** (`_ZONE_KENNZAHL_FELDER` in `modul2_bzo_analysis.py`). Klein/gross
ist die Unterscheidung schmale/breite Fassade, *nicht* Strasse/Nachbar.

Die Klassifikation allein ändert die Zahlen also nicht. Deshalb kam `strassenabstand_m`
als eigenes Feld ins Zonen-Schema, mit derselben Ehrlichkeitsdisziplin
(`confidence: nicht_bestimmbar` statt Schätzwert); der System-Prompt verbietet die
Ableitung aus dem Grenzabstand ausdrücklich.

**Fallback-Regel, wenn kein Strassenabstand gefunden wird:** die betroffene Kante
wird als `abstand_nicht_bestimmbar` geführt und behält die Bandbreite. Auf keinen
Fall ersatzweise `grenzabstand_gross_m` einsetzen — das wäre Scheingenauigkeit.

## Umsetzung (abgeschlossen)

Live verifiziert an Buchs AG 1145 durch die gesamte Pipeline:

```
Kante  0   13.8 m  nachbarparzelle  Parzelle 1144   -> 6.00 m (grenzabstand_gross_m)
Kante  1   41.0 m  strasse          Rosenweg        -> 4.00 m (strassenabstand_m)
Kante 42    9.8 m  strasse          J. Baechlistr.  -> 4.00 m (strassenabstand_m)
Kante 43   28.9 m  nachbarparzelle  Parzelle 316    -> 6.00 m (grenzabstand_gross_m)
Kante 44   12.7 m  nachbarparzelle  Parzelle 1762   -> 6.00 m (grenzabstand_gross_m)

G1-Modus kantenklassifikation: Baubereich 117.1 m2
Kontrollbandbreite unveraendert: 57.23 .. 206.76 m2
```

Der Strassenabstand kam als eigenstaendiger Wert aus § 111 Abs. 1 lit. a BauG
Aargau ("gegenueber Kantonsstrassen 6 m, gegenueber Gemeindestrassen 4 m"),
nicht aus dem Grenzabstand. Genau diese Staffelung nach Strassenklasse steht
als Vorbehalt an jeder Strassenkante — die Objektart der Achse wird bereits
mitgefuehrt (`strassen_objektart`), aber noch nicht ausgewertet.

## Umsetzungsschritte (alle erledigt)

1. `potenzial_engine/kantenklassifikation.py` — `klassifiziere_kanten(ring, e, n)`:
   je Kante Länge, Art, Begründung, Beleg (Nachbar-EGRID bzw. Strassenname),
   Layer-Quelle. Mindestlänge 3 m; kürzere Kanten werden als nicht relevant
   geführt, nicht stillschweigend weggelassen.
2. Quellennachweise je Kante über `quellen.py` (Layer + Abfragezeitpunkt).
3. `modul2_bzo_analysis.py`: `strassenabstand_m` ins Zonen-Schema und in den
   System-Prompt.
4. `g1_verdrahtung.py`: neuer Modus `kantenklassifikation`, der die Abstände je
   Kante zuordnet; Bandbreite bleibt als Ehrlichkeitskontrolle daneben stehen.
5. Tests: Kantenklassifikation offline über Doubles (Ringgeometrie + simulierte
   Layer-Antworten), dazu ein Live-Fall Buchs 1145 in `test_klassifikation.py`.
6. Kantenprotokoll im Dossier (`dist/index.html`), Abschnitt BAURECHT.

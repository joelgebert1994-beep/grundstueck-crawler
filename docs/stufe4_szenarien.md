# Stufe 4 — Entwicklungsszenarien

**Stand:** 11.09.2026 · **umgesetzt und an realen Daten verifiziert**
**Voraussetzung:** Stufe 3 abgeschlossen (Commit `d5b3178`)

## Was gebaut wurde

`entwicklungsszenarien.py` legte 2026 die Taxonomie fest und sagte ausdrücklich:
keine Rechenlogik. Diese Stufe liefert sie — aus Daten, die bereits vorlagen.
Zwei neue Module:

* **`bestand.py`** — alle Gebäude der Parzelle mit Grundriss, Geschosszahl,
  Baujahr, Nutzung und Volumen.
* **`szenarien.py`** — sechs baulich abgeleitete Szenarien mit Machbarkeit,
  Konflikten, Baukörpergeometrie, Geschossen, Höhen, Flächen und Wohnungen.

### Der Bestand nahm bisher die Garage

`get_gwr_data()` nahm `results[0]` einer Toleranzabfrage — derselbe Fehlertyp
wie der am 04.09. behobene Parzellen-Bug. Live an Buchs AG 1145 nachgewiesen:
die Abfrage liefert dort drei GWR-Einträge, und `results[0]` war die **Garage**
(EGID 263024777, 9 m², keine Geschosszahl, kein Baujahr) statt des Wohnhauses
(EGID 524242, 68 m², **2 Geschosse**, Baujahr 1918).

Für Stufe 4 ist das zentral: die Aufstockungsprüfung vergleicht die bestehende
Geschosszahl mit der zulässigen. Mit der Garage als Bestand käme
„Geschosszahl unbekannt" heraus, wo zwei Geschosse stehen.

`bestand.py` liest deshalb alle GWR-Einträge **innerhalb** des
Parzellenpolygons, dazu die Gebäudegrundrisse aus
`ch.swisstopo.vec25-gebaeude`, und ordnet sie über Punkt-in-Polygon zu. Das
Hauptgebäude ist die grösste Wohnnutzung.

Zwei Flächenbegriffe bleiben getrennt: `grundflaeche_gwr_m2` ist der
Registerwert (GWR-Merkmal `garea`), `grundriss_flaeche_m2` die Fläche des
Kartengrundrisses. An Buchs stehen 115.0 m² Grundriss gegen 98 m² GWR-Summe.
VEC25 ist generalisiert (1:25'000), das GWR ein Register — beide Werte sind
echt, der Unterschied wird ausgewiesen statt verrechnet.

### Das Ausnützungsbudget ist die zentrale Prüfung

Für Anbau, Aufstockung und Kombination gilt: **was das Baurecht insgesamt
zulässt, minus was der Bestand belegt.** Ist es aufgebraucht, ist keine
Erweiterung möglich — egal wie viel Platz auf der Parzelle frei wäre. Genau
das ist der Fall aus der Produktspezifikation.

Die Bestands-Geschossfläche entsteht aus Grundriss × Geschosszahl und wird
ausdrücklich als **Näherung** geführt: der Grundriss stammt aus einem
generalisierten Datensatz, und nicht jedes Geschoss hat die
Erdgeschossfläche. Eine Planabrechnung ersetzt sie.

### Die sechs Szenarien

| Szenario | Ableitung |
|---|---|
| **Bestand** | Gebäude, Geschosse, Baujahr, Nutzung aus GWR + Grundriss |
| **Anbau** | Baubereich **minus** Bestandsgrundriss → freie Teilflächen, je mit Fläche, maximalen Massen (kleinstes umschliessendes Rechteck) und Himmelsrichtung |
| **Aufstockung** | Vergleich Bestandsgeschosse gegen zulässige, dann Ausnützungsbudget, dann Höhenvergleich |
| **Dachausbau / Attika** | **bewusst nicht** über die Vollgeschoss-Logik — siehe unten |
| **Ersatzneubau** | G1-Baubereich; trennt theoretisch zulässig von geometrisch umsetzbar |
| **Bestand + Neubau** | wie Anbau, aber mit Gebäudeabstand zum Bestand |

Die Himmelsrichtung kommt aus dem Vektor Bestandsschwerpunkt → Restfläche,
die Maximalmasse aus `minimum_rotated_rectangle` (eine schräg liegende
Restfläche hätte in einer achsparallelen Bounding Box falsche Masse).

Eine Restfläche muss mindestens **15 m²** gross und **2.5 m** breit sein. Ein
40 m langer, 1.2 m breiter Streifen hat rechnerisch 48 m², ist aber kein
Anbauplatz — solche Flächen werden als Konflikt benannt, nicht stillschweigend
verworfen.

### Dach und Attika bleiben offen — und das ist die richtige Antwort

Ob ein Dachgeschoss ausgebaut oder ein Attikageschoss aufgesetzt werden darf,
hängt an Dachform, Kniestockhöhe, Rückversatz und Anrechenbarkeit. Die
Reglementsauswertung liefert davon heute keinen strukturierten Wert. Diese
Lücke mit der Vollgeschoss-Regel zu füllen wäre genau die Scheingenauigkeit,
die ausgeschlossen ist. Das Szenario ist deshalb `nicht_bestimmbar` und nennt,
welche Angaben fehlen. Wird `attika_zulaessig` übergeben, ändert sich die
Beurteilung — auch die der Aufstockung.

## Drei Befunde aus den Realdaten

**1 · „Kein Gebäude" war irreführend.** Wilen 18a meldete 2 Gebäude im
Bestand, der Anbau sagte „Kein Gebäude auf der Parzelle". Beides stimmte für
sich: es gibt GWR-Einträge, aber keinen Grundriss in VEC25. Die Meldung
unterscheidet das jetzt, und der Fall ist `nicht_bestimmbar` statt
`nicht_moeglich`.

**2 · Überbaute Parzellen.** Uettligen: der Bestand belegt 713 m²
Geschossfläche, das heutige Recht liesse 470 m² zu. Solche Bauten geniessen in
der Regel Besitzstandsgarantie. Das Budget weist die Überbauung jetzt
ausdrücklich aus.

**3 · Der Ersatzneubau wäre kleiner als der Bestand.** Dieselbe Parzelle: ein
Abbruch gibt 243 m² Geschossfläche auf. Das ist eine wirtschaftliche
Entscheidung, keine baurechtliche — und erscheint als eigener Konflikt
`besitzstand`.

## Visualisierung

**2D:** zwei neue Kartenebenen. `bestand` zeigt die echten Gebäudegrundrisse
mit GWR-Merkmalen im Popup; `szenario` zeigt die Baukörper des gewählten
Szenarios, eingefärbt nach Art (Bestand grau, Anbau orange, Aufstockung
violett, Ersatzneubau grün, Neubau blau), jeweils mit Fläche, Maximalmassen,
Geschossen, Höhe und Herkunft.

**3D:** Three.js (r128, von cdnjs). Jedes Volumen ist das Extrudat eines real
berechneten Polygons mit der berechneten Höhe — Parzelle flach, Baubereich
flach, Baukörper nach `geschosse × geschosshoehe`. Ist keine Höhe bekannt,
wird der Körper **flach** dargestellt statt geraten. Ziehen dreht, Scrollen
zoomt, die Szenarienwahl schaltet um.

Live im Browser geprüft: Canvas 1060 × 420 px, Three.js geladen, Umschalten
zwischen den Szenarien ändert Volumen und Legende (Bestand 6 m grau →
Ersatzneubau 9 m grün).

Die Höhe ist ausdrücklich die **konstruktive** Höhe des Baukörpers, nicht die
baurechtliche Gebäude- oder Gesamthöhe: die misst ab gewachsenem Terrain und
hängt an der Dachform.

## Realtests

8 Parzellen mit echtem Bestand (GWR + Grundrisse live), G1 aus den
gespeicherten Analysen:

| Regelungssystem | Fall |
|---|---|
| AZ | Buchs AG (0.5), Uettligen (0.5), Russikon (20.0, gemeldet) |
| aBGF | Wilen (0.8), Steckborn (0.75), Hünibach (0.45) |
| mehrere Höhenregeln | Graltshausen (2 VG, GH 8.5, GesH 13.0) |
| nur Geometrie | Madiswil (2 VG, GH 6) |
| Bestand + Attika | Buchs AG (2 Geschosse, Baujahr 1918, Garage separat) |
| überbaute Parzelle | Uettligen (713 gegen 470 m²) |
| Gebäude ohne Grundriss | Wilen 18a |

Verteilung über alle Fälle: Ersatzneubau 6× möglich / 2× eingeschränkt ·
Anbau 2× möglich / 3× eingeschränkt / 1× nicht bestimmbar / 2× nicht möglich ·
Aufstockung 1× eingeschränkt / 3× nicht bestimmbar / 4× nicht möglich ·
Bestand + Neubau 5× eingeschränkt / 1× nicht bestimmbar / 2× nicht möglich ·
Dachausbau 8× nicht bestimmbar.

Dass die Aufstockung so oft ausfällt, ist kein Fehler: in gewachsenen
Schweizer Ortskernen ist die zulässige Geschosszahl regelmässig ausgeschöpft.

**Einschränkung:** nur Buchs AG hat nach Stufe 2 eine vollständige
Kantenzuordnung und damit ein echtes G1-Einzelergebnis. Für die übrigen sieben
wurden die Szenarien für den Realtest auf dem konservativen Bandbreiten-Rand
**erzwungen** und als solche beschriftet. Die Engine selbst verweigert diesen
Fall: Szenarien auf einem willkürlich gewählten Rand wären nicht belastbar.

## Schnittstelle

```python
from potenzial_engine import analysiere_grundstueck, berechne_szenarien, WohnungstypVorgabe

analyse = analysiere_grundstueck("Rosenweg 4, 5033 Buchs AG")
analyse.ergebnis["szenarien"]          # alle sechs, ohne Wohnungsmix

berechne_szenarien(                    # Millisekunden, keine erneute Abfrage
    analyse,
    auswahl=["ersatzneubau", "aufstockung"],
    wohnungsmix=[WohnungstypVorgabe("3.5 Zi", 88.0, anteil=1.0)],
    attika_zulaessig=True,
    gebaeudeabstand_m=6.0,
)
```

Jedes Szenario ist über `to_dict()` eigenständig serialisierbar — die
Voraussetzung dafür, dass Markt, BKP und Wirtschaftlichkeit später je Szenario
getrennt gerechnet und gespeichert werden.

## Offene Punkte

* **Baulinien** werden als Konflikt gemeldet, aber nicht vom Baubereich
  abgezogen — welche Baulinie welcher Kante zugeordnet ist, ist nicht
  automatisiert.
* **Der Gebäudeabstand** zwischen zwei Bauten auf derselben Parzelle ist
  kantonal geregelt und liegt nicht strukturiert vor. Ohne Vorgabe wird
  **kein** Abstand abgezogen; die ausgewiesene Fläche ist dann eine Obergrenze.
* **Die Statik** einer Aufstockung ist nicht geprüft und wird als solche
  benannt.
* **Terrain und Nachbargebäude** fehlen in der 3D-Ansicht noch.
* **Wo genau** der Baukörper im Baubereich steht, ist eine Entwurfsfrage und
  wird nicht vorweggenommen — der Baubereich zeigt die mögliche Lage.

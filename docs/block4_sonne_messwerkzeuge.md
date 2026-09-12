# Block 4 — Sonne, Schatten und Messwerkzeuge

**Stand:** 12.09.2026 · **umgesetzt und im Browser gegen echte Daten geprüft**
**Grundlage:** die räumliche Basis aus [Block 1](block1_3d_umgebung.md)

## Keine neue Geometrie

Beschattet und gemessen wird genau das, was schon in der Szene steht: das
Terrain aus dem Höhenmodell, die Gebäude aus dem Gebäuderegister, der
Projektkörper aus der Berechnung. Es entsteht keine zweite Höhenlogik und
keine unsichtbare Messfläche.

Der Bezugsrahmen der Szene wird beim Aufbau **einmal** festgehalten:

```js
szeneRahmen = { mx, my, basis, spanne };
```

`mx`/`my` sind der LV95-Nullpunkt der Ansicht, `basis` die Terrainhöhe dort.
Die Messung rechnet damit zurück — sie leitet nichts eigenständig her.

## Sonnenstand: gerechnet wird in Python

Die Astronomie steht in `potenzial_engine/sonnenstand.py` und rechnet nach
dem Verfahren des NOAA Solar Calculator (Meeus). Im Browser steht **keine
zweite Sonnenformel**.

Der Zeitschieber braucht flüssige Bewegung, ein Serveraufruf je Bild wäre
unbrauchbar. Deshalb liefert `/sonne` den **ganzen Tag** als Stützstellen
(alle 10 Minuten, 145 Werte), und die Ansicht bewegt sich nur noch zwischen
ihnen. Zwischen zwei Stützstellen ändert sich die Sonnenhöhe um höchstens
1.7° — fein genug, und die Rechnung bleibt an einer prüfbaren Stelle.

### Die Achsen stehen an genau einer Stelle

Der Server liefert einen Einheitsvektor zur Sonne als `(ost, nord, hoch)`.
Die Ansicht bildet ihn ab:

```js
sonnenlicht.position.set(stand.ost * w, stand.hoch * w, -stand.nord * w);
```

Die Szene rechnet mit `+X = Ost`, `−Z = Nord`, `+Y = hoch`. Wer hier ein
Vorzeichen dreht, baut Schatten in die falsche Richtung — und das fällt sonst
niemandem auf. Deshalb ist die Zuordnung eine einzige Zeile, und die
Himmelsrichtung wird in Python getestet.

### Zeitzone

Gerechnet wird durchgehend in UTC; die Umrechnung macht `zoneinfo` mit der
echten Sommerzeitregel. Ein Zeitpunkt ohne Zonenangabe wird **abgewiesen**:
zwischen 13:30 MESZ und 13:30 MEZ liegt eine volle Stunde Schattenwurf.

## Was die Ansicht zeigt

```
☑ Sonne & Schatten    [Datum 2026-12-21] [Heute] ──────────▮──── [▶ Ablauf]
12:30 · Azimut 181° (S) · Höhe 19.2° · Schatten 2.9 m je m Bauhöhe
Aufgang 08:12 · Höchststand 12:25 (19°) · Untergang 16:39
```

**Schatten je Meter Bauhöhe** ist die Zahl, um die es beim Nachbarn geht:
2.9 m zur Winterwende gegen 0.9 m im September. Sie steht deshalb direkt
neben dem Sonnenstand.

Der Ablauf spielt von Sonnenauf- bis -untergang. Die Nacht mitlaufen zu
lassen hiesse, die halbe Zeit auf eine unbeleuchtete Szene zu schauen.
Steht die Sonne unter dem Horizont, gibt es kein Licht und keinen Schatten —
die Ansicht sagt das, statt eine Beleuchtung zu erfinden.

## Messwerkzeuge

| Werkzeug | Ergebnis |
|---|---|
| **Distanz** | waagrecht · schräg · Höhenunterschied |
| **Fläche** | m² waagrecht projiziert · Umfang · Punktzahl |
| **Höhe** | Höhenunterschied · von/auf m ü. M. |
| **Punkt** | LV95 E/N · m ü. M. · m über Parzellenmitte |

Zwei Festlegungen, die fachlich zählen:

**Die Distanz wird waagrecht geführt.** Im Baurecht zählt das waagrechte Mass
(Grenz- und Gebäudeabstand). Das schräge steht daneben, damit klar ist,
welches gemeint ist — nicht damit man es verwechselt.

**Die Fläche ist ausdrücklich die waagrechte Projektion.** Am Hang ist die
Geländefläche grösser als ihre Projektion. Wer das verwechselt, bekommt zu
viel Ausnützung heraus.

Gezeichnet wird in der Szene: Punkte als Kugeln, Strecken als Linien, beim
Höhenmass die senkrechte Strecke. Die Beschriftungen liegen als HTML über der
Ansicht und werden je Bild an die projizierte Lage gesetzt — dadurch bleiben
sie bei jedem Zoom scharf.

Ziehen dreht die Ansicht, Klicken misst. Unterschieden wird am zurückgelegten
Weg: wer dreht, bewegt die Maus dabei zwangsläufig.

## Der Befund aus dem Browsertest

**Die Schatten waren da — nur nicht zu sehen.**

Die erste Fassung war vollständig richtig konfiguriert: Schattenkarte an,
90 Gebäude als Werfer, Terrain als Empfänger, Schattenkamera korrekt über der
Szene. Trotzdem lag auf dem Boden nichts.

Die Ursache war das Terrain aus Block 1. Es ist mit **55 % Deckkraft**
gezeichnet, damit der Untergrund durchscheint. Über einem hellen Hintergrund
wäscht das den Schatten so weit aus, dass er praktisch verschwindet: aus
einem Unterschied von 31 % wurden 13 %, und der Rest ging im Farbverlauf des
Geländes unter.

Im Schattenmodus wird das Terrain deshalb undurchsichtig und danach wieder
durchscheinend. Die Deckkraft steht jetzt als eine Konstante da, nicht als
zwei Zahlen an zwei Stellen.

Der Weg dorthin ist erwähnenswert, weil er beinahe in die falsche Richtung
geführt hätte: die naheliegende Vermutung war ein Fehler in der
Schattenrechnung. Erst ein Kontrollkörper — ein undurchsichtiger Klotz über
einer undurchsichtigen Ebene — zeigte, dass der Schattenwurf einwandfrei
arbeitete. Gesucht war nicht der Rechenfehler, sondern die Darstellung.

## Im Browser geprüft, gegen echte Daten

Rosenweg 4, Buchs AG (EGRID CH975272732334), 90 Gebäude aus dem Register,
Terrain aus dem Höhenmodell:

| Prüfung | Ergebnis |
|---|---|
| Schatten bei Westsonne (18:20, 261°) | fallen nach Osten ✓ |
| Schatten bei Ostsonne (08:00, 94°) | fallen nach Westen ✓ |
| Winterwende 21.12., 12:30 | Höhe 19.2°, Schatten 2.9 m je m ✓ |
| Sonnenzeiten 21.12. | 08:12 / 12:25 / 16:39 — deckungsgleich mit den Python-Tests |
| Distanz | 64.59 m waagrecht, 64.74 m schräg, 4.40 m Höhe — √(64.59²+4.40²) = 64.74 ✓ |
| Fläche | 677.1 m², Umfang 110.2 m, 4 Punkte |
| Höhe | 6.32 m, von 386.8 auf 393.2 m ü. M. |
| Punkt | LV95 2'647'665 / 1'248'699 · 390.5 m ü. M. |
| Gemessene Höhen | liegen im amtlichen Terrainbereich 380.5–401.1 m ü. M. ✓ |
| Ablauf | läuft, pausiert, nimmt den Faden wieder auf |
| Szenarienwechsel | Messungen bleiben, keine Geistermessung (1 vor, 1 nach drei Wechseln) |
| Zurücksetzen | leert Liste und Szene |

Die gemessenen Höhen gegen den amtlichen Terrainbereich zu halten, ist die
eigentliche Genauigkeitsprobe: sie prüft den Massstab der Szene gegen eine
Quelle, die nicht aus der Messung stammt.

## Endpunkt

| Endpunkt | Zweck |
|---|---|
| `GET /sonne?lat=&lon=&datum=[&schritt=]` | Tagesverlauf, Auf- und Untergang, Höchststand |

Fehlt Breite/Länge zum Grundstück, bleibt die Sonne aus und die Ansicht sagt
warum — statt einen Standort anzunehmen.

## Tests

`tests/test_sonnenstand.py`, **74 Zusicherungen**, offline und ohne
Referenztabelle. Geprüft wird gegen Himmelsmechanik statt gegen abgeschriebene
Zahlen:

* Sonnenwenden: 90° − Breite ± 23.44° — das ist die Definition der Wende
* Tagundnachtgleiche: Aufgang im Osten, Untergang im Westen, überall
* Symmetrie von Auf- und Untergang um den Höchststand
* Südhalbkugel: Mittagssonne im Norden — der Test gegen das gedrehte Vorzeichen
* Richtungsvektor: Länge 1 und deckungsgleich mit Azimut und Höhe
* Sommerzeit, Polartag, Polarnacht, Refraktion am Horizont

**Ein echter Fehler kam dabei heraus:** `tagesverlauf()` rechnete mit
`timedelta` auf einer zonenbehafteten Ortszeit — das ist **Wanduhrzeit**, nicht
echte Minuten. An den beiden Umstellungstagen lagen die Stützstellen dadurch
ungleich weit auseinander. Gezählt wird jetzt in UTC, angezeigt in Ortszeit;
der Frühlingstag hat 24 Stützstellen, der normale 25, der Herbsttag 26.

**Engine 14/14 Suiten (954 Zusicherungen), kern 3/3.**

## Was noch fehlt

* **Besonnungsdauer** je Fassade oder Fenster in Stunden — die Geometrie
  trägt es, die Auswertung fehlt.
* **Verschattungsnachweis** nach kantonaler Vorgabe (z. B. 2-Stunden-Regel).
* **Messung im Kartenbild**, bisher nur in der 3D-Ansicht.
* **Messungen ins Dossier** übernehmen.

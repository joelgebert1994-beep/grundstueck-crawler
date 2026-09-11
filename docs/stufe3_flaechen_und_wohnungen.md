# Stufe 3 — Baurecht → Fläche → Wohnung

**Stand:** 11.09.2026 · **umgesetzt und an realen Daten verifiziert**
**Voraussetzung:** Stufe 2 abgeschlossen (Commit `8451533`)

## Was gebaut wurde

`potenzial_engine/flaechenmodell.py` schliesst die Lücke zwischen dem, was G1
geometrisch und baurechtlich ermittelt, und einer wirtschaftlich brauchbaren
Flächen- und Wohnungsaussage. G1 wurde dafür **nicht** angefasst: die Kaskade
Grundstück → anrechenbare Fläche → Fussabdruck → Geschosszahl →
Geschossfläche samt limitierender Grösse lag bereits vor.

### Die Flächenkaskade folgt der Norm, nicht einem Pauschalsatz

SIA 416 definiert Messgrössen, keine Verhältnisse zwischen ihnen:

```
GF  = NGF + KF
NGF = NF + VF + FF
NF  = HNF + NNF
```

`sia416_flaechen.berechne_sia416_kaskade()` kennt jetzt beide Wege dorthin:

* **detailliert** — `kf_anteil_an_gf` und `vf_ff_anteil_an_ngf`; dann ist auch
  die NGF bestimmt. Das ist der Weg, den Stufe 3 geht.
* **pauschal** — ein einziges `nf_anteil_an_gf`; dann bleibt die NGF
  `nicht_bestimmbar`, denn aus einem NF/GF-Verhältnis allein lässt sich die
  Trennlinie zwischen KF und VF/FF nicht rekonstruieren.

Beide gleichzeitig anzugeben ist ein Widerspruch und wird zurückgewiesen —
es wird nicht stillschweigend einer bevorzugt. Auch der detaillierte Weg mit
nur einer der beiden Annahmen ist ein Fehler: die zweite Hälfte liesse sich
nur über einen erfundenen Ersatzwert schliessen.

### Annahmen statt eingebauter Prozentsätze

Jeder Abzug ist ein benannter, begründeter, editierbarer Parameter mit
sichtbarer Herkunft. Drei Ebenen, die nie vermischt werden:

| Herkunft | Bedeutung |
|---|---|
| `referenz` | aus Vergleichsobjekten/externen Quellen (Ebene existiert, noch keine Quelle angebunden) |
| `systemannahme` | dokumentierter Vorschlag des Systems |
| `benutzerannahme` | vom Benutzer gesetzt — **hat immer Vorrang** |

Das Profil `wohnungsbau_mfh_neubau`:

| Schlüssel | Wert | üblicher Bereich |
|---|---|---|
| `kf_anteil_an_gf` | 0.15 | 0.12 – 0.18 |
| `vf_ff_anteil_an_ngf` | 0.14 | 0.10 – 0.20 |
| `hnf_anteil_an_nf` | 0.90 | 0.85 – 0.93 |
| `nwf_anteil_an_hnf` | 1.00 | 0.70 – 1.00 |
| `geschosshoehe_m` | 3.00 | 2.80 – 3.20 |
| `lichte_raumhoehe_m` | 2.50 | 2.30 – 2.70 |

Beim Überschreiben bleibt der Systemvorschlag in der Begründung sichtbar
(„Vom Benutzer gesetzt (Systemvorschlag war 0.15)"). Ein unbekannter
Schlüssel ist ein Fehler, keine stille Nichtbeachtung — sonst liefe eine
Eingabe ins Leere und der Benutzer sähe ein Ergebnis ohne seine Änderung.

### Höhen werden auseinandergehalten

`Geschosshöhe` (Rohboden–Rohboden), `lichte Raumhöhe` (Fertigboden bis
Unterkante Decke) und `konstruktive Höhe` (die Differenz). Eine lichte
Raumhöhe ≥ Geschosshöhe wird abgelehnt; eine unrealistisch dünne Decke wird
angemerkt, nicht korrigiert. **Keine davon ist die baurechtliche Gebäude-
oder Gesamthöhe** — das steht als Abgrenzung im Ergebnis.

### Geschosse: nicht jede Fläche zählt

Untergeschoss, Keller, Erdgeschoss, Vollgeschoss, Attika, Dachgeschoss,
Technik und Tiefgarage werden unterschieden, je mit `zaehlt_als_vollgeschoss`,
`zaehlt_zur_geschossflaeche` und `wohnnutzung_moeglich`. Untergeschoss,
Keller, Tiefgarage und Technik zählen weder zur Geschossfläche noch zur
Wohnfläche.

G1 liefert eine **Zahl** von Vollgeschossen, keine Gliederung. Erdgeschoss und
Obergeschosse werden daraus abgeleitet; Attika, Untergeschoss und Tiefgarage
erscheinen nur, wenn sie ausdrücklich übergeben werden. Dass Modul 2 heute
nicht strukturiert sagt, ob eine Zone ein Attikageschoss zulässt, steht als
**offener Punkt** im Ergebnis, statt durch eine Annahme überdeckt zu werden.

### BMZ ist ein Volumenmass

G1 rechnet einen BMZ-Deckel in eine Geschossfläche um; welches Volumen
dahintersteht, blieb unsichtbar. `volumenbetrachtung()` trennt jetzt:

* **baurechtlich zulässig** = BMZ × anrechenbare Landfläche
* **geometrisch umsetzbar** = Fussabdruck × Geschosse × Geschosshöhe

und nennt, welches der beiden bindet.

### Wohnungen: grösster Rest auf der Anzahl

Das frühere Verfahren teilte die Fläche je Typ zu und rundete ab. Dabei
verliert jeder Typ bis zu eine fast vollständige Wohnung — bei einem kleinen
Gebäude kommt überall 0 heraus, während die gesamte Fläche als „Rest"
erscheint. Rechnerisch nicht falsch, als Aussage unbrauchbar.

Jetzt: Gesamtzahl aus der mittleren Wohnungsgrösse des Mixes, dann Verteilung
nach **grösstem Rest** (Hare-Niemeyer). Übersteigt die belegte Fläche die
vorhandene, wird die grösste Wohnung **durch eine kleinere ersetzt**, nicht
ersatzlos gestrichen.

> Realfall Buchs AG: 197 m² Wohnfläche, Mix 20/50/30 (62/88/112 m²).
> Blosses Streichen ergab **1 Wohnung mit 109 m² Rest**, obwohl zwei
> hineinpassen. Jetzt: **2 Wohnungen (1× 2.5 Zi, 1× 3.5 Zi), 47 m² Rest.**

Der Mix akzeptiert **Anteile oder Stückzahlen** — nicht beides gemischt, das
ergäbe zwei verschiedene Gesamtflächen. Bei Stückzahlen wird gemeldet, ob es
passt, und der Fehlbetrag beziffert, statt zurechtgerechnet.

### Plausibilitätsprüfung der Nutzungsziffern

Live beobachtet: `AZ = 20.0` in einer Wohnzone W1 (Russikon ZH) — das wäre die
zwanzigfache Grundstücksfläche als Geschossfläche und ist offensichtlich eine
Prozentangabe, die als absolute Zahl gelesen wurde. Der Wert wird **nicht
korrigiert** (ob 20.0 als 0.20 gemeint war, entscheidet das Reglement), aber
als `manuelle_pruefung_erforderlich` gemeldet, mit Hinweis auf die
naheliegende Lesart.

### Bandbreite statt Verweigerung

Ist die Kantenzuordnung unvollständig, liefert G1 zwei Ränder. Einen davon
auszuwählen wäre Willkür; gar nicht zu rechnen wäre unnötig. Die Kaskade
läuft deshalb für **beide** Ränder, und das Ergebnis wird als Bandbreite
ausgewiesen — mit voller Herleitung je Rand.

## Realtests

15 gespeicherte Analysen, ohne erneute Geo- oder Gemini-Abfrage gerechnet:

| Regelungssystem | Fall | Befund |
|---|---|---|
| **AZ** | Säriswilstrasse 65, Uettligen (AZ 0.5) | GF limitiert durch `ausnuetzung_az` |
| **AZ, unplausibel** | Plattenstrasse 4, Russikon (AZ 20.0) | gemeldet; die Geometrie bindet ohnehin |
| **aBGF** | Wilen 18a (0.8), Frauenfelderstrasse 47A (0.75), Kelliweg 7 (0.45) | GF limitiert durch `ausnuetzung_agfz` |
| **BMZ** | Birmensdorf G3/6 (BMZ 6, Art. 21) | Volumen: zulässig 5'281.6 m³, geometrisch 4'478.7 m³ → **Geometrie bindet** |
| **BMZ** | Birmensdorf I5/7 (BMZ 7, Art. 21) | zulässig 6'161.9 m³, geometrisch 7'464.5 m³ → **Baurecht bindet**, GF limitiert durch `baumasse` |
| **BMZ** | Russikon Gewerbezone G (BMZ 4.5, Art. 43) | GF limitiert durch `baumasse` |
| **mehrere Höhenregeln** | Hauptstrasse 4 Graltshausen (2 VG, GH 8.5, GesH 13.0) | Geschosszahl aus dem strikteren Kandidaten |
| **nur Geometrie** | Madiswil (2 VG, GH 6, keine Ziffer) | GF limitiert durch `fussabdruck_x_geschosse` |
| **UG / Attika** | Buchs AG 1145 | Attika zählt zur GF, UG nicht — 421.3 m² statt 538.4 m² |
| **unklare Daten** | 8 Fälle | je mit benannter Ursache, keine Zahl |

**Zur BMZ:** unter den 15 Grundstücken liegt **keines** in einer Zone mit
Baumassenziffer. In den ausgewerteten Reglementen derselben Gemeinden steht
sie aber, mit Artikel und Confidence `hoch`. Die Tests kombinieren deshalb die
echte Parzellengeometrie mit einer echten, aus demselben Reglement
extrahierten Zone. Das ist **keine** Aussage darüber, was auf diesen Parzellen
zulässig wäre — die tatsächliche Zone ist eine andere. Es ist ein Test der
Rechenlogik an realen Werten statt an erfundenen.

**Zur ÜZ:** in keiner der ausgewerteten Reglemente wurde eine
Überbauungsziffer extrahiert (0 Treffer über alle 15 Analysen). Dieser Pfad
ist deshalb nur synthetisch geprüft (`test_flaechenmodell`,
`test_mehrere_regeln_gleichzeitig`) und steht für eine Verifikation an echten
Daten aus, sobald eine Gemeinde mit ÜZ analysiert wurde.

### Vollständige Kette an einem Fall

Buchs AG 1145 ist nach Stufe 2 der einzige Fall mit vollständiger
Kantenzuordnung und damit einem Einzelergebnis statt einer Bandbreite:

```
Grundstücksfläche                                          598.9 m2
anrechenbare Grundstücksfläche  keine Restriktionen        598.9 m2
Fussabdruck                     limitiert durch Geometrie  117.1 m2
Geschossfläche GF               limitiert durch AZ 0.5     299.4 m2   (Geometrie hätte 351.3 zugelassen)
Konstruktionsfläche KF          × 15 %                      44.9 m2
Nettogeschossfläche NGF         GF − KF                    254.5 m2
Verkehrs-/Funktionsfläche       × 14 %                      35.6 m2
Nutzfläche NF                   NGF − (VF+FF)              218.9 m2
Hauptnutzfläche HNF             × 90 %                     197.0 m2
Wohnfläche NWF                  × 100 %                    197.0 m2
Wohnungen                       Mix 20/50/30          2 (1× 2.5 Zi, 1× 3.5 Zi), 47.0 m2 Rest
```

Änderung von `kf_anteil_an_gf` auf 0.12 und `nwf_anteil_an_hnf` auf 0.85
schlägt sofort durch (KF 44.9 → 35.9 m², NWF 197.0 → 173.3 m²), ohne dass eine
einzige Abfrage wiederholt wird.

## Schnittstelle

```python
from potenzial_engine import analysiere_grundstueck, berechne_flaechen, WohnungstypVorgabe

analyse = analysiere_grundstueck("Rosenweg 4, 5033 Buchs AG")   # 1-3 Minuten
analyse.ergebnis["flaechen_und_wohnungen"]                      # Kaskade ohne Mix

# Millisekunden, keine erneute Geo-/Gemini-Abfrage:
berechne_flaechen(
    analyse,
    benutzerwerte={"kf_anteil_an_gf": 0.12},
    wohnungsmix=[WohnungstypVorgabe("3.5 Zi", 88.0, anteil=1.0)],
)
```

Das ist die Voraussetzung für Abschnitt 29/30 der Produktspezifikation:
teure Analysen einmal rechnen, Annahmen beliebig oft ändern.

## Was bewusst nicht gebaut wurde

Wirtschaftlichkeitsrechnung, BKP, Rendite, Gewinn, Residualwert und die
Markt-Datenpipeline. Das Datenmodell trägt sie: die Herkunftsebenen
(`referenz` / `systemannahme` / `benutzerannahme`) stehen bereits, die
Wohnungsstruktur liefert Anzahl, Fläche je Typ und Gesamtfläche je Typ —
genau die Grössen, an denen Verkaufspreise und Mieten später ansetzen,
wahlweise je m² oder je Wohnung.

## Offene Punkte

* **Überbauungsziffer** an echten Daten unverifiziert (siehe oben).
* **Attika/Untergeschoss-Zulässigkeit** liefert Modul 2 nicht strukturiert;
  solche Geschosse müssen heute übergeben werden.
* **Die Profilwerte sind Erfahrungswerte**, keine Referenzprojektdaten.
  `referenzprojekte.py` ist weiterhin leer — sobald dort echte Projekte
  liegen, treten sie als Herkunft `referenz` an die Stelle der
  Systemannahmen, ohne dass sich die Struktur ändert.

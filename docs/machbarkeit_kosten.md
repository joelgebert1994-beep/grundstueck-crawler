# K — Machbarkeit, Kosten, Wirtschaftlichkeit an der 3D-Projektstudie

> **Die Produktfrage.** *„Wenn ich dieses Grundstück so entwickle — welche
> Grössenordnung an Kosten, Ertrag und Wirtschaftlichkeit könnte daraus
> entstehen?"* Eine frühe Machbarkeitsanalyse, keine GU-Offerte.

Konzept, keine Implementierung. Stand 24.09.2026, Code bei `a015756` /
Kern `8023d4a` / Betrieb `d45be8b`.

---

## A — Bestandsaufnahme: was schon rechnet

Der wichtigste Befund, und er dreht die Planung um: **ein vollständiges
BKP-Kostenmodell ist gebaut.** `wirtschaftlichkeit.py` (1198 Zeilen) hat
nicht nur Erlös und Ergebnis, sondern Kostenpositionen mit Herkunft,
Rechenweg und Bezugsgrösse.

### Was da ist

| Baustein | Wo | Was es kann |
|---|---|---|
| `Kostenposition` | `wirtschaftlichkeit.py:432` | Drei Arten: `chf_pro_m2` (mit Flächenbasis), `absolut`, `prozent` (einer anderen Position oder Zwischensumme). Trägt `herkunft`, `begruendung`, und liefert je Position `rechnung` als lesbaren Satz. |
| `standard_kostenmodell()` | `:506` | **BKP 1 Aushub · 2 Gebäude · 3 Betriebseinrichtungen · 4 Umgebung · 5 Baunebenkosten/Honorare · 6 Reserve · Finanzierung · Vermarktung** — fertig verdrahtet, jede Position überschreibbar. |
| `abbruchposition()` | `:587` | Rückbau über m³ Bestandsvolumen. Fehlt `gvol` aus dem GWR: **kein geschätzter Betrag**, sondern `nicht_bestimmbar`. |
| `berechne_kosten()` | `:609` | Zwischensummen `subtotal_bkp1_4`, `..._1_5`, `..._1_6` — Prozentpositionen können sich nur auf bereits Bekanntes stützen. |
| `Verkaufsannahme` / `Mietannahme` | `:257` / `:341` | Erlös bzw. Jahresertrag, jeweils auf einer **benannten** Flächenbasis. |
| `_verkaufsflaeche()` | `:216` | Fläche, die **keiner Wohnung zugeordnet** ist, fliesst nicht in den Erlös. Live beobachtet: 72 von 197 m² wurden früher stillschweigend mitverkauft. |
| `_residualwert()` | `:840` | Max. Landwert = Erlös − Baukosten − Zielgewinn. Negativ wird als Befund gemeldet, nicht versteckt. |
| `_stellschraube()` / `_rueckwaertsrechnung()` | `:877` / `:918` | Sensitivität: welcher Wert müsste sich wie ändern, damit die Zielmarge aufgeht. |
| `FLAECHENBASIS` | `:71` | `nwf · belegt · hnf · nf · ngf · gf` — sechs benannte Bezugsflächen. |
| `Marktannahmen` | `:693` | Verkauf, Miete, Bodenpreis, Zielmarge, `land_ansatz` (Kauf / im Besitz). |

### Der Anschlusspunkt — und er ist überraschend klein

`berechne_fuer_szenario(szenario, …)` liest aus dem Szenario **genau fünf
Felder**:

```python
szenario["flaechen"]["flaechen"]   # die Flächenkaskade
szenario["wohnungen"]
szenario["id"]                     # nur für den Abbruch beim Ersatzneubau
szenario["bezeichnung"], szenario["machbarkeit"]   # nur zur Beschriftung
```

Und `szenario["flaechen"]` ist **exakt die Rückgabe von
`berechne_flaechen_und_wohnungen()`** — also genau das, was der
I-Endpunkt `/projektstudie/flaechen` seit dieser Woche für den
gezeichneten Körper liefert.

> **K ist deshalb keine neue Wirtschaftlichkeitslogik, sondern eine
> Verdrahtung.** Aus dem I-Ergebnis wird ein Szenario-Objekt gebaut und an
> die vorhandene Funktion gegeben. Kein zweiter Rechenweg, keine zweite
> Wahrheit.

### Was fehlt — und es ist nicht die Rechnung

1. **Die Kennwerte sind undatiert und unbelegt.** In
   `modul3_financial.py:61`:
   ```python
   AUSBAUSTANDARD_CHF_PRO_M2_BGF = {"rendite": 2400, "gehoben": 3100, "luxus": 4200}
   BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT = 50    # "Richtwert Mitte 40-60"
   BKP1_AUSHUB_CHF_PRO_M3_DEFAULT  = 30    # "grober Richtwert"
   BKP4_PROZENT_VON_BKP2_DEFAULT   = 0.05  # "Mitte 4-6 %"
   BKP5_PROZENT_DEFAULT            = 0.11  # "Mitte 10-12 %, nach SIA 102/103"
   ```
   Keine Quelle, kein Preisstand, keine Region, kein Gebäudetyp. Das ist
   die eigentliche Lücke von K — und genau das, was die Recherche in C
   schliesst.
2. **Keine Bandbreite.** Jede Position ist eine Zahl. Bei einer
   Vorstudie ist das Scheingenauigkeit (siehe H).
3. **Keine Teuerungsindexierung.** Ein Kennwert altert still.
4. **Der Name trägt den alten Begriff.** `..._CHF_PRO_M2_BGF` wird auf
   `gf` angewendet. BGF und GF meinen dasselbe (SIA 416 nennt es GF), es
   ist kein Rechenfehler — aber der Name gehört nachgezogen, sonst liest
   sich der Code, als vermische er zwei Grössen.
5. **Kein Bezug zur Variante.** Die Wirtschaftlichkeit hängt heute am
   Engine-Szenario, nicht am gezeichneten Körper der aktiven Variante.

---

## B — Die BKP-Beispiele, strukturell gelesen

Auf Struktur geprüft, nicht auf Inhalt. Keine Namen, Adressen, Parzellen
oder projektspezifischen Werte werden übernommen.

Vier übertragbare Prinzipien:

1. **Der Kostentreiber ist das Volumen, nicht die Fläche.** BKP 2 wird
   über m³ gerechnet, getrennt nach ober-/unterirdisch und „kalt".
2. **Nachgelagerte Gruppen sind Prozentsätze**, keine eigenen
   Schätzungen: Anschlussgebühren und Baunebenkosten als % von BKP 2+3,
   Reserve als % von BKP 2, Bauzinsen als % × Bauzeit × ½.
3. **Zwei Spalten nebeneinander** = zwei Varianten im selben Blatt.
4. **Im Kopf steht die Genauigkeit** (±25 %), und je Zeile steht, ob es
   eine Annahme ist.

Die Architektenstudie daneben zeigt die Kette, die unsere 3D-Studie
erzeugen soll: *Kubatur → Verkaufsflächen → Ausnützungsziffer*, endend
mit „zulässig x, tatsächlich y, übernutzt um z m²".

**Wo ich abweiche, und warum.** Unser bestehendes Modell rechnet BKP 2
auf **m² GF**, nicht auf m³. Für eine frühe Machbarkeit ist das die
robustere Basis: die 3D-Studie erzeugt Fussabdruck und Geschosse direkt,
das Volumen dagegen hinge zusätzlich an der Geschosshöhe und an der
Frage, was zum Volumen zählt. Die m³-Kennwerte bleiben trotzdem
verwendbar — als **Plausibilisierung** (siehe G), nicht als zweite
Rechnung. Punkt 3 des Auftrags erlaubt ausdrücklich die bessere Struktur.

---

## C — Schweizer Kennwerte: Recherche

### Was gilt

**SIA 416 ist die Bezugsnorm**, SIA 116 seit 2003 ausser Kraft. Die ETH
führt als Bezugsgrössen ausdrücklich GF (m²), GV (m³) und **BUF
(Umgebungsfläche, m²)** nach SIA 416. Unser Flächenmodell liegt damit
richtig; ältere m³-Kennwerte aus der SIA-116-Zeit dürfen nicht ungeprüft
mit unseren SIA-416-Volumen gemischt werden.

**CRB** liefert die Struktur (BKP, eBKP-H, Objektartenkatalog) und mit
`werk-material.online` die methodisch beste Kennwertsammlung. Sie hängt
an einer NPK-Lizenz — **kostenpflichtig, nicht beschafft.**

### Verwendbare Quellen

| Quelle | Art | Preisstand | Region | Stärke / Schwäche |
|---|---|---|---|---|
| **Wüest Partner für Lignum/BAFU, „Holzbaukennzahlen für Investoren — Wohnbauten" (2025)** | Studie, frei | **indexiert per 04.2023** | CH, nach Grossregion indexiert | **Beste freie Quelle.** 17 Holz- + Referenz-Massivbauten, **Quantile statt Mittelwerte**, Methodik offengelegt, inkl. MwSt, Tiefgarage getrennt ausgewiesen. Schwäche: MFH ab 15 Wohnungen, kein EFH. |
| **BFS Schweizerischer Baupreisindex** | amtlich, frei | halbjährlich April/Oktober | 7 Grossregionen, nach Bauwerksart | Der **Teuerungsschlüssel**. Liefert keine absoluten Kosten. |
| **ETH Zürich, Bauprozess: Kostenplanung** | Lehrmaterial, frei | laufend | CH | BKP-Anteile, Bezugsgrössen nach SIA 416, Kostengenauigkeit nach SIA 102. |
| **SIA 102 / 103** | Norm | laufend | CH | Honorare und **Kostengenauigkeit je Projektphase**. |
| aktiva.swiss Benchmarks | Zusammenstellung, frei | **kein Preisstand angegeben** | CH gesamt | Deckt EFH, MFH Miete/STWE, Büro, Tiefgarage, Rückbau, Sanierung. Nur zur Plausibilisierung — undatiert. |
| CRB `werk-material.online` | Fachstelle | laufend | CH | Methodisch führend, **kostenpflichtig** |

### Kennwerte, belastbar dokumentiert

**Wohnbauten Neubau, Massivbau, Preisstand April 2023, inkl. MwSt, exkl.
Tiefgarage.** Wüest Partner für Lignum/BAFU, 2025.

| Bezug | 10 % | 30 % | **Median** | 70 % | 90 % |
|---|---|---|---|---|---|
| BKP 1–5 / m³ GV | 701 | 846 | **974** | 1'137 | 1'548 |
| **BKP 1–5 / m² GF** | 1'994 | 2'666 | **3'043** | 3'354 | 4'413 |
| BKP 1–5 / m² HNF | 3'100 | 3'894 | **4'492** | 5'002 | 6'900 |
| BKP 2 / m³ GV | 640 | 808 | **898** | 1'047 | 1'474 |
| **BKP 2 / m² GF** | 1'834 | 2'390 | **2'801** | 3'188 | 4'215 |
| BKP 2 / m² HNF | 2'848 | 3'649 | **4'023** | 4'811 | 6'355 |

*Enthalten:* BKP 1–5 bzw. 2, inkl. MwSt. *Nicht enthalten:* Land, BKP 6–9,
Finanzierung, Vermarktung, Tiefgarage.

**BKP-Anteile.** Die ETH nennt für ein Schweizer MFH-Projekt BKP 2 ≈
**65–85 % der Erstellungskosten** — das ist die belastbare Angabe. Für
BKP 4 (≈ 5–10 %) und BKP 5 (≈ 10–15 %) fand ich nur Bauratgeberseiten
ohne Methodik; sie stehen hier als grobe Einordnung, nicht als Quelle.
Die heute eingebauten Werte (BKP 4 = 5 %, BKP 5 = 11 %) liegen in diesen
Spannen.

**Umrechnungs- und Hilfsgrössen** aus derselben Studie — für uns
wichtiger als die Absolutwerte, weil die 3D-Studie GF erzeugt und
manche Kennwerte HNF verlangen:

- Flächeneffizienz MFH: **HNF / GF oberirdisch ≈ 0.75**, Spanne
  0.70–0.80; über 0.79 nur mit grossem Planungsaufwand.
- `GV := GV_oi + GV_ui − GV_Tiefgarage`, `GF := GF_oi + GF_ui − GF_Tiefgarage`.
- Tiefgarage, wenn nicht separat: **BKP 2 ≈ 35'000, BKP 1–5 ≈ 42'000 je
  Einstellplatz**; Volumen ≈ GF × 2.70 m.
- Stellplatzbedarf ≈ **1 Platz je 100 m² GF oberirdisch**, **30 m² GF je
  Platz** (angelehnt an VSS-Parkierungsnorm 2022).
- **Bruttoanfangsrendite** Wohnliegenschaften, Transaktionen 2022–2023:
  10 % 2.58 · 30 % 3.25 · **Median 3.71** · 70 % 4.21 · 90 % 5.01 %.
- **Landanteil** an den Erstellungskosten BKP 1–9: bei den Fallbeispielen
  **10–90 %**. Diese Spannweite ist selbst das Ergebnis — ein fester
  Landanteil wäre eine Erfindung.

### Noch nicht belastbar beschafft

EFH aus einer **datierten** Quelle · Sanierung/Umbau · Rückbau ·
Umgebung BKP 4 als eigener Kennwert · Honorarsätze nach SIA 102/103.
Bis dahin bleiben die vorhandenen Richtwerte in Kraft — aber ab K mit
dem Vermerk „ohne belegte Quelle", statt wie eine Benchmark auszusehen.

---

## D — Vorgeschlagene Kostenstruktur

**Die vorhandene Struktur bleibt.** Sie ist bereits BKP-gegliedert,
prozentkettenfähig und herkunftsbewusst. Vier Ergänzungen:

### D1 Jede Position bekommt eine Quelle

`Kostenposition` erhält ein Feld `quelle`:

```python
quelle = {
    "name": "Wüest Partner / Lignum / BAFU 2025",
    "preisstand": "2023-04",
    "region": "CH, nach Grossregion indexiert",
    "typ": "MFH Neubau Massivbau",
    "bezug": "m2 GF",
    "enthalten": "BKP 2, inkl. MwSt",
    "nicht_enthalten": "Land, BKP 6-9, Finanzierung, Tiefgarage",
}
```

Fehlt sie, steht in der Oberfläche **„ohne belegte Quelle"** — nicht
nichts.

### D2 Jede Position bekommt eine Bandbreite

Statt `wert: 2400` ein Tripel aus den Quantilen:

```python
wert = 2801           # Median, gerechnet wird damit
band = (2390, 3188)   # 30 % / 70 % aus derselben Quelle
```

Die Rechnung läuft auf dem Median; das Band läuft **mit** und ergibt am
Ende eine Ergebnisspanne (siehe H).

### D3 Bezugsgrösse je Position, nicht pauschal

Punkt 7 des Auftrags. Vorschlag:

| Position | Bezug | Warum genau diese |
|---|---|---|
| BKP 1 Aushub | **m² Fussabdruck × Tiefe → m³** | Die Baugrube folgt dem Fussabdruck, nicht der Geschossfläche. Heute fälschlich GF × 3.5 m — bei vier Geschossen ist die Grube damit viermal zu gross. **Befund, siehe unten.** |
| BKP 1 Rückbau | **m³ GV Bestand** | Abbruch ist Volumenarbeit. Ohne `gvol` aus dem GWR: nicht bestimmbar. |
| BKP 2 Gebäude | **m² GF** (Alternative m³ GV) | Die 3D-Studie erzeugt GF direkt; GV hinge zusätzlich an der Geschosshöhe. |
| BKP 3 Betriebseinrichtungen | absolut | Im Wohnungsbau meist 0. |
| BKP 4 Umgebung | **m² BUF = Parzelle − Fussabdruck** | Sachlich richtiger als % von BKP 2: die Umgebung wächst mit der *unbebauten* Fläche, nicht mit dem Gebäude. Prozent bleibt als Rückfallebene. |
| BKP 5 Baunebenkosten/Honorare | **% von BKP 1–4** | So rechnet SIA 102/103 und so rechnet das Referenzblatt. |
| BKP 6–9 Reserve | **% von BKP 1–5**, phasenabhängig | Vorstudie 15 %. |
| Tiefgarage | **CHF je Einstellplatz** | Die einzige Grösse, für die es einen belegten Stückwert gibt. |
| Finanzierung | **% × Bauzeit × ½** | Über die Bauzeit im Mittel die halbe Summe gebunden — die Konvention aus dem Referenzblatt. |
| Vermarktung | **% vom Erlös** | Maklerhonorar ist erlösabhängig. |
| Land | **CHF/m² Parzelle** oder Residualwert | Beides vorhanden. |

> **Befund aus der Prüfung — gemessen, nicht vermutet.**
> `standard_kostenmodell()` setzt BKP 1 Aushub als `KOSTEN_PRO_M2` auf die
> **Geschossfläche**: `3.5 m × 30 CHF/m³ = 105 CHF/m²` × GF. Dieselbe
> Ableitung steht in `modul3_financial.py`
> (`aushub_volumen_m3 = neue_bgf_m2 × aushub_tiefe_m`).
>
> Nachgerechnet für 275 m² Fussabdruck und 4 Geschosse (GF 1'100 m²):
>
> ```
> gerechnet:            115'500 CHF   (105 CHF/m² × 1'100 m² GF)
> auf dem Fussabdruck:   28'875 CHF   (275 m² × 3.5 m × 30 CHF/m³)
> Faktor:                     4.0
> ```
>
> Die Baugrube hängt am Fussabdruck, nicht an der Geschossfläche — der
> Fehler wächst genau mit der Geschosszahl. Bei eingeschossiger Bauweise
> fällt er nicht auf, weil GF = Fussabdruck.
>
> Das ist ein echter Fehler im bestehenden Modell, unabhängig von K. Ich
> habe ihn **nicht angefasst**; er gehört in einen eigenen Auftrag — und
> zwar vor K, weil K ihn erst richtig sichtbar macht: wer die Geschosse
> von 3 auf 4 ändert, sieht die Baugrube mitwachsen.

### D4 Preisstand (Punkt 6)

Keine hart eingetragene 2026-Zahl. Der Weg:

```
Kennwert (Preisstand P, Grossregion R)
  × BaupreisindexHochbau[Wohnbau, R, heute] / BaupreisindexHochbau[Wohnbau, R, P]
  = Kennwert auf heutigem Preisstand
```

Quelle: **BFS Schweizerischer Baupreisindex**, Basis Oktober 2020 = 100,
halbjährlich (April/Oktober), publiziert Juni/Dezember, nach
Bauwerksart und Grossregion.

Beobachtete Werte Hochbau/Wohnbau: 10.2023 **114.5** · 04.2024 **115.2**
· 10.2024 **115.3** · 04.2025 **114.9**. Die Teuerung ist seit 2023 also
praktisch **flach** — der Faktor liegt nahe 1.0. Das entbindet nicht von
der Mechanik: der Indexstand gehört zur Laufzeit geholt und mit Datum
angezeigt, nicht eingebaut.

---

## E — Benutzerführung: zwei Stufen

### Stufe 1 — Schnelle Machbarkeit (1–2 Minuten)

Ein Block unter der Projektstudie im 3D-Reiter. **Fünf Eingaben, mehr
nicht:**

```
PROJEKTART      ( ) Mietwohnungen   (•) Stockwerkeigentum   ( ) EFH
AUSBAUSTANDARD  ( ) einfach  (•) mittel  ( ) gehoben
LAND            (•) Kauf, CHF [____]/m²   ( ) bereits im Besitz
VERKAUF         CHF [____] /m² — Vorschlag aus dem Marktreiter
ZIELMARGE       [15] %
─────────────────────────────────────────────────────────────
Anlagekosten     4.7 – 6.4 Mio CHF        ← Bandbreite, nicht eine Zahl
Erlös            6.2 – 7.1 Mio CHF
Ergebnis         −0.2 – +2.4 Mio CHF
Max. Landwert    1'180 – 2'050 CHF/m²
                 ±25 % (Vorstudie, SIA 102) · Preisstand 04.2025
```

Alles andere kommt aus dem Entwurf und den vorhandenen Modellen.

### Stufe 2 — Aufklappbar: die Herleitung

Dieselbe Rechnung, jede Zeile sichtbar — und das ist bereits das Format,
das `berechne_kosten()` heute schon liefert:

```
BKP 1  Aushub           28'875   275 m² Fussabdruck × 3.5 m × 30 CHF/m³   [Annahme]
BKP 2  Gebäude       3'081'100   2'801 CHF/m² × 1'100 m² GF               [Benchmark ①]
BKP 4  Umgebung        154'000   ...                                      [Annahme]
BKP 5  Baunebenkosten  358'000   11 % von BKP 1–4                         [SIA 102/103]
BKP 6  Reserve         543'000   15 % von BKP 1–5  (Vorstudie)            [SIA 102]
─────────────────────────────────────────────────────────────────────────
① Wüest Partner/Lignum/BAFU 2025 · Preisstand 04.2023, indexiert auf 04.2025
  · MFH Neubau Massivbau · inkl. MwSt · ohne Land, BKP 6–9, Tiefgarage
  · Median; Band 30–70 % = 2'390–3'188 CHF/m²
```

**Keine BKP-Untergruppen.** Untergruppen zu führen hiesse, eine
Detailtiefe vorzutäuschen, die eine Vorstudie nicht hat. Wer sie braucht,
braucht eine Kostenschätzung, kein Machbarkeitswerkzeug.

---

## F — Datenfluss

```
3D-Projektkörper der aktiven Variante        (entwurf_json, Block J)
  Fussabdruck · Geschosse · Geschosshöhe · Anordnung
        │
        ▼  /projektstudie/flaechen  (Block I, steht)
Flächenmodell (Engine)
  GF · KF · NGF · VF/FF · NF · HNF · NWF · Geschossaufbau
        │
        ▼  NEU in K: Szenario-Objekt bauen
{ id, bezeichnung: "Projektstudie", machbarkeit: "projektstudie",
  flaechen: <I-Ergebnis>, wohnungen: <I-Ergebnis.wohnungen> }
        │
        ▼  berechne_fuer_szenario()  ← VORHANDEN, unverändert
Kosten (BKP 1–6, Finanzierung, Vermarktung)
Erlös / Mietertrag
Anlagekosten · Ergebnis · Marge · Residualer Landwert · Stellschrauben
        │
        ▼
Anzeige mit Herkunft, Quelle, Preisstand und Bandbreite
```

Zwei Mengen kommen aus dem Entwurf und **nicht** aus dem Flächenmodell,
weil das Flächenmodell sie nicht führt:

- **Fussabdruck** für BKP 1 (Aushub) — aus Breite × Tiefe.
- **Umgebungsfläche BUF** für BKP 4 — Parzelle − Fussabdruck.

Beide sind reine Geometrie der Studie und werden als solche
gekennzeichnet.

---

## G — Was automatisch kommt, was eingegeben wird

| Wert | Herkunft | Eingabe nötig? |
|---|---|---|
| Fussabdruck, Geschosse, Höhe, GF (geometrisch) | **Projektion** aus dem Entwurf | nein |
| aGF, NGF, HNF, NWF, Geschossaufbau | **Engine** (SIA 416) | nein |
| Parzellenfläche, anrechenbare Landfläche, Ausnützung | **Engine** (G1) | nein |
| Bestandsvolumen für Rückbau | **Engine** (GWR `gvol`) — oft nicht bestimmbar | nur wenn fehlend |
| BKP 2 Kennwert | **Benchmark** (Wüest Partner, Median + Band) | nein, überschreibbar |
| BKP 1/4/5/6, Finanzierung, Vermarktung | **Annahme** bzw. Norm (SIA 102/103) | nein, überschreibbar |
| Baupreisindex | **Engine/extern** (BFS) | nein |
| Verkaufspreis / Mietzins | **Marktreiter** — Systemvorschlag aus Vergleichsobjekten | ja, wenn kein Vorschlag |
| Projektart, Ausbaustandard, Zielmarge, Landansatz | **Benutzereingabe** | ja, fünf Felder |
| Wohnungsmix | **Benutzerannahme**, sonst Wohnungszahl „nicht bestimmbar" | optional |

### Markt (Punkt 13)

Die sechs Segmente bleiben, wie sie sind. Die Zuordnung ist eine
**Vorauswahl mit Begründung**, keine automatische Übernahme:

| Projektart der Studie | Segment | Bedingung |
|---|---|---|
| Stockwerkeigentum, Neubau | **Wohnung Neubau** (CHF/m²) | nur dieses. Bestandswohnungen sind kein Neubaupreis. |
| Mietwohnungen | **Mietzins** (CHF/m²/Jahr) + Cap Rate | Mietzins ≠ Verkaufspreis. |
| EFH | **Einfamilienhaus** | nicht aus MFH-Preisen ableiten. |
| Renditeobjekt als Ganzes | **Renditeliegenschaft** | |
| Landwert als Gegenprobe | **Bauland** | Bauland ≠ fertiges Projekt — nur als Plausibilisierung des Residualwerts. |

Reicht das Segment nicht (unter `MIN_REFERENZEN_FUER_VORSCHLAG`), gibt es
**keinen Systemvorschlag** und die Machbarkeit bleibt in diesem Teil
offen. Die bestehende Regel — Systemvorschlag → verwendet, solange keine
eigene Annahme da ist; eigene Annahme hat Vorrang — bleibt unverändert.

---

## H — Unsicherheit

**Die fachlich richtige Antwort steht in SIA 102**, und sie deckt sich
mit dem Kopf des Referenzblatts:

| Phase | Kosteninformation | Genauigkeit |
|---|---|---|
| **Vorstudie** | **Grobkostenschätzung** | **± 25 %** |
| Vorprojekt | Kostenschätzung | ± 15 % |
| Bauprojekt | Kostenvoranschlag | ± 10 % |

Unser Werkzeug arbeitet in der **Vorstudie**. Also ±25 %, und das gehört
sichtbar in den Kopf — nicht kleingedruckt.

**Zwei Bänder, nicht eines.** Sie entstehen verschieden und dürfen nicht
vermischt werden:

1. **Das Quantilsband der Kennwerte** (30 %/70 % aus der Quelle). Es
   sagt: *so streuen reale Projekte.*
2. **Die Phasengenauigkeit ±25 %.** Sie sagt: *so ungenau ist eine
   Vorstudie unabhängig von der Streuung.*

Vorschlag: gerechnet wird mit dem Median, angezeigt wird das
**Quantilsband** als Spanne der Anlagekosten, und darunter steht die
Phasengenauigkeit als Satz. Ein prozentualer Korridor **statt** der
Quantile wäre schlechter — er würde die tatsächlich gemessene Streuung
durch eine pauschale ersetzen.

**Wo ein Kennwert nur breit oder nur projektbezogen vorliegt** (Aushub,
Umgebung, Rückbau), steht das an der Position: „grober Richtwert,
projektspezifisch stark abweichend" — so wie es heute schon in den
`begruendung`-Texten steht, nur sichtbar.

### Und was nicht passiert

- Kein Ergebnis auf den Franken genau. Anlagekosten auf 0.1 Mio gerundet.
- Keine Marge mit zwei Nachkommastellen aus einer ±25-%-Rechnung.
- Keine Kennzahl, die eine Quelle vortäuscht, die es nicht gibt.

---

## I — Erster K-Prototyp

Der kleinste Schritt, der die Kette beweist:

> 3D-Entwurf öffnen → Körper steht → Block „Machbarkeit" darunter →
> Projektart und Ausbaustandard wählen → **Anlagekosten, Erlös, Ergebnis
> und max. Landwert als Bandbreite** → Geschosse von 3 auf 4 ändern →
> alle vier Zahlen ändern sich nachvollziehbar → aufklappen zeigt BKP 1–6
> mit Rechenweg, Quelle und Preisstand.

**Umfang:**

1. Server: aus dem I-Ergebnis ein Szenario-Objekt bauen und
   `berechne_fuer_szenario()` aufrufen. Ein Endpunkt, keine neue Rechnung.
2. `Kostenposition` um `quelle` und `band` erweitern — additiv, die
   bestehenden Aufrufe bleiben gültig.
3. Die BKP-2-Kennwerte durch die belegten Quantile ersetzen, mit Quelle
   und Preisstand.
4. Frontend: der Machbarkeitsblock, fünf Eingaben, Bandbreite,
   aufklappbare Herleitung — angehängt an dieselbe Entprellung wie I.
5. Die Rechnung hängt an der **aktiven Variante** (Punkt 11): andere
   Variante → anderer Körper → andere Zahlen. Nichts wird gespeichert,
   was gerechnet werden kann (Punkt 12).

**Nicht im Prototyp:** BKP-Untergruppen, Mengengerüst je Bauteil,
Sanierungs- und Umbaukennwerte, Tiefgaragen-Automatik, Cashflow über die
Zeit, Steuern.

### Vorher zu klären

1. **Die BKP-1-Bezugsgrösse** (der Aushub-Befund aus D3). Er verfälscht
   heute jede Rechnung mit mehr als einem Geschoss. Eigener Auftrag,
   vor K.
2. **Ob BKP 4 auf BUF umgestellt wird** oder als Prozentsatz bleibt.
   Fachlich spricht mehr für BUF; es ist aber eine Änderung am
   bestehenden Modell.
3. **Ob wir CRB beschaffen.** Ohne sie bleiben EFH, Sanierung und Rückbau
   bei undatierten Richtwerten. Das ist tragbar, solange es dransteht —
   aber es ist die grösste verbleibende Lücke.

---

## Quellen

- [Wüest Partner für Lignum/BAFU: Holzbaukennzahlen für Investoren — Wohnbauten (2025)](https://timberfinance.ch/wp-content/uploads/2025/07/202504-Abschlussbericht_Holzbaukennzahlen_Wust-Partner.pdf)
- [BFS: Schweizerischer Baupreisindex](https://www.bfs.admin.ch/bfs/de/home/statistiken/preise/baupreise/baupreisindex.html)
- [ETH Zürich, Bauprozess: Kostenplanung](https://map.arch.ethz.ch/artikel/30/kostenplanung)
- [CRB: Baukostenplan BKP](https://www.crb.ch/de/normen-standards/baukostenplane/baukostenplan-bkp)
- [SIA LHO 102 für Architekten](https://staedteverband.ch/cmsfiles/SSV_130219_SIA102_2.pdf)
- [HEV Schweiz: Schweizerischer Baupreisindex](https://www.hev-schweiz.ch/vermieten/statistiken/schweizerischer-baupreisindex)
- [aktiva.swiss: Kosten-Benchmarks Neubaukosten Immobilien Schweiz](https://aktiva.swiss/immobilien-benchmarks/)

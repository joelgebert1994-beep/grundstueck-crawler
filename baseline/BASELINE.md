# Baseline vor dem Paketumbau (Phase 0.2)

**Datum:** 11.09.2026
**Basis-Commit:** `7007c04` — Ist-Zustand, unveraendert gesichert
**Python:** 3.12 · **Abhaengigkeiten:** `requests`, `shapely`

## Wozu diese Baseline dient

Die Phasen 0.3 (Paketierung, 29 flache Importe) und 0.4 (`_run_pipeline()` in den
Engine-Kern heben) veraendern **Struktur, nicht Verhalten**. Diese Baseline ist der
Beweis dafuer — oder deckt auf, wenn doch etwas verrutscht ist.

Nach jedem der beiden Schritte gilt: Testlauf wiederholen, Referenzfaelle neu
rechnen, mit den hier festgehaltenen Werten vergleichen. Abweichung heisst
zurueckrollen, nicht nacharbeiten.

## 1. Testlauf

Vollstaendiges Protokoll: [`testlauf_2026-09-11.txt`](testlauf_2026-09-11.txt)

| Suite | Ergebnis |
|---|---|
| `test_baubereich.py` | bestanden (9/9 synthetische G1-Faelle) |
| `test_sia416_flaechen.py` | bestanden |
| `test_quellen.py` | bestanden |
| `test_entwicklungsszenarien.py` | bestanden |
| `test_referenzprojekte.py` | bestanden |
| `test_klassifikation.py` | bestanden (4 echte Netzwerkfaelle + Parzellenauswahl-Regression) |

**6/6 Suiten, 311 einzelne OK-Zusicherungen, alle Exitcodes 0.**

Zwei Suiten brauchen Netzzugang (`test_klassifikation`, teilweise `test_quellen`);
keine braucht einen `GEMINI_API_KEY`. Wo eine Zonenzuordnung noetig ist, arbeitet
die Testsuite mit einem synthetischen Modul-2-Ergebnis statt eines LLM-Calls.

## 2. Referenzfaelle

Fuenf echte Analysen, alle nach dem Parzellenauswahl-Fix vom 04.09.2026 erzeugt
(`parzellenauswahl == "punkt_in_parzelle"` in allen fuenf). Rohdaten in
[`referenz/`](referenz/).

### Invarianten, die nach dem Umbau identisch sein muessen

| Fall | Parzelle | EGRID | Flaeche | Zonenstatus |
|---|---|---|---|---|
| Buchs AG — Rosenweg 4 | 1145 | `CH975272732334` | 598.9 m² | **gefunden** → Gartenstadtzone (Ga) |
| Rorschach SG — Hauptstrasse 78 | 235 | `CH179877736742` | 514.0 m² | sondernutzungsplan_massgebend |
| Frauenfeld TG — Rathausplatz 1 | 164 | `CH507729918047` | 198.8 m² | sondernutzungsplan_massgebend |
| Baden AG — Gartenstrasse 5 | 5591 | `CH487383957716` | 2333.8 m² | sondernutzungsplan_massgebend |
| Zuerich ZH — Bahnhofstrasse 1 | AA5662 | `CH139977917088` | 513.9 m² | sondernutzungsplan_massgebend |

**Buchs AG ist der einzige Fall, der vollstaendig durchrechnet** — die vier anderen
werden korrekt durch einen Sondernutzungsplan blockiert. Er deckt damit als
einziger den G1- und SIA-416-Pfad ab und ist das schaerfste Pruefkriterium:

```
G1-Modus:  bandbreite_grenzabstand_kante_nicht_differenziert
  alle_kanten_klein:  Baubereich 206.76 m²  Fussabdruck 206.76 m²  GF 299.44 m²
  alle_kanten_gross:  Baubereich  57.23 m²  Fussabdruck  57.23 m²  GF 171.69 m²
SIA 416:   GF bestimmt, NF/HNF/NNF nicht_bestimmbar (keine Referenzprojekte)
Modul 3:   None (kein Verkaufspreis uebergeben)
```

Diese G1-Werte wurden am 04.09. und am 11.09. unabhaengig voneinander auf zwei
Nachkommastellen identisch reproduziert — die Geometriekaskade ist stabil.

### Was sich zwischen Laeufen legitim aendern darf

Die Referenzfaelle rufen **echte** amtliche Dienste und Gemini auf. Deshalb sind
folgende Abweichungen **kein** Fehlschlag:

- `abgerufen_am` in den Quellenobjekten (Tagesdatum)
- Anzahl Rechtsvorschriften und Quellenobjekte, wenn ein Kanton seinen
  OEREB-Auszug aendert (Rorschach lieferte am 03.09. noch 50 Eintraege — allerdings
  zur **falschen** Nachbarparzelle, siehe Parzellenauswahl-Fix)
- Formulierungen und Kennzahl-Abdeckung aus Modul 2 (Gemini ist nicht
  deterministisch; am 04.09. waren es je nach Gemeinde 22–43 belegte Kennzahlen)

**Nicht** aendern duerfen sich: Parzellennummer, EGRID, amtliche Flaeche,
Auswahlmethode, Zonenzuordnungs-Status, G1-Geometriewerte und der
SIA-416-Bestimmtheitsstatus. Das sind die Invarianten der obigen Tabellen.

## 3. Reproduktion

```
# Testlauf
python test_baubereich.py            # analog fuer die uebrigen fuenf Suiten

# Referenzfall neu rechnen (braucht GEMINI_API_KEY in der Umgebung)
python -c "from webapp import _run_pipeline; import json; \
           e,_ = _run_pipeline('Rosenweg 4, 5033 Buchs AG', verkaufspreis=None); \
           print(json.dumps(e['zonen_zuordnung']['zone']['zonenbezeichnung']))"
```

Nach Phase 0.4 aendert sich der zweite Aufruf auf
`from potenzial_engine import analysiere_grundstueck` — das Ergebnis muss
identisch bleiben.

## 4. Bekannte offene Befunde (nicht Teil von Phase 0)

- **Modul 1b waehlt die Basiszone ohne Punkt-in-Polygon-Test.** Bei mehreren
  Grundnutzungen im 8-m-Suchradius wird `grundnutzungen[0]` genommen. In
  Frauenfeld liefert das "Strasse im Baugebiet", weil der Adresspunkt auf ein
  Strassenpolygon faellt. Strukturell derselbe Fehler wie der am 04.09. behobene
  `results[0]`-Parzellenbug. Fix gehoert in Phase 1: diejenige Grundnutzung
  waehlen, die den groessten Flaechenanteil der Parzelle ueberdeckt — die
  Geometrien liegen in beiden Faellen bereits vor.
- **NF/HNF/NNF bleiben `nicht_bestimmbar`**, solange `referenzprojekte.py` leer
  ist. Das ist gewollt, keine Luecke.

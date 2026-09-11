# Stufe 5 — Markt, BKP und Wirtschaftlichkeit

**Stand:** 11.09.2026 · **umgesetzt und an realen Daten verifiziert**
**Voraussetzung:** Stufe 4 abgeschlossen (Commit `1099dae`)

## Die Architekturentscheidung vorweg

`modul3_financial.py` rechnete bereits Residualwerte — aber auf der alten
Grundlage: BGF = AZ × Parzellenfläche (ohne Geometrie), NNF = **81 % der BGF**
als fester Faktor, ein einziges Szenario, keine Trennung von Referenz und
Benutzerannahme. Genau diesen 81-%-Faktor schliesst die Produktspezifikation
in Abschnitt 12 ausdrücklich aus.

Modul 3 ist zudem tief verdrahtet: Pipeline, Webapp, Export und fünf Stellen
in `test_klassifikation`. Ein Umbau in place hätte alles davon gebrochen.

**Entscheidung:** `wirtschaftlichkeit.py` als eigene Schicht auf den Stufen
3/4, die Modul 3s **Flächenherleitung ersetzt**, dessen **Kostenrichtwerte
aber unverändert importiert** — es gibt im Projekt weiterhin genau einen Satz
Richtwerte, nicht zwei. Modul 3 bleibt für die bestehende Schnittstelle
`berechne_wirtschaftlichkeit()` in Betrieb. Beide Module verweisen im
Docstring aufeinander.

## Die drei Herkunftsebenen

| Ebene | Bedeutung |
|---|---|
| `referenz` | Vergleichsobjekte mit Quelle, Datum, Objekt, Wert, Qualität |
| `systemannahme` | daraus abgeleitete Orientierung — **Median** der Referenzen |
| `benutzerannahme` | vom Benutzer gesetzt — **massgebend für die Rechnung** |

Eine Referenz ersetzt nie die Benutzerannahme. Alle drei Ebenen bleiben
gleichzeitig sichtbar:

```
Marktreferenzen  8'700 – 9'300 CHF/m²  (3 Vergleichsobjekte)
   Wüest Partner    2026-06  MFH Nachbarquartier   8'700 CHF/m²  [hoch]
   Wüest Partner    2026-06  Neubau Ortszentrum    9'000 CHF/m²  [hoch]
   Eigene Erhebung  2026-05  Vergleichsobjekt      9'300 CHF/m²  [mittel]
Systemvorschlag  9'000 CHF/m²  (Median)      -> systemannahme
Meine Annahme    9'500 CHF/m²                -> benutzerannahme
Gerechnet wird mit: 9'500 CHF/m²
```

Eine `Referenzwert`-Instanz ohne Quelle, Datum, Objekt oder Einheit wird
abgelehnt — ohne Herkunft ist eine Referenz nicht von einer Behauptung zu
unterscheiden.

## Verkauf und Miete in allen geforderten Varianten

**Verkauf:** CHF/m² auf wählbarer Basis (NWF, HNF, NF, NGF, GF oder
**belegte Wohnfläche**) · Preis je Wohnungstyp · Einzelpreise je Wohnung.
**Miete:** CHF/m²/Jahr · Monatsmiete je Typ · Einzelmieten je Wohnung.

Fehlt ein Typpreis, gibt es **keinen Teilerlös** — der fehlende Typ wird
benannt. Stimmen Anzahl Einzelpreise und Wohnungen nicht überein, wird das
abgelehnt statt zurechtgerechnet.

## Kosten: jede Position weist ihre Basis aus

```
BKP  Position                       Berechnung                                    Betrag
 1   Abbruch Bestand                57'500 CHF (Festbetrag)                       57'500
 1   Aushub und Vorbereitung        105 CHF/m² × 299.4 m² Geschossfläche GF       31'441
 2   Gebäude                        2'400 CHF/m² × 299.4 m² Geschossfläche GF    718'656
 3   Betriebseinrichtungen          0 CHF (Festbetrag)                                 0
 4   Umgebung                       5.0 % von 718'656 CHF (bkp2_gebaeude)         35'933
 5   Baunebenkosten und Honorare    11.0 % von 843'530 CHF (subtotal_bkp1_4)      92'788
 6   Reserve und Unvorhergesehenes  10.0 % von 936'318 CHF (subtotal_bkp1_5)      93'632
 F   Finanzierung (Bauzinsen)       2.5 % von 1'029'950 CHF (subtotal_bkp1_6)     25'749
 V   Vermarktung                    2.5 % des Verkaufserlöses                     46'788
```

Jede Position kennt drei Arten — `chf_pro_m2` (auf benannter Fläche),
`absolut`, `prozent` (von einer benannten Vorgängergrösse) — und ist einzeln
überschreibbar. Der Erlös wird **vor** den Kosten gerechnet, weil sich die
Vermarktung darauf bezieht; eine Prozentposition darf sich nur auf bereits
Bekanntes stützen.

BKP 3 ist mit 0 vorbelegt (im Wohnungsbau meist nicht relevant) statt
weggelassen. Das klassische BKP 9 läuft hier als Position 6, weil die Vorgabe
BKP 1–6 verlangt — das steht so in der Begründung.

## Drei Befunde aus den Realdaten

**1 · Dem Anbau die vollen Landkosten anzulasten ergab −96 % Marge.** Das ist
arithmetisch richtig (wer ein Grundstück für 629'000 CHF kauft, um 69 m²
anzubauen, macht ein schlechtes Geschäft), aber irreführend, wenn das
Grundstück bereits gehört. Es gibt jetzt `land_ansatz`:

| Ansatz | Bedeutung |
|---|---|
| `kauf` (Vorgabe) | volle Landkosten in jedem Szenario — die Erwerbssicht |
| `im_besitz` | keine Landkosten; Gewinn und Marge messen nur die Bauinvestition |

Der **Residualwert bleibt in beiden Fällen gleich** — er beantwortet die
umgekehrte Frage. Im Kauffall erscheint bei Erweiterungsszenarien ein
ausdrücklicher Hinweis.

**2 · Baukosten von 0 CHF, die keine waren.** Ohne Flächenbasis lieferten alle
tragenden Positionen `None`, die Prozentpositionen 0 — die Summe war 0 CHF und
sah aus wie „kostet nichts". Sie ist jetzt `None` mit Begründung.

**3 · Ein grosszügigerer Wohnungsmix halbierte die Wohnungszahl, liess Erlös
und Gewinn aber unverändert.** 197 m² Wohnfläche, Mix nur 3.5-/4.5-Zimmer →
1 Wohnung à 125 m², **72 m² keiner Wohnung zugeteilt** — aber voll mitverkauft.
Der Hinweis erscheint jetzt am Verkauf und unter den offenen Punkten, und
`basis='belegt'` rechnet nur die zugeteilte Fläche.

## Dynamik — live gemessen

Neuer Endpunkt `POST /entwicklung`: Szenarien **und** Wirtschaftlichkeit aus
den Benutzereingaben, ohne Geo- oder Gemini-Abfrage. Serverseitig **7 ms**,
im Browser inklusive Rundreise **12–86 ms**.

Im Browser durchgespielt (Buchs AG, Ersatzneubau):

| Änderung | Wirkung |
|---|---|
| Verkaufspreis 9'500 → 11'000 | Erlös → 2.17 Mio., Landwert → 804'039 |
| Bodenpreis 1'050 gesetzt | Gewinn 500'244, Marge 23.1 %, Rendite 3.1 % |
| BKP 2 2'400 → 3'250 CHF/m² | Investition 1.67 → 2.00 Mio., Gewinn → 165'774, Marge → 7.6 %, Landwert → 469'569 |
| Zielmarge 15 % → 25 % | Landwert → 252'869, **Gewinn unverändert** |
| Wohnungsmix auf 100 % 3.5 Zi | 2 Wohnungen à 88 m², 21 m² Restfläche ausgewiesen |

Dass die Zielmarge den Gewinn *nicht* verändert, ist kein Fehler: sie ist eine
Vorgabe an den Residualwert, keine Grösse der Ist-Rechnung.

## Realtests

Gerechnet auf 8 gespeicherten Analysen über alle Regelungssysteme:

| System | Fall | Ersatzneubau |
|---|---|---|
| AZ | Buchs AG (0.5) | Verkauf 1.77 Mio., Marge 6.6 %, Landwert 478'989 (800 CHF/m²) |
| AZ | Russikon (20.0, gemeldet) | Verkauf 2.58 Mio., Marge 3.5 %, Landwert 697'817 |
| aBGF | Wilen (0.8) | Verkauf 3.78 Mio., Marge 19.9 %, Landwert 1'022'739 |
| nur Geometrie | Graltshausen | Verkauf 16.42 Mio., Marge 28.2 %, Landwert 4'437'116 |

Dazu 10 Varianten am selben Fall (Preis hoch/tief, Systemvorschlag statt
eigener Annahme, anderer Mix, höhere BKP, höhere Zielmarge, andere Miete,
teureres Land, Grundstück im Besitz) — jede läuft sauber bis zum Residualwert
durch.

**BMZ:** wie in Stufe 3 gilt für keines der analysierten Grundstücke eine
Baumassenziffer. Der BMZ-Pfad wirkt über die Geschossfläche, die aus G1
kommt; er ist dort verifiziert und hier nicht erneut geprüft.

## Oberfläche

Der alte statische Preis-Abschnitt ist **ersetzt**, nicht ergänzt — es gibt
nur einen Weg zur Wirtschaftlichkeit in der UI. 2'804 Zeichen toter Code
(`finanzHtml`, die Preis-Button-Verdrahtung) sind entfernt.

Der neue Abschnitt zeigt: Ergebniskacheln (Erlös, Investition, Gewinn, Marge
mit Ziel-Badge, Rendite, **max. tragbarer Landwert** hervorgehoben), die
Residualformel im Klartext, offene Punkte, den Szenarienvergleich als
klickbare Tabelle, und darunter die Eingaben — Markt mit Referenzzeilen je
Grösse, Wohnungsmix mit Prozent-Feldern und Summenprüfung, BKP-Tabelle mit
einem Eingabefeld je Position und sichtbarer Berechnungsbasis.

Jede Eingabe löst nach 350 ms Ruhe eine Neuberechnung aus; Karte und
3D-Ansicht ziehen mit, weil sich die Szenarien mitändern.

## Was bewusst nicht gebaut wurde

Keine Marktdaten-Pipeline: `referenzen` ist eine Eingabe der Schnittstelle,
keine automatische Quelle. Sobald echte Vergleichsdaten angebunden sind,
treten sie an dieselbe Stelle, ohne dass sich die Struktur ändert.

## Offene Punkte

* **Referenzdaten** kommen heute vom Aufrufer. Es gibt keine angebundene
  Marktdatenquelle.
* **Der Systemvorschlag** ist der Median der Referenzen — ohne Lagekorrektur,
  ohne Zeitbereinigung, ohne Qualitätsgewichtung.
* **Finanzierung und Vermarktung** sind eigene Systemannahmen (je 2.5 %), die
  nicht aus Modul 3 stammen — dort gibt es sie nicht. Beide sind editierbar.
* **Das Abbruchvolumen** fehlt häufig im GWR (`gvol`); dann bleibt die Position
  offen statt geschätzt, und die Baukosten sind als unvollständig markiert.
* **Keine Mehrwertabgabe, keine Steuern, keine Bauzeit-/Cashflow-Betrachtung.**

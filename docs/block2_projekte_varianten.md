# Block 2 — Projekte und Varianten

**Stand:** 12.09.2026 · **umgesetzt und im Browser verifiziert**
**Grundlage:** [LUUCY-Benchmark](benchmark_luucy.md), Schlussfolgerung 1, Punkte 1 und 2

## Der tragende Entscheid: Varianten sind Deltas

Eine Variante speichert **keine** Ergebnisse und **keine** Kopie der Basis.
Sie speichert genau zwei Dinge:

```
szenario_id   welches Entwicklungsszenario
eingaben      NUR die Werte, die der Benutzer selbst gesetzt hat
```

Daraus folgt alles Weitere von selbst:

* **Was nicht in `eingaben` steht, kommt vom System.** Die Trennung
  Referenz → Systemvorschlag → Benutzerannahme bleibt ohne Zusatzaufwand
  erhalten, auch nach dem Speichern.
* **Ändert sich die Engine, ändert sich das Ergebnis mit.** Ein konserviertes
  Ergebnis wäre schlechter, nicht besser — es würde stillschweigend veralten.
* **Varianten sind unabhängig.** Eine Änderung an der einen berührt die andere
  nicht, obwohl beide dieselbe Grundstücks- und Baurechtsbasis nutzen.

Das Projekt speichert ebenfalls keine amtlichen Basisdaten — nur den EGRID.
Die Analyse ist darüber reproduzierbar und liegt bereits in `analyse`.

## Keine zweite Engine

`_rechne_variante()` gibt die Eingaben der Variante an `_rechne_entwicklung()`
— denselben Weg, den auch die freie Eingabe nimmt. Es gibt keinen eigenen
Rechenpfad für Varianten. Fünf Varianten rechnen dauerte gemessen **23 ms**.

## Datenmodell

| Tabelle | Zweck |
|---|---|
| `projekt` | Name, Adresse, EGRID, aktive Variante, Zeitstempel |
| `variante` | Name, Szenario, `eingaben_json`, `basiert_auf_variante_id`, Stand |
| `variante_verlauf` | jeder gespeicherte Stand — die Grundlage für „zurück" |

`basiert_auf_variante_id` hält fest, woraus eine Variante entstand — so bleibt
bei „Ersatzneubau – angepasst" der Zusammenhang sichtbar, statt zwei
unverbundene Einträge zu haben.

## Nichts wird still überschrieben

Jeder Speichervorgang legt einen neuen Stand an; der bisherige bleibt.
**Auch der Ausgangszustand ist ein Stand** — sonst käme man nicht dorthin
zurück, wo noch gar keine Annahme gesetzt war. Das war beim ersten Lauf nicht
so und wurde nachgezogen.

Eine Wiederherstellung ist selbst ein neuer Stand, nicht ein Rückschritt im
Verlauf. Damit ist auch ein Zurück vom Zurück möglich — die Grundlage für ein
späteres Undo/Redo, ohne dass sich die Tabellen ändern müssen.

Ein unbekannter Eingabeschlüssel wird **abgelehnt**, nicht ignoriert: eine
Eingabe, die ins Leere läuft, wäre schlimmer als ein Fehler. Leere Werte
werden nicht gespeichert — ein leeres Feld heisst „nicht gesetzt", nicht „auf
null gesetzt", sonst lebte eine gelöschte Eingabe als Benutzerannahme `null`
weiter.

## Zwei Befunde aus dem Browsertest

**1 · Vorbelegte Felder galten als eigene Annahme.** Beim ersten Durchlauf
landeten `zielmarge`, `land_ansatz` und `verkauf_basis` als „Benutzerwerte" in
der Variante, obwohl niemand sie angefasst hatte — genau die Unterscheidung,
um die es geht, war damit hinfällig. Die Oberfläche merkt sich jetzt, welche
Felder tatsächlich bedient wurden (`wBeruehrt`); nur die werden gespeichert.

**2 · Der Erlös änderte sich beim Wiederöffnen: 1.43 → 1.87 Mio.** Der
Wohnungsmix stand sichtbar im Formular, wurde aber nicht mitgespeichert, weil
er „nicht berührt" war. Beim Wiederöffnen fehlte er, die Rechnung fiel auf die
volle Wohnfläche statt auf die belegte zurück.

Der Mix wird deshalb **immer** mitgespeichert. Er steht sichtbar im Formular
und bestimmt das Ergebnis massgeblich — eine Anzeige, die nicht zur Rechnung
passt, ist schlimmer als ein Mix, der als Annahme geführt wird.

## Bedienung

```
Rosenweg 4, Buchs AG   Rosenweg 4, 5033 Buchs AG   [schliessen] [wechseln]

VARIANTEN
[ Bestand ] [ Anbau ① ] [ Aufstockung ] [ Ersatzneubau ③ ] [ Bestand + Neubau ] [ + Variante ]

Eigene Annahmen in dieser Variante: verkauf_chf_pro_m2, bodenpreis_chf_pro_m2,
wohnungsmix. Alles Übrige stammt vom System.
```

Die Ziffer am Knopf zählt die eigenen Annahmen der Variante. Ohne offenes
Projekt bleibt die bisherige Szenarienwahl — eine Analyse funktioniert
weiterhin ohne Projekt.

Ein Variantenwechsel lädt **kein neues Projekt**: er setzt den Zeiger um und
zeichnet Szene, Kennzahlen und Wirtschaftlichkeit neu.

## Variantenvergleich

Eine Zeile je Kennzahl, eine Spalte je Variante: Machbarkeit, NWF, Wohnungen,
Verkaufserlös, Kosten, Gewinn, Marge, max. Landwert, Anzahl eigener Annahmen.

Bewusst ohne Bewertung: welche Variante die beste ist, hängt an Risiko und
Machbarkeit, nicht am grössten Gewinn. Das entscheidet später Highest & Best
Use, nicht diese Tabelle.

## Endpunkte

| Endpunkt | Zweck |
|---|---|
| `GET /projekte` | Übersicht „Meine Projekte" |
| `GET /projekt?id=` | ein Projekt mit allen Varianten (`&verlauf=1` mit Ständen) |
| `POST /projekt` | eine Aktion je Aufruf: anlegen, umbenennen, löschen, Variante anlegen/speichern/duplizieren/löschen, aktiv setzen, Stand wiederherstellen |
| `POST /projekt/rechnen` | eine Variante oder alle — letzteres liefert den Vergleich |

## Im Browser geprüft

Projekt angelegt → 5 Varianten mit Machbarkeits-Badges, Vergleichstabelle mit
9 Zeilen. Variantenwechsel: Baukörper wechselt von *Rosenweg 4 · 6 m* über
*Baubereich · 9 m* zu *Anbau Süden · 9 m*, Szenario und Kennzahlen ziehen mit.

**Der entscheidende Test — speichern, schliessen, wieder öffnen:**

| | vorher | nachher |
|---|---|---|
| Variante | Ersatzneubau | Ersatzneubau |
| eigene Annahmen | verkauf, boden, mix | verkauf, boden, mix |
| Verkaufsfeld | 9500 | 9500 |
| Baukörper 3D | Baubereich · 9 m | Baubereich · 9 m |
| Verkaufserlös | CHF 1.43 Mio. | CHF 1.43 Mio. |
| Investition | CHF 1.65 Mio. | CHF 1.65 Mio. |
| Gewinn | CHF −223'206 | CHF −223'206 |

Identisch in allen Punkten.

## Tests

`kern/tests/test_projekt.py`, 54 Zusicherungen, ohne Netz auf einer temporären
Datenbank: Anlegen, Delta-Verhalten, Unabhängigkeit der Varianten,
Zusammenführen gegen Ersetzen, Verlauf und Wiederherstellung, Duplizieren,
Löschen ohne Waisen, Übersicht.

**13/13 Engine-Suiten (880 Zusicherungen), kern 3/3.**

## Was noch fehlt

* **Sanierung** als eigene Variante — die Szenariologik dafür gibt es noch
  nicht (Master-Spezifikation Abschnitt 16).
* **Undo/Redo in der Oberfläche** — der Verlauf trägt es, die Bedienung fehlt.
* **Variante umbenennen** in der Oberfläche — der Endpunkt ist da.
* **Projekte teilen** — kommt mit Block 5.

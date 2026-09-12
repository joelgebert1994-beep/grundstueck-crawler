# Block A — Markt- und Referenzdaten

**Stand:** 12.09.2026 · **umgesetzt und an echten Importen verifiziert**
**Voraussetzung:** Stufe 5 abgeschlossen, Flächenkette geschlossen (`8c50a91`)

## Hybrid statt Entweder-oder

Die Frage war „eigene Erfassung oder kommerzieller Konnektor". Die Antwort ist
beides — und eine dritte Ebene darüber. Drei Ebenen, die nie vermischt werden:

| Ebene | Was | Wo |
|---|---|---|
| **Referenzdaten** | Vergleichsobjekte, gleich welcher Herkunft | `marktdaten.Vergleichsobjekt` |
| **Systemvorschlag** | Median der *passenden* Objekte, mit Sicherheitsgrad | `marktdaten.Marktreferenz` |
| **Benutzerannahme** | was tatsächlich gerechnet wird | `wirtschaftlichkeit.Marktwert` |

Die Benutzerannahme hat immer Vorrang. Eine Referenz ersetzt sie nie.

## Anbieterneutral — und das ist keine Absichtserklärung

`Vergleichsobjekt` ist auf keinen Datenlieferanten zugeschnitten. Dieselbe
Struktur trägt eine Wüest-Partner-Auswertung, ein eigenes gebimo-Objekt, einen
CSV-Import und eine öffentliche Quelle. Was eine Quelle nicht liefert, bleibt
`None` — es wird nichts ergänzt, um die Struktur zu füllen.

Der CSV-Import ordnet Spalten über Synonyme zu und **faltet Umlaute**. Das war
kein Detail: ein Testexport mit `Wohnfläche` und `Qualität` landete zunächst
vollständig unter `merkmale` statt in den Feldern — die Preise pro m² wurden
dadurch gar nicht erst abgeleitet, und die Auswertung meldete korrekt „keine
passenden Vergleichsobjekte". Für Schweizer und deutsche Exporte wäre der
Importer ohne Umlautfaltung unbrauchbar gewesen.

Was keiner bekannten Spalte entspricht, landet unter `merkmale` statt verloren
zu gehen (`Lift: ja` blieb so erhalten).

Abgeleitet wird nur, was **eindeutig** folgt: Preis/m² aus Preis und Fläche,
Jahresmiete/m² aus Monatsmiete und Fläche, Bodenpreis nur bei Objektart
Bauland. Ein MFH-Kaufpreis wird **nicht** zum Bodenpreis gemacht.

## Keine künstliche Genauigkeit

Der Systemvorschlag ist der Median der passenden Objekte — versehen mit einem
Sicherheitsgrad aus drei Kriterien, jedes einzeln begründet:

| Kriterium | Wirkung |
|---|---|
| Anzahl | < 3 Objekte → `gering`; < 6 → höchstens `mittel` |
| Streuung | > 45 % des Medians → `gering`; > 20 % → höchstens `mittel` |
| Aktualität | neueste Referenz > 12 Monate → höchstens `mittel`; > 24 Monate → ausgeschlossen |

Bei `gering` steht im Klartext: *„Der Systemvorschlag ist nur schwach gestützt —
als Aussage taugt hier die Bandbreite, nicht der Punktwert."*

**Eine bewertungsnahe Gewichtung nach Mikrolage, Zustand und Ausbaustandard ist
bewusst nicht gebaut.** Dafür reicht die Datenbasis heute nicht, und ein
Modell, das mehr verspricht als seine Daten hergeben, wäre genau die
Scheingenauigkeit, die ausgeschlossen ist. Stattdessen wird offengelegt, welche
Objekte einbezogen und welche ausgeschlossen wurden — jedes mit Grund:

```
Verkaufspreis  n=5  Spanne 8'800–9'300  Systemvorschlag 8'900  Sicherheit mittel
   - 5 passende Vergleichsobjekte (ab 6 gilt hoch).
   ausgeschlossen: ETW Nelkenweg 3  -> andere Objektart (ETW)
   ausgeschlossen: MFH Altbau       -> andere Gemeinde (Zürich)
   ausgeschlossen: MFH Uralt        -> Datenstand 92 Monate alt (Grenze 24)
```

Das teure Zürcher Objekt hebt den Median damit **nicht** an.

## Ein Fehler, der die Auswertung still verfälscht hätte

Derselbe CSV-Import zweimal ausgeführt legte die Objekte ein zweites Mal an: aus
4 Vergleichsobjekten wurden 7, und die Sicherheit sprang von `mittel` auf
`hoch` — ohne dass eine einzige neue Beobachtung dazugekommen wäre.

Identität wird jetzt zweistufig bestimmt: über Quelle + `objekt_id` +
Datenstand, wenn die Quelle eine ID führt, sonst über einen Fingerabdruck aus
Quelle, Bezeichnung, Datenstand, Gemeinde und den Kennzahlen. Weicht auch nur
ein Wert ab, entsteht bewusst ein neuer Eintrag — dann ist es eine andere
Beobachtung.

## Aufbewahrung: Engine rechnet, kern erinnert sich

Die Engine bleibt zustandslos. `kern/marktdaten.py` legt die Vergleichsobjekte
ab (`vergleichsobjekt` in `schema.sql`), holt sie zurück und pflegt sie.
Eigene gebimo-Objekte liegen in **derselben** Tabelle wie importierte,
unterschieden nur durch `herkunftsart` — so lassen sie sich gemeinsam
auswerten, ohne dass eine Quelle das Datenmodell dominiert.

## Endpunkte

| Endpunkt | Zweck |
|---|---|
| `GET /marktdaten?gemeinde=&kanton=&objektart=` | Bestand und Auswertung |
| `POST /marktdaten` | erfassen — einzeln, als Liste oder als CSV |
| `POST /marktdaten/loeschen` | ein Objekt entfernen |

`POST /entwicklung` lädt die Referenzen jetzt **automatisch** für Gemeinde und
Kanton des Grundstücks und wertet sie aus. Der Systemvorschlag entsteht damit
aus echten gespeicherten Referenzen, nicht aus dem Request.

## Die Marktansicht

Drei Ebenen untereinander, in genau dieser Reihenfolge, mit Sicherheitsbadge
und aufklappbarer Belegtabelle (Objekt, Quelle, Stand, Alter, Wert, Qualität):

```
Verkaufspreis                                    [brauchbar]
MARKTREFERENZEN    8'800–9'300 CHF/m² (5 Objekte, 1× gebimo, 4× extern)
SYSTEMVORSCHLAG    8'900 CHF/m²
GERECHNET MIT      9'500 CHF/m²          [meine Annahme]
```

Im Browser durchgespielt (Buchs AG): Verkauf 8'900 → 9'500, Miete 262 → 280,
Boden 950 → 1'200 gesetzt. Ergebnis: Erlös 1.33 → 1.43 Mio., Investition
1.59 → 1.74 Mio., Residualwert 117'639 → 191'889. Der Systemvorschlag bleibt
in allen drei Fällen daneben sichtbar, der Badge wechselt von „Systemannahme"
auf „meine Annahme".

Ein Einzelwert wird als Einzelwert gezeigt, nicht als Bandbreite: „262
CHF/m²/Jahr" statt „262–262", und der Badge sagt **schwach gestützt**.

## Tests

`tests/test_marktdaten.py`, 64 Zusicherungen, vollständig offline. Gesamt:
**12/12 Suiten, 835 Zusicherungen**, kern 2/2.

## Aufgeräumt

Die für die Verifikation erfundenen Vergleichsobjekte (u. a. unter dem Namen
eines echten Anbieters) wurden nach dem Test **aus der Datenbank entfernt**.
Sie hätten später für echte Marktbeobachtungen gehalten werden können.
Die Ablage ist funktionsfähig und leer.

## Offen

* Eine kommerzielle Quelle ist weiterhin **nicht** angebunden — das braucht
  einen Vertrag, nicht Code. Der Weg dorthin ist der CSV-/Dict-Import, der
  ohne Codeänderung funktioniert.
* Erfassungsmaske für eigene Objekte in der Oberfläche: die Endpunkte stehen,
  die Eingabemaske fehlt noch.
* Gewichtung nach Mikrolage und Zustand: bewusst zurückgestellt, siehe oben.

# 3D-Entwurf: vom Betrachter zur Projektstudie

Dieses Papier ist der Bauplan für die Schritte B bis F. Schritt A
(dynamische Messwerkzeuge) ist umgesetzt und live geprüft; er steht hier
nur noch, soweit die späteren Schritte darauf aufsetzen.

Die Bestandsaufnahme des vorhandenen 3D-Codes steht in
[3d_bestandsaufnahme.md](3d_bestandsaufnahme.md). Was hier folgt, ist die
Antwort auf die Frage, **welche der gewünschten Funktionen der vorhandene
Code schon grundsätzlich trägt** — und was wirklich neu ist.

---

## 1 Was schon da ist

Der entscheidende Befund zuerst: **es fehlt weniger, als es aussieht.**
Fast jede Fähigkeit, die eine Massing-Umgebung braucht, steckt bereits im
Code — sie wird nur für die Messung benutzt statt für Baukörper.

| Gebraucht für B–F | Vorhanden | Wo |
|---|---|---|
| Objekt unter dem Zeiger finden | **ja** | `THREE.Raycaster`, `szenenPunkt()`, `griffTreffer()` |
| Beschriftung an der Geometrie, scharf bei jedem Zoom | **ja** | `messSchilderZeichnen()` — HTML-Schicht über der Leinwand, je Bild projiziert |
| Laufende Aktualisierung ohne Ruckeln | **ja** | die Bildschleife läuft ohnehin; `messTakt()` wertet den Zeiger genau einmal je Bild aus |
| Greifen, Ziehen, Loslassen | **ja, seit Schritt A** | `griffAnfassen()` / `griffZiehen()`, Vorrang vor dem Kameradrehen |
| Körper aus Polygon + Höhe | **ja** | `koerper(ring, mx, my, hoehe, farbe, deckkraft)` — Extrusion mit Kanten |
| Ebenen einzeln schalten | **ja** | `u3dGruppen`, `setze3DSicht()` |
| Lokaler Meterrahmen ↔ LV95 | **ja** | `szeneRahmen {mx, my, basis, spanne}`, `nachLv95()` |
| Geländehöhe an einem Punkt | **ja** | `terrainHoeheAn(terrain, e, n)` |
| Baubereich als Geometrie im Browser | **ja** | `e1.baubereich_koordinaten`, heute schon als flache Platte gezeichnet |
| Ansicht speichern und zurückholen | **ja** | `ansichtLesen()` / `ansichtSetzen()`, Spalte `variante.ansicht_json` |
| Varianten mit Verlauf und Abstammung | **ja, serverseitig** | Tabelle `variante` mit `stand`, `variante_verlauf`, `basiert_auf_variante_id` |
| Szenarienarten | **ja, in der Engine** | `bestand`, `sanierung`, `anbau`, `aufstockung`, `dachausbau`, `ersatzneubau`, `bestand_neubau` |

Wirklich neu sind nur vier Dinge:

1. **Auswahl** — ein angeklickter Baukörper muss sich als *ein Objekt*
   verstehen, nicht als Mesh + Kantenlinien. Dafür braucht jeder Körper
   eine Kennung an der Gruppe.
2. **Ein Rechteckkörper aus Breite / Tiefe / Drehung** statt aus einem
   berechneten Ring. Vier Eckpunkte, dann derselbe `koerper()`.
3. **Verschieben und Drehen ganzer Körper** statt einzelner Punkte. Die
   Ziehmechanik von Schritt A trägt das; sie schiebt nur einen anderen
   Wert.
4. **Punkt-in-Polygon und Abstand Punkt-zu-Strecke** — die einzigen zwei
   Rechnungen, die neu im Browser entstehen. Beide sind mathematisch
   eindeutig und in wenigen Zeilen geschrieben.

**Kein OrbitControls, kein TransformControls.** Die Kamerasteuerung ist
bewusst selbst geschrieben, weil sie im Meterrahmen der Szene rechnet
(Verschiebegeschwindigkeit aus `szeneRahmen.spanne`). Ein zugekaufter
Ziehgriff müsste dieselbe Umrechnung noch einmal machen — und wäre eine
zweite Wahrheit über dieselbe Geometrie.

---

## 2 Die Trennlinie

Das ist die wichtigste Festlegung, und sie entscheidet über alles Weitere.

**Die Engine sagt, was gilt.** Parzelle, Baubereich, Grenzabstände,
Baulinien, Restriktionen, zulässige Geschosse und Höhen, Bestand,
Flächenmodell, NWF, Wohnfläche, Ausnützungsreserve. Diese Zahlen werden
im Browser **gelesen, nie nachgerechnet**.

**Das 3D-Frontend sagt, was der Benutzer zeichnet.** Lage, Abmessung,
Drehung, Geschosszahl des Studienkörpers — und die daraus folgende reine
Arithmetik: Grundfläche = Breite × Tiefe, Geschossfläche = Grundfläche ×
Geschosse.

Zwischen beidem liegt eine dritte, schmale Klasse: **Sofortprüfungen, die
geometrisch eindeutig sind.** Liegt jede Ecke des Körpers im
Baubereichspolygon? Wie weit ist die nächste Ecke von der Parzellengrenze
entfernt? Das sind Ja/Nein- und Meter-Aussagen über zwei Geometrien, die
beide schon vorliegen. Sie erfinden keine Norm — sie messen nur.

Was **nicht** in diese Klasse fällt und deshalb im Frontend nichts zu
suchen hat: anrechenbare Geschossfläche nach SIA 416, Ausnützungsziffer,
Ausnützungsreserve, Gebäudehöhe nach kantonaler Messweise, jede
Bestimmung, die vom Reglement abhängt. Dafür gibt es Schritt G
(Server-Rückrechnung) — und bis dahin steht dort „noch nicht gerechnet",
nicht eine Zahl aus dem Browser.

### Wie das in der Oberfläche aussieht

Zwei Blöcke, sichtbar getrennt, mit unterschiedlicher Herkunftsmarke:

```
PROJEKTSTUDIE                          FACHLICHE PRÜFUNG
aus der gezeichneten Geometrie         aus der Engine bzw. eindeutiger Geometrie

14.0 × 22.0 m                          Baubereich        ✓ vollständig innerhalb
3 Geschosse à 3.0 m                    Grenzabstand      ✓ 4.2 m, gefordert 4.0 m
Grundfläche  308 m²                    Geschosse         ✓ 3 von 3 zulässig
Geschossfläche 924 m²                  Gebäudehöhe       — nicht bestimmbar
                                       Ausnützung        — noch nicht gerechnet
```

Die Marke „Projektstudie" bleibt an jeder Zahl der linken Spalte. Sie ist
keine Bescheidenheitsfloskel, sondern die Aussage: *das ist Ihre
Geometrie, nicht unser Befund.*

---

## 3 Datenmodell

Hier wird nichts Neues erfunden. Der Auftrag „Variante A / B / C" ist
**bereits gebaut** — in `Crawler/kern/projekt.py` und der Tabelle
`variante`:

- `variante.name` — „Ersatzneubau 3 Geschosse"
- `variante.szenario_id` — die Verbindung zur Engine-Szenarienart
- `variante.eingaben_json` — Benutzerannahmen, **mit** Verlauf (`stand`,
  `variante_verlauf`)
- `variante.ansicht_json` — Kamera, Ebenen, Sonne, Messungen, **ohne**
  Verlauf
- `variante.basiert_auf_variante_id` — „B ist aus A entstanden"

Die Studiengeometrie bekommt eine eigene Spalte `entwurf_json`, und zwar
mit dem Verhalten von `ansicht_json`, nicht von `eingaben_json`:

> Wer einen Baukörper zehn Zentimeter verschiebt, soll keinen neuen Stand
> erzeugen. Dieselbe Begründung steht schon bei `speichere_ansicht()`:
> „Würde jede Drehung einen Stand erzeugen, wäre der Verlauf nach einer
> Minute Arbeit unbrauchbar."

Einen Stand erzeugt erst eine ausdrückliche Handlung — „Entwurf
festhalten" oder das Anlegen einer neuen Variante daraus.

Inhalt von `entwurf_json`:

```json
{
  "rahmen": { "mx": 2754713.4, "my": 1260724.15, "basis": 398.0 },
  "koerper": [
    { "id": "k1", "name": "Baukörper 1",
      "mitte": [-4.2, 11.8], "breite": 14.0, "tiefe": 22.0,
      "drehung_grad": 18.0, "geschosse": 3, "geschosshoehe_m": 3.0,
      "herkunft": "benutzer" }
  ]
}
```

Der Rahmen gehört dazu, aus genau dem Grund, aus dem er schon bei den
Messungen dabeisteht: die Koordinaten sind lokale Meter, und ohne den
Bezug läge der Körper beim nächsten Öffnen stillschweigend woanders.
`pruefeRahmen()` gibt es bereits.

`herkunft: "aus_szenario"` markiert einen Körper, der aus einem
Engine-Szenario übernommen und danach vom Benutzer verändert wurde — die
gleiche Unterscheidung wie zwischen Systemvorschlag und Benutzerannahme
im Marktreiter.

---

## 4 Die Schritte

### B — Auswählen

Klick auf einen Körper markiert ihn; Klick ins Leere hebt die Markierung
auf. Sichtbar durch eine kräftigere Kante, nicht durch eine andere Farbe
(die Farbe bedeutet schon die Bauteilart).

*Trägt der Code:* `szenenPunkt()` liefert bereits `treffer[0].object`.
Neu ist nur `gruppe.userData.koerperId` beim Anlegen und der Rückweg vom
getroffenen Mesh zur Gruppe.

*Getestet wird:* Auswahl trifft den vordersten Körper, nicht das Gelände
dahinter; ein bestehender Szenarienkörper lässt sich auswählen, obwohl er
nicht aus dem Entwurf stammt; die Messwerkzeuge gehen weiterhin vor
(wer misst, wählt nicht aus).

### C — Einen Körper erzeugen

Knopf `+ Baukörper`. Der erste Körper entsteht **nicht auf der grünen
Wiese**: Vorgabe ist die grösste einbeschriebene Rechteckfläche im
Baubereich, sonst die Parzellenmitte. Geschosszahl und Geschosshöhe aus
der Engine, wo bestimmbar — sonst 3.0 m mit sichtbarer Marke
„angenommen", nie stillschweigend.

*Trägt der Code:* `koerper()` nimmt jeden Ring. Neu sind vier Eckpunkte
aus Mitte/Breite/Tiefe/Drehung.

*Getestet wird:* ohne Baubereich entsteht trotzdem ein Körper (in der
Parzellenmitte, mit Hinweis); ohne bestimmbare Geschosshöhe steht die
Annahme dran; der Körper liegt auf dem Gelände, nicht in der Luft.

### D — Verschieben und drehen

Ziehen am Körper verschiebt ihn in der Bodenebene. Ein Griff an der
Vorderkante dreht ihn. Beides läuft über dieselbe Mechanik wie das
Ziehen eines Messpunkts.

Wichtig und ausdrücklich: **keine versteckte Korrektur.** Verlässt der
Körper den Baubereich, wird das gezeigt — der Körper bleibt, wo der
Benutzer ihn hingezogen hat. Kein Einrasten, kein Zurückspringen. Wer
bewusst ausserhalb prüft, soll das dürfen und sehen.

*Getestet wird:* Verschieben bewegt nicht die Kamera; Drehen ändert die
Grundfläche nicht; der Körper folgt dem Gelände in der Höhe; Loslassen
ausserhalb des Baubereichs verschiebt nichts zurück.

### E — Abmessungen

Breite, Tiefe, Geschosse, Geschosshöhe als Zahlenfelder neben der Szene,
zusätzlich Ziehgriffe an den Seitenkanten. Jede Änderung wirkt sofort.

Die Gesamthöhe ist **keine freie Eingabe**: sie ist Geschosse ×
Geschosshöhe plus, wo die Engine eine Angabe liefert, Dach und Sockel.
Wo sie nicht bestimmbar ist, steht das da — statt einer gerechneten Zahl,
die wie ein Befund aussähe.

### F — Sofortprüfung

Vier Prüfungen, alle rein geometrisch:

| Prüfung | Rechnung | Grundlage aus der Engine |
|---|---|---|
| Innerhalb Baubereich | Punkt-in-Polygon für alle vier Ecken | `baubereich_koordinaten` |
| Grenzabstand | kürzester Abstand Ecke ↔ Parzellenkante | `parzellengeometrie`, geforderter Wert aus `abstandsgeometrie` |
| Baulinie | Schnitt Körper ↔ Baulinie | Restriktionsgeometrie |
| Geschosszahl | Vergleich | zulässige Geschosse aus der Zone |

Drei Zustände je Prüfung, nie zwei: **erfüllt**, **verletzt**, **nicht
bestimmbar**. Der dritte ist der wichtigste — wo die Engine keine
Anforderung kennt, darf keine grüne Marke stehen. Das ist dieselbe Regel,
nach der der Rest des Produkts arbeitet.

### Erst danach

Server-Rückrechnung (SIA 416 auf die gezeichnete Geometrie), mehrere
Körper je Variante, Variantenvergleich. Alles drei setzt voraus, dass
B–F stehen und geprüft sind.

---

## 5 Was bewusst offen bleibt

- **Kein CAD.** Keine Freiformgrundrisse, keine Dachformen, keine
  Fassaden, keine Geschossgrundrisse. Ein Massing-Modell beantwortet die
  Frage „passt das hierhin und wie wirkt es" — mehr soll es nicht.
- **Kein zweites Flächenmodell.** NWF, Wohnfläche und Ausnützungsreserve
  bleiben Sache der Engine, auch wenn die Versuchung gross ist, sie im
  Browser „schnell mitzurechnen".
- **Keine automatische Optimierung.** Kein „bestmöglicher Baukörper" auf
  Knopfdruck. Das wäre eine fachliche Aussage, die niemand geprüft hat.

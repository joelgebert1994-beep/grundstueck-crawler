# 3D-Projektstudie — Bestandsaufnahme vor dem Bauen

Stand **19.09.2026**. Nichts geändert, nichts gebaut. Gelesen wurde der
vorhandene Code in `dist/index.html`, geprüft wurde live auf
`grundstueck-crawler.pages.dev`.

---

## Kurzfassung

Es ist **deutlich mehr da als erwartet**. Die Szene, das Gelände, die
Nachbarschaft, der Baubereich und der Baukörper werden bereits in 3D
gezeichnet — aus echten Enginedaten. Was fehlt, ist nicht die Darstellung,
sondern die **Interaktion**: nichts in der Szene lässt sich auswählen,
greifen oder verändern.

Der Weg zur Massing-Umgebung ist damit kein Neubau, sondern eine
Erweiterung an drei Stellen: **Auswahl**, **Veränderung**, **Rückrechnung**.

---

## 1 · Was der bestehende Code heute kann

Alles Folgende ist im Code belegt, nicht vermutet.

| | Stand | Fundstelle |
|---|---|---|
| Scene | ja, Hintergrund aus dem CSS-Token | `new THREE.Scene()` |
| Kamera | PerspectiveCamera 45°, near 0.5, far 4000 | — |
| Renderer | WebGL, antialias, `preserveDrawingBuffer` für den Bildexport | — |
| Beleuchtung | AmbientLight 0.72 + DirectionalLight 0.85 | — |
| Schatten | **ja**, PCFSoftShadowMap, 2048², `bias` und `normalBias` gegen Shadow-Acne | — |
| Orbit | **eigene Implementierung**, nicht OrbitControls | `drehung`/`neigung`/`zoom` |
| Zoom | Mausrad, begrenzt auf 0.45–3.2 | `wheel`-Handler |
| Schwenken (Pan) | **nein** — `kamera.lookAt(0, 0, 0)` fest | Renderschleife |
| Gelände | ja, echtes Höhenraster als PlaneGeometry + Wireframe | `terrainMesh()` |
| Bestandsgebäude | ja, eigene und Nachbarn, mit Höhe; ohne Höhe flach und andersfarbig | `zeichneSzene()` |
| Strassen | ja, als Linienzug auf dem Gelände | — |
| Nachbarparzellen | ja, als Umrisslinie | — |
| Grundstück | ja, Fläche + Umriss, höhenrichtig | — |
| **Baubereich** | **ja, wird bereits gezeichnet** | `e1.baubereich_koordinaten` |
| Projektbaukörper | ja, aus dem Szenario, extrudiert mit berechneter Höhe | `sz.baukoerper` |
| Baulinien in 3D | **nein** | — |
| Grenzabstandskorridor | **nein** (nur implizit als Differenz Parzelle/Baubereich) | — |
| Ebenen schalten | ja, 5 Gruppen: terrain, gebaeude, strassen, grundstueck, projekt | `u3dSicht` |
| Raycaster | **ja — aber nur zum Messen** | `strahl`, `messKlick()` |
| Messwerkzeuge | Distanz, Fläche, Höhe, Punkt, mit Schildern | `messGruppe` |
| Sonne & Schatten | ja, ganzer Tagesverlauf über `/sonne`, animierbar | `sonneTag` |
| Bildexport | ja, ins Dossier | `bild3D()` |

**Wo es liegt:** im Abschnitt `sec-szenarien`, also im Reiter **Potenzial** —
nicht in einem eigenen Reiter.

**Koordinatenrahmen:** die Szene rechnet in Metern in einem lokalen Rahmen.
`szeneRahmen = {mx, my, basis, spanne}` — Nullpunkt ist der
Parzellenmittelpunkt, Höhe 0 die Geländehöhe dort. Das ist sauber gelöst und
genau die Grundlage, die eine Massing-Umgebung braucht: reale
Höhenunterschiede und berechnete Bauhöhen passen ohne Umrechnung zusammen.

---

## 2 · Was wir weiterverwenden können

**Fast alles.** Konkret:

| Funktion | Leistet | Für die Massing-Umgebung |
|---|---|---|
| `bereitMachen()` | Szene, Kamera, Renderer, Licht, Eingaben | unverändert |
| `form()` / `koerper()` | Polygon → Shape → Extrudat mit Kanten | **Kern des Baukörpers** |
| `linie()` | Linienzug auf Gelände | Baulinien, Abstandskorridor |
| `terrainMesh()` / `terrainHoeheAn()` | Gelände + Höhe an beliebigem Punkt | Aufsetzhöhe des Körpers |
| `szeneRahmen` | lokaler Meterrahmen | gemeinsames Koordinatensystem |
| `strahl` (Raycaster) | Pick auf Szenengruppen | **Auswahl statt nur Messung** |
| `d3schalter()` / `verdrahte3DSteuerung()` | Ebenenschalter | um neue Ebenen erweitern |
| `messKlick()` + `messSchilder` | Bildschirmbeschriftung an 3D-Punkt | Masse am Baukörper |
| `bild3D()` | Standbild fürs Dossier | Variantenvergleich |

Nichts davon muss ersetzt werden.

---

## 3 · Wie Geometrie heute ins Frontend kommt

| Was | Woher | Form |
|---|---|---|
| Parzelle | `modul1_geodaten.kataster.parzellengeometrie` | LV95-Ring |
| Baubereich | `g1_ergebnis.ergebnis.baubereich_koordinaten` | LV95-Ringe (mehrere möglich) |
| Baukörper | `szenarien.szenarien[id].baukoerper[]` | `ring` + `hoehe_m` + `art` + `name` |
| Gelände | `/api/umgebung` → `terrain.hoehen[][]` | Raster + `ursprung_lv95` + `schrittweite_m` |
| Nachbargebäude | `/api/umgebung` → `gebaeude[]` | `ring` + `hoehe_m` + `terrain_hoehe_m` + `eigen` |
| Strassen | `/api/umgebung` → `strassen[]` | `koordinaten` + `hoehen_m` |
| Nachbarparzellen | `/api/umgebung` → `nachbarparzellen[]` | `ring` + `terrain_hoehe_m` |
| Grenzabstände | `g1_ergebnis` Kantenprotokoll | je Kante `abstand_m`, `art`, Vorbehalte |
| Baulinien | `restriktionsgeometrie.baulinien_gefunden[]` | **nur in der 2D-Karte verwendet** |

Zwei Dinge fallen auf:

1. **Der Baubereich ist schon da.** Er kommt fertig aus der Engine und wird
   bereits gezeichnet. Wir müssen ihn nicht herleiten.
2. **Baulinien kommen nie in die 3D-Szene.** Sie existieren als Geometrie,
   werden aber nur in der Leaflet-Karte gezeichnet.

---

## 4 · Was für eine echte Massing-Umgebung fehlt

| Lücke | Heute | Nötig |
|---|---|---|
| **Auswahl** | Raycaster nur für Messung | Klick auf Baukörper → ausgewählt, hervorgehoben |
| **Greifen** | keine | Ziehen in der Ebene, Drehen, Skalieren |
| **Zustand** | Baukörper wird bei jedem Zeichnen aus der Enginedatenstruktur neu gebaut | ein *eigener*, veränderbarer Entwurfszustand neben den Enginedaten |
| **Schwenken** | `lookAt(0,0,0)` fest | Kameraziel verschiebbar |
| **Prüfung** | keine | liegt der Körper im Baubereich? Höhe zulässig? |
| **Rückrechnung** | keine | Fläche/Geschosse → GF, und was daraus folgt |
| **Varianten** | Szenarien der Engine, nicht editierbar | eigene Entwurfsvarianten speichern/vergleichen |
| **Abstandskorridor** | nicht dargestellt | Parzelle → Korridor → Baubereich sichtbar |
| **Baulinien in 3D** | fehlen | als vertikale Ebene/Linie |

---

## 5 · Wie ein editierbarer Baukörper technisch aussähe

Vorschlag, noch nicht gebaut:

```
entwurf = {
  id, name,
  grundriss: [[x,y], …]   // lokale Meter, relativ zu szeneRahmen
  drehung_grad,
  versatz: {x, y},
  geschosse: n,
  geschosshoehe_m,
  basis: "gelaende" | "absolut"
}
```

Der Körper entsteht daraus mit dem **vorhandenen** `koerper()`: Grundriss →
`ExtrudeGeometry` mit `geschosse × geschosshoehe_m`. Verschieben und Drehen
sind dann `mesh.position` und `mesh.rotation.y` — keine Geometrieneuberechnung
nötig, nur beim Ändern des Grundrisses.

**Warum ein eigener Zustand und nicht das Enginedatenobjekt:** sobald der
Benutzer zieht, ist das Ergebnis eine *Entwurfsannahme*. Sie in
`szenarien.baukoerper` zurückzuschreiben hiesse, eine gezeichnete Form wie
ein Engineergebnis aussehen zu lassen. Der Entwurf gehört in eine eigene
Ablage — so wie `wEingaben` neben den Marktreferenzen steht.

Für die Bedienung reicht anfangs:
* Ziehen in der Grundebene (Raycast auf eine unsichtbare Ebene bei y=0)
* Drehen über einen Regler, nicht über einen Gizmo
* Grundriss zunächst als **Rechteck mit Breite/Tiefe**, nicht als frei
  editierbares Polygon

Das ist bewusst bescheiden: ein Rechteck, das sich sauber prüfen lässt, ist
mehr wert als ein freies Polygon, dessen Prüfung wir schuldig bleiben.

---

## 6 · Die Grenze: Engine gegen Entwurf

Das ist der wichtigste Abschnitt.

| Kommt aus der Engine — belastbar | Entsteht im Entwurf — Projektion |
|---|---|
| Parzellengeometrie | Lage des Baukörpers |
| Baubereich | Grundrissform und -grösse |
| Grenzabstände je Kante | Geschosszahl innerhalb des Zulässigen |
| Zulässige Geschosse, Höhen | gewählte Geschosshöhe |
| Ausnützungsziffer, Budget | resultierende Geschossfläche |
| Bestandsgebäude, Gelände | alles Gezeichnete darüber hinaus |

**Drei Regeln, die daraus folgen:**

1. **Eindeutig → darstellen.** Ein eindeutiger Baubereich wird als Fläche
   gezeichnet.
2. **Bandbreite → mehrere Körper.** Liefert G1 mehrere zulässige
   Anordnungen, werden sie als Varianten gezeigt, nicht als eine gemittelte
   Form. Der bestehende Bandbreitenmechanismus
   (`bandbreite_zulaessige_anordnungen`) gilt hier unverändert.
3. **Nicht bestimmbar → nicht zeichnen.** Fehlt die Gebäudehöhe, wird der
   Körper flach dargestellt — genau das tut der Code heute schon, und die
   Legende sagt es dazu.

**Und die Regel, die alles trägt:** aus einer frei gezogenen Form darf nie
eine baurechtlich sichere Zahl werden. Die Studie darf sagen „dieser Körper
hätte 924 m² Geschossfläche" — sie darf nicht sagen „924 m² sind zulässig".
Ob sie zulässig sind, entscheidet die Ausnützungsziffer, und die kommt aus
der Engine.

---

## 7 · Grenzabstände räumlich zeigen

Die Kette, die der Benutzer sehen soll, ist aus vorhandenen Daten
darstellbar:

```
Grundstücksgrenze   Parzellenring              (da)
Abstandskorridor    Ring minus Baubereich      (ableitbar)
Baubereich          baubereich_koordinaten     (da)
Baukörper           Entwurf                    (neu)
```

Der Korridor ist die Fläche *zwischen* Parzellenring und Baubereichsring —
beide liegen vor. Als niedriges, halbtransparentes Volumen in Warnfarbe
gezeichnet wird daraus genau die Aussage „hier darf nichts stehen".

Je Kante kennt das Kantenprotokoll zusätzlich den konkreten Abstand und
seine Herkunft. Eine Beschriftung „4.0 m Grenzabstand, Nachbarparzelle" am
jeweiligen Rand ist damit möglich — und die vorhandene Schilderlogik der
Messwerkzeuge kann sie zeichnen.

---

## 8 · Bestand und Umgebung

Bereits vollständig vorhanden: Gelände als Raster, Nachbargebäude mit
Höhen, eigene Bestandsgebäude, Strassen, Nachbarparzellen — alles über
`/api/umgebung` mit einem Radius um die Parzelle.

Gebäude ohne bekannte Höhe werden **flach und in anderer Farbe** gezeigt,
und die Legende beziffert, wie viele das sind. Diese Ehrlichkeit muss
erhalten bleiben.

---

## 9 · Live-Rückmeldung: was gerechnet werden darf

Hier ist die Trennung besonders wichtig.

| Grösse | Im Browser rechenbar? | Warum |
|---|---|---|
| Fussabdruck m² | **ja** | reine Geometrie |
| Geschossfläche | **ja** | Fussabdruck × Geschosse |
| Gebäudehöhe | **ja** | Geschosse × Geschosshöhe |
| Abstand eingehalten | **ja** | Punkt-in-Polygon gegen den Baubereich |
| Baubereich eingehalten | **ja** | dasselbe |
| Geschosse zulässig | **ja** | Vergleich mit dem Enginewert |
| **NWF / Wohnfläche** | **nein** | kommt aus `flaechenmodell` mit Annahmenprofil — im Browser nachgebaut wären es zwei Wahrheiten |
| **Ausnützungsreserve** | **nein** | braucht das Ausnützungsbudget der Engine |
| **Wirtschaftlichkeit** | **nein** | `/api/entwicklung` |

Die Regel: **Geometrie im Browser, Fachlichkeit in der Engine.** Alles,
was über Länge × Breite × Geschosse hinausgeht, geht an den Server —
genauso wie heute die Wirtschaftlichkeit.

Für die Live-Rückmeldung heisst das: sofort und im Browser kommen
Fussabdruck, GF, Höhe und die Ja/Nein-Prüfungen. NWF, Wohnfläche und
Ausnützungsreserve kommen nach einem kurzen Serveraufruf — oder bleiben
offen, solange er nicht gelaufen ist.

---

## 10 · Architekturvorschlag für den Reiter

**Position:** nach Potenzial, vor Markt.

```
Übersicht · Baurecht · Karte · Potenzial · 3D-Entwurf · Markt · Wirtschaftlichkeit · Daten & Quellen
```

Die 3D-Ansicht zieht damit aus `sec-szenarien` heraus in einen eigenen
Abschnitt. Der Potenzialreiter behält seine Zahlen und Balken.

**Was man beim Öffnen sieht:**

1. Oben eine Zeile: Szenario wählen (Bestand · Ersatzneubau · …) und
   daneben der Zustand — „Baubereich eindeutig" oder „3 zulässige
   Anordnungen" oder „nicht bestimmbar".
2. Darunter die **Szene, gross** — mindestens 520 px hoch, nicht 380.
   Beim Öffnen: Gelände, Nachbarschaft, Parzelle, Abstandskorridor,
   Baubereich. **Noch kein Entwurfskörper** — der entsteht auf Knopfdruck.
3. Rechts daneben (ab ~1100 px, darunter darunter) die **Steuerung**:
   Ebenen, dann die Parameter des gewählten Körpers, dann die Prüfliste.
4. Unter der Szene die Live-Auswertung als Kachelzeile — dieselben `.kz`
   Kacheln wie in Übersicht und Wirtschaftlichkeit.

**Varianten:** eine Entwurfsvariante ist ein `entwurf`-Objekt (siehe 5).
Sie gehört in die bestehende Projekt-/Variantenablage (`projektAktion`,
`variante_speichern`) — dort liegen die Wirtschaftlichkeitseingaben schon.
Damit ist der Vergleich zweier Entwürfe dasselbe wie der Vergleich zweier
Varianten heute, und es entsteht keine zweite Ablage.

---

## 11 · Trägt das bestehende Three.js-Setup?

**Ja, mit zwei Einschränkungen.**

Version ist **r128** (2021), geladen von cdnjs. Für Massing reicht das: die
verwendeten Klassen sind seit Jahren stabil.

Zwei strukturelle Punkte:

1. **Kein Pan.** `kamera.lookAt(0, 0, 0)` steht fest in der Renderschleife.
   Für eine Projektstudie will man den Blick verschieben können. Das ist
   eine kleine Änderung (Zielpunkt als Variable), aber sie muss bewusst
   gemacht werden.
2. **Keine Controls-Addons geladen.** `OrbitControls` und
   `TransformControls` sind bei Three.js nicht im Kern, sondern Beiwerk.
   Für r128 gibt es sie auf demselben CDN.

**Empfehlung:** die eigene Orbitsteuerung **behalten**. Sie ist schlank,
funktioniert, und ihr Verhalten ist auf diese Anwendung abgestimmt
(Ziehen dreht, Klicken misst). `OrbitControls` würde diese Unterscheidung
zerstören. Für das Verschieben des Baukörpers genügt ein eigener Raycast
auf die Grundebene — ein `TransformControls`-Gizmo wäre mehr Bedienoberfläche,
als die Aufgabe braucht.

**Kein struktureller Blocker.**

---

## 12 · Zustand der Baulinien-Ebene

Geprüft. Die Ebene **existiert** und ist verdrahtet:

* Schalter `lay-baulinie`, Gruppe `gruppen.baulinie`, Zeichnung aus
  `restriktionsgeometrie.baulinien_gefunden`
* `setLayerVerfuegbar("baulinie", anzahl)` schaltet sie bei 0 auf
  `disabled` und die Beschriftung auf `.off` (ausgegraut)

**Der Mangel, den Sie vermuten, ist real — aber ein anderer:** die Ebene
ist nicht *still* deaktiviert, sie ist sichtbar ausgegraut. Was fehlt, ist
die **Unterscheidung zweier Zustände**:

| Zustand | Heute | Sollte heissen |
|---|---|---|
| geprüft, keine Baulinie vorhanden | ausgegraut | „keine Baulinie an dieser Parzelle" |
| Kanton liefert keine Baulinien-Daten | ausgegraut | „für diesen Kanton nicht verfügbar" |

Beides sieht identisch aus. Das ist derselbe Fehlertyp wie beim
Markt-Reiter: „keine Daten" und „nicht geprüft" werden gleich dargestellt.

Die Engine liefert die Information: `baulinien_gefunden` ist eine Liste;
ob die Abfrage überhaupt lief, steht im Restriktionsteil. Die Korrektur
wäre klein — aber sie gehört in einen eigenen Schritt, nicht in den
3D-Block.

---

## 13 · Luftbild — nicht reproduzierbar

Ich habe den Fehler **in drei Zuständen gesucht und nicht gefunden**:

| Zustand | Ergebnis |
|---|---|
| Reiter Karte, Zoom 18 | 9 Kacheln, alle geladen, kein Abschnitt |
| Reiter Karte, Zoom 21 | 4 Kacheln, alle geladen, korrekt hochskaliert |
| Übersichtsbühne (502 × 271) | 6 Kacheln, alle geladen, `map.getSize()` passt |

In allen drei Fällen stimmten Containergrösse und Leaflet-Grösse überein.

**Zwei Mechanismen bleiben als Verdacht, beide im Code belegt:**

1. `setzeAnsicht()` ruft **nie** `map.invalidateSize()`. Wechselt die
   Ansicht, während der Container gerade seine Grösse geändert hat
   (Bühnenwechsel, Fenstergrösse), rechnet Leaflet mit der alten Grösse
   und lässt einen Streifen leer.
2. `maxNativeZoom: 19` — jenseits Zoom 19 wird hochskaliert. Bei
   swissimage fällt das stärker auf als bei der Pixelkarte.

**Was ich brauche, um es zu beheben statt zu raten:** in welchem Reiter,
bei welchem Zoom und bei welcher Fensterbreite es auftritt — und ob es
nach einem Fenstergrössenwechsel verschwindet. Dann ist es in einer Zeile
erledigt.

---

## Vorschlag für den ersten Prototyp

Klein, und jeder Schritt einzeln prüfbar:

**Schritt 1 — Umzug ohne Funktionsänderung.** Die 3D-Ansicht bekommt einen
eigenen Reiter „3D-Entwurf" nach Potenzial, grössere Bühne, Kameraziel
verschiebbar. Sonst nichts. Danach ist sichtbar, ob der Umzug etwas
gebrochen hat.

**Schritt 2 — Baurechtsgrenzen sichtbar.** Abstandskorridor zwischen
Parzelle und Baubereich als eigene Ebene, Baulinien als vertikale Ebene,
je Kante der Abstand angeschrieben. Alles aus vorhandenen Daten, noch
keine Interaktion.

**Schritt 3 — Auswahl.** Klick auf einen Körper wählt ihn aus und zeigt
seine Masse. Nur lesen, noch nicht verändern.

**Schritt 4 — der erste veränderbare Körper.** Ein Rechteck mit Breite,
Tiefe, Drehung, Geschossen. Verschiebbar in der Grundebene. Live:
Fussabdruck, GF, Höhe, und die Prüfung „liegt im Baubereich" — grün oder
rot, sonst nichts.

**Schritt 5 — Rückrechnung.** NWF, Wohnfläche und Ausnützungsreserve über
den Server, mit demselben Muster wie die Wirtschaftlichkeit.

**Schritt 6 — Varianten.** Speichern und vergleichen über die bestehende
Variantenablage.

Nach Schritt 4 kann man das, was Sie beschrieben haben:
*Grundstück → Baurechtsgrenzen → bestehende Umgebung → möglicher Baukörper
→ frei drehbare Ansicht → veränderbares Szenario → Live-Auswertung.*

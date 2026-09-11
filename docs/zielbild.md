# Zielbild (verbindliche Produktspezifikation)

**Festgelegt:** 11.09.2026 durch den Auftraggeber · **Status:** Master-Leitplanke

Diese Datei ist die verbindliche Zieldefinition. Jeder Entwicklungsschritt wird
an ihr gemessen: *Bauen wir gerade in Richtung dieses Endprodukts?* Wenn eine
bestehende Struktur das Endprodukt später behindern würde, ist das früh zu
erkennen und sauber zu lösen. Bei einer echten Grundsatzentscheidung: STOPP und
berichten.

Das Endprodukt ist **kein Datenanzeiger**, sondern ein Werkzeug, das aus einem
Grundstück möglichst automatisch ableitet:

> Was ist heute vorhanden? · Was ist rechtlich erlaubt? · Was kann geometrisch
> tatsächlich gebaut werden? · Welche Entwicklungsszenarien sind möglich? ·
> Wie viel Fläche entsteht? · Wie viel davon ist Wohnfläche? · Wie viele
> Wohnungen? · Welcher Wohnungsmix? · Was kann verkauft/vermietet werden? ·
> Was kostet die Entwicklung? · Welcher Gewinn, welche Marge, welche Rendite? ·
> Welchen maximalen Landpreis trägt das Projekt? · Und wie sieht das räumlich aus?

Und es zeigt jederzeit nachvollziehbar, **wie** es zu den Ergebnissen kommt.

Die Benutzerführung versteckt die vielen Berechnungen. Sichtbar ist primär:
**Was kann ich machen? → Wie viel entsteht? → Was ist es wert? → Was kostet es?
→ Was bleibt übrig?**

---

## 1 Eingabe
Adresse eingeben → Grundstück auf Karte → auswählen → Analyse starten.
Alternativ: EGRID, Parzelle direkt auf der Karte, gespeichertes Grundstück
öffnen. Die Eingabe muss extrem einfach sein.

## 2 Grundstück
Automatisch möglichst vollständig: Adresse, Gemeinde, Kanton, EGRID, EGID,
Parzellennummer, amtliche Fläche, Polygon, Form, Ausrichtung, relevante Kanten,
bestehende Gebäude, weitere amtliche Daten.

## 3 Bestand
Gebäudegrundfläche, Baujahr, Geschosszahl, Vollgeschosse, Attika, Gebäudehöhe,
Gesamthöhe, Volumen, Nutzung, Wohnnutzung, Energiebezugsfläche, weitere
GWR-/amtliche Gebäudedaten, verfügbare Flächen.
**Bestand und Neubau sind logisch auseinanderzuhalten.**

## 4 Baurecht
Das Tool muss das konkrete lokale Regelwerk verstehen — nicht nur AZ. Je nach
Gemeinde/Kanton gelten: AZ, GFZ, ÜZ, BMZ, Grundflächenregel, BGF-Regeln,
anrechenbare Grundstücksfläche, Geschosszahl, Vollgeschosse, Attika,
Gebäudehöhe, Gesamthöhe, Fassadenhöhe, Baufeld, Baubereich, Baukörper — oder
Kombinationen. **Die Engine muss erkennen, welches Regelungssystem gilt.**

## 5 Baurechtliche Berechnung
Aus den Regeln konkrete Flächen/Volumen rechnen, z. B.
anrechenbare Grundstücksfläche × AZ = zulässige Geschossfläche.
Danach **weiterprüfen**: Baubereich, Grenzabstände, Strassenabstand,
Gebäudeabstand, Baulinien, Höhen, Geschosszahl, weitere Restriktionen.
Lässt die Geometrie weniger zu als die Ziffer: die baulich nutzbare Fläche
entsprechend begrenzen **bzw. als Konflikt ausweisen**.

## 6 BMZ / Volumen
Zulässiges Volumen rechnen, Baukörper geometrisch erzeugen, Höhen, Geschosse,
Dach, Attika, Untergeschosse, kantonale Regeln berücksichtigen.
**Theoretisch zulässiges und tatsächlich umsetzbares Volumen unterscheiden.**

## 7 ÜZ / Grundfläche
Fläche × ÜZ = zulässige Grundfläche, danach geometrisch prüfen. Beispiel:
theoretisch 300 m², geometrisch 255 m² → 255 m² als möglich ausweisen, 300 m²
als theoretisches Limit weiterhin zeigen.

## 8 Anrechenbare / nicht anrechenbare Flächen
Unterscheiden zwischen Grundstücksfläche, anrechenbarer Fläche, nicht
anrechenbaren Flächen, Baulinien, Strassenraum, Gewässerraum, Wald, weiteren
Ausschluss-/Sonderflächen. **Keine pauschalen Abzüge, wenn das konkrete Recht
etwas anderes sagt.**

## 9 Geschosslogik
Untergeschoss, Keller, Erdgeschoss, Vollgeschoss, Attika, Dachgeschoss,
Tiefgarage, Technik, Nebenflächen unterscheiden. Zulässt die Gemeinde
2 Vollgeschosse + Attika und hat der Bestand bereits 2 Vollgeschosse + Attika,
muss das System das erkennen und die Aufstockung entsprechend beurteilen —
nicht bloss „2 Geschosse möglich“ sagen. **Bestandssituation gegen konkretes
Regelwerk.**

## 10 Raumhöhe / Flächenumrechnung
Geschosshöhe, lichte Raumhöhe, konstruktive Höhe und baurechtlich relevante
Höhe unterscheiden. Jede für die Rechnung relevante Annahme muss **explizit
dargestellt und editierbar** sein.

## 11 Von BGF/GF zu Wohnfläche
Schrittweise von baurechtlich möglicher Fläche zur wirtschaftlich relevanten
Wohnfläche, mit sichtbarem Rechenweg (z. B. 1'200 m² BGF − 180 m² = 1'020 m²),
danach Erschliessung, Treppen, Lift, Technik, Nebenflächen, Konstruktion,
Wände → NWF/HNF/NF. **Die Abzüge dürfen NICHT fest verdrahtet sein** — der
Nutzer stellt sie ein (15 %, 12 %, eigene Berechnung).

## 12 SIA 416
GF → NGF → NF → HNF → NNF, jeweils klar ausgewiesen als *bestimmt*,
*berechnet*, *angenommen* oder *nicht bestimmbar*.
**Keine erfundenen 81-%-Umrechnungen.**

## 13 Flächendefinitionen
Grundstücksfläche, BGF/GF, NGF, NF, HNF, Wohnfläche/NWF, Verkaufsfläche strikt
auseinanderhalten. **Die jeweils verwendete Definition muss im Ergebnis
sichtbar sein.**

## 14 Entwicklungsszenarien
Bestand belassen · Anbau/Erweiterung · Aufstockung · Dachausbau ·
Ersatzneubau · Bestand + Neubau · *Noch nicht entschieden* (→ mehrere Szenarien
automatisch vergleichen). Je Variante: Machbarkeit, Baurecht, Geometrie,
Geschosse, Höhen, GF/BGF, NF/HNF/NWF, Wohnungen, Wohnungsmix, Verkauf/Miete,
Kosten, Gewinn, Marge, Rendite, Residualwert.

## 15 Konkrete bauliche Aussagen
Echte Aussagen statt Datenlisten, z. B.: *Aufstockung nicht empfohlen — die
zulässige Geschoss-/Höhenentwicklung ist ausgeschöpft. Anbau möglich, aber nur
im westlichen Bereich innerhalb des verbleibenden Baubereichs. Ersatzneubau
möglich: Baubereich Polygon X, max. Höhe Y m, Z Geschosse.*
**Diese Aussagen müssen auf den berechneten Daten beruhen.**

## 16 Geometrie
Grundstück, Baubereich, Grenzabstände, Strassenabstand, Gebäudeabstände,
Baulinien, Gewässer, Wald, Restriktionen, Schutzflächen. Kanten möglichst
automatisch klassifizieren; **wenn nicht eindeutig → manuelle Auswahl je Kante.**

## 17 2D / 3D
Visualisierung ist Kernbestandteil. Je Szenario den Baukörper aus den
berechneten Geometrien darstellen (Bestand, Anbau, Aufstockung, Ersatzneubau,
Bestand + Neubau). Langfristig: 3D-Grundstück, Terrain, Bestands- und
Nachbargebäude, Höhen, Baubereich, Schnitt, Volumenvergleich Bestand vs.
Potenzial.

## 18 Sonne
Langfristig Sonnenstand, Tagesverlauf, Beschattung, Jahreszeiten, Umgebung,
Gebäudehöhen, Verschattung — **auf realer Geometrie beruhend.**

## 19 Umgebung
ÖV, Schulen, Einkauf, Strassen, Topografie, Terrain, Infrastruktur, Lärm,
Aussicht/Sichtbeziehungen soweit technisch belastbar, Gebäudeumgebung.

## 20 ÖREB / Schutz / Sondernutzung
ÖREB, Nutzungsplanung, Gewässerraum, Wald, Natur, Landschaft, Ortsbild,
Denkmalschutz, Inventare, Gefahren, Lärm, belastete Standorte, Altlasten,
Fruchtfolgeflächen, Sondernutzungs-/Gestaltungs-/Quartierpläne,
Sonderbauvorschriften, Baulinienpläne.
**Sondernutzungspläne gegenüber der Grundzone korrekt priorisieren.**

## 21 Wohnungsmix
Frei editierbar (z. B. 2.5 Zi 20 % / 3.5 Zi 50 % / 4.5 Zi 30 %). Daraus Anzahl
Wohnungen, Grössen, NF/HNF/NWF, Verkaufspreise, Mieten, Gesamtumsatz/-ertrag.
Später zusätzlich: automatischer Vorschlag anhand Lage/Markt.

## 22 Marktpreise
Eigener, unabhängiger Markt-Layer: Bodenpreis, Verkaufspreis, Mietpreis je m²,
Preise/Mieten je Wohnung, Vergleichsobjekte und -grundstücke, Lagekorrekturen,
Datenstand, Datenqualität. **Alle Werte editierbar, Ergebnis sofort neu.**

## 23 BKP / Kosten
Strukturierter Kostenbereich, mindestens BKP 1 Vorbereitung, 2 Gebäude,
3 Betriebseinrichtungen, 4 Umgebung, 5 Baunebenkosten, 6 Reserve; weitere
Untergruppen nach Bedarf. Standardwerte möglich, **alle Werte editierbar** —
als CHF/m² HNF, absolut oder als eigene Einzelpositionen; abhängige
Berechnungen aktualisieren sofort.

## 24 Wirtschaftlichkeit
Je Szenario separat. Verkauf: Wohnfläche × Preis/m² → Gesamterlös.
Vermietung: Wohnfläche × Miete/m² → Jahresmietertrag. Kosten: Land, BKP 1–6,
Abbruch, Finanzierung, Vermarktung, Reserven, weitere. Ergebnis:
Gesamtinvestition, Verkaufserlös, Mietertrag, Gewinn, Marge, Rendite,
Kosten/m², Erlös/m².

## 25 Gewinn / Marge
Zielmarge vorgebbar. Erlös − Kosten = Gewinn; Gewinn / Umsatz = Marge.
Zielmarge und Kosten editierbar.

## 26 Residualer Landwert
Erlös − Projektkosten ohne Land − gewünschter Gewinn = maximal tragbarer
Landwert, als CHF total und CHF/m² Grundstück. **Dynamisch** auf Änderungen von
Verkaufspreis, Wohnungsmix, Fläche, BKP, Zielmarge, Finanzierung.

## 27 Szenariovergleich
Bestand · Anbau · Aufstockung · Ersatzneubau · Bestand + Neubau nebeneinander,
verglichen über Machbarkeit, GF/BGF, NF, HNF, NWF, Wohnungen, Verkauf, Miete,
Kosten, Gewinn, Marge, Rendite, Residualwert. **Auf einen Blick erkennbar,
welche Variante am attraktivsten ist.**

## 28 Quellen / Herleitung
Jede wichtige Zahl: Wert → Quelle → Dokument → Artikel → Zitat → Datenstand →
Confidence. Bei Benutzerwerten: *Benutzerannahme*. Herleitung im Drilldown.

## 29 Dynamische Neuberechnung
Grundstück, Bauvariante, BKP, Wohnungsmix, Verkaufspreis, Miete, Zielmarge —
jede Änderung wirkt sofort, **ohne unnötige komplette Neuanalyse.**

## 30 Caching / Trennung
Teure Analysen wiederverwenden. Anderer Wohnungsmix, anderer Verkaufspreis,
andere BKP, andere Miete → **keine erneute Gemini-/ÖREB-Analyse**, nur die
betroffene Rechenschicht.

## 31 Benutzeroberfläche
Premium-Produkt. Kein Behördendesign, kein statisches Dashboard, kein
Tabellenfriedhof, keine 100 Eingabefelder auf einmal. Adresse → Karte →
Analyse, danach klare Bereiche: ÜBERSICHT, BAURECHT, BESTAND, BAUBEREICH,
SZENARIEN, FLÄCHEN, WOHNUNGEN, MARKT, KOSTEN, WIRTSCHAFTLICHKEIT, 3D, QUELLEN.
Modern, visuell, interaktiv: Karten, Slider, Toggles, Drag/Drop wo sinnvoll,
2D/3D-Wechsel, Szenarien im direkten Vergleich.

## 32 Ergebnisse zuerst einfach
Die erste Ansicht ist keine Fachbuchseite, sondern z. B.: *Ersatzneubau
möglich · Aufstockung eingeschränkt · Anbau Ost nicht möglich · mögliche
Wohnfläche 1'020–1'100 m² · 12–15 Wohnungen · Verkauf CHF 9.0–10.0 Mio. ·
Investition CHF 6.8–7.4 Mio. · Marge 12–18 % · max. tragbarer Landpreis
CHF X–Y Mio.* Details danach.

## 33 Unsicherheit
Grün = belastbar · Gelb = Annahme/teilweise unsicher · Rot = nicht bestimmbar /
manuelle Prüfung. **Keine Scheingenauigkeit.**

## 34 Akquise (später)
Über der Analyse kann das AkquiseRadar liegen: Ereignis → Grundstück →
Potenzial → Szenario → Markt → Wirtschaftlichkeit → Opportunity.

## 35 Produktqualität
Kein Tool, das viele Daten anzeigt, sondern eines, das fachlich nachvollziehbar
sagt: *„Das kannst du mit diesem Grundstück wahrscheinlich machen“* — inklusive
warum, wie viel, wo, in welcher Variante, mit welcher Fläche, welchen
Wohnungen, zu welchem Marktwert, mit welchen Kosten, welchem Gewinn, welcher
Marge, welchem Landwert. Visuell und verständlich.

## 36 Entwicklungsreihenfolge
1. ÖREB / Datenabdeckung · 2. Geometrie / Kanten / Baubereich · 3. Bestand ·
4. Flächen / SIA 416 · 5. Szenarien · 6. 2D/3D · 7. Referenzobjekte /
Wohnungsmix · 8. Markt · 9. BKP · 10. Wirtschaftlichkeit · 11. Residualwert ·
12. Sonnensimulation / erweiterte Visualisierung · 13. Akquise / Opportunity.
**Die Grundarchitektur muss diese Erweiterungen ermöglichen.**

## 37 Absolute Qualitätsregel
**Niemals eine Zahl erfinden, nur damit die Darstellung vollständig aussieht.**
Nicht verfügbar → *nicht verfügbar*. Nicht eindeutig → *unsicher*. Prüfung
nötig → *manuelle Prüfung*. Kantonal/kommunal abweichende Regel → *lokale Regel
anwenden*. Verschiedene Definitionen → *Definition explizit zeigen*.
Lieber eine transparente Bandbreite als eine falsche Einzelzahl.

---

# Ergänzung: Markt- und Wirtschaftlichkeitsebene

Verkaufspreise und Mietzinse müssen **vollständig manuell eingebbar und
überschreibbar** sein. Dabei sind zwei Dinge strikt zu trennen:

**1 · Referenzdaten** — Vergleichsobjekte und Marktdaten (Verkaufs-/Mietpreise
CHF/m², Preise je Wohnung, Vergleichsgrundstücke, ähnliche Objekte, Lage-/
Qualitätsmerkmale, Datenstand, Quelle, Datenqualität). Diese dienen **nur als
Orientierung bzw. Vorschlag.**

**2 · Eigene Marktannahme** — die Werte, mit denen tatsächlich gerechnet wird.

> Referenz 8'700–9'300 CHF/m² · Systemvorschlag 9'000 · Benutzer setzt 9'500
> → die Wirtschaftlichkeit rechnet mit **9'500**.

**Referenzdaten dürfen NIE ungefragt die Benutzerannahme ersetzen.** Die UI
unterscheidet sichtbar: *MARKTREFERENZEN — „Das zeigen vergleichbare Objekte.“*
gegen *MEINE ANNAHME — „Damit rechne ich.“*

**Verkauf** wahlweise als CHF/m² Wohnfläche, CHF/m² NWF/NHF (je nach
verwendeter Definition), Preis je Wohnung oder individuelle Preise je
Wohnungstyp. **Miete** wahlweise CHF/m²/Jahr, Monatsmiete je Wohnung oder
unterschiedliche Mieten je Wohnungstyp.

**Dynamik:** Verkaufspreis → Erlös; Mietzins → Jahresmietertrag; Wohnungsmix →
Erlös/Ertrag; Fläche → Erlös/Ertrag; BKP → Kosten; Zielmarge → maximal
tragbarer Landpreis.

**Transparenz:** jede Zahl trägt ihre Herkunft — `[Referenz]`,
`[Systemannahme]` oder `[Benutzerannahme]`. Dasselbe Prinzip gilt später für
Bodenpreis, Verkauf, Miete, BKP, Finanzierung, Zielmarge, Leerstand und weitere
wirtschaftliche Parameter.

---

# Ergänzung: Visualisierung in realer Umgebung

Festgelegt am 11.09.2026, nach Stufe 4. Präzisiert Abschnitt 17.

Das Endprodukt besteht **nicht** aus einem farbigen Baukörper auf weissem
Hintergrund. Die Visualisierung bezieht die reale Umgebung des Grundstücks ein.

**1 · Kataster** — Grundstücksgrenze, Parzellen, bestehende Gebäude, Strassen,
Baulinien, relevante Restriktionen.

**2 · Luftbild** — reales Luftbild als Hintergrund, Grundstück darübergelegt,
bestehender Gebäudebestand, Umgebung sichtbar.

**3 · 3D** — Gelände/Topografie soweit verfügbar, bestehende Gebäude,
Nachbargebäude soweit Daten verfügbar, Strassen und Umgebung, Gebäudehöhen
soweit verfügbar, der berechnete mögliche Baukörper, die Szenarien.

**Alle Szenarien in derselben räumlichen Umgebung:** Bestand → tatsächlicher
Bestand · Anbau → Bestand plus möglicher Anbau exakt im berechneten zulässigen
Bereich · Aufstockung → Bestand plus zusätzliches berechnetes Volumen ·
Ersatzneubau → Bestand entfernt, berechneter neuer Baukörper ·
Bestand + Neubau → bestehendes Gebäude plus zusätzlicher Baukörper.

**Die 3D-Geometrie darf nicht frei erfunden sein.** Sie entsteht aus den
tatsächlich berechneten Grundstücksgrenzen, Baubereichen, Abständen,
Geschossen, Gebäudehöhen, Gesamthöhen und Szenarien. Fehlen Gebäudehöhe oder
andere Daten: **nicht raten** — transparente Darstellung bzw. entsprechender
Unsicherheitsstatus.

**Später zusätzlich:** Höhen-/Schnittansicht, Bestand gegen Potenzial,
Nachbargebäude, Gelände, Sonnensimulation, Beschattung, Sonnenstand,
Szenarien per Klick umschalten.

**Benutzerführung:** `[ Kataster ] [ Luftbild ] [ 3D ]`, und bei 3D
`[ Bestand ] [ Anbau ] [ Aufstockung ] [ Ersatzneubau ] [ Bestand + Neubau ]`.

Das Ziel ist eine visuell hochwertige, moderne Immobilienentwicklungsansicht —
**kein weisser GIS-Hintergrund mit isoliertem Würfel.**

Ausdrücklich **nicht jetzt** zu bauen: keine grosse neue
Visualisierungsarchitektur, keine Aufblähung der laufenden Stufe. Die
bestehende 3D-Grundlage bleibt so, dass reale Umgebung, Nachbargebäude,
Terrain, Luftbild und Sonnensimulation später sauber darauf aufsetzen.

---

## Was daraus für den laufenden Bau folgt

Nichts davon wird vorgezogen. Die freigegebene Stufenfolge bleibt. Aber bei
jedem Schritt gilt die Prüffrage aus Abschnitt 38 der Vorgabe: *Bauen wir
gerade in Richtung dieses Endprodukts?* Konkret schon jetzt beachtet:

* **Abschnitt 16** verlangt bei nicht eindeutiger Kante die manuelle Auswahl.
  Die Kantenklassifikation (Stufe 2) liefert deshalb je Kante einen eigenen
  Datensatz mit Art, Begründung, Beleg und Aussenpunkt — die Struktur, an der
  ein manueller Override später andockt, ohne sie zu ändern.
* **Abschnitt 37** ist der Grund, warum eine Strassenkante ohne belastbaren
  Strassenabstand keinen Ersatzwert bekommt, sondern die Bandbreite behält.
* **Abschnitt 28** ist der Grund, warum jede Kantenzuordnung ein eigenes
  Quellenobjekt erzeugt.
* **Die Visualisierungs-Ergänzung** ist der Grund, warum die 3D-Szene in einem
  lokalen Koordinatenrahmen am Parzellenschwerpunkt rechnet und jeder Körper
  über dieselbe Funktion entsteht — siehe
  [stufe4_szenarien.md](stufe4_szenarien.md), Abschnitt „Was die Grundlage
  trägt".

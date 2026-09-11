"""
Regressionstests fuer die Kantenklassifikation (Stufe 2, G2) und ihre
Verdrahtung in G1.

Vollstaendig OFFLINE: `_identify()` wird durch ein Double ersetzt, das eine
konstruierte Nachbarschaft liefert. Damit ist die Entscheidungsregel selbst
pruefbar, unabhaengig davon, was geo.admin.ch heute gerade antwortet.

Geprueft wird genau das, was schiefgehen kann:

  * Strassenparzellen tarnen sich als Nachbarparzellen -- der Schnitt-Test
    (Strassenachse verlaeuft durch das Polygon) muss sie enttarnen.
  * Der Aussenpunkt muss auch bei konkaven Parzellen und bei umgekehrter
    Ringorientierung wirklich ausserhalb liegen.
  * Eine Kante ohne belastbaren Befund muss "unbestimmt" heissen und darf
    keinen Abstand bekommen.
  * Der Strassenabstand darf NIE aus grenzabstand_klein_m/gross_m abgeleitet
    werden. Fehlt er, wird nicht kantenweise gerechnet -- dann bleibt die
    Bandbreite, und die offenen Kanten werden benannt.

CLI: python -m tests.test_kantenklassifikation
"""

from __future__ import annotations

import sys

from shapely.geometry import Polygon

from potenzial_engine import kantenklassifikation as kk
from potenzial_engine import modul2_bzo_analysis as m2
from potenzial_engine.g1_verdrahtung import (
    G1VerdrahtungError,
    _kantenabstaende_aus_klassifikation,
    berechne_g1_fuer_fall,
)

FEHLER: list[str] = []

# Reale LV95-Groessenordnung, damit nichts an Koordinatenannahmen haengt.
OX, OY = 2600000.0, 1200000.0


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def p(x: float, y: float) -> tuple[float, float]:
    return (OX + x, OY + y)


# Eigene Parzelle: Quadrat 20 x 20 m.
EIGEN_RING = [p(0, 0), p(20, 0), p(20, 20), p(0, 20)]
EIGEN_EGRID = "CH000000000001"

# Nachbarschaft:
#   Sueden  -> Strassenparzelle (Achse verlaeuft hindurch)
#   Osten   -> nichts
#   Norden  -> echte Nachbarparzelle
#   Westen  -> kein Polygon, aber eine Achse 1 m neben dem Probe-Punkt
NACHBAR_NORD = [p(0, 20), p(20, 20), p(20, 40), p(0, 40)]
STRASSENPARZELLE_SUED = [p(-5, -8), p(25, -8), p(25, 0), p(-5, 0)]
ACHSE_SUED = [p(-5, -4), p(25, -4)]
ACHSE_WEST = [p(-3, -10), p(-3, 40)]


def _identify_double(e, n, layer, tolerance=5, return_geometry=False):
    """Liefert die konstruierte Nachbarschaft im Format des MapServers."""
    if layer == kk.LAYER_STRASSEN:
        return [
            {"geometry": {"type": "LineString", "coordinates": [list(c) for c in ACHSE_SUED]},
             "properties": {"strassenname": "Dorfstrasse", "objektart": 11}},
            {"geometry": {"type": "LineString", "coordinates": [list(c) for c in ACHSE_WEST]},
             "properties": {"strassenname": "Hinterweg", "objektart": 11}},
        ]
    if layer == kk.LAYER_CADASTRE_GEOM:
        return [
            {"geometry": {"type": "Polygon", "coordinates": [[list(c) for c in EIGEN_RING]]},
             "properties": {"number": "100", "egris_egrid": EIGEN_EGRID}},
            {"geometry": {"type": "Polygon", "coordinates": [[list(c) for c in NACHBAR_NORD]]},
             "properties": {"number": "101", "egris_egrid": "CH000000000002"}},
            {"geometry": {"type": "Polygon", "coordinates": [[list(c) for c in STRASSENPARZELLE_SUED]]},
             "properties": {"number": "900", "egris_egrid": "CH000000000009"}},
        ]
    return []


def _mit_identify_double(fn=_identify_double):
    original = kk._identify
    kk._identify = fn
    return original


# ---------------------------------------------------------------------------
# 1. Aussenpunkt-Bestimmung
# ---------------------------------------------------------------------------

def test_aussenpunkt() -> None:
    print("=== Aussenpunkt: liegt wirklich ausserhalb, auch konkav und rueckwaerts ===")
    quadrat = Polygon(EIGEN_RING)
    for i in range(4):
        aussen = kk._aussenpunkt(EIGEN_RING, i)
        pruefe(not quadrat.contains(Polygon(EIGEN_RING).centroid.__class__(*aussen)),
               f"Quadrat, Kante {i}: Aussenpunkt liegt ausserhalb")

    # Ringorientierung umgekehrt -- darf nichts aendern.
    rueckwaerts = list(reversed(EIGEN_RING))
    poly_r = Polygon(rueckwaerts)
    alle_aussen = all(
        not poly_r.contains(poly_r.centroid.__class__(*kk._aussenpunkt(rueckwaerts, i)))
        for i in range(4)
    )
    pruefe(alle_aussen, "umgekehrte Ringorientierung: alle Aussenpunkte liegen ausserhalb")

    # L-Form (konkav): der Schwerpunkt liegt hier NICHT im Polygon -- eine
    # schwerpunktbasierte Richtungsbestimmung wuerde kippen.
    l_form = [p(0, 0), p(30, 0), p(30, 10), p(10, 10), p(10, 30), p(0, 30)]
    poly_l = Polygon(l_form)
    treffer = sum(
        1 for i in range(len(l_form))
        if not poly_l.contains(poly_l.centroid.__class__(*kk._aussenpunkt(l_form, i)))
    )
    pruefe(treffer == len(l_form), f"L-Form (konkav): alle {len(l_form)} Aussenpunkte ausserhalb ({treffer})")


# ---------------------------------------------------------------------------
# 2. Klassifikation der vier Faelle
# ---------------------------------------------------------------------------

def test_vier_faelle() -> None:
    print("=== Klassifikation: Strassenparzelle, Nachbar, Strassenraum, unbestimmt ===")
    original = _mit_identify_double()
    try:
        r = kk.klassifiziere_kanten(EIGEN_RING, OX + 10, OY + 10, eigenes_egrid=EIGEN_EGRID)
    finally:
        kk._identify = original

    kanten = {k["nr"]: k for k in r["kanten"]}
    pruefe(len(r["kanten"]) == 4, f"4 Kanten beschrieben ({len(r['kanten'])})")

    sued = kanten[0]
    pruefe(sued["art"] == kk.ART_STRASSE,
           f"Sued: Strassenparzelle wird als Strasse erkannt ({sued['art']})")
    pruefe(sued.get("strassenname") == "Dorfstrasse",
           f"Sued: Strassenname als Beleg ({sued.get('strassenname')})")
    pruefe("durchquert" in (sued.get("begruendung") or ""),
           "Sued: Begruendung nennt den Schnitt-Test")
    pruefe(sued.get("nachbar_nummer") == "900",
           f"Sued: die Strassenparzelle ist namentlich belegt ({sued.get('nachbar_nummer')})")

    ost = kanten[1]
    pruefe(ost["art"] == kk.ART_UNBESTIMMT, f"Ost: ohne Befund unbestimmt ({ost['art']})")
    pruefe("manuelle Pruefung" in (ost.get("begruendung") or ""),
           "Ost: Begruendung verlangt manuelle Pruefung")

    nord = kanten[2]
    pruefe(nord["art"] == kk.ART_NACHBARPARZELLE, f"Nord: echte Nachbarparzelle ({nord['art']})")
    pruefe(nord.get("nachbar_egrid") == "CH000000000002",
           f"Nord: Nachbar-EGRID als Beleg ({nord.get('nachbar_egrid')})")

    west = kanten[3]
    pruefe(west["art"] == kk.ART_STRASSE,
           f"West: nicht parzellierter Strassenraum ueber die Achse ({west['art']})")
    pruefe(west.get("abstand_zur_achse_m") is not None,
           f"West: der gemessene Achsabstand ist ausgewiesen ({west.get('abstand_zur_achse_m')})")

    pruefe(r["statistik"][kk.ART_STRASSE] == 2, f"Statistik: 2 Strassenkanten ({r['statistik'][kk.ART_STRASSE]})")
    pruefe(r["statistik"][kk.ART_NACHBARPARZELLE] == 1, "Statistik: 1 Nachbarkante")
    pruefe(r["vollstaendig"] is False, "unvollstaendig, solange eine Kante unbestimmt ist")
    pruefe(any("manuelle Pruefung" in h for h in r["hinweise"]),
           "Hinweis benennt die nicht zuordenbare Kante")
    pruefe(r["statistik"]["strassenparzellen_im_umfeld"] == 1,
           f"1 Strassenparzelle im Umfeld erkannt ({r['statistik']['strassenparzellen_im_umfeld']})")


def test_kurze_kante_wird_ausgewiesen() -> None:
    print("=== Kurze Kante: nicht klassifiziert, aber sichtbar ===")
    # Quadrat mit abgeschraegter Ecke von 1.4 m Laenge.
    ring = [p(1, 0), p(20, 0), p(20, 20), p(0, 20), p(0, 1)]
    original = _mit_identify_double()
    try:
        r = kk.klassifiziere_kanten(ring, OX + 10, OY + 10, eigenes_egrid=EIGEN_EGRID)
    finally:
        kk._identify = original

    kurze = [k for k in r["kanten"] if not k["relevant"]]
    pruefe(len(kurze) == 1, f"genau eine Kante unter der Schwelle ({len(kurze)})")
    pruefe(kurze[0]["art"] == kk.ART_NICHT_RELEVANT, "kurze Kante ist als nicht_relevant markiert")
    pruefe(len(r["kanten"]) == len(ring),
           f"trotzdem sind alle {len(ring)} Kanten aufgefuehrt ({len(r['kanten'])})")
    pruefe(r["statistik"]["kanten_relevant"] == len(ring) - 1, "Statistik zaehlt nur die massgebenden Kanten")


def test_fehlerfaelle() -> None:
    print("=== Fehlerfaelle: entartete Eingaben ===")
    for eingabe, beschreibung in [([], "leere Geometrie"), ([p(0, 0), p(1, 1)], "nur zwei Stuetzpunkte")]:
        geworfen = None
        try:
            kk.klassifiziere_kanten(eingabe, OX, OY)
        except kk.KantenklassifikationError as exc:
            geworfen = exc
        pruefe(geworfen is not None, f"{beschreibung} wird sauber abgelehnt")


# ---------------------------------------------------------------------------
# 3. Abstandszuordnung -- der heikelste Teil
# ---------------------------------------------------------------------------

def _klassifikation(arten: list[str]) -> dict:
    return {"kanten": [
        {"nr": i, "laenge_m": 20.0, "relevant": True, "art": art,
         "begruendung": f"konstruiert: {art}", "nachbar_egrid": None,
         "nachbar_nummer": None, "strassenname": None, "abstand_zur_achse_m": None}
        for i, art in enumerate(arten)
    ]}


ZONE_VOLLSTAENDIG = {
    "zonenbezeichnung": "W2",
    "grenzabstand_klein_m": {"wert": 4.0, "confidence": "hoch"},
    "grenzabstand_gross_m": {"wert": 6.0, "confidence": "hoch"},
    "strassenabstand_m": {"wert": 3.6, "confidence": "hoch"},
}


def test_abstandszuordnung() -> None:
    print("=== Abstandszuordnung je Kantenart ===")
    arten = [kk.ART_STRASSE, kk.ART_NACHBARPARZELLE, kk.ART_NACHBARPARZELLE, kk.ART_NACHBARPARZELLE]
    abstaende, protokoll, offene = _kantenabstaende_aus_klassifikation(
        ZONE_VOLLSTAENDIG, _klassifikation(arten), 4
    )
    pruefe(abstaende == [3.6, 6.0, 6.0, 6.0], f"Strasse 3.6 m, Nachbarn 6.0 m ({abstaende})")
    pruefe(protokoll[0]["abstand_feld"] == "strassenabstand_m",
           "Strassenkante verweist auf strassenabstand_m")
    pruefe(protokoll[1]["abstand_feld"] == "grenzabstand_gross_m",
           "Nachbarkante verweist auf grenzabstand_gross_m")
    pruefe(offene == [], f"keine offenen Punkte ({offene})")

    # Der entscheidende Fall: Strassenkante ohne Strassenabstand.
    zone_ohne = {**ZONE_VOLLSTAENDIG, "strassenabstand_m": {"wert": None, "confidence": "nicht_bestimmbar"}}
    abstaende, protokoll, offene = _kantenabstaende_aus_klassifikation(zone_ohne, _klassifikation(arten), 4)
    pruefe(abstaende is None, "ohne Strassenabstand wird NICHT kantenweise gerechnet")
    pruefe(protokoll[0]["abstand_m"] is None, "die Strassenkante bekommt keinen Wert")
    pruefe(protokoll[0]["abstand_m"] not in (4.0, 6.0),
           "der Grenzabstand wird NICHT als Ersatz-Strassenabstand eingesetzt")
    pruefe(any("Strassenabstand" in s for s in offene), f"der offene Punkt ist benannt ({offene})")
    pruefe("rechtlich nicht" in (protokoll[0]["unsicherheit"] or ""),
           "die Unsicherheit begruendet, warum kein Ersatzwert gilt")

    # Unbestimmte Kante blockiert die kantenweise Rechnung ebenfalls.
    abstaende, protokoll, offene = _kantenabstaende_aus_klassifikation(
        ZONE_VOLLSTAENDIG,
        _klassifikation([kk.ART_STRASSE, kk.ART_UNBESTIMMT, kk.ART_NACHBARPARZELLE, kk.ART_NACHBARPARZELLE]),
        4,
    )
    pruefe(abstaende is None, "eine unbestimmte Kante verhindert die kantenweise Rechnung")
    pruefe(protokoll[1]["abstand_m"] is None, "die unbestimmte Kante bekommt keinen Wert")
    pruefe(any("unbestimmt" in s for s in offene), f"auch das ist benannt ({offene})")

    # Fehlt der grosse Grenzabstand, greift der kleine -- mit Vermerk.
    zone_klein = {**ZONE_VOLLSTAENDIG, "grenzabstand_gross_m": {"wert": None, "confidence": "nicht_bestimmbar"}}
    abstaende, protokoll, _ = _kantenabstaende_aus_klassifikation(zone_klein, _klassifikation(arten), 4)
    pruefe(abstaende == [3.6, 4.0, 4.0, 4.0], f"ersatzweise der kleine Grenzabstand ({abstaende})")
    pruefe("gross_m fehlt" in (protokoll[1]["unsicherheit"] or ""), "der Ersatz ist vermerkt")

    # Vorbehalt an der Kennzahl selbst (z.B. AG: Strassenabstand nach
    # Strassenklasse gestaffelt) -- muss an jeder Strassenkante erscheinen.
    zone_vorbehalt = {
        **ZONE_VOLLSTAENDIG,
        "strassenabstand_m": {
            "wert": 4.0, "confidence": "mittel",
            "unklarheit": "Richtet sich nach kantonalem Baugesetz (Kantonsstrasse 6 m, Gemeindestrasse 4 m).",
            "bedingungen": [],
        },
    }
    abstaende, protokoll, _ = _kantenabstaende_aus_klassifikation(zone_vorbehalt, _klassifikation(arten), 4)
    pruefe(abstaende == [4.0, 6.0, 6.0, 6.0], f"der belegte Wert wird verwendet ({abstaende})")
    pruefe("Confidence 'mittel'" in (protokoll[0]["unsicherheit"] or ""),
           "die Confidence steht an der Strassenkante")
    pruefe("Kantonsstrasse" in (protokoll[0]["unsicherheit"] or ""),
           "die Unklarheit der Kennzahl steht an der Strassenkante")
    pruefe(protokoll[1]["unsicherheit"] is None, "Nachbarkanten tragen den Vorbehalt nicht")

    # Baulinie auf der Parzelle: der Strassenabstand bleibt stehen, der
    # Vorbehalt wird aber sichtbar -- eine Baulinie kann strenger sein.
    abstaende, protokoll, _ = _kantenabstaende_aus_klassifikation(
        ZONE_VOLLSTAENDIG, _klassifikation(arten), 4, baulinien_gefunden=2
    )
    pruefe(abstaende == [3.6, 6.0, 6.0, 6.0], "Baulinie aendert den Wert nicht (keine Scheingenauigkeit nach unten)")
    pruefe("Baulinie" in (protokoll[0]["unsicherheit"] or ""),
           "Strassenkante traegt den Baulinien-Vorbehalt")
    pruefe(protokoll[1]["unsicherheit"] is None, "Nachbarkanten sind davon nicht betroffen")

    # Kantenzahl passt nicht zur Geometrie -> Fehler statt stiller Fehlzuordnung.
    geworfen = None
    try:
        _kantenabstaende_aus_klassifikation(ZONE_VOLLSTAENDIG, _klassifikation(arten), 7)
    except G1VerdrahtungError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "abweichende Kantenzahl wird abgelehnt")


# ---------------------------------------------------------------------------
# 4. G1-Verdrahtung: Modus, Kontrollbandbreite, Plausibilitaet
# ---------------------------------------------------------------------------

def _modul1_double() -> dict:
    return {
        "kataster": {"parzellengeometrie": EIGEN_RING, "flaeche_m2": 400.0, "egrid": EIGEN_EGRID},
        "restriktionsgeometrie": {},
    }


def test_g1_modus() -> None:
    print("=== G1: Modus kantenklassifikation und Kontrollbandbreite ===")
    zone = {**ZONE_VOLLSTAENDIG, "vollgeschosse_max": {"wert": 2}, "ausnuetzungsziffer_az": {"wert": 0.5}}
    klass = _klassifikation([kk.ART_STRASSE, kk.ART_NACHBARPARZELLE, kk.ART_NACHBARPARZELLE, kk.ART_NACHBARPARZELLE])

    r = berechne_g1_fuer_fall(_modul1_double(), zone, kantenklassifikation=klass)
    pruefe(r["modus"] == "kantenklassifikation", f"Modus ist kantenklassifikation ({r['modus']})")
    pruefe("kontrolle_bandbreite" in r, "die Bandbreite steht als Kontrolle daneben")
    pruefe(set(r["kontrolle_bandbreite"]) == {"alle_kanten_klein", "alle_kanten_gross"},
           f"beide Kontrollszenarien vorhanden ({sorted(r['kontrolle_bandbreite'])})")
    pruefe(len(r.get("kantenprotokoll") or []) == 4, "Kantenprotokoll ist Teil des Ergebnisses")

    flaeche = r["ergebnis"]["baubereich_m2"]
    gross = r["kontrolle_bandbreite"]["alle_kanten_gross"]["baubereich_m2"]
    klein = r["kontrolle_bandbreite"]["alle_kanten_klein"]["baubereich_m2"]
    pruefe(gross <= flaeche <= klein,
           f"klassifizierter Baubereich liegt in der Bandbreite ({gross:.1f} <= {flaeche:.1f} <= {klein:.1f})")

    # Ohne Strassenabstand: zurueck zur Bandbreite, mit benanntem Grund.
    zone_ohne = {**zone, "strassenabstand_m": {"wert": None, "confidence": "nicht_bestimmbar"}}
    r2 = berechne_g1_fuer_fall(_modul1_double(), zone_ohne, kantenklassifikation=klass)
    pruefe(r2["modus"] == "bandbreite_grenzabstand_kante_nicht_differenziert",
           f"ohne Strassenabstand bleibt es bei der Bandbreite ({r2['modus']})")
    pruefe(bool(r2.get("kantenzuordnung_offen")), "der Grund ist im Ergebnis benannt")
    pruefe(len(r2.get("kantenprotokoll") or []) == 4, "das Kantenprotokoll bleibt trotzdem erhalten")

    # Ohne Klassifikation: unveraendertes Verhalten (Regression).
    r3 = berechne_g1_fuer_fall(_modul1_double(), zone)
    pruefe(r3["modus"] == "bandbreite_grenzabstand_kante_nicht_differenziert",
           f"ohne Klassifikation wie bisher ({r3['modus']})")
    pruefe("kantenprotokoll" not in r3, "ohne Klassifikation entsteht kein Kantenprotokoll")


def test_quellen_je_kante() -> None:
    print("=== Quellennachweis je Kante ===")
    original = _mit_identify_double()
    try:
        klass = kk.klassifiziere_kanten(EIGEN_RING, OX + 10, OY + 10, eigenes_egrid=EIGEN_EGRID)
    finally:
        kk._identify = original

    quellen = kk.quellen_fuer_kanten(klass)
    pruefe(len(quellen) == 4, f"eine Quelle je massgebender Kante ({len(quellen)})")
    pruefe(all(q.zitat for q in quellen), "jede Quelle traegt die Begruendung als Zitat")
    pruefe(all(kk.LAYER_CADASTRE_GEOM in q.quelle_bezeichnung for q in quellen),
           "jede Quelle nennt den verwendeten Layer")
    unbestimmt = [q for q in quellen if q.wert == kk.ART_UNBESTIMMT]
    pruefe(len(unbestimmt) == 1 and unbestimmt[0].confidence == "nicht_bestimmbar",
           "die unbestimmte Kante ist als nicht_bestimmbar gefuehrt")


# ---------------------------------------------------------------------------
# 5. Modul-2-Schema: strassenabstand_m
# ---------------------------------------------------------------------------

def test_modul2_schema() -> None:
    print("=== Modul 2: strassenabstand_m im Schema und im Prompt ===")
    pruefe("strassenabstand_m" in m2._ZONE_KENNZAHL_FELDER, "Feld ist in _ZONE_KENNZAHL_FELDER")
    pruefe("strassenabstand_m" in m2._ZONE_SCHEMA["properties"], "Feld ist im JSON-Schema")
    pruefe("strassenabstand_m" in m2._ZONE_SCHEMA["required"], "Feld ist verpflichtend")
    pruefe(m2._ZONE_SCHEMA["properties"]["strassenabstand_m"] is m2._KENNZAHL_SCHEMA,
           "Feld nutzt dasselbe Kennzahl-Schema wie alle anderen Werte")
    prompt = m2.SYSTEM_PROMPT
    pruefe("strassenabstand_m" in prompt, "Prompt benennt das Feld")
    pruefe("NIEMALS" in prompt and "Grenzabstand ab" in prompt,
           "Prompt verbietet die Ableitung aus dem Grenzabstand ausdruecklich")
    pruefe("nicht_bestimmbar" in prompt, "Prompt verlangt nicht_bestimmbar statt eines Schaetzwerts")


def main() -> None:
    test_aussenpunkt()
    test_vier_faelle()
    test_kurze_kante_wird_ausgewiesen()
    test_fehlerfaelle()
    test_abstandszuordnung()
    test_g1_modus()
    test_quellen_je_kante()
    test_modul2_schema()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE KANTENKLASSIFIKATIONS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

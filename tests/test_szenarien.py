"""
Regressionstests fuer Stufe 4: Entwicklungsszenarien und Bestandsermittlung.

Vollstaendig OFFLINE -- konstruierte G1-Ergebnisse und MapServer-Antworten.

Geprueft wird, was fachlich schiefgehen kann:

  * Der Bestand muss das WOHNGEBAEUDE finden, nicht die Garage. Genau das ging
    bisher schief: get_gwr_data() nahm results[0] einer Toleranzabfrage.
  * Ein Anbau darf nicht "moeglich" heissen, wenn die Ausnuetzung
    ausgeschoepft ist -- Platz auf der Parzelle genuegt nicht.
  * Eine Aufstockung muss am Vergleich Bestand gegen zulaessig scheitern,
    wenn die Geschosszahl erreicht ist.
  * Dachausbau/Attika darf NICHT ueber die Vollgeschoss-Logik beantwortet
    werden -- ohne strukturierte Regel bleibt es nicht_bestimmbar.
  * Ersatzneubau muss theoretisch zulaessig und geometrisch umsetzbar
    auseinanderhalten und das limitierende benennen.
  * Ein freistehender Zusatzbau braucht den Gebaeudeabstand, ein Anbau nicht.
  * Schmale Restflaechen sind keine Bauplaetze.

CLI: python -m tests.test_szenarien
"""

from __future__ import annotations

import sys

from potenzial_engine import szenarien as sz
from potenzial_engine.bestand import werte_bestand_aus
from potenzial_engine.flaechenmodell import WohnungstypVorgabe

FEHLER: list[str] = []

OX, OY = 2600000.0, 1200000.0


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def p(x: float, y: float) -> list[float]:
    return [OX + x, OY + y]


def rechteck(x0, y0, x1, y1) -> list[list[float]]:
    return [p(x0, y0), p(x1, y0), p(x1, y1), p(x0, y1), p(x0, y0)]


# Parzelle 40 x 30 m = 1200 m2; Baubereich 4 m eingerueckt = 32 x 22 = 704 m2
PARZELLE = rechteck(0, 0, 40, 30)
BAUBEREICH = rechteck(4, 4, 36, 26)
# Bestand: 12 x 10 m = 120 m2, im Westteil
BESTAND_GRUNDRISS = rechteck(5, 8, 17, 18)


def g1(**felder):
    basis = {
        "parzellenflaeche_m2": 1200.0,
        "anrechenbare_landflaeche_m2": 1200.0,
        "baubereich_koordinaten": [BAUBEREICH],
        "baubereich_m2": 704.0,
        "fussabdruck_m2": 704.0,
        "fussabdruck_limitiert_durch": "geometrie",
        "fussabdruck_kandidaten": {"geometrie": 704.0},
        "geschosszahl": 3,
        "geschosszahl_limitiert_durch": "vollgeschosse",
        "geschosszahl_kandidaten": {"vollgeschosse": 3},
        "geschossflaeche_m2": 960.0,
        "geschossflaeche_limitiert_durch": "ausnuetzung_az",
        "geschossflaeche_kandidaten": {"fussabdruck_x_geschosse": 2112.0, "ausnuetzung_az": 960.0},
    }
    basis.update(felder)
    return basis


def gwr_punkt(x, y, **attrs):
    return {"geometry": {"type": "Point", "coordinates": p(x, y)}, "properties": attrs}


def grundriss_treffer(ring):
    return {"geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {}}


def bestand_double(geschosse=2, mit_garage=True):
    """Wohnhaus plus Garage -- die Konstellation, an der results[0] scheiterte."""
    gwr = [
        gwr_punkt(11, 13, egid="524242", strname_deinr="Musterweg 4", gkat=1020,
                  gastw=geschosse, garea=110, gbauj=1918),
    ]
    if mit_garage:
        # Die Garage liegt NAEHER am Abfragepunkt -- genau so entstand der Fehler.
        gwr.insert(0, gwr_punkt(20, 5, egid="263024777", strname_deinr="Musterweg 4.1",
                                gkat=1060, garea=9))
    grundrisse = [grundriss_treffer(BESTAND_GRUNDRISS)]
    return werte_bestand_aus(gwr, grundrisse, PARZELLE)


MIX = [
    WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.2),
    WohnungstypVorgabe("3.5 Zi", 88.0, anteil=0.5),
    WohnungstypVorgabe("4.5 Zi", 112.0, anteil=0.3),
]


# ---------------------------------------------------------------------------
# 1. Bestand
# ---------------------------------------------------------------------------

def test_bestand() -> None:
    print("=== Bestand: das Wohnhaus, nicht die Garage ===")
    b = bestand_double()
    haupt = b["hauptgebaeude"]
    pruefe(b["gefunden"] is True, "Bestand gefunden")
    pruefe(haupt["egid"] == "524242", f"Hauptgebaeude ist das Wohnhaus ({haupt['egid']})")
    pruefe(haupt["geschosse"] == 2, f"2 Geschosse aus dem GWR ({haupt['geschosse']})")
    pruefe(haupt["baujahr"] == 1918, "Baujahr 1918 uebernommen")
    pruefe(haupt["wohnnutzung"] is True, "als Wohnnutzung erkannt")
    pruefe(haupt["grundriss_flaeche_m2"] == 120.0, f"Grundriss 120 m2 ({haupt['grundriss_flaeche_m2']})")
    pruefe(b["anzahl_gebaeude"] == 2, f"Garage separat gefuehrt ({b['anzahl_gebaeude']} Gebaeude)")
    garage = next(g for g in b["gebaeude"] if g["egid"] == "263024777")
    pruefe(garage["wohnnutzung"] is False, "die Garage ist als Nicht-Wohnnutzung markiert")
    pruefe(garage["ist_hauptgebaeude"] is False, "und NICHT das Hauptgebaeude")
    pruefe(b["ueberbauungsgrad_ist"] == 0.1, f"Ueberbauungsgrad 120/1200 = 0.1 ({b['ueberbauungsgrad_ist']})")

    leer = werte_bestand_aus([], [], PARZELLE)
    pruefe(leer["gefunden"] is False, "unbebaute Parzelle wird als solche gemeldet")
    pruefe(any("unbebaut" in h for h in leer["hinweise"]), "mit ausdruecklichem Hinweis")

    ohne_geschosse = bestand_double(geschosse=None)
    pruefe(
        any("Aufstockungspruefung" in h for h in ohne_geschosse["hinweise"]),
        "fehlende Geschosszahl wird als Folge fuer die Aufstockung benannt",
    )
    print()


# ---------------------------------------------------------------------------
# 2. Ausnuetzungsbudget
# ---------------------------------------------------------------------------

def test_budget() -> None:
    print("=== Ausnuetzungsbudget: zulaessig minus Bestand ===")
    b = sz.berechne_ausnuetzungsbudget(g1(), bestand_double())
    pruefe(b.zulaessig_gf_m2 == 960.0, "zulaessig 960 m2 aus G1")
    pruefe(b.bestand_gf_m2 == 240.0, f"Bestand 120 m2 x 2 Geschosse = 240 m2 ({b.bestand_gf_m2})")
    pruefe(b.verbleibend_gf_m2 == 720.0, f"verbleibend 720 m2 ({b.verbleibend_gf_m2})")
    pruefe("Naeherung" in (b.bestand_herkunft or ""), "die Bestands-GF ist als Naeherung gekennzeichnet")

    # Garage zaehlt nicht zur Geschossflaeche.
    pruefe(b.bestand_gf_m2 == 240.0, "die Garage geht NICHT in die Bestands-Geschossflaeche ein")

    knapp = sz.berechne_ausnuetzungsbudget(g1(geschossflaeche_m2=200.0), bestand_double())
    pruefe(knapp.verbleibend_gf_m2 == -40.0, f"negatives Budget wird ausgewiesen ({knapp.verbleibend_gf_m2})")
    pruefe(any("ausgeschoepft" in h for h in knapp.hinweise), "und als ausgeschoepft benannt")

    ohne = sz.berechne_ausnuetzungsbudget(g1(), bestand_double(geschosse=None))
    pruefe(ohne.bestand_gf_m2 is None, "ohne Geschosszahl keine Bestands-GF")
    pruefe(any("nicht bestimmbar" in h for h in ohne.hinweise), "mit benannter Ursache")
    print()


# ---------------------------------------------------------------------------
# 3. Anbau
# ---------------------------------------------------------------------------

def _szenarien(g1_ergebnis=None, bestand=None, **kw):
    return sz.berechne_szenarien(
        g1_ergebnis or g1(), bestand if bestand is not None else bestand_double(),
        zone={"zonenbezeichnung": "W3"}, wohnungsmix=MIX,
        wohnungsmix_begruendung="Testmix", **kw,
    )


def test_anbau() -> None:
    print("=== Anbau: Geometrie UND Ausnuetzung muessen beide reichen ===")
    r = _szenarien()
    a = r["szenarien"]["anbau"]
    pruefe(a["machbarkeit"] in (sz.MACHBARKEIT_MOEGLICH, sz.MACHBARKEIT_EINGESCHRAENKT),
           f"Anbau grundsaetzlich moeglich ({a['machbarkeit']})")
    pruefe(bool(a["baukoerper"]), "ein Baukoerper wurde bestimmt")
    koerper = a["baukoerper"][0]
    pruefe(koerper["flaeche_m2"] > 0, f"mit Flaeche ({koerper['flaeche_m2']} m2)")
    pruefe(koerper["max_laenge_m"] > 0 and koerper["max_breite_m"] > 0,
           f"und konkreten Maximalmassen ({koerper['max_laenge_m']} x {koerper['max_breite_m']} m)")
    pruefe(any(himmel in a["begruendung"] for himmel in sz._HIMMELSRICHTUNGEN),
           f"die Begruendung nennt die Himmelsrichtung ({a['begruendung'][:70]})")
    pruefe(koerper["hoehe_m"] is not None, f"der Baukoerper hat eine Hoehe ({koerper['hoehe_m']} m)")

    # Ausnuetzung ausgeschoepft -> trotz Platz nicht moeglich.
    eng = _szenarien(g1_ergebnis=g1(geschossflaeche_m2=200.0))
    a2 = eng["szenarien"]["anbau"]
    pruefe(a2["machbarkeit"] == sz.MACHBARKEIT_NICHT_MOEGLICH,
           f"ausgeschoepfte Ausnuetzung schliesst den Anbau aus ({a2['machbarkeit']})")
    pruefe("ausgeschoepft" in a2["begruendung"], "die Begruendung nennt die Ausnuetzung")
    pruefe(any(k["schwere"] == "ausschluss" for k in a2["konflikte"]), "als Ausschluss-Konflikt")
    pruefe("frei" in a2["begruendung"] or "Geometrisch" in a2["begruendung"],
           "und stellt klar, dass geometrisch Platz waere")

    # Ausnuetzung knapp -> begrenzt, aber moeglich.
    knapp = _szenarien(g1_ergebnis=g1(geschossflaeche_m2=300.0))
    a3 = knapp["szenarien"]["anbau"]
    pruefe(a3["machbarkeit"] == sz.MACHBARKEIT_EINGESCHRAENKT, "knappe Ausnuetzung: eingeschraenkt moeglich")
    pruefe(a3["geschossflaeche_m2"] == 60.0, f"begrenzt auf 300 - 240 = 60 m2 ({a3['geschossflaeche_m2']})")
    pruefe("Baurecht begrenzt" in (a3["geschossflaeche_herkunft"] or ""),
           "die Herkunft nennt das Baurecht als Schranke")

    # Ohne Bestand ist es kein Anbau.
    leer = _szenarien(bestand=werte_bestand_aus([], [], PARZELLE))
    pruefe(leer["szenarien"]["anbau"]["machbarkeit"] == sz.MACHBARKEIT_NICHT_MOEGLICH,
           "ohne Bestand kein Anbau")
    pruefe("Ersatzneubau" in leer["szenarien"]["anbau"]["begruendung"],
           "mit Verweis auf das passende Szenario")

    # Gebaeude ohne Grundriss ist etwas anderes als gar kein Gebaeude.
    # Live beobachtet an Wilen 18a: zwei GWR-Gebaeude, kein Grundriss in VEC25.
    ohne_grundriss = werte_bestand_aus(
        [gwr_punkt(11, 13, egid="1", gkat=1020, gastw=2, garea=110)], [], PARZELLE,
    )
    o = _szenarien(bestand=ohne_grundriss)["szenarien"]["anbau"]
    pruefe(o["machbarkeit"] == sz.MACHBARKEIT_NICHT_BESTIMMBAR,
           f"Gebaeude ohne Grundriss: nicht bestimmbar statt nicht moeglich ({o['machbarkeit']})")
    pruefe("Gebaeudegrundriss" in o["begruendung"],
           f"und die Begruendung nennt den fehlenden Grundriss statt 'kein Gebaeude' "
           f"({o['begruendung'][:80]})")
    pruefe("Kein Gebaeude auf der Parzelle" not in o["begruendung"],
           "die frueher irrefuehrende Meldung erscheint nicht mehr")
    print()


def test_schmale_restflaeche() -> None:
    print("=== Schmale Restflaeche ist kein Bauplatz ===")
    # Bestand fuellt den Baubereich bis auf einen 1.5 m breiten Streifen.
    schmal = rechteck(4, 4, 36, 24.5)
    b = werte_bestand_aus(
        [gwr_punkt(20, 14, egid="1", gkat=1020, gastw=2, garea=600)],
        [grundriss_treffer(schmal)], PARZELLE,
    )
    r = _szenarien(bestand=b)
    a = r["szenarien"]["anbau"]
    pruefe(a["machbarkeit"] == sz.MACHBARKEIT_NICHT_MOEGLICH,
           f"ein 1.5 m breiter Streifen ist kein Anbauplatz ({a['machbarkeit']})")
    pruefe(any("breit" in k["meldung"] for k in a["konflikte"]),
           "die Mindestbreite wird als Grund genannt")
    print()


# ---------------------------------------------------------------------------
# 4. Aufstockung und Dach
# ---------------------------------------------------------------------------

def test_aufstockung() -> None:
    print("=== Aufstockung: Bestand gegen zulaessig ===")
    r = _szenarien()
    a = r["szenarien"]["aufstockung"]
    pruefe(a["machbarkeit"] in (sz.MACHBARKEIT_MOEGLICH, sz.MACHBARKEIT_EINGESCHRAENKT),
           f"3 zulaessig, 2 im Bestand -> moeglich ({a['machbarkeit']})")
    pruefe(a["geschosse"] == 1, f"ein zusaetzliches Geschoss ({a['geschosse']})")
    pruefe(a["geschossflaeche_m2"] == 120.0, f"120 m2 Grundriss x 1 Geschoss ({a['geschossflaeche_m2']})")
    pruefe(a["hoehe_m"] == 9.0, f"Gesamthoehe 3 Geschosse x 3.0 m ({a['hoehe_m']})")
    pruefe(any("Tragfaehigkeit" in u for u in a["unsicherheiten"]),
           "die Statik wird ausdruecklich als ungeprueft benannt")

    # Der Fall aus der Produktspezifikation: Geschosszahl ausgeschoepft.
    voll = _szenarien(bestand=bestand_double(geschosse=3))
    a2 = voll["szenarien"]["aufstockung"]
    pruefe(a2["machbarkeit"] == sz.MACHBARKEIT_NICHT_MOEGLICH,
           f"3 zulaessig, 3 im Bestand -> nicht moeglich ({a2['machbarkeit']})")
    pruefe("ausgeschoepft" in a2["begruendung"], "mit der Geschosszahl als Grund")
    pruefe(any(k["art"] == "geschosszahl" for k in a2["konflikte"]), "als Geschosszahl-Konflikt")

    # Mit ausdruecklich zulaessiger Attika aendert sich die Beurteilung.
    mit_attika = _szenarien(bestand=bestand_double(geschosse=3), attika_zulaessig=True)
    a3 = mit_attika["szenarien"]["aufstockung"]
    pruefe(a3["machbarkeit"] == sz.MACHBARKEIT_EINGESCHRAENKT,
           f"mit zulaessiger Attika: eingeschraenkt statt ausgeschlossen ({a3['machbarkeit']})")
    pruefe("Attikageschoss" in a3["begruendung"], "und die Attika wird benannt")

    # Ohne Bestands-Geschosszahl ist es nicht entscheidbar.
    ohne = _szenarien(bestand=bestand_double(geschosse=None))
    a4 = ohne["szenarien"]["aufstockung"]
    pruefe(a4["machbarkeit"] == sz.MACHBARKEIT_NICHT_BESTIMMBAR,
           f"ohne Bestands-Geschosszahl nicht bestimmbar ({a4['machbarkeit']})")
    pruefe("manuelle pruefung" in a4["begruendung"].lower(),
           "mit der Aufforderung zur manuellen Pruefung")
    print()


def test_dachausbau() -> None:
    print("=== Dach/Attika: nicht ueber die Vollgeschoss-Logik ===")
    r = _szenarien()
    d = r["szenarien"]["dachausbau"]
    pruefe(d["machbarkeit"] == sz.MACHBARKEIT_NICHT_BESTIMMBAR,
           f"ohne strukturierte Dachregel nicht bestimmbar ({d['machbarkeit']})")
    pruefe("KEIN Ersatz" in d["begruendung"],
           "es wird ausdruecklich gesagt, dass die Vollgeschoss-Regel kein Ersatz ist")
    pruefe(any("Rueckversatz" in u for u in d["unsicherheiten"]),
           "und benannt, welche Angaben fehlen")

    mit = _szenarien(attika_zulaessig=True)
    d2 = mit["szenarien"]["dachausbau"]
    pruefe(d2["machbarkeit"] == sz.MACHBARKEIT_EINGESCHRAENKT,
           f"mit Vorgabe: eingeschraenkt moeglich ({d2['machbarkeit']})")
    pruefe(d2["geschossflaeche_m2"] is None,
           "aber ohne Flaechenangabe -- die haengt am Rueckversatz")

    nein = _szenarien(attika_zulaessig=False, dachgeschoss_zulaessig=False)
    pruefe(nein["szenarien"]["dachausbau"]["machbarkeit"] == sz.MACHBARKEIT_NICHT_MOEGLICH,
           "ausdrueckliches Nein wird uebernommen")
    print()


# ---------------------------------------------------------------------------
# 5. Ersatzneubau und Kombination
# ---------------------------------------------------------------------------

def test_ersatzneubau() -> None:
    print("=== Ersatzneubau: theoretisch zulaessig gegen geometrisch umsetzbar ===")
    r = _szenarien()
    e = r["szenarien"]["ersatzneubau"]
    pruefe(e["machbarkeit"] == sz.MACHBARKEIT_MOEGLICH, "Ersatzneubau moeglich")
    pruefe(e["geschossflaeche_m2"] == 960.0, "GF 960 m2 aus G1")
    pruefe("ausnuetzung_az" in (e["geschossflaeche_herkunft"] or ""), "limitierende Groesse benannt")
    pruefe(any(k["art"] == "ausnuetzung" for k in e["konflikte"]),
           "der Konflikt Geometrie gegen Ausnuetzung ist ausgewiesen")
    konflikt = next(k for k in e["konflikte"] if k["art"] == "ausnuetzung")
    pruefe("2112" in konflikt["meldung"] and "960" in konflikt["meldung"],
           f"mit beiden Zahlen ({konflikt['meldung'][:90]})")
    pruefe(any("abgebrochen" in u for u in e["unsicherheiten"]),
           "der noetige Abbruch wird benannt")

    # Umgekehrt: Geometrie ist die engere Schranke.
    eng = _szenarien(g1_ergebnis=g1(
        geschossflaeche_m2=300.0, geschossflaeche_limitiert_durch="fussabdruck_x_geschosse",
        geschossflaeche_kandidaten={"fussabdruck_x_geschosse": 300.0, "ausnuetzung_az": 960.0},
    ))
    e2 = eng["szenarien"]["ersatzneubau"]
    konflikt2 = next(k for k in e2["konflikte"] if k["art"] == "geometrie")
    pruefe("nicht unterzubringen" in konflikt2["meldung"],
           f"jetzt begrenzt die Geometrie ({konflikt2['meldung'][:90]})")
    print()


def test_ueberbaute_parzelle() -> None:
    """Realfall Uettligen: der Bestand belegt 713 m2, heute zulaessig sind 470 m2.
    Ein Ersatzneubau faellt dann KLEINER aus als das, was heute steht -- eine
    wirtschaftliche Aussage, die sichtbar sein muss."""
    print("=== Ueberbaute Parzelle: Ersatzneubau waere kleiner als der Bestand ===")
    eng = g1(geschossflaeche_m2=200.0)
    budget = sz.berechne_ausnuetzungsbudget(eng, bestand_double())
    pruefe(any("UEBERBAUT" in h for h in budget.hinweise),
           "das Budget weist die Ueberbauung ausdruecklich aus")
    pruefe(any("Besitzstandsgarantie" in h for h in budget.hinweise),
           "und nennt die Besitzstandsgarantie")

    r = _szenarien(g1_ergebnis=eng)
    e = r["szenarien"]["ersatzneubau"]
    pruefe(e["machbarkeit"] == sz.MACHBARKEIT_EINGESCHRAENKT,
           f"der Ersatzneubau ist damit nur eingeschraenkt sinnvoll ({e['machbarkeit']})")
    besitz = [k for k in e["konflikte"] if k["art"] == "besitzstand"]
    pruefe(len(besitz) == 1, "ein Besitzstand-Konflikt ist ausgewiesen")
    pruefe("KLEINER" in besitz[0]["meldung"], "mit der Aussage, dass der Neubau kleiner waere")
    pruefe("wirtschaftliche Entscheidung" in besitz[0]["meldung"],
           "und der Einordnung als wirtschaftliche, nicht baurechtliche Frage")

    # Normalfall: kein Besitzstand-Konflikt.
    normal = _szenarien()
    pruefe(not [k for k in normal["szenarien"]["ersatzneubau"]["konflikte"] if k["art"] == "besitzstand"],
           "bei genuegend Ausnuetzung erscheint der Konflikt nicht")
    print()


def test_bestand_plus_neubau() -> None:
    print("=== Bestand + Neubau: Gebaeudeabstand ist eine eigene Frage ===")
    r = _szenarien()
    k = r["szenarien"]["bestand_plus_neubau"]
    pruefe(k["machbarkeit"] in (sz.MACHBARKEIT_MOEGLICH, sz.MACHBARKEIT_EINGESCHRAENKT),
           f"grundsaetzlich moeglich ({k['machbarkeit']})")
    arten = {b["art"] for b in k["baukoerper"]}
    pruefe("bestand" in arten and "neubau" in arten,
           f"Bestand und Neubau sind beide als Baukoerper enthalten ({arten})")
    pruefe(any("Gebaeudeabstand" in u for u in k["unsicherheiten"]),
           "ohne Vorgabe wird KEIN Abstand angenommen und das ausgewiesen")

    mit_abstand = _szenarien(gebaeudeabstand_m=6.0)
    k2 = mit_abstand["szenarien"]["bestand_plus_neubau"]
    neubau = [b for b in k2["baukoerper"] if b["art"] == "neubau"]
    neubau_ohne = [b for b in k["baukoerper"] if b["art"] == "neubau"]
    flaeche_mit = sum(b["flaeche_m2"] for b in neubau)
    flaeche_ohne = sum(b["flaeche_m2"] for b in neubau_ohne)
    pruefe(flaeche_mit < flaeche_ohne,
           f"mit Gebaeudeabstand bleibt weniger Flaeche ({flaeche_mit} < {flaeche_ohne} m2)")
    pruefe(any(k["art"] == "gebaeudeabstand" for k in k2["konflikte"]),
           "der beruecksichtigte Abstand ist vermerkt")
    print()


# ---------------------------------------------------------------------------
# 6. Orchestrierung und Vergleich
# ---------------------------------------------------------------------------

def test_vergleich_und_grenzfaelle() -> None:
    print("=== Vergleich, Auswahl und Grenzfaelle ===")
    r = _szenarien()
    pruefe(len(r["szenarien"]) == len(sz.ALLE_SZENARIEN),
           f"alle {len(sz.ALLE_SZENARIEN)} Szenarien gerechnet ({len(r['szenarien'])})")
    pruefe(len(r["vergleich"]) == len(sz.ALLE_SZENARIEN), "eine Vergleichszeile je Szenario")
    machbarkeiten = [z["machbarkeit"] for z in r["vergleich"]]
    pruefe(machbarkeiten[0] == sz.MACHBARKEIT_MOEGLICH,
           f"die machbaren stehen oben ({machbarkeiten})")
    pruefe(machbarkeiten[-1] in (sz.MACHBARKEIT_NICHT_BESTIMMBAR, sz.MACHBARKEIT_NICHT_MOEGLICH),
           "und die nicht machbaren unten")
    pruefe(all("hoehe_m" in z for z in r["vergleich"]), "die Hoehe steht im Vergleich")

    nur_zwei = _szenarien(auswahl=["bestand", "ersatzneubau"])
    pruefe(set(nur_zwei["szenarien"]) == {"bestand", "ersatzneubau"}, "Auswahl wird beachtet")

    geworfen = None
    try:
        _szenarien(auswahl=["gibt_es_nicht"])
    except sz.SzenarioError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "ein unbekanntes Szenario wird abgelehnt")

    ohne_g1 = sz.berechne_szenarien(None, bestand_double(), zone=None)
    pruefe(ohne_g1["status"] == sz.MACHBARKEIT_NICHT_BESTIMMBAR, "ohne G1-Ergebnis nicht bestimmbar")
    pruefe("Bandbreiten-Rand" in ohne_g1["grund"], "mit der Bandbreite als benanntem Grund")
    pruefe(ohne_g1["szenarien"] == {}, "und ohne erfundene Szenarien")

    # Bestand bekommt bewusst KEINE Flaechenkaskade.
    b = r["szenarien"]["bestand"]
    pruefe(b["flaechen"] is None, "fuer den Bestand wird keine Neubau-Kaskade gerechnet")
    pruefe(any("NEUBAUTEN" in u for u in b["unsicherheiten"]), "mit ausdruecklicher Begruendung")
    pruefe(b["geschossflaeche_m2"] == 240.0, "die Bestands-GF steht trotzdem")
    print()


def test_baulinien() -> None:
    print("=== Baulinien werden als Konflikt ausgewiesen ===")
    ohne = _szenarien()
    mit = _szenarien(restriktionen={"baulinien_gefunden": [{"typ": "Strassenbaulinie"}]})
    for name in ("anbau", "ersatzneubau", "bestand_plus_neubau"):
        arten_ohne = {k["art"] for k in ohne["szenarien"][name]["konflikte"]}
        arten_mit = {k["art"] for k in mit["szenarien"][name]["konflikte"]}
        pruefe("baulinie" not in arten_ohne, f"{name}: ohne Baulinie kein Baulinien-Konflikt")
        pruefe("baulinie" in arten_mit, f"{name}: mit Baulinie erscheint der Konflikt")
    meldung = next(k["meldung"] for k in mit["szenarien"]["anbau"]["konflikte"] if k["art"] == "baulinie")
    pruefe("NICHT abgezogen" in meldung, "und stellt klar, dass sie im Baubereich fehlt")
    print()


def main() -> None:
    test_bestand()
    test_budget()
    test_anbau()
    test_schmale_restflaeche()
    test_aufstockung()
    test_dachausbau()
    test_ersatzneubau()
    test_ueberbaute_parzelle()
    test_bestand_plus_neubau()
    test_vergleich_und_grenzfaelle()
    test_baulinien()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE SZENARIEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

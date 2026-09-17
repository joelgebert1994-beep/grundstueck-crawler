"""
Bestand, Neubaugeometrie und zusaetzliches Potenzial sind drei Groessen.

Vollstaendig OFFLINE, mit der echten Geometrie des Falls, an dem der Fehler
sichtbar wurde: Buhofstrasse 55, 9424 Rheineck, Parzelle 160, 289.1 m2.

Was dort passiert ist
---------------------
Die Parzelle ist ein Rechteck von rund 16.0 x 18.2 m. Zwei Kanten grenzen an
eine Strasse (Abstand 3 m), die beiden anderen an Nachbarn. Die Verdrahtung
setzte auf JEDER Nachbarkante den grossen Grenzabstand (8 m) an -- und die
beiden Nachbarkanten liegen sich ueber die 16 m schmale Seite gegenueber.

    16.0 - 8.0 - 8.0 = 0.0

Die Huelle fiel auf 0.69 m2 zusammen, daraus wurde "Geschossflaeche 1.38 m2"
und im Dossier "Potenzial 1 m2". Rechnerisch richtig, als Aussage ueber das
Grundstueck unbrauchbar -- auf der Parzelle steht ein dreigeschossiges
Wohnhaus.

Die Regel, die daraus folgt
---------------------------
Bestimmen die Eingangsdaten die Gebaeudegeometrie nicht eindeutig, darf die
Engine ueber eine versteckte Annahme keine exakte Potenzialzahl erzeugen.
Der grosse Grenzabstand gilt in aller Regel fuer EINE Seite; welche, haengt
am noch nicht entworfenen Gebaeude. "Gross auf allen Seiten" ist deshalb
keine Schaetzung, sondern die strengste denkbare Anordnung -- eine
Untergrenze.

CLI: python -m tests.test_bestandstrennung
"""

from __future__ import annotations

import sys

from potenzial_engine.baubereich import vergleiche_bestand_mit_baubereich
from potenzial_engine.g1_verdrahtung import (
    berechne_g1_fuer_fall,
    nachbarabstand_unentscheidbar,
)
from potenzial_engine.pipeline import _bestand_und_neubaugeometrie

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


# --- Der echte Fall, Zahlen unveraendert aus der Analyse --------------------

RHEINECK_RING = [
    [2761214.8, 1259841.5], [2761230.6, 1259842.8],
    [2761231.8, 1259824.6], [2761215.8, 1259823.5],
]
RHEINECK_GRUNDRISS = [
    [2761214.3, 1259844.6], [2761228.9, 1259844.6],
    [2761228.9, 1259827.6], [2761214.3, 1259827.6],
]
RHEINECK_KANTEN = {
    "kanten": [
        {"nr": 0, "art": "strasse", "relevant": True},
        {"nr": 1, "art": "nachbarparzelle", "relevant": True},
        {"nr": 2, "art": "strasse", "relevant": True},
        {"nr": 3, "art": "nachbarparzelle", "relevant": True},
    ],
    "statistik": {}, "hinweise": [],
}
RHEINECK_ZONE = {
    "zonenbezeichnung": "Wohnzone W2",
    "grenzabstand_klein_m": {"wert": 4.0, "confidence": "hoch"},
    "grenzabstand_gross_m": {"wert": 8.0, "confidence": "hoch"},
    "strassenabstand_m": {"wert": 3.0, "confidence": "mittel"},
    "vollgeschosse_max": {"wert": 2, "confidence": "hoch"},
    "gebaeudehoehe_m": {"wert": 7.0, "confidence": "hoch"},
    "ausnuetzungsziffer_az": {"wert": 0.45, "confidence": "hoch"},
}


def rheineck_modul1() -> dict:
    return {
        "kataster": {"parzellengeometrie": RHEINECK_RING, "flaeche_m2": 289.1,
                     "parzellennummer": "160", "found": True},
        "kantenklassifikation": RHEINECK_KANTEN,
        "restriktionsgeometrie": {},
        "bestand": {
            "gefunden": True,
            "anzahl_gebaeude": 1,
            "bebaute_flaeche_gwr_m2": 118.0,
            "bebaute_flaeche_grundriss_m2": 248.2,
            "gebaeude": [{
                "egid": "1088316", "adresse": "Buhofstrasse 55",
                "geschosse": 3, "grundflaeche_gwr_m2": 118.0,
                "grundriss": RHEINECK_GRUNDRISS, "grundriss_flaeche_m2": 248.2,
                "ist_hauptgebaeude": True,
            }],
        },
    }


# ---------------------------------------------------------------------------


def test_unentscheidbarkeit() -> None:
    print("=== Wann die Abstandszuordnung offen ist ===")
    offen = nachbarabstand_unentscheidbar(RHEINECK_ZONE, RHEINECK_KANTEN)
    pruefe(offen is not None, "klein 4 m, gross 8 m und Nachbarkanten: offen")
    pruefe(offen["kanten"] == [1, 3],
           f"genau die beiden Nachbarkanten betroffen ({offen['kanten']})")

    gleich = dict(RHEINECK_ZONE, grenzabstand_gross_m={"wert": 4.0})
    pruefe(nachbarabstand_unentscheidbar(gleich, RHEINECK_KANTEN) is None,
           "sind beide Abstaende gleich, gibt es nichts zu entscheiden")

    ohne_gross = dict(RHEINECK_ZONE, grenzabstand_gross_m=None)
    pruefe(nachbarabstand_unentscheidbar(ohne_gross, RHEINECK_KANTEN) is None,
           "fehlt der grosse Abstand, bleibt es beim Einzelwert")

    nur_strasse = {"kanten": [{"nr": 0, "art": "strasse", "relevant": True}]}
    pruefe(nachbarabstand_unentscheidbar(RHEINECK_ZONE, nur_strasse) is None,
           "ohne Nachbarkante ebenso -- Strassenabstaende sind eindeutig zugeordnet")
    print()


def test_kein_scheinpraeziser_einzelwert() -> None:
    """Der Kern: aus 0.69 m2 darf keine Potenzialzahl werden."""
    print("=== Kein Einzelwert aus einer offenen Zuordnung ===")
    g1 = berechne_g1_fuer_fall(rheineck_modul1(), RHEINECK_ZONE,
                               kantenklassifikation=RHEINECK_KANTEN)

    pruefe(g1["modus"] == "bandbreite_nachbarabstand_nicht_zuordenbar",
           f"Bandbreiten-Modus statt Einzelergebnis ({g1['modus']})")
    pruefe("ergebnis" not in g1,
           "KEIN Feld 'ergebnis' -- die Flaechenkaskade liest genau das und "
           "meldet ohne es 'nicht bestimmbar'")
    pruefe(g1.get("baubereich_belastbar") is False, "ausdruecklich als nicht belastbar markiert")
    pruefe("nicht eindeutig bestimmbar" in (g1.get("grund_nicht_belastbar") or ""),
           "mit Begruendung im Klartext")

    # Und die Zahl, die frueher als Potenzial dastand, darf nirgends allein stehen.
    pruefe(g1.get("baubereich_m2") is None and g1.get("geschossflaeche_m2") is None,
           "0.69 / 1.38 erscheinen nicht als eigenstaendige Kennzahl")
    print()


def test_bandbreite_und_az() -> None:
    print("=== Bandbreite als Sensitivitaet, AZ getrennt davon ===")
    g1 = berechne_g1_fuer_fall(rheineck_modul1(), RHEINECK_ZONE,
                               kantenklassifikation=RHEINECK_KANTEN)
    b = g1["bandbreite"]

    unten, oben = b["baubereich_m2"]
    pruefe(abs(unten - 0.69) < 0.05, f"Untergrenze 0.69 m2 (gross auf beiden Seiten): {unten}")
    pruefe(abs(oben - 96.4) < 0.5, f"Obergrenze 96.4 m2 (klein auf beiden Seiten): {oben}")
    pruefe(unten < oben, "und die Untergrenze liegt unter der Obergrenze")
    pruefe("nicht ein baurechtlich bestimmtes Potenzial" in b["bedeutung"],
           "die Bandbreite wird als Sensitivitaet gekennzeichnet, nicht als Potenzial")

    pruefe(abs(g1["gf_nach_ausnuetzungsziffer_m2"] - 130.1) < 0.2,
           f"die Ausnuetzungsziffer bleibt rechenbar: {g1.get('gf_nach_ausnuetzungsziffer_m2')} m2")
    pruefe("0.45" in (g1.get("gf_nach_ausnuetzungsziffer_rechnung") or ""),
           "mit nachvollziehbarer Rechnung")
    pruefe("Theoretischer Wert" in (g1.get("gf_nach_ausnuetzungsziffer_bedeutung") or ""),
           "und ausdruecklich als theoretischer Wert der Zonengrundlage benannt")
    pruefe("zulaessige_geschossflaeche_az_m2" not in g1
           and "zulaessige_gesamtentwicklung_gf_m2" not in g1,
           "der Begriff 'zulaessige Gesamtentwicklung' kommt nicht mehr vor -- er "
           "behauptete mehr, als die Ausnuetzungsziffer hergibt")

    entartet = g1.get("untergrenze_entartet")
    pruefe(entartet is not None, "die zusammengefallene Untergrenze wird benannt")
    pruefe("strengsten Annahme" in (entartet or {}).get("erklaerung", ""),
           "und als Folge der strengsten Annahme erklaert, nicht als Befund")

    # Die Strassenkanten duerfen NICHT mitvariiert werden.
    pruefe(g1.get("betroffene_nachbarkanten") == [1, 3],
           "variiert werden nur die Nachbarkanten -- die Strassenzuordnung ist eindeutig")
    print()


def test_drei_ebenen_getrennt() -> None:
    print("=== Bestand, Neubaugeometrie und Zusatzpotenzial ===")
    m1 = rheineck_modul1()
    g1 = berechne_g1_fuer_fall(m1, RHEINECK_ZONE, kantenklassifikation=RHEINECK_KANTEN)
    d = _bestand_und_neubaugeometrie(m1, g1)

    bestand = d["bestand"]
    pruefe(bestand["grundflaeche"]["wert_m2"] == 118.0
           and bestand["grundflaeche"]["status"] == "gemessen",
           "Bestandsgrundflaeche 118 m2, als gemessener Registerwert gefuehrt")
    pruefe(bestand["geschosse"]["wert"] == [3]
           and bestand["geschosse"]["status"] == "gemessen",
           "Geschosszahl 3, ebenfalls aus dem Register")
    pruefe(bestand["grundriss_kataster"]["wert_m2"] == 248.2,
           "der abweichende Katasterwert steht daneben, nicht statt dessen")

    gf = bestand["geschossflaeche_abgeleitet"]
    pruefe(gf["wert_m2"] == 354.0 and gf["status"] == "abgeleitet",
           f"die Bestands-GF ist ABGELEITET, nicht gemessen ({gf['status']})")
    pruefe("NAEHERUNGSWERT" in gf["herleitung"] and "118 m2 x 3" in gf["rechnung"],
           "Herleitung und Rechnung stehen dabei")
    pruefe("geschossflaeche_m2" not in bestand,
           "es gibt kein Feld, das die Naeherung wie einen gemessenen Wert aussehen laesst")

    neubau = d["neubau_nach_heutiger_geometrie"]
    pruefe(neubau["belastbar"] is False, "Neubaugeometrie: nicht belastbar")
    pruefe("VOLLSTAENDIG NEUEN" in neubau["bedeutung"],
           "und es steht dabei, dass es um einen NEUEN Baukoerper geht")
    pruefe("bandbreite_geschossflaeche_m2" in neubau,
           "die Bandbreite steht stattdessen da")
    pruefe(neubau.get("geschossflaeche_m2") is None,
           "aber KEINE einzelne Geschossflaeche")

    rahmen = d["heutiger_rechtsrahmen"]
    pruefe(abs(rahmen["gf_nach_ausnuetzungsziffer_m2"] - 130.1) < 0.2,
           "der heutige Rechtsrahmen nennt 130.1 m2 nach Ausnuetzungsziffer")
    pruefe("Theoretischer Wert" in rahmen["bedeutung"],
           "als theoretischer Wert, nicht als zulaessige Gesamtentwicklung")

    zusatz = d["zusaetzliches_potenzial"]
    pruefe(zusatz["status"] == "nicht_abschliessend_bestimmbar",
           f"zusaetzliches Potenzial: nicht abschliessend bestimmbar ({zusatz['status']})")
    pruefe("zusaetzliche_geschossflaeche_m2" not in zusatz,
           "KEINE Differenz aus theoretischem Zonenwert und genaehertem Bestand -- "
           "die -223.9 m2 waeren ein scheinbarer Rueckbaubefund")
    pruefe("getrennt vom theoretischen Neubauwert" in zusatz["grund"],
           "mit der Begruendung im Klartext")
    pruefe(any("GENAEHERT" in p for p in zusatz["offene_punkte"]),
           "die Naeherung der Bestands-GF steht als offener Punkt")
    pruefe(any("nicht belastbar bestimmbar" in p for p in zusatz["offene_punkte"]),
           "die offene Geometrie ebenso")

    # Die Verwechslung, um die es geht: Neubaugeometrie ist nicht der Bestand.
    pruefe(neubau.get("bandbreite_geschossflaeche_m2", [None])[0]
           != gf["wert_m2"],
           "Neubaugeometrie und Bestand sind getrennte Groessen")
    print()


def test_bestandessituation_ohne_rechtsfolge() -> None:
    print("=== Bestandessituation: Feststellung, keine Rechtsauskunft ===")
    m1 = rheineck_modul1()
    g1 = berechne_g1_fuer_fall(m1, RHEINECK_ZONE, kantenklassifikation=RHEINECK_KANTEN)
    situation = _bestand_und_neubaugeometrie(m1, g1)["bestandssituation"]

    pruefe(situation["vergleichbar"] is True, "der Vergleich ist geometrisch moeglich")
    pruefe(situation["anteil_ausserhalb"] > 0.5,
           f"der Bestand liegt groesstenteils ausserhalb der Huelle "
           f"({situation['anteil_ausserhalb']:.0%})")
    pruefe(situation["pruefen"] is True, "und wird zur Pruefung gestellt")

    hinweis = situation["hinweis"]
    pruefe("zu pruefen" in hinweis, "der Text stellt zur Pruefung")
    pruefe("Daraus folgt NICHT" in hinweis,
           "und schliesst ausdruecklich aus, dass nur die Neubaugeometrie zulaessig waere")
    # Keine juristische Behauptung.
    for verboten in ("geniesst Bestandesschutz", "ist rechtmaessig", "ist unzulaessig",
                     "muss abgebrochen"):
        pruefe(verboten not in hinweis, f"keine Rechtsbehauptung '{verboten}'")

    # Gegenprobe: ein Gebaeude innerhalb der Huelle loest keine Pruefung aus.
    innen = vergleiche_bestand_mit_baubereich(
        [[[0, 0], [5, 0], [5, 5], [0, 5]]],
        [[[-10, -10], [20, -10], [20, 20], [-10, 20]]])
    pruefe(innen["anteil_ausserhalb"] == 0.0,
           "ein Gebaeude ganz innerhalb der Huelle liegt zu 0 % ausserhalb")
    print()


def test_eindeutiger_fall_bleibt_einzelwert() -> None:
    """Die neue Regel darf brauchbare Faelle nicht kaputtmachen."""
    print("=== Wo die Zuordnung eindeutig ist, bleibt es beim Einzelwert ===")
    zone = dict(RHEINECK_ZONE, grenzabstand_gross_m={"wert": 4.0, "confidence": "hoch"})
    g1 = berechne_g1_fuer_fall(rheineck_modul1(), zone, kantenklassifikation=RHEINECK_KANTEN)
    pruefe(g1["modus"] == "kantenklassifikation",
           f"gleiche Abstaende: kantenweise gerechnet ({g1['modus']})")
    pruefe("ergebnis" in g1 and g1["ergebnis"].get("baubereich_m2", 0) > 50,
           f"mit einem belastbaren Baubereich ({g1.get('ergebnis', {}).get('baubereich_m2')} m2)")
    print()


def test_ohne_bestand_und_mit_klarer_geometrie() -> None:
    """Die Gegenprobe: wo nichts steht und die Geometrie eindeutig ist, gibt
    es sehr wohl eine Zahl. Die neue Zurueckhaltung darf nicht dazu fuehren,
    dass die Engine gar nichts mehr sagt."""
    print("=== Ohne Bestand und mit eindeutiger Geometrie: eine Zahl ===")
    m1 = rheineck_modul1()
    m1["bestand"] = {"gefunden": False, "gebaeude": [], "anzahl_gebaeude": 0}
    zone = dict(RHEINECK_ZONE, grenzabstand_gross_m={"wert": 4.0, "confidence": "hoch"})

    g1 = berechne_g1_fuer_fall(m1, zone, kantenklassifikation=RHEINECK_KANTEN)
    d = _bestand_und_neubaugeometrie(m1, g1)

    pruefe(d["neubau_nach_heutiger_geometrie"]["belastbar"] is True,
           "eindeutige Abstaende: die Neubaugeometrie ist belastbar")
    zusatz = d["zusaetzliches_potenzial"]
    pruefe(zusatz["status"] == "bestimmbar",
           f"und ohne Bestand ist das zusaetzliche Potenzial bestimmbar ({zusatz['status']})")
    pruefe(abs(zusatz["zusaetzliche_geschossflaeche_m2"] - 130.1) < 0.2,
           f"es entspricht dem Wert nach Ausnuetzungsziffer "
           f"({zusatz.get('zusaetzliche_geschossflaeche_m2')} m2)")
    pruefe("kein Gebaeude verzeichnet" in zusatz["rechnung"],
           "und die Rechnung sagt, warum nichts abzuziehen ist")

    pruefe(d["bestand"]["geschossflaeche_abgeleitet"]["status"] == "nicht_bestimmbar",
           "ohne Gebaeude gibt es auch keine abgeleitete Bestandsflaeche")
    print()


def main() -> None:
    test_unentscheidbarkeit()
    test_kein_scheinpraeziser_einzelwert()
    test_bandbreite_und_az()
    test_drei_ebenen_getrennt()
    test_bestandessituation_ohne_rechtsfolge()
    test_eindeutiger_fall_bleibt_einzelwert()
    test_ohne_bestand_und_mit_klarer_geometrie()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE TESTS ZUR BESTANDSTRENNUNG BESTANDEN")


if __name__ == "__main__":
    main()

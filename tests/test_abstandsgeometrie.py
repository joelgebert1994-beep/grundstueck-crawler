"""
Abstandsgeometrie: der Versatz selbst und die zulaessigen Anordnungen.

Diese Suite ist aus zwei echten Fehlern entstanden, die beide erst an
realen Parzellen sichtbar wurden.

FEHLER 1 -- der Versatz war nicht monoton.
Die frueher verwendete Mitre-Konstruktion stuelpte den versetzten Ring um,
sobald ein Abstand den Innenradius der Parzelle ueberschritt. `buffer(0)`
reparierte die Selbstueberschneidung zu einem gueltigen Polygon, und davon
blieb nach `intersection(parzelle)` eine Restflaeche mit positivem Inhalt
uebrig. Gemessen an Buhofstrasse 20, Rheineck:

    4 m -> 58.52 m2      7 m -> 38.21 m2   <-- waechst wieder
    5 m -> 18.28 m2      8 m -> 54.45 m2
    6 m -> 13.97 m2     10 m -> 62.94 m2

Folgen im Produkt: die "0.7 m2" an Buhofstrasse 55 waren der Ausklang
eines Kollapses, und an Buhofstrasse 20 lag die ausgewiesene Untergrenze
(78.95 m2) UEBER der Obergrenze (61.63 m2).

FEHLER 2 -- die Bandbreite enthielt eine unzulaessige Anordnung.
Ihre Untergrenze war "grosser Grenzabstand auf ALLEN Nachbarseiten". Die
Engine schrieb selbst dazu, das sei "strenger als jede zulaessige
Anordnung" -- die Regel lautet: der grosse Abstand gilt fuer EINE Seite.
Ein Rechenrand, den niemand bauen darf, stand damit als Potenzialgrenze
im Dossier.

Die Testfaelle folgen der mit dem Nutzer abgestimmten Liste A-G:

  A  Monotonie ueber 0-15 m: nie ein Wachstum nach einem Kollaps.
  B  Kein Phantom: nach dem Kollaps exakt 0, nicht eine Restflaeche.
  C  Buhofstrasse 55: nur zulaessige Anordnungen in der Bandbreite.
  D  Buhofstrasse 20: keine vertauschte Unter-/Obergrenze.
  E  Fuehren alle zulaessigen Anordnungen auf denselben Wert -> Einzelwert.
  F  Fuehren sie auf verschiedene Werte -> weiterhin Bandbreite.
  G  Bestehende korrekte Faelle bleiben unveraendert.

Vollstaendig OFFLINE. Die Parzellen liegen als Konturen in
tests/daten/parzellen_rheineck.json.

CLI: python -m tests.test_abstandsgeometrie
"""

from __future__ import annotations

import json
import pathlib
import sys

from shapely.geometry import Polygon

from potenzial_engine.baubereich import berechne_baubereich_polygon, berechne_potenzial
from potenzial_engine.g1_verdrahtung import berechne_g1_fuer_fall, zulaessige_anordnungen

FEHLER: list[str] = []

DATEN = pathlib.Path(__file__).with_name("daten") / "parzellen_rheineck.json"
PARZELLEN = {k: v for k, v in json.loads(DATEN.read_text(encoding="utf-8")).items()
             if not k.startswith("_")}


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def nahe(a: float, b: float, toleranz: float = 0.05) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= toleranz


def _ring(name: str) -> list[tuple[float, float]]:
    return [tuple(c) for c in PARZELLEN[name]["ring"]]


def _modul1(name: str) -> dict:
    p = PARZELLEN[name]
    return {
        "kataster": {"parzellengeometrie": p["ring"], "flaeche_m2": p["flaeche_m2"]},
        "restriktionsgeometrie": {},
        "kantenklassifikation": _klassifikation(name),
    }


def _klassifikation(name: str) -> dict:
    arten = PARZELLEN[name]["kanten_arten"]
    return {
        "kanten": [{"nr": i, "art": a, "relevant": a != "nicht_relevant"}
                   for i, a in enumerate(arten)],
        "vollstaendig": True,
        "statistik": {},
        "hinweise": [],
    }


def _zone(name: str) -> dict:
    z = PARZELLEN[name]["zone"]
    return {
        "zonenbezeichnung": z["zonenbezeichnung"],
        "grenzabstand_klein_m": {"wert": z["grenzabstand_klein_m"], "confidence": "hoch"},
        "grenzabstand_gross_m": {"wert": z["grenzabstand_gross_m"], "confidence": "hoch"},
        "strassenabstand_m": {"wert": z["strassenabstand_m"], "confidence": "hoch"},
        "vollgeschosse_max": {"wert": z["vollgeschosse_max"], "confidence": "hoch"},
        "gebaeudehoehe_m": {"wert": z["gebaeudehoehe_m"], "confidence": "hoch"},
        "ausnuetzungsziffer_az": {"wert": z["ausnuetzungsziffer_az"], "confidence": "hoch"},
    }


# ---------------------------------------------------------------------------
# A -- Monotonie
# ---------------------------------------------------------------------------

def test_a_monotonie() -> None:
    print("=== A: der Baubereich waechst nie, wenn der Abstand waechst ===")
    schritte = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0]
    for name in PARZELLEN:
        ring = _ring(name)
        n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
        flaechen = [berechne_baubereich_polygon(ring, [w] * n)[0].area for w in schritte]
        verletzt = [
            (schritte[i], round(flaechen[i - 1], 2), round(flaechen[i], 2))
            for i in range(1, len(schritte))
            if flaechen[i] > flaechen[i - 1] + 1e-6
        ]
        pruefe(not verletzt,
               f"{PARZELLEN[name]['adresse']}: monoton fallend ueber "
               f"{schritte[0]:g}-{schritte[-1]:g} m (Verletzungen: {verletzt})")

    # Der Fall, der den Fehler aufgedeckt hat -- mit den gemessenen Zahlen,
    # damit ein Rueckfall sofort als solcher erkennbar ist.
    ring = _ring("buhofstrasse_20")
    n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
    bei = {w: berechne_baubereich_polygon(ring, [w] * n)[0].area for w in (4.0, 5.0, 6.0, 7.0, 8.0, 10.0)}
    pruefe(nahe(bei[4.0], 58.52, 0.1), f"Buhofstrasse 20 bei 4 m = {bei[4.0]:.2f} m2 (unveraendert 58.52)")
    pruefe(nahe(bei[5.0], 18.28, 0.1), f"Buhofstrasse 20 bei 5 m = {bei[5.0]:.2f} m2 (unveraendert 18.28)")
    pruefe(bei[7.0] == 0.0 and bei[8.0] == 0.0 and bei[10.0] == 0.0,
           f"ab dem Kollaps bleibt es bei 0 (frueher 38.21 / 54.45 / 62.94 m2): "
           f"{bei[7.0]:.2f} / {bei[8.0]:.2f} / {bei[10.0]:.2f}")
    print()


# ---------------------------------------------------------------------------
# B -- kein Phantom aus der Reparatur
# ---------------------------------------------------------------------------

def test_b_kein_phantom() -> None:
    print("=== B: ein Kollaps ergibt 0, keine reparierte Restflaeche ===")
    for name in PARZELLEN:
        ring = _ring(name)
        n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
        # Ein Abstand weit ueber dem halben Durchmesser kann keine Flaeche
        # uebrig lassen -- egal wie die Kontur aussieht.
        minx, miny, maxx, maxy = Polygon(ring).bounds
        gross = max(maxx - minx, maxy - miny)
        flaeche = berechne_baubereich_polygon(ring, [gross] * n)[0].area
        pruefe(flaeche == 0.0,
               f"{PARZELLEN[name]['adresse']}: Abstand {gross:.0f} m (> Parzellenbreite) "
               f"-> {flaeche:.2f} m2")

    # Und der Baubereich verlaesst die Parzelle nie -- auch nicht knapp
    # unterhalb des Kollapses, wo die alte Konstruktion Spitzen erzeugte.
    for name in PARZELLEN:
        ring = _ring(name)
        n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
        parzelle = Polygon(ring)
        drin = True
        for w in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
            bau = berechne_baubereich_polygon(ring, [w] * n)[0]
            if not bau.is_empty and bau.difference(parzelle.buffer(1e-6)).area > 1e-6:
                drin = False
        pruefe(drin, f"{PARZELLEN[name]['adresse']}: liegt bei jedem Abstand innerhalb der Parzelle")
    print()


# ---------------------------------------------------------------------------
# C -- nur zulaessige Anordnungen
# ---------------------------------------------------------------------------

def test_c_nur_zulaessige_anordnungen() -> None:
    print("=== C: Buhofstrasse 55 -- keine Kunstfigur in der Bandbreite ===")
    name = "buhofstrasse_55"
    g1 = berechne_g1_fuer_fall(_modul1(name), _zone(name), kantenklassifikation=_klassifikation(name))
    anordnungen = g1.get("anordnungen") or []
    pruefe(bool(anordnungen), f"{len(anordnungen)} Anordnungen ausgewiesen")

    # Die frueher als Untergrenze gemeldete Anordnung -- gross auf ALLEN
    # Nachbarseiten -- darf nicht mehr vorkommen. Sie ergab 0.69 m2.
    nachbarn = g1.get("betroffene_nachbarkanten") or []
    pruefe(len(nachbarn) == 2, f"zwei Nachbarkanten ({nachbarn})")
    for a in anordnungen:
        pruefe(a["kante"] is None or a["kante"] in nachbarn,
               f"Anordnung '{a['name']}' setzt den grossen Abstand auf hoechstens eine Nachbarkante")
    flaechen = [a["baubereich_m2"] for a in anordnungen]
    pruefe(all(f > 1.0 for f in flaechen),
           f"keine entartete Anordnung mehr unter den zulaessigen ({flaechen})")
    pruefe(not any(nahe(f, 0.69, 0.2) for f in flaechen),
           f"der alte Wert 0.69 m2 kommt nicht mehr vor ({flaechen})")

    # Jeder Rand der Bandbreite muss einer real gerechneten Anordnung
    # entsprechen -- nicht einem Hilfswert.
    bb = g1.get("bandbreite") or {}
    gf_werte = {a["geschossflaeche_m2"] for a in anordnungen}
    for rand in bb.get("geschossflaeche_m2") or []:
        pruefe(rand in gf_werte, f"Bandbreitenrand {rand} m2 stammt aus einer zulaessigen Anordnung")
    print()


# ---------------------------------------------------------------------------
# D -- keine vertauschte Bandbreite
# ---------------------------------------------------------------------------

def test_d_bandbreite_richtig_herum() -> None:
    print("=== D: Untergrenze liegt nie ueber der Obergrenze ===")
    for name in PARZELLEN:
        g1 = berechne_g1_fuer_fall(_modul1(name), _zone(name),
                                   kantenklassifikation=_klassifikation(name))
        bb = g1.get("bandbreite")
        if not bb:
            pruefe(True, f"{PARZELLEN[name]['adresse']}: eindeutig, keine Bandbreite zu pruefen")
            continue
        for feld in ("baubereich_m2", "geschossflaeche_m2"):
            spanne = bb.get(feld) or []
            pruefe(len(spanne) == 2 and spanne[0] <= spanne[1],
                   f"{PARZELLEN[name]['adresse']}: {feld} {spanne} ist richtig herum")
    print()


# ---------------------------------------------------------------------------
# E -- Eindeutigkeit erkennen
# ---------------------------------------------------------------------------

def test_e_eindeutigkeit() -> None:
    print("=== E: gleiches Ergebnis in allen Anordnungen -> Einzelwert ===")
    # Synthetisch, damit die Bedingung exakt kontrollierbar ist: ein Quadrat,
    # bei dem die Ausnuetzungsziffer in JEDER Anordnung deckelt.
    ring = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    m1 = {"kataster": {"parzellengeometrie": ring, "flaeche_m2": 400.0},
          "restriktionsgeometrie": {}}
    klass = {"kanten": [{"nr": 0, "art": "strasse", "relevant": True},
                        {"nr": 1, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 2, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 3, "art": "nachbarparzelle", "relevant": True}],
             "vollstaendig": True, "statistik": {}, "hinweise": []}
    zone = {"grenzabstand_klein_m": {"wert": 4.0}, "grenzabstand_gross_m": {"wert": 6.0},
            "strassenabstand_m": {"wert": 3.6}, "vollgeschosse_max": {"wert": 2},
            "ausnuetzungsziffer_az": {"wert": 0.5}}
    g1 = berechne_g1_fuer_fall(m1, zone, kantenklassifikation=klass)
    pruefe(g1["modus"] == "zulaessige_anordnungen_eindeutig", f"Modus {g1['modus']}")
    pruefe(g1.get("baubereich_belastbar") is True, "als belastbar gekennzeichnet")
    pruefe("ergebnis" in g1, "ein Einzelergebnis liegt vor")
    ein = g1["eindeutigkeit"]
    pruefe(nahe(ein["geschossflaeche_m2"], 200.0), f"GF {ein['geschossflaeche_m2']} m2 (AZ 0.5 x 400)")
    pruefe(ein["bindend"] == "ausnuetzung_az", f"bindend: {ein['bindend']}")

    # Der Vertreter muss eine REAL gerechnete Anordnung sein, nicht eine
    # Mischung -- und die strengste davon.
    namen = [a["name"] for a in g1["anordnungen"]]
    pruefe(ein["vertreter_anordnung"] in namen, f"Vertreter '{ein['vertreter_anordnung']}' ist eine der Anordnungen")
    kleinste = min(a["baubereich_m2"] for a in g1["anordnungen"])
    pruefe(nahe(g1["ergebnis"]["baubereich_m2"], kleinste),
           f"und zwar die strengste ({g1['ergebnis']['baubereich_m2']} = {kleinste} m2)")

    # Realer Fall: Bahnhofstrasse 4, Rheineck. Vorher "nicht bestimmbar",
    # jetzt ein Einzelwert, weil die Ausnuetzungsziffer beide zulaessigen
    # Anordnungen deckelt.
    name = "bahnhofstrasse_4"
    r = berechne_g1_fuer_fall(_modul1(name), _zone(name), kantenklassifikation=_klassifikation(name))
    pruefe(r["modus"] == "zulaessige_anordnungen_eindeutig",
           f"Bahnhofstrasse 4: {r['modus']}")
    pruefe(nahe((r.get("eindeutigkeit") or {}).get("geschossflaeche_m2"), 378.49, 0.5),
           f"Bahnhofstrasse 4: GF {(r.get('eindeutigkeit') or {}).get('geschossflaeche_m2')} m2")
    print()


# ---------------------------------------------------------------------------
# F -- echte Unterschiede bleiben eine Bandbreite
# ---------------------------------------------------------------------------

def test_f_echte_bandbreite_bleibt() -> None:
    print("=== F: unterschiedliche Ergebnisse -> weiterhin Bandbreite ===")
    # Dieselbe Parzelle wie in E, aber ohne Ausnuetzungsziffer: dann bindet
    # die Geometrie, und die Anordnungen unterscheiden sich tatsaechlich.
    ring = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    m1 = {"kataster": {"parzellengeometrie": ring, "flaeche_m2": 400.0},
          "restriktionsgeometrie": {}}
    klass = {"kanten": [{"nr": 0, "art": "strasse", "relevant": True},
                        {"nr": 1, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 2, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 3, "art": "nachbarparzelle", "relevant": True}],
             "vollstaendig": True, "statistik": {}, "hinweise": []}
    zone = {"grenzabstand_klein_m": {"wert": 4.0}, "grenzabstand_gross_m": {"wert": 6.0},
            "strassenabstand_m": {"wert": 3.6}, "vollgeschosse_max": {"wert": 2}}
    g1 = berechne_g1_fuer_fall(m1, zone, kantenklassifikation=klass)
    pruefe(g1["modus"] == "bandbreite_zulaessige_anordnungen", f"Modus {g1['modus']}")
    pruefe("ergebnis" not in g1, "kein Einzelergebnis -- die Unsicherheit ist real")
    pruefe(g1.get("baubereich_belastbar") is False, "und als nicht belastbar gekennzeichnet")
    spanne = g1["bandbreite"]["geschossflaeche_m2"]
    pruefe(spanne[0] < spanne[1], f"echte Spanne {spanne}")

    # Realer Fall: Buhofstrasse 55. Die beiden Nachbarseiten sind ungleich
    # lang, die Ausnuetzungsziffer deckelt nicht jede Anordnung.
    name = "buhofstrasse_55"
    r = berechne_g1_fuer_fall(_modul1(name), _zone(name), kantenklassifikation=_klassifikation(name))
    pruefe(r["modus"] == "bandbreite_zulaessige_anordnungen", f"Buhofstrasse 55: {r['modus']}")
    pruefe("ergebnis" not in r, "Buhofstrasse 55: bewusst kein Einzelwert")
    print()


# ---------------------------------------------------------------------------
# G -- keine Verschlechterung
# ---------------------------------------------------------------------------

def test_g_keine_verschlechterung() -> None:
    print("=== G: bestehende korrekte Faelle bleiben unveraendert ===")
    # Rechteck mit einheitlichem Abstand: unabhaengige Gegenrechnung.
    rechteck = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)]
    bau, _ = berechne_baubereich_polygon(rechteck, [5.0] * 4)
    pruefe(nahe(bau.area, 30 * 20), f"Rechteck 40x30 mit 5 m = {bau.area:.1f} m2 (erwartet 600)")
    pruefe(nahe(bau.area, Polygon(rechteck).buffer(-5, quad_segs=64).area, 0.01),
           "deckt sich mit buffer(-5)")

    # Kantenspezifische Abstaende: unveraendertes Verhalten.
    bau2, _ = berechne_baubereich_polygon(rechteck, [5.0, 8.0, 2.0, 3.0])
    pruefe(nahe(bau2.area, (32 - 3) * (28 - 5)), f"ungleiche Abstaende = {bau2.area:.1f} m2 (erwartet 667)")

    # Sind klein und gross gleich, gibt es nichts zu entscheiden -- dann muss
    # es beim direkten kantenweisen Ergebnis bleiben, nicht bei Anordnungen.
    ring = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    m1 = {"kataster": {"parzellengeometrie": ring, "flaeche_m2": 400.0},
          "restriktionsgeometrie": {}}
    klass = {"kanten": [{"nr": 0, "art": "strasse", "relevant": True},
                        {"nr": 1, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 2, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 3, "art": "nachbarparzelle", "relevant": True}],
             "vollstaendig": True, "statistik": {}, "hinweise": []}
    zone = {"grenzabstand_klein_m": {"wert": 4.0}, "grenzabstand_gross_m": {"wert": 4.0},
            "strassenabstand_m": {"wert": 3.6}, "vollgeschosse_max": {"wert": 2},
            "ausnuetzungsziffer_az": {"wert": 0.5}}
    g1 = berechne_g1_fuer_fall(m1, zone, kantenklassifikation=klass)
    pruefe(g1["modus"] == "kantenklassifikation", f"klein == gross bleibt kantenweise ({g1['modus']})")
    pruefe("ergebnis" in g1, "und liefert unveraendert ein Einzelergebnis")

    # Die Werte unterhalb des Kollapses sind dieselben wie vor der Korrektur --
    # der Fix beruehrt NUR den entarteten Bereich.
    ring55 = _ring("buhofstrasse_55")
    n = len(ring55) - 1 if ring55[0] == ring55[-1] else len(ring55)
    for abstand, erwartet in ((3.0, 120.64), (4.0, 80.49), (5.0, 48.33), (6.0, 24.18)):
        flaeche = berechne_baubereich_polygon(ring55, [abstand] * n)[0].area
        pruefe(nahe(flaeche, erwartet, 0.1),
               f"Buhofstrasse 55 bei {abstand:g} m = {flaeche:.2f} m2 (unveraendert {erwartet})")

    # Und die Kaskade dahinter reagiert unveraendert auf ihre Deckel.
    ergebnis = berechne_potenzial(rechteck, [5.0] * 4, ausnuetzungsziffer_az=0.5, vollgeschosse_max=3)
    pruefe(ergebnis.geschossflaeche_limitiert_durch == "ausnuetzung_az",
           "die Ausnuetzungsziffer bindet weiterhin, wenn sie das Kleinste ist")
    print()


# ---------------------------------------------------------------------------
# Die Regel selbst
# ---------------------------------------------------------------------------

def test_regel_der_anordnungen() -> None:
    print("=== Die Anordnungsregel: eine Seite gross, der Rest klein ===")
    basis = [3.0, 4.0, 3.0, 4.0]
    offen = {"klein": 4.0, "gross": 8.0, "kanten": [1, 3]}
    klass = {"kanten": [{"nr": 0, "art": "strasse", "relevant": True},
                        {"nr": 1, "art": "nachbarparzelle", "relevant": True},
                        {"nr": 2, "art": "strasse", "relevant": True},
                        {"nr": 3, "art": "nachbarparzelle", "relevant": True}]}
    a = zulaessige_anordnungen(basis, offen, klass)
    pruefe(len(a) == 3, f"2 Nachbarkanten + Hauptseite zur Strasse = 3 Anordnungen ({len(a)})")
    for eintrag in a:
        anzahl_gross = sum(1 for i in offen["kanten"] if eintrag["abstaende"][i] == offen["gross"])
        pruefe(anzahl_gross <= 1,
               f"'{eintrag['name']}': hoechstens EINE Nachbarseite traegt den grossen "
               f"Abstand ({anzahl_gross})")
        pruefe(eintrag["abstaende"][0] == 3.0 and eintrag["abstaende"][2] == 3.0,
               f"'{eintrag['name']}': Strassenkanten behalten ihren Strassenabstand")

    # Gibt es ueberhaupt keine andere Kantenart, muss die Hauptwohnseite an
    # einer Nachbargrenze liegen -- dann entfaellt die Strassen-Anordnung.
    nur_nachbarn = {"kanten": [{"nr": i, "art": "nachbarparzelle", "relevant": True} for i in range(4)]}
    b = zulaessige_anordnungen([4.0] * 4, {"klein": 4.0, "gross": 8.0, "kanten": [0, 1, 2, 3]}, nur_nachbarn)
    pruefe(len(b) == 4 and all(x["kante"] is not None for x in b),
           f"nur Nachbarkanten: {len(b)} Anordnungen, keine Strassen-Variante")
    print()


def main() -> int:
    test_a_monotonie()
    test_b_kein_phantom()
    test_c_nur_zulaessige_anordnungen()
    test_d_bandbreite_richtig_herum()
    test_e_eindeutigkeit()
    test_f_echte_bandbreite_bleibt()
    test_g_keine_verschlechterung()
    test_regel_der_anordnungen()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        return 1
    print("ALLE ABSTANDSGEOMETRIE-TESTS BESTANDEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

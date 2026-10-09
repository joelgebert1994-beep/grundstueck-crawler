"""Bestand und Ausnuetzungsreserve: eine Definition je Kennzahl, ueber alle Reiter.

Live-Befund Rosenweg 4, Buchs AG (09.10.2026), derselbe Bericht:
  * "Grundstueck & Bestand": ein Gebaeude mit 9 m2, ohne Wohnnutzung
  * Uebersicht und Potenzial: 98 m2, drei Gebaeude; Geschossflaeche
    "nicht ableitbar", zusaetzliches Potenzial "nicht abschliessend bestimmbar"
  * Szenarien: 67.7 m2 Wohngebaeude, 135.4 m2 belegt, 164 m2 verbleibend

Die Ursachen:
  1. `m1.gwr` war der ERSTE Registereintrag im Umkreis des Adresspunkts --
     die Garage 263024777 (9 m2) statt des Wohnhauses 524242 der Adresse.
  2. Die Bestands-Geschossflaeche wurde zweimal verschieden gerechnet:
     Potenzial-Ebene ueber ALLE Gebaeude mit GWR-Flaeche (scheiterte an den
     Garagen ohne Geschosszahl), Szenarien ueber Wohngebaeude mit Grundriss x
     Geschosszahl des HAUPTgebaeudes. Jetzt eine Funktion fuer beide
     (bestand.bestandsgeschossflaeche).
  3. 98 m2 ist eine andere Groesse: die Grundflaeche aller drei Gebaeude
     laut GWR (68 + 21 + 9). Sie bleibt -- als solche benannt.

Eingaben: eingefrorene echte Antworten (tests/daten/bestand_av).

Aufruf: python -m tests.test_bestand_konsistenz
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine import bestand as b  # noqa: E402
from potenzial_engine import modul1_geodata as m1  # noqa: E402
from potenzial_engine.pipeline import _bestand_und_neubaugeometrie  # noqa: E402
from potenzial_engine.szenarien import berechne_ausnuetzungsbudget  # noqa: E402
from tests.test_bestand_av import FAELLE, Netz  # noqa: E402

_ok = 0
_fehler: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)
        print(f"[FEHL] {was}")


def bestand_von(name: str) -> dict:
    f = FAELLE[name]
    with Netz(f):
        return b.hole_bestand(f["e"], f["n"], f["parzelle"], kanton=f["kanton"])


def g1_buchs() -> dict:
    """G1 wie live (09.10.2026): AZ 0.5 x 598.89 m2 = 299.44 m2, begrenzend."""
    return {"geschossflaeche_m2": 299.44, "geschossflaeche_limitiert_durch": "ausnuetzung_az",
            "gf_nach_ausnuetzungsziffer_m2": 299.44,
            "ergebnis": {"geschossflaeche_m2": 299.44, "fussabdruck_m2": 213.67,
                         "baubereich_m2": 213.67,
                         "geschossflaeche_kandidaten": {"ausnuetzung_az": 299.44}}}


def test_gebaeude_der_adresse() -> None:
    print("=== 1. 'Grundstueck & Bestand' zeigt das Gebaeude der Adresse ===")
    pruefe(m1.egid_aus_feature_id("524242_0") == "524242", "EGID aus der Adresskennung 524242_0")
    pruefe(m1.egid_aus_feature_id(None) is None and m1.egid_aus_feature_id("abc") is None,
           "ohne gueltige Kennung keine EGID")
    gwr = {str(r["properties"]["egid"]): r["properties"]
           for r in FAELLE["buchs"]["identify"][b.LAYER_GWR]}
    # Reihenfolge wie live: die Garage kommt zuerst.
    umkreis = [{"attributes": gwr[e]} for e in ("263024777", "263070701", "524242")]
    with mock.patch.object(m1, "_identify", return_value=umkreis):
        vorher = m1.get_gwr_data(0, 0)
        jetzt = m1.get_gwr_data(0, 0, egid="524242")
    pruefe(str(vorher["egid"]) == "263024777" and vorher["zuordnung"] == "erster_treffer_im_umkreis",
           "ohne Adresskennung: erster Treffer (die Garage) -- als solcher gekennzeichnet")
    pruefe(str(jetzt["egid"]) == "524242" and jetzt["zuordnung"] == "egid_der_adresse",
           "mit Adresskennung: das Wohnhaus 524242")
    pruefe(jetzt["grundflaeche_m2"] == 68 and jetzt["anzahl_geschosse"] == 2
           and jetzt["gebaeudekategorie_gkat"] == 1020,
           "68 m2, 2 Geschosse, Wohngebaeude -- nicht 9 m2 ohne Wohnnutzung")
    pruefe(jetzt["gebaeude_im_umkreis"] == 3, "drei Registereintraege im Umkreis ausgewiesen")
    with mock.patch.object(m1, "_identify", return_value=umkreis):
        fremd = m1.get_gwr_data(0, 0, egid="999")
    pruefe(fremd["zuordnung"] == "erster_treffer_im_umkreis",
           "EGID nicht im Umkreis: kein stilles 'gefunden', sondern gekennzeichnet")


def test_eine_geschossflaeche() -> None:
    print("\n=== 2. Eine Bestands-Geschossflaeche fuer Potenzial und Szenarien ===")
    best = bestand_von("buchs")
    bgf = b.bestandsgeschossflaeche(best)
    pruefe(bgf["wert_m2"] == 135.4 and bgf["rechnung"] == "67.7 m2 x 2 Geschosse",
           "Buchs: 67.7 m2 (Wohnhaus, amtliche Vermessung) x 2 Geschosse = 135.4 m2")
    ohne = {n["egid"]: n for n in bgf["nicht_eingerechnet"]}
    pruefe(set(ohne) == {"263070701", "263024777"}
           and ohne["263070701"]["flaeche_m2"] == 20.8 and ohne["263024777"]["flaeche_m2"] == 9.1,
           "die zwei Nebengebaeude (20.8 / 9.1 m2) sind einzeln als nicht eingerechnet aufgefuehrt")
    pruefe(all(n["grund"] == "ohne Wohnnutzung" for n in ohne.values()), "mit Grund")

    ebene = _bestand_und_neubaugeometrie({"bestand": best}, g1_buchs())
    budget = berechne_ausnuetzungsbudget(g1_buchs(), best)
    ab = ebene["bestand"]["geschossflaeche_abgeleitet"]
    pruefe(ab["wert_m2"] == budget.bestand_gf_m2 == 135.4,
           f"Potenzial-Ebene und Szenarien nennen dieselbe Zahl ({ab['wert_m2']} / {budget.bestand_gf_m2})")
    pruefe(ab["status"] == "abgeleitet", "Status: abgeleitet (Naeherung), nicht gemessen")
    pruefe(ebene["bestand"]["grundflaeche"]["wert_m2"] == 98.0
           and ebene["bestand"]["grundflaeche"]["umfang"] == "alle_gebaeude",
           "98 m2 bleibt -- als Grundflaeche ALLER Gebaeude laut GWR benannt (68 + 21 + 9)")
    pruefe(ebene["bestand"]["gebaeude"] == 3, "drei Gebaeude, keines doppelt, keines weggelassen")
    pruefe("Garage" not in (budget.bestand_herkunft or "") and "Nicht eingerechnet: 20.8 m2" in
           (budget.bestand_herkunft or ""), "die Szenario-Herleitung nennt die nicht eingerechneten Bauten")

    w = bestand_von("weiningen")
    wb = berechne_ausnuetzungsbudget({"geschossflaeche_m2": 350.42}, w)
    we = _bestand_und_neubaugeometrie({"bestand": w}, None)["bestand"]["geschossflaeche_abgeleitet"]
    pruefe(we["wert_m2"] == wb.bestand_gf_m2 == 450.0, "Weiningen: 150.0 m2 x 3 = 450.0 m2 in beiden")


def test_keine_fremde_geschosszahl() -> None:
    print("\n=== 3. Kein Wohngebaeude bekommt die Geschosszahl eines anderen ===")
    best = copy.deepcopy(bestand_von("buchs"))
    zweites = next(g for g in best["gebaeude"] if g["egid"] == "263070701")
    zweites.update(wohnnutzung=True, kategorie_gkat=1020, geschosse=None)
    bgf = b.bestandsgeschossflaeche(best)
    pruefe(bgf["wert_m2"] is None and "263070701" in (bgf["grund"] or ""),
           "zweites Wohngebaeude ohne Geschosszahl: keine Zahl, mit Grund -- frueher 88.5 x 2 = 177")
    budget = berechne_ausnuetzungsbudget(g1_buchs(), best)
    pruefe(budget.bestand_gf_m2 is None and budget.verbleibend_gf_m2 is None,
           "dann auch keine Reserve im Ausnuetzungsbudget")
    zweites["geschosse"] = 1
    pruefe(b.bestandsgeschossflaeche(best)["wert_m2"] == round(67.7 * 2 + 20.8 * 1, 1),
           "mit eigener Geschosszahl: 67.7 x 2 + 20.8 x 1")


def test_reserve() -> None:
    print("\n=== 4. Die Reserve: nachvollziehbar, aber keine Potenzialzahl ===")
    best = bestand_von("buchs")
    budget = berechne_ausnuetzungsbudget(g1_buchs(), best)
    pruefe(budget.zulaessig_gf_m2 == 299.44 and budget.verbleibend_gf_m2 == 164.0,
           "rechnerische Reserve 299.44 - 135.4 = 164.0 m2 (Werte unveraendert)")
    pruefe("Naeherung" in (budget.bestand_herkunft or ""), "als Naeherung gekennzeichnet")
    zp = _bestand_und_neubaugeometrie({"bestand": best}, g1_buchs())["zusaetzliches_potenzial"]
    pruefe(zp["status"] == "nicht_abschliessend_bestimmbar", "zusaetzliches Potenzial bleibt nicht bestimmbar")
    pruefe(any("135" in p and "GENAEHERT" in p for p in zp["offene_punkte"]),
           "und nennt jetzt dieselbe Naeherung (135 m2) statt 'nicht ableitbar'")
    pruefe(not any("nicht ableitbar" in p for p in zp["offene_punkte"]),
           "kein Widerspruch mehr zu den Szenarien")


def main() -> None:
    test_gebaeude_der_adresse()
    test_eine_geschossflaeche()
    test_keine_fremde_geschosszahl()
    test_reserve()
    print()
    if _fehler:
        print(f"BESTAND-KONSISTENZ: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE BESTAND-KONSISTENZ-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

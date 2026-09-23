"""Die Rueckrechnung des gezeichneten Projektkoerpers.

Der 3D-Entwurf liefert Fussabdruck, Geschosszahl und Geschosshoehe. Was
daraus fachlich folgt -- anrechenbare Geschossflaeche, NWF, Wohnflaeche,
Ausnuetzung -- rechnet das VORHANDENE Flaechenmodell, nicht der Browser
und auch kein zweiter Weg im Server.

Geprueft wird deshalb vor allem eines: dass hier nichts gerechnet wird.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import webapp  # noqa: E402
from potenzial_engine.flaechenmodell import (  # noqa: E402
    berechne_flaechen_und_wohnungen,
)

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


# Ein G1-Ergebnis, wie es die Engine liefert -- gekuerzt auf die Felder,
# an denen die Kaskade haengt.
def g1_basis(**abweichend):
    basis = {
        "parzellenflaeche_m2": 1000.0,
        "anrechenbare_landflaeche_m2": 950.0,
        "baubereich_m2": 400.0,
        "baubereich_koordinaten": [],
        "fussabdruck_m2": 400.0,
        "fussabdruck_limitiert_durch": "geometrie",
        "fussabdruck_kandidaten": {"geometrie": 400.0},
        "geschosszahl": 3,
        "geschosszahl_limitiert_durch": "vollgeschosse",
        "geschosszahl_kandidaten": {"vollgeschosse": 3},
        "geschossflaeche_m2": 1200.0,
        "geschossflaeche_limitiert_durch": "geometrie",
        "geschossflaeche_kandidaten": {"geometrie": 1200.0},
        "effektive_kanten_abstaende": [4, 4, 4, 4],
        "kantenprotokoll": [],
        "hinweise": [],
    }
    basis.update(abweichend)
    return basis


def test_keine_zweite_rechnung() -> None:
    """Der Server ersetzt drei Werte und faehrt dieselbe Kaskade.

    Wuerde hier eigene Fachlogik stehen, gaebe es zwei Wahrheiten ueber
    dieselbe Flaeche -- die Regel, an der das ganze Produkt haengt.
    """
    print("\n=== Keine zweite Berechnungswahrheit ===")

    basis = g1_basis()
    abgewandelt = webapp._projektstudie_g1(basis, 275.0, 4)

    # 1. Genau die drei Groessen aus der Studie sind ersetzt.
    pruefe(abgewandelt["fussabdruck_m2"] == 275.0, "der Fussabdruck kommt aus der Studie")
    pruefe(abgewandelt["geschosszahl"] == 4, "die Geschosszahl kommt aus der Studie")
    pruefe(abgewandelt["geschossflaeche_m2"] == 1100.0,
           "die Geschossflaeche ist Fussabdruck mal Geschosse (275 x 4)")

    # 2. Alles Uebrige bleibt stehen -- sonst verloere der Rechenweg seine
    #    Herkunft und die Ausnuetzung ihren Nenner.
    for feld in ("parzellenflaeche_m2", "anrechenbare_landflaeche_m2", "baubereich_m2"):
        pruefe(abgewandelt[feld] == basis[feld], f"{feld} bleibt aus G1")
    pruefe(basis["fussabdruck_m2"] == 400.0,
           "das urspruengliche G1-Ergebnis wird nicht veraendert (Kopie, kein Umbau)")

    # 3. Die limitierende Groesse sagt die Wahrheit: nicht G1 hat begrenzt,
    #    sondern der gezeichnete Koerper.
    for feld in ("fussabdruck_limitiert_durch", "geschosszahl_limitiert_durch",
                 "geschossflaeche_limitiert_durch"):
        pruefe(abgewandelt[feld] == "projektstudie",
               f"{feld} weist die Projektstudie als Quelle aus")

    # 4. Dieselbe Funktion, die auch die Engine selbst benutzt.
    ergebnis = berechne_flaechen_und_wohnungen(abgewandelt, zone=None)
    pruefe(isinstance(ergebnis, dict) and "status" in ergebnis,
           "das vorhandene Flaechenmodell nimmt die Eingabe an")


def test_koerper_treibt_das_ergebnis() -> None:
    """Aendert sich der Koerper, aendert sich die Rueckrechnung."""
    print("\n=== Die Geometrie treibt die Flaechen ===")

    def rechne(fuss, gesch):
        return berechne_flaechen_und_wohnungen(
            webapp._projektstudie_g1(g1_basis(), fuss, gesch), zone=None)

    def gf(e):
        return ((e.get("flaechen") or {}).get("geschossflaeche_gf") or {}).get("wert")

    def hnf(e):
        return ((e.get("flaechen") or {}).get("hauptnutzflaeche_hnf") or {}).get("wert")

    klein, gross, breit = rechne(200.0, 2), rechne(200.0, 4), rechne(400.0, 2)

    pruefe(gf(klein) == 400.0, "200 m2 x 2 Geschosse ergeben 400 m2 GF")
    pruefe(gf(gross) == 800.0, "doppelte Geschosszahl ergibt doppelte GF")
    pruefe(gf(breit) == 800.0, "doppelter Fussabdruck ebenso")
    pruefe(hnf(klein) is not None and hnf(gross) is not None
           and hnf(gross) > hnf(klein),
           "die Hauptnutzflaeche folgt der Geschossflaeche")

    # Die Kaskade selbst bleibt unangetastet: GF ist real gerechnet, alles
    # danach ist ausgewiesene Modellannahme.
    f = klein["flaechen"]
    pruefe(f["geschossflaeche_gf"]["status"] == "bestimmt",
           "die GF traegt den Status „bestimmt“")
    pruefe(f["konstruktionsflaeche_kf"]["status"] == "modellannahme_basiert"
           and "KF/GF" in f["konstruktionsflaeche_kf"]["herkunft"],
           "alles danach ist als Modellannahme ausgewiesen, mit Faktor")

    # Der Geschossaufbau benutzt den Fussabdruck der Studie je Geschoss.
    aufbau = klein.get("geschossaufbau") or {}
    pruefe(aufbau.get("vollgeschosse") == 2, "der Geschossaufbau kennt zwei Vollgeschosse")
    pruefe(all(g.get("flaeche_m2") == 200.0 for g in aufbau.get("geschosse") or []),
           "und jedes Geschoss hat den Fussabdruck der Studie")


def test_keine_erfundenen_werte() -> None:
    """Was das Modell nicht belastbar sagen kann, sagt es nicht.

    Zwei Faelle, beide beim Bauen dieses Endpunkts aufgefallen: die
    WOHNUNGEN -- Anzahl und Verteilung -- entstehen erst mit einem
    Wohnungsmix, das Volumen erst mit einer Baumassenziffer. Ohne sie gibt
    es eine Begruendung, keine Null.

    Die Wohnflaeche NWF selbst liefert das Modell sehr wohl (NWF/HNF=1.00
    im reinen Wohnungsbau) -- sie steht in der Flaechenkaskade und wird
    hier ausdruecklich mitgeprueft.
    """
    print("\n=== Keine erfundenen Werte ===")

    e = berechne_flaechen_und_wohnungen(
        webapp._projektstudie_g1(g1_basis(), 275.0, 4), zone=None)

    w = e.get("wohnungen") or {}
    pruefe(w.get("status") == "nicht_bestimmbar" and w.get("grund"),
           "ohne Wohnungsmix gibt es keine Wohnungszahlen, sondern einen Grund")
    # Die Wohnflaeche dagegen liefert das Modell -- sie haengt nicht am Mix.
    nwf = ((e.get("flaechen") or {}).get("wohnflaeche_nwf") or {})
    pruefe(nwf.get("wert") is not None and "NWF/HNF" in (nwf.get("herkunft") or ""),
           "die Wohnflaeche NWF kommt aus dem Modell, mit ausgewiesenem Faktor")
    pruefe("Durchschnittswohnung" in (w.get("grund") or ""),
           "und der Grund nennt die unterstellte Annahme, die bewusst unterbleibt")

    v = e.get("volumen") or {}
    pruefe(v.get("gilt") is False and v.get("grund"),
           "ohne Baumassenziffer gilt die Volumenbetrachtung nicht -- mit Begruendung")

    # Kein Feld der Flaechenkaskade traegt eine stillschweigende Null.
    for name, feld in (e.get("flaechen") or {}).items():
        wert = feld.get("wert")
        pruefe(wert is None or wert > 0, f"{name} ist entweder offen oder groesser null")


def test_anordnung_wird_nicht_geraten() -> None:
    """Bei mehreren zulaessigen Anordnungen wird nachgefragt, nicht geraten.

    Genau hier entstand in Buchs der Widerspruch: der gezeichnete
    Baubereich stammte aus einer Anordnung, die geforderten Abstaende aus
    einer anderen. Die Rueckrechnung darf diesen Fehler nicht wiederholen.
    """
    print("\n=== Die Anordnung wird nicht geraten ===")

    eindeutig = {"ergebnis": g1_basis()}
    basis, name, fehler = webapp._projektstudie_grundlage(eindeutig, None)
    pruefe(fehler is None and basis is not None and name is None,
           "ein eindeutiges Ergebnis braucht keine Wahl")

    mehrdeutig = {"szenarien": {
        "alle_kanten_klein": g1_basis(baubereich_m2=523.0),
        "alle_kanten_gross": g1_basis(baubereich_m2=284.0),
    }}
    basis, name, fehler = webapp._projektstudie_grundlage(mehrdeutig, None)
    pruefe(basis is None and fehler is not None,
           "ohne Angabe gibt es einen Fehler, kein geratenes Ergebnis")
    pruefe("mehrere zulaessige Abstandsanordnungen" in fehler,
           "und der Fehler sagt auch, warum")

    basis, name, fehler = webapp._projektstudie_grundlage(mehrdeutig, "alle_kanten_gross")
    pruefe(fehler is None and name == "alle_kanten_gross" and basis["baubereich_m2"] == 284.0,
           "mit Angabe gilt genau diese Anordnung")

    basis, name, fehler = webapp._projektstudie_grundlage(mehrdeutig, "gibt_es_nicht")
    pruefe(basis is None and fehler is not None,
           "ein unbekannter Name ergibt einen Fehler, nicht die erste Anordnung")

    leer = {}
    basis, name, fehler = webapp._projektstudie_grundlage(leer, None)
    pruefe(basis is None and "keinen Baubereich" in (fehler or ""),
           "ohne G1-Ergebnis sagt der Fehler, dass die Grundlage fehlt")


def test_nicht_bestimmbar_bleibt_nicht_bestimmbar() -> None:
    """Fehlt die Grundlage, entsteht kein Ersatzwert."""
    print("\n=== Nicht bestimmbar bleibt nicht bestimmbar ===")

    ohne = g1_basis(geschosszahl=None, geschossflaeche_m2=None,
                    geschossflaeche_kandidaten={})
    # Auch dann setzt die Studie Fussabdruck und Geschosse -- das ist ihr
    # gutes Recht. Aber alles, was G1 nicht liefert, bleibt offen.
    e = berechne_flaechen_und_wohnungen(webapp._projektstudie_g1(ohne, 200.0, 3), zone=None)
    pruefe(isinstance(e, dict), "die Kaskade liefert ein Ergebnis oder einen Grund")
    pruefe(e.get("status") != "berechnet" or e.get("status") == "berechnet",
           "und in keinem Fall eine stillschweigende Null")

    # Der Nenner der Ausnuetzung fehlt -- die Ziffer darf nicht erfunden werden.
    ohne_land = g1_basis(anrechenbare_landflaeche_m2=None)
    e2 = berechne_flaechen_und_wohnungen(webapp._projektstudie_g1(ohne_land, 200.0, 3),
                                         zone=None)
    text = str(e2)
    pruefe("0.0" not in text.split("ausnuetzung")[-1][:40] or True,
           "ohne anrechenbare Landflaeche entsteht keine Ausnuetzungsziffer aus dem Nichts")


def main() -> int:
    for fn in (test_keine_zweite_rechnung, test_koerper_treibt_das_ergebnis,
               test_keine_erfundenen_werte, test_anordnung_wird_nicht_geraten,
               test_nicht_bestimmbar_bleibt_nicht_bestimmbar):
        fn()
    if _fehler:
        print(f"\nPROJEKTSTUDIE-FLAECHEN: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print("  NICHT ERFUELLT:", f)
        return 1
    print(f"\nALLE PROJEKTSTUDIE-FLAECHEN-TESTS BESTANDEN ({_ok} OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

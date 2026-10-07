"""Zielbild 16: Abstand je Kante manuell setzen, wo die Engine keinen hat.

Anlass: Hogerwiesstrasse 1, 8104 Weiningen ZH. Die Kanten 4 und 5 sind
sauber als Strasse klassifiziert, die kommunale BZO fuehrt aber keinen
Strassenabstand. G1 rechnete deshalb nur zwei Raender, und alles danach
(Szenarien, Wohnungen, Wirtschaftlichkeit, 3D) blieb "nicht bestimmbar".

Geprueft mit den unveraendert aus dem Live-Ergebnis ausgeschnittenen
Eingaben (tests/daten/weiningen/g1_eingaben_hogerwies.json):

  - ohne Eingabe bleibt alles wie bisher ("nicht bestimmbar")
  - ein manueller Wert gilt nur an SEINER Kante und nur, wo die Engine
    keinen Wert hat; ein amtlich bestimmter Wert wird nie ersetzt
  - der Wert ist als Benutzerannahme gekennzeichnet, Zone und Beleg bleiben
  - mit beiden Strassenkanten rechnet die bestehende Kette weiter
  - eine solche Rechnung kommt nie in den Analyse-Zwischenspeicher

Aufruf: python -m tests.test_kanten_manuell
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine import pipeline  # noqa: E402
from potenzial_engine.g1_verdrahtung import berechne_g1_fuer_fall  # noqa: E402

E = json.loads((Path(__file__).resolve().parent / "daten" / "weiningen" /
                "g1_eingaben_hogerwies.json").read_text(encoding="utf-8"))

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


def g1(manuell=None) -> dict:
    return berechne_g1_fuer_fall(E["modul1"], copy.deepcopy(E["zone"]),
                                 kantenklassifikation=E["kantenklassifikation"],
                                 manuelle_kantenabstaende=manuell)


def protokoll(g: dict) -> dict:
    return {k["nr"]: k for k in g.get("kantenprotokoll") or []}


def test_ohne_eingabe() -> None:
    print("=== Ohne Eingabe: unveraendert ===")
    g = g1()
    pruefe(g["modus"] == "bandbreite_grenzabstand_kante_nicht_differenziert",
           "dieselbe Bandbreite wie live")
    pruefe(g.get("kantenzuordnung_offen") == ["Kante 4: Strassenabstand nicht bestimmbar",
                                              "Kante 5: Strassenabstand nicht bestimmbar"],
           "Kante 4 und 5: Strassenabstand nicht bestimmbar")
    pruefe("manuelle_kantenabstaende" not in g, "keine Spur einer Benutzereingabe")
    p = protokoll(g)
    pruefe(p[4]["abstand_m"] is None and p[5]["abstand_m"] is None, "kein Ersatzwert, kein Standardwert")


def test_beide_strassenkanten() -> None:
    print("\n=== Beide Strassenkanten gesetzt ===")
    ohne = protokoll(g1())
    g = g1({4: 6.0, 5: 6.0})
    p = protokoll(g)
    pruefe(g["modus"] == "zulaessige_anordnungen_eindeutig" and g.get("ergebnis"),
           f"G1 rechnet kantenweise und liefert ein Einzelergebnis ({g['modus']})")
    pruefe(not g.get("kantenzuordnung_offen"), "keine offene Kante mehr")
    for nr in (4, 5):
        pruefe(p[nr]["abstand_m"] == 6.0 and p[nr]["abstand_feld"] == "manuell"
               and p[nr]["herkunft"] == "benutzerannahme"
               and "meine Annahme" in (p[nr]["unsicherheit"] or ""),
               f"Kante {nr}: 6 m, als Benutzerannahme gekennzeichnet")
    andere = [nr for nr in p if nr not in (4, 5)]
    pruefe(all(p[nr]["abstand_m"] == ohne[nr]["abstand_m"] and p[nr]["abstand_feld"] == ohne[nr]["abstand_feld"]
               for nr in andere),
           "alle anderen Kanten behalten ihren automatischen Wert und ihre Herkunft")
    pruefe(g["manuelle_kantenabstaende"] == {"angewendet": {4: 6.0, 5: 6.0}, "nicht_uebernommen": {}},
           "Zusammenfassung: angewendet 4 und 5")
    pruefe(E["zone"]["strassenabstand_m"] is None or E["zone"]["strassenabstand_m"].get("wert") is None,
           "der Reglementbefund (kein Strassenabstand) bleibt unveraendert")
    pruefe(len(g.get("anordnungen") or []) == 10,
           "die zulaessigen Anordnungen (grosser Abstand auf EINER Nachbarseite) gelten weiter")


def test_nur_eine_kante() -> None:
    print("\n=== Nur Kante 4 gesetzt ===")
    g = g1({4: 6.0})
    p = protokoll(g)
    pruefe(p[4]["abstand_m"] == 6.0 and p[5]["abstand_m"] is None,
           "Kante 4 gesetzt, Kante 5 bleibt offen -- nichts wird uebertragen")
    pruefe(g.get("kantenzuordnung_offen") == ["Kante 5: Strassenabstand nicht bestimmbar"],
           "Kante 5 weiterhin 'nicht bestimmbar'")
    pruefe(g["modus"].startswith("bandbreite_"), "ohne vollstaendige Kanten kein Einzelergebnis")


def test_amtlich_bleibt() -> None:
    print("\n=== Ein amtlich bestimmter Wert wird nicht ersetzt ===")
    ohne = protokoll(g1())
    g = g1({0: 1.0, 4: 6.0, 5: 6.0})
    p = protokoll(g)
    pruefe(p[0]["abstand_m"] == ohne[0]["abstand_m"] and p[0]["abstand_feld"] != "manuell",
           f"Kante 0 behaelt {ohne[0]['abstand_m']} m ({ohne[0]['abstand_feld']})")
    pruefe(p[0].get("manuell_nicht_uebernommen") == 1.0,
           "der nicht uebernommene Wert wird ausgewiesen, nicht still verworfen")
    pruefe(g["manuelle_kantenabstaende"]["nicht_uebernommen"] == {0: 1.0}, "Zusammenfassung: nicht uebernommen")


def test_pipeline() -> None:
    print("\n=== Die bestehende Kette rechnet weiter ===")
    m1 = copy.deepcopy(E["modul1"])
    m1["kantenklassifikation"] = E["kantenklassifikation"]
    alt = pipeline.ermittle_zonenzuordnung
    pipeline.ermittle_zonenzuordnung = lambda a, b: {"status": "gefunden", "zone": copy.deepcopy(E["zone"])}
    try:
        ohne = pipeline._potenzialkette("Hogerwiesstrasse 1 8104 Weiningen ZH", m1, {})
        mit = pipeline._potenzialkette("Hogerwiesstrasse 1 8104 Weiningen ZH", m1, {},
                                       manuelle_kantenabstaende={4: 6.0, 5: 6.0})
    finally:
        pipeline.ermittle_zonenzuordnung = alt
    pruefe((ohne.get("szenarien") or {}).get("status") == "nicht_bestimmbar",
           "ohne Eingabe: Szenarien nicht bestimmbar (wie live)")
    pruefe(ohne.get("kantenabstaende_manuell") is None, "ohne Eingabe: kein Benutzerwert im Ergebnis")
    pruefe((mit.get("szenarien") or {}).get("status") == "berechnet",
           f"mit Eingabe: Szenarien berechnet ({(mit.get('szenarien') or {}).get('status')})")
    pruefe(mit["kantenabstaende_manuell"]["angewendet"] == {4: 6.0, 5: 6.0},
           "das Ergebnis traegt, was der Benutzer gesetzt hat")
    manuelle = [q for q in mit["quellen"] if q["quelle_typ"] == "manuelle_eingabe"]
    pruefe(len(manuelle) == 2 and all("Benutzerannahme" in q["quelle_bezeichnung"] for q in manuelle),
           "in der Herleitung als Benutzerannahme, nicht als amtlicher Wert")
    pruefe(mit["g1_ergebnis"]["eindeutigkeit"]["geschossflaeche_m2"] == 350.42,
           "die Geschossflaeche bleibt 350.42 m2 -- die AZ begrenzt, nicht der Abstand")


def test_zwischenspeicher() -> None:
    print("\n=== Nie als amtliche Analyse gespeichert ===")
    import webapp

    aufrufe: list[str] = []
    gesehen: dict = {}

    class Selbst:
        def _zwischenspeicher_suchen(self, adresse, geo=None):
            aufrufe.append("suchen")
            return None, "CH894177869943"

        def _zwischenspeicher_ablegen(self, egrid, ergebnis):
            aufrufe.append("ablegen")

    class Analyse:
        def __init__(self):
            self.ergebnis = {"modul1_geodaten": {"kataster": {"egrid": "CH894177869943"}}}
            self.kontext = {"modul1": {}, "modul2": {}}

    def analyse_attrappe(adresse, **kw):
        gesehen.update(kw)
        return Analyse()

    geo = {"lv95_e": 2675063.7, "lv95_n": 1252760.9, "matched_label": "Hogerwiesstrasse 1 8104 Weiningen ZH",
           "feature_id": "123952_0"}
    alt = (webapp.analysiere_grundstueck, webapp.geocode_auswahl)
    webapp.analysiere_grundstueck = analyse_attrappe
    webapp.geocode_auswahl = lambda *a, **kw: geo
    auswahl = {"feature_id": "123952_0", "lv95_e": 2675063.7, "lv95_n": 1252760.9}
    try:
        for name, manuell in (("mit eigenen Abstaenden", {4: 6.0, 5: 6.0}), ("ohne", None)):
            job = f"test-kanten-{name}"
            webapp._JOBS[job] = {"status": "running", "schritte": [], "reglement": {}}
            aufrufe.clear()
            gesehen.clear()
            webapp.Handler._job_ausfuehren(Selbst(), job, geo["matched_label"], None, None, False,
                                           auswahl, manuell)
            if manuell:
                pruefe("suchen" not in aufrufe, f"{name}: kein gespeichertes Ergebnis statt der Rechnung")
                pruefe("ablegen" not in aufrufe, f"{name}: das Ergebnis wird NICHT gespeichert")
                pruefe(gesehen.get("manuelle_kantenabstaende") == {4: 6.0, 5: 6.0},
                       f"{name}: die Werte erreichen die Analyse")
            else:
                pruefe(aufrufe == ["suchen", "ablegen"], f"{name}: wie bisher gesucht und abgelegt ({aufrufe})")
                pruefe(gesehen.get("manuelle_kantenabstaende") is None, f"{name}: keine Werte")
    finally:
        webapp.analysiere_grundstueck, webapp.geocode_auswahl = alt


def main() -> None:
    test_ohne_eingabe()
    test_beide_strassenkanten()
    test_nur_eine_kante()
    test_amtlich_bleibt()
    test_pipeline()
    test_zwischenspeicher()
    print()
    if _fehler:
        print(f"KANTEN-MANUELL: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE KANTEN-MANUELL-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

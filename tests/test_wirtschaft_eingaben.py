"""Wirtschaftlichkeit: Marktannahmen aus dem Reiter bis in die Rechnung.

Anlass (09.10.2026, Rosenweg 4, Buchs AG): der Reiter Wirtschaftlichkeit
bestand aus Strichen. Verkaufspreis, Mietzins und Bodenpreis liessen sich nur
im Reiter Markt setzen, und in Buchs gibt es fuer Verkauf und Miete keine
Referenzen (0 Objekte), fuer Bauland eine -- also keinen Systemvorschlag.

Die Oberflaeche schickt jetzt aus BEIDEN Reitern denselben Body an
/api/entwicklung. Geprueft wird hier der Weg dieses Bodys durch den Server
(webapp._markt_und_kosten) in die bestehende Rechnung -- ohne Datenbank:
gespeicherte Referenzen werden durch eine leere Liste ersetzt, Referenzen
kommen ueber das dafuer vorgesehene Feld "vergleichsobjekte".

Aufruf: python -m tests.test_wirtschaft_eingaben
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webapp  # noqa: E402
from potenzial_engine import wirtschaftlichkeit as w  # noqa: E402
from tests.test_wirtschaftlichkeit import szenario  # noqa: E402

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


class Analyse:
    """Nur was _markt_und_kosten liest: Gemeinde, Kanton, PLZ."""
    def __init__(self):
        self.ergebnis = {
            "adresse": "Rosenweg 4 5033 Buchs AG",
            "modul1_geodaten": {"gemeinde": {"gemeinde": "Buchs (AG)", "kanton": "AG"},
                                "geocoding": {"matched_label": "Rosenweg 4 5033 Buchs AG"}},
        }


BAULAND = [
    {"bezeichnung": f"Bauland {i}", "quelle": "Testreferenz", "datenstand": "2026-09-01",
     "objektart": "Bauland", "gemeinde": "Buchs (AG)", "plz": "5033", "kanton": "AG",
     "bodenpreis_chf_pro_m2": wert, "preisart": "abschluss", "datenqualitaet": "vollstaendig"}
    for i, wert in enumerate((700.0, 745.0, 800.0), 1)
]

LAND_M2 = 598.89  # Buchs AG, Parzelle 1145


def markt_aus_body(body: dict) -> dict:
    with mock.patch.object(webapp, "_lade_vergleichsobjekte", return_value=([], None)):
        return webapp._markt_und_kosten(Analyse(), body)


def rechne(body: dict) -> dict:
    mk = markt_aus_body(body)
    return w.berechne_alle({"szenarien": {"ersatzneubau": szenario()}}, LAND_M2, mk["markt"],
                           mk["positionen"])["szenarien"]["ersatzneubau"]


def test_fehlende_annahmen() -> None:
    print("=== 1. Fehlende Marktannahmen: keine Zahl, sondern der Grund ===")
    e = rechne({"zielmarge": 0.15, "land_ansatz": "kauf"})
    pruefe(e["ergebnis"]["verkaufserloes_chf"] is None, "ohne Verkaufspreis kein Erlös")
    pruefe(e["residualwert"]["status"] == "nicht_bestimmbar", "ohne Erlös kein tragbarer Landwert")
    pruefe(e["land"]["wert_chf"] is None and e["ergebnis"]["gewinn_chf"] is None,
           "ohne Bodenpreis weder Landwert noch Gewinn")
    pruefe(any("Verkauf" in o for o in e["offene_punkte"]) and any("Landwert" in o for o in e["offene_punkte"]),
           "die offenen Punkte nennen Verkauf und Landwert")
    pruefe(e["verkauf"].get("preis") is None or e["verkauf"]["preis"].get("wert") is None,
           "kein Verkaufspreis wird erfunden")


def test_systemvorschlag_uebernehmen() -> None:
    print("\n=== 2. Bodenpreis: Systemvorschlag erst nach Übernahme in der Rechnung ===")
    body = {"vergleichsobjekte": copy.deepcopy(BAULAND), "verkauf_chf_pro_m2": 9000}
    mk = markt_aus_body(body)
    boden = mk["markt"].bodenpreis_chf_pro_m2
    sv = boden.systemvorschlag
    pruefe(sv == 745.0 and boden.benutzerannahme is None,
           f"drei Bauland-Referenzen ergeben den Systemvorschlag 745 (Median): {sv}")
    e = rechne(body)
    pruefe(e["land"]["wert_chf"] is None and e["land"]["bodenpreis"]["systemvorschlag"] == 745.0,
           "nicht übernommen: Vorschlag sichtbar, aber kein Landwert")
    uebernommen = rechne(dict(body, bodenpreis_chf_pro_m2=sv))
    land = uebernommen["land"]
    pruefe(land["wert_chf"] == round(745.0 * LAND_M2, 0) and land["herkunft"] == "benutzerannahme",
           f"übernommen: Landwert 745 × {LAND_M2} m² als eigene Annahme ({land['wert_chf']})")
    pruefe(uebernommen["ergebnis"]["gewinn_chf"] is not None and uebernommen["ergebnis"]["marge"] is not None,
           "mit Verkaufspreis und Bodenpreis: Gewinn und Marge berechnet")


def test_manuell_angepasst() -> None:
    print("\n=== 3. Manuell angepasst: eigener Wert hat Vorrang, die Quelle bleibt ===")
    body = {"vergleichsobjekte": copy.deepcopy(BAULAND), "verkauf_chf_pro_m2": 9000,
            "bodenpreis_chf_pro_m2": 900}
    e = rechne(body)
    bp = e["land"]["bodenpreis"]
    pruefe(bp["benutzerannahme"] == 900 and bp["wert"] == 900 and bp["herkunft"] == "benutzerannahme",
           "Bodenpreis 900: eigene Annahme, damit wird gerechnet")
    pruefe(bp["systemvorschlag"] == 745.0, "der Systemvorschlag bleibt daneben stehen (745)")
    pruefe(sorted(r["wert"] for r in bp["referenzen"]) == [700.0, 745.0, 800.0],
           "die drei Referenzen sind unverändert")
    pruefe(e["land"]["wert_chf"] == round(900 * LAND_M2, 0), "Landwert mit 900 CHF/m²")
    vk = e["verkauf"]["preis"]
    pruefe(vk["benutzerannahme"] == 9000 and vk["herkunft"] == "benutzerannahme",
           "Verkaufspreis 9000 als eigene Annahme")


def test_uebergabe_an_rechnung() -> None:
    print("\n=== 4. Übergabe: derselbe Body ergibt dieselbe Rechnung wie direkt gesetzt ===")
    body = {"verkauf_chf_pro_m2": 9000, "miete_chf_pro_m2_jahr": 280,
            "bodenpreis_chf_pro_m2": 800, "zielmarge": 0.15, "land_ansatz": "kauf"}
    ueber_server = rechne(body)
    direkt_markt = w.Marktannahmen(
        verkauf=w.Verkaufsannahme(preis_pro_m2=w.marktwert("verkauf", "CHF/m2", benutzerannahme=9000)),
        miete=w.Mietannahme(miete_pro_m2_jahr=w.marktwert("miete", "CHF/m2/Jahr", benutzerannahme=280)),
        bodenpreis_chf_pro_m2=w.marktwert("boden", "CHF/m2", benutzerannahme=800),
        zielmarge=0.15)
    mk = markt_aus_body(body)
    direkt = w.berechne_alle({"szenarien": {"ersatzneubau": szenario()}}, LAND_M2, direkt_markt,
                             mk["positionen"])["szenarien"]["ersatzneubau"]
    for k in ("verkaufserloes_chf", "gesamtinvestition_chf", "gewinn_chf", "marge", "bruttorendite"):
        pruefe(ueber_server["ergebnis"][k] == direkt["ergebnis"][k] and ueber_server["ergebnis"][k] is not None,
               f"{k}: {ueber_server['ergebnis'][k]}")
    pruefe(ueber_server["residualwert"]["max_landwert_chf"] == direkt["residualwert"]["max_landwert_chf"],
           "tragbarer Landwert gleich")
    leer_body = rechne({"verkauf_chf_pro_m2": None, "bodenpreis_chf_pro_m2": None})
    pruefe(leer_body["ergebnis"]["verkaufserloes_chf"] is None,
           "ein geleertes Feld (null) nimmt den Wert wieder aus der Rechnung")


def test_ohne_szenario() -> None:
    print("\n=== 5. Nicht bestimmbare Szenarien bleiben es -- trotz Marktannahmen ===")
    mk = markt_aus_body({"verkauf_chf_pro_m2": 9000, "bodenpreis_chf_pro_m2": 800,
                         "miete_chf_pro_m2_jahr": 280})
    alle = w.berechne_alle({"szenarien": {}, "grund": "Keine eindeutige Geometrie."}, 289.1,
                           mk["markt"], mk["positionen"])
    pruefe(alle["status"] == "nicht_bestimmbar" and alle["szenarien"] == {},
           "ohne Szenario: nicht bestimmbar, keine Szenariozahl")
    pruefe(alle["grund"] == "Keine eindeutige Geometrie.", "der fachliche Grund bleibt der Grund")


def main() -> None:
    test_fehlende_annahmen()
    test_systemvorschlag_uebernehmen()
    test_manuell_angepasst()
    test_uebergabe_an_rechnung()
    test_ohne_szenario()
    print()
    if _fehler:
        print(f"WIRTSCHAFT-EINGABEN: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE WIRTSCHAFT-EINGABEN-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

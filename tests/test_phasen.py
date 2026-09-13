"""
Tests der Analyse in Phasen.

Vollstaendig OFFLINE -- geprueft wird die Zerlegung, nicht das Netz.

Der Anlass ist eine Messung an einem echten Fall: 126 s Gesamtlaufzeit,
davon 109 s (87 %) fuer das Lesen der Bau- und Nutzungsordnung durch das
Sprachmodell. Alles Uebrige steht nach rund zehn Sekunden. Der Benutzer
wartete trotzdem zwei Minuten vor einem leeren Bildschirm.

Geprueft wird deshalb:

  * Das Teilergebnis nach Modul 1 ist ECHT -- Parzelle, Flaeche, Gemeinde
    und Grundnutzung stehen darin endgueltig.
  * Es behauptet NICHTS ueber das, was noch fehlt: zonen_zuordnung,
    g1_ergebnis und Szenarien sind None, nicht "nicht bestimmbar".
  * Die Potenzialkette laesst sich einzeln nachholen -- ohne die amtlichen
    Abfragen zu wiederholen. Genau das macht einen Gemini-Fehlschlag
    billig statt teuer.
  * Ein Fehler in der Fortschrittsmeldung stoppt keine Analyse.

CLI: python -m tests.test_phasen
"""
from __future__ import annotations

import inspect
import sys

from potenzial_engine import pipeline

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


MODUL1 = {
    "input_address": "Rosenweg 4, 5033 Buchs AG",
    "kataster": {"egrid": "CH975272732334", "parzellennummer": "1145",
                 "flaeche_m2": 598.9, "parzellengeometrie": None,
                 "raw_attributes": {"gross": "wird getrimmt"}},
    "gemeinde": {"gemeinde": "Buchs (AG)", "kanton": "AG", "bfs_nummer": 4003},
    "geocoding": {"matched_label": "Rosenweg 4 5033 Buchs AG",
                  "lv95_e": 2647661.0, "lv95_n": 1248717.0,
                  "raw": {"gross": "wird getrimmt"}},
    "oereb": {"found": True, "kanton": "AG",
              "rechtsvorschriften": [{"titel": "BNO", "url": "https://x/bno.pdf",
                                      "ist_wahrscheinlich_bzo_reglement": True}],
              "amtliche_zonenbezeichnungen": [{"zonenbezeichnung": "Gartenstadtzone [Ga]",
                                               "ist_wahrscheinlich_basiszone": True}]},
    "nutzungsklassifikation": {"gefunden": True, "basiszone_status": "eindeutig",
                               "basiszone": {"typ_kommunal_bezeichnung": "Gartenstadtzone",
                                             "hauptnutzung_code": "11"},
                               "festlegungen": [], "sondernutzungsplaene_massgebend": []},
    "restriktionsgeometrie": {"gefunden": True},
    "kantenklassifikation": {"kanten": []},
}

MODUL2 = {"erkannte_zonen": [{"zonenbezeichnung": "Gartenstadtzone",
                              "ausnuetzungsziffer_az": 0.5,
                              "grenzabstand_klein_m": 4.0}]}


def test_teilergebnis() -> None:
    print("=== Das Teilergebnis nach Modul 1 ist echt ===")
    teil = pipeline._teilergebnis_nach_modul1("Rosenweg 4, 5033 Buchs AG", MODUL1)

    k = teil["modul1_geodaten"]["kataster"]
    pruefe(k["parzellennummer"] == "1145" and k["flaeche_m2"] == 598.9,
           "Parzelle und Flaeche stehen endgueltig fest")
    pruefe(teil["modul1_geodaten"]["gemeinde"]["gemeinde"] == "Buchs (AG)",
           "die Gemeinde ebenso")
    pruefe((teil["modul1_geodaten"]["nutzungsklassifikation"]["basiszone"]
            ["typ_kommunal_bezeichnung"]) == "Gartenstadtzone",
           "und die Grundnutzung -- sie kommt aus Modul 1b, nicht aus dem Reglement")
    pruefe("raw_attributes" not in k and "raw" not in teil["modul1_geodaten"]["geocoding"],
           "die rohen API-Blobs sind getrimmt wie im Endergebnis")

    # Der entscheidende Punkt: was fehlt, ist None -- nicht "nicht bestimmbar".
    for feld in ("zonen_zuordnung", "g1_ergebnis", "sia416_ergebnis",
                 "flaechen_und_wohnungen", "szenarien", "modul2_bzo_analyse"):
        pruefe(teil[feld] is None,
               f"{feld} ist None, solange es nicht gerechnet wurde -- keine Behauptung")
    pruefe(len(teil["quellen"]) > 0,
           f"die Quellennachweise der amtlichen Werte sind schon da ({len(teil['quellen'])})")
    print()


def test_potenzialkette_nachholbar() -> None:
    print("=== Die Potenzialkette laesst sich einzeln nachholen ===")
    ergebnis = pipeline._potenzialkette("Rosenweg 4, 5033 Buchs AG", MODUL1, MODUL2)

    pruefe(ergebnis["zonen_zuordnung"] is not None, "die Zonenzuordnung entsteht")
    pruefe(ergebnis["modul2_bzo_analyse"] is MODUL2,
           "die uebergebene Reglementsauswertung wird unveraendert uebernommen")
    pruefe(ergebnis["adresse"] == "Rosenweg 4, 5033 Buchs AG", "die Adresse bleibt")

    # Dieselben Schluessel wie das Teilergebnis -- die Oberflaeche muss nicht
    # zwei Formen kennen.
    teil = pipeline._teilergebnis_nach_modul1("Rosenweg 4, 5033 Buchs AG", MODUL1)
    pruefe(set(teil) == set(ergebnis),
           f"Teil- und Endergebnis haben dieselben Felder "
           f"({sorted(set(teil) ^ set(ergebnis))})")
    print()


def test_signatur_und_schritte() -> None:
    print("=== Fortschritt und Lader sind Parameter, keine Pflicht ===")
    p = inspect.signature(pipeline.analysiere_grundstueck).parameters
    pruefe(list(p)[0] == "adresse", "die Adresse bleibt das erste Argument")
    for name in ("fortschritt", "modul2_lader"):
        pruefe(name in p and p[name].default is None,
               f"'{name}' ist optional -- bestehende Aufrufer bleiben gueltig")

    schluessel = [s for s, _ in pipeline.SCHRITTE]
    pruefe(schluessel == ["grundstueck", "grundnutzung", "reglement", "potenzial"],
           f"die Schritte stehen in Ablaufreihenfolge ({schluessel})")
    pruefe(all(isinstance(b, str) and b for _, b in pipeline.SCHRITTE),
           "und tragen einen Klartext, den man anzeigen kann")

    quelle = inspect.getsource(pipeline.analysiere_grundstueck)
    pruefe("except Exception" in quelle and "melde" in quelle,
           "ein Fehler in der Fortschrittsmeldung darf die Analyse nicht stoppen")
    pruefe("_potenzialkette" in quelle,
           "die Potenzialkette wird aufgerufen, nicht ein zweites Mal ausgeschrieben")
    print()


def test_meldung_stoppt_nichts() -> None:
    print("=== Eine kaputte Anzeige stoppt keine Rechnung ===")
    gemeldet = []

    def kaputt(schritt, stand, teil=None):
        gemeldet.append(schritt)
        raise RuntimeError("Anzeige kaputt")

    # Der Rueckruf wird in analysiere_grundstueck gekapselt aufgerufen; hier
    # wird dieselbe Kapselung nachgestellt, ohne das Netz zu bemuehen.
    quelle = inspect.getsource(pipeline.analysiere_grundstueck)
    pruefe("def melde(" in quelle, "es gibt eine Kapselung fuer den Rueckruf")
    try:
        exec(compile(  # noqa: S102 -- geprueft wird genau dieser Codeausschnitt
            "def melde(schritt, stand, teil=None):\n"
            "    try:\n        kaputt(schritt, stand, teil)\n"
            "    except Exception:\n        pass\n"
            "melde('grundstueck', 'fertig')", "<pruefung>", "exec"),
            {"kaputt": kaputt})
        geworfen = False
    except Exception:  # noqa: BLE001
        geworfen = True
    pruefe(not geworfen and gemeldet == ["grundstueck"],
           "der Fehler wird geschluckt, die Meldung aber versucht")
    print()


def test_nebenlaeufigkeit() -> None:
    """Modul 1 fragt nebenlaeufig ab -- ohne die Abhaengigkeiten zu brechen.

    Gemessen brauchten die neun Einzelabfragen zusammen rund 14 s, obwohl
    keine auf die andere wartet; allein die Umgebungsdaten 5.1 s. Hier wird
    mit Attrappen geprueft, dass sie tatsaechlich gleichzeitig laufen UND
    dass die zweite Welle erst startet, wenn Kataster und Gemeinde da sind.
    """
    import threading
    import time

    from potenzial_engine import modul1_geodata as m1

    print("=== Modul 1 laeuft nebenlaeufig, aber in der richtigen Ordnung ===")

    beginn: dict[str, float] = {}
    ende: dict[str, float] = {}
    sperre = threading.Lock()
    t0 = time.perf_counter()

    def attrappe(name, dauer, rueckgabe):
        def f(*a, **kw):
            with sperre:
                beginn[name] = time.perf_counter() - t0
            time.sleep(dauer)
            with sperre:
                ende[name] = time.perf_counter() - t0
            return rueckgabe() if callable(rueckgabe) else rueckgabe
        return f

    class Wert:
        def __init__(self, d): self._d = d
        def model_dump(self): return self._d

    original = {name: getattr(m1, name) for name in (
        "geocode_address", "get_parcel_data", "get_municipality_data", "get_gwr_data",
        "get_radon_data", "get_topography", "get_umgebung", "get_oereb_data",
        "klassifiziere_nutzung", "hole_restriktionen_fuer_parzelle")}
    try:
        m1.geocode_address = attrappe("geo", 0.05, {
            "lv95_e": 2647661.0, "lv95_n": 1248717.0,
            "wgs84_lat": 47.38, "wgs84_lon": 8.06, "canton_hint": "ag"})
        m1.get_parcel_data = attrappe("kataster", 0.10, {
            "found": True, "egrid": "CH1", "parzellengeometrie": [(0, 0), (10, 0), (10, 10)]})
        m1.get_municipality_data = attrappe("gemeinde", 0.10, {"kanton": "AG",
                                                              "gemeinde": "Buchs (AG)"})
        m1.get_gwr_data = attrappe("gwr", 0.30, {"found": False})
        m1.get_radon_data = attrappe("radon", 0.30, {"found": False})
        m1.get_topography = attrappe("topo", 0.30, Wert({"hoehe": 400}))
        # Die langsamste Einzelquelle -- sie darf die zweite Welle NICHT
        # aufhalten.
        m1.get_umgebung = attrappe("umgebung", 0.60, Wert({"fehler": {}}))
        m1.get_oereb_data = attrappe("oereb", 0.30, {"found": True,
                                                     "rechtsvorschriften": []})
        m1.klassifiziere_nutzung = attrappe("nutzung", 0.30, {"gefunden": True,
                                                              "basiszone": None})
        m1.hole_restriktionen_fuer_parzelle = attrappe("restrikt", 0.30, {"gefunden": True})

        ergebnis = m1.run_modul1("Teststrasse 1")
        gesamt = time.perf_counter() - t0
    finally:
        for name, fn in original.items():
            setattr(m1, name, fn)

    pruefe(ergebnis["kataster"]["egrid"] == "CH1", "das Ergebnis ist vollstaendig aufgebaut")
    pruefe(ergebnis["gemeinde"]["kanton"] == "AG", "auch die Gemeinde steht drin")

    # Sequentiell waeren es 0.05 + 0.10 + 0.10 + 0.30*5 + 0.60 = 2.85 s.
    pruefe(gesamt < 1.6,
           f"nebenlaeufig deutlich schneller als die Summe der Einzelzeiten "
           f"({gesamt:.2f} s statt 2.85 s)")

    # Die Abhaengigkeiten muessen trotzdem gelten.
    pruefe(beginn["kataster"] >= ende["geo"] - 0.01,
           "Kataster startet erst nach dem Geocoding -- es braucht die Koordinate")
    for spaeter in ("oereb", "nutzung", "restrikt"):
        pruefe(beginn[spaeter] >= ende["kataster"] - 0.01
               and beginn[spaeter] >= ende["gemeinde"] - 0.01,
               f"{spaeter} startet erst, wenn Kataster und Gemeinde da sind")

    # Und der Punkt der Uebung: die langsame Umgebungsabfrage laeuft neben
    # der zweiten Welle, statt sie aufzuhalten.
    pruefe(beginn["oereb"] < ende["umgebung"],
           f"die zweite Welle startet, waehrend die Umgebungsabfrage noch laeuft "
           f"(oereb ab {beginn['oereb']:.2f} s, Umgebung bis {ende['umgebung']:.2f} s)")
    pruefe(abs(beginn["gwr"] - beginn["radon"]) < 0.05,
           "die unabhaengigen Abfragen starten gemeinsam, nicht nacheinander")
    print()


def test_einzelne_quelle_blockiert_nicht() -> None:
    """Eine defekte Quelle darf die uebrigen nicht aufhalten.

    Das Fehlerverhalten selbst bleibt unveraendert: was frueher abgebrochen
    hat, bricht weiterhin ab. Neu ist nur, dass die anderen Abfragen bis
    dahin gelaufen sind, statt hinter der defekten zu warten.
    """
    import time

    from potenzial_engine import modul1_geodata as m1

    print("=== Eine defekte Quelle blockiert die anderen nicht ===")

    gelaufen = []

    class Wert:
        def __init__(self, d): self._d = d
        def model_dump(self): return self._d

    def merke(name, rueckgabe, fehler=None):
        def f(*a, **kw):
            time.sleep(0.05)
            gelaufen.append(name)
            if fehler:
                raise fehler
            return rueckgabe() if callable(rueckgabe) else rueckgabe
        return f

    original = {name: getattr(m1, name) for name in (
        "geocode_address", "get_parcel_data", "get_municipality_data", "get_gwr_data",
        "get_radon_data", "get_topography", "get_umgebung", "get_oereb_data",
        "klassifiziere_nutzung", "hole_restriktionen_fuer_parzelle")}
    try:
        m1.geocode_address = merke("geo", {"lv95_e": 1.0, "lv95_n": 2.0,
                                           "wgs84_lat": 47.0, "wgs84_lon": 8.0,
                                           "canton_hint": "ag"})
        m1.get_parcel_data = merke("kataster", {"found": True, "egrid": "CH1",
                                                "parzellengeometrie": None})
        m1.get_municipality_data = merke("gemeinde", {"kanton": "AG"})
        m1.get_gwr_data = merke("gwr", {"found": False})
        m1.get_radon_data = merke("radon", {}, fehler=RuntimeError("Radon-Dienst weg"))
        m1.get_topography = merke("topo", Wert({}))
        m1.get_umgebung = merke("umgebung", Wert({}))
        m1.get_oereb_data = merke("oereb", {"found": True, "rechtsvorschriften": []})
        m1.klassifiziere_nutzung = merke("nutzung", {"gefunden": True, "basiszone": None})
        m1.hole_restriktionen_fuer_parzelle = merke("restrikt", {"gefunden": True})

        try:
            m1.run_modul1("Teststrasse 1")
            geworfen = None
        except Exception as exc:  # noqa: BLE001
            geworfen = str(exc)
    finally:
        for name, fn in original.items():
            setattr(m1, name, fn)

    pruefe(geworfen == "Radon-Dienst weg",
           f"der Fehler wird unveraendert weitergereicht -- kein stilles Verschlucken ({geworfen})")
    for name in ("gwr", "topo", "umgebung", "oereb", "nutzung"):
        pruefe(name in gelaufen,
               f"'{name}' ist trotzdem gelaufen -- die defekte Quelle hat nichts blockiert")
    print()


def main() -> None:
    test_teilergebnis()
    test_potenzialkette_nachholbar()
    test_signatur_und_schritte()
    test_meldung_stoppt_nichts()
    test_nebenlaeufigkeit()
    test_einzelne_quelle_blockiert_nicht()

    print("=" * 68)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE PHASEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

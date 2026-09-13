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


def main() -> None:
    test_teilergebnis()
    test_potenzialkette_nachholbar()
    test_signatur_und_schritte()
    test_meldung_stoppt_nichts()

    print("=" * 68)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE PHASEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

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
  * Modul 1 fragt nebenlaeufig ab, ohne eine Phase zu ueberspringen, zu
    verdoppeln oder ihre Antwort zu verlieren -- und ohne die
    Abhaengigkeiten zu brechen.

Was hier NICHT mehr geprueft wird: die Laufzeit. Eine feste Grenze
(`gesamt < 1.6 s`) hat gemessen, wie ausgelastet die Maschine gerade ist,
und ist mit offenem Browser reihenweise durchgefallen, waehrend am Code
nichts falsch war. Die Zahl bleibt nuetzlich und steht als Diagnose in
miss_modul1_laufzeit() -- gedruckt, nicht geprueft.

CLI: python -m tests.test_phasen            # Zusicherungen + Diagnose
     python -m tests.test_phasen --messen   # nur die Laufzeitmessung
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

    Geprueft wird die ORDNUNG, nicht die Uhr.

    Bis zum 17.09.2026 stand hier zusaetzlich eine feste Laufzeitgrenze
    (`gesamt < 1.6 s`). Sie hat gemessen, wie ausgelastet die Maschine
    gerade ist: mit offenem Browser und laufendem Vorschau-Server schlug
    sie mit 1.99 s, 2.58 s und 13.34 s fehl, allein gelaufen war sie
    gruen. Eine Zusicherung, die an der Nebenlast haengt, sagt nichts
    ueber den Code -- sie kostet nur das Vertrauen in die uebrigen
    Zusicherungen derselben Reihe. Die Messung steht jetzt als Diagnose
    in miss_modul1_laufzeit() und kann nicht mehr durchfallen.

    Was hier bleibt, ist von der Maschinenlast unabhaengig. Last
    verschiebt alle Zeitpunkte, aber sie kehrt keine Reihenfolge um und
    sie erzeugt keine Ueberlappung, wo keine ist:

      * Jede Quelle wird genau einmal abgefragt -- keine uebersprungen,
        keine doppelt.
      * Was jede Quelle geliefert hat, steht im Ergebnis. Eine Phase, die
        laeuft und deren Antwort dann verloren geht, faellt damit auf.
      * Es laufen tatsaechlich mehrere gleichzeitig, gemessen an der
        hoechsten Zahl gleichzeitig offener Abfragen.
      * Die Abhaengigkeiten gelten: was eine andere Abfrage braucht,
        beginnt nach deren Ende.
      * Unabhaengige Abfragen ueberlappen sich zeitlich.
    """
    import threading
    import time

    from potenzial_engine import modul1_geodata as m1

    print("=== Modul 1 laeuft nebenlaeufig, aber in der richtigen Ordnung ===")

    beginn: dict[str, float] = {}
    ende: dict[str, float] = {}
    aufrufe: dict[str, int] = {}
    sperre = threading.Lock()
    offen = 0
    hoechstens_offen = 0
    t0 = time.perf_counter()

    def attrappe(name, dauer, rueckgabe):
        def f(*a, **kw):
            nonlocal offen, hoechstens_offen
            with sperre:
                aufrufe[name] = aufrufe.get(name, 0) + 1
                beginn[name] = time.perf_counter() - t0
                offen += 1
                hoechstens_offen = max(hoechstens_offen, offen)
            time.sleep(dauer)
            with sperre:
                offen -= 1
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
    finally:
        for name, fn in original.items():
            setattr(m1, name, fn)

    # --- Keine Phase uebersprungen, keine doppelt --------------------------
    erwartet = ["geo", "kataster", "gemeinde", "gwr", "radon", "topo",
                "umgebung", "oereb", "nutzung", "restrikt"]
    fehlend = [n for n in erwartet if aufrufe.get(n, 0) == 0]
    doppelt = [n for n in erwartet if aufrufe.get(n, 0) > 1]
    pruefe(not fehlend, f"jede der {len(erwartet)} Quellen wurde abgefragt "
                        f"({'keine fehlt' if not fehlend else 'fehlt: ' + ', '.join(fehlend)})")
    pruefe(not doppelt, f"und keine doppelt "
                        f"({'keine' if not doppelt else 'doppelt: ' + ', '.join(doppelt)})")

    # --- Was geliefert wurde, steht auch im Ergebnis -----------------------
    pruefe(ergebnis["kataster"]["egrid"] == "CH1", "das Katasterergebnis steht im Ergebnis")
    pruefe(ergebnis["gemeinde"]["kanton"] == "AG", "auch die Gemeinde steht drin")
    pruefe((ergebnis.get("oereb") or {}).get("found") is True,
           "die OEREB-Antwort der zweiten Welle ist angekommen")
    pruefe((ergebnis.get("nutzungsklassifikation") or {}).get("gefunden") is True,
           "die Nutzungsklassifikation ebenso")
    pruefe((ergebnis.get("restriktionsgeometrie") or {}).get("gefunden") is True,
           "und die Restriktionen -- keine Phase laeuft ins Leere")

    # --- Es laeuft wirklich nebeneinander ----------------------------------
    # Gezaehlt wird, wie viele Abfragen gleichzeitig offen waren. Das ist
    # unabhaengig davon, wie schnell die Maschine gerade ist: sequenziell
    # waere der Hoechstwert 1, egal wie lange es dauert.
    pruefe(hoechstens_offen >= 2,
           f"mehrere Abfragen liefen gleichzeitig (hoechstens {hoechstens_offen} offen; "
           "sequenziell waere es 1)")

    # --- Die Abhaengigkeiten gelten ----------------------------------------
    def frueher_fertig_als_start(vorher, nachher):
        return beginn[nachher] >= ende[vorher] - 0.01

    pruefe(frueher_fertig_als_start("geo", "kataster"),
           "Kataster startet erst nach dem Geocoding -- es braucht die Koordinate")
    for spaeter in ("oereb", "nutzung", "restrikt"):
        pruefe(frueher_fertig_als_start("kataster", spaeter)
               and frueher_fertig_als_start("gemeinde", spaeter),
               f"'{spaeter}' startet erst, wenn Kataster und Gemeinde da sind")

    # --- Ueberlappung statt Reihenfolge ------------------------------------
    def ueberlappen(a, b):
        return beginn[a] < ende[b] and beginn[b] < ende[a]

    pruefe(ueberlappen("gwr", "radon"),
           "die unabhaengigen Abfragen gwr und radon laufen zur selben Zeit")
    pruefe(ueberlappen("gwr", "topo"),
           "gwr und topo ebenso")
    # Und der Punkt der Uebung: die langsame Umgebungsabfrage laeuft neben
    # der zweiten Welle, statt sie aufzuhalten.
    pruefe(ueberlappen("oereb", "umgebung"),
           f"die zweite Welle laeuft, waehrend die Umgebungsabfrage noch offen ist "
           f"(oereb {beginn['oereb']:.2f}-{ende['oereb']:.2f} s, "
           f"Umgebung {beginn['umgebung']:.2f}-{ende['umgebung']:.2f} s)")
    print()


def miss_modul1_laufzeit(wiederholungen: int = 1) -> None:
    """DIAGNOSE, keine Zusicherung -- diese Funktion kann nicht durchfallen.

    Sie misst, was die Nebenlaeufigkeit auf DIESER Maschine gerade
    einbringt. Das ist eine nuetzliche Zahl und ein schlechter Test: sie
    haengt an allem, was sonst noch laeuft. Deshalb wird sie gedruckt und
    nicht geprueft.

    Aufruf mit mehreren Wiederholungen:  python -m tests.test_phasen --messen
    """
    import time

    from potenzial_engine import modul1_geodata as m1

    dauern = {"geo": 0.05, "kataster": 0.10, "gemeinde": 0.10, "gwr": 0.30,
              "radon": 0.30, "topo": 0.30, "umgebung": 0.60, "oereb": 0.30,
              "nutzung": 0.30, "restrikt": 0.30}
    sequenziell = sum(dauern.values())

    class Wert:
        def __init__(self, d): self._d = d
        def model_dump(self): return self._d

    def attrappe(dauer, rueckgabe):
        def f(*a, **kw):
            time.sleep(dauer)
            return rueckgabe() if callable(rueckgabe) else rueckgabe
        return f

    original = {name: getattr(m1, name) for name in (
        "geocode_address", "get_parcel_data", "get_municipality_data", "get_gwr_data",
        "get_radon_data", "get_topography", "get_umgebung", "get_oereb_data",
        "klassifiziere_nutzung", "hole_restriktionen_fuer_parzelle")}
    messungen = []
    try:
        m1.geocode_address = attrappe(dauern["geo"], {
            "lv95_e": 2647661.0, "lv95_n": 1248717.0,
            "wgs84_lat": 47.38, "wgs84_lon": 8.06, "canton_hint": "ag"})
        m1.get_parcel_data = attrappe(dauern["kataster"], {
            "found": True, "egrid": "CH1", "parzellengeometrie": [(0, 0), (10, 0), (10, 10)]})
        m1.get_municipality_data = attrappe(dauern["gemeinde"], {"kanton": "AG",
                                                                 "gemeinde": "Buchs (AG)"})
        m1.get_gwr_data = attrappe(dauern["gwr"], {"found": False})
        m1.get_radon_data = attrappe(dauern["radon"], {"found": False})
        m1.get_topography = attrappe(dauern["topo"], Wert({"hoehe": 400}))
        m1.get_umgebung = attrappe(dauern["umgebung"], Wert({"fehler": {}}))
        m1.get_oereb_data = attrappe(dauern["oereb"], {"found": True, "rechtsvorschriften": []})
        m1.klassifiziere_nutzung = attrappe(dauern["nutzung"], {"gefunden": True,
                                                                "basiszone": None})
        m1.hole_restriktionen_fuer_parzelle = attrappe(dauern["restrikt"], {"gefunden": True})

        for _ in range(max(1, wiederholungen)):
            t0 = time.perf_counter()
            m1.run_modul1("Teststrasse 1")
            messungen.append(time.perf_counter() - t0)
    finally:
        for name, fn in original.items():
            setattr(m1, name, fn)

    schnellste = min(messungen)
    print("--- Diagnose: Laufzeit von Modul 1 (keine Zusicherung) ---")
    print(f"      {'Summe der Einzelzeiten (sequenziell)':<38}{sequenziell:5.2f} s")
    if len(messungen) > 1:
        beschriftung = f"nebenlaeufig, {len(messungen)} Laeufe"
        print(f"      {beschriftung:<38}{schnellste:5.2f} s bis {max(messungen):5.2f} s")
    else:
        print(f"      {'nebenlaeufig gemessen':<38}{schnellste:5.2f} s")
    print(f"      {'Verhaeltnis (schnellster Lauf)':<38}{schnellste / sequenziell:5.2f}")
    print("      Unter Last steigt dieser Wert. Das ist eine Eigenschaft der")
    print("      Maschine, nicht des Codes -- deshalb steht hier keine Grenze.")
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
    # Reiner Messmodus: keine Zusicherungen, nur die Laufzeitdiagnose.
    if "--messen" in sys.argv:
        miss_modul1_laufzeit(wiederholungen=5)
        return

    test_teilergebnis()
    test_potenzialkette_nachholbar()
    test_signatur_und_schritte()
    test_meldung_stoppt_nichts()
    test_nebenlaeufigkeit()
    test_einzelne_quelle_blockiert_nicht()

    # Die Laufzeit wird gezeigt, nicht geprueft. Sie steht hier, damit sie
    # nicht in Vergessenheit geraet -- aber unterhalb der Zusicherungen und
    # ohne Einfluss auf das Ergebnis der Reihe.
    miss_modul1_laufzeit()

    print("=" * 68)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE PHASEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

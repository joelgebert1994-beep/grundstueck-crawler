"""
Adresse -> Grundstueck: eine Eingabe ergibt reproduzierbar dasselbe
Grundstueck, und eine nicht passende Eingabe ergibt KEINES.

Anlass (30.09.2026, Weiningen ZH): Eingegeben wurde "Horgenwiesstrasse 1,
8104 Weiningen ZH" -- die Strasse heisst "Hogerwiesstrasse". Ein Lauf
analysierte "Puentenstrasse 2b", Parzelle 3285, Kernzone; korrekt waere
Parzelle 1784, W2 30 gewesen, rund 600 m entfernt. Ursache war keine
Parzellenlogik, sondern die Adressauswahl:

  * das Backend nahm von der Suche ungeprueft results[0]
  * es suchte denselben Text zweimal (Zwischenspeicher + Analyse)
  * die angeklickte Adresse kam nur als Text an, ohne ihre Kennung

Gerechnet wird mit ECHTEN Antworten des Suchdienstes und des GWR, am
30.09.2026 eingefroren (tests/daten/adresse/), und mit den echten
Funktionen aus modul1_geodata.py und webapp.py. Nachgebaut wird nur der
Netzzugriff.

A  Hogerwiesstrasse 1 zweimal -> identisch
B  Neuladen (Textweg ohne Auswahl) -> identisch, auch zur Auswahl
C  andere Adresse, dann wieder Hogerwiesstrasse 1 -> identisch
D  "Horgenwiesstrasse 1" -> NICHT still Puentenstrasse 2b
E  (verspaetete Suchantwort -> tests/js/adresssuche.test.js)
F  mehrere Treffer -> kein blindes results[0]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import potenzial_engine.modul1_geodata as m1  # noqa: E402

DATEN = Path(__file__).parent / "daten" / "adresse"

SUCHE = {
    "Horgenwiesstrasse 1, 8104 Weiningen ZH": "suche_horgenwiesstrasse_voll_limit10.json",
    "Horgenwiesstrasse 1, 8104": "suche_horgenwiesstrasse_teil_limit10.json",
    "Hogerwiesstrasse 1 8104 Weiningen ZH": "suche_hogerwiesstrasse_limit10.json",
    "Püntenstrasse 2b 8104 Weiningen ZH": "suche_puentenstrasse_limit10.json",
    "Bahnhofstrasse 1": "suche_bahnhofstrasse_ohne_plz_limit10.json",
    "Rosenweg 4, 5033 Buchs": "suche_rosenweg_buchs_limit10.json",
}
GWR = {"123952_0": "gwr_123952_0.json"}

HOGERWIES = "Hogerwiesstrasse 1 8104 Weiningen ZH"
HOGERWIES_ID = "123952_0"
HOGERWIES_E, HOGERWIES_N = 2675063.688000001, 1252760.8539999984
PUENTEN_E, PUENTEN_N = 2675481.0, 1252335.375

_ok = 0
_fehler: list[str] = []
_abrufe: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)
        print(f"[FEHL] {was}")


def _lade(name: str) -> dict:
    return json.loads((DATEN / name).read_text(encoding="utf-8"))


def _eingefroren(url: str, params: dict, timeout=None) -> dict:
    """Ersetzt nur den Netzzugriff -- alles Uebrige ist echter Code."""
    if url.endswith("/SearchServer"):
        _abrufe.append("suche:" + params["searchText"])
        return _lade(SUCHE[params["searchText"]])
    kennung = url.rsplit("/", 1)[-1]
    _abrufe.append("gwr:" + kennung)
    if kennung not in GWR:
        raise RuntimeError(f"404 fuer {kennung}")
    return _lade(GWR[kennung])


def _parzellenmerkmal(geo: dict) -> tuple:
    """Was die Parzellenwahl bekommt: genau der Punkt (und die Kennung)."""
    return (geo["feature_id"], round(geo["lv95_e"], 1), round(geo["lv95_n"], 1))


def test_a_b_c_reproduzierbar() -> None:
    print("\n=== A/B/C: dieselbe Adresse ergibt denselben Punkt ===")
    a1 = m1.geocode_address(HOGERWIES)
    a2 = m1.geocode_address(HOGERWIES)
    pruefe(_parzellenmerkmal(a1) == _parzellenmerkmal(a2),
           "A: Hogerwiesstrasse 1 zweimal -> identischer Punkt und identische Kennung")
    pruefe(a1["feature_id"] == HOGERWIES_ID and a1["auswahlmethode"] == "text_exakt",
           f"A: es ist der exakte Treffer {HOGERWIES_ID}")

    auswahl = m1.geocode_auswahl(HOGERWIES, HOGERWIES_ID, HOGERWIES_E, HOGERWIES_N)
    pruefe(_parzellenmerkmal(auswahl) == _parzellenmerkmal(a1),
           "B: Neuladen (Text ohne Auswahl) und bewusste Auswahl ergeben denselben Punkt")
    pruefe(auswahl["auswahlmethode"] == "auswahl_kennung",
           "B: die Auswahl wird ueber ihre Kennung aufgeloest, nicht ueber den Text")

    m1.geocode_address("Rosenweg 4, 5033 Buchs")
    c = m1.geocode_address(HOGERWIES)
    pruefe(_parzellenmerkmal(c) == _parzellenmerkmal(a1),
           "C: nach einer anderen Adresse wieder Hogerwiesstrasse 1 -> identisch")


def test_d_falsche_schreibweise() -> None:
    print("\n=== D: 'Horgenwiesstrasse 1' waehlt nichts still aus ===")
    for eingabe in ("Horgenwiesstrasse 1, 8104 Weiningen ZH", "Horgenwiesstrasse 1, 8104"):
        try:
            geo = m1.geocode_address(eingabe)
            pruefe(False, f"D: {eingabe!r} haette nichts waehlen duerfen, waehlte {geo['matched_label']!r}")
            continue
        except m1.AdresseNichtEindeutig as exc:
            pruefe(exc.art == "nicht_gefunden", f"D: {eingabe!r} -> 'keine passende Adresse'")
            pruefe(all(k["passung"] == "andere_strasse" for k in exc.kandidaten),
                   "D: alle Vorschlaege sind als 'andere Strasse' gekennzeichnet")
            pruefe("Keine passende Adresse" in str(exc), "D: die Meldung sagt es in Klartext")
            if eingabe.endswith("8104"):
                erster = exc.kandidaten[0]["label"]
                pruefe(erster.startswith("Püntenstrasse 2b"),
                       "D: der erste Suchtreffer ist tatsaechlich Puentenstrasse 2b ...")
                pruefe(True, "D: ... und wurde NICHT gewaehlt -- kein blindes results[0]")


def test_f_mehrdeutig() -> None:
    print("\n=== F: mehrere passende Treffer -> keine stille Wahl ===")
    try:
        geo = m1.geocode_address("Bahnhofstrasse 1")
        pruefe(False, f"F: 'Bahnhofstrasse 1' ohne PLZ waehlte still {geo['matched_label']!r}")
    except m1.AdresseNichtEindeutig as exc:
        pruefe(exc.art == "mehrdeutig", "F: 'Bahnhofstrasse 1' ohne PLZ -> mehrdeutig")
        pruefe(len(exc.kandidaten) > 1 and all(k["passung"] == "exakt" for k in exc.kandidaten),
               f"F: {len(exc.kandidaten)} passende Adressen werden zur Auswahl genannt")

    r = m1.geocode_address("Rosenweg 4, 5033 Buchs")
    pruefe(r["matched_label"] == "Rosenweg 4 5033 Buchs AG",
           "F: 'Rosenweg 4' ist eindeutig -- 4.1 und 4.2 sind andere Hausnummern")


def test_auswahl_kennung() -> None:
    print("\n=== Bewusste Auswahl: Kennung + Koordinate ===")
    try:
        m1.geocode_auswahl(HOGERWIES, HOGERWIES_ID, PUENTEN_E, PUENTEN_N)
        pruefe(False, "eine Kennung mit 600 m entfernter Koordinate darf nicht angenommen werden")
    except m1.AdresseNichtEindeutig:
        pruefe(False, "falscher Fehlertyp")
    except m1.Modul1Error as exc:
        pruefe("entfernt" in str(exc), "Kennung und Koordinate passen nicht -> abgelehnt, nichts analysiert")

    # Findet die Suche die Kennung nicht, wird sie direkt im GWR aufgeloest.
    _abrufe.clear()
    geo = m1.geocode_auswahl("Püntenstrasse 2b 8104 Weiningen ZH", HOGERWIES_ID,
                             HOGERWIES_E, HOGERWIES_N)
    pruefe(geo["auswahlmethode"] == "auswahl_kennung_gwr",
           "Kennung nicht im Suchergebnis -> Rueckfall auf das GWR, nicht auf einen Suchtreffer")
    pruefe(abs(geo["lv95_e"] - 2675063.7) < 0.5 and abs(geo["lv95_n"] - 1252760.9) < 0.5,
           "der Punkt kommt aus dem GWR-Datensatz der gewaehlten Kennung")
    pruefe(abs(geo["wgs84_lat"] - 47.42137) < 0.0002 and abs(geo["wgs84_lon"] - 8.43341) < 0.0002,
           "WGS84 aus der Naeherungsformel stimmt mit dem Suchdienst ueberein")

    # Auch im GWR-Rueckfall: Kennung mit entfernter Koordinate wird abgewiesen.
    try:
        m1.geocode_auswahl("Püntenstrasse 2b 8104 Weiningen ZH", HOGERWIES_ID, PUENTEN_E, PUENTEN_N)
        pruefe(False, "GWR-Rueckfall: Kennung mit 600 m entfernter Koordinate darf nicht angenommen werden")
    except m1.Modul1Error as exc:
        pruefe("laut GWR" in str(exc) and "entfernt" in str(exc),
               "GWR-Rueckfall: Kennung und Koordinate passen nicht -> abgelehnt")


def test_nur_einmal_gesucht() -> None:
    print("\n=== Die Adresse wird genau einmal aufgeloest ===")
    import webapp

    gesehen: dict = {}

    class Abbruch(Exception):
        pass

    def analyse_attrappe(adresse, **kw):
        gesehen["geo"] = kw.get("geo")
        raise Abbruch()

    alt_analyse, alt_kern = webapp.analysiere_grundstueck, webapp._kern_projekt
    webapp.analysiere_grundstueck = analyse_attrappe
    webapp._kern_projekt = lambda: (None, None)
    try:
        for name, auswahl in (("mit Auswahl", {"feature_id": HOGERWIES_ID, "lv95_e": HOGERWIES_E,
                                                "lv95_n": HOGERWIES_N}),
                              ("ohne Auswahl", None)):
            job = f"test-{name}"
            webapp._JOBS[job] = {"status": "running", "schritte": [], "reglement": {}}
            _abrufe.clear()
            gesehen.clear()
            webapp.Handler._job_ausfuehren(_Selbst(), job, HOGERWIES, None, None, False, auswahl)
            suchen = [a for a in _abrufe if a.startswith("suche:")]
            pruefe(len(suchen) == 1, f"{name}: genau eine Suche (vorher zwei) -- {suchen}")
            pruefe((gesehen.get("geo") or {}).get("feature_id") == HOGERWIES_ID,
                   f"{name}: die Analyse bekommt die aufgeloeste Adresse durchgereicht")

        job = "test-falsch"
        webapp._JOBS[job] = {"status": "running", "schritte": [], "reglement": {}}
        gesehen.clear()
        webapp.Handler._job_ausfuehren(_Selbst(), job, "Horgenwiesstrasse 1, 8104", None, None,
                                       False, None)
        j = webapp._JOBS[job]
        pruefe(j["status"] == "error" and (j.get("adresswahl") or {}).get("art") == "nicht_gefunden",
               "falsche Schreibweise -> Auftrag endet mit Adresswahl statt Analyse")
        pruefe("geo" not in gesehen, "und die Analyse wurde gar nicht erst aufgerufen")
        pruefe(not any(k["label"].startswith("Püntenstrasse") and k["passung"] == "exakt"
                       for k in j["adresswahl"]["kandidaten"]),
               "Puentenstrasse 2b steht hoechstens als 'andere Strasse' zur Auswahl")
    finally:
        webapp.analysiere_grundstueck, webapp._kern_projekt = alt_analyse, alt_kern


def test_gwr_heizung() -> None:
    """Derselbe eingefrorene GWR-Datensatz: Heizung und Warmwasser.

    Gehoert inhaltlich zum GWR, nicht zur Adresswahl -- steht hier, weil der
    Datensatz derselbe ist. Geprueft wird nur das Auslesen; uebersetzt wird
    in der Oberflaeche (tests/js/heizung.test.js).
    """
    print("\n=== GWR: Heizung und Warmwasser werden ausgelesen, nicht ergaenzt ===")
    attrs = _lade("gwr_123952_0.json")["feature"]["properties"]
    h = m1._waermeangabe(attrs, "gwaerzh1", "genh1", "gwaersceh1", "gwaerdath1")
    pruefe(h == {"waermeerzeuger_code": 7430, "energiequelle_code": 7530,
                 "informationsquelle_code": 860, "aktualisiert_am": "29.11.2001"},
           "Heizung: Heizkessel 7430, Heizoel 7530, Quelle 860, Angabe vom 29.11.2001")
    pruefe(m1._waermeangabe(attrs, "gwaerzh2", "genh2", "gwaersceh2", "gwaerdath2") is None,
           "keine zweite Heizung im Register -> None, nichts ergaenzt")
    w = m1._waermeangabe(attrs, "gwaerzw1", "genw1", "gwaerscew1", "gwaerdatw1")
    pruefe((w or {}).get("waermeerzeuger_code") == 7650 and (w or {}).get("aktualisiert_am") == "23.04.2026",
           "Warmwasser: Code 7650, Angabe vom 23.04.2026")


class _Selbst:
    """Nur die zwei Methoden, die _job_ausfuehren am Handler braucht."""

    def _zwischenspeicher_suchen(self, adresse, geo=None):
        import webapp
        return webapp.Handler._zwischenspeicher_suchen(self, adresse, geo)

    def _zwischenspeicher_ablegen(self, egrid, ergebnis):
        return None


def main() -> int:
    alt = m1._get
    m1._get = _eingefroren
    try:
        for fn in (test_a_b_c_reproduzierbar, test_d_falsche_schreibweise, test_f_mehrdeutig,
                   test_auswahl_kennung, test_nur_einmal_gesucht, test_gwr_heizung):
            fn()
    finally:
        m1._get = alt
    print()
    if _fehler:
        print(f"ADRESSWAHL: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print("  NICHT ERFUELLT:", f)
        return 1
    print(f"ALLE ADRESSWAHL-TESTS BESTANDEN ({_ok} OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

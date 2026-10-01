"""Standort & Energie: Naehe, OeV-Gueteklasse, Solar, Restriktions-Fehler.

Anlass (01.10.2026, Hogerwiesstrasse 1, 8104 Weiningen ZH):

  - Das Dossier nannte als naechste Schule eine Tagesvorschule in 1255 m.
    Die Primarschule Weiningen liegt 378 m entfernt -- in OpenStreetMap als
    FLAECHE erfasst, und gesucht wurden nur Punkte ("node").
  - Neu: OeV-Gueteklasse (ARE), Bahnhof, Kindergarten; Solareignung des
    Daches (BFE, Modell) getrennt von der im Register erfassten Anlage
    (BFE, exakt ueber die EGID).
  - Eine gescheiterte Restriktionsabfrage stand in der Uebersicht wie
    "geprueft, nicht betroffen". Jetzt traegt das Ergebnis `fehler`.

Alle Antworten sind am 01.10.2026 eingefrorene ECHTE Antworten der Dienste
(tests/daten/standort). Ersetzt wird nur der Netzzugriff.

Aufruf: python -m tests.test_standort_energie
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine import modul1_geodata as m1  # noqa: E402
from potenzial_engine import quellen as q  # noqa: E402
from potenzial_engine import restriktionsgeometrie as rg  # noqa: E402

DATEN = Path(__file__).resolve().parent / "daten" / "standort"
OVERPASS = json.loads((DATEN / "overpass_hogerwies.json").read_text(encoding="utf-8"))
GEOADMIN = json.loads((DATEN / "geoadmin_hogerwies.json").read_text(encoding="utf-8"))

E, N = 2675063.688, 1252760.854
LAT, LON = 47.42137, 8.43341
GWR_HOGERWIES = {"found": True, "egid": 123952,
                 "raw_attributes": {"gkode": 2675058.2, "gkodn": 1252765.119}}

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


class _Antwort:
    def __init__(self, daten): self._d = daten
    def raise_for_status(self): pass
    def json(self): return self._d


_overpass_abfragen: list[str] = []


def _post(url, data=None, timeout=None, **kw):
    _overpass_abfragen.append(data["data"])
    return _Antwort(OVERPASS)


def _get_eingefroren(url, params, timeout=None):
    art = url.rsplit("/", 1)[-1]
    schluessel = f"{art}:{params.get('layers') or params.get('layer')}:{params.get('searchText', '')}"
    _abrufe.append(schluessel)
    if schluessel not in GEOADMIN:
        raise RuntimeError(f"nicht eingefroren: {schluessel}")
    return GEOADMIN[schluessel]


def _oev(lat, lon):
    return m1.ProximityEntry(name="Weiningen ZH, Lindenplatz", distanz_m=206.0, typ="bus"), None


def test_naehe() -> None:
    print("\n=== Naehe: Flaechen zaehlen, Bahnhof und Kindergarten ===")
    u = m1.get_umgebung(LAT, LON, E, N).model_dump()
    abfrage = _overpass_abfragen[-1]
    pruefe("nwr(" in abfrage and "node(" not in abfrage,
           "Overpass sucht Punkte UND Flaechen (nwr), nicht nur Punkte")
    pruefe("out center;" in abfrage and "out body 150" not in abfrage,
           "Flaechen liefern ihren Mittelpunkt, keine Obergrenze schneidet Treffer ab")
    s = u["schule_naechste"] or {}
    pruefe(s.get("name") == "Primarschule Weiningen" and s.get("distanz_m") == 378.0,
           f"Schule: Primarschule Weiningen 378 m (vorher Tagesvorschule 1255 m) -- {s}")
    k = u["kindergarten_naechster"] or {}
    pruefe(k.get("name") == "Kindergarten Schlüechti" and k.get("distanz_m") == 360.0,
           f"Kindergarten Schlüechti 360 m -- {k}")
    b = u["bahnhof_naechster"] or {}
    pruefe(b.get("name") == "Schlieren" and 2600 < (b.get("distanz_m") or 0) < 2800,
           f"Bahnhof Schlieren rund 2.7 km -- {b}")
    pruefe(u["radien_m"].get("bahnhof_naechster") == 6000 and u["radien_m"].get("schule_naechste") == 3000,
           "der Suchradius je Kategorie wird mitgeliefert (kein Treffer gilt nur darin)")
    g = u["oev_gueteklasse"] or {}
    pruefe(g.get("klasse") == "C" and g.get("bezeichnung") == "mittelmässige Erschliessung",
           f"OeV-Gueteklasse C, mittelmaessige Erschliessung (ARE) -- {g}")
    pruefe(u["fehler"] == {}, "keine Fehler")


def test_naehe_fehler() -> None:
    print("\n=== Ein Ausfall ist kein Negativbefund ===")
    def kaputt(*a, **kw):
        raise requests.exceptions.ConnectionError("504")
    alt = m1.session.post
    m1.session.post = kaputt
    try:
        u = m1.get_umgebung(LAT, LON, E, N).model_dump()
    finally:
        m1.session.post = alt
    for feld in ("schule_naechste", "kindergarten_naechster", "bahnhof_naechster",
                 "supermarkt_naechster", "spital_naechstes"):
        pruefe(u[feld] is None and feld in u["fehler"],
               f"{feld}: kein Wert UND als Fehler vermerkt")

    alt_get = m1._get
    m1._get = lambda *a, **kw: (_ for _ in ()).throw(requests.exceptions.HTTPError("502"))
    try:
        g, fehler = m1.get_oev_gueteklasse(E, N)
    finally:
        m1._get = alt_get
    pruefe(g is None and fehler and "502" in fehler, "Gueteklasse: Ausfall -> Fehler, keine Klasse erfunden")

    m1._get = lambda *a, **kw: {"results": []}
    try:
        g, fehler = m1.get_oev_gueteklasse(E, N)
    finally:
        m1._get = alt_get
    pruefe(g is not None and g.klasse is None and fehler is None,
           "Gueteklasse: gelungene Abfrage ohne Treffer -> 'keine Klasse', kein Fehler")


def test_energie() -> None:
    print("\n=== Solar: Eignung (Modell) getrennt von der Anlage (Register) ===")
    _abrufe.clear()
    en = m1.get_energie(GWR_HOGERWIES)
    fl = (en.get("solar_dach") or {}).get("flaechen") or []
    pruefe(en["abgefragt"] and len(fl) == 4, f"vier Dachflaechen DES Gebaeudes (nicht des Umkreises): {len(fl)}")
    pruefe(sorted(f["klasse_text"] for f in fl) == ["mittel", "mittel", "sehr gut", "sehr gut"],
           "2 x sehr gut, 2 x mittel")
    pruefe(sum(f["stromertrag_kwh_jahr"] for f in fl) == 16991 + 1477 + 12432 + 5639,
           "Stromertrag je Flaeche unveraendert aus dem Modell")
    pruefe(all(f["stand"] == "08.12.2021" for f in fl), "Stand des Modells 08.12.2021")
    pruefe(any(a.startswith("identify:all:ch.bfe.solarenergie") for a in _abrufe)
           and "find:ch.bfe.solarenergie-eignung-daecher:206867" in _abrufe,
           "Dach am GWR-Gebaeudepunkt, dann alle Flaechen ueber die Gebaeudekennung")
    pruefe(en["anlagen"] == [], "fuer EGID 123952 ist im Register keine Anlage erfasst")
    pruefe("find:ch.bfe.elektrizitaetsproduktionsanlagen:123952" in _abrufe,
           "die Anlage wird exakt ueber die EGID gesucht, nicht ueber die Naehe")

    nachbar = m1.get_energie({"found": True, "egid": 123950,
                              "raw_attributes": {"gkode": 2675058.2, "gkodn": 1252765.119}})
    a = (nachbar.get("anlagen") or [{}])[0]
    pruefe(a.get("kategorie") == "Photovoltaik" and a.get("leistung") == "10.88 kW"
           and a.get("in_betrieb_seit") == "08.09.2020",
           f"Hogerwiesstrasse 3 (EGID 123950): Photovoltaik 10.88 kW seit 08.09.2020 -- {a}")

    _abrufe.clear()
    ohne = m1.get_energie({"found": False})
    pruefe(ohne["abgefragt"] is False and not _abrufe,
           "ohne GWR-Gebaeude wird nichts abgefragt (und nichts behauptet)")

    alt = GEOADMIN.pop("find:ch.bfe.elektrizitaetsproduktionsanlagen:123952")
    try:
        en = m1.get_energie(GWR_HOGERWIES)
    finally:
        GEOADMIN["find:ch.bfe.elektrizitaetsproduktionsanlagen:123952"] = alt
    pruefe(en["anlagen"] is None and "anlagen" in en["fehler"] and en["solar_dach"]["gefunden"],
           "Registerausfall: Anlage 'nicht bestimmbar', die Dacheignung bleibt")


def test_quellen() -> None:
    print("\n=== Herkunft der neuen Werte ===")
    u = m1.get_umgebung(LAT, LON, E, N).model_dump()
    en = m1.get_energie(GWR_HOGERWIES)
    objekte = q.quellen_aus_modul1_ergebnis({"umgebung": u, "energie": en})
    felder = {o.feld: o for o in objekte}
    for feld in ("umgebung.oev_gueteklasse", "umgebung.bahnhof_naechster",
                 "umgebung.kindergarten_naechster", "energie.solar_dach", "energie.anlagen"):
        pruefe(feld in felder, f"Quellenobjekt fuer {feld}")
    pruefe(felder.get("umgebung.oev_gueteklasse") is not None
           and felder["umgebung.oev_gueteklasse"].wert == "C", "Gueteklasse C als belegter Wert")
    namen = {q.QUELLE_BEZEICHNUNG_OEV_GUETEKLASSE, q.QUELLE_BEZEICHNUNG_SOLAR_DACH,
             q.QUELLE_BEZEICHNUNG_PRODUKTIONSANLAGEN}
    pruefe(all(n in q._BEKANNTE_AMTLICHE_ENDPUNKTE for n in namen),
           "ARE-Gueteklassen, BFE-Dach und BFE-Anlagen haben einen bekannten Endpunkt")


def test_restriktion_fehler() -> None:
    print("\n=== Restriktionsabfrage: Fehler ist strukturiert ===")
    alt = (rg.hole_gewaesserraum_flaechen, rg.hole_waldgrenzen, rg.klassifiziere_nutzung)
    def kaputt(*a, **kw):
        raise requests.exceptions.ConnectionError("geodienste.ch nicht erreichbar")
    rg.hole_gewaesserraum_flaechen = kaputt
    rg.hole_waldgrenzen = lambda bbox: []
    rg.klassifiziere_nutzung = lambda *a, **kw: {"gefunden": True, "festlegungen": []}
    try:
        r = rg.hole_restriktionen_fuer_parzelle(E, N, "ZH", [(E, N), (E + 20, N), (E + 20, N + 20), (E, N + 20)])
    finally:
        rg.hole_gewaesserraum_flaechen, rg.hole_waldgrenzen, rg.klassifiziere_nutzung = alt
    pruefe("gewaesserraum" in r["fehler"], "Gewaesserraum: Ausfall steht in `fehler`")
    pruefe("wald" not in r["fehler"] and "baulinien" not in r["fehler"],
           "die gelungenen Teilabfragen gelten als geprueft")
    pruefe(r["suchumkreis_m"]["wald"] == 50.0 and r["suchumkreis_m"]["baulinien"] == 60.0,
           "der Suchumkreis wird mitgeliefert")


def main() -> None:
    m1.session.post = _post
    m1._get = _get_eingefroren
    m1.get_oev_proximity = _oev
    test_naehe()
    test_naehe_fehler()
    test_energie()
    test_quellen()
    test_restriktion_fehler()
    print()
    if _fehler:
        print(f"STANDORT/ENERGIE: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE STANDORT-/ENERGIE-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

"""Bestandsgeometrie aus der amtlichen Vermessung -- und Geplantes getrennt davon.

Anlass (07./08.10.2026): Karte, 3D und Rechnung verwendeten fuer den Bestand
VEC25, einen auf 1:25'000 generalisierten Datensatz. Er war an allen
geprueften Parzellen zu gross (Weiningen 264.1 statt 150.0 m2, Buchs AG 115.0
statt 67.7 m2) und fasste in Buchs drei Gebaeude zu einem zusammen. Der
Umriss geht ins Ausnuetzungsbudget, in die freie Flaeche fuer Anbau/Neubau
und in die Aufstockung ein.

Jetzt: amtliche Vermessung (geodienste.ch, AV Situationsplan), wo der Kanton
sie frei gibt; VEC25 nur als ausgewiesener Ersatz. Projektierte Gebaeude aus
derselben Vermessung stehen getrennt -- sie sind GEPLANT, nicht Bestand.

Alle Antworten sind am 08.10.2026 eingefrorene ECHTE Antworten
(tests/daten/bestand_av). Ersetzt wird nur der Netzzugriff.

Aufruf: python -m tests.test_bestand_av
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine import bestand as b  # noqa: E402
from potenzial_engine import quellen as q  # noqa: E402
from potenzial_engine.pipeline import _bestand_und_neubaugeometrie  # noqa: E402
from potenzial_engine.szenarien import berechne_ausnuetzungsbudget  # noqa: E402

DATEN = Path(__file__).resolve().parent / "daten" / "bestand_av"
FAELLE = {n: json.loads((DATEN / f"{n}.json").read_text(encoding="utf-8")) for n in ("buchs", "weiningen")}

_ok = 0
_fehler: list[str] = []
_av_abrufe: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)
        print(f"[FEHL] {was}")


class _Antwort:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


class Netz:
    """Liefert die eingefrorenen Antworten eines Falls -- oder einen Ausfall."""

    def __init__(self, fall: dict, av_ausfall: bool = False, av_leer: bool = False):
        self.fall, self.av_ausfall, self.av_leer = fall, av_ausfall, av_leer

    def __enter__(self):
        self.alt = (b.requests.get, b._identify)

        def get(url, params=None, timeout=None, **kw):
            typ = (params or {}).get("TYPENAMES", "?")
            _av_abrufe.append(typ)
            if self.av_ausfall:
                raise ConnectionError("geodienste.ch nicht erreichbar")
            if self.av_leer:
                return _Antwort('<wfs:FeatureCollection numberReturned="0"></wfs:FeatureCollection>')
            return _Antwort(self.fall["av"][typ])

        def identify(e, n, layer, tolerance=5, return_geometry=False):
            return copy.deepcopy(self.fall["identify"].get(layer, []))

        b.requests.get, b._identify = get, identify
        return self

    def __exit__(self, *a):
        b.requests.get, b._identify = self.alt


def bestand(name: str, kanton: str | None = None, **netz) -> dict:
    f = FAELLE[name]
    with Netz(f, **netz):
        return b.hole_bestand(f["e"], f["n"], f["parzelle"], kanton=kanton or f["kanton"])


def test_amtlich() -> None:
    print("=== Amtliche Vermessung statt VEC25 ===")
    erg = bestand("buchs")
    gb = {g["egid"]: g for g in erg["gebaeude"]}
    pruefe(erg["grundriss_quelle"]["art"] == "amtliche_vermessung", "Buchs: Quelle amtliche Vermessung")
    pruefe(erg["quellen_layer"][-1] == b.AV_TYP_GEBAEUDE, "die Quelle steht beim Ergebnis, nicht VEC25")
    pruefe(set(gb) == {"263070701", "524242", "263024777"},
           f"Buchs 1145: drei amtliche Gebaeude ({sorted(gb)}) -- VEC25 kannte eines")
    pruefe(all(abs(g["grundriss_flaeche_m2"] - g["grundflaeche_gwr_m2"]) <= 1.0 for g in gb.values()),
           "jede Grundrissflaeche stimmt mit der GWR-Gebaeudeflaeche ueberein (Abweichung <= 1 m2): "
           + str([(g["egid"], g["grundriss_flaeche_m2"], g["grundflaeche_gwr_m2"]) for g in gb.values()]))
    parz = Polygon(FAELLE["buchs"]["parzelle"])
    pruefe(all(Polygon(g["grundriss"]).intersection(parz).area >= 0.98 * Polygon(g["grundriss"]).area
               for g in gb.values()), "alle drei liegen (fast) vollstaendig auf der Parzelle")
    alle_av = FAELLE["buchs"]["av"][b.AV_TYP_GEBAEUDE].count("<wfs:member>")
    pruefe(alle_av > 3, f"aus {alle_av} Vermessungsgebaeuden im Umfeld zaehlen nur die drei der Parzelle")
    pruefe(erg["bebaute_flaeche_grundriss_m2"] == 97.6, "bebaute Flaeche 97.6 m2 (vorher VEC25 115.0 m2)")
    pruefe(not any("generalisiert" in h for h in erg["hinweise"]), "kein Hinweis auf einen generalisierten Datensatz")

    w = bestand("weiningen")
    pruefe(w["gebaeude"][0]["egid"] == "123952" and w["gebaeude"][0]["grundriss_flaeche_m2"] == 150.0,
           "Weiningen: 150.0 m2 (VEC25 264.1 m2), gleich der GWR-Flaeche")

    nochmals = bestand("buchs")
    pruefe([g["grundriss"] for g in nochmals["gebaeude"]] == [g["grundriss"] for g in erg["gebaeude"]],
           "reproduzierbar: dieselben Eingaben ergeben dieselben Umrisse")


def test_ersatz() -> None:
    print("\n=== VEC25 nur als ausgewiesener Ersatz ===")
    _av_abrufe.clear()
    lu = bestand("weiningen", kanton="LU")
    pruefe(not _av_abrufe, "Kanton ohne freie Vermessung: keine Vermessungsabfrage")
    pruefe(lu["grundriss_quelle"]["art"] == "vec25" and "vereinfacht" in lu["grundriss_quelle"]["bezeichnung"],
           "Quelle VEC25, als 'vereinfacht' bezeichnet")
    pruefe(any("nicht frei" in h for h in lu["hinweise"]), "der Grund steht in den Hinweisen")
    pruefe(lu["gebaeude"][0]["grundriss_flaeche_m2"] == 264.1, "VEC25-Umriss 264.1 m2 -- nicht mit AV gemischt")
    pruefe(lu["quellen_layer"][-1] == b.LAYER_GEBAEUDE_GRUNDRISS, "die Quelle sagt VEC25")

    aus = bestand("weiningen", av_ausfall=True)
    pruefe(aus["grundriss_quelle"]["art"] == "vec25" and any("nicht erreichbar" in h for h in aus["hinweise"]),
           "Vermessung nicht erreichbar: VEC25 mit Hinweis, nicht still")

    leer = bestand("weiningen", av_leer=True)
    pruefe(leer["grundriss_quelle"]["art"] == "amtliche_vermessung" and all(g["grundriss"] is None for g in leer["gebaeude"]),
           "leere Vermessung in freiem Kanton: KEIN Auffuellen mit VEC25")

    _av_abrufe.clear()
    with Netz(FAELLE["weiningen"]):
        _t, quelle = b.hole_gebaeudegrundrisse(1.0, 2.0, 70, "ZH", wie_bestand="vec25")
    pruefe(not _av_abrufe and quelle["art"] == "vec25",
           "3D folgt der Quelle des Bestands: war er VEC25, wird die Vermessung nicht abgefragt")


def test_geplant() -> None:
    print("\n=== Geplant (projektiert) ist nicht Bestand ===")
    erg = bestand("buchs")
    pj = erg["projektiert"]
    pruefe(pj["abgefragt"] and len(pj["gebaeude"]) == 1 and pj["gebaeude"][0]["egid"] == "524248",
           "Buchs: ein projektiertes Gebaeude (EGID 524248) aus der Vermessung")
    pruefe(pj["gebaeude"][0]["status"] == "projektiert" and pj["gebaeude"][0]["auf_parzelle"] is False,
           "Status projektiert, liegt in der Umgebung (nicht auf der Parzelle)")
    pruefe("projektierte" in pj["quelle"] and pj["url"] == b.AV_WFS_URL, "Originalquelle erhalten")
    egids = {g["egid"] for g in erg["gebaeude"]}
    pruefe("524248" not in egids, "das projektierte Gebaeude steht NICHT im Bestand")
    w = bestand("weiningen")
    pruefe(len(w["projektiert"]["gebaeude"]) == 3, "Weiningen: drei projektierte Gebaeude im Umfeld")

    # Auch ein projektiertes Gebaeude AUF der Parzelle aendert die Rechnung nicht.
    mit_geplant = copy.deepcopy(erg)
    mit_geplant["projektiert"]["gebaeude"].append({"ring": erg["gebaeude"][1]["grundriss"], "flaeche_m2": 500.0,
                                                   "egid": "999", "auf_parzelle": True, "status": "projektiert"})
    g1 = {"geschossflaeche_m2": 299.44}
    a, c = berechne_ausnuetzungsbudget(g1, erg), berechne_ausnuetzungsbudget(g1, mit_geplant)
    pruefe(a.bestand_gf_m2 == c.bestand_gf_m2 == 135.4 and a.verbleibend_gf_m2 == c.verbleibend_gf_m2 == 164.0,
           f"Ausnuetzungsbudget unberuehrt von Geplantem: Bestand {c.bestand_gf_m2} m2, frei {c.verbleibend_gf_m2} m2")

    lu = bestand("buchs", kanton="LU")
    pruefe(lu["projektiert"]["abgefragt"] is False and lu["projektiert"]["gebaeude"] == [],
           "ohne freie Vermessung: Geplantes 'nicht abgefragt' -- kein Ersatz, keine Behauptung 'keines'")


def test_quellen() -> None:
    print("\n=== Herkunft im Quellenbereich ===")
    erg = bestand("buchs")
    obj = {o.feld: o for o in q.quellen_aus_modul1_ergebnis({"bestand": erg})}
    g = obj.get("bestand.bebaute_flaeche_grundriss_m2")
    pruefe(g is not None and g.quelle_bezeichnung.startswith("Amtliche Vermessung") and g.quelle_url == b.AV_WFS_URL,
           "Grundriss: 'Amtliche Vermessung', mit Endpunkt")
    pruefe("bestand.projektiert" in obj and "projektierte" in obj["bestand.projektiert"].quelle_bezeichnung,
           "projektierte Gebaeude mit eigener Quelle")
    lu = bestand("buchs", kanton="LU")
    obj = {o.feld: o for o in q.quellen_aus_modul1_ergebnis({"bestand": lu})}
    pruefe("vereinfacht" in obj["bestand.bebaute_flaeche_grundriss_m2"].quelle_bezeichnung,
           "VEC25-Ersatz steht als 'vereinfacht' in den Quellen")
    ebene = _bestand_und_neubaugeometrie({"bestand": lu}, None)["bestand"]["grundriss_kataster"]
    pruefe("amtliche Vermessung" not in ebene["quelle"] and ebene["quelle_art"] == "vec25",
           f"VEC25 heisst nicht mehr 'amtliche Vermessung' ({ebene['quelle']})")
    ebene = _bestand_und_neubaugeometrie({"bestand": erg}, None)["bestand"]["grundriss_kataster"]
    pruefe(ebene["quelle_art"] == "amtliche_vermessung", "amtlicher Umriss heisst amtliche Vermessung")


def main() -> None:
    test_amtlich()
    test_ersatz()
    test_geplant()
    test_quellen()
    print()
    if _fehler:
        print(f"BESTAND-AV: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE BESTAND-AV-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

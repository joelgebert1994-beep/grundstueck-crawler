"""
Bestand -- was steht heute tatsaechlich auf der Parzelle?

Bis Stufe 3 lieferte Modul 1 mit `get_gwr_data()` EINEN GWR-Eintrag: den
ersten Treffer einer Toleranzabfrage. Das ist derselbe Fehlertyp wie der am
04.09. behobene `results[0]`-Parzellenbug -- live nachgewiesen an Buchs AG
1145 (Rosenweg 4): die Toleranzabfrage liefert dort drei GWR-Eintraege, und
`results[0]` war die GARAGE (EGID 263024777, 9 m2, keine Geschosszahl,
kein Baujahr) statt des Wohnhauses (EGID 524242, 68 m2, 2 Geschosse,
Baujahr 1918).

Fuer die Entwicklungsszenarien ist das entscheidend: die Aufstockungspruefung
vergleicht die BESTEHENDE Geschosszahl mit der zulaessigen. Mit der Garage als
Bestand kaeme "Geschosszahl unbekannt" heraus, wo in Wirklichkeit zwei
Geschosse stehen.

Dieses Modul liest deshalb ALLE Gebaeude der Parzelle:

  * GWR-Eintraege, die geometrisch INNERHALB des Parzellenpolygons liegen
  * Gebaeudegrundrisse der AMTLICHEN VERMESSUNG (Bodenbedeckung Gebaeude,
    geodienste.ch "AV Situationsplan"), wo der Kanton sie frei gibt --
    sonst `ch.swisstopo.vec25-gebaeude`, ausdruecklich als vereinfacht
  * Zuordnung Grundriss <-> GWR-Eintrag ueber Punkt-in-Polygon

Seit 07.10.2026 die amtliche Vermessung zuerst. VEC25 ist auf 1:25'000
generalisiert und war an allen geprueften Parzellen deutlich zu gross:
Weiningen 1784 264.1 m2 gegen 150.0 m2 (Vermessung = GWR 150), Rheineck 103
133.1 gegen 107.6 (GWR 108), Buchs AG 1145 115.0 gegen 67.7 (GWR 68). Der
Umriss geht in Rechnungen ein (Ausnuetzungsbudget, freie Flaeche fuer
Anbau/Neubau, Aufstockung) -- er war dort also nicht nur ungenau gezeichnet.

Zwei Flaechenbegriffe, die NICHT dasselbe sind und deshalb getrennt bleiben:
`grundflaeche_gwr_m2` ist die im Register gefuehrte Gebaeudeflaeche (GWR-
Merkmal `garea`), `grundriss_flaeche_m2` die Flaeche des Kartengrundrisses.
VEC25 ist ein generalisierter Datensatz (Massstab 1:25'000) -- an Buchs 1145
stehen 115.0 m2 Grundriss gegen 98 m2 GWR-Summe. Beide Werte sind echt; der
Unterschied ist eine Eigenschaft der Datensaetze, keine Ungenauigkeit dieses
Moduls, und wird deshalb ausgewiesen statt verrechnet.

Netzwerkzugriff: ja (geo.admin.ch MapServer identify), gebuendelt in zwei
Abfragen. Die Auswertung selbst ist rein lokal und damit offline testbar.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

import re

import requests
from shapely.geometry import Point, Polygon, shape

from .modul1_geodata import LAYER_GWR, _identify

LAYER_GEBAEUDE_GRUNDRISS = "ch.swisstopo.vec25-gebaeude"

# Amtliche Vermessung, Bodenbedeckung "Gebaeude", ueber geodienste.ch. Frei
# zugaenglich nur fuer diese Kantone (FILTER_ALLOWED_CANTONS der Antwort,
# geprueft 07.10.2026); die uebrigen verlangen eine Registrierung. Ausserhalb
# dieser Liste ist eine leere Antwort KEIN Befund "unbebaut".
AV_WFS_URL = "https://geodienste.ch/db/av_situationsplan_0/deu"
AV_TYP_GEBAEUDE = "ms:land_cover_surface_building"
# Projektierte Gebaeude der amtlichen Vermessung: bewilligt bzw. im Bau, noch
# nicht als Bodenbedeckung "Gebaeude" erfasst. Sie sind GEPLANT, nicht Bestand
# -- sie gehen in keine Bestandsrechnung ein und werden nie als realisiert
# oder bebaubar behandelt.
AV_TYP_PROJEKTIERT = "ms:land_cover_surface_project_buildings"
QUELLE_AV_PROJEKTIERT = ("Amtliche Vermessung, projektierte Gebäude "
                         "(geodienste.ch, AV Situationsplan)")
AV_KANTONE_FREI = frozenset({
    "AG", "AI", "AR", "BE", "BL", "BS", "FL", "FR", "GE", "GL", "GR", "SG", "SH", "SO",
    "SZ", "TG", "TI", "UR", "VS", "ZG", "ZH"})
GRUNDRISS_AV = "amtliche_vermessung"
GRUNDRISS_VEC25 = "vec25"
GRUNDRISS_QUELLE_TEXT = {
    GRUNDRISS_AV: "Amtliche Vermessung, Bodenbedeckung Gebäude (geodienste.ch, AV Situationsplan)",
    GRUNDRISS_VEC25: "swisstopo VEC25 Gebäude (vereinfacht, Massstab 1:25'000)",
}
_AV_TIMEOUT = 30
_AV_MEMBER = re.compile(r"<wfs:member>(.*?)</wfs:member>", re.S)
_AV_ATTR = re.compile(r"<ms:(\w+)>([^<]*)</ms:\1>")
_AV_POLYGON = re.compile(r"<gml:Polygon\b.*?</gml:Polygon>", re.S)
_AV_AUSSEN = re.compile(r"<gml:exterior>.*?<gml:posList[^>]*>([^<]+)</gml:posList>", re.S)
_AV_INNEN = re.compile(r"<gml:interior>.*?<gml:posList[^>]*>([^<]+)</gml:posList>", re.S)
_AV_WEITER = re.compile(r'next="([^"]+)"')

# Wie weit das Umfeld geholt wird (Pixel; rund 2 m je Pixel bei der in
# _identify() gesetzten mapExtent). Grosszuegig, weil danach geometrisch
# gefiltert wird -- Vollstaendigkeit zaehlt hier mehr als Praezision.
_UMFELD_TOLERANZ_PX = 40

# GWR-Gebaeudekategorien (Merkmal GKAT). Nur die Kategorien, die fuer die
# Unterscheidung Wohnnutzung/Nebengebaeude gebraucht werden.
GKAT_TEXT: dict[int, str] = {
    1010: "Provisorische Unterkunft",
    1020: "Gebaeude mit ausschliesslicher Wohnnutzung",
    1030: "Wohngebaeude mit Nebennutzung",
    1040: "Gebaeude mit teilweiser Wohnnutzung",
    1060: "Gebaeude ohne Wohnnutzung",
    1080: "Sonderbau",
}
_GKAT_MIT_WOHNNUTZUNG = {1010, 1020, 1030, 1040}


class BestandError(Exception):
    """Fehler bei der Bestandsermittlung."""


@dataclass
class Gebaeude:
    egid: Optional[str]
    adresse: Optional[str]
    kategorie_gkat: Optional[int]
    kategorie_text: Optional[str]
    wohnnutzung: Optional[bool]
    baujahr: Optional[int]
    geschosse: Optional[int]
    grundflaeche_gwr_m2: Optional[float]
    energiebezugsflaeche_m2: Optional[float]
    gebaeudevolumen_m3: Optional[float]
    grundriss: Optional[list[list[float]]]
    grundriss_flaeche_m2: Optional[float]
    ist_hauptgebaeude: bool
    hinweise: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _zahl(wert: Any) -> Optional[float]:
    if wert in (None, ""):
        return None
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _ganzzahl(wert: Any) -> Optional[int]:
    z = _zahl(wert)
    return int(z) if z is not None else None


def _polygone_aus_treffer(treffer: list[dict[str, Any]]) -> list[Polygon]:
    """Zerlegt Polygone und MultiPolygone in einzelne Polygone.

    VEC25 liefert MultiPolygon -- ein MultiPolygon kann mehrere baulich
    getrennte Gebaeude enthalten, die einzeln zu behandeln sind.
    """
    polygone: list[Polygon] = []
    for r in treffer:
        geom = r.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:  # noqa: BLE001 -- eine fehlerhafte Einzelgeometrie stoppt den Lauf nicht
            continue
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            continue
        if g.geom_type == "Polygon":
            polygone.append(g)
        elif g.geom_type == "MultiPolygon":
            polygone.extend(p for p in g.geoms if not p.is_empty)
    return polygone


def _ring(polygon: Polygon) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in polygon.exterior.coords]


def werte_bestand_aus(
    gwr_treffer: list[dict[str, Any]],
    grundriss_treffer: list[dict[str, Any]],
    parzelle_ring: list[tuple[float, float]],
    grundriss_quelle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Die reine Auswertung -- ohne Netzzugriff, damit offline pruefbar.

    `gwr_treffer` und `grundriss_treffer` sind MapServer-Antworten im Format
    von `_identify(..., return_geometry=True)` (die Vermessung wird beim
    Abruf in dasselbe Format gebracht). `grundriss_quelle` sagt, woher die
    Grundrisse stammen; ohne Angabe VEC25 (bisheriges Verhalten).
    """
    grundriss_quelle = grundriss_quelle or {"art": GRUNDRISS_VEC25,
                                            "bezeichnung": GRUNDRISS_QUELLE_TEXT[GRUNDRISS_VEC25]}
    vereinfacht = grundriss_quelle.get("art") != GRUNDRISS_AV
    parzelle = Polygon(parzelle_ring)
    if not parzelle.is_valid:
        parzelle = parzelle.buffer(0)
    if parzelle.is_empty:
        raise BestandError("Parzellenpolygon ist leer -- Bestand nicht bestimmbar.")

    # 1. GWR-Eintraege, die WIRKLICH auf der Parzelle liegen.
    gwr_auf_parzelle: list[tuple[Point, dict[str, Any]]] = []
    for r in gwr_treffer:
        geom = r.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        koord = geom.get("coordinates") or []
        if len(koord) < 2:
            continue
        punkt = Point(koord[0], koord[1])
        if parzelle.contains(punkt):
            gwr_auf_parzelle.append((punkt, r.get("properties") or r.get("attributes") or {}))

    # 2. Gebaeudegrundrisse, die die Parzelle beruehren.
    grundrisse: list[Polygon] = []
    for p in _polygone_aus_treffer(grundriss_treffer):
        schnitt = p.intersection(parzelle)
        if schnitt.is_empty or schnitt.area < 1.0:
            continue
        grundrisse.append(p)

    # 3. Zuordnung: welcher GWR-Eintrag liegt in welchem Grundriss.
    zugeordnet: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(grundrisse))}
    ohne_grundriss: list[dict[str, Any]] = []
    for punkt, attrs in gwr_auf_parzelle:
        index = next((i for i, g in enumerate(grundrisse) if g.contains(punkt)), None)
        if index is None:
            ohne_grundriss.append(attrs)
        else:
            zugeordnet[index].append(attrs)

    gebaeude: list[Gebaeude] = []

    def baue(attrs: dict[str, Any], polygon: Optional[Polygon], hinweise: list[str]) -> Gebaeude:
        gkat = _ganzzahl(attrs.get("gkat"))
        return Gebaeude(
            egid=str(attrs.get("egid")) if attrs.get("egid") else None,
            adresse=attrs.get("strname_deinr") or None,
            kategorie_gkat=gkat,
            kategorie_text=GKAT_TEXT.get(gkat) if gkat is not None else None,
            wohnnutzung=(gkat in _GKAT_MIT_WOHNNUTZUNG) if gkat is not None else None,
            baujahr=_ganzzahl(attrs.get("gbauj")),
            geschosse=_ganzzahl(attrs.get("gastw")),
            grundflaeche_gwr_m2=_zahl(attrs.get("garea")),
            energiebezugsflaeche_m2=_zahl(attrs.get("gebf")),
            gebaeudevolumen_m3=_zahl(attrs.get("gvol")),
            grundriss=_ring(polygon) if polygon is not None else None,
            grundriss_flaeche_m2=round(polygon.area, 1) if polygon is not None else None,
            ist_hauptgebaeude=False,
            hinweise=hinweise,
        )

    for i, polygon in enumerate(grundrisse):
        eintraege = zugeordnet[i]
        if not eintraege:
            gebaeude.append(baue({}, polygon, [
                "Gebaeudegrundriss ohne zugeordneten GWR-Eintrag -- Baujahr, Geschosszahl "
                "und Nutzung sind fuer diesen Baukoerper nicht bekannt."
            ]))
            continue
        # Mehrere GWR-Eintraege in einem Grundriss: der flaechengroesste
        # fuehrt, die uebrigen werden vermerkt statt verworfen.
        eintraege = sorted(eintraege, key=lambda a: _zahl(a.get("garea")) or 0.0, reverse=True)
        hinweise = []
        if len(eintraege) > 1:
            weitere = ", ".join(f"EGID {a.get('egid')}" for a in eintraege[1:])
            hinweise.append(
                f"{len(eintraege)} GWR-Eintraege in diesem Grundriss; hier gefuehrt wird der "
                f"flaechengroesste. Weitere: {weitere}."
            )
        gebaeude.append(baue(eintraege[0], polygon, hinweise))

    for attrs in ohne_grundriss:
        gebaeude.append(baue(attrs, None, [
            ("GWR-Eintrag auf der Parzelle ohne passenden Gebaeudegrundriss in "
             f"{LAYER_GEBAEUDE_GRUNDRISS} -- der Datensatz ist generalisiert (1:25'000) "
             "und fuehrt kleine Nebengebaeude teils nicht.") if vereinfacht else
            ("GWR-Eintrag auf der Parzelle ohne Gebaeudegrundriss in der amtlichen "
             "Vermessung -- Register und Vermessung sind hier nicht deckungsgleich.")
        ]))

    # 4. Hauptgebaeude: groesste Wohnnutzung, sonst groesste Flaeche.
    def groesse(g: Gebaeude) -> float:
        return g.grundriss_flaeche_m2 or g.grundflaeche_gwr_m2 or 0.0

    wohn = [g for g in gebaeude if g.wohnnutzung]
    haupt = max(wohn or gebaeude, key=groesse) if gebaeude else None
    if haupt is not None:
        haupt.ist_hauptgebaeude = True

    hinweise: list[str] = []
    if not gebaeude:
        hinweise.append(
            "Kein Gebaeude auf der Parzelle gefunden -- weder ein GWR-Eintrag innerhalb des "
            "Parzellenpolygons noch ein Gebaeudegrundriss. Die Parzelle ist vermutlich unbebaut."
        )
    if haupt is not None and haupt.geschosse is None:
        hinweise.append(
            "Fuer das Hauptgebaeude ist im GWR keine Geschosszahl gefuehrt -- eine "
            "Aufstockungspruefung ist damit nicht belastbar moeglich."
        )
    if haupt is not None and not wohn and gebaeude:
        hinweise.append(
            "Kein Gebaeude mit Wohnnutzung auf der Parzelle -- als Hauptgebaeude gilt hier "
            "das flaechengroesste ohne Wohnnutzung."
        )

    grundriss_summe = round(sum(g.grundriss_flaeche_m2 or 0.0 for g in gebaeude), 1)
    gwr_summe = round(sum(g.grundflaeche_gwr_m2 or 0.0 for g in gebaeude), 1)
    if grundriss_summe and gwr_summe and abs(grundriss_summe - gwr_summe) / max(grundriss_summe, gwr_summe) > 0.15:
        hinweise.append(
            f"Grundrissflaeche ({grundriss_summe} m2) und GWR-Gebaeudeflaeche ({gwr_summe} m2) "
            "weichen um mehr als 15 % voneinander ab. Beide Werte sind echt -- "
            + ("VEC25 ist ein generalisierter Kartendatensatz, " if vereinfacht
               else "die Vermessung zeigt den Grundriss, ")
            + "das GWR ist ein Register. Sie werden nicht verrechnet."
        )
    if grundriss_quelle.get("hinweis"):
        hinweise.append(grundriss_quelle["hinweis"])

    return {
        "gefunden": bool(gebaeude),
        "gebaeude": [g.to_dict() for g in gebaeude],
        "hauptgebaeude": haupt.to_dict() if haupt is not None else None,
        "anzahl_gebaeude": len(gebaeude),
        "bebaute_flaeche_grundriss_m2": grundriss_summe or None,
        "bebaute_flaeche_gwr_m2": gwr_summe or None,
        "ueberbauungsgrad_ist": (
            round(grundriss_summe / parzelle.area, 3) if grundriss_summe and parzelle.area else None
        ),
        "hinweise": hinweise,
        "quellen_layer": [LAYER_GWR, LAYER_GEBAEUDE_GRUNDRISS if vereinfacht else AV_TYP_GEBAEUDE],
        "grundriss_quelle": grundriss_quelle,
        "abgerufen_am": datetime.now().date().isoformat(),
    }


def _av_gebaeude(bbox: tuple[float, float, float, float],
                 typ: str = AV_TYP_GEBAEUDE) -> list[dict[str, Any]]:
    """Gebaeude der amtlichen Vermessung im Rechteck, im Trefferformat von
    `_identify(..., return_geometry=True)` -- damit laeuft die bestehende
    Auswertung (Polygone, Punkt-in-Grundriss) unveraendert weiter. `typ`:
    bestehende (Standard) oder projektierte Gebaeude -- derselbe Dienst."""
    minx, miny, maxx, maxy = bbox
    url: str = AV_WFS_URL
    params: Optional[dict[str, str]] = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": typ,
        "BBOX": f"{minx},{miny},{maxx},{maxy},urn:ogc:def:crs:EPSG::2056"}
    treffer: list[dict[str, Any]] = []
    for _seite in range(20):  # Der Dienst blaettert nur auf Verlangen; begrenzt, nie endlos.
        resp = requests.get(url, params=params, timeout=_AV_TIMEOUT)
        resp.raise_for_status()
        if "ExceptionReport" in resp.text[:2000]:
            raise RuntimeError("geodienste.ch meldet einen Fehler (ExceptionReport)")
        for block in _AV_MEMBER.findall(resp.text):
            attrs = dict(_AV_ATTR.findall(block))
            for polygon_gml in _AV_POLYGON.findall(block):
                aussen = _AV_AUSSEN.search(polygon_gml)
                if not aussen:
                    continue
                ringe = []
                for pos in [aussen.group(1)] + _AV_INNEN.findall(polygon_gml):
                    z = [float(v) for v in pos.split()]
                    ringe.append([[z[i], z[i + 1]] for i in range(0, len(z) - 1, 2)])
                treffer.append({"geometry": {"type": "Polygon", "coordinates": ringe},
                                "properties": {"egid": attrs.get("gwr_egid") or None,
                                               "kanton": attrs.get("kanton"),
                                               "qualitaet": attrs.get("qualitaet")}})
        weiter = _AV_WEITER.search(resp.text[:4000])
        if not weiter:
            break
        url, params = weiter.group(1).replace("&amp;", "&"), None
    return treffer


def hole_gebaeudegrundrisse(
    e: float, n: float, tolerance_px: int, kanton: Optional[str] = None,
    wie_bestand: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gebaeudegrundrisse um den Punkt -- fuer den Bestand UND die 3D-Umgebung.

    Zuerst die amtliche Vermessung. VEC25 nur, wenn der Kanton die
    Vermessung nicht frei gibt oder der Dienst nicht antwortet -- und dann mit
    dem ausdruecklichen Vermerk "vereinfacht". Eine leere Antwort der
    Vermessung in einem freien Kanton heisst: dort steht kein Gebaeude; sie
    wird NICHT durch VEC25 aufgefuellt.

    Das Rechteck entspricht dem Umkreis der bisherigen Toleranzabfrage
    (rund 2 m je Pixel, siehe `_identify`).

    `wie_bestand`: die Quelle, die der Bestand DIESER Analyse bekommen hat.
    Musste er auf VEC25 ausweichen, tut es die 3D-Szene auch -- in einem Fall
    stehen nie Umrisse zweier Quellen nebeneinander.
    """
    k = (kanton or "").strip().upper()
    radius = tolerance_px * 2.0
    if wie_bestand == GRUNDRISS_VEC25:
        treffer = _identify(e, n, LAYER_GEBAEUDE_GRUNDRISS, tolerance=tolerance_px, return_geometry=True)
        return treffer, {"art": GRUNDRISS_VEC25, "bezeichnung": GRUNDRISS_QUELLE_TEXT[GRUNDRISS_VEC25],
                         "hinweis": "Wie beim Bestand dieser Analyse: Gebaeudeumriss vereinfacht "
                                    "aus VEC25 (1:25'000)."}
    if k in AV_KANTONE_FREI:
        try:
            treffer = _av_gebaeude((e - radius, n - radius, e + radius, n + radius))
            return treffer, {"art": GRUNDRISS_AV, "bezeichnung": GRUNDRISS_QUELLE_TEXT[GRUNDRISS_AV],
                             "url": AV_WFS_URL}
        except Exception as exc:  # noqa: BLE001 -- dann vereinfacht, aber gesagt
            hinweis = (f"Amtliche Vermessung (geodienste.ch) nicht erreichbar ({type(exc).__name__}) -- "
                       "Gebaeudeumriss vereinfacht aus VEC25 (1:25'000).")
    else:
        hinweis = (f"Kanton {k or '?'} gibt die Gebaeudegrundrisse der amtlichen Vermessung ueber "
                   "geodienste.ch nicht frei -- Gebaeudeumriss vereinfacht aus VEC25 (1:25'000).")
    treffer = _identify(e, n, LAYER_GEBAEUDE_GRUNDRISS, tolerance=tolerance_px, return_geometry=True)
    return treffer, {"art": GRUNDRISS_VEC25, "bezeichnung": GRUNDRISS_QUELLE_TEXT[GRUNDRISS_VEC25],
                     "hinweis": hinweis}


def hole_bestand(
    e: float, n: float, parzelle_ring: list[tuple[float, float]], kanton: Optional[str] = None,
) -> dict[str, Any]:
    """Ermittelt alle Gebaeude auf der Parzelle (GWR + Grundrisse)."""
    if not parzelle_ring:
        return {
            "gefunden": False,
            "reason": "Keine Parzellengeometrie -- Bestand nicht ermittelbar.",
            "gebaeude": [],
        }
    gwr = _identify(e, n, LAYER_GWR, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True)
    grundrisse, quelle = hole_gebaeudegrundrisse(e, n, _UMFELD_TOLERANZ_PX, kanton)
    ergebnis = werte_bestand_aus(gwr, grundrisse, parzelle_ring, grundriss_quelle=quelle)
    # Getrennt vom Bestand angehaengt -- NACH der Auswertung, damit sie in
    # keine Flaeche, kein Budget und kein Szenario einfliessen koennen.
    ergebnis["projektiert"] = hole_projektierte_gebaeude(e, n, parzelle_ring, kanton)
    return ergebnis


def hole_projektierte_gebaeude(
    e: float, n: float, parzelle_ring: list[tuple[float, float]], kanton: Optional[str] = None,
) -> dict[str, Any]:
    """Projektierte Gebaeude der amtlichen Vermessung im Umfeld der Parzelle.

    Nur, was die Vermessung als projektiert fuehrt -- nie ein vom Crawler
    errechneter Koerper. Kein Ersatz aus einer anderen Quelle: gibt der
    Kanton die Vermessung nicht frei oder antwortet der Dienst nicht, heisst
    das "nicht bestimmbar", nicht "keine geplanten Gebaeude".
    """
    k = (kanton or "").strip().upper()
    if k not in AV_KANTONE_FREI:
        return {"abgefragt": False, "gebaeude": [],
                "grund": f"Kanton {k or '?'} gibt die amtliche Vermessung ueber geodienste.ch nicht frei."}
    radius = _UMFELD_TOLERANZ_PX * 2.0
    try:
        treffer = _av_gebaeude((e - radius, n - radius, e + radius, n + radius), AV_TYP_PROJEKTIERT)
    except Exception as exc:  # noqa: BLE001
        return {"abgefragt": False, "gebaeude": [],
                "grund": f"Amtliche Vermessung (geodienste.ch) nicht erreichbar ({type(exc).__name__})."}
    parzelle = Polygon(parzelle_ring)
    if not parzelle.is_valid:
        parzelle = parzelle.buffer(0)
    gebaeude = []
    for t, polygon in zip(treffer, (_polygone_aus_treffer([t]) for t in treffer)):
        for p in polygon:
            gebaeude.append({
                "ring": _ring(p),
                "flaeche_m2": round(p.area, 1),
                "egid": (t.get("properties") or {}).get("egid"),
                "auf_parzelle": p.intersection(parzelle).area >= 1.0,
                "status": "projektiert",
            })
    return {"abgefragt": True, "gebaeude": gebaeude, "quelle": QUELLE_AV_PROJEKTIERT,
            "url": AV_WFS_URL}


def bestandsgeschosse(bestand: dict[str, Any]) -> Optional[int]:
    """Geschosszahl des Hauptgebaeudes, oder None wenn nicht gefuehrt."""
    haupt = (bestand or {}).get("hauptgebaeude") or {}
    return haupt.get("geschosse")


def bestandsgrundriss(bestand: dict[str, Any]) -> list[list[float]]:
    """Alle Gebaeudegrundrisse der Parzelle als Ringe -- die Flaeche, die
    ein Anbau oder ein zusaetzlicher Baukoerper NICHT belegen kann."""
    return [g["grundriss"] for g in (bestand or {}).get("gebaeude", []) if g.get("grundriss")]

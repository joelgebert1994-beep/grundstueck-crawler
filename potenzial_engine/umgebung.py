"""
Raeumlicher Kontext fuer die 3D-Ansicht.

Bis hierher zeigte die 3D-Ansicht die Parzelle, den Baubereich und den
Projektkoerper auf leerer Flaeche -- geometrisch richtig, raeumlich
nichtssagend. Dieses Modul beschafft das, was drumherum gehoert:

    Terrain  ->  swissALTI3D ueber den Hoehenprofil-Dienst
    Parzelle ->  amtliche Vermessung (bereits vorhanden)
    Nachbarn ->  Katasterpolygone (bereits fuer die Kantenklassifikation geholt)
    Gebaeude ->  GWR + VEC25-Grundrisse (bereits fuer den Bestand geholt)
    Strassen ->  TLM3D-Achsen (bereits fuer die Kantenklassifikation geholt)

Vier der fuenf Quellen werden also ohnehin schon abgefragt -- dieses Modul
holt sie gebuendelt fuer das UMFELD statt nur fuer die Parzelle und ergaenzt
das Terrain. Es gibt keine zweite Geometrie-Implementierung: die Auswertung
der Gebaeudetreffer laeuft ueber dieselben Helfer wie im Bestand.

Hoehen werden NICHT geraten
---------------------------
Ein Gebaeude bekommt seine Hoehe aus der GWR-Geschosszahl mal der
Geschosshoehen-Annahme. Gibt es keinen GWR-Eintrag im Grundriss, bleibt die
Hoehe `None` mit `hoehe_quelle = "nicht_bestimmbar"` -- die Ansicht stellt
solche Gebaeude flach dar und sagt das in der Legende. Eine erfundene
Regelhoehe waere genau die Scheingenauigkeit, die ausgeschlossen ist.

Das Terrain stammt aus swissALTI3D (DTM2, 2 m Aufloesung). Der Profil-Dienst
liefert eine ganze Linie je Anfrage; ein Raster von n x n Punkten kostet
deshalb n Anfragen statt n zum Quadrat.

Netzwerkzugriff: ja. Reine Beschaffung und Aufbereitung, keine Bewertung.
"""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape

from .bestand import LAYER_GEBAEUDE_GRUNDRISS, _ganzzahl, _polygone_aus_treffer, _ring
from .kantenklassifikation import LAYER_STRASSEN
from .modul1_geodata import LAYER_CADASTRE_GEOM, LAYER_GWR, _identify, session

PROFIL_URL = "https://api3.geo.admin.ch/rest/services/profile.json"

# Wie weit das Umfeld reicht. 120 m decken die Nachbarschaft ab, ohne die
# Szene mit Gebaeuden zu fuellen, die raeumlich nichts mehr beitragen.
STANDARD_RADIUS_M = 120.0

# Rasterweite des Terrains. 16 x 16 Punkte ueber 240 m sind rund 16 m
# Maschenweite -- fein genug fuer die Gelaendeform, grob genug fuer 16
# Anfragen statt 256.
STANDARD_RASTER = 16

# Tolerance in PIXELN (siehe kantenklassifikation.py: rund 2 m je Pixel).
_UMFELD_TOLERANZ_PX = 70

# Ohne bekannte Geschosszahl keine Hoehe -- siehe Modul-Docstring.
STANDARD_GESCHOSSHOEHE_M = 3.0

HOEHE_AUS_GESCHOSSEN = "geschosse_x_geschosshoehe"
HOEHE_NICHT_BESTIMMBAR = "nicht_bestimmbar"


class UmgebungError(Exception):
    """Der raeumliche Kontext konnte nicht beschafft werden."""


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------

def _profil_zeile(x_von: float, x_bis: float, y: float, punkte: int) -> list[Optional[float]]:
    """Eine Rasterzeile ueber den Hoehenprofil-Dienst."""
    geom = {"type": "LineString", "coordinates": [[x_von, y], [x_bis, y]]}
    try:
        resp = session.get(
            PROFIL_URL,
            params={"geom": json.dumps(geom), "sr": 2056, "nb_points": punkte},
            timeout=20,
        )
        resp.raise_for_status()
        daten = resp.json()
    except Exception:  # noqa: BLE001 -- eine fehlende Zeile darf die Szene nicht kippen
        return [None] * punkte

    hoehen: list[Optional[float]] = []
    for p in daten[:punkte]:
        alts = p.get("alts") or {}
        wert = alts.get("DTM2") or alts.get("COMB") or alts.get("DTM25")
        hoehen.append(float(wert) if wert is not None else None)
    while len(hoehen) < punkte:
        hoehen.append(None)
    return hoehen


def hole_terrain(
    e: float, n: float, radius_m: float = STANDARD_RADIUS_M, raster: int = STANDARD_RASTER
) -> dict[str, Any]:
    """Ein regelmaessiges Hoehenraster um den Mittelpunkt.

    Die Zeilen werden parallel geholt -- sequenziell waeren 16 Anfragen
    spuerbar, nebenlaeufig sind es unter einer Sekunde.
    """
    if raster < 2:
        raise UmgebungError(f"Raster muss mindestens 2 sein, erhalten: {raster}")

    x_von, x_bis = e - radius_m, e + radius_m
    y_von, y_bis = n - radius_m, n + radius_m
    schritt = (2 * radius_m) / (raster - 1)
    y_werte = [y_von + i * schritt for i in range(raster)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        zeilen = list(pool.map(lambda y: _profil_zeile(x_von, x_bis, y, raster), y_werte))

    alle = [h for zeile in zeilen for h in zeile if h is not None]
    fehlend = sum(1 for zeile in zeilen for h in zeile if h is None)
    hinweise: list[str] = []
    if fehlend:
        hinweise.append(
            f"{fehlend} von {raster * raster} Rasterpunkten ohne Hoehe -- der Dienst hat sie "
            "nicht geliefert. Die Ansicht interpoliert dort aus den Nachbarn."
        )
    if not alle:
        raise UmgebungError(
            "Der Hoehendienst lieferte keinen einzigen Rasterpunkt -- ohne Terrain wird die "
            "Szene nicht aufgebaut."
        )

    return {
        "gefunden": True,
        "raster": raster,
        "radius_m": radius_m,
        "schrittweite_m": round(schritt, 2),
        "ursprung_lv95": [round(x_von, 2), round(y_von, 2)],
        # zeilen[i][j] gehoert zu y = y_von + i*schritt, x = x_von + j*schritt
        "hoehen": [[None if h is None else round(h, 2) for h in zeile] for zeile in zeilen],
        "min_hoehe_m": round(min(alle), 2),
        "max_hoehe_m": round(max(alle), 2),
        "quelle": "swissALTI3D (DTM2) ueber api3.geo.admin.ch/rest/services/profile.json",
        "hinweise": hinweise,
    }


def hoehe_an(terrain: dict[str, Any], x: float, y: float) -> Optional[float]:
    """Terrainhoehe an einem Punkt, bilinear aus dem Raster.

    Liegt der Punkt ausserhalb des Rasters, wird auf den Rand geklemmt --
    besser ein Randwert als gar keine Hoehe fuer ein Gebaeude am Bildrand.
    """
    hoehen = terrain.get("hoehen") or []
    if not hoehen:
        return None
    raster = len(hoehen)
    schritt = terrain["schrittweite_m"]
    x0, y0 = terrain["ursprung_lv95"]

    fx = min(max((x - x0) / schritt, 0.0), raster - 1.0)
    fy = min(max((y - y0) / schritt, 0.0), raster - 1.0)
    i0, j0 = int(fy), int(fx)
    i1, j1 = min(i0 + 1, raster - 1), min(j0 + 1, raster - 1)
    dy, dx = fy - i0, fx - j0

    ecken = [hoehen[i0][j0], hoehen[i0][j1], hoehen[i1][j0], hoehen[i1][j1]]
    gewichte = [(1 - dx) * (1 - dy), dx * (1 - dy), (1 - dx) * dy, dx * dy]
    summe = sum(g for h, g in zip(ecken, gewichte) if h is not None)
    if summe <= 0:
        # Alle vier Ecken fehlen -- den naechsten vorhandenen Wert nehmen.
        vorhanden = [h for zeile in hoehen for h in zeile if h is not None]
        return round(sum(vorhanden) / len(vorhanden), 2) if vorhanden else None
    wert = sum(h * g for h, g in zip(ecken, gewichte) if h is not None) / summe
    return round(wert, 2)


# ---------------------------------------------------------------------------
# Gebaeude im Umfeld
# ---------------------------------------------------------------------------

def werte_gebaeude_aus(
    gwr_treffer: list[dict[str, Any]],
    grundriss_treffer: list[dict[str, Any]],
    parzelle_ring: list[tuple[float, float]],
    geschosshoehe_m: float = STANDARD_GESCHOSSHOEHE_M,
) -> list[dict[str, Any]]:
    """Ordnet GWR-Eintraege den Grundrissen zu und trennt eigen von fremd.

    Netzfrei, damit offline pruefbar. Verwendet dieselben Helfer wie
    `bestand.py` -- die Zuordnung Punkt-in-Grundriss gibt es nur einmal.
    """
    parzelle = Polygon(parzelle_ring)
    if not parzelle.is_valid:
        parzelle = parzelle.buffer(0)

    punkte: list[tuple[Point, dict[str, Any]]] = []
    for r in gwr_treffer:
        geom = r.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        koord = geom.get("coordinates") or []
        if len(koord) >= 2:
            punkte.append((Point(koord[0], koord[1]), r.get("properties") or r.get("attributes") or {}))

    gebaeude: list[dict[str, Any]] = []
    for polygon in _polygone_aus_treffer(grundriss_treffer):
        if polygon.is_empty or polygon.area < 4.0:
            continue
        treffer = [attrs for punkt, attrs in punkte if polygon.contains(punkt)]
        # Von mehreren Eintraegen im selben Grundriss gibt der mit der
        # groessten Geschosszahl die Hoehe vor -- das Gebaeude ist so hoch
        # wie sein hoechster Teil.
        geschosse = max(
            (g for g in (_ganzzahl(a.get("gastw")) for a in treffer) if g is not None),
            default=None,
        )
        auf_parzelle = not polygon.intersection(parzelle).is_empty and \
            polygon.intersection(parzelle).area >= 1.0

        gebaeude.append({
            "ring": _ring(polygon),
            "grundflaeche_m2": round(polygon.area, 1),
            "eigen": auf_parzelle,
            "geschosse": geschosse,
            "hoehe_m": round(geschosse * geschosshoehe_m, 2) if geschosse else None,
            "hoehe_quelle": HOEHE_AUS_GESCHOSSEN if geschosse else HOEHE_NICHT_BESTIMMBAR,
            "egid": next((str(a["egid"]) for a in treffer if a.get("egid")), None),
            "baujahr": next(
                (j for j in (_ganzzahl(a.get("gbauj")) for a in treffer) if j is not None), None),
            "adresse": next((a.get("strname_deinr") for a in treffer if a.get("strname_deinr")), None),
        })
    return gebaeude


# ---------------------------------------------------------------------------
# Gesamtszene
# ---------------------------------------------------------------------------

def _nachbarparzellen(e: float, n: float, eigenes_egrid: Optional[str]) -> list[dict[str, Any]]:
    eigen_punkt = Point(e, n)
    parzellen = []
    for r in _identify(e, n, LAYER_CADASTRE_GEOM, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True):
        geom = r.get("geometry") or {}
        if geom.get("type") != "Polygon" or not geom.get("coordinates"):
            continue
        try:
            p = Polygon([(c[0], c[1]) for c in geom["coordinates"][0]])
        except Exception:  # noqa: BLE001
            continue
        if not p.is_valid:
            # buffer(0) repariert ein selbstschneidendes Polygon, kann dabei
            # aber ein MultiPolygon liefern -- dann gilt der groesste Teil.
            repariert = p.buffer(0)
            if getattr(repariert, "geom_type", "") == "MultiPolygon":
                repariert = max(repariert.geoms, key=lambda g: g.area)
            p = repariert
        if p.is_empty or p.geom_type != "Polygon":
            continue
        attrs = r.get("properties") or r.get("attributes") or {}
        egrid = attrs.get("egris_egrid")
        ist_eigen = (egrid == eigenes_egrid) if (egrid and eigenes_egrid) else p.contains(eigen_punkt)
        if ist_eigen:
            continue
        parzellen.append({
            "ring": [[round(x, 2), round(y, 2)] for x, y in p.exterior.coords],
            "nummer": attrs.get("number"),
            "egrid": egrid,
            "flaeche_m2": round(p.area, 1),
        })
    return parzellen


def _strassen(e: float, n: float) -> list[dict[str, Any]]:
    strassen = []
    for r in _identify(e, n, LAYER_STRASSEN, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True):
        geom = r.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:  # noqa: BLE001
            continue
        attrs = r.get("properties") or r.get("attributes") or {}
        teile = list(g.geoms) if isinstance(g, MultiLineString) else ([g] if isinstance(g, LineString) else [])
        for teil in teile:
            strassen.append({
                "koordinaten": [[round(x, 2), round(y, 2)] for x, y in teil.coords],
                "name": attrs.get("strassenname"),
                "objektart": attrs.get("objektart"),
            })
    return strassen


def hole_umgebung(
    e: float,
    n: float,
    parzelle_ring: list[tuple[float, float]],
    *,
    eigenes_egrid: Optional[str] = None,
    radius_m: float = STANDARD_RADIUS_M,
    raster: int = STANDARD_RASTER,
    geschosshoehe_m: float = STANDARD_GESCHOSSHOEHE_M,
) -> dict[str, Any]:
    """Der vollstaendige raeumliche Kontext fuer die 3D-Ansicht.

    Alle Koordinaten in LV95. Jedes Objekt traegt seine Terrainhoehe, damit
    die Ansicht es ohne eigene Interpolation setzen kann.
    """
    if not parzelle_ring:
        raise UmgebungError("Keine Parzellengeometrie -- ohne sie gibt es keine Szene.")

    terrain = hole_terrain(e, n, radius_m, raster)

    gwr = _identify(e, n, LAYER_GWR, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True)
    grundrisse = _identify(e, n, LAYER_GEBAEUDE_GRUNDRISS, tolerance=_UMFELD_TOLERANZ_PX,
                           return_geometry=True)
    gebaeude = werte_gebaeude_aus(gwr, grundrisse, parzelle_ring, geschosshoehe_m)

    # Jedes Objekt auf das Terrain setzen.
    for g in gebaeude:
        xs = [p[0] for p in g["ring"]]
        ys = [p[1] for p in g["ring"]]
        g["terrain_hoehe_m"] = hoehe_an(terrain, sum(xs) / len(xs), sum(ys) / len(ys))

    nachbarn = _nachbarparzellen(e, n, eigenes_egrid)
    for p in nachbarn:
        xs = [k[0] for k in p["ring"]]
        ys = [k[1] for k in p["ring"]]
        p["terrain_hoehe_m"] = hoehe_an(terrain, sum(xs) / len(xs), sum(ys) / len(ys))

    strassen = _strassen(e, n)
    for s in strassen:
        s["hoehen_m"] = [hoehe_an(terrain, x, y) for x, y in s["koordinaten"]]

    parzelle_hoehen = [hoehe_an(terrain, x, y) for x, y in parzelle_ring]
    ohne_hoehe = [g for g in gebaeude if g["hoehe_m"] is None]

    hinweise = list(terrain.get("hinweise") or [])
    if ohne_hoehe:
        hinweise.append(
            f"{len(ohne_hoehe)} von {len(gebaeude)} Gebaeuden ohne bekannte Geschosszahl -- "
            "sie werden flach dargestellt. Eine Regelhoehe wird nicht unterstellt."
        )
    if not nachbarn:
        hinweise.append("Keine Nachbarparzellen im Umfeld gefunden.")
    if not strassen:
        hinweise.append("Keine Strassenachsen im Umfeld gefunden.")

    return {
        "gefunden": True,
        "zentrum_lv95": [round(e, 2), round(n, 2)],
        "radius_m": radius_m,
        "terrain": terrain,
        "parzelle": {
            "ring": [[round(x, 2), round(y, 2)] for x, y in parzelle_ring],
            "terrain_hoehen_m": parzelle_hoehen,
        },
        "nachbarparzellen": nachbarn,
        "gebaeude": gebaeude,
        "strassen": strassen,
        "geschosshoehe_annahme_m": geschosshoehe_m,
        "statistik": {
            "gebaeude": len(gebaeude),
            "gebaeude_eigen": sum(1 for g in gebaeude if g["eigen"]),
            "gebaeude_ohne_hoehe": len(ohne_hoehe),
            "nachbarparzellen": len(nachbarn),
            "strassenabschnitte": len(strassen),
            "terrainpunkte": raster * raster,
        },
        "quellen": {
            "terrain": terrain["quelle"],
            "parzellen": LAYER_CADASTRE_GEOM,
            "gebaeude_grundriss": LAYER_GEBAEUDE_GRUNDRISS,
            "gebaeude_merkmale": LAYER_GWR,
            "strassen": LAYER_STRASSEN,
        },
        "hinweise": hinweise,
    }

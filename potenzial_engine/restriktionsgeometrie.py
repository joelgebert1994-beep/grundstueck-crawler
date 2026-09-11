"""
Restriktionsgeometrie-Beschaffung fuer G1 (Gewaesserraum, Waldgrenzen, Baulinien)
==================================================================================
Liefert reale Restriktionsflaechen aus oeffentlichen WFS-Diensten, aufbereitet
zum direkten Einspeisen in baubereich.berechne_potenzial()s
`restriktionsflaechen`-Parameter. Bewusst GETRENNT von baubereich.py gehalten
(das dort explizit netzwerkfrei bleibt) -- "Datenbeschaffung separat" gemaess
G1-Vorgabe.

Quellen (alle live verifiziert, 2026-08-28):
  - Gewaesserraum: geodienste.ch gewaesserraum_v1_1_0 (ms:gewaesserraum).
    Liefert direkt Polygone. Traegt ein "verzicht"-Feld (Ja/Nein) -- Flaechen
    mit Verzicht auf Ausscheidung sind KEINE Restriktion und werden
    ausgefiltert. ACHTUNG Rechtsstatus-Schreibweise weicht von der
    Nutzungsplanung ab: hier "In Kraft" (mit Leerzeichen/Grossbuchstaben)
    statt "inKraft" wie bei npl_nutzungsplanung/npl_waldgrenzen -- noch eine
    Casing-Inkonsistenz zwischen geodienste-Subdiensten (vgl.
    feedback_oereb_webservice_gotchas). Normalisiert ueber _ist_inkraft().
  - Waldgrenzen: geodienste.ch npl_waldgrenzen_v1_2_0 (ms:waldgrenzen).
    Liefert nur die GRENZLINIE, NICHT den gesetzlichen Waldabstand (der ist
    kantonal/kommunal unterschiedlich geregelt und steht i.d.R. nur in der
    BZO, nicht maschinenlesbar). Deshalb: Geometrie wird gefunden und der
    Minimalabstand zur Parzelle gemeldet, aber NUR dann als Restriktionsflaeche
    verwendet, wenn der Aufrufer `waldabstand_m` explizit uebergibt -- kein
    stillschweigender Default (z.B. "30m"), das waere geraten statt berechnet.
  - Baulinien: ueber modul1b_nutzungsklassifikation.klassifiziere_nutzung()
    (bereits bestehende geodienste/ZH-WFS-Doppelabfrage, siehe dort), gefiltert
    auf foederale Kategorie 71 (linienbezogene Baulinien -- NICHT zu
    verwechseln mit Kategorie 61 "Sondernutzungsplaene", zu der auch
    Baulinienplaene zaehlen koennen, siehe SONDERNUTZUNGSPLAN_KATEGORIE dort).
    Rechtlich ist eine Baulinie eine Grenze, jenseits derer nicht gebaut
    werden darf -- WELCHE Seite Baugebiet ist, steht nicht in der Geometrie.
    Dokumentierte Annahme (siehe baulinie_zu_restriktionsflaeche): die
    flaechenmaessige MEHRHEITSSEITE der Parzelle gilt als Baugebiet, die
    Minderheitsseite wird zur Restriktion.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import requests
from shapely.geometry import LineString, Polygon
from shapely.ops import split

from .modul1b_nutzungsklassifikation import (
    NutzungsklassifikationError,
    extrahiere_koordinatenlisten,
    klassifiziere_nutzung,
)

GEWAESSERRAUM_WFS_URL = "https://geodienste.ch/db/gewaesserraum_v1_1_0/deu"
WALDGRENZEN_WFS_URL = "https://geodienste.ch/db/npl_waldgrenzen_v1_2_0/deu"
BAULINIEN_KATEGORIE = "71"

_TIMEOUT = 30

# Baulinien werden ueber einen groesseren, GEOMETRIE-basiert nachgefilterten
# Radius abgefragt (nicht den kleinen 8m-Default von klassifiziere_nutzung,
# der auf die Klassifikations-Mehrdeutigkeitsfrage zugeschnitten ist).
_BAULINIEN_SUCH_RADIUS_M = 60.0
# Marge um die Parzellen-Bounding-Box fuer Gewaesserraum/Waldgrenzen-Abfragen.
_BBOX_MARGE_M = 50.0
_LINIE_VERLAENGERUNG_M = 500.0


# ---------------------------------------------------------------------------
# Generische WFS-Abfrage (identisches Muster wie modul1b_nutzungsklassifikation,
# bewusst hier separat gehalten statt private Funktionen modulübergreifend zu
# importieren -- unterschiedliche Dienste/Basis-URLs, geringe Duplikation).
# ---------------------------------------------------------------------------

def _wfs_get_features(url: str, typename: str, bbox: tuple[float, float, float, float]) -> list[dict[str, str]]:
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "BBOX": f"{minx},{miny},{maxx},{maxy},urn:ogc:def:crs:EPSG::2056",
    }
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    blocks = re.findall(r"<wfs:member>(.*?)</wfs:member>", resp.text, re.S)
    results = []
    for block in blocks:
        attrs: dict[str, str] = {}
        for tag, value in re.findall(r"<ms:(\w+)>(.*?)</ms:\1>", block, re.S):
            attrs[tag] = value.strip()
        results.append(attrs)
    return results


def _ist_inkraft(rechtsstatus_wert: Optional[str]) -> bool:
    """Normalisiert ueber die live beobachtete Schreibweisen-Inkonsistenz
    zwischen geodienste-Subdiensten ("inKraft" vs. "In Kraft")."""
    return (rechtsstatus_wert or "").strip().lower().replace(" ", "") == "inkraft"


def _parzelle_bbox_mit_marge(
    parzelle_ring: list[tuple[float, float]], marge_m: float = _BBOX_MARGE_M
) -> tuple[float, float, float, float]:
    xs = [p[0] for p in parzelle_ring]
    ys = [p[1] for p in parzelle_ring]
    return (min(xs) - marge_m, min(ys) - marge_m, max(xs) + marge_m, max(ys) + marge_m)


def _als_valides_polygon(ring: list[tuple[float, float]]) -> Polygon:
    poly = Polygon(ring)
    return poly if poly.is_valid else poly.buffer(0)


# ---------------------------------------------------------------------------
# Gewaesserraum
# ---------------------------------------------------------------------------

def hole_gewaesserraum_flaechen(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    rohdaten = _wfs_get_features(GEWAESSERRAUM_WFS_URL, "ms:gewaesserraum", bbox)
    flaechen = []
    for raw in rohdaten:
        if not _ist_inkraft(raw.get("rechtsstatus")):
            continue
        if (raw.get("verzicht") or "").strip().lower() == "ja":
            continue
        for koordinaten in extrahiere_koordinatenlisten(raw.get("wkb_geometry") or ""):
            flaechen.append(
                {"koordinaten": koordinaten, "gewaessername": raw.get("gewaessername"), "kanton": raw.get("kanton")}
            )
    return flaechen


# ---------------------------------------------------------------------------
# Waldgrenzen (nur Geometrie -- Waldabstand siehe Modul-Docstring)
# ---------------------------------------------------------------------------

def hole_waldgrenzen(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    rohdaten = _wfs_get_features(WALDGRENZEN_WFS_URL, "ms:waldgrenzen", bbox)
    linien = []
    for raw in rohdaten:
        if not _ist_inkraft(raw.get("rechtsstatus")):
            continue
        for koordinaten in extrahiere_koordinatenlisten(raw.get("wkb_geometry") or ""):
            linien.append({"koordinaten": koordinaten, "art": raw.get("art"), "kanton": raw.get("kanton")})
    return linien


# ---------------------------------------------------------------------------
# Baulinien (Kategorie 71) -> Restriktionsflaeche
# ---------------------------------------------------------------------------

def baulinien_aus_festlegungen(festlegungen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        f for f in festlegungen
        if f.get("hauptnutzung_code") == BAULINIEN_KATEGORIE
        and f.get("ist_rechtskraeftig")
        and f.get("geometrie_koordinaten")
    ]


def _linie_verlaengern(koordinaten: list[tuple[float, float]], verlaengerung_m: float = _LINIE_VERLAENGERUNG_M):
    if len(koordinaten) < 2:
        return None
    x1, y1 = koordinaten[0]
    x2, y2 = koordinaten[-1]
    dx, dy = x2 - x1, y2 - y1
    laenge = math.hypot(dx, dy)
    if laenge == 0:
        return None
    ux, uy = dx / laenge, dy / laenge
    start = (x1 - ux * verlaengerung_m, y1 - uy * verlaengerung_m)
    ende = (x2 + ux * verlaengerung_m, y2 + uy * verlaengerung_m)
    return LineString([start, ende])


def baulinie_zu_restriktionsflaeche(
    koordinaten: list[tuple[float, float]], parzelle_ring: list[tuple[float, float]]
) -> Optional[list[tuple[float, float]]]:
    """Wandelt eine Baulinien-Geometrie in eine Restriktionsflaeche um (siehe
    Modul-Docstring fuer die Mehrheitsseiten-Annahme). None, wenn die Linie
    die Parzelle nicht schneidet (Baulinie liegt ausserhalb, kein Effekt)."""
    parzelle = _als_valides_polygon(parzelle_ring)
    verlaengerte_linie = _linie_verlaengern(koordinaten)
    if verlaengerte_linie is None or not parzelle.intersects(verlaengerte_linie):
        return None
    try:
        teile = split(parzelle, verlaengerte_linie)
    except Exception:
        return None
    polygone = [g for g in teile.geoms if g.geom_type == "Polygon"]
    if len(polygone) < 2:
        return None
    polygone.sort(key=lambda g: g.area)
    return list(polygone[0].exterior.coords)  # kleinere Seite = Restriktion (Annahme)


# ---------------------------------------------------------------------------
# Oeffentliche Hauptfunktion
# ---------------------------------------------------------------------------

def hole_restriktionen_fuer_parzelle(
    e: float,
    n: float,
    kanton: Optional[str],
    parzelle_ring: list[tuple[float, float]],
    *,
    waldabstand_m: Optional[float] = None,
    baulinien_radius_m: float = _BAULINIEN_SUCH_RADIUS_M,
) -> dict[str, Any]:
    """Fragt Gewaesserraum, Waldgrenzen und Baulinien fuer die Umgebung einer
    Parzelle ab und liefert eine direkt fuer
    baubereich.berechne_potenzial(restriktionsflaechen=...) nutzbare Liste,
    plus Rohdaten und transparente Hinweise zu jeder Annahme/Einschraenkung.
    """
    hinweise: list[str] = []
    bbox = _parzelle_bbox_mit_marge(parzelle_ring)
    parzelle_poly = _als_valides_polygon(parzelle_ring)

    try:
        gewaesserraum_roh = hole_gewaesserraum_flaechen(bbox)
    except requests.exceptions.RequestException as exc:
        gewaesserraum_roh = []
        hinweise.append(f"Gewaesserraum-Abfrage fehlgeschlagen: {exc}")

    gewaesserraum_flaechen = []
    for gr in gewaesserraum_roh:
        poly = _als_valides_polygon(gr["koordinaten"])
        if parzelle_poly.intersects(poly):
            gewaesserraum_flaechen.append(gr)

    try:
        waldgrenzen_roh = hole_waldgrenzen(bbox)
    except requests.exceptions.RequestException as exc:
        waldgrenzen_roh = []
        hinweise.append(f"Waldgrenzen-Abfrage fehlgeschlagen: {exc}")

    waldgrenze_min_abstand_m = None
    for wg in waldgrenzen_roh:
        abstand = parzelle_poly.distance(LineString(wg["koordinaten"]))
        if waldgrenze_min_abstand_m is None or abstand < waldgrenze_min_abstand_m:
            waldgrenze_min_abstand_m = abstand

    wald_restriktion = None
    if waldgrenzen_roh and waldabstand_m is not None:
        naechste = min(waldgrenzen_roh, key=lambda wg: parzelle_poly.distance(LineString(wg["koordinaten"])))
        wald_restriktion_poly = LineString(naechste["koordinaten"]).buffer(waldabstand_m)
        wald_restriktion = list(wald_restriktion_poly.exterior.coords)
        hinweise.append(
            f"Waldabstand {waldabstand_m} m manuell uebergeben -> naechste Waldgrenze wurde "
            f"per Linien-Buffer(radius={waldabstand_m} m) in eine Restriktionsflaeche "
            "umgerechnet (Naeherung: ein echter Waldabstand ist KEIN gleichmaessiger "
            "Radius-Buffer um die gesamte Linie, sondern eine parallel versetzte Linie -- "
            "fuer die Groessenordnung der Flaeche ist der Unterschied bei den bisher "
            "getesteten Parzellen aber vernachlaessigbar)."
        )
    elif waldgrenzen_roh:
        hinweise.append(
            f"Waldgrenze gefunden (naechster Punkt {waldgrenze_min_abstand_m:.1f} m von der "
            "Parzelle entfernt), aber kein waldabstand_m uebergeben -- Restriktion NICHT "
            "automatisch angewendet. Der gesetzliche Waldabstand ist kantonal/kommunal "
            "unterschiedlich geregelt und liegt aktuell nicht als strukturierte, "
            "maschinenlesbare Quelle vor (nur die Grenzliniengeometrie selbst)."
        )

    try:
        klass = klassifiziere_nutzung(e, n, kanton, radius_m=baulinien_radius_m)
        alle_festlegungen = klass.get("festlegungen", []) if klass.get("gefunden") else []
    except NutzungsklassifikationError as exc:
        alle_festlegungen = []
        hinweise.append(f"Baulinien-Abfrage (ueber Nutzungsklassifikation) fehlgeschlagen: {exc}")

    baulinien = baulinien_aus_festlegungen(alle_festlegungen)
    baulinien_restriktionen = []
    for bl in baulinien:
        for koordinaten in bl["geometrie_koordinaten"]:
            restriktion = baulinie_zu_restriktionsflaeche(koordinaten, parzelle_ring)
            if restriktion:
                baulinien_restriktionen.append(restriktion)
    if baulinien:
        hinweise.append(
            f"{len(baulinien)} rechtskraeftige Baulinie(n) (foederale Kategorie 71) im "
            f"Radius {baulinien_radius_m:.0f} m gefunden. Welche Seite Baugebiet ist, wurde "
            "ueber die flaechenmaessige Mehrheitsseite der Parzelle angenommen (keine "
            "amtliche Quelle liefert das direkt) -- siehe baulinie_zu_restriktionsflaeche()."
        )

    restriktionsflaechen_fuer_g1 = (
        [gr["koordinaten"] for gr in gewaesserraum_flaechen]
        + ([wald_restriktion] if wald_restriktion else [])
        + baulinien_restriktionen
    )

    return {
        "gefunden": True,
        "gewaesserraum_flaechen": gewaesserraum_flaechen,
        "waldgrenzen_gefunden": bool(waldgrenzen_roh),
        "waldgrenze_min_abstand_m": round(waldgrenze_min_abstand_m, 1) if waldgrenze_min_abstand_m is not None else None,
        "waldabstand_m_verwendet": waldabstand_m,
        "baulinien_gefunden": baulinien,
        "restriktionsflaechen_fuer_g1": restriktionsflaechen_fuer_g1,
        "hinweise": hinweise,
    }

"""
Modul 1: Geo-Data & Registry Ingestion
========================================
Nimmt eine Schweizer Adresse entgegen und ermittelt darauf aufbauend:
  1. LV95-Koordinaten (Geocoding via api3.geo.admin.ch)
  2. Kataster-Daten: EGRID, Parzellennummer, Parzellenflaeche, Gemeinde, Kanton
  3. GWR-Bestandsdaten: EGID, Baujahr, Geschosse, Gebaeudekategorie, Grundflaeche
  4. OEREB-Daten: oeffentlich-rechtliche Eigentumsbeschraenkungen inkl. Links zu
     kommunalen Bau- und Zonenordnungen (BZO), sofern der jeweilige Kanton den
     Bundes-OEREB-Webservice bedient. Umfasst auch 4 der foederal standardisierten
     Umwelt-/Risikothemen: Belastete Standorte (KbS), Grundwasserschutz,
     Gewaesserraum, Laermempfindlichkeitsstufen (siehe umweltrisiken-Feld).
  5. Radon-Risikoeinstufung (BAG-Layer, unabhaengig vom OEREB-Kataster).
  6. Topografie: Hoehe, Hangneigung (Grad/%), Ausrichtung -- berechnet aus
     swissALTI3D-Punktsampling (Pydantic-Modell Topographie).
  7. Erschliessung: Distanz zur naechsten OeV-Haltestelle (transport.opendata.ch),
     Schule/Spital/Supermarkt (OpenStreetMap Overpass) -- Pydantic-Modell
     Umgebung, inkl. explizitem 'fehler'-Feld, damit eine fehlgeschlagene
     Abfrage nie wie ein verifizierter Negativbefund aussieht.

Bewusst NICHT abgedeckt (recherchiert, aber keine verlaessliche bundesweite
Quelle gefunden -- siehe Kommentar bei _ENV_THEME_GROUPS): Naturgefahren-
Gefahrenkarten und Erdwaermesonden-Eignung. Beides ist nur kantonal
publiziert, falls ueberhaupt offen zugaenglich.

Alle Aufrufe laufen ueber oeffentliche, unauthentifizierte Bundes-APIs
(api3.geo.admin.ch, oereb.geo.admin.ch). Es werden keine Credentials benoetigt.

WICHTIGER HINWEIS zu OEREB:
Die Attributnamen der Kataster- (AV) und GWR-Layer koennen sich je nach
swisstopo-Release leicht unterscheiden, und nicht jeder Kanton bedient den
foederalen OEREB-Webservice unter der gleichen Struktur (manche liefern nur
eine Teilmenge der Thema-Layer). Deshalb liefert dieses Skript IMMER die
rohen Attribute mit ("raw_attributes" / "raw_extract"), zusaetzlich zu einer
best-effort normalisierten Sicht. So bleibt das Modul auch dann nutzbar, wenn
ein Feldname fuer einen bestimmten Kanton abweicht.

CLI:
    python modul1_geodata.py "Bahnhofstrasse 1, 8001 Zuerich"

Als Bibliothek:
    from potenzial_engine.modul1_geodata import run_modul1
    result = run_modul1("Bahnhofstrasse 1, 8001 Zuerich")
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Optional

import math
import urllib.parse
import xml.etree.ElementTree as ElementTree

import requests
from pydantic import BaseModel

from .modul1b_nutzungsklassifikation import klassifiziere_nutzung
from .restriktionsgeometrie import hole_restriktionen_fuer_parzelle

GEOADMIN_BASE = "https://api3.geo.admin.ch/rest/services/api"
HEIGHT_URL = "https://api3.geo.admin.ch/rest/services/height"
TRANSPORT_OPENDATA_URL = "https://transport.opendata.ch/v1/locations"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bekannte swisstopo-Layer-IDs (stabil, oeffentlich dokumentiert)
LAYER_PARCEL = "ch.swisstopo-vd.amtliche-vermessung"
LAYER_MUNICIPALITY = "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"
LAYER_GWR = "ch.bfs.gebaeude_wohnungs_register"
LAYER_CADASTRE_GEOM = "ch.kantone.cadastralwebmap-farbe"

# ---------------------------------------------------------------------------
# OEREB-Kataster: es gibt KEINEN einheitlichen Bundes-Proxy. Jeder Kanton
# betreibt seinen eigenen OEREB-Webservice unter einer eigenen Basis-URL
# (Quelle: cadastre.ch, Stand August 2026). Fehlt ein Kanton in dieser Liste,
# wird das transparent gemeldet statt einen falschen Endpunkt zu erraten --
# das Feld muss dann per Hand mit der Basis-URL des jeweiligen Kantons
# ergaenzt werden (siehe https://www.cadastre.ch/de/oereb-webservice).
#
# Templates verwenden {base}, {fmt} (xml|json|pdf) und {egrid}.
# ---------------------------------------------------------------------------
OEREB_CANTON_SERVICES: dict[str, str] = {
    "ZH": "https://maps.zh.ch/oereb/v2/extract/{fmt}?EGRID={egrid}",
    "BS": "https://api.oereb.bs.ch/extract/{fmt}/?EGRID={egrid}",
    "TG": "https://map.geo.tg.ch/services/oereb/extract/{fmt}?EGRID={egrid}",
    "BL": "https://oereb.geo.bl.ch/extract/{fmt}/?EGRID={egrid}",
    "AG": "https://api.geo.ag.ch/v2/oereb/extract/{fmt}/?EGRID={egrid}",
    "LU": "https://svc.geo.lu.ch/oereb/extract/{fmt}/?EGRID={egrid}",
    # SG: live verifiziert 2026-09-03 -- echter EGRID (CH427712875908) liefert
    # 200 mit gueltigem openoereb-Schema in JSON UND XML, Amt fuer
    # Raumentwicklung und Geoinformation SG als PLRCadastreAuthority. Gefunden
    # ueber Websuche (vorherige Recherche 2026-08-26 hatte dies noch nicht
    # gefunden -- Endpunkt war entweder neu oder schlicht nicht auffindbar).
    "SG": "https://oereb.geo.sg.ch/ktsg/wsgi/oereb/extract/{fmt}/?EGRID={egrid}",
    # BE: live verifiziert 2026-09-11 mit echtem EGRID (CH856146853576,
    # Guemligen) -- 200 mit gueltigem openoereb-Schema, "Amt fuer
    # Geoinformation" als PLRCadastreAuthority, 7 Restriktionen inkl. 3x
    # ch.Nutzungsplanung, 32 Rechtsvorschriften. Die amtliche LandRegistryArea
    # (4886 m2) deckte sich mit der unabhaengig aus der Katastergeometrie
    # berechneten Flaeche (4884 m2) -- unabhaengige Bestaetigung.
    # Warum die Recherche vom 26.08. das verfehlte: der Pfad hat KEIN
    # "/oereb/"-Segment, die Basis ist direkt "/extract/{fmt}/".
    "BE": "https://www.oereb.apps.be.ch/extract/{fmt}/?EGRID={egrid}",
    # SO: live verifiziert 2026-09-11. Der HTTP 415 vom 26.08. war kein
    # geaenderter Endpunkt, sondern die Formatwahl: Solothurn liefert
    # AUSSCHLIESSLICH XML, JSON quittiert es mit 415. Mit dem Beispiel-EGRID
    # der Kantonsdoku (CH857632820629): 151 KB, 12 Restriktionen, 66
    # Rechtsvorschriften, darunter Zonenreglement und Baureglement.
    "SO": "https://geo.so.ch/api/oereb/extract/{fmt}/?EGRID={egrid}",
}

# Kantone, deren Webservice KEIN JSON liefert. Der Auszug ist derselbe
# (openoereb, schemas.geo.admin.ch/V_D/OeREB/2.0) -- nur die Serialisierung
# unterscheidet sich, deshalb wird XML nach dem Abruf in dieselbe Struktur
# ueberfuehrt und von denselben Extraktoren ausgewertet.
OEREB_CANTON_FORMAT: dict[str, str] = {
    "SO": "xml",
}

# Recherchiert, aber KEIN funktionierender Endpunkt gefunden (Stand 2026-09-03)
# -- GR, ZG, SH, BE, AR, AI. Erschoepfte Wege: Websuche nach dem ueblichen
# "{domain}/extract/json?EGRID=..."-Muster, offizielle cadastre.ch-Doku (listet
# keine kantonalen URLs), opendata.swiss package_search pro Kanton, sowie ein
# vermeintlicher Universal-Proxy "proxy.oereb.services" aus einem Fachblog, der
# jedoch nicht auflöst (DNS-Fehler -- vermutlich stillgelegt oder umbenannt).
# SG ist zusaetzlich eine Angular-SPA (oereb.geo.sg.ch) ohne im JS-Bundle oder
# ueblichen Config-Pfaden auffindbare API-Basis-URL. Kein weiteres Raten --
# naechster Schritt waere direkter Kontakt mit dem jeweiligen kantonalen GIS-
# Amt (analog zur Erkenntnis bei BL/TG im Akquisitionsradar-Projekt).

DEFAULT_TIMEOUT = 20
USER_AGENT = "gebimo-immo-potenzial-engine/1.0 (+internal tool)"

# Manche Gemeinde-Websites weisen unbekannte User-Agents ab (live beobachtet:
# Berlingen TG, HTTP 403 beim Abruf des Baureglements). Der Browser-UA wird
# NUR als zweiter Versuch verwendet -- der ehrliche Werkzeug-UA bleibt der
# Normalfall.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def _get_mit_wiederholung(
    url: str, timeout: int = DEFAULT_TIMEOUT, versuche: int = 3, **kwargs
) -> requests.Response:
    """GET mit Wiederholung bei voruebergehenden Stoerungen.

    Zwei real beobachtete Faelle (Stand 11.09.2026) haben diese Funktion
    ausgeloest:
      * api3.geo.admin.ch brach einmalig mit ReadTimeout ab -- ein
        Wiederholungsversuch haette gereicht
      * eine Gemeinde-Website (Berlingen TG) antwortete dem Werkzeug-UA mit
        HTTP 403; mit Browser-UA laesst sie das oeffentliche Dokument zu

    Nicht wiederholt werden echte Ablehnungen (404, 410) -- dort waere jeder
    weitere Versuch sinnlos.
    """
    letzter_fehler: Optional[Exception] = None
    for versuch in range(versuche):
        kopfzeilen = dict(kwargs.pop("headers", {}) or {})
        if versuch > 0:
            kopfzeilen["User-Agent"] = BROWSER_USER_AGENT
        try:
            resp = session.get(url, timeout=timeout, headers=kopfzeilen or None, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            letzter_fehler = exc
            time.sleep(1.5 * (versuch + 1))
            continue
        if resp.status_code in (403, 429, 500, 502, 503, 504) and versuch < versuche - 1:
            letzter_fehler = requests.exceptions.HTTPError(f"HTTP {resp.status_code}", response=resp)
            time.sleep(1.5 * (versuch + 1))
            continue
        return resp
    raise letzter_fehler if letzter_fehler else requests.exceptions.RequestException(url)


class Modul1Error(Exception):
    """Fehler innerhalb der Geo-Data-Ingestion-Pipeline."""


def _get(url: str, params: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> Any:
    """Zentrale GET-Abfrage aller Bundes-Geodienste.

    Laeuft ueber _get_mit_wiederholung(), weil api3.geo.admin.ch gelegentlich
    mit ReadTimeout abbricht (live beobachtet 11.09.2026 -- ein ganzer
    Analyselauf scheiterte daran, obwohl ein Wiederholungsversuch genuegt
    haette).
    """
    resp = _get_mit_wiederholung(url, timeout=timeout, params=params)
    resp.raise_for_status()
    return resp.json()


def _first_key(attrs: dict[str, Any], candidates: list[str]) -> Optional[Any]:
    """Sucht case-insensitiv nach dem ersten passenden Feldnamen."""
    lower_map = {k.lower(): v for k, v in attrs.items()}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


# ---------------------------------------------------------------------------
# 1. Geocoding
# ---------------------------------------------------------------------------

def geocode_address(address: str) -> dict[str, Any]:
    """Wandelt eine Schweizer Adresse in LV95-Koordinaten (E, N) um.

    Nutzt den SearchServer von geo.admin.ch mit sr=2056 (LV95).
    """
    params = {
        "searchText": address,
        "type": "locations",
        "origins": "address",
        "limit": 5,
        "sr": 2056,
    }
    data = _get(f"{GEOADMIN_BASE}/SearchServer", params)
    results = data.get("results", [])
    if not results:
        raise Modul1Error(f"Adresse nicht gefunden: {address!r}")

    best = results[0]["attrs"]
    return {
        "query": address,
        "matched_label": best.get("label", "").replace("<b>", "").replace("</b>", ""),
        "lv95_e": best.get("y"),  # geo.admin liefert E in "y", N in "x"
        "lv95_n": best.get("x"),
        "wgs84_lat": best.get("lat"),
        "wgs84_lon": best.get("lon"),
        "canton_hint": best.get("detail", "").split()[-1] if best.get("detail") else None,
        "raw": best,
    }


# ---------------------------------------------------------------------------
# 2. Generisches MapServer-Identify (fuer Kataster / Gemeinde / GWR)
# ---------------------------------------------------------------------------

def _identify(
    e: float, n: float, layer: str, tolerance: int = 5, return_geometry: bool = False
) -> list[dict[str, Any]]:
    """Fragt einen geo.admin.ch MapServer-Layer per Punktkoordinate ab."""
    half = 1000
    params = {
        "geometry": f"{e},{n}",
        "geometryType": "esriGeometryPoint",
        "layers": f"all:{layer}",
        "tolerance": tolerance,
        "mapExtent": f"{e - half},{n - half},{e + half},{n + half}",
        "imageDisplay": "1000,1000,96",
        "sr": 2056,
        "returnGeometry": "true" if return_geometry else "false",
    }
    if return_geometry:
        # ACHTUNG: geometryFormat=geojson schaltet die GESAMTE Antwort auf
        # GeoJSON-Konventionen um (Feature-Attribute stehen dann unter
        # "properties" statt "attributes") -- deshalb NUR setzen, wenn
        # tatsaechlich Geometrie angefordert wird, sonst brechen alle
        # anderen _identify()-Aufrufe (die auf "attributes" lesen) still.
        params["geometryFormat"] = "geojson"
    data = _get(f"{GEOADMIN_BASE}/MapServer/identify", params)
    return data.get("results", [])


# Der Identify-Dienst liefert hoechstens so viele Treffer je Anfrage.
IDENTIFY_MAX_TREFFER = 200


def identify_rechteck(
    bbox: tuple[float, float, float, float],
    layer: str,
    *,
    return_geometry: bool = False,
    limit: int = IDENTIFY_MAX_TREFFER,
) -> list[dict[str, Any]]:
    """Fragt einen Layer fuer ein ganzes RECHTECK ab statt fuer einen Punkt.

    Derselbe Dienst, dieselben Layer wie `_identify` -- nur mit
    `esriGeometryEnvelope` statt `esriGeometryPoint`. Das ist die Grundlage
    des Gebietsscreenings: eine Anfrage liefert bis zu 200 Parzellen samt
    Geometrie, statt 200 Einzelabfragen.

    ACHTUNG: Liefert die Antwort genau `limit` Treffer, ist sie mit hoher
    Wahrscheinlichkeit abgeschnitten. Der Aufrufer muss das Rechteck dann
    teilen -- sonst fehlen Parzellen, ohne dass es jemand merkt.
    """
    xmin, ymin, xmax, ymax = bbox
    params = {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "layers": f"all:{layer}",
        "tolerance": 0,
        "mapExtent": f"{xmin},{ymin},{xmax},{ymax}",
        "imageDisplay": "500,500,96",
        "sr": 2056,
        "returnGeometry": "true" if return_geometry else "false",
        "limit": limit,
    }
    if return_geometry:
        # Siehe _identify(): geometryFormat=geojson verschiebt die Attribute
        # nach "properties" -- deshalb nur setzen, wenn Geometrie gebraucht wird.
        params["geometryFormat"] = "geojson"
    data = _get(f"{GEOADMIN_BASE}/MapServer/identify", params)
    return data.get("results", [])


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-Casting-Test, ob Punkt (x,y) innerhalb eines Polygons liegt."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_area_m2(ring: list[tuple[float, float]]) -> float:
    """Shoelace-Formel -- Koordinaten in Metern (EPSG:2056), Ergebnis direkt in m2."""
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def get_parcel_geometry_ring(e: float, n: float) -> Optional[list[tuple[float, float]]]:
    """Liefert das Parzellenpolygon (LV95/EPSG:2056-Koordinatenring) ueber den
    kantonsuebergreifenden Katasterplan-Layer (ch.kantone.cadastralwebmap-farbe).

    Das ist dieselbe Geometrie, die vorher nur intern fuer die Flaechen-
    Fallback-Berechnung (Shoelace) genutzt wurde -- jetzt zusaetzlich als
    eigene Funktion exponiert, damit G1 (baubereich.py) mit der ECHTEN
    Parzellengeometrie statt nur mit der Flaechenzahl rechnen kann.
    """
    results = _identify(e, n, LAYER_CADASTRE_GEOM, tolerance=3, return_geometry=True)
    for r in results:
        geom = r.get("geometry")
        if not geom or geom.get("type") != "Polygon":
            continue
        ring = [(pt[0], pt[1]) for pt in geom["coordinates"][0]]
        if _point_in_polygon(e, n, ring):
            return ring
    return None


def get_parcel_area_m2(e: float, n: float) -> Optional[float]:
    """Ermittelt die amtliche Parzellenflaeche per Geometrie-Shoelace-Berechnung.

    Wird als Fallback genutzt, weil das "area"-Attribut im OpenData-AV-Layer
    (get_parcel_data) haeufig fehlt (z.B. bei ZH leer) -- die Geometrie selbst
    ist aber praktisch immer vorhanden. Dieselbe Methode wird bereits im
    bestehenden Akquisitionsradar-Projekt genutzt (extraction/geo_admin.py).
    """
    ring = get_parcel_geometry_ring(e, n)
    if ring is None:
        return None
    return round(_polygon_area_m2(ring), 1)


# ---------------------------------------------------------------------------
# 3. Kataster / Parzelle
# ---------------------------------------------------------------------------

def _waehle_treffer_am_punkt(
    results: list[dict[str, Any]], e: float, n: float
) -> tuple[dict[str, Any], str]:
    """Waehlt aus mehreren Toleranz-Treffern denjenigen, dessen Polygon den
    abgefragten Punkt tatsaechlich ENTHAELT -- dieselbe Pruefung, die
    get_parcel_geometry_ring() fuer die Geometrie schon macht.

    Hintergrund: _identify() arbeitet mit einer Pixel-Toleranz und liefert
    deshalb auch angrenzende Parzellen zurueck. Die Reihenfolge kommt vom
    Dienst und ist nicht stabil.

    Rueckgabe: (Attribute des gewaehlten Treffers, Auswahlmethode). Enthaelt
    keiner der Treffer den Punkt (z.B. Punkt exakt auf einer Parzellengrenze
    oder Geometrie fehlt), wird der erste Treffer verwendet und das
    transparent ueber die Auswahlmethode ausgewiesen -- kein stiller Default.
    """
    for r in results:
        geom = r.get("geometry") or {}
        if geom.get("type") != "Polygon" or not geom.get("coordinates"):
            continue
        ring = [(pt[0], pt[1]) for pt in geom["coordinates"][0]]
        if _point_in_polygon(e, n, ring):
            # Bei angeforderter Geometrie liefert der Dienst GeoJSON-
            # Konventionen: Attribute stehen unter "properties" statt
            # "attributes" (siehe Kommentar in _identify).
            return (r.get("properties") or r.get("attributes") or {}), "punkt_in_parzelle"
    erster = results[0]
    return (erster.get("properties") or erster.get("attributes") or {}), "erster_treffer_ohne_punktpruefung"


def get_parcel_data(e: float, n: float) -> dict[str, Any]:
    """Ermittelt EGRID, Parzellennummer und Flaeche ueber den OpenData-AV-Layer.

    WICHTIG: "OpenData-AV" ist die frei zugaengliche Teilmenge der amtlichen
    Vermessung. Nicht jede Gemeinde/jeder Kanton stellt seine Parzellendaten
    darin (vollstaendig) zur Verfuegung -- getestet funktioniert es u.a. fuer
    ZH und BS, waehrend z.B. Luzern hier keine Treffer liefert. Ein "found:
    false" kann also eine echte Deckungsluecke der offenen Daten sein, nicht
    zwingend ein falscher Punkt.
    """
    # Geometrie MIT abfragen: die Toleranzabfrage liefert regelmaessig mehrere
    # benachbarte Parzellen (in Buchs AG z.B. vier), und die Reihenfolge des
    # Dienstes ist NICHT stabil und stellt die tatsaechlich getroffene Parzelle
    # nicht zwingend nach vorne. Frueher wurde ungeprueft results[0] genommen --
    # dadurch konnten EGRID und Parzellennummer von einer NACHBARparzelle
    # stammen, waehrend die Flaeche aus der richtigen Geometrie kam. Da der
    # EGRID die gesamte OEREB-Abfrage steuert (Zonen, Rechtsvorschriften),
    # wurde im Extremfall das falsche Grundstueck analysiert.
    results = _identify(e, n, LAYER_PARCEL, return_geometry=True)
    if not results:
        return {
            "found": False,
            "reason": "Kein Kataster-Objekt an diesem Punkt gefunden (evtl. keine OpenData-AV-Deckung fuer diese Gemeinde).",
        }

    attrs, auswahl_methode = _waehle_treffer_am_punkt(results, e, n)
    # Geometrie EINMAL abrufen (statt separat pro Aufrufer) -- wird sowohl als
    # Flaechen-Fallback als auch direkt fuer G1 (baubereich.py) gebraucht, das
    # die ECHTE Parzellenkontur statt nur die Flaechenzahl braucht.
    parzellengeometrie = get_parcel_geometry_ring(e, n)

    flaeche_m2 = _first_key(attrs, ["area", "flaeche", "shape_area"])
    flaeche_quelle = "av_attribut" if flaeche_m2 is not None else None

    if flaeche_m2 is None:
        # Attribut fehlt haeufig (z.B. ZH) -- Flaeche stattdessen aus der
        # Katasterplan-Geometrie berechnen (Shoelace).
        flaeche_m2 = round(_polygon_area_m2(parzellengeometrie), 1) if parzellengeometrie else None
        flaeche_quelle = "geometrie_berechnet" if flaeche_m2 is not None else None

    return {
        "found": True,
        "egrid": _first_key(attrs, ["egris_egrid", "egrid"]),
        "parzellennummer": _first_key(attrs, ["number", "nummer", "parcel_number", "objektname"]),
        "flaeche_m2": flaeche_m2,
        "flaeche_quelle": flaeche_quelle,
        "parzellengeometrie": parzellengeometrie,
        "identdn": _first_key(attrs, ["identdn", "ident_dn"]),
        "parzellenauswahl": auswahl_methode,
        "raw_attributes": attrs,
    }


def get_municipality_data(e: float, n: float) -> dict[str, Any]:
    """Ermittelt Gemeindename, BFS-Gemeindenummer und Kanton.

    Der Layer liefert historische Zeitscheiben der Gemeindegrenzen (eine pro
    Grenzmutation seit 1850). Wir filtern deshalb explizit auf den mit
    is_current_jahr=true markierten, aktuell gueltigen Eintrag.
    """
    results = _identify(e, n, LAYER_MUNICIPALITY)
    if not results:
        return {"found": False, "reason": "Keine Gemeinde-Flaeche an diesem Punkt gefunden."}

    current = [r for r in results if r.get("attributes", {}).get("is_current_jahr") is True]
    chosen = current[0] if current else max(
        results, key=lambda r: r.get("attributes", {}).get("jahr", 0)
    )
    attrs = chosen.get("attributes", {})
    return {
        "found": True,
        "gemeinde": _first_key(attrs, ["name", "gemname", "gemeindename"]),
        "bfs_nummer": _first_key(attrs, ["bfs_nummer", "gde_nr", "gemeinde_bfs_nummer", "id"]),
        "kanton": _first_key(attrs, ["kanton", "kantonsname"]),
        "raw_attributes": attrs,
    }


# ---------------------------------------------------------------------------
# 4. GWR (Gebaeude- und Wohnungsregister)
# ---------------------------------------------------------------------------

def get_gwr_data(e: float, n: float) -> dict[str, Any]:
    """Ermittelt Gebaeudebestandsdaten (EGID, Baujahr, Geschosse, Kategorie, Flaeche).

    Hinweis: Liegt der Adresspunkt nicht exakt auf dem Gebaeude-Polygon/Punkt
    (z.B. bei Neubauprojekten auf unbebauter Parzelle), liefert dieser Layer
    keinen Treffer -- das ist erwartetes Verhalten, kein Fehler.
    """
    results = _identify(e, n, LAYER_GWR, tolerance=10)
    if not results:
        return {"found": False, "reason": "Kein GWR-Gebaeudeeintrag an diesem Punkt (evtl. unbebaute Parzelle)."}

    attrs = results[0].get("attributes", {})
    return {
        "found": True,
        "egid": _first_key(attrs, ["egid"]),
        "baujahr": _first_key(attrs, ["gbauj", "baujahr"]),
        "anzahl_geschosse": _first_key(attrs, ["gastw", "geschosse"]),
        "gebaeudekategorie_gkat": _first_key(attrs, ["gkat", "gebaeudekategorie"]),
        "gebaeudeklasse_gklas": _first_key(attrs, ["gklas", "gebaeudeklasse"]),
        "grundflaeche_m2": _first_key(attrs, ["garea", "gebaeudeflaeche", "flaeche"]),
        "energiebezugsflaeche_m2": _first_key(attrs, ["gebf"]),
        "gebaeudevolumen_m3": _first_key(attrs, ["gvol"]),
        "raw_attributes": attrs,
    }


# ---------------------------------------------------------------------------
# 5. OEREB (Oeffentlich-rechtliche Eigentumsbeschraenkungen)
# ---------------------------------------------------------------------------

def _find_pdf_links(node: Any, found: Optional[list[str]] = None) -> list[str]:
    """Durchsucht ein verschachteltes OEREB-JSON rekursiv nach PDF-/Dokument-Links
    (z.B. Legenden, Themenblaetter), unabhaengig von der genauen Struktur pro Kanton.

    ACHTUNG: Dies ist nur ein grober Fallback. Die eigentlichen Rechtsvorschriften
    (Bauordnung/BZO-Reglement) stecken im eCH-0122-Standard NICHT als ".pdf"-Link,
    sondern in RealEstate.RestrictionOnLandownership[].LegalProvisions[].TextAtWeb --
    siehe _extract_legal_provisions() unten, die deshalb bevorzugt genutzt wird.
    """
    if found is None:
        found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and value.lower().startswith("http") and ".pdf" in value.lower():
                if value not in found:
                    found.append(value)
            else:
                _find_pdf_links(value, found)
    elif isinstance(node, list):
        for item in node:
            _find_pdf_links(item, found)
    return found


# Bundesrecht wird ausschliesslich auf diesen beiden Plattformen publiziert
# und kann per Definition NIE eine kommunale Zonenvorschrift enthalten
# (Raumplanungsgesetz, Umweltschutzgesetz etc. sind reines Rahmenrecht).
_BUNDESRECHT_HOSTS = ("fedlex.admin.ch", "lexfind.ch")

# Kantonale SYSTEMATISCHE Gesetzessammlungen (verschiedene Kantone nutzen
# dieselbe Software-Familie unter je eigener Domain) -- fuehren kantonales
# Rahmenrecht (Planungs-/Baugesetz, Vollzugsverordnungen). Enthalten SELTEN,
# aber nicht nie, zonenrelevante Zahlen (z.B. kantonsweite Wald-/Gewaesser-
# abstaende) -- werden deshalb nachrangig behandelt, nicht ausgeschlossen.
_KANTONALE_SAMMLUNG_HOST_HINWEISE = ("clex.ch", "rechtsbuch.", "gesetzessammlungen.", "rechtssammlung.")


def _rechtsebene_aus_url(url: str) -> str:
    """Klassifiziert eine Rechtsvorschrift-URL strukturell nach ihrer Hosting-
    Plattform statt nach Titel-Stichworten (die je nach Gemeinde/Kanton stark
    variieren -- z.B. heisst das massgebende Reglement in Liestal schlicht
    "Zentrum", nicht "Bauordnung"/"BZO"). Alles, was NICHT auf einer bekannten
    Bundesrechts- oder kantonalen Sammlungsplattform liegt (also insbesondere
    die OEREB-eigenen parzellenbezogenen Dokumentablagen oereblex.*.ch,
    oerebdocs.*.ch etc.), gilt als potenziell kommunal/parzellenspezifisch --
    denn genau dafuer existiert das OEREB-Rechtsvorschriften-Register.

    Live verifiziert (2026-08-28) an echten Faellen in AG/BL/TG: das
    kommunale Reglement liegt IMMER auf einer parzellenbezogenen OEREB-
    Dokumentablage, waehrend Bundesrecht (fedlex.admin.ch) und kantonales
    Rahmenrecht (bl.clex.ch, rechtsbuch.tg.ch, gesetzessammlungen.ag.ch) auf
    separaten, erkennbaren Domains liegen. ZH ist ein bekannter Grenzfall:
    dort liegt SOWOHL das kommunale Reglement als auch kantonales Recht
    (PBG/RPG) auf derselben oerebdocs.zh.ch-Domain -- fuer ZH liefert diese
    Funktion deshalb fuer beide "kommunal_oder_parzellenspezifisch", eine
    hostbasierte Unterscheidung ist dort strukturell nicht moeglich.
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(host == h or host.endswith("." + h) for h in _BUNDESRECHT_HOSTS):
        return "bundesrecht"
    if any(hinweis in host for hinweis in _KANTONALE_SAMMLUNG_HOST_HINWEISE):
        return "kantonale_gesetzessammlung"
    return "kommunal_oder_parzellenspezifisch"


def _ist_nutzungsplanung_theme(theme_code: str) -> bool:
    """Grundnutzung/zonenrelevante OEREB-Themen (foederal standardisierter
    Theme-Code) -- schliesst projektierte/haengige Planaenderungen aus.
    Gemeinsam genutzt von _extract_legal_provisions() und
    _extract_official_zone_labels(), damit beide Funktionen exakt dieselbe
    Definition von "zonenrelevant" verwenden."""
    theme_lower = (theme_code or "").lower()
    return "nutzungsplanung" in theme_lower and "proj" not in theme_lower


def _extract_legal_provisions(extract: dict[str, Any]) -> list[dict[str, Any]]:
    """Liest RealEstate.RestrictionOnLandownership[].LegalProvisions[] aus dem
    OEREB-Extrakt (eCH-0122-Standard) und liefert eine deduplizierte, strukturierte
    Liste der Rechtsvorschriften inkl. Dokument-Link. Das ist die verlaessliche
    Quelle fuer die eigentliche Bauordnung/BZO -- nicht die generischen PDF-Legenden.

    "ist_wahrscheinlich_bzo_reglement" wird STRUKTURELL bestimmt (Theme-
    Zugehoerigkeit der Restriktion + Hosting-Plattform der Dokument-URL,
    siehe _ist_nutzungsplanung_theme()/_rechtsebene_aus_url()) statt ueber
    eine manuell gepflegte Titel-Stichwortliste -- die brach z.B. bei Liestal
    BL, wo das massgebende Reglement schlicht "Zentrum" heisst.
    """
    provisions: dict[str, dict[str, Any]] = {}
    restrictions = extract.get("RealEstate", {}).get("RestrictionOnLandownership", [])
    for restriction in restrictions:
        theme = _ci_get(restriction, "Theme", {}) or {}
        theme_code = _ci_get(theme, "Code", "") or ""
        ist_zonenrelevante_restriktion = _ist_nutzungsplanung_theme(theme_code)

        legend = _ci_get(restriction, "LegendText", []) or []
        zonen_bezug = " ".join(t.get("Text", "") for t in legend if t.get("Text")) or None

        for lp in _ci_get(restriction, "LegalProvisions", []) or []:
            title = " ".join(t.get("Text", "") for t in (_ci_get(lp, "Title", []) or []) if t.get("Text"))
            url_entries = _ci_get(lp, "TextAtWeb", []) or []
            url = url_entries[0].get("Text") if url_entries else None
            if not url:
                continue
            lawstatus = _ci_get(lp, "Lawstatus", {}) or {}
            lawstatus_list = _ci_get(lawstatus, "Text", []) or []
            lawstatus_text = lawstatus_list[0].get("Text") if lawstatus_list else _ci_get(lawstatus, "Code")
            office = _ci_get(lp, "ResponsibleOffice", {}) or {}
            office_name_list = _ci_get(office, "Name", []) or []
            office_name = office_name_list[0].get("Text") if office_name_list else None
            official_number_list = _ci_get(lp, "OfficialNumber", []) or []

            rechtsebene = _rechtsebene_aus_url(url)
            # Wahrscheinlich BZO-relevant: an einer zonenrelevanten Restriktion
            # haengend UND nicht auf einer reinen Bundesrechts-Plattform
            # (Bundesrecht kann strukturell nie eine kommunale Zonenvorschrift
            # enthalten, unabhaengig davon, an welcher Restriktion es haengt).
            is_bzo_like = ist_zonenrelevante_restriktion and rechtsebene != "bundesrecht"

            if url not in provisions:
                provisions[url] = {
                    "titel": title,
                    "url": url,
                    "rechtsstatus": lawstatus_text,
                    "amtliche_nummer": official_number_list[0].get("Text") if official_number_list else None,
                    "zustaendige_stelle": office_name,
                    "rechtsebene": rechtsebene,
                    "ist_wahrscheinlich_bzo_reglement": is_bzo_like,
                    # Zonenbezeichnung(en) (LegendText) der Restriktion(en), an
                    # denen dieses Dokument haengt -- ermoeglicht spaeter (siehe
                    # priorisiere_nach_basiszone()) eine Priorisierung ohne
                    # Titel-Stichworte: Dokumente, die an der Restriktion der
                    # TATSAECHLICHEN Grundnutzung dieser Parzelle haengen, sind
                    # deutlich wahrscheinlicher das massgebende Reglement als
                    # solche, die nur an einer Ueberlagerung (Sondernutzungsplan,
                    # Gestaltungsplan) haengen.
                    "zonen_bezuege": [zonen_bezug] if zonen_bezug else [],
                }
            else:
                if ist_zonenrelevante_restriktion and not provisions[url]["ist_wahrscheinlich_bzo_reglement"]:
                    # Dieselbe URL kann an mehreren Restriktionen haengen (z.B.
                    # ein Dokument, das sowohl fuer die Grundnutzung als auch
                    # fuer eine Ueberlagerung zitiert wird) -- sobald IRGENDEINE
                    # davon zonenrelevant ist, gilt das Dokument als BZO-relevant.
                    provisions[url]["ist_wahrscheinlich_bzo_reglement"] = rechtsebene != "bundesrecht"
                if zonen_bezug and zonen_bezug not in provisions[url]["zonen_bezuege"]:
                    provisions[url]["zonen_bezuege"].append(zonen_bezug)

    # Sortierung: kommunal/parzellenspezifisch zuerst, dann kantonales
    # Rahmenrecht, Bundesrecht (nie BZO-relevant) zuletzt. Die feinere
    # Priorisierung nach tatsaechlicher Grundnutzung (Basiszone) erfolgt erst
    # in priorisiere_nach_basiszone(), da diese Funktion die Klassifikation
    # (Modul 1b) noch nicht kennt.
    rechtsebene_rang = {"kommunal_oder_parzellenspezifisch": 0, "kantonale_gesetzessammlung": 1, "bundesrecht": 2}
    return sorted(
        provisions.values(),
        key=lambda p: (not p["ist_wahrscheinlich_bzo_reglement"], rechtsebene_rang.get(p["rechtsebene"], 1)),
    )


def priorisiere_nach_basiszone(
    rechtsvorschriften: list[dict[str, Any]], basiszone_name: Optional[str]
) -> list[dict[str, Any]]:
    """Priorisiert Rechtsvorschriften zusaetzlich danach, ob sie an der
    Restriktion haengen, deren LegendText der TATSAECHLICHEN Grundnutzung
    dieser Parzelle entspricht (aus Modul 1b/klassifiziere_nutzung()).

    Notwendig, weil "kommunal_oder_parzellenspezifisch" (Theme+Host-basiert)
    allein bei Parzellen mit mehreren Ueberlagerungen/Sondernutzungsplaenen
    nicht ausreicht: live an Baden nachgewiesen, wo das massgebende BNO-
    Dokument in der reinen Theme/Host-Sortierung erst an Position 8 von 12
    landete (mehrere Gestaltungsplan-/Kantonaler-Nutzungsplan-Ueberlagerungen
    kamen davor), waehrend die BNO strukturell an der Restriktion mit
    LegendText "Kernzone 5 [K5]" haengt -- exakt der von Modul 1b unabhaengig
    (via geodienste.ch-WFS) bestimmten Basiszone. Reine Wortuebereinstimmung
    (Substring, case-insensitive) statt einer Titel-Stichwortliste -- verbindet
    zwei bereits unabhaengig verifizierte Datenquellen (OEREB-Extrakt und
    Modul 1b), statt eine neue Heuristik zu erfinden.
    """
    if not basiszone_name:
        return rechtsvorschriften
    basiszone_lower = basiszone_name.lower()

    def _trifft_basiszone(p: dict[str, Any]) -> bool:
        for zonen_bezug in p.get("zonen_bezuege", []):
            zb_lower = zonen_bezug.lower()
            if basiszone_lower in zb_lower or zb_lower in basiszone_lower:
                return True
        return False

    return sorted(
        rechtsvorschriften,
        key=lambda p: (not _trifft_basiszone(p), not p["ist_wahrscheinlich_bzo_reglement"]),
    )


def _ci_get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    """Case-insensitiver dict.get() -- eCH-0122-JSON schreibt Feldnamen wie
    'Theme.Code' je nach kantonalem Backend mal gross, mal klein (ZH: 'code',
    BL: 'Code'). Siehe auch response_root.get('Extract'/'extract') oben."""
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return default


# ---------------------------------------------------------------------------
# Umwelt-/Risikothemen: bereits Teil des OEREB-Extrakts (kein zusaetzlicher
# API-Call noetig). Dies sind 4 der ca. 20 foederal standardisierten
# OEREB-Themen (ÖREBKV-Anhang) -- JEDE Gemeinde/Kanton, die den OEREB-
# Webservice bedient, liefert diese Themen mit (entweder als "betroffen" mit
# Detaildaten, oder explizit als "nicht betroffen"/"keine Daten").
#
# ACHTUNG Scope: Naturgefahren (Gefahrenkarten Wasser/Rutschung/Sturz) und
# Erdwaermesonden-Eignung sind NICHT Teil der foederal standardisierten
# OEREB-Themenliste und auch NICHT als brauchbarer bundesweiter MapServer-
# Layer auf geo.admin.ch verfuegbar (verifiziert 2026-08-26: kein Layer mit
# ausreichender Abdeckung gefunden -- nur fragmentarische BAFU-Spezial-Layer
# wie Sturz/Lawinen aus dem Waldschutz-Kontext). Genau wie bei den Zonenplan-
# Ausnuetzungsziffern (siehe Akquisitionsradar-Projekt) sind diese Themen
# nur KANTONAL publiziert, falls ueberhaupt offen zugaenglich -- hier bewusst
# NICHT als Feature eingebaut, um keine falsche/unvollstaendige Abdeckung als
# "verifiziert" auszugeben. Bei Bedarf pro Kanton einzeln recherchieren
# (gleiches Vorgehen wie extraction/oereb_*.py im Hauptprojekt).
# ---------------------------------------------------------------------------
_ENV_THEME_GROUPS: dict[str, list[str]] = {
    "belastete_standorte": [
        "ch.BelasteteStandorte",
        "ch.BelasteteStandorteMilitaer",
        "ch.BelasteteStandorteZivileFlugplaetze",
        "ch.BelasteteStandorteOeffentlicherVerkehr",
    ],
    "grundwasserschutz": ["ch.Grundwasserschutzzonen", "ch.Grundwasserschutzareale"],
    "gewaesserraum": ["ch.Gewaesserraum"],
    "laermempfindlichkeitsstufen": ["ch.Laermempfindlichkeitsstufen"],
}


def _theme_membership_codes(extract: dict[str, Any], list_key: str) -> set[str]:
    entries = extract.get(list_key, []) or []
    return {(_ci_get(t, "Code") or "") for t in entries}


def _extract_environmental_themes(extract: dict[str, Any]) -> dict[str, Any]:
    """Wertet die 4 verifizierten Umwelt-/Risiko-OEREB-Themen aus (siehe
    _ENV_THEME_GROUPS): Status (betroffen/nicht_betroffen/keine_daten/nicht_publiziert)
    + Detaildaten (LegendText etc.) fuer jedes betroffene Thema.

    "nicht_betroffen" ist selbst eine wertvolle, verifizierte Aussage (z.B.
    "amtlich bestaetigt: kein Eintrag im Kataster der belasteten Standorte")
    und wird deshalb genauso ausgegeben wie ein "betroffen"-Treffer -- niemals
    stillschweigend weggelassen.
    """
    concerned = _theme_membership_codes(extract, "ConcernedTheme")
    not_concerned = _theme_membership_codes(extract, "NotConcernedTheme")
    without_data = _theme_membership_codes(extract, "ThemeWithoutData")
    restrictions = extract.get("RealEstate", {}).get("RestrictionOnLandownership", [])

    result: dict[str, Any] = {}
    for group_name, theme_codes in _ENV_THEME_GROUPS.items():
        matched_status = None
        for code in theme_codes:
            if code in concerned:
                matched_status = "betroffen"
                break
            if code in not_concerned:
                matched_status = matched_status or "nicht_betroffen"
            elif code in without_data:
                matched_status = matched_status or "keine_daten"

        details = []
        if matched_status == "betroffen":
            for r in restrictions:
                theme = _ci_get(r, "Theme", {}) or {}
                theme_code = _ci_get(theme, "Code", "") or ""
                if theme_code not in theme_codes:
                    continue
                legend = _ci_get(r, "LegendText", []) or []
                zone_name = " ".join(t.get("Text", "") for t in legend if t.get("Text"))
                if not zone_name:
                    continue
                details.append({
                    "bezeichnung": zone_name,
                    "flaechenanteil_prozent": _ci_get(r, "PartInPercent"),
                })

        result[group_name] = {
            "status": matched_status or "nicht_publiziert",
            "details": details,
        }
    return result


def get_radon_data(e: float, n: float) -> dict[str, Any]:
    """Radon-Risikoeinstufung am Standort (Bundesamt fuer Gesundheit BAG,
    Layer ch.bag.radonkarte -- ein echter, punktabfragbarer MapServer-Layer,
    unabhaengig vom OEREB-Kataster)."""
    results = _identify(e, n, "ch.bag.radonkarte", tolerance=10)
    if not results:
        return {"found": False, "reason": "Kein Radonkarte-Eintrag an diesem Punkt gefunden."}

    attrs = results[0].get("attributes", {})
    return {
        "found": True,
        "wahrscheinlichkeit_prozent": _first_key(attrs, ["probability_prozent", "probability"]),
        "konfidenz": _first_key(attrs, ["confidence"]),
        "raw_attributes": attrs,
    }


def _extract_official_zone_labels(extract: dict[str, Any]) -> list[dict[str, Any]]:
    """Liest die amtliche Grundnutzungs-Zonenbezeichnung(en) fuer DIESE Parzelle
    aus RealEstate.RestrictionOnLandownership[].LegendText.

    Das ist die rechtsverbindliche Zoneninformation fuer den konkreten
    Standort (im Gegensatz zu Modul 2s BZO-Analyse, die ALLE in der BZO
    definierten Zonen auflistet). Ueber diese Bezeichnung(en) wird spaeter
    (z.B. in Modul 3) gegen Modul 2s "erkannte_zonen" gematcht.

    Heuristik: Grundnutzung = Theme-Code enthaelt "nutzungsplanung", aber
    NICHT "proj" (projektierte/haengige Planaenderungen). Nur rechtskraeftige
    Eintraege (Lawstatus "inForce"/"rechtskraeftig") werden beruecksichtigt.
    Liefert ALLE Treffer, sortiert nach Flaechenanteil absteigend, und markiert
    den groessten Anteil als "ist_wahrscheinlich_basiszone" -- kleinere Anteile
    sind i.d.R. ueberlagernde Teilflaechen (Schutzzonen, Gewaesserabstand etc.),
    die nicht stillschweigend als alternative Grundnutzung verwechselt werden
    duerfen, aber fuer die Potenzialanalyse trotzdem relevant sein koennen
    (z.B. Denkmalschutz-Teilflaeche).
    """
    zones: list[dict[str, Any]] = []
    restrictions = extract.get("RealEstate", {}).get("RestrictionOnLandownership", [])
    for restriction in restrictions:
        theme = _ci_get(restriction, "Theme", {}) or {}
        theme_code = _ci_get(theme, "Code", "") or ""
        if not _ist_nutzungsplanung_theme(theme_code):
            continue

        lawstatus = _ci_get(restriction, "Lawstatus", {}) or {}
        lawstatus_code = _ci_get(lawstatus, "Code", "")
        if lawstatus_code and lawstatus_code != "inForce":
            continue

        legend = _ci_get(restriction, "LegendText", []) or []
        zone_name = " ".join(t.get("Text", "") for t in legend if t.get("Text"))
        if not zone_name:
            continue

        zones.append({
            "zonenbezeichnung": zone_name,
            "theme_code": theme_code,
            "flaechenanteil_prozent": _ci_get(restriction, "PartInPercent"),
        })

    zones.sort(key=lambda z: z["flaechenanteil_prozent"] or 0, reverse=True)
    for i, z in enumerate(zones):
        z["ist_wahrscheinlich_basiszone"] = i == 0
    return zones


# Felder, die in der JSON-Serialisierung IMMER eine Liste sind. Im XML sehen
# sie bei nur einem Vorkommen wie ein Einzelobjekt aus -- ohne diese Liste
# wuerde ein Extraktor bei genau einer Restriktion ins Leere greifen.
_OEREB_XML_LISTENFELDER = frozenset({
    "RestrictionOnLandownership", "LegalProvisions", "Document", "Reference",
    "ConcernedTheme", "NotConcernedTheme", "ThemeWithoutData", "Geometry",
    "Map", "LegendAtWeb", "OtherLegend",
})

# XML kennt keine Zahlen, nur Text. Diese Felder werden numerisch gebraucht
# (u.a. sortiert _extract_official_zone_labels nach PartInPercent).
_OEREB_XML_ZAHLENFELDER = frozenset({"PartInPercent", "LandRegistryArea", "Area", "Length"})


def _oereb_xml_zu_dict(element) -> Any:
    """Ueberfuehrt einen openoereb-XML-Knoten in dieselbe Struktur, die der
    Bund auch als JSON ausliefert.

    Drei Anpassungen sind noetig, weil XML das Modell anders abbildet:
      * Namespaces abstreifen (ns3:Extract -> Extract)
      * MultilingualText entpacken: {"LocalisedText": {...}} -> [{...}]
      * Listenfelder erzwingen, auch bei nur einem Vorkommen
    """
    kinder = list(element)
    if not kinder:
        text = (element.text or "").strip()
        if not text:
            return None
        name = element.tag.split("}")[-1]
        if name in _OEREB_XML_ZAHLENFELDER:
            try:
                return float(text) if "." in text else int(text)
            except ValueError:
                return text
        return text

    ergebnis: dict[str, Any] = {}
    for kind in kinder:
        name = kind.tag.split("}")[-1]
        wert = _oereb_xml_zu_dict(kind)
        if isinstance(wert, dict) and set(wert) == {"LocalisedText"}:
            inner = wert["LocalisedText"]
            wert = inner if isinstance(inner, list) else [inner]
        if name in ergebnis:
            if not isinstance(ergebnis[name], list):
                ergebnis[name] = [ergebnis[name]]
            ergebnis[name].append(wert)
        else:
            ergebnis[name] = wert
    for feld in _OEREB_XML_LISTENFELDER & set(ergebnis):
        if not isinstance(ergebnis[feld], list):
            ergebnis[feld] = [ergebnis[feld]]
    return ergebnis


def get_oereb_data(egrid: str, kanton: Optional[str]) -> dict[str, Any]:
    """Holt den OEREB-Extrakt fuer ein EGRID vom kantonalen Webservice und
    extrahiert darin enthaltene Dokument-/PDF-Links (u.a. kommunale
    BZO-Reglemente).

    Jeder Kanton betreibt seinen eigenen OEREB-Webservice unter eigener
    Basis-URL (siehe OEREB_CANTON_SERVICES). Ist der Kanton dort nicht
    hinterlegt, wird das transparent gemeldet statt einen Endpunkt zu raten.
    """
    if not egrid:
        return {"found": False, "reason": "Kein EGRID vorhanden -- OEREB-Abfrage uebersprungen."}

    kanton_key = (kanton or "").strip().upper()
    template = OEREB_CANTON_SERVICES.get(kanton_key)
    if not template:
        return {
            "found": False,
            "reason": f"Kein OEREB-Webservice fuer Kanton {kanton_key or '?'} in OEREB_CANTON_SERVICES hinterlegt.",
            "hint": (
                "Basis-URL des kantonalen ÖREB-Webservice unter "
                "https://www.cadastre.ch/de/oereb-webservice nachschlagen und in "
                "OEREB_CANTON_SERVICES ergaenzen."
            ),
        }

    fmt = OEREB_CANTON_FORMAT.get(kanton_key, "json")
    url = template.format(base="", fmt=fmt, egrid=egrid)
    try:
        resp = _get_mit_wiederholung(url, timeout=30)
        resp.raise_for_status()
        if fmt == "xml":
            wurzel = ElementTree.fromstring(resp.content)
            data = {wurzel.tag.split("}")[-1]: _oereb_xml_zu_dict(wurzel)}
        else:
            data = resp.json()
    except ElementTree.ParseError as exc:
        return {"found": False, "reason": f"OEREB-Antwort ({kanton_key}) ist kein gueltiges XML: {exc}", "url": url}
    except requests.exceptions.HTTPError as exc:
        return {"found": False, "reason": f"OEREB-Webservice ({kanton_key}) antwortete mit Fehler: {exc}", "url": url}
    except requests.exceptions.RequestException as exc:
        return {"found": False, "reason": f"OEREB-Anfrage ({kanton_key}) fehlgeschlagen: {exc}", "url": url}

    # Manche kantonalen Backends (z.B. BL) liefern "extract" statt "Extract" --
    # eCH-0122-JSON-Serialisierung ist bei der Gross-/Kleinschreibung nicht
    # einheitlich implementiert, daher case-insensitiv zugreifen.
    response_root = data.get("GetExtractByIdResponse", {})
    extract = response_root.get("Extract") or response_root.get("extract") or {}
    legal_provisions = _extract_legal_provisions(extract)
    official_zones = _extract_official_zone_labels(extract)
    umweltrisiken = _extract_environmental_themes(extract)
    pdf_links = _find_pdf_links(data)
    return {
        "found": True,
        "kanton": kanton_key,
        "source_url": url,
        "amtliche_zonenbezeichnungen": official_zones,
        "rechtsvorschriften": legal_provisions,
        "umweltrisiken": umweltrisiken,
        "legenden_und_themen_pdfs": pdf_links,
        "raw_extract": data,
    }


# ---------------------------------------------------------------------------
# 6. Topografie (Steigung/Ausrichtung) & Erschliessung (Distanz zu Infrastruktur)
#
# Datenquellen bewusst getrennt von den Bundes-Kataster-APIs oben, weil es
# dafuer keinen geo.admin.ch-MapServer-Layer gibt:
#   - Hoehe: dedizierter geo.admin.ch "height"-REST-Service (swissALTI3D),
#     KEIN MapServer-Layer -- Steigung/Ausrichtung werden daraus durch
#     Sampling von 4 Nachbarpunkten selbst berechnet (kein direkter Slope-
#     Endpunkt vorhanden).
#   - OeV-Distanz: transport.opendata.ch (etablierte, offene Schweizer ÖV-API,
#     nicht Teil von geo.admin.ch -- der einzige geo.admin-Layer dafuer,
#     ch.bav.haltestellen-oev, ist vom Typ "wmts" und nicht punktabfragbar,
#     siehe [[feedback_oereb_webservice_gotchas]]).
#   - Schule/Spital/Supermarkt: OpenStreetMap Overpass API -- es gibt dafuer
#     keine zentrale Schweizer Bundesquelle (Schulstandorte sind kommunal
#     gefuehrt), Overpass ist hier die einzige praktikable offene Quelle.
#
# Alle Felder sind Optional -- ein einzelner nicht erreichbarer Dienst darf
# den Rest von Modul 1 nicht zum Absturz bringen (siehe get_topography/
# get_umgebung: Fehler pro Quelle werden abgefangen, nicht propagiert).
# ---------------------------------------------------------------------------

class ProximityEntry(BaseModel):
    name: Optional[str] = None
    distanz_m: Optional[float] = None
    typ: Optional[str] = None


class Topographie(BaseModel):
    hoehe_m: Optional[float] = None
    slope_deg: Optional[float] = None
    slope_pct: Optional[float] = None
    aspect: Optional[str] = None       # Himmelsrichtung der Hangneigung (N/NE/E/SE/S/SW/W/NW)
    aspect_deg: Optional[float] = None
    quelle: str = "swissALTI3D (geo.admin.ch height-REST-Service)"


class Umgebung(BaseModel):
    oev_naechste_haltestelle: Optional[ProximityEntry] = None
    schule_naechste: Optional[ProximityEntry] = None
    spital_naechstes: Optional[ProximityEntry] = None
    supermarkt_naechster: Optional[ProximityEntry] = None
    # WICHTIG: ein None-Feld oben bedeutet "kein Treffer im Suchradius" NUR,
    # wenn hier KEIN Fehler fuer diese Kategorie steht. Overpass ist ein
    # oeffentlicher Shared-Service und antwortet unter Last mit 502/504 --
    # ohne dieses Feld waere "Abfrage fehlgeschlagen" nicht von "confirmed
    # nichts in der Naehe" zu unterscheiden (siehe Testfall 2026-08-26).
    fehler: dict[str, str] = {}


_COMPASS_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _compass_direction(deg: float) -> str:
    idx = round((deg % 360) / 45) % 8
    return _COMPASS_LABELS[idx]


def _get_height_m(e: float, n: float) -> Optional[float]:
    try:
        resp = session.get(HEIGHT_URL, params={"easting": e, "northing": n, "sr": 2056}, timeout=10)
        resp.raise_for_status()
        return float(resp.json()["height"])
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return None


def get_topography(e: float, n: float, sample_offset_m: float = 10.0) -> Topographie:
    """Steigung & Ausrichtung durch Sampling von Hoehenwerten an 4 Nachbarpunkten
    (N/E/S/W im Abstand sample_offset_m) und zentraler Differenz -- der
    height-REST-Service liefert nur Einzelpunkt-Hoehen, keinen Slope direkt.
    """
    center = _get_height_m(e, n)
    if center is None:
        return Topographie()

    h_east = _get_height_m(e + sample_offset_m, n)
    h_west = _get_height_m(e - sample_offset_m, n)
    h_north = _get_height_m(e, n + sample_offset_m)
    h_south = _get_height_m(e, n - sample_offset_m)

    if None in (h_east, h_west, h_north, h_south):
        # Nachbarpunkte nicht vollstaendig verfuegbar (z.B. am Kartenrand) --
        # dann nur die reine Hoehe liefern statt eine unvollstaendige Steigung zu erfinden.
        return Topographie(hoehe_m=center)

    dz_dx = (h_east - h_west) / (2 * sample_offset_m)
    dz_dy = (h_north - h_south) / (2 * sample_offset_m)
    slope_rad = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = math.degrees(slope_rad)
    slope_pct = math.sqrt(dz_dx**2 + dz_dy**2) * 100

    # Aspect = Richtung des staerksten Gefaelles (talwaerts), 0 deg = Nord
    aspect_deg = math.degrees(math.atan2(-dz_dx, dz_dy)) % 360

    return Topographie(
        hoehe_m=round(center, 1),
        slope_deg=round(slope_deg, 1),
        slope_pct=round(slope_pct, 1),
        aspect=_compass_direction(aspect_deg),
        aspect_deg=round(aspect_deg, 1),
    )


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_oev_proximity(lat: float, lon: float) -> Optional[ProximityEntry]:
    """Naechste OeV-Haltestelle ueber transport.opendata.ch (liefert Distanz
    in Metern bereits vorsortiert mit)."""
    try:
        resp = session.get(TRANSPORT_OPENDATA_URL, params={"x": lat, "y": lon, "type": "station"}, timeout=10)
        resp.raise_for_status()
        stations = resp.json().get("stations", [])
    except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
        return None, f"transport.opendata.ch nicht erreichbar: {exc}"

    # Erster Treffer mit "distance" ist meist ein unspezifischer Adress-Treffer
    # (distance ~0, kein "icon"/Verkehrsmittel) -- nur echte Haltestellen (mit icon) zaehlen.
    for s in stations:
        if s.get("icon") and s.get("distance") is not None:
            return ProximityEntry(name=s.get("name"), distanz_m=round(s["distance"], 0), typ=s.get("icon")), None
    return None, None  # echte Null-Treffer -- keine Haltestelle gefunden, kein Fehler


_OVERPASS_POI_TAGS: dict[str, tuple[str, str]] = {
    "schule_naechste": ("amenity", "school"),
    "spital_naechstes": ("amenity", "hospital"),
    "supermarkt_naechster": ("shop", "supermarket"),
}


def _query_overpass_nearest_multi(
    lat: float, lon: float, tags: dict[str, tuple[str, str]], radius_m: int = 3000
) -> tuple[dict[str, Optional[ProximityEntry]], Optional[str]]:
    """Sucht den naechsten OSM-Node fuer MEHRERE tag=value-Filter gleichzeitig
    in EINER Overpass-Anfrage (statt einer Anfrage pro Kategorie) -- schont
    den oeffentlichen Shared-Service und reduziert das Risiko von 429/502/504
    unter Last (empirisch beobachtet bei 3 sequenziellen Einzelanfragen,
    2026-08-26). Distanz wird lokal per Haversine berechnet, da Overpass
    selbst keine Distanz/Sortierung liefert.

    Liefert (Ergebnisse-pro-Kategorie, Fehlermeldung). Ein Fehler betrifft
    dann ALLE Kategorien gleichzeitig (ein API-Call) -- muss von echten
    "keine Treffer im Radius" pro Kategorie unterschieden werden, sonst
    taeuscht ein Timeout einen verifizierten Negativbefund vor.
    """
    filters = "".join(f"node(around:{radius_m},{lat},{lon})[{k}={v}];" for k, v in tags.values())
    query = f"[out:json][timeout:25];({filters});out body 150;"

    try:
        resp = session.post(OVERPASS_URL, data={"data": query}, timeout=30)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
        error = f"Overpass-Sammelabfrage fehlgeschlagen: {exc}"
        return {name: None for name in tags}, error

    results: dict[str, Optional[ProximityEntry]] = {}
    for name, (key, value) in tags.items():
        candidates = [el for el in elements if el.get("tags", {}).get(key) == value]
        if not candidates:
            results[name] = None
            continue
        nearest = min(candidates, key=lambda el: _haversine_m(lat, lon, el["lat"], el["lon"]))
        distanz = _haversine_m(lat, lon, nearest["lat"], nearest["lon"])
        results[name] = ProximityEntry(
            name=nearest.get("tags", {}).get("name"), distanz_m=round(distanz, 0), typ=value
        )
    return results, None


def get_umgebung(lat: float, lon: float) -> Umgebung:
    """Distanz zu OeV-Haltestelle, Schule, Spital, Supermarkt. Jede Quelle
    wird unabhaengig abgefragt -- schlaegt eine fehl (Netzwerk, Timeout),
    bleibt nur DIESES Feld None UND wird unter 'fehler' vermerkt, statt
    stillschweigend wie ein verifizierter Negativbefund auszusehen.
    """
    oev, oev_err = get_oev_proximity(lat, lon)
    poi_results, poi_err = _query_overpass_nearest_multi(lat, lon, _OVERPASS_POI_TAGS)

    fehler = {k: v for k, v in {"oev_naechste_haltestelle": oev_err}.items() if v}
    if poi_err:
        fehler.update({name: poi_err for name in _OVERPASS_POI_TAGS})

    return Umgebung(
        oev_naechste_haltestelle=oev,
        schule_naechste=poi_results.get("schule_naechste"),
        spital_naechstes=poi_results.get("spital_naechstes"),
        supermarkt_naechster=poi_results.get("supermarkt_naechster"),
        fehler=fehler,
    )


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def run_modul1(address: str) -> dict[str, Any]:
    started = time.time()
    result: dict[str, Any] = {"input_address": address}

    geo = geocode_address(address)
    result["geocoding"] = geo

    e, n = geo["lv95_e"], geo["lv95_n"]
    if e is None or n is None:
        raise Modul1Error("Geocoding lieferte keine gueltigen LV95-Koordinaten.")

    result["kataster"] = get_parcel_data(e, n)
    result["gemeinde"] = get_municipality_data(e, n)
    result["gwr"] = get_gwr_data(e, n)
    result["radon"] = get_radon_data(e, n)
    result["topographie"] = get_topography(e, n).model_dump()

    lat, lon = geo.get("wgs84_lat"), geo.get("wgs84_lon")
    result["umgebung"] = get_umgebung(lat, lon).model_dump() if lat and lon else Umgebung().model_dump()

    egrid = result["kataster"].get("egrid")
    canton_hint = geo.get("canton_hint")
    kanton = result["gemeinde"].get("kanton") or (canton_hint.upper() if canton_hint else None)
    result["oereb"] = get_oereb_data(egrid, kanton)
    result["nutzungsklassifikation"] = klassifiziere_nutzung(e, n, kanton)

    # Rechtsvorschriften zusaetzlich nach der (unabhaengig von geodienste.ch/
    # ZH-WFS bestimmten) tatsaechlichen Basiszone priorisieren -- siehe
    # priorisiere_nach_basiszone() fuer die Begruendung (live an Baden
    # nachgewiesen: ohne diesen Schritt landet die massgebende BNO hinter
    # mehreren Sondernutzungsplan-Ueberlagerungen).
    if result["oereb"].get("found") and result["nutzungsklassifikation"].get("basiszone"):
        basiszone = result["nutzungsklassifikation"]["basiszone"]
        basiszone_name = basiszone.get("typ_kommunal_bezeichnung") or basiszone.get("typ_kantonal_bezeichnung")
        result["oereb"]["rechtsvorschriften"] = priorisiere_nach_basiszone(
            result["oereb"].get("rechtsvorschriften", []), basiszone_name
        )

    parzellengeometrie = result["kataster"].get("parzellengeometrie") if result["kataster"].get("found") else None
    if parzellengeometrie:
        result["restriktionsgeometrie"] = hole_restriktionen_fuer_parzelle(e, n, kanton, parzellengeometrie)
    else:
        result["restriktionsgeometrie"] = {
            "gefunden": False,
            "reason": "Keine Parzellengeometrie verfuegbar (siehe kataster.found) -- Restriktionsabfrage uebersprungen.",
        }

    # G2 -- welche Kante grenzt an Strasse, welche an einen Nachbarn. Erst
    # damit kann G1 kantenspezifisch statt als Bandbreite rechnen. Ein Fehler
    # hier darf die Analyse nicht stoppen: die Bandbreite bleibt als
    # Rueckfallebene bestehen, der Grund wird festgehalten statt verschluckt.
    if parzellengeometrie:
        # Lokaler Import: kantenklassifikation.py liest seinerseits aus diesem
        # Modul (_identify, LAYER_CADASTRE_GEOM) -- ein Modulzyklus auf
        # Dateiebene waere sonst unvermeidlich.
        from .kantenklassifikation import KantenklassifikationError, klassifiziere_kanten

        try:
            result["kantenklassifikation"] = klassifiziere_kanten(
                parzellengeometrie, e, n, eigenes_egrid=egrid
            )
        except (KantenklassifikationError, requests.exceptions.RequestException) as exc:
            result["kantenklassifikation"] = {
                "gefunden": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "kanten": [],
            }
    else:
        result["kantenklassifikation"] = {
            "gefunden": False,
            "reason": "Keine Parzellengeometrie verfuegbar -- Kantenklassifikation uebersprungen.",
            "kanten": [],
        }

    # Bestand: alle Gebaeude der Parzelle mit Grundriss und GWR-Merkmalen.
    # Loest die alte Einzelabfrage get_gwr_data() NICHT ab (sie bleibt fuer
    # Abwaertskompatibilitaet unter result["gwr"]), liefert aber die
    # parzellenweite Sicht, die die Entwicklungsszenarien brauchen.
    if parzellengeometrie:
        from .bestand import hole_bestand

        try:
            result["bestand"] = hole_bestand(e, n, parzellengeometrie)
        except (Exception,) as exc:  # noqa: BLE001 -- Bestand darf die Analyse nicht stoppen
            result["bestand"] = {
                "gefunden": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "gebaeude": [],
            }
    else:
        result["bestand"] = {
            "gefunden": False,
            "reason": "Keine Parzellengeometrie verfuegbar -- Bestandsermittlung uebersprungen.",
            "gebaeude": [],
        }

    result["_meta"] = {
        "duration_seconds": round(time.time() - started, 2),
        "modul": "Modul 1 - Geo-Data & Registry Ingestion",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Modul 1: Geo-Data & Registry Ingestion")
    parser.add_argument("address", help="Schweizer Adresse, z.B. 'Bahnhofstrasse 1, 8001 Zuerich'")
    args = parser.parse_args()

    try:
        result = run_modul1(args.address)
    except Modul1Error as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

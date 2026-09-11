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
  * Gebaeudegrundrisse aus `ch.swisstopo.vec25-gebaeude`, geschnitten mit
    der Parzelle
  * Zuordnung Grundriss <-> GWR-Eintrag ueber Punkt-in-Polygon

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

from shapely.geometry import Point, Polygon, shape

from .modul1_geodata import LAYER_GWR, _identify

LAYER_GEBAEUDE_GRUNDRISS = "ch.swisstopo.vec25-gebaeude"

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
) -> dict[str, Any]:
    """Die reine Auswertung -- ohne Netzzugriff, damit offline pruefbar.

    `gwr_treffer` und `grundriss_treffer` sind MapServer-Antworten im Format
    von `_identify(..., return_geometry=True)`.
    """
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
            "GWR-Eintrag auf der Parzelle ohne passenden Gebaeudegrundriss in "
            f"{LAYER_GEBAEUDE_GRUNDRISS} -- der Datensatz ist generalisiert (1:25'000) "
            "und fuehrt kleine Nebengebaeude teils nicht."
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
            "weichen um mehr als 15 % voneinander ab. Beide Werte sind echt -- VEC25 ist ein "
            "generalisierter Kartendatensatz, das GWR ein Register. Sie werden nicht verrechnet."
        )

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
        "quellen_layer": [LAYER_GWR, LAYER_GEBAEUDE_GRUNDRISS],
        "abgerufen_am": datetime.now().date().isoformat(),
    }


def hole_bestand(
    e: float, n: float, parzelle_ring: list[tuple[float, float]]
) -> dict[str, Any]:
    """Ermittelt alle Gebaeude auf der Parzelle (GWR + Grundrisse)."""
    if not parzelle_ring:
        return {
            "gefunden": False,
            "reason": "Keine Parzellengeometrie -- Bestand nicht ermittelbar.",
            "gebaeude": [],
        }
    gwr = _identify(e, n, LAYER_GWR, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True)
    grundrisse = _identify(
        e, n, LAYER_GEBAEUDE_GRUNDRISS, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True
    )
    return werte_bestand_aus(gwr, grundrisse, parzelle_ring)


def bestandsgeschosse(bestand: dict[str, Any]) -> Optional[int]:
    """Geschosszahl des Hauptgebaeudes, oder None wenn nicht gefuehrt."""
    haupt = (bestand or {}).get("hauptgebaeude") or {}
    return haupt.get("geschosse")


def bestandsgrundriss(bestand: dict[str, Any]) -> list[list[float]]:
    """Alle Gebaeudegrundrisse der Parzelle als Ringe -- die Flaeche, die
    ein Anbau oder ein zusaetzlicher Baukoerper NICHT belegen kann."""
    return [g["grundriss"] for g in (bestand or {}).get("gebaeude", []) if g.get("grundriss")]

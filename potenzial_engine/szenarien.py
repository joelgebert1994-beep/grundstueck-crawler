"""
Stufe 4 -- Entwicklungsszenarien, baulich abgeleitet.

`entwicklungsszenarien.py` legte die Taxonomie fest (welche Szenarien es gibt
und welche Eingaben jedes braucht) und sagte ausdruecklich: keine Rechenlogik.
Dieses Modul liefert sie -- aus den Daten, die bereits vorliegen:

    G1 (baubereich.py)      Baubereich-Polygon, Fussabdruck, Geschosszahl,
                            Geschossflaeche und je Stufe die limitierende Groesse
    bestand.py              Gebaeude der Parzelle mit Grundriss, Geschosszahl,
                            Baujahr, Nutzung
    flaechenmodell.py       GF -> NGF -> NF -> HNF -> NWF -> Wohnungen
    kantenklassifikation.py welche Kante an Strasse, welche an Nachbarn grenzt
    restriktionsgeometrie   Gewaesserraum, Waldabstand, Baulinien

Kein Szenario erfindet Architektur. Jeder Baukoerper entsteht aus dem
Baubereich, den Grenzabstaenden und dem, was das Baurecht an Geschossen und
Flaeche zulaesst. Wo eine Angabe fehlt, ist das Szenario `nicht_bestimmbar`
MIT Ursache -- nicht "moeglich" mit geschaetzten Zahlen.

Die zentrale baurechtliche Pruefung fuer Anbau, Aufstockung und Kombination
ist das AUSNUETZUNGSBUDGET: was das Baurecht insgesamt zulaesst, minus das,
was der Bestand bereits belegt. Ist es aufgebraucht, ist keine Erweiterung
moeglich, egal wie viel Platz auf der Parzelle noch frei waere.

Jedes Szenario ist eigenstaendig serialisierbar (`to_dict()`), damit spaeter
Markt, BKP und Wirtschaftlichkeit je Szenario getrennt gerechnet und
gespeichert werden koennen.

Netzwerkfrei -- reine Berechnung auf uebergebenen Daten.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .entwicklungsszenarien import Szenariotyp
from .flaechenmodell import (
    GESCHOSS_ATTIKA,
    PROFIL_WOHNUNGSBAU_MFH,
    WohnungstypVorgabe,
    annahmenprofil,
    berechne_flaechen_und_wohnungen,
    HERKUNFT_SYSTEMANNAHME,
    berechne_wohnungen, HERKUNFT_BENUTZERANNAHME,)

MACHBARKEIT_MOEGLICH = "moeglich"
MACHBARKEIT_EINGESCHRAENKT = "eingeschraenkt_moeglich"
MACHBARKEIT_NICHT_MOEGLICH = "nicht_moeglich"
MACHBARKEIT_NICHT_BESTIMMBAR = "nicht_bestimmbar"
MACHBARKEIT_BESTEHT = "besteht"

# Kleinste Flaeche, die als Anbau- oder Neubaubereich ueberhaupt sinnvoll ist.
# Darunter ist der verbleibende Baubereich ein Geometrie-Rest, kein Bauplatz.
MIN_BAUFLAECHE_M2 = 15.0

# Mindestbreite eines verbleibenden Bereichs. Ein 40 m langer, 1.2 m breiter
# Streifen hat rechnerisch 48 m2, ist aber kein Anbau.
MIN_BAUBREITE_M = 2.5

_HIMMELSRICHTUNGEN = ["Norden", "Nordosten", "Osten", "Suedosten",
                      "Sueden", "Suedwesten", "Westen", "Nordwesten"]


class SzenarioError(Exception):
    """Fehler bei der Szenarienbildung (fehlende Pflichtdaten)."""


# ---------------------------------------------------------------------------
# Geometrie-Hilfen
# ---------------------------------------------------------------------------

def _polygon(ring: Any) -> Optional[Polygon]:
    if not ring:
        return None
    try:
        p = Polygon([(float(c[0]), float(c[1])) for c in ring])
    except (TypeError, ValueError, IndexError):
        return None
    if not p.is_valid:
        p = p.buffer(0)
    return None if p.is_empty else p


def _als_flaeche(koordinatenlisten: Any) -> Optional[Polygon | MultiPolygon]:
    """G1 liefert baubereich_koordinaten als Liste von Ringen."""
    teile = [p for p in (_polygon(r) for r in (koordinatenlisten or [])) if p is not None]
    if not teile:
        return None
    vereint = unary_union(teile)
    return None if vereint.is_empty else vereint


def _einzelpolygone(geometrie: Any) -> list[Polygon]:
    if geometrie is None or geometrie.is_empty:
        return []
    if geometrie.geom_type == "Polygon":
        return [geometrie]
    if geometrie.geom_type == "MultiPolygon":
        return [p for p in geometrie.geoms if not p.is_empty]
    return []


def _ring(polygon: Polygon) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in polygon.exterior.coords]


def _masse(polygon: Polygon) -> tuple[float, float]:
    """Laenge und Breite des kleinsten umschliessenden Rechtecks.

    Nicht die Bounding Box der Achsen -- eine schraeg liegende Restflaeche
    haette darin falsche Masse. `minimum_rotated_rectangle` dreht mit.
    """
    rechteck = polygon.minimum_rotated_rectangle
    if rechteck.geom_type != "Polygon":
        return (0.0, 0.0)
    punkte = list(rechteck.exterior.coords)[:4]
    if len(punkte) < 4:
        return (0.0, 0.0)
    kanten = [
        math.hypot(punkte[(i + 1) % 4][0] - punkte[i][0], punkte[(i + 1) % 4][1] - punkte[i][1])
        for i in range(4)
    ]
    return (round(max(kanten[0], kanten[1]), 1), round(min(kanten[0], kanten[1]), 1))


def _richtung(von: Polygon, zu: Polygon) -> str:
    """Himmelsrichtung von `von` nach `zu` (LV95: +N ist Norden, +E ist Osten)."""
    dx = zu.centroid.x - von.centroid.x
    dy = zu.centroid.y - von.centroid.y
    if dx == 0 and dy == 0:
        return "zentral"
    winkel = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return _HIMMELSRICHTUNGEN[int(round(winkel / 45)) % 8]


def _hoehe(geschosse: Optional[int], geschosshoehe_m: Optional[float]) -> Optional[float]:
    """Bauwerkshoehe aus Geschosszahl x Geschosshoehe.

    Das ist die konstruktive Hoehe des Baukoerpers, NICHT die baurechtliche
    Gebaeude- oder Gesamthoehe: die misst vom gewachsenen Terrain und kann
    durch Dachform und Terrainverlauf abweichen. Sie dient der Darstellung
    und dem Vergleich mit dem zulaessigen Mass.
    """
    if geschosse is None or geschosshoehe_m is None:
        return None
    return round(geschosse * geschosshoehe_m, 2)


def _baukoerper(
    name: str, polygon: Polygon, geschosse: Optional[int], hoehe_m: Optional[float],
    herkunft: str, art: str = "neubau",
) -> dict[str, Any]:
    laenge, breite = _masse(polygon)
    return {
        "name": name,
        "art": art,
        "ring": _ring(polygon),
        "flaeche_m2": round(polygon.area, 1),
        "max_laenge_m": laenge,
        "max_breite_m": breite,
        "geschosse": geschosse,
        "hoehe_m": hoehe_m,
        "herkunft": herkunft,
    }


# ---------------------------------------------------------------------------
# Baurechtliche Hilfsgroessen
# ---------------------------------------------------------------------------

def _kennzahl(zone: Optional[dict[str, Any]], feld: str) -> Optional[float]:
    if not zone:
        return None
    roh = zone.get(feld)
    wert = roh.get("wert") if isinstance(roh, dict) else roh
    try:
        return float(wert) if wert is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class Ausnuetzungsbudget:
    """Was das Baurecht insgesamt zulaesst, minus was der Bestand belegt."""
    zulaessig_gf_m2: Optional[float]
    bestand_gf_m2: Optional[float]
    verbleibend_gf_m2: Optional[float]
    bestand_herkunft: Optional[str]
    limitierend: Optional[str]
    hinweise: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def berechne_ausnuetzungsbudget(
    g1_ergebnis: dict[str, Any], bestand: Optional[dict[str, Any]]
) -> Ausnuetzungsbudget:
    """Wie viel Geschossflaeche bleibt neben dem Bestand noch uebrig?

    Die Bestands-Geschossflaeche wird aus Grundriss x Geschosszahl gebildet.
    Das ist eine NAEHERUNG: der Grundriss stammt aus einem generalisierten
    Kartendatensatz, und nicht jedes Geschoss hat die Flaeche des
    Erdgeschosses. Sie wird deshalb als solche benannt und nicht als
    gemessene Groesse ausgegeben. Eine Planabrechnung ersetzt sie, sobald
    eine vorliegt.
    """
    zulaessig = g1_ergebnis.get("geschossflaeche_m2")
    hinweise: list[str] = []

    haupt = (bestand or {}).get("hauptgebaeude") or {}
    gebaeude = (bestand or {}).get("gebaeude") or []
    geschosse = haupt.get("geschosse")

    bestand_gf = None
    herkunft = None
    if geschosse is not None:
        # Alle Gebaeude mit Wohnnutzung zaehlen zur Geschossflaeche; reine
        # Nebengebaeude (Garagen, Schuppen) in der Regel nicht.
        flaeche = sum(
            (g.get("grundriss_flaeche_m2") or g.get("grundflaeche_gwr_m2") or 0.0)
            for g in gebaeude if g.get("wohnnutzung")
        )
        if flaeche:
            bestand_gf = round(flaeche * geschosse, 1)
            herkunft = (
                f"Naeherung: {flaeche:.1f} m2 Grundflaeche der Wohngebaeude x {geschosse} "
                "Geschoss(e). Der Grundriss stammt aus einem generalisierten Kartendatensatz, "
                "und nicht jedes Geschoss hat die Erdgeschossflaeche -- eine Planabrechnung "
                "ersetzt diesen Wert."
            )
    if bestand_gf is None and gebaeude:
        hinweise.append(
            "Bestands-Geschossflaeche nicht bestimmbar: "
            + ("im GWR ist keine Geschosszahl gefuehrt." if geschosse is None
               else "kein Gebaeude mit Wohnnutzung auf der Parzelle.")
            + " Ohne sie laesst sich nicht sagen, wie viel Ausnuetzung noch frei ist."
        )

    verbleibend = None
    if zulaessig is not None and bestand_gf is not None:
        verbleibend = round(zulaessig - bestand_gf, 1)
        if verbleibend <= 0:
            hinweise.append(
                f"Die zulaessige Geschossflaeche ({zulaessig:.1f} m2) ist durch den Bestand "
                f"({bestand_gf:.1f} m2) bereits ausgeschoepft."
            )
        if bestand_gf > zulaessig:
            hinweise.append(
                f"Die Parzelle ist UEBERBAUT: der Bestand belegt {bestand_gf:.0f} m2 "
                f"Geschossflaeche, das heutige Recht liesse nur {zulaessig:.0f} m2 zu "
                f"({bestand_gf - zulaessig:.0f} m2 darueber). Solche Bauten geniessen in der "
                "Regel Besitzstandsgarantie -- sie duerfen bestehen bleiben, aber ein "
                "Ersatzneubau faellt kleiner aus als der Bestand. Der Umfang der Garantie "
                "ist kantonal geregelt und hier nicht geprueft."
            )

    return Ausnuetzungsbudget(
        zulaessig_gf_m2=zulaessig,
        bestand_gf_m2=bestand_gf,
        verbleibend_gf_m2=verbleibend,
        bestand_herkunft=herkunft,
        limitierend=g1_ergebnis.get("geschossflaeche_limitiert_durch"),
        hinweise=hinweise,
    )


# ---------------------------------------------------------------------------
# Szenario-Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class Szenario:
    """Ein eigenstaendig speicher- und rechenbares Entwicklungsszenario."""
    id: str
    typ: str
    bezeichnung: str
    machbarkeit: str
    begruendung: str
    baukoerper: list[dict[str, Any]] = field(default_factory=list)
    geschosse: Optional[int] = None
    hoehe_m: Optional[float] = None
    geschossflaeche_m2: Optional[float] = None
    geschossflaeche_herkunft: Optional[str] = None
    flaechen: Optional[dict[str, Any]] = None
    wohnungen: Optional[dict[str, Any]] = None
    konflikte: list[dict[str, Any]] = field(default_factory=list)
    unsicherheiten: list[str] = field(default_factory=list)
    quellen: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _konflikt(art: str, meldung: str, schwere: str = "einschraenkung") -> dict[str, Any]:
    return {"art": art, "meldung": meldung, "schwere": schwere}


def baulinien_konflikt(restriktionen: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Baulinien treten an die Stelle der Abstandsmasse und koennen strenger
    sein. G1 zieht sie NICHT vom Baubereich ab -- welche Baulinie welcher Kante
    zugeordnet ist, ist nicht automatisiert. Wo welche gefunden wurden, wird
    das deshalb je Szenario als Konflikt ausgewiesen statt uebergangen."""
    anzahl = len((restriktionen or {}).get("baulinien_gefunden") or [])
    if not anzahl:
        return None
    return _konflikt(
        "baulinie",
        f"{anzahl} Baulinie(n) auf oder an der Parzelle. Eine Baulinie tritt an die Stelle des "
        "Abstandsmasses und kann den Baubereich weiter einschraenken -- sie ist im hier "
        "gezeigten Baubereich NICHT abgezogen. Manuelle Pruefung erforderlich.",
    )


# ---------------------------------------------------------------------------
# Die einzelnen Szenarien
# ---------------------------------------------------------------------------

def _flaechen_fuer(
    geschossflaeche_m2: Optional[float],
    g1_ergebnis: dict[str, Any],
    zone: Optional[dict[str, Any]],
    profil: str,
    benutzerwerte: Optional[dict[str, float]],
    wohnungsmix: Optional[list[WohnungstypVorgabe]],
    wohnungsmix_begruendung: str,
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    zusaetzliche_geschosse: Optional[list[dict[str, Any]]] = None,
    geschosszahl: Optional[int] = None,
    restflaeche_verteilen: bool = False,
) -> Optional[dict[str, Any]]:
    """Faehrt die Flaechenkaskade fuer eine szenariospezifische GF.

    Das G1-Ergebnis wird dafuer mit der Szenario-GF und -Geschosszahl
    ueberschrieben -- alles andere (anrechenbare Landflaeche, Kandidaten,
    limitierende Groesse) bleibt, damit der Rechenweg die echte Herkunft
    behaelt.
    """
    if geschossflaeche_m2 is None:
        return None
    abgewandelt = dict(g1_ergebnis)
    abgewandelt["geschossflaeche_m2"] = geschossflaeche_m2
    if geschosszahl is not None:
        abgewandelt["geschosszahl"] = geschosszahl
    return berechne_flaechen_und_wohnungen(
        abgewandelt, zone=zone, profil=profil, benutzerwerte=benutzerwerte,
        wohnungsmix=wohnungsmix, wohnungsmix_begruendung=wohnungsmix_begruendung,
        wohnungsmix_herkunft=wohnungsmix_herkunft,
        zusaetzliche_geschosse=zusaetzliche_geschosse,
        restflaeche_verteilen=restflaeche_verteilen,
    )


def _fehlender_bestand_grund(bestand: Optional[dict[str, Any]], was: str) -> str:
    """Warum ist kein bebaubarer Bestand da -- gar kein Gebaeude, oder eines
    ohne Grundriss?

    Der Unterschied ist fuer den Benutzer wesentlich: im ersten Fall ist die
    Parzelle unbebaut, im zweiten steht sehr wohl ein Haus, nur fehlt seine
    Geometrie im Kartendatensatz. Live beobachtet an Wilen 18a: zwei
    GWR-Gebaeude, kein Grundriss in VEC25.
    """
    gebaeude = (bestand or {}).get("gebaeude") or []
    if not gebaeude:
        return (
            f"Kein Gebaeude auf der Parzelle -- {was} setzt einen Bestand voraus. "
            "Fuer eine unbebaute Parzelle ist der Ersatzneubau das passende Szenario."
        )
    return (
        f"Auf der Parzelle stehen {len(gebaeude)} Gebaeude, aber fuer keines liegt ein "
        "Gebaeudegrundriss vor (der Kartendatensatz ist generalisiert und fuehrt nicht "
        f"jedes Gebaeude). Ohne Grundriss laesst sich nicht bestimmen, wo {was} Platz "
        "haette -- manuelle Pruefung erforderlich."
    )


def szenario_bestand(
    bestand: dict[str, Any], budget: Ausnuetzungsbudget, *,
    geschosshoehe_m: Optional[float] = None, **kw
) -> Szenario:
    gebaeude = (bestand or {}).get("gebaeude") or []
    haupt = (bestand or {}).get("hauptgebaeude") or {}

    if not gebaeude:
        return Szenario(
            id="bestand", typ=Szenariotyp.BESTAND.value, bezeichnung="Bestand belassen",
            machbarkeit=MACHBARKEIT_NICHT_MOEGLICH,
            begruendung="Auf der Parzelle steht kein Gebaeude -- es gibt keinen Bestand, den man belassen koennte.",
            quellen=(bestand or {}).get("quellen_layer", []),
        )

    koerper = [
        _baukoerper(
            name=g.get("adresse") or f"EGID {g.get('egid')}" or "Gebaeude",
            polygon=_polygon(g["grundriss"]),
            geschosse=g.get("geschosse"),
            hoehe_m=_hoehe(g.get("geschosse"), geschosshoehe_m),
            herkunft=f"Gebaeudegrundriss aus {(bestand or {}).get('quellen_layer', ['?'])[-1]}, "
                     "Geschosszahl und Baujahr aus dem GWR; Hoehe als Geschosszahl x "
                     "angenommener Geschosshoehe (der Bestand von 1918 kann davon abweichen)",
            art="bestand",
        )
        for g in gebaeude if g.get("grundriss")
    ]

    unsicherheiten = list((bestand or {}).get("hinweise", []))
    for g in gebaeude:
        unsicherheiten.extend(g.get("hinweise", []))
    if haupt.get("geschosse") is None:
        unsicherheiten.append("Geschosszahl des Hauptgebaeudes im GWR nicht gefuehrt.")

    unsicherheiten.append(
        "Fuer den Bestand wird KEINE Flaechenkaskade gerechnet: die Verhaeltnisse "
        "KF/GF, VF+FF/NGF und HNF/NF des Annahmenprofils sind Erfahrungswerte fuer "
        "NEUBAUTEN. Ein Altbau hat andere Konstruktions- und Erschliessungsanteile. "
        "Belastbare Bestandsflaechen brauchen Grundrisse oder eine Abrechnung -- die "
        "GWR-Energiebezugsflaeche ist dafuer kein Ersatz (andere Definition)."
    )

    return Szenario(
        id="bestand", typ=Szenariotyp.BESTAND.value, bezeichnung="Bestand belassen",
        machbarkeit=MACHBARKEIT_BESTEHT,
        begruendung=(
            f"{len(gebaeude)} Gebaeude auf der Parzelle. Hauptgebaeude: "
            f"{haupt.get('kategorie_text') or 'Kategorie unbekannt'}"
            + (f", Baujahr {haupt['baujahr']}" if haupt.get("baujahr") else "")
            + (f", {haupt['geschosse']} Geschoss(e)" if haupt.get("geschosse") else "")
            + "."
        ),
        baukoerper=koerper,
        geschosse=haupt.get("geschosse"),
        hoehe_m=_hoehe(haupt.get("geschosse"), geschosshoehe_m),
        geschossflaeche_m2=budget.bestand_gf_m2,
        geschossflaeche_herkunft=budget.bestand_herkunft,
        unsicherheiten=unsicherheiten,
        quellen=(bestand or {}).get("quellen_layer", []),
    )


def szenario_sanierung(
    bestand: dict[str, Any], budget: Ausnuetzungsbudget, *,
    restriktionen: Optional[dict[str, Any]] = None,
    bestand_flaeche_nwf_m2: Optional[float] = None,
    geschosshoehe_m: Optional[float] = None,
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list[WohnungstypVorgabe]] = None,
    wohnungsmix_begruendung: str = "",
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    restflaeche_verteilen: bool = False,
    **kw,
) -> Szenario:
    """Der Bestand bleibt, wird aber erneuert -- ohne neue Geschossflaeche.

    Der fachliche Kern: das ist das EINZIGE Szenario, das die Ausnuetzung
    nicht beruehrt. Anbau, Aufstockung, Dachausbau, Ersatzneubau und
    Bestand+Neubau konkurrieren alle um dasselbe Budget; eine Sanierung
    schafft keine Flaeche und verbraucht deshalb keines. Daraus folgt das
    Wesentliche: sie ist auch dort moeglich, wo das Budget ausgeschoepft
    oder UEBERSCHRITTEN ist -- und genau dann ist sie oft die einzige
    Option, die bleibt.

    Was hier bewusst NICHT geschieht:

      * Keine geschaetzten Bestandsflaechen. Die Verhaeltnisse KF/GF,
        VF+FF/NGF und HNF/NF des Annahmenprofils sind Erfahrungswerte fuer
        NEUBAUTEN; ein Altbau hat andere Konstruktions- und
        Erschliessungsanteile. Das steht so schon im Bestand-Szenario, und
        die Sanierung darf nicht die Hintertuer sein, durch die solche
        Zahlen doch hereinkommen.
      * Keine Sanierungskosten. Sie streuen von der Pinselsanierung bis zur
        Totalsanierung um ein Vielfaches und haengen am Zustand, den die
        Engine nicht kennt.

    Rechenbar wird das Szenario, sobald `bestand_flaeche_nwf_m2` aus Plaenen
    oder einer Abrechnung vorliegt. Dann laeuft dieselbe Kette wie bei den
    uebrigen Szenarien und es ist mit ihnen vergleichbar.
    """
    gebaeude = (bestand or {}).get("gebaeude") or []
    haupt = (bestand or {}).get("hauptgebaeude") or {}

    if not gebaeude:
        return Szenario(
            id="sanierung", typ=Szenariotyp.SANIERUNG.value, bezeichnung="Sanierung",
            machbarkeit=MACHBARKEIT_NICHT_MOEGLICH,
            begruendung=_fehlender_bestand_grund(bestand, "eine Sanierung"),
            quellen=(bestand or {}).get("quellen_layer", []),
        )

    koerper = [
        _baukoerper(
            name=g.get("adresse") or f"EGID {g.get('egid')}" or "Gebaeude",
            polygon=_polygon(g["grundriss"]),
            geschosse=g.get("geschosse"),
            hoehe_m=_hoehe(g.get("geschosse"), geschosshoehe_m),
            herkunft="Unveraendertes Bestandsvolumen -- eine Sanierung aendert "
                     "weder Grundriss noch Geschosszahl",
            art="bestand",
        )
        for g in gebaeude if g.get("grundriss")
    ]

    konflikte: list[dict[str, Any]] = []
    unsicherheiten = list((bestand or {}).get("hinweise", []))
    for g in gebaeude:
        unsicherheiten.extend(g.get("hinweise", []))

    # --- Der Punkt, an dem sich die Sanierung von allem anderen abhebt ---
    if budget.verbleibend_gf_m2 is not None and budget.verbleibend_gf_m2 < 0:
        ausnuetzung_text = (
            f"Der Bestand ueberschreitet die zulaessige Geschossflaeche um "
            f"{abs(budget.verbleibend_gf_m2):,.0f} m2. Fuer eine Sanierung ist das "
            "ohne Belang: sie schafft keine neue Geschossflaeche. Jede Erweiterung "
            "waere dagegen ausgeschlossen."
        )
    elif budget.verbleibend_gf_m2 is not None:
        ausnuetzung_text = (
            f"Die Sanierung verbraucht keine Ausnuetzung -- die "
            f"{budget.verbleibend_gf_m2:,.0f} m2 ungenutzte Geschossflaeche bleiben "
            "vollstaendig fuer eine spaetere Erweiterung erhalten."
        )
    else:
        ausnuetzung_text = (
            "Die Sanierung verbraucht keine Ausnuetzung. Wie viel Geschossflaeche "
            "ungenutzt bleibt, ist nicht bestimmbar."
        )

    baulinie = baulinien_konflikt(restriktionen)
    if baulinie:
        # Bei der Sanierung wirkt eine Baulinie anders als bei einem Neubau:
        # sie verbietet das Bestehende nicht, kann aber einer spaeteren
        # Erweiterung im Weg stehen. Das gehoert unterschieden.
        konflikte.append(_konflikt(
            "baulinie",
            baulinie["meldung"] + " Fuer die Sanierung selbst ist sie ohne Belang, solange "
            "das Volumen unveraendert bleibt.",
            schwere="hinweis",
        ))

    # --- Flaechen: nur mit echter Angabe ---------------------------------
    flaechen = None
    wohnungen = None
    if bestand_flaeche_nwf_m2 is not None and bestand_flaeche_nwf_m2 > 0:
        wohnungen = berechne_wohnungen(
            bestand_flaeche_nwf_m2, wohnungsmix, wohnungsmix_begruendung,
            restflaeche_verteilen, herkunft=wohnungsmix_herkunft,
        )
        flaechen = {
            "status": "benutzerangabe",
            "nwf_m2": round(bestand_flaeche_nwf_m2, 1),
            "herkunft": HERKUNFT_BENUTZERANNAHME,
            "begruendung": (
                "Wohnflaeche des Bestands als Benutzerangabe uebernommen. Die Engine "
                "leitet sie NICHT aus der Geschossflaeche ab -- die Flaechenverhaeltnisse "
                "des Annahmenprofils gelten fuer Neubauten."
            ),
            "wohnungen": wohnungen,
        }
        machbarkeit = MACHBARKEIT_MOEGLICH
        begruendung = (
            f"Sanierung des Bestands ohne Volumenaenderung, gerechnet auf "
            f"{bestand_flaeche_nwf_m2:,.0f} m2 Wohnflaeche (Angabe des Benutzers). "
            + ausnuetzung_text
        )
    else:
        machbarkeit = MACHBARKEIT_NICHT_BESTIMMBAR
        begruendung = (
            "Baulich moeglich -- eine Sanierung setzt nur einen Bestand voraus, und der "
            "ist da. " + ausnuetzung_text + " Wirtschaftlich noch nicht bestimmbar: dafuer "
            "fehlt die tatsaechliche Wohnflaeche des Bestands."
        )
        unsicherheiten.append(
            "Fuer eine Wirtschaftlichkeitsrechnung fehlt die Wohnflaeche des Bestands. "
            "Sie wird bewusst NICHT aus der Geschossflaeche abgeleitet: die Verhaeltnisse "
            "KF/GF, VF+FF/NGF und HNF/NF des Annahmenprofils sind Erfahrungswerte fuer "
            "Neubauten, ein Altbau hat andere Konstruktions- und Erschliessungsanteile. "
            "Belastbar ist sie nur aus Plaenen oder einer Abrechnung."
        )

    unsicherheiten.append(
        "Sanierungskosten werden nicht vorgeschlagen. Sie reichen von der "
        "Pinselsanierung bis zur Totalsanierung um ein Vielfaches auseinander und "
        "haengen am Gebaeudezustand, den diese Analyse nicht kennt. Der Ansatz gehoert "
        "als eigene Annahme gesetzt."
    )
    if haupt.get("baujahr"):
        unsicherheiten.append(
            f"Baujahr {haupt['baujahr']}: Bauteile, Schadstoffe und energetischer Zustand "
            "bestimmen den Sanierungsumfang und sind hier nicht erhoben."
        )

    return Szenario(
        id="sanierung", typ=Szenariotyp.SANIERUNG.value, bezeichnung="Sanierung",
        machbarkeit=machbarkeit,
        begruendung=begruendung,
        baukoerper=koerper,
        geschosse=haupt.get("geschosse"),
        hoehe_m=_hoehe(haupt.get("geschosse"), geschosshoehe_m),
        # Die Geschossflaeche bleibt die des Bestands -- unveraendert, mit
        # derselben Herkunftsangabe wie dort.
        geschossflaeche_m2=budget.bestand_gf_m2,
        geschossflaeche_herkunft=budget.bestand_herkunft,
        flaechen=flaechen,
        wohnungen=wohnungen,
        konflikte=konflikte,
        unsicherheiten=unsicherheiten,
        quellen=(bestand or {}).get("quellen_layer", []),
    )


def szenario_anbau(
    g1_ergebnis: dict[str, Any], bestand: dict[str, Any], budget: Ausnuetzungsbudget,
    zone: Optional[dict[str, Any]], *, profil: str, benutzerwerte, wohnungsmix,
    wohnungsmix_begruendung: str, wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    geschosshoehe_m: Optional[float] = None,
    restriktionen: Optional[dict[str, Any]] = None, **kw
) -> Szenario:
    baubereich = _als_flaeche(g1_ergebnis.get("baubereich_koordinaten"))
    bestandsflaechen = [p for p in (_polygon(g.get("grundriss")) for g in (bestand or {}).get("gebaeude", []))
                        if p is not None]

    szenario = Szenario(
        id="anbau", typ=Szenariotyp.ANBAU_ERWEITERUNG.value,
        bezeichnung="Anbau / Erweiterung", machbarkeit=MACHBARKEIT_NICHT_BESTIMMBAR,
        begruendung="", quellen=["G1-Baubereich", *(bestand or {}).get("quellen_layer", [])],
    )

    if baubereich is None:
        szenario.begruendung = (
            "Kein Baubereich vorhanden -- ohne ihn laesst sich nicht bestimmen, wo ein Anbau "
            "stehen koennte. Ursache siehe G1."
        )
        return szenario
    if not bestandsflaechen:
        hat_gebaeude = bool((bestand or {}).get("gebaeude"))
        szenario.machbarkeit = (
            MACHBARKEIT_NICHT_BESTIMMBAR if hat_gebaeude else MACHBARKEIT_NICHT_MOEGLICH
        )
        szenario.begruendung = _fehlender_bestand_grund(bestand, "ein Anbau")
        return szenario

    bestandsunion = unary_union(bestandsflaechen)
    frei = baubereich.difference(bestandsunion)
    teilflaechen = [
        p for p in _einzelpolygone(frei)
        if p.area >= MIN_BAUFLAECHE_M2 and _masse(p)[1] >= MIN_BAUBREITE_M
    ]
    verworfen = [p for p in _einzelpolygone(frei)
                 if p.area >= MIN_BAUFLAECHE_M2 and _masse(p)[1] < MIN_BAUBREITE_M]
    for p in verworfen:
        laenge, breite = _masse(p)
        szenario.konflikte.append(_konflikt(
            "geometrie",
            f"Ein freier Bereich von {p.area:.0f} m2 im {_richtung(bestandsunion, p)} ist nur "
            f"{breite:.1f} m breit (bei {laenge:.1f} m Laenge) -- unter der Mindestbreite von "
            f"{MIN_BAUBREITE_M:g} m nicht bebaubar.",
        ))

    if not teilflaechen:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = (
            f"Der Baubereich ({baubereich.area:.0f} m2) wird vom Bestand so ausgefuellt, dass "
            f"keine zusammenhaengende Restflaeche von mindestens {MIN_BAUFLAECHE_M2:g} m2 und "
            f"{MIN_BAUBREITE_M:g} m Breite bleibt. Grenzabstaende und Restriktionen sind darin "
            "bereits beruecksichtigt."
        )
        return szenario

    teilflaechen.sort(key=lambda p: p.area, reverse=True)
    richtungen = [_richtung(bestandsunion, p) for p in teilflaechen]

    # Geschosszahl: ein Anbau darf nicht hoeher werden als die Zone zulaesst.
    zulaessige_geschosse = g1_ergebnis.get("geschosszahl")
    bestand_geschosse = ((bestand or {}).get("hauptgebaeude") or {}).get("geschosse")
    geschosse = zulaessige_geschosse
    if geschosse is not None and bestand_geschosse is not None and bestand_geschosse < geschosse:
        szenario.unsicherheiten.append(
            f"Die Zone laesst {zulaessige_geschosse} Geschoss(e) zu, der Bestand hat "
            f"{bestand_geschosse}. Ein Anbau ueber die Bestandshoehe hinaus ist baurechtlich "
            "denkbar, gestalterisch aber oft nicht gewollt -- hier wird mit der zulaessigen "
            "Geschosszahl gerechnet."
        )

    flaeche_gesamt = sum(p.area for p in teilflaechen)
    for p, richtung in zip(teilflaechen, richtungen):
        laenge, breite = _masse(p)
        szenario.baukoerper.append(_baukoerper(
            name=f"Anbau {richtung}", polygon=p, geschosse=geschosse,
            hoehe_m=_hoehe(geschosse, geschosshoehe_m),
            herkunft="Baubereich abzueglich Bestandsgrundriss; Grenzabstaende, Strassenabstand "
                     "und Restriktionsflaechen sind im Baubereich bereits abgezogen",
            art="anbau",
        ))

    # Baurechtliche Pruefung: reicht die Ausnuetzung ueberhaupt?
    gf_geometrisch = round(flaeche_gesamt * geschosse, 1) if geschosse is not None else None
    gf_budget = budget.verbleibend_gf_m2

    if gf_budget is not None and gf_budget <= 0:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = (
            f"Geometrisch waeren im {richtungen[0]} noch {teilflaechen[0].area:.0f} m2 frei, "
            f"aber die zulaessige Geschossflaeche ({budget.zulaessig_gf_m2:.0f} m2) ist durch "
            f"den Bestand ({budget.bestand_gf_m2:.0f} m2) bereits ausgeschoepft."
        )
        szenario.konflikte.append(_konflikt(
            "ausnuetzung",
            f"Verbleibende Geschossflaeche {gf_budget:.0f} m2 -- kein Spielraum fuer einen Anbau.",
            schwere="ausschluss",
        ))
        return szenario

    if gf_geometrisch is None:
        szenario.machbarkeit = MACHBARKEIT_NICHT_BESTIMMBAR
        szenario.begruendung = (
            f"Ein Anbau im {richtungen[0]} waere geometrisch moeglich "
            f"({teilflaechen[0].area:.0f} m2, maximal {_masse(teilflaechen[0])[0]:.1f} x "
            f"{_masse(teilflaechen[0])[1]:.1f} m), aber die zulaessige Geschosszahl ist "
            "unbekannt -- damit laesst sich keine Flaeche bestimmen."
        )
        return szenario

    gf = gf_geometrisch
    herkunft = f"Freier Baubereich {flaeche_gesamt:.1f} m2 x {geschosse} Geschoss(e)"
    if gf_budget is not None and gf_budget < gf_geometrisch:
        gf = gf_budget
        herkunft = (
            f"Geometrisch moeglich waeren {gf_geometrisch:.1f} m2 "
            f"({flaeche_gesamt:.1f} m2 x {geschosse} Geschoss(e)), die verbleibende Ausnuetzung "
            f"laesst aber nur {gf_budget:.1f} m2 zu -- das Baurecht begrenzt."
        )
        szenario.konflikte.append(_konflikt(
            "ausnuetzung",
            f"Die Ausnuetzung begrenzt den Anbau auf {gf_budget:.0f} m2 Geschossflaeche; "
            f"geometrisch waeren {gf_geometrisch:.0f} m2 moeglich.",
        ))

    bereiche = ", ".join(
        f"{r} ({p.area:.0f} m2, max. {_masse(p)[0]:.1f} x {_masse(p)[1]:.1f} m)"
        for p, r in zip(teilflaechen, richtungen)
    )
    baulinie = baulinien_konflikt(restriktionen)
    if baulinie:
        szenario.konflikte.append(baulinie)
    szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT if szenario.konflikte else MACHBARKEIT_MOEGLICH
    szenario.begruendung = f"Anbau moeglich im Bereich: {bereiche}."
    szenario.geschosse = geschosse
    szenario.hoehe_m = _hoehe(geschosse, geschosshoehe_m)
    szenario.geschossflaeche_m2 = gf
    szenario.geschossflaeche_herkunft = herkunft
    szenario.flaechen = _flaechen_fuer(
        gf, g1_ergebnis, zone, profil, benutzerwerte, wohnungsmix, wohnungsmix_begruendung,
        wohnungsmix_herkunft,
        restflaeche_verteilen=kw.get("restflaeche_verteilen", False),
        geschosszahl=geschosse,
    )
    if szenario.flaechen:
        szenario.wohnungen = szenario.flaechen.get("wohnungen")
    if budget.bestand_gf_m2 is None:
        szenario.unsicherheiten.append(
            "Die Bestands-Geschossflaeche ist nicht bestimmbar -- ob die Ausnuetzung fuer "
            "diesen Anbau reicht, konnte deshalb NICHT geprueft werden."
        )
        szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT
    elif budget.bestand_herkunft:
        szenario.unsicherheiten.append(budget.bestand_herkunft)
    return szenario


def szenario_aufstockung(
    g1_ergebnis: dict[str, Any], bestand: dict[str, Any], budget: Ausnuetzungsbudget,
    zone: Optional[dict[str, Any]], *, profil: str, benutzerwerte, wohnungsmix,
    wohnungsmix_begruendung: str, wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    attika_zulaessig: Optional[bool] = None,
    geschosshoehe_m: Optional[float] = None, **kw
) -> Szenario:
    haupt = (bestand or {}).get("hauptgebaeude") or {}
    grundriss = _polygon(haupt.get("grundriss"))
    bestand_geschosse = haupt.get("geschosse")
    zulaessige_geschosse = g1_ergebnis.get("geschosszahl")

    szenario = Szenario(
        id="aufstockung", typ=Szenariotyp.AUFSTOCKUNG_DACHAUSBAU.value,
        bezeichnung="Aufstockung", machbarkeit=MACHBARKEIT_NICHT_BESTIMMBAR,
        begruendung="", quellen=["G1", *(bestand or {}).get("quellen_layer", [])],
    )

    if grundriss is None:
        hat_gebaeude = bool((bestand or {}).get("gebaeude"))
        szenario.begruendung = _fehlender_bestand_grund(bestand, "eine Aufstockung")
        szenario.machbarkeit = (
            MACHBARKEIT_NICHT_BESTIMMBAR if hat_gebaeude else MACHBARKEIT_NICHT_MOEGLICH
        )
        return szenario
    if bestand_geschosse is None:
        szenario.begruendung = (
            "Im GWR ist fuer das Hauptgebaeude keine Geschosszahl gefuehrt. Ob aufgestockt "
            "werden darf, ergibt sich aus dem Vergleich Bestand gegen zulaessig -- ohne die "
            "Bestandszahl ist das nicht entscheidbar. Manuelle Pruefung erforderlich."
        )
        szenario.unsicherheiten.append("GWR-Merkmal 'gastw' (Anzahl Geschosse) fehlt.")
        return szenario
    if zulaessige_geschosse is None:
        szenario.begruendung = (
            "Die zulaessige Geschosszahl ist nicht bestimmbar (weder Vollgeschosse noch "
            "Gebaeudehoehe in den Zonendaten) -- ein Vergleich mit dem Bestand ist damit "
            "nicht moeglich."
        )
        return szenario

    zusaetzliche = zulaessige_geschosse - bestand_geschosse
    vergleich = (
        f"Zulaessig {zulaessige_geschosse} Geschoss(e) (limitiert durch "
        f"{g1_ergebnis.get('geschosszahl_limitiert_durch')}), Bestand {bestand_geschosse}."
    )

    # Attika ist eine eigene Frage: die Zone kann ein Attikageschoss ueber den
    # Vollgeschossen zulassen. Modul 2 liefert das nicht strukturiert.
    if attika_zulaessig is None:
        szenario.unsicherheiten.append(
            "Ob die Zone ueber den Vollgeschossen ein Attikageschoss zulaesst, liefert die "
            "Reglementsauswertung nicht als strukturierten Wert. Diese Pruefung fehlt deshalb "
            "-- sie kann die Beurteilung in beide Richtungen aendern."
        )

    if zusaetzliche <= 0:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = (
            f"{vergleich} Die zulaessige Geschosszahl ist damit bereits ausgeschoepft "
            "-- eine Aufstockung ist nach der Regelbauweise nicht moeglich."
        )
        szenario.konflikte.append(_konflikt(
            "geschosszahl",
            f"Bestand {bestand_geschosse} Geschoss(e) entspricht bereits dem Maximum von "
            f"{zulaessige_geschosse}.",
            schwere="ausschluss",
        ))
        if attika_zulaessig:
            szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT
            szenario.begruendung += (
                " Ein Attikageschoss waere laut Vorgabe zusaetzlich zulaessig -- es zaehlt "
                "nicht als Vollgeschoss."
            )
        return szenario

    if budget.verbleibend_gf_m2 is not None and budget.verbleibend_gf_m2 <= 0:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = (
            f"{vergleich} Rein nach Geschosszahl waeren {zusaetzliche} Geschoss(e) moeglich, "
            f"aber die zulaessige Geschossflaeche ({budget.zulaessig_gf_m2:.0f} m2) ist durch "
            f"den Bestand ({budget.bestand_gf_m2:.0f} m2) bereits ausgeschoepft."
        )
        szenario.konflikte.append(_konflikt(
            "ausnuetzung", "Keine verbleibende Geschossflaeche.", schwere="ausschluss",
        ))
        return szenario

    gf_geometrisch = round(grundriss.area * zusaetzliche, 1)
    gf = gf_geometrisch
    herkunft = (
        f"Bestandsgrundriss {grundriss.area:.1f} m2 x {zusaetzliche} zusaetzliche(s) Geschoss(e)"
    )
    if budget.verbleibend_gf_m2 is not None and budget.verbleibend_gf_m2 < gf_geometrisch:
        gf = budget.verbleibend_gf_m2
        herkunft = (
            f"Geometrisch moeglich waeren {gf_geometrisch:.1f} m2 ({grundriss.area:.1f} m2 x "
            f"{zusaetzliche} Geschoss(e)), die verbleibende Ausnuetzung laesst aber nur "
            f"{budget.verbleibend_gf_m2:.1f} m2 zu."
        )
        szenario.konflikte.append(_konflikt(
            "ausnuetzung",
            f"Die Ausnuetzung begrenzt die Aufstockung auf {budget.verbleibend_gf_m2:.0f} m2; "
            f"geometrisch waeren {gf_geometrisch:.0f} m2 moeglich.",
        ))

    szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT if szenario.konflikte else MACHBARKEIT_MOEGLICH
    szenario.begruendung = (
        f"{vergleich} Aufstockung um {zusaetzliche} Geschoss(e) auf dem bestehenden Grundriss "
        f"({grundriss.area:.0f} m2) moeglich."
    )
    szenario.geschosse = zusaetzliche
    szenario.hoehe_m = _hoehe(bestand_geschosse + zusaetzliche, geschosshoehe_m)
    zulaessige_hoehe = _kennzahl(zone, "gebaeudehoehe_m") or _kennzahl(zone, "gesamthoehe_m")
    if szenario.hoehe_m is not None and zulaessige_hoehe is not None and szenario.hoehe_m > zulaessige_hoehe:
        szenario.konflikte.append(_konflikt(
            "hoehe",
            f"Das aufgestockte Gebaeude kaeme rechnerisch auf {szenario.hoehe_m:.2f} m "
            f"({bestand_geschosse + zusaetzliche} Geschosse x angenommener Geschosshoehe), "
            f"zulaessig sind {zulaessige_hoehe:g} m. Die Geschosshoehe ist eine Annahme und "
            "die baurechtliche Hoehe misst ab gewachsenem Terrain -- manuelle Pruefung.",
        ))
    szenario.geschossflaeche_m2 = gf
    szenario.geschossflaeche_herkunft = herkunft
    szenario.baukoerper.append(_baukoerper(
        name=f"Aufstockung +{zusaetzliche} Geschoss(e)", polygon=grundriss,
        geschosse=zusaetzliche, hoehe_m=_hoehe(zusaetzliche, geschosshoehe_m),
        herkunft="Bestandsgrundriss, vertikal erweitert -- keine neue Grundflaeche",
        art="aufstockung",
    ))
    szenario.flaechen = _flaechen_fuer(
        gf, g1_ergebnis, zone, profil, benutzerwerte, wohnungsmix, wohnungsmix_begruendung,
        wohnungsmix_herkunft,
        restflaeche_verteilen=kw.get("restflaeche_verteilen", False),
        geschosszahl=zusaetzliche,
    )
    if szenario.flaechen:
        szenario.wohnungen = szenario.flaechen.get("wohnungen")
    if budget.bestand_herkunft:
        szenario.unsicherheiten.append(budget.bestand_herkunft)
    szenario.unsicherheiten.append(
        "Die Tragfaehigkeit des Bestands fuer zusaetzliche Geschosse ist eine statische Frage "
        "und hier NICHT geprueft."
    )
    return szenario


def szenario_dachausbau(
    bestand: dict[str, Any], *, attika_zulaessig: Optional[bool] = None,
    dachgeschoss_zulaessig: Optional[bool] = None, **kw
) -> Szenario:
    """Dachausbau und Attika -- bewusst NICHT ueber die Vollgeschoss-Logik.

    Ob ein Dachgeschoss ausgebaut oder ein Attikageschoss aufgesetzt werden
    darf, steht im kommunalen Reglement (Dachform, Kniestockhoehe,
    Rueckversatz, Anrechenbarkeit). Modul 2 liefert davon heute keinen
    strukturierten Wert. Diese Luecke mit der Vollgeschoss-Regel zu fuellen
    waere genau die Scheingenauigkeit, die hier nicht vorkommen darf.
    """
    haupt = (bestand or {}).get("hauptgebaeude") or {}
    szenario = Szenario(
        id="dachausbau", typ=Szenariotyp.AUFSTOCKUNG_DACHAUSBAU.value,
        bezeichnung="Dachausbau / Attika", machbarkeit=MACHBARKEIT_NICHT_BESTIMMBAR,
        begruendung="", quellen=(bestand or {}).get("quellen_layer", []),
    )
    if not haupt:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = "Kein Gebaeude auf der Parzelle -- kein Dach, das ausgebaut werden koennte."
        return szenario

    if attika_zulaessig is None and dachgeschoss_zulaessig is None:
        szenario.begruendung = (
            "Nicht bestimmbar. Ob ein Dachgeschoss ausgebaut oder ein Attikageschoss aufgesetzt "
            "werden darf, haengt an Dachform, Kniestockhoehe, Rueckversatz und Anrechenbarkeit "
            "-- alles Angaben, die die Reglementsauswertung heute nicht strukturiert liefert. "
            "Die Vollgeschoss-Regel ist dafuer KEIN Ersatz."
        )
        szenario.unsicherheiten.append(
            "Benoetigt: Attika-/Dachgeschossregelung der Zone als strukturierter Wert "
            "(zulaessig ja/nein, Rueckversatz, maximale Flaeche, Anrechenbarkeit)."
        )
        return szenario

    erlaubt = [name for name, wert in
               (("Attikageschoss", attika_zulaessig), ("Dachgeschossausbau", dachgeschoss_zulaessig))
               if wert]
    if not erlaubt:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = "Weder Attikageschoss noch Dachgeschossausbau sind laut Vorgabe zulaessig."
        return szenario

    szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT
    szenario.begruendung = (
        f"{' und '.join(erlaubt)} laut Vorgabe zulaessig. Flaeche und Volumen haengen an "
        "Rueckversatz und Dachform und sind ohne diese Angaben nicht bezifferbar."
    )
    szenario.unsicherheiten.append(
        "Die zulaessige Flaeche des Attika-/Dachgeschosses ist nicht bekannt -- ein "
        "Rueckversatz reduziert sie gegenueber dem darunterliegenden Geschoss erheblich."
    )
    return szenario


def szenario_ersatzneubau(
    g1_ergebnis: dict[str, Any], bestand: dict[str, Any], zone: Optional[dict[str, Any]],
    *, profil: str, benutzerwerte, wohnungsmix, wohnungsmix_begruendung: str,
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    geschosshoehe_m: Optional[float] = None, restriktionen: Optional[dict[str, Any]] = None,
    budget: Optional[Ausnuetzungsbudget] = None, **kw
) -> Szenario:
    baubereich = _als_flaeche(g1_ergebnis.get("baubereich_koordinaten"))
    gf = g1_ergebnis.get("geschossflaeche_m2")
    geschosse = g1_ergebnis.get("geschosszahl")
    fussabdruck = g1_ergebnis.get("fussabdruck_m2")

    szenario = Szenario(
        id="ersatzneubau", typ=Szenariotyp.ERSATZNEUBAU.value,
        bezeichnung="Ersatzneubau", machbarkeit=MACHBARKEIT_NICHT_BESTIMMBAR,
        begruendung="", quellen=["G1", *(bestand or {}).get("quellen_layer", [])],
    )

    if gf is None or baubereich is None:
        szenario.begruendung = (
            "G1 konnte weder Baubereich noch Geschossflaeche bestimmen -- ohne sie gibt es "
            f"keinen Ersatzneubau zu rechnen. Kandidaten: {g1_ergebnis.get('geschossflaeche_kandidaten') or 'keine'}."
        )
        return szenario

    # Theoretisch zulaessig gegen geometrisch umsetzbar -- das ist die
    # Kernaussage dieses Szenarios.
    kandidaten = g1_ergebnis.get("geschossflaeche_kandidaten") or {}
    geometrisch = kandidaten.get("fussabdruck_x_geschosse")
    theoretisch = {k: v for k, v in kandidaten.items() if k != "fussabdruck_x_geschosse"}
    limitierend = g1_ergebnis.get("geschossflaeche_limitiert_durch")

    if geometrisch is not None and theoretisch:
        hoechstes_theoretisch = max(theoretisch.values())
        if geometrisch < hoechstes_theoretisch:
            szenario.konflikte.append(_konflikt(
                "geometrie",
                f"Die Nutzungsziffern liessen {hoechstes_theoretisch:.0f} m2 Geschossflaeche zu, "
                f"die Geometrie (Baubereich x Geschosse) nur {geometrisch:.0f} m2 -- "
                f"{hoechstes_theoretisch - geometrisch:.0f} m2 sind rechtlich zulaessig, aber "
                "auf dieser Parzelle nicht unterzubringen.",
            ))
        else:
            szenario.konflikte.append(_konflikt(
                "ausnuetzung",
                f"Die Geometrie liesse {geometrisch:.0f} m2 zu, die Nutzungsziffern begrenzen "
                f"auf {hoechstes_theoretisch:.0f} m2 -- das Baurecht ist hier die engere Schranke.",
            ))

    baulinie = baulinien_konflikt(restriktionen)
    if baulinie:
        szenario.konflikte.append(baulinie)
    szenario.machbarkeit = MACHBARKEIT_MOEGLICH
    szenario.begruendung = (
        f"Abbruch und Neubau im gesamten Baubereich ({baubereich.area:.0f} m2). Zulaessiger "
        f"Fussabdruck {fussabdruck:.0f} m2"
        + (f" ({g1_ergebnis.get('fussabdruck_limitiert_durch')})" if fussabdruck else "")
        + f", {geschosse} Geschoss(e), Geschossflaeche {gf:.0f} m2 "
        f"(limitiert durch {limitierend})."
    )
    szenario.geschosse = geschosse
    szenario.hoehe_m = _hoehe(geschosse, geschosshoehe_m)
    szenario.geschossflaeche_m2 = gf
    szenario.geschossflaeche_herkunft = f"G1, limitiert durch {limitierend}"

    # Der Baukoerper belegt den zulaessigen Fussabdruck. Ist er kleiner als
    # der Baubereich, wird der Baubereich als moegliche LAGE gezeigt -- wo
    # genau das Gebaeude darin steht, ist eine Entwurfsfrage.
    szenario.baukoerper.append(_baukoerper(
        name="Baubereich (moegliche Lage)", polygon=baubereich if baubereich.geom_type == "Polygon"
        else max(_einzelpolygone(baubereich), key=lambda p: p.area),
        geschosse=geschosse, hoehe_m=_hoehe(geschosse, geschosshoehe_m),
        herkunft="G1-Baubereich nach Grenzabstaenden und Restriktionen; der zulaessige "
                 f"Fussabdruck betraegt {fussabdruck:.0f} m2 und kann darin frei platziert werden"
        if fussabdruck else "G1-Baubereich",
        art="ersatzneubau",
    ))
    if fussabdruck is not None and baubereich.area - fussabdruck > 1.0:
        szenario.unsicherheiten.append(
            f"Der zulaessige Fussabdruck ({fussabdruck:.0f} m2) ist kleiner als der Baubereich "
            f"({baubereich.area:.0f} m2). Wo genau der Baukoerper darin steht, ist eine "
            "Entwurfsfrage und wird hier nicht vorweggenommen."
        )

    szenario.flaechen = _flaechen_fuer(
        gf, g1_ergebnis, zone, profil, benutzerwerte, wohnungsmix, wohnungsmix_begruendung,
        wohnungsmix_herkunft,
        restflaeche_verteilen=kw.get("restflaeche_verteilen", False),
    )
    if szenario.flaechen:
        szenario.wohnungen = szenario.flaechen.get("wohnungen")
    if (bestand or {}).get("gebaeude"):
        szenario.unsicherheiten.append(
            f"{len((bestand or {}).get('gebaeude'))} bestehende(s) Gebaeude muessen abgebrochen "
            "werden. Abbruchkosten, Entsorgung und ein allfaelliger Substanzschutz sind hier "
            "nicht geprueft."
        )

    # Der wirtschaftlich entscheidende Fall: ein Ersatzneubau, der KLEINER
    # ausfaellt als der Bestand. Live beobachtet an Uettligen (Bestand 713 m2,
    # heute zulaessig 470 m2).
    bestand_gf = budget.bestand_gf_m2 if budget else None
    if bestand_gf is not None and gf < bestand_gf:
        szenario.konflikte.append(_konflikt(
            "besitzstand",
            f"Der Ersatzneubau waere mit {gf:.0f} m2 Geschossflaeche KLEINER als der Bestand "
            f"({bestand_gf:.0f} m2) -- die Parzelle ist nach heutigem Recht ueberbaut. Der "
            "Bestand geniesst in der Regel Besitzstandsgarantie; ein Abbruch gibt diesen "
            "Vorteil auf. Das ist eine wirtschaftliche Entscheidung, keine baurechtliche.",
            schwere="einschraenkung",
        ))
        szenario.machbarkeit = MACHBARKEIT_EINGESCHRAENKT
    return szenario


def szenario_bestand_plus_neubau(
    g1_ergebnis: dict[str, Any], bestand: dict[str, Any], budget: Ausnuetzungsbudget,
    zone: Optional[dict[str, Any]], *, profil: str, benutzerwerte, wohnungsmix,
    wohnungsmix_begruendung: str, wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    gebaeudeabstand_m: Optional[float] = None,
    geschosshoehe_m: Optional[float] = None, restriktionen: Optional[dict[str, Any]] = None,
    **kw
) -> Szenario:
    """Wie der Anbau, aber als eigenstaendiger Baukoerper.

    Der Unterschied ist baurechtlich wesentlich: ein freistehender zweiter
    Baukoerper muss den Gebaeudeabstand zum Bestand einhalten, ein Anbau
    nicht (er wird Teil desselben Gebaeudes).
    """
    baubereich = _als_flaeche(g1_ergebnis.get("baubereich_koordinaten"))
    bestandsflaechen = [p for p in (_polygon(g.get("grundriss")) for g in (bestand or {}).get("gebaeude", []))
                        if p is not None]

    szenario = Szenario(
        id="bestand_plus_neubau", typ=Szenariotyp.KOMBINATION_BESTAND_NEUBAU.value,
        bezeichnung="Bestand + Neubau", machbarkeit=MACHBARKEIT_NICHT_BESTIMMBAR,
        begruendung="", quellen=["G1-Baubereich", *(bestand or {}).get("quellen_layer", [])],
    )

    if baubereich is None:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = "Kein Baubereich vorhanden."
        return szenario
    if not bestandsflaechen:
        hat_gebaeude = bool((bestand or {}).get("gebaeude"))
        szenario.machbarkeit = (
            MACHBARKEIT_NICHT_BESTIMMBAR if hat_gebaeude else MACHBARKEIT_NICHT_MOEGLICH
        )
        szenario.begruendung = _fehlender_bestand_grund(bestand, "ein zusaetzlicher Baukoerper")
        return szenario

    bestandsunion = unary_union(bestandsflaechen)
    # Der Gebaeudeabstand ist kantonal/kommunal geregelt und liegt nicht
    # strukturiert vor. Ohne Wert wird KEIN Abstand angenommen -- stattdessen
    # wird das ausgewiesen.
    if gebaeudeabstand_m is None:
        szenario.unsicherheiten.append(
            "Der Gebaeudeabstand zwischen zwei Bauten auf derselben Parzelle ist kantonal "
            "geregelt und liegt nicht strukturiert vor. Hier wurde KEIN Abstand abgezogen -- "
            "die ausgewiesene Flaeche ist deshalb eine Obergrenze."
        )
        abstandsflaeche = bestandsunion
    else:
        abstandsflaeche = bestandsunion.buffer(gebaeudeabstand_m)
        szenario.konflikte.append(_konflikt(
            "gebaeudeabstand",
            f"Gebaeudeabstand {gebaeudeabstand_m:g} m zum Bestand beruecksichtigt.",
            schwere="hinweis",
        ))

    frei = baubereich.difference(abstandsflaeche)
    teilflaechen = [
        p for p in _einzelpolygone(frei)
        if p.area >= MIN_BAUFLAECHE_M2 and _masse(p)[1] >= MIN_BAUBREITE_M
    ]
    if not teilflaechen:
        szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
        szenario.begruendung = (
            "Neben dem Bestand bleibt im Baubereich keine Flaeche von mindestens "
            f"{MIN_BAUFLAECHE_M2:g} m2 und {MIN_BAUBREITE_M:g} m Breite frei"
            + (f" (Gebaeudeabstand {gebaeudeabstand_m:g} m beruecksichtigt)." if gebaeudeabstand_m else ".")
        )
        return szenario

    teilflaechen.sort(key=lambda p: p.area, reverse=True)
    geschosse = g1_ergebnis.get("geschosszahl")
    flaeche_gesamt = sum(p.area for p in teilflaechen)

    for p in teilflaechen:
        szenario.baukoerper.append(_baukoerper(
            name=f"Neubau {_richtung(bestandsunion, p)}", polygon=p, geschosse=geschosse,
            hoehe_m=_hoehe(geschosse, geschosshoehe_m),
            herkunft="Baubereich abzueglich Bestand"
                     + (f" und Gebaeudeabstand {gebaeudeabstand_m:g} m" if gebaeudeabstand_m else ""),
            art="neubau",
        ))
    for g in bestandsflaechen:
        szenario.baukoerper.append(_baukoerper(
            name="Bestand (bleibt)", polygon=g,
            geschosse=((bestand or {}).get("hauptgebaeude") or {}).get("geschosse"),
            hoehe_m=_hoehe(((bestand or {}).get("hauptgebaeude") or {}).get("geschosse"), geschosshoehe_m),
            herkunft="Bestandsgrundriss", art="bestand",
        ))

    if geschosse is None:
        szenario.begruendung = (
            f"Geometrisch waeren {flaeche_gesamt:.0f} m2 fuer einen zusaetzlichen Baukoerper "
            "frei, aber die zulaessige Geschosszahl ist unbekannt."
        )
        return szenario

    gf_geometrisch = round(flaeche_gesamt * geschosse, 1)
    gf = gf_geometrisch
    herkunft = f"Freie Flaeche {flaeche_gesamt:.1f} m2 x {geschosse} Geschoss(e)"
    if budget.verbleibend_gf_m2 is not None:
        if budget.verbleibend_gf_m2 <= 0:
            szenario.machbarkeit = MACHBARKEIT_NICHT_MOEGLICH
            szenario.begruendung = (
                f"Geometrisch waeren {flaeche_gesamt:.0f} m2 frei, aber die zulaessige "
                f"Geschossflaeche ist durch den Bestand bereits ausgeschoepft."
            )
            szenario.konflikte.append(_konflikt("ausnuetzung", "Keine verbleibende Geschossflaeche.",
                                                schwere="ausschluss"))
            return szenario
        if budget.verbleibend_gf_m2 < gf_geometrisch:
            gf = budget.verbleibend_gf_m2
            herkunft = (
                f"Geometrisch moeglich waeren {gf_geometrisch:.1f} m2, die verbleibende "
                f"Ausnuetzung laesst aber nur {budget.verbleibend_gf_m2:.1f} m2 zu."
            )
            szenario.konflikte.append(_konflikt(
                "ausnuetzung",
                f"Die Ausnuetzung begrenzt den Neubau auf {budget.verbleibend_gf_m2:.0f} m2.",
            ))

    baulinie = baulinien_konflikt(restriktionen)
    if baulinie:
        szenario.konflikte.append(baulinie)
    szenario.machbarkeit = (
        MACHBARKEIT_EINGESCHRAENKT
        if any(k["schwere"] != "hinweis" for k in szenario.konflikte) or szenario.unsicherheiten
        else MACHBARKEIT_MOEGLICH
    )
    szenario.begruendung = (
        f"Der Bestand bleibt stehen; zusaetzlicher Baukoerper auf "
        + ", ".join(f"{_richtung(bestandsunion, p)} ({p.area:.0f} m2, max. "
                    f"{_masse(p)[0]:.1f} x {_masse(p)[1]:.1f} m)" for p in teilflaechen)
        + "."
    )
    szenario.geschosse = geschosse
    szenario.hoehe_m = _hoehe(geschosse, geschosshoehe_m)
    szenario.geschossflaeche_m2 = gf
    szenario.geschossflaeche_herkunft = herkunft
    szenario.flaechen = _flaechen_fuer(
        gf, g1_ergebnis, zone, profil, benutzerwerte, wohnungsmix, wohnungsmix_begruendung,
        wohnungsmix_herkunft,
        restflaeche_verteilen=kw.get("restflaeche_verteilen", False),
        geschosszahl=geschosse,
    )
    if szenario.flaechen:
        szenario.wohnungen = szenario.flaechen.get("wohnungen")
    if budget.bestand_herkunft:
        szenario.unsicherheiten.append(budget.bestand_herkunft)
    return szenario


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

ALLE_SZENARIEN = ("bestand", "sanierung", "anbau", "aufstockung", "dachausbau",
                  "ersatzneubau", "bestand_plus_neubau")


def berechne_szenarien(
    g1_ergebnis: Optional[dict[str, Any]],
    bestand: Optional[dict[str, Any]],
    zone: Optional[dict[str, Any]] = None,
    *,
    restriktionen: Optional[dict[str, Any]] = None,
    auswahl: Optional[list[str]] = None,
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list[WohnungstypVorgabe]] = None,
    wohnungsmix_begruendung: str = "",
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    attika_zulaessig: Optional[bool] = None,
    dachgeschoss_zulaessig: Optional[bool] = None,
    gebaeudeabstand_m: Optional[float] = None,
    restflaeche_verteilen: bool = False,
    bestand_flaeche_nwf_m2: Optional[float] = None,
) -> dict[str, Any]:
    """Rechnet alle (oder die gewaehlten) Entwicklungsszenarien.

    `g1_ergebnis` ist das einzelne G1-Ergebnis (der `ergebnis`-Teil aus
    `berechne_g1_fuer_fall`), nicht die Bandbreite -- ein Szenario auf einem
    willkuerlich gewaehlten Bandbreiten-Rand waere nicht belastbar.
    """
    if not g1_ergebnis:
        return {
            "status": MACHBARKEIT_NICHT_BESTIMMBAR,
            "grund": (
                "Kein einzelnes G1-Ergebnis vorhanden. Szenarien brauchen einen konkreten "
                "Baubereich und eine konkrete Geschosszahl; auf einem Bandbreiten-Rand waeren "
                "sie nicht belastbar. Siehe Kantenprotokoll fuer die offenen Kanten."
            ),
            "szenarien": {},
        }

    bestand = bestand or {"gebaeude": [], "hauptgebaeude": None, "quellen_layer": []}
    budget = berechne_ausnuetzungsbudget(g1_ergebnis, bestand)

    geschosshoehe = annahmenprofil(profil, benutzerwerte)["geschosshoehe_m"]
    gemeinsam = dict(
        profil=profil, benutzerwerte=benutzerwerte, wohnungsmix=wohnungsmix,
        wohnungsmix_begruendung=wohnungsmix_begruendung,
        wohnungsmix_herkunft=wohnungsmix_herkunft,
        geschosshoehe_m=geschosshoehe.wert, restriktionen=restriktionen,
        restflaeche_verteilen=restflaeche_verteilen,
    )
    bauer = {
        "bestand": lambda: szenario_bestand(bestand, budget, **gemeinsam),
        "sanierung": lambda: szenario_sanierung(
            bestand, budget, bestand_flaeche_nwf_m2=bestand_flaeche_nwf_m2, **gemeinsam),
        "anbau": lambda: szenario_anbau(g1_ergebnis, bestand, budget, zone, **gemeinsam),
        "aufstockung": lambda: szenario_aufstockung(
            g1_ergebnis, bestand, budget, zone, attika_zulaessig=attika_zulaessig, **gemeinsam),
        "dachausbau": lambda: szenario_dachausbau(
            bestand, attika_zulaessig=attika_zulaessig,
            dachgeschoss_zulaessig=dachgeschoss_zulaessig, **gemeinsam),
        "ersatzneubau": lambda: szenario_ersatzneubau(
            g1_ergebnis, bestand, zone, budget=budget, **gemeinsam),
        "bestand_plus_neubau": lambda: szenario_bestand_plus_neubau(
            g1_ergebnis, bestand, budget, zone, gebaeudeabstand_m=gebaeudeabstand_m, **gemeinsam),
    }

    gewaehlt = auswahl or list(ALLE_SZENARIEN)
    unbekannt = [s for s in gewaehlt if s not in bauer]
    if unbekannt:
        raise SzenarioError(f"Unbekannte Szenarien: {unbekannt}. Bekannt: {sorted(bauer)}")

    ergebnisse = {name: bauer[name]().to_dict() for name in gewaehlt}

    return {
        "status": "berechnet",
        "ausnuetzungsbudget": budget.to_dict(),
        "geschosshoehe": geschosshoehe.to_dict(),
        "szenarien": ergebnisse,
        "vergleich": vergleiche(ergebnisse),
    }


def vergleiche(szenarien: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Eine Zeile je Szenario fuer den direkten Vergleich."""
    zeilen = []
    for name, s in szenarien.items():
        flaechen = (s.get("flaechen") or {}).get("flaechen") or {}
        wohnungen = s.get("wohnungen") or {}
        zeilen.append({
            "id": name,
            "bezeichnung": s.get("bezeichnung"),
            "machbarkeit": s.get("machbarkeit"),
            "geschosse": s.get("geschosse"),
            "hoehe_m": s.get("hoehe_m"),
            "geschossflaeche_m2": s.get("geschossflaeche_m2"),
            "nutzflaeche_nf_m2": (flaechen.get("nutzflaeche_nf") or {}).get("wert"),
            "hauptnutzflaeche_hnf_m2": (flaechen.get("hauptnutzflaeche_hnf") or {}).get("wert"),
            "wohnflaeche_nwf_m2": (flaechen.get("wohnflaeche_nwf") or {}).get("wert"),
            "wohnungen": wohnungen.get("anzahl_wohnungen"),
            "anzahl_konflikte": len(s.get("konflikte") or []),
            "anzahl_unsicherheiten": len(s.get("unsicherheiten") or []),
        })
    reihenfolge = {MACHBARKEIT_MOEGLICH: 0, MACHBARKEIT_EINGESCHRAENKT: 1, MACHBARKEIT_BESTEHT: 2,
                   MACHBARKEIT_NICHT_BESTIMMBAR: 3, MACHBARKEIT_NICHT_MOEGLICH: 4}
    zeilen.sort(key=lambda z: (
        reihenfolge.get(z["machbarkeit"], 9), -(z["geschossflaeche_m2"] or 0)
    ))
    return zeilen

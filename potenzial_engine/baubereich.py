"""
G1 -- Geometrischer/baurechtlicher Potenzial-Kernel (Baubereich-Kaskade).

Reine Berechnungslogik, KEIN Netzwerkzugriff. Nimmt Parzellengeometrie,
kantenspezifische Grenzabstaende, Restriktionsflaechen und Nutzungsziffern
als Parameter entgegen und berechnet die Kaskade:

    Parzellenpolygon
      -> kantenspezifische Grenzabstaende (Halbebenen-Schnitt)
      -> Restriktionsflaechen abziehen (Gewaesserraum/Wald/...)
      -> Baubereich
      -> Fussabdruck (ggf. durch Ueberbauungsziffer gedeckelt)
      -> Geschosszahl (Vollgeschosse vs. Hoehe/Geschosshoehe, das Striktere gilt)
      -> Geschossflaeche aus Geometrie
      -> Gegenkontrolle gegen AZ / aGFZ / BMZ
      -> limitierender Parameter je Kaskadenstufe

Datenbeschaffung (Parzellengeometrie aus Modul 1, Nachbarparzellen,
Gewaesserraum-/Waldgrenzen-WFS) ist bewusst NICHT Teil dieses Moduls -- das
ist ein separater Beschaffungsschritt (G2), der die hier erwarteten
Roh-Koordinatenlisten liefert.

Wichtig -- kein globaler Buffer: Ein einfacher `polygon.buffer(-d)` waere
fuer UNGLEICHE Grenzabstaende pro Kante (z.B. Kernzone: Strassenseite anders
als Nachbarseite) nicht moeglich (buffer() kennt nur einen einzigen,
einheitlichen Abstand). Stattdessen wird pro Kante eine nach innen versetzte
Stuetzgerade bestimmt und jeder neue Eckpunkt als Schnittpunkt der beiden
BENACHBARTEN Versatzgeraden konstruiert (Mitre-Konstruktion, siehe
`_line_intersection`/`berechne_baubereich_polygon`).

ACHTUNG -- bewusst NICHT per sequenziellem Halbebenen-Schnitt ueber die volle
Polygonflaeche implementiert: eine fruehere Version dieses Moduls schnitt die
Restflaeche nacheinander mit der Halbebene JEDER Kante (begrenzt durch deren
volle Gerade). Das ist fuer KONVEXE Polygone identisch zur Mitre-Konstruktion,
erodiert aber KONKAVE Polygone falsch, weil die unendliche Stuetzgerade einer
Kante auch weit entfernte, mit dieser Kante gar nicht benachbarte Teile des
Polygons abschneidet (am Reflex-Eckfall des L-Form-Testfalls T2 live
nachgewiesen: 36 m2 statt korrekt 156 m2, gegengeprueft mit einer von der
eigenen Implementierung unabhaengigen shapely-`buffer(-d)`-Berechnung fuer den
Fall gleicher Abstaende auf allen Kanten). Die Mitre-Konstruktion bezieht pro
Eckpunkt nur die ZWEI angrenzenden Kanten ein und ist deshalb auch fuer
konkave Parzellen korrekt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

Koordinate = tuple[float, float]
Ring = list[Koordinate]

# Epsilon fuer den Innenseiten-Test einer Kante (Meter). Ein Punkt wird knapp
# neben dem Kantenmittelpunkt in beide moeglichen Normalenrichtungen gesetzt;
# welcher davon effektiv IM Parzellenpolygon liegt, bestimmt die
# Innenrichtung. Funktioniert unabhaengig von der Ringorientierung
# (CW/CCW) und unabhaengig von Konvexitaet/Konkavitaet, da real gegen das
# Polygon getestet wird (nicht nur gegen eine Interior-Point-Heuristik, die
# bei stark konkaven Parzellen die falsche Seite waehlen kann).
_EDGE_NORMAL_EPS_M = 0.01


def _schliesse_ring_nicht(ring: Ring) -> Ring:
    r = list(ring)
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]
    return r


def _edge_inward_normal(parzelle: Polygon, p1: Koordinate, p2: Koordinate) -> Koordinate:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    laenge = math.hypot(dx, dy)
    if laenge == 0:
        raise ValueError(f"Entartete Kante (Laenge 0) im Parzellenpolygon bei {p1}.")
    ux, uy = dx / laenge, dy / laenge
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    n1 = (-uy, ux)
    n2 = (uy, -ux)
    eps = min(_EDGE_NORMAL_EPS_M, laenge * 0.1)
    test1 = Point(mx + n1[0] * eps, my + n1[1] * eps)
    if parzelle.contains(test1):
        return n1
    return n2


def _line_intersection(
    p1: Koordinate, d1: Koordinate, p2: Koordinate, d2: Koordinate
) -> Optional[Koordinate]:
    """Schnittpunkt zweier Geraden (Punkt + Richtungsvektor). None bei
    (nahezu) parallelen Geraden."""
    x1, y1 = p1
    dx1, dy1 = d1
    x2, y2 = p2
    dx2, dy2 = d2
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return None
    t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / denom
    return (x1 + dx1 * t, y1 + dy1 * t)


def berechne_baubereich_polygon(
    parzelle_koordinaten: Ring, kanten_abstaende: list[float]
) -> tuple[Polygon, list[dict]]:
    """Baubereich = Parzelle, jede Kante um ihren individuellen Grenzabstand
    nach innen versetzt, per Mitre-Konstruktion (siehe Modul-Docstring fuer
    die Begruendung, warum kein sequenzieller Halbebenen-Schnitt verwendet
    wird).

    `kanten_abstaende[i]` ist der Grenzabstand (in Metern) fuer die Kante von
    `parzelle_koordinaten[i]` nach `parzelle_koordinaten[(i+1) % n]`. Ein Wert
    von 0 oder None laesst diese Kante an ihrer Original-Position (keine
    Einschraenkung durch diese Kante). Muss genau einen Wert pro Kante
    enthalten (die Zuordnung, welche Kante Strassen-/Nachbar-/Grenzabstand
    bekommt, ist Aufgabe des Aufrufers -- reine Geometrie kennt diese
    Unterscheidung nicht).
    """
    ring = _schliesse_ring_nicht(parzelle_koordinaten)
    n = len(ring)
    if len(kanten_abstaende) != n:
        raise ValueError(
            f"kanten_abstaende braucht genau {n} Werte (eine Kante je Vertex-Paar "
            f"ring[i]->ring[i+1]), erhalten: {len(kanten_abstaende)}."
        )

    parzelle = Polygon(ring)
    if not parzelle.is_valid:
        parzelle = parzelle.buffer(0)

    kanten_info = []
    for i in range(n):
        p1, p2 = ring[i], ring[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        laenge = math.hypot(dx, dy)
        if laenge == 0:
            raise ValueError(f"Entartete Kante (Laenge 0) im Parzellenpolygon bei {p1}.")
        richtung = (dx / laenge, dy / laenge)
        distanz = kanten_abstaende[i] or 0.0
        if distanz > 0:
            normal = _edge_inward_normal(parzelle, p1, p2)
        else:
            normal = (0.0, 0.0)
        offset_punkt = (p1[0] + normal[0] * distanz, p1[1] + normal[1] * distanz)
        kanten_info.append(
            {"p1": p1, "p2": p2, "richtung": richtung, "offset_punkt": offset_punkt, "distanz": distanz}
        )

    neue_ring = []
    for i in range(n):
        vorherige = kanten_info[i - 1]  # Kante, die bei ring[i] endet
        aktuelle = kanten_info[i]  # Kante, die bei ring[i] beginnt
        schnitt = _line_intersection(
            vorherige["offset_punkt"], vorherige["richtung"],
            aktuelle["offset_punkt"], aktuelle["richtung"],
        )
        if schnitt is None:
            # (nahezu) parallele Nachbarkanten an dieser Ecke (entartet/
            # kollinear) -- Fallback auf den Versatzpunkt der Folgekante,
            # statt eine unendliche/undefinierte Mitre-Spitze zu erzeugen.
            schnitt = aktuelle["offset_punkt"]
        neue_ring.append(schnitt)

    baubereich = Polygon(neue_ring)
    if not baubereich.is_valid:
        # Bei starker Erosion an einer Reflex-Ecke kann der mitre-konstruierte
        # Ring sich selbst schneiden (die Kerbe "kollabiert"). buffer(0) loest
        # das nach der ueblichen GEOS-Selbstueberschneidungs-Reparatur auf.
        baubereich = baubereich.buffer(0)
    # Sicherheitsnetz: Baubereich darf die Originalparzelle nie verlassen
    # (kann bei sehr spitzen/stumpfen Mitre-Ecken theoretisch passieren).
    baubereich = baubereich.intersection(parzelle)

    protokoll = [
        {
            "kante_index": i,
            "von": kanten_info[i]["p1"],
            "nach": kanten_info[i]["p2"],
            "grenzabstand_m": kanten_info[i]["distanz"],
        }
        for i in range(n)
    ]
    return baubereich, protokoll


def _restriktionen_abziehen(
    polygon: Polygon | MultiPolygon, restriktionsflaechen: list[Ring]
) -> tuple[Polygon | MultiPolygon, Polygon | MultiPolygon]:
    restr_polys = []
    for r in restriktionsflaechen:
        p = Polygon(_schliesse_ring_nicht(r))
        if not p.is_valid:
            p = p.buffer(0)
        restr_polys.append(p)
    union = unary_union(restr_polys)
    return polygon.difference(union), union


def _geometrie_zu_koordinaten(geom: Polygon | MultiPolygon) -> list[list[Koordinate]]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [list(geom.exterior.coords)]
    if geom.geom_type == "MultiPolygon":
        return [list(p.exterior.coords) for p in geom.geoms]
    return []


@dataclass
class PotenzialErgebnis:
    baubereich_koordinaten: list[list[Koordinate]]
    baubereich_vor_restriktion_m2: float
    baubereich_m2: float
    parzellenflaeche_m2: float
    anrechenbare_landflaeche_m2: float
    fussabdruck_m2: float
    fussabdruck_limitiert_durch: str
    fussabdruck_kandidaten: dict
    geschosszahl: Optional[int]
    geschosszahl_limitiert_durch: Optional[str]
    geschosszahl_kandidaten: dict
    geschossflaeche_aus_geometrie_m2: Optional[float]
    geschossflaeche_m2: Optional[float]
    geschossflaeche_limitiert_durch: Optional[str]
    geschossflaeche_kandidaten: dict
    kantenprotokoll: list[dict]
    effektive_kanten_abstaende: list[float]
    hinweise: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "baubereich_koordinaten": self.baubereich_koordinaten,
            "baubereich_vor_restriktion_m2": self.baubereich_vor_restriktion_m2,
            "baubereich_m2": self.baubereich_m2,
            "parzellenflaeche_m2": self.parzellenflaeche_m2,
            "anrechenbare_landflaeche_m2": self.anrechenbare_landflaeche_m2,
            "fussabdruck_m2": self.fussabdruck_m2,
            "fussabdruck_limitiert_durch": self.fussabdruck_limitiert_durch,
            "fussabdruck_kandidaten": self.fussabdruck_kandidaten,
            "geschosszahl": self.geschosszahl,
            "geschosszahl_limitiert_durch": self.geschosszahl_limitiert_durch,
            "geschosszahl_kandidaten": self.geschosszahl_kandidaten,
            "geschossflaeche_aus_geometrie_m2": self.geschossflaeche_aus_geometrie_m2,
            "geschossflaeche_m2": self.geschossflaeche_m2,
            "geschossflaeche_limitiert_durch": self.geschossflaeche_limitiert_durch,
            "geschossflaeche_kandidaten": self.geschossflaeche_kandidaten,
            "kantenprotokoll": self.kantenprotokoll,
            "effektive_kanten_abstaende": self.effektive_kanten_abstaende,
            "hinweise": self.hinweise,
        }


def berechne_potenzial(
    parzelle_koordinaten: Ring,
    kanten_abstaende: list[float],
    *,
    restriktionsflaechen: Optional[list[Ring]] = None,
    restriktionsflaechen_zaehlen_zur_landflaeche: bool = False,
    ausnuetzungsziffer_az: Optional[float] = None,
    anrechenbare_geschossflaechenziffer_abgf: Optional[float] = None,
    baumassenziffer_bmz: Optional[float] = None,
    ueberbauungsziffer_uz: Optional[float] = None,
    vollgeschosse_max: Optional[int] = None,
    gebaeudehoehe_m: Optional[float] = None,
    geschosshoehe_m: float = 3.0,
    mehrlaengenzuschlag_schwelle_m: Optional[float] = None,
    mehrlaengenzuschlag_zuschlag_pro_m: Optional[float] = None,
) -> PotenzialErgebnis:
    """Fuehrt die gesamte G1-Kaskade fuer eine Parzelle aus.

    Reine Geometrie/Arithmetik -- kein Netzwerkzugriff. Alle Nutzungsziffern
    und Grenzabstaende sind explizite Parameter (Datenbeschaffung ist Sache
    des Aufrufers/G2). Keine stillen Annahmen: jede Umrechnung (BMZ->Flaeche,
    Restriktionsflaechen-Behandlung, Mehrlaengenzuschlag-Naeherung) wird in
    `hinweise` dokumentiert.
    """
    ring = _schliesse_ring_nicht(parzelle_koordinaten)
    n = len(ring)
    hinweise: list[str] = []

    # -- Mehrlaengenzuschlag (Naeherung) ------------------------------------
    # Rechtlich korrekt ist der Zuschlag von der GEBAEUDElaenge abhaengig,
    # die aber erst aus dem fertigen Baukoerper folgt (Zirkelbezug). Als
    # transparente Naeherung wird hier die Laenge der jeweiligen
    # PARZELLENKANTE als Proxy verwendet -- explizit dokumentiert, nicht
    # stillschweigend uebernommen.
    effektive_abstaende = list(kanten_abstaende)
    if mehrlaengenzuschlag_schwelle_m is not None and mehrlaengenzuschlag_zuschlag_pro_m is not None:
        for i in range(n):
            p1, p2 = ring[i], ring[(i + 1) % n]
            kantenlaenge = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            basis = kanten_abstaende[i] or 0.0
            if kantenlaenge > mehrlaengenzuschlag_schwelle_m and basis > 0:
                zuschlag = (kantenlaenge - mehrlaengenzuschlag_schwelle_m) * mehrlaengenzuschlag_zuschlag_pro_m
                effektive_abstaende[i] = basis + zuschlag
                hinweise.append(
                    f"Mehrlaengenzuschlag Kante {i}: Parzellenkantenlaenge {kantenlaenge:.1f} m "
                    f"> Schwelle {mehrlaengenzuschlag_schwelle_m:.1f} m -> Grenzabstand von "
                    f"{basis:.2f} m auf {effektive_abstaende[i]:.2f} m erhoeht. Naeherung: nutzt "
                    "die Parzellenkantenlaenge als Proxy fuer die Gebaeudelaenge, da die "
                    "tatsaechliche Gebaeudelaenge erst aus dem Ergebnis dieser Kaskade folgen "
                    "wuerde (Zirkelbezug It. Spezifikation)."
                )

    # -- Baubereich (Halbebenen-Kaskade) ------------------------------------
    baubereich, kantenprotokoll = berechne_baubereich_polygon(ring, effektive_abstaende)
    baubereich_vor_restriktion_m2 = round(baubereich.area, 2) if not baubereich.is_empty else 0.0

    restriktion_union = None
    if restriktionsflaechen:
        baubereich, restriktion_union = _restriktionen_abziehen(baubereich, restriktionsflaechen)

    baubereich_m2 = round(baubereich.area, 2) if not baubereich.is_empty else 0.0
    if baubereich_m2 == 0.0:
        hinweise.append(
            "Baubereich ist nach Grenzabstaenden/Restriktionen leer -- Grenzabstaende und/oder "
            "Restriktionsflaechen erschoepfen die Parzelle vollstaendig."
        )

    parzelle_poly = Polygon(ring)
    if not parzelle_poly.is_valid:
        parzelle_poly = parzelle_poly.buffer(0)
    parzellenflaeche_m2 = round(parzelle_poly.area, 2)

    if restriktionsflaechen and restriktion_union is not None and not restriktionsflaechen_zaehlen_zur_landflaeche:
        anrechenbare_landflaeche_m2 = round(parzelle_poly.difference(restriktion_union).area, 2)
        hinweise.append(
            "Anrechenbare Landflaeche wurde um die Restriktionsflaechen reduziert (Annahme, "
            "ueberschreibbar via restriktionsflaechen_zaehlen_zur_landflaeche=True): in diesen "
            "Flaechen (z.B. Gewaesserraum/Wald) darf nicht gebaut werden, sie zaehlen deshalb "
            "hier nicht zur AZ-/BMZ-massgebenden Grundstuecksflaeche. Kantonale Praxis kann "
            "abweichen und ist nicht Teil dieses Geometrie-Kernels."
        )
    else:
        anrechenbare_landflaeche_m2 = parzellenflaeche_m2

    # -- Fussabdruck ---------------------------------------------------------
    fussabdruck_kandidaten = {"geometrie": baubereich_m2}
    if ueberbauungsziffer_uz is not None:
        fussabdruck_kandidaten["ueberbauungsziffer"] = round(ueberbauungsziffer_uz * anrechenbare_landflaeche_m2, 2)
    fussabdruck_limitiert_durch = min(fussabdruck_kandidaten, key=fussabdruck_kandidaten.get)
    fussabdruck_m2 = fussabdruck_kandidaten[fussabdruck_limitiert_durch]

    # -- Geschosszahl ---------------------------------------------------------
    geschosszahl_kandidaten: dict = {}
    if vollgeschosse_max is not None:
        geschosszahl_kandidaten["vollgeschosse"] = vollgeschosse_max
    if gebaeudehoehe_m is not None:
        geschosszahl_kandidaten["hoehe"] = math.floor(gebaeudehoehe_m / geschosshoehe_m + 1e-9)

    geschosszahl: Optional[int]
    geschosszahl_limitiert_durch: Optional[str]
    if geschosszahl_kandidaten:
        geschosszahl_limitiert_durch = min(geschosszahl_kandidaten, key=geschosszahl_kandidaten.get)
        geschosszahl = geschosszahl_kandidaten[geschosszahl_limitiert_durch]
        werte = set(geschosszahl_kandidaten.values())
        if len(geschosszahl_kandidaten) > 1 and len(werte) == 1:
            geschosszahl_limitiert_durch = "vollgeschosse_und_hoehe_gleich"
    else:
        geschosszahl = None
        geschosszahl_limitiert_durch = None
        hinweise.append("Weder vollgeschosse_max noch gebaeudehoehe_m angegeben -- Geschosszahl unbestimmt.")

    # -- Geschossflaeche + Gegenkontrolle -------------------------------------
    geschossflaeche_aus_geometrie_m2 = (
        round(fussabdruck_m2 * geschosszahl, 2) if geschosszahl is not None else None
    )

    ziffern_kandidaten: dict = {}
    if geschossflaeche_aus_geometrie_m2 is not None:
        ziffern_kandidaten["fussabdruck_x_geschosse"] = geschossflaeche_aus_geometrie_m2
    if ausnuetzungsziffer_az is not None:
        ziffern_kandidaten["ausnuetzung_az"] = round(ausnuetzungsziffer_az * anrechenbare_landflaeche_m2, 2)
    if anrechenbare_geschossflaechenziffer_abgf is not None:
        ziffern_kandidaten["ausnuetzung_agfz"] = round(
            anrechenbare_geschossflaechenziffer_abgf * anrechenbare_landflaeche_m2, 2
        )
    if baumassenziffer_bmz is not None:
        ziffern_kandidaten["baumasse"] = round(
            baumassenziffer_bmz * anrechenbare_landflaeche_m2 / geschosshoehe_m, 2
        )
        hinweise.append(
            f"BMZ-Deckel in Geschossflaeche umgerechnet ueber Annahme Geschosshoehe={geschosshoehe_m} m "
            "(BMZ ist eigentlich ein Volumenmass m3/m2, keine direkte Flaeche)."
        )

    if ziffern_kandidaten:
        geschossflaeche_limitiert_durch = min(ziffern_kandidaten, key=ziffern_kandidaten.get)
        geschossflaeche_m2 = ziffern_kandidaten[geschossflaeche_limitiert_durch]
    else:
        geschossflaeche_limitiert_durch = None
        geschossflaeche_m2 = None
        hinweise.append(
            "Keine Nutzungsziffer (AZ/aGFZ/BMZ) und keine bestimmbare Geschosszahl vorhanden -- "
            "Geschossflaeche unbestimmt."
        )

    return PotenzialErgebnis(
        baubereich_koordinaten=_geometrie_zu_koordinaten(baubereich),
        baubereich_vor_restriktion_m2=baubereich_vor_restriktion_m2,
        baubereich_m2=baubereich_m2,
        parzellenflaeche_m2=parzellenflaeche_m2,
        anrechenbare_landflaeche_m2=anrechenbare_landflaeche_m2,
        fussabdruck_m2=fussabdruck_m2,
        fussabdruck_limitiert_durch=fussabdruck_limitiert_durch,
        fussabdruck_kandidaten=fussabdruck_kandidaten,
        geschosszahl=geschosszahl,
        geschosszahl_limitiert_durch=geschosszahl_limitiert_durch,
        geschosszahl_kandidaten=geschosszahl_kandidaten,
        geschossflaeche_aus_geometrie_m2=geschossflaeche_aus_geometrie_m2,
        geschossflaeche_m2=geschossflaeche_m2,
        geschossflaeche_limitiert_durch=geschossflaeche_limitiert_durch,
        geschossflaeche_kandidaten=ziffern_kandidaten,
        kantenprotokoll=kantenprotokoll,
        effektive_kanten_abstaende=effektive_abstaende,
        hinweise=hinweise,
    )

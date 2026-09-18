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

Wie der Baubereich definiert ist
--------------------------------
Ein Grenzabstand ist eine ABSTANDSBEDINGUNG, keine Konstruktionsvorschrift:

    Der Baubereich ist die Menge aller Punkte der Parzelle, die von der
    Kante i mindestens kanten_abstaende[i] Meter entfernt sind -- und
    zwar fuer JEDE Kante i gleichzeitig.

Genau so wird hier gerechnet: je Kante die Menge der zu nahen Punkte (der
Puffer um die KANTENSTRECKE, nicht um ihre unendliche Gerade), diese
Mengen vereinigt, von der Parzelle abgezogen.

Drei Eigenschaften folgen unmittelbar aus dieser Definition, und alle drei
sind fachlich zwingend:

  * MONOTON. Ein groesserer Abstand kann den Baubereich nur verkleinern,
    nie vergroessern.
  * KOLLABIERT SAUBER. Erschoepfen die Abstaende die Parzelle, ist das
    Ergebnis leer -- und nicht eine Restflaeche mit positivem Inhalt.
  * KORREKT FUER KONKAVE PARZELLEN. Gepuffert wird die Strecke, nicht die
    Gerade; eine weit entfernte Kante schneidet deshalb nichts ab, was
    gar nicht zu ihr gehoert.

Warum nicht `polygon.buffer(-d)`: der kennt nur EINEN einheitlichen
Abstand und bildet kantenspezifische Grenzabstaende (Strassenseite anders
als Nachbarseite) nicht ab. Fuer den Sonderfall gleicher Abstaende auf
allen Kanten ist das Ergebnis hier mit `buffer(-d)` identisch -- das
prueft tests/test_baubereich.py als unabhaengige Gegenrechnung.

Historie -- zwei Verfahren, die beide falsch waren
---------------------------------------------------
1. Sequenzieller HALBEBENEN-SCHNITT ueber die volle Polygonflaeche. Fuer
   konvexe Polygone richtig, fuer konkave falsch: die unendliche
   Stuetzgerade einer Kante schneidet auch weit entfernte, mit dieser
   Kante gar nicht benachbarte Teile ab (am L-Form-Testfall T2
   nachgewiesen: 36 m2 statt korrekt 156 m2).

2. MITRE-KONSTRUKTION: jede Kantengerade nach innen versetzen, jeden
   neuen Eckpunkt als Schnittpunkt der beiden benachbarten Versatzgeraden.
   Richtig, solange der versetzte Ring sich nicht selbst schneidet -- und
   genau das tut er, sobald ein Abstand den Innenradius der Parzelle
   ueberschreitet. Der Ring stuelpt sich um, `buffer(0)` reparierte die
   Selbstueberschneidung zu einem GUELTIGEN Polygon, und
   `intersection(parzelle)` liess davon eine Restflaeche mit positivem
   Inhalt uebrig. Gemessen an Buhofstrasse 20, Rheineck (Parzelle 693,
   299.5 m2, gleicher Abstand auf allen vier Kanten):

       4 m -> 58.52 m2      7 m -> 38.21 m2   <-- waechst wieder
       5 m -> 18.28 m2      8 m -> 54.45 m2
       6 m -> 13.97 m2     10 m -> 62.94 m2

   Der Baubereich wuchs also, je weiter man vom Rand wegrueckte. Daher
   auch die beiden sichtbaren Folgefehler: die "0.7 m2" an Buhofstrasse 55
   waren der Ausklang eines Kollapses, und an Buhofstrasse 20 lag die
   gemeldete Untergrenze (78.95 m2) ueber der Obergrenze (61.63 m2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

Koordinate = tuple[float, float]
Ring = list[Koordinate]

# Aufloesung der Rundung an den Enden eines Kantenpuffers (Viertelkreis-
# Segmente). Die Rundungen liegen fast immer ausserhalb der Parzelle und
# wirken sich kaum aus; 32 statt der shapely-Vorgabe 8 haelt den Fehler
# auch dort im Millimeterbereich, wo sie hineinragen.
_PUFFER_SEGMENTE = 32


def _schliesse_ring_nicht(ring: Ring) -> Ring:
    r = list(ring)
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]
    return r


def berechne_baubereich_polygon(
    parzelle_koordinaten: Ring, kanten_abstaende: list[float]
) -> tuple[Polygon, list[dict]]:
    """Baubereich = alle Punkte der Parzelle, die von JEDER Kante mindestens
    deren Grenzabstand entfernt sind (siehe Modul-Docstring).

    `kanten_abstaende[i]` ist der Grenzabstand (in Metern) fuer die Kante von
    `parzelle_koordinaten[i]` nach `parzelle_koordinaten[(i+1) % n]`. Ein Wert
    von 0 oder None laesst diese Kante ohne Einschraenkung. Muss genau einen
    Wert pro Kante enthalten (die Zuordnung, welche Kante Strassen-/Nachbar-/
    Grenzabstand bekommt, ist Aufgabe des Aufrufers -- reine Geometrie kennt
    diese Unterscheidung nicht).
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

    sperrflaechen = []
    kanten_info = []
    for i in range(n):
        p1, p2 = ring[i], ring[(i + 1) % n]
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) == 0:
            raise ValueError(f"Entartete Kante (Laenge 0) im Parzellenpolygon bei {p1}.")
        distanz = kanten_abstaende[i] or 0.0
        kanten_info.append({"p1": p1, "p2": p2, "distanz": distanz})
        if distanz > 0:
            # Der Puffer um die STRECKE, nicht um ihre Gerade: das ist genau
            # die Menge der Punkte, die dieser Kante zu nah sind. Eine weit
            # entfernte Kante schneidet so nichts ab, was nicht zu ihr gehoert
            # -- der Grund, warum konkave Parzellen hier korrekt erodieren.
            sperrflaechen.append(
                LineString([p1, p2]).buffer(distanz, quad_segs=_PUFFER_SEGMENTE)
            )

    if sperrflaechen:
        baubereich = parzelle.difference(unary_union(sperrflaechen))
    else:
        baubereich = parzelle

    # difference() liefert bei erschoepfenden Abstaenden eine leere Geometrie
    # -- und genau das ist richtig. Es gibt hier bewusst KEINE Reparatur, die
    # aus einem Kollaps wieder eine Flaeche macht.
    if baubereich.is_empty:
        baubereich = Polygon()

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


def vergleiche_bestand_mit_baubereich(
    bestand_ringe: Optional[list],
    baubereich_ringe: Optional[list],
) -> Optional[dict]:
    """Wie viel des bestehenden Gebaeudes liegt im heutigen Baubereich?

    Reine Geometrie, keine rechtliche Aussage. Die Frage, die damit
    beantwortbar wird: laesst sich der Bestand ueberhaupt mit den heute
    modellierten Abstaenden erklaeren? Liegt er zu grossen Teilen ausserhalb,
    ist er aelter als die geltende Ordnung -- was das rechtlich bedeutet
    (Bestandesschutz, altrechtliche Baute, Ausnahmebewilligung), sagt diese
    Funktion NICHT und darf sie nicht sagen.

    Liefert None, wenn eine der beiden Geometrien fehlt.
    """
    if not bestand_ringe or not baubereich_ringe:
        return None

    def flaechen(ringe):
        teile = []
        for ring in ringe:
            if not ring or len(ring) < 3:
                continue
            p = Polygon(ring)
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty and p.area > 0:
                teile.append(p)
        return unary_union(teile) if teile else None

    bestand = flaechen(bestand_ringe)
    baubereich = flaechen(baubereich_ringe)
    if bestand is None or baubereich is None or bestand.area <= 0:
        return None

    innen = bestand.intersection(baubereich).area
    return {
        "bestand_m2": round(bestand.area, 1),
        "im_baubereich_m2": round(innen, 1),
        "ausserhalb_m2": round(bestand.area - innen, 1),
        "anteil_ausserhalb": round((bestand.area - innen) / bestand.area, 3),
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

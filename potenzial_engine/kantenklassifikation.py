"""
G2 -- Kantenklassifikation: welche Parzellenkante grenzt woran?

G1 (`baubereich.py`) rechnet die Baubereich-Kaskade mit KANTENSPEZIFISCHEN
Grenzabstaenden -- genau dafuer wurde die Mitre-Konstruktion gebaut. Geliefert
wurde ihm bisher nur eine Bandbreite ("alle Kanten klein" gegen "alle Kanten
gross"), weil niemand automatisch wusste, welche Kante zur Strasse zeigt.
Dieses Modul schliesst diese Luecke.

Entscheidungsregel -- geometrischer Nachweis statt geratener Schwellenwert
-------------------------------------------------------------------------
Der naheliegende Weg ("Strasse, wenn eine Strassenachse innerhalb der
Toleranz liegt") ist NICHT belastbar: die `tolerance` von `_identify()` ist in
PIXELN angegeben, nicht in Metern -- bei mapExtent 2000 m auf 1000 px sind das
2 m je Pixel, `tolerance=8` also rund 16 m. Damit wuerde jeder Nachbargarten
zur Strasse.

Stattdessen entscheidet ein Schnitt-Test, der keinen Schwellenwert braucht:

  | hinter der Kante            | Strassenachse durch dieses Polygon? | Art             |
  |-----------------------------|-------------------------------------|-----------------|
  | fremdes Katasterpolygon     | ja                                  | strasse         |
  | fremdes Katasterpolygon     | nein                                | nachbarparzelle |
  | kein Katasterpolygon        | Achse in Naehe (s.u.)               | strasse         |
  | kein Katasterpolygon        | keine Achse                         | unbestimmt      |

Damit ist zugleich die Verfeinerung erledigt, die die Machbarkeitspruefung
offen liess: STRASSENPARZELLEN SIND ECHTE PARZELLEN und erschienen sonst als
Nachbar.

Der einzige verbleibende Meterwert ist `_ACHSE_MAX_ABSTAND_M` fuer den Fall
"gar kein Katasterpolygon hinter der Kante" (nicht parzellierter Strassenraum).
Er ist bewusst klein gehalten und wird in der Begruendung jeder betroffenen
Kante mit dem tatsaechlich gemessenen Abstand ausgewiesen, damit die Zuordnung
nachpruefbar bleibt statt zu verschwinden.

Wald und Gewaesser bekommen hier BEWUSST keine eigene Kantenart:
`restriktionsgeometrie.py` liefert Waldabstand und Gewaesserraum bereits als
FLAECHEN, die G1 abzieht. Eine zweite, davon unabhaengige Kantenaussage waere
eine Parallelarchitektur mit Widerspruchsrisiko. Diese Klassifikation
beschraenkt sich auf genau die Unterscheidung, die den Abstandswert bestimmt:
Strasse gegen Nachbar.

Netzwerkzugriff: ja (geo.admin.ch MapServer identify), aber gebuendelt --
Strassenachsen und Katasterpolygone des Umfelds werden EINMAL geholt und
danach rein lokal gegen jede Kante geprueft. Die reine Entscheidungslogik
steht in `_klassifiziere_kante_lokal()` und ist ohne Netz testbar.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape

from .modul1_geodata import LAYER_CADASTRE_GEOM, _identify

LAYER_STRASSEN = "ch.swisstopo.swisstlm3d-strassen"

# Kanten unterhalb dieser Laenge praegen den Baubereich nicht (abgeschraegte
# Ecken, Vermessungsstuetzpunkte). Sie werden NICHT weggelassen, sondern als
# "nicht_relevant" gefuehrt -- eine verschwiegene Kante waere eine stille
# Annahme.
MIN_KANTENLAENGE_M = 3.0

# Wie weit ausserhalb der Kante geprueft wird. Gross genug, um nicht auf der
# Parzellengrenze selbst zu landen (Vermessungsungenauigkeit, Rundung der
# Katasterpolygone), klein genug, um nicht ueber ein schmales Nachbargrundstueck
# hinwegzuspringen.
_PROBE_ABSTAND_M = 2.0

# Nur fuer den Fall "hinter der Kante liegt ueberhaupt kein Katasterpolygon":
# dann ist der Strassenraum nicht parzelliert und es bleibt nur der Abstand zur
# Achse. Wird in der Begruendung mit dem gemessenen Wert ausgewiesen.
_ACHSE_MAX_ABSTAND_M = 6.0

# Wie weit das Umfeld einmalig geholt wird (Pixel, siehe Docstring oben:
# rund 2 m je Pixel). Bewusst grosszuegig -- hier ist Vollstaendigkeit des
# Umfelds gefragt, nicht Praezision; entschieden wird danach geometrisch.
_UMFELD_TOLERANZ_PX = 60

ART_STRASSE = "strasse"
ART_NACHBARPARZELLE = "nachbarparzelle"
ART_UNBESTIMMT = "unbestimmt"
ART_NICHT_RELEVANT = "nicht_relevant"


class KantenklassifikationError(Exception):
    """Fehler bei der Kantenklassifikation (fehlende Geometrie o.ae.)."""


# ---------------------------------------------------------------------------
# Geometrie-Hilfen (netzfrei)
# ---------------------------------------------------------------------------

def _ring_ohne_schluss(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    r = [(float(p[0]), float(p[1])) for p in ring]
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]
    return r


def _aussenpunkt(
    ring_offen: list[tuple[float, float]], i: int, abstand_m: float = _PROBE_ABSTAND_M
) -> tuple[float, float]:
    """Punkt `abstand_m` ausserhalb der Mitte von Kante i.

    Die Aussenrichtung wird real gegen das Polygon geprueft (nicht ueber die
    Ringorientierung CW/CCW, die bei Katasterdaten nicht garantiert ist, und
    nicht ueber den Schwerpunkt, der bei stark konkaven Parzellen ausserhalb
    liegen kann).
    """
    n = len(ring_offen)
    (x1, y1), (x2, y2) = ring_offen[i], ring_offen[(i + 1) % n]
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    laenge = math.hypot(dx, dy)
    if laenge == 0:
        raise KantenklassifikationError(f"Entartete Kante (Laenge 0) an Index {i}.")
    nx, ny = -dy / laenge, dx / laenge  # Normale

    polygon = Polygon(ring_offen)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    # Winziger Testschritt entscheidet, welche Normalenrichtung nach aussen zeigt.
    innen_test = Point(mx + nx * 0.01, my + ny * 0.01)
    if polygon.contains(innen_test):
        nx, ny = -nx, -ny
    return (mx + nx * abstand_m, my + ny * abstand_m)


def kantenlaengen(ring: list[tuple[float, float]]) -> list[float]:
    ring_offen = _ring_ohne_schluss(ring)
    n = len(ring_offen)
    return [
        math.hypot(ring_offen[(i + 1) % n][0] - ring_offen[i][0],
                   ring_offen[(i + 1) % n][1] - ring_offen[i][1])
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Umfelddaten (Netzzugriff, einmalig)
# ---------------------------------------------------------------------------

def _hole_strassenachsen(e: float, n: float) -> list[dict[str, Any]]:
    achsen = []
    for r in _identify(e, n, LAYER_STRASSEN, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True):
        geom = r.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:  # noqa: BLE001 -- fehlerhafte Einzelgeometrie darf den Lauf nicht stoppen
            continue
        if not isinstance(g, (LineString, MultiLineString)):
            continue
        attrs = r.get("properties") or r.get("attributes") or {}
        achsen.append({"geometrie": g, "strassenname": attrs.get("strassenname"), "objektart": attrs.get("objektart")})
    return achsen


def _hole_katasterpolygone(e: float, n: float, eigenes_egrid) -> list[dict[str, Any]]:
    # `eigenes_egrid` darf EIN EGRID oder eine Menge sein: bei einer
    # Parzellenkombination gehoeren zwei Parzellen zur eigenen Kontur, und
    # eine davon als "Nachbar" zu melden waere falsch.
    eigene = ({eigenes_egrid} if isinstance(eigenes_egrid, str)
              else set(eigenes_egrid or ()))
    eigen_punkt = Point(e, n)
    polygone = []
    for r in _identify(e, n, LAYER_CADASTRE_GEOM, tolerance=_UMFELD_TOLERANZ_PX, return_geometry=True):
        geom = r.get("geometry") or {}
        if geom.get("type") != "Polygon" or not geom.get("coordinates"):
            continue
        try:
            p = Polygon([(c[0], c[1]) for c in geom["coordinates"][0]])
        except Exception:  # noqa: BLE001
            continue
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        attrs = r.get("properties") or r.get("attributes") or {}
        egrid = attrs.get("egris_egrid")
        # Die eigene Parzelle raus: bevorzugt ueber das EGRID (eindeutig),
        # sonst ueber die Lage des Anfragepunkts.
        ist_eigen = (egrid in eigene) if (egrid and eigene) else p.contains(eigen_punkt)
        if ist_eigen:
            continue
        polygone.append({"geometrie": p, "nummer": attrs.get("number"), "egrid": egrid})
    return polygone


def _markiere_strassenparzellen(
    polygone: list[dict[str, Any]], achsen: list[dict[str, Any]]
) -> None:
    """Setzt je Polygon, ob eine Strassenachse hindurchfuehrt -- der Test, der
    Strassenparzellen von echten Nachbarn trennt."""
    for p in polygone:
        p["ist_strassenparzelle"] = False
        p["strassenname"] = None
        p["strassen_objektart"] = None
        for achse in achsen:
            if p["geometrie"].intersects(achse["geometrie"]):
                p["ist_strassenparzelle"] = True
                p["strassenname"] = achse.get("strassenname")
                # Die Objektart ist der Anknuepfungspunkt fuer kantonale
                # Regeln, die den Strassenabstand nach Strassenklasse
                # staffeln (z.B. AG: Kantonsstrasse 6 m, Gemeindestrasse
                # 4 m). Hier nur festgehalten, noch nicht ausgewertet.
                p["strassen_objektart"] = achse.get("objektart")
                break


# ---------------------------------------------------------------------------
# Entscheidungslogik (netzfrei -- hier liegt die eigentliche Regel)
# ---------------------------------------------------------------------------

def _klassifiziere_kante_lokal(
    aussen: tuple[float, float],
    polygone: list[dict[str, Any]],
    achsen: list[dict[str, Any]],
) -> dict[str, Any]:
    """Entscheidet fuer EINEN Aussenpunkt, was dort liegt.

    Rein lokal: bekommt die bereits geholten Umfelddaten uebergeben und greift
    selbst nicht aufs Netz zu -- damit vollstaendig offline testbar.
    """
    punkt = Point(*aussen)

    treffer = next((p for p in polygone if p["geometrie"].contains(punkt)), None)
    if treffer is not None:
        bezeichnung = f"Parzelle {treffer['nummer']}" if treffer.get("nummer") else "Nachbarparzelle"
        if treffer.get("egrid"):
            bezeichnung += f" ({treffer['egrid']})"
        if treffer.get("ist_strassenparzelle"):
            strasse = treffer.get("strassenname") or "ohne Namen"
            return {
                "art": ART_STRASSE,
                "begruendung": (
                    f"{bezeichnung} liegt hinter der Kante und wird von der Strassenachse "
                    f"'{strasse}' durchquert -- Strassenparzelle."
                ),
                "nachbar_egrid": treffer.get("egrid"),
                "nachbar_nummer": treffer.get("nummer"),
                "strassenname": treffer.get("strassenname"),
                "strassen_objektart": treffer.get("strassen_objektart"),
                "abstand_zur_achse_m": None,
            }
        return {
            "art": ART_NACHBARPARZELLE,
            "begruendung": (
                f"{bezeichnung} liegt hinter der Kante; keine Strassenachse verlaeuft durch "
                "dieses Polygon."
            ),
            "nachbar_egrid": treffer.get("egrid"),
            "nachbar_nummer": treffer.get("nummer"),
            "strassenname": None,
            "strassen_objektart": None,
            "abstand_zur_achse_m": None,
        }

    # Kein Katasterpolygon hinter der Kante -- in vielen Gemeinden ist der
    # Strassenraum nicht parzelliert. Nur hier zaehlt der Abstand zur Achse.
    naechste, naechster_abstand = None, None
    for achse in achsen:
        d = achse["geometrie"].distance(punkt)
        if naechster_abstand is None or d < naechster_abstand:
            naechste, naechster_abstand = achse, d

    if naechste is not None and naechster_abstand is not None and naechster_abstand <= _ACHSE_MAX_ABSTAND_M:
        strasse = naechste.get("strassenname") or "ohne Namen"
        return {
            "art": ART_STRASSE,
            "begruendung": (
                f"Kein Katasterpolygon hinter der Kante (nicht parzellierter Strassenraum); "
                f"Achse '{strasse}' in {naechster_abstand:.1f} m "
                f"(Grenzwert {_ACHSE_MAX_ABSTAND_M:.0f} m)."
            ),
            "nachbar_egrid": None,
            "nachbar_nummer": None,
            "strassenname": naechste.get("strassenname"),
            "strassen_objektart": naechste.get("objektart"),
            "abstand_zur_achse_m": round(naechster_abstand, 1),
        }

    abstand_text = (
        f"naechste Achse {naechster_abstand:.1f} m entfernt (Grenzwert {_ACHSE_MAX_ABSTAND_M:.0f} m)"
        if naechster_abstand is not None
        else "keine Strassenachse im abgefragten Umfeld"
    )
    return {
        "art": ART_UNBESTIMMT,
        "begruendung": (
            f"Kein Katasterpolygon hinter der Kante und keine zuordenbare Strasse -- {abstand_text}. "
            "Nicht belastbar bestimmbar, manuelle Pruefung erforderlich."
        ),
        "nachbar_egrid": None,
        "nachbar_nummer": None,
        "strassenname": None,
        "strassen_objektart": None,
        "abstand_zur_achse_m": round(naechster_abstand, 1) if naechster_abstand is not None else None,
    }


# ---------------------------------------------------------------------------
# Oeffentliche Schnittstelle
# ---------------------------------------------------------------------------

def klassifiziere_kanten(
    parzelle_ring: list[tuple[float, float]],
    e: float,
    n: float,
    *,
    eigenes_egrid: Any = None,
    min_kantenlaenge_m: float = MIN_KANTENLAENGE_M,
) -> dict[str, Any]:
    """Klassifiziert jede Kante der Parzelle als Strasse/Nachbar/unbestimmt.

    `e`, `n` sind der Anfragepunkt innerhalb der Parzelle (LV95) -- er dient
    zugleich als Mittelpunkt der einmaligen Umfeldabfrage.

    Rueckgabe:
        {
          "kanten": [ {nr, laenge_m, relevant, art, begruendung,
                       nachbar_egrid, nachbar_nummer, strassenname,
                       abstand_zur_achse_m, aussenpunkt_lv95}, ... ],
          "statistik": {...},
          "vollstaendig": bool,   # jede relevante Kante zugeordnet?
          "hinweise": [...],
          "quellen_layer": [...],
          "abgerufen_am": "YYYY-MM-DD",
        }
    """
    if not parzelle_ring:
        raise KantenklassifikationError("Keine Parzellengeometrie uebergeben -- Kanten nicht bestimmbar.")

    ring_offen = _ring_ohne_schluss(parzelle_ring)
    if len(ring_offen) < 3:
        raise KantenklassifikationError(
            f"Parzellenpolygon hat nur {len(ring_offen)} Stuetzpunkte -- keine Flaeche."
        )

    achsen = _hole_strassenachsen(e, n)
    polygone = _hole_katasterpolygone(e, n, eigenes_egrid)
    _markiere_strassenparzellen(polygone, achsen)

    laengen = kantenlaengen(ring_offen)
    kanten: list[dict[str, Any]] = []
    for i, laenge in enumerate(laengen):
        if laenge < min_kantenlaenge_m:
            kanten.append({
                "nr": i,
                "laenge_m": round(laenge, 2),
                "relevant": False,
                "art": ART_NICHT_RELEVANT,
                "begruendung": (
                    f"Kante kuerzer als {min_kantenlaenge_m:g} m -- fuer den Baubereich nicht "
                    "praegend (abgeschraegte Ecke/Vermessungsstuetzpunkt). Nicht klassifiziert, "
                    "aber der Vollstaendigkeit halber ausgewiesen."
                ),
                "nachbar_egrid": None, "nachbar_nummer": None,
                "strassenname": None, "strassen_objektart": None,
                "abstand_zur_achse_m": None, "aussenpunkt_lv95": None,
            })
            continue

        aussen = _aussenpunkt(ring_offen, i)
        befund = _klassifiziere_kante_lokal(aussen, polygone, achsen)
        kanten.append({
            "nr": i,
            "laenge_m": round(laenge, 2),
            "relevant": True,
            **befund,
            "aussenpunkt_lv95": [round(aussen[0], 2), round(aussen[1], 2)],
        })

    relevante = [k for k in kanten if k["relevant"]]
    statistik = {
        "kanten_gesamt": len(kanten),
        "kanten_relevant": len(relevante),
        ART_STRASSE: sum(1 for k in relevante if k["art"] == ART_STRASSE),
        ART_NACHBARPARZELLE: sum(1 for k in relevante if k["art"] == ART_NACHBARPARZELLE),
        ART_UNBESTIMMT: sum(1 for k in relevante if k["art"] == ART_UNBESTIMMT),
        "strassenparzellen_im_umfeld": sum(1 for p in polygone if p.get("ist_strassenparzelle")),
        "katasterpolygone_im_umfeld": len(polygone),
        "strassenachsen_im_umfeld": len(achsen),
    }

    hinweise: list[str] = []
    if not relevante:
        hinweise.append(
            f"Keine Kante erreicht {min_kantenlaenge_m:g} m -- die Parzellengeometrie ist fuer eine "
            "Kantenklassifikation zu kleinteilig."
        )
    if statistik[ART_UNBESTIMMT]:
        hinweise.append(
            f"{statistik[ART_UNBESTIMMT]} von {len(relevante)} massgebenden Kanten sind nicht "
            "belastbar zuordenbar -- fuer diese Kanten bleibt der Abstand offen "
            "(manuelle Pruefung erforderlich)."
        )
    if not achsen:
        hinweise.append(
            f"Layer {LAYER_STRASSEN} lieferte im Umfeld keine Strassenachse -- "
            "Strassenkanten sind damit nicht nachweisbar."
        )

    return {
        "kanten": kanten,
        "statistik": statistik,
        "vollstaendig": bool(relevante) and statistik[ART_UNBESTIMMT] == 0,
        "hinweise": hinweise,
        "quellen_layer": [LAYER_CADASTRE_GEOM, LAYER_STRASSEN],
        "abgerufen_am": datetime.now().date().isoformat(),
    }


def quellen_fuer_kanten(klassifikation: dict[str, Any]) -> list[Any]:
    """Ein Quellenobjekt je klassifizierter Kante -- damit die Zuordnung
    denselben Nachweisweg nimmt wie jeder andere Wert der Engine.

    Import lokal, weil `quellen.py` seinerseits aus `modul1_geodata` liest und
    ein Modulzyklus sonst schwer zu ueberblicken waere.
    """
    from .quellen import QUELLE_TYP_AMTLICH, Quellenobjekt

    abgerufen = klassifikation.get("abgerufen_am")
    quellen = []
    for kante in klassifikation.get("kanten", []):
        if not kante.get("relevant"):
            continue
        if kante["art"] == ART_STRASSE:
            bezeichnung = (
                f"Kantenzuordnung Strasse (Layer {LAYER_STRASSEN} + {LAYER_CADASTRE_GEOM}, "
                "geometrischer Schnitt-Test)"
            )
        elif kante["art"] == ART_NACHBARPARZELLE:
            bezeichnung = (
                f"Kantenzuordnung Nachbarparzelle (Layer {LAYER_CADASTRE_GEOM}, "
                "Punkt-in-Polygon ausserhalb der Kante)"
            )
        else:
            bezeichnung = (
                f"Kantenzuordnung nicht bestimmbar (Layer {LAYER_CADASTRE_GEOM} + "
                f"{LAYER_STRASSEN} ohne eindeutigen Befund)"
            )
        quellen.append(Quellenobjekt(
            feld=f"kante_{kante['nr']}_art",
            wert=kante["art"],
            quelle_typ=QUELLE_TYP_AMTLICH,
            quelle_bezeichnung=bezeichnung,
            zitat=kante.get("begruendung"),
            confidence="hoch" if kante["art"] != ART_UNBESTIMMT else "nicht_bestimmbar",
            abgerufen_am=abgerufen,
        ))
    return quellen

"""Screening: interessante Parzellen in einem Gebiet finden.

Der Sprung von "ein Grundstueck pruefen" zu "Grundstuecke finden". Dieses
Modul RECHNET NICHTS NEU und beschafft NICHTS -- es ist reine Auswertung
ueber Daten, die der Aufrufer bereits geholt hat (Pipeline), und es benutzt
dieselben Kennzahlen und dieselbe Zonenzuordnung wie die Einzelanalyse.

Screening ist ein Filter, kein Lead-Score
------------------------------------------
Es gibt hier keine Punktzahl, keine Gewichtung und keine Aussage darueber,
ob jemand verkaufen will -- dafuer gibt es keine Daten, und eine Zahl
daraus waere eine Behauptung. Sortiert wird nach einer GERECHNETEN Groesse:
der Ausnutzungsreserve in Quadratmetern Geschossflaeche.

    Reserve = zulaessige Geschossflaeche - bestehende Geschossflaeche

Beide Summanden stammen aus amtlichen Daten: die zulaessige aus der
Ausnuetzungsziffer der Zone (Modul 2, einmal je Gemeinde) mal der
Parzellenflaeche, die bestehende aus dem Gebaeude- und Wohnungsregister.

Die Einstufung ist deshalb bewusst strukturell und ohne erfundene Schwellen:

    unbebaut        im GWR ist kein Gebaeude auf dieser Parzelle verzeichnet
    unternutzt      Reserve > 0
    ausgeschoepft   Reserve <= 0
    nicht_bestimmbar  Ausnuetzungsziffer oder Bestand unbekannt

Wie gross die Reserve ist, sagt die Zahl daneben -- nicht eine Einteilung in
"gross" und "klein", die niemand begruenden koennte.

Was dieses Modul NICHT behauptet
---------------------------------
* Dass eine Parzelle verkaeuflich ist. Eigentuemerdaten sind nicht
  oeffentlich; das Screening sagt, wo Potenzial LIEGT, nicht wo es zu haben
  ist.
* Dass die Reserve baulich realisierbar ist. Dafuer braucht es Grenz-
  abstaende, Restriktionen und den Baubereich -- das ist Stufe 2 und 3.
* Dass ein fehlender GWR-Eintrag "unbebaut" bedeutet. Er bedeutet "nicht
  verzeichnet", und genau so steht es da.

Die drei Stufen
---------------
    Stufe 1   amtliche Flaechendaten, je Kachel drei Abfragen, danach lokal.
              Liefert Flaeche, Zone, Bestand und Reserve. Kein LLM.
    Stufe 2   die G1-Kaskade auf der echten Parzellenkontur (reine
              Arithmetik) fuer die Kandidaten aus Stufe 1.
    Stufe 3   die vollstaendige Einzelanalyse -- unveraendert die
              bestehende, auf Knopfdruck fuer einzelne Parzellen.

Die teure Reglementsauswertung (Modul 2, LLM) laeuft EINMAL JE GEMEINDE,
nicht je Parzelle: dieselbe Bau- und Nutzungsordnung gilt fuer alle
Parzellen darin. Das ist der Grund, warum ein Gebietsscreening ueberhaupt
bezahlbar ist.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from shapely.geometry import Polygon

__all__ = [
    "EINSTUFUNG_UNBEBAUT", "EINSTUFUNG_UNTERNUTZT", "EINSTUFUNG_AUSGESCHOEPFT",
    "EINSTUFUNG_NICHT_BESTIMMBAR", "GATE_KEINE_BAUZONE", "GATE_OEFFENTLICH",
    "MAX_TREFFER_JE_ABFRAGE", "kacheln", "polygon_aus_ring", "flaeche_m2",
    "bestand_je_parzelle", "zone_fuer_parzelle", "bewerte_parzelle", "sortiere",
]

# Der Identify-Dienst von geo.admin.ch liefert hoechstens so viele Treffer je
# Anfrage. Eine Kachel, die genau so viele zurueckgibt, ist mit hoher
# Wahrscheinlichkeit abgeschnitten -- dann wird sie geteilt statt stillschweigend
# unvollstaendig ausgewertet. Gemessen: eine Kachel mit 600 m Kante lieferte in
# Buchs AG genau 200 Parzellen, eine mit 300 m Kante 158.
MAX_TREFFER_JE_ABFRAGE = 200

# Kachelgroesse fuer Stufe 1. Klein genug, dass eine dichte Dorfkernkachel
# unter der Trefferobergrenze bleibt.
STANDARD_KACHEL_M = 300.0
MIN_KACHEL_M = 40.0

EINSTUFUNG_UNBEBAUT = "unbebaut"
EINSTUFUNG_UNTERNUTZT = "unternutzt"
EINSTUFUNG_AUSGESCHOEPFT = "ausgeschoepft"
EINSTUFUNG_NICHT_BESTIMMBAR = "nicht_bestimmbar"

GATE_KEINE_BAUZONE = "keine_bauzone"
GATE_OEFFENTLICH = "oeffentliche_nutzung"
GATE_KEINE_ZONE = "keine_zone_zugeordnet"
GATE_STRASSE = "strassenparzelle"

# Foederale MGDM-Hauptnutzungskategorien (Nutzungsplanung des Bundes).
# "1x" sind Bauzonen; 15 und 18 sind zwar Bauzonen, aber keine, in denen ein
# privater Entwickler baut.
_BAUZONE_PRAEFIX = "1"
_KATEGORIE_OEFFENTLICH = "15"     # Zone fuer oeffentliche Nutzungen
_KATEGORIE_VERKEHR = "18"         # Verkehrszone innerhalb der Bauzone


# ---------------------------------------------------------------------------
# Kacheln
# ---------------------------------------------------------------------------

def kacheln(
    bbox: tuple[float, float, float, float],
    kante_m: float = STANDARD_KACHEL_M,
) -> list[tuple[float, float, float, float]]:
    """Zerlegt ein Suchgebiet in Kacheln (LV95, xmin/ymin/xmax/ymax)."""
    xmin, ymin, xmax, ymax = bbox
    if xmax <= xmin or ymax <= ymin:
        return []
    kante_m = max(kante_m, MIN_KACHEL_M)
    ergebnis = []
    y = ymin
    while y < ymax:
        x = xmin
        while x < xmax:
            ergebnis.append((x, y, min(x + kante_m, xmax), min(y + kante_m, ymax)))
            x += kante_m
        y += kante_m
    return ergebnis


def teile_kachel(kachel: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]:
    """Viertelt eine Kachel -- fuer den Fall, dass sie an der Trefferobergrenze lag."""
    xmin, ymin, xmax, ymax = kachel
    if (xmax - xmin) <= MIN_KACHEL_M or (ymax - ymin) <= MIN_KACHEL_M:
        return []
    mx, my = (xmin + xmax) / 2, (ymin + ymax) / 2
    return [(xmin, ymin, mx, my), (mx, ymin, xmax, my),
            (xmin, my, mx, ymax), (mx, my, xmax, ymax)]


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------

def polygon_aus_ring(ring: Optional[Iterable]) -> Optional[Polygon]:
    if not ring:
        return None
    try:
        punkte = [(float(p[0]), float(p[1])) for p in ring]
    except (TypeError, ValueError, IndexError):
        return None
    if len(punkte) < 3:
        return None
    p = Polygon(punkte)
    if not p.is_valid:
        # Eine selbstueberschneidende Kontur repariert buffer(0) -- das
        # Ergebnis kann dabei in mehrere Teilflaechen zerfallen. Real
        # vorgekommen bei einer Parzelle aus der amtlichen Vermessung in
        # Buchs AG. Dann gilt die groesste Teilflaeche; ein MultiPolygon
        # hat keine Aussenkontur und haette alles Weitere abgebrochen.
        p = p.buffer(0)
        if p.geom_type == "MultiPolygon":
            teile = [t for t in p.geoms if t.area > 0]
            if not teile:
                return None
            p = max(teile, key=lambda t: t.area)
    if p.geom_type != "Polygon":
        return None
    return p if (not p.is_empty and p.area > 0) else None


def flaeche_m2(ring: Optional[Iterable]) -> Optional[float]:
    p = polygon_aus_ring(ring)
    return round(p.area, 1) if p else None


# ---------------------------------------------------------------------------
# Bestand aus dem GWR
# ---------------------------------------------------------------------------

# Wie weit ueber das Suchgebiet hinaus das Gebaeuderegister mitgelesen wird.
# Eine Parzelle am Kachelrand reicht regelmaessig darueber hinaus; ohne
# diesen Rand fehlten ihre Gebaeude, und sie erschiene als unbebaut. Real
# passiert: Parzelle 1967 in Buchs AG (7'481 m2) stand als Top-Treffer
# "unbebaut" in der Liste, obwohl dort seit 1989 ein Gebaeude mit 2'585 m2
# Grundflaeche steht -- es lag 4 m ausserhalb des abgefragten Rechtecks.
RAND_M = 150.0


def ordne_gebaeude_zu(
    gwr_eintraege: Iterable[dict[str, Any]],
    polygone: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Ordnet GWR-Gebaeude den Parzellen zu -- EGRID zuerst, dann Lage.

    Das GWR fuehrt den EGRID der Parzelle fast immer mit (im Testgebiet 581
    von 582 Gebaeuden). Fast immer ist aber nicht immer, und der eine
    Ausreisser landete ausgerechnet auf dem groessten Treffer der Liste.
    Fehlt der EGRID, entscheidet die Gebaeudekoordinate (gkode/gkodn) --
    dieselbe amtliche Quelle, nur ueber die Geometrie statt ueber den
    Schluessel.
    """
    je_parzelle: dict[str, list[dict[str, Any]]] = {}
    ohne_schluessel = []
    for eintrag in gwr_eintraege or []:
        egrid = (eintrag or {}).get("egrid")
        if egrid and egrid in polygone:
            je_parzelle.setdefault(egrid, []).append(eintrag)
        elif egrid:
            # EGRID vorhanden, aber die Parzelle nicht im Suchgebiet.
            continue
        else:
            ohne_schluessel.append(eintrag)

    if ohne_schluessel:
        from shapely.geometry import Point

        for eintrag in ohne_schluessel:
            x, y = eintrag.get("gkode"), eintrag.get("gkodn")
            if not x or not y:
                continue
            punkt = Point(float(x), float(y))
            for egrid, polygon in polygone.items():
                if polygon is not None and polygon.contains(punkt):
                    eintrag = dict(eintrag, egrid=egrid, zuordnung="ueber_lage")
                    je_parzelle.setdefault(egrid, []).append(eintrag)
                    break
    return je_parzelle


def bestand_je_parzelle(gwr_eintraege: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fasst die GWR-Gebaeude je Parzelle zusammen -- ueber den EGRID.

    Das GWR fuehrt den EGRID der Parzelle mit (in der Stichprobe Buchs AG:
    201 von 201 Gebaeuden). Die Zuordnung ist damit amtlich und braucht keine
    geometrische Verschneidung.

    Die bestehende Geschossflaeche wird als Grundflaeche x Geschosszahl
    genaehert. Das ist eine NAEHERUNG und wird als solche gefuehrt: das GWR
    kennt keine Geschossflaeche. Fehlt die Geschosszahl -- in derselben
    Stichprobe bei 79 von 201 Gebaeuden --, kann dieses Gebaeude nicht
    mitgerechnet werden. Die Summe ist dann UNVOLLSTAENDIG, die daraus
    abgeleitete Reserve entsprechend zu gross. Das wird ausgewiesen, nicht
    ueberspielt.
    """
    je_parzelle: dict[str, dict[str, Any]] = {}
    for eintrag in gwr_eintraege or []:
        egrid = (eintrag or {}).get("egrid")
        if not egrid:
            continue
        eintragung = je_parzelle.setdefault(egrid, {
            "gebaeude": 0, "grundflaeche_m2": 0.0, "bgf_m2": 0.0,
            "bgf_vollstaendig": True, "ohne_geschosszahl": 0,
            "baujahr_aeltestes": None, "baujahr_juengstes": None,
            "gebaeudekategorien": [], "adresse": None,
        })
        eintragung["gebaeude"] += 1
        flaeche = eintrag.get("garea")
        geschosse = eintrag.get("gastw")
        if flaeche:
            eintragung["grundflaeche_m2"] += float(flaeche)
        if flaeche and geschosse:
            eintragung["bgf_m2"] += float(flaeche) * float(geschosse)
        else:
            eintragung["bgf_vollstaendig"] = False
            eintragung["ohne_geschosszahl"] += 1
        baujahr = eintrag.get("gbauj")
        if baujahr:
            jahr = int(baujahr)
            alt, jung = eintragung["baujahr_aeltestes"], eintragung["baujahr_juengstes"]
            eintragung["baujahr_aeltestes"] = jahr if alt is None else min(alt, jahr)
            eintragung["baujahr_juengstes"] = jahr if jung is None else max(jung, jahr)
        # Die Adresse eines Gebaeudes ist der einzige Weg, diese Parzelle
        # spaeter in der vollstaendigen Einzelanalyse zu oeffnen -- die
        # laeuft ueber eine Adresse, nicht ueber eine Koordinate. Auf einer
        # unbebauten Parzelle gibt es keine, und dann steht das auch so da.
        if not eintragung["adresse"] and eintrag.get("strname_deinr"):
            plz = eintrag.get("dplz4") or eintrag.get("plz_plz6")
            ort = eintrag.get("ggdename") or eintrag.get("dplzname")
            eintragung["adresse"] = ", ".join(
                t for t in (eintrag["strname_deinr"],
                            " ".join(str(x) for x in (plz, ort) if x)) if t)
        kategorie = eintrag.get("gkat")
        if kategorie and kategorie not in eintragung["gebaeudekategorien"]:
            eintragung["gebaeudekategorien"].append(kategorie)

    for eintragung in je_parzelle.values():
        eintragung["grundflaeche_m2"] = round(eintragung["grundflaeche_m2"], 1)
        eintragung["bgf_m2"] = round(eintragung["bgf_m2"], 1)
    return je_parzelle


# ---------------------------------------------------------------------------
# Zone je Parzelle
# ---------------------------------------------------------------------------

def zone_fuer_parzelle(
    parzelle: Polygon,
    grundnutzungen: Iterable[dict[str, Any]],
    *,
    mehrdeutig_ab_anteil: float = 0.2,
) -> dict[str, Any]:
    """Welche Grundnutzung gilt fuer diese Parzelle?

    Entschieden wird ueber den groessten Flaechenanteil, nicht ueber einen
    Punkt: eine Parzelle an einer Zonengrenze wuerde sonst je nach Lage des
    Adresspunkts der einen oder der anderen Zone zugeschlagen. Deckt eine
    zweite Zone mehr als `mehrdeutig_ab_anteil` der Parzelle, gilt die
    Zuordnung als mehrdeutig -- dann ist nicht bestimmbar, welche Kennzahlen
    gelten, und das Screening sagt das, statt zu waehlen.
    """
    if parzelle is None or parzelle.area <= 0:
        return {"status": "keine_geometrie", "zone": None, "anteil": None}

    treffer: list[tuple[float, dict[str, Any]]] = []
    for festlegung in grundnutzungen or []:
        if not festlegung.get("ist_rechtskraeftig"):
            continue
        for ring in festlegung.get("geometrie_koordinaten") or []:
            zonenpolygon = polygon_aus_ring(ring)
            if zonenpolygon is None:
                continue
            try:
                ueberlappung = parzelle.intersection(zonenpolygon).area
            except Exception:  # noqa: BLE001 -- entartete Geometrie darf nichts stoppen
                continue
            if ueberlappung > 0:
                treffer.append((ueberlappung, festlegung))

    if not treffer:
        return {"status": "keine_grundnutzung_gefunden", "zone": None, "anteil": None}

    # Mehrere Teilflaechen derselben Zone zusammenzaehlen.
    summiert: dict[int, tuple[float, dict[str, Any]]] = {}
    for flaeche, festlegung in treffer:
        schluessel = id(festlegung)
        vorher = summiert.get(schluessel)
        summiert[schluessel] = ((vorher[0] if vorher else 0.0) + flaeche, festlegung)

    nach_flaeche: dict[str, tuple[float, dict[str, Any]]] = {}
    for flaeche, festlegung in summiert.values():
        name = (festlegung.get("typ_kommunal_bezeichnung")
                or festlegung.get("typ_kantonal_bezeichnung") or "?")
        vorher = nach_flaeche.get(name)
        nach_flaeche[name] = ((vorher[0] if vorher else 0.0) + flaeche, festlegung)

    sortiert = sorted(nach_flaeche.items(), key=lambda x: x[1][0], reverse=True)
    bester_name, (beste_flaeche, beste_zone) = sortiert[0]
    anteil = beste_flaeche / parzelle.area

    zweiter_anteil = (sortiert[1][1][0] / parzelle.area) if len(sortiert) > 1 else 0.0
    if zweiter_anteil > mehrdeutig_ab_anteil:
        return {
            "status": "mehrdeutig",
            "zone": None,
            "anteil": round(anteil, 3),
            "kandidaten": [{"bezeichnung": n, "anteil": round(f / parzelle.area, 3)}
                           for n, (f, _) in sortiert[:4]],
            "grund": (f"Die Parzelle liegt zu {anteil:.0%} in '{bester_name}' und zu "
                      f"{zweiter_anteil:.0%} in '{sortiert[1][0]}'. Welche Kennzahlen "
                      "gelten, ist ohne Aufteilung je Zonenanteil nicht bestimmbar."),
        }

    return {
        "status": "eindeutig",
        "zone": beste_zone,
        "bezeichnung": bester_name,
        "anteil": round(anteil, 3),
        "hauptnutzung_code": beste_zone.get("hauptnutzung_code"),
    }


def markiere_strassenparzellen(polygone: dict[str, Any], achsen: Iterable[Any]) -> set[str]:
    """Welche Parzellen sind Strassenparzellen? Eine Strassenachse fuehrt hindurch.

    Derselbe Test wie in der Kantenklassifikation -- dort trennt er echte
    Nachbarn von der Strasse, hier haelt er die Strasse aus der Trefferliste.

    Warum das Bauzonen-Gate das nicht erledigt: Zonenplaene legen die Bauzone
    regelmaessig ueber die Strassenflaeche mit. Real passiert: die
    Strassenparzelle 303 (Rosenweg, 3'345 m2) stand in der Gartenstadtzone
    und erschien mit 1'673 m2 "Reserve" auf Platz 2 der Liste. Derselbe
    Fehler wie bei der Parzellenkombination, nur an anderer Stelle.
    """
    achsen = list(achsen or [])
    if not achsen:
        return set()
    strassen = set()
    for egrid, polygon in polygone.items():
        if polygon is None:
            continue
        for achse in achsen:
            try:
                if polygon.intersects(achse):
                    strassen.add(egrid)
                    break
            except Exception:  # noqa: BLE001 -- entartete Geometrie stoppt nichts
                continue
    return strassen


def _kategorie(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    bereinigt = str(code).lstrip("Cc")
    return bereinigt[:2] if bereinigt[:2].isdigit() else None


def pruefe_bauzone(zone_info: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Gate: ist das ueberhaupt eine Bauzone, in der privat gebaut wird?

    Gibt None zurueck, wenn die Parzelle weitergeprueft werden soll, sonst
    den Ausschluss mit Grund. Die Kategorien stammen aus dem foederalen
    MGDM-Modell "Nutzungsplanung" -- nichts davon ist gesetzt.
    """
    if zone_info.get("status") != "eindeutig":
        return {"gate": GATE_KEINE_ZONE,
                "grund": zone_info.get("grund")
                         or "Keine eindeutige rechtskraeftige Grundnutzung zugeordnet."}
    kategorie = _kategorie(zone_info.get("hauptnutzung_code"))
    if kategorie is None:
        return {"gate": GATE_KEINE_ZONE,
                "grund": "Die Zone traegt keinen auswertbaren Hauptnutzungscode."}
    if not kategorie.startswith(_BAUZONE_PRAEFIX):
        return {"gate": GATE_KEINE_BAUZONE,
                "grund": (f"'{zone_info.get('bezeichnung')}' ist keine Bauzone "
                          f"(Hauptnutzungskategorie {kategorie}).")}
    if kategorie in (_KATEGORIE_OEFFENTLICH, _KATEGORIE_VERKEHR):
        return {"gate": GATE_OEFFENTLICH,
                "grund": (f"'{zone_info.get('bezeichnung')}' ist eine Bauzone fuer "
                          "oeffentliche Nutzungen oder Verkehr (Kategorie "
                          f"{kategorie}) -- keine Flaeche fuer eine private Entwicklung.")}
    return None


# ---------------------------------------------------------------------------
# Die Bewertung einer Parzelle
# ---------------------------------------------------------------------------

def bewerte_parzelle(
    parzelle: dict[str, Any],
    bestand: Optional[dict[str, Any]],
    zone_info: dict[str, Any],
    kennzahlen: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Eine Parzelle in Stufe 1 -- ohne Netzzugriff, ohne LLM.

    `kennzahlen` ist die aus Modul 2 zugeordnete Zonendefinition (dieselbe
    Struktur wie in der Einzelanalyse). Fehlt sie oder fehlt darin die
    Ausnuetzungsziffer, gibt es keine Reserve -- und keine erfundene.
    """
    flaeche = parzelle.get("flaeche_m2")
    eintrag: dict[str, Any] = {
        "egrid": parzelle.get("egrid"),
        "parzellennummer": parzelle.get("parzellennummer"),
        "gemeinde": parzelle.get("gemeinde"),
        "flaeche_m2": flaeche,
        "zone": zone_info.get("bezeichnung"),
        "zone_anteil": zone_info.get("anteil"),
        "zone_status": zone_info.get("status"),
        "bestand": bestand,
        "adresse": (bestand or {}).get("adresse"),
        "offene_punkte": [],
        "datenqualitaet": {},
    }

    # Eine Strassenachse allein macht noch keine Strassenparzelle: eine
    # Zufahrt kann quer ueber ein grosses privates Grundstueck fuehren. Real
    # passiert: Parzelle 1967 in Buchs AG (7'481 m2, Gebaeude von 1966) fiel
    # dadurch aus der Liste. Wo ein Gebaeude im Register steht, ist die
    # Flaeche keine oeffentliche Verkehrsflaeche -- die Achse ist dann eine
    # Zufahrt.
    #
    # Und der Rest wird nicht behauptet, sondern zur Pruefung gestellt: die
    # TLM3D-Strassenarten sind Zahlencodes, deren Bedeutung hier nicht
    # nachgeschlagen ist. Statt sie zu raten, wird der Befund benannt.
    if parzelle.get("ist_strassenparzelle") and not bestand:
        eintrag.update(
            einstufung=EINSTUFUNG_NICHT_BESTIMMBAR, ausgeschieden=GATE_STRASSE,
            reserve_bgf_m2=None,
            grund=("Durch diese Parzelle fuehrt eine Strassenachse, und im "
                   "Gebaeuderegister steht kein Gebaeude darauf. Das spricht fuer "
                   "oeffentliche Verkehrsflaeche -- auch wenn der Zonenplan die "
                   "Bauzone darueberlegt."))
        eintrag["offene_punkte"].append(
            "Im Katasterplan pruefen, ob es sich um Strassenflaeche oder um ein "
            "Baugrundstueck mit Zufahrt handelt.")
        return eintrag

    gate = pruefe_bauzone(zone_info)
    if gate:
        eintrag.update(einstufung=EINSTUFUNG_NICHT_BESTIMMBAR,
                       ausgeschieden=gate["gate"], grund=gate["grund"],
                       reserve_bgf_m2=None)
        return eintrag

    az = _ziffer(kennzahlen, "ausnuetzungsziffer_az")
    if az is None:
        az = _ziffer(kennzahlen, "anrechenbare_geschossflaechenziffer_abgf")
    eintrag["ausnuetzungsziffer"] = az

    if not flaeche:
        eintrag.update(einstufung=EINSTUFUNG_NICHT_BESTIMMBAR, reserve_bgf_m2=None,
                       grund="Keine Parzellenflaeche aus der amtlichen Vermessung.")
        return eintrag
    if az is None:
        eintrag.update(
            einstufung=EINSTUFUNG_NICHT_BESTIMMBAR, reserve_bgf_m2=None,
            grund=("Fuer diese Zone ist keine Ausnuetzungsziffer bekannt. Ohne sie "
                   "laesst sich die zulaessige Geschossflaeche nicht bestimmen -- "
                   "und damit keine Reserve."))
        eintrag["offene_punkte"].append(
            "Ausnuetzungsziffer der Zone aus der Bau- und Nutzungsordnung nachtragen.")
        return eintrag

    zulaessig = round(az * flaeche, 1)
    eintrag["zulaessige_bgf_m2"] = zulaessig
    eintrag["datenqualitaet"]["zulaessige_bgf"] = (
        "Obergrenze: gerechnet auf der vollen Parzellenflaeche. Abzuege fuer "
        "Gewaesserraum, Waldabstand oder Baulinien sind erst in Stufe 2 bekannt."
    )

    if bestand is None and parzelle.get("am_rand"):
        # Am Rand des Suchgebiets kann ein Gebaeude schlicht ausserhalb des
        # abgefragten Bereichs liegen. "Kein Eintrag gefunden" heisst hier
        # nicht "unbebaut" -- das waere genau der Fehler, der Parzelle 1967
        # an die Spitze der Liste gebracht hat.
        eintrag.update(
            einstufung=EINSTUFUNG_NICHT_BESTIMMBAR, reserve_bgf_m2=None,
            grund=("Diese Parzelle reicht ueber das abgefragte Gebiet hinaus. Ob dort "
                   "Gebaeude stehen, ist damit nicht entschieden -- ein fehlender "
                   "Registereintrag ist hier kein Nachweis."))
        eintrag["offene_punkte"].append(
            "Suchgebiet erweitern oder diese Parzelle einzeln pruefen.")
        return eintrag

    if bestand is None:
        eintrag.update(
            einstufung=EINSTUFUNG_UNBEBAUT,
            bestehende_bgf_m2=0.0,
            reserve_bgf_m2=zulaessig,
            ausnutzungsgrad=0.0,
            grund=(f"Im Gebaeude- und Wohnungsregister ist auf dieser Parzelle kein "
                   f"Gebaeude verzeichnet. Die zulaessige Geschossflaeche von "
                   f"{zulaessig:,.0f} m2 ist damit vollstaendig unausgenutzt."),
        )
        eintrag["offene_punkte"].append(
            "'Nicht verzeichnet' ist nicht dasselbe wie 'unbebaut' -- vor Ort oder "
            "im Katasterplan bestaetigen.")
        return eintrag

    bestehend = bestand.get("bgf_m2")
    if parzelle.get("am_rand"):
        eintrag["datenqualitaet"]["randlage"] = (
            "Die Parzelle reicht ueber das abgefragte Gebiet hinaus -- dort koennten "
            "weitere Gebaeude stehen. Die Reserve ist deshalb eine Obergrenze."
        )
        eintrag["offene_punkte"].append(
            "Suchgebiet erweitern -- der Bestand dieser Parzelle ist moeglicherweise "
            "unvollstaendig erfasst.")
    if not bestand.get("bgf_vollstaendig"):
        eintrag["datenqualitaet"]["bestehende_bgf"] = (
            f"Unvollstaendig: fuer {bestand.get('ohne_geschosszahl')} von "
            f"{bestand.get('gebaeude')} Gebaeuden fuehrt das GWR keine Geschosszahl. "
            "Die bestehende Geschossflaeche ist deshalb zu klein und die Reserve "
            "entsprechend zu gross."
        )
        eintrag["offene_punkte"].append(
            "Geschosszahl der Bestandsbauten pruefen -- die Reserve ist eine Obergrenze.")
    else:
        eintrag["datenqualitaet"]["bestehende_bgf"] = (
            "Genaehert als Grundflaeche x Geschosszahl aus dem GWR -- das Register "
            "fuehrt keine Geschossflaeche."
        )

    reserve = round(zulaessig - bestehend, 1)
    grad = round(bestehend / zulaessig, 3) if zulaessig else None
    eintrag.update(bestehende_bgf_m2=bestehend, reserve_bgf_m2=reserve,
                   ausnutzungsgrad=grad)

    if reserve > 0:
        eintrag["einstufung"] = EINSTUFUNG_UNTERNUTZT
        eintrag["grund"] = (
            f"Zulaessig sind rund {zulaessig:,.0f} m2 Geschossflaeche, bestehend sind "
            f"rund {bestehend:,.0f} m2 -- eine Reserve von {reserve:,.0f} m2 "
            f"({1 - grad:.0%} der zulaessigen Flaeche)."
            + (f" Aeltester Bau von {bestand.get('baujahr_aeltestes')}."
               if bestand.get("baujahr_aeltestes") else "")
        )
    else:
        eintrag["einstufung"] = EINSTUFUNG_AUSGESCHOEPFT
        eintrag["grund"] = (
            f"Die zulaessige Geschossflaeche von rund {zulaessig:,.0f} m2 ist mit "
            f"rund {bestehend:,.0f} m2 bereits ausgeschoepft."
        )
    return eintrag


def _ziffer(kennzahlen: Optional[dict[str, Any]], feld: str) -> Optional[float]:
    """Liest eine Nutzungsziffer aus einer Modul-2-Zonendefinition.

    Die Kennzahlen liegen je nach Herkunft als blanke Zahl oder als Objekt mit
    'wert' vor -- beides wird gelesen, nichts wird geraten.
    """
    if not kennzahlen:
        return None
    wert = kennzahlen.get(feld)
    if isinstance(wert, dict):
        wert = wert.get("wert")
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return zahl if zahl > 0 else None


# ---------------------------------------------------------------------------
# Reihenfolge
# ---------------------------------------------------------------------------

_RANG = {
    EINSTUFUNG_UNBEBAUT: 0,
    EINSTUFUNG_UNTERNUTZT: 0,
    EINSTUFUNG_AUSGESCHOEPFT: 1,
    EINSTUFUNG_NICHT_BESTIMMBAR: 2,
}


def sortiere(eintraege: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sortiert nach der Reserve in Quadratmetern Geschossflaeche.

    Bewusst keine Punktzahl: die Reserve IST die Groesse, um die es geht, und
    sie ist gerechnet statt gewichtet. Parzellen ohne bestimmbare Reserve
    stehen hinten -- nicht, weil sie uninteressant waeren, sondern weil ueber
    sie nichts gesagt werden kann.
    """
    return sorted(
        eintraege,
        key=lambda e: (_RANG.get(e.get("einstufung"), 3), -(e.get("reserve_bgf_m2") or 0.0)),
    )

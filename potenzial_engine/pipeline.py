"""Oeffentliche Aufrufschnittstelle der Potenzial-Engine.

Diese Datei enthaelt KEINE neue Fachlogik. Sie ist die aus webapp.py gehobene
Orchestrierung (frueher _run_pipeline), die Modul 1 -> Modul 1b -> Modul 2 ->
Zonenzuordnung -> G1 -> SIA 416 -> Quellen verdrahtet. Jede einzelne
Berechnung passiert unveraendert in den Fachmodulen.

Zwei Einstiegspunkte, bewusst getrennt:

    analysiere_grundstueck(adresse)     baurechtliche Analyse, OHNE Preis
    berechne_wirtschaftlichkeit(...)    Residualwert, MIT Preis

Diese Trennung ist fachlich, nicht kosmetisch: welche Zone amtlich gilt und
was darauf gebaut werden darf, haengt nicht vom Verkaufspreis ab. Die
Wirtschaftlichkeit ist optional und darf die baurechtliche Analyse nie
voraussetzen oder blockieren.

Die Engine bleibt zustandslos -- sie fuehrt keine Datenbank und speichert
nichts. Wer Ergebnisse aufbewahren will (Analyse-Historie pro EGRID),
uebernimmt das ausserhalb.

Noch nicht unterstuetzt: Aufruf ueber EGRID statt Adresse. run_modul1()
geocodiert heute ausschliesslich Adressen; die EGRID-Aufloesung entsteht in
Phase 1 zusammen mit der gemeinsamen Datenschicht.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .entwicklungsszenarien import SZENARIO_ANFORDERUNGEN
from .g1_verdrahtung import G1VerdrahtungError, berechne_g1_fuer_fall
from .flaechenmodell import (
    HERKUNFT_SYSTEMANNAHME,
    PROFIL_WOHNUNGSBAU_MFH,
    WohnungstypVorgabe,
    berechne_flaechen_und_wohnungen,
)
from .hbu import bestimme_hbu as _bestimme_hbu
from .kantenklassifikation import quellen_fuer_kanten
from .szenarien import berechne_szenarien as _berechne_szenarien
from .wirtschaftlichkeit import Marktannahmen, berechne_alle as _berechne_wirtschaftlich
from .modul1_geodata import Modul1Error, run_modul1
from .modul2_bzo_analysis import analyze_from_oereb_result
from .modul3_financial import ermittle_zonenzuordnung, run_from_modul_results
from .quellen import quellen_aus_modul1_ergebnis
from .sia416_flaechen import berechne_sia416_kaskade

# Statisch, unabhaengig von der Adresse -- reine Taxonomie/Dokumentation aus
# entwicklungsszenarien.py (KEINE Berechnungslogik dort, siehe Modul). Einmal
# serialisiert, in jeder Antwort mitgegeben.
ENTWICKLUNGSSZENARIEN_INFO = [
    {
        "szenario": a.szenario.value,
        "beschreibung": a.beschreibung,
        "benoetigte_zusatzeingaben": a.benoetigte_zusatzeingaben,
        "benoetigte_flaechendaten": a.benoetigte_flaechendaten,
        "heute_bereits_abgedeckt_durch": a.heute_bereits_abgedeckt_durch,
    }
    for a in SZENARIO_ANFORDERUNGEN.values()
]

# Grosse Rohdaten-Blobs, die fuer die Anzeige nicht gebraucht werden und die
# Antwort unnoetig aufblaehen wuerden -- reine Darstellungs-Optimierung, die
# zugrunde liegenden Objekte bleiben unveraendert (sie stehen weiterhin
# vollstaendig im Kontext).
_TRIM_PATHS = (
    ("kataster", "raw_attributes"),
    ("gemeinde", "raw_attributes"),
    ("gwr", "raw_attributes"),
    ("geocoding", "raw"),
    ("oereb", "raw_extract"),
)


class PreisEingabeFehler(Modul1Error):
    """Preisangabe fehlt oder ist nicht in CHF/m2 umrechenbar.

    Erbt bewusst von Modul1Error: die Ursache ist eine fehlende Modul-1-
    Groesse (die amtliche Parzellenflaeche), und aufrufender Code hat diesen
    Fall bisher genau so behandelt -- frueher wurde an dieser Stelle direkt
    ein Modul1Error geworfen.
    """


@dataclass
class Analyse:
    """Ergebnis einer Grundstuecksanalyse.

    ergebnis: aufbereitet zur Weitergabe/Anzeige (Rohdaten-Blobs getrimmt).
    kontext:  die unveraenderten Modul-1-/Modul-2-Rohergebnisse. Sie werden
              gebraucht, um spaeter die Wirtschaftlichkeit zu rechnen, ohne
              Geodaten und LLM-Auswertung erneut zu durchlaufen (das kostet
              sonst 1-3 Minuten pro Aufruf). Bewusst getrennt vom Ergebnis,
              damit sie nicht versehentlich an ein Frontend gesendet werden.
    """

    ergebnis: dict[str, Any]
    kontext: dict[str, Any] = field(repr=False)


@dataclass
class Wirtschaftlichkeit:
    """Ergebnis der Residualwertrechnung (Modul 3).

    verwendeter_preis_chf_pro_m2 wird mitgeliefert, weil bei Eingabe eines
    Gesamtpreises erst hier feststeht, mit welchem Quadratmeterpreis
    tatsaechlich gerechnet wurde.
    """

    ergebnis: dict[str, Any]
    verwendeter_preis_chf_pro_m2: float


def _trimmed_modul1(modul1_result: dict) -> dict:
    trimmed = dict(modul1_result)
    for section, feld in _TRIM_PATHS:
        if section in trimmed and isinstance(trimmed[section], dict) and feld in trimmed[section]:
            trimmed[section] = {k: v for k, v in trimmed[section].items() if k != feld}
    return trimmed


def _sia416_fuer_geschossflaeche(geschossflaeche_m2: Optional[float]) -> Optional[dict]:
    """Ruft die SIA-416-Kaskade OHNE jede NF/GF- oder HNF/NF-Modellannahme auf
    -- es gibt aktuell keine echten Referenzprojekte (siehe
    referenzprojekte.REFERENZPROJEKTE, bewusst leer). GF wird dadurch korrekt
    als 'bestimmt' ausgewiesen (reale G1-Geometrie), NF/HNF/NNF korrekt als
    'nicht_bestimmbar' -- keine erfundene Zahl. Liefert None, wenn G1 selbst
    keine Geschossflaeche ermitteln konnte."""
    if geschossflaeche_m2 is None:
        return None
    return asdict(berechne_sia416_kaskade(geschossflaeche_gf_m2=geschossflaeche_m2))


def _sia416_fuer_g1_ergebnis(g1_ergebnis: Optional[dict]) -> Optional[dict]:
    if not g1_ergebnis:
        return None
    # Beide Bandbreiten-Modi: die fehlende Kantenzuordnung UND die nicht
    # zuordenbaren Nachbarabstaende liefern Szenarien statt eines Ergebnisses.
    if str(g1_ergebnis.get("modus") or "").startswith("bandbreite_"):
        ausgabe = {}
        for name, e in (g1_ergebnis.get("szenarien") or {}).items():
            sia416 = _sia416_fuer_geschossflaeche(e.get("geschossflaeche_m2"))
            if sia416 is not None:
                ausgabe[name] = sia416
        return ausgabe or None
    return _sia416_fuer_geschossflaeche((g1_ergebnis.get("ergebnis") or {}).get("geschossflaeche_m2"))


def _preis_pro_m2(
    modul1_result: dict,
    verkaufspreis_chf_pro_m2: Optional[float],
    verkaufspreis_total_chf: Optional[float],
) -> float:
    """Loest die beiden Preis-Eingabearten in EINEN CHF/m2-Wert auf.

    Der Gesamtpreis ist eine reine Praesentations-Umrechnung (Division durch
    die amtliche Parzellenflaeche) -- die Fachlogik (Modul 3) erhaelt
    unveraendert nur einen CHF/m2-Wert, wie seit jeher. Die Umrechnung ist
    erst moeglich, wenn die Parzellenflaeche aus Modul 1 vorliegt.
    """
    if verkaufspreis_chf_pro_m2 is not None:
        return verkaufspreis_chf_pro_m2
    if verkaufspreis_total_chf is None:
        raise PreisEingabeFehler("Verkaufspreis pro m2 oder Verkaufspreis total ist noetig.")
    flaeche = modul1_result.get("kataster", {}).get("flaeche_m2")
    if not flaeche:
        raise PreisEingabeFehler(
            "Verkaufspreis total kann nicht umgerechnet werden -- amtliche Parzellenflaeche "
            "unbekannt. Bitte stattdessen den Verkaufspreis pro m2 angeben."
        )
    return verkaufspreis_total_chf / flaeche


def _g1_einzelergebnis(g1_ergebnis: Optional[dict]) -> Optional[dict]:
    """Das eine G1-Ergebnis, auf dem die Flaechenkaskade aufsetzt.

    Im Bandbreiten-Modus gibt es kein einzelnes Ergebnis -- dann liefert diese
    Funktion `None`, und die Kaskade meldet das als nicht bestimmbar, statt
    sich stillschweigend einen der beiden Raender auszusuchen.
    """
    if not g1_ergebnis:
        return None
    return g1_ergebnis.get("ergebnis")


def _flaechen_fuer_g1_ergebnis(
    g1_ergebnis: Optional[dict],
    zonen_zuordnung: dict,
    *,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list] = None,
    wohnungsmix_begruendung: str = "",
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
) -> Optional[dict]:
    def rechne(g1_einzel: dict) -> dict:
        return berechne_flaechen_und_wohnungen(
            g1_einzel,
            zone=zonen_zuordnung.get("zone"),
            profil=profil,
            benutzerwerte=benutzerwerte,
            wohnungsmix=wohnungsmix,
            wohnungsmix_begruendung=wohnungsmix_begruendung,
        )

    einzel = _g1_einzelergebnis(g1_ergebnis)
    if einzel is not None:
        return rechne(einzel)

    szenarien = (g1_ergebnis or {}).get("szenarien") or {}
    if not szenarien:
        return None

    # Ist die Kantenzuordnung unvollstaendig, liefert G1 zwei Raender statt
    # eines Ergebnisses. Einen davon auszuwaehlen waere Willkuer -- beide
    # durchzurechnen und als Bandbreite auszuweisen ist die ehrliche Form.
    gerechnet = {name: rechne(erg) for name, erg in szenarien.items()}
    return {
        "status": "bandbreite",
        "grund": (
            "Die Kantenzuordnung ist unvollstaendig, deshalb liefert G1 zwei Raender "
            "statt eines Ergebnisses. Die Flaechenkaskade wurde fuer beide gerechnet; "
            "das reale Ergebnis liegt dazwischen. Siehe das Kantenprotokoll fuer die "
            "offenen Kanten."
        ),
        "szenarien": gerechnet,
        "spanne": {
            feld: sorted(
                w for w in (
                    ((e.get("flaechen") or {}).get(feld) or {}).get("wert") for e in gerechnet.values()
                ) if w is not None
            )
            for feld in ("geschossflaeche_gf", "nutzflaeche_nf", "hauptnutzflaeche_hnf", "wohnflaeche_nwf")
        },
        "wohnungen_spanne": sorted(
            n for n in ((e.get("wohnungen") or {}).get("anzahl_wohnungen") for e in gerechnet.values())
            if n is not None
        ),
    }


def _szenarien_fuer_analyse(
    g1_ergebnis: Optional[dict],
    zonen_zuordnung: dict,
    modul1_result: dict,
    **kwargs,
) -> dict:
    """Szenarien auf dem einzelnen G1-Ergebnis.

    Liegt nur eine Bandbreite vor, waeren Szenarien auf einem willkuerlich
    gewaehlten Rand nicht belastbar -- dann meldet berechne_szenarien() das
    selbst mit Grund.
    """
    return _berechne_szenarien(
        _g1_einzelergebnis(g1_ergebnis),
        modul1_result.get("bestand"),
        zonen_zuordnung.get("zone"),
        restriktionen=modul1_result.get("restriktionsgeometrie"),
        **kwargs,
    )


def berechne_szenarien(
    analyse: Analyse,
    *,
    auswahl: Optional[list[str]] = None,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list[WohnungstypVorgabe]] = None,
    wohnungsmix_begruendung: str = "",
    # Ob der Mix eine eigene Entscheidung ist oder die Vorbelegung der
    # Oberflaeche. Muss hier stehen, obwohl der innere Helfer **kwargs nimmt:
    # DIESE Signatur ist die Aussenkante, und was sie nicht kennt, scheitert
    # beim Aufruf, statt durchgereicht zu werden.
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
    attika_zulaessig: Optional[bool] = None,
    dachgeschoss_zulaessig: Optional[bool] = None,
    gebaeudeabstand_m: Optional[float] = None,
    restflaeche_verteilen: bool = False,
    # Tatsaechliche Wohnflaeche des Bestands fuer das Sanierungsszenario.
    bestand_flaeche_nwf_m2: Optional[float] = None,
) -> dict:
    """Rechnet die Entwicklungsszenarien neu -- ohne erneute Abfrage.

    Arbeitet auf einer bereits erstellten Analyse. Ein anderer Wohnungsmix,
    eine andere Annahme oder eine nachgetragene Attika-Regel kosten damit
    Millisekunden statt Minuten.
    """
    return _szenarien_fuer_analyse(
        analyse.ergebnis.get("g1_ergebnis"),
        analyse.ergebnis.get("zonen_zuordnung") or {},
        analyse.kontext.get("modul1") or {},
        auswahl=auswahl, benutzerwerte=benutzerwerte, wohnungsmix=wohnungsmix,
        wohnungsmix_begruendung=wohnungsmix_begruendung,
        wohnungsmix_herkunft=wohnungsmix_herkunft, profil=profil,
        attika_zulaessig=attika_zulaessig, dachgeschoss_zulaessig=dachgeschoss_zulaessig,
        gebaeudeabstand_m=gebaeudeabstand_m, restflaeche_verteilen=restflaeche_verteilen,
        bestand_flaeche_nwf_m2=bestand_flaeche_nwf_m2,
    )


def _kachel_daten(
    kachel: tuple[float, float, float, float],
    kanton: Optional[str],
) -> dict[str, Any]:
    """Die drei Abfragen je Kachel -- und nur diese drei.

    Kataster, Gebaeuderegister und Nutzungsplanung fuer ein ganzes Rechteck
    statt je Parzelle. Das ist der Unterschied zwischen einem Screening, das
    laeuft, und einem, das Stunden braucht.
    """
    from .modul1_geodata import (
        IDENTIFY_MAX_TREFFER,
        LAYER_CADASTRE_GEOM,
        LAYER_GWR,
        identify_rechteck,
    )
    from .modul1b_nutzungsklassifikation import _fetch_geodienste, _fetch_zh_wfs

    from .screening import RAND_M

    parzellen_roh = identify_rechteck(kachel, LAYER_CADASTRE_GEOM, return_geometry=True)
    # Das Gebaeuderegister mit Rand: eine Parzelle am Kachelrand reicht
    # darueber hinaus, und ohne diesen Rand fehlten ihre Gebaeude.
    xmin, ymin, xmax, ymax = kachel
    gwr_roh = identify_rechteck(
        (xmin - RAND_M, ymin - RAND_M, xmax + RAND_M, ymax + RAND_M),
        LAYER_GWR, limit=500)

    mitte_e, mitte_n = (xmin + xmax) / 2, (ymin + ymax) / 2
    radius = max(xmax - xmin, ymax - ymin) / 2 + RAND_M

    festlegungen: list[dict[str, Any]] = []
    zonen_fehler = None
    try:
        if (kanton or "").upper() == "ZH":
            festlegungen = _fetch_zh_wfs(mitte_e, mitte_n, radius)
        else:
            festlegungen = _fetch_geodienste(mitte_e, mitte_n, radius, kanton)
    except Exception as exc:  # noqa: BLE001 -- eine Kachel ohne Zonen stoppt nichts
        zonen_fehler = f"{type(exc).__name__}: {exc}"

    # Strassenachsen der Kachel -- derselbe Layer, den die Kantenklassifikation
    # benutzt, nur rechteckweise. Ohne ihn stehen Strassenparzellen mit
    # dreistelligen "Reserven" in der Trefferliste.
    achsen = []
    try:
        from shapely.geometry import shape

        from .kantenklassifikation import LAYER_STRASSEN

        for eintrag in identify_rechteck(
                (xmin - RAND_M, ymin - RAND_M, xmax + RAND_M, ymax + RAND_M),
                LAYER_STRASSEN, return_geometry=True, limit=500):
            geom = eintrag.get("geometry")
            if not geom:
                continue
            try:
                achsen.append(shape(geom))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001 -- ohne Achsen bleibt der Rest gueltig
        achsen = []
        zonen_fehler = zonen_fehler or f"Strassenachsen: {type(exc).__name__}: {exc}"

    return {
        "parzellen": parzellen_roh,
        "gwr": [(g.get("attributes") or {}) for g in gwr_roh],
        "grundnutzungen": [f for f in festlegungen if f.get("ebene") == "grundnutzung"],
        "strassenachsen": achsen,
        "abgeschnitten": len(parzellen_roh) >= IDENTIFY_MAX_TREFFER,
        "zonen_fehler": zonen_fehler,
    }


def screene_gebiet(
    bbox: tuple[float, float, float, float],
    *,
    kanton: Optional[str] = None,
    modul2_result: Optional[dict] = None,
    gemeinde: Optional[str] = None,
    max_kacheln: int = 40,
    min_flaeche_m2: Optional[float] = None,
) -> dict[str, Any]:
    """Stufe 1 des Screenings: alle Parzellen eines Gebiets, amtlich und lokal.

    Kein LLM, keine Einzelanalyse, keine neue Datenquelle -- dieselben Layer,
    die Modul 1 ohnehin abfragt, nur rechteckweise statt punktweise.

    `modul2_result` ist die Reglementsauswertung der Gemeinde. Sie gilt fuer
    ALLE Parzellen darin und wird deshalb genau einmal gebraucht, nicht je
    Parzelle -- das ist der Grund, warum ein Gebietsscreening bezahlbar ist.
    Fehlt sie, laeuft das Screening trotzdem: es liefert dann Flaeche, Zone
    und Bestand, aber keine Reserve, und sagt das auch.

    `min_flaeche_m2` filtert VOR der Bewertung -- rein technisch, um
    Restflaechen und Strassenparzellen aus der Liste zu halten. Es ist kein
    fachliches Kriterium und wird als gesetzter Filter ausgewiesen.
    """
    from .modul3_financial import match_zone
    from . import screening as scr

    offene_kacheln = list(scr.kacheln(bbox))
    bericht = {
        "bbox": list(bbox),
        "gemeinde": gemeinde,
        "kanton": kanton,
        "kacheln_geplant": len(offene_kacheln),
        "kacheln_gerechnet": 0,
        "kacheln_geteilt": 0,
        "abfragen": 0,
        "parzellen_gefunden": 0,
        "zonen_fehler": [],
    }
    if len(offene_kacheln) > max_kacheln:
        return {
            "status": "zu_gross",
            "grund": (f"Das Gebiet ergibt {len(offene_kacheln)} Kacheln, erlaubt sind "
                      f"{max_kacheln}. Ein kleineres Suchgebiet waehlen -- lieber zwei "
                      "Durchgaenge als ein Ergebnis, das nach einer Minute abbricht."),
            "bericht": bericht,
        }

    erkannte_zonen = (modul2_result or {}).get("erkannte_zonen") or []
    gesehen: dict[str, dict[str, Any]] = {}
    polygone: dict[str, Any] = {}
    gwr_gesamt: dict[Any, dict[str, Any]] = {}
    strassenachsen: list[Any] = []
    gemeinden_je_egrid: dict[str, Any] = {}
    zonen_cache: dict[str, Optional[dict[str, Any]]] = {}

    while offene_kacheln:
        kachel = offene_kacheln.pop(0)
        daten = _kachel_daten(kachel, kanton)
        bericht["kacheln_gerechnet"] += 1
        bericht["abfragen"] += 4
        strassenachsen.extend(daten.get("strassenachsen") or [])
        if daten["zonen_fehler"]:
            bericht["zonen_fehler"].append(daten["zonen_fehler"])

        if daten["abgeschnitten"]:
            teile = scr.teile_kachel(kachel)
            if teile:
                # Sonst fehlten Parzellen, ohne dass es jemand merkt.
                offene_kacheln.extend(teile)
                bericht["kacheln_geteilt"] += 1
                bericht["kacheln_geplant"] += len(teile)
                continue
            bericht.setdefault("warnungen", []).append(
                f"Kachel {kachel} liefert die Hoechstzahl an Treffern und laesst sich "
                "nicht weiter teilen -- dort koennen Parzellen fehlen.")

        for g in daten["gwr"]:
            kennung = g.get("egid")
            if kennung is not None:
                gwr_gesamt[kennung] = g
        gemeinden_je_egrid.update({g.get("egrid"): g.get("ggdename")
                                   for g in daten["gwr"] if g.get("egrid")})

        for roh in daten["parzellen"]:
            attribute = roh.get("properties") or roh.get("attributes") or {}
            egrid = attribute.get("egris_egrid")
            if not egrid or egrid in gesehen:
                continue
            ring = ((roh.get("geometry") or {}).get("coordinates") or [None])[0]
            polygon = scr.polygon_aus_ring(ring)
            flaeche = round(polygon.area, 1) if polygon else None
            if min_flaeche_m2 and (flaeche or 0) < min_flaeche_m2:
                continue

            zone_info = scr.zone_fuer_parzelle(polygon, daten["grundnutzungen"])
            polygone[egrid] = polygon

            # Die Zuordnung amtliche Zone -> Modul-2-Kennzahlen ist je
            # Zonenbezeichnung immer dieselbe -- einmal rechnen genuegt.
            kennzahlen = None
            if zone_info.get("status") == "eindeutig" and erkannte_zonen:
                name = zone_info.get("bezeichnung")
                if name not in zonen_cache:
                    treffer = match_zone(
                        [{"zonenbezeichnung": name, "ist_wahrscheinlich_basiszone": True}],
                        erkannte_zonen)
                    zonen_cache[name] = (treffer.get("zone")
                                         if treffer.get("status") == "gefunden" else None)
                kennzahlen = zonen_cache[name]

            gesehen[egrid] = {
                "attribute": attribute, "polygon": polygon, "flaeche_m2": flaeche,
                "zone_info": zone_info, "kennzahlen": kennzahlen,
            }

    # Erst jetzt zuordnen: ein Gebaeude kann in einer anderen Kachel liegen
    # als seine Parzelle, und ein Gebaeude ohne EGRID braucht alle Konturen
    # auf einmal, um ueber seine Lage zugeordnet zu werden.
    strassenparzellen = scr.markiere_strassenparzellen(polygone, strassenachsen)
    bericht["strassenparzellen"] = len(strassenparzellen)
    zuordnung = scr.ordne_gebaeude_zu(gwr_gesamt.values(), polygone)
    bericht["gebaeude_gelesen"] = len(gwr_gesamt)
    bericht["gebaeude_ueber_lage"] = sum(
        1 for liste in zuordnung.values() for g in liste if g.get("zuordnung") == "ueber_lage")

    xmin, ymin, xmax, ymax = bbox
    innen = (xmin - scr.RAND_M, ymin - scr.RAND_M, xmax + scr.RAND_M, ymax + scr.RAND_M)

    ergebnisse = []
    for egrid, roh in gesehen.items():
        polygon = roh["polygon"]
        bestand_je = scr.bestand_je_parzelle(zuordnung.get(egrid) or [])
        grenzen = polygon.bounds if polygon else None
        am_rand = bool(grenzen) and not (
            innen[0] <= grenzen[0] and innen[1] <= grenzen[1]
            and grenzen[2] <= innen[2] and grenzen[3] <= innen[3])
        eintrag = scr.bewerte_parzelle(
            {"egrid": egrid,
             "parzellennummer": roh["attribute"].get("number"),
             "gemeinde": gemeinden_je_egrid.get(egrid) or gemeinde,
             "flaeche_m2": roh["flaeche_m2"],
             "am_rand": am_rand,
             "ist_strassenparzelle": egrid in strassenparzellen},
            bestand_je.get(egrid),
            roh["zone_info"],
            roh["kennzahlen"],
        )
        eintrag["am_rand"] = am_rand
        eintrag["geometrie"] = [[round(x, 1), round(y, 1)] for x, y in
                                polygon.exterior.coords[:-1]] if polygon else None
        eintrag["schwerpunkt_lv95"] = ([round(polygon.representative_point().x, 1),
                                        round(polygon.representative_point().y, 1)]
                                       if polygon else None)
        ergebnisse.append(eintrag)

    bericht["parzellen_gefunden"] = len(ergebnisse)
    bericht["parzellen_am_rand"] = sum(1 for e in ergebnisse if e.get("am_rand"))
    sortiert = scr.sortiere(ergebnisse)

    zusammenfassung: dict[str, int] = {}
    for eintrag in sortiert:
        schluessel = eintrag.get("einstufung")
        zusammenfassung[schluessel] = zusammenfassung.get(schluessel, 0) + 1

    return {
        "status": "fertig",
        "bericht": bericht,
        "kennzahlen_vorhanden": bool(erkannte_zonen),
        "hinweis_kennzahlen": (
            None if erkannte_zonen else
            "Ohne ausgewertete Bau- und Nutzungsordnung gibt es keine "
            "Ausnuetzungsziffer und damit keine Reserve. Das Screening zeigt dann "
            "Flaeche, Zone und Bestand -- mehr laesst sich ohne sie nicht sagen."
        ),
        "min_flaeche_m2": min_flaeche_m2,
        "zusammenfassung": zusammenfassung,
        "parzellen": sortiert,
    }


def vertiefe_kandidat(
    egrid: str,
    geometrie: list,
    zone: dict[str, Any],
    *,
    restriktionsflaechen: Optional[list] = None,
) -> dict[str, Any]:
    """Stufe 2: die echte G1-Kaskade auf der Parzellenkontur.

    Ruft `berechne_potenzial` -- dieselbe Funktion wie die Einzelanalyse --
    mit den Grenzabstaenden der Zone. Ohne Kantenklassifikation gibt es keine
    kantenscharfe Zuordnung; gerechnet wird deshalb eine BANDBREITE zwischen
    "alle Kanten klein" und "alle Kanten gross". Das ist ehrlich und kostet
    keinen einzigen Netzaufruf.
    """
    from .baubereich import berechne_potenzial
    from .g1_verdrahtung import _kennzahl_wert

    ring = [(float(x), float(y)) for x, y in (geometrie or [])]
    if len(ring) < 3:
        return {"status": "nicht_bestimmbar", "grund": "Keine brauchbare Parzellenkontur."}

    klein = _kennzahl_wert(zone.get("grenzabstand_klein_m"))
    gross = _kennzahl_wert(zone.get("grenzabstand_gross_m"))
    abstaende = [a for a in (klein, gross) if a is not None]
    if not abstaende:
        return {"status": "nicht_bestimmbar",
                "grund": ("Fuer diese Zone sind keine Grenzabstaende bekannt -- ohne sie "
                          "gibt es keinen Baubereich.")}

    gemeinsam = dict(
        restriktionsflaechen=restriktionsflaechen or None,
        ausnuetzungsziffer_az=_kennzahl_wert(zone.get("ausnuetzungsziffer_az")),
        anrechenbare_geschossflaechenziffer_abgf=_kennzahl_wert(
            zone.get("anrechenbare_geschossflaechenziffer_abgf")),
        baumassenziffer_bmz=_kennzahl_wert(zone.get("baumassenziffer_bmz")),
        ueberbauungsziffer_uz=_kennzahl_wert(zone.get("ueberbauungsziffer_uz")),
        vollgeschosse_max=(int(_kennzahl_wert(zone.get("vollgeschosse_max")))
                           if _kennzahl_wert(zone.get("vollgeschosse_max")) is not None
                           else None),
        gebaeudehoehe_m=(_kennzahl_wert(zone.get("gebaeudehoehe_m"))
                         or _kennzahl_wert(zone.get("gesamthoehe_m"))),
    )

    varianten = {}
    for name, abstand in (("optimistisch", min(abstaende)), ("konservativ", max(abstaende))):
        if name in varianten:
            continue
        ergebnis = berechne_potenzial(ring, [abstand] * len(ring), **gemeinsam)
        varianten[name] = {
            "grenzabstand_m": abstand,
            "baubereich_m2": ergebnis.baubereich_m2,
            "fussabdruck_m2": ergebnis.fussabdruck_m2,
            "geschosszahl": ergebnis.geschosszahl,
            "geschossflaeche_m2": ergebnis.geschossflaeche_m2,
            "geschossflaeche_limitiert_durch": ergebnis.geschossflaeche_limitiert_durch,
        }
    return {
        "status": "bandbreite" if len(set(abstaende)) > 1 else "einzel",
        "egrid": egrid,
        "varianten": varianten,
        "hinweis": (
            "Gerechnet ohne Kantenklassifikation: jede Kante traegt denselben "
            "Grenzabstand. Welche Kante an einer Strasse liegt und welche an einem "
            "Nachbarn, klaert erst die vollstaendige Einzelanalyse -- das echte "
            "Ergebnis liegt zwischen diesen beiden Werten."
        ),
    }


def _kette_fuer_parzelle(
    modul1_result: dict,
    zonen_zuordnung: dict,
    markt,
    kostenpositionen,
    marktlage: Optional[dict],
    szenario_kwargs: dict,
    kantenklassifikation: Optional[dict],
) -> dict:
    """G1 -> Flaechen -> Szenarien -> Wirtschaftlichkeit fuer EINE Kontur.

    Genau die Kette, die `analysiere_grundstueck` und
    `berechne_wirtschaftlichkeit_je_szenario` ohnehin durchlaufen -- hier nur
    an einem Stueck aufgerufen, damit A und A+B mit identischen Annahmen
    gerechnet werden. Ein Vergleich zweier Ketten mit verschiedenen
    Kostenansaetzen oder Verkaufspreisen waere wertlos.
    """
    ergebnis: dict[str, Any] = {"g1": None, "g1_fehler": None}
    try:
        ergebnis["g1"] = berechne_g1_fuer_fall(
            modul1_result, zonen_zuordnung["zone"],
            kantenklassifikation=kantenklassifikation or None,
        )
    except G1VerdrahtungError as exc:
        ergebnis["g1_fehler"] = str(exc)
        return ergebnis

    ergebnis["flaechen"] = _flaechen_fuer_g1_ergebnis(ergebnis["g1"], zonen_zuordnung)
    ergebnis["szenarien"] = _szenarien_fuer_analyse(
        ergebnis["g1"], zonen_zuordnung, modul1_result, **szenario_kwargs
    )

    kataster = modul1_result.get("kataster") or {}
    bestand = (modul1_result.get("bestand") or {})
    haupt = bestand.get("hauptgebaeude") or {}
    wirtschaft = _berechne_wirtschaftlich(
        ergebnis["szenarien"],
        kataster.get("flaeche_m2"),
        markt,
        kostenpositionen,
        bestand_volumen_m3=haupt.get("gebaeudevolumen_m3"),
        marktlage=marktlage,
    )
    wirtschaft["hbu"] = _bestimme_hbu(ergebnis["szenarien"], wirtschaft, marktlage)
    ergebnis["wirtschaft"] = wirtschaft
    return ergebnis


def berechne_kombination(
    analyse: Analyse,
    *,
    e_b: float,
    n_b: float,
    markt: Marktannahmen,
    kostenpositionen: Optional[list] = None,
    kaufpreis_b_chf: Optional[float] = None,
    zusatzkosten_chf: Optional[float] = None,
    marktlage: Optional[dict] = None,
    **szenario_kwargs,
) -> dict[str, Any]:
    """Vergleicht Parzelle A allein mit der Kombination A+B.

    `e_b`/`n_b` ist ein Punkt in Parzelle B (LV95) -- in der Oberflaeche ein
    Kartenklick auf die Nachbarparzelle. Daraus werden ueber DIESELBEN
    Modul-1-Funktionen Kontur, Flaeche, EGRID und Zonenbezeichnung von B
    geholt; eine neue Datenquelle gibt es nicht.

    Die Kette laeuft danach zweimal durch dieselben Funktionen -- einmal auf
    A, einmal auf der vereinigten Kontur. Nur so sind die beiden Ergebnisse
    ueberhaupt vergleichbar, und nur so gibt es keine zweite Rechenlogik.

    Reihenfolge der Pruefungen (Filter, wie beim HBU): Geometrie, Angrenzung,
    Zone, G1. Faellt eine Stufe aus, wird mit Grund abgebrochen statt
    weitergerechnet.
    """
    from .kombination import (
        STATUS_MOEGLICH,
        ist_strassenparzelle,
        pruefe_zonen,
        vereinige,
        vergleiche,
    )
    from .modul1_geodata import get_gwr_data, get_parcel_data
    from .modul1b_nutzungsklassifikation import klassifiziere_nutzung
    from .restriktionsgeometrie import hole_restriktionen_fuer_parzelle

    m1_a = analyse.ergebnis.get("modul1_geodaten") or {}
    zonen_zuordnung = analyse.ergebnis.get("zonen_zuordnung") or {}
    if zonen_zuordnung.get("status") != "gefunden":
        return {
            "status": "nicht_bestimmbar",
            "grund": ("Fuer Parzelle A ist keine Zone eindeutig zugeordnet. Ohne sie gibt "
                      "es schon fuer A allein keine belastbare Geschossflaeche -- ein "
                      "Vergleich mit A+B waere ein Vergleich zweier Unbekannter."),
        }

    kataster_a = m1_a.get("kataster") or {}
    ring_a = kataster_a.get("parzellengeometrie")
    geo_a = m1_a.get("geocoding") or {}
    e_a, n_a = geo_a.get("lv95_e"), geo_a.get("lv95_n")
    kanton = (m1_a.get("gemeinde") or {}).get("kanton")

    # --- Parzelle B holen (dieselben amtlichen Layer wie Modul 1) ---------
    kataster_b = get_parcel_data(e_b, n_b)
    if not kataster_b.get("found"):
        return {
            "status": "nicht_bestimmbar",
            "grund": (f"An dieser Stelle liegt keine Parzelle in den offenen "
                      f"Katasterdaten: {kataster_b.get('reason') or 'kein Treffer'}."),
            "parzelle_b": kataster_b,
        }
    if kataster_b.get("egrid") and kataster_b["egrid"] == kataster_a.get("egrid"):
        return {
            "status": "nicht_zulaessig",
            "grund": "Das ist dieselbe Parzelle wie A -- eine Kombination mit sich selbst.",
            "parzelle_b": {k: kataster_b.get(k) for k in ("egrid", "parzellennummer")},
        }

    # --- 0 Ist B ueberhaupt eine Bauparzelle? ------------------------------
    # Die Kantenklassifikation von A weiss bereits, welche Nachbarparzelle
    # eine STRASSENparzelle ist (eine Strassenachse laeuft hindurch). Ohne
    # diese Pruefung liesse sich A mit der Gemeindestrasse kombinieren: die
    # Zonenplaene legen die Zone regelmaessig ueber die Strassenflaeche, die
    # Zonenpruefung schlaegt also nicht an. Real beobachtet an Rosenweg 4 --
    # die Strassenparzelle 1143 ergab 385'071 CHF "Mehrwert".
    strassen_grund = ist_strassenparzelle(
        m1_a.get("kantenklassifikation"), kataster_b.get("egrid"),
        kataster_b.get("parzellennummer"))
    if strassen_grund:
        return {
            "status": "nicht_zulaessig",
            "grund": strassen_grund,
            "parzelle_b": {k: kataster_b.get(k) for k in
                           ("egrid", "parzellennummer", "flaeche_m2")},
        }

    # --- 1 Geometrie und Angrenzung ---------------------------------------
    geometrie = vereinige(ring_a, kataster_b.get("parzellengeometrie"))
    antwort: dict[str, Any] = {
        "parzelle_a": {
            "egrid": kataster_a.get("egrid"),
            "parzellennummer": kataster_a.get("parzellennummer"),
            "flaeche_m2": kataster_a.get("flaeche_m2"),
        },
        "parzelle_b": {
            "egrid": kataster_b.get("egrid"),
            "parzellennummer": kataster_b.get("parzellennummer"),
            "flaeche_m2": kataster_b.get("flaeche_m2"),
            "flaeche_quelle": kataster_b.get("flaeche_quelle"),
            "parzellengeometrie": kataster_b.get("parzellengeometrie"),
        },
        "geometrie": geometrie,
    }
    if geometrie["status"] != STATUS_MOEGLICH:
        antwort["status"] = geometrie["status"]
        antwort["grund"] = geometrie["grund"]
        return antwort

    # --- 2 Zone -----------------------------------------------------------
    klass_a = m1_a.get("nutzungsklassifikation") or {}
    klass_b = klassifiziere_nutzung(e_b, n_b, kanton)
    antwort["nutzungsklassifikation_b"] = klass_b
    zonen = pruefe_zonen(klass_a.get("basiszone"), klass_b.get("basiszone"))
    antwort["zonen"] = zonen
    if zonen["status"] != STATUS_MOEGLICH:
        antwort["status"] = zonen["status"]
        antwort["grund"] = zonen["grund"]
        return antwort

    # Ein Sondernutzungsplan auf B wuerde dieselbe Sperre ausloesen wie auf A.
    snp_b = klass_b.get("sondernutzungsplaene_massgebend") or []
    if snp_b:
        antwort["status"] = "nicht_bestimmbar"
        antwort["grund"] = (
            "Parzelle B liegt in einem Sondernutzungs-/Gestaltungsplan-Perimeter. "
            "Dessen Inhalt kann von der ordentlichen Bau- und Zonenordnung abweichen "
            "und wird von dieser Engine nicht ausgewertet -- fuer A gilt dieselbe Regel."
        )
        return antwort

    # --- 3 Die vereinigte Kontur durch dieselbe Kette ---------------------
    union_ring = [tuple(p) for p in geometrie["ring"]]
    egrids = {g for g in (kataster_a.get("egrid"), kataster_b.get("egrid")) if g}

    klassifikation_ab = None
    kanten_fehler = None
    try:
        from .kantenklassifikation import KantenklassifikationError, klassifiziere_kanten

        klassifikation_ab = klassifiziere_kanten(
            union_ring, e_a, n_a, eigenes_egrid=egrids or None
        )
        if not klassifikation_ab.get("kanten"):
            klassifikation_ab = None
    except Exception as exc:  # noqa: BLE001 -- Rueckfall auf die Bandbreite, kein Abbruch
        kanten_fehler = f"{type(exc).__name__}: {exc}"
        klassifikation_ab = None
    antwort["kantenklassifikation_ab"] = klassifikation_ab
    antwort["kantenklassifikation_fehler"] = kanten_fehler

    restriktionen_ab = m1_a.get("restriktionsgeometrie")
    try:
        restriktionen_ab = hole_restriktionen_fuer_parzelle(e_a, n_a, kanton, union_ring)
    except Exception as exc:  # noqa: BLE001
        antwort["restriktionen_fehler"] = f"{type(exc).__name__}: {exc}"

    flaeche_ab = round((kataster_a.get("flaeche_m2") or 0) + (kataster_b.get("flaeche_m2") or 0), 1)
    m1_ab = dict(m1_a)
    m1_ab["kataster"] = {**kataster_a,
                         "parzellengeometrie": geometrie["ring"],
                         "flaeche_m2": flaeche_ab or geometrie["flaeche_m2"]}
    m1_ab["restriktionsgeometrie"] = restriktionen_ab
    m1_ab["kantenklassifikation"] = klassifikation_ab or {"kanten": []}

    kette_a = _kette_fuer_parzelle(
        m1_a, zonen_zuordnung, markt, kostenpositionen, marktlage, szenario_kwargs,
        (m1_a.get("kantenklassifikation") or {}).get("kanten") and m1_a.get("kantenklassifikation"),
    )
    kette_ab = _kette_fuer_parzelle(
        m1_ab, zonen_zuordnung, markt, kostenpositionen, marktlage, szenario_kwargs,
        klassifikation_ab,
    )
    antwort["a"] = kette_a
    antwort["ab"] = kette_ab

    # --- 4 Erschliessung --------------------------------------------------
    antwort["erschliessung"] = _erschliessung(
        m1_a.get("kantenklassifikation"), klassifikation_ab)

    # --- 5 Bestand auf B --------------------------------------------------
    try:
        gwr_b = get_gwr_data(e_b, n_b)
    except Exception:  # noqa: BLE001
        gwr_b = {"found": False}
    antwort["bestand_b"] = _bestand_b(gwr_b)

    # --- 6 Der Vergleich --------------------------------------------------
    antwort["vergleich"] = vergleiche(
        kette_a, kette_ab,
        flaeche_a_m2=kataster_a.get("flaeche_m2"),
        flaeche_b_m2=kataster_b.get("flaeche_m2"),
        kaufpreis_b_chf=kaufpreis_b_chf,
        zusatzkosten_chf=zusatzkosten_chf,
    )
    antwort["status"] = STATUS_MOEGLICH
    return antwort


def _erschliessung(klass_a: Optional[dict], klass_ab: Optional[dict]) -> dict[str, Any]:
    """Bleibt die kombinierte Parzelle erschlossen?

    Geprueft wird nur, was die Kantenklassifikation hergibt: hat die Kontur
    eine Kante an einer Strassenparzelle. Eine Erschliessung ueber ein
    Fuss-/Fahrwegrecht steht in keinem dieser Layer -- sie wird deshalb NICHT
    ausgeschlossen, sondern als offener Punkt benannt.
    """
    def strassenkanten(k: Optional[dict]) -> int:
        return sum(1 for kante in ((k or {}).get("kanten") or [])
                   if kante.get("art") == "strasse")

    a, ab = strassenkanten(klass_a), strassenkanten(klass_ab)
    if klass_ab is None:
        return {
            "status": "nicht_bestimmbar",
            "strassenkanten_a": a,
            "grund": ("Fuer die kombinierte Kontur konnte keine Kantenklassifikation "
                      "erstellt werden -- ob sie an eine Strasse grenzt, ist damit offen."),
        }
    if ab > 0:
        return {
            "status": "erschlossen",
            "strassenkanten_a": a, "strassenkanten_ab": ab,
            "grund": (f"Die kombinierte Parzelle grenzt mit {ab} Kante(n) an eine "
                      f"Strassenparzelle (A allein: {a})."),
        }
    return {
        "status": "offen",
        "strassenkanten_a": a, "strassenkanten_ab": ab,
        "grund": ("Keine Kante der kombinierten Parzelle grenzt an eine Strassenparzelle. "
                  "Das schliesst eine Erschliessung nicht aus -- ein Fuss-/Fahrwegrecht "
                  "steht in keinem oeffentlichen Layer -- aber sie ist hier nicht "
                  "nachgewiesen und muss manuell geprueft werden."),
    }


def _bestand_b(gwr: Optional[dict]) -> dict[str, Any]:
    """Steht auf B ein Gebaeude? Wichtig fuer Abbruchkosten -- die hier
    NICHT geschaetzt, sondern als Benutzerannahme erfragt werden."""
    if not (gwr or {}).get("found"):
        return {
            "bebaut": False,
            "hinweis": ("Auf B ist im GWR kein Gebaeude verzeichnet. Der Layer trifft "
                        "allerdings nur, wenn der Abfragepunkt auf dem Gebaeude liegt -- "
                        "'kein Treffer' heisst nicht zwingend 'unbebaut'."),
        }
    return {
        "bebaut": True,
        "egid": gwr.get("egid"),
        "baujahr": gwr.get("baujahr"),
        "grundflaeche_m2": gwr.get("grundflaeche_m2"),
        "hinweis": (
            "Auf B steht ein Gebaeude"
            + (f" (Baujahr {gwr.get('baujahr')})" if gwr.get("baujahr") else "")
            + ". Abbruch, Rueckbau oder Weiterverwendung sind hier nicht bewertet -- "
              "allfaellige Kosten gehoeren in das Feld 'zusaetzliche Kosten'. Geschaetzt "
              "wird hier nichts."
        ),
    }

def berechne_wirtschaftlichkeit_je_szenario(
    analyse: Analyse,
    markt: Marktannahmen,
    *,
    kostenpositionen: Optional[list] = None,
    auswahl: Optional[list[str]] = None,
    szenarien_ergebnis: Optional[dict] = None,
    # Ausgewertete Vergleichsobjekte. Sie aendern keine Rechnung -- sie
    # ordnen nur den rueckwaerts ermittelten Preis ein. Fehlen sie, bleibt
    # die Einordnung weg statt geschaetzt zu werden.
    marktlage: Optional[dict] = None,
    **szenario_kwargs,
) -> dict:
    """Markt, BKP und Wirtschaftlichkeit je Szenario -- ohne erneute Abfrage.

    Rechnet auf einer bereits erstellten Analyse. Eine Aenderung an
    Verkaufspreis, Miete, Bodenpreis, Wohnungsmix, BKP oder Zielmarge kostet
    Millisekunden; Geodaten, ÖREB und die Reglementsauswertung werden NICHT
    wiederholt.

    `szenarien_ergebnis` kann uebergeben werden, wenn die Szenarien bereits mit
    einem bestimmten Wohnungsmix gerechnet wurden; sonst werden sie hier mit
    `szenario_kwargs` neu gebildet.
    """
    if szenarien_ergebnis is None:
        szenarien_ergebnis = berechne_szenarien(analyse, **szenario_kwargs)

    kataster = (analyse.ergebnis.get("modul1_geodaten") or {}).get("kataster") or {}
    bestand = (analyse.kontext.get("modul1") or {}).get("bestand") or {}
    haupt = bestand.get("hauptgebaeude") or {}

    wirtschaft = _berechne_wirtschaftlich(
        szenarien_ergebnis,
        kataster.get("flaeche_m2"),
        markt,
        kostenpositionen,
        auswahl=auswahl,
        bestand_volumen_m3=haupt.get("gebaeudevolumen_m3"),
        marktlage=marktlage,
    )
    # Highest & Best Use fuehrt die eben gerechneten Ergebnisse zusammen. Es
    # rechnet nichts neu -- deshalb steht es hier und nicht als eigener
    # Aufruf, den jemand vergessen koennte.
    wirtschaft["hbu"] = _bestimme_hbu(szenarien_ergebnis, wirtschaft, marktlage)
    return wirtschaft


def berechne_flaechen(
    analyse: Analyse,
    *,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list[WohnungstypVorgabe]] = None,
    wohnungsmix_begruendung: str = "",
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
) -> Optional[dict]:
    """Rechnet die Flaechenkaskade und die Wohnungsstruktur neu.

    Arbeitet auf einer bereits erstellten Analyse: Geodaten, Reglement und
    Geometrie werden NICHT erneut abgerufen. Ein geaenderter Abzug oder ein
    anderer Wohnungsmix kostet damit Millisekunden statt Minuten -- die
    Voraussetzung dafuer, dass die Werte im Produkt frei einstellbar sind.
    """
    return _flaechen_fuer_g1_ergebnis(
        analyse.ergebnis.get("g1_ergebnis"),
        analyse.ergebnis.get("zonen_zuordnung") or {},
        benutzerwerte=benutzerwerte,
        wohnungsmix=wohnungsmix,
        wohnungsmix_begruendung=wohnungsmix_begruendung,
        profil=profil,
    )


# ---------------------------------------------------------------------------
# Die Analyse in Phasen -- damit die erste Ansicht nicht auf Gemini wartet
# ---------------------------------------------------------------------------

# Die Bereiche, ueber die der Fortschritt berichtet. Reihenfolge = Ablauf.
SCHRITTE = (
    ("grundstueck", "Grundstück und Karte"),
    ("grundnutzung", "Grundnutzung und amtliche Daten"),
    ("reglement", "Vertiefte Reglementsauswertung"),
    ("potenzial", "Baubereich, Flächen und Szenarien"),
)

STAND_OFFEN = "offen"
STAND_LAEUFT = "laeuft"
STAND_FERTIG = "fertig"
STAND_FEHLER = "fehler"


def _teilergebnis_nach_modul1(adresse: str, modul1_result: dict) -> dict:
    """Was schon feststeht, sobald die amtlichen Daten da sind.

    Das ist ein ECHTES Teilergebnis, kein Platzhalter: Parzelle, Flaeche,
    Gemeinde, Geometrie, Grundnutzung, Restriktionen und Kantenklassifikation
    sind an dieser Stelle endgueltig. Was von der Reglementsauswertung
    abhaengt, bleibt bewusst leer -- und der Stand sagt, dass es noch laeuft.

    Gerechnet wird hier nichts. Dieselben Werte, nur frueher gezeigt.
    """
    return {
        "adresse": adresse,
        "modul1_geodaten": _trimmed_modul1(modul1_result),
        "zonen_zuordnung": None,
        "g1_ergebnis": None,
        "g1_fehler": None,
        "sia416_ergebnis": None,
        "flaechen_und_wohnungen": None,
        "szenarien": None,
        "quellen": [asdict(q) for q in quellen_aus_modul1_ergebnis(modul1_result)],
        "entwicklungsszenarien": ENTWICKLUNGSSZENARIEN_INFO,
        "modul2_bzo_analyse": None,
        "modul3_financial": None,
        # Dasselbe Feldgeruest wie das Endergebnis: die Oberflaeche liest
        # beide, und ein Feld, das erst spaeter auftaucht, waere eine Falle.
        "bestand_und_neubaugeometrie": None,
    }


def analysiere_grundstueck(
    adresse: str,
    *,
    fortschritt=None,
    modul2_lader=None,
) -> Analyse:
    """Vollstaendige baurechtliche Potenzialanalyse fuer eine Adresse.

    Ablauf: Geodaten (Modul 1) -> Nutzungsklassifikation (Modul 1b) ->
    Auswertung des kommunalen Reglements (Modul 2, LLM) -> Zonenzuordnung ->
    G1-Baubereich -> SIA 416 -> Quellennachweise.

    Braucht KEINEN Verkaufspreis. Dauert typischerweise 1-3 Minuten, weil
    Modul 2 das Reglement der Gemeinde tatsaechlich liest.

    `fortschritt(schritt, stand, teilergebnis)` wird an den Phasengrenzen
    aufgerufen. Gemessen entfallen 87 % der Laufzeit auf Modul 2 -- alles
    Uebrige steht nach rund zehn Sekunden. Der Rueckruf gibt es weiter,
    damit die Oberflaeche das anzeigen kann, statt vor einem leeren
    Ergebnis zu warten. An der Rechnung aendert er nichts.

    `modul2_lader(oereb, gemeinde, kanton)` ersetzt den direkten
    Gemini-Aufruf -- so kann der Aufrufer einen Zwischenspeicher davorlegen,
    ohne dass die Engine eine Datenbank kennen muss.

    Wirft Modul1Error, wenn fuer die Parzelle keine amtlichen Zonendaten
    (OEREB) vorliegen -- dann waere jede Potenzialaussage haltlos.
    """
    def melde(schritt, stand, teil=None):
        if fortschritt:
            try:
                fortschritt(schritt, stand, teil)
            except Exception:  # noqa: BLE001 -- ein Anzeigefehler stoppt keine Analyse
                pass

    melde("grundstueck", STAND_LAEUFT)
    modul1_result = run_modul1(adresse)
    oereb = modul1_result.get("oereb", {})
    if not oereb.get("found"):
        melde("grundstueck", STAND_FEHLER)
        raise Modul1Error(f"Keine amtlichen Zonendaten (OEREB) gefunden: {oereb.get('reason')}")

    teil = _teilergebnis_nach_modul1(adresse, modul1_result)
    melde("grundstueck", STAND_FERTIG, teil)
    melde("grundnutzung", STAND_FERTIG, teil)

    gemeinde = modul1_result.get("gemeinde", {}).get("gemeinde")
    kanton = oereb.get("kanton")

    melde("reglement", STAND_LAEUFT, teil)
    lader = modul2_lader or (
        lambda o, gemeinde=None, kanton=None: analyze_from_oereb_result(
            o, gemeinde=gemeinde, kanton=kanton, backend="gemini"))
    try:
        modul2_result = lader(oereb, gemeinde=gemeinde, kanton=kanton)
    except Exception:
        # Die amtlichen Daten bleiben gueltig -- nur die Reglementsauswertung
        # fehlt. Der Aufrufer entscheidet, ob er das Teilergebnis behaelt.
        melde("reglement", STAND_FEHLER, teil)
        raise
    melde("reglement", STAND_FERTIG)

    melde("potenzial", STAND_LAEUFT)
    ergebnis = _potenzialkette(adresse, modul1_result, modul2_result)
    melde("potenzial", STAND_FERTIG, ergebnis)
    return Analyse(ergebnis=ergebnis, kontext={"modul1": modul1_result, "modul2": modul2_result})


def _bestand_und_neubaugeometrie(
    modul1_result: dict, g1_ergebnis: Optional[dict],
) -> dict:
    """Die drei Ebenen sauber getrennt -- Bestand, Neubaugeometrie, Zusatz.

    Der Fehler, den das verhindert: G1 rechnet auf der gruenen Wiese. Sein
    Fussabdruck ist der maximal zulaessige Fussabdruck eines NEUEN
    Gebaeudekoerpers unter den heute modellierten Abstaenden -- weder der
    freie zusaetzliche noch der bestehende. Ohne diese Trennung liest sich
    "Fussabdruck 0.7 m2" wie "auf diesem Grundstueck ist nichts moeglich",
    obwohl dort ein Haus mit 248 m2 Grundflaeche steht.

    Die rechtliche Einordnung bleibt ausdruecklich offen: dass ein Gebaeude
    die heutigen Abstaende unterschreitet, ist eine geometrische Feststellung
    und KEIN Nachweis eines Bestandesschutzes.
    """
    from .baubereich import vergleiche_bestand_mit_baubereich

    bestand = modul1_result.get("bestand") or {}
    gebaeude = bestand.get("gebaeude") or []
    grundrisse = [g.get("grundriss") for g in gebaeude if g.get("grundriss")]

    # Die Grundflaeche des GWR gehoert zu DIESEM Gebaeude; das Katasterpolygon
    # kann mehr umfassen. In Rheineck stehen 118 m2 (GWR) gegen 248 m2
    # (Grundriss) -- das Polygon deckt die ganze Haeuserzeile. Gerechnet wird
    # deshalb mit dem GWR-Wert, und die Abweichung wird ausgewiesen.
    geschosse = [g.get("geschosse") for g in gebaeude]
    flaechen = [g.get("grundflaeche_gwr_m2") for g in gebaeude]
    bestand_gf = None
    if gebaeude and all(g for g in geschosse) and all(f for f in flaechen):
        bestand_gf = round(sum(f * g for f, g in zip(flaechen, geschosse)), 1)

    # Die bestehende Geschossflaeche ist NIE gemessen: das Gebaeude- und
    # Wohnungsregister fuehrt keine Geschossflaeche. Was hier steht, ist
    # Grundflaeche mal Geschosszahl -- eine Ableitung aus zwei Registerwerten.
    # Sie als "Bestand: 354 m2 GF" auszugeben, taeuschte eine Genauigkeit vor,
    # die die Daten nicht hergeben: Untergeschosse, Dachgeschosse,
    # unterschiedlich grosse Geschosse und Anbauten sind darin nicht
    # abgebildet.
    ebene_bestand = {
        "gebaeude": len(gebaeude),
        "grundflaeche": {
            "wert_m2": bestand.get("bebaute_flaeche_gwr_m2"),
            "quelle": "Gebaeude- und Wohnungsregister (GWR)",
            "status": "gemessen" if bestand.get("bebaute_flaeche_gwr_m2") else "nicht_verfuegbar",
        },
        "grundriss_kataster": {
            "wert_m2": bestand.get("bebaute_flaeche_grundriss_m2"),
            "quelle": "amtliche Vermessung (Gebaeudepolygon)",
            "hinweis": (
                "Das Katasterpolygon kann mehr umfassen als dieses eine Gebaeude -- "
                "bei zusammengebauten Haeusern deckt es die ganze Zeile."),
        },
        "geschosse": {
            "wert": [g for g in geschosse if g] or None,
            "quelle": "Gebaeude- und Wohnungsregister (GWR)",
            "status": "gemessen" if all(g for g in geschosse) and gebaeude else "unvollstaendig",
        },
        "geschossflaeche_abgeleitet": {
            "wert_m2": bestand_gf,
            "status": "abgeleitet" if bestand_gf is not None else "nicht_bestimmbar",
            "rechnung": (
                None if bestand_gf is None else
                " + ".join(f"{f:,.0f} m2 x {g} Geschosse" for f, g in zip(flaechen, geschosse))),
            "herleitung": (
                "Grundflaeche x Geschosszahl. NAEHERUNGSWERT -- das Register fuehrt "
                "keine Geschossflaeche. Unter- und Dachgeschosse, unterschiedlich "
                "grosse Geschosse und Anbauten sind darin nicht abgebildet."),
            "grund": (
                None if bestand_gf is not None else
                "Das Gebaeuderegister fuehrt fuer diese Parzelle keine vollstaendige "
                "Geschosszahl oder Grundflaeche -- auch eine Naeherung ist daraus "
                "nicht ableitbar."),
        },
    }

    # --- Neubau nach heutiger Geometrie ---------------------------------
    modus = (g1_ergebnis or {}).get("modus")
    einzel = (g1_ergebnis or {}).get("ergebnis") or {}
    bandbreite = (g1_ergebnis or {}).get("bandbreite") or {}
    ebene_neubau = {
        "bedeutung": (
            "Maximal zulaessiger Fussabdruck und Geschossflaeche eines VOLLSTAENDIG "
            "NEUEN Baukoerpers unter den heute modellierten Abstaenden. Nicht der "
            "freie zusaetzliche und nicht der bestehende Fussabdruck."),
        "belastbar": bool(einzel) and (g1_ergebnis or {}).get("baubereich_belastbar") is not False,
    }
    if einzel:
        ebene_neubau.update(
            baubereich_m2=einzel.get("baubereich_m2"),
            fussabdruck_m2=einzel.get("fussabdruck_m2"),
            geschossflaeche_m2=einzel.get("geschossflaeche_m2"))
    elif bandbreite:
        ebene_neubau.update(
            bandbreite_baubereich_m2=bandbreite.get("baubereich_m2"),
            bandbreite_geschossflaeche_m2=bandbreite.get("geschossflaeche_m2"),
            grund=(g1_ergebnis or {}).get("grund_nicht_belastbar"))
    elif str(modus or "").startswith("bandbreite_"):
        ebene_neubau["grund"] = (g1_ergebnis or {}).get("hinweis")
    else:
        ebene_neubau["grund"] = "Keine G1-Geometrie vorhanden."

    # --- Geschossflaeche nach der aktuellen Ausnuetzungsziffer -----------
    # Bewusst NICHT "zulaessige Gesamtentwicklung". Dieser Wert sagt, welche
    # Geschossflaeche die heutige Ausnuetzungsziffer auf diese Landflaeche
    # rechnet -- mehr nicht. Er beruecksichtigt weder Abstaende noch
    # Sonderregelungen, Bonusregelungen oder den Bestand.
    az_gf = (g1_ergebnis or {}).get("gf_nach_ausnuetzungsziffer_m2")
    if az_gf is None and einzel:
        kandidaten = einzel.get("geschossflaeche_kandidaten") or {}
        az_gf = kandidaten.get("ausnuetzung_az")
    rechtsrahmen = {
        "gf_nach_ausnuetzungsziffer_m2": az_gf,
        "rechnung": (g1_ergebnis or {}).get("gf_nach_ausnuetzungsziffer_rechnung"),
        "bedeutung": (
            "Theoretischer Wert der aktuellen Zonengrundlage: Ausnuetzungsziffer mal "
            "anrechenbare Landflaeche. Keine Aussage darueber, was auf diesem "
            "Grundstueck insgesamt zulaessig oder baulich realisierbar ist."),
    }

    # --- Zusaetzliches Entwicklungspotenzial ----------------------------
    # Die Differenz aus theoretischem Zonenwert und abgeleitetem Bestand ist
    # KEIN Potenzial. Sie verrechnet zwei Groessen verschiedener Art:
    #
    #   * der Zonenwert ist theoretisch und kennt weder Abstaende noch
    #     Sonderregelungen
    #   * die Bestands-GF ist aus zwei Registerwerten abgeleitet, nicht
    #     gemessen
    #
    # Waere die Differenz negativ, entstuende daraus scheinbar ein
    # Rueckbaubefund -- fuer einen Altbau im Ortskern die Regel und trotzdem
    # falsch. Die Bestandessituation und die Abstands-/Geometriefrage sind
    # getrennt vom theoretischen Neubauwert zu beurteilen.
    hindernisse: list[str] = []
    if az_gf is None:
        hindernisse.append(
            "Es gibt keine belastbare Ausnuetzungsziffer, also auch keinen "
            "theoretischen Zonenwert.")
    if not ebene_neubau.get("belastbar"):
        hindernisse.append(
            "Die Neubaugeometrie unter den heutigen Abstaenden ist nicht belastbar "
            "bestimmbar -- ohne sie ist offen, was von einem theoretischen Wert "
            "baulich uebrig bliebe.")
    if gebaeude and bestand_gf is None:
        hindernisse.append(
            "Die bestehende Geschossflaeche ist aus dem Register nicht ableitbar.")
    elif gebaeude:
        hindernisse.append(
            "Der Bestand ist mit rund " + f"{bestand_gf:,.0f}" + " m2 nur GENAEHERT "
            "bekannt (Grundflaeche x Geschosszahl). Eine Differenz aus einem "
            "theoretischen Zonenwert und einer Naeherung waere keine Potenzialzahl.")

    if hindernisse:
        ebene_zusatz = {
            "status": "nicht_abschliessend_bestimmbar",
            "grund": ("Bestandessituation und Abstands-/Geometriefrage muessen getrennt "
                      "vom theoretischen Neubauwert beurteilt werden."),
            "offene_punkte": hindernisse,
        }
    else:
        # Kein Bestand, belastbare Geometrie, belastbare Ziffer: dann ist das
        # zusaetzliche Potenzial schlicht das Potenzial.
        ebene_zusatz = {
            "status": "bestimmbar",
            "zusaetzliche_geschossflaeche_m2": az_gf,
            "rechnung": f"{az_gf:,.1f} m2 nach Ausnuetzungsziffer, kein Gebaeude verzeichnet",
        }

    # --- Bestandessituation: Feststellung, keine rechtliche Einordnung ---
    obere_huelle = None
    if einzel.get("baubereich_koordinaten"):
        obere_huelle = einzel["baubereich_koordinaten"]
    else:
        # Bei einer Bandbreite gilt die GROSSZUEGIGSTE Huelle: nur was auch
        # dort nicht hineinpasst, laesst sich mit den heutigen Abstaenden
        # sicher nicht erklaeren.
        oben = ((g1_ergebnis or {}).get("szenarien") or {}).get(
            bandbreite.get("obergrenze_szenario") or "")
        if oben:
            obere_huelle = oben.get("baubereich_koordinaten")

    vergleich = vergleiche_bestand_mit_baubereich(grundrisse, obere_huelle)
    bestandssituation = {"vergleichbar": vergleich is not None}
    if vergleich:
        bestandssituation.update(vergleich)
        if vergleich["anteil_ausserhalb"] > 0.05:
            bestandssituation["hinweis"] = (
                f"Der Bestand liegt zu {vergleich['anteil_ausserhalb']:.0%} ausserhalb der "
                "heute modellierten Abstandsgeometrie. Er laesst sich damit nicht aus den "
                "geltenden Abstaenden erklaeren -- Bestandessituation und allfaelliger "
                "Bestandesschutz sind zu pruefen. Daraus folgt NICHT, dass nur die heutige "
                "Neubaugeometrie zulaessig waere.")
            bestandssituation["pruefen"] = True
        else:
            bestandssituation["hinweis"] = (
                "Der Bestand liegt im Wesentlichen innerhalb der heute modellierten "
                "Abstandsgeometrie.")
            bestandssituation["pruefen"] = False

    return {
        "bestand": ebene_bestand,
        "neubau_nach_heutiger_geometrie": ebene_neubau,
        "heutiger_rechtsrahmen": rechtsrahmen,
        "zusaetzliches_potenzial": ebene_zusatz,
        "bestandssituation": bestandssituation,
    }


def _potenzialkette(adresse: str, modul1_result: dict, modul2_result: dict) -> dict:
    """Zonenzuordnung, G1, SIA 416, Flaechen, Szenarien, Quellen.

    Unveraendert aus der bisherigen `analysiere_grundstueck` herausgeloest --
    damit sie nach einem fehlgeschlagenen Modul 2 nachgeholt werden kann,
    ohne die amtlichen Abfragen zu wiederholen.
    """
    # Preisunabhaengig: welche BZO-Zone gilt amtlich fuer dieses Grundstueck.
    zonen_zuordnung = ermittle_zonenzuordnung(modul1_result, modul2_result)

    # G1 (Baubereich/Fussabdruck/Geschossflaeche) braucht eine EINDEUTIG
    # zugeordnete Zone -- bei Mehrdeutigkeit oder SNP-Blockierung wird bewusst
    # nicht geraten, welcher Kandidat gilt, sondern G1 uebersprungen.
    g1_ergebnis = None
    g1_fehler = None
    if zonen_zuordnung.get("status") == "gefunden":
        # Kantenklassifikation nur weiterreichen, wenn sie tatsaechlich Kanten
        # beschreibt -- ein Fehlschlag (Netz, entartete Geometrie) fuehrt zur
        # bisherigen Bandbreite zurueck, nicht zu einem Abbruch.
        klassifikation = modul1_result.get("kantenklassifikation") or {}
        if not klassifikation.get("kanten"):
            klassifikation = None
        try:
            g1_ergebnis = berechne_g1_fuer_fall(
                modul1_result, zonen_zuordnung["zone"], kantenklassifikation=klassifikation
            )
        except G1VerdrahtungError as exc:
            g1_fehler = str(exc)

    sia416_ergebnis = _sia416_fuer_g1_ergebnis(g1_ergebnis)

    # Stufe 3: die Bruecke Baurecht -> Flaeche -> Wohnung. Ohne Wohnungsmix,
    # weil der eine Benutzerentscheidung ist -- die Flaechenkaskade steht
    # trotzdem vollstaendig da, und die Wohnungszahl meldet sich ehrlich als
    # nicht bestimmbar. Nachtraeglich mit eigenen Annahmen neu rechenbar
    # ueber berechne_flaechen(), ohne erneute Geo-/Gemini-Abfrage.
    flaechenmodell_ergebnis = _flaechen_fuer_g1_ergebnis(g1_ergebnis, zonen_zuordnung)

    # Stufe 4: die Entwicklungsszenarien. Ebenfalls ohne Wohnungsmix -- der ist
    # eine Benutzerentscheidung. Nachtraeglich neu rechenbar ueber
    # berechne_szenarien(), ohne erneute Geo-/Gemini-Abfrage.
    szenarien_ergebnis = _szenarien_fuer_analyse(
        g1_ergebnis, zonen_zuordnung, modul1_result,
    )

    # Quellenobjekte: Rueckverfolgbarkeit jedes amtlichen Modul-1-Werts auf
    # Endpunkt/Layer/URL -- vor dem Trimmen berechnet (unabhaengig davon, ob
    # raw_attributes/raw_extract fuer die Anzeige weggeschnitten werden).
    quellen = [asdict(q) for q in quellen_aus_modul1_ergebnis(modul1_result)]
    kanten_klassifikation = modul1_result.get("kantenklassifikation") or {}
    if kanten_klassifikation.get("kanten"):
        quellen += [asdict(q) for q in quellen_fuer_kanten(kanten_klassifikation)]

    return {
        "adresse": adresse,
        "modul1_geodaten": _trimmed_modul1(modul1_result),
        "zonen_zuordnung": zonen_zuordnung,
        "g1_ergebnis": g1_ergebnis,
        "g1_fehler": g1_fehler,
        "sia416_ergebnis": sia416_ergebnis,
        "flaechen_und_wohnungen": flaechenmodell_ergebnis,
        "szenarien": szenarien_ergebnis,
        "quellen": quellen,
        "entwicklungsszenarien": ENTWICKLUNGSSZENARIEN_INFO,
        "modul2_bzo_analyse": modul2_result,
        "modul3_financial": None,
        # Bestand, Neubaugeometrie und zusaetzliches Potenzial sind drei
        # verschiedene Groessen. G1 liefert nur die mittlere.
        "bestand_und_neubaugeometrie": _bestand_und_neubaugeometrie(
            modul1_result, g1_ergebnis),
    }


def berechne_wirtschaftlichkeit(
    analyse: Analyse,
    verkaufspreis_chf_pro_m2: Optional[float] = None,
    verkaufspreis_total_chf: Optional[float] = None,
) -> Wirtschaftlichkeit:
    """Residualwertrechnung (Modul 3) auf einer bereits erstellten Analyse.

    Rechnet auf dem Kontext der Analyse -- Geodaten und Reglementsauswertung
    werden NICHT erneut abgerufen. Dadurch ist der Aufruf in Sekunden fertig
    statt in Minuten, und die baurechtliche Analyse bleibt unangetastet.

    Genau eine der beiden Preisangaben ist noetig. Modul 3 selbst erhaelt
    immer einen CHF/m2-Wert.
    """
    kontext = analyse.kontext
    preis = _preis_pro_m2(kontext["modul1"], verkaufspreis_chf_pro_m2, verkaufspreis_total_chf)
    modul3_result = run_from_modul_results(kontext["modul1"], kontext["modul2"], preis)
    return Wirtschaftlichkeit(ergebnis=modul3_result, verwendeter_preis_chf_pro_m2=preis)

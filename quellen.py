"""
Einheitliches Quellenobjekt (Konzept-/Vorbereitungsmodul).

Ziel: jeder einzelne Wert, den die Potenzial-Engine ausgibt, soll sich
lueckenlos zurueckverfolgen lassen:

    Wert -> Quelle -> Originaldokument -> Artikel/Fundstelle -> Zitat -> URL

Dieses Modul definiert dafuer ein einziges Schema (`Quellenobjekt`) und
Adapter, die bestehende Modul-Ausgaben (Modul 1 amtliche Werte, Modul 2
LLM-Kennzahlen, SIA-416-Modellannahmen) VERLUSTFREI dorthin abbilden --
ohne die bestehenden Module selbst zu veraendern. Die Adapter sind
bewusst lesend/additiv: modul1_geodata.py und modul2_bzo_analysis.py
bleiben unveraendert, ihre gruenen Regressionstests bleiben gueltig.

`quelle_url` wird dort automatisch gefuellt, wo eine echte, bereits in
Modul 1/2 verwendete URL vorliegt (siehe `_BEKANNTE_AMTLICHE_ENDPUNKTE`,
`url_fuer_oereb_kanton()` und der `source_dokumente`-Parameter von
`aus_modul2_kennzahl()`). Fuer Werte ohne bekannte Fundstelle bleibt es
bewusst `None` -- kein erfundener Link wird eingesetzt.

`quellen_aus_modul1_ergebnis()` (unten) leitet aus einem fertigen
`run_modul1()`-Ergebnis-Dict eine vollstaendige, pro Feld aufgeschluesselte
Quellenliste ab -- rein additiv als Nachbearbeitung, OHNE run_modul1()
selbst zu veraendern oder erneut abzufragen. Jede darin verwendete URL/
Layer-ID stammt aus einer bereits in modul1_geodata.py existierenden
Konstante (siehe Importe unten) oder direkt aus dem Ergebnis-Dict selbst
(z.B. `oereb.source_url`, das Modul 1 pro EGRID bereits real aufloest).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from modul1_geodata import (
    GEOADMIN_BASE,
    HEIGHT_URL,
    LAYER_CADASTRE_GEOM,
    LAYER_GWR,
    LAYER_MUNICIPALITY,
    LAYER_PARCEL,
    OEREB_CANTON_SERVICES,
    OVERPASS_URL,
    TRANSPORT_OPENDATA_URL,
)

# Dieselben, in modul1_geodata._identify()/geocode_address() tatsaechlich
# verwendeten REST-Pfade -- gebaut aus der importierten GEOADMIN_BASE-
# Konstante, kein eigener Endpunkt-Wert.
MAPSERVER_IDENTIFY_URL = f"{GEOADMIN_BASE}/MapServer/identify"
SEARCHSERVER_URL = f"{GEOADMIN_BASE}/SearchServer"

# Radonkarte-Layer-ID: in modul1_geodata.get_radon_data() nur als Literal
# verwendet (keine eigene benannte Konstante dort) -- hier bewusst nicht
# nachtraeglich in modul1_geodata.py in eine Konstante ausgelagert, um
# dessen Logik nicht anzufassen; der Wert ist identisch mit dem dortigen
# Literal "ch.bag.radonkarte".
LAYER_RADON = "ch.bag.radonkarte"

QUELLE_TYP_AMTLICH = "amtliche_quelle"
QUELLE_TYP_LLM_EXTRAKTION = "llm_extraktion"
QUELLE_TYP_MODELLANNAHME = "modellannahme"
QUELLE_TYP_GEOMETRIE_BERECHNUNG = "geometrie_berechnung"
QUELLE_TYP_MANUELL = "manuelle_eingabe"

_GUELTIGE_QUELLE_TYPEN = {
    QUELLE_TYP_AMTLICH,
    QUELLE_TYP_LLM_EXTRAKTION,
    QUELLE_TYP_MODELLANNAHME,
    QUELLE_TYP_GEOMETRIE_BERECHNUNG,
    QUELLE_TYP_MANUELL,
}

# Bekannte, in Modul 1 tatsaechlich verwendete Bezeichnungen fuer amtliche
# Quellen -- gemappt auf die REALEN Endpunkt-Konstanten aus
# modul1_geodata.py (single source of truth, hier nicht neu deklariert).
# Zeigt auf den technischen API-Endpunkt, nicht auf eine pro-Wert-
# Deep-Link-Seite (die gibt es bei diesen REST-/Identify-Services nicht).
QUELLE_BEZEICHNUNG_KATASTER = f"Kataster (swisstopo amtliche Vermessung, Layer {LAYER_PARCEL}, via geo.admin.ch MapServer identify)"
QUELLE_BEZEICHNUNG_PARZELLENGEOMETRIE = f"Katasterplan-Geometrie (Layer {LAYER_CADASTRE_GEOM}, via geo.admin.ch MapServer identify)"
QUELLE_BEZEICHNUNG_GWR = f"GWR Gebaeude- und Wohnungsregister (Layer {LAYER_GWR}, via geo.admin.ch MapServer identify)"
QUELLE_BEZEICHNUNG_GEMEINDE = f"Gemeindegrenzen swissBOUNDARIES3D (Layer {LAYER_MUNICIPALITY}, via geo.admin.ch MapServer identify)"
QUELLE_BEZEICHNUNG_RADON = f"BAG Radonkarte (Layer {LAYER_RADON}, via geo.admin.ch MapServer identify)"
QUELLE_BEZEICHNUNG_GEOCODING = "Adressgeocoding (geo.admin.ch SearchServer)"
QUELLE_BEZEICHNUNG_HOEHENMODELL = "swissALTI3D Hoehenmodell (geo.admin.ch height-REST-Service)"
QUELLE_BEZEICHNUNG_OEV = "Oeffentlicher Verkehr (transport.opendata.ch)"
QUELLE_BEZEICHNUNG_UMGEBUNG = "Umgebungsinfrastruktur (OpenStreetMap Overpass API)"

_BEKANNTE_AMTLICHE_ENDPUNKTE: Dict[str, str] = {
    QUELLE_BEZEICHNUNG_KATASTER: MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_PARZELLENGEOMETRIE: MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_GWR: MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_GEMEINDE: MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_RADON: MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_GEOCODING: SEARCHSERVER_URL,
    QUELLE_BEZEICHNUNG_HOEHENMODELL: HEIGHT_URL,
    QUELLE_BEZEICHNUNG_OEV: TRANSPORT_OPENDATA_URL,
    QUELLE_BEZEICHNUNG_UMGEBUNG: OVERPASS_URL,
}


def url_fuer_oereb_kanton(kanton_kuerzel: str, egrid: str, fmt: str = "json") -> Optional[str]:
    """Baut die konkrete, abrufbare OEREB-Webservice-URL fuer einen
    Kanton + EGRID aus der in modul1_geodata.OEREB_CANTON_SERVICES
    hinterlegten, live verifizierten Vorlage. Liefert `None` statt eines
    geratenen Endpunkts, wenn der Kanton dort (noch) nicht gefuehrt wird
    (siehe modul1_geodata.py fuer den aktuellen Abdeckungsstand)."""
    template = OEREB_CANTON_SERVICES.get(kanton_kuerzel.upper())
    if not template:
        return None
    return template.format(fmt=fmt, egrid=egrid)


@dataclass
class Quellenobjekt:
    feld: str
    wert: Any
    quelle_typ: str
    quelle_bezeichnung: str
    quelle_url: Optional[str] = None
    artikel_referenz: Optional[str] = None
    zitat: Optional[str] = None
    confidence: Optional[str] = None
    abgerufen_am: Optional[str] = None

    def __post_init__(self) -> None:
        if self.quelle_typ not in _GUELTIGE_QUELLE_TYPEN:
            raise ValueError(
                f"Unbekannter quelle_typ '{self.quelle_typ}' fuer Feld '{self.feld}' -- "
                f"muss einer von {sorted(_GUELTIGE_QUELLE_TYPEN)} sein."
            )
        if not self.quelle_bezeichnung or not self.quelle_bezeichnung.strip():
            raise ValueError(f"quelle_bezeichnung fuer Feld '{self.feld}' fehlt.")


def _url_aus_source_dokumenten(quelle_dokument: Optional[str], source_dokumente: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Sucht die reale Dokument-URL zu einem von Gemini/Claude genannten
    `quelle_dokument`-Titel in Modul 2s eigenem `_meta.source_dokumente`
    (siehe modul2_bzo_analysis.analyze_from_oereb_result(), das dort
    bereits Titel+URL der tatsaechlich analysierten Dokumente mitfuehrt).
    Erst exakter Treffer, dann Teilstring-Abgleich (das LLM zitiert den
    Titel manchmal leicht abweichend/gekuerzt) -- ohne Treffer `None`,
    es wird keine URL geraten."""
    if not quelle_dokument or not source_dokumente:
        return None
    for doc in source_dokumente:
        if doc.get("titel") == quelle_dokument:
            return doc.get("url")
    ql = quelle_dokument.strip().lower()
    for doc in source_dokumente:
        titel = (doc.get("titel") or "").strip().lower()
        if titel and (titel in ql or ql in titel):
            return doc.get("url")
    return None


def aus_modul2_kennzahl(
    feldname: str,
    kennzahl: Dict[str, Any],
    source_dokumente: Optional[List[Dict[str, Any]]] = None,
) -> Quellenobjekt:
    """Wandelt ein Modul-2-Kennzahl-Dict (wert/quelle_dokument/
    artikel_referenz/zitat/confidence/...) in ein Quellenobjekt.
    Erwartet die seit der Kennzahl-Schema-Erweiterung produzierte
    Struktur; fehlt ein Feld, wird es als `None` uebernommen statt
    ergaenzt.

    `source_dokumente` ist optional die Liste aus
    `analyze_from_oereb_result(...)["_meta"]["source_dokumente"]`
    (`[{"titel": ..., "url": ...}, ...]`) -- wird sie mitgegeben, fuellt
    sich `quelle_url` automatisch mit der tatsaechlichen Dokument-URL."""
    return Quellenobjekt(
        feld=feldname,
        wert=kennzahl.get("wert"),
        quelle_typ=QUELLE_TYP_LLM_EXTRAKTION,
        quelle_bezeichnung=kennzahl.get("quelle_dokument") or "unbekanntes BZO-/Reglement-Dokument",
        quelle_url=_url_aus_source_dokumenten(kennzahl.get("quelle_dokument"), source_dokumente),
        artikel_referenz=kennzahl.get("artikel_referenz"),
        zitat=kennzahl.get("zitat"),
        confidence=kennzahl.get("confidence"),
    )


def aus_amtlichem_wert(
    feldname: str,
    wert: Any,
    quelle_bezeichnung: str,
    quelle_url: Optional[str] = None,
    abgerufen_am: Optional[str] = None,
) -> Quellenobjekt:
    """Fuer Werte aus Modul 1 (GWR, Kataster, geo.admin.ch, ÖREB-
    Webservices etc.) -- amtliche Register-/Geodienst-Antworten ohne
    Artikel/Zitat-Konzept (das gibt es nur bei Dokumenten, nicht bei
    API-Antworten).

    Ist `quelle_url` nicht gesetzt, wird sie automatisch aus
    `_BEKANNTE_AMTLICHE_ENDPUNKTE` nachgeschlagen, sofern
    `quelle_bezeichnung` einer der `QUELLE_BEZEICHNUNG_*`-Konstanten
    entspricht (sonst bleibt sie `None` -- kein erfundener Endpunkt)."""
    return Quellenobjekt(
        feld=feldname, wert=wert, quelle_typ=QUELLE_TYP_AMTLICH,
        quelle_bezeichnung=quelle_bezeichnung,
        quelle_url=quelle_url or _BEKANNTE_AMTLICHE_ENDPUNKTE.get(quelle_bezeichnung),
        confidence="hoch", abgerufen_am=abgerufen_am or datetime.now().date().isoformat(),
    )


def aus_modellannahme(feldname: str, wert: Any, begruendung: str, quelle: Optional[str] = None) -> Quellenobjekt:
    """Fuer SIA-416-Verhaeltniszahlen, Wohnungsmix-Annahmen und
    aehnliche Modellannahmen -- macht sie im selben Schema wie amtliche
    und LLM-extrahierte Werte sichtbar, statt sie unmarkiert
    durchzureichen."""
    return Quellenobjekt(
        feld=feldname, wert=wert, quelle_typ=QUELLE_TYP_MODELLANNAHME,
        quelle_bezeichnung=f"Modellannahme: {begruendung}", quelle_url=quelle,
        confidence="modellannahme",
    )


def aus_geometrie_berechnung(feldname: str, wert: Any, herkunft: str) -> Quellenobjekt:
    """Fuer G1-Ergebniswerte (Baubereich, Fussabdruck, Geschossflaeche
    etc.) -- real berechnet aus Parzellengeometrie + Kennzahlen, keine
    Annahme und kein Dokumentzitat."""
    return Quellenobjekt(
        feld=feldname, wert=wert, quelle_typ=QUELLE_TYP_GEOMETRIE_BERECHNUNG,
        quelle_bezeichnung=herkunft, confidence="hoch",
    )


def quellen_aus_modul1_ergebnis(result: Dict[str, Any]) -> List[Quellenobjekt]:
    """Leitet aus einem fertigen `run_modul1(address)`-Ergebnis-Dict die
    vollstaendige, pro Feld aufgeschluesselte Quellenliste ab.

    Reine Nachbearbeitung: fragt nichts erneut ab, veraendert `result`
    nicht, und wird von `run_modul1()` selbst NICHT aufgerufen (additiv --
    modul1_geodata.py bleibt unveraendert, seine gruenen Regressionen
    bleiben gueltig). Jede verwendete URL/Layer-ID stammt entweder aus
    einer in modul1_geodata.py bereits existierenden Konstante oder direkt
    aus `result` selbst (z.B. `oereb.source_url`, das Modul 1 pro EGRID
    bereits real aufloest -- siehe get_oereb_data()).

    Enthaelt nur Eintraege fuer tatsaechlich ermittelte Werte. Ein
    "found": False (kein Treffer/keine Deckung) hat keinen amtlich
    ermittelten Wert und wird deshalb NICHT als Quellenobjekt gefuehrt --
    der Grund dafuer steht bereits transparent im jeweiligen "reason"-Feld
    des Original-Ergebnisses.

    Bekannte Luecke: `abgerufen_am` ist der Zeitpunkt dieses
    Ableitungsaufrufs, nicht der tatsaechliche Abrufzeitpunkt in
    run_modul1() -- Modul 1 speichert aktuell nur die Laufzeitdauer
    (`_meta.duration_seconds`), keinen absoluten Zeitstempel. Eine exakte
    Loesung braeuchte ein zusaetzliches `_meta`-Feld in run_modul1()
    selbst (siehe Bericht) und wurde hier bewusst NICHT als Aenderung an
    modul1_geodata.py umgesetzt."""
    quellen: List[Quellenobjekt] = []
    abgerufen_am = result.get("_meta", {}).get("abgerufen_am") or datetime.now().date().isoformat()

    geo = result.get("geocoding") or {}
    if geo.get("lv95_e") is not None and geo.get("lv95_n") is not None:
        quellen.append(aus_amtlichem_wert(
            "geocoding.lv95_koordinaten", {"lv95_e": geo["lv95_e"], "lv95_n": geo["lv95_n"]},
            quelle_bezeichnung=QUELLE_BEZEICHNUNG_GEOCODING, quelle_url=SEARCHSERVER_URL, abgerufen_am=abgerufen_am,
        ))
    if geo.get("matched_label"):
        quellen.append(aus_amtlichem_wert(
            "geocoding.matched_label", geo["matched_label"],
            quelle_bezeichnung=QUELLE_BEZEICHNUNG_GEOCODING, quelle_url=SEARCHSERVER_URL, abgerufen_am=abgerufen_am,
        ))

    kataster = result.get("kataster") or {}
    if kataster.get("found"):
        if kataster.get("egrid") is not None:
            quellen.append(aus_amtlichem_wert(
                "kataster.egrid", kataster["egrid"],
                quelle_bezeichnung=QUELLE_BEZEICHNUNG_KATASTER, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
            ))
        if kataster.get("parzellennummer") is not None:
            quellen.append(aus_amtlichem_wert(
                "kataster.parzellennummer", kataster["parzellennummer"],
                quelle_bezeichnung=QUELLE_BEZEICHNUNG_KATASTER, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
            ))
        if kataster.get("flaeche_m2") is not None:
            # flaeche_quelle unterscheidet zwei WIRKLICH verschiedene Herkuenfte
            # (AV-Attribut vs. selbst aus der Geometrie berechnet) -- beide
            # transparent als eigene, konkrete Bezeichnung statt vereinheitlicht.
            if kataster.get("flaeche_quelle") == "geometrie_berechnet":
                bezeichnung = f"{QUELLE_BEZEICHNUNG_PARZELLENGEOMETRIE} [Flaeche via Shoelace-Berechnung, AV-Attribut fehlte]"
            else:
                bezeichnung = f"{QUELLE_BEZEICHNUNG_KATASTER} [Flaeche direkt aus AV-Attribut]"
            quellen.append(aus_amtlichem_wert(
                "kataster.flaeche_m2", kataster["flaeche_m2"],
                quelle_bezeichnung=bezeichnung, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
            ))
        if kataster.get("parzellengeometrie"):
            quellen.append(aus_amtlichem_wert(
                "kataster.parzellengeometrie", f"{len(kataster['parzellengeometrie'])} Stuetzpunkte",
                quelle_bezeichnung=QUELLE_BEZEICHNUNG_PARZELLENGEOMETRIE, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
            ))

    gemeinde = result.get("gemeinde") or {}
    if gemeinde.get("found"):
        for feld in ("gemeinde", "kanton", "bfs_nummer"):
            if gemeinde.get(feld) is not None:
                quellen.append(aus_amtlichem_wert(
                    f"gemeinde.{feld}", gemeinde[feld],
                    quelle_bezeichnung=QUELLE_BEZEICHNUNG_GEMEINDE, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
                ))

    gwr = result.get("gwr") or {}
    if gwr.get("found"):
        for feld in (
            "egid", "baujahr", "anzahl_geschosse", "gebaeudekategorie_gkat",
            "gebaeudeklasse_gklas", "grundflaeche_m2", "energiebezugsflaeche_m2", "gebaeudevolumen_m3",
        ):
            if gwr.get(feld) is not None:
                quellen.append(aus_amtlichem_wert(
                    f"gwr.{feld}", gwr[feld],
                    quelle_bezeichnung=QUELLE_BEZEICHNUNG_GWR, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
                ))

    radon = result.get("radon") or {}
    if radon.get("found") and radon.get("wahrscheinlichkeit_prozent") is not None:
        quellen.append(aus_amtlichem_wert(
            "radon.wahrscheinlichkeit_prozent", radon["wahrscheinlichkeit_prozent"],
            quelle_bezeichnung=QUELLE_BEZEICHNUNG_RADON, quelle_url=MAPSERVER_IDENTIFY_URL, abgerufen_am=abgerufen_am,
        ))

    topo = result.get("topographie") or {}
    if topo.get("hoehe_m") is not None:
        quellen.append(aus_amtlichem_wert(
            "topographie.hoehe_m", topo["hoehe_m"],
            quelle_bezeichnung=QUELLE_BEZEICHNUNG_HOEHENMODELL, quelle_url=HEIGHT_URL, abgerufen_am=abgerufen_am,
        ))
    if topo.get("slope_deg") is not None:
        quellen.append(aus_amtlichem_wert(
            "topographie.hangneigung",
            {"slope_deg": topo["slope_deg"], "slope_pct": topo.get("slope_pct"), "aspect": topo.get("aspect")},
            quelle_bezeichnung=f"{QUELLE_BEZEICHNUNG_HOEHENMODELL} [aus 4-Punkt-Sampling abgeleitet, kein direkter Slope-Endpunkt]",
            quelle_url=HEIGHT_URL, abgerufen_am=abgerufen_am,
        ))

    umgebung = result.get("umgebung") or {}
    fehler = umgebung.get("fehler") or {}
    if umgebung.get("oev_naechste_haltestelle") and "oev_naechste_haltestelle" not in fehler:
        quellen.append(aus_amtlichem_wert(
            "umgebung.oev_naechste_haltestelle", umgebung["oev_naechste_haltestelle"],
            quelle_bezeichnung=QUELLE_BEZEICHNUNG_OEV, quelle_url=TRANSPORT_OPENDATA_URL, abgerufen_am=abgerufen_am,
        ))
    for feld in ("schule_naechste", "spital_naechstes", "supermarkt_naechster"):
        if umgebung.get(feld) and feld not in fehler:
            quellen.append(aus_amtlichem_wert(
                f"umgebung.{feld}", umgebung[feld],
                quelle_bezeichnung=QUELLE_BEZEICHNUNG_UMGEBUNG, quelle_url=OVERPASS_URL, abgerufen_am=abgerufen_am,
            ))

    oereb = result.get("oereb") or {}
    if oereb.get("found"):
        oereb_bezeichnung = f"OEREB-Webservice Kanton {oereb.get('kanton', '?')} (eCH-0122-Extrakt)"
        oereb_url = oereb.get("source_url")
        if oereb.get("amtliche_zonenbezeichnungen"):
            quellen.append(aus_amtlichem_wert(
                "oereb.amtliche_zonenbezeichnungen", oereb["amtliche_zonenbezeichnungen"],
                quelle_bezeichnung=oereb_bezeichnung, quelle_url=oereb_url, abgerufen_am=abgerufen_am,
            ))
        if oereb.get("rechtsvorschriften"):
            quellen.append(aus_amtlichem_wert(
                "oereb.rechtsvorschriften", f"{len(oereb['rechtsvorschriften'])} Dokument(e)",
                quelle_bezeichnung=oereb_bezeichnung, quelle_url=oereb_url, abgerufen_am=abgerufen_am,
            ))
        if oereb.get("umweltrisiken"):
            quellen.append(aus_amtlichem_wert(
                "oereb.umweltrisiken", oereb["umweltrisiken"],
                quelle_bezeichnung=oereb_bezeichnung, quelle_url=oereb_url, abgerufen_am=abgerufen_am,
            ))

    return quellen

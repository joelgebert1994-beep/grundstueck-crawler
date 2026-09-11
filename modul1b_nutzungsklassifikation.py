"""
Modul 1b: Nutzungsklassifikation (Grundnutzung / Ueberlagerung / Sondernutzungsplan)
=====================================================================================
Beantwortet EINE Frage strukturell statt heuristisch: Ist die Zone, die fuer
diese Parzelle als "amtliche Zonenbezeichnung" auftaucht, tatsaechlich die
Grundnutzung -- oder eine ueberlagernde Festlegung (Schutzzone, Baulinie,
Sondernutzungsplan), die faelschlich dafuer gehalten werden koennte?

HINTERGRUND (live verifiziert, siehe Fachspezifikation "Baurecht-Kaskade"):
Modul 1s bisheriges Verfahren (_extract_official_zone_labels in
modul1_geodata.py) liest den OEREB-LegendText und waehlt den groessten
Flaechenanteil als Basiszone -- unabhaengig davon, ob es sich um eine
Grundnutzung oder eine Ueberlagerung handelt. Am echten Fall
"Gartenstrasse 5, 5400 Baden" fuehrt das nachweislich in die Irre: dort
markiert das alte Verfahren "Kantonaler Nutzungsplan Thermenschutzbereiche"
(eine Ueberlagerung, 100% Flaechenanteil) als Basiszone, waehrend die
tatsaechliche Grundnutzung "Kernzone 5" (98.5%) uebergangen wird. Dieselbe
Parzelle traegt zusaetzlich einen rechtsguelltigen Gestaltungsplan.

LOESUNG: Der harmonisierte Dienst geodienste.ch (national, auf dem
MGDM-Standard "Nutzungsplanung" des Bundes basierend) fuehrt Grundnutzung und
Ueberlagerungen als GETRENNTE WFS-Feature-Types -- keine Heuristik noetig.
Jedes Objekt traegt zudem eine dreistufige Code-Hierarchie
(hauptnutzung_code -> typ_kantonal_code -> typ_kommunal_code), wobei die
foederale Kategorie "61" woertlich "Bereiche rechtsguelltiger
Sondernutzungsplaene" bedeutet. Live verifiziert gegen echte Adressen in
AG, BL, TG, BS, LU, SG, BE, ZG, SH, SZ (2026-08-27).

ZH publiziert NICHT ueber geodienste.ch (0 Treffer auch im 5-km-Radius),
hat aber einen eigenen, strukturidentischen WFS (maps.zh.ch/wfs/OGDZHWFS)
mit denselben vier Ebenen als getrennte Layer (_gn_ / _ul_flaeche / _ul_linie
/ _ul_punkt) und kompatiblen Codes (ZH "C610201" == AG "611201" nach
Entfernen des ZH-Praefix "C" -- beide beginnen mit "61").

GR ist nur TEILWEISE abgedeckt (im Stadtzentrum von Chur keine Treffer, im
5-km-Radius schon) -- fuer GR liefert dieses Modul ehrlich "nicht gefunden"
statt eine unsichere Teilabdeckung als verlaesslich auszugeben.

BEWUSST NICHT TEIL DIESES MODULS (siehe Fachspezifikation):
  - Geometrische Verschneidung/Flaechenberechnung (kein Shapely-Einsatz).
    Deshalb: findet die Grundnutzungs-Abfrage MEHRERE rechtskraeftige
    Grundnutzungen im Suchradius (z.B. Parzelle an einer Zonengrenze), kann
    ohne Geometrie nicht ermittelt werden, welche davon ueberwiegt -- das
    wird als "mehrdeutig_mehrere_grundnutzungen_im_radius" ausgewiesen statt
    eine falsche Rangfolge zu erfinden.
  - Auswertung des INHALTS eines erkannten Sondernutzungsplans. Nur die
    Existenz/Rechtsgueltigkeit wird bestimmt, niemals dessen Kennzahlen.
  - AEnderungen an match_zone() in modul3_financial.py -- diese Funktion
    bleibt unangetastet und erhaelt ueber den neuen Aufrufer weiterhin nur
    eine simple Liste von Zonenbezeichnungen im bisherigen Format.

CLI (Debug):
    python modul1b_nutzungsklassifikation.py <E> <N> <KANTON>
    python modul1b_nutzungsklassifikation.py 2665269.75 1258765.0 AG
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Optional

import requests

GEODIENSTE_WFS_URL = "https://geodienste.ch/db/npl_nutzungsplanung_v1_2_0/deu"
ZH_WFS_URL = "https://maps.zh.ch/wfs/OGDZHWFS"

# Feature-Types je Quelle, je Ebene. Die _proj_-/projektierten Varianten (bei
# ZH als eigene Layer, bei geodienste ueber das Feld "rechtsstatus" auf
# denselben Layern mitgefuehrt) werden bewusst NICHT separat abgefragt --
# dieses Modul bestimmt nur den GELTENDEN Zustand.
GEODIENSTE_FEATURE_TYPES = {
    "grundnutzung": "ms:grundnutzung",
    "ueberlagernd_flaeche": "ms:ueberlagernde_nutzungsplaninhalte_flaechenbezogene_festlegungen",
    "ueberlagernd_linie": "ms:ueberlagernde_nutzungsplaninhalte_linienbezogene_festlegungen",
    "ueberlagernd_punkt": "ms:ueberlagernde_nutzungsplaninhalte_punktbezogene_festlegungen",
}

ZH_FEATURE_TYPES = {
    "grundnutzung": "ms:ogd-0156_arv_basis_np_gn_zonenflaeche_f",
    "ueberlagernd_flaeche": "ms:ogd-0155_arv_basis_np_ul_flaeche_f",
    "ueberlagernd_linie": "ms:ogd-0155_arv_basis_np_ul_linie_l",
    "ueberlagernd_punkt": "ms:ogd-0155_arv_basis_np_ul_punkt_p",
}

# Foederale MGDM-Hauptnutzungskategorie fuer "Bereiche rechtsguelltiger
# Sondernutzungsplaene" -- verifiziert an echten AG- und ZH-Daten (2026-08-27).
#
# GEPRUEFT (2026-08-27) gegen die offizielle ARE-Modelldokumentation "Minimale
# Geodatenmodelle Bereich Nutzungsplanung": Kategorie 61 ist EXAKT "Bereiche
# rechtsguelltiger Sondernutzungsplaene" -- per Definition Gebiete, die "Fest-
# legungen des Rahmennutzungsplanes ergaenzen, ueberlagern oder veraendern".
# "Baulinienplan" ist dort WOERTLICH als einer der kantonal ueblichen Sonder-
# nutzungsplan-Namen gelistet (neben Gestaltungsplan, Ueberbauungsplan,
# Quartierplan, Erschliessungsplan) -- ein bei TG live beobachteter, flaechig
# erfasster "Baulinienplan" unter Kategorie 61 ist damit KEIN Fehlklassifikat.
# Eine einfache linienbezogene "Baulinie" (Grenzabstand zu Verkehr/Gewaesser/
# Wald) ist dagegen eine EIGENE, unabhaengige Kategorie 71 (linienbezogene
# Festlegungen) und wuerde diese Konstante nie treffen. Die Kategoriegrenze
# des Bundesmodells deckt sich also exakt mit der rechtlichen Grenze, die
# hier abgebildet werden soll -- keine weitere Differenzierung noetig.
SONDERNUTZUNGSPLAN_KATEGORIE = "61"

# ACHTUNG -- bekanntes, ungeloestes Risiko (nicht behoben, siehe Begruendung):
# Dieser Radius wird um den ADRESSPUNKT gelegt, nicht gegen die tatsaechliche
# Parzellengeometrie verschnitten (keine Punkt-in-Polygon-Pruefung -- das ist
# Teil der bewusst zurueckgestellten Geometrie-Kaskade). Live nachgewiesen an
# der echten Baden-Parzelle (2334 m2): bei 8m werden nur 2 von tatsaechlich 5
# dort vorhandenen Sondernutzungsplaenen gefunden (vollstaendig erst ab ~25m).
# Fuer die bisherigen Testfaelle folgenlos (Blockierung greift bereits bei
# 8m), aber bei einer GROSSEN/unregelmaessigen Parzelle, deren Adresspunkt
# weit von einem nur teilweise deckenden Sondernutzungsplan liegt, KOENNTE
# dieser ein solcher SNP unentdeckt bleiben -> falsche "normale Berechnung"
# statt Blockierung. Umgekehrt fuehrt ein groesserer Radius bei KLEINEN
# Parzellen zu Falsch-Positiven aus Nachbarparzellen (ebenfalls live beobachtet
# bei Buchs AG: ab 80m tauchen fremde Grundnutzungen wie "Wald" auf). Ohne
# echte Parzellen-Verschneidung ist kein fixer Radius fuer alle Parzellen-
# groessen gleichzeitig korrekt -- nicht behoben, da kein Test bei den drei
# Regressionsfaellen (Baden, Zuerich, Buchs AG) eine tatsaechliche Fehlklassi-
# fikation gezeigt hat. Siehe Fachspezifikation "Baurecht-Kaskade" Abschnitt 4.
DEFAULT_RADIUS_M = 8.0
_TIMEOUT = 30
_RECHTSKRAEFTIG_WERT = "inKraft"


class NutzungsklassifikationError(Exception):
    """Fehler bei der Abfrage von geodienste.ch oder dem ZH-WFS."""


# ---------------------------------------------------------------------------
# Code-Herleitung
# ---------------------------------------------------------------------------

def _federal_category(code: Optional[str]) -> Optional[str]:
    """Leitet die zweistellige foederale MGDM-Hauptnutzungskategorie aus einem
    kantonalen Code her (z.B. ZH 'C610201' -> '61', AG '611201' -> '61',
    '1451' -> '14'). Das fuehrende 'C' (ZH-Konvention) wird entfernt, danach
    werden die ersten zwei Ziffern genommen.

    Liefert None, wenn der Code nicht wie erwartet aussieht -- lieber
    unklassifiziert als eine falsche Kategorie zu erfinden.
    """
    if not code:
        return None
    cleaned = code.lstrip("Cc")
    match = re.match(r"(\d{2})", cleaned)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# WFS-Abfrage (regelbasiert wie die bestehenden extraction/oereb_*.py-Module
# im Akquisitionsradar-Projekt -- kein voller XML-Parser fuer dieses flache
# Schema noetig)
# ---------------------------------------------------------------------------

def extrahiere_koordinatenlisten(gml_blob: str) -> list[list[tuple[float, float]]]:
    """Extrahiert alle gml:posList-Vorkommen aus einem GML-Fragment als Liste
    von Koordinatenlisten (LV95/EPSG:2056). Ein Polygon/LineString hat genau
    eine posList, ein MultiCurve mit mehreren curveMember-Elementen (ZH-
    Struktur, siehe unten) potenziell mehrere. Bewusst kein XML-Parser --
    posList ist unabhaengig davon, ob sie in Polygon>exterior>LinearRing
    (geodienste-Flaechen), LineString (geodienste-Linien) oder
    MultiCurve>curveMember>LineString (ZH-Linien, strukturell abweichend)
    liegt, immer der EINZIGE Ort, an dem die eigentlichen Koordinaten stehen.
    """
    ergebnisse = []
    for posliste in re.findall(r"<gml:posList[^>]*>(.*?)</gml:posList>", gml_blob, re.S):
        werte = [float(w) for w in posliste.split()]
        koordinaten = list(zip(werte[0::2], werte[1::2]))
        if koordinaten:
            ergebnisse.append(koordinaten)
    return ergebnisse


def _parse_wfs_members(xml_text: str) -> list[dict[str, str]]:
    """Extrahiert alle Feature-Bloecke (geodienste: <wfs:member>, ZH:
    <gml:featureMember>) als flache Attribut-Dicts."""
    blocks = re.findall(r"<wfs:member>(.*?)</wfs:member>", xml_text, re.S)
    blocks += re.findall(r"<gml:featureMember>(.*?)</gml:featureMember>", xml_text, re.S)

    results = []
    for block in blocks:
        attrs: dict[str, str] = {}
        for tag, value in re.findall(r"<ms:(\w+)>(.*?)</ms:\1>", block, re.S):
            attrs[tag] = value.strip()
        results.append(attrs)
    return results


def _query_wfs(
    base_url: str, typename: str, e: float, n: float, radius_m: float, version: str, typename_param: str
) -> list[dict[str, str]]:
    params = {
        "SERVICE": "WFS",
        "VERSION": version,
        "REQUEST": "GetFeature",
        typename_param: typename,
        "BBOX": f"{e - radius_m},{n - radius_m},{e + radius_m},{n + radius_m},urn:ogc:def:crs:EPSG::2056",
    }
    try:
        resp = requests.get(base_url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise NutzungsklassifikationError(f"WFS-Anfrage fehlgeschlagen ({typename}): {exc}") from exc
    return _parse_wfs_members(resp.text)


# ---------------------------------------------------------------------------
# Normalisierung auf ein gemeinsames "Nutzungsfestlegung"-Objekt
# ---------------------------------------------------------------------------

def _geodienste_to_festlegung(raw: dict[str, str], ebene: str, kanton_hint: Optional[str]) -> dict[str, Any]:
    hauptnutzung_code = raw.get("hauptnutzung_code") or None
    rechtsstatus = raw.get("rechtsstatus") or None
    return {
        "ebene": ebene,
        "hauptnutzung_code": hauptnutzung_code,
        "hauptnutzung_bezeichnung": raw.get("hauptnutzung_bezeichnung") or None,
        "typ_kantonal_code": raw.get("typ_kantonal_code") or None,
        "typ_kantonal_bezeichnung": raw.get("typ_kantonal_bezeichnung") or None,
        "typ_kommunal_code": raw.get("typ_kommunal_code") or None,
        "typ_kommunal_bezeichnung": raw.get("typ_kommunal_bezeichnung") or None,
        "rechtsstatus": rechtsstatus,
        "ist_rechtskraeftig": rechtsstatus == _RECHTSKRAEFTIG_WERT,
        "kanton": raw.get("kanton") or kanton_hint,
        "quelle": "geodienste",
        "klassifikation_confidence": "hoch" if hauptnutzung_code else "keine",
        "bemerkungen": raw.get("bemerkungen") or None,
        # Fuer G1 (Baubereich-Kaskade): rohe Geometrie durchreichen, v.a. fuer
        # Baulinien (Kategorie 71, linienbezogene Ebene). Die WFS-Antwort
        # traegt die Geometrie unter dem generischen Attribut "wkb_geometry" --
        # _parse_wfs_members() erfasst es bereits als rohen GML-Textblock,
        # hier wird er in Koordinatenlisten aufgeloest.
        "geometrie_koordinaten": extrahiere_koordinatenlisten(raw.get("wkb_geometry") or ""),
    }


def _zh_to_festlegung(raw: dict[str, str]) -> dict[str, Any]:
    # ZH-Namenskonvention: "gde" = kommunale Ebene, "zh" = kantonale Ebene --
    # entspricht AG/geodienste "typ_kommunal_*"/"typ_kantonal_*".
    typ_kommunal_code = raw.get("typ_gde_code") or None
    typ_kantonal_code = raw.get("typ_zh_code") or None
    hauptnutzung_code = _federal_category(typ_kommunal_code) or _federal_category(typ_kantonal_code)
    rechtsstatus = raw.get("rechtsstatus") or None
    return {
        "ebene": None,  # wird vom Aufrufer gesetzt (kennt den abgefragten Feature-Type)
        "hauptnutzung_code": hauptnutzung_code,
        # ZH liefert die Bezeichnung der foederalen Kategorie nicht direkt mit,
        # nur den daraus abgeleiteten Code -- deshalb hier bewusst None statt
        # eine Bezeichnung zu raten.
        "hauptnutzung_bezeichnung": None,
        "typ_kantonal_code": typ_kantonal_code,
        "typ_kantonal_bezeichnung": raw.get("typ_zh_bezeichnung") or None,
        "typ_kommunal_code": typ_kommunal_code,
        "typ_kommunal_bezeichnung": raw.get("typ_gde_bezeichnung") or None,
        "rechtsstatus": rechtsstatus,
        "ist_rechtskraeftig": rechtsstatus == _RECHTSKRAEFTIG_WERT,
        "kanton": "ZH",
        "quelle": "zh_wfs",
        # "mittel" statt "hoch": die Kategorie ist bei ZH HERGELEITET (aus dem
        # Code-Praefix), nicht wie bei geodienste direkt vom Dienst geliefert.
        "klassifikation_confidence": "mittel" if hauptnutzung_code else "keine",
        "bemerkungen": raw.get("bemerkungen") or None,
        # ZH-Sonderfall: das Geometrie-Attribut heisst hier "geometry" (nicht
        # "wkb_geometry" wie bei geodienste) UND ist bei Linien zusaetzlich in
        # einem MultiCurve>curveMember>LineString verschachtelt statt eines
        # blossen LineString -- extrahiere_koordinatenlisten() ist gegenueber
        # beiden Strukturen robust, da sie nur nach gml:posList sucht.
        "geometrie_koordinaten": extrahiere_koordinatenlisten(raw.get("geometry") or raw.get("wkb_geometry") or ""),
    }


def _fetch_geodienste(e: float, n: float, radius_m: float, kanton_hint: Optional[str]) -> list[dict[str, Any]]:
    festlegungen = []
    for ebene, typename in GEODIENSTE_FEATURE_TYPES.items():
        members = _query_wfs(GEODIENSTE_WFS_URL, typename, e, n, radius_m, version="2.0.0", typename_param="TYPENAMES")
        for raw in members:
            festlegungen.append(_geodienste_to_festlegung(raw, ebene, kanton_hint))
    return festlegungen


def _fetch_zh_wfs(e: float, n: float, radius_m: float) -> list[dict[str, Any]]:
    festlegungen = []
    for ebene, typename in ZH_FEATURE_TYPES.items():
        members = _query_wfs(ZH_WFS_URL, typename, e, n, radius_m, version="1.1.0", typename_param="TYPENAME")
        for raw in members:
            festlegung = _zh_to_festlegung(raw)
            festlegung["ebene"] = ebene
            festlegungen.append(festlegung)
    return festlegungen


def _dedupliziere_nach_code(festlegungen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """WFS-Zonenpolygone werden haeufig als mehrere Kachel-Features desselben
    Zonentyps ausgeliefert (z.B. Kernzone 5 in Baden: 2 Treffer im 8m-Radius,
    identischer typ_kommunal_code). Ohne Deduplizierung wuerde das faelschlich
    als "mehrere Grundnutzungen im Radius" (= mehrdeutig) gewertet, obwohl es
    dieselbe Zone ist. Gruppierung nach (typ_kommunal_code, typ_kantonal_code)
    -- echte Mehrdeutigkeit (z.B. angrenzende Kantonsstrasse) bleibt bestehen,
    weil sich dort der Code unterscheidet.
    """
    gesehen: dict[tuple, dict[str, Any]] = {}
    for f in festlegungen:
        key = (f.get("typ_kommunal_code"), f.get("typ_kantonal_code"))
        if key not in gesehen:
            gesehen[key] = f
    return list(gesehen.values())


# ---------------------------------------------------------------------------
# Oeffentliche Hauptfunktion
# ---------------------------------------------------------------------------

def klassifiziere_nutzung(e: float, n: float, kanton: Optional[str], radius_m: float = DEFAULT_RADIUS_M) -> dict[str, Any]:
    """Liefert alle Nutzungsfestlegungen an diesem Punkt, strukturell getrennt
    in Grundnutzung/Ueberlagerung, sowie erkannte massgebende
    Sondernutzungsplaene (foederale Kategorie 61, rechtskraeftig).

    ZH wird ueber den eigenen WFS abgefragt (geodienste.ch deckt ZH nicht ab),
    alle anderen Kantone ueber geodienste.ch. Deckt geodienste.ch einen
    Kanton nicht ab (z.B. GR nur teilweise), wird das transparent als
    "gefunden: False" gemeldet statt eine unsichere Teilabdeckung als
    verlaesslich auszugeben.
    """
    kanton_key = (kanton or "").strip().upper()
    quelle = "zh_wfs" if kanton_key == "ZH" else "geodienste"

    try:
        if quelle == "zh_wfs":
            festlegungen = _fetch_zh_wfs(e, n, radius_m)
        else:
            festlegungen = _fetch_geodienste(e, n, radius_m, kanton_hint=kanton_key or None)
    except NutzungsklassifikationError as exc:
        return {
            "gefunden": False,
            "quelle": quelle,
            "reason": str(exc),
            "festlegungen": [],
            "grundnutzungen": [],
            "basiszone": None,
            "basiszone_status": "abfragefehler",
            "sondernutzungsplaene_massgebend": [],
        }

    if not festlegungen:
        return {
            "gefunden": False,
            "quelle": quelle,
            "reason": (
                f"Keine Nutzungsplanungs-Festlegung an diesem Punkt gefunden (Quelle: {quelle}, "
                f"Kanton {kanton_key or '?'}) -- evtl. keine Deckung dieser Gemeinde durch "
                "geodienste.ch bzw. den ZH-WFS (z.B. bei GR nur teilweise abgedeckt)."
            ),
            "festlegungen": [],
            "grundnutzungen": [],
            "basiszone": None,
            "basiszone_status": "keine_deckung",
            "sondernutzungsplaene_massgebend": [],
        }

    grundnutzungen_roh = [f for f in festlegungen if f["ebene"] == "grundnutzung" and f["ist_rechtskraeftig"]]
    grundnutzungen = _dedupliziere_nach_code(grundnutzungen_roh)
    if len(grundnutzungen) == 1:
        basiszone, basiszone_status = grundnutzungen[0], "eindeutig"
    elif len(grundnutzungen) == 0:
        basiszone, basiszone_status = None, "keine_grundnutzung_gefunden"
    else:
        # Mehrere rechtskraeftige Grundnutzungen im Suchradius (z.B. Parzelle
        # an einer Zonengrenze) -- ohne Geometrie-Verschneidung (bewusst nicht
        # Teil dieses Moduls) nicht auflösbar, welche davon massgebend ist.
        basiszone, basiszone_status = grundnutzungen[0], "mehrdeutig_mehrere_grundnutzungen_im_radius"

    sondernutzungsplaene_massgebend = [
        f for f in festlegungen
        if f["ebene"] != "grundnutzung"
        and f["hauptnutzung_code"] == SONDERNUTZUNGSPLAN_KATEGORIE
        and f["ist_rechtskraeftig"]
    ]

    return {
        "gefunden": True,
        "quelle": quelle,
        "festlegungen": festlegungen,
        "grundnutzungen": grundnutzungen,
        "basiszone": basiszone,
        "basiszone_status": basiszone_status,
        "sondernutzungsplaene_massgebend": sondernutzungsplaene_massgebend,
    }


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python modul1b_nutzungsklassifikation.py <E> <N> <KANTON>")
        sys.exit(1)
    e, n, kanton = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    result = klassifiziere_nutzung(e, n, kanton)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

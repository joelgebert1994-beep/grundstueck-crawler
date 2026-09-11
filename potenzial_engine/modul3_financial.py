"""
Modul 3: Financial Engine (SIA 416/BGF-Transformation, BKP 1-9, Residualwert)
================================================================================
Nimmt die Ergebnisse von Modul 1 (Parzelle/GWR-Bestand/amtliche Zone) und
Modul 2 (BZO-Zonenkennzahlen + Sonderregelungen) entgegen und berechnet:

  1. SIA-416/BGF-Transformationslogik: max. realisierbare BGF (Basis-AZ +
     parsebare Bonusziffern x Parzellenflaeche), Umrechnung BGF->NNF (81%
     Wirkungsgrad Wohnbau), grobe SIA-416-Volumenschaetzung, Delta zum
     GWR-Bestand inkl. Ersatzneubau/Aufstockung-Threshold.
  2. Dynamischer eBKP-H/BKP-1-9-Kostenrechner (Abbruch+Aushub, Hauptbaukosten
     nach Ausbaustandard, Umgebung, Baunebenkosten, Reserve).
  3. Schweizer Residualwert-/Margen-Engine (GDV ./. Baukosten ./. Marge).
  4. Szenarien-Matrix (Base Case / Optimistisch / Konservativ).

WICHTIGES DESIGNPRINZIP (konsistent mit Modul 1/2 und dem bestehenden
Akquisitionsradar-Projekt): registrierte FAKTEN (Parzellenflaeche, AZ aus der
BZO, GWR-Bestand) werden nie geraten -- fehlen sie, bricht die Berechnung mit
einer klaren Fehlermeldung ab, statt einen Platzhalter als "Ergebnis"
auszugeben. Kostenraten/Prozentsaetze (BKP-Ansaetze, Marge, Wirkungsgrad,
Reserve) sind dagegen MODELLANNAHMEN eines Schaetztools -- die sind bewusst
als explizite, ueberschreibbare Parameter mit SIA-orientierten Richtwerten
gestaltet und werden im Ergebnis unter "annahmen" immer vollstaendig
mitgeliefert, damit nichts unsichtbar angenommen wird.

Rechtlicher/fachlicher Hinweis: Dies ist eine Grobschaetzung (Vorprojekt-
Genauigkeit, SIA 102 Kostengenauigkeitsstufe +/-15-25%), keine Kostenplanung
und keine Bewertung nach anerkannten Bewertungsstandards (z.B. Fachempfehlung
SEK SVIT). Fuer Kaufentscheide durch einen Fachplaner/Bewerter verifizieren.

CLI:
    python modul3_financial.py --address "Bahnhofstrasse 1, 8001 Zuerich" --verkaufspreis-m2 14000
    python modul3_financial.py --parzelle-m2 500 --az 1.2 --bestand-bgf-m2 350 --verkaufspreis-m2 12000

Als Bibliothek:
    from potenzial_engine.modul3_financial import run_full_pipeline
    result = run_full_pipeline("Bahnhofstrasse 1, 8001 Zuerich", verkaufspreis_chf_pro_m2=14000)
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from typing import Any, Optional


class Modul3Error(Exception):
    """Fehler innerhalb der Financial-Engine (z.B. fehlende Pflichtdaten)."""


# ---------------------------------------------------------------------------
# Konstanten / SIA-orientierte Richtwerte (ueberschreibbar, siehe Funktionssignaturen)
# ---------------------------------------------------------------------------

NNF_WIRKUNGSGRAD_WOHNBAU = 0.81  # BGF -> NNF, Schweizer Standardwert Wohnbau
GESCHOSSHOEHE_M_DEFAULT = 3.0    # fuer grobe SIA-416-Volumenschaetzung

AUSBAUSTANDARD_CHF_PRO_M2_BGF = {
    "rendite": 2400,
    "gehoben": 3100,
    "luxus": 4200,
}

BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT = 50       # Richtwert Mitte 40-60 CHF/m3 Gebaeudevolumen
BKP1_AUSHUB_CHF_PRO_M3_DEFAULT = 30        # grober Richtwert Aushub, projektspezifisch stark abweichend
BKP1_AUSHUB_TIEFE_M_DEFAULT = 3.5          # typische UG-Aushubtiefe

BKP4_PROZENT_VON_BKP2_DEFAULT = 0.05       # Mitte 4-6%
BKP5_PROZENT_DEFAULT = 0.11                # Mitte 10-12%, auf BKP1+2+4

BKP9_PROZENT_BY_GENAUIGKEIT = {
    "grobkostenschaetzung": 0.15,  # Vorprojekt, SIA 102 Phase 31
    "kostenschaetzung": 0.10,      # Projektierung, SIA 102 Phase 32
    "kostenvoranschlag": 0.05,     # Bauprojekt, SIA 102 Phase 33
}

MARGE_PROZENT_VOM_GDV_DEFAULT = 0.15

# Delta-Schwellenwerte GWR-Bestand vs. Potenzial -> Ersatzneubau/Aufstockung
ERSATZNEUBAU_DELTA_SCHWELLE_DEFAULT = 0.40   # Potenzial >= 40% ueber Bestand -> Ersatzneubau pruefen
AUFSTOCKUNG_DELTA_SCHWELLE_DEFAULT = 0.20    # < 20% -> Aufstockung/Anbau meist ausreichend

ZONE_MATCH_MIN_SIMILARITY = 0.55  # difflib-Aehnlichkeitsschwelle fuer Zonen-Zuordnung


# ---------------------------------------------------------------------------
# 1. Zonen-Zuordnung: amtliche Zonenbezeichnung (Modul 1) <-> BZO-Zonentabelle (Modul 2)
# ---------------------------------------------------------------------------

def _normalize_zone_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


ZONE_MATCH_TIE_MARGIN = 0.03  # Kandidaten innerhalb dieses Abstands vom Top-Score gelten als gleichwertig


def match_zone(
    amtliche_zonenbezeichnungen: list[dict[str, Any]],
    erkannte_zonen: list[dict[str, Any]],
    min_similarity: float = ZONE_MATCH_MIN_SIMILARITY,
) -> dict[str, Any]:
    """Ordnet die amtliche (fuer DIE Parzelle rechtsverbindliche) Zonenbezeichnung
    aus Modul 1 einer der in Modul 2 aus der BZO extrahierten Zonendefinitionen zu.

    Nutzt die Basiszone (ist_wahrscheinlich_basiszone=True aus Modul 1) als
    Suchbegriff und difflib-Stringaehnlichkeit gegen alle erkannten Zonen aus
    Modul 2. Liefert KEINE Zuordnung, wenn die beste Uebereinstimmung unter
    min_similarity liegt -- lieber explizit "unsicher" melden als eine falsche
    Zone automatisch verwenden.

    WICHTIG (live entdeckt an einem echten ZH-Fall): Modul 1s amtliche
    Zonenbezeichnung kann unspezifischer sein als die BZO-Zonentabelle -- z.B.
    liefert das OEREB-LegendText nur "Kernzone", waehrend die BZO "Kernzone
    K2".."Kernzone K5" mit stark unterschiedlicher AZ (0.6 bis 1.7, fast das
    Dreifache) definiert. Ein simples "hoechster Score gewinnt" wuerde hier
    IMMER denselben (den zufaellig zuerst gelisteten) Subtyp waehlen und eine
    von vier moeglichen Zonen als "gefunden" ausgeben, obwohl alle vier
    identisch gut passen. Deshalb werden alle Kandidaten innerhalb von
    ZONE_MATCH_TIE_MARGIN vom Top-Score gesammelt; gibt es mehr als einen,
    ist die Zuordnung *per Definition* mehrdeutig und wird explizit als
    "mehrere_gleich_gute_kandidaten" gemeldet statt geraten.
    """
    if not amtliche_zonenbezeichnungen:
        return {"status": "keine_amtliche_zone", "zone": None, "aehnlichkeit": None}
    if not erkannte_zonen:
        return {"status": "keine_bzo_zonen", "zone": None, "aehnlichkeit": None}

    basiszone = next(
        (z for z in amtliche_zonenbezeichnungen if z.get("ist_wahrscheinlich_basiszone")),
        amtliche_zonenbezeichnungen[0],
    )
    target = _normalize_zone_name(basiszone["zonenbezeichnung"])

    scored = []
    for zone in erkannte_zonen:
        candidate = _normalize_zone_name(zone.get("zonenbezeichnung", ""))
        if not candidate:
            continue
        score = difflib.SequenceMatcher(None, target, candidate).ratio()
        # Substring-Bonus: das LLM formuliert Zonennamen von Lauf zu Lauf
        # unterschiedlich ("Kernzone K2" vs. "K2 (Kernzonen Baubereich)") --
        # reine SequenceMatcher-Aehnlichkeit reagiert empfindlich auf
        # Wortumstellung. Steckt der amtliche Name (>=5 Zeichen, um triviale
        # Kurzwoerter wie "zone" auszuschliessen) als Teilstring im Kandidaten
        # (oder umgekehrt), ist das ein starkes Signal unabhaengig von der
        # Reihenfolge -- deckt auch deutsche Singular/Plural-Varianten ab
        # ("kernzone" in "kernzonen"). Bleibt trotzdem ueber die
        # Tie-Erkennung unten sicher, wenn mehrere Kandidaten gleichermassen
        # zutreffen (z.B. alle vier Kernzone-Subtypen).
        if len(target) >= 5 and (target in candidate or candidate in target):
            score = max(score, 0.9)
        scored.append((score, zone))

    if not scored:
        return {"status": "keine_bzo_zonen", "zone": None, "aehnlichkeit": None}

    best_score = max(s for s, _ in scored)
    if best_score < min_similarity:
        return {
            "status": "unsicher",
            "amtliche_zonenbezeichnung": basiszone["zonenbezeichnung"],
            "beste_kandidatin": max(scored, key=lambda t: t[0])[1].get("zonenbezeichnung"),
            "aehnlichkeit": round(best_score, 2),
            "zone": None,
            "hinweis": "Automatische Zonenzuordnung unsicher -- manuell mit der BZO abgleichen.",
        }

    top_tied = [z for s, z in scored if s >= best_score - ZONE_MATCH_TIE_MARGIN]
    if len(top_tied) > 1:
        return {
            "status": "mehrere_gleich_gute_kandidaten",
            "amtliche_zonenbezeichnung": basiszone["zonenbezeichnung"],
            "aehnlichkeit": round(best_score, 2),
            "zone": None,
            "kandidaten": [
                {"zonenbezeichnung": z.get("zonenbezeichnung"), "ausnuetzungsziffer_az": _kennzahl_wert(z.get("ausnuetzungsziffer_az"))}
                for z in top_tied
            ],
            "hinweis": (
                f"Die amtliche Zonenbezeichnung {basiszone['zonenbezeichnung']!r} ist nicht spezifisch "
                f"genug, um zwischen {len(top_tied)} gleich gut passenden BZO-Zonen zu unterscheiden -- "
                "amtlichen Zonenplan der Gemeinde konsultieren, um den exakten Subtyp zu bestimmen."
            ),
        }

    return {
        "status": "gefunden",
        "amtliche_zonenbezeichnung": basiszone["zonenbezeichnung"],
        "aehnlichkeit": round(best_score, 2),
        "zone": top_tied[0],
    }


# ---------------------------------------------------------------------------
# 2. Bonus-Parsing: Sonderregelungen (Modul 2) -> numerische AZ-Zuschlaege
# ---------------------------------------------------------------------------

_PERCENT_BONUS_RE = re.compile(r"\+?\s*(\d+(?:[.,]\d+)?)\s*%")


def parse_applicable_boni(
    sonderregelungen: list[dict[str, Any]],
    zonenbezeichnung: Optional[str],
) -> dict[str, Any]:
    """Filtert Sonderregelungen aus Modul 2 auf die uebergebene Zone (oder
    zonenuebergreifende Regeln) und extrahiert daraus, wo eindeutig moeglich,
    einen numerischen Prozent-Bonus auf die AZ.

    Nur klar als "+X%" (oder "X%") erkennbare bonus_effekt-Texte werden
    automatisch verrechnet. Alles andere (z.B. "zusaetzliches Vollgeschoss
    anrechenbar", nicht-numerische Beschreibungen) wird separat als
    "nicht_automatisch_verrechnet" ausgewiesen -- lieber eine Regel dem Nutzer
    zur manuellen Pruefung vorlegen, als einen Bonus-Wert zu erfinden.
    """
    applicable = [
        s for s in sonderregelungen
        if not s.get("gilt_fuer_zonen") or (zonenbezeichnung and zonenbezeichnung in s["gilt_fuer_zonen"])
    ]

    parsed_boni = []
    manual_review = []
    for regel in applicable:
        effekt = regel.get("bonus_effekt") or ""
        match = _PERCENT_BONUS_RE.search(effekt)
        if match:
            prozent = float(match.group(1).replace(",", ".")) / 100.0
            parsed_boni.append({
                "titel": regel.get("titel"),
                "typ": regel.get("typ"),
                "bonus_az_prozent": prozent,
                "artikel_referenz": regel.get("artikel_referenz"),
            })
        else:
            manual_review.append({
                "titel": regel.get("titel"),
                "typ": regel.get("typ"),
                "beschreibung": regel.get("beschreibung"),
                "bonus_effekt_text": regel.get("bonus_effekt"),
                "artikel_referenz": regel.get("artikel_referenz"),
            })

    total_bonus_prozent = sum(b["bonus_az_prozent"] for b in parsed_boni)
    return {
        "automatisch_verrechnete_boni": parsed_boni,
        "summe_bonus_az_prozent": round(total_bonus_prozent, 4),
        "nicht_automatisch_verrechnet": manual_review,
    }


# ---------------------------------------------------------------------------
# 3. SIA-416/BGF-Transformationslogik
# ---------------------------------------------------------------------------

def calculate_bgf_transformation(
    parzellenflaeche_m2: float,
    basis_az: float,
    bonus_az_prozent: float,
    bestand_bgf_m2: Optional[float] = None,
    bestand_volumen_m3: Optional[float] = None,
    geschosshoehe_m: float = GESCHOSSHOEHE_M_DEFAULT,
    nnf_wirkungsgrad: float = NNF_WIRKUNGSGRAD_WOHNBAU,
    ersatzneubau_schwelle: float = ERSATZNEUBAU_DELTA_SCHWELLE_DEFAULT,
    aufstockung_schwelle: float = AUFSTOCKUNG_DELTA_SCHWELLE_DEFAULT,
) -> dict[str, Any]:
    """SIA-416/BGF-Transformation: Basis-AZ + Bonus -> max. realisierbare BGF
    -> NNF -> grobe Volumenschaetzung -> Delta zum GWR-Bestand mit
    Ersatzneubau/Aufstockung-Empfehlung.
    """
    if parzellenflaeche_m2 is None or parzellenflaeche_m2 <= 0:
        raise Modul3Error("Parzellenflaeche fehlt oder ist <= 0 -- BGF-Berechnung nicht moeglich.")
    if basis_az is None or basis_az <= 0:
        raise Modul3Error("Basis-Ausnuetzungsziffer (AZ) fehlt oder ist <= 0 -- BGF-Berechnung nicht moeglich.")

    effektive_az = basis_az * (1 + bonus_az_prozent)
    max_bgf_m2 = round(parzellenflaeche_m2 * effektive_az, 1)
    realisierbare_nnf_m2 = round(max_bgf_m2 * nnf_wirkungsgrad, 1)
    sia416_volumen_m3 = round(max_bgf_m2 * geschosshoehe_m, 1)

    result: dict[str, Any] = {
        "parzellenflaeche_m2": parzellenflaeche_m2,
        "basis_az": basis_az,
        "bonus_az_prozent": bonus_az_prozent,
        "effektive_az": round(effektive_az, 4),
        "max_realisierbare_bgf_m2": max_bgf_m2,
        "realisierbare_nnf_m2": realisierbare_nnf_m2,
        "nnf_wirkungsgrad": nnf_wirkungsgrad,
        "sia416_gebaeudevolumen_m3_schaetzung": sia416_volumen_m3,
        "geschosshoehe_m_annahme": geschosshoehe_m,
        "delta_zum_bestand": None,
    }

    if bestand_bgf_m2 is not None and bestand_bgf_m2 > 0:
        delta_m2 = round(max_bgf_m2 - bestand_bgf_m2, 1)
        delta_prozent = round(delta_m2 / bestand_bgf_m2, 4)

        if delta_prozent >= ersatzneubau_schwelle:
            empfehlung = "ersatzneubau_pruefen"
            begruendung = (
                f"Potenzial liegt {delta_prozent:.0%} ueber dem Bestand (Schwelle "
                f"{ersatzneubau_schwelle:.0%}) -- Bestand nutzt die Parzelle stark "
                "unter, Ersatzneubau wirtschaftlich naheliegend."
            )
        elif delta_prozent < aufstockung_schwelle:
            empfehlung = "aufstockung_anbau_ausreichend"
            begruendung = (
                f"Potenzial liegt nur {delta_prozent:.0%} ueber dem Bestand (Schwelle "
                f"{aufstockung_schwelle:.0%}) -- Aufstockung/Anbau duerfte das "
                "Potenzial bereits weitgehend ausschoepfen."
            )
        else:
            empfehlung = "einzelfallpruefung"
            begruendung = (
                f"Potenzial liegt {delta_prozent:.0%} ueber dem Bestand -- im "
                "Schwellenbereich zwischen Aufstockung und Ersatzneubau, "
                "Einzelfallpruefung noetig (Statik, Denkmalschutz, Wirtschaftlichkeit)."
            )

        result["delta_zum_bestand"] = {
            "bestand_bgf_m2": bestand_bgf_m2,
            "bestand_volumen_m3": bestand_volumen_m3,
            "delta_bgf_m2": delta_m2,
            "delta_prozent": delta_prozent,
            "empfehlung": empfehlung,
            "begruendung": begruendung,
            "schwellenwerte_verwendet": {
                "ersatzneubau_ab_delta_prozent": ersatzneubau_schwelle,
                "aufstockung_bis_delta_prozent": aufstockung_schwelle,
            },
        }

    return result


# ---------------------------------------------------------------------------
# 4. Dynamischer eBKP-H / BKP 1-9 Kostenrechner
# ---------------------------------------------------------------------------

def calculate_bkp_costs(
    neue_bgf_m2: float,
    ausbaustandard: str,
    ersatzneubau: bool,
    bestand_volumen_m3: Optional[float] = None,
    kostengenauigkeit: str = "kostenschaetzung",
    abbruch_chf_pro_m3: float = BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT,
    aushub_chf_pro_m3: float = BKP1_AUSHUB_CHF_PRO_M3_DEFAULT,
    aushub_tiefe_m: float = BKP1_AUSHUB_TIEFE_M_DEFAULT,
    bkp2_chf_pro_m2: Optional[float] = None,
    bkp4_prozent: float = BKP4_PROZENT_VON_BKP2_DEFAULT,
    bkp5_prozent: float = BKP5_PROZENT_DEFAULT,
    bkp9_prozent: Optional[float] = None,
) -> dict[str, Any]:
    """BKP 1-9 Kostenschaetzung. Alle Ansaetze sind Modellannahmen (siehe
    Moduldocstring) und werden vollstaendig im Rueckgabewert unter 'annahmen'
    dokumentiert.

    ausbaustandard: "rendite" | "gehoben" | "luxus" (siehe AUSBAUSTANDARD_CHF_PRO_M2_BGF)
    kostengenauigkeit: "grobkostenschaetzung" | "kostenschaetzung" | "kostenvoranschlag"
        steuert die BKP-9-Reserve, falls bkp9_prozent nicht explizit gesetzt ist.
    """
    if ausbaustandard not in AUSBAUSTANDARD_CHF_PRO_M2_BGF and bkp2_chf_pro_m2 is None:
        raise Modul3Error(
            f"Unbekannter ausbaustandard {ausbaustandard!r} -- "
            f"erlaubt: {list(AUSBAUSTANDARD_CHF_PRO_M2_BGF)} oder bkp2_chf_pro_m2 explizit setzen."
        )
    if bkp9_prozent is None:
        if kostengenauigkeit not in BKP9_PROZENT_BY_GENAUIGKEIT:
            raise Modul3Error(
                f"Unbekannte kostengenauigkeit {kostengenauigkeit!r} -- "
                f"erlaubt: {list(BKP9_PROZENT_BY_GENAUIGKEIT)} oder bkp9_prozent explizit setzen."
            )
        bkp9_prozent = BKP9_PROZENT_BY_GENAUIGKEIT[kostengenauigkeit]

    bkp2_rate = bkp2_chf_pro_m2 if bkp2_chf_pro_m2 is not None else AUSBAUSTANDARD_CHF_PRO_M2_BGF[ausbaustandard]

    # BKP 1: Abbruch (nur bei Ersatzneubau) + Aushub (immer, Neubau braucht Baugrube)
    abbruch_chf = 0.0
    if ersatzneubau and bestand_volumen_m3:
        abbruch_chf = round(bestand_volumen_m3 * abbruch_chf_pro_m3, 0)
    aushub_volumen_m3 = round(neue_bgf_m2 * aushub_tiefe_m, 1)
    aushub_chf = round(aushub_volumen_m3 * aushub_chf_pro_m3, 0)
    bkp1_chf = abbruch_chf + aushub_chf

    # BKP 2: Hauptbaukosten
    bkp2_chf = round(neue_bgf_m2 * bkp2_rate, 0)

    # BKP 4: Umgebung
    bkp4_chf = round(bkp2_chf * bkp4_prozent, 0)

    # BKP 5: Baunebenkosten/Honorare (SIA 102/103), auf BKP1+2+4
    subtotal_1_2_4 = bkp1_chf + bkp2_chf + bkp4_chf
    bkp5_chf = round(subtotal_1_2_4 * bkp5_prozent, 0)

    # BKP 9: Reserve/Unvorhergesehenes, auf BKP1+2+4+5
    subtotal_1_2_4_5 = subtotal_1_2_4 + bkp5_chf
    bkp9_chf = round(subtotal_1_2_4_5 * bkp9_prozent, 0)

    gesamtbaukosten_chf = subtotal_1_2_4_5 + bkp9_chf

    return {
        "bkp1_abbruch_aushub_chf": bkp1_chf,
        "bkp1_detail": {"abbruch_chf": abbruch_chf, "aushub_chf": aushub_chf, "aushub_volumen_m3": aushub_volumen_m3},
        "bkp2_hauptbaukosten_chf": bkp2_chf,
        "bkp4_umgebung_chf": bkp4_chf,
        "bkp5_baunebenkosten_chf": bkp5_chf,
        "bkp9_reserve_chf": bkp9_chf,
        "gesamtbaukosten_bkp1_9_chf": round(gesamtbaukosten_chf, 0),
        "annahmen": {
            "ausbaustandard": ausbaustandard if bkp2_chf_pro_m2 is None else "manuell",
            "bkp2_chf_pro_m2_bgf": bkp2_rate,
            "abbruch_chf_pro_m3": abbruch_chf_pro_m3,
            "aushub_chf_pro_m3": aushub_chf_pro_m3,
            "aushub_tiefe_m": aushub_tiefe_m,
            "bkp4_prozent_von_bkp2": bkp4_prozent,
            "bkp5_prozent": bkp5_prozent,
            "bkp9_prozent": bkp9_prozent,
            "kostengenauigkeit": kostengenauigkeit,
        },
    }


# ---------------------------------------------------------------------------
# 5. Residualwert-/Margen-Engine
# ---------------------------------------------------------------------------

def calculate_residual_value(
    realisierbare_nnf_m2: float,
    verkaufspreis_chf_pro_m2: float,
    gesamtbaukosten_chf: float,
    marge_prozent_vom_gdv: float = MARGE_PROZENT_VOM_GDV_DEFAULT,
) -> dict[str, Any]:
    """Schweizer Residualwertmethode: GDV ./. Baukosten ./. Entwicklermarge = max. Landkaufpreis."""
    if verkaufspreis_chf_pro_m2 is None or verkaufspreis_chf_pro_m2 <= 0:
        raise Modul3Error(
            "verkaufspreis_chf_pro_m2 fehlt oder ist <= 0 -- ohne einen begruendeten "
            "Marktpreis (z.B. Wueest Partner/Vergleichstransaktionen) wird hier bewusst "
            "kein Residualwert berechnet, statt einen erfundenen Wert auszugeben."
        )

    gdv_chf = round(realisierbare_nnf_m2 * verkaufspreis_chf_pro_m2, 0)
    marge_chf = round(gdv_chf * marge_prozent_vom_gdv, 0)
    residualwert_chf = round(gdv_chf - gesamtbaukosten_chf - marge_chf, 0)

    return {
        "gdv_soll_erloes_chf": gdv_chf,
        "verkaufspreis_chf_pro_m2_nnf": verkaufspreis_chf_pro_m2,
        "gesamtbaukosten_chf": gesamtbaukosten_chf,
        "marge_prozent_vom_gdv": marge_prozent_vom_gdv,
        "marge_chf": marge_chf,
        "residualwert_max_landkaufpreis_chf": residualwert_chf,
        "residualwert_negativ": residualwert_chf < 0,
    }


# ---------------------------------------------------------------------------
# 6. Gesamtberechnung fuer EIN Szenario
# ---------------------------------------------------------------------------

def run_scenario(
    parzellenflaeche_m2: float,
    basis_az: float,
    bonus_az_prozent: float,
    ausbaustandard: str,
    verkaufspreis_chf_pro_m2: float,
    bestand_bgf_m2: Optional[float] = None,
    bestand_volumen_m3: Optional[float] = None,
    marge_prozent_vom_gdv: float = MARGE_PROZENT_VOM_GDV_DEFAULT,
    kostengenauigkeit: str = "kostenschaetzung",
    **bgf_und_bkp_overrides: Any,
) -> dict[str, Any]:
    bgf = calculate_bgf_transformation(
        parzellenflaeche_m2=parzellenflaeche_m2,
        basis_az=basis_az,
        bonus_az_prozent=bonus_az_prozent,
        bestand_bgf_m2=bestand_bgf_m2,
        bestand_volumen_m3=bestand_volumen_m3,
        **{k: v for k, v in bgf_und_bkp_overrides.items() if k in (
            "geschosshoehe_m", "nnf_wirkungsgrad", "ersatzneubau_schwelle", "aufstockung_schwelle"
        )},
    )

    ersatzneubau = bool(
        bgf["delta_zum_bestand"] and bgf["delta_zum_bestand"]["empfehlung"] == "ersatzneubau_pruefen"
    )

    bkp = calculate_bkp_costs(
        neue_bgf_m2=bgf["max_realisierbare_bgf_m2"],
        ausbaustandard=ausbaustandard,
        ersatzneubau=ersatzneubau,
        bestand_volumen_m3=bestand_volumen_m3,
        kostengenauigkeit=kostengenauigkeit,
        **{k: v for k, v in bgf_und_bkp_overrides.items() if k in (
            "abbruch_chf_pro_m3", "aushub_chf_pro_m3", "aushub_tiefe_m",
            "bkp2_chf_pro_m2", "bkp4_prozent", "bkp5_prozent", "bkp9_prozent",
        )},
    )

    residualwert = calculate_residual_value(
        realisierbare_nnf_m2=bgf["realisierbare_nnf_m2"],
        verkaufspreis_chf_pro_m2=verkaufspreis_chf_pro_m2,
        gesamtbaukosten_chf=bkp["gesamtbaukosten_bkp1_9_chf"],
        marge_prozent_vom_gdv=marge_prozent_vom_gdv,
    )

    return {"sia416_bgf": bgf, "bkp_kosten": bkp, "residualwert": residualwert}


# ---------------------------------------------------------------------------
# 7. Szenarien-Matrix
# ---------------------------------------------------------------------------

def run_scenario_matrix(
    parzellenflaeche_m2: float,
    basis_az: float,
    bonus_az_prozent: float,
    verkaufspreis_chf_pro_m2: float,
    bestand_bgf_m2: Optional[float] = None,
    bestand_volumen_m3: Optional[float] = None,
) -> dict[str, Any]:
    """Base Case / Optimistisch / Konservativ -- variiert Ausbaustandard,
    Bonus-Beruecksichtigung, Kostengenauigkeits-Reserve und Marge-Erwartung.
    """
    szenarien = {
        "konservativ": dict(
            bonus_az_prozent=0.0,  # keine Boni angenommen, nur Basis-AZ
            ausbaustandard="rendite",
            kostengenauigkeit="grobkostenschaetzung",  # hoehere Reserve (15%)
            marge_prozent_vom_gdv=0.18,
        ),
        "base_case": dict(
            bonus_az_prozent=bonus_az_prozent / 2,  # nur die Haelfte der Boni als gesichert angenommen
            ausbaustandard="gehoben",
            kostengenauigkeit="kostenschaetzung",
            marge_prozent_vom_gdv=0.15,
        ),
        "optimistisch": dict(
            bonus_az_prozent=bonus_az_prozent,  # alle automatisch parsebaren Boni voll angerechnet
            ausbaustandard="gehoben",
            kostengenauigkeit="kostenvoranschlag",  # niedrigere Reserve (5%)
            marge_prozent_vom_gdv=0.12,
        ),
    }

    results = {}
    for name, params in szenarien.items():
        results[name] = run_scenario(
            parzellenflaeche_m2=parzellenflaeche_m2,
            basis_az=basis_az,
            verkaufspreis_chf_pro_m2=verkaufspreis_chf_pro_m2,
            bestand_bgf_m2=bestand_bgf_m2,
            bestand_volumen_m3=bestand_volumen_m3,
            **params,
        )
    return results


# ---------------------------------------------------------------------------
# 8. Orchestrierung: Modul 1 -> Modul 2 -> Modul 3
# ---------------------------------------------------------------------------

def _kennzahl_wert(v: Any) -> Any:
    """Liest 'wert' aus einer Modul-2-Kennzahl (Schema mit wert/einheit/
    confidence/bedingungen/...) ODER akzeptiert weiterhin eine blosse Zahl
    (altes flaches Schema, z.B. synthetische Testdaten in
    test_klassifikation.py) -- reine Abwaertskompatibilitaet, keine neue
    Berechnungslogik. match_zone()/die Szenarien-Rechnung selbst bleiben
    unveraendert."""
    return v.get("wert") if isinstance(v, dict) else v


def _zone_basis_az(zone: dict[str, Any]) -> Optional[float]:
    return _kennzahl_wert(zone.get("ausnuetzungsziffer_az")) or _kennzahl_wert(zone.get("anrechenbare_geschossflaechenziffer_abgf"))


def _run_for_zone(
    zone: dict[str, Any],
    parzellenflaeche_m2: float,
    modul2_result: dict[str, Any],
    modul1_result: dict[str, Any],
    verkaufspreis_chf_pro_m2: float,
) -> dict[str, Any]:
    """Fuehrt Bonus-Parsing + Szenarien-Matrix fuer EINE konkrete Zone aus.
    Extrahiert aus run_from_modul_results(), damit dieselbe Rechnung sowohl
    fuer eine eindeutig gefundene Zone als auch -- im Bandbreiten-Fall --
    mehrfach fuer verschiedene Kandidaten-Zonen wiederverwendet werden kann.
    """
    basis_az = _zone_basis_az(zone)
    if basis_az is None:
        raise Modul3Error(
            f"Zone {zone.get('zonenbezeichnung')!r} hat weder AZ noch aBGF in Modul 2s "
            "Extraktion -- Berechnung nicht moeglich (evtl. BMZ-basierte Zone, siehe 'bmz')."
        )

    boni = parse_applicable_boni(modul2_result.get("sonderregelungen", []), zone.get("zonenbezeichnung"))

    gwr = modul1_result.get("gwr", {})
    bestand_bgf_m2 = gwr.get("energiebezugsflaeche_m2") if gwr.get("found") else None
    bestand_volumen_m3 = gwr.get("gebaeudevolumen_m3") if gwr.get("found") else None

    szenarien = run_scenario_matrix(
        parzellenflaeche_m2=parzellenflaeche_m2,
        basis_az=basis_az,
        bonus_az_prozent=boni["summe_bonus_az_prozent"],
        verkaufspreis_chf_pro_m2=verkaufspreis_chf_pro_m2,
        bestand_bgf_m2=bestand_bgf_m2,
        bestand_volumen_m3=bestand_volumen_m3,
    )

    return {
        "zone": zone,
        "boni_verrechnung": boni,
        "gwr_bestand_referenz": {
            "energiebezugsflaeche_m2": bestand_bgf_m2,
            "gebaeudevolumen_m3": bestand_volumen_m3,
            "baujahr": gwr.get("baujahr"),
        },
        "szenarien": szenarien,
    }


def _ermittle_basiszone_bezeichnung(modul1_result: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Liefert die Eingabe fuer match_zone() (Format wie bisher:
    amtliche_zonenbezeichnungen-Liste) sowie die verwendete Quelle.

    Bevorzugt die Nutzungsklassifikation aus Modul 1b (geodienste.ch/ZH-WFS),
    weil sie Grundnutzung strukturell von Ueberlagerungen trennt -- das
    aeltere OEREB-LegendText-Verfahren (amtliche_zonenbezeichnungen) waehlt
    stattdessen den groessten Flaechenanteil und kann dabei faelschlich eine
    Ueberlagerung als Basiszone waehlen (live entdeckt an
    "Gartenstrasse 5, 5400 Baden": dort waere "Kantonaler Nutzungsplan
    Thermenschutzbereiche" statt "Kernzone 5" gewaehlt worden). Faellt auf
    das alte Verfahren zurueck, wenn Modul 1b keine eindeutige Grundnutzung
    liefert (z.B. Kanton ohne geodienste.ch-/ZH-WFS-Abdeckung wie GR, SG).
    """
    klass = modul1_result.get("nutzungsklassifikation", {})
    if klass.get("gefunden") and klass.get("basiszone_status") == "eindeutig":
        basiszone = klass["basiszone"]
        bezeichnung = basiszone.get("typ_kommunal_bezeichnung") or basiszone.get("typ_kantonal_bezeichnung")
        if bezeichnung:
            return [{"zonenbezeichnung": bezeichnung, "ist_wahrscheinlich_basiszone": True}], "nutzungsklassifikation"

    return modul1_result.get("oereb", {}).get("amtliche_zonenbezeichnungen", []), "oereb_legendtext_fallback"


def ermittle_zonenzuordnung(modul1_result: dict[str, Any], modul2_result: dict[str, Any]) -> dict[str, Any]:
    """Ermittelt, OHNE Verkaufspreis, ob und welche Modul-2-BZO-Zone fuer
    dieses Grundstueck amtlich gilt. Reine Auslagerung aus
    run_from_modul_results() (identisches Verhalten, keine Aenderung an der
    Fachlogik) -- macht die Zonenzuordnung/BZO-Kennzahlen unabhaengig von
    der Finanzrechnung nutzbar (die Finanzrechnung braucht einen Preis,
    die Zonenzuordnung selbst nie).

    Liefert entweder
      - {"status": "sondernutzungsplan_massgebend", "sondernutzungsplaene": [...], "hinweis": ...}
      - oder das zone_match-Dict von match_zone() (Status "gefunden",
        "mehrere_gleich_gute_kandidaten", "keine_amtliche_zone",
        "keine_bzo_zonen" etc.), ergaenzt um "basiszone_quelle".
    """
    klassifikation = modul1_result.get("nutzungsklassifikation", {})
    sondernutzungsplaene = klassifikation.get("sondernutzungsplaene_massgebend", []) if klassifikation.get("gefunden") else []
    if sondernutzungsplaene:
        return {
            "status": "sondernutzungsplan_massgebend",
            "sondernutzungsplaene": sondernutzungsplaene,
            "hinweis": (
                "Diese Parzelle liegt in einem rechtsgueltigen Sondernutzungs-/"
                "Gestaltungsplan-Perimeter (foederale MGDM-Kategorie 61). Der "
                "Planinhalt kann von der ordentlichen Bau- und Zonenordnung "
                "abweichen und wird von dieser Engine nicht automatisiert "
                "ausgewertet -- eine aus der ordentlichen Zone abgeleitete "
                "Potenzialzahl waere hier nicht belastbar. Planinhalt anhand "
                "der Rechtsgrundlagen im OEREB-Auszug manuell pruefen."
            ),
        }

    amtliche_zonenbezeichnungen, basiszone_quelle = _ermittle_basiszone_bezeichnung(modul1_result)
    zone_match = match_zone(amtliche_zonenbezeichnungen, modul2_result.get("erkannte_zonen", []))
    zone_match["basiszone_quelle"] = basiszone_quelle
    return zone_match


def run_from_modul_results(
    modul1_result: dict[str, Any],
    modul2_result: dict[str, Any],
    verkaufspreis_chf_pro_m2: float,
) -> dict[str, Any]:
    """Nimmt die fertigen Ergebnisse von Modul 1 und Modul 2 entgegen und
    fuehrt die komplette Szenarien-Matrix aus. Bricht mit Modul3Error ab, wenn
    Pflichtdaten (Parzellenflaeche) fehlen -- rechnet nie mit geratenen Werten
    weiter.

    Sonderfall "mehrere_gleich_gute_kandidaten" (siehe match_zone()): es gibt
    Faelle (z.B. Zuerich Kernzone K2-K5), in denen selbst der detaillierteste
    verfuegbare amtliche GIS-Layer den exakten Zonen-Subtyp NICHT maschinen-
    lesbar ausweist -- verifiziert am 2026-08-26 gegen den ZH-WFS-Layer
    ogd-0156_arv_basis_np_gn_zonenflaeche_f: fuer Kernzonen sind dort ALLE
    Kennzahlenfelder (ausnuetzungsziffer_min/max etc.) bewusst leer, mit dem
    Vermerk "siehe gueltige Bau- und Zonenordnung". Es gibt in diesem Fall
    keine Quelle, aus der sich der Subtyp automatisch UND korrekt ableiten
    liesse -- eine einzelne Zahl auszugeben waere Raten, keine Berechnung.
    Statt hart abzubrechen, wird deshalb eine Bandbreite ueber ALLE
    gleichwertigen Kandidaten gerechnet (System zeigt Minimum, Maximum und
    alle Zwischenwerte transparent, mit dem Hinweis, welcher Subtyp per
    amtlichem Zonenplan manuell zu bestaetigen ist).

    Sonderfall "sondernutzungsplan_massgebend" (Modul 1b, siehe
    _ermittle_basiszone_bezeichnung()): traegt die Parzelle einen
    rechtskraeftigen Sondernutzungsplan/Gestaltungsplan (foederale MGDM-
    Kategorie 61), wird ueberhaupt keine Zonenzuordnung und keine
    Finanzberechnung durchgefuehrt. Der Planinhalt kann von der ordentlichen
    BZO abweichen und wird von dieser Engine nicht ausgewertet -- eine aus
    der ordentlichen Zone abgeleitete Zahl waere hier eine scheinpraezise
    Falschaussage, live entdeckt an "Gartenstrasse 5, 5400 Baden" (Kernzone
    K5 UND Gestaltungsplan gleichzeitig) sowie an "Bahnhofstrasse 1, 8001
    Zuerich" (Kernzone UND Gestaltungsplan gleichzeitig -- die zuvor
    ausgegebene Bandbreite von 1.49 bis 4.23 Mio. CHF fuer diese Adresse ist
    damit ebenfalls als unbelastbar zurueckgezogen).
    """
    parzellenflaeche_m2 = modul1_result.get("kataster", {}).get("flaeche_m2")
    if parzellenflaeche_m2 is None:
        raise Modul3Error("Parzellenflaeche aus Modul 1 nicht verfuegbar -- Berechnung nicht moeglich.")

    zone_match = ermittle_zonenzuordnung(modul1_result, modul2_result)

    if zone_match["status"] == "sondernutzungsplan_massgebend":
        zone_match["_meta"] = {"modul": "Modul 3 - Financial Engine", "auflösungsmodus": "sondernutzungsplan_blockiert"}
        return zone_match

    if zone_match["status"] == "gefunden":
        run = _run_for_zone(zone_match["zone"], parzellenflaeche_m2, modul2_result, modul1_result, verkaufspreis_chf_pro_m2)
        return {
            "zonen_zuordnung": zone_match,
            "boni_verrechnung": run["boni_verrechnung"],
            "gwr_bestand_referenz": run["gwr_bestand_referenz"],
            "szenarien": run["szenarien"],
            "_meta": {"modul": "Modul 3 - Financial Engine", "auflösungsmodus": "eindeutig"},
        }

    if zone_match["status"] == "mehrere_gleich_gute_kandidaten":
        kandidaten_zonen = [
            z for z in modul2_result.get("erkannte_zonen", [])
            if z.get("zonenbezeichnung") in {k["zonenbezeichnung"] for k in zone_match["kandidaten"]}
        ]
        # sortiert nach Basis-AZ, damit "niedrigster"/"hoechster" Kandidat eindeutig ist
        kandidaten_zonen = [z for z in kandidaten_zonen if _zone_basis_az(z) is not None]
        if not kandidaten_zonen:
            raise Modul3Error(
                f"Zonenzuordnung mehrdeutig UND keiner der Kandidaten hat eine AZ/aBGF: {zone_match}"
            )
        kandidaten_zonen.sort(key=_zone_basis_az)

        bandbreite = {
            z["zonenbezeichnung"]: _run_for_zone(z, parzellenflaeche_m2, modul2_result, modul1_result, verkaufspreis_chf_pro_m2)
            for z in kandidaten_zonen
        }
        minimum = bandbreite[kandidaten_zonen[0]["zonenbezeichnung"]]
        maximum = bandbreite[kandidaten_zonen[-1]["zonenbezeichnung"]]

        return {
            "zonen_zuordnung": zone_match,
            "bandbreite_je_subtyp": bandbreite,
            "bandbreite_zusammenfassung": {
                "minimum_subtyp": kandidaten_zonen[0]["zonenbezeichnung"],
                "minimum_residualwert_base_case_chf": minimum["szenarien"]["base_case"]["residualwert"]["residualwert_max_landkaufpreis_chf"],
                "maximum_subtyp": kandidaten_zonen[-1]["zonenbezeichnung"],
                "maximum_residualwert_base_case_chf": maximum["szenarien"]["base_case"]["residualwert"]["residualwert_max_landkaufpreis_chf"],
                "hinweis": zone_match["hinweis"],
            },
            "_meta": {"modul": "Modul 3 - Financial Engine", "auflösungsmodus": "bandbreite_mehrdeutig"},
        }

    raise Modul3Error(
        f"Zonenzuordnung nicht eindeutig moeglich (Status: {zone_match['status']}) -- "
        f"{zone_match.get('hinweis', '')} Details: {zone_match}"
    )


def run_full_pipeline(
    address: str, verkaufspreis_chf_pro_m2: float, backend: Optional[str] = None
) -> dict[str, Any]:
    """Kompletter Durchlauf Adresse -> Modul 1 -> Modul 2 -> Modul 3 in einem Aufruf.

    backend: an Modul 2 durchgereicht -- "gemini" (Standard, kostenlos) oder "claude".
    """
    from .modul1_geodata import run_modul1
    from .modul2_bzo_analysis import analyze_from_oereb_result

    modul1_result = run_modul1(address)

    oereb = modul1_result.get("oereb", {})
    if not oereb.get("found"):
        raise Modul3Error(f"Modul 1 lieferte keine OEREB-Daten: {oereb.get('reason')}")

    gemeinde = modul1_result.get("gemeinde", {}).get("gemeinde")
    kanton = oereb.get("kanton")
    modul2_result = analyze_from_oereb_result(oereb, gemeinde=gemeinde, kanton=kanton, backend=backend)

    modul3_result = run_from_modul_results(modul1_result, modul2_result, verkaufspreis_chf_pro_m2)

    return {
        "adresse": address,
        "modul1_geodaten": modul1_result,
        "modul2_bzo_analyse": modul2_result,
        "modul3_financial": modul3_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Modul 3: Financial Engine")
    parser.add_argument("--verkaufspreis-m2", type=float, required=True, help="Verkaufspreis CHF/m2 NNF")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--address", help="Komplette Pipeline: Adresse -> Modul 1 -> Modul 2 -> Modul 3")
    mode.add_argument("--parzelle-m2", type=float, help="Manueller Modus: Parzellenflaeche direkt angeben")

    parser.add_argument("--az", type=float, help="Manueller Modus: Basis-Ausnuetzungsziffer")
    parser.add_argument("--bonus-prozent", type=float, default=0.0, help="Manueller Modus: Bonus auf AZ, z.B. 0.1 fuer +10%%")
    parser.add_argument("--bestand-bgf-m2", type=float, default=None)
    parser.add_argument("--bestand-volumen-m3", type=float, default=None)
    parser.add_argument(
        "--backend", choices=["gemini", "claude"], default=None,
        help="Modul-2-Backend fuer --address-Modus. Standard: gemini (kostenlos, braucht GEMINI_API_KEY).",
    )
    args = parser.parse_args()

    from .modul1_geodata import Modul1Error
    from .modul2_bzo_analysis import Modul2Error

    try:
        if args.address:
            result = run_full_pipeline(args.address, verkaufspreis_chf_pro_m2=args.verkaufspreis_m2, backend=args.backend)
        else:
            if args.az is None:
                raise Modul3Error("--az ist im manuellen Modus (--parzelle-m2) erforderlich.")
            result = {
                "szenarien": run_scenario_matrix(
                    parzellenflaeche_m2=args.parzelle_m2,
                    basis_az=args.az,
                    bonus_az_prozent=args.bonus_prozent,
                    verkaufspreis_chf_pro_m2=args.verkaufspreis_m2,
                    bestand_bgf_m2=args.bestand_bgf_m2,
                    bestand_volumen_m3=args.bestand_volumen_m3,
                )
            }
    except (Modul3Error, Modul1Error, Modul2Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

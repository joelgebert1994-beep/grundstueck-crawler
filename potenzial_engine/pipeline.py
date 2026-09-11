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
from .kantenklassifikation import quellen_fuer_kanten
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
    if g1_ergebnis.get("modus") == "bandbreite_grenzabstand_kante_nicht_differenziert":
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


def analysiere_grundstueck(adresse: str) -> Analyse:
    """Vollstaendige baurechtliche Potenzialanalyse fuer eine Adresse.

    Ablauf: Geodaten (Modul 1) -> Nutzungsklassifikation (Modul 1b) ->
    Auswertung des kommunalen Reglements (Modul 2, LLM) -> Zonenzuordnung ->
    G1-Baubereich -> SIA 416 -> Quellennachweise.

    Braucht KEINEN Verkaufspreis. Dauert typischerweise 1-3 Minuten, weil
    Modul 2 das Reglement der Gemeinde tatsaechlich liest.

    Wirft Modul1Error, wenn fuer die Parzelle keine amtlichen Zonendaten
    (OEREB) vorliegen -- dann waere jede Potenzialaussage haltlos.
    """
    modul1_result = run_modul1(adresse)
    oereb = modul1_result.get("oereb", {})
    if not oereb.get("found"):
        raise Modul1Error(f"Keine amtlichen Zonendaten (OEREB) gefunden: {oereb.get('reason')}")

    gemeinde = modul1_result.get("gemeinde", {}).get("gemeinde")
    kanton = oereb.get("kanton")
    modul2_result = analyze_from_oereb_result(oereb, gemeinde=gemeinde, kanton=kanton, backend="gemini")

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

    # Quellenobjekte: Rueckverfolgbarkeit jedes amtlichen Modul-1-Werts auf
    # Endpunkt/Layer/URL -- vor dem Trimmen berechnet (unabhaengig davon, ob
    # raw_attributes/raw_extract fuer die Anzeige weggeschnitten werden).
    quellen = [asdict(q) for q in quellen_aus_modul1_ergebnis(modul1_result)]
    kanten_klassifikation = modul1_result.get("kantenklassifikation") or {}
    if kanten_klassifikation.get("kanten"):
        quellen += [asdict(q) for q in quellen_fuer_kanten(kanten_klassifikation)]

    ergebnis = {
        "adresse": adresse,
        "modul1_geodaten": _trimmed_modul1(modul1_result),
        "zonen_zuordnung": zonen_zuordnung,
        "g1_ergebnis": g1_ergebnis,
        "g1_fehler": g1_fehler,
        "sia416_ergebnis": sia416_ergebnis,
        "quellen": quellen,
        "entwicklungsszenarien": ENTWICKLUNGSSZENARIEN_INFO,
        "modul2_bzo_analyse": modul2_result,
        "modul3_financial": None,
    }
    return Analyse(ergebnis=ergebnis, kontext={"modul1": modul1_result, "modul2": modul2_result})


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

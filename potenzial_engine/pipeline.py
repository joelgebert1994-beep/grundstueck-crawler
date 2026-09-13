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

    ergebnis = {
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

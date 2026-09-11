"""
Referenzprojekt-Datenstruktur (Design-Vorbereitung, KEINE Implementierung
einer Modellannahme).

Definiert, WELCHE Daten ein eigenes, abgeschlossenes Bauprojekt liefern
muesste, damit es spaeter als dokumentiertes Referenzprojekt zur
Kalibrierung/Verankerung einer SIA-416-Modellannahme dienen kann (siehe
"Ansatz A: dokumentierte Referenzprojekte" in der SIA-416-Methodik-
Entscheidungsvorlage). Enthaelt bewusst KEINE seed-Instanzen mit echten
oder erfundenen Zahlen -- `REFERENZPROJEKTE` ist eine leere Registry, bis
echte Projektdaten vorliegen und bewusst eingetragen werden.

Die einzigen "Berechnungen" in diesem Modul sind reine Verhaeltniszahlen
AUS bereits vollstaendig bekannten, realen Projektwerten (z.B. NF/GF eines
Projekts, dessen NF und GF beide tatsaechlich vorliegen) -- das ist eine
Tatsachenfeststellung ueber ein abgeschlossenes Projekt, KEINE Modellannahme
fuer ein neues, unbekanntes Objekt. Fehlt einer der beiden Werte, liefert
die jeweilige Eigenschaft `None` statt zu schaetzen.

`leite_bandbreite_ab()` aggregiert MEHRERE Referenzprojekte zu einer
konservativ/mittel/optimiert-Bandbreite (siehe dort fuer die Methodik) --
weiterhin ohne Seed-Werte: die Funktion arbeitet ausschliesslich mit
tatsaechlich uebergebenen Projekten, produziert nichts von sich aus.

Kein Bezug zu run_full_pipeline()/G1/Modul 3 -- reine, eigenstaendige
Datenstruktur.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from statistics import median_low
from typing import Any, Dict, List, Optional, Tuple, Union

from entwicklungsszenarien import Szenariotyp
from sia416_flaechen import BandbreitenWert, FlaechenverhaeltnisBandbreite

DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT = "vollstaendig_verifiziert"
DATENQUALITAET_TEILWEISE_VERIFIZIERT = "teilweise_verifiziert"
DATENQUALITAET_GESCHAETZT = "geschaetzt"

_GUELTIGE_DATENQUALITAET = {
    DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT,
    DATENQUALITAET_TEILWEISE_VERIFIZIERT,
    DATENQUALITAET_GESCHAETZT,
}

GEBAEUDETYP_EFH = "EFH"
GEBAEUDETYP_MFH = "MFH"
GEBAEUDETYP_GEWERBE = "Gewerbe"
GEBAEUDETYP_GEMISCHT = "Gemischt"  # reale gemischt genutzte Bestandsbauten -- siehe Hinweis in __post_init__

_GUELTIGE_GEBAEUDETYPEN = {GEBAEUDETYP_EFH, GEBAEUDETYP_MFH, GEBAEUDETYP_GEWERBE, GEBAEUDETYP_GEMISCHT}

_GUELTIGE_SZENARIEN = {s.value for s in Szenariotyp}

VERHAELTNIS_KF_GF = "kf_gf"
VERHAELTNIS_NF_GF = "nf_gf"
VERHAELTNIS_HNF_NF = "hnf_nf"
VERHAELTNIS_HNF_GF = "hnf_gf"

_VERHAELTNIS_PROPERTY = {
    VERHAELTNIS_KF_GF: "kf_gf_quote",
    VERHAELTNIS_NF_GF: "nf_gf_quote",
    VERHAELTNIS_HNF_NF: "hnf_nf_quote",
    VERHAELTNIS_HNF_GF: "hnf_gf_quote",
}


@dataclass(frozen=True)
class Referenzprojekt:
    """Ein einzelnes, dokumentiertes Bauprojekt mit tatsaechlich
    gemessenen/abgerechneten Flaechen -- kein Modellwert. Pflichtfelder
    sind das Minimum, um das Projekt ueberhaupt eindeutig zu identifizieren
    und seiner Quelle zuzuordnen; die Flaechenwerte selbst sind bewusst
    optional, damit ein unvollstaendiger, aber ehrlich als solcher
    gekennzeichneter Datensatz erfasst werden kann, statt ihn wegzulassen."""

    projekt_bezeichnung: str
    gebaeudetyp: str  # siehe GEBAEUDETYP_* -- "Gemischt" fuer real gemischt genutzte Bestandsbauten zulaessig
    gemeinde: str
    kanton: str
    quelle_bezeichnung: str  # z.B. "Bauabrechnung", "Architekturplan (Ausfuehrung)", "eigenes Projekt Gebimo XY"

    # WELCHES reale Entwicklungsszenario (siehe entwicklungsszenarien.Szenariotyp)
    # dieses Projekt tatsaechlich war -- z.B. "aufstockung_dachausbau" fuer ein
    # dokumentiertes Aufstockungsprojekt. None, wenn unbekannt/nicht kategorisiert
    # (dann wird das Projekt bei der Aggregation NICHT beruecksichtigt, siehe
    # leite_bandbreite_ab() -- unbekannte Anwendbarkeit ist nicht neutral).
    entwicklungsszenario: Optional[str] = None

    baujahr: Optional[int] = None

    # SIA-416-Flaechen -- NUR eintragen, was tatsaechlich aus Plaenen/
    # Abrechnung bekannt ist. Ein fehlender Wert bleibt None, wird nicht
    # aus einem anderen Feld hergeleitet oder geschaetzt.
    geschossflaeche_gf_m2: Optional[float] = None
    konstruktionsflaeche_kf_m2: Optional[float] = None
    nutzflaeche_nf_m2: Optional[float] = None
    hauptnutzflaeche_hnf_m2: Optional[float] = None

    erschliessungstyp: Optional[str] = None  # z.B. "Zweispaenner", "Laubengang", "Einzelerschliessung (EFH)"
    bauweise: Optional[str] = None  # z.B. "Massivbau", "Holzbau", "Hybridbau"
    anzahl_geschosse: Optional[int] = None
    unterirdische_geschosse: Optional[int] = None
    hat_lift: Optional[bool] = None
    energiestandard: Optional[str] = None  # z.B. "Minergie", "Minergie-P" -- kann Grundrisseffizienz beeinflussen

    quelle_referenz: Optional[str] = None  # Aktenzeichen/Plannummer/interner Verweis -- kein erfundener Link
    datenqualitaet: Optional[str] = None  # siehe DATENQUALITAET_* -- Einschaetzung der ERFASSUNG, nicht des Projekts selbst
    uebertragbarkeits_hinweis: Optional[str] = None  # z.B. "Attikageschoss, nicht repraesentativ fuer Regelgeschoss"

    def __post_init__(self) -> None:
        for feld_name, feld_wert in (
            ("projekt_bezeichnung", self.projekt_bezeichnung),
            ("gebaeudetyp", self.gebaeudetyp),
            ("gemeinde", self.gemeinde),
            ("kanton", self.kanton),
            ("quelle_bezeichnung", self.quelle_bezeichnung),
        ):
            if not feld_wert or not feld_wert.strip():
                raise ValueError(f"Referenzprojekt.{feld_name} ist Pflicht und darf nicht leer sein.")
        if self.gebaeudetyp not in _GUELTIGE_GEBAEUDETYPEN:
            raise ValueError(
                f"Referenzprojekt.gebaeudetyp '{self.gebaeudetyp}' ist ungueltig -- "
                f"muss einer von {sorted(_GUELTIGE_GEBAEUDETYPEN)} sein (kein freier Text, "
                "sonst matcht es spaeter bei der Aggregation nicht zuverlaessig)."
            )
        if self.entwicklungsszenario is not None and self.entwicklungsszenario not in _GUELTIGE_SZENARIEN:
            raise ValueError(
                f"Referenzprojekt.entwicklungsszenario '{self.entwicklungsszenario}' ist ungueltig -- "
                f"muss einer von {sorted(_GUELTIGE_SZENARIEN)} (entwicklungsszenarien.Szenariotyp) sein oder None."
            )
        if self.datenqualitaet is not None and self.datenqualitaet not in _GUELTIGE_DATENQUALITAET:
            raise ValueError(
                f"Referenzprojekt.datenqualitaet '{self.datenqualitaet}' ist ungueltig -- "
                f"muss einer von {sorted(_GUELTIGE_DATENQUALITAET)} sein oder None."
            )

    # -- Abgeleitete Verhaeltnisse: reine Tatsachenfeststellung ueber DIESES
    # bereits abgeschlossene Projekt, keine Modellannahme fuer ein neues
    # Objekt. Liefert None, wenn einer der beiden benoetigten Originalwerte
    # fehlt -- niemals ein geschaetztes Verhaeltnis. --

    @property
    def kf_gf_quote(self) -> Optional[float]:
        """KF/GF dieses Projekts, nur wenn beide Originalwerte vorhanden."""
        if self.konstruktionsflaeche_kf_m2 is None or not self.geschossflaeche_gf_m2:
            return None
        return round(self.konstruktionsflaeche_kf_m2 / self.geschossflaeche_gf_m2, 4)

    @property
    def nf_gf_quote(self) -> Optional[float]:
        """NF/GF dieses Projekts, nur wenn beide Originalwerte vorhanden."""
        if self.nutzflaeche_nf_m2 is None or not self.geschossflaeche_gf_m2:
            return None
        return round(self.nutzflaeche_nf_m2 / self.geschossflaeche_gf_m2, 4)

    @property
    def hnf_nf_quote(self) -> Optional[float]:
        """HNF/NF dieses Projekts, nur wenn beide Originalwerte vorhanden."""
        if self.hauptnutzflaeche_hnf_m2 is None or not self.nutzflaeche_nf_m2:
            return None
        return round(self.hauptnutzflaeche_hnf_m2 / self.nutzflaeche_nf_m2, 4)

    @property
    def hnf_gf_quote(self) -> Optional[float]:
        """HNF/GF dieses Projekts (direktes Verhaeltnis, wie es manche
        Sekundaerquellen als Beispielrechnung angeben), nur wenn beide
        Originalwerte vorhanden."""
        if self.hauptnutzflaeche_hnf_m2 is None or not self.geschossflaeche_gf_m2:
            return None
        return round(self.hauptnutzflaeche_hnf_m2 / self.geschossflaeche_gf_m2, 4)

    @property
    def verfuegbare_verhaeltnisse(self) -> Dict[str, Optional[float]]:
        """Uebersicht aller 4 Verhaeltnisse -- None, wo die dafuer noetigen
        Originalwerte fehlen. Reine Zusammenfassung der 4 Properties oben."""
        return {
            VERHAELTNIS_KF_GF: self.kf_gf_quote,
            VERHAELTNIS_NF_GF: self.nf_gf_quote,
            VERHAELTNIS_HNF_NF: self.hnf_nf_quote,
            VERHAELTNIS_HNF_GF: self.hnf_gf_quote,
        }

    @property
    def ist_belastbare_referenz(self) -> bool:
        """Erfuellt die in der SIA-416-Methodik-Entscheidungsvorlage
        (Abschnitt 5) festgelegten Mindestanforderungen an eine belastbare
        Referenz: GF, NF UND HNF muessen ALLE real vorhanden sein (nicht
        nur einzelne Flaechen -- ohne HNF laesst sich HNF/NF gar nicht
        bilden), und die Datenqualitaet darf nicht 'geschaetzt' sein, denn
        eine Schaetzung ist per Definition keine reale Referenz (das waere
        Ansatz B, nicht Ansatz A). Sagt NICHTS darueber aus, ob GENUG
        solcher Projekte vorliegen, um daraus eine Bandbreite zu bilden --
        das prueft `leite_bandbreite_ab()` separat."""
        if self.geschossflaeche_gf_m2 is None or self.nutzflaeche_nf_m2 is None or self.hauptnutzflaeche_hnf_m2 is None:
            return False
        if self.datenqualitaet == DATENQUALITAET_GESCHAETZT:
            return False
        return True


# Bewusst leer -- wird erst befuellt, wenn echte, dokumentierte
# Referenzprojekte vorliegen (siehe Entscheidungsvorlage, Abschnitt
# "Offene Entscheidungen": Auswahl geeigneter eigener Projekte ist
# Sache von Joel/Team, nicht dieser Vorbereitung).
REFERENZPROJEKTE: List[Referenzprojekt] = []


# ---------------------------------------------------------------------------
# Erfassung/Import -- WIE echte Projekte spaeter eingebracht werden koennen.
# Reine Serialisierung, keine Modellwerte, keine Validierung ueber das
# hinaus, was Referenzprojekt.__post_init__ ohnehin durchsetzt.
# ---------------------------------------------------------------------------

def referenzprojekt_zu_dict(projekt: Referenzprojekt) -> Dict[str, Any]:
    return asdict(projekt)


def referenzprojekt_aus_dict(daten: Dict[str, Any]) -> Referenzprojekt:
    """Baut ein Referenzprojekt aus einem Dict (z.B. aus JSON). Unbekannte
    Schluessel werden NICHT stillschweigend ignoriert, sondern werfen einen
    Fehler -- ein Tippfehler im importierten Datensatz soll auffallen,
    nicht kommentarlos verloren gehen."""
    bekannte_felder = {f.name for f in fields(Referenzprojekt)}
    unbekannt = set(daten) - bekannte_felder
    if unbekannt:
        raise ValueError(f"Unbekannte Felder in importierten Referenzprojekt-Daten: {sorted(unbekannt)}")
    return Referenzprojekt(**daten)


def lade_referenzprojekte_aus_json(pfad: Union[str, Path]) -> List[Referenzprojekt]:
    """Laedt eine Liste von Referenzprojekten aus einer JSON-Datei (Format:
    Liste von Objekten, Feldnamen wie Referenzprojekt-Attribute). Gedacht als
    der Weg, wie Joel/Team spaeter echte Projektdaten einbringt, ohne Code
    zu aendern -- eine Datei ablegen und laden, statt REFERENZPROJEKTE von
    Hand im Quellcode zu editieren."""
    pfad = Path(pfad)
    rohdaten = json.loads(pfad.read_text(encoding="utf-8"))
    if not isinstance(rohdaten, list):
        raise ValueError(f"{pfad}: erwartet eine JSON-Liste von Referenzprojekten, erhalten {type(rohdaten).__name__}.")
    return [referenzprojekt_aus_dict(d) for d in rohdaten]


def speichere_referenzprojekte_als_json(projekte: List[Referenzprojekt], pfad: Union[str, Path]) -> None:
    Path(pfad).write_text(
        json.dumps([referenzprojekt_zu_dict(p) for p in projekte], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Aggregation mehrerer Referenzprojekte zu einer Bandbreite (KONZEPT, keine
# Seed-Werte -- die Funktion produziert nur dann etwas, wenn tatsaechlich
# genug passende Referenzprojekte uebergeben werden).
# ---------------------------------------------------------------------------

def leite_bandbreite_ab(
    projekte: List[Referenzprojekt],
    verhaeltnis: str,
    gebaeudetyp: str,
    entwicklungsszenario: str,
    mindestanzahl: int = 2,
) -> FlaechenverhaeltnisBandbreite:
    """Aggregiert mehrere Referenzprojekte zu EINER Bandbreite (konservativ/
    mittel/optimiert) fuer ein bestimmtes Verhaeltnis, einen Gebaeudetyp und
    ein Entwicklungsszenario. Arbeitet ausschliesslich mit tatsaechlich
    uebergebenen Projekten -- keine Seed-Werte, keine Schaetzung.

    Beruecksichtigt nur Projekte, die
      - `ist_belastbare_referenz` erfuellen (GF+NF+HNF real, nicht geschaetzt),
      - im uebergebenen `gebaeudetyp` UND `entwicklungsszenario` EXAKT
        uebereinstimmen (ein Projekt mit `entwicklungsszenario=None` wird
        NICHT beruecksichtigt -- unbekannte Anwendbarkeit ist nicht neutral),
      - fuer das gewuenschte `verhaeltnis` tatsaechlich einen Wert liefern
        (z.B. faellt ein Projekt ohne KF-Angabe bei `verhaeltnis="kf_gf"`
        heraus, auch wenn es fuer NF/HNF-Verhaeltnisse belastbar waere).

    Methodik (bewusst ohne kuenstliche Praezision):
      - konservativ = kleinster beobachteter Wert
      - optimiert   = groesster beobachteter Wert
      - mittel      = median_low -- IMMER ein tatsaechlich beobachteter Wert
        eines konkreten Projekts, NIE ein rechnerischer Durchschnitt (der bei
        einer geraden Projektanzahl keinem realen Fall entspraeche). Bei
        genau 2 passenden Projekten faellt 'mittel' deshalb rechnerisch mit
        'konservativ' zusammen (beide = der kleinere der beiden Werte) --
        das ist eine ehrliche Konsequenz von zu wenig Datenpunkten, kein
        Fehler. Fuer eine echte, von 'konservativ' unterscheidbare Mitte
        werden mindestens 3 Projekte empfohlen (siehe Entscheidungsvorlage).

    Jeder der drei resultierenden `BandbreitenWert` traegt in `quelle` die
    konkreten Projektbezeichnung(en), aus denen er stammt -- voll
    rueckverfolgbar, keine anonyme Kennzahl.

    Wirft ValueError, wenn weniger als `mindestanzahl` passende Projekte
    vorliegen (Default 2, technisches Minimum fuer ueberhaupt eine Spanne)
    -- es wird KEINE Bandbreite aus zu wenigen Datenpunkten konstruiert."""
    if verhaeltnis not in _VERHAELTNIS_PROPERTY:
        raise ValueError(f"Unbekanntes Verhaeltnis '{verhaeltnis}' -- muss eines von {sorted(_VERHAELTNIS_PROPERTY)} sein.")
    property_name = _VERHAELTNIS_PROPERTY[verhaeltnis]

    passende: List[Tuple[Referenzprojekt, float]] = []
    for p in projekte:
        if not p.ist_belastbare_referenz:
            continue
        if p.gebaeudetyp != gebaeudetyp or p.entwicklungsszenario != entwicklungsszenario:
            continue
        wert = getattr(p, property_name)
        if wert is None:
            continue
        passende.append((p, wert))

    if len(passende) < mindestanzahl:
        raise ValueError(
            f"Nur {len(passende)} passende(s) Referenzprojekt(e) fuer verhaeltnis={verhaeltnis!r}, "
            f"gebaeudetyp={gebaeudetyp!r}, entwicklungsszenario={entwicklungsszenario!r} gefunden -- "
            f"mindestens {mindestanzahl} noetig. Keine Bandbreite wird aus zu wenigen Datenpunkten konstruiert."
        )

    passende.sort(key=lambda pw: pw[1])
    werte = [w for _, w in passende]
    konservativ_wert, optimiert_wert = werte[0], werte[-1]
    mittel_wert = median_low(werte)
    n = len(passende)

    def _projekte_fuer(wert: float) -> str:
        return ", ".join(p.projekt_bezeichnung for p, w in passende if w == wert)

    basis_quelle = f"{n} Referenzprojekte ({gebaeudetyp}/{entwicklungsszenario})"
    gueltigkeitsbereich = f"{gebaeudetyp}, Szenario {entwicklungsszenario}, aggregiert aus {n} Referenzprojekten"

    def _punkt(wert: float, label: str, begruendung: str) -> BandbreitenWert:
        return BandbreitenWert(
            wert=wert, einheit="Verhaeltnis",
            quelle=f"{basis_quelle} -- {label}: {_projekte_fuer(wert)}",
            begruendung=begruendung, gueltigkeitsbereich=gueltigkeitsbereich,
            gebaeudetyp=gebaeudetyp, entwicklungsszenario=entwicklungsszenario,
        )

    return FlaechenverhaeltnisBandbreite(
        konservativ=_punkt(konservativ_wert, "konservativ", "Kleinster beobachteter Wert unter den verfuegbaren Referenzprojekten."),
        mittel=_punkt(mittel_wert, "mittel", "Median (median_low) -- ein tatsaechlich beobachteter Projektwert, kein rechnerischer Durchschnitt."),
        optimiert=_punkt(optimiert_wert, "optimiert", "Groesster beobachteter Wert unter den verfuegbaren Referenzprojekten."),
    )

"""
Stufe 3 -- die Bruecke BAURECHT -> FLAECHE -> WOHNUNG.

G1 (`baubereich.py`) liefert, was baurechtlich und geometrisch moeglich ist:
anrechenbare Landflaeche, Fussabdruck, Geschosszahl, Geschossflaeche, und je
Kaskadenstufe die limitierende Groesse. `sia416_flaechen.py` liefert die
Norm-Kaskade GF -> NGF -> NF -> HNF/NNF sowie die Wohnungsverteilung. Dieses
Modul verbindet beides und ergaenzt, was fuer eine belastbare Flaechen- und
Wohnungsaussage zusaetzlich noetig ist:

  * eine EXPLIZITE, editierbare Annahmenbasis statt eingebauter Prozentsaetze
  * ein Hoehenmodell, das Geschosshoehe, lichte Raumhoehe und konstruktive
    Hoehe auseinanderhaelt -- und keine davon mit der baurechtlichen
    Gebaeude-/Gesamthoehe verwechselt
  * einen Geschossaufbau, der Untergeschoss, Keller, Erdgeschoss,
    Vollgeschoss, Attika, Dachgeschoss, Technik und Tiefgarage unterscheidet;
    nicht jede Flaeche zaehlt zur Geschossflaeche, und noch weniger ist
    Wohnflaeche
  * eine Volumenbetrachtung, die das baurechtlich zulaessige Volumen (BMZ)
    vom geometrisch tatsaechlich umsetzbaren trennt
  * einen nachvollziehbaren Rechenweg: jeder Schritt mit Eingang, Abzug,
    Ausgang, Herkunft und Begruendung

Drei Herkunftsebenen, die spaeter die Marktdaten-Integration traegt und die
in der Ausgabe NIE vermischt werden duerfen:

    referenz        -- aus Vergleichsobjekten/externen Quellen (noch keine
                       angebunden; die Ebene existiert, damit sie spaeter
                       nicht nachtraeglich eingezogen werden muss)
    systemannahme   -- ein dokumentierter, begruendeter Vorschlag des Systems
    benutzerannahme -- vom Benutzer gesetzt; hat IMMER Vorrang

Keine Zahl entsteht hier, nur damit eine Zahl da ist. Fehlt eine Grundlage,
bleibt der Wert `nicht_bestimmbar` mit konkreter Ursache.

Netzwerkfrei und ohne Seiteneffekte -- reine Berechnung auf uebergebenen Daten.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .sia416_flaechen import (
    STATUS_BESTIMMT,
    STATUS_MODELLANNAHME_BASIERT,
    STATUS_NICHT_BESTIMMBAR,
    Modellannahme,
    SIA416Ergebnis,
    SIA416Wert,
    Wohnungsmix,
    WohnungstypAnteil,
    berechne_sia416_kaskade,
    berechne_wohnungsanzahl,
)

HERKUNFT_BERECHNET = "berechnet"
HERKUNFT_REFERENZ = "referenz"
HERKUNFT_SYSTEMANNAHME = "systemannahme"
HERKUNFT_BENUTZERANNAHME = "benutzerannahme"
HERKUNFT_NICHT_BESTIMMBAR = "nicht_bestimmbar"

# Reihenfolge des Vorrangs: was weiter hinten steht, sticht.
_HERKUNFT_RANG = {
    HERKUNFT_NICHT_BESTIMMBAR: 0,
    HERKUNFT_REFERENZ: 1,
    HERKUNFT_SYSTEMANNAHME: 2,
    HERKUNFT_BERECHNET: 3,
    HERKUNFT_BENUTZERANNAHME: 4,
}


class FlaechenmodellError(Exception):
    """Fehler im Flaechenmodell (widerspruechliche oder fehlende Eingaben)."""


# ---------------------------------------------------------------------------
# Annahmen
# ---------------------------------------------------------------------------

@dataclass
class Annahme:
    """Ein einzelner editierbarer Parameter mit sichtbarer Herkunft.

    `begruendung` ist Pflicht: eine Annahme ohne Begruendung ist von einem
    stillen Default nicht zu unterscheiden.
    """
    schluessel: str
    wert: float
    einheit: str
    begruendung: str
    herkunft: str = HERKUNFT_SYSTEMANNAHME
    quelle: Optional[str] = None
    referenzbereich: Optional[tuple[float, float]] = None

    def __post_init__(self) -> None:
        if not self.begruendung or not self.begruendung.strip():
            raise FlaechenmodellError(
                f"Annahme '{self.schluessel}' ohne Begruendung -- waere von einem stillen "
                "Default nicht unterscheidbar."
            )
        if self.herkunft not in _HERKUNFT_RANG:
            raise FlaechenmodellError(
                f"Unbekannte Herkunft '{self.herkunft}' fuer '{self.schluessel}' -- "
                f"erlaubt: {sorted(_HERKUNFT_RANG)}"
            )

    def mit_benutzerwert(self, wert: float, begruendung: Optional[str] = None) -> "Annahme":
        """Der Benutzer setzt den Wert. Die Systemannahme bleibt als
        Referenzbereich sichtbar, damit erkennbar bleibt, wovon abgewichen
        wurde -- ersetzt wird sie nie stillschweigend."""
        return Annahme(
            schluessel=self.schluessel,
            wert=wert,
            einheit=self.einheit,
            begruendung=begruendung or f"Vom Benutzer gesetzt (Systemvorschlag war {self.wert:g}).",
            herkunft=HERKUNFT_BENUTZERANNAHME,
            quelle=self.quelle,
            referenzbereich=self.referenzbereich,
        )

    def als_modellannahme(self) -> Modellannahme:
        return Modellannahme(
            wert=self.wert,
            begruendung=f"[{self.herkunft}] {self.begruendung}",
            quelle=self.quelle,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.referenzbereich:
            d["referenzbereich"] = list(self.referenzbereich)
        return d


# Dokumentierter Vorschlag fuer Wohnungsbau-Neubau in Massivbauweise. Jede
# Zahl ist ein Erfahrungswert, KEINE Norm: SIA 416 definiert Messgroessen,
# keine Verhaeltnisse zwischen ihnen. Alle Werte sind zu ueberschreiben,
# sobald ein Grundriss- oder Referenzprojekt vorliegt.
# Ab diesem Streckungsfaktor ist die Restflaechenverteilung nicht mehr
# plausibel: die Wohnungen werden dann so viel groesser, dass es ein anderes
# Produkt ist (125 m2 auf 197 m2 sind keine 4.5-Zimmerwohnung mehr).
MAX_VERTEILUNGSFAKTOR = 1.15

PROFIL_WOHNUNGSBAU_MFH = "wohnungsbau_mfh_neubau"

_PROFILE: dict[str, list[Annahme]] = {
    PROFIL_WOHNUNGSBAU_MFH: [
        Annahme(
            schluessel="kf_anteil_an_gf", wert=0.15, einheit="Anteil",
            begruendung=(
                "Konstruktionsflaeche (Aussen- und Innenwaende, Stuetzen) im Wohnungsbau-"
                "Neubau in Massivbauweise. Erfahrungswert, keine Normvorgabe -- haengt an "
                "Bauweise und Wandaufbau und ist am Projekt zu pruefen."
            ),
            referenzbereich=(0.12, 0.18),
        ),
        Annahme(
            schluessel="vf_ff_anteil_an_ngf", wert=0.14, einheit="Anteil",
            begruendung=(
                "Verkehrsflaeche (Treppenhaus, Lift, Korridore) plus Funktionsflaeche "
                "(Technik, Haustechnikraeume) im Verhaeltnis zur Nettogeschossflaeche. "
                "Haengt stark am Erschliessungskonzept: ein Punkthaus mit einem Treppenhaus "
                "liegt tiefer als eine lange Zeile mit mehreren Steigzonen."
            ),
            referenzbereich=(0.10, 0.20),
        ),
        Annahme(
            schluessel="hnf_anteil_an_nf", wert=0.90, einheit="Anteil",
            begruendung=(
                "Hauptnutzflaeche (Wohnraeume) im Verhaeltnis zur Nutzflaeche; die "
                "Differenz ist Nebennutzflaeche (Kellerabteile, Waschen, Trocknen, "
                "Abstellraeume)."
            ),
            referenzbereich=(0.85, 0.93),
        ),
        Annahme(
            schluessel="nwf_anteil_an_hnf", wert=1.00, einheit="Anteil",
            begruendung=(
                "Im reinen Wohnungsbau ist die Hauptnutzflaeche zugleich die Wohnflaeche. "
                "Bei gemischter Nutzung (Gewerbe im Erdgeschoss) ist dieser Wert zu "
                "reduzieren -- dann ist NWF echt kleiner als HNF."
            ),
            referenzbereich=(0.70, 1.00),
        ),
        Annahme(
            schluessel="geschosshoehe_m", wert=3.00, einheit="m",
            begruendung=(
                "Geschosshoehe (Oberkante Rohboden bis Oberkante Rohboden) im "
                "Wohnungsbau-Neubau. NICHT die baurechtliche Gebaeude- oder Gesamthoehe."
            ),
            referenzbereich=(2.80, 3.20),
        ),
        Annahme(
            schluessel="lichte_raumhoehe_m", wert=2.50, einheit="m",
            begruendung=(
                "Lichte Raumhoehe (Oberkante Fertigboden bis Unterkante Decke). Viele "
                "kantonale Baugesetze verlangen im Wohnungsbau mindestens 2.30-2.40 m."
            ),
            referenzbereich=(2.30, 2.70),
        ),
    ],
}


def annahmenprofil(
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
    benutzerwerte: Optional[dict[str, float]] = None,
) -> dict[str, Annahme]:
    """Liefert die Annahmen eines Profils, ueberschrieben durch Benutzerwerte.

    Ein unbekannter Schluessel in `benutzerwerte` ist ein Fehler und wird
    nicht ignoriert -- sonst liefe eine Eingabe ins Leere und der Benutzer
    saehe ein Ergebnis, das seine Aenderung gar nicht enthaelt.
    """
    if profil not in _PROFILE:
        raise FlaechenmodellError(f"Unbekanntes Annahmenprofil '{profil}' -- bekannt: {sorted(_PROFILE)}")
    annahmen = {a.schluessel: a for a in _PROFILE[profil]}
    for schluessel, wert in (benutzerwerte or {}).items():
        if schluessel not in annahmen:
            raise FlaechenmodellError(
                f"Unbekannter Annahmen-Schluessel '{schluessel}' -- bekannt: {sorted(annahmen)}"
            )
        annahmen[schluessel] = annahmen[schluessel].mit_benutzerwert(wert)
    return annahmen


# ---------------------------------------------------------------------------
# Hoehenmodell
# ---------------------------------------------------------------------------

@dataclass
class Hoehenmodell:
    """Haelt die drei Hoehenbegriffe auseinander, die regelmaessig
    verwechselt werden:

      geschosshoehe_m   -- Rohboden bis Rohboden. Diese Groesse geht in die
                           Umrechnung Volumen <-> Geschosszahl ein.
      lichte_raumhoehe_m -- Fertigboden bis Unterkante Decke. Das ist die
                           Groesse, die der Bewohner erlebt und die viele
                           Baugesetze mindestens verlangen.
      konstruktive_hoehe_m -- die Differenz (Decke plus Bodenaufbau).

    KEINE davon ist die baurechtliche Gebaeude- oder Gesamthoehe; die misst
    vom gewachsenen Terrain bis zur Dachkante bzw. zum First und begrenzt
    das Gebaeude als Ganzes.
    """
    geschosshoehe_m: Annahme
    lichte_raumhoehe_m: Annahme
    hinweise: list[str] = field(default_factory=list)

    @property
    def konstruktive_hoehe_m(self) -> float:
        return round(self.geschosshoehe_m.wert - self.lichte_raumhoehe_m.wert, 3)

    def __post_init__(self) -> None:
        if self.lichte_raumhoehe_m.wert >= self.geschosshoehe_m.wert:
            raise FlaechenmodellError(
                f"Lichte Raumhoehe ({self.lichte_raumhoehe_m.wert} m) muss kleiner sein als die "
                f"Geschosshoehe ({self.geschosshoehe_m.wert} m) -- die Differenz ist der "
                "Deckenaufbau. Gleich oder groesser waere physisch unmoeglich."
            )
        if self.konstruktive_hoehe_m < 0.20:
            self.hinweise.append(
                f"Konstruktive Hoehe betraegt nur {self.konstruktive_hoehe_m:.2f} m "
                "(Decke plus Bodenaufbau). Im Massivbau sind 0.30-0.50 m ueblich -- "
                "die Hoehenannahmen sind zu pruefen."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "geschosshoehe_m": self.geschosshoehe_m.to_dict(),
            "lichte_raumhoehe_m": self.lichte_raumhoehe_m.to_dict(),
            "konstruktive_hoehe_m": self.konstruktive_hoehe_m,
            "abgrenzung": (
                "Geschosshoehe und lichte Raumhoehe sind NICHT die baurechtliche "
                "Gebaeude- oder Gesamthoehe -- diese misst vom gewachsenen Terrain bis "
                "Dachkante bzw. First und begrenzt das Gebaeude als Ganzes."
            ),
            "hinweise": self.hinweise,
        }


# ---------------------------------------------------------------------------
# Geschossaufbau
# ---------------------------------------------------------------------------

GESCHOSS_UNTERGESCHOSS = "untergeschoss"
GESCHOSS_KELLER = "keller"
GESCHOSS_TIEFGARAGE = "tiefgarage"
GESCHOSS_ERDGESCHOSS = "erdgeschoss"
GESCHOSS_VOLLGESCHOSS = "vollgeschoss"
GESCHOSS_ATTIKA = "attika"
GESCHOSS_DACHGESCHOSS = "dachgeschoss"
GESCHOSS_TECHNIK = "technik"

# Was zaehlt wozu -- die Voreinstellung folgt der in der Schweiz ueblichen
# Systematik. Sie ist bewusst als Tabelle sichtbar und NICHT im Code
# verstreut, weil kantonales und kommunales Recht davon abweichen kann.
_GESCHOSSART_VORGABE: dict[str, dict[str, Any]] = {
    GESCHOSS_ERDGESCHOSS: {"vollgeschoss": True, "geschossflaeche": True, "wohnen": True},
    GESCHOSS_VOLLGESCHOSS: {"vollgeschoss": True, "geschossflaeche": True, "wohnen": True},
    GESCHOSS_ATTIKA: {"vollgeschoss": False, "geschossflaeche": True, "wohnen": True},
    GESCHOSS_DACHGESCHOSS: {"vollgeschoss": False, "geschossflaeche": True, "wohnen": True},
    GESCHOSS_UNTERGESCHOSS: {"vollgeschoss": False, "geschossflaeche": False, "wohnen": False},
    GESCHOSS_KELLER: {"vollgeschoss": False, "geschossflaeche": False, "wohnen": False},
    GESCHOSS_TIEFGARAGE: {"vollgeschoss": False, "geschossflaeche": False, "wohnen": False},
    GESCHOSS_TECHNIK: {"vollgeschoss": False, "geschossflaeche": False, "wohnen": False},
}


@dataclass
class Geschoss:
    bezeichnung: str
    art: str
    flaeche_m2: Optional[float]
    zaehlt_als_vollgeschoss: bool
    zaehlt_zur_geschossflaeche: bool
    wohnnutzung_moeglich: bool
    begruendung: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Geschossaufbau:
    geschosse: list[Geschoss]
    vollgeschosse: int
    geschossflaeche_m2: Optional[float]
    hinweise: list[str] = field(default_factory=list)
    offene_punkte: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "geschosse": [g.to_dict() for g in self.geschosse],
            "vollgeschosse": self.vollgeschosse,
            "geschossflaeche_m2": self.geschossflaeche_m2,
            "hinweise": self.hinweise,
            "offene_punkte": self.offene_punkte,
        }


def leite_geschossaufbau_ab(
    g1_ergebnis: dict[str, Any],
    *,
    zusaetzliche_geschosse: Optional[list[dict[str, Any]]] = None,
) -> Geschossaufbau:
    """Baut aus G1s Geschosszahl und Fussabdruck einen expliziten
    Geschossaufbau.

    G1 liefert eine ZAHL von Vollgeschossen, keine Gliederung. Erdgeschoss
    und Obergeschosse werden daraus abgeleitet; alles andere (Attika,
    Untergeschoss, Tiefgarage) ist eine Angabe, die aus dem Baurecht oder
    vom Benutzer kommen muss -- sie wird NICHT unterstellt. Dass Modul 2
    heute nicht strukturiert sagt, ob die Zone ein Attikageschoss zulaesst,
    ist ein offener Punkt und wird als solcher gemeldet, nicht durch eine
    Annahme ueberdeckt.
    """
    geschosszahl = g1_ergebnis.get("geschosszahl")
    fussabdruck = g1_ergebnis.get("fussabdruck_m2")
    hinweise: list[str] = []
    offene: list[str] = []

    if geschosszahl is None:
        return Geschossaufbau(
            geschosse=[], vollgeschosse=0, geschossflaeche_m2=None,
            offene_punkte=[
                "G1 konnte keine Geschosszahl bestimmen (weder Vollgeschosse noch "
                "Gebaeudehoehe in den Zonendaten) -- ohne sie gibt es keinen Geschossaufbau."
            ],
        )

    geschosse: list[Geschoss] = []
    for i in range(int(geschosszahl)):
        ist_eg = i == 0
        art = GESCHOSS_ERDGESCHOSS if ist_eg else GESCHOSS_VOLLGESCHOSS
        vorgabe = _GESCHOSSART_VORGABE[art]
        geschosse.append(Geschoss(
            bezeichnung="EG" if ist_eg else f"OG{i}",
            art=art,
            flaeche_m2=fussabdruck,
            zaehlt_als_vollgeschoss=vorgabe["vollgeschoss"],
            zaehlt_zur_geschossflaeche=vorgabe["geschossflaeche"],
            wohnnutzung_moeglich=vorgabe["wohnen"],
            begruendung=(
                f"Aus G1: {geschosszahl} Vollgeschoss(e), limitiert durch "
                f"{g1_ergebnis.get('geschosszahl_limitiert_durch')}. Flaeche = zulaessiger "
                "Fussabdruck; ein realer Grundriss kann je Geschoss abweichen."
            ),
        ))

    for zusatz in zusaetzliche_geschosse or []:
        art = zusatz.get("art")
        if art not in _GESCHOSSART_VORGABE:
            raise FlaechenmodellError(
                f"Unbekannte Geschossart '{art}' -- bekannt: {sorted(_GESCHOSSART_VORGABE)}"
            )
        vorgabe = _GESCHOSSART_VORGABE[art]
        geschosse.append(Geschoss(
            bezeichnung=zusatz.get("bezeichnung") or art.upper(),
            art=art,
            flaeche_m2=zusatz.get("flaeche_m2"),
            zaehlt_als_vollgeschoss=bool(zusatz.get("zaehlt_als_vollgeschoss", vorgabe["vollgeschoss"])),
            zaehlt_zur_geschossflaeche=bool(zusatz.get("zaehlt_zur_geschossflaeche", vorgabe["geschossflaeche"])),
            wohnnutzung_moeglich=bool(zusatz.get("wohnnutzung_moeglich", vorgabe["wohnen"])),
            begruendung=zusatz.get("begruendung") or "Explizit uebergeben (Baurecht oder Benutzereingabe).",
        ))

    offene.append(
        "Ob die Zone ein Attikageschoss, ein Dachgeschoss oder anrechenbare Untergeschosse "
        "zulaesst, wird von Modul 2 heute nicht als strukturierter Wert geliefert. Solche "
        "Geschosse erscheinen nur, wenn sie ausdruecklich uebergeben werden -- unterstellt "
        "werden sie nicht."
    )

    anrechenbar = [g for g in geschosse if g.zaehlt_zur_geschossflaeche and g.flaeche_m2 is not None]
    gf = round(sum(g.flaeche_m2 for g in anrechenbar), 2) if anrechenbar else None
    fehlende_flaeche = [g.bezeichnung for g in geschosse if g.zaehlt_zur_geschossflaeche and g.flaeche_m2 is None]
    if fehlende_flaeche:
        hinweise.append(
            f"Ohne Flaechenangabe und daher nicht in der Geschossflaeche enthalten: "
            f"{', '.join(fehlende_flaeche)}."
        )
    nicht_anrechenbar = [g.bezeichnung for g in geschosse if not g.zaehlt_zur_geschossflaeche]
    if nicht_anrechenbar:
        hinweise.append(
            f"Nicht zur Geschossflaeche gezaehlt: {', '.join(nicht_anrechenbar)}. "
            "Untergeschoss, Keller, Tiefgarage und Technik sind in der Regel weder "
            "Geschossflaeche noch Wohnflaeche -- kantonale Anrechnungsregeln koennen "
            "abweichen und sind zu pruefen."
        )

    return Geschossaufbau(
        geschosse=geschosse,
        vollgeschosse=sum(1 for g in geschosse if g.zaehlt_als_vollgeschoss),
        geschossflaeche_m2=gf,
        hinweise=hinweise,
        offene_punkte=offene,
    )


# ---------------------------------------------------------------------------
# Plausibilitaet der Nutzungsziffern
# ---------------------------------------------------------------------------

# Uebliche Wertebereiche Schweizer Nutzungsziffern. Eine Ueberschreitung wird
# NICHT korrigiert -- der extrahierte Wert bleibt stehen. Sie wird gemeldet,
# damit ein Datenfehler nicht als Ergebnis durchgeht. Live beobachtet:
# "AZ=20.0" in einer Wohnzone W1 (Russikon ZH) -- das waere die zwanzigfache
# Grundstuecksflaeche als Geschossflaeche und ist offensichtlich eine
# Prozentangabe, die als absolute Zahl gelesen wurde.
_ZIFFER_BEREICHE: dict[str, tuple[float, float, str]] = {
    "ausnuetzungsziffer_az": (0.1, 3.0, "Ausnuetzungsziffer"),
    "anrechenbare_geschossflaechenziffer_abgf": (0.1, 3.0, "anrechenbare Geschossflaechenziffer"),
    "ueberbauungsziffer_uz": (0.05, 0.9, "Ueberbauungsziffer"),
    "baumassenziffer_bmz": (1.0, 12.0, "Baumassenziffer"),
}


def pruefe_nutzungsziffern(zone: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Meldet Nutzungsziffern ausserhalb des ueblichen Bereichs.

    Reine Meldung, keine Korrektur: ob 20.0 als 0.20 gemeint war, entscheidet
    das Reglement, nicht diese Funktion. Ein stillschweigendes Teilen durch
    100 waere genau die Sorte Zahlenerfindung, die hier nicht vorkommen darf.
    """
    if not zone:
        return []
    befunde = []
    for feld, (untere, obere, name) in _ZIFFER_BEREICHE.items():
        roh = zone.get(feld)
        wert = roh.get("wert") if isinstance(roh, dict) else roh
        if wert is None:
            continue
        try:
            zahl = float(wert)
        except (TypeError, ValueError):
            continue
        if untere <= zahl <= obere:
            continue
        vermutung = None
        if zahl > obere and untere <= zahl / 100.0 <= obere:
            vermutung = (
                f"Bei einer Prozentangabe waere {zahl / 100.0:g} gemeint -- das laege im "
                "ueblichen Bereich. NICHT automatisch umgerechnet."
            )
        befunde.append({
            "feld": feld,
            "wert": zahl,
            "ueblicher_bereich": [untere, obere],
            "schwere": "manuelle_pruefung_erforderlich",
            "meldung": (
                f"{name} = {zahl:g} liegt ausserhalb des in der Schweiz ueblichen Bereichs "
                f"({untere:g} bis {obere:g})."
                + (f" {vermutung}" if vermutung else "")
                + " Der Wert wird unveraendert weitergerechnet; die daraus folgenden "
                "Flaechen sind entsprechend unsicher."
            ),
        })
    return befunde


# ---------------------------------------------------------------------------
# Volumen (BMZ)
# ---------------------------------------------------------------------------

def volumenbetrachtung(
    g1_ergebnis: dict[str, Any],
    baumassenziffer_bmz: Optional[float],
    geschosshoehe: Annahme,
) -> dict[str, Any]:
    """Trennt das baurechtlich zulaessige Volumen vom geometrisch
    umsetzbaren.

    G1 rechnet einen BMZ-Deckel bereits in eine Geschossflaeche um; welches
    VOLUMEN dahintersteht, blieb dabei unsichtbar. Genau diese Groesse ist
    aber die Aussage, die eine volumenbasierte Zone macht.
    """
    landflaeche = g1_ergebnis.get("anrechenbare_landflaeche_m2")
    fussabdruck = g1_ergebnis.get("fussabdruck_m2")
    geschosszahl = g1_ergebnis.get("geschosszahl")

    if baumassenziffer_bmz is None:
        return {
            "gilt": False,
            "grund": "Fuer diese Zone ist keine Baumassenziffer hinterlegt -- "
                     "die Nutzung wird nicht ueber das Volumen begrenzt.",
        }
    if landflaeche is None:
        return {
            "gilt": True,
            "zulaessiges_volumen_m3": None,
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": "Anrechenbare Landflaeche unbekannt -- BMZ x Flaeche nicht berechenbar.",
        }

    zulaessig = round(baumassenziffer_bmz * landflaeche, 1)
    geometrisch = None
    if fussabdruck is not None and geschosszahl is not None:
        geometrisch = round(fussabdruck * geschosszahl * geschosshoehe.wert, 1)

    ergebnis: dict[str, Any] = {
        "gilt": True,
        "baumassenziffer_bmz": baumassenziffer_bmz,
        "anrechenbare_landflaeche_m2": landflaeche,
        "zulaessiges_volumen_m3": zulaessig,
        "zulaessiges_volumen_herkunft": (
            f"BMZ {baumassenziffer_bmz} x anrechenbare Landflaeche {landflaeche} m2 "
            "(baurechtliches Limit, unabhaengig von der Geometrie)"
        ),
        "geometrisch_moegliches_volumen_m3": geometrisch,
        "geschosshoehe": geschosshoehe.to_dict(),
        "status": STATUS_BESTIMMT if geometrisch is not None else STATUS_MODELLANNAHME_BASIERT,
    }

    if geometrisch is None:
        ergebnis["geometrisch_grund"] = (
            "Fussabdruck oder Geschosszahl unbekannt -- das tatsaechlich umsetzbare "
            "Volumen laesst sich nicht bestimmen."
        )
        ergebnis["bindend"] = "baurecht"
        return ergebnis

    ergebnis["geometrisch_herkunft"] = (
        f"Fussabdruck {fussabdruck} m2 x {geschosszahl} Geschoss(e) x Geschosshoehe "
        f"{geschosshoehe.wert} m [{geschosshoehe.herkunft}]"
    )
    ergebnis["bindend"] = "geometrie" if geometrisch < zulaessig else "baurecht"
    ergebnis["massgebendes_volumen_m3"] = min(zulaessig, geometrisch)
    ergebnis["hinweis"] = (
        "Das baurechtlich zulaessige Volumen ist nicht dasselbe wie das geometrisch "
        "umsetzbare: Grenzabstaende, Baubereich und Geschosszahl koennen es unterschreiten. "
        f"Massgebend ist hier das {ergebnis['bindend']}-begrenzte Volumen."
    )
    return ergebnis


# ---------------------------------------------------------------------------
# Wohnungsmix -- Anteile ODER Stueckzahlen
# ---------------------------------------------------------------------------

@dataclass
class WohnungstypVorgabe:
    typ: str
    flaeche_nwf_pro_einheit_m2: float
    anteil: Optional[float] = None
    anzahl: Optional[int] = None

    def __post_init__(self) -> None:
        if (self.anteil is None) == (self.anzahl is None):
            raise FlaechenmodellError(
                f"Wohnungstyp '{self.typ}': genau eines von anteil oder anzahl angeben "
                "-- beides zugleich waere widerspruechlich, keines von beidem unbestimmt."
            )
        if self.flaeche_nwf_pro_einheit_m2 <= 0:
            raise FlaechenmodellError(
                f"Wohnungstyp '{self.typ}': Flaeche je Einheit muss groesser als 0 sein."
            )


def _flaechenbilanz(
    verfuegbar: Optional[float], belegt: Optional[float],
) -> dict[str, Any]:
    """Die Flaechenkette muss geschlossen sein: verfuegbar = belegt + Rest.

    Ohne diese Bilanz konnte Flaeche unbemerkt im Erloes landen, die keiner
    Wohnung zugeordnet war (live beobachtet: 197 m2 Wohnflaeche, ein Mix aus
    nur 3.5-/4.5-Zimmerwohnungen belegte davon 125 m2, die restlichen 72 m2
    wurden trotzdem voll mitverkauft).
    """
    if verfuegbar is None or belegt is None:
        return {
            "verfuegbar_m2": verfuegbar, "belegt_m2": belegt,
            "nicht_zugeordnet_m2": None, "geschlossen": False,
            "hinweis": "Flaechenbilanz nicht bestimmbar.",
        }
    rest = round(verfuegbar - belegt, 1)
    geschlossen = abs(rest) <= 0.5
    return {
        "verfuegbar_m2": round(verfuegbar, 1),
        "belegt_m2": round(belegt, 1),
        "nicht_zugeordnet_m2": rest,
        "geschlossen": geschlossen,
        "hinweis": (
            "Die gesamte Wohnflaeche ist Wohnungen zugeordnet."
            if geschlossen else
            f"{rest:,.1f} m2 sind KEINER Wohnung zugeordnet. Diese Flaeche geht nicht in "
            "Verkaufserloes oder Mietertrag ein. Entweder den Wohnungsmix anpassen, die "
            "Wohnungen vergroessern (restflaeche_verteilen=True) oder die Flaeche als "
            "gemeinsame Nebennutzflaeche fuehren."
        ),
    }


def _verteile_restflaeche(zeilen: list[dict[str, Any]], verfuegbar: float) -> Optional[float]:
    """Vergroessert alle Wohnungen gleichmaessig, bis die Flaeche aufgeht.

    Das ist die mathematisch saubere Variante zu "Rest stehen lassen": die
    Anzahl Wohnungen bleibt, ihre Flaechen wachsen proportional. Liefert den
    Faktor zurueck, damit sichtbar bleibt, wie stark verschoben wurde.
    """
    belegt = sum(z["flaeche_total_m2"] for z in zeilen)
    if belegt <= 0 or verfuegbar <= 0:
        return None
    faktor = verfuegbar / belegt
    for z in zeilen:
        if not z["anzahl"]:
            continue
        z["flaeche_pro_einheit_urspruenglich_m2"] = z["flaeche_pro_einheit_m2"]
        z["flaeche_pro_einheit_m2"] = round(z["flaeche_pro_einheit_m2"] * faktor, 1)
        z["flaeche_total_m2"] = round(z["anzahl"] * z["flaeche_pro_einheit_m2"], 1)
    return round(faktor, 4)


def berechne_wohnungen(
    nwf_m2: Optional[float],
    typen: Optional[list[WohnungstypVorgabe]],
    begruendung: str = "",
    restflaeche_verteilen: bool = False,
    herkunft: str = HERKUNFT_SYSTEMANNAHME,
) -> dict[str, Any]:
    """Leitet aus der Wohnflaeche eine Wohnungsstruktur ab.

    Zwei Eingabearten, die sich nicht mischen lassen:
      * ANTEILE -- die Wohnflaeche wird nach Prozenten verteilt, je Typ
        werden nur ganze Einheiten gebildet.
      * STUECKZAHLEN -- der Benutzer gibt die Anzahl je Typ vor; gerechnet
        wird die benoetigte Flaeche und die Differenz zur verfuegbaren.
        Passt es nicht, wird das gemeldet und nicht zurechtgerechnet.

    Jedes Ergebnis traegt eine `flaechenbilanz`: verfuegbar, belegt und
    nicht zugeordnet. Mit `restflaeche_verteilen=True` werden die Wohnungen
    gleichmaessig vergroessert, bis die Bilanz aufgeht -- die Anzahl bleibt,
    der Verschiebefaktor wird ausgewiesen.
    """
    if nwf_m2 is None:
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": "Keine Wohnflaeche bestimmt -- ohne sie ist keine Wohnungsanzahl ableitbar.",
        }
    if not typen:
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": (
                "Kein Wohnungsmix vorgegeben. Es wird bewusst keine Durchschnittswohnung "
                "unterstellt -- die Wohnungsgroesse bestimmt das Ergebnis zu stark."
            ),
        }

    nach_anteil = [t for t in typen if t.anteil is not None]
    nach_anzahl = [t for t in typen if t.anzahl is not None]
    if nach_anteil and nach_anzahl:
        raise FlaechenmodellError(
            "Wohnungsmix mischt Anteile und Stueckzahlen -- das ergibt zwei verschiedene "
            "Gesamtflaechen. Bitte durchgaengig das eine oder das andere."
        )

    if nach_anzahl:
        zeilen = []
        benoetigt = 0.0
        for t in nach_anzahl:
            flaeche = round(t.anzahl * t.flaeche_nwf_pro_einheit_m2, 1)
            benoetigt += flaeche
            zeilen.append({
                "typ": t.typ, "anzahl": t.anzahl,
                "flaeche_pro_einheit_m2": t.flaeche_nwf_pro_einheit_m2,
                "flaeche_total_m2": flaeche,
            })
        differenz = round(nwf_m2 - benoetigt, 1)
        return {
            "status": STATUS_MODELLANNAHME_BASIERT,
            "eingabeart": "stueckzahlen",
            "typen": zeilen,
            "anzahl_wohnungen": sum(t.anzahl for t in nach_anzahl),
            "benoetigte_flaeche_m2": round(benoetigt, 1),
            "verfuegbare_flaeche_m2": round(nwf_m2, 1),
            "belegte_flaeche_m2": round(benoetigt, 1),
            "restflaeche_m2": differenz,
            "differenz_m2": differenz,
            "passt": differenz >= 0,
            "flaechenbilanz": _flaechenbilanz(nwf_m2, benoetigt),
            "hinweis": (
                f"Die vorgegebenen Wohnungen brauchen {benoetigt:.1f} m2, verfuegbar sind "
                f"{nwf_m2:.1f} m2 -- "
                + ("Reserve " if differenz >= 0 else "Fehlbetrag ")
                + f"{abs(differenz):.1f} m2. Es wird weder auf- noch abgerundet."
            )
            + (f" Mix-Begruendung: {begruendung}" if begruendung else ""),
            "herkunft": herkunft,
        }

    summe = sum(t.anteil for t in nach_anteil)
    if abs(summe - 1.0) > 1e-6:
        raise FlaechenmodellError(
            f"Wohnungsmix-Anteile ergeben {summe:.4f}, nicht 1.0 -- wird nicht automatisch "
            "normalisiert, das wuerde den Mix stillschweigend veraendern."
        )

    mix = Wohnungsmix(
        typen=[
            WohnungstypAnteil(typ=t.typ, anteil=t.anteil, flaeche_hnf_pro_einheit_m2=t.flaeche_nwf_pro_einheit_m2)
            for t in nach_anteil
        ],
        begruendung=begruendung or "Wohnungsmix als Anteile vorgegeben.",
    )
    roh = berechne_wohnungsanzahl(nwf_m2, mix)
    if roh is None:  # pragma: no cover -- nwf_m2 und mix sind hier gesetzt
        return {"status": STATUS_NICHT_BESTIMMBAR, "grund": "Verteilung nicht berechenbar."}

    zeilen = []
    for t_vorgabe, t_ergebnis in zip(nach_anteil, roh.typen):
        zeilen.append({
            "typ": t_ergebnis.typ,
            "anteil": t_vorgabe.anteil,
            "flaeche_pro_einheit_m2": t_vorgabe.flaeche_nwf_pro_einheit_m2,
            "sollanteil_m2": t_ergebnis.hnf_sollanteil_m2,
            "anzahl": t_ergebnis.anzahl_ganze_einheiten,
            "flaeche_total_m2": t_ergebnis.belegte_hnf_m2,
            "abweichung_vom_sollanteil_m2": t_ergebnis.abweichung_vom_sollanteil_m2,
            "ist_anteil": (
                round(t_ergebnis.anzahl_ganze_einheiten / roh.gesamtanzahl_ganze_einheiten, 3)
                if roh.gesamtanzahl_ganze_einheiten else None
            ),
        })

    faktor = None
    if restflaeche_verteilen and roh.gesamtanzahl_ganze_einheiten:
        faktor = _verteile_restflaeche(zeilen, nwf_m2)

    belegt = round(sum(z["flaeche_total_m2"] for z in zeilen), 1)
    rest = round(nwf_m2 - belegt, 1)

    ergebnis = {
        "status": STATUS_MODELLANNAHME_BASIERT,
        # Woher der Mix kommt. Ein vom System vorgeschlagener Mix ist KEINE
        # Benutzerannahme -- er sieht im Formular nur so aus, weil er dort
        # schon steht. Wer das nicht unterscheidet, weist im Dossier einen
        # Vorschlag als Entscheidung des Eigentuemers aus.
        "herkunft": herkunft,
        "eingabeart": "anteile",
        "typen": zeilen,
        "anzahl_wohnungen": roh.gesamtanzahl_ganze_einheiten,
        "verfuegbare_flaeche_m2": round(nwf_m2, 1),
        "belegte_flaeche_m2": belegt,
        "restflaeche_m2": rest,
        "durchschnittsflaeche_m2": (
            round(belegt / roh.gesamtanzahl_ganze_einheiten, 1)
            if roh.gesamtanzahl_ganze_einheiten else None
        ),
        "mittlere_wohnungsgroesse_im_mix_m2": roh.durchschnittsflaeche_pro_einheit_m2,
        "flaechenbilanz": _flaechenbilanz(nwf_m2, belegt),
        "hinweis": roh.unklarheit,
    }
    if faktor is not None:
        ergebnis["restflaeche_verteilt"] = True
        ergebnis["verteilungsfaktor"] = faktor
        ergebnis["hinweis"] = (
            f"Die Restflaeche wurde auf die {roh.gesamtanzahl_ganze_einheiten} Wohnungen "
            f"verteilt: alle Flaechen x {faktor:.3f}. Die Anzahl Wohnungen bleibt gleich, "
            "die einzelnen Wohnungen werden entsprechend groesser. "
        ) + (roh.unklarheit or "")
        # Ein grosser Faktor heisst: der Mix passt nicht zur verfuegbaren
        # Flaeche. 125 m2 auf 197 m2 zu strecken ergibt keine 4.5-Zimmer-
        # wohnung mehr, sondern ein anderes Produkt.
        if faktor > MAX_VERTEILUNGSFAKTOR:
            ergebnis["verteilung_unplausibel"] = True
            ergebnis["hinweis"] = (
                f"ACHTUNG: die Wohnungen muessten um {(faktor - 1) * 100:.0f} % wachsen, damit "
                "die Flaeche aufgeht -- der Wohnungsmix passt nicht zur verfuegbaren Flaeche. "
                "Besser den Mix anpassen (kleinere Typen oder andere Anteile) als die "
                "Wohnungen so stark zu strecken. "
            ) + ergebnis["hinweis"]
    return ergebnis


# ---------------------------------------------------------------------------
# Gesamtrechnung mit Rechenweg
# ---------------------------------------------------------------------------

def _schritt(
    bezeichnung: str, eingang: Optional[float], operation: str,
    ausgang: Optional[float], herkunft: str, einheit: str = "m2",
) -> dict[str, Any]:
    return {
        "schritt": bezeichnung, "eingang": eingang, "operation": operation,
        "ausgang": ausgang, "einheit": einheit, "herkunft": herkunft,
    }


def berechne_flaechen_und_wohnungen(
    g1_ergebnis: dict[str, Any],
    *,
    zone: Optional[dict[str, Any]] = None,
    profil: str = PROFIL_WOHNUNGSBAU_MFH,
    benutzerwerte: Optional[dict[str, float]] = None,
    wohnungsmix: Optional[list[WohnungstypVorgabe]] = None,
    wohnungsmix_begruendung: str = "",
    wohnungsmix_herkunft: str = HERKUNFT_SYSTEMANNAHME,
    zusaetzliche_geschosse: Optional[list[dict[str, Any]]] = None,
    restflaeche_verteilen: bool = False,
) -> dict[str, Any]:
    """Die vollstaendige Bruecke: G1-Ergebnis -> Flaechen -> Wohnungen.

    `g1_ergebnis` ist das `to_dict()` eines `PotenzialErgebnis` (bzw. der
    `ergebnis`-Teil aus `berechne_g1_fuer_fall`). `zone` ist der
    Modul-2-Zoneneintrag, nur fuer die Baumassenziffer gebraucht.

    Jede Stufe erscheint zusaetzlich im `rechenweg` mit Eingang, Operation,
    Ausgang und Herkunft -- damit jede Zahl im Ergebnis nachvollziehbar
    bleibt, wie es die Produktspezifikation verlangt.
    """
    annahmen = annahmenprofil(profil, benutzerwerte)
    hoehen = Hoehenmodell(
        geschosshoehe_m=annahmen["geschosshoehe_m"],
        lichte_raumhoehe_m=annahmen["lichte_raumhoehe_m"],
    )

    geschossaufbau = leite_geschossaufbau_ab(g1_ergebnis, zusaetzliche_geschosse=zusaetzliche_geschosse)

    bmz = None
    if zone:
        roh = zone.get("baumassenziffer_bmz")
        bmz = roh.get("wert") if isinstance(roh, dict) else roh
    volumen = volumenbetrachtung(g1_ergebnis, bmz, annahmen["geschosshoehe_m"])
    ziffernbefunde = pruefe_nutzungsziffern(zone)

    gf = g1_ergebnis.get("geschossflaeche_m2")
    rechenweg: list[dict[str, Any]] = []

    rechenweg.append(_schritt(
        "Grundstuecksflaeche", None, "amtliche Vermessung",
        g1_ergebnis.get("parzellenflaeche_m2"), "Kataster (amtliche Vermessung)",
    ))
    rechenweg.append(_schritt(
        "anrechenbare Grundstuecksflaeche", g1_ergebnis.get("parzellenflaeche_m2"),
        "abzueglich nicht ueberbaubarer Restriktionsflaechen",
        g1_ergebnis.get("anrechenbare_landflaeche_m2"),
        "G1: Gewaesserraum/Wald/Restriktionen abgezogen",
    ))
    rechenweg.append(_schritt(
        "Fussabdruck", g1_ergebnis.get("anrechenbare_landflaeche_m2"),
        f"limitiert durch {g1_ergebnis.get('fussabdruck_limitiert_durch')}",
        g1_ergebnis.get("fussabdruck_m2"),
        f"G1, Kandidaten: {g1_ergebnis.get('fussabdruck_kandidaten')}",
    ))
    rechenweg.append(_schritt(
        "Geschossflaeche GF", g1_ergebnis.get("fussabdruck_m2"),
        f"limitiert durch {g1_ergebnis.get('geschossflaeche_limitiert_durch')}", gf,
        f"G1, Kandidaten: {g1_ergebnis.get('geschossflaeche_kandidaten')}",
    ))

    if gf is None:
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": (
                "G1 konnte keine Geschossflaeche bestimmen -- ohne sie beginnt die "
                "Flaechenkaskade nicht. Ursache: "
                f"{g1_ergebnis.get('geschossflaeche_kandidaten') or 'keine Nutzungsziffer und keine Geschosszahl'}."
            ),
            "annahmen": {k: a.to_dict() for k, a in annahmen.items()},
            "hoehenmodell": hoehen.to_dict(),
            "geschossaufbau": geschossaufbau.to_dict(),
            "volumen": volumen,
            "datenpruefung": ziffernbefunde,
            "rechenweg": rechenweg,
            "wohnungen": {"status": STATUS_NICHT_BESTIMMBAR, "grund": "Keine Wohnflaeche bestimmt."},
        }

    sia = berechne_sia416_kaskade(
        geschossflaeche_gf_m2=gf,
        kf_anteil_an_gf=annahmen["kf_anteil_an_gf"].als_modellannahme(),
        vf_ff_anteil_an_ngf=annahmen["vf_ff_anteil_an_ngf"].als_modellannahme(),
        hnf_anteil_an_nf=annahmen["hnf_anteil_an_nf"].als_modellannahme(),
    )

    for wert, vorher, operation in (
        (sia.konstruktionsflaeche_kf, gf, f"x {annahmen['kf_anteil_an_gf'].wert:.0%} (Konstruktion)"),
        (sia.nettogeschossflaeche_ngf, gf, "GF - KF"),
        (sia.verkehrs_und_funktionsflaeche_vf_ff, sia.nettogeschossflaeche_ngf.wert,
         f"x {annahmen['vf_ff_anteil_an_ngf'].wert:.0%} (Erschliessung, Treppen/Lift, Technik)"),
        (sia.nutzflaeche_nf, sia.nettogeschossflaeche_ngf.wert, "NGF - (VF+FF)"),
        (sia.hauptnutzflaeche_hnf, sia.nutzflaeche_nf.wert,
         f"x {annahmen['hnf_anteil_an_nf'].wert:.0%} (Rest = Nebennutzflaeche)"),
    ):
        if wert is None:
            continue
        rechenweg.append(_schritt(
            wert.feld, vorher, operation, wert.wert, wert.herkunft or wert.unklarheit or "",
        ))

    nwf_annahme = annahmen["nwf_anteil_an_hnf"]
    hnf = sia.hauptnutzflaeche_hnf.wert
    if hnf is None:
        nwf = SIA416Wert(
            feld="wohnflaeche_nwf", wert=None, status=STATUS_NICHT_BESTIMMBAR,
            unklarheit="HNF ist nicht bestimmt -- die Wohnflaeche leitet sich daraus ab.",
        )
    else:
        nwf = SIA416Wert(
            feld="wohnflaeche_nwf", wert=round(hnf * nwf_annahme.wert, 1),
            status=STATUS_MODELLANNAHME_BASIERT,
            herkunft=f"[{nwf_annahme.herkunft}] NWF/HNF={nwf_annahme.wert:.2f}: {nwf_annahme.begruendung}",
        )
        rechenweg.append(_schritt(
            "wohnflaeche_nwf", hnf, f"x {nwf_annahme.wert:.0%} (Wohnanteil an der Hauptnutzflaeche)",
            nwf.wert, nwf.herkunft,
        ))

    wohnungen = berechne_wohnungen(
        nwf.wert, wohnungsmix, wohnungsmix_begruendung, restflaeche_verteilen,
        herkunft=wohnungsmix_herkunft)
    if wohnungen.get("anzahl_wohnungen"):
        rechenweg.append(_schritt(
            "wohnungen", nwf.wert, f"verteilt auf den Wohnungsmix ({wohnungen['eingabeart']})",
            wohnungen["anzahl_wohnungen"], wohnungen.get("hinweis", ""), einheit="Wohnungen",
        ))

    flaechen = {w.feld: {
        "wert": w.wert, "einheit": w.einheit, "status": w.status,
        "herkunft": w.herkunft, "unklarheit": w.unklarheit,
    } for w in list(sia.als_liste()) + [nwf]}

    return {
        "status": STATUS_MODELLANNAHME_BASIERT,
        "profil": profil,
        "annahmen": {k: a.to_dict() for k, a in annahmen.items()},
        "hoehenmodell": hoehen.to_dict(),
        "geschossaufbau": geschossaufbau.to_dict(),
        "volumen": volumen,
        "datenpruefung": ziffernbefunde,
        "flaechen": flaechen,
        "rechenweg": rechenweg,
        "wohnungen": wohnungen,
        "abgrenzung": (
            "GF stammt aus der realen Geometrie- und Baurechtskaskade. Alle Schritte "
            "danach beruhen auf den oben aufgefuehrten Annahmen -- SIA 416 definiert "
            "Messgroessen, keine Verhaeltnisse zwischen ihnen. Jede Annahme ist "
            "ueberschreibbar; eine Benutzerannahme hat immer Vorrang."
        ),
    }

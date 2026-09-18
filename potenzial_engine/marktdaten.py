"""
Block A -- Markt- und Referenzdaten, anbieterneutral.

Drei Ebenen, die nie vermischt werden:

    1  REFERENZDATEN       Vergleichsobjekte, woher auch immer sie stammen
    2  SYSTEMVORSCHLAG     daraus abgeleitete Orientierung, mit Sicherheitsgrad
    3  BENUTZERANNAHME     fuer die konkrete Rechnung -- hat immer Vorrang

Die Benutzerannahme lebt in `wirtschaftlichkeit.Marktwert`; dieses Modul
liefert die Ebenen 1 und 2 und uebergibt sie dorthin. Es gibt damit weiterhin
genau einen Rechenweg, keine zweite Marktlogik.

Anbieterneutral
---------------
`Vergleichsobjekt` ist auf KEINEN Anbieter zugeschnitten. Dieselbe Struktur
traegt eine Wueest-Partner-Auswertung, ein selbst erfasstes gebimo-Objekt,
einen CSV-Import und eine oeffentliche Quelle. Was die Quelle nicht liefert,
bleibt `None` -- nichts wird ergaenzt, um die Struktur zu fuellen.

Herkunftsarten (WOHER die Referenz kommt, nicht WIE gut sie ist):

    extern    kommerzielle oder oeffentliche Datenquelle
    gebimo    eigenes Vergleichsobjekt von gebimo
    manuell   im Einzelfall von Hand erfasst

Keine kuenstliche Genauigkeit
-----------------------------
Der Systemvorschlag ist der Median der PASSENDEN Vergleichsobjekte, versehen
mit einem Sicherheitsgrad aus Anzahl, Streuung und Aktualitaet. Bei zu wenig
oder zu heterogenen Daten heisst das Ergebnis ausdruecklich `gering` -- dann
ist die Bandbreite die Aussage, nicht der Punktwert. Eine bewertungsnahe
Gewichtung nach Mikrolage, Zustand und Ausbaustandard ist bewusst NICHT
gebaut: dafuer reicht die Datenbasis heute nicht, und ein Modell, das mehr
verspricht als seine Daten hergeben, waere genau die Scheingenauigkeit, die
ausgeschlossen ist. Welche Objekte einbezogen und welche ausgeschlossen
wurden, wird stattdessen offengelegt.

Netzwerkfrei und zustandslos -- die Aufbewahrung eigener Vergleichsobjekte
gehoert in die Datenschicht (`kern`), nicht in die Engine.
"""

from __future__ import annotations

import csv
import io
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional

from .wirtschaftlichkeit import (
    MIN_REFERENZEN_FUER_VORSCHLAG,
    Referenzwert,
    WirtschaftlichkeitError,
    marktwert,
)

HERKUNFT_EXTERN = "extern"
HERKUNFT_GEBIMO = "gebimo"
HERKUNFT_MANUELL = "manuell"
_HERKUNFTSARTEN = {HERKUNFT_EXTERN, HERKUNFT_GEBIMO, HERKUNFT_MANUELL}

# Die drei Marktgroessen, fuer die es Referenzen gibt.
GROESSE_VERKAUF = "verkauf"
GROESSE_MIETE = "miete"
GROESSE_BODEN = "boden"

_GROESSEN: dict[str, tuple[str, str, str]] = {
    # schluessel: (Feld im Vergleichsobjekt, Einheit, Klartext)
    GROESSE_VERKAUF: ("preis_chf_pro_m2", "CHF/m2", "Verkaufspreis"),
    GROESSE_MIETE: ("mietzins_chf_pro_m2_jahr", "CHF/m2/Jahr", "Mietzins"),
    GROESSE_BODEN: ("bodenpreis_chf_pro_m2", "CHF/m2", "Bodenpreis"),
}

# Wie belastbar ist die ERFASSTE ANGABE? Nicht: wie gut ist das Objekt.
# Drei Stufen plus "weiss nicht" -- die Stufe geht in den Sicherheitsgrad
# ein (siehe _sicherheit), wo "gering" und "unbekannt" gleich behandelt
# werden: beides heisst, dass man sich auf die Zahl nicht stuetzen kann.
QUALITAET_HOCH = "hoch"
QUALITAET_MITTEL = "mittel"
QUALITAET_GERING = "gering"
QUALITAET_UNBEKANNT = "unbekannt"
_QUALITAETEN = {QUALITAET_HOCH, QUALITAET_MITTEL, QUALITAET_GERING, QUALITAET_UNBEKANNT}

# Was eine Stufe bedeutet -- dieselben Saetze stehen im Erfassungsformular.
# Sie gehoeren hierher, weil die Skala hier definiert ist: zwei Stellen mit
# eigenen Erklaerungen driften auseinander.
QUALITAET_BEDEUTUNG = {
    QUALITAET_HOCH: "belegt -- aus Kaufvertrag, Abrechnung oder amtlicher Quelle",
    QUALITAET_MITTEL: "so angegeben -- aus Inserat, Expose oder Auskunft",
    QUALITAET_GERING: "geschaetzt oder abgeleitet",
    QUALITAET_UNBEKANNT: "nicht beurteilbar",
}

# Fruehere Bezeichnungen und gaengige Schreibweisen aus Fremdexporten.
#
# Diese Zuordnung ist AUSDRUECKLICH und dokumentiert (docs/blockA_marktdaten.md),
# weil sie zwischen zwei verschiedenen Achsen uebersetzt: die alte Auswahl im
# Formular beschrieb die HERKUNFT einer Angabe (geprueft / angegeben /
# geschaetzt), diese Skala beschreibt ihre BELASTBARKEIT. Das ist nicht
# dasselbe -- aber in dieser Richtung eindeutig: was belegt ist, ist
# belastbar; was geschaetzt ist, ist es nicht.
#
# Was NICHT in dieser Tabelle steht, wird nicht geraten. Es wird zu
# "unbekannt" und der Rohwert bleibt unter merkmale erhalten, damit die
# Einstufung nachpruefbar ist und nichts still verschwindet.
QUALITAET_SYNONYME = {
    "geprueft": QUALITAET_HOCH,
    "belegt": QUALITAET_HOCH,
    "beurkundet": QUALITAET_HOCH,
    "amtlich": QUALITAET_HOCH,
    "high": QUALITAET_HOCH,
    "angegeben": QUALITAET_MITTEL,
    "gemeldet": QUALITAET_MITTEL,
    "inserat": QUALITAET_MITTEL,
    "medium": QUALITAET_MITTEL,
    "geschaetzt": QUALITAET_GERING,
    "abgeleitet": QUALITAET_GERING,
    "berechnet": QUALITAET_GERING,
    "low": QUALITAET_GERING,
    "unknown": QUALITAET_UNBEKANNT,
    "keine": QUALITAET_UNBEKANNT,
}


def normalisiere_qualitaet(roh: Any) -> tuple[str, Optional[str]]:
    """Eine Stufe aus einer beliebigen Schreibweise.

    Liefert `(stufe, nicht_erkannt)`. Ist der zweite Wert gesetzt, enthaelt
    er den Rohtext -- die Einstufung lautet dann "unbekannt", und der
    Aufrufer haelt den Rohtext fest, statt ihn wegzuwerfen.

    Handerfassung (aus_dicts) und Import (lese_csv) rufen beide DIESE
    Funktion. Vorher normalisierte nur der CSV-Weg, und zwar still auf
    "unbekannt"; die Handerfassung wies dieselbe Eingabe rundweg ab. Damit
    hatte dasselbe Wort je nach Eingabeweg drei verschiedene Bedeutungen:
    hohe Qualitaet, keine Qualitaet, oder ein Fehler.
    """
    text = _normalisiere_spalte(str(roh or ""))
    if not text:
        return QUALITAET_UNBEKANNT, None
    if text in _QUALITAETEN:
        return text, None
    if text in QUALITAET_SYNONYME:
        return QUALITAET_SYNONYME[text], None
    return QUALITAET_UNBEKANNT, str(roh)

# Was der Preis BEDEUTET. Ein Inseratspreis ist kein Abschluss -- in der
# Schweiz liegen Angebotspreise systematisch ueber den beurkundeten Preisen,
# und um wie viel, weiss niemand ohne Handaenderungsdaten. Wer beides in
# denselben Median wirft, rechnet einen Aufschlag ein, den er nicht kennt.
PREISART_ANGEBOT = "angebot"
PREISART_ABSCHLUSS = "abschluss"
PREISART_UNBEKANNT = "unbekannt"
_PREISARTEN = {PREISART_ANGEBOT, PREISART_ABSCHLUSS, PREISART_UNBEKANNT}

SICHERHEIT_HOCH = "hoch"
SICHERHEIT_MITTEL = "mittel"
SICHERHEIT_GERING = "gering"
SICHERHEIT_KEINE = "keine_daten"

# Ab wie vielen passenden Objekten ein Punktwert ueberhaupt etwas aussagt.
# EINE Definition, aus `wirtschaftlichkeit` uebernommen: dort entsteht der
# Vorschlag technisch, hier wird er fachlich begruendet. Zwei eigene Zahlen
# waeren zwei Wahrheiten.
MIN_OBJEKTE_MITTEL = MIN_REFERENZEN_FUER_VORSCHLAG
MIN_OBJEKTE_HOCH = 6
# Relative Streuung (Spannweite / Median), ab der die Sicherheit sinkt.
MAX_STREUUNG_HOCH = 0.20
MAX_STREUUNG_MITTEL = 0.45
# Ab welchem Alter eine Referenz an Gewicht verliert.
MAX_ALTER_MONATE = 24

# Plausibilitaetsgrenzen -- KEINE Marktaussage, sondern Datenhygiene.
# Sie sagen nicht, was ein Quadratmeter wert ist, sondern welcher Wert
# ueberhaupt aus einem Grundstueckspreis stammen kann. Anlass sind echte
# Importfaelle: ein Bauland-Inserat ergab 0 CHF/m2 (Preis "auf Anfrage"),
# ein anderes 30'333 CHF/m2 (die Flaeche war die Gebaeudegrundflaeche, nicht
# die Parzelle). Beide haetten den Median still verschoben.
# Ausgeschlossene Objekte verschwinden nicht -- sie werden mit Grund
# ausgewiesen und lassen sich von Hand korrigieren.
PLAUSIBEL: dict[str, tuple[float, float]] = {
    GROESSE_VERKAUF: (1_000.0, 30_000.0),      # CHF/m2 Wohnflaeche
    GROESSE_MIETE: (60.0, 900.0),              # CHF/m2/Jahr
    GROESSE_BODEN: (50.0, 20_000.0),           # CHF/m2 Grundstueck
}

# Objektarten in einer kleinen, festen Sprache. Die Portale schreiben
# "Haus", "Einfamilienhaus", "Chalet", "Doppeleinfamilienhaus" und
# "Terrassenhaus" fuer dieselbe Sache -- ungefiltert waeren das fuenf
# unvergleichbare Gruppen.
OBJEKTART_WOHNUNG = "wohnung"
OBJEKTART_EFH = "efh"
OBJEKTART_MFH = "mfh"
OBJEKTART_HAUS = "haus"           # Haus, Art unbestimmt -- so steht es im Inserat
OBJEKTART_BAULAND = "bauland"
OBJEKTART_GEWERBE = "gewerbe"
OBJEKTART_UNBEKANNT = "unbekannt"

_OBJEKTART_WOERTER: tuple[tuple[str, str], ...] = (
    # Reihenfolge zaehlt: das spezifischere Wort zuerst.
    ("mehrfamilienhaus", OBJEKTART_MFH),
    ("wohn- und geschaeftshaus", OBJEKTART_MFH),
    ("renditeobjekt", OBJEKTART_MFH),
    ("einfamilienhaus", OBJEKTART_EFH),
    ("doppeleinfamilienhaus", OBJEKTART_EFH),
    ("reihenhaus", OBJEKTART_EFH),
    ("terrassenhaus", OBJEKTART_EFH),
    ("bauernhaus", OBJEKTART_EFH),
    ("chalet", OBJEKTART_EFH),
    ("villa", OBJEKTART_EFH),
    ("efh", OBJEKTART_EFH),
    ("mfh", OBJEKTART_MFH),
    ("eigentumswohnung", OBJEKTART_WOHNUNG),
    ("etw", OBJEKTART_WOHNUNG),
    ("attikawohnung", OBJEKTART_WOHNUNG),
    ("maisonette", OBJEKTART_WOHNUNG),
    ("wohnung", OBJEKTART_WOHNUNG),
    ("studio", OBJEKTART_WOHNUNG),
    ("bauland", OBJEKTART_BAULAND),
    ("bauparzelle", OBJEKTART_BAULAND),
    ("grundstueck", OBJEKTART_BAULAND),
    ("parzelle", OBJEKTART_BAULAND),
    ("gewerbe", OBJEKTART_GEWERBE),
    ("buero", OBJEKTART_GEWERBE),
    ("lager", OBJEKTART_GEWERBE),
    ("hotel", OBJEKTART_GEWERBE),
    ("haus", OBJEKTART_HAUS),
)


def normalisiere_objektart(roh: Optional[str]) -> str:
    """Bringt eine Objektart in die feste Sprache oben.

    Ein Inseratstext, der versehentlich im Feld Objektart landet (real
    beobachtet: eine ganze Homegate-Seite), ist keine Objektart -- zu lange
    Werte gelten als unbekannt statt als eigene Gruppe.
    """
    text = str(roh or "").strip()
    if not text or len(text) > 60:
        return OBJEKTART_UNBEKANNT
    text = _normalisiere_spalte(text)
    for wort, art in _OBJEKTART_WOERTER:
        if _normalisiere_spalte(wort) in text:
            return art
    return OBJEKTART_UNBEKANNT


class MarktdatenError(Exception):
    """Fehlerhafte oder unvollstaendige Marktdaten."""


# ---------------------------------------------------------------------------
# Das Vergleichsobjekt
# ---------------------------------------------------------------------------

@dataclass
class Vergleichsobjekt:
    """Ein Vergleichsobjekt -- unabhaengig davon, woher es stammt.

    Pflicht sind nur `quelle`, `datenstand` und `bezeichnung`: ohne Herkunft
    und Datum ist eine Referenz keine Referenz, sondern eine Behauptung. Alles
    Uebrige bleibt `None`, wenn die Quelle es nicht liefert.
    """
    bezeichnung: str
    quelle: str
    datenstand: str                      # ISO-Datum, z.B. "2026-06-30"
    herkunftsart: str = HERKUNFT_EXTERN
    anbieter: Optional[str] = None
    objekt_id: Optional[str] = None
    adresse: Optional[str] = None
    plz: Optional[str] = None
    gemeinde: Optional[str] = None
    kanton: Optional[str] = None
    objektart: Optional[str] = None      # z.B. "MFH", "EFH", "Bauland", "ETW"
    baujahr: Optional[int] = None
    flaeche_m2: Optional[float] = None
    zimmer: Optional[float] = None
    preis_chf: Optional[float] = None
    preis_chf_pro_m2: Optional[float] = None
    mietzins_chf_monat: Optional[float] = None
    mietzins_chf_pro_m2_jahr: Optional[float] = None
    grundstuecksflaeche_m2: Optional[float] = None
    bodenpreis_chf_pro_m2: Optional[float] = None
    datenqualitaet: str = QUALITAET_UNBEKANNT
    preisart: str = PREISART_UNBEKANNT
    bemerkung: Optional[str] = None
    merkmale: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for feld in ("bezeichnung", "quelle", "datenstand"):
            if not str(getattr(self, feld) or "").strip():
                raise MarktdatenError(
                    f"Vergleichsobjekt ohne '{feld}' ist nicht zulaessig -- ohne Herkunft und "
                    "Datum ist eine Referenz nicht von einer Behauptung zu unterscheiden."
                )
        if self.herkunftsart not in _HERKUNFTSARTEN:
            raise MarktdatenError(
                f"Unbekannte Herkunftsart '{self.herkunftsart}' -- erlaubt: {sorted(_HERKUNFTSARTEN)}"
            )
        if self.datenqualitaet not in _QUALITAETEN:
            raise MarktdatenError(
                f"Unbekannte Datenqualitaet '{self.datenqualitaet}' -- erlaubt: {sorted(_QUALITAETEN)}"
            )
        if self.preisart not in _PREISARTEN:
            raise MarktdatenError(
                f"Unbekannte Preisart '{self.preisart}' -- erlaubt: {sorted(_PREISARTEN)}"
            )
        if self.plz is not None:
            self.plz = str(self.plz).strip() or None
        self._leite_ab()

    @property
    def objektart_normal(self) -> str:
        """Die Objektart in der festen Sprache -- die Rohangabe bleibt erhalten."""
        return normalisiere_objektart(self.objektart)

    def _leite_ab(self) -> None:
        """Rechnet nur, was sich EINDEUTIG ergibt -- nichts wird geschaetzt."""
        if self.preis_chf_pro_m2 is None and self.preis_chf and self.flaeche_m2:
            self.preis_chf_pro_m2 = round(self.preis_chf / self.flaeche_m2, 2)
        if (self.mietzins_chf_pro_m2_jahr is None and self.mietzins_chf_monat
                and self.flaeche_m2):
            self.mietzins_chf_pro_m2_jahr = round(
                self.mietzins_chf_monat * 12 / self.flaeche_m2, 2)
        # Nur bei Bauland ist der Kaufpreis der Bodenpreis. Geprueft wird die
        # NORMALISIERTE Objektart: die Portale schreiben auch "Bauparzelle",
        # "Grundstueck" und "Gewerbegrundstueck" fuer dieselbe Sache.
        if (self.bodenpreis_chf_pro_m2 is None and self.preis_chf
                and self.grundstuecksflaeche_m2
                and normalisiere_objektart(self.objektart) == OBJEKTART_BAULAND):
            self.bodenpreis_chf_pro_m2 = round(
                self.preis_chf / self.grundstuecksflaeche_m2, 2)

    @property
    def alter_monate(self) -> Optional[int]:
        try:
            stand = datetime.fromisoformat(self.datenstand).date()
        except ValueError:
            try:
                stand = datetime.strptime(self.datenstand, "%Y-%m").date()
            except ValueError:
                return None
        heute = date.today()
        return (heute.year - stand.year) * 12 + (heute.month - stand.month)

    def wert_fuer(self, groesse: str) -> Optional[float]:
        if groesse not in _GROESSEN:
            raise MarktdatenError(f"Unbekannte Marktgroesse '{groesse}' -- erlaubt: {sorted(_GROESSEN)}")
        return getattr(self, _GROESSEN[groesse][0])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["alter_monate"] = self.alter_monate
        d["objektart_normal"] = self.objektart_normal
        return d

    def als_referenzwert(self, groesse: str) -> Optional[Referenzwert]:
        """Projiziert das Objekt auf EINE Marktgroesse.

        Damit fliesst es in denselben `Marktwert` wie jede andere Referenz --
        es gibt keinen zweiten Rechenweg.
        """
        wert = self.wert_fuer(groesse)
        if wert is None:
            return None
        return Referenzwert(
            quelle=f"{self.quelle}" + (f" / {self.anbieter}" if self.anbieter else ""),
            datum=self.datenstand,
            objekt=self.bezeichnung + (f", {self.gemeinde}" if self.gemeinde else ""),
            wert=float(wert),
            einheit=_GROESSEN[groesse][1],
            qualitaet=self.datenqualitaet,
        )


# ---------------------------------------------------------------------------
# Passung: welche Objekte sind ueberhaupt vergleichbar?
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Vergleichsfilter:
    """Wonach ein Vergleichsobjekt zum Projekt passen muss.

    Bewusst grob: Gemeinde, Kanton, Objektart, Baujahrfenster und Alter der
    Daten. Eine feinere Gewichtung nach Mikrolage, Zustand und Ausbaustandard
    braucht eine Datenbasis, die es heute nicht gibt.
    """
    gemeinde: Optional[str] = None
    plz: Optional[str] = None
    # Die ersten Stellen der PLZ als geografische Umgebung -- KEINE
    # Verwaltungseinheit. "50xx" heisst: derselbe Postkreis, nicht derselbe
    # Kanton. Wird nur fuer die ausdrueckliche Ausweitung benutzt.
    plz_praefix: Optional[str] = None
    kanton: Optional[str] = None
    objektart: Optional[str] = None
    baujahr_von: Optional[int] = None
    baujahr_bis: Optional[int] = None
    max_alter_monate: Optional[int] = MAX_ALTER_MONATE

    def _ort_passt(self, obj: Vergleichsobjekt, gleich) -> Optional[str]:
        """Die Ortspruefung -- PLZ zuerst, Gemeindename als Rueckfallebene."""
        sucht_ort = bool(self.plz or self.plz_praefix or self.gemeinde)
        if not sucht_ort:
            return None

        if self.plz and obj.plz:
            return (None if str(self.plz).strip() == str(obj.plz).strip()
                    else f"andere PLZ ({obj.plz})")
        if self.plz_praefix and obj.plz:
            return (None if str(obj.plz).strip().startswith(str(self.plz_praefix))
                    else f"andere PLZ-Region ({obj.plz})")
        if self.gemeinde and obj.gemeinde:
            return (None if gleich(self.gemeinde, obj.gemeinde)
                    else f"andere Gemeinde ({obj.gemeinde})")
        return ("Lage nicht vergleichbar -- weder PLZ noch Gemeinde sind auf beiden "
                "Seiten bekannt")

    def pruefe(self, obj: Vergleichsobjekt) -> Optional[str]:
        """None wenn das Objekt passt, sonst der Ausschlussgrund."""
        def gleich(a, b):
            return (a or "").strip().lower() == (b or "").strip().lower()

        # --- Lage --------------------------------------------------------
        # Zwei Ortsschluessel, und sie fehlen in unterschiedlichen Quellen:
        # Portalinserate fuehren fast immer eine PLZ und oft keinen Kanton,
        # von Hand erfasste Referenzen fuehren meist einen Gemeindenamen und
        # keine PLZ. Deshalb wird der Reihe nach geprueft, was BEIDE haben --
        # und nur wenn keiner der beiden Schluessel auf beiden Seiten
        # vorliegt, gilt die Lage als nicht vergleichbar.
        #
        # Die Reihenfolge ist nicht beliebig: die PLZ schlaegt den Namen, denn
        # es gibt vier Gemeinden namens Buchs. Ohne sie waere ein Bauland in
        # Buchs ZH eine Referenz fuer Buchs AG.
        grund = self._ort_passt(obj, gleich)
        if grund:
            return grund
        if self.kanton and obj.kanton and not gleich(self.kanton, obj.kanton):
            return f"anderer Kanton ({obj.kanton})"
        # Verglichen wird die NORMALISIERTE Objektart: "Haus", "Chalet" und
        # "Reihenhaus" sind im Inserat drei Woerter und fachlich eine Gruppe.
        if self.objektart and obj.objektart:
            if normalisiere_objektart(self.objektart) != obj.objektart_normal:
                return f"andere Objektart ({obj.objektart})"
        if self.baujahr_von and obj.baujahr and obj.baujahr < self.baujahr_von:
            return f"Baujahr {obj.baujahr} vor {self.baujahr_von}"
        if self.baujahr_bis and obj.baujahr and obj.baujahr > self.baujahr_bis:
            return f"Baujahr {obj.baujahr} nach {self.baujahr_bis}"
        alter = obj.alter_monate
        if self.max_alter_monate is not None and alter is not None and alter > self.max_alter_monate:
            return f"Datenstand {alter} Monate alt (Grenze {self.max_alter_monate})"
        return None


# ---------------------------------------------------------------------------
# Die Referenz-Auswertung
# ---------------------------------------------------------------------------

def eignung(obj: Vergleichsobjekt, groesse: str) -> Optional[str]:
    """Darf dieses Objekt fuer DIESE Marktgroesse verwendet werden?

    Gibt None zurueck, wenn es passt, sonst den Ausschlussgrund.

    Der Fall, um den es hier geht: ein Inserat fuer ein bestehendes
    Mehrfamilienhaus nennt einen Angebotspreis fuer das ganze Haus. Geteilt
    durch die Wohnflaeche ergibt das eine Zahl in CHF/m2 -- aber diese Zahl
    beantwortet die Frage "was kostet dieses Bestandshaus", nicht die Frage
    "fuer wie viel lassen sich hier neu gebaute Wohnungen verkaufen". Genau
    Letzteres rechnet die Wirtschaftlichkeit. Die beiden zu vermischen waere
    kein Datenmangel, sondern ein Methodenfehler.

    Von Hand erfasste Referenzen (manuell, gebimo) bleiben immer zugelassen:
    dort entscheidet der Benutzer, was er als Vergleich heranzieht -- so wie
    die Benutzerannahme ueberall in diesem Werkzeug Vorrang hat.
    """
    if groesse != GROESSE_VERKAUF:
        return None
    if obj.herkunftsart in (HERKUNFT_MANUELL, HERKUNFT_GEBIMO):
        return None
    if obj.preisart == PREISART_ABSCHLUSS:
        return None
    art = obj.objektart_normal
    if art == OBJEKTART_WOHNUNG:
        return None
    return (
        f"Angebotspreis fuer ein ganzes Objekt ({obj.objektart or 'Art unbekannt'}) -- "
        "das ist der Preis des Bestands, nicht der Verkaufspreis neu gebauter "
        "Wohnungen. Als Verkaufsreferenz taugen Wohnungspreise oder beurkundete "
        "Abschluesse."
    )


def plausibel(wert: float, groesse: str) -> Optional[str]:
    """Kann dieser Wert ueberhaupt aus einem Preis stammen?

    Keine Marktaussage -- reine Datenhygiene. Siehe `PLAUSIBEL`.
    """
    grenzen = PLAUSIBEL.get(groesse)
    if not grenzen:
        return None
    unten, oben = grenzen
    if wert < unten:
        return (f"{wert:,.0f} unterschreitet die Plausibilitaetsgrenze von {unten:,.0f} "
                f"{_GROESSEN[groesse][1]} -- vermutlich fehlt der Preis oder die Flaeche.")
    if wert > oben:
        return (f"{wert:,.0f} ueberschreitet die Plausibilitaetsgrenze von {oben:,.0f} "
                f"{_GROESSEN[groesse][1]} -- vermutlich ist die Flaeche nicht die, "
                "auf die sich der Preis bezieht.")
    return None


# Ab wie vielen Werten sich ein Ausreisser ueberhaupt bestimmen laesst.
MIN_OBJEKTE_AUSREISSER = 5
AUSREISSER_FAKTOR = 1.5


def _ausreisser(werte: list[float]) -> tuple[float, float]:
    """Der Bereich, ausserhalb dessen ein Wert als Ausreisser gilt.

    Quartilsabstand statt Standardabweichung: Immobilienpreise sind
    rechtsschief, und genau der eine falsche Wert, den wir suchen, wuerde die
    Standardabweichung so aufblaehen, dass er selbst wieder hineinpasst.

    Unter `MIN_OBJEKTE_AUSREISSER` Werten wird NICHT aussortiert -- bei vier
    Beobachtungen ist nicht zu unterscheiden, ob eine davon falsch ist oder
    ob der Markt einfach streut. Dann sinkt stattdessen die Sicherheit.
    """
    sortiert = sorted(werte)
    q1 = statistics.median(sortiert[: len(sortiert) // 2])
    q2 = statistics.median(sortiert[(len(sortiert) + 1) // 2:])
    abstand = q2 - q1
    return (q1 - AUSREISSER_FAKTOR * abstand, q2 + AUSREISSER_FAKTOR * abstand)


def _sicherheit(werte: list[float], objekte: list[Vergleichsobjekt]) -> tuple[str, list[str]]:
    """Wie belastbar ist ein Punktwert aus diesen Referenzen?

    Drei Kriterien, alle einzeln begruendet: Anzahl, Streuung, Aktualitaet.
    """
    gruende: list[str] = []
    if not werte:
        return SICHERHEIT_KEINE, ["Keine passenden Vergleichsobjekte."]

    stufe = SICHERHEIT_HOCH
    if len(werte) < MIN_OBJEKTE_MITTEL:
        stufe = SICHERHEIT_GERING
        gruende.append(
            f"Nur {len(werte)} passende(s) Vergleichsobjekt(e) -- unter {MIN_OBJEKTE_MITTEL} "
            "ist ein Punktwert nicht belastbar, die Bandbreite ist die Aussage."
        )
    elif len(werte) < MIN_OBJEKTE_HOCH:
        stufe = SICHERHEIT_MITTEL
        gruende.append(f"{len(werte)} passende Vergleichsobjekte (ab {MIN_OBJEKTE_HOCH} gilt hoch).")

    median = statistics.median(werte)
    streuung = (max(werte) - min(werte)) / median if median else 0.0
    if streuung > MAX_STREUUNG_MITTEL:
        stufe = SICHERHEIT_GERING
        gruende.append(
            f"Die Vergleichswerte streuen um {streuung:.0%} des Medians -- die Objekte sind "
            "untereinander zu unterschiedlich fuer einen belastbaren Punktwert."
        )
    elif streuung > MAX_STREUUNG_HOCH and stufe == SICHERHEIT_HOCH:
        stufe = SICHERHEIT_MITTEL
        gruende.append(f"Die Vergleichswerte streuen um {streuung:.0%} des Medians.")

    alter = [o.alter_monate for o in objekte if o.alter_monate is not None]
    if alter and min(alter) > 12:
        if stufe == SICHERHEIT_HOCH:
            stufe = SICHERHEIT_MITTEL
        gruende.append(f"Die neueste Referenz ist {min(alter)} Monate alt.")

    # Reine Angebotsdaten koennen nie "hoch" werden. Ein Inseratspreis ist
    # das, was jemand verlangt -- nicht das, was jemand bezahlt hat. Der
    # Abstand dazwischen ist systematisch und ohne Handaenderungsdaten nicht
    # zu beziffern. Ihn wegzulassen hiesse, eine Unsicherheit zu verschweigen,
    # die wir kennen.
    if objekte and all(o.preisart != PREISART_ABSCHLUSS for o in objekte):
        if stufe == SICHERHEIT_HOCH:
            stufe = SICHERHEIT_MITTEL
        gruende.append(
            "Keine der Referenzen ist ein beurkundeter Abschluss -- ohne Handaenderungs"
            "daten bleibt die Sicherheit hoechstens mittel."
        )

    gering_qualitaet = [o for o in objekte if o.datenqualitaet in (QUALITAET_GERING, QUALITAET_UNBEKANNT)]
    if gering_qualitaet:
        gruende.append(
            f"{len(gering_qualitaet)} von {len(objekte)} Referenzen haben geringe oder "
            "unbekannte Datenqualitaet."
        )
    if not gruende:
        gruende.append(
            f"{len(werte)} passende Vergleichsobjekte, Streuung {streuung:.0%}, aktuell."
        )
    return stufe, gruende


@dataclass
class Marktreferenz:
    """Die ausgewertete Referenzlage fuer EINE Marktgroesse."""
    groesse: str
    einheit: str
    bezeichnung: str
    objekte: list[Vergleichsobjekt]
    ausgeschlossen: list[dict[str, Any]]
    sicherheit: str
    begruendung: list[str]

    @property
    def werte(self) -> list[float]:
        return [w for w in (o.wert_fuer(self.groesse) for o in self.objekte) if w is not None]

    @property
    def spanne(self) -> Optional[tuple[float, float]]:
        w = self.werte
        return (min(w), max(w)) if w else None

    @property
    def median(self) -> Optional[float]:
        w = self.werte
        return round(statistics.median(w), 2) if w else None

    @property
    def systemvorschlag(self) -> Optional[float]:
        """Der Median -- aber nur, wenn die Datenbasis ihn traegt.

        Unter `MIN_OBJEKTE_MITTEL` Referenzen gibt es KEINEN Punktwert. Zwei
        Beobachtungen haben einen Median, aber er ist keine Orientierung: er
        sagt nur, was zufaellig in der Mitte dieser zwei lag. Die Spanne wird
        weiterhin ausgewiesen -- sie ist dann die ganze Aussage.
        """
        if len(self.werte) < MIN_OBJEKTE_MITTEL:
            return None
        return self.median

    @property
    def mindestanforderung_erfuellt(self) -> bool:
        return len(self.werte) >= MIN_OBJEKTE_MITTEL

    def ausschluss_nach_art(self) -> dict[str, int]:
        zaehler: dict[str, int] = {}
        for e in self.ausgeschlossen:
            zaehler[e.get("art", "?")] = zaehler.get(e.get("art", "?"), 0) + 1
        return zaehler

    def _ausschluss_auswahl(self, hoechstens: int = 40) -> list[dict[str, Any]]:
        rang = {"ausreisser": 0, "unplausibel": 1, "nicht_geeignet": 2,
                "passt_nicht": 3, "kein_wert": 4}
        sortiert = sorted(self.ausgeschlossen, key=lambda e: rang.get(e.get("art"), 9))
        return sortiert[:hoechstens]

    def nach_preisart(self) -> dict[str, int]:
        zaehler: dict[str, int] = {}
        for o in self.objekte:
            zaehler[o.preisart] = zaehler.get(o.preisart, 0) + 1
        return zaehler

    def nach_herkunft(self) -> dict[str, int]:
        zaehler: dict[str, int] = {}
        for o in self.objekte:
            zaehler[o.herkunftsart] = zaehler.get(o.herkunftsart, 0) + 1
        return zaehler

    def to_dict(self) -> dict[str, Any]:
        spanne = self.spanne
        return {
            "groesse": self.groesse,
            "bezeichnung": self.bezeichnung,
            "einheit": self.einheit,
            "anzahl": len(self.objekte),
            "spanne": list(spanne) if spanne else None,
            "median": self.median,
            "systemvorschlag": self.systemvorschlag,
            "sicherheit": self.sicherheit,
            "begruendung": self.begruendung,
            "nach_herkunft": self.nach_herkunft(),
            "nach_preisart": self.nach_preisart(),
            "mindestanforderung": {
                "erfuellt": self.mindestanforderung_erfuellt,
                "min_objekte": MIN_OBJEKTE_MITTEL,
                "vorhanden": len(self.werte),
            },
            "objekte": [o.to_dict() for o in self.objekte],
            # Nur eine Auswahl: bei 1'385 Referenzen haben ueber 1'300 schlicht
            # keinen Wert fuer diese Groesse, und die Antwort waere zu 90 %
            # eine Liste von Nichtvorkommnissen. Die aussagekraeftigen
            # Ausschluesse stehen zuerst -- Zahlen zu allen in
            # "ausgeschlossen_nach_art".
            "ausgeschlossen": self._ausschluss_auswahl(),
            "ausgeschlossen_gesamt": len(self.ausgeschlossen),
            "ausgeschlossen_nach_art": self.ausschluss_nach_art(),
            "punktwert_belastbar": (self.mindestanforderung_erfuellt
                                    and self.sicherheit in (SICHERHEIT_HOCH, SICHERHEIT_MITTEL)),
        }

    def als_marktwert(self, benutzerannahme: Optional[float] = None):
        """Uebergibt die Referenzlage an die Wirtschaftlichkeit.

        Der Systemvorschlag wird ausdruecklich gesetzt (statt ihn dort erneut
        aus den Referenzen zu bilden), damit Sicherheitsbewertung und
        Vorschlag aus derselben Auswertung stammen.
        """
        referenzen = [r for r in (o.als_referenzwert(self.groesse) for o in self.objekte) if r]
        hinweis = f"Sicherheit {self.sicherheit}: " + " ".join(self.begruendung)
        if not self.mindestanforderung_erfuellt:
            hinweis = (
                f"Kein Systemvorschlag: {len(self.werte)} Referenz(en), noetig sind "
                f"{MIN_OBJEKTE_MITTEL}. Ohne diese Grundlage waere ein Punktwert eine "
                "Behauptung. " + hinweis
            )
        elif self.sicherheit == SICHERHEIT_GERING:
            hinweis = (
                "Der Systemvorschlag ist nur schwach gestuetzt -- als Aussage taugt hier die "
                "Bandbreite, nicht der Punktwert. " + hinweis
            )
        angebote = self.nach_preisart().get(PREISART_ANGEBOT, 0)
        if angebote:
            hinweis += (
                f" {angebote} von {len(self.objekte)} Referenzen sind Angebotspreise, keine "
                "beurkundeten Abschluesse -- Angebotspreise liegen in der Regel hoeher."
            )
        return marktwert(
            self.groesse, self.einheit,
            referenzen=referenzen,
            systemvorschlag=self.systemvorschlag,
            benutzerannahme=benutzerannahme,
            begruendung=hinweis,
        )


def werte_referenzen_aus(
    objekte: Iterable[Vergleichsobjekt],
    groesse: str,
    filter_: Optional[Vergleichsfilter] = None,
) -> Marktreferenz:
    """Filtert die Vergleichsobjekte und wertet sie fuer eine Groesse aus.

    Ausgeschlossene Objekte verschwinden nicht -- sie werden mit Grund
    ausgewiesen, damit nachvollziehbar bleibt, worauf der Vorschlag beruht.
    """
    if groesse not in _GROESSEN:
        raise MarktdatenError(f"Unbekannte Marktgroesse '{groesse}' -- erlaubt: {sorted(_GROESSEN)}")
    _, einheit, bezeichnung = _GROESSEN[groesse]
    filter_ = filter_ or Vergleichsfilter()

    passend: list[Vergleichsobjekt] = []
    ausgeschlossen: list[dict[str, Any]] = []

    def raus(obj: Vergleichsobjekt, grund: str, art: str) -> None:
        ausgeschlossen.append({
            "bezeichnung": obj.bezeichnung, "quelle": obj.quelle,
            "art": art, "grund": grund,
        })

    # Vier Pruefungen in fester Reihenfolge. Jede beantwortet eine eigene
    # Frage, und jeder Ausschluss traegt seinen Grund mit.
    for obj in objekte:
        wert = obj.wert_fuer(groesse)
        if wert is None:                                   # 1 hat es den Wert?
            raus(obj, f"kein Wert fuer {bezeichnung}", "kein_wert")
            continue
        grund = eignung(obj, groesse)                      # 2 darf er das sein?
        if grund:
            raus(obj, grund, "nicht_geeignet")
            continue
        grund = plausibel(wert, groesse)                   # 3 kann er stimmen?
        if grund:
            raus(obj, grund, "unplausibel")
            continue
        grund = filter_.pruefe(obj)                        # 4 passt er hierher?
        if grund:
            raus(obj, grund, "passt_nicht")
            continue
        passend.append(obj)

    # 5 Ausreisser -- erst jetzt, auf den tatsaechlich vergleichbaren Objekten.
    werte = [w for w in (o.wert_fuer(groesse) for o in passend) if w is not None]
    if len(werte) >= MIN_OBJEKTE_AUSREISSER:
        unten, oben = _ausreisser(werte)
        behalten: list[Vergleichsobjekt] = []
        for obj in passend:
            wert = obj.wert_fuer(groesse)
            if wert is not None and not (unten <= wert <= oben):
                raus(obj, f"{wert:,.0f} {einheit} liegt ausserhalb des Quartilsbereichs "
                          f"({unten:,.0f} bis {oben:,.0f}) der uebrigen "
                          f"{len(werte)} Referenzen", "ausreisser")
            else:
                behalten.append(obj)
        passend = behalten
        werte = [w for w in (o.wert_fuer(groesse) for o in passend) if w is not None]

    sicherheit, begruendung = _sicherheit(werte, passend)
    if ausgeschlossen:
        nach_art: dict[str, int] = {}
        for e in ausgeschlossen:
            nach_art[e["art"]] = nach_art.get(e["art"], 0) + 1
        klartext = {
            "kein_wert": "ohne Wert", "nicht_geeignet": "fachlich ungeeignet",
            "unplausibel": "unplausibel", "passt_nicht": "passt nicht zum Projekt",
            "ausreisser": "Ausreisser",
        }
        begruendung.append(
            f"{len(ausgeschlossen)} Objekt(e) nicht einbezogen ("
            + ", ".join(f"{n}x {klartext.get(a, a)}" for a, n in nach_art.items())
            + ")."
        )
    return Marktreferenz(
        groesse=groesse, einheit=einheit, bezeichnung=bezeichnung,
        objekte=passend, ausgeschlossen=ausgeschlossen,
        sicherheit=sicherheit, begruendung=begruendung,
    )


# ---------------------------------------------------------------------------
# Was tun, wenn am Ort selbst zu wenige Referenzen liegen?
# ---------------------------------------------------------------------------

GEBIET_PLZ = "plz"
GEBIET_PLZ_REGION = "plz_region"
GEBIET_GEMEINDE = "gemeinde"

_GEBIET_TEXT = {
    GEBIET_PLZ: "gleiche PLZ",
    GEBIET_PLZ_REGION: "PLZ-Region",
    GEBIET_GEMEINDE: "gleiche Gemeinde",
}


def werte_mit_ausweitung(
    objekte: Iterable[Vergleichsobjekt],
    groesse: str,
    *,
    gemeinde: Optional[str] = None,
    plz: Optional[str] = None,
    objektart: Optional[str] = None,
    max_alter_monate: Optional[int] = MAX_ALTER_MONATE,
) -> tuple[Marktreferenz, dict[str, Any]]:
    """Wertet am Ort aus -- und weitet nur aus, wenn es dort zu wenig gibt.

    Die Frage, die dahintersteht: eine einzelne Gemeinde hat selten drei
    vergleichbare Inserate gleichzeitig am Markt. Dann gibt es zwei ehrliche
    Antworten -- "keine Aussage" oder "eine Aussage ueber ein groesseres
    Gebiet". Die zweite ist brauchbarer, aber nur, wenn dabeisteht, worueber
    sie eine Aussage macht.

    Deshalb wird die Ausweitung AUSGEWIESEN, nicht stillschweigend gemacht,
    und sie geht nur einen Schritt weit: von der PLZ auf die PLZ-Region (die
    ersten beiden Stellen). Eine gesamtschweizerische Auswertung gibt es
    nicht -- Bodenpreise von 82 bis 4'956 CHF/m2 in einem Median
    zusammenzufassen waere eine Zahl ohne Gegenstand.

    Liefert (referenz, gebiet) -- `gebiet` sagt, welche Stufe gilt und warum.
    """
    objekte = list(objekte)

    def versuch(f: Vergleichsfilter) -> Marktreferenz:
        return werte_referenzen_aus(objekte, groesse, f)

    stufen: list[tuple[str, str, Vergleichsfilter]] = []
    if plz:
        # `gemeinde` wird auf jeder Stufe mitgegeben: von Hand erfasste
        # Referenzen fuehren einen Gemeindenamen und keine PLZ und wuerden
        # sonst aus der eigenen Gemeinde herausfallen.
        stufen.append((GEBIET_PLZ, str(plz), Vergleichsfilter(
            plz=str(plz), gemeinde=gemeinde, objektart=objektart,
            max_alter_monate=max_alter_monate)))
        if len(str(plz)) >= 2:
            praefix = str(plz)[:2]
            stufen.append((GEBIET_PLZ_REGION, f"{praefix}xx", Vergleichsfilter(
                plz_praefix=praefix, gemeinde=gemeinde, objektart=objektart,
                max_alter_monate=max_alter_monate)))
    elif gemeinde:
        stufen.append((GEBIET_GEMEINDE, gemeinde, Vergleichsfilter(
            gemeinde=gemeinde, objektart=objektart, max_alter_monate=max_alter_monate)))
    else:
        stufen.append((GEBIET_GEMEINDE, "ohne Ortsangabe", Vergleichsfilter(
            objektart=objektart, max_alter_monate=max_alter_monate)))

    verlauf: list[dict[str, Any]] = []
    ergebnis: Marktreferenz
    gewaehlt = stufen[0]
    for stufe, bezeichnung, f in stufen:
        r = versuch(f)
        verlauf.append({"stufe": stufe, "bezeichnung": bezeichnung,
                        "referenzen": len(r.werte)})
        ergebnis, gewaehlt = r, (stufe, bezeichnung, f)
        if r.mindestanforderung_erfuellt:
            break

    gebiet = {
        "stufe": gewaehlt[0],
        "bezeichnung": gewaehlt[1],
        "text": _GEBIET_TEXT.get(gewaehlt[0], gewaehlt[0]),
        "ausgeweitet": gewaehlt[0] != stufen[0][0],
        "verlauf": verlauf,
    }
    if gebiet["ausgeweitet"]:
        gebiet["hinweis"] = (
            f"Am Ort selbst lagen zu wenige Referenzen vor ({verlauf[0]['referenzen']} statt "
            f"{MIN_OBJEKTE_MITTEL}). Ausgewertet wurde deshalb die PLZ-Region "
            f"{gewaehlt[1]} -- das ist eine Aussage ueber die Umgebung, nicht ueber "
            "diese Gemeinde."
        )
        ergebnis.begruendung.insert(0, gebiet["hinweis"])
    elif not ergebnis.mindestanforderung_erfuellt:
        gebiet["hinweis"] = (
            f"Auch nach Ausweitung reichen die Referenzen nicht ({len(ergebnis.werte)} statt "
            f"{MIN_OBJEKTE_MITTEL}). Es gibt deshalb keinen Systemvorschlag -- der Wert "
            "muss als eigene Annahme gesetzt werden."
        )
    return ergebnis, gebiet

def marktlage(
    objekte: Iterable[Vergleichsobjekt],
    filter_: Optional[Vergleichsfilter] = None,
) -> dict[str, Marktreferenz]:
    """Alle drei Marktgroessen auf einmal."""
    objekte = list(objekte)
    return {g: werte_referenzen_aus(objekte, g, filter_) for g in _GROESSEN}


# ---------------------------------------------------------------------------
# Import: CSV, anbieterneutral
# ---------------------------------------------------------------------------

# Welche Spaltennamen auf welches Feld zeigen. Bewusst grosszuegig, damit
# Exporte verschiedener Anbieter ohne Codeaenderung einlesbar sind.
_SPALTEN: dict[str, tuple[str, ...]] = {
    "bezeichnung": ("bezeichnung", "objekt", "name", "titel", "beschreibung"),
    "quelle": ("quelle", "source"),
    "anbieter": ("anbieter", "provider", "datenanbieter"),
    "objekt_id": ("objekt_id", "objektid", "id", "referenz"),
    "datenstand": ("datenstand", "datum", "stand", "date"),
    "adresse": ("adresse", "strasse", "address"),
    "plz": ("plz", "postleitzahl", "npa", "zip"),
    "preisart": ("preisart", "preis_art", "art_des_preises"),
    "gemeinde": ("gemeinde", "ort", "stadt", "municipality"),
    "kanton": ("kanton", "canton", "kt"),
    "objektart": ("objektart", "typ", "art", "kategorie"),
    "baujahr": ("baujahr", "bj", "year"),
    "flaeche_m2": ("flaeche_m2", "flaeche", "wohnflaeche", "flaeche m2", "area"),
    "zimmer": ("zimmer", "zi", "rooms"),
    "preis_chf": ("preis_chf", "preis", "kaufpreis", "price"),
    "preis_chf_pro_m2": ("preis_chf_pro_m2", "preis_pro_m2", "chf/m2", "preis m2"),
    "mietzins_chf_monat": ("mietzins_chf_monat", "miete", "mietzins", "monatsmiete"),
    "mietzins_chf_pro_m2_jahr": ("mietzins_chf_pro_m2_jahr", "miete_pro_m2_jahr", "mietzins m2"),
    "grundstuecksflaeche_m2": ("grundstuecksflaeche_m2", "grundstueck", "landflaeche", "parzelle"),
    "bodenpreis_chf_pro_m2": ("bodenpreis_chf_pro_m2", "bodenpreis", "landpreis"),
    "datenqualitaet": ("datenqualitaet", "qualitaet", "quality"),
    "bemerkung": ("bemerkung", "notiz", "kommentar", "remark"),
}

def _normalisiere_spalte(name: str) -> str:
    """Vergleichsform eines Spaltennamens.

    Schweizer und deutsche Exporte schreiben "Wohnflaeche" mal so, mal
    "Wohnfläche", mal "Wohnfl. m2". Ohne Umlautfaltung und Zeichenbereinigung
    faende der Import diese Spalten nicht -- live beobachtet an einem CSV mit
    "Wohnfläche" und "Qualität", deren Werte still unter `merkmale` landeten
    statt in den Feldern.
    """
    ersetzungen = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe",
                   "Ü": "ue", "ß": "ss", "é": "e", "è": "e", "à": "a"}
    text = "".join(ersetzungen.get(z, z) for z in name.strip().lower())
    return "".join(z for z in text if z.isalnum())


_ZAHLENFELDER = {
    "baujahr", "flaeche_m2", "zimmer", "preis_chf", "preis_chf_pro_m2",
    "mietzins_chf_monat", "mietzins_chf_pro_m2_jahr", "grundstuecksflaeche_m2",
    "bodenpreis_chf_pro_m2",
}


def _zahl(text: Any) -> Optional[float]:
    if text in (None, ""):
        return None
    s = str(text).strip().replace("'", "").replace("’", "").replace(" ", "")
    s = s.replace("CHF", "").replace("chf", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def lese_csv(
    text: str,
    quelle: str,
    herkunftsart: str = HERKUNFT_EXTERN,
    datenstand: Optional[str] = None,
) -> tuple[list[Vergleichsobjekt], list[dict[str, Any]]]:
    """Liest Vergleichsobjekte aus einem CSV -- ohne Anbieterbindung.

    Die Spaltenzuordnung erfolgt ueber bekannte Synonyme (siehe `_SPALTEN`);
    unbekannte Spalten landen unveraendert unter `merkmale`, damit nichts
    verloren geht. `quelle` und `datenstand` koennen global gesetzt werden,
    falls das CSV sie nicht je Zeile fuehrt.

    Liefert (objekte, fehler) -- eine unbrauchbare Zeile stoppt den Import
    nicht, sie wird mit Grund gemeldet.
    """
    if herkunftsart not in _HERKUNFTSARTEN:
        raise MarktdatenError(f"Unbekannte Herkunftsart '{herkunftsart}'.")

    probe = text[:2048]
    try:
        dialekt = csv.Sniffer().sniff(probe, delimiters=";,\t")
    except csv.Error:
        dialekt = csv.excel
        dialekt.delimiter = ";" if probe.count(";") > probe.count(",") else ","

    leser = csv.DictReader(io.StringIO(text), dialect=dialekt)
    rueck: dict[str, str] = {}
    normalisiert = {feld: {_normalisiere_spalte(s_) for s_ in syn}
                    for feld, syn in _SPALTEN.items()}
    for feld, synonyme in normalisiert.items():
        for spalte in leser.fieldnames or []:
            if spalte and _normalisiere_spalte(spalte) in synonyme:
                rueck[spalte] = feld
                break

    objekte: list[Vergleichsobjekt] = []
    fehler: list[dict[str, Any]] = []
    for nr, zeile in enumerate(leser, start=2):
        daten: dict[str, Any] = {}
        merkmale: dict[str, Any] = {}
        for spalte, wert in zeile.items():
            if spalte is None:
                continue
            feld = rueck.get(spalte)
            if feld is None:
                if str(wert or "").strip():
                    merkmale[spalte.strip()] = wert
                continue
            daten[feld] = _zahl(wert) if feld in _ZAHLENFELDER else (str(wert).strip() or None)
        if daten.get("baujahr") is not None:
            daten["baujahr"] = int(daten["baujahr"])
        daten.setdefault("quelle", None)
        daten["quelle"] = daten.get("quelle") or quelle
        daten["datenstand"] = daten.get("datenstand") or datenstand
        daten["herkunftsart"] = herkunftsart
        daten["merkmale"] = merkmale
        daten["datenqualitaet"], roh_qualitaet = normalisiere_qualitaet(
            daten.get("datenqualitaet"))
        if roh_qualitaet is not None:
            # Nicht erkannt heisst "unbekannt" -- aber der Rohtext bleibt
            # stehen. Ihn wegzuwerfen hiesse, eine Einstufung zu behaupten,
            # die niemand nachpruefen kann.
            merkmale["datenqualitaet_roh"] = roh_qualitaet
        if not daten.get("bezeichnung"):
            daten["bezeichnung"] = daten.get("adresse") or daten.get("objekt_id") or f"Zeile {nr}"
        try:
            objekte.append(Vergleichsobjekt(**daten))
        except (MarktdatenError, TypeError) as exc:
            fehler.append({"zeile": nr, "grund": str(exc), "rohdaten": zeile})
    return objekte, fehler


def aus_dicts(eintraege: Iterable[dict[str, Any]]) -> tuple[list[Vergleichsobjekt], list[dict[str, Any]]]:
    """Vergleichsobjekte aus JSON-artigen Dicts (API, Datenschicht, Formular)."""
    objekte: list[Vergleichsobjekt] = []
    fehler: list[dict[str, Any]] = []
    erlaubt = set(Vergleichsobjekt.__dataclass_fields__)
    for i, eintrag in enumerate(eintraege):
        daten = {k: v for k, v in (eintrag or {}).items() if k in erlaubt}
        unbekannt = {k: v for k, v in (eintrag or {}).items() if k not in erlaubt}
        if unbekannt:
            daten["merkmale"] = {**(daten.get("merkmale") or {}), **unbekannt}
        # Derselbe Weg wie beim CSV-Import. Vorher gab es hier gar keine
        # Normalisierung: dieselbe Eingabe wurde ueber den einen Weg
        # stillschweigend zu "unbekannt" und ueber den anderen rundweg
        # abgewiesen -- inklusive der Vorauswahl des eigenen Formulars.
        if "datenqualitaet" in daten:
            daten["datenqualitaet"], roh_qualitaet = normalisiere_qualitaet(
                daten["datenqualitaet"])
            if roh_qualitaet is not None:
                daten["merkmale"] = {**(daten.get("merkmale") or {}),
                                     "datenqualitaet_roh": roh_qualitaet}
        try:
            objekte.append(Vergleichsobjekt(**daten))
        except (MarktdatenError, TypeError) as exc:
            fehler.append({"index": i, "grund": str(exc), "rohdaten": eintrag})
    return objekte, fehler

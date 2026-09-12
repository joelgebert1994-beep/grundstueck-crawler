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

from .wirtschaftlichkeit import Referenzwert, WirtschaftlichkeitError, marktwert

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

QUALITAET_HOCH = "hoch"
QUALITAET_MITTEL = "mittel"
QUALITAET_GERING = "gering"
QUALITAET_UNBEKANNT = "unbekannt"
_QUALITAETEN = {QUALITAET_HOCH, QUALITAET_MITTEL, QUALITAET_GERING, QUALITAET_UNBEKANNT}

SICHERHEIT_HOCH = "hoch"
SICHERHEIT_MITTEL = "mittel"
SICHERHEIT_GERING = "gering"
SICHERHEIT_KEINE = "keine_daten"

# Ab wie vielen passenden Objekten ein Punktwert ueberhaupt etwas aussagt.
MIN_OBJEKTE_MITTEL = 3
MIN_OBJEKTE_HOCH = 6
# Relative Streuung (Spannweite / Median), ab der die Sicherheit sinkt.
MAX_STREUUNG_HOCH = 0.20
MAX_STREUUNG_MITTEL = 0.45
# Ab welchem Alter eine Referenz an Gewicht verliert.
MAX_ALTER_MONATE = 24


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
        self._leite_ab()

    def _leite_ab(self) -> None:
        """Rechnet nur, was sich EINDEUTIG ergibt -- nichts wird geschaetzt."""
        if self.preis_chf_pro_m2 is None and self.preis_chf and self.flaeche_m2:
            self.preis_chf_pro_m2 = round(self.preis_chf / self.flaeche_m2, 2)
        if (self.mietzins_chf_pro_m2_jahr is None and self.mietzins_chf_monat
                and self.flaeche_m2):
            self.mietzins_chf_pro_m2_jahr = round(
                self.mietzins_chf_monat * 12 / self.flaeche_m2, 2)
        if (self.bodenpreis_chf_pro_m2 is None and self.preis_chf
                and self.grundstuecksflaeche_m2 and self.objektart
                and "bauland" in self.objektart.lower()):
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
    kanton: Optional[str] = None
    objektart: Optional[str] = None
    baujahr_von: Optional[int] = None
    baujahr_bis: Optional[int] = None
    max_alter_monate: Optional[int] = MAX_ALTER_MONATE

    def pruefe(self, obj: Vergleichsobjekt) -> Optional[str]:
        """None wenn das Objekt passt, sonst der Ausschlussgrund."""
        def gleich(a, b):
            return (a or "").strip().lower() == (b or "").strip().lower()

        if self.gemeinde and obj.gemeinde and not gleich(self.gemeinde, obj.gemeinde):
            return f"andere Gemeinde ({obj.gemeinde})"
        if self.kanton and obj.kanton and not gleich(self.kanton, obj.kanton):
            return f"anderer Kanton ({obj.kanton})"
        if self.objektart and obj.objektart and not gleich(self.objektart, obj.objektart):
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
        """Der Median -- aber nur, wenn er ueberhaupt etwas aussagt.

        Bei Sicherheit `gering` bleibt der Vorschlag bestehen, wird aber
        ausdruecklich als schwach gestuetzt gefuehrt; bei fehlenden Daten gibt
        es keinen.
        """
        return self.median

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
            "objekte": [o.to_dict() for o in self.objekte],
            "ausgeschlossen": self.ausgeschlossen,
            "punktwert_belastbar": self.sicherheit in (SICHERHEIT_HOCH, SICHERHEIT_MITTEL),
        }

    def als_marktwert(self, benutzerannahme: Optional[float] = None):
        """Uebergibt die Referenzlage an die Wirtschaftlichkeit.

        Der Systemvorschlag wird ausdruecklich gesetzt (statt ihn dort erneut
        aus den Referenzen zu bilden), damit Sicherheitsbewertung und
        Vorschlag aus derselben Auswertung stammen.
        """
        referenzen = [r for r in (o.als_referenzwert(self.groesse) for o in self.objekte) if r]
        hinweis = f"Sicherheit {self.sicherheit}: " + " ".join(self.begruendung)
        if self.sicherheit == SICHERHEIT_GERING and self.median is not None:
            hinweis = (
                "Der Systemvorschlag ist nur schwach gestuetzt -- als Aussage taugt hier die "
                "Bandbreite, nicht der Punktwert. " + hinweis
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
    for obj in objekte:
        if obj.wert_fuer(groesse) is None:
            ausgeschlossen.append({
                "bezeichnung": obj.bezeichnung, "quelle": obj.quelle,
                "grund": f"kein Wert fuer {bezeichnung}",
            })
            continue
        grund = filter_.pruefe(obj)
        if grund:
            ausgeschlossen.append({
                "bezeichnung": obj.bezeichnung, "quelle": obj.quelle, "grund": grund,
            })
            continue
        passend.append(obj)

    werte = [w for w in (o.wert_fuer(groesse) for o in passend) if w is not None]
    sicherheit, begruendung = _sicherheit(werte, passend)
    if ausgeschlossen:
        begruendung.append(
            f"{len(ausgeschlossen)} Objekt(e) nicht einbezogen (siehe 'ausgeschlossen')."
        )
    return Marktreferenz(
        groesse=groesse, einheit=einheit, bezeichnung=bezeichnung,
        objekte=passend, ausgeschlossen=ausgeschlossen,
        sicherheit=sicherheit, begruendung=begruendung,
    )


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
        roh_qualitaet = _normalisiere_spalte(str(daten.get("datenqualitaet") or ""))
        daten["datenqualitaet"] = (
            roh_qualitaet if roh_qualitaet in _QUALITAETEN else QUALITAET_UNBEKANNT
        )
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
        try:
            objekte.append(Vergleichsobjekt(**daten))
        except (MarktdatenError, TypeError) as exc:
            fehler.append({"index": i, "grund": str(exc), "rohdaten": eintrag})
    return objekte, fehler

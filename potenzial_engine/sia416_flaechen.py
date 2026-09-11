"""
SIA-416-Flaechenkaskade (Konzept-/Vorbereitungsmodul).

SIA 416 definiert MESSGROESSEN fuer Gebaeudeflaechen, keine
Verhaeltniszahlen zwischen ihnen:

    GF (Geschossflaeche)  = NF + VF + FF + KF
    NF (Nutzflaeche)      = HNF + NNF

Die Norm schreibt an keiner Stelle vor, welcher Anteil einer gegebenen
GF auf NF, HNF oder die uebrigen Kategorien entfaellt -- das haengt vom
Gebaeudetyp, Grundriss und Erschliessungskonzept ab und ist von Fall zu
Fall verschieden. Jede hier verwendete Verhaeltniszahl (z.B. "NF macht
X% der GF aus") ist deshalb IMMER eine Modellannahme und wird als
solche mit Pflicht-Begruendung gefuehrt -- es gibt keine eingebauten
Prozentsaetze und keine stillen Defaults. Fehlt eine Modellannahme,
bleibt der davon abhaengige Wert explizit `None` mit Status
`nicht_bestimmbar`, statt geraten oder ersetzt zu werden.

GF selbst ist KEINE Modellannahme, sondern das reale Ergebnis der
G1-Geometrie-Kaskade (baubereich.py) auf Basis von Parzellengeometrie
und BZO-Kennzahlen -- sie wird hier nur als bereits berechneter
Eingabewert entgegengenommen.

Dieses Modul ist bewusst NICHT an run_full_pipeline() oder G1
angebunden (analog dazu, wie G1 selbst zunaechst eigenstaendig gebaut
wurde, bevor eine Verdrahtung erfolgte). Es steht fuer sich, ist
unabhaengig testbar und wird erst verdrahtet, wenn das Zieldatenmodell
fuer Modul 3/4 feststeht. `aus_g1_ergebnis()`/`berechne_sia416_aus_g1()`
unten zeigen den vorgesehenen Anschlusspunkt an G1, ohne ihn automatisch
aufzurufen -- der Aufrufer fuehrt G1 selbst aus und uebergibt das
Ergebnis explizit.

Die Kaskade rechnet aktuell mit EINER undifferenzierten Geschossflaeche
(implizit: vollstaendiger Neubau nach geltendem Baurecht, wie es G1
heute liefert). Eine Unterscheidung nach Entwicklungsszenario (Bestand,
Anbau, Aufstockung, Ersatzneubau, Kombination -- siehe
entwicklungsszenarien.py) ist damit noch NICHT abgebildet; das
Datenmodell verbaut sie aber auch nicht: eine spaetere Erweiterung
kaeme als zusaetzlicher, expliziter Parameter (z.B. eine
Bestandsflaeche, die vor der Kaskade abgezogen wird), nicht als
Umbau der bestehenden Funktionssignaturen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .baubereich import PotenzialErgebnis

STATUS_BESTIMMT = "bestimmt"
STATUS_MODELLANNAHME_BASIERT = "modellannahme_basiert"
STATUS_NICHT_BESTIMMBAR = "nicht_bestimmbar"


@dataclass
class Modellannahme:
    """Eine explizit vom Aufrufer gelieferte Verhaeltnis- oder
    Erfahrungszahl. `begruendung` ist Pflicht -- eine Modellannahme
    ohne Begruendung ist nicht von einem stillen Default zu
    unterscheiden und daher hier nicht zulaessig."""
    wert: float
    begruendung: str
    quelle: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.begruendung or not self.begruendung.strip():
            raise ValueError(
                "Modellannahme ohne Begruendung ist nicht zulaessig "
                "(waere nicht von einem stillen Default unterscheidbar)."
            )


@dataclass(frozen=True)
class BandbreitenWert:
    """Ein einzelner Punkt (konservativ/mittel/optimiert) innerhalb einer
    Bandbreiten-Modellannahme. Traegt eine EIGENE Begruendung statt nur
    eine gemeinsame fuer die ganze Bandbreite -- "warum ist DAS der
    konservative Fall" ist eine andere Aussage als "warum diese
    Bandbreite ueberhaupt". `gueltigkeitsbereich` grenzt ab, fuer welche
    Grundrisstypen/Bauformen der Wert gedacht ist (Uebertragbarkeit).

    Design-Vorbereitung -- wird aktuell von KEINER Berechnung konsumiert."""
    wert: float
    einheit: str
    quelle: str
    begruendung: str
    gueltigkeitsbereich: str
    gebaeudetyp: str
    entwicklungsszenario: str

    def __post_init__(self) -> None:
        if not 0.0 < self.wert < 1.0:
            raise ValueError(f"BandbreitenWert.wert muss zwischen 0 und 1 liegen, erhalten: {self.wert}")
        for feld_name in ("einheit", "quelle", "begruendung", "gueltigkeitsbereich", "gebaeudetyp", "entwicklungsszenario"):
            wert = getattr(self, feld_name)
            if not wert or not wert.strip():
                raise ValueError(f"BandbreitenWert.{feld_name} ist Pflicht und darf nicht leer sein.")


@dataclass(frozen=True)
class FlaechenverhaeltnisBandbreite:
    """Spaeteres Bandbreiten-Datenmodell fuer eine SIA-416-Modellannahme
    (z.B. NF/GF oder HNF/NF) -- ersetzt einen Einzelwert durch drei
    explizit begruendete Punkte fuer denselben Gebaeudetyp/dasselbe
    Entwicklungsszenario, konsistent mit Modul 3s bestehender
    Base/Optimistisch/Konservativ-Szenarien-Matrix.

    WICHTIG: konservativ/mittel/optimiert werden NICHT automatisch
    sortiert oder aufeinander normalisiert -- eine inkonsistente
    Eingabe (z.B. konservativ > optimiert) ist ein Fehler in der
    Modellannahme selbst und wird als solcher zurueckgewiesen, nicht
    still korrigiert. Reine Schema-Definition -- wird aktuell von KEINER
    Berechnung konsumiert (`berechne_sia416_kaskade()` nimmt weiterhin
    eine einzelne `Modellannahme` entgegen)."""
    konservativ: BandbreitenWert
    mittel: BandbreitenWert
    optimiert: BandbreitenWert

    def __post_init__(self) -> None:
        if not (self.konservativ.wert <= self.mittel.wert <= self.optimiert.wert):
            raise ValueError(
                f"Bandbreite ist nicht konsistent geordnet (konservativ={self.konservativ.wert} <= "
                f"mittel={self.mittel.wert} <= optimiert={self.optimiert.wert} erwartet) -- wird NICHT "
                "automatisch sortiert oder normalisiert, das waere eine stille Korrektur der Eingabe."
            )
        typen = {self.konservativ.gebaeudetyp, self.mittel.gebaeudetyp, self.optimiert.gebaeudetyp}
        szenarien = {self.konservativ.entwicklungsszenario, self.mittel.entwicklungsszenario, self.optimiert.entwicklungsszenario}
        if len(typen) > 1 or len(szenarien) > 1:
            raise ValueError(
                "konservativ/mittel/optimiert muessen sich auf denselben Gebaeudetyp und dasselbe "
                "Entwicklungsszenario beziehen -- sonst ist es keine Bandbreite EINER Groesse, "
                f"sondern drei unabhaengige Zahlen (Gebaeudetypen: {typen}, Szenarien: {szenarien})."
            )


# ---------------------------------------------------------------------------
# GWR-Sperrregel: Modul-1/GWR-Felder, die wie SIA-416-Flaechen AUSSEHEN,
# es aber NICHT sind -- siehe SIA-416-Methodik-Entscheidungsvorlage.
# ---------------------------------------------------------------------------

GWR_FELDER_KEINE_SIA416_FLAECHE = {
    "gwr.energiebezugsflaeche_m2": (
        "SIA-380/1-Energiebezugsflaeche (Waermebedarfsrechnung), NICHT SIA-416-NF/HNF. "
        "Definitionsunterschiede u.a. bei beheizten Nebenraeumen -- darf nicht als "
        "Ersatzwert fuer die Bestands-HNF verwendet werden."
    ),
    "gwr.grundflaeche_m2": (
        "Gebaeude-GRUNDflaeche (Fussabdruck EINES Geschosses/der Bodenflaeche laut GWR-"
        "Merkmal 'garea'), keine ueber alle Geschosse summierte Geschossflaeche (GF) und "
        "keine NF/HNF."
    ),
    "gwr.gebaeudevolumen_m3": (
        "Gebaeudevolumen (m3), keine Flaeche ueberhaupt -- eine Umrechnung in eine Flaeche "
        "braeuchte zusaetzlich eine Geschosshoehen-Annahme (eigene Modellannahme)."
    ),
    "kataster.flaeche_m2": (
        "Amtliche Parzellen-/Grundstuecksflaeche (Land), keine Gebaeudeflaeche und damit "
        "keine SIA-416-Groesse."
    ),
}


def pruefe_keine_sia416_verwechslung(feldname: str) -> Optional[str]:
    """Liefert die Warnung zu `feldname`, falls dieses Feld bekanntermassen
    KEINE SIA-416-Flaeche ist (siehe GWR_FELDER_KEINE_SIA416_FLAECHE),
    sonst `None`. Reiner Nachschlage-Helfer, keine Validierung von
    Berechnungsergebnissen.

    Verwandte, aber bewusst NICHT in dieser Tabelle gefuehrte Falle: G1s
    `fussabdruck_m2` (baubereich.PotenzialErgebnis) heisst umgangssprachlich
    aehnlich wie GWR `grundflaeche_m2`, meint aber etwas anderes --
    baurechtlich ZULAESSIGER Fussabdruck (Potenzial) vs. tatsaechlich
    GEBAUTE Grundflaeche (Bestand). Kein GWR-Feld, deshalb nicht Teil
    dieser Sperrliste, aber dieselbe Verwechslungsgefahr."""
    return GWR_FELDER_KEINE_SIA416_FLAECHE.get(feldname)


@dataclass
class SIA416Wert:
    feld: str
    wert: Optional[float]
    einheit: str = "m2"
    status: str = STATUS_BESTIMMT
    herkunft: Optional[str] = None
    unklarheit: Optional[str] = None


@dataclass
class SIA416Ergebnis:
    geschossflaeche_gf: SIA416Wert
    nutzflaeche_nf: SIA416Wert
    hauptnutzflaeche_hnf: SIA416Wert
    nebennutzflaeche_nnf: SIA416Wert
    uebrige_flaechen_vf_ff_kf: SIA416Wert

    def als_liste(self) -> List[SIA416Wert]:
        return [
            self.geschossflaeche_gf,
            self.nutzflaeche_nf,
            self.hauptnutzflaeche_hnf,
            self.nebennutzflaeche_nnf,
            self.uebrige_flaechen_vf_ff_kf,
        ]


def berechne_sia416_kaskade(
    geschossflaeche_gf_m2: float,
    nf_anteil_an_gf: Optional[Modellannahme] = None,
    hnf_anteil_an_nf: Optional[Modellannahme] = None,
) -> SIA416Ergebnis:
    """Leitet NF/HNF/NNF aus einer gegebenen GF ab -- ausschliesslich
    ueber explizit mitgegebene Modellannahmen. Ohne `nf_anteil_an_gf`
    bleiben NF, HNF, NNF und die Restkategorie `nicht_bestimmbar`.
    Ohne `hnf_anteil_an_nf` bleiben HNF/NNF `nicht_bestimmbar`, auch
    wenn NF bereits bestimmt ist.
    """
    gf = SIA416Wert(
        feld="geschossflaeche_gf", wert=geschossflaeche_gf_m2,
        status=STATUS_BESTIMMT, herkunft="G1-Geometrie-Kaskade (reale Berechnung, keine Annahme)",
    )

    if nf_anteil_an_gf is None:
        nf = SIA416Wert(
            feld="nutzflaeche_nf", wert=None, status=STATUS_NICHT_BESTIMMBAR,
            unklarheit="Kein NF/GF-Verhaeltnis angegeben -- SIA 416 schreibt keinen "
                       "Anteil vor, dieser haengt vom Grundriss ab.",
        )
        rest = SIA416Wert(
            feld="uebrige_flaechen_vf_ff_kf", wert=None, status=STATUS_NICHT_BESTIMMBAR,
            unklarheit="Ergibt sich erst aus GF - NF, NF ist nicht bestimmt.",
        )
    else:
        if not 0.0 < nf_anteil_an_gf.wert < 1.0:
            raise ValueError(
                f"nf_anteil_an_gf.wert muss zwischen 0 und 1 liegen, erhalten: {nf_anteil_an_gf.wert}"
            )
        nf_wert = geschossflaeche_gf_m2 * nf_anteil_an_gf.wert
        nf = SIA416Wert(
            feld="nutzflaeche_nf", wert=round(nf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft=f"Modellannahme NF/GF={nf_anteil_an_gf.wert:.2f}: {nf_anteil_an_gf.begruendung}"
                     + (f" (Quelle: {nf_anteil_an_gf.quelle})" if nf_anteil_an_gf.quelle else ""),
        )
        rest = SIA416Wert(
            feld="uebrige_flaechen_vf_ff_kf", wert=round(geschossflaeche_gf_m2 - nf_wert, 1),
            status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="GF - NF (VF/FF/KF werden hier nicht einzeln aufgeschluesselt -- "
                     "dafuer waere ein Grundriss noetig, keine weitere Annahme).",
        )

    if hnf_anteil_an_nf is None or nf.wert is None:
        grund = ("Kein HNF/NF-Verhaeltnis angegeben." if hnf_anteil_an_nf is None
                 else "NF selbst ist nicht bestimmt.")
        hnf = SIA416Wert(feld="hauptnutzflaeche_hnf", wert=None, status=STATUS_NICHT_BESTIMMBAR, unklarheit=grund)
        nnf = SIA416Wert(feld="nebennutzflaeche_nnf", wert=None, status=STATUS_NICHT_BESTIMMBAR, unklarheit=grund)
    else:
        if not 0.0 < hnf_anteil_an_nf.wert < 1.0:
            raise ValueError(
                f"hnf_anteil_an_nf.wert muss zwischen 0 und 1 liegen, erhalten: {hnf_anteil_an_nf.wert}"
            )
        hnf_wert = nf.wert * hnf_anteil_an_nf.wert
        hnf = SIA416Wert(
            feld="hauptnutzflaeche_hnf", wert=round(hnf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft=f"Modellannahme HNF/NF={hnf_anteil_an_nf.wert:.2f}: {hnf_anteil_an_nf.begruendung}"
                     + (f" (Quelle: {hnf_anteil_an_nf.quelle})" if hnf_anteil_an_nf.quelle else ""),
        )
        nnf = SIA416Wert(
            feld="nebennutzflaeche_nnf", wert=round(nf.wert - hnf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="NF - HNF",
        )

    return SIA416Ergebnis(
        geschossflaeche_gf=gf, nutzflaeche_nf=nf,
        hauptnutzflaeche_hnf=hnf, nebennutzflaeche_nnf=nnf,
        uebrige_flaechen_vf_ff_kf=rest,
    )


@dataclass
class WohnungstypAnteil:
    typ: str
    anteil: float
    flaeche_hnf_pro_einheit_m2: float


@dataclass
class Wohnungsmix:
    """Wohnungsmix ist NIE ein stiller Default -- ohne diese Struktur
    (oder wenn ihre Anteile nicht 1.0 ergeben) wird keine
    Wohnungsanzahl berechnet, sondern `nicht_bestimmbar` gemeldet."""
    typen: List[WohnungstypAnteil]
    begruendung: str

    def __post_init__(self) -> None:
        if not self.begruendung or not self.begruendung.strip():
            raise ValueError("Wohnungsmix ohne Begruendung ist nicht zulaessig.")
        summe = sum(t.anteil for t in self.typen)
        if abs(summe - 1.0) > 1e-6:
            raise ValueError(
                f"Wohnungsmix-Anteile ergeben {summe:.4f}, nicht 1.0 -- "
                "wird nicht automatisch normalisiert, da das den Mix stillschweigend veraendern wuerde."
            )


@dataclass
class WohnungstypErgebnis:
    typ: str
    hnf_zugewiesen_m2: float
    anzahl_ganze_einheiten: int
    rest_hnf_m2: float


@dataclass
class WohnungsmixErgebnis:
    typen: List[WohnungstypErgebnis]
    gesamtanzahl_ganze_einheiten: int
    gesamt_rest_hnf_m2: float
    unklarheit: str


def berechne_wohnungsanzahl(
    hnf_wohnen_m2: Optional[float],
    wohnungsmix: Optional[Wohnungsmix],
) -> Optional[WohnungsmixErgebnis]:
    """Verteilt eine gegebene Wohn-HNF auf den Wohnungsmix. Liefert
    `None`, wenn HNF oder Mix fehlen -- es wird kein impliziter
    Durchschnittswert (z.B. "100 m2 pro Wohnung") angenommen. Der Rest
    pro Typ (unvollstaendige Einheit) wird transparent ausgewiesen statt
    gerundet."""
    if hnf_wohnen_m2 is None or wohnungsmix is None:
        return None

    ergebnisse: List[WohnungstypErgebnis] = []
    gesamt_ganze = 0
    gesamt_rest = 0.0
    for t in wohnungsmix.typen:
        hnf_fuer_typ = hnf_wohnen_m2 * t.anteil
        anzahl = int(hnf_fuer_typ // t.flaeche_hnf_pro_einheit_m2)
        rest = round(hnf_fuer_typ - anzahl * t.flaeche_hnf_pro_einheit_m2, 1)
        ergebnisse.append(WohnungstypErgebnis(
            typ=t.typ, hnf_zugewiesen_m2=round(hnf_fuer_typ, 1),
            anzahl_ganze_einheiten=anzahl, rest_hnf_m2=rest,
        ))
        gesamt_ganze += anzahl
        gesamt_rest += rest

    return WohnungsmixErgebnis(
        typen=ergebnisse,
        gesamtanzahl_ganze_einheiten=gesamt_ganze,
        gesamt_rest_hnf_m2=round(gesamt_rest, 1),
        unklarheit=(
            f"Wohnungsmix-Annahme: {wohnungsmix.begruendung}. "
            "Restflaechen pro Typ sind unvollstaendige Einheiten (z.B. durch Grundrissoptimierung "
            "gewinnbar oder als gemeinsame Nebennutzflaeche zu verwenden) -- bewusst nicht aufgerundet."
        ),
    )


def aus_g1_ergebnis(g1_ergebnis: "PotenzialErgebnis") -> SIA416Wert:
    """Liest die reale, geometrisch berechnete Geschossflaeche aus einem
    G1-Ergebnis (baubereich.berechne_potenzial()) als GF-Anker fuer die
    SIA-416-Kaskade. Reiner Adapter -- ruft G1 nicht selbst auf, der
    Aufrufer fuehrt G1 aus und uebergibt das fertige Ergebnis."""
    if g1_ergebnis.geschossflaeche_m2 is None:
        return SIA416Wert(
            feld="geschossflaeche_gf", wert=None, status=STATUS_NICHT_BESTIMMBAR,
            unklarheit=(
                "G1 konnte keine Geschossflaeche bestimmen (kein bindender Kandidat) -- "
                f"Kandidaten: {g1_ergebnis.geschossflaeche_kandidaten or {}}"
            ),
        )
    return SIA416Wert(
        feld="geschossflaeche_gf", wert=g1_ergebnis.geschossflaeche_m2, status=STATUS_BESTIMMT,
        herkunft=f"G1-Geometrie-Kaskade, limitiert durch: {g1_ergebnis.geschossflaeche_limitiert_durch}",
    )


def berechne_sia416_aus_g1(
    g1_ergebnis: "PotenzialErgebnis",
    nf_anteil_an_gf: Optional[Modellannahme] = None,
    hnf_anteil_an_nf: Optional[Modellannahme] = None,
) -> Optional[SIA416Ergebnis]:
    """Verbindet G1-Ergebnis und SIA-416-Kaskade in einem Aufruf.

    Liefert `None`, wenn G1 selbst keine Geschossflaeche bestimmen
    konnte -- dann gibt es keine sinnvolle GF-Basis fuer die Kaskade;
    der Aufrufer muss diesen Fall selbst als "G1 nicht bestimmbar"
    behandeln (Grund steht in `g1_ergebnis.geschossflaeche_limitiert_durch`
    bzw. `g1_ergebnis.geschossflaeche_kandidaten`). Modellannahmen fuer
    NF/HNF bleiben wie in `berechne_sia416_kaskade()` vollstaendig
    optional und werden nicht ersetzt."""
    if g1_ergebnis.geschossflaeche_m2 is None:
        return None
    ergebnis = berechne_sia416_kaskade(
        geschossflaeche_gf_m2=g1_ergebnis.geschossflaeche_m2,
        nf_anteil_an_gf=nf_anteil_an_gf, hnf_anteil_an_nf=hnf_anteil_an_nf,
    )
    ergebnis.geschossflaeche_gf.herkunft = (
        f"G1-Geometrie-Kaskade, limitiert durch: {g1_ergebnis.geschossflaeche_limitiert_durch}"
    )
    return ergebnis

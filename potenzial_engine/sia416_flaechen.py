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
    """Die Kaskade nach SIA 416.

    Norm-Gliederung (Definitionen, keine Verhaeltniszahlen):
        GF  = NGF + KF
        NGF = NF + VF + FF
        NF  = HNF + NNF

    Zwei Wege fuehren zur NF, und sie schliessen sich gegenseitig aus:
      * DETAILLIERT ueber die Norm-Gliederung (kf_anteil_an_gf und
        vf_ff_anteil_an_ngf) -- dann ist auch NGF bestimmt.
      * PAUSCHAL ueber ein einziges NF/GF-Verhaeltnis (nf_anteil_an_gf) --
        dann bleibt NGF `nicht_bestimmbar`, denn aus einem NF/GF-Verhaeltnis
        allein laesst sich die Trennlinie zwischen KF und VF/FF nicht
        rekonstruieren.
    Beide Wege gleichzeitig anzugeben ist ein Widerspruch und wird
    zurueckgewiesen, nicht stillschweigend aufgeloest.
    """
    geschossflaeche_gf: SIA416Wert
    nutzflaeche_nf: SIA416Wert
    hauptnutzflaeche_hnf: SIA416Wert
    nebennutzflaeche_nnf: SIA416Wert
    uebrige_flaechen_vf_ff_kf: SIA416Wert
    nettogeschossflaeche_ngf: Optional[SIA416Wert] = None
    konstruktionsflaeche_kf: Optional[SIA416Wert] = None
    verkehrs_und_funktionsflaeche_vf_ff: Optional[SIA416Wert] = None

    def als_liste(self) -> List[SIA416Wert]:
        werte = [
            self.geschossflaeche_gf,
            self.konstruktionsflaeche_kf,
            self.nettogeschossflaeche_ngf,
            self.verkehrs_und_funktionsflaeche_vf_ff,
            self.nutzflaeche_nf,
            self.hauptnutzflaeche_hnf,
            self.nebennutzflaeche_nnf,
            self.uebrige_flaechen_vf_ff_kf,
        ]
        return [w for w in werte if w is not None]


def _anteil_pruefen(name: str, annahme: Modellannahme) -> float:
    if not 0.0 < annahme.wert < 1.0:
        raise ValueError(f"{name}.wert muss zwischen 0 und 1 liegen, erhalten: {annahme.wert}")
    return annahme.wert


def _herkunftstext(name: str, annahme: Modellannahme) -> str:
    text = f"Modellannahme {name}={annahme.wert:.2f}: {annahme.begruendung}"
    return text + (f" (Quelle: {annahme.quelle})" if annahme.quelle else "")


def _detaillierte_ngf_stufe(
    gf_m2: float,
    kf_anteil_an_gf: Modellannahme,
    vf_ff_anteil_an_ngf: Modellannahme,
) -> tuple[SIA416Wert, SIA416Wert, SIA416Wert, float]:
    """GF -> KF -> NGF -> VF/FF -> NF entlang der Norm-Gliederung."""
    kf_anteil = _anteil_pruefen("kf_anteil_an_gf", kf_anteil_an_gf)
    vf_ff_anteil = _anteil_pruefen("vf_ff_anteil_an_ngf", vf_ff_anteil_an_ngf)

    kf_wert = gf_m2 * kf_anteil
    ngf_wert = gf_m2 - kf_wert
    vf_ff_wert = ngf_wert * vf_ff_anteil
    nf_wert = ngf_wert - vf_ff_wert

    kf = SIA416Wert(
        feld="konstruktionsflaeche_kf", wert=round(kf_wert, 1),
        status=STATUS_MODELLANNAHME_BASIERT,
        herkunft=_herkunftstext("KF/GF", kf_anteil_an_gf),
    )
    ngf = SIA416Wert(
        feld="nettogeschossflaeche_ngf", wert=round(ngf_wert, 1),
        status=STATUS_MODELLANNAHME_BASIERT, herkunft="GF - KF (SIA 416: GF = NGF + KF)",
    )
    vf_ff = SIA416Wert(
        feld="verkehrs_und_funktionsflaeche_vf_ff", wert=round(vf_ff_wert, 1),
        status=STATUS_MODELLANNAHME_BASIERT,
        herkunft=_herkunftstext("(VF+FF)/NGF", vf_ff_anteil_an_ngf),
    )
    return kf, ngf, vf_ff, nf_wert


def berechne_sia416_kaskade(
    geschossflaeche_gf_m2: float,
    nf_anteil_an_gf: Optional[Modellannahme] = None,
    hnf_anteil_an_nf: Optional[Modellannahme] = None,
    kf_anteil_an_gf: Optional[Modellannahme] = None,
    vf_ff_anteil_an_ngf: Optional[Modellannahme] = None,
) -> SIA416Ergebnis:
    """Leitet NGF/NF/HNF/NNF aus einer gegebenen GF ab -- ausschliesslich
    ueber explizit mitgegebene Modellannahmen, nie ueber eingebaute
    Prozentsaetze.

    Zwei sich ausschliessende Wege zur NF (siehe SIA416Ergebnis):
      * detailliert: `kf_anteil_an_gf` UND `vf_ff_anteil_an_ngf` -- dann ist
        auch NGF bestimmt.
      * pauschal: `nf_anteil_an_gf` -- dann bleibt NGF `nicht_bestimmbar`.
    Beides gleichzeitig ist ein Widerspruch und wird abgelehnt. Wird vom
    detaillierten Weg nur eine Haelfte geliefert, fehlt der Kaskade ein
    Glied -- auch das ist ein Fehler, kein Anlass fuer eine Ersatzannahme.

    Ohne jede dieser Angaben bleiben NF, HNF, NNF und die Restkategorie
    `nicht_bestimmbar`. Ohne `hnf_anteil_an_nf` bleiben HNF/NNF
    `nicht_bestimmbar`, auch wenn NF bereits bestimmt ist.
    """
    detailliert_teilweise = (kf_anteil_an_gf is None) != (vf_ff_anteil_an_ngf is None)
    if detailliert_teilweise:
        raise ValueError(
            "Der detaillierte Weg braucht BEIDE Annahmen (kf_anteil_an_gf und "
            "vf_ff_anteil_an_ngf) -- mit nur einer davon liesse sich die NF nur ueber "
            "einen erfundenen Ersatzwert fuer die andere bestimmen."
        )
    detailliert = kf_anteil_an_gf is not None and vf_ff_anteil_an_ngf is not None
    if detailliert and nf_anteil_an_gf is not None:
        raise ValueError(
            "nf_anteil_an_gf (pauschal) und kf/vf_ff (detailliert) gleichzeitig angegeben -- "
            "das sind zwei widersprechende Herleitungen derselben NF. Es wird keine davon "
            "stillschweigend bevorzugt."
        )

    gf = SIA416Wert(
        feld="geschossflaeche_gf", wert=geschossflaeche_gf_m2,
        status=STATUS_BESTIMMT, herkunft="G1-Geometrie-Kaskade (reale Berechnung, keine Annahme)",
    )

    kf_wert_obj = ngf_wert_obj = vf_ff_wert_obj = None

    if detailliert:
        kf_wert_obj, ngf_wert_obj, vf_ff_wert_obj, nf_roh = _detaillierte_ngf_stufe(
            geschossflaeche_gf_m2, kf_anteil_an_gf, vf_ff_anteil_an_ngf
        )
        nf = SIA416Wert(
            feld="nutzflaeche_nf", wert=round(nf_roh, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="NGF - (VF+FF) (SIA 416: NGF = NF + VF + FF)",
        )
        rest = SIA416Wert(
            feld="uebrige_flaechen_vf_ff_kf", wert=round(geschossflaeche_gf_m2 - nf_roh, 1),
            status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="GF - NF, aufgeschluesselt in KF und VF+FF (siehe dort)",
        )
    elif nf_anteil_an_gf is None:
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
        nf_anteil = _anteil_pruefen("nf_anteil_an_gf", nf_anteil_an_gf)
        nf_wert = geschossflaeche_gf_m2 * nf_anteil
        nf = SIA416Wert(
            feld="nutzflaeche_nf", wert=round(nf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft=_herkunftstext("NF/GF", nf_anteil_an_gf),
        )
        rest = SIA416Wert(
            feld="uebrige_flaechen_vf_ff_kf", wert=round(geschossflaeche_gf_m2 - nf_wert, 1),
            status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="GF - NF (VF/FF/KF werden hier nicht einzeln aufgeschluesselt -- "
                     "dafuer waere ein Grundriss noetig, keine weitere Annahme).",
        )
        ngf_wert_obj = SIA416Wert(
            feld="nettogeschossflaeche_ngf", wert=None, status=STATUS_NICHT_BESTIMMBAR,
            unklarheit="Aus einem pauschalen NF/GF-Verhaeltnis laesst sich die Trennlinie "
                       "zwischen KF und VF/FF nicht rekonstruieren -- dafuer braucht es "
                       "kf_anteil_an_gf und vf_ff_anteil_an_ngf.",
        )

    if hnf_anteil_an_nf is None or nf.wert is None:
        grund = ("Kein HNF/NF-Verhaeltnis angegeben." if hnf_anteil_an_nf is None
                 else "NF selbst ist nicht bestimmt.")
        hnf = SIA416Wert(feld="hauptnutzflaeche_hnf", wert=None, status=STATUS_NICHT_BESTIMMBAR, unklarheit=grund)
        nnf = SIA416Wert(feld="nebennutzflaeche_nnf", wert=None, status=STATUS_NICHT_BESTIMMBAR, unklarheit=grund)
    else:
        hnf_anteil = _anteil_pruefen("hnf_anteil_an_nf", hnf_anteil_an_nf)
        hnf_wert = nf.wert * hnf_anteil
        hnf = SIA416Wert(
            feld="hauptnutzflaeche_hnf", wert=round(hnf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft=_herkunftstext("HNF/NF", hnf_anteil_an_nf),
        )
        nnf = SIA416Wert(
            feld="nebennutzflaeche_nnf", wert=round(nf.wert - hnf_wert, 1), status=STATUS_MODELLANNAHME_BASIERT,
            herkunft="NF - HNF",
        )

    return SIA416Ergebnis(
        geschossflaeche_gf=gf, nutzflaeche_nf=nf,
        hauptnutzflaeche_hnf=hnf, nebennutzflaeche_nnf=nnf,
        uebrige_flaechen_vf_ff_kf=rest,
        nettogeschossflaeche_ngf=ngf_wert_obj,
        konstruktionsflaeche_kf=kf_wert_obj,
        verkehrs_und_funktionsflaeche_vf_ff=vf_ff_wert_obj,
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
    """Ergebnis je Wohnungstyp.

    `hnf_sollanteil_m2` ist die Flaeche, die dem Typ nach seinem Mix-Anteil
    rechnerisch zustuende; `belegte_hnf_m2` die Flaeche der tatsaechlich
    gebildeten ganzen Wohnungen. Die Differenz kann in beide Richtungen
    gehen -- ganze Wohnungen lassen sich nun einmal nicht anteilsgenau
    verteilen. Sie wird deshalb als ABWEICHUNG gefuehrt und nicht als
    "Rest", der faelschlich immer positiv aussehen wuerde."""
    typ: str
    hnf_sollanteil_m2: float
    anzahl_ganze_einheiten: int
    belegte_hnf_m2: float
    abweichung_vom_sollanteil_m2: float
    soll_einheiten: float = 0.0


@dataclass
class WohnungsmixErgebnis:
    typen: List[WohnungstypErgebnis]
    gesamtanzahl_ganze_einheiten: int
    gesamt_rest_hnf_m2: float
    unklarheit: str
    durchschnittsflaeche_pro_einheit_m2: Optional[float] = None
    belegte_hnf_m2: Optional[float] = None


def berechne_wohnungsanzahl(
    hnf_wohnen_m2: Optional[float],
    wohnungsmix: Optional[Wohnungsmix],
) -> Optional[WohnungsmixErgebnis]:
    """Verteilt eine gegebene Wohn-HNF auf den Wohnungsmix.

    Verfahren: groesster Rest (Hare-Niemeyer) auf der ANZAHL Wohnungen,
    nicht Abrunden je Typ auf der Flaeche.

    Der Unterschied ist nicht kosmetisch. Rundet man je Typ die zugeteilte
    Flaeche ab, verliert jeder Typ bis zu eine fast vollstaendige Wohnung --
    bei einem kleinen Gebaeude kommt so ueberall 0 heraus, waehrend die
    gesamte Flaeche als "Rest" ausgewiesen wird. Das ist rechnerisch nicht
    falsch, aber als Aussage unbrauchbar. Stattdessen wird zuerst die
    Gesamtzahl aus der mittleren Wohnungsgroesse des Mixes bestimmt und
    diese Zahl dann so auf die Typen verteilt, dass die Anteile so genau
    wie moeglich getroffen werden.

    Liefert `None`, wenn HNF oder Mix fehlen -- es wird kein impliziter
    Durchschnittswert (z.B. "100 m2 pro Wohnung") angenommen. Die nicht
    belegte Restflaeche wird transparent ausgewiesen statt aufgerundet.
    """
    if hnf_wohnen_m2 is None or wohnungsmix is None:
        return None

    mittlere_groesse = sum(t.anteil * t.flaeche_hnf_pro_einheit_m2 for t in wohnungsmix.typen)
    if mittlere_groesse <= 0:
        return None

    gesamtzahl = int(hnf_wohnen_m2 // mittlere_groesse)

    soll = [gesamtzahl * t.anteil for t in wohnungsmix.typen]
    anzahl = [int(w) for w in soll]
    reste = [(soll[i] - anzahl[i], wohnungsmix.typen[i].anteil, -i) for i in range(len(soll))]
    for _ in range(gesamtzahl - sum(anzahl)):
        # Groesster Rest gewinnt; bei Gleichstand der groessere Mix-Anteil,
        # zuletzt die Reihenfolge der Eingabe -- deterministisch, nicht zufaellig.
        i = max(range(len(reste)), key=lambda k: reste[k])
        anzahl[i] += 1
        reste[i] = (-1.0, reste[i][1], reste[i][2])

    # Die mittlere Groesse ist ein Durchschnitt: verschiebt der groesste Rest
    # die Verteilung zu den grossen Typen, kann die belegte Flaeche die
    # vorhandene knapp uebersteigen. Dann wird die groesste Wohnung entfernt
    # und -- wenn moeglich -- durch eine kleinere ersetzt, statt die
    # Wohnungszahl zu senken.
    #
    # Warum das zaehlt: 197 m2 Wohnflaeche bei einem Mix 20/50/30
    # (62/88/112 m2) ergaben beim blossen Entfernen EINE Wohnung mit 109 m2
    # Rest, obwohl zwei hineinpassen (62 + 88 = 150 m2). Eine Wohnung
    # wegzulassen, wo zwei Platz haben, ist kein konservatives Ergebnis,
    # sondern ein falsches.
    flaechen = [t.flaeche_hnf_pro_einheit_m2 for t in wohnungsmix.typen]

    def belegt() -> float:
        return sum(anzahl[i] * flaechen[i] for i in range(len(anzahl)))

    # Jeder Durchgang verkleinert die belegte Flaeche echt (entfernt eine
    # Wohnung, setzt hoechstens eine strikt kleinere ein) -- die Schleife
    # endet also immer.
    while belegt() > hnf_wohnen_m2 and sum(anzahl) > 0:
        belegte_typen = [i for i in range(len(anzahl)) if anzahl[i] > 0]
        i = max(belegte_typen, key=lambda k: flaechen[k])
        anzahl[i] -= 1
        ersatz = [
            k for k in range(len(anzahl))
            if flaechen[k] < flaechen[i] and belegt() + flaechen[k] <= hnf_wohnen_m2
        ]
        if ersatz:
            # Unter den passenden kleineren Typen derjenige, der gegenueber
            # seinem Soll-Anteil am staerksten unterbelegt ist.
            j = max(ersatz, key=lambda k: soll[k] - anzahl[k])
            anzahl[j] += 1

    ergebnisse: List[WohnungstypErgebnis] = []
    for i, t in enumerate(wohnungsmix.typen):
        belegte_flaeche = anzahl[i] * t.flaeche_hnf_pro_einheit_m2
        sollanteil = hnf_wohnen_m2 * t.anteil
        ergebnisse.append(WohnungstypErgebnis(
            typ=t.typ,
            hnf_sollanteil_m2=round(sollanteil, 1),
            anzahl_ganze_einheiten=anzahl[i],
            belegte_hnf_m2=round(belegte_flaeche, 1),
            abweichung_vom_sollanteil_m2=round(belegte_flaeche - sollanteil, 1),
            soll_einheiten=round(soll[i], 2),
        ))

    belegte_gesamt = round(belegt(), 1)
    return WohnungsmixErgebnis(
        typen=ergebnisse,
        gesamtanzahl_ganze_einheiten=sum(anzahl),
        gesamt_rest_hnf_m2=round(hnf_wohnen_m2 - belegte_gesamt, 1),
        durchschnittsflaeche_pro_einheit_m2=round(mittlere_groesse, 1),
        belegte_hnf_m2=belegte_gesamt,
        unklarheit=(
            f"Wohnungsmix-Annahme: {wohnungsmix.begruendung}. Gesamtzahl aus mittlerer "
            f"Wohnungsgroesse {mittlere_groesse:.1f} m2, verteilt nach groesstem Rest. "
            "Die nicht belegte Restflaeche ist bewusst nicht aufgerundet -- sie ist durch "
            "Grundrissoptimierung gewinnbar oder als gemeinsame Nebennutzflaeche zu fuehren."
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

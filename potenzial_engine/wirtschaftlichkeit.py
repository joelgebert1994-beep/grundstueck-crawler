"""
Stufe 5 -- Markt, BKP und Wirtschaftlichkeit je Szenario.

Setzt auf dem auf, was die Stufen 1-4 bereits liefern:

    szenarien.py       je Szenario Geschossflaeche, Wohnungen, Machbarkeit
    flaechenmodell.py  GF -> NGF -> NF -> HNF -> NWF mit Herkunft je Wert

und ergaenzt die wirtschaftliche Ebene: Verkauf, Miete, Bodenpreis, BKP,
Gewinn, Marge, Rendite und den residualen Landwert.

Verhaeltnis zu modul3_financial.py
----------------------------------
Modul 3 rechnet seit 2026 Residualwerte -- aber auf der alten Grundlage:
BGF = AZ x Parzellenflaeche (ohne Geometrie), NNF = 81 % der BGF (ein fester
Umrechnungsfaktor), ein einziges Szenario, keine Trennung von Referenz und
Benutzerannahme. Die Stufen 1-4 haben diese Grundlage ersetzt: die
Geschossflaeche kommt aus G1s Geometriekaskade, die Nutzflaechen aus der
SIA-416-Gliederung mit einzeln begruendeten Annahmen.

Dieses Modul ersetzt deshalb Modul 3s FLAECHENHERLEITUNG, uebernimmt aber
dessen KOSTENRICHTWERTE unveraendert (Import unten) -- es gibt weiterhin nur
EINEN Satz Richtwerte im Projekt, nicht zwei. Modul 3 bleibt fuer die
bestehende Schnittstelle `berechne_wirtschaftlichkeit()` in Betrieb.

Drei Herkunftsebenen, die nie vermischt werden
----------------------------------------------
    referenz        Vergleichsobjekte und Marktdaten mit Quelle und Datum
    systemannahme   daraus abgeleitete Orientierung (Median der Referenzen)
    benutzerannahme vom Benutzer gesetzt -- MASSGEBEND fuer die Rechnung

Eine Referenz ersetzt nie die Benutzerannahme. Fehlt beides, bleibt der Wert
`nicht_bestimmbar` und die davon abhaengigen Groessen werden nicht gerechnet.

Netzwerkfrei. Eine Aenderung an Markt, Wohnungsmix oder BKP loest keine neue
Baurechts- oder Geodatenabfrage aus -- genau dafuer ist diese Schicht getrennt.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .flaechenmodell import (
    HERKUNFT_BENUTZERANNAHME,
    HERKUNFT_NICHT_BESTIMMBAR,
    HERKUNFT_REFERENZ,
    HERKUNFT_SYSTEMANNAHME,
)
from .modul3_financial import (
    AUSBAUSTANDARD_CHF_PRO_M2_BGF,
    BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT,
    BKP1_AUSHUB_CHF_PRO_M3_DEFAULT,
    BKP1_AUSHUB_TIEFE_M_DEFAULT,
    BKP4_PROZENT_VON_BKP2_DEFAULT,
    BKP5_PROZENT_DEFAULT,
    BKP9_PROZENT_BY_GENAUIGKEIT,
    MARGE_PROZENT_VOM_GDV_DEFAULT,
)


class WirtschaftlichkeitError(Exception):
    """Widerspruechliche oder fehlende Eingaben in der Wirtschaftlichkeit."""


# Flaechen, auf die sich ein Preis oder eine Kostenposition beziehen kann.
# Der Schluessel ist der Feldname aus flaechenmodell.berechne_flaechen_und_wohnungen.
# "belegt" ist keine Flaeche aus der SIA-Kaskade, sondern die Summe der
# tatsaechlich gebildeten Wohnungen -- siehe _flaeche_aus().
FLAECHENBASIS = {
    "nwf": ("wohnflaeche_nwf", "Wohnfläche NWF"),
    "belegt": (None, "belegte Wohnfläche (Summe der Wohnungen)"),
    "hnf": ("hauptnutzflaeche_hnf", "Hauptnutzfläche HNF"),
    "nf": ("nutzflaeche_nf", "Nutzfläche NF"),
    "ngf": ("nettogeschossflaeche_ngf", "Nettogeschossfläche NGF"),
    "gf": ("geschossflaeche_gf", "Geschossfläche GF"),
}


# ---------------------------------------------------------------------------
# Marktwerte: Referenz / Systemvorschlag / Benutzerannahme
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Referenzwert:
    """Ein Vergleichsobjekt. Quelle und Datum sind Pflicht -- eine Referenz
    ohne Herkunft ist keine Referenz, sondern eine Behauptung."""
    quelle: str
    datum: str
    objekt: str
    wert: float
    einheit: str
    qualitaet: str = "unbekannt"

    def __post_init__(self) -> None:
        for feld in ("quelle", "datum", "objekt", "einheit"):
            if not str(getattr(self, feld) or "").strip():
                raise WirtschaftlichkeitError(
                    f"Referenzwert ohne '{feld}' ist nicht zulaessig -- ohne Herkunft ist "
                    "eine Referenz nicht von einer Behauptung zu unterscheiden."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Marktwert:
    """Eine Marktgroesse mit allen drei Ebenen gleichzeitig sichtbar.

    Der Systemvorschlag wird aus den Referenzen abgeleitet (Median -- gegen
    Ausreisser robuster als der Mittelwert), sofern nicht ausdruecklich
    gesetzt. Er ist eine ORIENTIERUNG, kein Rechenwert, sobald der Benutzer
    eine eigene Annahme gesetzt hat.
    """
    schluessel: str
    einheit: str
    referenzen: list[Referenzwert] = field(default_factory=list)
    systemvorschlag: Optional[float] = None
    benutzerannahme: Optional[float] = None
    begruendung: str = ""

    def __post_init__(self) -> None:
        if self.systemvorschlag is None and self.referenzen:
            self.systemvorschlag = round(statistics.median(r.wert for r in self.referenzen), 2)

    @property
    def wert(self) -> Optional[float]:
        """Der Wert, mit dem tatsaechlich gerechnet wird."""
        return self.benutzerannahme if self.benutzerannahme is not None else self.systemvorschlag

    @property
    def herkunft(self) -> str:
        if self.benutzerannahme is not None:
            return HERKUNFT_BENUTZERANNAHME
        if self.systemvorschlag is not None:
            return HERKUNFT_SYSTEMANNAHME if self.referenzen else HERKUNFT_SYSTEMANNAHME
        return HERKUNFT_NICHT_BESTIMMBAR

    @property
    def spanne(self) -> Optional[tuple[float, float]]:
        if not self.referenzen:
            return None
        werte = [r.wert for r in self.referenzen]
        return (min(werte), max(werte))

    def mit_benutzerwert(self, wert: float) -> "Marktwert":
        return Marktwert(
            schluessel=self.schluessel, einheit=self.einheit, referenzen=list(self.referenzen),
            systemvorschlag=self.systemvorschlag, benutzerannahme=wert,
            begruendung=self.begruendung,
        )

    def to_dict(self) -> dict[str, Any]:
        spanne = self.spanne
        return {
            "schluessel": self.schluessel,
            "einheit": self.einheit,
            "wert": self.wert,
            "herkunft": self.herkunft,
            "systemvorschlag": self.systemvorschlag,
            "benutzerannahme": self.benutzerannahme,
            "referenzspanne": list(spanne) if spanne else None,
            "referenzen": [r.to_dict() for r in self.referenzen],
            "anzahl_referenzen": len(self.referenzen),
            "begruendung": self.begruendung or (
                f"{len(self.referenzen)} Vergleichsobjekt(e), Median als Systemvorschlag."
                if self.referenzen else "Ohne Referenzen -- reine Annahme."
            ),
        }


def marktwert(schluessel: str, einheit: str, **kw) -> Marktwert:
    """Bequemer Konstruktor."""
    return Marktwert(schluessel=schluessel, einheit=einheit, **kw)


# ---------------------------------------------------------------------------
# Verkauf und Miete
# ---------------------------------------------------------------------------

VERKAUF_PRO_M2 = "chf_pro_m2"
VERKAUF_PRO_TYP = "pro_wohnungstyp"
VERKAUF_PRO_WOHNUNG = "pro_wohnung"


def _flaeche_aus(
    flaechen: Optional[dict[str, Any]], basis: str,
    wohnungen: Optional[dict[str, Any]] = None,
) -> tuple[Optional[float], str]:
    if basis not in FLAECHENBASIS:
        raise WirtschaftlichkeitError(
            f"Unbekannte Flaechenbasis '{basis}' -- erlaubt: {sorted(FLAECHENBASIS)}"
        )
    feld, name = FLAECHENBASIS[basis]
    if feld is None:  # "belegt"
        return (wohnungen or {}).get("belegte_flaeche_m2"), name
    wert = ((flaechen or {}).get(feld) or {}).get("wert")
    return wert, name


def _verkaufsflaeche(
    flaechen: Optional[dict[str, Any]], basis: str, wohnungen: Optional[dict[str, Any]],
) -> tuple[Optional[float], str, Optional[float], Optional[str]]:
    """Die Flaeche, auf der ein Preis je m2 tatsaechlich gerechnet werden darf.

    Kernregel: Flaeche, die KEINER Wohnung zugeordnet ist, fliesst nicht in
    Erloes oder Mietertrag. Liegt ein Wohnungsmix vor, ist die belegte Flaeche
    massgebend -- auch wenn als Basis eine groessere Flaeche gewaehlt wurde.
    Die Differenz wird beziffert zurueckgegeben statt stillschweigend
    mitverkauft.

    Live beobachtet: 197 m2 Wohnflaeche, ein Mix aus nur 3.5-/4.5-Zimmer-
    wohnungen belegte davon 125 m2 -- die restlichen 72 m2 wurden trotzdem
    voll mitverkauft.

    Liefert (flaeche, name, nicht_zugeordnet_m2, hinweis).
    """
    flaeche, name = _flaeche_aus(flaechen, basis, wohnungen)
    if flaeche is None:
        return None, name, None, None

    belegt = (wohnungen or {}).get("belegte_flaeche_m2")
    if basis == "belegt" or belegt is None:
        return flaeche, name, None, None

    rest = round(flaeche - belegt, 1)
    if rest <= 0.5:
        return flaeche, name, None, None
    if rest < 0:
        # Der Mix braucht mehr als vorhanden -- das meldet berechne_wohnungen
        # selbst; hier wird auf die vorhandene Flaeche begrenzt.
        return flaeche, name, None, None

    return belegt, f"{name}, davon zugeordnet", rest, (
        f"{rest:,.1f} m2 der {name} ({flaeche:,.1f} m2) sind KEINER Wohnung zugeordnet und "
        f"gehen NICHT in die Rechnung ein -- gerechnet wird auf {belegt:,.1f} m2. "
        "Den Wohnungsmix anpassen, die Restflaeche auf die Wohnungen verteilen oder sie als "
        "gemeinsame Nebennutzflaeche fuehren."
    )


@dataclass
class Verkaufsannahme:
    """Wie der Verkaufserloes gebildet wird.

    Drei Arten, die sich ausschliessen:
      chf_pro_m2       Preis je m2 einer benannten Flaeche (NWF, HNF, ...)
      pro_wohnungstyp  ein Preis je Wohnungstyp (2.5 Zi, 3.5 Zi, ...)
      pro_wohnung      eine Liste konkreter Einzelpreise
    """
    art: str = VERKAUF_PRO_M2
    basis: str = "nwf"
    preis_pro_m2: Optional[Marktwert] = None
    preise_pro_typ: dict[str, Marktwert] = field(default_factory=dict)
    preise_pro_wohnung: list[float] = field(default_factory=list)

    def berechne(self, flaechen, wohnungen) -> dict[str, Any]:
        if self.art == VERKAUF_PRO_M2:
            if self.preis_pro_m2 is None or self.preis_pro_m2.wert is None:
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Kein Verkaufspreis je m2 gesetzt."}
            flaeche, name, nicht_zugeordnet, hinweis = _verkaufsflaeche(
                flaechen, self.basis, wohnungen)
            if flaeche is None:
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": f"{name} ist nicht bestimmt -- ohne sie kein Erloes."}
            preis = self.preis_pro_m2.wert
            return {
                "erloes_chf": round(flaeche * preis, 0),
                "status": self.preis_pro_m2.herkunft,
                "basis": self.basis, "basis_name": name, "basis_flaeche_m2": flaeche,
                "nicht_zugeordnet_m2": nicht_zugeordnet,
                "preis": self.preis_pro_m2.to_dict(),
                "rechnung": f"{flaeche:,.1f} m² {name} × {preis:,.0f} CHF/m²",
                "hinweis": hinweis,
            }

        if self.art == VERKAUF_PRO_TYP:
            typen = (wohnungen or {}).get("typen") or []
            if not typen:
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Keine Wohnungsstruktur -- ohne sie kein Preis je Typ."}
            zeilen, summe, offen = [], 0.0, []
            for t in typen:
                mw = self.preise_pro_typ.get(t["typ"])
                if mw is None or mw.wert is None:
                    offen.append(t["typ"])
                    continue
                betrag = t["anzahl"] * mw.wert
                summe += betrag
                zeilen.append({"typ": t["typ"], "anzahl": t["anzahl"],
                               "preis_chf": mw.wert, "betrag_chf": round(betrag, 0),
                               "herkunft": mw.herkunft})
            if offen:
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": f"Kein Preis gesetzt fuer: {', '.join(offen)}.",
                        "zeilen": zeilen}
            return {"erloes_chf": round(summe, 0), "status": HERKUNFT_BENUTZERANNAHME,
                    "zeilen": zeilen,
                    "rechnung": " + ".join(f"{z['anzahl']}× {z['typ']} à {z['preis_chf']:,.0f}" for z in zeilen)}

        if self.art == VERKAUF_PRO_WOHNUNG:
            if not self.preise_pro_wohnung:
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Keine Einzelpreise gesetzt."}
            anzahl = (wohnungen or {}).get("anzahl_wohnungen")
            if anzahl is not None and anzahl != len(self.preise_pro_wohnung):
                return {"erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": (f"{len(self.preise_pro_wohnung)} Einzelpreise fuer {anzahl} "
                                  "Wohnungen -- die Zahlen muessen uebereinstimmen.")}
            return {"erloes_chf": round(sum(self.preise_pro_wohnung), 0),
                    "status": HERKUNFT_BENUTZERANNAHME,
                    "rechnung": f"{len(self.preise_pro_wohnung)} Einzelpreise summiert"}

        raise WirtschaftlichkeitError(
            f"Unbekannte Verkaufsart '{self.art}' -- erlaubt: "
            f"{VERKAUF_PRO_M2}, {VERKAUF_PRO_TYP}, {VERKAUF_PRO_WOHNUNG}"
        )


MIETE_PRO_M2_JAHR = "chf_pro_m2_jahr"
MIETE_PRO_WOHNUNG_MONAT = "chf_pro_wohnung_monat"
MIETE_PRO_TYP_MONAT = "chf_pro_typ_monat"


@dataclass
class Mietannahme:
    art: str = MIETE_PRO_M2_JAHR
    basis: str = "nwf"
    miete_pro_m2_jahr: Optional[Marktwert] = None
    mieten_pro_typ_monat: dict[str, Marktwert] = field(default_factory=dict)
    mieten_pro_wohnung_monat: list[float] = field(default_factory=list)

    def berechne(self, flaechen, wohnungen) -> dict[str, Any]:
        if self.art == MIETE_PRO_M2_JAHR:
            if self.miete_pro_m2_jahr is None or self.miete_pro_m2_jahr.wert is None:
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Kein Mietansatz je m2 gesetzt."}
            flaeche, name, nicht_zugeordnet, hinweis = _verkaufsflaeche(
                flaechen, self.basis, wohnungen)
            if flaeche is None:
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": f"{name} ist nicht bestimmt."}
            ansatz = self.miete_pro_m2_jahr.wert
            return {"jahresertrag_chf": round(flaeche * ansatz, 0),
                    "status": self.miete_pro_m2_jahr.herkunft,
                    "basis": self.basis, "basis_name": name, "basis_flaeche_m2": flaeche,
                    "nicht_zugeordnet_m2": nicht_zugeordnet,
                    "ansatz": self.miete_pro_m2_jahr.to_dict(),
                    "rechnung": f"{flaeche:,.1f} m² {name} × {ansatz:,.0f} CHF/m²/Jahr",
                    "hinweis": hinweis}

        if self.art == MIETE_PRO_TYP_MONAT:
            typen = (wohnungen or {}).get("typen") or []
            if not typen:
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Keine Wohnungsstruktur."}
            zeilen, summe, offen = [], 0.0, []
            for t in typen:
                mw = self.mieten_pro_typ_monat.get(t["typ"])
                if mw is None or mw.wert is None:
                    offen.append(t["typ"])
                    continue
                jahr = t["anzahl"] * mw.wert * 12
                summe += jahr
                zeilen.append({"typ": t["typ"], "anzahl": t["anzahl"],
                               "monatsmiete_chf": mw.wert, "jahresertrag_chf": round(jahr, 0),
                               "herkunft": mw.herkunft})
            if offen:
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": f"Kein Mietansatz fuer: {', '.join(offen)}.", "zeilen": zeilen}
            return {"jahresertrag_chf": round(summe, 0), "status": HERKUNFT_BENUTZERANNAHME,
                    "zeilen": zeilen,
                    "rechnung": " + ".join(
                        f"{z['anzahl']}× {z['typ']} à {z['monatsmiete_chf']:,.0f}/Mt" for z in zeilen)}

        if self.art == MIETE_PRO_WOHNUNG_MONAT:
            if not self.mieten_pro_wohnung_monat:
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": "Keine Einzelmieten gesetzt."}
            anzahl = (wohnungen or {}).get("anzahl_wohnungen")
            if anzahl is not None and anzahl != len(self.mieten_pro_wohnung_monat):
                return {"jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR,
                        "grund": (f"{len(self.mieten_pro_wohnung_monat)} Einzelmieten fuer "
                                  f"{anzahl} Wohnungen.")}
            return {"jahresertrag_chf": round(sum(self.mieten_pro_wohnung_monat) * 12, 0),
                    "status": HERKUNFT_BENUTZERANNAHME,
                    "rechnung": f"{len(self.mieten_pro_wohnung_monat)} Monatsmieten × 12"}

        raise WirtschaftlichkeitError(f"Unbekannte Mietart '{self.art}'.")


# ---------------------------------------------------------------------------
# Kosten (BKP)
# ---------------------------------------------------------------------------

KOSTEN_PRO_M2 = "chf_pro_m2"
KOSTEN_ABSOLUT = "absolut"
KOSTEN_PROZENT = "prozent"

# Richtwerte fuer die beiden Positionen, die weder in BKP 1-6 noch in Modul 3
# vorkommen. Es sind Systemannahmen -- editierbar wie jede andere Position.
FINANZIERUNG_PROZENT_DEFAULT = 0.025   # Bauzinsen ueber die Bauzeit
VERMARKTUNG_PROZENT_DEFAULT = 0.025    # Makler, Werbung, Verkaufsdokumentation

BKP_BEZEICHNUNG = {
    "1": "Vorbereitungsarbeiten",
    "2": "Gebäude",
    "3": "Betriebseinrichtungen",
    "4": "Umgebung",
    "5": "Baunebenkosten",
    "6": "Reserve",
}


@dataclass
class Kostenposition:
    """Eine Kostenposition mit sichtbarer Berechnungsbasis.

    `art` bestimmt, worauf sich `wert` bezieht:
      chf_pro_m2  -> `basis` ist eine Flaeche (nwf, hnf, gf, ...)
      absolut     -> `wert` ist der Betrag in CHF, `basis` wird ignoriert
      prozent     -> `basis` ist der Schluessel einer anderen Position oder
                     einer Zwischensumme (z.B. "bkp2", "subtotal_1_2_3_4")
    """
    schluessel: str
    bkp: str
    bezeichnung: str
    art: str
    wert: Optional[float]
    basis: Optional[str] = None
    herkunft: str = HERKUNFT_SYSTEMANNAHME
    begruendung: str = ""

    def mit_benutzerwert(self, wert: float, art: Optional[str] = None,
                         basis: Optional[str] = None) -> "Kostenposition":
        return Kostenposition(
            schluessel=self.schluessel, bkp=self.bkp, bezeichnung=self.bezeichnung,
            art=art or self.art, wert=wert, basis=basis if basis is not None else self.basis,
            herkunft=HERKUNFT_BENUTZERANNAHME,
            begruendung=f"Vom Benutzer gesetzt (Systemvorschlag war {self.wert}).",
        )

    def berechne(self, flaechen, zwischenstand: dict[str, float],
                 wohnungen: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        eintrag = {
            "schluessel": self.schluessel, "bkp": self.bkp, "bezeichnung": self.bezeichnung,
            "art": self.art, "ansatz": self.wert, "basis": self.basis,
            "herkunft": self.herkunft, "begruendung": self.begruendung,
            "betrag_chf": None, "rechnung": None, "grund": None,
        }
        if self.wert is None:
            eintrag["grund"] = "Kein Ansatz gesetzt."
            return eintrag

        if self.art == KOSTEN_ABSOLUT:
            eintrag["betrag_chf"] = round(self.wert, 0)
            eintrag["rechnung"] = f"{self.wert:,.0f} CHF (Festbetrag)"
            return eintrag

        if self.art == KOSTEN_PRO_M2:
            flaeche, name = _flaeche_aus(flaechen, self.basis or "gf", wohnungen)
            if flaeche is None:
                eintrag["grund"] = f"{name} ist nicht bestimmt -- Position nicht berechenbar."
                return eintrag
            eintrag["betrag_chf"] = round(flaeche * self.wert, 0)
            eintrag["basis_name"] = name
            eintrag["basis_flaeche_m2"] = flaeche
            eintrag["rechnung"] = f"{self.wert:,.0f} CHF/m² × {flaeche:,.1f} m² {name}"
            return eintrag

        if self.art == KOSTEN_PROZENT:
            bezug = zwischenstand.get(self.basis or "")
            if bezug is None:
                eintrag["grund"] = (
                    f"Bezugsgroesse '{self.basis}' ist nicht verfuegbar -- moeglich sind "
                    f"{sorted(zwischenstand)}."
                )
                return eintrag
            eintrag["betrag_chf"] = round(bezug * self.wert, 0)
            eintrag["basis_name"] = self.basis
            eintrag["basis_betrag_chf"] = round(bezug, 0)
            eintrag["rechnung"] = f"{self.wert:.1%} von {bezug:,.0f} CHF ({self.basis})"
            return eintrag

        raise WirtschaftlichkeitError(
            f"Unbekannte Kostenart '{self.art}' -- erlaubt: {KOSTEN_PRO_M2}, {KOSTEN_ABSOLUT}, {KOSTEN_PROZENT}"
        )


def standard_kostenmodell(
    ausbaustandard: str = "rendite",
    kostengenauigkeit: str = "kostenschaetzung",
    kostenbasis: str = "gf",
) -> list[Kostenposition]:
    """BKP 1-6 mit den Richtwerten aus modul3_financial.

    Alle Ansaetze sind Modellannahmen und ueberschreibbar. Die Richtwerte
    stammen unveraendert aus Modul 3 -- es gibt im Projekt nur EINEN Satz.
    """
    if ausbaustandard not in AUSBAUSTANDARD_CHF_PRO_M2_BGF:
        raise WirtschaftlichkeitError(
            f"Unbekannter Ausbaustandard '{ausbaustandard}' -- "
            f"bekannt: {sorted(AUSBAUSTANDARD_CHF_PRO_M2_BGF)}"
        )
    if kostengenauigkeit not in BKP9_PROZENT_BY_GENAUIGKEIT:
        raise WirtschaftlichkeitError(
            f"Unbekannte Kostengenauigkeit '{kostengenauigkeit}' -- "
            f"bekannt: {sorted(BKP9_PROZENT_BY_GENAUIGKEIT)}"
        )
    aushub_rate = BKP1_AUSHUB_TIEFE_M_DEFAULT * BKP1_AUSHUB_CHF_PRO_M3_DEFAULT
    return [
        Kostenposition(
            "bkp1_aushub", "1", "Aushub und Vorbereitung", KOSTEN_PRO_M2,
            round(aushub_rate, 0), kostenbasis,
            begruendung=(
                f"{BKP1_AUSHUB_TIEFE_M_DEFAULT:g} m Aushubtiefe × "
                f"{BKP1_AUSHUB_CHF_PRO_M3_DEFAULT:g} CHF/m³ (Richtwert Modul 3). "
                "Projektspezifisch stark abweichend."
            ),
        ),
        Kostenposition(
            "bkp2_gebaeude", "2", "Gebäude", KOSTEN_PRO_M2,
            AUSBAUSTANDARD_CHF_PRO_M2_BGF[ausbaustandard], kostenbasis,
            begruendung=f"Ausbaustandard '{ausbaustandard}' (Richtwert Modul 3).",
        ),
        Kostenposition(
            "bkp3_betriebseinrichtungen", "3", "Betriebseinrichtungen", KOSTEN_ABSOLUT, 0.0,
            begruendung=(
                "Im Wohnungsbau meist nicht relevant und deshalb mit 0 vorbelegt. "
                "Bei Gewerbeanteil hier den tatsaechlichen Betrag setzen."
            ),
        ),
        Kostenposition(
            "bkp4_umgebung", "4", "Umgebung", KOSTEN_PROZENT,
            BKP4_PROZENT_VON_BKP2_DEFAULT, "bkp2_gebaeude",
            begruendung="Anteil von BKP 2, Mitte 4-6 % (Richtwert Modul 3).",
        ),
        Kostenposition(
            "bkp5_baunebenkosten", "5", "Baunebenkosten und Honorare", KOSTEN_PROZENT,
            BKP5_PROZENT_DEFAULT, "subtotal_bkp1_4",
            begruendung="Anteil von BKP 1-4, Mitte 10-12 % nach SIA 102/103 (Richtwert Modul 3).",
        ),
        Kostenposition(
            "bkp6_reserve", "6", "Reserve und Unvorhergesehenes", KOSTEN_PROZENT,
            BKP9_PROZENT_BY_GENAUIGKEIT[kostengenauigkeit], "subtotal_bkp1_5",
            begruendung=(
                f"Kostengenauigkeit '{kostengenauigkeit}' (Richtwert Modul 3). "
                "In der klassischen BKP-Gliederung ist das BKP 9; hier als Position 6 "
                "gefuehrt, weil die Produktvorgabe BKP 1-6 verlangt."
            ),
        ),
        Kostenposition(
            "finanzierung", "F", "Finanzierung (Bauzinsen)", KOSTEN_PROZENT,
            FINANZIERUNG_PROZENT_DEFAULT, "subtotal_bkp1_6",
            begruendung=(
                "Bauzinsen ueber die Bauzeit, als Anteil der Baukosten BKP 1-6. Haengt an "
                "Zinssatz, Bauzeit und Eigenkapitalquote -- am Projekt zu setzen."
            ),
        ),
        Kostenposition(
            "vermarktung", "V", "Vermarktung", KOSTEN_PROZENT,
            VERMARKTUNG_PROZENT_DEFAULT, "verkaufserloes",
            begruendung=(
                "Makler, Werbung und Verkaufsdokumentation als Anteil des Verkaufserloeses. "
                "Bei Vermietung stattdessen die Erstvermietungskosten setzen."
            ),
        ),
    ]


def abbruchposition(bestand_volumen_m3: Optional[float]) -> Kostenposition:
    """Abbruch -- nur beim Ersatzneubau, und nur mit bekanntem Volumen."""
    if not bestand_volumen_m3:
        return Kostenposition(
            "bkp1_abbruch", "1", "Abbruch Bestand", KOSTEN_ABSOLUT, None,
            herkunft=HERKUNFT_NICHT_BESTIMMBAR,
            begruendung=(
                "Das Gebaeudevolumen des Bestands ist nicht bekannt (GWR-Merkmal 'gvol' "
                "fehlt haeufig). Ohne Volumen wird kein Abbruchbetrag geschaetzt -- er ist "
                "als eigene Position zu setzen."
            ),
        )
    return Kostenposition(
        "bkp1_abbruch", "1", "Abbruch Bestand", KOSTEN_ABSOLUT,
        round(bestand_volumen_m3 * BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT, 0),
        begruendung=(
            f"{bestand_volumen_m3:,.0f} m³ Gebaeudevolumen × "
            f"{BKP1_ABBRUCH_CHF_PRO_M3_DEFAULT:g} CHF/m³ (Richtwert Modul 3)."
        ),
    )


def berechne_kosten(
    positionen: list[Kostenposition],
    flaechen: Optional[dict[str, Any]],
    zusatzbasen: Optional[dict[str, float]] = None,
    wohnungen: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Rechnet die Positionen der Reihe nach und fuehrt Zwischensummen mit.

    Die Reihenfolge zaehlt: eine Prozentposition kann sich nur auf etwas
    beziehen, das vorher berechnet wurde. Fehlt die Bezugsgroesse, wird die
    Position als nicht berechenbar gemeldet statt uebersprungen.
    """
    # Groessen, die ausserhalb der Kostenliste entstehen und auf die sich eine
    # Prozentposition beziehen darf -- z.B. die Vermarktung auf den Erloes.
    zwischenstand: dict[str, float] = dict(zusatzbasen or {})
    zeilen: list[dict[str, Any]] = []
    nach_bkp: dict[str, float] = {}
    offen: list[str] = []

    for pos in positionen:
        eintrag = pos.berechne(flaechen, zwischenstand, wohnungen)
        zeilen.append(eintrag)
        betrag = eintrag.get("betrag_chf")
        if betrag is None:
            offen.append(f"{pos.bezeichnung}: {eintrag.get('grund')}")
            continue
        zwischenstand[pos.schluessel] = betrag
        nach_bkp[pos.bkp] = round(nach_bkp.get(pos.bkp, 0.0) + betrag, 0)
        # Zwischensummen fuer die Prozentpositionen der spaeteren Stufen.
        zwischenstand["subtotal_bkp1_4"] = round(
            sum(v for k, v in nach_bkp.items() if k in {"1", "2", "3", "4"}), 0)
        zwischenstand["subtotal_bkp1_5"] = round(
            sum(v for k, v in nach_bkp.items() if k in {"1", "2", "3", "4", "5"}), 0)
        zwischenstand["subtotal_bkp1_6"] = round(
            sum(v for k, v in nach_bkp.items() if k in {"1", "2", "3", "4", "5", "6"}), 0)
        zwischenstand["subtotal_alle"] = round(sum(nach_bkp.values()), 0)

    # Eine Summe von 0 CHF, die nur entstand, weil alle tragenden Positionen
    # nicht berechenbar waren, ist irrefuehrend: sie sieht aus wie "kostet
    # nichts", heisst aber "nichts gerechnet".
    tragend_berechnet = any(
        z.get("betrag_chf") for z in zeilen if z.get("art") in (KOSTEN_PRO_M2, KOSTEN_ABSOLUT)
    )
    summe = round(sum(nach_bkp.values()), 0) if nach_bkp else None
    if summe is not None and not tragend_berechnet:
        summe = None
        offen.append(
            "Baukosten insgesamt: keine tragende Position war berechenbar (es fehlt die "
            "Flaechenbasis). Die Summe waere 0 CHF und damit irrefuehrend."
        )

    return {
        "positionen": zeilen,
        "nach_bkp": nach_bkp,
        "baukosten_chf": summe,
        "offene_positionen": offen,
        "vollstaendig": not offen,
    }


# ---------------------------------------------------------------------------
# Wirtschaftlichkeit je Szenario
# ---------------------------------------------------------------------------

# Wie das Land in Gewinn und Marge eingeht.
LAND_KAUF = "kauf"          # Das Grundstueck wird erworben -- volle Landkosten.
LAND_IM_BESITZ = "im_besitz"  # Es gehoert bereits -- keine Landkosten im Projekt.

_LAND_ANSATZ_TEXT = {
    LAND_KAUF: (
        "Das Grundstueck wird erworben: die vollen Landkosten gehen in jedes Szenario ein. "
        "Fuer eine Erweiterung des Bestands (Anbau, Aufstockung) bedeutet das, dass der "
        "gesamte Landpreis einer kleinen Zusatzflaeche gegenuebersteht -- die Marge faellt "
        "dann folgerichtig schlecht aus."
    ),
    LAND_IM_BESITZ: (
        "Das Grundstueck gehoert bereits: es werden KEINE Landkosten angesetzt. Gewinn und "
        "Marge messen dann nur die Bauinvestition. Der residuale Landwert bleibt davon "
        "unberuehrt -- er beantwortet die andere Frage, welchen Preis das Projekt tragen wuerde."
    ),
}


@dataclass
class Marktannahmen:
    """Alle marktseitigen Eingaben in einem Objekt."""
    verkauf: Optional[Verkaufsannahme] = None
    miete: Optional[Mietannahme] = None
    bodenpreis_chf_pro_m2: Optional[Marktwert] = None
    landpreis_total_chf: Optional[float] = None
    zielmarge: float = MARGE_PROZENT_VOM_GDV_DEFAULT
    land_ansatz: str = LAND_KAUF

    def __post_init__(self) -> None:
        if self.land_ansatz not in _LAND_ANSATZ_TEXT:
            raise WirtschaftlichkeitError(
                f"Unbekannter Land-Ansatz '{self.land_ansatz}' -- erlaubt: "
                f"{LAND_KAUF}, {LAND_IM_BESITZ}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verkauf_art": self.verkauf.art if self.verkauf else None,
            "miete_art": self.miete.art if self.miete else None,
            "bodenpreis": self.bodenpreis_chf_pro_m2.to_dict() if self.bodenpreis_chf_pro_m2 else None,
            "landpreis_total_chf": self.landpreis_total_chf,
            "zielmarge": self.zielmarge,
            "land_ansatz": self.land_ansatz,
            "land_ansatz_bedeutung": _LAND_ANSATZ_TEXT[self.land_ansatz],
        }


def berechne_fuer_szenario(
    szenario: dict[str, Any],
    grundstuecksflaeche_m2: Optional[float],
    markt: Marktannahmen,
    kostenpositionen: Optional[list[Kostenposition]] = None,
    *,
    bestand_volumen_m3: Optional[float] = None,
) -> dict[str, Any]:
    """Die vollstaendige wirtschaftliche Rechnung fuer EIN Szenario."""
    flaechen = (szenario.get("flaechen") or {}).get("flaechen")
    wohnungen = szenario.get("wohnungen")

    positionen = list(kostenpositionen) if kostenpositionen is not None else standard_kostenmodell()
    # Abbruch nur beim Ersatzneubau, und nur wenn nicht schon gesetzt.
    if szenario.get("id") == "ersatzneubau" and not any(p.schluessel == "bkp1_abbruch" for p in positionen):
        positionen = [abbruchposition(bestand_volumen_m3), *positionen]

    # Der Erloes wird zuerst gerechnet: die Vermarktungskosten beziehen sich
    # darauf, und eine Kostenposition darf sich nur auf bereits Bekanntes stuetzen.
    verkauf = markt.verkauf.berechne(flaechen, wohnungen) if markt.verkauf else {
        "erloes_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR, "grund": "Keine Verkaufsannahme gesetzt."}
    miete = markt.miete.berechne(flaechen, wohnungen) if markt.miete else {
        "jahresertrag_chf": None, "status": HERKUNFT_NICHT_BESTIMMBAR, "grund": "Keine Mietannahme gesetzt."}
    erloes = verkauf.get("erloes_chf")

    zusatzbasen = {"verkaufserloes": erloes} if erloes is not None else {}
    kosten = berechne_kosten(positionen, flaechen, zusatzbasen, wohnungen)
    baukosten = kosten["baukosten_chf"]
    jahresertrag = miete.get("jahresertrag_chf")

    # Landwert: entweder vom Benutzer gesetzt (total oder je m2), sonst offen.
    # Gehoert das Grundstueck bereits, gehen KEINE Landkosten ins Projekt.
    if markt.land_ansatz == LAND_IM_BESITZ:
        landwert = 0.0
        landwert_herkunft = HERKUNFT_BENUTZERANNAHME
        landwert_rechnung = "Grundstueck im Besitz -- keine Landkosten im Projekt angesetzt"
    else:
        landwert = markt.landpreis_total_chf
        landwert_herkunft = HERKUNFT_BENUTZERANNAHME if landwert is not None else HERKUNFT_NICHT_BESTIMMBAR
        landwert_rechnung = "Gesamtkaufpreis (Benutzerannahme)" if landwert is not None else None
        if landwert is None and markt.bodenpreis_chf_pro_m2 and markt.bodenpreis_chf_pro_m2.wert is not None:
            if grundstuecksflaeche_m2:
                landwert = round(markt.bodenpreis_chf_pro_m2.wert * grundstuecksflaeche_m2, 0)
                landwert_herkunft = markt.bodenpreis_chf_pro_m2.herkunft
                landwert_rechnung = (
                    f"{grundstuecksflaeche_m2:,.1f} m² × "
                    f"{markt.bodenpreis_chf_pro_m2.wert:,.0f} CHF/m²"
                )

    gesamtinvestition = None
    if baukosten is not None and landwert is not None:
        gesamtinvestition = round(baukosten + landwert, 0)

    gewinn = marge = rendite = None
    if erloes is not None and gesamtinvestition is not None:
        gewinn = round(erloes - gesamtinvestition, 0)
        marge = round(gewinn / erloes, 4) if erloes else None
    if jahresertrag is not None and gesamtinvestition:
        rendite = round(jahresertrag / gesamtinvestition, 4)

    # Residualwert: rueckwaerts, ohne Land.
    residual = _residualwert(erloes, baukosten, markt.zielmarge, grundstuecksflaeche_m2)

    zielmarge_erreicht = None
    if marge is not None:
        zielmarge_erreicht = marge >= markt.zielmarge

    def pro_m2(betrag: Optional[float], basis: str = "nwf") -> Optional[float]:
        flaeche, _ = _flaeche_aus(flaechen, basis, wohnungen)
        if betrag is None or not flaeche:
            return None
        return round(betrag / flaeche, 0)

    return {
        "szenario_id": szenario.get("id"),
        "bezeichnung": szenario.get("bezeichnung"),
        "machbarkeit": szenario.get("machbarkeit"),
        "verkauf": verkauf,
        "miete": miete,
        "flaechenbilanz": (wohnungen or {}).get("flaechenbilanz"),
        "kosten": kosten,
        "land": {
            "wert_chf": landwert, "herkunft": landwert_herkunft, "rechnung": landwert_rechnung,
            "ansatz": markt.land_ansatz, "ansatz_bedeutung": _LAND_ANSATZ_TEXT[markt.land_ansatz],
            "bodenpreis": markt.bodenpreis_chf_pro_m2.to_dict() if markt.bodenpreis_chf_pro_m2 else None,
            "grundstuecksflaeche_m2": grundstuecksflaeche_m2,
        },
        "ergebnis": {
            "gesamtinvestition_chf": gesamtinvestition,
            "verkaufserloes_chf": erloes,
            "jahresmietertrag_chf": jahresertrag,
            "gewinn_chf": gewinn,
            "marge": marge,
            "zielmarge": markt.zielmarge,
            "zielmarge_erreicht": zielmarge_erreicht,
            "bruttorendite": rendite,
            "kosten_pro_m2_nwf": pro_m2(gesamtinvestition),
            "erloes_pro_m2_nwf": pro_m2(erloes),
        },
        "residualwert": residual,
        "markt": markt.to_dict(),
        "offene_punkte": _offene_punkte(
            kosten, verkauf, miete, landwert, gesamtinvestition,
            szenario_id=szenario.get("id"), land_ansatz=markt.land_ansatz,
        ),
    }


def _residualwert(
    erloes: Optional[float], baukosten: Optional[float], zielmarge: float,
    grundstuecksflaeche_m2: Optional[float],
) -> dict[str, Any]:
    """Verkaufserloes minus Projektkosten ohne Land minus Zielgewinn."""
    if erloes is None or baukosten is None:
        fehlend = []
        if erloes is None:
            fehlend.append("Verkaufserloes")
        if baukosten is None:
            fehlend.append("Baukosten")
        return {
            "status": HERKUNFT_NICHT_BESTIMMBAR,
            "grund": f"{' und '.join(fehlend)} nicht bestimmt -- ohne sie kein Residualwert.",
        }
    zielgewinn = round(erloes * zielmarge, 0)
    wert = round(erloes - baukosten - zielgewinn, 0)
    return {
        "status": "berechnet",
        "max_landwert_chf": wert,
        "max_landwert_chf_pro_m2": (
            round(wert / grundstuecksflaeche_m2, 0) if grundstuecksflaeche_m2 else None
        ),
        "negativ": wert < 0,
        "zielmarge": zielmarge,
        "zielgewinn_chf": zielgewinn,
        "rechnung": (
            f"{erloes:,.0f} CHF Erlös - {baukosten:,.0f} CHF Baukosten - "
            f"{zielgewinn:,.0f} CHF Zielgewinn ({zielmarge:.1%})"
        ),
        "hinweis": (
            "Bei negativem Wert trägt das Projekt zu den gesetzten Annahmen keinen Landpreis -- "
            "Verkaufspreis, Wohnungsmix, BKP oder Zielmarge prüfen."
        ) if wert < 0 else None,
    }


# Szenarien, die auf dem Bestand aufbauen statt ihn zu ersetzen.
_ERWEITERUNGSSZENARIEN = {"anbau", "aufstockung", "dachausbau", "bestand_plus_neubau"}


def _offene_punkte(kosten, verkauf, miete, landwert, gesamtinvestition,
                   szenario_id=None, land_ansatz=LAND_KAUF) -> list[str]:
    offen = list(kosten.get("offene_positionen") or [])
    if szenario_id in _ERWEITERUNGSSZENARIEN and land_ansatz == LAND_KAUF and landwert:
        offen.append(
            "Landkosten: Dieses Szenario erweitert den Bestand, traegt hier aber die VOLLEN "
            "Landkosten -- das ist die Sicht beim Kauf des Grundstuecks. Gehoert es bereits, "
            f"mit land_ansatz='{LAND_IM_BESITZ}' rechnen; Gewinn und Marge aendern sich dann "
            "erheblich."
        )
    if verkauf.get("erloes_chf") is None and verkauf.get("grund"):
        offen.append(f"Verkauf: {verkauf['grund']}")
    if verkauf.get("hinweis"):
        offen.append(f"Verkauf: {verkauf['hinweis']}")
    if miete.get("jahresertrag_chf") is None and miete.get("grund"):
        offen.append(f"Miete: {miete['grund']}")
    if landwert is None:
        offen.append(
            "Landwert: weder ein Gesamtkaufpreis noch ein Bodenpreis je m² gesetzt -- "
            "Gewinn und Marge sind deshalb nicht bestimmbar. Der residuale Landwert "
            "steht trotzdem zur Verfügung, er braucht den Landpreis gerade nicht."
        )
    elif gesamtinvestition is None:
        offen.append("Gesamtinvestition: Baukosten unvollständig.")
    return offen


def berechne_alle(
    szenarien_ergebnis: dict[str, Any],
    grundstuecksflaeche_m2: Optional[float],
    markt: Marktannahmen,
    kostenpositionen: Optional[list[Kostenposition]] = None,
    *,
    auswahl: Optional[list[str]] = None,
    bestand_volumen_m3: Optional[float] = None,
) -> dict[str, Any]:
    """Rechnet alle machbaren Szenarien durch und stellt sie gegenueber."""
    szenarien = (szenarien_ergebnis or {}).get("szenarien") or {}
    if not szenarien:
        return {
            "status": HERKUNFT_NICHT_BESTIMMBAR,
            "grund": (szenarien_ergebnis or {}).get("grund")
                     or "Keine Szenarien vorhanden -- ohne sie keine Wirtschaftlichkeit.",
            "szenarien": {},
        }

    gewaehlt = auswahl or list(szenarien)
    unbekannt = [s for s in gewaehlt if s not in szenarien]
    if unbekannt:
        raise WirtschaftlichkeitError(
            f"Unbekannte Szenarien: {unbekannt}. Vorhanden: {sorted(szenarien)}"
        )

    ergebnisse = {}
    for name in gewaehlt:
        s = dict(szenarien[name])
        s.setdefault("id", name)
        ergebnisse[name] = berechne_fuer_szenario(
            s, grundstuecksflaeche_m2, markt, kostenpositionen,
            bestand_volumen_m3=bestand_volumen_m3,
        )

    return {
        "status": "berechnet",
        "szenarien": ergebnisse,
        "vergleich": vergleiche_wirtschaftlich(ergebnisse),
        "markt": markt.to_dict(),
    }


def vergleiche_wirtschaftlich(ergebnisse: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Eine Zeile je Szenario, sortiert nach Gewinn."""
    zeilen = []
    for name, e in ergebnisse.items():
        erg = e.get("ergebnis") or {}
        res = e.get("residualwert") or {}
        zeilen.append({
            "id": name,
            "bezeichnung": e.get("bezeichnung"),
            "machbarkeit": e.get("machbarkeit"),
            "verkaufserloes_chf": erg.get("verkaufserloes_chf"),
            "jahresmietertrag_chf": erg.get("jahresmietertrag_chf"),
            "baukosten_chf": (e.get("kosten") or {}).get("baukosten_chf"),
            "kosten_vollstaendig": (e.get("kosten") or {}).get("vollstaendig"),
            "gesamtinvestition_chf": erg.get("gesamtinvestition_chf"),
            "gewinn_chf": erg.get("gewinn_chf"),
            "marge": erg.get("marge"),
            "zielmarge_erreicht": erg.get("zielmarge_erreicht"),
            "bruttorendite": erg.get("bruttorendite"),
            "max_landwert_chf": res.get("max_landwert_chf"),
            "max_landwert_chf_pro_m2": res.get("max_landwert_chf_pro_m2"),
            "anzahl_offene_punkte": len(e.get("offene_punkte") or []),
        })
    zeilen.sort(key=lambda z: (
        z["max_landwert_chf"] if z["max_landwert_chf"] is not None else float("-inf")
    ), reverse=True)
    return zeilen

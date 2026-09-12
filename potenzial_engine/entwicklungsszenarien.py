"""
Entwicklungsszenarien-Taxonomie (Design-Vorbereitung, KEINE Berechnungslogik).

Legt nur fest, WELCHE Entwicklungsszenarien die Potenzial-Engine spaeter
unterscheiden soll und WELCHE zusaetzlichen Eingaben jedes Szenario
braucht -- damit das bestehende Datenmodell (G1, SIA-416, spaeter
Modul 3/4) nicht stillschweigend auf ein einziges implizites Szenario
verengt bleibt ("vollstaendiger Neubau nach geltendem Baurecht auf
freier Parzelle", das heute z.B. G1/Modul 3 tatsaechlich rechnen).

Enthaelt bewusst KEINE Berechnung und KEINE Integration in G1/SIA-416/
Modul 3: jede szenariospezifische Logik (Bestandsabzug von der
Geschossflaeche, Abbruch-/Entsorgungskosten, Statik-Pruefung fuer eine
Aufstockung, getrennte GF-Bilanzen bei einer Kombination, etc.) wird
erst implementiert, wenn eines dieser Szenarien tatsaechlich gebraucht
wird. Bis dahin dient dieses Modul nur als geteiltes Vokabular/Checkliste.

`sia416_besonderheit` je Szenario dokumentiert zusaetzlich, OB und WARUM
die GF->NF/HNF-Umrechnung (sia416_flaechen.py) fuer dieses Szenario eine
eigene Modellannahme braucht statt eine bestehende (Neubau-/Bestands-)
Quote zu uebernehmen -- ebenfalls reine Dokumentation, keine Logik.

`benoetigte_flaechendaten` grenzt davon eine engere Teilmenge ab: NUR die
Flaechen-/Geometriewerte, die spaeter fuer die GF-pro-Bauteil-Bilanz vor
der SIA-416-Kaskade noetig waeren (z.B. "welche GF-Teilmenge ist Bestand,
welche Neubau") -- im Unterschied zu `benoetigte_zusatzeingaben`, das auch
nicht-geometrische Bestaetigungen/Kosten enthaelt (z.B. Statik-Pruefung,
Abbruchkosten).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class Szenariotyp(str, Enum):
    BESTAND = "bestand"
    # Sanierung ist bewusst ein eigener Typ und keine Spielart von BESTAND:
    # "belassen" heisst nichts tun, "sanieren" heisst investieren ohne zu
    # erweitern. Wirtschaftlich sind das zwei voellig verschiedene Faelle.
    SANIERUNG = "sanierung"
    ANBAU_ERWEITERUNG = "anbau_erweiterung"
    AUFSTOCKUNG_DACHAUSBAU = "aufstockung_dachausbau"
    ERSATZNEUBAU = "ersatzneubau"
    KOMBINATION_BESTAND_NEUBAU = "kombination_bestand_neubau"


@dataclass(frozen=True)
class SzenarioAnforderung:
    """Beschreibt, WELCHE zusaetzlichen Eingaben ein Szenario braucht --
    reine Metadaten fuer die spaetere Implementierung, keine dieser
    Eingaben wird hier berechnet, geprueft oder defaultet."""
    szenario: Szenariotyp
    benoetigte_zusatzeingaben: List[str]
    beschreibung: str
    heute_bereits_abgedeckt_durch: str
    sia416_besonderheit: str
    benoetigte_flaechendaten: List[str]


SZENARIO_ANFORDERUNGEN: Dict[Szenariotyp, SzenarioAnforderung] = {
    Szenariotyp.BESTAND: SzenarioAnforderung(
        szenario=Szenariotyp.BESTAND,
        benoetigte_zusatzeingaben=["gwr_bestandsgeschossflaeche_m2", "gwr_bestandsgeschosse"],
        beschreibung="Ist-Zustand ohne bauliche Massnahme -- dient als Referenzwert fuer alle "
                     "anderen Szenarien (Delta-Betrachtung).",
        heute_bereits_abgedeckt_durch="Modul 1 GWR-Abfrage liefert die Rohdaten (Baujahr, Geschosse, "
                                       "Energiebezugsflaeche); es gibt aber noch keine Ableitung "
                                       "'Bestand als eigenes Szenario neben dem Neubau-Ergebnis'.",
        sia416_besonderheit="GWR-Energiebezugsflaeche (SIA 380/1) darf NICHT als HNF verwendet werden "
                             "(siehe sia416_flaechen.GWR_FELDER_KEINE_SIA416_FLAECHE) -- ohne echte "
                             "Grundrissdaten braucht auch der Bestand eine eigene Modellannahme.",
        benoetigte_flaechendaten=[
            "bestehende_geschossflaeche_m2 (moeglichst aus Plan/Abrechnung, NICHT aus GWR-Energiebezugsflaeche)",
            "bestehende_geschosszahl (fuer Vergleich mit G1s baurechtlich zulaessiger Geschosszahl)",
        ],
    ),
    Szenariotyp.SANIERUNG: SzenarioAnforderung(
        szenario=Szenariotyp.SANIERUNG,
        benoetigte_zusatzeingaben=[
            "bestand_flaeche_nwf_m2 (aus Plan oder Abrechnung)",
            "sanierungsumfang (Pinsel-, Teil- oder Totalsanierung)",
            "sanierungskosten_chf_pro_m2",
        ],
        beschreibung="Der Bestand bleibt in Volumen und Grundriss unveraendert und wird "
                     "erneuert. Das EINZIGE Szenario, das keine Ausnuetzung verbraucht -- "
                     "es schafft keine neue Geschossflaeche. Deshalb bleibt es auch dort "
                     "moeglich, wo das Ausnuetzungsbudget ausgeschoepft oder ueberschritten "
                     "ist und jede Erweiterung ausscheidet.",
        heute_bereits_abgedeckt_durch="Baukoerper, Geschosszahl und Ausnuetzungsbudget kommen "
                                       "aus derselben Bestandsauswertung wie beim Szenario "
                                       "'Bestand belassen'; die Flaeche muss der Benutzer "
                                       "beisteuern.",
        sia416_besonderheit="Die Flaechenkaskade wird NICHT gerechnet: die Verhaeltnisse "
                             "KF/GF, VF+FF/NGF und HNF/NF des Annahmenprofils sind "
                             "Erfahrungswerte fuer Neubauten. Ein Altbau hat andere "
                             "Konstruktions- und Erschliessungsanteile. Die Sanierung darf "
                             "nicht die Hintertuer sein, durch die geschaetzte "
                             "Bestandsflaechen doch in die Rechnung kommen.",
        benoetigte_flaechendaten=[
            "bestehende_wohnflaeche_nwf_m2 (aus Plan/Abrechnung, NICHT aus GWR-Energiebezugsflaeche)",
            "sanierungsumfang je Bauteil (Huelle, Haustechnik, Ausbau) fuer eine Kostenschaetzung",
        ],
    ),
    Szenariotyp.ANBAU_ERWEITERUNG: SzenarioAnforderung(
        szenario=Szenariotyp.ANBAU_ERWEITERUNG,
        benoetigte_zusatzeingaben=[
            "gwr_bestandsgeschossflaeche_m2",
            "verbleibende_baurechtliche_reserve_m2",
            "statische_anschliessbarkeit_bestaetigt",
        ],
        beschreibung="Erweiterung des bestehenden Gebaeudes auf freier Flaeche innerhalb des "
                     "G1-Baubereichs, unter Beibehaltung des Bestandsgebaeudes.",
        heute_bereits_abgedeckt_durch="Nichts -- G1 rechnet nur den vollen Baubereich/Fussabdruck "
                                       "auf freier Parzelle, ohne ein bestehendes Gebaeudevolumen "
                                       "auszusparen oder anzurechnen.",
        sia416_besonderheit="Der neue GF-Anteil erhaelt seine eigene Quote (aktueller Grundrisstyp), "
                             "nicht zwingend die ggf. aeltere, weniger effiziente Bestandsquote.",
        benoetigte_flaechendaten=[
            "bestehende_geschossflaeche_m2 (Bestandsteil, unveraendert)",
            "baubereich_geometrie_anbauteil (Teilmenge von G1s Baubereich, die tatsaechlich frei/bebaubar ist)",
            "geschossflaeche_anbauteil_m2 (separat von der Bestandsflaeche zu fuehren)",
        ],
    ),
    Szenariotyp.AUFSTOCKUNG_DACHAUSBAU: SzenarioAnforderung(
        szenario=Szenariotyp.AUFSTOCKUNG_DACHAUSBAU,
        benoetigte_zusatzeingaben=[
            "gwr_bestandsgeschosse",
            "statik_tragreserve_bestaetigt",
            "zusaetzliche_geschosse_zulaessig",
        ],
        beschreibung="Zusaetzliche Vollgeschosse oder Dachausbau auf dem bestehenden Gebaeude -- "
                     "setzt eine hier NICHT gepruefte Tragwerksreserve voraus.",
        heute_bereits_abgedeckt_durch="G1s Geschosszahl-Kaskade (Vollgeschosse vs. Hoehe) liefert "
                                       "die baurechtlich zulaessige Gesamtgeschosszahl -- die Differenz "
                                       "zum GWR-Bestand (= zusaetzlich mögliche Geschosse) wird aber "
                                       "aktuell nirgends explizit gebildet.",
        sia416_besonderheit="Eigene Quote empfohlen statt Uebernahme der Neubau- oder Bestandsquote: "
                             "Dachschraege reduziert anrechenbare NF (SIA-416-Hoehenausschluss), "
                             "gemeinsame Erschliessung mit dem Bestand senkt gleichzeitig den "
                             "Zusatzaufwand pro m2 -- zwei gegenlaeufige Effekte.",
        benoetigte_flaechendaten=[
            "zusaetzliche_geschosse_m2 (G1-Geschosszahl-Kaskade minus Bestandsgeschosse, als eigene GF-Teilmenge)",
            "dachschraegen_geometrie (fuer den SIA-416-Hoehenausschluss bei der NF-Ermittlung)",
            "bestehende_geschossflaeche_pro_geschoss_m2 (fuer den Fussabdruck des Aufbaus, i.d.R. identisch mit Bestand)",
        ],
    ),
    Szenariotyp.ERSATZNEUBAU: SzenarioAnforderung(
        szenario=Szenariotyp.ERSATZNEUBAU,
        benoetigte_zusatzeingaben=[
            "abbruch_und_entsorgungskosten_chf",
            "gwr_delta_schwellenwert_ueberschritten",
        ],
        beschreibung="Vollstaendiger Abbruch und Neubau nach aktuell geltendem Baurecht.",
        heute_bereits_abgedeckt_durch="Entspricht dem Grundfall, den G1 und Modul 3 heute bereits "
                                       "rechnen (BGF/Residualwert auf Basis der vollen baurechtlichen "
                                       "Ausnuetzung); die GWR-Delta-Schwellenwert-Pruefung existiert "
                                       "bereits in Modul 3.",
        sia416_besonderheit="Standardquote des jeweiligen Gebaeudetyps -- der Fall, fuer den die "
                             "GF->NF->HNF-Kaskade heute implizit ausgelegt ist (keine Bestands- oder "
                             "Dachschraegen-Sonderbehandlung noetig).",
        benoetigte_flaechendaten=[
            "geschossflaeche_m2 (bereits vollstaendig aus G1 verfuegbar, keine zusaetzliche Erhebung noetig)",
        ],
    ),
    Szenariotyp.KOMBINATION_BESTAND_NEUBAU: SzenarioAnforderung(
        szenario=Szenariotyp.KOMBINATION_BESTAND_NEUBAU,
        benoetigte_zusatzeingaben=[
            "gwr_bestandsgeschossflaeche_m2",
            "neubauteil_geschossflaeche_m2",
            "trennung_bestand_neubau_baurechtlich_zulaessig",
        ],
        beschreibung="Teilweiser Erhalt eines Gebaeudeteils bei gleichzeitigem Neubau auf einem "
                     "anderen Parzellenteil -- braucht getrennte GF-Bilanzen fuer Bestand und Neubau, "
                     "die am Ende zusammengefuehrt werden.",
        heute_bereits_abgedeckt_durch="Nichts -- weder G1 noch SIA-416-Kaskade kennen aktuell mehr "
                                       "als eine einzelne, ungeteilte Geschossflaeche pro Parzelle.",
        sia416_besonderheit="Bestand- und Neubau-Anteil erhalten je ihre eigene Quote und werden "
                             "erst NACH der Umrechnung summiert -- nicht die GF vorher addieren und "
                             "eine gemeinsame Quote darauf anwenden.",
        benoetigte_flaechendaten=[
            "bestehende_geschossflaeche_m2 (Bestandsteil)",
            "geschossflaeche_neubauteil_m2 (separat aus G1 fuer den entsprechenden Parzellenteil)",
            "trennlinie_geometrie (welcher Teil der Parzelle/des Gebaeudes ist Bestand vs. Neubau)",
        ],
    ),
}


def anforderungen_fuer(szenario: Szenariotyp) -> SzenarioAnforderung:
    return SZENARIO_ANFORDERUNGEN[szenario]

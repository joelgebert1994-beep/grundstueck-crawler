"""
Offline-Regressionstests fuer die SIA-416-Flaechenkaskade
(sia416_flaechen.py). Kein Netzwerkzugriff, keine Live-Daten.

CLI: python test_sia416_flaechen.py
"""
from __future__ import annotations

import sys

from potenzial_engine.baubereich import PotenzialErgebnis
from potenzial_engine.sia416_flaechen import (
    BandbreitenWert,
    FlaechenverhaeltnisBandbreite,
    GWR_FELDER_KEINE_SIA416_FLAECHE,
    Modellannahme,
    STATUS_BESTIMMT,
    STATUS_MODELLANNAHME_BASIERT,
    STATUS_NICHT_BESTIMMBAR,
    Wohnungsmix,
    WohnungstypAnteil,
    aus_g1_ergebnis,
    berechne_sia416_aus_g1,
    berechne_sia416_kaskade,
    berechne_wohnungsanzahl,
    pruefe_keine_sia416_verwechslung,
)

FEHLER: list[str] = []


def _dummy_g1_ergebnis(geschossflaeche_m2, limitiert_durch=None, kandidaten=None) -> PotenzialErgebnis:
    """Minimaler, synthetischer G1-Ergebnis-Stub fuer die Adapter-Tests --
    nur die fuer die SIA-416-Kaskade relevanten Felder sind realistisch,
    die uebrigen sind Platzhalter (Geometrie ist hier nicht der Testgegenstand,
    siehe test_baubereich.py fuer die G1-Geometrietests selbst)."""
    return PotenzialErgebnis(
        baubereich_koordinaten=[], baubereich_vor_restriktion_m2=0.0, baubereich_m2=0.0,
        parzellenflaeche_m2=0.0, anrechenbare_landflaeche_m2=0.0,
        fussabdruck_m2=0.0, fussabdruck_limitiert_durch="geometrie", fussabdruck_kandidaten={},
        geschosszahl=None, geschosszahl_limitiert_durch=None, geschosszahl_kandidaten={},
        geschossflaeche_aus_geometrie_m2=None,
        geschossflaeche_m2=geschossflaeche_m2,
        geschossflaeche_limitiert_durch=limitiert_durch,
        geschossflaeche_kandidaten=kandidaten or {},
        kantenprotokoll=[], effektive_kanten_abstaende=[],
    )


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def test_1_ohne_modellannahme_bleibt_alles_nicht_bestimmbar() -> None:
    print("=== 1) Nur GF gegeben, keine Modellannahme -> NF/HNF/NNF/Rest bleiben nicht_bestimmbar ===")
    ergebnis = berechne_sia416_kaskade(geschossflaeche_gf_m2=1000.0)
    pruefe(ergebnis.geschossflaeche_gf.wert == 1000.0, "GF unveraendert uebernommen")
    pruefe(ergebnis.geschossflaeche_gf.status == STATUS_BESTIMMT, "GF-Status = bestimmt")
    for w in [ergebnis.nutzflaeche_nf, ergebnis.hauptnutzflaeche_hnf,
              ergebnis.nebennutzflaeche_nnf, ergebnis.uebrige_flaechen_vf_ff_kf]:
        pruefe(w.wert is None, f"{w.feld}.wert ist None (kein Raten)")
        pruefe(w.status == STATUS_NICHT_BESTIMMBAR, f"{w.feld}.status = nicht_bestimmbar")
        pruefe(bool(w.unklarheit), f"{w.feld}.unklarheit ist gesetzt und erklaert WARUM")
    print()


def test_2_modellannahme_ohne_begruendung_wird_abgelehnt() -> None:
    print("=== 2) Modellannahme ohne Begruendung -> ValueError (keine stillen Defaults) ===")
    try:
        Modellannahme(wert=0.85, begruendung="")
        pruefe(False, "haette ValueError werfen muessen")
    except ValueError:
        pruefe(True, "ValueError korrekt ausgeloest bei leerer Begruendung")
    print()


def test_3_nf_bestimmt_hnf_bleibt_nicht_bestimmbar_ohne_zweite_annahme() -> None:
    print("=== 3) NF ueber Modellannahme bestimmt, HNF ohne eigene Annahme bleibt nicht_bestimmbar ===")
    nf_annahme = Modellannahme(wert=0.85, begruendung="Erfahrungswert Mehrfamilienhaus Neubau, interne Vergleichsprojekte")
    ergebnis = berechne_sia416_kaskade(geschossflaeche_gf_m2=1000.0, nf_anteil_an_gf=nf_annahme)
    pruefe(ergebnis.nutzflaeche_nf.wert == 850.0, f"NF = 850.0 (tatsaechlich {ergebnis.nutzflaeche_nf.wert})")
    pruefe(ergebnis.nutzflaeche_nf.status == STATUS_MODELLANNAHME_BASIERT, "NF-Status = modellannahme_basiert")
    pruefe("Erfahrungswert Mehrfamilienhaus" in ergebnis.nutzflaeche_nf.herkunft, "Begruendung wird in herkunft sichtbar mitgefuehrt")
    pruefe(ergebnis.uebrige_flaechen_vf_ff_kf.wert == 150.0, f"Rest (VF+FF+KF) = GF-NF = 150.0 (tatsaechlich {ergebnis.uebrige_flaechen_vf_ff_kf.wert})")
    pruefe(ergebnis.hauptnutzflaeche_hnf.wert is None, "HNF bleibt None ohne eigene HNF/NF-Annahme")
    pruefe(ergebnis.hauptnutzflaeche_hnf.status == STATUS_NICHT_BESTIMMBAR, "HNF-Status = nicht_bestimmbar trotz bestimmter NF")
    print()


def test_4_vollstaendige_kaskade_mit_beiden_annahmen() -> None:
    print("=== 4) Vollstaendige Kaskade: beide Modellannahmen gegeben ===")
    nf_annahme = Modellannahme(wert=0.85, begruendung="Erfahrungswert MFH")
    hnf_annahme = Modellannahme(wert=0.80, begruendung="Erfahrungswert Wohnnutzung ohne Gemeinschaftsraeume", quelle="internes Benchmark 2024")
    ergebnis = berechne_sia416_kaskade(geschossflaeche_gf_m2=1000.0, nf_anteil_an_gf=nf_annahme, hnf_anteil_an_nf=hnf_annahme)
    pruefe(ergebnis.nutzflaeche_nf.wert == 850.0, "NF = 850.0")
    pruefe(ergebnis.hauptnutzflaeche_hnf.wert == 680.0, f"HNF = 850*0.8 = 680.0 (tatsaechlich {ergebnis.hauptnutzflaeche_hnf.wert})")
    pruefe(ergebnis.nebennutzflaeche_nnf.wert == 170.0, f"NNF = NF-HNF = 170.0 (tatsaechlich {ergebnis.nebennutzflaeche_nnf.wert})")
    pruefe(ergebnis.hauptnutzflaeche_hnf.status == STATUS_MODELLANNAHME_BASIERT, "HNF-Status = modellannahme_basiert")
    pruefe("internes Benchmark 2024" in ergebnis.hauptnutzflaeche_hnf.herkunft, "Quelle der Modellannahme wird mitgefuehrt")
    print()


def test_5_ungueltiger_anteil_wird_abgelehnt() -> None:
    print("=== 5) Anteil ausserhalb (0,1) -> ValueError statt stiller Fehlrechnung ===")
    try:
        berechne_sia416_kaskade(geschossflaeche_gf_m2=1000.0, nf_anteil_an_gf=Modellannahme(wert=1.4, begruendung="test"))
        pruefe(False, "haette ValueError werfen muessen")
    except ValueError:
        pruefe(True, "ValueError korrekt ausgeloest bei Anteil > 1")
    print()


def test_6_wohnungsmix_ohne_eingabe_liefert_none() -> None:
    print("=== 6) Wohnungsanzahl ohne HNF oder ohne Mix -> None (kein Durchschnittswert geraten) ===")
    pruefe(berechne_wohnungsanzahl(None, None) is None, "beide fehlen -> None")
    pruefe(berechne_wohnungsanzahl(680.0, None) is None, "HNF da, Mix fehlt -> None")
    mix = Wohnungsmix(typen=[WohnungstypAnteil("2.5-Zimmer", 1.0, 65.0)], begruendung="Testfall")
    pruefe(berechne_wohnungsanzahl(None, mix) is None, "Mix da, HNF fehlt -> None")
    print()


def test_7_wohnungsmix_anteile_muessen_1_ergeben() -> None:
    print("=== 7) Wohnungsmix-Anteile != 1.0 -> ValueError (keine stille Normalisierung) ===")
    try:
        Wohnungsmix(
            typen=[WohnungstypAnteil("2.5-Zimmer", 0.5, 65.0), WohnungstypAnteil("4.5-Zimmer", 0.3, 95.0)],
            begruendung="Testfall Summe 0.8",
        )
        pruefe(False, "haette ValueError werfen muessen")
    except ValueError:
        pruefe(True, "ValueError korrekt ausgeloest bei Summe 0.8")
    print()


def test_8_wohnungsmix_verteilung_mit_transparentem_rest() -> None:
    print("=== 8) Wohnungsmix-Verteilung: groesster Rest auf der Anzahl, kein Runden der Flaeche ===")
    mix = Wohnungsmix(
        typen=[
            WohnungstypAnteil("2.5-Zimmer", 0.6, 65.0),
            WohnungstypAnteil("4.5-Zimmer", 0.4, 95.0),
        ],
        begruendung="Marktanalyse Gemeinde X, Nachfrage nach Familienwohnungen",
    )
    ergebnis = berechne_wohnungsanzahl(680.0, mix)
    pruefe(ergebnis is not None, "Ergebnis vorhanden")
    typ_klein = next(t for t in ergebnis.typen if t.typ == "2.5-Zimmer")
    typ_gross = next(t for t in ergebnis.typen if t.typ == "4.5-Zimmer")

    # Mittlere Wohnungsgroesse im Mix: 0.6*65 + 0.4*95 = 77.0 m2
    # -> 680 / 77 = 8.8 -> 8 Wohnungen insgesamt.
    # Soll je Typ: 4.8 und 3.2 -> ganze 4 und 3, eine Einheit bleibt uebrig,
    # sie geht an den groesseren Rest (0.8 > 0.2) -> 5 und 3.
    pruefe(ergebnis.durchschnittsflaeche_pro_einheit_m2 == 77.0,
           f"mittlere Wohnungsgroesse im Mix = 77.0 (tatsaechlich {ergebnis.durchschnittsflaeche_pro_einheit_m2})")
    pruefe(ergebnis.gesamtanzahl_ganze_einheiten == 8,
           f"Gesamt ganze Einheiten = 8 (tatsaechlich {ergebnis.gesamtanzahl_ganze_einheiten})")
    pruefe(typ_klein.anzahl_ganze_einheiten == 5,
           f"2.5-Zi ganze Einheiten = 5 (tatsaechlich {typ_klein.anzahl_ganze_einheiten})")
    pruefe(typ_gross.anzahl_ganze_einheiten == 3,
           f"4.5-Zi ganze Einheiten = 3 (tatsaechlich {typ_gross.anzahl_ganze_einheiten})")

    # Der Ist-Anteil (5/8 = 62.5 %) trifft den Soll-Anteil (60 %) deutlich besser
    # als das frueher verwendete typweise Abrunden der Flaeche (das ergab 6/8 = 75 %).
    ist_anteil_klein = typ_klein.anzahl_ganze_einheiten / ergebnis.gesamtanzahl_ganze_einheiten
    pruefe(abs(ist_anteil_klein - 0.6) <= abs(0.75 - 0.6),
           f"Ist-Anteil {ist_anteil_klein:.3f} liegt naeher am Soll 0.6 als das alte Verfahren (0.75)")

    pruefe(typ_klein.hnf_sollanteil_m2 == 408.0,
           f"2.5-Zi Sollanteil = 680*0.6 = 408.0 (tatsaechlich {typ_klein.hnf_sollanteil_m2})")
    pruefe(typ_klein.belegte_hnf_m2 == 325.0,
           f"2.5-Zi belegt = 5*65 = 325.0 (tatsaechlich {typ_klein.belegte_hnf_m2})")
    pruefe(typ_gross.belegte_hnf_m2 == 285.0,
           f"4.5-Zi belegt = 3*95 = 285.0 (tatsaechlich {typ_gross.belegte_hnf_m2})")
    pruefe(typ_gross.abweichung_vom_sollanteil_m2 == 13.0,
           f"4.5-Zi liegt 13.0 m2 ueber seinem Sollanteil (tatsaechlich {typ_gross.abweichung_vom_sollanteil_m2})")

    pruefe(ergebnis.belegte_hnf_m2 == 610.0, f"belegte HNF = 610.0 (tatsaechlich {ergebnis.belegte_hnf_m2})")
    pruefe(ergebnis.gesamt_rest_hnf_m2 == 70.0, f"Restflaeche = 680-610 = 70.0 (tatsaechlich {ergebnis.gesamt_rest_hnf_m2})")
    pruefe(ergebnis.belegte_hnf_m2 <= 680.0, "die belegte Flaeche uebersteigt die vorhandene NIE")
    pruefe("Marktanalyse Gemeinde X" in ergebnis.unklarheit, "Begruendung des Mix bleibt im Ergebnis sichtbar")
    print()


def test_8b_kleines_gebaeude_liefert_trotzdem_wohnungen() -> None:
    """Regression: das frueher verwendete typweise Abrunden der Flaeche lieferte
    bei kleinen Gebaeuden UEBERALL 0 Wohnungen und wies die gesamte Flaeche als
    'Rest' aus -- rechnerisch nicht falsch, als Aussage unbrauchbar."""
    print("=== 8b) Kleines Gebaeude: die Verteilung darf nicht bei 0 Wohnungen enden ===")
    mix = Wohnungsmix(
        typen=[
            WohnungstypAnteil("2.5-Zimmer", 0.2, 62.0),
            WohnungstypAnteil("3.5-Zimmer", 0.5, 88.0),
            WohnungstypAnteil("4.5-Zimmer", 0.3, 112.0),
        ],
        begruendung="Regressionsfall kleines Mehrfamilienhaus",
    )
    ergebnis = berechne_wohnungsanzahl(154.1, mix)
    # Mittlere Groesse 0.2*62 + 0.5*88 + 0.3*112 = 90.0 -> 154.1/90 = 1.7 -> 1 Wohnung.
    pruefe(ergebnis.gesamtanzahl_ganze_einheiten == 1,
           f"eine Wohnung statt null (tatsaechlich {ergebnis.gesamtanzahl_ganze_einheiten})")
    belegt = next(t for t in ergebnis.typen if t.anzahl_ganze_einheiten > 0)
    pruefe(belegt.typ == "3.5-Zimmer", f"sie geht an den groessten Mix-Anteil (tatsaechlich {belegt.typ})")
    pruefe(ergebnis.belegte_hnf_m2 <= 154.1, "die Wohnung passt in die vorhandene Flaeche")
    pruefe(ergebnis.gesamt_rest_hnf_m2 == round(154.1 - 88.0, 1),
           f"der Rest ist die tatsaechlich freie Flaeche (tatsaechlich {ergebnis.gesamt_rest_hnf_m2})")
    print()


def test_8d_zu_grosse_wohnung_wird_ersetzt_nicht_gestrichen() -> None:
    """Regression aus dem Realfall Buchs AG: 197 m2 Wohnflaeche, Mix 20/50/30
    (62/88/112 m2). Der groesste Rest verteilt auf 3.5-Zi + 4.5-Zi = 200 m2 --
    2.9 m2 zu viel. Wer dann nur die grosse Wohnung streicht, kommt auf EINE
    Wohnung mit 109 m2 Rest, obwohl zwei hineinpassen. Die grosse Wohnung muss
    durch eine kleinere ersetzt werden, nicht ersatzlos entfallen."""
    print("=== 8d) Zu grosse Wohnung wird durch eine kleinere ersetzt, nicht gestrichen ===")
    mix = Wohnungsmix(
        typen=[
            WohnungstypAnteil("2.5-Zimmer", 0.2, 62.0),
            WohnungstypAnteil("3.5-Zimmer", 0.5, 88.0),
            WohnungstypAnteil("4.5-Zimmer", 0.3, 112.0),
        ],
        begruendung="Realfall Buchs AG",
    )
    e = berechne_wohnungsanzahl(197.0, mix)
    pruefe(e.gesamtanzahl_ganze_einheiten == 2,
           f"zwei Wohnungen statt einer (tatsaechlich {e.gesamtanzahl_ganze_einheiten})")
    pruefe(e.belegte_hnf_m2 == 150.0,
           f"62 + 88 = 150 m2 belegt (tatsaechlich {e.belegte_hnf_m2})")
    pruefe(e.belegte_hnf_m2 <= 197.0, "und passt in die vorhandene Flaeche")
    pruefe(e.gesamt_rest_hnf_m2 == 47.0,
           f"Rest 47 m2 statt 109 m2 (tatsaechlich {e.gesamt_rest_hnf_m2})")
    gross = next(t for t in e.typen if t.typ == "4.5-Zimmer")
    pruefe(gross.anzahl_ganze_einheiten == 0, "die nicht passende 4.5-Zi-Wohnung entfaellt")
    print()


def test_8c_belegung_uebersteigt_flaeche_nie() -> None:
    """Die mittlere Wohnungsgroesse ist ein Durchschnitt -- verschiebt der
    groesste Rest die Verteilung zu den grossen Typen, koennte die belegte
    Flaeche die vorhandene knapp uebersteigen. Dann wird eine Einheit
    abgezogen, statt eine Wohnung auszuweisen, die nicht hineinpasst."""
    print("=== 8c) Die belegte Flaeche uebersteigt die vorhandene nie ===")
    mix = Wohnungsmix(
        typen=[
            WohnungstypAnteil("1.5-Zimmer", 0.5, 40.0),
            WohnungstypAnteil("5.5-Zimmer", 0.5, 160.0),
        ],
        begruendung="Extremer Mix zur Pruefung der Flaechendeckung",
    )
    for flaeche in (100.0, 199.0, 200.0, 250.0, 399.0, 1000.0):
        ergebnis = berechne_wohnungsanzahl(flaeche, mix)
        pruefe(
            ergebnis.belegte_hnf_m2 <= flaeche + 1e-9,
            f"{flaeche:.0f} m2 -> {ergebnis.gesamtanzahl_ganze_einheiten} Wohnungen, "
            f"belegt {ergebnis.belegte_hnf_m2} m2 (passt)",
        )
    print()


def test_9_aus_g1_ergebnis_erfolgreich() -> None:
    print("=== 9) aus_g1_ergebnis: G1 hat eine Geschossflaeche bestimmt ===")
    g1 = _dummy_g1_ergebnis(600.0, limitiert_durch="ausnuetzung_az", kandidaten={"ausnuetzung_az": 600.0, "fussabdruck_x_geschosse": 720.0})
    gf = aus_g1_ergebnis(g1)
    pruefe(gf.wert == 600.0, f"GF uebernommen (tatsaechlich {gf.wert})")
    pruefe(gf.status == STATUS_BESTIMMT, "GF-Status = bestimmt")
    pruefe("ausnuetzung_az" in gf.herkunft, "limitierender Parameter wird in herkunft sichtbar")
    print()


def test_10_aus_g1_ergebnis_nicht_bestimmbar() -> None:
    print("=== 10) aus_g1_ergebnis: G1 konnte keine Geschossflaeche bestimmen ===")
    g1 = _dummy_g1_ergebnis(None)
    gf = aus_g1_ergebnis(g1)
    pruefe(gf.wert is None, "GF bleibt None statt geraten")
    pruefe(gf.status == STATUS_NICHT_BESTIMMBAR, "GF-Status = nicht_bestimmbar")
    pruefe(bool(gf.unklarheit), "Unklarheit erklaert, dass G1 selbst keinen Kandidaten fand")
    print()


def test_11_berechne_sia416_aus_g1_end_zu_end() -> None:
    print("=== 11) berechne_sia416_aus_g1: End-zu-End mit erfolgreichem G1-Ergebnis ===")
    g1 = _dummy_g1_ergebnis(1000.0, limitiert_durch="baumassenziffer")
    nf_annahme = Modellannahme(wert=0.85, begruendung="Erfahrungswert MFH")
    ergebnis = berechne_sia416_aus_g1(g1, nf_anteil_an_gf=nf_annahme)
    pruefe(ergebnis is not None, "Ergebnis wird geliefert")
    pruefe(ergebnis.geschossflaeche_gf.wert == 1000.0, "GF korrekt aus G1 uebernommen")
    pruefe("baumassenziffer" in ergebnis.geschossflaeche_gf.herkunft, "G1-Herkunft (limitierender Parameter) im Endergebnis sichtbar")
    pruefe(ergebnis.nutzflaeche_nf.wert == 850.0, f"NF korrekt weiterberechnet (tatsaechlich {ergebnis.nutzflaeche_nf.wert})")
    print()


def test_12_berechne_sia416_aus_g1_ohne_g1_ergebnis() -> None:
    print("=== 12) berechne_sia416_aus_g1: G1 liefert keine GF -> None statt Kaskade auf Fantasiewert ===")
    g1 = _dummy_g1_ergebnis(None)
    ergebnis = berechne_sia416_aus_g1(g1, nf_anteil_an_gf=Modellannahme(wert=0.85, begruendung="x"))
    pruefe(ergebnis is None, "Kaskade wird gar nicht erst ausgefuehrt")
    print()


def _dummy_bandbreiten_wert(wert: float, entwicklungsszenario: str = "ersatzneubau") -> BandbreitenWert:
    return BandbreitenWert(
        wert=wert, einheit="Verhaeltnis", quelle="Testquelle", begruendung="Testbegruendung",
        gueltigkeitsbereich="MFH Regelgeschoss", gebaeudetyp="MFH", entwicklungsszenario=entwicklungsszenario,
    )


def test_13_bandbreitenwert_erzwingt_vollstaendige_metadaten() -> None:
    print("=== 13) BandbreitenWert: alle Metadatenfelder sind Pflicht, Wert muss in (0,1) liegen ===")
    try:
        BandbreitenWert(wert=0.8, einheit="", quelle="", begruendung="x", gueltigkeitsbereich="x", gebaeudetyp="MFH", entwicklungsszenario="ersatzneubau")
        pruefe(False, "haette ValueError werfen muessen (leere quelle)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei leerer quelle")
    try:
        _dummy_bandbreiten_wert(1.5)
        pruefe(False, "haette ValueError werfen muessen (wert > 1)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei wert ausserhalb (0,1)")
    print()


def test_14_flaechenverhaeltnis_bandbreite_konsistenzpruefung() -> None:
    print("=== 14) FlaechenverhaeltnisBandbreite: keine automatische Sortierung/Normalisierung ===")
    try:
        FlaechenverhaeltnisBandbreite(
            konservativ=_dummy_bandbreiten_wert(0.9), mittel=_dummy_bandbreiten_wert(0.8), optimiert=_dummy_bandbreiten_wert(0.7),
        )
        pruefe(False, "haette ValueError werfen muessen (konservativ > optimiert)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei unsortierter Bandbreite -- keine stille Korrektur")

    try:
        FlaechenverhaeltnisBandbreite(
            konservativ=_dummy_bandbreiten_wert(0.7, "ersatzneubau"),
            mittel=_dummy_bandbreiten_wert(0.8, "aufstockung_dachausbau"),
            optimiert=_dummy_bandbreiten_wert(0.9, "ersatzneubau"),
        )
        pruefe(False, "haette ValueError werfen muessen (unterschiedliche Szenarien gemischt)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei gemischten Entwicklungsszenarien innerhalb einer Bandbreite")

    gueltig = FlaechenverhaeltnisBandbreite(
        konservativ=_dummy_bandbreiten_wert(0.7), mittel=_dummy_bandbreiten_wert(0.8), optimiert=_dummy_bandbreiten_wert(0.9),
    )
    pruefe(gueltig.mittel.wert == 0.8, "konsistent geordnete Bandbreite wird akzeptiert")
    print()


def test_15_gwr_sperrregel() -> None:
    print("=== 15) GWR-Sperrregel: bekannte Falschverwendungen werden erkannt ===")
    pruefe("gwr.energiebezugsflaeche_m2" in GWR_FELDER_KEINE_SIA416_FLAECHE, "Energiebezugsflaeche ist gelistet")
    warnung = pruefe_keine_sia416_verwechslung("gwr.energiebezugsflaeche_m2")
    pruefe(warnung is not None and "SIA-380/1" in warnung, "Warnung nennt den korrekten Normbezug (SIA 380/1, nicht SIA 416)")
    pruefe(pruefe_keine_sia416_verwechslung("gwr.grundflaeche_m2") is not None, "Grundflaeche (Fussabdruck) ist gelistet")
    pruefe(pruefe_keine_sia416_verwechslung("gwr.gebaeudevolumen_m3") is not None, "Gebaeudevolumen ist gelistet")
    pruefe(pruefe_keine_sia416_verwechslung("kataster.flaeche_m2") is not None, "Parzellenflaeche ist gelistet")
    pruefe(pruefe_keine_sia416_verwechslung("gwr.baujahr") is None, "unkritisches Feld (baujahr) liefert korrekt keine Warnung")
    print()


def main() -> None:
    test_1_ohne_modellannahme_bleibt_alles_nicht_bestimmbar()
    test_2_modellannahme_ohne_begruendung_wird_abgelehnt()
    test_3_nf_bestimmt_hnf_bleibt_nicht_bestimmbar_ohne_zweite_annahme()
    test_4_vollstaendige_kaskade_mit_beiden_annahmen()
    test_5_ungueltiger_anteil_wird_abgelehnt()
    test_6_wohnungsmix_ohne_eingabe_liefert_none()
    test_7_wohnungsmix_anteile_muessen_1_ergeben()
    test_8_wohnungsmix_verteilung_mit_transparentem_rest()
    test_8b_kleines_gebaeude_liefert_trotzdem_wohnungen()
    test_8c_belegung_uebersteigt_flaeche_nie()
    test_8d_zu_grosse_wohnung_wird_ersetzt_nicht_gestrichen()
    test_9_aus_g1_ergebnis_erfolgreich()
    test_10_aus_g1_ergebnis_nicht_bestimmbar()
    test_11_berechne_sia416_aus_g1_end_zu_end()
    test_12_berechne_sia416_aus_g1_ohne_g1_ergebnis()
    test_13_bandbreitenwert_erzwingt_vollstaendige_metadaten()
    test_14_flaechenverhaeltnis_bandbreite_konsistenzpruefung()
    test_15_gwr_sperrregel()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE SIA-416-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

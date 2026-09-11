"""
Offline-Regressionstests fuer die Referenzprojekt-Datenstruktur
(referenzprojekte.py). Reine Schema-/Validierungspruefung -- es gibt
keine Berechnungslogik zu testen, das Modul ist bewusst nur
Design-Vorbereitung ohne seed-Daten.

CLI: python test_referenzprojekte.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from referenzprojekte import (
    DATENQUALITAET_GESCHAETZT,
    DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT,
    GEBAEUDETYP_MFH,
    REFERENZPROJEKTE,
    VERHAELTNIS_HNF_NF,
    VERHAELTNIS_KF_GF,
    VERHAELTNIS_NF_GF,
    Referenzprojekt,
    lade_referenzprojekte_aus_json,
    leite_bandbreite_ab,
    referenzprojekt_aus_dict,
    referenzprojekt_zu_dict,
    speichere_referenzprojekte_als_json,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def test_1_registry_ist_leer() -> None:
    print("=== 1) REFERENZPROJEKTE ist leer -- keine erfundenen/vorbelegten Projekte ===")
    pruefe(REFERENZPROJEKTE == [], "Registry enthaelt keine seed-Eintraege")
    print()


def test_2_pflichtfelder_werden_durchgesetzt() -> None:
    print("=== 2) Pflichtfelder (Identifikation/Quelle) sind erzwungen, Flaechenwerte optional ===")
    try:
        Referenzprojekt(
            projekt_bezeichnung="", gebaeudetyp="MFH", gemeinde="Musterhausen",
            kanton="ZH", quelle_bezeichnung="Bauabrechnung",
        )
        pruefe(False, "haette ValueError werfen muessen (leere projekt_bezeichnung)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei leerer projekt_bezeichnung")

    # Ein Projekt OHNE jegliche Flaechenangabe ist gueltig -- ein
    # unvollstaendiger, aber transparent als solcher erkennbarer
    # Datensatz ist besser als gar keiner.
    minimal = Referenzprojekt(
        projekt_bezeichnung="Testprojekt Minimal", gebaeudetyp="MFH",
        gemeinde="Musterhausen", kanton="ZH", quelle_bezeichnung="Bauabrechnung",
    )
    pruefe(minimal.geschossflaeche_gf_m2 is None, "GF bleibt None, wenn nicht angegeben (kein Default)")
    pruefe(minimal.hauptnutzflaeche_hnf_m2 is None, "HNF bleibt None, wenn nicht angegeben (kein Default)")
    print()


def test_3_vollstaendiges_projekt_haelt_alle_felder() -> None:
    print("=== 3) Vollstaendig befuelltes Referenzprojekt behaelt alle Werte verlustfrei ===")
    projekt = Referenzprojekt(
        projekt_bezeichnung="Testprojekt Vollstaendig", gebaeudetyp="MFH",
        gemeinde="Musterhausen", kanton="ZH", quelle_bezeichnung="Bauabrechnung",
        baujahr=2022, geschossflaeche_gf_m2=1200.0, konstruktionsflaeche_kf_m2=150.0,
        nutzflaeche_nf_m2=1000.0, hauptnutzflaeche_hnf_m2=820.0,
        erschliessungstyp="Zweispaenner", bauweise="Massivbau", anzahl_geschosse=5,
        unterirdische_geschosse=1, hat_lift=True, energiestandard="Minergie",
        quelle_referenz="Plan-Nr. 2022-118", uebertragbarkeits_hinweis="Regelgeschoss, keine Attika enthalten",
    )
    pruefe(projekt.geschossflaeche_gf_m2 == 1200.0, "GF korrekt gesetzt")
    pruefe(projekt.hauptnutzflaeche_hnf_m2 == 820.0, "HNF korrekt gesetzt")
    pruefe(projekt.erschliessungstyp == "Zweispaenner", "Erschliessungstyp korrekt gesetzt")
    pruefe(projekt.uebertragbarkeits_hinweis is not None, "Uebertragbarkeitshinweis kann dokumentiert werden")
    print()


def test_4_abgeleitete_verhaeltnisse_nur_bei_vollstaendigen_originalwerten() -> None:
    print("=== 4) NF/GF, HNF/NF, HNF/GF: nur berechnet, wenn beide Originalwerte vorhanden ===")
    nur_gf = Referenzprojekt(
        projekt_bezeichnung="Nur GF", gebaeudetyp="MFH", gemeinde="Musterhausen",
        kanton="ZH", quelle_bezeichnung="Bauabrechnung", geschossflaeche_gf_m2=1000.0,
    )
    pruefe(nur_gf.nf_gf_quote is None, "nf_gf_quote ist None ohne NF (kein Raten)")
    pruefe(nur_gf.hnf_nf_quote is None, "hnf_nf_quote ist None ohne NF/HNF")
    pruefe(nur_gf.hnf_gf_quote is None, "hnf_gf_quote ist None ohne HNF")

    vollstaendig = Referenzprojekt(
        projekt_bezeichnung="Vollstaendig", gebaeudetyp="MFH", gemeinde="Musterhausen",
        kanton="ZH", quelle_bezeichnung="Bauabrechnung",
        geschossflaeche_gf_m2=1000.0, nutzflaeche_nf_m2=850.0, hauptnutzflaeche_hnf_m2=680.0,
    )
    pruefe(vollstaendig.nf_gf_quote == 0.85, f"nf_gf_quote = 850/1000 = 0.85 (tatsaechlich {vollstaendig.nf_gf_quote})")
    pruefe(vollstaendig.hnf_nf_quote == 0.8, f"hnf_nf_quote = 680/850 = 0.8 (tatsaechlich {vollstaendig.hnf_nf_quote})")
    pruefe(vollstaendig.hnf_gf_quote == 0.68, f"hnf_gf_quote = 680/1000 = 0.68 (tatsaechlich {vollstaendig.hnf_gf_quote})")
    print()


def test_5_datenqualitaet_wird_validiert() -> None:
    print("=== 5) datenqualitaet: nur definierte Werte zulaessig, None bleibt erlaubt ===")
    try:
        Referenzprojekt(
            projekt_bezeichnung="x", gebaeudetyp="MFH", gemeinde="Musterhausen",
            kanton="ZH", quelle_bezeichnung="Bauabrechnung", datenqualitaet="ziemlich_sicher",
        )
        pruefe(False, "haette ValueError werfen muessen (unbekannter datenqualitaet-Wert)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei unbekanntem datenqualitaet-Wert")

    ok = Referenzprojekt(
        projekt_bezeichnung="x", gebaeudetyp="MFH", gemeinde="Musterhausen",
        kanton="ZH", quelle_bezeichnung="Bauabrechnung", datenqualitaet=DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT,
    )
    pruefe(ok.datenqualitaet == DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT, "gueltiger Wert wird uebernommen")

    ohne_angabe = Referenzprojekt(
        projekt_bezeichnung="x", gebaeudetyp="MFH", gemeinde="Musterhausen",
        kanton="ZH", quelle_bezeichnung="Bauabrechnung",
    )
    pruefe(ohne_angabe.datenqualitaet is None, "None bleibt erlaubt (keine Pflichtangabe)")
    print()


def test_6_json_import_export_rundreise() -> None:
    print("=== 6) JSON-Export/Import: verlustfreie Rundreise, unbekannte Felder werden erkannt ===")
    projekt = Referenzprojekt(
        projekt_bezeichnung="Rundreise-Test", gebaeudetyp="MFH", gemeinde="Musterhausen",
        kanton="ZH", quelle_bezeichnung="Bauabrechnung", baujahr=2023,
        geschossflaeche_gf_m2=1200.0, nutzflaeche_nf_m2=1000.0, hauptnutzflaeche_hnf_m2=800.0,
        erschliessungstyp="Zweispaenner", bauweise="Massivbau", anzahl_geschosse=5,
        datenqualitaet=DATENQUALITAET_GESCHAETZT, uebertragbarkeits_hinweis="Testfall",
    )
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / "referenzprojekte.json"
        speichere_referenzprojekte_als_json([projekt], pfad)
        geladen = lade_referenzprojekte_aus_json(pfad)

    pruefe(len(geladen) == 1, "genau 1 Projekt zurueckgeladen")
    pruefe(geladen[0] == projekt, "Roundtrip ist verlustfrei (dataclass-Gleichheit)")
    pruefe(geladen[0].nf_gf_quote == projekt.nf_gf_quote, "abgeleitete Eigenschaften funktionieren auch nach dem Reload")

    try:
        referenzprojekt_aus_dict({**referenzprojekt_zu_dict(projekt), "unbekanntes_feld": 123})
        pruefe(False, "haette ValueError werfen muessen (unbekanntes Feld)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei unbekanntem Feld im importierten Datensatz (kein stilles Ignorieren)")
    print()


def _projekt(name, gf=None, kf=None, nf=None, hnf=None, szenario="ersatzneubau", datenqualitaet=DATENQUALITAET_VOLLSTAENDIG_VERIFIZIERT):
    return Referenzprojekt(
        projekt_bezeichnung=name, gebaeudetyp=GEBAEUDETYP_MFH, gemeinde="Musterhausen", kanton="ZH",
        quelle_bezeichnung="Bauabrechnung", entwicklungsszenario=szenario, datenqualitaet=datenqualitaet,
        geschossflaeche_gf_m2=gf, konstruktionsflaeche_kf_m2=kf, nutzflaeche_nf_m2=nf, hauptnutzflaeche_hnf_m2=hnf,
    )


def test_7_gebaeudetyp_und_entwicklungsszenario_werden_validiert() -> None:
    print("=== 7) gebaeudetyp und entwicklungsszenario: nur definierte Werte, kein freier Text ===")
    try:
        Referenzprojekt(projekt_bezeichnung="x", gebaeudetyp="Mehrfamilienhaus", gemeinde="m", kanton="ZH", quelle_bezeichnung="q")
        pruefe(False, "haette ValueError werfen muessen (freier Text statt 'MFH')")
    except ValueError:
        pruefe(True, "ValueError korrekt bei nicht-kanonischem gebaeudetyp")

    try:
        Referenzprojekt(projekt_bezeichnung="x", gebaeudetyp=GEBAEUDETYP_MFH, gemeinde="m", kanton="ZH",
                         quelle_bezeichnung="q", entwicklungsszenario="komplettabriss")
        pruefe(False, "haette ValueError werfen muessen (unbekanntes Szenario)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei unbekanntem entwicklungsszenario")

    ok = Referenzprojekt(projekt_bezeichnung="x", gebaeudetyp=GEBAEUDETYP_MFH, gemeinde="m", kanton="ZH",
                          quelle_bezeichnung="q", entwicklungsszenario="aufstockung_dachausbau")
    pruefe(ok.entwicklungsszenario == "aufstockung_dachausbau", "gueltiges Szenariotyp-Value wird uebernommen")
    print()


def test_8_kf_gf_quote_und_verfuegbare_verhaeltnisse() -> None:
    print("=== 8) kf_gf_quote und verfuegbare_verhaeltnisse-Uebersicht ===")
    p = _projekt("KF-Test", gf=1000.0, kf=150.0, nf=850.0, hnf=680.0)
    pruefe(p.kf_gf_quote == 0.15, f"kf_gf_quote = 150/1000 = 0.15 (tatsaechlich {p.kf_gf_quote})")
    uebersicht = p.verfuegbare_verhaeltnisse
    pruefe(uebersicht[VERHAELTNIS_KF_GF] == 0.15, "Uebersicht enthaelt kf_gf")
    pruefe(uebersicht[VERHAELTNIS_NF_GF] == 0.85, "Uebersicht enthaelt nf_gf")

    p_ohne_kf = _projekt("Ohne KF", gf=1000.0, nf=850.0, hnf=680.0)
    pruefe(p_ohne_kf.verfuegbare_verhaeltnisse[VERHAELTNIS_KF_GF] is None, "kf_gf fehlt korrekt in der Uebersicht, wenn KF unbekannt")
    print()


def test_9_ist_belastbare_referenz() -> None:
    print("=== 9) ist_belastbare_referenz: GF+NF+HNF UND keine Schaetzung ===")
    vollstaendig = _projekt("Vollstaendig", gf=1000.0, nf=850.0, hnf=680.0)
    pruefe(vollstaendig.ist_belastbare_referenz is True, "GF+NF+HNF vorhanden, nicht geschaetzt -> belastbar")

    nur_gf_nf = _projekt("Nur GF+NF", gf=1000.0, nf=850.0)
    pruefe(nur_gf_nf.ist_belastbare_referenz is False, "HNF fehlt -> nicht belastbar, obwohl NF/GF berechenbar waere")

    geschaetzt = _projekt("Geschaetzt", gf=1000.0, nf=850.0, hnf=680.0, datenqualitaet=DATENQUALITAET_GESCHAETZT)
    pruefe(geschaetzt.ist_belastbare_referenz is False, "vollstaendige, aber geschaetzte Daten sind NICHT belastbar (Ansatz B, nicht A)")
    print()


def test_10_leite_bandbreite_ab_zu_wenig_projekte() -> None:
    print("=== 10) leite_bandbreite_ab: zu wenig passende Projekte -> ValueError statt Fake-Bandbreite ===")
    ein_projekt = [_projekt("Solo", gf=1000.0, nf=850.0, hnf=680.0)]
    try:
        leite_bandbreite_ab(ein_projekt, VERHAELTNIS_NF_GF, GEBAEUDETYP_MFH, "ersatzneubau")
        pruefe(False, "haette ValueError werfen muessen (nur 1 Projekt, mindestens 2 noetig)")
    except ValueError:
        pruefe(True, "ValueError korrekt bei nur 1 passendem Projekt")
    print()


def test_11_leite_bandbreite_ab_filtert_korrekt() -> None:
    print("=== 11) leite_bandbreite_ab: filtert nach Belastbarkeit, Typ, Szenario UND Verhaeltnis-Verfuegbarkeit ===")
    projekte = [
        _projekt("A", gf=1000.0, kf=150.0, nf=800.0, hnf=640.0),   # nf_gf=0.80
        _projekt("B", gf=1000.0, kf=140.0, nf=850.0, hnf=680.0),   # nf_gf=0.85
        _projekt("C", gf=1000.0, kf=130.0, nf=900.0, hnf=720.0),   # nf_gf=0.90
        _projekt("D_geschaetzt", gf=1000.0, nf=950.0, hnf=760.0, datenqualitaet=DATENQUALITAET_GESCHAETZT),  # ausgeschlossen
        _projekt("E_anderes_szenario", gf=1000.0, nf=999.0, hnf=999.0, szenario="bestand"),  # ausgeschlossen
        _projekt("F_kein_szenario", gf=1000.0, kf=100.0, nf=100.0, hnf=100.0, szenario=None),  # ausgeschlossen
    ]
    bandbreite = leite_bandbreite_ab(projekte, VERHAELTNIS_NF_GF, GEBAEUDETYP_MFH, "ersatzneubau")
    pruefe(bandbreite.konservativ.wert == 0.8, f"konservativ = min = 0.8 (tatsaechlich {bandbreite.konservativ.wert})")
    pruefe(bandbreite.optimiert.wert == 0.9, f"optimiert = max = 0.9 (tatsaechlich {bandbreite.optimiert.wert})")
    pruefe(bandbreite.mittel.wert == 0.85, f"mittel = median_low = 0.85, aus Projekt B (tatsaechlich {bandbreite.mittel.wert})")
    pruefe("A" in bandbreite.konservativ.quelle, "konservativ-Quelle nennt das konkrete Projekt A")
    pruefe("B" in bandbreite.mittel.quelle, "mittel-Quelle nennt das konkrete Projekt B")
    pruefe("D_geschaetzt" not in bandbreite.konservativ.quelle and "D_geschaetzt" not in bandbreite.mittel.quelle and "D_geschaetzt" not in bandbreite.optimiert.quelle,
           "geschaetztes Projekt D wird nirgends verwendet")
    pruefe(bandbreite.konservativ.gebaeudetyp == GEBAEUDETYP_MFH, "Gebaeudetyp wird als Gueltigkeitsbereich mitgefuehrt")
    pruefe(bandbreite.konservativ.entwicklungsszenario == "ersatzneubau", "Entwicklungsszenario wird als Gueltigkeitsbereich mitgefuehrt")

    # KF/GF mit nur 2 der 3 belastbaren MFH/ersatzneubau-Projekten (A, B -- C hat kf=130 auch vorhanden,
    # also eigentlich alle 3 -- pruefen wir stattdessen explizit die 2-Projekte-Kollaps-Regel separat unten).
    kf_bandbreite = leite_bandbreite_ab(projekte, VERHAELTNIS_KF_GF, GEBAEUDETYP_MFH, "ersatzneubau")
    pruefe(kf_bandbreite.konservativ.wert == 0.13, f"kf_gf konservativ = 0.13 (Projekt C, tatsaechlich {kf_bandbreite.konservativ.wert})")
    print()


def test_12_leite_bandbreite_ab_zwei_projekte_kollabiert_mittel_mit_konservativ() -> None:
    print("=== 12) leite_bandbreite_ab mit genau 2 Projekten: mittel faellt ehrlich mit konservativ zusammen ===")
    projekte = [
        _projekt("X", gf=1000.0, nf=800.0, hnf=640.0),
        _projekt("Y", gf=1000.0, nf=900.0, hnf=720.0),
    ]
    bandbreite = leite_bandbreite_ab(projekte, VERHAELTNIS_NF_GF, GEBAEUDETYP_MFH, "ersatzneubau")
    pruefe(bandbreite.konservativ.wert == 0.8, "konservativ = 0.8")
    pruefe(bandbreite.mittel.wert == 0.8, "mittel faellt mit konservativ zusammen (median_low bei 2 Werten) -- kein erfundener Mittelwert")
    pruefe(bandbreite.optimiert.wert == 0.9, "optimiert = 0.9")
    print()


def main() -> None:
    test_1_registry_ist_leer()
    test_2_pflichtfelder_werden_durchgesetzt()
    test_3_vollstaendiges_projekt_haelt_alle_felder()
    test_4_abgeleitete_verhaeltnisse_nur_bei_vollstaendigen_originalwerten()
    test_5_datenqualitaet_wird_validiert()
    test_6_json_import_export_rundreise()
    test_7_gebaeudetyp_und_entwicklungsszenario_werden_validiert()
    test_8_kf_gf_quote_und_verfuegbare_verhaeltnisse()
    test_9_ist_belastbare_referenz()
    test_10_leite_bandbreite_ab_zu_wenig_projekte()
    test_11_leite_bandbreite_ab_filtert_korrekt()
    test_12_leite_bandbreite_ab_zwei_projekte_kollabiert_mittel_mit_konservativ()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE REFERENZPROJEKTE-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

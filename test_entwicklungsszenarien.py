"""
Offline-Regressionstests fuer die Entwicklungsszenarien-Taxonomie
(entwicklungsszenarien.py). Reine Struktur-/Vollstaendigkeitspruefung --
es gibt keine Berechnungslogik zu testen, das Modul ist bewusst nur
Design-Vorbereitung.

CLI: python test_entwicklungsszenarien.py
"""
from __future__ import annotations

import sys

from entwicklungsszenarien import SZENARIO_ANFORDERUNGEN, Szenariotyp, anforderungen_fuer

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def test_1_alle_fuenf_geforderten_szenarien_vorhanden() -> None:
    print("=== 1) Alle 5 vom Auftrag geforderten Szenarien sind als Enum-Werte vorhanden ===")
    erwartet = {
        "bestand", "anbau_erweiterung", "aufstockung_dachausbau",
        "ersatzneubau", "kombination_bestand_neubau",
    }
    tatsaechlich = {s.value for s in Szenariotyp}
    pruefe(tatsaechlich == erwartet, f"Enum-Werte stimmen exakt ueberein (tatsaechlich {sorted(tatsaechlich)})")
    print()


def test_2_jedes_szenario_hat_eine_anforderung() -> None:
    print("=== 2) Jeder Enum-Wert hat genau einen SZENARIO_ANFORDERUNGEN-Eintrag, keine Luecke ===")
    for s in Szenariotyp:
        pruefe(s in SZENARIO_ANFORDERUNGEN, f"{s.value} hat einen Eintrag")
    pruefe(len(SZENARIO_ANFORDERUNGEN) == len(list(Szenariotyp)), "keine ueberzaehligen Eintraege")
    print()


def test_3_jede_anforderung_ist_vollstaendig_dokumentiert() -> None:
    print("=== 3) Jede Anforderung hat nicht-leere Zusatzeingaben, Beschreibung und Status-Notiz ===")
    for szenario, anforderung in SZENARIO_ANFORDERUNGEN.items():
        pruefe(len(anforderung.benoetigte_zusatzeingaben) > 0, f"{szenario.value}: mindestens 1 Zusatzeingabe benannt")
        pruefe(bool(anforderung.beschreibung.strip()), f"{szenario.value}: Beschreibung vorhanden")
        pruefe(bool(anforderung.heute_bereits_abgedeckt_durch.strip()), f"{szenario.value}: Status quo dokumentiert")
        pruefe(bool(anforderung.sia416_besonderheit.strip()), f"{szenario.value}: SIA-416-Besonderheit dokumentiert")
        pruefe(len(anforderung.benoetigte_flaechendaten) > 0, f"{szenario.value}: mindestens 1 Flaechen-/Geometriedatum benannt")
        pruefe(anforderung.szenario == szenario, f"{szenario.value}: Anforderung referenziert das richtige Szenario")
    print()


def test_4_anforderungen_fuer_liefert_korrekten_eintrag() -> None:
    print("=== 4) anforderungen_fuer() liefert den korrekten Eintrag ===")
    a = anforderungen_fuer(Szenariotyp.AUFSTOCKUNG_DACHAUSBAU)
    pruefe(a.szenario == Szenariotyp.AUFSTOCKUNG_DACHAUSBAU, "korrektes Szenario zurueckgegeben")
    pruefe("statik_tragreserve_bestaetigt" in a.benoetigte_zusatzeingaben, "erwartete Zusatzeingabe enthalten")
    print()


def main() -> None:
    test_1_alle_fuenf_geforderten_szenarien_vorhanden()
    test_2_jedes_szenario_hat_eine_anforderung()
    test_3_jede_anforderung_ist_vollstaendig_dokumentiert()
    test_4_anforderungen_fuer_liefert_korrekten_eintrag()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE ENTWICKLUNGSSZENARIEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

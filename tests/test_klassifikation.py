"""
Regressionstests fuer Modul 1b (Nutzungsklassifikation) und deren Verdrahtung
in Modul 1 / Modul 3.

Laueft OHNE API-Key (Gemini/Claude) -- die Klassifikation braucht nur
oeffentliche Geodienste (geodienste.ch, ZH-WFS, geo.admin.ch, kantonale
OEREB-Webservices). Wo eine Zonenzuordnung noetig ist, wird ein synthetisches
Modul-2-Ergebnis verwendet statt eines echten LLM-Calls.

Faelle:
  - Baden (AG): Kernzone 5 als Grundnutzung, gleichzeitig zwei rechtsgueltige
    Sondernutzungsplaene (Kategorie 61) -- muss blockieren.
  - Zuerich: Kernzone als Grundnutzung, gleichzeitig ein rechtsgueltiger
    Gestaltungsplan -- muss ebenfalls blockieren (der zuvor als Bandbreite
    ausgegebene Residualwert 1.49-4.23 Mio. CHF ist damit nicht mehr gueltig).
  - Buchs AG: Gartenstadtzone ohne Sondernutzungsplan -- muss normal
    durchrechnen, mit basiszone_quelle == "nutzungsklassifikation".
  - Rorschach (SG): OEREB_CANTON_SERVICES fehlte lange ein SG-Eintrag (siehe
    modul1_geodata.py, 2026-09-03 ergaenzt, live verifiziert) -- prueft, dass
    der SG-Webservice tatsaechlich erreichbar ist UND rechtskraeftige
    Rechtsvorschriften liefert. Traegt ausserdem real einen
    Sondernutzungsplan ("BauG_Sondernutzungsplan") -- muss wie Baden/Zuerich
    blockieren.

CLI: python test_klassifikation.py
"""

from __future__ import annotations

import sys

from potenzial_engine.modul1_geodata import run_modul1
from potenzial_engine.modul3_financial import ermittle_zonenzuordnung, run_from_modul_results

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def test_baden() -> None:
    print("=== Baden (AG): Kernzone 5 + 2 Sondernutzungsplaene -> muss blockieren ===")
    r1 = run_modul1("Gartenstrasse 5, 5400 Baden")
    k = r1["nutzungsklassifikation"]

    pruefe(k["gefunden"] is True, "Nutzungsklassifikation gefunden")
    pruefe(k["quelle"] == "geodienste", "Quelle ist geodienste.ch")
    pruefe(k["basiszone_status"] == "eindeutig", "Basiszone eindeutig bestimmt")
    pruefe(
        k["basiszone"] is not None and "Kernzone" in k["basiszone"]["typ_kommunal_bezeichnung"],
        f"Grundnutzung ist Kernzone (tatsaechlich: {k['basiszone']['typ_kommunal_bezeichnung'] if k['basiszone'] else None})",
    )
    snp_titel = [s["typ_kommunal_bezeichnung"] for s in k["sondernutzungsplaene_massgebend"]]
    pruefe(any("Gestaltungsplan" in t for t in snp_titel), f"Gestaltungsplan als SNP erkannt ({snp_titel})")
    pruefe(
        not any(t == k["basiszone"]["typ_kommunal_bezeichnung"] for t in snp_titel),
        "Grundnutzung selbst taucht nicht in der SNP-Liste auf",
    )

    dummy_modul2 = {"erkannte_zonen": [], "sonderregelungen": []}
    r3 = run_from_modul_results(r1, dummy_modul2, verkaufspreis_chf_pro_m2=13000)
    pruefe(r3.get("status") == "sondernutzungsplan_massgebend", f"Modul 3 blockiert (status={r3.get('status')})")
    pruefe("szenarien" not in r3, "Keine Szenarien-Matrix im blockierten Ergebnis -- keine scheinpraezise Zahl")
    print()


def test_zuerich() -> None:
    print("=== Zuerich: Kernzone + Gestaltungsplan -> muss blockieren ===")
    r1 = run_modul1("Bahnhofstrasse 1, 8001 Zuerich")
    k = r1["nutzungsklassifikation"]

    pruefe(k["gefunden"] is True, "Nutzungsklassifikation gefunden")
    pruefe(k["quelle"] == "zh_wfs", "Quelle ist der ZH-Sonderweg (zh_wfs)")
    pruefe(k["basiszone_status"] == "eindeutig", "Basiszone eindeutig bestimmt")
    pruefe(
        k["basiszone"] is not None and "Kernzone" in k["basiszone"]["typ_kommunal_bezeichnung"],
        f"Grundnutzung ist Kernzone (tatsaechlich: {k['basiszone']['typ_kommunal_bezeichnung'] if k['basiszone'] else None})",
    )
    snp_titel = [s["typ_kommunal_bezeichnung"] for s in k["sondernutzungsplaene_massgebend"]]
    pruefe(any("Gestaltungsplan" in t for t in snp_titel), f"Gestaltungsplan als SNP erkannt ({snp_titel})")
    pruefe(
        not any("Kernzonenplan" in t for t in snp_titel),
        f"Kernzonenplan (Kategorie 69, Ergaenzung) wird NICHT als SNP gefuehrt ({snp_titel})",
    )

    dummy_modul2 = {"erkannte_zonen": [], "sonderregelungen": []}
    r3 = run_from_modul_results(r1, dummy_modul2, verkaufspreis_chf_pro_m2=13000)
    pruefe(r3.get("status") == "sondernutzungsplan_massgebend", f"Modul 3 blockiert (status={r3.get('status')})")
    pruefe(
        "szenarien" not in r3,
        "Keine Szenarien-Matrix -- die zuvor ausgegebene Bandbreite (1.49-4.23 Mio. CHF) gilt als zurueckgezogen",
    )
    print()


def test_normalfall_ohne_snp() -> None:
    print("=== Buchs AG: Gartenstadtzone ohne SNP -> muss normal durchrechnen ===")
    r1 = run_modul1("Rosenweg 4, 5033 Buchs AG")
    k = r1["nutzungsklassifikation"]

    pruefe(k["gefunden"] is True, "Nutzungsklassifikation gefunden")
    pruefe(k["basiszone_status"] == "eindeutig", "Basiszone eindeutig bestimmt")
    pruefe(len(k["sondernutzungsplaene_massgebend"]) == 0, "Kein Sondernutzungsplan vorhanden")

    modul2_synthetic = {
        "erkannte_zonen": [{
            "zonenbezeichnung": "Gartenstadtzone", "ausnuetzungsziffer_az": 0.35,
            "anrechenbare_geschossflaechenziffer_abgf": None, "baumassenziffer_bmz": None,
            "gesamthoehe_m": None, "gebaeudehoehe_m": 9.0, "grenzabstand_klein_m": 4.0,
            "grenzabstand_gross_m": None, "vollgeschosse_max": 2,
            "artikel_referenz": "Art. 20 (Testdaten)", "zitat": "Testdaten, kein echtes BZO-Zitat",
        }],
        "sonderregelungen": [],
    }
    r3 = run_from_modul_results(r1, modul2_synthetic, verkaufspreis_chf_pro_m2=11000)

    pruefe(r3["_meta"]["auflösungsmodus"] == "eindeutig", "Modul 3 rechnet normal (kein Blockieren)")
    zz = r3["zonen_zuordnung"]
    pruefe(zz["status"] == "gefunden", "Zone erfolgreich zugeordnet")
    pruefe(zz.get("basiszone_quelle") == "nutzungsklassifikation", "Basiszone stammt aus Modul 1b, nicht aus dem alten Fallback")
    pruefe(zz["zone"]["zonenbezeichnung"] == "Gartenstadtzone", "Richtige Zone zugeordnet")
    residualwert = r3["szenarien"]["base_case"]["residualwert"]["residualwert_max_landkaufpreis_chf"]
    pruefe(isinstance(residualwert, (int, float)), f"Residualwert berechnet: {residualwert:,.0f} CHF")
    print()


def test_rorschach_sg() -> None:
    print("=== Rorschach (SG): OEREB-Webservice muss erreichbar sein und echte Rechtsvorschriften liefern ===")
    r1 = run_modul1("Hauptstrasse 78, 9400 Rorschach")
    oereb = r1["oereb"]

    pruefe(oereb.get("found") is True, f"OEREB fuer SG gefunden (reason falls nicht: {oereb.get('reason')})")
    pruefe(oereb.get("kanton") == "SG", "Kanton korrekt als SG erkannt")
    rechtsvorschriften = oereb.get("rechtsvorschriften", [])
    pruefe(len(rechtsvorschriften) > 0, f"Rechtsvorschriften geladen ({len(rechtsvorschriften)} Eintraege)")
    bzo_relevant = [p for p in rechtsvorschriften if p.get("ist_wahrscheinlich_bzo_reglement")]
    pruefe(len(bzo_relevant) > 0, f"Mindestens ein BZO-relevantes Dokument erkannt ({[p['titel'] for p in bzo_relevant]})")

    k = r1["nutzungsklassifikation"]
    pruefe(k.get("gefunden") is True, "Nutzungsklassifikation fuer SG gefunden (via geodienste.ch)")
    snp_titel = [s.get("typ_kommunal_bezeichnung") for s in k.get("sondernutzungsplaene_massgebend", [])]
    pruefe(len(snp_titel) > 0, f"Sondernutzungsplan real erkannt ({snp_titel})")

    dummy_modul2 = {"erkannte_zonen": [], "sonderregelungen": []}
    r3 = run_from_modul_results(r1, dummy_modul2, verkaufspreis_chf_pro_m2=8000)
    pruefe(r3.get("status") == "sondernutzungsplan_massgebend", f"Modul 3 blockiert (status={r3.get('status')})")
    print()


def test_zonenzuordnung_ohne_verkaufspreis() -> None:
    print("=== ermittle_zonenzuordnung(): BZO-Zuordnung funktioniert OHNE Verkaufspreis (Web-App-Fix) ===")
    r1 = run_modul1("Rosenweg 4, 5033 Buchs AG")
    modul2_synthetic = {
        "erkannte_zonen": [{
            "zonenbezeichnung": "Gartenstadtzone", "ausnuetzungsziffer_az": 0.35,
            "anrechenbare_geschossflaechenziffer_abgf": None, "baumassenziffer_bmz": None,
            "gesamthoehe_m": None, "gebaeudehoehe_m": 9.0, "grenzabstand_klein_m": 4.0,
            "grenzabstand_gross_m": None, "vollgeschosse_max": 2,
        }],
        "sonderregelungen": [],
    }
    # Kein Verkaufspreis-Parameter noetig -- genau das war vorher gekoppelt.
    zz = ermittle_zonenzuordnung(r1, modul2_synthetic)
    pruefe(zz["status"] == "gefunden", f"Zonenzuordnung ohne Preis gefunden (status={zz['status']})")
    pruefe(zz["zone"]["zonenbezeichnung"] == "Gartenstadtzone", "Richtige Zone auch ohne Preis zugeordnet")

    # Muss identisch zu dem sein, was run_from_modul_results() intern verwendet.
    r3 = run_from_modul_results(r1, modul2_synthetic, verkaufspreis_chf_pro_m2=11000)
    pruefe(
        r3["zonen_zuordnung"]["zone"]["zonenbezeichnung"] == zz["zone"]["zonenbezeichnung"],
        "Identisches Ergebnis wie die preisabhaengige Finanzrechnung (keine Fachlogik-Abweichung durch die Auslagerung)",
    )
    print()


def test_parzellenauswahl_am_punkt() -> None:
    """Regression fuer einen realen Datenfehler (gefunden 2026-09-04):

    Die AV-Toleranzabfrage liefert an dieser Adresse VIER benachbarte
    Parzellen. get_parcel_data() nahm frueher ungeprueft results[0] und gab
    damit EGRID und Parzellennummer einer NACHBARparzelle zurueck (1055 bzw.
    1143, je nach schwankender Reihenfolge des Dienstes), waehrend die Flaeche
    aus der richtigen Geometrie stammte. Da der EGRID die gesamte
    OEREB-Abfrage steuert, wurde damit potenziell das falsche Grundstueck
    analysiert.
    """
    print("=== Parzellenauswahl: es muss die Parzelle gewaehlt werden, die den Punkt ENTHAELT ===")
    from potenzial_engine.modul1_geodata import _identify, _point_in_polygon, LAYER_PARCEL, get_parcel_data

    e, n = 2647661.0, 1248717.25  # Rosenweg 4, 5033 Buchs AG (amtliches Geocoding)

    treffer = _identify(e, n, LAYER_PARCEL, return_geometry=True)
    pruefe(len(treffer) > 1, f"Toleranzabfrage liefert mehrere Parzellen ({len(treffer)}) -- Auswahl ist noetig")

    enthaltende = [
        r for r in treffer
        if (r.get("geometry") or {}).get("type") == "Polygon"
        and _point_in_polygon(e, n, [(p[0], p[1]) for p in r["geometry"]["coordinates"][0]])
    ]
    pruefe(len(enthaltende) == 1, f"Genau eine Parzelle enthaelt den Punkt (tatsaechlich: {len(enthaltende)})")

    d = get_parcel_data(e, n)
    pruefe(d["parzellenauswahl"] == "punkt_in_parzelle", f"Auswahl per Punkt-in-Parzelle (tatsaechlich: {d['parzellenauswahl']})")

    erwartet = enthaltende[0].get("properties") or enthaltende[0].get("attributes") or {}
    pruefe(
        d["egrid"] == erwartet.get("egris_egrid"),
        f"EGRID stammt von der Parzelle, die den Punkt enthaelt ({d['egrid']})",
    )
    pruefe(
        str(d["parzellennummer"]) == str(erwartet.get("number")),
        f"Parzellennummer stammt von derselben Parzelle ({d['parzellennummer']})",
    )
    pruefe(
        d["parzellennummer"] != erwartet_falsch(treffer, erwartet),
        "Nicht mehr die Nachbarparzelle aus results[0] (der alte Fehler)",
    )
    print()


def erwartet_falsch(treffer: list, richtig: dict) -> object:
    """Parzellennummer des ersten Treffers -- genau der Wert, den die alte
    Implementierung faelschlich zurueckgab, sofern er nicht zufaellig der
    richtige ist."""
    erster = treffer[0].get("properties") or treffer[0].get("attributes") or {}
    if erster.get("egris_egrid") == richtig.get("egris_egrid"):
        return object()  # results[0] war zufaellig korrekt -- kein Vergleichswert
    return erster.get("number")


def main() -> None:
    test_baden()
    test_zuerich()
    test_normalfall_ohne_snp()
    test_rorschach_sg()
    test_zonenzuordnung_ohne_verkaufspreis()
    test_parzellenauswahl_am_punkt()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE TESTS BESTANDEN")


if __name__ == "__main__":
    main()

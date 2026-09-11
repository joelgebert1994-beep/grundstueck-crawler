"""
G1 durch die reale Pipeline: 7 echte Grundstuecke, echte Parzellengeometrie
und echte Restriktionsgeometrie (Gewaesserraum/Waldgrenzen/Baulinien) aus
Modul 1, kombiniert mit den G1-Geometrie-Kern (baubereich.py) ueber die
Verdrahtung in g1_verdrahtung.py.

WICHTIGE EINSCHRAENKUNG (siehe Ausgabe unten): Modul 2 (BZO-Kennzahlen-
Extraktion per Gemini/Claude) kann in dieser Umgebung mangels API-Key nicht
live laufen. Die AZ/BMZ/UEZ/Hoehe/Grenzabstand-Werte je Zone sind deshalb
PLATZHALTER (klar gekennzeichnet, analog zum bereits etablierten Muster in
test_klassifikation.py) -- NICHT ueber den echten Modul-2-Code-Pfad bezogen.
Alles andere (Geocoding, Parzellengeometrie, Gewaesserraum/Waldgrenzen/
Baulinien-WFS-Abfragen, Nutzungsklassifikation) ist echt und live.

CLI: python g1_reale_faelle.py
"""

from __future__ import annotations

from potenzial_engine.modul1_geodata import run_modul1
from potenzial_engine.g1_verdrahtung import berechne_g1_fuer_fall, laengste_kante_index


def drucke_kaskade(titel: str, g1: dict) -> None:
    print(f"--- {titel} ---")
    print(f"  Modus: {g1['modus']}")
    print(f"  Parzellenflaeche (amtlich): {g1['parzellenflaeche_amtlich_m2']} m2")
    rq = g1["restriktionsquellen"]
    print(
        f"  Restriktionsquellen: Gewaesserraum={rq['gewaesserraum_flaechen']} Flaeche(n), "
        f"Waldgrenze_min_abstand={rq['waldgrenze_min_abstand_m']} m "
        f"(verwendet={rq['waldabstand_m_verwendet']}), Baulinien={rq['baulinien_gefunden']}"
    )
    for h in rq["hinweise"]:
        print(f"    Hinweis: {h}")

    ergebnisse = g1.get("szenarien") or {"": g1.get("ergebnis")}
    for name, e in ergebnisse.items():
        praefix = f"  [{name}] " if name else "  "
        restriktionsflaeche_m2 = round(e["parzellenflaeche_m2"] - e["anrechenbare_landflaeche_m2"], 1)
        print(f"{praefix}Parzelle {e['parzellenflaeche_m2']} m2 -> Restriktion {restriktionsflaeche_m2} m2 "
              f"-> anrechenbar {e['anrechenbare_landflaeche_m2']} m2")
        print(f"{praefix}Baubereich {e['baubereich_m2']} m2 -> Fussabdruck {e['fussabdruck_m2']} m2 "
              f"(limitiert durch: {e['fussabdruck_limitiert_durch']})")
        print(f"{praefix}Geschosse: {e['geschosszahl']} (limitiert durch: {e['geschosszahl_limitiert_durch']})")
        print(f"{praefix}Geschossflaeche: {e['geschossflaeche_m2']} m2 "
              f"(limitiert durch: {e['geschossflaeche_limitiert_durch']})")
        for h in e["hinweise"]:
            print(f"{praefix}Hinweis: {h}")
    print()


def main() -> None:
    print("=" * 70)
    print("FALL 1: Baden -- Gartenstrasse 5, 5400 Baden (Kernzone 5, real 2x SNP-blockiert)")
    print("=" * 70)
    r1 = run_modul1("Gartenstrasse 5, 5400 Baden")
    zone_baden = {
        "zonenbezeichnung": "Kernzone 5 (PLATZHALTER, kein echtes BZO-Zitat)",
        "ausnuetzungsziffer_az": 1.0, "gebaeudehoehe_m": 12.0, "vollgeschosse_max": 4,
        "grenzabstand_klein_m": 4.0, "grenzabstand_gross_m": 6.0,
    }
    g1 = berechne_g1_fuer_fall(r1, zone_baden)
    drucke_kaskade("Baden (G1-Geometrie unabhaengig von der SNP-Finanzblockierung)", g1)
    print("  HINWEIS: In der echten Modul-3-Pipeline bleibt dieser Fall wegen 2 rechtskraeftigen")
    print("  Sondernutzungsplaenen blockiert (siehe test_klassifikation.py) -- diese G1-Zahl ist")
    print("  eine reine Geometrie-Demonstration, KEINE belastbare Finanzaussage fuer diese Parzelle.\n")

    print("=" * 70)
    print("FALL 2: Zuerich -- Bahnhofstrasse 1, 8001 Zuerich (Kernzone, real SNP-blockiert)")
    print("=" * 70)
    r2 = run_modul1("Bahnhofstrasse 1, 8001 Zuerich")
    zone_zuerich = {
        "zonenbezeichnung": "Kernzone (PLATZHALTER, kein echtes BZO-Zitat)",
        "ausnuetzungsziffer_az": 1.2, "gebaeudehoehe_m": 18.0, "vollgeschosse_max": 5,
        "grenzabstand_klein_m": 0.0, "grenzabstand_gross_m": 3.0,
    }
    g1 = berechne_g1_fuer_fall(r2, zone_zuerich)
    drucke_kaskade("Zuerich (G1-Geometrie unabhaengig von der SNP-Finanzblockierung)", g1)

    print("=" * 70)
    print("FALL 3: Buchs AG -- Rosenweg 4, 5033 Buchs AG (Gartenstadtzone, Normalfall)")
    print("=" * 70)
    r3 = run_modul1("Rosenweg 4, 5033 Buchs AG")
    zone_buchs = {
        "zonenbezeichnung": "Gartenstadtzone (PLATZHALTER, identisch zu test_klassifikation.py)",
        "ausnuetzungsziffer_az": 0.35, "gebaeudehoehe_m": 9.0, "vollgeschosse_max": 2,
        "grenzabstand_klein_m": 4.0,
    }
    g1 = berechne_g1_fuer_fall(r3, zone_buchs)
    drucke_kaskade("Buchs AG", g1)

    print("=" * 70)
    print("FALL 4: TG -- Bahnhofstrasse 10, 8500 Frauenfeld (REALE Baulinien gefunden)")
    print("=" * 70)
    r4 = run_modul1("Bahnhofstrasse 10, 8500 Frauenfeld")
    zone_tg = {
        "zonenbezeichnung": "Wohn- und Arbeitszone 4 (PLATZHALTER, kein echtes BZO-Zitat)",
        "ausnuetzungsziffer_az": 0.9, "gebaeudehoehe_m": 14.0, "vollgeschosse_max": 4,
        "grenzabstand_klein_m": 4.0, "grenzabstand_gross_m": 7.0,
    }
    g1 = berechne_g1_fuer_fall(r4, zone_tg)
    drucke_kaskade("TG Frauenfeld (mit real gefundenen Baulinien als Restriktion)", g1)

    print("=" * 70)
    print("FALL 5: Gewaesserraum -- Sihlquai 70, 8005 Zuerich (REALE Ueberlappung, Abstand 0.0 m)")
    print("=" * 70)
    r5 = run_modul1("Sihlquai 70, 8005 Zuerich")
    zone_gewaesser = {
        "zonenbezeichnung": "Zentrumszone (PLATZHALTER, kein echtes BZO-Zitat)",
        "ausnuetzungsziffer_az": 1.5, "gebaeudehoehe_m": 20.0, "vollgeschosse_max": 6,
        "grenzabstand_klein_m": 3.0,
    }
    g1 = berechne_g1_fuer_fall(r5, zone_gewaesser)
    drucke_kaskade("Sihlquai 70 (mit real abgezogener Gewaesserraum-Flaeche)", g1)

    print("=" * 70)
    print("FALL 6: Waldnaehe -- Sonnenbergstrasse 1, 8803 Rueschlikon (Waldgrenze 13.0 m entfernt)")
    print("=" * 70)
    r6 = run_modul1("Sonnenbergstrasse 1, 8803 Rueschlikon")
    zone_wald = {
        "zonenbezeichnung": "W2 (PLATZHALTER, kein echtes BZO-Zitat)",
        "ausnuetzungsziffer_az": 0.4, "gebaeudehoehe_m": 8.0, "vollgeschosse_max": 2,
        "grenzabstand_klein_m": 4.0,
    }
    g1_ohne = berechne_g1_fuer_fall(r6, zone_wald)
    drucke_kaskade("Rueschlikon OHNE Waldabstand-Override (Geometrie gefunden, nicht angewendet)", g1_ohne)
    # Illustrativ: zeigt, dass die Restriktion tatsaechlich wirkt, SOBALD ein
    # Waldabstand bekannt ist -- 15m ist hier ein angenommener Beispielwert,
    # KEIN recherchierter gesetzlicher Wert fuer Rueschlikon.
    from potenzial_engine.modul1_geodata import geocode_address
    from potenzial_engine.restriktionsgeometrie import hole_restriktionen_fuer_parzelle
    geo = geocode_address("Sonnenbergstrasse 1, 8803 Rueschlikon")
    r6_mit_wald = dict(r6)
    r6_mit_wald["restriktionsgeometrie"] = hole_restriktionen_fuer_parzelle(
        geo["lv95_e"], geo["lv95_n"], r6["gemeinde"].get("kanton"),
        r6["kataster"]["parzellengeometrie"], waldabstand_m=15.0,
    )
    g1_mit = berechne_g1_fuer_fall(r6_mit_wald, zone_wald)
    drucke_kaskade("Rueschlikon MIT illustrativem Waldabstand=15m (Beispielwert, nicht recherchiert)", g1_mit)

    print("=" * 70)
    print("FALL 7: Unterschiedliche Grenzabstaende -- Buchs AG, manueller Kanten-Override")
    print("=" * 70)
    ring = r3["kataster"]["parzellengeometrie"]
    idx_laengste = laengste_kante_index(ring)
    n_kanten = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
    override = [4.0] * n_kanten
    override[idx_laengste] = 7.0
    print(f"  Illustrations-Heuristik: laengste Kante (Index {idx_laengste} von {n_kanten}) erhaelt")
    print("  Grenzabstand_gross=7.0m, alle anderen Kanten Grenzabstand_klein=4.0m.")
    print("  ACHTUNG: 'laengste Kante = Strassenseite' ist eine reine Illustrations-Annahme,")
    print("  keine belastbare Regel -- echte Kantenklassifikation ist nicht Teil dieses Schritts.\n")
    g1 = berechne_g1_fuer_fall(r3, zone_buchs, kanten_abstaende_override=override)
    drucke_kaskade("Buchs AG mit differenzierten Kanten-Grenzabstaenden", g1)


if __name__ == "__main__":
    main()

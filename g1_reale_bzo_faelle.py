"""
G1 mit ECHTEN BZO-Zahlen durch die reale Pipeline.

WICHTIGE EINSCHRAENKUNG: In dieser Umgebung ist kein GEMINI_API_KEY/
ANTHROPIC_API_KEY gesetzt -- Modul 2s Gemini-Codepfad (analyze_bzo_documents)
konnte deshalb NICHT live ausgefuehrt werden. Um trotzdem eine echte,
platzhalterfreie End-to-End-Rechnung zu zeigen, wurden die realen BZO-/
Teilzonenreglement-PDFs stattdessen manuell (WebFetch/pymupdf) gelesen und
die Kennzahlen mit Artikel-Referenz von Hand extrahiert -- exakt dieselben
Dokumente, die Modul 2 auch bekommen haette, nur ohne den LLM-Schritt selbst.
Jede Zahl unten traegt ihre Quelle/Artikel-Referenz im Kommentar.

Getestete Gemeinden/Systeme (bewusst unterschiedliche kantonale Regelsysteme):
  - Buchs AG:  Ausnuetzungsziffer-basiert (klassisches AZ-System)
  - Baden AG:  Geschosszahl+Hoehe-basiert, KEINE Ausnuetzungsziffer
               (zeigt: Geschossflaeche kann auch OHNE jede Nutzungsziffer
               rein aus Geometrie x Geschosszahl folgen)
  - Liestal BL: Ueberbauungsziffer(%)-basiert (Bebauungsziffer)
  - Frauenfeld TG: NUR TEILWEISE real bestimmbar -- ehrlich als Luecke
               ausgewiesen statt geraten (siehe Fall 4)

Baden und Zuerich bleiben ausdruecklich SNP-blockiert in der echten
Finanzpipeline (siehe test_klassifikation.py) -- die G1-Zahlen fuer Baden
hier sind eine reine, jetzt aber vollstaendig echte Geometrie-Demonstration,
KEINE Finanzaussage.

CLI: python g1_reale_bzo_faelle.py
"""

from __future__ import annotations

from modul1_geodata import run_modul1
from g1_verdrahtung import berechne_g1_fuer_fall


def drucke_kaskade(titel: str, g1: dict, quelle: str) -> None:
    print(f"--- {titel} ---")
    print(f"  BZO-Quelle: {quelle}")
    print(f"  Modus: {g1['modus']}")
    print(f"  Parzellenflaeche (amtlich): {g1['parzellenflaeche_amtlich_m2']} m2")
    rq = g1["restriktionsquellen"]
    print(
        f"  Restriktionsquellen: Gewaesserraum={rq['gewaesserraum_flaechen']} Flaeche(n), "
        f"Waldgrenze_min_abstand={rq['waldgrenze_min_abstand_m']} m "
        f"(verwendet={rq['waldabstand_m_verwendet']}), Baulinien={rq['baulinien_gefunden']}"
    )

    ergebnisse = g1.get("szenarien") or {"": g1.get("ergebnis")}
    for name, e in ergebnisse.items():
        praefix = f"  [{name}] " if name else "  "
        restriktionsflaeche_m2 = round(e["parzellenflaeche_m2"] - e["anrechenbare_landflaeche_m2"], 1)
        print(f"{praefix}1) Parzelle: {e['parzellenflaeche_m2']} m2")
        print(f"{praefix}2) Restriktionen abgezogen: {restriktionsflaeche_m2} m2 -> anrechenbar: {e['anrechenbare_landflaeche_m2']} m2")
        print(f"{praefix}3) Baubereich (Grenzabstaende): {e['baubereich_m2']} m2")
        print(f"{praefix}4) Fussabdruck: {e['fussabdruck_m2']} m2 -- Kandidaten: {e['fussabdruck_kandidaten']} -> LIMITIERT DURCH: {e['fussabdruck_limitiert_durch']}")
        print(f"{praefix}5) Geschosszahl: {e['geschosszahl']} -- Kandidaten: {e['geschosszahl_kandidaten']} -> LIMITIERT DURCH: {e['geschosszahl_limitiert_durch']}")
        print(f"{praefix}6) AZ/UEZ/BMZ-Gegenkontrolle -- Kandidaten: {e['geschossflaeche_kandidaten']}")
        print(f"{praefix}7) Resultierende Geschossflaeche: {e['geschossflaeche_m2']} m2 -> LIMITIERT DURCH: {e['geschossflaeche_limitiert_durch']}")
        for h in e["hinweise"]:
            print(f"{praefix}Hinweis: {h}")
    print()


def main() -> None:
    print("=" * 78)
    print("FALL 1 (Normalfall, item 8): Buchs AG -- Rosenweg 4, 5033 Buchs AG")
    print("Gartenstadtzone [Ga] -- AZ-basiertes System")
    print("=" * 78)
    r1 = run_modul1("Rosenweg 4, 5033 Buchs AG")
    zone_buchs = {
        "zonenbezeichnung": "Gartenstadtzone [Ga]",
        "ausnuetzungsziffer_az": 0.5,      # § 18 Baumassentabelle "Ga", S. 14
        "gebaeudehoehe_m": 10.0,           # § 18 Tabelle: 10.00m (uebliche Dachform); 11.50m nur bei Schraegdach mit Zusatzbedingungen (Anm. c) -- konservativ 10.00 gewaehlt
        "grenzabstand_klein_m": 4.0,       # § 18 Tabelle
        "grenzabstand_gross_m": 6.0,       # § 18 Tabelle
        # KEIN BMZ, KEIN UEZ/GFZ, KEIN explizites vollgeschosse_max im Dokument
        # -- echte Abwesenheit dieser Kennzahlen fuer diese Zone, nicht vergessen.
    }
    g1 = berechne_g1_fuer_fall(r1, zone_buchs)
    drucke_kaskade("Buchs AG (100% echte BZO-Zahlen)", g1, "Bau- und Nutzungsordnung Buchs, § 18 Baumassentabelle + § 23 Gartenstadtzone (Stand 11.10.2023)")

    print("=" * 78)
    print("FALL 2 (item 7, bleibt SNP-blockiert): Baden -- Gartenstrasse 5, 5400 Baden")
    print("Kernzone 5 [K5] -- Geschosszahl+Hoehe-System, KEINE Ausnuetzungsziffer")
    print("=" * 78)
    r2 = run_modul1("Gartenstrasse 5, 5400 Baden")
    zone_baden = {
        "zonenbezeichnung": "Kernzone 5 [K5]",
        "vollgeschosse_max": 5,            # Zonentabelle Baden, Spalte "Anzahl Geschosse", S. 4
        "gebaeudehoehe_m": 20.0,           # dieselbe Tabelle, Spalte "Max. Gesamthoehe"
        "grenzabstand_klein_m": 4.5,       # dieselbe Tabelle, Spalte "Kleiner Grenzabstand" (kein separater "grosser" Wert fuer K5 in der Tabelle)
        "geschosshoehe_m": 4.0,            # aus Tabelle abgeleitet (20.0m / 5 Geschosse) -- verhindert einen kuenstlichen Hoehen-Engpass gegenueber der explizit vorgegebenen Geschosszahl
        # KEIN AZ, KEIN aBGF, KEIN BMZ, KEIN UEZ -- diese Zone kennt ueberhaupt
        # keine Nutzungsziffer, die Geschossflaeche folgt hier zwingend NUR
        # aus Fussabdruck x Geschosszahl.
    }
    g1 = berechne_g1_fuer_fall(r2, zone_baden)
    drucke_kaskade("Baden (100% echte BZO-Zahlen, G1-Geometrie-Demo)", g1, "Bau- und Nutzungsordnung Baden, Zonentabelle S. 4")
    print("  WICHTIG: In der echten Modul-3-Finanzpipeline bleibt dieser Fall wegen 2")
    print("  rechtskraeftigen Sondernutzungsplaenen blockiert (siehe test_klassifikation.py,")
    print("  22/22 gruen) -- diese G1-Zahl ist reine, jetzt vollstaendig reale Geometrie-")
    print("  Demonstration, KEINE belastbare Finanzaussage fuer diese Parzelle.\n")

    print("=" * 78)
    print("FALL 3 (item 3, UEZ-Nachweis): Rathausstrasse 1, 4410 Liestal")
    print("Zentrumszone 1 (Teil der Kernzone Liestal) -- Ueberbauungsziffer(%)-System")
    print("=" * 78)
    r3 = run_modul1("Rathausstrasse 1, 4410 Liestal")
    zone_liestal = {
        "zonenbezeichnung": "Zentrumszone 1 (Subzone exemplarisch -- genaue Zuordnung Rathausstrasse 1 zu Zentrumszone 1/2/3 nicht anhand des Teilzonenplans verifiziert, siehe Hinweis)",
        "ueberbauungsziffer_uz": 0.30,     # § 16 Abs. 2 Teilzonenreglement Zentrum Liestal: "Zentrumszone 1: max. 30 %"
        "vollgeschosse_max": 3,            # § 16 Abs. 1: "In den Zentrumszonen duerfen maximal 3 Vollgeschosse realisiert werden"
        "gebaeudehoehe_m": 13.5,           # § 16 Abs. 4: "zulaessige Gebaeudehoehe in m: 13.50 m" (Zentrumszone 1/2)
        "grenzabstand_klein_m": 0.0,       # abgeleitet aus § 8 Abs. 2 (Grenzbaurecht/geschlossene Bauweise ausdruecklich zulaessig) -- kein separater Zahlenwert im Dokument gefunden
        "geschosshoehe_m": 4.5,            # 13.5m / 3 Geschosse
    }
    g1 = berechne_g1_fuer_fall(r3, zone_liestal)
    drucke_kaskade("Liestal Zentrumszone 1 (echte UEZ=30%, Subzonen-Zuordnung als Annahme markiert)", g1, "Teilzonenreglement Zentrum Liestal, § 16 + § 8 (Stand RRB 1361, 15.10.2024)")
    print("  HINWEIS: Rathausstrasse 1 klassifiziert amtlich nur als generische 'Kernzone'")
    print("  (OEREB/geodienste), das Teilzonenreglement unterscheidet aber Zentrumszone 1/2/3")
    print("  mit unterschiedlicher Bebauungsziffer (30%/25%/frei). Zentrumszone 1 wurde hier")
    print("  als Beispiel gewaehlt, OHNE Abgleich mit dem Teilzonenplan-Geometrie -- die echte")
    print("  Subzone dieser konkreten Parzelle ist damit nicht abschliessend verifiziert.\n")

    print("=" * 78)
    print("FALL 4 (item 2/4, ehrlich unvollstaendig): Bahnhofstrasse 10, 8500 Frauenfeld TG")
    print("Wohn- und Arbeitszone 4 [WA4]")
    print("=" * 78)
    r4 = run_modul1("Bahnhofstrasse 10, 8500 Frauenfeld")
    print("  REAL BESTAETIGT:")
    print("  - vollgeschosse_max = 4 (Baureglement Frauenfeld, Schlussbestimmungen 'Zonenbezeichnung',")
    print("    S. 17: alte Bezeichnung 'WG4 Wohn- und Gewerbezone 4 VOLLGESCHOSSE' -> neu 'WA4')")
    print("  - Waldabstand = 25 m ab Waldrand, Gewaesserabstand = 30 m (Seen/Fluesse) bzw. 15 m")
    print("    (Baeche/Kanaele) OHNE Gewaesserraumlinie (kantonales PBG TG, §§ 75-76)")
    print(f"  - {len(r4['restriktionsgeometrie'].get('baulinien_gefunden', []))} reale, rechtskraeftige Baulinien (Kategorie 71) live gefunden")
    print("  NICHT in Textform auffindbar (weder im kommunalen Baureglement noch im kantonalen")
    print("  Planungs- und Baugesetz/PBV): Ausnuetzungsziffer bzw. Bebauungsziffer, Gebaeudehoehe")
    print("  und der nachbarschaftliche Grenzabstand fuer WA4. Nach Textdurchsicht von Baureglement")
    print("  + PBG + PBV liegen diese Werte vermutlich nur auf dem GRAFISCHEN Zonenplan (Kartenwerk),")
    print("  nicht als Text/Tabelle -- eine belastbare Geschossflaechen-Kaskade ist deshalb OHNE")
    print("  Rateannahme fuer diesen Fall nicht moeglich. Bewusst NICHT mit einem Platzhalter")
    print("  aufgefuellt (Vorgabe: keine Platzhalter in einem 'realen' End-to-End-Test).\n")


if __name__ == "__main__":
    main()

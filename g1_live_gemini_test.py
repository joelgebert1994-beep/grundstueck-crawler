"""
Live-Test: Modul 1 (inkl. neuer themenbasierter Dokumentauswahl) -> Modul 2
(Gemini, neues Kennzahl-Schema mit Bedingungen+Confidence) -> G1.

Liest GEMINI_API_KEY ausschliesslich aus der Umgebungsvariable -- der Key
wird in diesem Skript nie entgegengenommen, geloggt oder ausgegeben.

WICHTIG: Die Dokumentauswahl laeuft hier IMMER automatisch ueber
analyze_from_oereb_result() (Modul 1s neue theorie-/host-basierte
Priorisierung, siehe _extract_legal_provisions()/priorisiere_nach_basiszone()
in modul1_geodata.py) -- KEINE manuelle URL-Korrektur mehr (im Unterschied
zum Vorgaenger-Skript aus der letzten Session).

CLI: python g1_live_gemini_test.py <fallname>
  fallname: "buchs", "liestal", "frauenfeld", "baden" oder "zuerich"
"""

from __future__ import annotations

import sys

from modul1_geodata import run_modul1
from modul2_bzo_analysis import analyze_from_oereb_result, Modul2Error
from g1_verdrahtung import berechne_g1_fuer_fall, G1VerdrahtungError

# Referenzwerte: in der letzten Session manuell aus den echten BZO-Dokumenten
# verifiziert (siehe g1_reale_bzo_faelle.py). Nur fuer Faelle vorhanden, wo
# das gemacht wurde -- Frauenfeld/Baden/Zuerich laufen ohne Referenzvergleich,
# rein als Robustheits-/Dokumentauswahl-Test.
REFERENZWERTE = {
    "buchs": {
        "zonenbezeichnung_erwartet": "Gartenstadtzone",
        "ausnuetzungsziffer_az": 0.5,
        "anrechenbare_geschossflaechenziffer_abgf": None,
        "baumassenziffer_bmz": None,
        "ueberbauungsziffer_uz": None,
        "gesamthoehe_m": 10.0,  # oder 11.50 bei Schraegdach mit Zusatzbedingungen (Anm. c) -- jetzt strukturiert als Bedingung erwartet
        "gebaeudehoehe_m": None,
        "grenzabstand_klein_m": 4.0,
        "grenzabstand_gross_m": 6.0,
        "vollgeschosse_max": None,
        "quelle": "Bau- und Nutzungsordnung Buchs, § 18 Baumassentabelle + § 23 (manuell verifiziert)",
    },
    "liestal": {
        "zonenbezeichnung_erwartet": "Zentrumszone 1",
        "ausnuetzungsziffer_az": None,
        "anrechenbare_geschossflaechenziffer_abgf": None,
        "baumassenziffer_bmz": None,
        "ueberbauungsziffer_uz": 0.30,
        "gesamthoehe_m": None,
        "gebaeudehoehe_m": 13.5,
        "grenzabstand_klein_m": None,  # kein expliziter Zahlenwert im Dokument -- Gemini soll dies KORREKT als nicht_bestimmbar melden, nicht raten
        "grenzabstand_gross_m": None,
        "vollgeschosse_max": 3,
        "quelle": "Teilzonenreglement Zentrum Liestal, § 16 + § 8 (manuell verifiziert)",
    },
}

ADRESSEN = {
    "buchs": "Rosenweg 4, 5033 Buchs AG",
    "liestal": "Rathausstrasse 1, 4410 Liestal",
    "frauenfeld": "Bahnhofstrasse 10, 8500 Frauenfeld",
    "baden": "Gartenstrasse 5, 5400 Baden",
    "zuerich": "Bahnhofstrasse 1, 8001 Zuerich",
}

ZONENSUCHE = {
    "buchs": "Gartenstadtzone",
    "liestal": "Zentrumszone 1",
    "frauenfeld": "Wohn- und Arbeitszone 4",
    "baden": "Kernzone 5",
    "zuerich": "Kernzone",
}

VERGLEICHSFELDER = [
    "ausnuetzungsziffer_az", "anrechenbare_geschossflaechenziffer_abgf",
    "baumassenziffer_bmz", "ueberbauungsziffer_uz", "gesamthoehe_m",
    "gebaeudehoehe_m", "grenzabstand_klein_m", "grenzabstand_gross_m",
    "vollgeschosse_max",
]


def naehe(a, b, toleranz=0.05) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= toleranz


def drucke_kennzahl(feld: str, k: dict) -> None:
    print(f"    {feld}: wert={k.get('wert')} einheit={k.get('einheit')!r} confidence={k.get('confidence')}")
    if k.get("quelle_dokument"):
        print(f"        quelle_dokument: {k['quelle_dokument']}")
    if k.get("artikel_referenz"):
        print(f"        artikel_referenz: {k['artikel_referenz']}")
    if k.get("zitat"):
        print(f"        zitat: {k['zitat']}")
    if k.get("unklarheit"):
        print(f"        unklarheit: {k['unklarheit']}")
    for b in k.get("bedingungen") or []:
        print(f"        BEDINGUNG: falls '{b.get('bedingung_text')}' -> wert={b.get('wert_unter_bedingung')} ({b.get('artikel_referenz')})")


def main() -> None:
    fall = sys.argv[1] if len(sys.argv) > 1 else "buchs"
    adresse = ADRESSEN[fall]
    referenz = REFERENZWERTE.get(fall)

    print("=" * 78)
    print(f"LIVE-TEST: {fall.upper()} -- {adresse}")
    print("=" * 78)

    print("\n[1/5] Modul 1 (echte amtliche Geodaten + automatische Dokumentauswahl)...")
    modul1_result = run_modul1(adresse)
    oereb = modul1_result.get("oereb", {})
    if not oereb.get("found"):
        print("FEHLER: Modul 1 lieferte keine OEREB-Daten:", oereb.get("reason"))
        sys.exit(1)
    kanton = oereb.get("kanton")
    gemeinde = modul1_result.get("gemeinde", {}).get("gemeinde")

    alle_provisions = oereb.get("rechtsvorschriften", [])
    bzo_provisions = [p for p in alle_provisions if p.get("ist_wahrscheinlich_bzo_reglement")]
    print(f"  {len(bzo_provisions)} von {len(alle_provisions)} Dokumenten als BZO-relevant erkannt (automatisch, KEINE manuelle Auswahl):")
    for p in bzo_provisions[:5]:
        print(f"    [{p.get('rechtsebene')}] {p.get('titel')}")
    klass = modul1_result.get("nutzungsklassifikation", {})
    print(f"  Basiszone (Modul 1b): {(klass.get('basiszone') or {}).get('typ_kommunal_bezeichnung')}")

    print("\n[2/5] Modul 2 (ECHTER Gemini-API-Call, automatische Dokumentauswahl, max_documents=5)...")
    try:
        modul2_result = analyze_from_oereb_result(oereb, gemeinde=gemeinde, kanton=kanton, backend="gemini")
    except Modul2Error as exc:
        print(f"  FEHLER: {exc}")
        sys.exit(1)
    meta = modul2_result.get("_meta", {})
    print(f"  Backend: {meta.get('backend')}, Modell: {meta.get('model')}, Tokens: in={meta.get('input_tokens')} out={meta.get('output_tokens')}")
    print(f"  Dokument-Titel (Gemini): {modul2_result.get('dokument_titel')}")
    print(f"  Erkannte Zonen: {len(modul2_result.get('erkannte_zonen', []))}, Sonderregelungen: {len(modul2_result.get('sonderregelungen', []))}")
    if modul2_result.get("unklarheiten_und_pruefhinweise"):
        print("  Unklarheiten/Pruefhinweise (Gemini):")
        for u in modul2_result["unklarheiten_und_pruefhinweise"]:
            print(f"    - {u}")

    zonensuche = ZONENSUCHE[fall]
    kandidaten = [
        z for z in modul2_result.get("erkannte_zonen", [])
        if zonensuche.lower() in (z.get("zonenbezeichnung") or "").lower()
    ]
    if not kandidaten:
        print(f"\nFEHLER: Keine Zone gefunden, die '{zonensuche}' enthaelt. Erkannte Zonen:")
        for z in modul2_result.get("erkannte_zonen", []):
            print(f"    - {z.get('zonenbezeichnung')}")
        sys.exit(1)
    gemini_zone = kandidaten[0]

    print(f"\n[3/5] Gemini-Extraktion fuer Zone '{gemini_zone.get('zonenbezeichnung')}' (neues Kennzahl-Schema):")
    for feld in VERGLEICHSFELDER:
        drucke_kennzahl(feld, gemini_zone.get(feld) or {})

    alle_ok = True
    if referenz:
        print(f"\n[4/5] Vergleich Gemini vs. manuell verifizierte Referenz ({referenz['quelle']}):")
        for feld in VERGLEICHSFELDER:
            g = (gemini_zone.get(feld) or {}).get("wert")
            r = referenz[feld]
            stimmt = naehe(g, r) if isinstance(r, (int, float)) or isinstance(g, (int, float)) else (g == r)
            status = "OK   " if stimmt else "ABWEICHUNG"
            if not stimmt:
                alle_ok = False
            print(f"    [{status}] {feld}: Gemini={g!r}  Referenz={r!r}")
    else:
        print(f"\n[4/5] Kein manueller Referenzwert fuer '{fall}' hinterlegt -- reiner Dokumentauswahl-/Robustheitstest.")

    print(f"\n[5/5] G1-Kaskade mit den GEMINI-Werten (keine manuellen Zahlen):")
    try:
        g1 = berechne_g1_fuer_fall(modul1_result, gemini_zone)
    except G1VerdrahtungError as exc:
        print(f"  G1 hat korrekt abgelehnt statt zu raten: {exc}")
        g1 = None

    if g1:
        for h in g1.get("kennzahl_hinweise", []):
            print(f"  Kennzahl-Hinweis: {h}")
        ergebnisse = g1.get("szenarien") or {"": g1.get("ergebnis")}
        for name, e in ergebnisse.items():
            praefix = f"  [{name}] " if name else "  "
            print(f"{praefix}Parzelle {e['parzellenflaeche_m2']} m2 -> anrechenbar {e['anrechenbare_landflaeche_m2']} m2")
            print(f"{praefix}Baubereich {e['baubereich_m2']} m2 -> Fussabdruck {e['fussabdruck_m2']} m2 "
                  f"(Kandidaten: {e['fussabdruck_kandidaten']}, limitiert durch: {e['fussabdruck_limitiert_durch']})")
            print(f"{praefix}Geschosse {e['geschosszahl']} (Kandidaten: {e['geschosszahl_kandidaten']}, "
                  f"limitiert durch: {e['geschosszahl_limitiert_durch']})")
            print(f"{praefix}Geschossflaeche {e['geschossflaeche_m2']} m2 "
                  f"(Kandidaten: {e['geschossflaeche_kandidaten']}, limitiert durch: {e['geschossflaeche_limitiert_durch']})")

    print("\n" + "=" * 78)
    if referenz:
        print(f"GESAMTERGEBNIS: {'ALLE FELDER STIMMEN UEBEREIN' if alle_ok else 'ES GIBT ABWEICHUNGEN (siehe oben)'}")
    else:
        print("GESAMTERGEBNIS: Dokumentauswahl + Gemini-Extraktion liefen ohne Absturz durch (kein Referenzvergleich).")
    print("=" * 78)


if __name__ == "__main__":
    main()

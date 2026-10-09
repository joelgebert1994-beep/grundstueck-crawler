"""A3: Plausibilitaetspruefung der Reglementwerte.

Ein ausgelesener Wert wird gegen SEINEN EIGENEN Beleg geprueft (Einheit,
Originaltext) -- nicht gegen pauschale Wertebereiche. Was sich widerspricht,
wird zurueckgehalten (wert None in der Rechenkopie), nie korrigiert.

Echte Belege:
  * Weiningen W2 30 -- Live-Eingaben (tests/daten/weiningen/g1_eingaben_hogerwies.json)
  * Rheineck W2 -- gespeicherte Reglementauswertung (tests/daten/rheineck/zone_w2.json)
  * Birmensdorf/Russikon -- Muster aus gespeicherten Auswertungen: "max. 70 %"
    wurde als AZ 70 statt 0.70 gelesen

Aufruf: python -m tests.test_reglement_plausibilitaet
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine.g1_verdrahtung import berechne_g1_fuer_fall  # noqa: E402
from potenzial_engine.modul3_financial import match_zone  # noqa: E402
from potenzial_engine.reglement_plausibilitaet import (  # noqa: E402
    STATUS_PRUEFBEDUERFTIG, pruefe_kennzahl, pruefe_zone, zahlen_im_text,
)

DATEN = Path(__file__).resolve().parent / "daten"
WEININGEN = json.loads((DATEN / "weiningen" / "g1_eingaben_hogerwies.json").read_text(encoding="utf-8"))
RHEINECK = json.loads((DATEN / "rheineck" / "zone_w2.json").read_text(encoding="utf-8"))["zone"]

_ok = 0
_fehler: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)
        print(f"[FEHL] {was}")


def kz(wert, einheit=None, zitat=None, **mehr):
    return {"wert": wert, "einheit": einheit, "quelle_dokument": "Bau- und Zonenordnung",
            "artikel_referenz": "Art. 7", "zitat": zitat, "confidence": "hoch",
            "bedingungen": [], "unklarheit": None, **mehr}


def arten(feld, k):
    return [b["art"] for b in pruefe_kennzahl(feld, k)]


def ueber_match_zone(zone):
    m = match_zone([{"zonenbezeichnung": zone["zonenbezeichnung"], "ist_wahrscheinlich_basiszone": True}],
                   [zone])
    return m


def test_weiningen() -> None:
    print("=== 1. Weiningen: 'max. 30 %' bleibt 0.30 ===")
    zone = WEININGEN["zone"]
    az = zone["ausnuetzungsziffer_az"]
    pruefe(az["wert"] == 0.3 and az["einheit"] == "Prozent" and az["zitat"] == "Ausnützungsziffer max. 30 %",
           "Beleg wie live: 0.3, Etikett 'Prozent', Originaltext 'max. 30 %'")
    pruefe(arten("ausnuetzungsziffer_az", az) == [], "kein Befund: 30 % belegt 0.30")
    pruefe(pruefe_zone(zone) is zone, "die Zone kommt unveraendert zurueck (dasselbe Objekt)")
    m = ueber_match_zone(zone)
    pruefe(m["status"] == "gefunden" and m["zone"]["ausnuetzungsziffer_az"]["wert"] == 0.3,
           "match_zone liefert AZ 0.3")
    g = berechne_g1_fuer_fall(WEININGEN["modul1"], m["zone"], kantenklassifikation=WEININGEN["kantenklassifikation"])
    pruefe(g.get("gf_nach_ausnuetzungsziffer_m2") == 350.42,
           f"G1 rechnet weiter 0.30 x 1'168.1 = 350.42 m2: {g.get('gf_nach_ausnuetzungsziffer_m2')}")
    pruefe(not any("pruefbeduerftig" in h for h in g.get("kennzahl_hinweise") or []),
           "kein Plausibilitaetshinweis in G1")


def test_rheineck() -> None:
    print("\n=== 2. Rheineck: AZ 0.45 aus Art. 8 des altrechtlichen Reglements ===")
    az = RHEINECK["ausnuetzungsziffer_az"]
    pruefe(az["wert"] == 0.45 and az["artikel_referenz"] == "Art. 8 BauR" and az["einheit"] is None,
           "Beleg wie gespeichert: 0.45, Art. 8 BauR, ohne Einheit")
    pruefe(arten("ausnuetzungsziffer_az", az) == [], "kein Befund ('W2' ist ein Zonenkuerzel, keine Zahl)")
    pruefe(pruefe_zone(RHEINECK) is RHEINECK, "die ganze Zone W2 kommt unveraendert zurueck")
    m = ueber_match_zone(RHEINECK)
    pruefe(m["zone"]["ausnuetzungsziffer_az"]["wert"] == 0.45 and "plausibilitaet" not in m,
           "match_zone: AZ 0.45, keine Plausibilitaetsmeldung")


def test_falsche_einheit() -> None:
    print("\n=== 3. Falsche Einheit laeuft nicht als belastbarer Wert durch ===")
    pruefe("einheit_unpassend" in arten("grenzabstand_klein_m", kz(4, "%", "Grenzabstand 4 %")),
           "Grenzabstand in % -> einheit_unpassend")
    pruefe("einheit_unpassend" in arten("ausnuetzungsziffer_az", kz(0.4, "m", "AZ 0.4")),
           "AZ in Metern -> einheit_unpassend")
    pruefe("einheit_unpassend" in arten("gebaeudehoehe_m", kz(250, "cm", "Gebaeudehoehe 250 cm")),
           "Hoehe in cm (nicht umgerechnet) -> einheit_unpassend")
    pruefe("einheit_unpassend" in arten("strassenabstand_m", kz(120, "m²", "Strassenabstand 120 m²")),
           "Abstand in m2 -> einheit_unpassend")
    pruefe("einheit_widerspricht" in arten("grenzabstand_gross_m", kz(8, "m", "Grenzabstand gross 8 %")),
           "Einheit 'm', Originaltext nennt 8 % -> einheit_widerspricht")
    pruefe("einheit_mehrdeutig" in arten("ausnuetzungsziffer_az", kz(0.3, "Prozent", None)),
           "'Prozent' ohne Originaltext: 0.3 % oder 30 %? -> einheit_mehrdeutig")
    # Wirkung bis in G1: mit falscher Einheit traegt G1 keinen Abstand und keine AZ
    zone = copy.deepcopy(WEININGEN["zone"])
    zone["ausnuetzungsziffer_az"] = kz(0.3, "m", "Ausnützungsziffer 0.3 m")
    m = ueber_match_zone(zone)
    pruefe(m["zone"]["ausnuetzungsziffer_az"]["wert"] is None, "in der Rechenkopie: AZ zurueckgehalten (None)")
    g = berechne_g1_fuer_fall(WEININGEN["modul1"], m["zone"], kantenklassifikation=WEININGEN["kantenklassifikation"])
    pruefe("gf_nach_ausnuetzungsziffer_m2" not in g, "G1 rechnet keine AZ-Geschossflaeche")
    pruefe(any("pruefbeduerftig" in h and "ausnuetzungsziffer_az" in h for h in g.get("kennzahl_hinweise") or []),
           "G1-Hinweis nennt die Kennzahl als pruefbeduerftig")


def test_dezimal_prozent() -> None:
    print("\n=== 4. Dezimal-/Prozentfehler werden erkannt ===")
    pruefe(arten("ausnuetzungsziffer_az", kz(70, "%", "Ausnützungsziffer max. 70 %")) == ["prozent_nicht_umgerechnet"],
           "Birmensdorf: 'max. 70 %' als 70 -> prozent_nicht_umgerechnet")
    pruefe(arten("ausnuetzungsziffer_az", kz(20.0, "%", "Ausnützungsziffer % max. 20")) == ["prozent_nicht_umgerechnet"],
           "Russikon: 'Ausnuetzungsziffer % max. 20' als 20 -> prozent_nicht_umgerechnet")
    pruefe(arten("ausnuetzungsziffer_az", kz(30, None, "Ausnützungsziffer max. 30 %")) == ["prozent_nicht_umgerechnet"],
           "'max. 30 %' als Verhaeltniszahl 30 (ohne Einheit) -> prozent_nicht_umgerechnet")
    pruefe(arten("grenzabstand_klein_m", kz(30, "m", "Grenzabstand klein max. 0.3 m")) == ["dezimalfehler"],
           "'max. 0.3 m' als Abstand 30 m -> dezimalfehler")
    pruefe(arten("gesamthoehe_m", kz(1.05, "m", "Gesamthöhe 10.5 m")) == ["dezimalfehler"],
           "'10.5 m' als 1.05 m -> dezimalfehler")
    pruefe(arten("ausnuetzungsziffer_az", kz(4.5, None, "Ausnützungsziffer 0.45")) == ["dezimalfehler"],
           "'0.45' als 4.5 -> dezimalfehler")
    pruefe(arten("grenzabstand_klein_m", kz(400, "m", "Grenzabstand klein 400 cm")) == ["zentimeter_nicht_umgerechnet"],
           "'400 cm' als 400 m -> zentimeter_nicht_umgerechnet")
    pruefe(arten("grenzabstand_klein_m", kz(5, "m", "Grenzabstand klein 4 m")) == ["originaltext_widerspricht"],
           "Originaltext 4 m, Wert 5 -> originaltext_widerspricht")
    pruefe(arten("vollgeschosse_max", kz(2.5, "Geschosse", "max. 2.5 Vollgeschosse")) == ["keine_ganze_zahl"],
           "2.5 Vollgeschosse -> keine_ganze_zahl")
    pruefe(arten("grenzabstand_klein_m", kz(-4, "m", None)) == ["negativ"], "negativer Abstand -> negativ")
    pruefe(arten("gebaeudehoehe_m", kz(9, "m", "Gebaeudehoehe 9 m", confidence="nicht_bestimmbar"))
           == ["status_widerspricht"], "Wert trotz 'nicht bestimmbar' -> status_widerspricht")
    zone = {"zonenbezeichnung": "W2", "grenzabstand_klein_m": kz(8, "m", "klein 8 m"),
            "grenzabstand_gross_m": kz(4, "m", "gross 4 m")}
    g = pruefe_zone(zone)
    pruefe(g["grenzabstand_klein_m"]["wert"] is None and g["grenzabstand_gross_m"]["wert"] is None,
           "grosser Grenzabstand kleiner als der kleine -> beide zurueckgehalten")


def test_ungewoehnlich_aber_belegt() -> None:
    print("\n=== 5. Ungewoehnlich, aber belegt: wird NICHT verworfen ===")
    faelle = [
        ("ausnuetzungsziffer_az", kz(2.8, None, "Ausnützungsziffer 2.8")),
        ("ausnuetzungsziffer_az", kz(0.05, None, "Ausnützungsziffer 0.05")),
        ("ausnuetzungsziffer_az", kz(1.5, "%", "Ausnützungsziffer max. 150 %")),
        ("ausnuetzungsziffer_az", kz(20.0, None, None)),  # ohne Beleg: nichts zu widersprechen
        ("ueberbauungsziffer_uz", kz(0.95, None, "Überbauungsziffer 95 %")),
        ("baumassenziffer_bmz", kz(14.0, "m³/m²", "Baumassenziffer 14 m3/m2")),
        ("gesamthoehe_m", kz(60, "m", "Gesamthöhe 60 m")),
        ("grenzabstand_klein_m", kz(0, "m", "Grenzbau zulässig, Grenzabstand 0 m")),
        ("strassenabstand_m", kz(0.5, "m", "Strassenabstand 0.50 m")),
        ("grenzabstand_klein_m", kz(4.0, "m", "Grenzabstand 400 cm")),
        ("vollgeschosse_max", kz(8, "Geschosse", "max. 8 Vollgeschosse")),
        ("anrechenbare_geschossflaechenziffer_abgf", kz(0.6, "oberirdische Geschossflächenziffer",
                                                        "Die oberirdische Geschossflächenziffer beträgt: a. in der FB 0,6;")),
        ("grenzabstand_klein_m", kz(5.0, "m", "GA klein min. 5.0 m 2)")),
        ("ausnuetzungsziffer_az", kz(1250.0 / 1000, None, "AZ 1.25 gemäss Art. 12 Abs. 3")),
    ]
    for feld, k in faelle:
        pruefe(arten(feld, k) == [], f"{feld} = {k['wert']} ({k['einheit']}, '{k['zitat']}') bleibt")
    zone = {"zonenbezeichnung": "Hochhauszone H", "ausnuetzungsziffer_az": kz(2.8, None, "Ausnützungsziffer 2.8"),
            "gesamthoehe_m": kz(60, "m", "Gesamthöhe 60 m")}
    pruefe(pruefe_zone(zone) is zone, "Zone mit AZ 2.8 und 60 m Hoehe: unveraendert, wird gerechnet")
    pruefe(zahlen_im_text("Art. 22 Abs. 2 W2 Grenzabstand 1'200 m") == [(1200.0, "m")],
           "Artikel, Absatz und Zonenkuerzel sind keine Masse; 1'200 wird gelesen")


def test_beleg_bleibt() -> None:
    print("\n=== 6. Originaltext und Quelle gehen nie verloren ===")
    original = kz(70, "%", "Ausnützungsziffer max. 70 %",
                  bedingungen=[{"bedingung_text": "Arealueberbauung", "wert_unter_bedingung": 80,
                                "artikel_referenz": "Art. 9"}],
                  unklarheit="Tabelle im Anhang")
    zone = {"zonenbezeichnung": "Z3/70 % (Dreigeschossige Zentrumszone)", "ausnuetzungsziffer_az": original,
            "gesamthoehe_m": kz(12, "m", "Gesamthöhe 12 m")}
    vorher = copy.deepcopy(zone)
    m = ueber_match_zone(zone)
    g = m["zone"]["ausnuetzungsziffer_az"]
    pruefe(zone == vorher, "die Modul-2-Zone selbst ist unveraendert (nichts ueberschrieben)")
    pruefe(g["wert"] is None and g["wert_extrahiert"] == 70, "Rechenkopie: wert None, wert_extrahiert 70 (nicht 0.70)")
    for feld in ("zitat", "artikel_referenz", "quelle_dokument", "einheit", "confidence", "bedingungen", "unklarheit"):
        pruefe(g[feld] == original[feld], f"{feld} erhalten: {original[feld]!r}")
    p = g["plausibilitaet"]
    pruefe(p["status"] == STATUS_PRUEFBEDUERFTIG and p["in_rechnung"] is False
           and p["befunde"][0]["art"] == "prozent_nicht_umgerechnet", "Status pruefbeduerftig, nicht in der Rechnung")
    pruefe(m["zone"]["gesamthoehe_m"] is zone["gesamthoehe_m"], "die unauffaellige Gesamthoehe bleibt unberuehrt")
    pruefe(m["zone"]["gesamthoehe_m"]["wert"] == 12, "und wird weiter gerechnet")


def main() -> None:
    test_weiningen()
    test_rheineck()
    test_falsche_einheit()
    test_dezimal_prozent()
    test_ungewoehnlich_aber_belegt()
    test_beleg_bleibt()
    print()
    if _fehler:
        print(f"REGLEMENT-PLAUSIBILITAET: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE REGLEMENT-PLAUSIBILITAETS-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

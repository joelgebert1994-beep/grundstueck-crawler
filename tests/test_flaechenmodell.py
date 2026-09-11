"""
Regressionstests fuer Stufe 3: die Bruecke BAURECHT -> FLAECHE -> WOHNUNG.

Vollstaendig OFFLINE -- reine Berechnung auf konstruierten G1-Ergebnissen.

Geprueft wird, was fachlich schiefgehen kann:

  * Es darf keinen eingebauten Prozentsatz geben, der stillschweigend wirkt.
    Jede Annahme traegt Herkunft und Begruendung, und eine Benutzerannahme
    hat Vorrang vor dem Systemvorschlag.
  * Die SIA-416-Kaskade muss der Norm-Gliederung folgen (GF = NGF + KF,
    NGF = NF + VF + FF, NF = HNF + NNF) und darf sich nicht ueber zwei
    widersprechende Wege gleichzeitig herleiten lassen.
  * Geschosshoehe, lichte Raumhoehe und konstruktive Hoehe duerfen nicht
    vermischt und nicht mit der baurechtlichen Gebaeudehoehe verwechselt
    werden.
  * Untergeschoss, Keller, Tiefgarage und Technik sind weder Geschossflaeche
    noch Wohnflaeche.
  * BMZ ist ein VOLUMENmass: das baurechtlich zulaessige Volumen und das
    geometrisch umsetzbare sind zwei verschiedene Groessen.
  * Gelten mehrere Regeln gleichzeitig, muss die effektiv limitierende
    ausgewiesen sein.
  * Fehlt eine Grundlage, ist das Ergebnis nicht_bestimmbar MIT Ursache --
    nie eine erfundene Zahl.

CLI: python -m tests.test_flaechenmodell
"""

from __future__ import annotations

import sys

from potenzial_engine.flaechenmodell import (
    GESCHOSS_ATTIKA,
    GESCHOSS_TIEFGARAGE,
    GESCHOSS_UNTERGESCHOSS,
    HERKUNFT_BENUTZERANNAHME,
    HERKUNFT_SYSTEMANNAHME,
    PROFIL_WOHNUNGSBAU_MFH,
    Annahme,
    FlaechenmodellError,
    Hoehenmodell,
    WohnungstypVorgabe,
    annahmenprofil,
    berechne_flaechen_und_wohnungen,
    berechne_wohnungen,
    leite_geschossaufbau_ab,
    volumenbetrachtung,
)
from potenzial_engine.sia416_flaechen import (
    STATUS_NICHT_BESTIMMBAR,
    Modellannahme,
    berechne_sia416_kaskade,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def g1(**felder):
    """Ein G1-Ergebnis, wie baubereich.PotenzialErgebnis.to_dict() es liefert."""
    basis = {
        "parzellenflaeche_m2": 1500.0,
        "anrechenbare_landflaeche_m2": 1380.0,
        "fussabdruck_m2": 300.0,
        "fussabdruck_limitiert_durch": "ueberbauungsziffer",
        "fussabdruck_kandidaten": {"geometrie": 420.0, "ueberbauungsziffer": 300.0},
        "geschosszahl": 4,
        "geschosszahl_limitiert_durch": "vollgeschosse",
        "geschosszahl_kandidaten": {"vollgeschosse": 4, "hoehe": 4},
        "geschossflaeche_m2": 1104.0,
        "geschossflaeche_limitiert_durch": "ausnuetzung_az",
        "geschossflaeche_kandidaten": {"fussabdruck_x_geschosse": 1200.0, "ausnuetzung_az": 1104.0},
    }
    basis.update(felder)
    return basis


# ---------------------------------------------------------------------------
# 1. Annahmen: Herkunft, Vorrang, keine stillen Defaults
# ---------------------------------------------------------------------------

def test_annahmen() -> None:
    print("=== Annahmen: Herkunft sichtbar, Benutzer hat Vorrang ===")
    profil = annahmenprofil()
    pruefe(all(a.herkunft == HERKUNFT_SYSTEMANNAHME for a in profil.values()),
           "alle Profilwerte sind als Systemannahme gekennzeichnet")
    pruefe(all(a.begruendung.strip() for a in profil.values()),
           "jede Annahme traegt eine Begruendung")
    pruefe(all(a.referenzbereich for a in profil.values()),
           "jede Annahme nennt den Bereich, in dem sie ueblicherweise liegt")

    geaendert = annahmenprofil(benutzerwerte={"kf_anteil_an_gf": 0.12})
    kf = geaendert["kf_anteil_an_gf"]
    pruefe(kf.wert == 0.12, f"Benutzerwert wird uebernommen ({kf.wert})")
    pruefe(kf.herkunft == HERKUNFT_BENUTZERANNAHME, "und als Benutzerannahme gekennzeichnet")
    pruefe("Systemvorschlag war 0.15" in kf.begruendung,
           f"der ueberschriebene Systemvorschlag bleibt sichtbar ({kf.begruendung[:60]})")
    pruefe(geaendert["hnf_anteil_an_nf"].herkunft == HERKUNFT_SYSTEMANNAHME,
           "nicht geaenderte Werte bleiben Systemannahme")

    geworfen = None
    try:
        annahmenprofil(benutzerwerte={"gibt_es_nicht": 0.5})
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None,
           "ein unbekannter Schluessel wird abgelehnt, statt ins Leere zu laufen")

    geworfen = None
    try:
        Annahme(schluessel="x", wert=0.5, einheit="Anteil", begruendung="  ")
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "eine Annahme ohne Begruendung wird abgelehnt")
    print()


# ---------------------------------------------------------------------------
# 2. SIA-416-Kaskade nach der Norm-Gliederung
# ---------------------------------------------------------------------------

def test_sia_gliederung() -> None:
    print("=== SIA 416: GF = NGF + KF, NGF = NF + VF + FF, NF = HNF + NNF ===")
    r = berechne_sia416_kaskade(
        1000.0,
        kf_anteil_an_gf=Modellannahme(0.15, "Testannahme KF"),
        vf_ff_anteil_an_ngf=Modellannahme(0.14, "Testannahme VF/FF"),
        hnf_anteil_an_nf=Modellannahme(0.90, "Testannahme HNF"),
    )
    kf, ngf = r.konstruktionsflaeche_kf.wert, r.nettogeschossflaeche_ngf.wert
    vf_ff, nf = r.verkehrs_und_funktionsflaeche_vf_ff.wert, r.nutzflaeche_nf.wert
    hnf, nnf = r.hauptnutzflaeche_hnf.wert, r.nebennutzflaeche_nnf.wert

    pruefe(kf == 150.0, f"KF = 15 % von 1000 = 150.0 ({kf})")
    pruefe(ngf == 850.0, f"NGF = GF - KF = 850.0 ({ngf})")
    pruefe(abs((ngf + kf) - 1000.0) < 0.05, "GF = NGF + KF geht auf")
    pruefe(vf_ff == 119.0, f"VF+FF = 14 % von 850 = 119.0 ({vf_ff})")
    pruefe(nf == 731.0, f"NF = NGF - (VF+FF) = 731.0 ({nf})")
    pruefe(abs((nf + vf_ff) - ngf) < 0.05, "NGF = NF + VF + FF geht auf")
    pruefe(abs((hnf + nnf) - nf) < 0.05, f"NF = HNF + NNF geht auf ({hnf} + {nnf} = {nf})")

    # Der pauschale Weg laesst die NGF ehrlich offen.
    p = berechne_sia416_kaskade(1000.0, nf_anteil_an_gf=Modellannahme(0.85, "Pauschal"))
    pruefe(p.nutzflaeche_nf.wert == 850.0, "pauschaler Weg liefert die NF weiterhin")
    pruefe(p.nettogeschossflaeche_ngf.status == STATUS_NICHT_BESTIMMBAR,
           "NGF bleibt dabei nicht_bestimmbar")
    pruefe("KF und VF/FF" in (p.nettogeschossflaeche_ngf.unklarheit or ""),
           "mit konkreter Ursache statt nur einem leeren Feld")

    # Zwei widersprechende Herleitungen derselben NF -> Fehler.
    geworfen = None
    try:
        berechne_sia416_kaskade(
            1000.0,
            nf_anteil_an_gf=Modellannahme(0.85, "pauschal"),
            kf_anteil_an_gf=Modellannahme(0.15, "detailliert"),
            vf_ff_anteil_an_ngf=Modellannahme(0.14, "detailliert"),
        )
    except ValueError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "pauschal und detailliert gleichzeitig wird abgelehnt")

    geworfen = None
    try:
        berechne_sia416_kaskade(1000.0, kf_anteil_an_gf=Modellannahme(0.15, "nur halb"))
    except ValueError as exc:
        geworfen = exc
    pruefe(geworfen is not None,
           "der detaillierte Weg mit nur einer der beiden Annahmen wird abgelehnt")
    print()


# ---------------------------------------------------------------------------
# 3. Hoehenmodell
# ---------------------------------------------------------------------------

def test_hoehenmodell() -> None:
    print("=== Hoehen: Geschosshoehe, lichte Raumhoehe und konstruktive Hoehe getrennt ===")
    annahmen = annahmenprofil()
    h = Hoehenmodell(annahmen["geschosshoehe_m"], annahmen["lichte_raumhoehe_m"])
    pruefe(h.geschosshoehe_m.wert == 3.00, "Geschosshoehe 3.00 m")
    pruefe(h.lichte_raumhoehe_m.wert == 2.50, "lichte Raumhoehe 2.50 m")
    pruefe(h.konstruktive_hoehe_m == 0.50, f"konstruktive Hoehe = Differenz = 0.50 m ({h.konstruktive_hoehe_m})")
    pruefe("Gesamthoehe" in h.to_dict()["abgrenzung"],
           "die Abgrenzung zur baurechtlichen Gebaeude-/Gesamthoehe steht im Ergebnis")

    geworfen = None
    try:
        Hoehenmodell(
            annahmen["geschosshoehe_m"],
            annahmen["lichte_raumhoehe_m"].mit_benutzerwert(3.20),
        )
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "lichte Raumhoehe >= Geschosshoehe wird abgelehnt")

    knapp = Hoehenmodell(
        annahmen["geschosshoehe_m"],
        annahmen["lichte_raumhoehe_m"].mit_benutzerwert(2.90),
    )
    pruefe(any("Konstruktive Hoehe" in hh for hh in knapp.hinweise),
           "eine unrealistisch duenne Decke wird angemerkt, nicht korrigiert")
    print()


# ---------------------------------------------------------------------------
# 4. Geschossaufbau
# ---------------------------------------------------------------------------

def test_geschossaufbau() -> None:
    print("=== Geschosse: nicht jede Flaeche ist Geschoss- oder Wohnflaeche ===")
    aufbau = leite_geschossaufbau_ab(g1())
    pruefe(len(aufbau.geschosse) == 4, f"4 Geschosse aus G1 ({len(aufbau.geschosse)})")
    pruefe(aufbau.geschosse[0].art == "erdgeschoss", "das unterste ist das Erdgeschoss")
    pruefe(aufbau.vollgeschosse == 4, f"4 Vollgeschosse ({aufbau.vollgeschosse})")
    pruefe(aufbau.geschossflaeche_m2 == 1200.0, f"4 x 300 m2 = 1200 m2 ({aufbau.geschossflaeche_m2})")
    pruefe(any("Attikageschoss" in o for o in aufbau.offene_punkte),
           "dass Modul 2 Attika/UG nicht strukturiert liefert, ist als offener Punkt vermerkt")

    mit_zusatz = leite_geschossaufbau_ab(g1(), zusaetzliche_geschosse=[
        {"art": GESCHOSS_ATTIKA, "bezeichnung": "Attika", "flaeche_m2": 180.0,
         "begruendung": "Zone laesst Attika zu (Benutzerangabe)"},
        {"art": GESCHOSS_UNTERGESCHOSS, "bezeichnung": "UG", "flaeche_m2": 300.0,
         "begruendung": "Keller und Technik"},
        {"art": GESCHOSS_TIEFGARAGE, "bezeichnung": "TG", "flaeche_m2": 420.0,
         "begruendung": "Einstellhalle"},
    ])
    nach_art = {gg.bezeichnung: gg for gg in mit_zusatz.geschosse}
    pruefe(nach_art["Attika"].zaehlt_zur_geschossflaeche is True, "Attika zaehlt zur Geschossflaeche")
    pruefe(nach_art["Attika"].zaehlt_als_vollgeschoss is False, "Attika ist kein Vollgeschoss")
    pruefe(nach_art["Attika"].wohnnutzung_moeglich is True, "Attika ist bewohnbar")
    pruefe(nach_art["UG"].zaehlt_zur_geschossflaeche is False, "Untergeschoss zaehlt NICHT zur Geschossflaeche")
    pruefe(nach_art["UG"].wohnnutzung_moeglich is False, "Untergeschoss ist keine Wohnflaeche")
    pruefe(nach_art["TG"].zaehlt_zur_geschossflaeche is False, "Tiefgarage zaehlt NICHT zur Geschossflaeche")
    pruefe(mit_zusatz.vollgeschosse == 4, f"Vollgeschosse bleiben 4 ({mit_zusatz.vollgeschosse})")
    pruefe(mit_zusatz.geschossflaeche_m2 == 1380.0,
           f"Geschossflaeche = 1200 + 180 Attika, ohne UG und TG ({mit_zusatz.geschossflaeche_m2})")
    pruefe(any("Nicht zur Geschossflaeche gezaehlt" in h for h in mit_zusatz.hinweise),
           "die ausgeschlossenen Geschosse sind namentlich benannt")

    ohne = leite_geschossaufbau_ab(g1(geschosszahl=None, geschossflaeche_m2=None))
    pruefe(ohne.geschossflaeche_m2 is None, "ohne Geschosszahl keine Geschossflaeche")
    pruefe(bool(ohne.offene_punkte), "und ein benannter offener Punkt statt einer Annahme")

    geworfen = None
    try:
        leite_geschossaufbau_ab(g1(), zusaetzliche_geschosse=[{"art": "dachterrasse"}])
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "eine unbekannte Geschossart wird abgelehnt")
    print()


# ---------------------------------------------------------------------------
# 5. Volumen (BMZ)
# ---------------------------------------------------------------------------

def test_volumen() -> None:
    print("=== BMZ: zulaessiges Volumen gegen geometrisch umsetzbares ===")
    hoehe = annahmenprofil()["geschosshoehe_m"]

    ohne = volumenbetrachtung(g1(), None, hoehe)
    pruefe(ohne["gilt"] is False, "ohne BMZ gilt keine Volumenbegrenzung")

    # BMZ 4.0 x 1380 m2 = 5520 m3; Geometrie 300 x 4 x 3.0 = 3600 m3 -> Geometrie bindet.
    v = volumenbetrachtung(g1(), 4.0, hoehe)
    pruefe(v["zulaessiges_volumen_m3"] == 5520.0, f"zulaessig = 4.0 x 1380 = 5520 m3 ({v['zulaessiges_volumen_m3']})")
    pruefe(v["geometrisch_moegliches_volumen_m3"] == 3600.0,
           f"geometrisch = 300 x 4 x 3.0 = 3600 m3 ({v['geometrisch_moegliches_volumen_m3']})")
    pruefe(v["bindend"] == "geometrie", f"die Geometrie bindet ({v['bindend']})")
    pruefe(v["massgebendes_volumen_m3"] == 3600.0, "massgebend ist der kleinere Wert")

    # BMZ 2.0 x 1380 = 2760 m3 < 3600 m3 -> das Baurecht bindet.
    v2 = volumenbetrachtung(g1(), 2.0, hoehe)
    pruefe(v2["bindend"] == "baurecht", f"bei knapper BMZ bindet das Baurecht ({v2['bindend']})")
    pruefe(v2["massgebendes_volumen_m3"] == 2760.0, "massgebend ist wieder der kleinere Wert")

    v3 = volumenbetrachtung(g1(fussabdruck_m2=None), 2.0, hoehe)
    pruefe(v3["geometrisch_moegliches_volumen_m3"] is None, "ohne Fussabdruck kein geometrisches Volumen")
    pruefe("nicht bestimmen" in v3.get("geometrisch_grund", ""), "mit benannter Ursache")
    print()


# ---------------------------------------------------------------------------
# 6. Wohnungen
# ---------------------------------------------------------------------------

def test_wohnungen() -> None:
    print("=== Wohnungen: Anteile oder Stueckzahlen, keine Bruchteile ===")
    mix = [
        WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.2),
        WohnungstypVorgabe("3.5 Zi", 88.0, anteil=0.5),
        WohnungstypVorgabe("4.5 Zi", 112.0, anteil=0.3),
    ]
    r = berechne_wohnungen(900.0, mix, "Testmix")
    pruefe(r["eingabeart"] == "anteile", "Anteilseingabe erkannt")
    pruefe(r["mittlere_wohnungsgroesse_im_mix_m2"] == 90.0,
           f"mittlere Groesse 0.2*62+0.5*88+0.3*112 = 90.0 ({r['mittlere_wohnungsgroesse_im_mix_m2']})")
    pruefe(r["anzahl_wohnungen"] == 10, f"900 / 90 = 10 Wohnungen ({r['anzahl_wohnungen']})")
    pruefe(all(isinstance(t["anzahl"], int) for t in r["typen"]), "nur ganze Wohnungen je Typ")
    pruefe(sum(t["anzahl"] for t in r["typen"]) == r["anzahl_wohnungen"],
           "die Typenzahlen summieren sich exakt auf die Gesamtzahl")
    pruefe(r["belegte_flaeche_m2"] <= 900.0,
           f"die belegte Flaeche passt in die vorhandene ({r['belegte_flaeche_m2']} <= 900.0)")

    nach_stueck = berechne_wohnungen(900.0, [
        WohnungstypVorgabe("2.5 Zi", 62.0, anzahl=6),
        WohnungstypVorgabe("3.5 Zi", 88.0, anzahl=8),
    ], "Stueckzahlen")
    pruefe(nach_stueck["eingabeart"] == "stueckzahlen", "Stueckzahleingabe erkannt")
    pruefe(nach_stueck["anzahl_wohnungen"] == 14, "6 + 8 = 14 Wohnungen")
    pruefe(nach_stueck["benoetigte_flaeche_m2"] == 1076.0, "6*62 + 8*88 = 1076 m2")
    pruefe(nach_stueck["passt"] is False, "1076 m2 passen nicht in 900 m2 -- das wird gemeldet")
    pruefe(nach_stueck["differenz_m2"] == -176.0, f"Fehlbetrag 176 m2 ({nach_stueck['differenz_m2']})")

    ohne_mix = berechne_wohnungen(900.0, None)
    pruefe(ohne_mix["status"] == STATUS_NICHT_BESTIMMBAR, "ohne Mix keine Wohnungszahl")
    pruefe("Durchschnittswohnung" in ohne_mix["grund"],
           "es wird ausdruecklich keine Durchschnittswohnung unterstellt")

    ohne_flaeche = berechne_wohnungen(None, mix)
    pruefe(ohne_flaeche["status"] == STATUS_NICHT_BESTIMMBAR, "ohne Wohnflaeche keine Wohnungszahl")

    geworfen = None
    try:
        berechne_wohnungen(900.0, [
            WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.5),
            WohnungstypVorgabe("3.5 Zi", 88.0, anzahl=4),
        ])
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "Anteile und Stueckzahlen gemischt wird abgelehnt")

    geworfen = None
    try:
        berechne_wohnungen(900.0, [WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.6)])
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "Anteile ungleich 1.0 werden nicht stillschweigend normalisiert")

    geworfen = None
    try:
        WohnungstypVorgabe("2.5 Zi", 62.0)
    except FlaechenmodellError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "weder Anteil noch Anzahl wird abgelehnt")
    print()


# ---------------------------------------------------------------------------
# 7. Gesamtrechnung und Rechenweg
# ---------------------------------------------------------------------------

def test_gesamtrechnung() -> None:
    print("=== Gesamtrechnung: Rechenweg, limitierende Groesse, Dynamik ===")
    mix = [
        WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.2),
        WohnungstypVorgabe("3.5 Zi", 88.0, anteil=0.5),
        WohnungstypVorgabe("4.5 Zi", 112.0, anteil=0.3),
    ]
    zone = {"baumassenziffer_bmz": {"wert": 4.0, "confidence": "hoch"}}
    r = berechne_flaechen_und_wohnungen(g1(), zone=zone, wohnungsmix=mix, wohnungsmix_begruendung="Testmix")

    schritte = {s["schritt"]: s for s in r["rechenweg"]}
    pruefe("Grundstuecksflaeche" in schritte, "der Rechenweg beginnt bei der Grundstuecksflaeche")
    pruefe(schritte["anrechenbare Grundstuecksflaeche"]["ausgang"] == 1380.0,
           "anrechenbare Flaeche 1380 m2 (1500 minus 120 Restriktion)")
    pruefe(schritte["Geschossflaeche GF"]["ausgang"] == 1104.0,
           "GF 1104 m2, wie von G1 geliefert")
    pruefe("ausnuetzung_az" in schritte["Geschossflaeche GF"]["operation"],
           f"der limitierende Parameter ist benannt ({schritte['Geschossflaeche GF']['operation']})")
    pruefe("fussabdruck_x_geschosse" in schritte["Geschossflaeche GF"]["herkunft"],
           "und die unterlegenen Kandidaten bleiben sichtbar")

    for feld in ("konstruktionsflaeche_kf", "nettogeschossflaeche_ngf", "nutzflaeche_nf",
                 "hauptnutzflaeche_hnf", "wohnflaeche_nwf"):
        pruefe(feld in schritte, f"Rechenweg enthaelt {feld}")
        pruefe(bool(schritte[feld]["herkunft"]), f"{feld} nennt seine Herkunft")

    pruefe(r["flaechen"]["wohnflaeche_nwf"]["wert"] is not None, "Wohnflaeche bestimmt")
    pruefe(r["wohnungen"]["anzahl_wohnungen"] > 0, f"Wohnungen abgeleitet ({r['wohnungen']['anzahl_wohnungen']})")
    pruefe(r["volumen"]["gilt"] is True, "die Volumenbetrachtung greift, weil eine BMZ gilt")

    # Dynamik: ein geaenderter Abzug muss sofort durchschlagen.
    strenger = berechne_flaechen_und_wohnungen(
        g1(), zone=zone, benutzerwerte={"kf_anteil_an_gf": 0.12},
        wohnungsmix=mix, wohnungsmix_begruendung="Testmix",
    )
    pruefe(strenger["flaechen"]["konstruktionsflaeche_kf"]["wert"] < r["flaechen"]["konstruktionsflaeche_kf"]["wert"],
           "kleinerer Konstruktionsanteil -> kleinere KF")
    pruefe(strenger["flaechen"]["wohnflaeche_nwf"]["wert"] > r["flaechen"]["wohnflaeche_nwf"]["wert"],
           "und damit mehr Wohnflaeche")
    pruefe(strenger["annahmen"]["kf_anteil_an_gf"]["herkunft"] == HERKUNFT_BENUTZERANNAHME,
           "die Aenderung ist als Benutzerannahme ausgewiesen")

    # Gemischte Nutzung: NWF wird echt kleiner als HNF.
    gemischt = berechne_flaechen_und_wohnungen(
        g1(), zone=zone, benutzerwerte={"nwf_anteil_an_hnf": 0.75}, wohnungsmix=mix,
    )
    pruefe(gemischt["flaechen"]["wohnflaeche_nwf"]["wert"] < gemischt["flaechen"]["hauptnutzflaeche_hnf"]["wert"],
           "bei gemischter Nutzung ist die Wohnflaeche kleiner als die HNF")

    # Ohne Wohnungsmix: Flaechen ja, Wohnungen ehrlich offen.
    ohne_mix = berechne_flaechen_und_wohnungen(g1(), zone=zone)
    pruefe(ohne_mix["flaechen"]["wohnflaeche_nwf"]["wert"] is not None,
           "ohne Mix stehen die Flaechen trotzdem")
    pruefe(ohne_mix["wohnungen"]["status"] == STATUS_NICHT_BESTIMMBAR,
           "die Wohnungszahl bleibt ohne Mix nicht_bestimmbar")

    # Ohne GF bricht die Kaskade sauber ab.
    ohne_gf = berechne_flaechen_und_wohnungen(
        g1(geschossflaeche_m2=None, geschossflaeche_limitiert_durch=None, geschossflaeche_kandidaten={}),
    )
    pruefe(ohne_gf["status"] == STATUS_NICHT_BESTIMMBAR, "ohne GF ist das Ergebnis nicht_bestimmbar")
    pruefe("Geschossflaeche" in ohne_gf["grund"], "mit konkreter Ursache")
    pruefe("flaechen" not in ohne_gf, "und ohne erfundene Flaechenwerte")
    print()


def test_mehrere_regeln_gleichzeitig() -> None:
    print("=== Mehrere Regeln gleichzeitig: die effektiv limitierende gilt ===")
    # AZ 0.80 auf 1380 m2 = 1104 m2; Geometrie 300 x 4 = 1200 m2 -> AZ bindet.
    az_bindet = berechne_flaechen_und_wohnungen(g1())
    schritt = next(s for s in az_bindet["rechenweg"] if s["schritt"] == "Geschossflaeche GF")
    pruefe(schritt["ausgang"] == 1104.0, "AZ begrenzt auf 1104 m2, nicht die Geometrie mit 1200 m2")
    pruefe("ausnuetzung_az" in schritt["operation"], "und das steht so im Rechenweg")

    # Umgekehrt: knappe Geometrie bindet trotz grosszuegiger AZ.
    geo_bindet = berechne_flaechen_und_wohnungen(g1(
        geschossflaeche_m2=1200.0,
        geschossflaeche_limitiert_durch="fussabdruck_x_geschosse",
        geschossflaeche_kandidaten={"fussabdruck_x_geschosse": 1200.0, "ausnuetzung_az": 1656.0},
    ))
    schritt2 = next(s for s in geo_bindet["rechenweg"] if s["schritt"] == "Geschossflaeche GF")
    pruefe("fussabdruck_x_geschosse" in schritt2["operation"],
           "jetzt bindet die Geometrie, und auch das ist benannt")
    pruefe("ausnuetzung_az" in schritt2["herkunft"],
           "das theoretische AZ-Limit bleibt als unterlegener Kandidat sichtbar")

    # UEZ gegen Geometrie beim Fussabdruck.
    fuss = next(s for s in az_bindet["rechenweg"] if s["schritt"] == "Fussabdruck")
    pruefe(fuss["ausgang"] == 300.0, "UEZ begrenzt den Fussabdruck auf 300 m2")
    pruefe("ueberbauungsziffer" in fuss["operation"], "die UEZ ist als limitierend benannt")
    pruefe("420.0" in fuss["herkunft"],
           "die geometrisch moeglichen 420 m2 bleiben als theoretisches Limit sichtbar")
    print()


def main() -> None:
    test_annahmen()
    test_sia_gliederung()
    test_hoehenmodell()
    test_geschossaufbau()
    test_volumen()
    test_wohnungen()
    test_gesamtrechnung()
    test_mehrere_regeln_gleichzeitig()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE FLAECHENMODELL-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

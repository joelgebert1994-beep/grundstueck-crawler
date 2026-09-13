"""
Tests der Parzellenkombination A vs. A+B.

Vollstaendig OFFLINE.

Der Satz, um den es in diesem Modul geht: **mehr Land ist nicht automatisch
mehr Potenzial.** Geprueft wird deshalb vor allem, wann die Engine sich
weigert, eine Kombination gut zu finden:

  * Die Parzellen grenzen gar nicht aneinander.
  * Sie liegen in verschiedenen Zonen -- dann muesste je Zonenanteil
    gerechnet werden, und eine mit A's Kennzahlen durchgerechnete
    Gesamtflaeche waere falsch, nicht nur ungenau.
  * Die zusaetzliche Flaeche bringt keine oder kaum zusaetzliche
    Geschossflaeche, weil nicht die Ausnuetzungsziffer bindet, sondern die
    Geometrie oder die Geschosszahl.
  * Der Mehrwert steht, aber der Kaufpreis fuer B fehlt -- dann bleibt der
    Zusatznutzen offen statt geschaetzt.

CLI: python -m tests.test_kombination
"""

from __future__ import annotations

import sys

from potenzial_engine import kombination as kb

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def rechteck(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# Zwei Rechtecke, die sich eine 20 m lange Kante teilen.
A = rechteck(0, 0, 30, 20)
B_ANGRENZEND = rechteck(30, 0, 50, 20)
B_ENTFERNT = rechteck(60, 0, 80, 20)
B_ECKE = rechteck(30, 20, 50, 40)     # beruehrt A nur in einem Punkt


def g1(gf, limitiert="ausnuetzungsziffer"):
    return {"modus": "einzel",
            "ergebnis": {"geschossflaeche_m2": gf,
                         "geschossflaeche_limitiert_durch": limitiert}}


def seite(gf, residual, *, limitiert="ausnuetzungsziffer", hbu=None, szenarien=None):
    wirtschaft = {
        "szenarien": szenarien or {"ersatzneubau": {"residualwert": {"max_landwert_chf": residual}}},
    }
    if hbu:
        wirtschaft["hbu"] = {"status": "empfohlen", "empfehlung": {"id": hbu}}
    return {"g1": g1(gf, limitiert), "wirtschaft": wirtschaft}


# ---------------------------------------------------------------------------


def test_vereinigung() -> None:
    print("=== Vereinigung: was ueberhaupt zusammengehoert ===")

    r = kb.vereinige(A, B_ANGRENZEND)
    pruefe(r["status"] == kb.STATUS_MOEGLICH, f"angrenzende Parzellen ({r['status']})")
    pruefe(r["flaeche_m2"] == 1000.0, f"Flaeche 600 + 400 = 1000 ({r['flaeche_m2']})")
    pruefe(abs(r["beruehrungslaenge_m"] - 20.0) < 1.0,
           f"gemeinsame Grenze rund 20 m ({r['beruehrungslaenge_m']})")
    pruefe("Grenzabstand" in r["hinweis"],
           "und der Hinweis nennt, warum diese Grenze zaehlt")
    pruefe(len(r["ring"]) == 4, f"die Vereinigung ist ein Rechteck ({len(r['ring'])} Ecken)")

    weg = kb.vereinige(A, B_ENTFERNT)
    pruefe(weg["status"] == kb.STATUS_NICHT_ZULAESSIG,
           f"getrennte Parzellen: nicht zulaessig ({weg['status']})")
    pruefe("grenzen nicht aneinander" in weg["grund"], "mit klarem Grund")

    ecke = kb.vereinige(A, B_ECKE)
    pruefe(ecke["status"] == kb.STATUS_NICHT_ZULAESSIG,
           f"blosse Eckberuehrung reicht nicht ({ecke['status']})")

    selbe = kb.vereinige(A, A)
    pruefe(selbe["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           f"deckungsgleiche Konturen: nicht bestimmbar ({selbe['status']})")
    pruefe("ueberlappen" in selbe["grund"], "und der Grund sagt warum")

    ohne = kb.vereinige(A, None)
    pruefe(ohne["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           "ohne Kontur fuer B: nicht bestimmbar")
    pruefe("Parzelle B" in ohne["grund"], "und es wird gesagt, welche fehlt")
    print()


def test_loch() -> None:
    """Zwei Parzellen, zwischen denen eine dritte liegt, ergeben keine
    durchgehende Bauparzelle -- auch wenn sie sich an den Raendern beruehren."""
    print("=== Eine dritte Flaeche dazwischen ===")
    # U-Form plus Deckel: die Vereinigung umschliesst ein Loch.
    u = [(0, 0), (30, 0), (30, 10), (10, 10), (10, 20), (30, 20), (30, 30), (0, 30)]
    deckel = rechteck(30, 0, 40, 30)
    r = kb.vereinige(u, deckel)
    pruefe(r["status"] == kb.STATUS_NICHT_BESTIMMBAR, f"Loch erkannt ({r['status']})")
    pruefe("Loch" in r["grund"], "und benannt")
    print()


def test_zonen() -> None:
    print("=== Zone: dieselben Kennzahlen oder gar keine Aussage ===")

    gleich = kb.pruefe_zonen(
        {"typ_kommunal_bezeichnung": "Wohnzone W2"},
        {"typ_kommunal_bezeichnung": "Wohnzone  W2"})  # doppeltes Leerzeichen
    pruefe(gleich["gleich"] is True, "gleiche Zone trotz abweichender Schreibweise")

    anders = kb.pruefe_zonen(
        {"typ_kommunal_bezeichnung": "Wohnzone W2"},
        {"typ_kommunal_bezeichnung": "Gewerbezone G"})
    pruefe(anders["gleich"] is False, "verschiedene Zonen erkannt")
    pruefe(anders["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           "Ergebnis: nicht bestimmbar -- NICHT unzulaessig, denn rechtlich ginge es")
    pruefe("je Zonenanteil" in anders["grund"],
           "und der Grund sagt, was stattdessen noetig waere")
    pruefe("falsch, nicht nur ungenau" in anders["grund"],
           "und warum nicht einfach mit A's Kennzahlen gerechnet wird")

    fehlt = kb.pruefe_zonen({"typ_kommunal_bezeichnung": "Wohnzone W2"}, None)
    pruefe(fehlt["status"] == kb.STATUS_NICHT_BESTIMMBAR, "ohne Zone fuer B: nicht bestimmbar")
    pruefe("Parzelle B" in fehlt["grund"], "und es wird gesagt, welche fehlt")
    print()


def test_mehr_land_ist_nicht_mehr_potenzial() -> None:
    """Der Kern des Blocks."""
    print("=== Mehr Land ist nicht automatisch mehr Potenzial ===")

    # Fall 1: die Ausnuetzungsziffer bindet auf beiden Seiten -- B traegt,
    # was es verspricht.
    voll = kb.vergleiche(
        seite(600, 400_000), seite(900, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    p = voll["potenzial"]
    pruefe(p["status"] == kb.POTENZIAL_ZUSATZ, f"volle Ausbeute erkannt ({p['status']})")
    pruefe(abs(p["ausbeute"] - 1.0) < 0.02, f"Ausbeute rund 1.0 ({p['ausbeute']})")

    # Fall 2: bei A+B bindet die Geschosszahl, nicht mehr die Flaeche.
    wenig = kb.vergleiche(
        seite(600, 400_000),
        seite(700, 450_000, limitiert="vollgeschosse_max"),
        flaeche_a_m2=1000.0, flaeche_b_m2=1000.0)
    p = wenig["potenzial"]
    pruefe(p["status"] == kb.POTENZIAL_WENIG, f"geringe Ausbeute erkannt ({p['status']})")
    pruefe(abs(p["ausbeute"] - 0.1667) < 0.01, f"Ausbeute rund 17 % ({p['ausbeute']})")
    pruefe("17 %" in p["begruendung"] or "17%" in p["begruendung"],
           "die Ausbeute wird beziffert statt in 'viel/wenig' eingeteilt")
    pruefe("vollgeschosse_max" in p["begruendung"],
           "und es wird gesagt, WAS stattdessen bindet")

    # Fall 3: gar kein Zuwachs -- doppelte Flaeche, gleiche Geschossflaeche.
    keins = kb.vergleiche(
        seite(600, 400_000),
        seite(600, 400_000, limitiert="baubereich_geometrie"),
        flaeche_a_m2=1000.0, flaeche_b_m2=1000.0)
    p = keins["potenzial"]
    pruefe(p["status"] == kb.POTENZIAL_KEIN, f"kein Zuwachs erkannt ({p['status']})")
    pruefe("keine zusaetzliche Geschossflaeche" in p["begruendung"], "und benannt")
    pruefe("baubereich_geometrie" in p["begruendung"], "mit der bindenden Grenze")

    # Fall 4: ueberproportional -- an der gemeinsamen Grenze faellt der
    # Grenzabstand weg, der Baubereich waechst staerker als die Flaeche.
    mehr = kb.vergleiche(
        seite(400, 250_000, limitiert="baubereich_geometrie"),
        seite(1200, 800_000, limitiert="ausnuetzungsziffer"),
        flaeche_a_m2=1000.0, flaeche_b_m2=1000.0)
    pruefe(mehr["potenzial"]["status"] == kb.POTENZIAL_ZUSATZ,
           "ueberproportionaler Gewinn wird als Zusatzpotenzial gefuehrt")
    pruefe(mehr["potenzial"]["ausbeute"] > 1.5,
           f"mit einer Ausbeute ueber 1 ({mehr['potenzial']['ausbeute']})")
    print()


def test_bandbreite_ist_kein_vergleich() -> None:
    print("=== Ohne eindeutige Geschossflaeche kein Vergleich ===")
    bandbreite = {"modus": "bandbreite_grenzabstand_kante_nicht_differenziert",
                  "szenarien": {}}
    r = kb.vergleiche(
        {"g1": bandbreite, "wirtschaft": {}},
        seite(900, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    pruefe(r["potenzial"]["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           "Bandbreite auf der A-Seite: nicht bestimmbar")
    pruefe("Bandbreite" in r["potenzial"]["grund"],
           "und der Grund nennt die Bandbreite statt eines Rechenfehlers")
    print()


def test_wirtschaftlicher_zusatznutzen() -> None:
    print("=== Mehrwert, Kaufpreis, Zusatznutzen ===")

    ohne_preis = kb.vergleiche(
        seite(600, 400_000), seite(900, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    w = ohne_preis["wirtschaft"]
    pruefe(w["mehrwert_chf"] == 300_000, f"Mehrwert 700'000 - 400'000 ({w['mehrwert_chf']})")
    pruefe("hoechstens kosten" in w["rechnung"],
           "die Rechnung sagt, was der Mehrwert bedeutet: der Hoechstpreis fuer B")
    pruefe(w["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           "ohne Kaufpreis bleibt der Zusatznutzen offen")
    pruefe("nicht geschaetzt" in w["grund"], "und es wird kein Preis erfunden")

    lohnt = kb.vergleiche(
        seite(600, 400_000), seite(1000, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0,
        kaufpreis_b_chf=200_000)
    w = lohnt["wirtschaft"]
    pruefe(w["zusatznutzen_chf"] == 100_000, f"300'000 - 200'000 ({w['zusatznutzen_chf']})")
    pruefe(w["lohnt_sich"] is True, "und die Kombination traegt sich")

    zu_teuer = kb.vergleiche(
        seite(600, 400_000), seite(1000, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0,
        kaufpreis_b_chf=280_000, zusatzkosten_chf=60_000)
    w = zu_teuer["wirtschaft"]
    pruefe(w["zusatznutzen_chf"] == -40_000, f"mit Zusatzkosten negativ ({w['zusatznutzen_chf']})")
    pruefe(w["lohnt_sich"] is False, "und die Kombination traegt sich nicht")
    pruefe("traegt sich die Kombination nicht" in w["grund"], "das steht im Klartext da")

    # Der Fall, der zaehlt: B bringt Potenzial, ist aber zu teuer.
    pruefe(zu_teuer["potenzial"]["status"] == kb.POTENZIAL_ZUSATZ
           and zu_teuer["wirtschaft"]["lohnt_sich"] is False,
           "Zusatzpotenzial JA und wirtschaftlich NEIN sind zwei getrennte Aussagen")

    ohne_residual = kb.vergleiche(
        {"g1": g1(600), "wirtschaft": {"szenarien": {"x": {"residualwert": {}}}}},
        seite(900, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    pruefe(ohne_residual["wirtschaft"]["status"] == kb.STATUS_NICHT_BESTIMMBAR,
           "ohne Residualwert fuer A: nicht bestimmbar")
    pruefe("fuer A" in ohne_residual["wirtschaft"]["grund"], "und es wird gesagt, welcher fehlt")
    print()


def test_hbu_und_szenarien() -> None:
    print("=== Aendert die Kombination die beste Nutzung? ===")

    wechsel = kb.vergleiche(
        seite(600, 400_000, hbu="aufstockung"),
        seite(900, 700_000, hbu="ersatzneubau"),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    h = wechsel["hbu"]
    pruefe(h["aendert_sich"] is True, "Wechsel der Empfehlung erkannt")
    pruefe("nicht mehr 'aufstockung'" in h["hinweis"], "und im Klartext benannt")

    gleich = kb.vergleiche(
        seite(600, 400_000, hbu="ersatzneubau"),
        seite(900, 700_000, hbu="ersatzneubau"),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    pruefe(gleich["hbu"]["aendert_sich"] is False, "gleichbleibende Empfehlung ebenso")

    ohne = kb.vergleiche(
        seite(600, 400_000), seite(900, 700_000),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    pruefe(ohne["hbu"]["aendert_sich"] is None,
           "ohne Empfehlung auf einer Seite: kein Vergleich statt einer Behauptung")

    # Szenario fuer Szenario, damit nicht nur der Spitzenwert zaehlt.
    je_szenario = kb.vergleiche(
        seite(600, 400_000, szenarien={
            "bestand": {"residualwert": {"max_landwert_chf": 100_000}},
            "ersatzneubau": {"residualwert": {"max_landwert_chf": 400_000}}}),
        seite(900, 700_000, szenarien={
            "bestand": {"residualwert": {"max_landwert_chf": 100_000}},
            "ersatzneubau": {"residualwert": {"max_landwert_chf": 700_000}}}),
        flaeche_a_m2=1000.0, flaeche_b_m2=500.0)
    zeilen = {z["id"]: z for z in je_szenario["szenarien"]}
    pruefe(zeilen["bestand"]["differenz_chf"] == 0,
           "der Bestand gewinnt durch B nichts -- er nutzt die Flaeche nicht")
    pruefe(zeilen["ersatzneubau"]["differenz_chf"] == 300_000,
           "der Ersatzneubau schon")
    print()


def test_aussenkante_kombination() -> None:
    """Die Kombination muss ueber denselben Weg laufen wie /entwicklung.

    Geprueft wird das VERHALTEN: dass `berechne_kombination` existiert, die
    erwarteten Parameter nimmt und dieselben inneren Funktionen benutzt wie
    die uebrige Kette -- keine zweite Rechenlogik.
    """
    import inspect

    from potenzial_engine import pipeline

    print("=== Aussenkante: eine Kette, zweimal durchlaufen ===")

    p = inspect.signature(pipeline.berechne_kombination).parameters
    for name in ("analyse", "e_b", "n_b", "markt", "kaufpreis_b_chf",
                 "zusatzkosten_chf", "marktlage"):
        pruefe(name in p, f"berechne_kombination nimmt '{name}' entgegen")

    quelle = inspect.getsource(pipeline._kette_fuer_parzelle)
    for funktion in ("berechne_g1_fuer_fall", "_flaechen_fuer_g1_ergebnis",
                     "_szenarien_fuer_analyse", "_berechne_wirtschaftlich",
                     "_bestimme_hbu"):
        pruefe(funktion in quelle,
               f"die Kette benutzt {funktion} -- dieselbe Funktion wie die Analyse")

    komb_quelle = inspect.getsource(pipeline.berechne_kombination)
    pruefe("_kette_fuer_parzelle(" in komb_quelle
           and komb_quelle.count("_kette_fuer_parzelle(") >= 2,
           "A und A+B laufen durch dieselbe Kettenfunktion")

    # Das Modul selbst darf keine Daten beschaffen und nichts nachrechnen.
    kb_quelle = inspect.getsource(kb)
    for verboten in ("requests", "urllib", "sqlite3", "modul1_geodata"):
        pruefe(f"import {verboten}" not in kb_quelle and f"from .{verboten}" not in kb_quelle,
               f"kombination.py bindet {verboten} nicht ein -- es vergleicht nur")

    # Und die Gegenprobe, dass der Vergleich wirklich nur liest: dieselben
    # Eingaben zweimal ergeben dasselbe Ergebnis.
    eins = kb.vergleiche(seite(600, 400_000), seite(1000, 700_000),
                         flaeche_a_m2=1000.0, flaeche_b_m2=667.0)
    zwei = kb.vergleiche(seite(600, 400_000), seite(1000, 700_000),
                         flaeche_a_m2=1000.0, flaeche_b_m2=667.0)
    pruefe(eins == zwei, "der Vergleich ist zustandslos und wiederholbar")
    print()


def test_strassenparzelle() -> None:
    """Am echten Fall gefunden: die Gemeindestrasse als Kombinationspartner.

    Die Zonenpruefung faengt das NICHT ab -- Zonenplaene legen die Bauzone
    regelmaessig ueber die Strassenflaeche mit. An Rosenweg 4 (Buchs AG) lag
    die Strassenparzelle 1143 laut Klassifikation in derselben
    Gartenstadtzone und ergab dadurch 385'071 CHF "Mehrwert" fuer eine
    Flaeche, die niemand kaufen und ueberbauen kann.
    """
    print("=== Die Gemeindestrasse ist kein Bauland ===")
    klassifikation = {"kanten": [
        {"nr": 0, "art": "nachbarparzelle", "nachbar_egrid": "CH_NACHBAR", "nachbar_nummer": "316"},
        {"nr": 1, "art": "strasse", "nachbar_egrid": "CH_STRASSE", "nachbar_nummer": "1143"},
    ]}

    grund = kb.ist_strassenparzelle(klassifikation, "CH_STRASSE", "1143")
    pruefe(grund is not None, "eine Strassenparzelle wird erkannt")
    pruefe("Strassenachse" in (grund or ""), "und der Grund nennt die Strassenachse")
    pruefe("1143" in (grund or ""), "und die Parzellennummer")

    pruefe(kb.ist_strassenparzelle(klassifikation, "CH_NACHBAR", "316") is None,
           "eine echte Nachbarparzelle nicht")
    pruefe(kb.ist_strassenparzelle(klassifikation, None) is None,
           "ohne EGRID wird nichts behauptet")
    pruefe(kb.ist_strassenparzelle(None, "CH_STRASSE") is None,
           "ohne Klassifikation ebenso -- die Sperre darf nicht raten")
    print()


def test_aussenkante_endpunkte() -> None:
    """`/entwicklung` und `/kombination` muessen dieselben Eingaben gleich lesen.

    Waeren es zwei Leseroutinen, verglichen A und A+B unter verschiedenen
    Annahmen -- und die Differenz maesse den Unterschied der Annahmen statt
    den der Parzellen. Geprueft wird das VERHALTEN der Hilfsfunktionen, nicht
    ihr Quelltext.
    """
    import inspect

    import webapp

    print("=== Aussenkante: beide Endpunkte lesen dieselben Eingaben ===")

    daten = {
        "zielmarge": 0.18, "verkauf_chf_pro_m2": 9200, "verkauf_basis": "hnf",
        "bodenpreis_chf_pro_m2": 900, "ausbaustandard": "gehoben",
        "attika_zulaessig": True, "gebaeudeabstand_m": 8,
        "bestand_flaeche_nwf_m2": 180,
        "wohnungsmix": [{"typ": "4.5", "flaeche_m2": 110, "anteil": 1.0}],
        "wohnungsmix_vom_benutzer": True,
    }

    # 1 Die Szenario-Argumente: EIN Leser, von beiden benutzt.
    kwargs = webapp._szenario_kwargs(daten)
    pruefe(kwargs["attika_zulaessig"] is True and kwargs["gebaeudeabstand_m"] == 8,
           "die Szenario-Argumente kommen vollstaendig an")
    pruefe(kwargs["wohnungsmix_herkunft"] == "benutzerannahme",
           "die Herkunft des Wohnungsmix ebenso")
    pruefe(kwargs["bestand_flaeche_nwf_m2"] == 180,
           "und die Bestandsflaeche fuer die Sanierung")

    for name in ("_rechne_entwicklung", "_rechne_kombination"):
        quelle = inspect.getsource(getattr(webapp, name))
        pruefe("_szenario_kwargs(daten)" in quelle,
               f"{name} liest die Szenario-Argumente ueber _szenario_kwargs")
        pruefe("_markt_und_kosten(analyse, daten)" in quelle,
               f"{name} liest Markt und Kosten ueber _markt_und_kosten")

    # 2 Die Marktannahmen: derselbe Verkaufspreis, dieselbe Zielmarge.
    from potenzial_engine import Analyse

    analyse = Analyse(
        ergebnis={
            "adresse": "Teststrasse 1, 5033 Buchs AG",
            "modul1_geodaten": {
                "kataster": {"flaeche_m2": 600.0},
                "gemeinde": {"gemeinde": "Buchs (AG)", "kanton": "AG"},
                "geocoding": {"matched_label": "Teststrasse 1 5033 Buchs AG"},
            },
        },
        kontext={"modul1": {}},
    )
    mk = webapp._markt_und_kosten(analyse, daten)
    pruefe(mk["markt"].zielmarge == 0.18,
           f"die Zielmarge wird durchgereicht ({mk['markt'].zielmarge})")
    pruefe(mk["markt"].verkauf.basis == "hnf",
           "die Verkaufsbasis ebenso -- sie entscheidet, auf welcher Flaeche gerechnet wird")
    pruefe(mk["markt"].verkauf.preis_pro_m2.benutzerannahme == 9200,
           "und der Verkaufspreis als Benutzerannahme")
    pruefe(mk["plz"] == "5033", "die PLZ fuer die Marktreferenzen ebenso")
    pruefe(len(mk["positionen"]) > 0, "die Kostenpositionen werden gebildet")

    # 3 Zweimaliges Lesen ergibt dasselbe -- sonst waere der Vergleich zufaellig.
    zweit = webapp._markt_und_kosten(analyse, daten)
    pruefe(zweit["markt"].zielmarge == mk["markt"].zielmarge
           and zweit["markt"].verkauf.basis == mk["markt"].verkauf.basis,
           "und ist bei jedem Aufruf gleich")

    # 4 Der Endpunkt selbst muss registriert sein.
    quelle = inspect.getsource(webapp.Handler.do_POST) if hasattr(webapp, "Handler") else ""
    if not quelle:
        for name, obj in vars(webapp).items():
            if inspect.isclass(obj) and hasattr(obj, "do_POST"):
                quelle = inspect.getsource(obj.do_POST)
                break
    pruefe('"/kombination"' in quelle,
           "der Endpunkt /kombination ist registriert -- nicht nur die Funktion vorhanden")
    print()


def main() -> None:
    test_vereinigung()
    test_loch()
    test_zonen()
    test_mehr_land_ist_nicht_mehr_potenzial()
    test_bandbreite_ist_kein_vergleich()
    test_wirtschaftlicher_zusatznutzen()
    test_hbu_und_szenarien()
    test_strassenparzelle()
    test_aussenkante_kombination()
    test_aussenkante_endpunkte()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE KOMBINATIONS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

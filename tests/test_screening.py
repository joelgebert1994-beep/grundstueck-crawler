"""
Tests des Gebietsscreenings.

Vollstaendig OFFLINE.

Der Satz, um den es geht: **Screening ist ein Filter, kein Lead-Score.**
Geprueft wird deshalb vor allem, was das Screening NICHT tut:

  * Es sortiert nicht nach Grundstuecksgroesse. Eine grosse, voll
    ausgeschoepfte Parzelle steht hinter einer kleinen mit Reserve.
  * Es erfindet keine Ausnuetzungsziffer. Fehlt sie, gibt es keine Reserve.
  * Es behauptet nicht "unbebaut", wenn das Gebaeuderegister nur nichts
    verzeichnet -- es sagt genau das.
  * Es rechnet eine unvollstaendige Bestandsflaeche nicht schoen, sondern
    weist die Reserve als Obergrenze aus.
  * Es verschweigt nicht, wenn eine Kachel an der Trefferobergrenze lag.

CLI: python -m tests.test_screening
"""

from __future__ import annotations

import sys

from potenzial_engine import screening as scr

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def rechteck(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def zone(bezeichnung, code, ring, rechtskraeftig=True):
    return {
        "ebene": "grundnutzung",
        "hauptnutzung_code": code,
        "typ_kommunal_bezeichnung": bezeichnung,
        "ist_rechtskraeftig": rechtskraeftig,
        "geometrie_koordinaten": [ring],
    }


def gwr(egrid, *, garea=None, gastw=None, gbauj=None, gkat=1020):
    return {"egrid": egrid, "garea": garea, "gastw": gastw, "gbauj": gbauj, "gkat": gkat}


# ---------------------------------------------------------------------------


def test_kacheln() -> None:
    print("=== Kacheln: das Gebiet wird zerlegt, nicht abgeschnitten ===")
    k = scr.kacheln((0, 0, 600, 600), kante_m=300)
    pruefe(len(k) == 4, f"600 x 600 m ergibt vier Kacheln zu 300 m ({len(k)})")
    pruefe(k[0] == (0, 0, 300, 300), f"die erste sitzt richtig ({k[0]})")

    rest = scr.kacheln((0, 0, 400, 400), kante_m=300)
    pruefe(len(rest) == 4 and rest[-1] == (300, 300, 400, 400),
           "der Rand wird beschnitten statt ueberstanden")
    pruefe(scr.kacheln((0, 0, 0, 0)) == [], "ein leeres Gebiet ergibt keine Kachel")

    geteilt = scr.teile_kachel((0, 0, 300, 300))
    pruefe(len(geteilt) == 4, "eine volle Kachel laesst sich vierteln")
    pruefe(sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in geteilt) == 300 * 300,
           "und die Viertel decken sie vollstaendig")
    pruefe(scr.teile_kachel((0, 0, 30, 30)) == [],
           "unter der Mindestgroesse wird nicht weiter geteilt -- sonst laeuft es ewig")
    print()


def test_bestand() -> None:
    print("=== Bestand aus dem GWR: genaehert, und das steht dabei ===")
    b = scr.bestand_je_parzelle([
        gwr("CH_A", garea=100, gastw=3, gbauj=1965),
        gwr("CH_A", garea=40, gastw=1, gbauj=1998),
        gwr("CH_B", garea=200, gastw=None, gbauj=1974),
    ])
    pruefe(b["CH_A"]["gebaeude"] == 2, "beide Gebaeude derselben Parzelle zusammengefasst")
    pruefe(b["CH_A"]["bgf_m2"] == 340.0, f"BGF 100x3 + 40x1 = 340 ({b['CH_A']['bgf_m2']})")
    pruefe(b["CH_A"]["bgf_vollstaendig"] is True, "vollstaendig, weil beide Geschosszahlen da sind")
    pruefe(b["CH_A"]["baujahr_aeltestes"] == 1965 and b["CH_A"]["baujahr_juengstes"] == 1998,
           "aeltester und juengster Bau werden gefuehrt")

    pruefe(b["CH_B"]["bgf_vollstaendig"] is False,
           "ohne Geschosszahl gilt die Summe als unvollstaendig")
    pruefe(b["CH_B"]["bgf_m2"] == 0.0,
           "und das Gebaeude wird NICHT mit geratener Geschosszahl mitgerechnet")
    pruefe(b["CH_B"]["ohne_geschosszahl"] == 1, "die Luecke wird beziffert")

    pruefe(scr.bestand_je_parzelle([{"garea": 100, "gastw": 2}]) == {},
           "ein GWR-Eintrag ohne EGRID wird keiner Parzelle zugeschlagen")
    print()


def test_zonenzuordnung() -> None:
    print("=== Zone: groesster Flaechenanteil, nicht ein Punkt ===")
    parzelle = scr.polygon_aus_ring(rechteck(0, 0, 100, 100))

    klar = scr.zone_fuer_parzelle(parzelle, [zone("Wohnzone W2", "11", rechteck(-50, -50, 150, 150))])
    pruefe(klar["status"] == "eindeutig", f"vollstaendig ueberdeckt: eindeutig ({klar['status']})")
    pruefe(klar["bezeichnung"] == "Wohnzone W2", "und benannt")
    pruefe(klar["anteil"] == 1.0, f"Anteil 100 % ({klar['anteil']})")

    # 85 / 15 -- die kleinere Zone bleibt unter der Mehrdeutigkeitsschwelle.
    knapp = scr.zone_fuer_parzelle(parzelle, [
        zone("Wohnzone W2", "11", rechteck(0, 0, 100, 85)),
        zone("Gewerbezone", "12", rechteck(0, 85, 100, 100))])
    pruefe(knapp["status"] == "eindeutig" and knapp["bezeichnung"] == "Wohnzone W2",
           "bei 85 zu 15 entscheidet der groessere Anteil")

    # 60 / 40 -- hier ist nicht mehr bestimmbar, welche Kennzahlen gelten.
    geteilt = scr.zone_fuer_parzelle(parzelle, [
        zone("Wohnzone W2", "11", rechteck(0, 0, 100, 60)),
        zone("Gewerbezone", "12", rechteck(0, 60, 100, 100))])
    pruefe(geteilt["status"] == "mehrdeutig", f"bei 60 zu 40: mehrdeutig ({geteilt['status']})")
    pruefe(geteilt["zone"] is None, "und es wird KEINE der beiden gewaehlt")
    pruefe("nicht bestimmbar" in geteilt["grund"], "mit klarem Grund")

    ohne = scr.zone_fuer_parzelle(parzelle, [
        zone("Wohnzone W2", "11", rechteck(0, 0, 100, 100), rechtskraeftig=False)])
    pruefe(ohne["status"] == "keine_grundnutzung_gefunden",
           "eine nicht rechtskraeftige Festlegung zaehlt nicht")
    print()


def test_bauzonen_gate() -> None:
    print("=== Gate: nur Bauzonen, in denen privat gebaut wird ===")
    faelle = [
        ("11", "Wohnzone", None),
        ("13", "Mischzone", None),
        ("14", "Zentrumszone", None),
        ("21", "Landwirtschaftszone", scr.GATE_KEINE_BAUZONE),
        ("44", "Wald", scr.GATE_KEINE_BAUZONE),
        ("15", "Zone fuer oeffentliche Bauten", scr.GATE_OEFFENTLICH),
        ("18", "Verkehrszone", scr.GATE_OEFFENTLICH),
    ]
    falsch = []
    for code, name, erwartet in faelle:
        ergebnis = scr.pruefe_bauzone({"status": "eindeutig", "bezeichnung": name,
                                       "hauptnutzung_code": code + "1201"})
        tatsaechlich = (ergebnis or {}).get("gate")
        if tatsaechlich != erwartet:
            falsch.append((code, name, tatsaechlich, erwartet))
    pruefe(not falsch, f"alle sieben Kategorien richtig eingestuft ({falsch})")

    ohne = scr.pruefe_bauzone({"status": "mehrdeutig", "grund": "zwei Zonen"})
    pruefe(ohne["gate"] == scr.GATE_KEINE_ZONE, "ohne eindeutige Zone: kein Weiterrechnen")
    pruefe(ohne["grund"] == "zwei Zonen", "und der Grund wird durchgereicht statt ersetzt")
    print()


def test_einstufung() -> None:
    print("=== Einstufung: strukturell, ohne erfundene Schwellen ===")
    w2 = {"status": "eindeutig", "bezeichnung": "Wohnzone W2",
          "hauptnutzung_code": "111201", "anteil": 1.0}
    kennzahlen = {"ausnuetzungsziffer_az": 0.5}

    unbebaut = scr.bewerte_parzelle(
        {"egrid": "CH_1", "flaeche_m2": 1000.0}, None, w2, kennzahlen)
    pruefe(unbebaut["einstufung"] == scr.EINSTUFUNG_UNBEBAUT, "kein GWR-Eintrag: unbebaut")
    pruefe(unbebaut["reserve_bgf_m2"] == 500.0, f"die ganze Ausnuetzung ist Reserve ({unbebaut['reserve_bgf_m2']})")
    pruefe(any("nicht dasselbe wie" in p for p in unbebaut["offene_punkte"]),
           "aber 'nicht verzeichnet' wird nicht zu 'unbebaut' erklaert")

    unternutzt = scr.bewerte_parzelle(
        {"egrid": "CH_2", "flaeche_m2": 1000.0},
        {"gebaeude": 1, "bgf_m2": 200.0, "bgf_vollstaendig": True,
         "ohne_geschosszahl": 0, "baujahr_aeltestes": 1968},
        w2, kennzahlen)
    pruefe(unternutzt["einstufung"] == scr.EINSTUFUNG_UNTERNUTZT, "Reserve vorhanden: unternutzt")
    pruefe(unternutzt["reserve_bgf_m2"] == 300.0, f"500 - 200 = 300 ({unternutzt['reserve_bgf_m2']})")
    pruefe(unternutzt["ausnutzungsgrad"] == 0.4, "der Ausnutzungsgrad wird beziffert")
    pruefe("1968" in unternutzt["grund"], "und das Baujahr genannt, wenn bekannt")

    voll = scr.bewerte_parzelle(
        {"egrid": "CH_3", "flaeche_m2": 1000.0},
        {"gebaeude": 1, "bgf_m2": 520.0, "bgf_vollstaendig": True, "ohne_geschosszahl": 0},
        w2, kennzahlen)
    pruefe(voll["einstufung"] == scr.EINSTUFUNG_AUSGESCHOEPFT, "kein Spielraum: ausgeschoepft")
    pruefe(voll["reserve_bgf_m2"] == -20.0, "die negative Reserve wird nicht auf null gerundet")

    ohne_az = scr.bewerte_parzelle(
        {"egrid": "CH_4", "flaeche_m2": 1000.0}, None, w2, {"vollgeschosse_max": 2})
    pruefe(ohne_az["einstufung"] == scr.EINSTUFUNG_NICHT_BESTIMMBAR,
           "ohne Ausnuetzungsziffer: nicht bestimmbar")
    pruefe(ohne_az["reserve_bgf_m2"] is None, "und keine erfundene Reserve")
    pruefe(any("Ausnuetzungsziffer" in p for p in ohne_az["offene_punkte"]),
           "sondern ein offener Punkt")

    lueckig = scr.bewerte_parzelle(
        {"egrid": "CH_5", "flaeche_m2": 1000.0},
        {"gebaeude": 3, "bgf_m2": 150.0, "bgf_vollstaendig": False, "ohne_geschosszahl": 2},
        w2, kennzahlen)
    pruefe("zu gross" in lueckig["datenqualitaet"]["bestehende_bgf"],
           "unvollstaendiger Bestand: die Reserve gilt als Obergrenze")
    pruefe(any("Obergrenze" in p for p in lueckig["offene_punkte"]),
           "und steht als offener Punkt da")
    print()


def test_nicht_nach_groesse_sortiert() -> None:
    """Der Kern: 'nicht einfach groessere Grundstuecke zuerst'."""
    print("=== Gross ist nicht interessant ===")
    w2 = {"status": "eindeutig", "bezeichnung": "Wohnzone W2",
          "hauptnutzung_code": "111201", "anteil": 1.0}
    kennzahlen = {"ausnuetzungsziffer_az": 0.5}

    gross_voll = scr.bewerte_parzelle(
        {"egrid": "GROSS", "parzellennummer": "1", "flaeche_m2": 5000.0},
        {"gebaeude": 4, "bgf_m2": 2600.0, "bgf_vollstaendig": True, "ohne_geschosszahl": 0},
        w2, kennzahlen)
    klein_leer = scr.bewerte_parzelle(
        {"egrid": "KLEIN", "parzellennummer": "2", "flaeche_m2": 700.0},
        None, w2, kennzahlen)
    mittel_reserve = scr.bewerte_parzelle(
        {"egrid": "MITTEL", "parzellennummer": "3", "flaeche_m2": 1200.0},
        {"gebaeude": 1, "bgf_m2": 120.0, "bgf_vollstaendig": True, "ohne_geschosszahl": 0},
        w2, kennzahlen)

    reihe = [e["egrid"] for e in scr.sortiere([gross_voll, klein_leer, mittel_reserve])]
    pruefe(reihe == ["MITTEL", "KLEIN", "GROSS"],
           f"Reserve entscheidet, nicht Flaeche ({reihe})")
    pruefe(gross_voll["flaeche_m2"] > klein_leer["flaeche_m2"]
           and reihe.index("GROSS") > reihe.index("KLEIN"),
           "die mit Abstand groesste Parzelle steht zuhinterst -- sie ist ausgeschoepft")

    # Und nicht bestimmbare Parzellen stehen dahinter, nicht davor.
    unklar = scr.bewerte_parzelle({"egrid": "UNKLAR", "flaeche_m2": 9000.0}, None, w2, {})
    reihe2 = [e["egrid"] for e in scr.sortiere([unklar, gross_voll, mittel_reserve])]
    pruefe(reihe2[-1] == "UNKLAR",
           f"ueber eine nicht bestimmbare Parzelle wird nichts behauptet ({reihe2})")
    print()


def test_keine_punktzahl() -> None:
    """Es darf nirgends eine Punktzahl oder Wahrscheinlichkeit entstehen."""
    print("=== Kein Lead-Score, keine Verkaufswahrscheinlichkeit ===")
    import inspect

    # Geprueft werden die NAMEN im ausfuehrbaren Code, nicht der Fliesstext:
    # der Modulkopf sagt ausdruecklich, dass es keinen Score gibt, und wuerde
    # eine blosse Textsuche natuerlich ausloesen.
    import ast

    baum = ast.parse(inspect.getsource(scr))
    namen = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Name):
            namen.add(knoten.id.lower())
        elif isinstance(knoten, ast.Attribute):
            namen.add(knoten.attr.lower())
        elif isinstance(knoten, ast.arg):
            namen.add(knoten.arg.lower())
        elif isinstance(knoten, (ast.FunctionDef, ast.ClassDef)):
            namen.add(knoten.name.lower())
        elif isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            # Schluesselnamen in Dicts sind Konstanten -- die zaehlen mit.
            if len(knoten.value) < 40:
                namen.add(knoten.value.lower())
    for verboten in ("score", "punktzahl", "wahrscheinlichkeit", "gewicht", "rating"):
        treffer = sorted(n for n in namen if verboten in n)
        pruefe(not treffer, f"kein Name mit '{verboten}' im Code ({treffer[:3]})")

    w2 = {"status": "eindeutig", "bezeichnung": "W2", "hauptnutzung_code": "11", "anteil": 1.0}
    eintrag = scr.bewerte_parzelle({"egrid": "X", "flaeche_m2": 1000.0}, None, w2,
                                   {"ausnuetzungsziffer_az": 0.5})
    pruefe(all(not k.endswith("_score") for k in eintrag),
           "und kein Score-Feld im Ergebnis")
    pruefe("grund" in eintrag and "datenqualitaet" in eintrag and "offene_punkte" in eintrag,
           "stattdessen Grund, Datenqualitaet und offene Punkte")
    print()


def test_aussenkante_screening() -> None:
    """Das Screening muss ueber den Endpunkt-Pfad dieselben Funktionen benutzen
    wie die Einzelanalyse -- keine zweite Engine."""
    import inspect

    from potenzial_engine import pipeline

    print("=== Aussenkante: eine Engine, zwei Betriebsarten ===")

    p = inspect.signature(pipeline.screene_gebiet).parameters
    for name in ("bbox", "kanton", "modul2_result", "min_flaeche_m2"):
        pruefe(name in p, f"screene_gebiet nimmt '{name}' entgegen")

    quelle = inspect.getsource(pipeline.screene_gebiet)
    pruefe("match_zone" in quelle,
           "die Zonenzuordnung laeuft ueber match_zone -- dieselbe Funktion wie die Analyse")
    pruefe("bewerte_parzelle" in quelle and "sortiere" in quelle,
           "Bewertung und Reihenfolge kommen aus screening.py")
    pruefe("teile_kachel" in quelle,
           "eine abgeschnittene Kachel wird geteilt, nicht stillschweigend uebernommen")

    vertief = inspect.getsource(pipeline.vertiefe_kandidat)
    pruefe("berechne_potenzial" in vertief,
           "Stufe 2 benutzt berechne_potenzial -- dieselbe G1-Kaskade wie die Analyse")

    # screening.py darf nichts beschaffen.
    scr_quelle = inspect.getsource(scr)
    for verboten in ("requests", "urllib", "sqlite3", "modul1_geodata", "genai"):
        pruefe(f"import {verboten}" not in scr_quelle and f"from .{verboten}" not in scr_quelle,
               f"screening.py bindet {verboten} nicht ein -- es wertet nur aus")

    # Stufe 2 ohne Grenzabstaende: Bandbreite statt Zahl.
    ohne = pipeline.vertiefe_kandidat("CH_X", rechteck(0, 0, 40, 30), {})
    pruefe(ohne["status"] == "nicht_bestimmbar",
           "ohne Grenzabstaende gibt es keinen Baubereich")

    mit = pipeline.vertiefe_kandidat(
        "CH_X", rechteck(0, 0, 40, 30),
        {"grenzabstand_klein_m": 4.0, "grenzabstand_gross_m": 8.0,
         "ausnuetzungsziffer_az": 0.6, "vollgeschosse_max": 3})
    pruefe(mit["status"] == "bandbreite", f"mit zwei Abstaenden: Bandbreite ({mit['status']})")
    pruefe(set(mit["varianten"]) == {"optimistisch", "konservativ"},
           "beide Raender werden gerechnet")
    pruefe(mit["varianten"]["optimistisch"]["baubereich_m2"]
           > mit["varianten"]["konservativ"]["baubereich_m2"],
           "der kleinere Grenzabstand ergibt den groesseren Baubereich")
    pruefe("zwischen diesen beiden Werten" in mit["hinweis"],
           "und es steht dabei, dass das echte Ergebnis dazwischen liegt")
    print()


def test_strassenparzelle() -> None:
    """Am echten Fall gefunden -- zweimal hintereinander.

    Erst stand die Strassenparzelle 303 (Rosenweg, 3'345 m2) mit 1'673 m2
    "Reserve" auf Platz 2 der Trefferliste: Zonenplaene legen die Bauzone
    ueber die Strassenflaeche, das Bauzonen-Gate greift also nicht.

    Dann war die Sperre zu grob: Parzelle 1967 (7'481 m2, Gebaeude von 1966)
    fiel ebenfalls heraus, weil eine Zufahrt darueber fuehrt. Wo ein Gebaeude
    im Register steht, ist die Flaeche keine oeffentliche Verkehrsflaeche.
    """
    print("=== Die Strasse ist kein Bauland -- die Zufahrt schon ===")
    from shapely.geometry import LineString

    w2 = {"status": "eindeutig", "bezeichnung": "Wohnzone W2",
          "hauptnutzung_code": "111201", "anteil": 1.0}
    kennzahlen = {"ausnuetzungsziffer_az": 0.8}

    strasse = scr.bewerte_parzelle(
        {"egrid": "STRASSE", "flaeche_m2": 3345.0, "ist_strassenparzelle": True},
        None, w2, kennzahlen)
    pruefe(strasse["ausgeschieden"] == scr.GATE_STRASSE,
           "Achse durch die Parzelle und kein Gebaeude: Strassenparzelle")
    pruefe(strasse["reserve_bgf_m2"] is None, "und keine Reserve ausgewiesen")
    pruefe("spricht fuer" in strasse["grund"],
           "der Befund wird benannt, nicht behauptet -- die TLM3D-Strassenarten "
           "sind Zahlencodes, deren Bedeutung hier nicht nachgeschlagen ist")
    pruefe(any("Katasterplan" in p for p in strasse["offene_punkte"]),
           "mit einem konkreten naechsten Pruefschritt")

    mit_haus = scr.bewerte_parzelle(
        {"egrid": "ZUFAHRT", "flaeche_m2": 7481.0, "ist_strassenparzelle": True},
        {"gebaeude": 1, "bgf_m2": 5444.0, "bgf_vollstaendig": True,
         "ohne_geschosszahl": 0, "baujahr_aeltestes": 1966},
        w2, kennzahlen)
    pruefe(mit_haus["einstufung"] == scr.EINSTUFUNG_UNTERNUTZT,
           f"mit Gebaeude im Register: normale Bewertung ({mit_haus['einstufung']})")
    pruefe(mit_haus["reserve_bgf_m2"] == 540.8,
           f"und die Reserve wird gerechnet ({mit_haus['reserve_bgf_m2']})")

    # Die geometrische Markierung selbst.
    polygone = {
        "DURCH": scr.polygon_aus_ring(rechteck(0, 0, 100, 20)),
        "DANEBEN": scr.polygon_aus_ring(rechteck(0, 40, 100, 60)),
    }
    achse = LineString([(0, 10), (100, 10)])
    markiert = scr.markiere_strassenparzellen(polygone, [achse])
    pruefe(markiert == {"DURCH"}, f"nur die durchquerte Parzelle ({markiert})")
    pruefe(scr.markiere_strassenparzellen(polygone, []) == set(),
           "ohne Achsen wird nichts markiert -- die Sperre darf nicht raten")
    print()


def test_randlage() -> None:
    """Der zweite Fehler am echten Fall: eine Parzelle ragte 4 m aus dem
    abgefragten Rechteck, ihr Gebaeude lag draussen -- und sie stand als
    groesster "unbebauter" Treffer an der Spitze."""
    print("=== Am Rand des Suchgebiets wird nichts behauptet ===")
    w2 = {"status": "eindeutig", "bezeichnung": "Wohnzone W2",
          "hauptnutzung_code": "111201", "anteil": 1.0}
    kennzahlen = {"ausnuetzungsziffer_az": 0.8}

    rand = scr.bewerte_parzelle(
        {"egrid": "RAND", "flaeche_m2": 7481.0, "am_rand": True}, None, w2, kennzahlen)
    pruefe(rand["einstufung"] == scr.EINSTUFUNG_NICHT_BESTIMMBAR,
           f"kein GWR-Eintrag am Rand heisst NICHT unbebaut ({rand['einstufung']})")
    pruefe("nicht entschieden" in rand["grund"], "sondern: nicht entschieden")
    pruefe(any("Suchgebiet erweitern" in p for p in rand["offene_punkte"]),
           "mit dem naechsten Schritt")

    innen = scr.bewerte_parzelle(
        {"egrid": "INNEN", "flaeche_m2": 7481.0, "am_rand": False}, None, w2, kennzahlen)
    pruefe(innen["einstufung"] == scr.EINSTUFUNG_UNBEBAUT,
           "mitten im Gebiet gilt der fehlende Eintrag weiterhin als unbebaut")

    mit_rand = scr.bewerte_parzelle(
        {"egrid": "RAND2", "flaeche_m2": 2000.0, "am_rand": True},
        {"gebaeude": 1, "bgf_m2": 300.0, "bgf_vollstaendig": True, "ohne_geschosszahl": 0},
        w2, kennzahlen)
    pruefe("randlage" in mit_rand["datenqualitaet"],
           "auch mit Gebaeude wird die Randlage ausgewiesen")
    pruefe("Obergrenze" in mit_rand["datenqualitaet"]["randlage"],
           "und die Reserve als Obergrenze gefuehrt")
    print()


def test_gebaeude_ohne_egrid() -> None:
    """Im Testgebiet fuehrte genau 1 von 582 GWR-Gebaeuden keinen EGRID --
    und es stand ausgerechnet auf dem groessten Treffer der Liste."""
    print("=== Ein Gebaeude ohne EGRID geht nicht verloren ===")
    polygone = {
        "CH_A": scr.polygon_aus_ring(rechteck(0, 0, 100, 100)),
        "CH_B": scr.polygon_aus_ring(rechteck(200, 0, 300, 100)),
    }
    eintraege = [
        {"egrid": "CH_A", "egid": 1, "garea": 100, "gastw": 2},
        {"egrid": None, "egid": 2, "garea": 200, "gastw": 3, "gkode": 50, "gkodn": 50},
        {"egrid": None, "egid": 3, "garea": 50, "gastw": 1, "gkode": 9999, "gkodn": 9999},
    ]
    zugeordnet = scr.ordne_gebaeude_zu(eintraege, polygone)
    pruefe(len(zugeordnet.get("CH_A", [])) == 2,
           f"das Gebaeude ohne EGRID wird ueber seine Lage zugeordnet "
           f"({len(zugeordnet.get('CH_A', []))})")
    pruefe(any(g.get("zuordnung") == "ueber_lage" for g in zugeordnet["CH_A"]),
           "und die Zuordnungsart bleibt nachvollziehbar")
    pruefe("CH_B" not in zugeordnet, "ein Gebaeude ausserhalb aller Parzellen bleibt liegen")

    bestand = scr.bestand_je_parzelle(zugeordnet["CH_A"])
    pruefe(bestand["CH_A"]["bgf_m2"] == 800.0,
           f"und zaehlt in die Bestandsflaeche mit (100x2 + 200x3) ({bestand['CH_A']['bgf_m2']})")
    print()


def main() -> None:
    test_kacheln()
    test_bestand()
    test_zonenzuordnung()
    test_bauzonen_gate()
    test_einstufung()
    test_nicht_nach_groesse_sortiert()
    test_strassenparzelle()
    test_randlage()
    test_gebaeude_ohne_egrid()
    test_keine_punktzahl()
    test_aussenkante_screening()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE SCREENING-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

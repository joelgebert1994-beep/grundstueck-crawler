"""
Tests des Highest & Best Use.

Vollstaendig OFFLINE. Geprueft wird vor allem, wann KEINE Empfehlung
ausgesprochen werden darf -- eine Empfehlung ist leicht, ihr Ausbleiben ist
die schwerere und wichtigere Leistung:

  * Kein Szenario besteht alle vier Stufen -> keine beste Nutzung.
  * Der Residualwert der Spitzenkandidaten fehlt -> nicht bestimmbar.
  * Der Vorsprung ist kleiner als die Streuung der Marktreferenz -> praktisch
    gleichwertig, keine Rangfolge.

Und die Trennung, um die es fachlich geht: rechtlich zulaessig, physisch
moeglich, finanziell durchfuehrbar und hoechster Wert sind FILTER in fester
Reihenfolge, kein gewichteter Score. Eine Punktzahl wuerde rechtliche
Unzulaessigkeit gegen einen hoeheren Gewinn aufrechenbar machen.

CLI: python -m tests.test_hbu
"""

from __future__ import annotations

import sys

from potenzial_engine import hbu

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def szenario(id_, machbarkeit="moeglich", baukoerper=True, konflikte=None, bezeichnung=None):
    return {
        "id": id_,
        "bezeichnung": bezeichnung or id_.replace("_", " ").title(),
        "machbarkeit": machbarkeit,
        "baukoerper": [{"name": "K"}] if baukoerper else [],
        "konflikte": konflikte or [],
        "begruendung": f"Begruendung {id_}",
    }


def wirt(landwert, *, marge=0.18, ziel_erreicht=True, kosten_vollstaendig=True,
         pro_m2=None, grund=None):
    residual = ({"max_landwert_chf": landwert, "max_landwert_chf_pro_m2": pro_m2}
                if landwert is not None
                else {"status": "nicht_bestimmbar", "grund": grund or "Kein Erloes."})
    return {
        "residualwert": residual,
        "ergebnis": {"marge": marge, "zielmarge_erreicht": ziel_erreicht, "gewinn_chf": 1000},
        "kosten": {"vollstaendig": kosten_vollstaendig},
    }


def lauf(szenarien, wirtschaft, marktlage=None):
    return hbu.bestimme_hbu(
        {"szenarien": {s["id"]: s for s in szenarien}},
        {"szenarien": wirtschaft},
        marktlage,
    )


MARKT_ENG = {"verkauf": {"spanne": [8600, 9200], "median": 8900, "sicherheit": "mittel"}}
MARKT_BREIT = {"verkauf": {"spanne": [6000, 12000], "median": 9000, "sicherheit": "gering"}}


# ---------------------------------------------------------------------------


def test_empfehlung() -> None:
    print("=== Empfehlung: hoechster tragbarer Landwert gewinnt ===")
    r = lauf(
        [szenario("bestand", machbarkeit="besteht"), szenario("ersatzneubau"),
         szenario("anbau")],
        {"bestand": wirt(120000), "ersatzneubau": wirt(400000, pro_m2=670),
         "anbau": wirt(180000)},
        MARKT_ENG,
    )
    pruefe(r["status"] == hbu.STATUS_EMPFOHLEN, f"Es wird empfohlen ({r['status']})")
    pruefe(r["empfehlung"]["id"] == "ersatzneubau",
           f"Der hoechste Landwert gewinnt ({r['empfehlung']['id']})")
    pruefe([e["id"] for e in r["rangfolge"]] == ["ersatzneubau", "anbau", "bestand"],
           "Die Rangfolge stimmt")
    pruefe([e["platz"] for e in r["rangfolge"]] == [1, 2, 3], "mit Plaetzen")
    pruefe(r["kriterium"]["groesse"] == "max_landwert_chf",
           "Das Kriterium wird benannt")
    pruefe("Gewinn bevorzugte immer das groesste Projekt" in r["kriterium"]["begruendung"],
           "und begruendet, warum nicht der Gewinn")
    pruefe("400,000" in r["begruendung"] and "670" in r["begruendung"],
           "Die Begruendung nennt die Zahlen")
    pruefe("55.0%" in r["begruendung"] or "Vorsprung" in r["begruendung"],
           "und den Vorsprung auf Platz 2")
    pruefe(r["belastbarkeit"]["abstand_zum_zweiten"] == 0.55,
           f"Der Abstand ist beziffert ({r['belastbarkeit']['abstand_zum_zweiten']})")
    print()


def test_filter_nicht_score() -> None:
    """Jede Stufe ist ein Filter. Wer sie nicht besteht, ist raus -- nicht
    schlechter bewertet."""
    print("=== Die vier Stufen sind Filter, kein Score ===")

    r = lauf(
        [szenario("nicht_erlaubt", machbarkeit="nicht_moeglich"),
         szenario("ausgeschlossen", konflikte=[
             {"art": "zone", "meldung": "In dieser Zone unzulaessig.", "schwere": "ausschluss"}]),
         szenario("ohne_geometrie", baukoerper=False),
         szenario("ohne_rechnung"),
         szenario("negativ"),
         szenario("gut")],
        {"nicht_erlaubt": wirt(999999), "ausgeschlossen": wirt(999999),
         "ohne_geometrie": wirt(999999), "negativ": wirt(-50000),
         "gut": wirt(300000)},
        MARKT_ENG,
    )
    raus = {e["id"]: e for e in r["ausgeschieden"]}

    pruefe(raus["nicht_erlaubt"]["gescheitert_an"] == "rechtlich",
           "Baurechtlich unmoeglich scheitert an Stufe 1")
    pruefe(raus["ausgeschlossen"]["gescheitert_an"] == "rechtlich",
           "ein Ausschluss-Konflikt ebenso")
    pruefe("unzulaessig" in raus["ausgeschlossen"]["grund"],
           "und der Grund nennt den Konflikt")
    pruefe(raus["ohne_geometrie"]["gescheitert_an"] == "physisch",
           "Ohne Baukoerper scheitert es an Stufe 2")
    pruefe(raus["ohne_rechnung"]["gescheitert_an"] == "finanziell",
           "Ohne Wirtschaftlichkeitsrechnung an Stufe 3")
    pruefe(raus["negativ"]["gescheitert_an"] == "finanziell",
           "Ein negativer Landwert ebenso")
    pruefe("traegt diese Nutzung keinen Landpreis" in raus["negativ"]["grund"],
           "mit verstaendlichem Grund")

    pruefe([e["id"] for e in r["rangfolge"]] == ["gut"],
           "Nur das bestandene Szenario steht in der Rangfolge")
    pruefe(r["empfehlung"]["id"] == "gut", "und wird empfohlen")

    # Der entscheidende Punkt: ein hoher Landwert rettet ein rechtlich
    # unzulaessiges Szenario NICHT.
    pruefe(all(e["id"] != "nicht_erlaubt" for e in r["rangfolge"]),
           "Ein Landwert von 999'999 rettet die rechtliche Unzulaessigkeit nicht -- "
           "genau das waere bei einem gewichteten Score passiert")
    print()


def test_keine_empfehlung() -> None:
    print("=== Wann KEINE Empfehlung ausgesprochen wird ===")

    leer = hbu.bestimme_hbu({"szenarien": {}, "grund": "Kein G1-Ergebnis."}, {}, MARKT_ENG)
    pruefe(leer["status"] == hbu.STATUS_NICHT_BESTIMMBAR,
           "Ohne Szenarien: nicht bestimmbar")
    pruefe("Kein G1-Ergebnis" in leer["grund"],
           "und der Grund wird durchgereicht statt ersetzt")

    alle_raus = lauf(
        [szenario("a", machbarkeit="nicht_moeglich"), szenario("b", baukoerper=False)],
        {"a": wirt(100000), "b": wirt(100000)}, MARKT_ENG)
    pruefe(alle_raus["status"] == hbu.STATUS_NICHT_BESTIMMBAR,
           "Besteht kein Szenario alle Stufen: nicht bestimmbar")
    pruefe(alle_raus["rangfolge"] == [], "keine Rangfolge")
    pruefe("was jeweils fehlt" in alle_raus["grund"],
           "und der Verweis auf die ausgeschiedenen Szenarien")

    ohne_residual = lauf(
        [szenario("a"), szenario("b")],
        {"a": wirt(None, grund="Kein Verkaufserloes gesetzt."),
         "b": wirt(None, grund="Baukosten unvollstaendig.")},
        MARKT_ENG)
    pruefe(ohne_residual["status"] == hbu.STATUS_NICHT_BESTIMMBAR,
           "Ohne Residualwert: nicht bestimmbar")
    gruende = [e["grund"] for e in ohne_residual["ausgeschieden"]]
    pruefe(any("Kein Verkaufserloes" in g for g in gruende),
           "Der Grund aus der Wirtschaftlichkeit wird uebernommen, nicht neu erfunden")
    print()


def test_gleichwertig() -> None:
    """Der Kern der Scheingenauigkeits-Vermeidung."""
    print("=== Praktisch gleichwertig: kein Vorsprung ohne Unterscheidbarkeit ===")

    # 400'000 gegen 395'000 = 1.25 % Abstand. Die Referenzen streuen 3.37 %.
    knapp = lauf([szenario("a"), szenario("b")],
                 {"a": wirt(400000), "b": wirt(395000)}, MARKT_ENG)
    pruefe(knapp["status"] == hbu.STATUS_GLEICHWERTIG,
           f"Bei 1.25 % Abstand und 3.4 % Streuung: gleichwertig ({knapp['status']})")
    pruefe(knapp["empfehlung"] is None, "Es wird KEINE Empfehlung ausgesprochen")
    pruefe("nicht unterscheidbar" in knapp["grund"], "mit klarer Begruendung")
    pruefe("Risiko, Bauzeit und Aufwand" in knapp["grund"],
           "und dem Hinweis, woran die Entscheidung dann faellt")
    pruefe(knapp["rangfolge"], "Die Rangfolge bleibt sichtbar -- sie ist nur nicht belastbar")

    # Derselbe Abstand, aber enge Referenzen gibt es nicht -> gereiht, aber
    # als nicht belastbar gekennzeichnet.
    ohne = lauf([szenario("a"), szenario("b")], {"a": wirt(400000), "b": wirt(395000)})
    pruefe(ohne["status"] == hbu.STATUS_EMPFOHLEN,
           "Ohne Marktreferenz wird gereiht (es gibt keine Schwelle zum Vergleichen)")
    pruefe(ohne["belastbarkeit"]["marktreferenz_vorhanden"] is False,
           "aber das Fehlen wird ausgewiesen")
    pruefe(any("nicht marktseitig belegt" in v for v in ohne["vorbehalte"]),
           "und steht als Vorbehalt bei der Empfehlung")

    # Breite Streuung schluckt auch einen groesseren Vorsprung.
    breit = lauf([szenario("a"), szenario("b")],
                 {"a": wirt(400000), "b": wirt(320000)}, MARKT_BREIT)
    pruefe(breit["status"] == hbu.STATUS_GLEICHWERTIG,
           "Streuen die Referenzen breit (33 %), ist auch ein Vorsprung von 20 % "
           "nicht unterscheidbar")

    # Deutlicher Vorsprung besteht auch gegen breite Streuung.
    klar = lauf([szenario("a"), szenario("b")],
                {"a": wirt(900000), "b": wirt(300000)}, MARKT_BREIT)
    pruefe(klar["status"] == hbu.STATUS_EMPFOHLEN,
           "Ein Vorsprung von 67 % besteht auch gegen breite Streuung")
    print()


def test_vorbehalte() -> None:
    print("=== Vorbehalte: die Empfehlung traegt ihre Einschraenkungen mit ===")

    unvollstaendig = lauf([szenario("a")], {"a": wirt(400000, kosten_vollstaendig=False)},
                          MARKT_ENG)
    pruefe(any("Baukosten sind unvollstaendig" in v for v in unvollstaendig["vorbehalte"]),
           "Unvollstaendige Baukosten stehen als Vorbehalt")
    pruefe(any("zu hoch" in v for v in unvollstaendig["vorbehalte"]),
           "mit der Richtung des Fehlers")

    verfehlt = lauf([szenario("a")], {"a": wirt(400000, ziel_erreicht=False)}, MARKT_ENG)
    pruefe(any("Zielmarge nicht erreicht" in v for v in verfehlt["vorbehalte"]),
           "Eine verfehlte Zielmarge ebenso")
    pruefe(any("Rueckwaertsrechnung" in v for v in verfehlt["vorbehalte"]),
           "mit Verweis auf die Rueckwaertsrechnung -- dort steht, was sich aendern muesste")

    schwach = lauf([szenario("a")], {"a": wirt(400000)},
                   {"verkauf": {"spanne": [8000, 9000], "median": 8500,
                                "sicherheit": "gering"}})
    pruefe(any("gering" in v for v in schwach["vorbehalte"]),
           "Eine schwache Marktreferenz wird benannt")

    sauber = lauf([szenario("a")], {"a": wirt(400000)}, MARKT_ENG)
    pruefe(sauber["vorbehalte"] == [],
           "Bei sauberer Datenlage bleibt die Vorbehaltsliste leer -- es wird nicht "
           "vorsichtshalber gewarnt")
    print()


def test_bestand_ist_zulaessig() -> None:
    """Der Bestand steht bereits rechtmaessig -- machbarkeit 'besteht'."""
    print("=== Der Bestand ist rechtlich zulaessig ===")
    r = lauf([szenario("bestand", machbarkeit="besteht")], {"bestand": wirt(250000)},
             MARKT_ENG)
    pruefe(r["status"] == hbu.STATUS_EMPFOHLEN,
           "'besteht' gilt als rechtlich zulaessig -- das Haus steht ja")
    pruefe(r["empfehlung"]["id"] == "bestand",
           "und der Bestand kann die beste Nutzung sein")

    print()


def test_nicht_beurteilbar_ist_kein_scheitern() -> None:
    """Gefunden am echten Fall (Rosenweg 4): die Sanierung traegt
    machbarkeit='nicht_bestimmbar', obwohl ihre eigene Begruendung "baulich
    moeglich" sagt -- unbestimmt ist dort die Wirtschaftlichkeit. Das als
    Scheitern an der RECHTSSTUFE zu fuehren, behauptet eine Unzulaessigkeit,
    die niemand festgestellt hat. In einem Investorenbericht ist das keine
    Ungenauigkeit, sondern eine falsche Aussage."""
    print("=== 'nicht bestimmbar' ist kein Scheitern, sondern Unwissen ===")

    r = lauf([szenario("gut"), szenario("unklar", machbarkeit="nicht_bestimmbar")],
             {"gut": wirt(300000), "unklar": wirt(250000)}, MARKT_ENG)

    unklar = [e for e in r["geprueft"] if e["id"] == "unklar"][0]
    pruefe(unklar["nicht_beurteilbar"] is True, "Das Szenario gilt als nicht beurteilbar")
    pruefe(unklar["gescheitert_an"] is None,
           "und NICHT als an einer Stufe gescheitert -- schon gar nicht an der rechtlichen")
    pruefe([e["id"] for e in r["ausgeschieden"]] == [],
           "Es steht nicht unter den ausgeschiedenen Szenarien")
    pruefe([e["id"] for e in r["nicht_beurteilbar"]] == ["unklar"],
           "sondern in einer eigenen Gruppe")
    pruefe(any("Nicht beurteilbar waren" in v and "Unklar" in v for v in r["vorbehalte"]),
           "und die Empfehlung traegt es als Vorbehalt mit -- sie ist das Beste "
           "des Beurteilbaren, nicht das Beste von allem")
    pruefe(r["empfehlung"]["id"] == "gut",
           "Das beurteilbare Szenario wird trotzdem empfohlen")

    # Wenn NUR unbeurteilbare Szenarien da sind, gibt es keine Empfehlung.
    allein = lauf([szenario("unklar", machbarkeit="nicht_bestimmbar")],
                  {"unklar": wirt(250000)}, MARKT_ENG)
    pruefe(allein["status"] == hbu.STATUS_NICHT_BESTIMMBAR,
           "Nur unbeurteilbare Szenarien: keine Empfehlung")
    pruefe("nicht beurteilbar" in allein["grund"],
           "und der Grund sagt, dass sie nicht beurteilbar waren, nicht dass sie durchfielen")
    print()


def test_gleichstand() -> None:
    """Am echten Fall ergeben Anbau, Aufstockung und Bestand+Neubau exakt
    denselben Landwert -- in allen drei Faellen ist dieselbe ungenutzte
    Ausnuetzung die bindende Groesse. Sie zu 2., 3. und 4. zu nummerieren
    behauptete eine Reihenfolge, die die Zahlen nicht hergeben."""
    print("=== Gleiche Werte teilen sich den Platz ===")

    r = lauf([szenario("a"), szenario("b"), szenario("c"), szenario("d")],
             {"a": wirt(500000), "b": wirt(118108), "c": wirt(118108), "d": wirt(118108)},
             MARKT_ENG)
    plaetze = {e["id"]: e["platz"] for e in r["rangfolge"]}
    pruefe(plaetze == {"a": 1, "b": 2, "c": 2, "d": 2},
           f"Gleiche Landwerte bekommen denselben Platz ({plaetze})")

    # Gleichstand an der SPITZE: dann gaebe die Sortierreihenfolge den
    # Ausschlag -- reine Willkuer. Auch ohne Marktreferenz keine Empfehlung.
    spitze = lauf([szenario("a"), szenario("b")],
                  {"a": wirt(300000), "b": wirt(300000)}, None)
    pruefe(spitze["status"] == hbu.STATUS_GLEICHWERTIG,
           f"Gleichstand an der Spitze: keine Empfehlung ({spitze['status']})")
    pruefe(spitze["empfehlung"] is None, "auch ohne jede Marktreferenz")
    pruefe("gleichauf" in spitze["grund"], "und der Grund sagt es unverbluemt")
    print()


def test_aussenkante_hbu() -> None:
    """HBU muss bei jedem Aufruf mitkommen -- auch bei kuenftigen Aenderungen.

    Anlass sind die beiden Fehler aus Block 9: die Engine kannte einen
    Parameter, die Wrapper-Signatur nicht, und das fiel nur ueber den
    Endpunkt auf. Hier wird deshalb nicht nur geprueft, DASS hbu gerechnet
    wird, sondern dass es an der Stelle entsteht, die der Webdienst
    tatsaechlich aufruft.
    """
    import inspect

    from potenzial_engine import hbu, pipeline

    print("=== Aussenkante: HBU kommt ueber den Webdienst-Pfad mit ===")

    # Zuerst das Verhalten, nicht der Quelltext: die Funktion, die webapp.py
    # aufruft, MUSS hbu im Ergebnis haben. Eine Pruefung auf den Quelltext
    # allein haette den Verdrahtungsfehler nicht bemerkt -- sie haette nur
    # bestaetigt, dass die Zeile dasteht.
    from potenzial_engine import Analyse
    from potenzial_engine import wirtschaftlichkeit as wi

    analyse = Analyse(ergebnis={"modul1_geodaten": {"kataster": {"flaeche_m2": 600.0}}},
                      kontext={"modul1": {}})
    markt = wi.Marktannahmen(verkauf=wi.Verkaufsannahme(basis="nwf", preis_pro_m2=9000.0))
    ergebnis = pipeline.berechne_wirtschaftlichkeit_je_szenario(
        analyse, markt,
        szenarien_ergebnis={"szenarien": {}, "grund": "Testlauf ohne Szenarien."})
    pruefe("hbu" in ergebnis,
           "berechne_wirtschaftlichkeit_je_szenario liefert hbu tatsaechlich mit -- "
           "genau diese Funktion ruft webapp.py auf")
    pruefe(ergebnis.get("hbu", {}).get("grund") == "Testlauf ohne Szenarien.",
           "und reicht den Grund aus der Szenarienrechnung durch")

    quelle = inspect.getsource(pipeline.berechne_wirtschaftlichkeit_je_szenario)
    pruefe("marktlage" in quelle,
           "Die Marktlage wird fuer die Unterscheidungsschwelle durchgereicht")

    # Die Signatur von bestimme_hbu muss zu dem passen, was die Pipeline
    # uebergibt: Szenarien, Wirtschaftlichkeit, Marktlage.
    p = list(inspect.signature(hbu.bestimme_hbu).parameters)
    pruefe(p[:3] == ["szenarien_ergebnis", "wirtschaft_ergebnis", "marktlage"],
           f"bestimme_hbu nimmt genau diese drei Ergebnisse entgegen ({p})")

    # HBU darf NICHTS importieren, was eine neue Datenquelle waere.
    hbu_quelle = inspect.getsource(hbu)
    for verboten in ("requests", "urllib", "sqlite3", "modul1_geodata", "modul2_"):
        pruefe(f"import {verboten}" not in hbu_quelle and f"from .{verboten}" not in hbu_quelle,
               f"hbu.py bindet {verboten} nicht ein -- es fuehrt Ergebnisse zusammen, "
               f"es beschafft keine Daten")

    # Und es darf keine eigene Rechnung enthalten.
    pruefe("def berechne_" not in hbu_quelle,
           "hbu.py rechnet nichts selbst -- keine berechne_-Funktion darin")
    print()


def main() -> None:
    test_empfehlung()
    test_filter_nicht_score()
    test_keine_empfehlung()
    test_gleichwertig()
    test_vorbehalte()
    test_bestand_ist_zulaessig()
    test_nicht_beurteilbar_ist_kein_scheitern()
    test_gleichstand()
    test_aussenkante_hbu()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE HBU-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

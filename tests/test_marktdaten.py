"""
Regressionstests fuer Block A: Markt- und Referenzdaten.

Vollstaendig OFFLINE.

Geprueft wird, was fachlich schiefgehen kann:

  * Eine Referenz ohne Quelle oder Datum darf nicht als Referenz durchgehen.
  * Das Datenmodell darf auf keinen Anbieter zugeschnitten sein -- ein CSV
    mit fremden Spaltennamen und Umlauten muss einlesbar sein, und was nicht
    zugeordnet werden kann, darf nicht verloren gehen.
  * Abgeleitet wird nur, was EINDEUTIG folgt (Preis / Flaeche), nie geschaetzt.
  * Der Systemvorschlag darf keine Genauigkeit vortaeuschen: zu wenige, zu
    heterogene oder zu alte Referenzen ergeben `gering`, und dann ist die
    Bandbreite die Aussage.
  * Ausgeschlossene Objekte muessen mit Grund sichtbar bleiben.
  * Die Benutzerannahme hat immer Vorrang -- eine Referenz ersetzt sie nie.
  * Handerfassung und CSV-Import beurteilen dieselbe Eingabe gleich.

CLI: python -m tests.test_marktdaten
"""

from __future__ import annotations

import sys
from datetime import date

from potenzial_engine import marktdaten as md
from potenzial_engine.flaechenmodell import (
    HERKUNFT_BENUTZERANNAHME,
    HERKUNFT_NICHT_BESTIMMBAR,
    HERKUNFT_SYSTEMANNAHME,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def heute_minus(monate: int) -> str:
    """Datenstand relativ zu heute -- damit die Tests nicht mit der Zeit kippen."""
    jahr, monat = date.today().year, date.today().month - monate
    while monat <= 0:
        monat += 12
        jahr -= 1
    return f"{jahr:04d}-{monat:02d}-01"


def objekt(**kw):
    daten = dict(
        bezeichnung="MFH Testweg 1", quelle="Testquelle", datenstand=heute_minus(2),
        gemeinde="Buchs (AG)", kanton="AG", objektart="MFH",
        preis_chf_pro_m2=9000.0, datenqualitaet=md.QUALITAET_HOCH,
        # Beurkundeter Abschluss: sonst greift die Eignungsregel, und diese
        # Tests pruefen die Passung, nicht die Eignung (dafuer test_eignung).
        preisart=md.PREISART_ABSCHLUSS,
    )
    daten.update(kw)
    return md.Vergleichsobjekt(**daten)


# ---------------------------------------------------------------------------
# 1. Das Vergleichsobjekt
# ---------------------------------------------------------------------------

def test_vergleichsobjekt() -> None:
    print("=== Vergleichsobjekt: Herkunft ist Pflicht, Ableitung nur wenn eindeutig ===")
    for feld in ("bezeichnung", "quelle", "datenstand"):
        geworfen = None
        try:
            objekt(**{feld: ""})
        except md.MarktdatenError as exc:
            geworfen = exc
        pruefe(geworfen is not None, f"ohne '{feld}' wird das Objekt abgelehnt")

    geworfen = None
    try:
        objekt(herkunftsart="irgendwas")
    except md.MarktdatenError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "eine unbekannte Herkunftsart wird abgelehnt")

    # Preis je m2 wird abgeleitet -- aus Preis und Flaeche, sonst gar nicht.
    o = objekt(preis_chf_pro_m2=None, preis_chf=7_380_000, flaeche_m2=820)
    pruefe(o.preis_chf_pro_m2 == 9000.0, f"Preis/m² aus Preis und Flaeche ({o.preis_chf_pro_m2})")
    ohne = objekt(preis_chf_pro_m2=None, preis_chf=7_380_000, flaeche_m2=None)
    pruefe(ohne.preis_chf_pro_m2 is None, "ohne Flaeche wird nichts abgeleitet")

    miete = objekt(mietzins_chf_monat=2450, flaeche_m2=100)
    pruefe(miete.mietzins_chf_pro_m2_jahr == 294.0,
           f"Jahresmiete je m² aus Monatsmiete ({miete.mietzins_chf_pro_m2_jahr})")

    land = objekt(objektart="Bauland", preis_chf=1_045_000, grundstuecksflaeche_m2=1100,
                  preis_chf_pro_m2=None)
    pruefe(land.bodenpreis_chf_pro_m2 == 950.0,
           f"Bodenpreis nur bei Bauland abgeleitet ({land.bodenpreis_chf_pro_m2})")
    kein_land = objekt(objektart="MFH", preis_chf=1_045_000, grundstuecksflaeche_m2=1100,
                       preis_chf_pro_m2=None)
    pruefe(kein_land.bodenpreis_chf_pro_m2 is None,
           "bei einem MFH wird der Kaufpreis NICHT zum Bodenpreis gemacht")

    alt = objekt(datenstand=heute_minus(30))
    pruefe(alt.alter_monate == 30, f"Alter in Monaten ({alt.alter_monate})")
    pruefe(objekt(datenstand="unleserlich").alter_monate is None,
           "ein unleserliches Datum ergibt kein Alter statt eines geratenen")
    print()


# ---------------------------------------------------------------------------
# 2. Import: anbieterneutral
# ---------------------------------------------------------------------------

CSV_FREMD = """Objekt;Gemeinde;Kanton;Typ;Baujahr;Wohnfläche;Kaufpreis;Datum;Qualität;Lift;Bemerkung
MFH Rosenweg 12;Buchs (AG);AG;MFH;2019;820;7'380'000;{d0};hoch;ja;Erstvermietung
MFH Bahnstrasse 5;Buchs (AG);AG;MFH;2021;640;5952000;{d1};hoch;nein;
"""


def test_import() -> None:
    print("=== CSV-Import: fremde Spaltennamen, Umlaute, Tausendertrenner ===")
    text = CSV_FREMD.format(d0=heute_minus(3), d1=heute_minus(4))
    objekte, fehler = md.lese_csv(text, quelle="Fremdexport", herkunftsart=md.HERKUNFT_EXTERN)
    pruefe(len(objekte) == 2 and not fehler, f"2 Objekte gelesen, keine Fehler ({len(objekte)}, {fehler})")

    erstes = objekte[0]
    pruefe(erstes.flaeche_m2 == 820.0,
           f"'Wohnfläche' mit Umlaut wird erkannt ({erstes.flaeche_m2})")
    pruefe(erstes.preis_chf == 7_380_000.0,
           f"Tausendertrenner mit Apostroph gelesen ({erstes.preis_chf})")
    pruefe(erstes.preis_chf_pro_m2 == 9000.0, "Preis/m² daraus abgeleitet")
    pruefe(erstes.datenqualitaet == md.QUALITAET_HOCH,
           f"'Qualität' mit Umlaut wird erkannt ({erstes.datenqualitaet})")
    pruefe(erstes.objektart == "MFH" and erstes.baujahr == 2019, "Typ und Baujahr zugeordnet")
    pruefe(erstes.merkmale.get("Lift") == "ja",
           f"unbekannte Spalten gehen nicht verloren ({erstes.merkmale})")
    pruefe(erstes.herkunftsart == md.HERKUNFT_EXTERN, "Herkunftsart gesetzt")
    pruefe(erstes.quelle == "Fremdexport", "Quelle global gesetzt, weil das CSV keine fuehrt")

    # Komma als Dezimaltrenner und CHF im Feld.
    komma = md.lese_csv(
        "objekt,quelle,datum,preis_pro_m2\nX,Q,2026-01-01,\"CHF 8950,50\"\n",
        quelle="Q", herkunftsart=md.HERKUNFT_MANUELL)[0]
    pruefe(komma and komma[0].preis_chf_pro_m2 == 8950.5,
           f"Komma-Dezimaltrenner und CHF-Praefix gelesen ({komma[0].preis_chf_pro_m2 if komma else None})")

    # Eine unbrauchbare Zeile stoppt den Import nicht.
    gemischt, fehler2 = md.lese_csv(
        "objekt;quelle;datum;preis_pro_m2\nGut;Q;2026-01-01;9000\n;;;\n",
        quelle="", herkunftsart=md.HERKUNFT_EXTERN)
    pruefe(len(gemischt) == 1 and len(fehler2) == 1,
           f"gute Zeile uebernommen, schlechte gemeldet ({len(gemischt)}/{len(fehler2)})")

    aus_dict, _ = md.aus_dicts([{
        "bezeichnung": "Aus API", "quelle": "API", "datenstand": "2026-05-01",
        "preis_chf_pro_m2": 9100, "unbekanntes_feld": "bleibt erhalten",
    }])
    pruefe(aus_dict[0].merkmale.get("unbekanntes_feld") == "bleibt erhalten",
           "auch bei Dicts gehen unbekannte Felder nicht verloren")
    print()


# ---------------------------------------------------------------------------
# 3. Passung und Sicherheit
# ---------------------------------------------------------------------------

def test_filter() -> None:
    print("=== Passung: was nicht vergleichbar ist, wird mit Grund ausgeschlossen ===")
    objekte = [
        objekt(bezeichnung="Passt A", preis_chf_pro_m2=8800),
        objekt(bezeichnung="Passt B", preis_chf_pro_m2=9000),
        objekt(bezeichnung="Passt C", preis_chf_pro_m2=9300),
        objekt(bezeichnung="Andere Gemeinde", gemeinde="Zürich", preis_chf_pro_m2=14000),
        objekt(bezeichnung="Andere Objektart", objektart="ETW", preis_chf_pro_m2=11000),
        objekt(bezeichnung="Zu alt", datenstand=heute_minus(40), preis_chf_pro_m2=6000),
        objekt(bezeichnung="Ohne Wert", preis_chf_pro_m2=None),
    ]
    f = md.Vergleichsfilter(gemeinde="Buchs (AG)", objektart="MFH")
    r = md.werte_referenzen_aus(objekte, md.GROESSE_VERKAUF, f)

    pruefe(len(r.objekte) == 3, f"3 passende Objekte ({len(r.objekte)})")
    pruefe(r.spanne == (8800.0, 9300.0), f"Spanne 8800-9300 ({r.spanne})")
    pruefe(r.median == 9000.0, f"Median 9000 ({r.median})")
    gruende = {a["bezeichnung"]: a["grund"] for a in r.ausgeschlossen}
    pruefe("Zürich" in gruende.get("Andere Gemeinde", ""), "Gemeinde-Ausschluss benannt")
    pruefe("ETW" in gruende.get("Andere Objektart", ""), "Objektart-Ausschluss benannt")
    pruefe("Monate alt" in gruende.get("Zu alt", ""), "Alters-Ausschluss benannt")
    pruefe("kein Wert" in gruende.get("Ohne Wert", ""), "fehlender Wert benannt")
    pruefe(len(r.ausgeschlossen) == 4, f"alle 4 Ausschluesse ausgewiesen ({len(r.ausgeschlossen)})")

    # Ein teures Zuercher Objekt darf den Median NICHT anheben.
    pruefe(r.median < 10000, "der ausgeschlossene Zuercher Wert verschiebt den Median nicht")
    print()


def test_sicherheit() -> None:
    print("=== Sicherheit: keine kuenstliche Genauigkeit ===")
    keine = md.werte_referenzen_aus([], md.GROESSE_VERKAUF)
    pruefe(keine.sicherheit == md.SICHERHEIT_KEINE, "ohne Daten: keine_daten")
    pruefe(keine.systemvorschlag is None, "und kein Systemvorschlag")

    wenige = md.werte_referenzen_aus(
        [objekt(bezeichnung="A", preis_chf_pro_m2=9000),
         objekt(bezeichnung="B", preis_chf_pro_m2=9100)],
        md.GROESSE_VERKAUF)
    pruefe(wenige.sicherheit == md.SICHERHEIT_GERING,
           f"2 Objekte: gering ({wenige.sicherheit})")
    pruefe(any("Bandbreite ist die Aussage" in b for b in wenige.begruendung),
           "mit dem Hinweis, dass die Bandbreite die Aussage ist")
    # Geaendert: unter der Mindestanzahl gibt es KEINEN Punktwert mehr. Zwei
    # Beobachtungen haben einen Median, aber er sagt nur, was zufaellig in
    # ihrer Mitte lag.
    pruefe(wenige.systemvorschlag is None,
           "unter 3 Referenzen gibt es keinen Systemvorschlag")
    pruefe(wenige.spanne == (9000.0, 9100.0),
           f"die Spanne bleibt -- sie ist dann die ganze Aussage ({wenige.spanne})")
    pruefe(wenige.median == 9050.0,
           "der Median bleibt als Rohwert nachvollziehbar, wird aber nicht vorgeschlagen")
    pruefe(wenige.to_dict()["mindestanforderung"] == {
               "erfuellt": False, "min_objekte": md.MIN_OBJEKTE_MITTEL, "vorhanden": 2},
           "und die Mindestanforderung wird beziffert ausgewiesen")

    mittel = md.werte_referenzen_aus(
        [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=9000 + i * 50) for i in range(4)],
        md.GROESSE_VERKAUF)
    pruefe(mittel.sicherheit == md.SICHERHEIT_MITTEL, f"4 enge Objekte: mittel ({mittel.sicherheit})")

    viele = md.werte_referenzen_aus(
        [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=9000 + i * 30) for i in range(7)],
        md.GROESSE_VERKAUF)
    pruefe(viele.sicherheit == md.SICHERHEIT_HOCH, f"7 enge, aktuelle Objekte: hoch ({viele.sicherheit})")

    # Starke Streuung druckt die Sicherheit, egal wie viele Objekte.
    streuend = md.werte_referenzen_aus(
        [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=p)
         for i, p in enumerate([6000, 7000, 9000, 11000, 13000, 14000, 15000])],
        md.GROESSE_VERKAUF)
    pruefe(streuend.sicherheit == md.SICHERHEIT_GERING,
           f"stark streuende Objekte: gering ({streuend.sicherheit})")
    pruefe(any("streuen" in b for b in streuend.begruendung), "mit benannter Streuung")

    # Alte Referenzen druecken die Sicherheit ebenfalls.
    alt = md.werte_referenzen_aus(
        [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=9000 + i * 30, datenstand=heute_minus(18))
         for i in range(7)],
        md.GROESSE_VERKAUF)
    pruefe(alt.sicherheit == md.SICHERHEIT_MITTEL,
           f"nur aeltere Referenzen: hoechstens mittel ({alt.sicherheit})")
    pruefe(any("Monate alt" in b for b in alt.begruendung), "mit benanntem Alter")

    schwach = md.werte_referenzen_aus(
        [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=9000 + i * 30,
                datenqualitaet=md.QUALITAET_GERING) for i in range(7)],
        md.GROESSE_VERKAUF)
    pruefe(any("Datenqualitaet" in b for b in schwach.begruendung),
           "geringe Datenqualitaet wird vermerkt")
    print()


# ---------------------------------------------------------------------------
# 4. Uebergabe an die Wirtschaftlichkeit
# ---------------------------------------------------------------------------

def test_uebergabe() -> None:
    print("=== Uebergabe: Benutzerannahme hat Vorrang, Ebenen bleiben getrennt ===")
    objekte = [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=p, quelle=f"Quelle {i}")
               for i, p in enumerate([8800, 9000, 9300])]
    r = md.werte_referenzen_aus(objekte, md.GROESSE_VERKAUF,
                                md.Vergleichsfilter(gemeinde="Buchs (AG)", objektart="MFH"))

    ohne = r.als_marktwert()
    pruefe(ohne.wert == 9000.0, f"ohne Benutzerannahme gilt der Systemvorschlag ({ohne.wert})")
    pruefe(ohne.herkunft == HERKUNFT_SYSTEMANNAHME, "als Systemannahme gekennzeichnet")
    pruefe(ohne.spanne == (8800.0, 9300.0), "die Referenzspanne bleibt sichtbar")
    pruefe(len(ohne.referenzen) == 3, f"alle 3 Referenzen uebergeben ({len(ohne.referenzen)})")
    pruefe(all(x.quelle and x.datum and x.objekt for x in ohne.referenzen),
           "jede Referenz traegt Quelle, Datum und Objekt")

    mit = r.als_marktwert(benutzerannahme=9500)
    pruefe(mit.wert == 9500, f"die Benutzerannahme ist massgebend ({mit.wert})")
    pruefe(mit.herkunft == HERKUNFT_BENUTZERANNAHME, "als Benutzerannahme gekennzeichnet")
    pruefe(mit.systemvorschlag == 9000.0, "der Systemvorschlag bleibt daneben sichtbar")
    pruefe(mit.spanne == (8800.0, 9300.0), "und die Referenzspanne ebenfalls")

    zuwenig = md.werte_referenzen_aus([objekt(preis_chf_pro_m2=9000)], md.GROESSE_VERKAUF)
    mw = zuwenig.als_marktwert()
    pruefe(mw.systemvorschlag is None and "Kein Systemvorschlag" in mw.begruendung,
           f"unter der Mindestanzahl wird das im Klartext gesagt ({mw.begruendung[:48]})")

    # Genug Referenzen, aber zu heterogen: dann gibt es einen Vorschlag, und
    # er wird ausdruecklich als schwach gestuetzt gefuehrt.
    schwach = md.werte_referenzen_aus(
        [objekt(bezeichnung="A", preis_chf_pro_m2=6000),
         objekt(bezeichnung="B", preis_chf_pro_m2=9000),
         objekt(bezeichnung="C", preis_chf_pro_m2=14000)],
        md.GROESSE_VERKAUF).als_marktwert()
    pruefe("schwach gestuetzt" in schwach.begruendung,
           f"bei geringer Sicherheit steht das im Klartext ({schwach.begruendung[:48]})")

    leer = md.werte_referenzen_aus([], md.GROESSE_VERKAUF).als_marktwert()
    pruefe(leer.wert is None and leer.herkunft == HERKUNFT_NICHT_BESTIMMBAR,
           "ohne Referenzen und ohne Benutzerwert bleibt es nicht bestimmbar")
    leer_mit = md.werte_referenzen_aus([], md.GROESSE_VERKAUF).als_marktwert(benutzerannahme=9500)
    pruefe(leer_mit.wert == 9500,
           "eine Benutzerannahme genuegt auch ganz ohne Referenzen")
    print()


def test_marktlage() -> None:
    print("=== Marktlage: alle Segmente auf einmal ===")
    objekte = [
        # Beurkundet -- sonst zaehlt es als Bestand und nicht als Neubau.
        objekt(bezeichnung="Verkauf A", preis_chf_pro_m2=9000,
               objektart="Eigentumswohnung", preisart=md.PREISART_ABSCHLUSS),
        objekt(bezeichnung="Verkauf B", preis_chf_pro_m2=9200,
               objektart="Eigentumswohnung", preisart=md.PREISART_ABSCHLUSS),
        objekt(bezeichnung="Miete A", preis_chf_pro_m2=None, mietzins_chf_pro_m2_jahr=260),
        objekt(bezeichnung="Bauland", objektart="Bauland", preis_chf_pro_m2=None,
               bodenpreis_chf_pro_m2=950),
        objekt(bezeichnung="Haus", objektart="Einfamilienhaus",
               preis_chf_pro_m2=None, preis_chf=1_350_000),
        objekt(bezeichnung="Rendite", objektart="Mehrfamilienhaus",
               preis_chf_pro_m2=None, preis_chf=3_900_000),
    ]
    lage = md.marktlage(objekte)
    pruefe(set(lage) == set(md.GROESSEN_REIHENFOLGE),
           f"alle sechs Segmente ausgewertet ({sorted(lage)})")
    pruefe(list(lage) == list(md.GROESSEN_REIHENFOLGE),
           "und in fester Reihenfolge -- die Oberflaeche verlaesst sich darauf")
    pruefe(len(lage["efh"].objekte) == 1, f"1 EFH-Referenz ({len(lage['efh'].objekte)})")
    pruefe(len(lage["mfh"].objekte) == 1, f"1 MFH-Referenz ({len(lage['mfh'].objekte)})")
    pruefe(len(lage["efh"].objekte) == 1 and lage["efh"].objekte[0].bezeichnung == "Haus",
           "das Haus zaehlt zum EFH, nicht zur Renditeliegenschaft")
    pruefe(len(lage["verkauf"].objekte) == 2, f"2 Verkaufsreferenzen ({len(lage['verkauf'].objekte)})")
    pruefe(len(lage["miete"].objekte) == 1, "1 Mietreferenz")
    pruefe(len(lage["boden"].objekte) == 1, "1 Bodenreferenz")
    d = lage["verkauf"].to_dict()
    pruefe(d["punktwert_belastbar"] is False, "2 Objekte gelten nicht als belastbarer Punktwert")
    pruefe("objekte" in d and "ausgeschlossen" in d, "Ein- und Ausschluss sind im Ergebnis")
    pruefe(d["nach_herkunft"] == {"extern": 2}, f"Herkunft aufgeschluesselt ({d['nach_herkunft']})")

    geworfen = None
    try:
        md.werte_referenzen_aus([], "gibt_es_nicht")
    except md.MarktdatenError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "eine unbekannte Marktgroesse wird abgelehnt")
    print()


def test_objektart_normalisieren() -> None:
    """Die Portale schreiben fuer dieselbe Sache fuenf verschiedene Woerter."""
    print("=== Objektart: eine feste Sprache statt Inseratsvokabular ===")
    faelle = {
        "Haus": md.OBJEKTART_HAUS,
        "Einfamilienhaus": md.OBJEKTART_EFH,
        "Doppeleinfamilienhaus": md.OBJEKTART_EFH,
        "Chalet": md.OBJEKTART_EFH,
        "Terrassenhaus": md.OBJEKTART_EFH,
        "Mehrfamilienhaus": md.OBJEKTART_MFH,
        "MFH": md.OBJEKTART_MFH,
        "Eigentumswohnung": md.OBJEKTART_WOHNUNG,
        "4.5-Zimmer-Wohnung": md.OBJEKTART_WOHNUNG,
        "Bauland": md.OBJEKTART_BAULAND,
        "Bauparzelle": md.OBJEKTART_BAULAND,
        "Gewerbegrundstück": md.OBJEKTART_BAULAND,
        "Hotel": md.OBJEKTART_GEWERBE,
        "": md.OBJEKTART_UNBEKANNT,
        None: md.OBJEKTART_UNBEKANNT,
    }
    falsch = {k: md.normalisiere_objektart(k) for k, v in faelle.items()
              if md.normalisiere_objektart(k) != v}
    pruefe(not falsch, f"alle {len(faelle)} Schreibweisen richtig zugeordnet ({falsch})")

    # Real beobachtet: eine ganze Homegate-Seite stand im Feld Objektart.
    blob = "Mehrfamilienhaus\nDokumente (0)\nDein neues Eigenheim richtig versichern" * 20
    pruefe(md.normalisiere_objektart(blob) == md.OBJEKTART_UNBEKANNT,
           "ein Inseratstext im Feld Objektart gilt als unbekannt, nicht als eigene Gruppe")
    print()


def test_eignung() -> None:
    """Der Methodenfehler, um den es geht: der Angebotspreis eines
    bestehenden Hauses ist NICHT der Verkaufspreis neu gebauter Wohnungen."""
    print("=== Eignung: nicht jeder CHF/m2 ist ein Verkaufspreis ===")

    bestand = objekt(bezeichnung="MFH aus dem Inserat", objektart="Mehrfamilienhaus",
                     herkunftsart=md.HERKUNFT_EXTERN, preisart=md.PREISART_ANGEBOT,
                     preis_chf_pro_m2=9000)
    grund = md.eignung(bestand, md.GROESSE_VERKAUF)
    pruefe(grund is not None,
           "ein importierter Bestands-Angebotspreis taugt nicht als Verkaufsreferenz")
    pruefe("nicht der Verkaufspreis neu gebauter" in (grund or ""),
           "und der Grund sagt warum")

    # Geaendert mit den neuen Segmenten: auch ein WOHNUNGSINSERAT ist ein
    # Bestandspreis. Frueher galt es als Verkaufsreferenz -- das war zu
    # grosszuegig, und seit es das Segment Wohnung Bestand gibt, hat es
    # ein eigenes Fach.
    wohnung = objekt(bezeichnung="ETW aus dem Inserat", objektart="Eigentumswohnung",
                     herkunftsart=md.HERKUNFT_EXTERN, preisart=md.PREISART_ANGEBOT,
                     preis_chf_pro_m2=9000)
    grund_wohnung = md.eignung(wohnung, md.GROESSE_VERKAUF)
    pruefe(grund_wohnung is not None and "Wohnung Bestand" in grund_wohnung,
           "auch ein Wohnungsinserat ist ein Bestandspreis und verweist aufs "
           "richtige Segment")
    pruefe(md.eignung(wohnung, md.GROESSE_WOHNUNG_BESTAND) is None,
           "dort ist es zugelassen")
    pruefe(md.eignung(wohnung, md.GROESSE_EFH) is not None,
           "aber nicht im Segment Einfamilienhaus")

    abschluss = objekt(bezeichnung="Beurkundet", objektart="Mehrfamilienhaus",
                       herkunftsart=md.HERKUNFT_EXTERN, preisart=md.PREISART_ABSCHLUSS,
                       preis_chf_pro_m2=9000)
    pruefe(md.eignung(abschluss, md.GROESSE_VERKAUF) is None,
           "ein beurkundeter Abschluss zaehlt unabhaengig von der Objektart")

    # Die wichtigste Ausnahme: was der Benutzer selbst erfasst, gilt.
    eigen = objekt(bezeichnung="Eigene Referenz", objektart="Mehrfamilienhaus",
                   herkunftsart=md.HERKUNFT_MANUELL, preisart=md.PREISART_UNBEKANNT,
                   preis_chf_pro_m2=9000)
    pruefe(md.eignung(eigen, md.GROESSE_VERKAUF) is None,
           "eine von Hand erfasste Referenz bleibt zugelassen -- der Benutzer entscheidet")
    pruefe(md.eignung(bestand, md.GROESSE_BODEN) is None,
           "Fuer Bodenpreis und Miete gibt es keine solche Einschraenkung")

    # Und in der Auswertung: der ungeeignete faellt raus, der geeignete bleibt.
    r = md.werte_referenzen_aus([bestand, eigen], md.GROESSE_VERKAUF)
    pruefe([o.bezeichnung for o in r.objekte] == ["Eigene Referenz"],
           f"in der Auswertung bleibt nur die geeignete ({[o.bezeichnung for o in r.objekte]})")
    pruefe(any(a["art"] == "nicht_geeignet" for a in r.ausgeschlossen),
           "der Ausschluss ist als 'nicht_geeignet' gekennzeichnet")
    print()


def test_plausibilitaet_und_ausreisser() -> None:
    """Beide Faelle stammen aus dem echten Bestand des AkquiseRadars."""
    print("=== Unplausible Werte und Ausreisser ===")

    null = objekt(bezeichnung="Preis auf Anfrage", preis_chf_pro_m2=0.0)
    absurd = objekt(bezeichnung="Falsche Bezugsflaeche", preis_chf_pro_m2=30333.0)
    r = md.werte_referenzen_aus(
        [null, absurd] + [objekt(bezeichnung=f"O{i}", preis_chf_pro_m2=9000 + i * 100)
                          for i in range(3)],
        md.GROESSE_VERKAUF)
    gruende = {a["bezeichnung"]: a for a in r.ausgeschlossen}
    pruefe(gruende.get("Preis auf Anfrage", {}).get("art") == "unplausibel",
           "0 CHF/m2 ist kein Preis -- real beobachtet bei 'Preis auf Anfrage'")
    pruefe(gruende.get("Falsche Bezugsflaeche", {}).get("art") == "unplausibel",
           "30333 CHF/m2 ebenso -- dort war die Flaeche die Gebaeude- statt der Parzellenflaeche")
    pruefe(len(r.objekte) == 3, f"die drei brauchbaren bleiben ({len(r.objekte)})")

    # Ausreisser: statistisch, nicht gesetzt -- und erst ab genug Werten.
    viele = [objekt(bezeichnung=f"N{i}", preis_chf_pro_m2=w) for i, w in
             enumerate([8800, 8900, 9000, 9100, 9200, 9300])]
    mit = md.werte_referenzen_aus(
        viele + [objekt(bezeichnung="Ausreisser", preis_chf_pro_m2=19000)],
        md.GROESSE_VERKAUF)
    pruefe(any(a["bezeichnung"] == "Ausreisser" and a["art"] == "ausreisser"
               for a in mit.ausgeschlossen),
           "ein Wert weit ausserhalb des Quartilsbereichs wird aussortiert")
    pruefe(mit.median == 9050.0, f"und verschiebt den Median nicht ({mit.median})")

    wenige = md.werte_referenzen_aus(
        [objekt(bezeichnung="A", preis_chf_pro_m2=8800),
         objekt(bezeichnung="B", preis_chf_pro_m2=9000),
         objekt(bezeichnung="Hoch", preis_chf_pro_m2=14000)],
        md.GROESSE_VERKAUF)
    pruefe(not any(a["art"] == "ausreisser" for a in wenige.ausgeschlossen),
           "bei drei Werten wird NICHT aussortiert -- da ist nicht zu unterscheiden, "
           "ob einer falsch ist oder der Markt streut")
    pruefe(wenige.sicherheit == md.SICHERHEIT_GERING, "stattdessen sinkt die Sicherheit")
    print()


def test_plz_und_preisart() -> None:
    print("=== PLZ und Preisart ===")
    # Es gibt vier Gemeinden namens Buchs.
    buchs_ag = objekt(bezeichnung="Buchs AG", plz="5033", gemeinde="Buchs",
                      preis_chf_pro_m2=9000)
    buchs_zh = objekt(bezeichnung="Buchs ZH", plz="8107", gemeinde="Buchs",
                      preis_chf_pro_m2=14000)
    r = md.werte_referenzen_aus([buchs_ag, buchs_zh], md.GROESSE_VERKAUF,
                                md.Vergleichsfilter(gemeinde="Buchs", plz="5033"))
    pruefe([o.bezeichnung for o in r.objekte] == ["Buchs AG"],
           "gleicher Gemeindename, andere PLZ: nicht vergleichbar")
    pruefe("andere PLZ" in r.ausgeschlossen[0]["grund"], "und der Grund nennt die PLZ")

    # Reine Angebotsdaten koennen nie 'hoch' werden.
    # Gemessen im Segment Wohnung BESTAND: dorthin gehoeren Wohnungs-
    # inserate, seit "Verkauf" ausschliesslich Neubau meint. Die Aussage
    # dieses Tests ist der Sicherheitsgrad, nicht das Segment.
    angebote = [objekt(bezeichnung=f"A{i}", preis_chf_pro_m2=9000 + i * 20,
                       objektart="Eigentumswohnung", preisart=md.PREISART_ANGEBOT)
                for i in range(8)]
    nur_angebot = md.werte_referenzen_aus(angebote, md.GROESSE_WOHNUNG_BESTAND)
    pruefe(nur_angebot.sicherheit == md.SICHERHEIT_MITTEL,
           f"8 enge, aktuelle Angebotspreise ergeben hoechstens mittel ({nur_angebot.sicherheit})")
    pruefe(any("beurkundeter Abschluss" in b for b in nur_angebot.begruendung),
           "mit der Begruendung, dass Handaenderungsdaten fehlen")

    mit_abschluss = md.werte_referenzen_aus(
        angebote + [objekt(bezeichnung="Beurkundet", preis_chf_pro_m2=9080,
                           objektart="Eigentumswohnung",
                           preisart=md.PREISART_ABSCHLUSS)],
        md.GROESSE_WOHNUNG_BESTAND)
    pruefe(mit_abschluss.sicherheit == md.SICHERHEIT_HOCH,
           f"mit einem beurkundeten Abschluss wird hoch erreichbar ({mit_abschluss.sicherheit})")
    pruefe(mit_abschluss.nach_preisart()[md.PREISART_ANGEBOT] == 8,
           "und die Zusammensetzung nach Preisart bleibt sichtbar")
    print()


def test_aussenkante_marktdaten() -> None:
    """Die Marktauswertung muss ueber den Endpunkt-Pfad ankommen.

    Geprueft wird das VERHALTEN von `webapp._rechne_entwicklung` -- genau der
    Funktion, die /entwicklung aufruft. Ein Test auf den Quelltext haette in
    Block 10 einen Verdrahtungsfehler durchgelassen; seither wird hier
    aufgerufen statt gelesen.
    """
    print("=== Aussenkante: Marktlage kommt ueber den Endpunkt-Pfad mit ===")

    import webapp
    from potenzial_engine import Analyse

    # Eine Analyse, wie sie aus dem Zwischenspeicher zurueckgebaut wird.
    analyse = Analyse(
        ergebnis={
            "adresse": "Rosenweg 4, 5033 Buchs AG",
            "modul1_geodaten": {
                "kataster": {"flaeche_m2": 600.0},
                "gemeinde": {"gemeinde": "Buchs (AG)", "kanton": "AG"},
                "geocoding": {"matched_label": "Rosenweg 4 5033 Buchs AG"},
            },
        },
        kontext={"modul1": {}},
    )
    pruefe(webapp._plz_aus_analyse(analyse.ergebnis) == "5033",
           "Die PLZ wird aus der geokodierten Adresse gelesen -- keine neue Abfrage")

    antwort = webapp._rechne_entwicklung(analyse, {
        "zielmarge": 0.15,
        # Im Request mitgegebene Referenzen decken den Fall ab, dass die
        # Datenschicht auf diesem Rechner leer ist.
        "vergleichsobjekte": [
            {"bezeichnung": f"Referenz {i}", "quelle": "Test",
             "datenstand": heute_minus(1), "plz": "5033", "gemeinde": "Buchs (AG)",
             "objektart": "Eigentumswohnung", "preisart": md.PREISART_ABSCHLUSS,
             "preis_chf_pro_m2": 9000 + i * 50}
            for i in range(3)
        ],
    })

    gebiet = antwort.get("referenzgebiet") or {}
    pruefe(gebiet.get("plz") == "5033",
           f"Das Referenzgebiet nennt die PLZ ({gebiet.get('plz')})")
    pruefe("je_groesse" in gebiet
           and set(gebiet["je_groesse"]) == set(md.GROESSEN_REIHENFOLGE),
           "und fuer jedes Segment, welches Gebiet ausgewertet wurde "
           f"({sorted(gebiet.get('je_groesse') or {})})")

    lage = antwort.get("marktlage") or {}
    fehlend = [f"{g}.{k}" for g in lage for k in
               ("mindestanforderung", "nach_preisart", "ausgeschlossen_nach_art",
                "systemvorschlag", "punktwert_belastbar")
               if k not in lage[g]]
    pruefe(not fehlend, f"Jede Marktgroesse traegt die Einstufung mit ({fehlend})")

    verkauf = lage[md.GROESSE_VERKAUF]
    pruefe(verkauf["mindestanforderung"]["min_objekte"] == md.MIN_OBJEKTE_MITTEL,
           "Die Mindestanforderung steht in der Antwort und stammt aus EINER Konstante")
    # Bewusst keine feste Zahl: auf diesem Rechner liegen zusaetzlich die
    # gespeicherten Referenzen in der Datenschicht, und ein Test, der von
    # deren Inhalt abhaengt, faellt beim naechsten Import um.
    pruefe(verkauf["mindestanforderung"]["erfuellt"] is True
           and verkauf["systemvorschlag"] is not None,
           f"Drei passende Abschluesse ergeben einen Vorschlag ({verkauf['systemvorschlag']})")
    pruefe(verkauf["spanne"] and verkauf["spanne"][0] <= verkauf["systemvorschlag"]
           <= verkauf["spanne"][1],
           "und er liegt innerhalb der Referenzspanne")

    # Und die Wirtschaftlichkeit rechnet mit genau diesem Wert weiter -- nicht
    # mit einem zweiten, anderswo gebildeten.
    preis = (((antwort.get("wirtschaftlichkeit") or {}).get("szenarien") or {})
             .get("ersatzneubau") or {}).get("verkauf") or {}
    if preis.get("preis"):
        pruefe(preis["preis"].get("systemvorschlag") == verkauf["systemvorschlag"],
               "derselbe Vorschlag steht im Verkaufspreis der Rechnung")
    print()


def test_qualitaet_eine_terminologie() -> None:
    """Eine Skala, ein Normalisierungsweg -- fuer Hand und CSV gleich.

    Live beobachtet: das Erfassungsformular bot "geprueft / angegeben /
    geschaetzt / unbekannt", die Engine kennt "hoch / mittel / gering /
    unbekannt". Drei der vier Auswahlen wurden beim Speichern abgewiesen,
    darunter die VORAUSWAHL -- ein Formular, dessen Standardeinstellung
    nicht speicherbar war.

    Dasselbe Wort hatte dabei je nach Eingabeweg drei Bedeutungen:
    ueber CSV wurde es still zu "unbekannt", ueber die Handerfassung war
    es ein Fehler, und gemeint war "hoch".
    """
    print("\n== Qualitaet: eine Terminologie ==")

    # 1. Die kanonische Skala ist vollstaendig erklaert -- die Saetze
    #    stehen hier und nicht in der Oberflaeche, sonst driften sie.
    pruefe(set(md.QUALITAET_BEDEUTUNG) == md._QUALITAETEN,
           "jede Qualitaetsstufe hat eine Bedeutung hinterlegt")

    # 2. Die alten Woerter werden erkannt -- ausdruecklich, nicht geraten.
    for wort, erwartet in (("geprueft", md.QUALITAET_HOCH),
                           ("geprüft", md.QUALITAET_HOCH),
                           ("angegeben", md.QUALITAET_MITTEL),
                           ("geschaetzt", md.QUALITAET_GERING),
                           ("geschätzt", md.QUALITAET_GERING),
                           ("unbekannt", md.QUALITAET_UNBEKANNT)):
        stufe, roh = md.normalisiere_qualitaet(wort)
        pruefe(stufe == erwartet and roh is None,
               f"'{wort}' wird zu '{erwartet}' (gefunden: {stufe})")

    # 3. Die kanonischen Werte bleiben, wie sie sind -- auch in anderer
    #    Schreibweise.
    for wort in ("hoch", "MITTEL", " gering "):
        stufe, roh = md.normalisiere_qualitaet(wort)
        pruefe(stufe == wort.strip().lower() and roh is None,
               f"'{wort}' bleibt '{stufe}'")

    # 4. Was NICHT in der Tabelle steht, wird nicht geraten: "unbekannt"
    #    ist die ehrliche Antwort, und der Rohtext bleibt erhalten.
    stufe, roh = md.normalisiere_qualitaet("Sternchen")
    pruefe(stufe == md.QUALITAET_UNBEKANNT and roh == "Sternchen",
           "ein unbekanntes Wort wird 'unbekannt' UND behaelt seinen Rohwert")
    stufe, roh = md.normalisiere_qualitaet(None)
    pruefe(stufe == md.QUALITAET_UNBEKANNT and roh is None,
           "keine Angabe ist 'unbekannt' ohne Rohwert -- es gibt keinen")

    # 5. Der Kern: Handerfassung und CSV verhalten sich GLEICH. Das war
    #    der eigentliche Fehler -- nicht die Woerter, sondern die zwei
    #    verschiedenen Antworten auf dieselbe Eingabe.
    basis = {"bezeichnung": "X", "quelle": "T", "datenstand": "2026-06-01",
             "objektart": "ETW", "preis_chf_pro_m2": 8900}
    for wort in ("geprueft", "angegeben", "geschaetzt", "hoch", "unbekannt", "Sternchen"):
        per_hand, fehler = md.aus_dicts([dict(basis, datenqualitaet=wort)])
        csv = ("bezeichnung;objektart;preis_chf_pro_m2;datenqualitaet\n"
               f"X;ETW;8900;{wort}")
        per_csv, _ = md.lese_csv(csv, quelle="T", datenstand="2026-06-01")
        pruefe(len(per_hand) == 1 and len(per_csv) == 1,
               f"'{wort}' wird auf BEIDEN Wegen angenommen"
               + (f" (Hand: {fehler[0]['grund'][:40]})" if fehler else ""))
        if per_hand and per_csv:
            pruefe(per_hand[0].datenqualitaet == per_csv[0].datenqualitaet,
                   f"'{wort}' ergibt beidseitig '{per_hand[0].datenqualitaet}'")
            pruefe(per_hand[0].merkmale.get("datenqualitaet_roh")
                   == per_csv[0].merkmale.get("datenqualitaet_roh"),
                   f"'{wort}': der Rohwert wird beidseitig gleich behandelt")

    # 6. Die Vorauswahl des Formulars muss speicherbar sein. Genau das
    #    war sie nicht.
    objekte, fehler = md.aus_dicts([dict(basis, datenqualitaet="unbekannt")])
    pruefe(len(objekte) == 1 and not fehler,
           "die Vorauswahl 'unbekannt' laesst sich speichern")

    # 7. Eine ungueltige Stufe direkt im Datenmodell bleibt ein Fehler --
    #    die Normalisierung gehoert an den Rand, nicht in den Kern.
    try:
        md.Vergleichsobjekt(bezeichnung="X", quelle="T", datenstand="2026-06-01",
                            preis_chf_pro_m2=8900, datenqualitaet="geprueft")
        pruefe(False, "Vergleichsobjekt weist eine nicht kanonische Stufe ab")
    except md.MarktdatenError:
        pruefe(True, "Vergleichsobjekt weist eine nicht kanonische Stufe ab")

    # 8. Was die Stufe TATSAECHLICH bewirkt -- gemessen, nicht vermutet.
    #
    #    Sie erscheint in der BEGRUENDUNG des Sicherheitsgrads, wo
    #    "gering" und "unbekannt" zusammengezaehlt werden. Die Stufe des
    #    Sicherheitsgrads selbst aendert sie heute NICHT (_sicherheit
    #    haengt an Anzahl, Streuung, Aktualitaet und Preisart). Der Test
    #    haelt diesen Stand fest, damit eine spaetere Aenderung daran
    #    eine bewusste ist und keine stille.
    def lage(stufe: str):
        eintraege = [
            {"bezeichnung": f"O{i}", "quelle": "T", "datenstand": "2026-06-01",
             "objektart": "ETW", "preis_chf_pro_m2": p, "datenqualitaet": stufe,
             "preisart": md.PREISART_ABSCHLUSS}
            # Genug Referenzen fuer "hoch" und eng beieinander -- sonst
            # entscheidet nicht die Qualitaetsstufe, sondern die Anzahl
            # oder die Streuung, und der Test misst etwas anderes.
            for i, p in enumerate(8500 + 20 * n for n in range(md.MIN_OBJEKTE_HOCH))
        ]
        objekte, _ = md.aus_dicts(eintraege)
        return md.werte_referenzen_aus(objekte, md.GROESSE_VERKAUF)

    pruefe(lage(md.QUALITAET_HOCH).sicherheit == md.SICHERHEIT_HOCH,
           f"{md.MIN_OBJEKTE_HOCH} belegte Referenzen ergeben Sicherheit hoch "
           f"(gefunden: {lage(md.QUALITAET_HOCH).sicherheit})")
    for stufe in (md.QUALITAET_UNBEKANNT, md.QUALITAET_GERING):
        ref = lage(stufe)
        text = " ".join(ref.begruendung)
        pruefe("geringe oder unbekannte Datenqualitaet" in text,
               f"'{stufe}' wird in der Begruendung des Sicherheitsgrads ausgewiesen")
        pruefe(f"{md.MIN_OBJEKTE_HOCH} von {md.MIN_OBJEKTE_HOCH}" in text,
               f"'{stufe}' zaehlt dabei wie 'gering' -- beide in derselben Zahl")
        pruefe(ref.sicherheit == md.SICHERHEIT_HOCH,
               f"'{stufe}' aendert die STUFE des Sicherheitsgrads heute nicht "
               f"(gefunden: {ref.sicherheit}) -- festgehaltener Stand")
    pruefe("Datenqualitaet" not in " ".join(lage(md.QUALITAET_HOCH).begruendung),
           "bei belegten Angaben steht dazu nichts in der Begruendung")


def main() -> None:
    test_vergleichsobjekt()
    test_import()
    test_filter()
    test_sicherheit()
    test_uebergabe()
    test_objektart_normalisieren()
    test_eignung()
    test_plausibilitaet_und_ausreisser()
    test_plz_und_preisart()
    test_marktlage()
    test_aussenkante_marktdaten()
    test_qualitaet_eine_terminologie()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE MARKTDATEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

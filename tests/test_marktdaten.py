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
    pruefe(wenige.systemvorschlag is not None,
           "der Median existiert trotzdem -- er ist nur schwach gestuetzt")

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

    schwach = md.werte_referenzen_aus([objekt(preis_chf_pro_m2=9000)], md.GROESSE_VERKAUF)
    mw = schwach.als_marktwert()
    pruefe("schwach gestuetzt" in mw.begruendung,
           f"bei geringer Sicherheit steht das im Klartext ({mw.begruendung[:60]})")

    leer = md.werte_referenzen_aus([], md.GROESSE_VERKAUF).als_marktwert()
    pruefe(leer.wert is None and leer.herkunft == HERKUNFT_NICHT_BESTIMMBAR,
           "ohne Referenzen und ohne Benutzerwert bleibt es nicht bestimmbar")
    leer_mit = md.werte_referenzen_aus([], md.GROESSE_VERKAUF).als_marktwert(benutzerannahme=9500)
    pruefe(leer_mit.wert == 9500,
           "eine Benutzerannahme genuegt auch ganz ohne Referenzen")
    print()


def test_marktlage() -> None:
    print("=== Marktlage: alle drei Groessen auf einmal ===")
    objekte = [
        objekt(bezeichnung="Verkauf A", preis_chf_pro_m2=9000),
        objekt(bezeichnung="Verkauf B", preis_chf_pro_m2=9200),
        objekt(bezeichnung="Miete A", preis_chf_pro_m2=None, mietzins_chf_pro_m2_jahr=260),
        objekt(bezeichnung="Bauland", objektart="Bauland", preis_chf_pro_m2=None,
               bodenpreis_chf_pro_m2=950),
    ]
    lage = md.marktlage(objekte)
    pruefe(set(lage) == {"verkauf", "miete", "boden"}, "alle drei Groessen ausgewertet")
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


def main() -> None:
    test_vergleichsobjekt()
    test_import()
    test_filter()
    test_sicherheit()
    test_uebergabe()
    test_marktlage()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE MARKTDATEN-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

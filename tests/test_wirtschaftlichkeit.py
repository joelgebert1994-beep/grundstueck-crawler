"""
Regressionstests fuer Stufe 5: Markt, BKP und Wirtschaftlichkeit.

Vollstaendig OFFLINE -- konstruierte Szenarien, keine Netzabfrage.

Geprueft wird, was fachlich schiefgehen kann:

  * Eine Referenz darf NIE die Benutzerannahme ersetzen. Gerechnet wird immer
    mit der Benutzerannahme, und alle drei Ebenen bleiben sichtbar.
  * Jede Kostenposition muss ihre Berechnungsbasis ausweisen -- CHF/m² auf
    welcher Flaeche, Prozent von welcher Groesse.
  * Eine Summe von 0 CHF, die nur entstand, weil nichts berechenbar war, ist
    irrefuehrend und muss `None` sein.
  * Einem Anbau die vollen Landkosten anzulasten ist die Kaufsicht -- gehoert
    das Grundstueck bereits, aendert sich das Ergebnis erheblich. Beide Faelle
    muessen unterscheidbar sein.
  * Jede Aenderung (Preis, Mix, BKP, Zielmarge) muss durch die ganze Rechnung
    laufen, bis zum Residualwert.
  * Fehlt eine Grundlage, ist das Ergebnis nicht_bestimmbar MIT Ursache.

CLI: python -m tests.test_wirtschaftlichkeit
"""

from __future__ import annotations

import sys

from potenzial_engine import wirtschaftlichkeit as w
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


def flaechen(gf=1000.0, nf=731.0, hnf=658.0, nwf=658.0):
    return {
        "geschossflaeche_gf": {"wert": gf},
        "nettogeschossflaeche_ngf": {"wert": 850.0},
        "nutzflaeche_nf": {"wert": nf},
        "hauptnutzflaeche_hnf": {"wert": hnf},
        "wohnflaeche_nwf": {"wert": nwf},
    }


def wohnungen(anzahl=7):
    return {
        "anzahl_wohnungen": anzahl,
        "typen": [
            {"typ": "2.5 Zi", "anzahl": 2, "flaeche_pro_einheit_m2": 62.0},
            {"typ": "3.5 Zi", "anzahl": 3, "flaeche_pro_einheit_m2": 88.0},
            {"typ": "4.5 Zi", "anzahl": 2, "flaeche_pro_einheit_m2": 112.0},
        ],
    }


def szenario(id="ersatzneubau", **kw):
    s = {
        "id": id, "bezeichnung": "Ersatzneubau", "machbarkeit": "moeglich",
        "flaechen": {"flaechen": flaechen()}, "wohnungen": wohnungen(),
    }
    s.update(kw)
    return s


def markt(**kw):
    vorgabe = dict(
        verkauf=w.Verkaufsannahme(preis_pro_m2=w.marktwert("verkauf", "CHF/m2", benutzerannahme=9500)),
        miete=w.Mietannahme(miete_pro_m2_jahr=w.marktwert("miete", "CHF/m2/Jahr", benutzerannahme=265)),
        bodenpreis_chf_pro_m2=w.marktwert("boden", "CHF/m2", benutzerannahme=1050),
        zielmarge=0.15,
    )
    vorgabe.update(kw)
    return w.Marktannahmen(**vorgabe)


# ---------------------------------------------------------------------------
# 1. Marktwert: die drei Ebenen
# ---------------------------------------------------------------------------

def test_marktwert() -> None:
    print("=== Marktwert: Referenz, Systemvorschlag, Benutzerannahme ===")
    referenzen = [
        w.Referenzwert("Wüest Partner", "2026-06", "Vergleich A", 8700, "CHF/m2", "hoch"),
        w.Referenzwert("Wüest Partner", "2026-06", "Vergleich B", 9000, "CHF/m2", "hoch"),
        w.Referenzwert("Eigene Erhebung", "2026-05", "Vergleich C", 9300, "CHF/m2", "mittel"),
    ]
    mw = w.marktwert("verkauf", "CHF/m2", referenzen=referenzen)
    pruefe(mw.systemvorschlag == 9000.0, f"Systemvorschlag ist der Median der Referenzen ({mw.systemvorschlag})")
    pruefe(mw.spanne == (8700, 9300), f"Referenzspanne 8700-9300 ({mw.spanne})")
    pruefe(mw.wert == 9000.0, "ohne Benutzerannahme wird mit dem Systemvorschlag gerechnet")
    pruefe(mw.herkunft == HERKUNFT_SYSTEMANNAHME, "und das ist als Systemannahme gekennzeichnet")

    eigen = mw.mit_benutzerwert(9500)
    pruefe(eigen.wert == 9500, f"die Benutzerannahme ist massgebend ({eigen.wert})")
    pruefe(eigen.herkunft == HERKUNFT_BENUTZERANNAHME, "und als solche gekennzeichnet")
    pruefe(eigen.systemvorschlag == 9000.0, "der Systemvorschlag bleibt daneben sichtbar")
    pruefe(eigen.spanne == (8700, 9300), "die Referenzspanne bleibt sichtbar")
    d = eigen.to_dict()
    pruefe(d["anzahl_referenzen"] == 3 and d["referenzen"][0]["quelle"] == "Wüest Partner",
           "jede Referenz behaelt Quelle, Datum, Objekt und Qualitaet")

    leer = w.marktwert("verkauf", "CHF/m2")
    pruefe(leer.wert is None and leer.herkunft == HERKUNFT_NICHT_BESTIMMBAR,
           "ohne jede Angabe bleibt der Wert nicht bestimmbar")

    geworfen = None
    try:
        w.Referenzwert("", "2026-06", "X", 9000, "CHF/m2")
    except w.WirtschaftlichkeitError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "eine Referenz ohne Quelle wird abgelehnt")
    print()


# ---------------------------------------------------------------------------
# 2. Verkauf und Miete in allen Varianten
# ---------------------------------------------------------------------------

def test_verkauf() -> None:
    print("=== Verkauf: je m², je Wohnungstyp, je Wohnung ===")
    pro_m2 = w.Verkaufsannahme(basis="nwf", preis_pro_m2=w.marktwert("v", "CHF/m2", benutzerannahme=9500))
    r = pro_m2.berechne(flaechen(), wohnungen())
    pruefe(r["erloes_chf"] == 6251000, f"658 m² × 9500 = 6'251'000 ({r['erloes_chf']:,.0f})")
    pruefe("Wohnfläche NWF" in r["rechnung"], f"die Basis steht in der Rechnung ({r['rechnung']})")

    auf_hnf = w.Verkaufsannahme(basis="hnf", preis_pro_m2=w.marktwert("v", "CHF/m2", benutzerannahme=9500))
    pruefe(auf_hnf.berechne(flaechen(nwf=500.0), wohnungen())["erloes_chf"] == 6251000,
           "eine andere Basis rechnet auf einer anderen Flaeche")

    pro_typ = w.Verkaufsannahme(art=w.VERKAUF_PRO_TYP, preise_pro_typ={
        "2.5 Zi": w.marktwert("p", "CHF", benutzerannahme=720000),
        "3.5 Zi": w.marktwert("p", "CHF", benutzerannahme=980000),
        "4.5 Zi": w.marktwert("p", "CHF", benutzerannahme=1280000),
    })
    r2 = pro_typ.berechne(flaechen(), wohnungen())
    pruefe(r2["erloes_chf"] == 2 * 720000 + 3 * 980000 + 2 * 1280000,
           f"Preise je Typ summiert ({r2['erloes_chf']:,.0f})")
    pruefe(len(r2["zeilen"]) == 3, "je Typ eine Zeile")

    unvollstaendig = w.Verkaufsannahme(art=w.VERKAUF_PRO_TYP, preise_pro_typ={
        "2.5 Zi": w.marktwert("p", "CHF", benutzerannahme=720000)})
    r3 = unvollstaendig.berechne(flaechen(), wohnungen())
    pruefe(r3["erloes_chf"] is None, "ein fehlender Typpreis liefert keinen Teilerloes")
    pruefe("3.5 Zi" in r3["grund"], f"die fehlenden Typen sind benannt ({r3['grund']})")

    pro_wohnung = w.Verkaufsannahme(art=w.VERKAUF_PRO_WOHNUNG,
                                    preise_pro_wohnung=[700000] * 7)
    pruefe(pro_wohnung.berechne(flaechen(), wohnungen())["erloes_chf"] == 4900000,
           "Einzelpreise werden summiert")
    falsch = w.Verkaufsannahme(art=w.VERKAUF_PRO_WOHNUNG, preise_pro_wohnung=[700000] * 5)
    r4 = falsch.berechne(flaechen(), wohnungen())
    pruefe(r4["erloes_chf"] is None and "uebereinstimmen" in r4["grund"],
           "5 Preise fuer 7 Wohnungen werden abgelehnt")

    ohne_flaeche = pro_m2.berechne(flaechen(nwf=None), wohnungen())
    pruefe(ohne_flaeche["erloes_chf"] is None and "nicht bestimmt" in ohne_flaeche["grund"],
           "ohne Wohnflaeche kein Erloes, mit Ursache")
    print()


def test_restflaeche() -> None:
    """Die Flaechenkette muss geschlossen sein.

    Realfall Buchs AG: 197 m2 Wohnflaeche, ein Mix aus nur 3.5-/4.5-Zimmer-
    wohnungen belegt davon 125 m2. Die restlichen 72 m2 wurden frueher voll
    mitverkauft, obwohl sie keiner Wohnung zugeordnet sind. Genau das darf
    nicht passieren.
    """
    print("=== Flaechenkette: nicht zugeordnete Flaeche wird NICHT verkauft ===")
    from potenzial_engine.flaechenmodell import WohnungstypVorgabe, berechne_wohnungen

    mix = [WohnungstypVorgabe("3.5 Zi", 88.0, anteil=0.4),
           WohnungstypVorgabe("4.5 Zi", 125.0, anteil=0.6)]
    whg = berechne_wohnungen(197.0, mix, "Realfall Buchs AG")
    bilanz = whg["flaechenbilanz"]
    pruefe(bilanz["verfuegbar_m2"] == 197.0, "verfuegbare Flaeche in der Bilanz")
    pruefe(bilanz["belegt_m2"] == 125.0, f"belegt 125 m2 ({bilanz['belegt_m2']})")
    pruefe(bilanz["nicht_zugeordnet_m2"] == 72.0, f"72 m2 nicht zugeordnet ({bilanz['nicht_zugeordnet_m2']})")
    pruefe(bilanz["geschlossen"] is False, "die Kette ist damit nicht geschlossen")
    pruefe("KEINER Wohnung zugeordnet" in bilanz["hinweis"], "und das steht im Klartext")

    fl = flaechen(nwf=197.0)
    voll = w.Verkaufsannahme(basis="nwf", preis_pro_m2=w.marktwert("v", "CHF/m2", benutzerannahme=9500))
    r = voll.berechne(fl, whg)
    pruefe(r["erloes_chf"] == round(125.0 * 9500, 0),
           f"verkauft werden nur die zugeordneten 125 m2 ({r['erloes_chf']:,.0f})")
    pruefe(r["erloes_chf"] != round(197.0 * 9500, 0), "NICHT die vollen 197 m2")
    pruefe(r["basis_flaeche_m2"] == 125.0, "die Basis ist die belegte Flaeche")
    pruefe(r["nicht_zugeordnet_m2"] == 72.0, "die nicht zugeordnete Flaeche ist beziffert")
    pruefe("NICHT in die Rechnung ein" in (r["hinweis"] or ""), "und ausdruecklich ausgeschlossen")

    miete = w.Mietannahme(miete_pro_m2_jahr=w.marktwert("m", "CHF/m2/Jahr", benutzerannahme=265))
    m = miete.berechne(fl, whg)
    pruefe(m["jahresertrag_chf"] == round(125.0 * 265, 0),
           f"auch die Miete rechnet nur auf der zugeordneten Flaeche ({m['jahresertrag_chf']:,.0f})")
    pruefe(m["nicht_zugeordnet_m2"] == 72.0, "mit derselben Bezifferung")

    # Weg 1: Restflaeche auf die Wohnungen verteilen -- die Kette schliesst.
    verteilt = berechne_wohnungen(197.0, mix, "verteilt", restflaeche_verteilen=True)
    b2 = verteilt["flaechenbilanz"]
    pruefe(b2["geschlossen"] is True, "nach der Verteilung ist die Kette geschlossen")
    pruefe(b2["nicht_zugeordnet_m2"] == 0.0, "nichts bleibt unzugeordnet")
    pruefe(verteilt["anzahl_wohnungen"] == whg["anzahl_wohnungen"],
           "die Anzahl Wohnungen bleibt gleich")
    belegte = next(t for t in verteilt["typen"] if t["anzahl"])
    pruefe(belegte["flaeche_pro_einheit_m2"] > belegte["flaeche_pro_einheit_urspruenglich_m2"],
           f"die Wohnungen werden groesser ({belegte['flaeche_pro_einheit_urspruenglich_m2']} "
           f"-> {belegte['flaeche_pro_einheit_m2']} m2)")
    r2 = voll.berechne(fl, verteilt)
    pruefe(r2["erloes_chf"] == round(197.0 * 9500, 0),
           "jetzt DARF die volle Flaeche verkauft werden -- sie ist zugeordnet")
    pruefe(r2["nicht_zugeordnet_m2"] is None, "und es bleibt nichts offen")

    # Eine zu starke Streckung ist ein Warnsignal, kein stilles Ergebnis.
    pruefe(verteilt.get("verteilung_unplausibel") is True,
           f"58 % Wachstum wird als unplausibel gemeldet (Faktor {verteilt.get('verteilungsfaktor')})")
    pruefe("passt nicht zur verfuegbaren Flaeche" in verteilt["hinweis"],
           "mit dem Rat, lieber den Mix anzupassen")

    # Weg 2: ein Mix, der ohnehin aufgeht.
    guter_mix = [WohnungstypVorgabe("2.5 Zi", 62.0, anteil=0.2),
                 WohnungstypVorgabe("3.5 Zi", 88.0, anteil=0.5),
                 WohnungstypVorgabe("4.5 Zi", 112.0, anteil=0.3)]
    passt = berechne_wohnungen(900.0, guter_mix, "passt", restflaeche_verteilen=True)
    pruefe(passt["flaechenbilanz"]["geschlossen"] is True, "ein passender Mix schliesst die Kette")
    pruefe(passt.get("verteilung_unplausibel") is not True, "ohne Unplausibilitaets-Warnung")

    # Die Bilanz gehoert ins Szenario-Ergebnis.
    gesamt = w.berechne_fuer_szenario(
        szenario(flaechen={"flaechen": fl}, wohnungen=whg), 1200.0, markt())
    pruefe(gesamt["flaechenbilanz"]["nicht_zugeordnet_m2"] == 72.0,
           "die Flaechenbilanz steht im Szenario-Ergebnis")
    pruefe(any("KEINER Wohnung zugeordnet" in o for o in gesamt["offene_punkte"]),
           "und unter den offenen Punkten")
    print()


def test_miete() -> None:
    print("=== Miete: je m²/Jahr, je Typ, je Wohnung ===")
    pro_m2 = w.Mietannahme(miete_pro_m2_jahr=w.marktwert("m", "CHF/m2/Jahr", benutzerannahme=265))
    r = pro_m2.berechne(flaechen(), wohnungen())
    pruefe(r["jahresertrag_chf"] == round(658 * 265, 0), f"658 × 265 ({r['jahresertrag_chf']:,.0f})")

    pro_typ = w.Mietannahme(art=w.MIETE_PRO_TYP_MONAT, mieten_pro_typ_monat={
        "2.5 Zi": w.marktwert("m", "CHF/Mt", benutzerannahme=1950),
        "3.5 Zi": w.marktwert("m", "CHF/Mt", benutzerannahme=2450),
        "4.5 Zi": w.marktwert("m", "CHF/Mt", benutzerannahme=3050),
    })
    r2 = pro_typ.berechne(flaechen(), wohnungen())
    erwartet = (2 * 1950 + 3 * 2450 + 2 * 3050) * 12
    pruefe(r2["jahresertrag_chf"] == erwartet, f"Monatsmieten × 12 ({r2['jahresertrag_chf']:,.0f})")

    pro_wohnung = w.Mietannahme(art=w.MIETE_PRO_WOHNUNG_MONAT, mieten_pro_wohnung_monat=[2400] * 7)
    pruefe(pro_wohnung.berechne(flaechen(), wohnungen())["jahresertrag_chf"] == 2400 * 7 * 12,
           "Einzelmieten × 12")
    print()


# ---------------------------------------------------------------------------
# 3. Kosten: Basis muss sichtbar sein
# ---------------------------------------------------------------------------

def test_kosten() -> None:
    print("=== Kosten: jede Position weist ihre Basis aus ===")
    positionen = w.standard_kostenmodell()
    bkp = {p.bkp for p in positionen}
    pruefe({"1", "2", "3", "4", "5", "6"} <= bkp, f"BKP 1-6 sind alle vorhanden ({sorted(bkp)})")
    pruefe("F" in bkp and "V" in bkp, "Finanzierung und Vermarktung sind eigene Positionen")

    k = w.berechne_kosten(positionen, flaechen(), {"verkaufserloes": 6251000})
    nach = {p["schluessel"]: p for p in k["positionen"]}
    pruefe(nach["bkp2_gebaeude"]["betrag_chf"] == 2400 * 1000,
           f"BKP 2: 2400 CHF/m² × 1000 m² GF ({nach['bkp2_gebaeude']['betrag_chf']:,.0f})")
    pruefe("Geschossfläche GF" in nach["bkp2_gebaeude"]["rechnung"],
           f"mit sichtbarer Basis ({nach['bkp2_gebaeude']['rechnung']})")
    pruefe(nach["bkp4_umgebung"]["betrag_chf"] == round(2400 * 1000 * 0.05, 0),
           "BKP 4: 5 % von BKP 2")
    pruefe("bkp2_gebaeude" in nach["bkp4_umgebung"]["rechnung"],
           f"mit benannter Bezugsgroesse ({nach['bkp4_umgebung']['rechnung']})")
    pruefe(nach["vermarktung"]["betrag_chf"] == round(6251000 * 0.025, 0),
           "Vermarktung: 2.5 % des Verkaufserloeses")
    pruefe(k["vollstaendig"] is True, "alle Positionen berechenbar")
    pruefe(all(p["herkunft"] == HERKUNFT_SYSTEMANNAHME for p in k["positionen"]),
           "alle Standardansaetze sind als Systemannahme gekennzeichnet")

    # Benutzer aendert BKP 2.
    geaendert = [p.mit_benutzerwert(3250) if p.schluessel == "bkp2_gebaeude" else p for p in positionen]
    k2 = w.berechne_kosten(geaendert, flaechen(), {"verkaufserloes": 6251000})
    nach2 = {p["schluessel"]: p for p in k2["positionen"]}
    pruefe(nach2["bkp2_gebaeude"]["betrag_chf"] == 3250 * 1000, "geaenderter Ansatz wirkt sofort")
    pruefe(nach2["bkp2_gebaeude"]["herkunft"] == HERKUNFT_BENUTZERANNAHME, "als Benutzerannahme markiert")
    pruefe(nach2["bkp4_umgebung"]["betrag_chf"] > nach["bkp4_umgebung"]["betrag_chf"],
           "und schlaegt auf die davon abhaengigen Positionen durch")
    pruefe(k2["baukosten_chf"] > k["baukosten_chf"], "die Gesamtkosten steigen entsprechend")

    # Kostenbasis umstellen: CHF/m² HNF statt GF.
    auf_hnf = [w.Kostenposition("bkp2_gebaeude", "2", "Gebäude", w.KOSTEN_PRO_M2, 3250, "hnf")]
    k3 = w.berechne_kosten(auf_hnf, flaechen())
    pruefe(k3["positionen"][0]["betrag_chf"] == round(3250 * 658, 0),
           f"auf HNF gerechnet ({k3['positionen'][0]['betrag_chf']:,.0f})")
    pruefe("Hauptnutzfläche HNF" in k3["positionen"][0]["rechnung"], "Basis in der Rechnung sichtbar")

    # Absolutbetrag.
    absolut = [w.Kostenposition("bkp4_umgebung", "4", "Umgebung", w.KOSTEN_ABSOLUT, 300000)]
    pruefe(w.berechne_kosten(absolut, flaechen())["baukosten_chf"] == 300000,
           "ein Festbetrag wird unveraendert uebernommen")

    # Eine Summe von 0, die nur aus Nichtberechenbarem entsteht, ist irrefuehrend.
    ohne = w.berechne_kosten(w.standard_kostenmodell(), None)
    pruefe(ohne["baukosten_chf"] is None,
           f"ohne Flaechen keine Baukostensumme statt 0 CHF ({ohne['baukosten_chf']})")
    pruefe(any("irrefuehrend" in o for o in ohne["offene_positionen"]),
           "mit ausdruecklicher Begruendung")

    # Prozent auf eine unbekannte Bezugsgroesse.
    falsch = [w.Kostenposition("x", "9", "Test", w.KOSTEN_PROZENT, 0.1, "gibt_es_nicht")]
    z = w.berechne_kosten(falsch, flaechen())
    pruefe(z["positionen"][0]["betrag_chf"] is None and "nicht verfuegbar" in z["positionen"][0]["grund"],
           "eine unbekannte Bezugsgroesse wird benannt, nicht uebersprungen")
    print()


# ---------------------------------------------------------------------------
# 4. Gesamtrechnung, Zielmarge, Residualwert
# ---------------------------------------------------------------------------

def test_gesamtrechnung() -> None:
    print("=== Gesamtrechnung: Gewinn, Marge, Rendite, Residualwert ===")
    r = w.berechne_fuer_szenario(szenario(), 1200.0, markt())
    erg = r["ergebnis"]
    pruefe(erg["verkaufserloes_chf"] == 6251000, "Erloes aus Flaeche × Preis")
    pruefe(r["land"]["wert_chf"] == round(1200 * 1050, 0), f"Landwert 1200 m² × 1050 ({r['land']['wert_chf']:,.0f})")
    pruefe(erg["gesamtinvestition_chf"] == round(r["kosten"]["baukosten_chf"] + r["land"]["wert_chf"], 0),
           "Gesamtinvestition = Baukosten + Land")
    pruefe(erg["gewinn_chf"] == round(erg["verkaufserloes_chf"] - erg["gesamtinvestition_chf"], 0),
           "Gewinn = Erloes - Investition")
    # marge ist auf 4 Nachkommastellen gerundet -- die Toleranz muss das zulassen.
    pruefe(abs(erg["marge"] - erg["gewinn_chf"] / erg["verkaufserloes_chf"]) < 1e-4,
           f"Marge = Gewinn / Erloes ({erg['marge']:.1%})")
    pruefe(erg["zielmarge_erreicht"] == (erg["marge"] >= 0.15),
           f"Zielmarge-Aussage stimmt ({erg['zielmarge_erreicht']})")
    pruefe(erg["bruttorendite"] is not None, "Bruttorendite aus Mietertrag und Investition")
    pruefe(erg["kosten_pro_m2_nwf"] and erg["erloes_pro_m2_nwf"], "Kosten und Erloes je m² NWF")

    res = r["residualwert"]
    erwartet = round(6251000 - r["kosten"]["baukosten_chf"] - round(6251000 * 0.15, 0), 0)
    pruefe(res["max_landwert_chf"] == erwartet, f"Residualwert korrekt ({res['max_landwert_chf']:,.0f})")
    pruefe(res["max_landwert_chf_pro_m2"] == round(erwartet / 1200, 0), "und je m² Grundstueck")
    pruefe("Zielgewinn" in res["rechnung"], f"mit sichtbarer Rechnung ({res['rechnung'][:60]})")
    print()


def test_dynamik() -> None:
    print("=== Dynamik: jede Aenderung laeuft durch bis zum Residualwert ===")
    basis = w.berechne_fuer_szenario(szenario(), 1200.0, markt())

    # Verkaufspreis hoch -> Erloes, Gewinn, Marge, Residualwert steigen.
    teurer = w.berechne_fuer_szenario(szenario(), 1200.0, markt(
        verkauf=w.Verkaufsannahme(preis_pro_m2=w.marktwert("v", "CHF/m2", benutzerannahme=11000))))
    pruefe(teurer["ergebnis"]["verkaufserloes_chf"] > basis["ergebnis"]["verkaufserloes_chf"],
           "hoeherer Preis -> hoeherer Erloes")
    pruefe(teurer["ergebnis"]["gewinn_chf"] > basis["ergebnis"]["gewinn_chf"], "-> hoeherer Gewinn")
    pruefe(teurer["ergebnis"]["marge"] > basis["ergebnis"]["marge"], "-> hoehere Marge")
    pruefe(teurer["residualwert"]["max_landwert_chf"] > basis["residualwert"]["max_landwert_chf"],
           "-> hoeherer tragbarer Landwert")

    # Kleinere Wohnflaeche (anderer Mix) -> alles kleiner.
    kleiner = w.berechne_fuer_szenario(
        szenario(flaechen={"flaechen": flaechen(nwf=500.0)}), 1200.0, markt())
    pruefe(kleiner["ergebnis"]["verkaufserloes_chf"] < basis["ergebnis"]["verkaufserloes_chf"],
           "weniger Wohnflaeche -> weniger Erloes")
    pruefe(kleiner["residualwert"]["max_landwert_chf"] < basis["residualwert"]["max_landwert_chf"],
           "-> kleinerer Residualwert")

    # Hoehere BKP -> Gewinn und Residualwert sinken.
    teure_bkp = [p.mit_benutzerwert(3250) if p.schluessel == "bkp2_gebaeude" else p
                 for p in w.standard_kostenmodell()]
    mit_bkp = w.berechne_fuer_szenario(szenario(), 1200.0, markt(), teure_bkp)
    pruefe(mit_bkp["kosten"]["baukosten_chf"] > basis["kosten"]["baukosten_chf"], "hoehere BKP -> hoehere Kosten")
    pruefe(mit_bkp["ergebnis"]["gewinn_chf"] < basis["ergebnis"]["gewinn_chf"], "-> weniger Gewinn")
    pruefe(mit_bkp["residualwert"]["max_landwert_chf"] < basis["residualwert"]["max_landwert_chf"],
           "-> kleinerer Residualwert")

    # Hoehere Zielmarge -> Residualwert sinkt, Gewinn bleibt.
    streng = w.berechne_fuer_szenario(szenario(), 1200.0, markt(zielmarge=0.25))
    pruefe(streng["residualwert"]["max_landwert_chf"] < basis["residualwert"]["max_landwert_chf"],
           "hoehere Zielmarge -> kleinerer tragbarer Landwert")
    pruefe(streng["ergebnis"]["gewinn_chf"] == basis["ergebnis"]["gewinn_chf"],
           "der tatsaechliche Gewinn aendert sich dadurch nicht")
    pruefe(streng["ergebnis"]["zielmarge_erreicht"] is not basis["ergebnis"]["zielmarge_erreicht"]
           or streng["ergebnis"]["zielmarge"] == 0.25,
           "die Zielmarge wird im Ergebnis mitgefuehrt")

    # Hoeherer Bodenpreis -> Gewinn sinkt, Residualwert bleibt (er kennt kein Land).
    teures_land = w.berechne_fuer_szenario(szenario(), 1200.0, markt(
        bodenpreis_chf_pro_m2=w.marktwert("b", "CHF/m2", benutzerannahme=2000)))
    pruefe(teures_land["ergebnis"]["gewinn_chf"] < basis["ergebnis"]["gewinn_chf"],
           "teureres Land -> weniger Gewinn")
    pruefe(teures_land["residualwert"]["max_landwert_chf"] == basis["residualwert"]["max_landwert_chf"],
           "der Residualwert bleibt gleich -- er beantwortet die umgekehrte Frage")
    print()


def test_landansatz() -> None:
    print("=== Land: Kauf gegen bereits im Besitz ===")
    kauf = w.berechne_fuer_szenario(szenario("anbau"), 1200.0, markt(land_ansatz=w.LAND_KAUF))
    besitz = w.berechne_fuer_szenario(szenario("anbau"), 1200.0, markt(land_ansatz=w.LAND_IM_BESITZ))
    pruefe(kauf["land"]["wert_chf"] == 1260000, "im Kauffall die vollen Landkosten")
    pruefe(besitz["land"]["wert_chf"] == 0, "im Besitzfall keine Landkosten")
    pruefe(besitz["ergebnis"]["gewinn_chf"] > kauf["ergebnis"]["gewinn_chf"],
           "der Gewinn faellt entsprechend unterschiedlich aus")
    pruefe(besitz["residualwert"]["max_landwert_chf"] == kauf["residualwert"]["max_landwert_chf"],
           "der Residualwert ist in beiden Faellen derselbe")
    pruefe(any("VOLLEN Landkosten" in o for o in kauf["offene_punkte"]),
           "beim Anbau im Kauffall wird ausdruecklich darauf hingewiesen")
    pruefe(not any("VOLLEN Landkosten" in o for o in besitz["offene_punkte"]),
           "im Besitzfall entfaellt der Hinweis")
    pruefe("KEINE Landkosten" in besitz["land"]["ansatz_bedeutung"],
           "die Bedeutung des Ansatzes steht im Ergebnis")
    pruefe("erworben" in kauf["land"]["ansatz_bedeutung"],
           "und im Kauffall entsprechend anders")

    geworfen = None
    try:
        w.Marktannahmen(land_ansatz="irgendwas")
    except w.WirtschaftlichkeitError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "ein unbekannter Land-Ansatz wird abgelehnt")
    print()


def test_unvollstaendig() -> None:
    print("=== Fehlende Grundlagen: nicht bestimmbar MIT Ursache ===")
    ohne_preis = w.berechne_fuer_szenario(szenario(), 1200.0, w.Marktannahmen())
    pruefe(ohne_preis["ergebnis"]["verkaufserloes_chf"] is None, "ohne Verkaufsannahme kein Erloes")
    pruefe(ohne_preis["residualwert"]["status"] == HERKUNFT_NICHT_BESTIMMBAR,
           "und damit kein Residualwert")
    pruefe("Verkaufserloes" in ohne_preis["residualwert"]["grund"], "mit benannter Ursache")
    pruefe(any("Landwert" in o for o in ohne_preis["offene_punkte"]),
           "der fehlende Landwert steht unter den offenen Punkten")

    ohne_flaechen = w.berechne_fuer_szenario(
        szenario(flaechen=None, wohnungen=None), 1200.0, markt())
    pruefe(ohne_flaechen["ergebnis"]["verkaufserloes_chf"] is None, "ohne Flaechen kein Erloes")
    pruefe(ohne_flaechen["kosten"]["baukosten_chf"] is None, "und keine Baukosten")
    pruefe(len(ohne_flaechen["offene_punkte"]) >= 2, "mehrere offene Punkte benannt")

    negativ = w.berechne_fuer_szenario(szenario(), 1200.0, markt(
        verkauf=w.Verkaufsannahme(preis_pro_m2=w.marktwert("v", "CHF/m2", benutzerannahme=2000))))
    pruefe(negativ["residualwert"]["negativ"] is True, "ein negativer Residualwert wird als solcher markiert")
    pruefe("negativem Wert" in (negativ["residualwert"]["hinweis"] or ""),
           "mit Hinweis, welche Annahmen zu pruefen sind")
    print()


def test_vergleich() -> None:
    print("=== Szenarienvergleich ===")
    szenarien_ergebnis = {
        "szenarien": {
            "ersatzneubau": szenario("ersatzneubau"),
            "anbau": dict(szenario("anbau"), bezeichnung="Anbau",
                          flaechen={"flaechen": flaechen(nwf=200.0)}, wohnungen=wohnungen(2)),
            "bestand": {"id": "bestand", "bezeichnung": "Bestand", "machbarkeit": "besteht",
                        "flaechen": None, "wohnungen": None},
        }
    }
    r = w.berechne_alle(szenarien_ergebnis, 1200.0, markt())
    pruefe(len(r["vergleich"]) == 3, "eine Zeile je Szenario")
    pruefe(r["vergleich"][0]["id"] == "ersatzneubau",
           f"das Szenario mit dem hoechsten Landwert steht oben ({r['vergleich'][0]['id']})")
    pruefe(all("max_landwert_chf" in z for z in r["vergleich"]), "der Landwert steht im Vergleich")
    pruefe(all("kosten_vollstaendig" in z for z in r["vergleich"]),
           "und ob die Kosten vollstaendig berechenbar waren")
    bestand = next(z for z in r["vergleich"] if z["id"] == "bestand")
    pruefe(bestand["baukosten_chf"] is None, "der Bestand ohne Flaechen zeigt keine 0-Kosten")

    nur_eins = w.berechne_alle(szenarien_ergebnis, 1200.0, markt(), auswahl=["ersatzneubau"])
    pruefe(set(nur_eins["szenarien"]) == {"ersatzneubau"}, "die Auswahl wird beachtet")

    geworfen = None
    try:
        w.berechne_alle(szenarien_ergebnis, 1200.0, markt(), auswahl=["gibt_es_nicht"])
    except w.WirtschaftlichkeitError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "ein unbekanntes Szenario wird abgelehnt")

    leer = w.berechne_alle({"szenarien": {}, "grund": "Testgrund"}, 1200.0, markt())
    pruefe(leer["status"] == HERKUNFT_NICHT_BESTIMMBAR and "Testgrund" in leer["grund"],
           "ohne Szenarien wird der Grund durchgereicht")
    print()


def test_rueckwaertsrechnung() -> None:
    """Was muesste sich aendern, damit die Zielmarge aufgeht?

    Dieselbe Gleichung wie vorwaerts, nach einer anderen Unbekannten
    aufgeloest. Keine neue Rechenlogik, keine neue Datenquelle -- gerechnet
    wird mit genau den Groessen, die die Vorwaertsrechnung ohnehin bildet.

    Die schaerfste Probe steht gleich am Anfang: der rueckwaerts ermittelte
    Landpreis MUSS dem Residualwert entsprechen. Beide beantworten dieselbe
    Frage auf verschiedenen Wegen; weichen sie ab, ist eine der beiden
    Rechnungen falsch.
    """
    print("=== Rueckwaertsrechnung: was muesste sich aendern? ===")

    # Zahlen aus einer echten Rechnung (Rosenweg 4, Ersatzneubau).
    ERLOES, BAUKOSTEN, LAND = 1425000.0, 1019361.0, 628845.0
    FLAECHE_GS, FLAECHE_NWF, ZIEL = 598.9, 150.0, 0.15

    r = w._rueckwaertsrechnung(
        erloes=ERLOES, baukosten=BAUKOSTEN, landwert=LAND,
        marge=-0.1566, zielmarge=ZIEL,
        verkauf={"basis_flaeche_m2": FLAECHE_NWF, "basis_name": "Wohnflaeche NWF"},
        flaechen=None, grundstuecksflaeche_m2=FLAECHE_GS,
    )
    pruefe(r["status"] == "berechnet", "Mit allen Groessen ist sie berechenbar")
    pruefe(r["zielmarge_erreicht"] is False, "Die Zielmarge ist nicht erreicht")

    schrauben = {s["schluessel"]: s for s in r["stellschrauben"]}
    pruefe(set(schrauben) == {"landpreis", "verkaufserloes", "baukosten", "flaeche"},
           f"Vier Stellschrauben ({sorted(schrauben)})")

    # --- Die Kreuzprobe gegen den Residualwert ---------------------------
    residual = w._residualwert(ERLOES, BAUKOSTEN, ZIEL, FLAECHE_GS)
    pruefe(schrauben["landpreis"]["noetig_chf"] == residual["max_landwert_chf"],
           f"Der noetige Landpreis entspricht dem Residualwert "
           f"({schrauben['landpreis']['noetig_chf']:,.0f} CHF) -- zwei Wege, ein Ergebnis")
    pruefe(schrauben["landpreis"]["je_einheit"]["noetig"]
           == residual["max_landwert_chf_pro_m2"],
           "auch je Quadratmeter Grundstueck")

    # --- Die Gleichung geht auf --------------------------------------------
    noetiger_erloes = schrauben["verkaufserloes"]["noetig_chf"]
    marge_dann = (noetiger_erloes - BAUKOSTEN - LAND) / noetiger_erloes
    pruefe(abs(marge_dann - ZIEL) < 0.001,
           f"Beim noetigen Erloes ergibt sich genau die Zielmarge ({marge_dann:.3%})")

    noetige_kosten = schrauben["baukosten"]["noetig_chf"]
    marge_kosten = (ERLOES - noetige_kosten - LAND) / ERLOES
    pruefe(abs(marge_kosten - ZIEL) < 0.001,
           f"Bei den noetigen Baukosten ebenso ({marge_kosten:.3%})")

    # --- Die Luecke ist dieselbe, egal welche Schraube -------------------
    pruefe(schrauben["landpreis"]["aenderung_chf"] == schrauben["baukosten"]["aenderung_chf"],
           f"Land und Baukosten muessen um denselben Betrag sinken "
           f"({schrauben['landpreis']['aenderung_chf']:,.0f} CHF) -- beide stehen auf "
           "derselben Seite der Gleichung")
    pruefe(r["luecke_chf"] == -schrauben["landpreis"]["aenderung_chf"],
           "und das ist genau die ausgewiesene Luecke")

    # --- Richtung und Erfuellung -------------------------------------------
    pruefe(schrauben["landpreis"]["richtung"] == "tiefer"
           and schrauben["verkaufserloes"]["richtung"] == "hoeher",
           "Die Richtungen stimmen: Land tiefer, Erloes hoeher")
    pruefe(all(not s["erfuellt"] for s in schrauben.values() if s.get("status") == "berechnet"),
           "Keine Stellschraube ist erfuellt -- die Zielmarge ist ja verfehlt")

    # --- Je Einheit ---------------------------------------------------------
    je = schrauben["verkaufserloes"]["je_einheit"]
    pruefe(je["ist"] == round(ERLOES / FLAECHE_NWF, 0),
           f"Der Ist-Preis je m2 stimmt ({je['ist']:,.0f} CHF/m2)")
    pruefe(je["noetig"] > je["ist"], "und der noetige liegt darueber")

    # --- Erreichte Zielmarge: nichts muss sich bewegen ---------------------
    gut = w._rueckwaertsrechnung(
        erloes=2000000.0, baukosten=900000.0, landwert=400000.0,
        marge=0.35, zielmarge=ZIEL,
        verkauf={"basis_flaeche_m2": 200.0, "basis_name": "NWF"},
        flaechen=None, grundstuecksflaeche_m2=600.0)
    pruefe(gut["zielmarge_erreicht"] is True, "Bei erreichter Zielmarge wird das gemeldet")
    pruefe(gut["luecke_chf"] == 0, "die Luecke ist null")
    pruefe(all(s["erfuellt"] for s in gut["stellschrauben"] if s.get("status") == "berechnet"),
           "und jede Stellschraube gilt als erfuellt")

    # --- Mehr Flaeche hilft nicht immer -------------------------------------
    eng = w._rueckwaertsrechnung(
        erloes=1000000.0, baukosten=1100000.0, landwert=300000.0,
        marge=-0.40, zielmarge=ZIEL,
        verkauf={"basis_flaeche_m2": 120.0, "basis_name": "NWF"},
        flaechen=None, grundstuecksflaeche_m2=500.0)
    flaeche = next(s for s in eng["stellschrauben"] if s["schluessel"] == "flaeche")
    pruefe(flaeche["status"] == "nicht_zielfuehrend",
           "Liegen die Baukosten je m2 ueber dem Erloes je m2, ist mehr Flaeche nicht "
           "zielfuehrend")
    pruefe("verschlechtert das Ergebnis" in flaeche["grund"],
           "und es wird gesagt, dass zusaetzliche Flaeche es SCHLECHTER macht")
    pruefe("kein Mengen-, sondern ein Preis- oder Kostenproblem" in flaeche["grund"],
           "mit der richtigen Schlussfolgerung")

    # --- Keine Scheinpraezision ---------------------------------------------
    for fehlt, name in (
        (dict(erloes=None, baukosten=1e6, landwert=5e5), "Verkaufserloes"),
        (dict(erloes=1e6, baukosten=None, landwert=5e5), "Baukosten"),
        (dict(erloes=1e6, baukosten=1e6, landwert=None), "Landkosten"),
    ):
        ohne = w._rueckwaertsrechnung(
            marge=None, zielmarge=ZIEL, verkauf={}, flaechen=None,
            grundstuecksflaeche_m2=600.0, **fehlt)
        pruefe(ohne["status"] == "nicht_bestimmbar" and name in ohne["grund"],
               f"Fehlt {name}, wird nicht gerechnet -- der Grund nennt die Groesse")

    unsinn = w._rueckwaertsrechnung(
        erloes=1e6, baukosten=5e5, landwert=2e5, marge=0.3, zielmarge=1.0,
        verkauf={}, flaechen=None, grundstuecksflaeche_m2=600.0)
    pruefe(unsinn["status"] == "nicht_bestimmbar",
           "Eine Zielmarge von 100 % wird abgewiesen statt durch null geteilt")

    # --- Einordnung gegen erfasste Vergleichsobjekte ------------------------
    mit_markt = w._rueckwaertsrechnung(
        erloes=ERLOES, baukosten=BAUKOSTEN, landwert=LAND, marge=-0.1566, zielmarge=ZIEL,
        verkauf={"basis_flaeche_m2": FLAECHE_NWF, "basis_name": "NWF"},
        flaechen=None, grundstuecksflaeche_m2=FLAECHE_GS,
        marktlage={"verkauf": {"spanne": [8600, 9200]}})
    je_markt = next(s for s in mit_markt["stellschrauben"]
                    if s["schluessel"] == "verkaufserloes")["je_einheit"]
    pruefe(je_markt["im_referenzbereich"] is False,
           "Der noetige Preis liegt ueber allen Vergleichsobjekten")
    pruefe("am Markt zu belegen" in je_markt["einordnung"],
           "und das wird als solches benannt, nicht als Unmoeglichkeit")

    knapp = w._rueckwaertsrechnung(
        erloes=1900000.0, baukosten=1019361.0, landwert=400000.0, marge=0.10, zielmarge=0.10,
        verkauf={"basis_flaeche_m2": 200.0, "basis_name": "NWF"},
        flaechen=None, grundstuecksflaeche_m2=FLAECHE_GS,
        marktlage={"verkauf": {"spanne": [7000, 9200]}})
    je_knapp = next(s for s in knapp["stellschrauben"]
                    if s["schluessel"] == "verkaufserloes")["je_einheit"]
    pruefe(je_knapp["im_referenzbereich"] is True,
           f"Liegt er in der Spanne, wird das ebenso gesagt ({je_knapp['noetig']:,.0f} CHF/m2)")

    ohne_markt = w._rueckwaertsrechnung(
        erloes=ERLOES, baukosten=BAUKOSTEN, landwert=LAND, marge=-0.1566, zielmarge=ZIEL,
        verkauf={"basis_flaeche_m2": FLAECHE_NWF, "basis_name": "NWF"},
        flaechen=None, grundstuecksflaeche_m2=FLAECHE_GS)
    je_ohne = next(s for s in ohne_markt["stellschrauben"]
                   if s["schluessel"] == "verkaufserloes")["je_einheit"]
    pruefe("einordnung" not in je_ohne,
           "Ohne Vergleichsobjekte wird NICHT eingeordnet -- lieber keine Aussage als eine "
           "erfundene")
    print()


def main() -> None:
    test_rueckwaertsrechnung()
    test_marktwert()
    test_verkauf()
    test_restflaeche()
    test_miete()
    test_kosten()
    test_gesamtrechnung()
    test_dynamik()
    test_landansatz()
    test_unvollstaendig()
    test_vergleich()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE WIRTSCHAFTLICHKEITS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

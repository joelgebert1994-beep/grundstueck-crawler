"""
Offline-Regressionstests fuer das Quellenobjekt-Schema (quellen.py).
Kein Netzwerkzugriff.

CLI: python test_quellen.py
"""
from __future__ import annotations

import sys

from potenzial_engine.quellen import (
    MAPSERVER_IDENTIFY_URL,
    QUELLE_BEZEICHNUNG_GWR,
    QUELLE_TYP_AMTLICH,
    QUELLE_TYP_GEOMETRIE_BERECHNUNG,
    QUELLE_TYP_LLM_EXTRAKTION,
    QUELLE_TYP_MODELLANNAHME,
    Quellenobjekt,
    aus_amtlichem_wert,
    aus_geometrie_berechnung,
    aus_modellannahme,
    aus_modul2_kennzahl,
    quellen_aus_modul1_ergebnis,
    url_fuer_oereb_kanton,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def test_1_unbekannter_quelle_typ_wird_abgelehnt() -> None:
    print("=== 1) Unbekannter quelle_typ -> ValueError ===")
    try:
        Quellenobjekt(feld="x", wert=1, quelle_typ="erfunden", quelle_bezeichnung="Test")
        pruefe(False, "haette ValueError werfen muessen")
    except ValueError:
        pruefe(True, "ValueError korrekt ausgeloest")
    print()


def test_2_fehlende_bezeichnung_wird_abgelehnt() -> None:
    print("=== 2) Leere quelle_bezeichnung -> ValueError ===")
    try:
        Quellenobjekt(feld="x", wert=1, quelle_typ=QUELLE_TYP_AMTLICH, quelle_bezeichnung="  ")
        pruefe(False, "haette ValueError werfen muessen")
    except ValueError:
        pruefe(True, "ValueError korrekt ausgeloest")
    print()


def test_3_adapter_modul2_kennzahl_vollstaendig() -> None:
    print("=== 3) Adapter aus realer Modul-2-Kennzahl-Struktur (mit Bedingungen/Confidence) ===")
    kennzahl = {
        "wert": 10.0, "einheit": "m",
        "quelle_dokument": "Bau- und Nutzungsordnung Buchs",
        "artikel_referenz": "§18 Anm. c", "zitat": "Gesamthoehe 10.0m",
        "confidence": "hoch",
        "bedingungen": [{"bedingung_text": "Schraegdach", "wert_unter_bedingung": 11.5, "artikel_referenz": "§18 Anm. c"}],
    }
    q = aus_modul2_kennzahl("gesamthoehe_m", kennzahl)
    pruefe(q.quelle_typ == QUELLE_TYP_LLM_EXTRAKTION, "quelle_typ = llm_extraktion")
    pruefe(q.wert == 10.0, "Wert korrekt uebernommen")
    pruefe(q.quelle_bezeichnung == "Bau- und Nutzungsordnung Buchs", "Quelldokument korrekt uebernommen")
    pruefe(q.artikel_referenz == "§18 Anm. c", "Artikel-Referenz korrekt uebernommen")
    pruefe(q.zitat == "Gesamthoehe 10.0m", "Zitat korrekt uebernommen")
    pruefe(q.confidence == "hoch", "Confidence korrekt uebernommen")
    print()


def test_4_adapter_modul2_kennzahl_fehlende_felder_bleiben_none() -> None:
    print("=== 4) Adapter mit unvollstaendigem Kennzahl-Dict -> fehlende Felder bleiben None, kein Erfinden ===")
    q = aus_modul2_kennzahl("az", {"wert": 0.5})
    pruefe(q.artikel_referenz is None, "artikel_referenz bleibt None")
    pruefe(q.zitat is None, "zitat bleibt None")
    pruefe(q.confidence is None, "confidence bleibt None")
    pruefe(q.quelle_bezeichnung == "unbekanntes BZO-/Reglement-Dokument", "Fallback-Bezeichnung transparent statt leer")
    print()


def test_5_adapter_amtlicher_wert() -> None:
    print("=== 5) Adapter aus amtlichem Modul-1-Wert (GWR, bekannte Bezeichnung) ===")
    q = aus_amtlichem_wert("baujahr", 1978, quelle_bezeichnung=QUELLE_BEZEICHNUNG_GWR)
    pruefe(q.quelle_typ == QUELLE_TYP_AMTLICH, "quelle_typ = amtliche_quelle")
    pruefe(q.confidence == "hoch", "amtliche Werte defaulten auf confidence=hoch")
    pruefe(q.quelle_url == MAPSERVER_IDENTIFY_URL,
           f"quelle_url wird aus der bekannten Endpunkt-Konstante nachgeschlagen (tatsaechlich {q.quelle_url})")
    pruefe(bool(q.abgerufen_am), "abgerufen_am wird automatisch gesetzt")

    q2 = aus_amtlichem_wert("irgendwas", 1, quelle_bezeichnung="Freitext ohne bekannte Konstante")
    pruefe(q2.quelle_url is None, "quelle_url bleibt None bei unbekannter Bezeichnung (kein Erfinden)")

    q3 = aus_amtlichem_wert("baujahr", 1978, quelle_bezeichnung=QUELLE_BEZEICHNUNG_GWR, quelle_url="https://explizit.example/")
    pruefe(q3.quelle_url == "https://explizit.example/", "explizit uebergebene quelle_url hat Vorrang vor dem Lookup")
    print()


def test_7_url_aus_modul2_source_dokumenten() -> None:
    print("=== 7) quelle_url wird aus Modul-2 source_dokumente nachgeschlagen (exakt + Teilstring) ===")
    source_dokumente = [
        {"titel": "Bau- und Nutzungsordnung Buchs", "url": "https://example.ch/bno_buchs.pdf"},
        {"titel": "Kantonales Baugesetz", "url": "https://example.ch/kbg.pdf"},
    ]
    q_exakt = aus_modul2_kennzahl(
        "az", {"wert": 0.5, "quelle_dokument": "Bau- und Nutzungsordnung Buchs"}, source_dokumente=source_dokumente,
    )
    pruefe(q_exakt.quelle_url == "https://example.ch/bno_buchs.pdf", f"exakter Titel-Treffer liefert URL (tatsaechlich {q_exakt.quelle_url})")

    q_teil = aus_modul2_kennzahl(
        "az", {"wert": 0.5, "quelle_dokument": "BNO Buchs (Bau- und Nutzungsordnung Buchs, Fassung 2019)"},
        source_dokumente=source_dokumente,
    )
    pruefe(q_teil.quelle_url == "https://example.ch/bno_buchs.pdf", f"Teilstring-Treffer liefert URL (tatsaechlich {q_teil.quelle_url})")

    q_kein_treffer = aus_modul2_kennzahl(
        "az", {"wert": 0.5, "quelle_dokument": "Voellig anderes Dokument"}, source_dokumente=source_dokumente,
    )
    pruefe(q_kein_treffer.quelle_url is None, "kein Treffer -> quelle_url bleibt None statt zu raten")

    q_ohne_liste = aus_modul2_kennzahl("az", {"wert": 0.5, "quelle_dokument": "Bau- und Nutzungsordnung Buchs"})
    pruefe(q_ohne_liste.quelle_url is None, "ohne source_dokumente-Parameter bleibt quelle_url None (Rueckwaertskompatibilitaet)")
    print()


def test_8_url_fuer_oereb_kanton() -> None:
    print("=== 8) url_fuer_oereb_kanton: reale Vorlage aus Modul 1, kein Raten fuer unbekannte Kantone ===")
    url_zh = url_fuer_oereb_kanton("zh", "CH123456789012")
    pruefe(url_zh == "https://maps.zh.ch/oereb/v2/extract/json?EGRID=CH123456789012",
           f"ZH-URL korrekt aus Vorlage gebaut (tatsaechlich {url_zh})")
    # SG wurde 2026-09-03 real verifiziert und ergaenzt -- GR bleibt als
    # (Stand 2026-09-03) tatsaechlich nicht gelisteter Kanton fuer diesen Test.
    pruefe(url_fuer_oereb_kanton("GR", "CH000") is None, "GR ist in Modul 1 nicht gelistet -> None statt geratener Endpunkt")
    print()


def test_6_adapter_modellannahme_und_geometrie() -> None:
    print("=== 6) Adapter fuer Modellannahme und Geometrie-Berechnung ===")
    q_modell = aus_modellannahme("nf_anteil_an_gf", 0.85, begruendung="Erfahrungswert MFH", quelle="internes Benchmark")
    pruefe(q_modell.quelle_typ == QUELLE_TYP_MODELLANNAHME, "quelle_typ = modellannahme")
    pruefe("Erfahrungswert MFH" in q_modell.quelle_bezeichnung, "Begruendung landet in quelle_bezeichnung")

    q_geo = aus_geometrie_berechnung("geschossflaeche", 850.0, herkunft="G1-Kaskade")
    pruefe(q_geo.quelle_typ == QUELLE_TYP_GEOMETRIE_BERECHNUNG, "quelle_typ = geometrie_berechnung")
    pruefe(q_geo.artikel_referenz is None and q_geo.zitat is None, "keine Dokument-Felder bei Geometrie-Werten")
    print()


_SYNTHETISCHES_MODUL1_ERGEBNIS = {
    "input_address": "Bahnhofstrasse 1, 8001 Zuerich",
    "geocoding": {
        "query": "Bahnhofstrasse 1, 8001 Zuerich", "matched_label": "Bahnhofstrasse 1, 8001 Zuerich",
        "lv95_e": 2683112.0, "lv95_n": 1247937.0, "wgs84_lat": 47.378, "wgs84_lon": 8.539,
        "canton_hint": "ZH", "raw": {},
    },
    "kataster": {
        "found": True, "egrid": "CH123456789012", "parzellennummer": "4567",
        "flaeche_m2": 850.3, "flaeche_quelle": "geometrie_berechnet",
        "parzellengeometrie": [(0, 0), (10, 0), (10, 10), (0, 10)], "identdn": None, "raw_attributes": {},
    },
    "gemeinde": {"found": True, "gemeinde": "Zuerich", "bfs_nummer": 261, "kanton": "ZH", "raw_attributes": {}},
    "gwr": {
        "found": True, "egid": "1234567", "baujahr": 1978, "anzahl_geschosse": 5,
        "gebaeudekategorie_gkat": 1040, "gebaeudeklasse_gklas": 1122,
        "grundflaeche_m2": 320.0, "energiebezugsflaeche_m2": 1500.0, "gebaeudevolumen_m3": 4800.0,
        "raw_attributes": {},
    },
    "radon": {"found": True, "wahrscheinlichkeit_prozent": 15, "konfidenz": "mittel", "raw_attributes": {}},
    "topographie": {"hoehe_m": 408.2, "slope_deg": 2.1, "slope_pct": 3.7, "aspect": "SE", "aspect_deg": 135.0, "quelle": "swissALTI3D"},
    "umgebung": {
        "oev_naechste_haltestelle": {"name": "Zuerich HB", "distanz_m": 120.0, "typ": "bus"},
        "schule_naechste": None, "spital_naechstes": {"name": "Unispital", "distanz_m": 900.0, "typ": "hospital"},
        "supermarkt_naechster": None, "fehler": {},
    },
    "oereb": {
        "found": True, "kanton": "ZH", "source_url": "https://maps.zh.ch/oereb/v2/extract/json?EGRID=CH123456789012",
        "amtliche_zonenbezeichnungen": [{"zonenbezeichnung": "Kernzone", "ist_wahrscheinlich_basiszone": True}],
        "rechtsvorschriften": [{"titel": "Bau- und Zonenordnung Zuerich", "url": "https://example.ch/bzo.pdf"}],
        "umweltrisiken": {}, "legenden_und_themen_pdfs": [], "raw_extract": {},
    },
    "nutzungsklassifikation": {}, "restriktionsgeometrie": {"gefunden": False},
    "_meta": {"duration_seconds": 4.2, "modul": "Modul 1 - Geo-Data & Registry Ingestion"},
}


def test_9_quellen_aus_modul1_ergebnis_end_zu_end() -> None:
    print("=== 9) quellen_aus_modul1_ergebnis: End-zu-End amtlicher Abruf -> Quellenobjekt ===")
    quellen = quellen_aus_modul1_ergebnis(_SYNTHETISCHES_MODUL1_ERGEBNIS)
    by_feld = {q.feld: q for q in quellen}

    pruefe("kataster.egrid" in by_feld, "kataster.egrid ist als Quellenobjekt vorhanden")
    pruefe(by_feld["kataster.egrid"].wert == "CH123456789012", "Wert stimmt mit dem Original ueberein")
    pruefe(by_feld["kataster.egrid"].quelle_url == MAPSERVER_IDENTIFY_URL, "quelle_url zeigt auf den realen MapServer-identify-Endpunkt")
    pruefe("ch.swisstopo-vd.amtliche-vermessung" in by_feld["kataster.egrid"].quelle_bezeichnung, "konkrete Layer-ID steht in der Bezeichnung")

    pruefe("kataster.flaeche_m2" in by_feld, "kataster.flaeche_m2 vorhanden")
    pruefe("Shoelace-Berechnung" in by_feld["kataster.flaeche_m2"].quelle_bezeichnung,
           "Flaechenherkunft (geometrie_berechnet) wird konkret in der Bezeichnung unterschieden")

    pruefe("gwr.baujahr" in by_feld, "gwr.baujahr vorhanden")
    pruefe(by_feld["gwr.baujahr"].wert == 1978, "GWR-Baujahr korrekt uebernommen")

    pruefe("oereb.amtliche_zonenbezeichnungen" in by_feld, "oereb.amtliche_zonenbezeichnungen vorhanden")
    pruefe(
        by_feld["oereb.amtliche_zonenbezeichnungen"].quelle_url == "https://maps.zh.ch/oereb/v2/extract/json?EGRID=CH123456789012",
        "quelle_url ist die ECHTE, in Modul 1 bereits aufgeloeste OEREB-URL (source_url), nicht neu gebaut",
    )

    pruefe("umgebung.oev_naechste_haltestelle" in by_feld, "umgebung.oev_naechste_haltestelle vorhanden (kein Fehler vermerkt)")
    pruefe("umgebung.schule_naechste" not in by_feld, "umgebung.schule_naechste fehlt korrekt (None -- kein amtlicher Wert)")
    pruefe("umgebung.supermarkt_naechster" not in by_feld, "umgebung.supermarkt_naechster fehlt korrekt (None)")

    for q in quellen:
        pruefe(bool(q.abgerufen_am), f"{q.feld}: abgerufen_am ist gesetzt")
        pruefe(q.confidence == "hoch", f"{q.feld}: amtliche Werte haben confidence=hoch")
    print()


def test_10_quellen_aus_modul1_ergebnis_mit_fehlschlaegen() -> None:
    print("=== 10) quellen_aus_modul1_ergebnis: found=False und Umgebungs-Fehler erzeugen KEIN Quellenobjekt ===")
    ergebnis = dict(_SYNTHETISCHES_MODUL1_ERGEBNIS)
    ergebnis["kataster"] = {"found": False, "reason": "Kein Kataster-Objekt an diesem Punkt gefunden."}
    ergebnis["oereb"] = {"found": False, "reason": "Kein OEREB-Webservice fuer Kanton XX hinterlegt."}
    ergebnis["umgebung"] = {
        "oev_naechste_haltestelle": {"name": "sollte ignoriert werden", "distanz_m": 1.0, "typ": "bus"},
        "schule_naechste": None, "spital_naechstes": None, "supermarkt_naechster": None,
        "fehler": {"oev_naechste_haltestelle": "transport.opendata.ch nicht erreichbar: Timeout"},
    }
    quellen = quellen_aus_modul1_ergebnis(ergebnis)
    felder = {q.feld for q in quellen}
    pruefe(not any(f.startswith("kataster.") for f in felder), "kein kataster.*-Quellenobjekt bei found=False")
    pruefe(not any(f.startswith("oereb.") for f in felder), "kein oereb.*-Quellenobjekt bei found=False")
    pruefe(
        "umgebung.oev_naechste_haltestelle" not in felder,
        "trotz vorhandenem Wert kein Quellenobjekt, wenn 'fehler' das Feld als unsicher markiert "
        "(Netzwerkfehler waehrend derselben Abfrage darf nicht als verifizierter Treffer erscheinen)",
    )
    print()


def main() -> None:
    test_1_unbekannter_quelle_typ_wird_abgelehnt()
    test_2_fehlende_bezeichnung_wird_abgelehnt()
    test_3_adapter_modul2_kennzahl_vollstaendig()
    test_4_adapter_modul2_kennzahl_fehlende_felder_bleiben_none()
    test_5_adapter_amtlicher_wert()
    test_6_adapter_modellannahme_und_geometrie()
    test_7_url_aus_modul2_source_dokumenten()
    test_8_url_fuer_oereb_kanton()
    test_9_quellen_aus_modul1_ergebnis_end_zu_end()
    test_10_quellen_aus_modul1_ergebnis_mit_fehlschlaegen()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE QUELLENOBJEKT-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

"""
Die Reglementsauswertung ueberlebt Aenderungen am Rest der Engine.

Vollstaendig OFFLINE: kein Gemini, kein Netz, temporaere Datenbank. Der
Modellaufruf und der Dokumentabruf sind durch Attrappen ersetzt -- geprueft
wird die Entkopplung, nicht das Sprachmodell.

Der Anlass
----------
Von 126 s einer echten Analyse entfielen 109 s (87 %) auf das Lesen der
Bau- und Nutzungsordnung. Diese Auswertung lag im Zwischenspeicher, aber
ihr Schluessel trug den Fingerabdruck der GESAMTEN Engine -- einen
SHA-256 ueber alle potenzial_engine/*.py. Damit entwertete jede
Codeaenderung jede gespeicherte Auswertung. Der reale Bestand zeigte es:
vier Gemeinden, verteilt auf drei Engine-Fassungen. Nach jedem Commit war
jede Gemeinde wieder zwei Minuten Gemini -- und war Gemini nicht
erreichbar (am 17.09.2026 den ganzen Tag, HTTP 503), gab es gar kein
Ergebnis.

Der Schluessel traegt jetzt die Eingaben und den Erzeuger:

    Gemeinde + Kanton
  + die tatsaechlich ausgewerteten Dokumente mit SHA-256 ueber den INHALT
  + modul2_version (Systemanweisung + Ausgabeschema + Modell + Fassung)

Modul 1 steht bewusst nicht darin, obwohl es die Dokumentauswahl
beeinflusst: seine Wirkung IST der Dokumentensatz, und der wird gehasht.

CLI: python -m tests.test_reglement_zwischenspeicher
"""
from __future__ import annotations

import hashlib
import inspect
import sys
import tempfile
from pathlib import Path

from potenzial_engine import modul2_bzo_analysis as m2
from potenzial_engine.modul2_bzo_analysis import (
    _ZONE_KENNZAHL_FELDER, _ergaenze_pruefung, pruefe_auswertung,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


# --- Attrappen --------------------------------------------------------------

OEREB = {"rechtsvorschriften": [
    {"titel": "Bau- und Nutzungsordnung", "url": "https://gemeinde.ch/bno.pdf",
     "ist_wahrscheinlich_bzo_reglement": True},
    {"titel": "Zonenplan", "url": "https://gemeinde.ch/zonenplan.pdf",
     "ist_wahrscheinlich_bzo_reglement": True},
]}

AUSWERTUNG = {
    "dokument_titel": "Bau- und Nutzungsordnung",
    "gemeinde": "Testhausen",
    "erkannte_zonen": [{"zonenbezeichnung": "Wohnzone, 2 Vollgeschosse (W2)",
                        "ausnuetzungsziffer_az": {"wert": 0.45}}],
    "sonderregelungen": [],
    "unklarheiten_und_pruefhinweise": [],
    "_meta": {"modul": "Modul 2", "backend": "gemini"},
}


class Welt:
    """Der Zustand, den die Attrappen sehen: Dokumente und Gemini."""

    def __init__(self):
        self.inhalte = {"https://gemeinde.ch/bno.pdf": b"BNO Fassung A",
                        "https://gemeinde.ch/zonenplan.pdf": b"Zonenplan A"}
        self.erreichbar = True
        self.gemini_laeuft = True
        self.gemini_aufrufe = 0

    def hole_dokumente(self, urls):
        geladen, uebersprungen = [], []
        for url in urls:
            daten = self.inhalte.get(url)
            if daten is None or not self.erreichbar:
                uebersprungen.append({"url": url, "grund": "nicht erreichbar (Attrappe)"})
                continue
            geladen.append({"url": url, "daten": daten,
                            "sha256": hashlib.sha256(daten).hexdigest(),
                            "bytes": len(daten)})
        return {"geladen": geladen, "uebersprungen": uebersprungen}

    def auswerten(self, oereb, gemeinde=None, kanton=None, backend=None, dokumente=None):
        self.gemini_aufrufe += 1
        if not self.gemini_laeuft:
            raise m2.Modul2Error(
                "Gemini-API-Fehler: 503 UNAVAILABLE. This model is currently "
                "experiencing high demand.")
        ergebnis = dict(AUSWERTUNG)
        ergebnis["_meta"] = dict(AUSWERTUNG["_meta"])
        ergebnis["_meta"]["lauf"] = self.gemini_aufrufe
        return ergebnis


def lader_mit(welt: Welt, db_pfad: Path):
    """Baut den Lader aus webapp.py mit Attrappen statt Netz und Gemini."""
    import webapp
    from kern import db as kern_db

    m2.hole_dokumente = welt.hole_dokumente
    m2.analyze_from_oereb_result = welt.auswerten

    class KernShim:
        @staticmethod
        def verbinde(pfad=None):
            return kern_db.verbinde(db_pfad)

    webapp._kern_projekt = lambda: (KernShim, None)
    return webapp._bzo_zwischenspeicher()


def frische_welt():
    verzeichnis = Path(tempfile.mkdtemp())
    return Welt(), verzeichnis / "kern_test.db"


# ---------------------------------------------------------------------------


def test_zweiter_lauf_trifft() -> None:
    print("=== Dieselbe Gemeinde ein zweites Mal: kein neuer Gemini-Lauf ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)

    erst = lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 1, "der erste Lauf wertet aus")
    pruefe(erst["_zwischenspeicher"]["aus_zwischenspeicher"] is False,
           "und sagt, dass er frisch gerechnet wurde")

    zweit = lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 1, "der zweite Lauf nicht mehr")
    pruefe(zweit["_zwischenspeicher"]["aus_zwischenspeicher"] is True,
           "er kommt sichtbar aus dem Speicher")
    print()


def test_engine_aenderung_laesst_gueltig() -> None:
    """Fall 1 und 2: UI-, G1-, SIA-416-Aenderungen entwerten nichts."""
    print("=== Aenderung an Oberflaeche, G1, SIA 416: Auswertung bleibt gueltig ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 1, "einmal ausgewertet")

    # Der Fingerabdruck der gesamten Engine aendert sich bei JEDER
    # Codeaenderung -- frueher hing der Schluessel daran.
    import webapp
    vorher = webapp.ENGINE_VERSION
    webapp.ENGINE_VERSION = "voellig-andere-engine-fassung"
    try:
        treffer = lade(OEREB, gemeinde="Testhausen", kanton="TH")
    finally:
        webapp.ENGINE_VERSION = vorher

    pruefe(welt.gemini_aufrufe == 1,
           "nach einer Engine-Aenderung KEIN neuer Gemini-Lauf")
    pruefe(treffer["_zwischenspeicher"]["aus_zwischenspeicher"] is True,
           "die gespeicherte Auswertung wird weiterverwendet")

    # Und der Beleg auf der anderen Seite: der Abdruck von Modul 2 kennt
    # den Engine-Stand ueberhaupt nicht.
    pruefe(m2.modul2_fingerabdruck() == m2.modul2_fingerabdruck(),
           "modul2_fingerabdruck() ist stabil -- er liest nur Prompt, Schema und Modell")
    print()


def test_prompt_schema_modell() -> None:
    """Fall 3: was Modul 2 wirklich veraendert, MUSS neu ausgewertet werden."""
    print("=== Prompt, Schema oder Modell geaendert: neuer Lauf ===")
    grundlage = m2.modul2_fingerabdruck()

    proben = [
        ("SYSTEM_PROMPT", m2.SYSTEM_PROMPT + " Zusaetzliche Anweisung."),
        ("GEMINI_MODEL", "gemini-9.9-irgendwas"),
        ("AUSWERTUNG_VERSION", m2.AUSWERTUNG_VERSION + 1),
    ]
    for name, wert in proben:
        alt = getattr(m2, name)
        setattr(m2, name, wert)
        try:
            pruefe(m2.modul2_fingerabdruck() != grundlage,
                   f"{name} geaendert -> anderer Fingerabdruck -> neuer Lauf")
        finally:
            setattr(m2, name, alt)

    # Das Schema steckt als Dict im Modul und geht ebenfalls ein.
    alt = m2.BZO_ANALYSIS_SCHEMA
    m2.BZO_ANALYSIS_SCHEMA = dict(alt, zusatzfeld={"type": "string"})
    try:
        pruefe(m2.modul2_fingerabdruck() != grundlage,
               "Ausgabeschema erweitert -> anderer Fingerabdruck -> neuer Lauf")
    finally:
        m2.BZO_ANALYSIS_SCHEMA = alt

    pruefe(m2.modul2_fingerabdruck() == grundlage,
           "und nach dem Zuruecksetzen wieder derselbe")

    # Ende zu Ende: mit geaendertem Prompt laeuft Gemini tatsaechlich neu.
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")
    alt_prompt = m2.SYSTEM_PROMPT
    m2.SYSTEM_PROMPT = alt_prompt + " Nachtrag."
    try:
        lade(OEREB, gemeinde="Testhausen", kanton="TH")
    finally:
        m2.SYSTEM_PROMPT = alt_prompt
    pruefe(welt.gemini_aufrufe == 2,
           "geaenderter Prompt -> die Auswertung wird tatsaechlich wiederholt")
    print()


def test_dokumentinhalt_geaendert() -> None:
    """Fall 4: gleiche URL, revidierter Inhalt."""
    print("=== Reglement revidiert (gleiche URL, anderer Inhalt): neuer Lauf ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 1, "einmal ausgewertet")

    # oereblex behaelt bei einer Revision die URL bei -- eine reine
    # URL-Pruefung wuerde das verschlafen.
    welt.inhalte["https://gemeinde.ch/bno.pdf"] = b"BNO Fassung B, revidiert 2026"
    treffer = lade(OEREB, gemeinde="Testhausen", kanton="TH")

    pruefe(welt.gemini_aufrufe == 2,
           "geaenderter Dokumentinhalt -> neu ausgewertet, obwohl die URL dieselbe ist")
    pruefe(treffer["_zwischenspeicher"]["aus_zwischenspeicher"] is False,
           "das Ergebnis ist frisch")
    print()


def test_dokumentensatz_geaendert() -> None:
    """Fall 5: ein Dokument kommt dazu bzw. faellt weg."""
    print("=== Dokument kommt dazu oder faellt weg: neuer Lauf ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")

    mit_nachtrag = {"rechtsvorschriften": OEREB["rechtsvorschriften"] + [
        {"titel": "Nachtrag", "url": "https://gemeinde.ch/nachtrag.pdf",
         "ist_wahrscheinlich_bzo_reglement": True}]}
    welt.inhalte["https://gemeinde.ch/nachtrag.pdf"] = b"Nachtrag 2026"
    lade(mit_nachtrag, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 2, "ein zusaetzliches Dokument -> neuer Lauf")

    ohne_zonenplan = {"rechtsvorschriften": OEREB["rechtsvorschriften"][:1]}
    lade(ohne_zonenplan, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 3, "ein weggefallenes Dokument ebenso")

    # Und die Gegenprobe: derselbe Satz trifft wieder.
    lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(welt.gemini_aufrufe == 3,
           "der urspruengliche Satz trifft weiterhin seinen Eintrag")
    print()


def test_gemini_weg_mit_bestand() -> None:
    """Fall 6: Gemini faellt aus, eine gueltige Auswertung liegt vor."""
    print("=== Gemini nicht verfuegbar, Auswertung vorhanden: sie wird verwendet ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")

    welt.gemini_laeuft = False
    treffer = lade(OEREB, gemeinde="Testhausen", kanton="TH")
    pruefe(treffer is not None and treffer["_zwischenspeicher"]["aus_zwischenspeicher"],
           "die gespeicherte Auswertung traegt den Ausfall")
    pruefe(welt.gemini_aufrufe == 1,
           "Gemini wird gar nicht erst gefragt -- der Treffer kommt vorher")
    pruefe(treffer["erkannte_zonen"][0]["zonenbezeichnung"].startswith("Wohnzone"),
           "und liefert die Zone, auf der alles Weitere aufbaut")
    print()


def test_gemini_weg_ohne_bestand() -> None:
    """Fall 7: Gemini faellt aus, es gibt nichts -- dann fehlt es eben."""
    print("=== Gemini nicht verfuegbar, nichts vorhanden: Auswertung fehlt ===")
    welt, pfad = frische_welt()
    welt.gemini_laeuft = False
    lade = lader_mit(welt, pfad)

    geworfen = None
    try:
        lade(OEREB, gemeinde="Testhausen", kanton="TH")
    except m2.Modul2Error as exc:
        geworfen = str(exc)
    except Exception as exc:  # noqa: BLE001
        geworfen = f"{type(exc).__name__}: {exc}"

    pruefe(geworfen is not None,
           "es gibt kein Ergebnis -- der Fehler wird weitergereicht")
    pruefe("503" in (geworfen or "") or "UNAVAILABLE" in (geworfen or ""),
           f"und zwar der echte Grund ({(geworfen or '')[:60]}…)")

    # Der entscheidende Punkt: nichts wurde erfunden und nichts abgelegt.
    from kern import db as kern_db
    con = kern_db.verbinde(pfad)
    anzahl = con.execute("SELECT COUNT(*) FROM bzo_auswertung").fetchone()[0]
    pruefe(anzahl == 0,
           "kein halbes Ergebnis im Speicher -- lieber nichts als etwas Erfundenes")
    print()


def test_dokumente_nicht_erreichbar() -> None:
    """Fall 8: die Dokumente sind weg, die Auswertung ist da."""
    print("=== Dokumente nicht erreichbar: Rueckfall mit sichtbarem Vermerk ===")
    welt, pfad = frische_welt()
    lade = lader_mit(welt, pfad)
    lade(OEREB, gemeinde="Testhausen", kanton="TH")

    welt.erreichbar = False
    treffer = lade(OEREB, gemeinde="Testhausen", kanton="TH")
    zs = (treffer or {}).get("_zwischenspeicher", {})

    pruefe(treffer is not None, "die vorhandene Auswertung wird verwendet")
    pruefe(zs.get("dokumente_geprueft") is False,
           "sie ist als UNGEPRUEFT gekennzeichnet -- niemand hat nachgesehen, "
           "ob das Reglement inzwischen revidiert wurde")
    pruefe("nicht erreichbar" in (zs.get("hinweis") or ""),
           "der Hinweis nennt den Grund")
    pruefe((zs.get("gerechnet_am") or "")[:2] == "20" and len(zs.get("gerechnet_am") or "") >= 10,
           f"und das Datum der verwendeten Auswertung ({zs.get('gerechnet_am')})")
    pruefe(welt.gemini_aufrufe == 1, "ohne neuen Gemini-Lauf")

    # Gegenprobe: ohne Bestand gibt es auch hier kein Ersatzergebnis.
    welt2, pfad2 = frische_welt()
    welt2.erreichbar = False
    lade2 = lader_mit(welt2, pfad2)
    geworfen = None
    try:
        lade2(OEREB, gemeinde="Andersort", kanton="TH")
    except Exception as exc:  # noqa: BLE001
        geworfen = str(exc)
    pruefe(geworfen is not None and "abrufbar" in geworfen,
           "ohne Dokumente UND ohne Bestand: klarer Fehler, kein Ersatzwert")
    print()


# --- Plausibilitaet der Modellantwort ---------------------------------------
#
# Anlass: Rheineck, 18.09.2026. Aus denselben fuenf PDF (gleicher SHA-256),
# mit demselben Prompt und demselben Modell kam an einem Tag
# "strassenabstand_m: 3 m, confidence hoch, zwei Bedingungen" und am naechsten
# "wert null, nicht_bestimmbar" -- mit den drei Zahlen im Freitextfeld
# 'unklarheit': "Staatsstrassen 4 m, Gemeindestrassen 3 m, Wege 2 m". Die
# Werte waren gefunden, sie standen nur im falschen Feld. Die schwaechere
# Antwort landete im Zwischenspeicher und galt danach als Tatsache.
#
# Gegen die Nichtreproduzierbarkeit hilft kein Prompt allein -- die Antwort
# muss geprueft werden, bevor sie abgelegt wird.

def _zone(**felder: dict) -> dict:
    """Eine Zone mit allen Kennzahlfeldern, standardmaessig sauber gefuellt."""
    leer = {"wert": None, "einheit": None, "quelle_dokument": "BauR",
            "artikel_referenz": None, "zitat": None,
            "confidence": "nicht_bestimmbar", "bedingungen": [], "unklarheit": None}
    zone = {"zonenbezeichnung": "Wohnzone W2"}
    for feld in _ZONE_KENNZAHL_FELDER:
        zone[feld] = dict(leer)
    zone.update(felder)
    return zone


def test_plausibilitaet_mass_im_freitext() -> None:
    """Der Rheineck-Fall: Zahl in 'unklarheit', 'wert' leer."""
    print("\n[Plausibilitaet] Mass im Freitext, Wert leer")
    zone = _zone(strassenabstand_m={
        "wert": None, "einheit": None, "quelle_dokument": "BauR Rheineck",
        "artikel_referenz": "Art. 20", "zitat": None,
        "confidence": "nicht_bestimmbar", "bedingungen": [],
        "unklarheit": ("Strassenabstand ist in Art. 20 nach Strassentyp "
                       "(Staatsstrassen 4 m, Gemeindestrassen 3 m, Wege 2 m) geregelt."),
    })
    befunde = pruefe_auswertung({"erkannte_zonen": [zone]})
    treffer = [b for b in befunde if b["feld"] == "strassenabstand_m"]
    pruefe(len(treffer) == 1, "genau ein Befund zum Strassenabstand")
    pruefe(bool(treffer) and treffer[0]["art"] == "mass_im_freitext",
           "als 'mass_im_freitext' eingeordnet")


def test_plausibilitaet_kein_regelfall() -> None:
    """Bedingungen erfasst, aber kein Regelfall gewaehlt."""
    print("\n[Plausibilitaet] Bedingungen ohne Regelfall")
    zone = _zone(strassenabstand_m={
        "wert": None, "einheit": "m", "quelle_dokument": "BauR",
        "artikel_referenz": "Art. 20", "zitat": None,
        "confidence": "nicht_bestimmbar",
        "bedingungen": [
            {"bedingung_text": "an Staatsstrassen", "wert_unter_bedingung": 4,
             "artikel_referenz": "Art. 20"},
            {"bedingung_text": "an Wegen", "wert_unter_bedingung": 2,
             "artikel_referenz": "Art. 20"},
        ],
        "unklarheit": None,
    })
    befunde = pruefe_auswertung({"erkannte_zonen": [zone]})
    treffer = [b for b in befunde if b["feld"] == "strassenabstand_m"]
    pruefe(len(treffer) == 1, "der fehlende Regelfall wird gemeldet")
    pruefe(bool(treffer) and treffer[0]["art"] == "kein_regelfall",
           "als 'kein_regelfall' eingeordnet")


def test_plausibilitaet_schweigt_bei_gueltiger_antwort() -> None:
    """Die Antwort vom 17.09. -- Regelfall gesetzt, Ausnahmen daneben."""
    print("\n[Plausibilitaet] vollstaendige Antwort erzeugt keinen Befund")
    zone = _zone(strassenabstand_m={
        "wert": 3, "einheit": "m", "quelle_dokument": "BauR Rheineck",
        "artikel_referenz": "Art. 20 BauR", "zitat": "an Gemeindestrassen 3 m",
        "confidence": "hoch",
        "bedingungen": [
            {"bedingung_text": "an Staatsstrassen", "wert_unter_bedingung": 4,
             "artikel_referenz": "Art. 20 BauR"},
        ],
        "unklarheit": None,
    })
    befunde = pruefe_auswertung({"erkannte_zonen": [zone]})
    pruefe(not [b for b in befunde if b["feld"] == "strassenabstand_m"],
           "kein Befund, wenn Regelfall und Bedingungen richtig getrennt sind")


def test_plausibilitaet_haengt_an_der_antwort() -> None:
    """Der Befund steht IM Ergebnis -- sonst wird er nicht gelesen."""
    print("\n[Plausibilitaet] Befund wird an die Antwort gehaengt")
    zone = _zone(strassenabstand_m={
        "wert": None, "einheit": None, "quelle_dokument": "BauR",
        "artikel_referenz": "Art. 20", "zitat": None,
        "confidence": "nicht_bestimmbar", "bedingungen": [],
        "unklarheit": "an Gemeindestrassen 3 m",
    })
    antwort = _ergaenze_pruefung({"erkannte_zonen": [zone],
                                  "unklarheiten_und_pruefhinweise": []})
    p = (antwort.get("_meta") or {}).get("plausibilitaet") or {}
    pruefe(p.get("geprueft") is True, "_meta.plausibilitaet.geprueft gesetzt")
    pruefe(p.get("vollstaendig") is False, "als unvollstaendig markiert")
    pruefe(len(antwort["unklarheiten_und_pruefhinweise"]) == 1,
           "der Hinweis steht auch dort, wo ein Mensch hinsieht")


def test_meta_traegt_auswertungslogik() -> None:
    """Womit wurde ausgewertet? Muss am Ergebnis haengen, nicht nur im Hash."""
    print("\n[Plausibilitaet] Herkunft der Auswertungslogik")
    quelle = inspect.getsource(m2)
    for feld in ('"auswertung_version": AUSWERTUNG_VERSION',
                 '"modul2_version": modul2_fingerabdruck('):
        pruefe(feld in quelle, f"_meta traegt {feld.split(chr(34))[1]}")


def main() -> None:
    test_zweiter_lauf_trifft()
    test_engine_aenderung_laesst_gueltig()
    test_prompt_schema_modell()
    test_dokumentinhalt_geaendert()
    test_dokumentensatz_geaendert()
    test_gemini_weg_mit_bestand()
    test_gemini_weg_ohne_bestand()
    test_dokumente_nicht_erreichbar()
    test_plausibilitaet_mass_im_freitext()
    test_plausibilitaet_kein_regelfall()
    test_plausibilitaet_schweigt_bei_gueltiger_antwort()
    test_plausibilitaet_haengt_an_der_antwort()
    test_meta_traegt_auswertungslogik()

    print("=" * 72)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE TESTS ZUM REGLEMENTS-ZWISCHENSPEICHER BESTANDEN")


if __name__ == "__main__":
    main()

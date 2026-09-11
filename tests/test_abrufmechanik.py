"""
Regressionstests fuer die Abrufmechanik (Stufe 1 -- Abdeckung schliessen).

Diese Tests laufen VOLLSTAENDIG OFFLINE: alle HTTP-Zugriffe werden durch
Doubles ersetzt. Sie sichern genau die Faelle ab, die in den 15 Live-Analysen
vom 11.09.2026 ganze Analyselaeufe zum Absturz gebracht haben:

  1. _get_mit_wiederholung()
     - wiederholt bei Timeout/ConnectionError (api3.geo.admin.ch brach
       einmalig mit ReadTimeout ab und riss den ganzen Lauf mit)
     - wiederholt bei 403/429/5xx und schickt ab dem 2. Versuch einen
       Browser-User-Agent (Gemeinde-Websites weisen unbekannte UAs ab)
     - wiederholt NICHT bei 404 -- eine echte Ablehnung bleibt eine Ablehnung
     - gibt am Ende den letzten echten Fehler weiter, nicht None

  2. analyze_bzo_from_urls()
     - ein einzelnes nicht ladbares Dokument darf die Analyse nicht abbrechen
       (live: Berlingen TG, http://www.berlingen.ch -> HTTP 403 auch mit
       Browser-UA; raise_for_status() wirft HTTPError, nicht Modul2Error --
       genau diese Luecke liess den Lauf scheitern)
     - das uebersprungene Dokument muss transparent ausgewiesen werden
     - wenn KEINE URL ein Dokument liefert, muss abgebrochen werden

  3. OEREB-Abdeckung
     - BE und SO sind hinterlegt (in Stufe 1 ergaenzt; BE nutzt einen
       Endpunkt ohne /oereb/-Pfadsegment, SO liefert ausschliesslich XML)
     - _oereb_xml_zu_dict() erzeugt aus der XML-Serialisierung dieselbe
       Struktur, die die Extraktoren vom JSON kennen

CLI: python -m tests.test_abrufmechanik
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ElementTree

import requests

from potenzial_engine import modul1_geodata as m1
from potenzial_engine import modul2_bzo_analysis as m2

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


class AntwortDouble:
    """Minimale requests.Response-Attrappe."""

    def __init__(self, status_code: int, text: str = "", content_type: str = "application/pdf"):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error", response=self)


class SessionDouble:
    """Ersetzt modul1_geodata.session.get und protokolliert jeden Versuch."""

    def __init__(self, antworten: list):
        self.antworten = list(antworten)
        self.aufrufe: list[dict] = []

    def get(self, url, timeout=None, headers=None, **kwargs):
        self.aufrufe.append({"url": url, "headers": dict(headers or {})})
        naechste = self.antworten.pop(0)
        if isinstance(naechste, Exception):
            raise naechste
        return naechste


def _mit_session(antworten: list):
    """Tauscht die Modul-1-Session gegen ein Double und gibt beide zurueck."""
    double = SessionDouble(antworten)
    original = m1.session
    m1.session = double
    return double, original


# ---------------------------------------------------------------------------
# 1. _get_mit_wiederholung
# ---------------------------------------------------------------------------

def test_wiederholung() -> None:
    print("=== _get_mit_wiederholung: Wiederholung und User-Agent-Wechsel ===")
    original_sleep = m1.time.sleep
    m1.time.sleep = lambda _s: None  # Tests sollen nicht real warten
    try:
        # a) Timeout beim ersten Versuch -> zweiter Versuch liefert das Ergebnis
        double, original = _mit_session([
            requests.exceptions.ReadTimeout("simulierter ReadTimeout"),
            AntwortDouble(200, "ok"),
        ])
        try:
            resp = m1._get_mit_wiederholung("https://example.test/a")
            pruefe(resp.status_code == 200, "ReadTimeout wird wiederholt und liefert danach 200")
            pruefe(len(double.aufrufe) == 2, f"genau 2 Versuche unternommen ({len(double.aufrufe)})")
        finally:
            m1.session = original

        # b) 403 beim ersten Versuch -> zweiter Versuch mit Browser-User-Agent
        double, original = _mit_session([AntwortDouble(403), AntwortDouble(200, "ok")])
        try:
            resp = m1._get_mit_wiederholung("https://example.test/b")
            pruefe(resp.status_code == 200, "403 wird wiederholt und liefert danach 200")
            pruefe(
                "User-Agent" not in double.aufrufe[0]["headers"],
                "erster Versuch ohne aufgesetzten Browser-User-Agent",
            )
            pruefe(
                double.aufrufe[1]["headers"].get("User-Agent") == m1.BROWSER_USER_AGENT,
                "zweiter Versuch mit Browser-User-Agent",
            )
        finally:
            m1.session = original

        # c) 404 ist eine echte Ablehnung -- kein zweiter Versuch
        double, original = _mit_session([AntwortDouble(404)])
        try:
            resp = m1._get_mit_wiederholung("https://example.test/c")
            pruefe(resp.status_code == 404, "404 wird unveraendert zurueckgegeben")
            pruefe(len(double.aufrufe) == 1, f"404 loest KEINE Wiederholung aus ({len(double.aufrufe)} Versuch(e))")
        finally:
            m1.session = original

        # d) dauerhaft 403 -> die Antwort wird zurueckgegeben, der Aufrufer
        #    entscheidet per raise_for_status(). Genau so entstand live der
        #    Berlingen-HTTPError; er gehoert dorthin und darf hier NICHT
        #    verschluckt werden.
        double, original = _mit_session([AntwortDouble(403), AntwortDouble(403), AntwortDouble(403)])
        try:
            resp = m1._get_mit_wiederholung("https://example.test/d")
            pruefe(len(double.aufrufe) == 3, f"alle 3 Versuche unternommen ({len(double.aufrufe)})")
            pruefe(resp.status_code == 403, "dauerhaftes 403 wird als Antwort durchgereicht")
            geworfen = None
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as exc:
                geworfen = exc
            pruefe(geworfen is not None, "der Aufrufer erhaelt daraus einen HTTPError")
        finally:
            m1.session = original

        # e) dauerhafter Verbindungsabbruch -> es gibt keine Antwort, also
        #    muss der letzte echte Fehler weitergereicht werden (nie None).
        double, original = _mit_session([
            requests.exceptions.ConnectionError("abbruch 1"),
            requests.exceptions.ConnectionError("abbruch 2"),
            requests.exceptions.ConnectionError("abbruch 3"),
        ])
        try:
            geworfen = None
            try:
                m1._get_mit_wiederholung("https://example.test/e")
            except Exception as exc:  # noqa: BLE001 -- der Typ ist Teil der Pruefung
                geworfen = exc
            pruefe(
                isinstance(geworfen, requests.exceptions.RequestException),
                f"dauerhafter Verbindungsabbruch wirft RequestException ({type(geworfen).__name__})",
            )
            pruefe(len(double.aufrufe) == 3, f"auch hier alle 3 Versuche unternommen ({len(double.aufrufe)})")
        finally:
            m1.session = original
    finally:
        m1.time.sleep = original_sleep


# ---------------------------------------------------------------------------
# 2. analyze_bzo_from_urls: ein Dokument darf den Lauf nicht reissen
# ---------------------------------------------------------------------------

def test_dokument_ueberspringen() -> None:
    print("=== analyze_bzo_from_urls: nicht ladbares Dokument wird uebersprungen ===")
    gesperrt = "http://www.berlingen.ch"
    erreichbar = "https://oereblex.tg.ch/api/attachments/11194"

    def download_double(url, timeout=m2.DEFAULT_TIMEOUT):
        if url == gesperrt:
            # Exakt das reale Verhalten: raise_for_status() wirft HTTPError.
            raise requests.exceptions.HTTPError(f"403 Client Error:  for url: {url}/")
        return b"%PDF-1.4 simuliertes Dokument"

    analysiert: dict = {}

    def analyse_double(pdf_documents, gemeinde=None, kanton=None, backend=None, max_tokens=8000):
        analysiert["anzahl"] = len(pdf_documents)
        return {"_meta": {}, "zonen": []}

    o_download, o_analyse = m2.download_pdf, m2.analyze_bzo_documents
    m2.download_pdf, m2.analyze_bzo_documents = download_double, analyse_double
    try:
        ergebnis = m2.analyze_bzo_from_urls([erreichbar, gesperrt], gemeinde="Berlingen", kanton="TG")
        pruefe(analysiert.get("anzahl") == 1, f"das erreichbare Dokument wurde analysiert ({analysiert.get('anzahl')})")
        uebersprungen = ergebnis["_meta"].get("uebersprungene_dokumente") or []
        pruefe(len(uebersprungen) == 1, f"genau 1 uebersprungenes Dokument ausgewiesen ({len(uebersprungen)})")
        pruefe(
            bool(uebersprungen) and uebersprungen[0]["url"] == gesperrt,
            "die gesperrte URL ist namentlich ausgewiesen",
        )
        grund = uebersprungen[0]["grund"] if uebersprungen else ""
        pruefe("HTTPError" in grund, f"der Grund nennt den Fehlertyp ({grund[:40]})")

        # Wenn KEINE URL etwas liefert, muss weiterhin abgebrochen werden --
        # eine Analyse ohne Dokument waere Scheingenauigkeit.
        abbruch = None
        try:
            m2.analyze_bzo_from_urls([gesperrt], gemeinde="Berlingen", kanton="TG")
        except m2.Modul2Error as exc:
            abbruch = exc
        pruefe(abbruch is not None, "ohne jedes ladbare Dokument wird sauber abgebrochen")
        pruefe(
            abbruch is not None and gesperrt in str(abbruch),
            "die Abbruchmeldung nennt die gescheiterte URL",
        )
    finally:
        m2.download_pdf, m2.analyze_bzo_documents = o_download, o_analyse


# ---------------------------------------------------------------------------
# 3. OEREB-Abdeckung: BE/SO und die XML-Serialisierung
# ---------------------------------------------------------------------------

_XML_BEISPIEL = """<Extract xmlns="http://schemas.geo.admin.ch/V_D/OeREB/2.0/Extract">
  <RealEstate>
    <Number>1145</Number>
    <LandRegistryArea>1234</LandRegistryArea>
    <RestrictionOnLandownership>
      <PartInPercent>12.5</PartInPercent>
      <Information><LocalisedText><Language>de</Language><Text>Wohnzone W2</Text></LocalisedText></Information>
    </RestrictionOnLandownership>
  </RealEstate>
</Extract>"""


def test_oereb_abdeckung() -> None:
    print("=== OEREB: Kantonsabdeckung und XML-Serialisierung ===")
    pruefe("BE" in m1.OEREB_CANTON_SERVICES, "Kanton BE ist hinterlegt")
    pruefe("SO" in m1.OEREB_CANTON_SERVICES, "Kanton SO ist hinterlegt")
    pruefe(
        "/oereb/" not in m1.OEREB_CANTON_SERVICES.get("BE", ""),
        "BE-Endpunkt ohne /oereb/-Pfadsegment (live verifiziert)",
    )
    pruefe(m1.OEREB_CANTON_FORMAT.get("SO") == "xml", "SO ist als XML-Dienst markiert")
    pruefe(m1.OEREB_CANTON_FORMAT.get("ZH", "json") == "json", "Kantone ohne Eintrag bleiben auf JSON")
    for kanton, template in sorted(m1.OEREB_CANTON_SERVICES.items()):
        pruefe("{egrid}" in template, f"{kanton}-Vorlage enthaelt den EGRID-Platzhalter")

    # XML -> dict: Einzelvorkommen muessen zu Listen werden, MultilingualText
    # muss auf die JSON-Form reduziert werden, Zahlenfelder auf float.
    data = m1._oereb_xml_zu_dict(ElementTree.fromstring(_XML_BEISPIEL))
    re_ = data.get("RealEstate") or {}
    restriktionen = re_.get("RestrictionOnLandownership")
    pruefe(isinstance(restriktionen, list), f"einzelne Restriktion wird zur Liste ({type(restriktionen).__name__})")
    # Ganzzahlige Werte bleiben int -- genau wie in der JSON-Serialisierung,
    # damit beide Wege dieselben Typen liefern.
    flaeche = re_.get("LandRegistryArea")
    pruefe(
        isinstance(flaeche, int) and not isinstance(flaeche, bool) and flaeche == 1234,
        f"LandRegistryArea als Zahl, ganzzahlig wie im JSON ({flaeche!r})",
    )
    erste = restriktionen[0] if isinstance(restriktionen, list) else {}
    pruefe(
        isinstance(erste.get("PartInPercent"), float) and erste["PartInPercent"] == 12.5,
        f"PartInPercent als Zahl ({erste.get('PartInPercent')!r})",
    )
    info = erste.get("Information")
    pruefe(
        isinstance(info, list) and bool(info) and info[0].get("Text") == "Wohnzone W2",
        f"MultilingualText auf die JSON-Form reduziert ({info!r})",
    )


def main() -> None:
    test_wiederholung()
    test_dokument_ueberspringen()
    test_oereb_abdeckung()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE ABRUFMECHANIK-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

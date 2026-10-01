"""
Die Reglementsauswertung ist technisch robust und von der uebrigen Analyse
getrennt.

Vollstaendig OFFLINE: Modul 1, der Dokumentabruf und der Gemini-Client sind
Attrappen, die Datenbank ist temporaer. Die Endpunkte /analyze, /status und
/analyse/reglement laufen dagegen echt -- ueber einen lokalen HTTP-Server.
Der Gemini-Client wird auf SDK-Ebene ersetzt (google.genai.Client), damit
Klassifikation, Retry und Timeout aus Modul 2 unveraendert mitlaufen.

Szenarien:
  A  503 -> 503 -> Erfolg          completed, keine zweite Grundstuecksanalyse
  B  503 -> 503 -> 503             temporarily_unavailable, amtliche Daten bleiben
  C  B + manuelles Wiederholen     nur der Reglementsschritt, danach completed
  D  RECITATION / HTTP 400         failed, nicht wiederholbar, kein Retry
  E  Cache-Treffer                 kein Gemini-Aufruf
  F  geaendertes Dokument          kein falscher Treffer
  G  zwei parallele Auftraege      ein Gemini-Aufruf

CLI: python -m tests.test_reglement_stabilitaet
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import webapp
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from kern import db as kern_db
from potenzial_engine import modul2_bzo_analysis as m2
from potenzial_engine import pipeline
from tests.test_phasen import MODUL1, MODUL2

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


AUSWERTUNG = {**copy.deepcopy(MODUL2), "dokument_titel": "BNO", "gemeinde": "Buchs (AG)",
              "stand_datum": None, "sonderregelungen": [], "unklarheiten_und_pruefhinweise": []}


def fehler_503():
    return genai_errors.ServerError(503, {"error": {
        "code": 503, "status": "UNAVAILABLE",
        "message": "This model is currently experiencing high demand."}})


def fehler_400():
    return genai_errors.ClientError(400, {"error": {
        "code": 400, "status": "INVALID_ARGUMENT", "message": "Request contains an invalid argument."}})


# --- Attrappen ---------------------------------------------------------------

class Welt:
    """Alles, was die Attrappen sehen: Dokumente, Gemini, Modul 1."""

    def __init__(self):
        self.inhalte = {"https://x/bno.pdf": b"BNO Fassung A"}
        self.skript: list = []           # je Gemini-Aufruf: Exception, "recitation" oder "ok"
        self.gemini_aufrufe = 0
        self.timeouts_ms: list = []
        self.pausen: list[float] = []
        self.modul1_aufrufe = 0
        self.gemini_dauer_s = 0.0
        self.lock = threading.Lock()

    # Modul 1 -- zaehlt, ob eine Grundstuecksanalyse neu gestartet wird.
    # `geo` ist die bereits aufgeloeste Adresse (seit 30.09.2026 wird sie
    # genau einmal aufgeloest und durchgereicht).
    def run_modul1(self, adresse, geo=None):
        with self.lock:
            self.modul1_aufrufe += 1
        return copy.deepcopy(MODUL1)

    # Die Adressaufloesung gehoert zur Welt der Attrappen -- sonst ginge
    # dieser Offline-Test fuer den Suchdienst doch ans Netz.
    def geocode(self, adresse, *_args):
        g = copy.deepcopy(MODUL1.get("geocoding") or {})
        g.setdefault("lv95_e", 2647000.0)
        g.setdefault("lv95_n", 1248000.0)
        g.update(query=adresse, feature_id="attrappe_0", auswahlmethode="text_exakt")
        return g

    def hole_dokumente(self, urls):
        geladen = []
        for url in urls:
            daten = self.inhalte.get(url)
            if daten is not None:
                geladen.append({"url": url, "daten": daten, "bytes": len(daten),
                                "sha256": hashlib.sha256(daten).hexdigest()})
        return {"geladen": geladen, "uebersprungen": []}

    # Der Gemini-Client auf SDK-Ebene
    def generate_content(self, model, contents, config):
        with self.lock:
            self.gemini_aufrufe += 1
            self.timeouts_ms.append(config.http_options.timeout)
            schritt = self.skript.pop(0) if self.skript else "ok"
        if self.gemini_dauer_s:
            time.sleep(self.gemini_dauer_s)
        if isinstance(schritt, BaseException):
            raise schritt
        grund = (genai_types.FinishReason.RECITATION if schritt == "recitation"
                 else genai_types.FinishReason.STOP)
        return SimpleNamespace(candidates=[SimpleNamespace(finish_reason=grund)],
                               text="" if schritt == "recitation" else json.dumps(AUSWERTUNG),
                               usage_metadata=None)


def einrichten(welt: Welt) -> Path:
    """Haengt die Attrappen ein und gibt den Pfad der temporaeren DB zurueck."""
    db_pfad = Path(tempfile.mkdtemp()) / "kern_test.db"

    class KernShim:
        def __getattr__(self, name):
            return getattr(kern_db, name)

        def verbinde(self, pfad=None):
            return kern_db.verbinde(db_pfad)

    webapp._kern_projekt = lambda: (KernShim(), None)
    webapp.ZUGANGSSCHLUESSEL = ""
    os.environ["GEMINI_API_KEY"] = "attrappe"
    pipeline.run_modul1 = welt.run_modul1
    webapp.geocode_address = welt.geocode
    webapp.geocode_auswahl = welt.geocode
    # Die Parzellenabfrage der Zwischenspeicher-Suche ebenso: ohne EGRID
    # gibt es keinen Treffer, und das ist hier gewollt (neu_rechnen).
    webapp.get_parcel_data = lambda e, n: {}
    m2.hole_dokumente = welt.hole_dokumente
    genai.Client = lambda *a, **k: SimpleNamespace(
        models=SimpleNamespace(generate_content=welt.generate_content))
    # Nur die Wartezeiten von Modul 2 werden aufgezeichnet statt abgewartet.
    m2.time = SimpleNamespace(sleep=welt.pausen.append, monotonic=time.monotonic, time=time.time)
    return db_pfad


class Server:
    def __init__(self):
        self.httpd = webapp.ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
        self.basis = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def post(self, pfad, daten):
        anfrage = urllib.request.Request(self.basis + pfad, data=json.dumps(daten).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def status(self, job_id):
        with urllib.request.urlopen(f"{self.basis}/status/{job_id}", timeout=10) as r:
            return json.loads(r.read())

    def warte(self, job_id, grenze_s=15):
        ende = time.time() + grenze_s
        while time.time() < ende:
            s = self.status(job_id)
            if s["status"] != "running":
                return s
            time.sleep(0.05)
        raise AssertionError("Job endet nicht")

    def analyse(self):
        _, a = self.post("/analyze", {"adresse": "Rosenweg 4, 5033 Buchs AG", "neu_rechnen": True})
        return a["job_id"], self.warte(a["job_id"])

    def schliessen(self):
        self.httpd.shutdown()


def anzahl_gespeichert(db_pfad: Path) -> int:
    return kern_db.verbinde(db_pfad).execute("SELECT COUNT(*) FROM bzo_auswertung").fetchone()[0]


# --- Einheiten: Klassifikation und Wiederholung ------------------------------

def test_klassifikation() -> None:
    print("=== Fehlerklassifikation ===")
    import httpx
    faelle = [
        (genai_errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}),
         m2.FEHLERART_RATE_LIMIT, True),
        (fehler_503(), m2.FEHLERART_DIENST_UEBERLASTET, True),
        (genai_errors.ServerError(504, {"error": {"code": 504, "status": "DEADLINE_EXCEEDED"}}),
         m2.FEHLERART_ZEITUEBERSCHREITUNG, True),
        (httpx.ReadTimeout("timed out"), m2.FEHLERART_ZEITUEBERSCHREITUNG, True),
        (TimeoutError(), m2.FEHLERART_ZEITUEBERSCHREITUNG, True),
        (httpx.ConnectError("connection refused"), m2.FEHLERART_NETZWERK, True),
        (ConnectionResetError(), m2.FEHLERART_NETZWERK, True),
        (fehler_400(), m2.FEHLERART_API_FEHLER, False),
        (genai_errors.ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED"}}),
         m2.FEHLERART_API_FEHLER, False),
        (ValueError("irgendetwas"), m2.FEHLERART_UNBEKANNT, False),
    ]
    for exc, art, temporaer in faelle:
        ist = m2.klassifiziere_fehler(exc)
        pruefe(ist == art and (ist in m2.TEMPORAERE_FEHLERARTEN) == temporaer,
               f"{type(exc).__name__}: {art} ({'wiederholbar' if temporaer else 'dauerhaft'})")

    alt = m2.Modul2Error("x")
    pruefe(alt.fehlerart == m2.FEHLERART_UNBEKANNT and alt.wiederholbar is False,
           "Modul2Error ohne Angaben bleibt gueltig -- und ist nicht pauschal wiederholbar")
    print()


def test_backoff_und_fenster() -> None:
    print("=== Backoff mit Jitter, Obergrenze, Gesamtfenster ===")
    pausen = [m2._wartezeit(v) for v in (1, 2, 3, 4) for _ in range(50)]
    p1, p2, p4 = pausen[:50], pausen[50:100], pausen[150:]
    b, j = m2.GEMINI_RETRY_BASE_DELAY_S, m2.GEMINI_RETRY_JITTER_ANTEIL
    pruefe(all(b <= p <= b * (1 + j) for p in p1), f"1. Pause {b}..{b * (1 + j):.0f} s")
    pruefe(all(2 * b <= p <= 2 * b * (1 + j) for p in p2), "2. Pause verdoppelt")
    pruefe(len(set(p1)) > 1, "mit Zufallsanteil (nicht alle gleich)")
    mx = m2.GEMINI_RETRY_MAX_DELAY_S
    pruefe(all(p <= mx * (1 + j) for p in p4), f"nach oben begrenzt (~{mx} s)")

    # Gesamtfenster: eine Uhr, die nach dem ersten Fehlschlag fast am Ende steht.
    jetzt = [0.0]
    versuche = []

    def aufruf(timeout_s):
        versuche.append(timeout_s)
        jetzt[0] += m2.GEMINI_GESAMTFENSTER_S - 20
        raise fehler_503()

    try:
        m2._rufe_mit_wiederholung(aufruf, schlafe=lambda s: None, uhr=lambda: jetzt[0])
        geworfen = None
    except m2.Modul2Error as exc:
        geworfen = exc
    pruefe(len(versuche) == 1, "kein neuer Versuch, wenn das Gesamtfenster nicht mehr reicht")
    pruefe(geworfen is not None and geworfen.wiederholbar and geworfen.versuche == 1,
           "der Fehler bleibt temporaer und nennt die Zahl der Versuche")
    pruefe(versuche[0] <= m2.GEMINI_TIMEOUT_S, f"Einzelaufruf mit Timeout ({versuche[0]} s)")
    print()


# --- A, B, C: ueber die echten Endpunkte ------------------------------------

def test_a_503_503_erfolg() -> None:
    print("=== A: 503 -> 503 -> Erfolg ===")
    welt = Welt()
    einrichten(welt)
    welt.skript = [fehler_503(), fehler_503(), "ok"]
    srv = Server()
    try:
        _, s = srv.analyse()
    finally:
        srv.schliessen()
    r = s.get("reglement") or {}
    pruefe(s["status"] == "done", f"Analyse fertig ({s['status']})")
    pruefe(r.get("status") == "completed", f"Reglementstatus completed ({r.get('status')})")
    pruefe(welt.gemini_aufrufe == 3 and r.get("versuche") == 3, "drei Gemini-Versuche")
    pruefe(len(welt.pausen) == 2 and welt.pausen[1] > welt.pausen[0],
           f"zwei wachsende Pausen ({[round(p, 1) for p in welt.pausen]} s)")
    pruefe(all(t == m2.GEMINI_TIMEOUT_S * 1000 for t in welt.timeouts_ms),
           "jeder Aufruf traegt einen Timeout")
    pruefe(welt.modul1_aufrufe == 1, "keine zweite Grundstuecksanalyse")
    print()


def test_b_und_c_temporaer_dann_manuell() -> None:
    print("=== B: 503 -> 503 -> 503 -> Ende ===")
    welt = Welt()
    db_pfad = einrichten(welt)
    welt.skript = [fehler_503(), fehler_503(), fehler_503()]
    srv = Server()
    try:
        job_id, s = srv.analyse()
        r = s.get("reglement") or {}
        teil = s.get("teilergebnis") or {}
        pruefe(s["status"] == "teilweise", f"Auftrag teilweise ({s['status']})")
        pruefe(r.get("status") == "temporarily_unavailable",
               f"Reglementstatus temporarily_unavailable ({r.get('status')})")
        pruefe(r.get("wiederholbar") is True and s.get("wiederholbar") is True,
               "wiederholbar = true (im Block und auf oberster Ebene)")
        pruefe(r.get("fehlerart") == m2.FEHLERART_DIENST_UEBERLASTET, f"Fehlerart {r.get('fehlerart')}")
        pruefe(welt.gemini_aufrufe == 3 and r.get("versuche") == 3, "begrenzt auf drei Versuche")
        pruefe("überlastet" in (r.get("meldung") or "") and "503" in (r.get("detail") or ""),
               "verstaendliche Meldung, technisches Detail getrennt")
        pruefe(s.get("fehler") == r.get("meldung"), "'fehler' traegt die verstaendliche Meldung")
        pruefe((teil.get("modul1_geodaten") or {}).get("kataster", {}).get("egrid") == "CH975272732334",
               "amtliche Daten (Parzelle) bleiben erhalten")
        pruefe(teil.get("zonen_zuordnung") is None and teil.get("g1_ergebnis") is None,
               "nichts geschaetzt: Zonenwerte und Baubereich bleiben leer")
        pruefe(anzahl_gespeichert(db_pfad) == 0, "der Fehlschlag steht nicht im Zwischenspeicher")
        print()

        print("=== C: manuelles Wiederholen -> Erfolg ===")
        welt.skript = ["ok"]
        code, antwort = srv.post("/analyse/reglement", {"job_id": job_id})
        pruefe(code == 200 and antwort.get("status") == "running", "Wiederholung angenommen")
        s2 = srv.warte(job_id)
        r2 = s2.get("reglement") or {}
        pruefe(s2["status"] == "done", f"Analyse danach fertig ({s2['status']})")
        pruefe(r2.get("status") == "completed", f"Reglementstatus completed ({r2.get('status')})")
        pruefe(r2.get("laeufe") == 2, f"zweiter Lauf des Reglementsschritts ({r2.get('laeufe')})")
        pruefe(welt.modul1_aufrufe == 1, "kein neuer Grundstuecks-Crawl, kein OEREB-Neuabruf")
        pruefe(welt.gemini_aufrufe == 4, "genau ein zusaetzlicher Gemini-Aufruf")
        erg = s2.get("ergebnis") or {}
        pruefe((erg.get("modul1_geodaten") or {}).get("kataster", {}).get("egrid") == "CH975272732334",
               "bestehende Daten bleiben erhalten")
        pruefe(erg.get("zonen_zuordnung") is not None, "die Analyse wird danach weitergefuehrt")
        pruefe(anzahl_gespeichert(db_pfad) == 1, "erst der Erfolg wird zwischengespeichert")

        # Unbekannter Auftrag (Neustart): klare Fehlerart statt Absturz
        code, antwort = srv.post("/analyse/reglement", {"job_id": "gibt-es-nicht"})
        pruefe(code == 404 and antwort.get("fehlerart") == "auftrag_unbekannt",
               "abgelaufener Auftrag: 404 mit Fehlerart auftrag_unbekannt")
    finally:
        srv.schliessen()
    print()


def test_d_dauerhaft() -> None:
    print("=== D: dauerhafter Fehler (RECITATION, HTTP 400) ===")
    for name, schritt, art in (("RECITATION", "recitation", m2.FEHLERART_ANTWORT_BLOCKIERT),
                               ("HTTP 400", fehler_400(), m2.FEHLERART_API_FEHLER)):
        welt = Welt()
        einrichten(welt)
        welt.skript = [schritt, "ok"]
        srv = Server()
        try:
            _, s = srv.analyse()
        finally:
            srv.schliessen()
        r = s.get("reglement") or {}
        pruefe(s["status"] == "teilweise" and r.get("status") == "failed",
               f"{name}: Status failed ({r.get('status')})")
        pruefe(r.get("wiederholbar") is False and s.get("wiederholbar") is False,
               f"{name}: wiederholbar = false")
        pruefe(r.get("fehlerart") == art, f"{name}: Fehlerart {r.get('fehlerart')}")
        pruefe(welt.gemini_aufrufe == 1 and not welt.pausen, f"{name}: kein weiterer Versuch")
    print()


# --- E, F, G: Zwischenspeicher und Nebenlaeufigkeit -------------------------

def test_e_f_cache() -> None:
    print("=== E: Cache-Treffer / F: geaendertes Dokument ===")
    welt = Welt()
    einrichten(welt)
    srv = Server()
    try:
        srv.analyse()
        pruefe(welt.gemini_aufrufe == 1, "erste Analyse wertet aus")
        _, s = srv.analyse()
        r = s.get("reglement") or {}
        pruefe(welt.gemini_aufrufe == 1, "E: zweite Analyse ohne Gemini-Aufruf")
        pruefe(r.get("status") == "completed" and r.get("aus_zwischenspeicher") is True,
               "E: completed aus dem Zwischenspeicher")
        pruefe(r.get("versuche") == 0, "E: null Versuche")

        welt.inhalte["https://x/bno.pdf"] = b"BNO Fassung B, revidiert"
        _, s = srv.analyse()
        r = s.get("reglement") or {}
        pruefe(welt.gemini_aufrufe == 2, "F: geaenderter Inhalt -> Gemini neu gefragt")
        pruefe(r.get("aus_zwischenspeicher") is False, "F: kein falscher Treffer")
    finally:
        srv.schliessen()
    print()


def test_g_parallel() -> None:
    print("=== G: zwei parallele Auftraege desselben Reglements ===")
    welt = Welt()
    einrichten(welt)
    welt.gemini_dauer_s = 0.4
    lade = webapp._bzo_zwischenspeicher()
    oereb = MODUL1["oereb"]
    ergebnisse: list = []

    def lauf(gemeinde):
        ergebnisse.append(lade(oereb, gemeinde=gemeinde, kanton="AG"))

    faeden = [threading.Thread(target=lauf, args=("Buchs (AG)",)) for _ in range(2)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(10)
    pruefe(len(ergebnisse) == 2, "beide Auftraege liefern ein Ergebnis")
    pruefe(welt.gemini_aufrufe == 1, f"nur ein Gemini-Aufruf ({welt.gemini_aufrufe})")
    pruefe(sorted(bool(e["_zwischenspeicher"]["aus_zwischenspeicher"]) for e in ergebnisse)
           == [False, True], "der zweite trifft das Ergebnis des ersten")

    # Gegenprobe: verschiedene Gemeinden sperren sich nicht gegenseitig.
    welt.gemini_aufrufe = 0
    beginn = time.time()
    faeden = [threading.Thread(target=lauf, args=(g,)) for g in ("Aarau", "Suhr")]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(10)
    dauer = time.time() - beginn
    pruefe(welt.gemini_aufrufe == 2, "verschiedene Schluessel: je ein Aufruf")
    pruefe(dauer < 2 * welt.gemini_dauer_s, f"und parallel, nicht nacheinander ({dauer:.2f} s)")
    print()


def main() -> None:
    test_klassifikation()
    test_backoff_und_fenster()
    test_a_503_503_erfolg()
    test_b_und_c_temporaer_dann_manuell()
    test_d_dauerhaft()
    test_e_f_cache()
    test_g_parallel()

    print("=" * 72)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print("  -", f)
        sys.exit(1)
    print("ALLE TESTS ZUR REGLEMENTS-STABILITAET BESTANDEN")


if __name__ == "__main__":
    main()

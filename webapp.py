"""
Minimaler Web-Entry-Point fuer die Potenzial-Engine: POST /analyze startet
einen Analyse-Job im Hintergrund und liefert sofort eine job_id zurueck;
GET /status/<job_id> liefert den aktuellen Stand. Wird vom
Cloudflare-Pages-Frontend (dist/index.html, Leaflet-Karte) per fetch()
mit Polling aufgerufen.

Asynchrones Job-Muster ist noetig, weil eine einzelne Analyse (Modul 1 +
Gemini) 1-3 Minuten dauern kann -- eine einzelne durchgehaltene HTTP-
Anfrage durch Cloudflare Tunnel + Pages Function haelt das nicht zuverlaessig
durch (live beobachtet: "Incoming request ended abruptly: context canceled"
nach einer gewissen Zeit). Kurze Polling-Requests (alle paar Sekunden) sind
von diesem Timeout nicht betroffen.

Bewusst OHNE Web-Framework (Flask/FastAPI nicht installiert) -- reine
Python-Stdlib (http.server + threading), damit keine neue Abhaengigkeit
noetig ist. Keine Fachlogik hier neu geschrieben -- dieses Modul ruft
ausschliesslich bestehende, bereits getestete Funktionen aus
modul1_geodata.py/modul2_bzo_analysis.py/modul3_financial.py auf.

WICHTIG: Die Zonenzuordnung (welche BZO-Zone amtlich gilt, inkl. aller
Kennzahlen) ist IMMER preisunabhaengig -- siehe
modul3_financial.ermittle_zonenzuordnung() (price-unabhaengige Auslagerung
aus run_from_modul_results()). Nur die anschliessende Finanzrechnung
(Residualwert/Szenarien) braucht tatsaechlich einen Verkaufspreis und wird
NUR ausgefuehrt, wenn einer mitgegeben wurde.

Start:
    export GEMINI_API_KEY=...   (oder set auf Windows)
    python webapp.py [port]     (Standard-Port 8787)

Fuer die oeffentliche Erreichbarkeit unter grundstueck-crawler.pages.dev
wird zusaetzlich ein Cloudflare Tunnel auf diesen Port benoetigt -- Cloudflare
Pages selbst kann diesen Python-Code nicht direkt ausfuehren.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from potenzial_engine.entwicklungsszenarien import SZENARIO_ANFORDERUNGEN
from potenzial_engine.g1_verdrahtung import G1VerdrahtungError, berechne_g1_fuer_fall
from potenzial_engine.modul1_geodata import Modul1Error, get_gwr_data, get_parcel_data, run_modul1
from potenzial_engine.modul2_bzo_analysis import Modul2Error, analyze_from_oereb_result
from potenzial_engine.modul3_financial import Modul3Error, ermittle_zonenzuordnung, run_from_modul_results
from potenzial_engine.quellen import Quellenobjekt, quellen_aus_modul1_ergebnis
from potenzial_engine.sia416_flaechen import berechne_sia416_kaskade

DEFAULT_PORT = 8787

# Statisch, unabhaengig von der Adresse -- reine Taxonomie/Dokumentation
# aus entwicklungsszenarien.py (KEINE Berechnungslogik dort, siehe Modul).
# Einmal serialisiert, in jeder Antwort mitgegeben.
ENTWICKLUNGSSZENARIEN_INFO = [
    {
        "szenario": a.szenario.value,
        "beschreibung": a.beschreibung,
        "benoetigte_zusatzeingaben": a.benoetigte_zusatzeingaben,
        "benoetigte_flaechendaten": a.benoetigte_flaechendaten,
        "heute_bereits_abgedeckt_durch": a.heute_bereits_abgedeckt_durch,
    }
    for a in SZENARIO_ANFORDERUNGEN.values()
]

# In-Memory-Job-Speicher -- reicht fuer einen einzelnen lokalen Prozess mit
# einem Nutzer; ueberlebt keinen Neustart, braucht aber auch keinen (Jobs
# sind pro Analyse-Anfrage kurzlebig).
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 30 * 60


def _cleanup_alte_jobs() -> None:
    grenze = time.time() - _JOB_TTL_SECONDS
    with _JOBS_LOCK:
        for job_id in [j for j, v in _JOBS.items() if v["erstellt_um"] < grenze]:
            del _JOBS[job_id]

# Grosse Rohdaten-Blobs, die fuer die UI nicht gebraucht werden und die
# JSON-Antwort unnoetig aufblaehen wuerden -- reine Darstellungs-
# Optimierung, die zugrunde liegenden Objekte bleiben unveraendert.
_TRIM_PATHS = (
    ("kataster", "raw_attributes"),
    ("gemeinde", "raw_attributes"),
    ("gwr", "raw_attributes"),
    ("geocoding", "raw"),
    ("oereb", "raw_extract"),
)


def _trimmed_modul1(modul1_result: dict) -> dict:
    trimmed = dict(modul1_result)
    for section, feld in _TRIM_PATHS:
        if section in trimmed and isinstance(trimmed[section], dict) and feld in trimmed[section]:
            trimmed[section] = {k: v for k, v in trimmed[section].items() if k != feld}
    return trimmed


def _sia416_fuer_geschossflaeche(geschossflaeche_m2: Optional[float]) -> Optional[dict]:
    """Ruft die SIA-416-Kaskade OHNE jede NF/GF- oder HNF/NF-Modellannahme
    auf -- es gibt aktuell keine echten Referenzprojekte (siehe
    referenzprojekte.REFERENZPROJEKTE, bewusst leer). GF wird dadurch
    korrekt als 'bestimmt' ausgewiesen (reale G1-Geometrie), NF/HNF/NNF
    korrekt als 'nicht_bestimmbar' -- keine erfundene Zahl. Liefert None,
    wenn G1 selbst keine Geschossflaeche ermitteln konnte."""
    if geschossflaeche_m2 is None:
        return None
    return asdict(berechne_sia416_kaskade(geschossflaeche_gf_m2=geschossflaeche_m2))


def _sia416_fuer_g1_ergebnis(g1_ergebnis: Optional[dict]) -> Optional[dict]:
    if not g1_ergebnis:
        return None
    if g1_ergebnis.get("modus") == "bandbreite_grenzabstand_kante_nicht_differenziert":
        ausgabe = {}
        for name, e in (g1_ergebnis.get("szenarien") or {}).items():
            sia416 = _sia416_fuer_geschossflaeche(e.get("geschossflaeche_m2"))
            if sia416 is not None:
                ausgabe[name] = sia416
        return ausgabe or None
    return _sia416_fuer_geschossflaeche((g1_ergebnis.get("ergebnis") or {}).get("geschossflaeche_m2"))


def _run_pipeline(
    adresse: str, verkaufspreis: Optional[float], verkaufspreis_total: Optional[float] = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Liefert (ergebnis_fuer_ui, kontext). Der Kontext enthaelt die
    unveraenderten Modul-1-/Modul-2-Rohergebnisse und bleibt serverseitig im
    Job liegen -- damit eine spaetere Wirtschaftlichkeitsrechnung (Modul 3)
    ohne erneuten Geodaten-/Gemini-Durchlauf moeglich ist. Er wird NIE an das
    Frontend gesendet."""
    modul1_result = run_modul1(adresse)
    oereb = modul1_result.get("oereb", {})
    if not oereb.get("found"):
        raise Modul1Error(f"Keine amtlichen Zonendaten (OEREB) gefunden: {oereb.get('reason')}")

    # Verkaufspreis TOTAL ist eine reine Praesentations-Umrechnung (Division
    # durch die amtliche Parzellenflaeche) -- die Fachlogik (Modul 3) erhaelt
    # unveraendert nur einen CHF/m2-Wert, wie bisher. Erst hier moeglich,
    # weil die Parzellenflaeche erst nach run_modul1() bekannt ist.
    if verkaufspreis is None and verkaufspreis_total is not None:
        parzellenflaeche_fuer_umrechnung = modul1_result.get("kataster", {}).get("flaeche_m2")
        if not parzellenflaeche_fuer_umrechnung:
            raise Modul1Error(
                "Verkaufspreis total kann nicht umgerechnet werden -- amtliche Parzellenflaeche unbekannt. "
                "Bitte stattdessen den Verkaufspreis pro m2 angeben."
            )
        verkaufspreis = verkaufspreis_total / parzellenflaeche_fuer_umrechnung

    gemeinde = modul1_result.get("gemeinde", {}).get("gemeinde")
    kanton = oereb.get("kanton")
    modul2_result = analyze_from_oereb_result(oereb, gemeinde=gemeinde, kanton=kanton, backend="gemini")

    # Preisunabhaengig: welche BZO-Zone gilt amtlich fuer dieses Grundstueck.
    zonen_zuordnung = ermittle_zonenzuordnung(modul1_result, modul2_result)

    # G1 (Baubereich/Fussabdruck/Geschossflaeche) braucht eine EINDEUTIG
    # zugeordnete Zone -- bei Mehrdeutigkeit oder SNP-Blockierung wird
    # bewusst nicht geraten, welcher Kandidat gilt, sondern G1 uebersprungen.
    g1_ergebnis = None
    g1_fehler = None
    if zonen_zuordnung.get("status") == "gefunden":
        try:
            g1_ergebnis = berechne_g1_fuer_fall(modul1_result, zonen_zuordnung["zone"])
        except G1VerdrahtungError as exc:
            g1_fehler = str(exc)

    sia416_ergebnis = _sia416_fuer_g1_ergebnis(g1_ergebnis)

    # Quellenobjekte: Rueckverfolgbarkeit jedes amtlichen Modul-1-Werts auf
    # Endpunkt/Layer/URL -- vor dem Trimmen berechnet (unabhaengig davon,
    # ob raw_attributes/raw_extract fuer die UI weggeschnitten werden).
    quellen = [asdict(q) for q in quellen_aus_modul1_ergebnis(modul1_result)]

    modul3_result = None
    if verkaufspreis is not None:
        modul3_result = run_from_modul_results(modul1_result, modul2_result, verkaufspreis)

    ergebnis = {
        "adresse": adresse,
        "modul1_geodaten": _trimmed_modul1(modul1_result),
        "zonen_zuordnung": zonen_zuordnung,
        "g1_ergebnis": g1_ergebnis,
        "g1_fehler": g1_fehler,
        "sia416_ergebnis": sia416_ergebnis,
        "quellen": quellen,
        "entwicklungsszenarien": ENTWICKLUNGSSZENARIEN_INFO,
        "modul2_bzo_analyse": modul2_result,
        "modul3_financial": modul3_result,
    }
    return ergebnis, {"modul1": modul1_result, "modul2": modul2_result}


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._cors()
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:  # noqa: N802 -- http.server API
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            self._send_json({"ok": True, "service": "grundstueck-crawler-backend"})
        elif self.path.startswith("/status/"):
            self._handle_status(self.path[len("/status/"):])
        elif self.path.startswith("/pick"):
            self._handle_pick()
        else:
            self._send_json({"ok": False, "fehler": "Nicht gefunden."}, status=404)

    def _handle_pick(self) -> None:
        """Kartenklick auf einen beliebigen Punkt: liefert Parzelle + GWR-
        Gebaeudedaten fuer diese Koordinate. Ruft ausschliesslich die bereits
        bestehenden Modul-1-Funktionen auf denselben amtlichen swisstopo-
        Layern auf -- keine neue Datenquelle, keine neue Fachlogik, kein LLM
        (deshalb in Sekundenbruchteilen fertig und ohne Job noetig)."""
        query = parse_qs(urlparse(self.path).query)
        try:
            e = float(query.get("e", [""])[0])
            n = float(query.get("n", [""])[0])
        except (TypeError, ValueError):
            self._send_json({"ok": False, "fehler": "e und n (LV95) sind Pflichtparameter."}, status=400)
            return
        try:
            self._send_json({"ok": True, "parzelle": get_parcel_data(e, n), "gwr": get_gwr_data(e, n)})
        except Exception:  # noqa: BLE001 -- Kartenklick darf den Server nie stoppen
            traceback.print_exc()
            self._send_json({"ok": False, "fehler": "Abfrage an dieser Stelle fehlgeschlagen."}, status=502)

    def _handle_status(self, job_id: str) -> None:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
        if job is None:
            self._send_json({"ok": False, "fehler": "Unbekannte job_id (evtl. abgelaufen)."}, status=404)
            return
        if job["status"] == "running":
            self._send_json({"ok": True, "status": "running"})
        elif job["status"] == "error":
            self._send_json({"ok": True, "status": "error", "fehler": job["fehler"]})
        else:
            self._send_json({"ok": True, "status": "done", "ergebnis": job["ergebnis"]})

    def _lies_json_body(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json({"ok": False, "fehler": "Ungueltiges JSON."}, status=400)
            return None

    def _preis_aus_body(self, daten: dict) -> tuple[bool, Optional[float], Optional[float]]:
        """Validiert verkaufspreis / verkaufspreis_total. Rueckgabe:
        (gueltig, verkaufspreis, verkaufspreis_total)."""
        verkaufspreis = daten.get("verkaufspreis")
        verkaufspreis_total = daten.get("verkaufspreis_total")
        for feldname, wert in (("verkaufspreis", verkaufspreis), ("verkaufspreis_total", verkaufspreis_total)):
            if wert is not None:
                try:
                    float(wert)
                except (TypeError, ValueError):
                    self._send_json({"ok": False, "fehler": f"{feldname} muss eine Zahl sein."}, status=400)
                    return False, None, None
        return (
            True,
            float(verkaufspreis) if verkaufspreis is not None else None,
            float(verkaufspreis_total) if verkaufspreis_total is not None else None,
        )

    def _handle_wirtschaftlichkeit(self) -> None:
        """Rechnet Modul 3 fuer einen bereits abgeschlossenen Job nach --
        auf den serverseitig zwischengespeicherten Modul-1-/Modul-2-
        Ergebnissen. Damit kostet die optionale Wirtschaftlichkeit keinen
        zweiten Geodaten-/Gemini-Durchlauf. run_from_modul_results() bleibt
        unveraendert; die baurechtliche Analyse wird nicht neu berechnet."""
        daten = self._lies_json_body()
        if daten is None:
            return
        job_id = (daten.get("job_id") or "").strip()
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            kontext = job.get("kontext") if job else None
        if job is None or job["status"] != "done" or not kontext:
            self._send_json(
                {"ok": False, "fehler": "Keine abgeschlossene Analyse zu dieser job_id (evtl. abgelaufen)."},
                status=404,
            )
            return

        gueltig, verkaufspreis, verkaufspreis_total = self._preis_aus_body(daten)
        if not gueltig:
            return
        if verkaufspreis is None and verkaufspreis_total is None:
            self._send_json(
                {"ok": False, "fehler": "Verkaufspreis pro m2 oder Verkaufspreis total ist noetig."}, status=400
            )
            return

        modul1_result = kontext["modul1"]
        if verkaufspreis is None:
            flaeche = modul1_result.get("kataster", {}).get("flaeche_m2")
            if not flaeche:
                self._send_json(
                    {
                        "ok": False,
                        "fehler": (
                            "Verkaufspreis total kann nicht umgerechnet werden -- amtliche Parzellenflaeche "
                            "unbekannt. Bitte den Verkaufspreis pro m2 angeben."
                        ),
                    },
                    status=400,
                )
                return
            verkaufspreis = verkaufspreis_total / flaeche

        try:
            modul3_result = run_from_modul_results(modul1_result, kontext["modul2"], verkaufspreis)
        except (Modul1Error, Modul2Error, Modul3Error) as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "fehler": "Unerwarteter Fehler (siehe Server-Log)."}, status=500)
            return

        with _JOBS_LOCK:
            if job_id in _JOBS and _JOBS[job_id].get("ergebnis"):
                _JOBS[job_id]["ergebnis"]["modul3_financial"] = modul3_result
        self._send_json(
            {"ok": True, "modul3_financial": modul3_result, "verwendeter_preis_chf_pro_m2": round(verkaufspreis, 2)}
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/wirtschaftlichkeit":
            self._handle_wirtschaftlichkeit()
            return
        if self.path != "/analyze":
            self._send_json({"ok": False, "fehler": "Nicht gefunden."}, status=404)
            return

        daten = self._lies_json_body()
        if daten is None:
            return

        adresse = (daten.get("adresse") or "").strip()
        if not adresse:
            self._send_json({"ok": False, "fehler": "Adresse ist ein Pflichtfeld."}, status=400)
            return

        gueltig, verkaufspreis, verkaufspreis_total = self._preis_aus_body(daten)
        if not gueltig:
            return

        _cleanup_alte_jobs()
        job_id = uuid.uuid4().hex
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "status": "running",
                "erstellt_um": time.time(),
                "ergebnis": None,
                "fehler": None,
                "kontext": None,
            }

        thread = threading.Thread(
            target=self._job_ausfuehren, args=(job_id, adresse, verkaufspreis, verkaufspreis_total), daemon=True
        )
        thread.start()

        self._send_json({"ok": True, "job_id": job_id})

    def _job_ausfuehren(
        self, job_id: str, adresse: str, verkaufspreis: Optional[float], verkaufspreis_total: Optional[float] = None
    ) -> None:
        try:
            ergebnis, kontext = _run_pipeline(adresse, verkaufspreis, verkaufspreis_total)
        except (Modul1Error, Modul2Error, Modul3Error) as exc:
            with _JOBS_LOCK:
                _JOBS[job_id].update(status="error", fehler=str(exc))
            return
        except Exception:  # noqa: BLE001 -- Hintergrund-Thread soll nie unbeobachtet sterben
            traceback.print_exc()
            with _JOBS_LOCK:
                _JOBS[job_id].update(status="error", fehler="Unerwarteter Fehler bei der Analyse (siehe Server-Log).")
            return
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="done", ergebnis=ergebnis, kontext=kontext)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 -- http.server API
        sys.stderr.write(f"{self.address_string()} - {format % args}\n")


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("WARNUNG: GEMINI_API_KEY ist nicht gesetzt -- Modul 2 wird fehlschlagen.", file=sys.stderr)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Grundstueck-Crawler-Backend laeuft auf http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

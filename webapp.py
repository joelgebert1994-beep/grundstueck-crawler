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
noetig ist.

HIER STEHT KEINE FACHLOGIK. Dieses Modul ist nur Transport: HTTP, Jobs,
Eingabevalidierung. Die gesamte Analyse liegt im Paket und wird ueber zwei
Funktionen aufgerufen (siehe potenzial_engine/pipeline.py):

    analysiere_grundstueck(adresse)     baurechtliche Analyse, ohne Preis
    berechne_wirtschaftlichkeit(...)    Residualwert, mit Preis

Die Trennung ist fachlich: welche BZO-Zone amtlich gilt und was darauf
gebaut werden darf, haengt nicht vom Verkaufspreis ab. Die Wirtschaftlichkeit
ist optional und blockiert die baurechtliche Analyse nie.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from potenzial_engine import Analyse, analysiere_grundstueck, berechne_wirtschaftlichkeit
from potenzial_engine.modul1_geodata import Modul1Error, get_gwr_data, get_parcel_data
from potenzial_engine.modul2_bzo_analysis import Modul2Error
from potenzial_engine.modul3_financial import Modul3Error

DEFAULT_PORT = 8787

# In-Memory-Job-Speicher -- reicht fuer einen einzelnen lokalen Prozess mit
# einem Nutzer; ueberlebt keinen Neustart, braucht aber auch keinen (Jobs
# sind pro Analyse-Anfrage kurzlebig).
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 30 * 60


def _zahl(wert, vorgabe=None):
    """Liest eine Zahl aus dem Request-Body. Leere Eingabe heisst 'nicht
    gesetzt', nicht 0 -- ein leeres Feld darf keinen Preis von null bedeuten."""
    if wert in (None, "", "null"):
        return vorgabe
    try:
        return float(wert)
    except (TypeError, ValueError):
        raise ValueError(f"{wert!r} ist keine Zahl.") from None


def _rechne_entwicklung(analyse: "Analyse", daten: dict) -> dict:
    """Szenarien und Wirtschaftlichkeit aus den Benutzereingaben.

    Erwartet im Body optional:
      wohnungsmix  [{typ, flaeche_m2, anteil | anzahl}, ...]
      verkauf_chf_pro_m2, verkauf_basis, miete_chf_pro_m2_jahr,
      bodenpreis_chf_pro_m2, landpreis_total_chf, zielmarge, land_ansatz
      bkp  {schluessel: wert}   -- ueberschreibt einzelne Kostenansaetze
      annahmen {schluessel: wert} -- ueberschreibt Flaechen-Annahmen
      attika_zulaessig, gebaeudeabstand_m
    """
    from potenzial_engine import wirtschaftlichkeit as wi
    from potenzial_engine.flaechenmodell import WohnungstypVorgabe
    from potenzial_engine.pipeline import (
        berechne_szenarien as _szen,
        berechne_wirtschaftlichkeit_je_szenario as _wirt,
    )

    mix = None
    for eintrag in daten.get("wohnungsmix") or []:
        anteil = _zahl(eintrag.get("anteil"))
        anzahl = _zahl(eintrag.get("anzahl"))
        vorgabe = WohnungstypVorgabe(
            typ=str(eintrag.get("typ") or "Typ"),
            flaeche_nwf_pro_einheit_m2=_zahl(eintrag.get("flaeche_m2"), 0) or 0.0,
            anteil=anteil,
            anzahl=int(anzahl) if anzahl is not None else None,
        )
        mix = (mix or []) + [vorgabe]

    annahmen = {k: _zahl(v) for k, v in (daten.get("annahmen") or {}).items() if _zahl(v) is not None}

    szenarien = _szen(
        analyse,
        benutzerwerte=annahmen or None,
        wohnungsmix=mix,
        wohnungsmix_begruendung=daten.get("wohnungsmix_begruendung") or "Benutzereingabe",
        attika_zulaessig=daten.get("attika_zulaessig"),
        gebaeudeabstand_m=_zahl(daten.get("gebaeudeabstand_m")),
    )

    def referenzen(schluessel):
        return [
            wi.Referenzwert(
                quelle=str(r.get("quelle") or "?"), datum=str(r.get("datum") or "?"),
                objekt=str(r.get("objekt") or "?"), wert=_zahl(r.get("wert"), 0) or 0.0,
                einheit=str(r.get("einheit") or "CHF/m2"),
                qualitaet=str(r.get("qualitaet") or "unbekannt"),
            )
            for r in (daten.get("referenzen") or {}).get(schluessel, [])
        ]

    markt = wi.Marktannahmen(
        verkauf=wi.Verkaufsannahme(
            basis=daten.get("verkauf_basis") or "nwf",
            preis_pro_m2=wi.marktwert("verkauf", "CHF/m2",
                                      referenzen=referenzen("verkauf"),
                                      benutzerannahme=_zahl(daten.get("verkauf_chf_pro_m2"))),
        ),
        miete=wi.Mietannahme(
            basis=daten.get("miete_basis") or "nwf",
            miete_pro_m2_jahr=wi.marktwert("miete", "CHF/m2/Jahr",
                                           referenzen=referenzen("miete"),
                                           benutzerannahme=_zahl(daten.get("miete_chf_pro_m2_jahr"))),
        ),
        bodenpreis_chf_pro_m2=wi.marktwert("boden", "CHF/m2",
                                           referenzen=referenzen("boden"),
                                           benutzerannahme=_zahl(daten.get("bodenpreis_chf_pro_m2"))),
        landpreis_total_chf=_zahl(daten.get("landpreis_total_chf")),
        zielmarge=_zahl(daten.get("zielmarge"), 0.15),
        land_ansatz=daten.get("land_ansatz") or wi.LAND_KAUF,
    )

    positionen = wi.standard_kostenmodell(
        ausbaustandard=daten.get("ausbaustandard") or "rendite",
        kostengenauigkeit=daten.get("kostengenauigkeit") or "kostenschaetzung",
        kostenbasis=daten.get("kostenbasis") or "gf",
    )
    ueberschrieben = daten.get("bkp") or {}
    if ueberschrieben:
        positionen = [
            p.mit_benutzerwert(_zahl(ueberschrieben[p.schluessel]))
            if p.schluessel in ueberschrieben and _zahl(ueberschrieben[p.schluessel]) is not None
            else p
            for p in positionen
        ]

    wirtschaft = _wirt(analyse, markt, kostenpositionen=positionen,
                       szenarien_ergebnis=szenarien)
    return {"szenarien": szenarien, "wirtschaftlichkeit": wirtschaft}


def _cleanup_alte_jobs() -> None:
    grenze = time.time() - _JOB_TTL_SECONDS
    with _JOBS_LOCK:
        for job_id in [j for j, v in _JOBS.items() if v["erstellt_um"] < grenze]:
            del _JOBS[job_id]

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

        try:
            w = berechne_wirtschaftlichkeit(
                Analyse(ergebnis=job["ergebnis"], kontext=kontext),
                verkaufspreis_chf_pro_m2=verkaufspreis,
                verkaufspreis_total_chf=verkaufspreis_total,
            )
        except (Modul1Error, Modul2Error, Modul3Error) as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "fehler": "Unerwarteter Fehler (siehe Server-Log)."}, status=500)
            return

        with _JOBS_LOCK:
            if job_id in _JOBS and _JOBS[job_id].get("ergebnis"):
                _JOBS[job_id]["ergebnis"]["modul3_financial"] = w.ergebnis
        self._send_json(
            {
                "ok": True,
                "modul3_financial": w.ergebnis,
                "verwendeter_preis_chf_pro_m2": round(w.verwendeter_preis_chf_pro_m2, 2),
            }
        )

    def _handle_entwicklung(self) -> None:
        """Szenarien und Wirtschaftlichkeit neu rechnen -- ohne erneute Geo-
        oder Gemini-Abfrage.

        Das ist der Endpunkt, der die Oberflaeche dynamisch macht: der
        Benutzer aendert Verkaufspreis, Miete, Bodenpreis, Wohnungsmix, eine
        BKP-Position oder die Zielmarge, und bekommt in Millisekunden die
        ganze Kette bis zum Residualwert zurueck. Die teure baurechtliche
        Analyse bleibt unberuehrt.
        """
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

        try:
            antwort = _rechne_entwicklung(
                Analyse(ergebnis=job["ergebnis"], kontext=kontext), daten
            )
        except (ValueError, TypeError, KeyError) as exc:
            self._send_json({"ok": False, "fehler": f"Ungueltige Eingabe: {exc}"}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "fehler": f"Unerwarteter Fehler: {exc}"}, status=500)
            return

        self._send_json({"ok": True, **antwort})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/entwicklung":
            self._handle_entwicklung()
            return
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
            analyse = analysiere_grundstueck(adresse)
            # Ein bei /analyze mitgegebener Preis ist optional und aendert die
            # baurechtliche Analyse nicht -- er wird nur zusaetzlich gerechnet.
            if verkaufspreis is not None or verkaufspreis_total is not None:
                w = berechne_wirtschaftlichkeit(
                    analyse,
                    verkaufspreis_chf_pro_m2=verkaufspreis,
                    verkaufspreis_total_chf=verkaufspreis_total,
                )
                analyse.ergebnis["modul3_financial"] = w.ergebnis
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
            _JOBS[job_id].update(status="done", ergebnis=analyse.ergebnis, kontext=analyse.kontext)

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

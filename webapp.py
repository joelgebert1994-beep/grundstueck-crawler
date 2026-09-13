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
from pathlib import Path
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
import hashlib
import hmac
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from potenzial_engine import Analyse, analysiere_grundstueck, berechne_wirtschaftlichkeit
from potenzial_engine import sonnenstand
from potenzial_engine.modul1_geodata import (
    Modul1Error, geocode_address, get_gwr_data, get_parcel_data)
from potenzial_engine.modul2_bzo_analysis import Modul2Error
from potenzial_engine.modul3_financial import Modul3Error

DEFAULT_PORT = 8787

# Im Betrieb gibt die Plattform den Port vor (PORT), lokal bleibt es 8787.
# Ohne das startet der Dienst im Container am falschen Port und die
# Plattform haelt ihn fuer tot.
def _port() -> int:
    for quelle in (sys.argv[1] if len(sys.argv) > 1 else None, os.environ.get("PORT")):
        if quelle:
            try:
                return int(quelle)
            except ValueError:
                pass
    return DEFAULT_PORT


# Wo das Werkzeug laeuft. "entwicklung" lokal, "produktion" im Betrieb --
# die Oberflaeche zeigt es an, damit niemand versehentlich auf der
# Entwicklungsumgebung arbeitet und sich ueber fehlende Projekte wundert.
UMGEBUNG = os.environ.get("UMGEBUNG", "entwicklung")

# Im oeffentlichen Betrieb steht der Dienst im Internet. Ein offener
# /analyze-Endpunkt loest je Aufruf eine 129-Sekunden-Analyse und einen
# LLM-Aufruf aus -- das ist fremdes Geld und fremde Kontingente. Ist
# ZUGANGSSCHLUESSEL gesetzt, muss jeder Aufruf ausser /health ihn im Kopf
# X-Gebimo-Schluessel mitbringen. Lokal ist die Variable nicht gesetzt und
# es aendert sich nichts.
ZUGANGSSCHLUESSEL = os.environ.get("ZUGANGSSCHLUESSEL", "")

# Die Oberflaeche. Im Betrieb liefert Cloudflare Pages sie aus und leitet
# /api/* hierher weiter. Lokal gibt es kein Pages -- damit man das Werkzeug
# ohne zweiten Server und ohne Tunnel benutzen kann, liefert der Dienst die
# Datei dann selbst aus und nimmt /api/* genauso entgegen.
#
# Es entsteht dadurch KEINE zweite Anwendung: dieselbe Datei, dieselben
# Endpunkte, nur ohne Pages davor.
_OBERFLAECHE = Path(__file__).resolve().parent / "dist" / "index.html"

# --- Analyse-Zwischenspeicher -------------------------------------------
#
# Eine Analyse dauert gemessen 129 Sekunden, davon ~115 Sekunden fuer den
# einen Gemini-Aufruf, der das kommunale Reglement liest. Dieselbe Parzelle
# ein zweites Mal zu rechnen kostet dasselbe noch einmal -- ohne dass sich
# am Ergebnis etwas aendert. Die Tabelle dafuer steht seit Phase 1 in der
# Datenschicht (`analyse`, mit egrid/engine_version/eingaben_hash) und war
# bis jetzt nie angeschlossen.
#
# Wie lange ein Eintrag gilt. Amtliche Grundlagen aendern sich selten, aber
# sie aendern sich: eine revidierte BZO nach einem Jahr stillschweigend
# weiterzuverwenden waere schlimmer als 129 Sekunden zu warten.
ANALYSE_CACHE_TAGE = float(os.environ.get("ANALYSE_CACHE_TAGE", "30"))


def _engine_fingerabdruck() -> str:
    """Inhaltsabdruck des Engine-Codes als Versionsschluessel.

    Eine von Hand gepflegte Versionsnummer wird vergessen -- und dann
    liefert der Zwischenspeicher Ergebnisse einer Rechnung, die es nicht
    mehr gibt. Ein Abdruck des Quellcodes kann nicht vergessen werden:
    aendert sich die Engine, aendert sich der Schluessel, und kein alter
    Eintrag wird je wieder getroffen.

    Der Preis ist eine niedrigere Trefferquote nach jeder Codeaenderung.
    Das ist der richtige Preis: lieber ein Treffer zu wenig als ein
    Ergebnis, das nicht mehr zur Rechnung passt.
    """
    h = hashlib.sha256()
    verzeichnis = Path(__file__).resolve().parent / "potenzial_engine"
    for pfad in sorted(verzeichnis.glob("*.py")):
        h.update(pfad.name.encode("utf-8"))
        h.update(pfad.read_bytes())
    return h.hexdigest()[:16]


ENGINE_VERSION = _engine_fingerabdruck()

# In-Memory-Job-Speicher -- reicht fuer einen einzelnen lokalen Prozess mit
# einem Nutzer; ueberlebt keinen Neustart, braucht aber auch keinen (Jobs
# sind pro Analyse-Anfrage kurzlebig).
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 30 * 60


# Die Vergleichsobjekte liegen in der Datenschicht (kern), nicht in der
# Engine -- die ist zustandslos. Fehlt kern (Engine allein ausgecheckt),
# laeuft alles Uebrige weiter, es gibt dann nur keine gespeicherten
# Referenzen.
_KERN_PFAD = Path(__file__).resolve().parent.parent / "Crawler"
if _KERN_PFAD.exists() and str(_KERN_PFAD) not in sys.path:
    sys.path.insert(0, str(_KERN_PFAD))


def _kern_projekt():
    """Die Projektablage, oder None wenn die Datenschicht fehlt."""
    try:
        from kern import db as kern_db, projekt as kern_pj
    except ImportError:
        return None, None
    return kern_db, kern_pj


def _rechne_variante(analyse, variante: dict) -> dict:
    """Eine Variante rechnen -- ueber denselben Weg wie jede andere Eingabe.

    Die Variante liefert nur ihr Delta (Szenario plus Benutzerannahmen); die
    Rechnung macht `_rechne_entwicklung`. Es gibt damit keine zweite
    Rechenlogik fuer Varianten, und eine Aenderung an der Engine schlaegt
    sofort durch.
    """
    daten = dict(variante.get("eingaben") or {})
    ergebnis = _rechne_entwicklung(analyse, daten)
    szenario_id = variante.get("szenario_id")
    ergebnis["variante"] = {
        "variante_id": variante.get("variante_id"),
        "name": variante.get("name"),
        "szenario_id": szenario_id,
        "stand": variante.get("stand"),
        # Was der Benutzer selbst gesetzt hat -- alles Uebrige ist
        # Systemvorschlag. Die Oberflaeche kennzeichnet das entsprechend.
        "benutzerwerte": variante.get("benutzerwerte") or [],
        "eingaben": daten,
    }
    ergebnis["aktives_szenario"] = szenario_id
    return ergebnis


def _kern_marktdaten():
    """Die Marktdaten-Ablage, oder None wenn die Datenschicht fehlt."""
    try:
        from kern import db as kern_db, marktdaten as kern_markt
    except ImportError:
        return None, None
    return kern_db, kern_markt


def _lade_vergleichsobjekte(gemeinde=None, kanton=None, objektart=None):
    kern_db, kern_markt = _kern_marktdaten()
    if kern_markt is None:
        return [], "Datenschicht (kern) nicht verfuegbar -- keine gespeicherten Referenzen."
    try:
        con = kern_db.verbinde()
        return kern_markt.lade(con, gemeinde=gemeinde, kanton=kanton, objektart=objektart), None
    except Exception as exc:  # noqa: BLE001
        return [], f"Referenzen nicht ladbar: {exc}"


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
        # Die Oberflaeche belegt den Mix vor und schickt ihn IMMER mit, damit
        # eine wieder geoeffnete Variante dasselbe rechnet. Ob der Benutzer
        # ihn angefasst hat, sagt aber nur er selbst -- hier pauschal
        # "Benutzereingabe" einzutragen machte aus einem Systemvorschlag eine
        # Entscheidung des Eigentuemers, im Dossier wie im Variantenvergleich.
        wohnungsmix_begruendung=daten.get("wohnungsmix_begruendung") or "",
        wohnungsmix_herkunft=(
            "benutzerannahme" if daten.get("wohnungsmix_vom_benutzer")
            else "systemannahme"),
        attika_zulaessig=daten.get("attika_zulaessig"),
        gebaeudeabstand_m=_zahl(daten.get("gebaeudeabstand_m")),
        restflaeche_verteilen=bool(daten.get("restflaeche_verteilen")),
        # Tatsaechliche Wohnflaeche des Bestands fuer das Sanierungsszenario.
        # Fehlt sie, bleibt die Sanierung bewusst unberechnet statt geschaetzt.
        bestand_flaeche_nwf_m2=_zahl(daten.get("bestand_flaeche_nwf_m2")),
    )

    # Referenzlage aus den gespeicherten Vergleichsobjekten: gefiltert auf
    # Gemeinde und Kanton des Grundstuecks, ausgewertet mit Sicherheitsgrad.
    # Der Systemvorschlag entsteht damit aus echten Referenzen, die
    # Benutzerannahme bleibt davon unberuehrt und hat weiter Vorrang.
    from potenzial_engine import marktdaten as mdt

    m1 = analyse.ergebnis.get("modul1_geodaten") or {}
    gemeinde = (m1.get("gemeinde") or {}).get("gemeinde")
    kanton = (m1.get("gemeinde") or {}).get("kanton")
    gespeichert, referenz_fehler = _lade_vergleichsobjekte(gemeinde=gemeinde, kanton=kanton)

    # Zusaetzlich im Request mitgegebene Referenzen (z.B. Einzelfall-Eingabe).
    aus_request, _ = mdt.aus_dicts(daten.get("vergleichsobjekte") or [])
    alle_objekte = list(gespeichert) + list(aus_request)

    vergleichsfilter = mdt.Vergleichsfilter(
        gemeinde=gemeinde, kanton=kanton,
        objektart=daten.get("referenz_objektart") or None,
    )
    lage = {
        g: mdt.werte_referenzen_aus(alle_objekte, g, vergleichsfilter)
        for g in (mdt.GROESSE_VERKAUF, mdt.GROESSE_MIETE, mdt.GROESSE_BODEN)
    }

    markt = wi.Marktannahmen(
        verkauf=wi.Verkaufsannahme(
            basis=daten.get("verkauf_basis") or "nwf",
            preis_pro_m2=lage[mdt.GROESSE_VERKAUF].als_marktwert(
                _zahl(daten.get("verkauf_chf_pro_m2"))),
        ),
        miete=wi.Mietannahme(
            basis=daten.get("miete_basis") or "nwf",
            miete_pro_m2_jahr=lage[mdt.GROESSE_MIETE].als_marktwert(
                _zahl(daten.get("miete_chf_pro_m2_jahr"))),
        ),
        bodenpreis_chf_pro_m2=lage[mdt.GROESSE_BODEN].als_marktwert(
            _zahl(daten.get("bodenpreis_chf_pro_m2"))),
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
                       szenarien_ergebnis=szenarien,
                       # Fuer die Einordnung des rueckwaerts ermittelten
                       # Verkaufspreises gegen die erfassten Vergleichsobjekte.
                       marktlage={g: r.to_dict() for g, r in lage.items()})
    return {
        "szenarien": szenarien,
        "wirtschaftlichkeit": wirtschaft,
        "marktlage": {g: r.to_dict() for g, r in lage.items()},
        "marktlage_fehler": referenz_fehler,
        "referenzgebiet": {"gemeinde": gemeinde, "kanton": kanton},
    }


def _variantenvergleich(varianten: list, ergebnisse: dict) -> list:
    """Eine Zeile je Variante -- die Grundlage der Vergleichstabelle.

    Bewusst flach und ohne Bewertung: welche Variante die beste ist, haengt
    an Risiko und Machbarkeit, nicht am groessten Gewinn. Das entscheidet
    spaeter Highest & Best Use, nicht diese Tabelle.
    """
    zeilen = []
    for v in varianten:
        e = ergebnisse.get(str(v["variante_id"])) or {}
        w = ((e.get("wirtschaftlichkeit") or {}).get("szenarien") or {}).get(v["szenario_id"]) or {}
        s = ((e.get("szenarien") or {}).get("szenarien") or {}).get(v["szenario_id"]) or {}
        flaechen = ((s.get("flaechen") or {}).get("flaechen")) or {}
        erg = w.get("ergebnis") or {}
        res = w.get("residualwert") or {}
        zeilen.append({
            "variante_id": v["variante_id"],
            "name": v["name"],
            "szenario_id": v["szenario_id"],
            "benutzerwerte": v.get("benutzerwerte") or [],
            "machbarkeit": s.get("machbarkeit"),
            "nwf_m2": (flaechen.get("wohnflaeche_nwf") or {}).get("wert"),
            "geschossflaeche_m2": (flaechen.get("geschossflaeche_gf") or {}).get("wert"),
            "wohnungen": (s.get("wohnungen") or {}).get("anzahl_wohnungen"),
            "verkaufserloes_chf": erg.get("verkaufserloes_chf"),
            "jahresmietertrag_chf": erg.get("jahresmietertrag_chf"),
            "baukosten_chf": (w.get("kosten") or {}).get("baukosten_chf"),
            "gesamtinvestition_chf": erg.get("gesamtinvestition_chf"),
            "gewinn_chf": erg.get("gewinn_chf"),
            "marge": erg.get("marge"),
            "zielmarge_erreicht": erg.get("zielmarge_erreicht"),
            "max_landwert_chf": res.get("max_landwert_chf"),
            "fehler": e.get("fehler"),
        })
    return zeilen


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

    def _zugang_ok(self) -> bool:
        """Prueft den gemeinsamen Schluessel, falls einer gesetzt ist.

        Vergleich mit compare_digest: ein zeichenweiser Vergleich verraet
        ueber die Laufzeit, wie viele Zeichen stimmen.
        """
        if not ZUGANGSSCHLUESSEL:
            return True
        mitgebracht = self.headers.get("X-Gebimo-Schluessel") or ""
        if hmac.compare_digest(mitgebracht, ZUGANGSSCHLUESSEL):
            return True
        self._send_json(
            {"ok": False, "art": "kein_zugang", "technisch": True,
             "fehler": "Kein gueltiger Zugangsschluessel."}, status=401)
        return False

    def _pfad_ohne_api(self) -> None:
        """Lokal kommt /api/... direkt hier an, im Betrieb ohne Praefix.

        Beides muss funktionieren, damit die Oberflaeche unveraendert bleibt:
        sie ruft immer /api/... auf, egal ob Pages davor steht oder nicht.
        """
        if self.path.startswith("/api/"):
            self.path = self.path[4:] or "/"

    def _sende_oberflaeche(self) -> bool:
        """Liefert dist/index.html aus, wenn sie da ist."""
        if not _OBERFLAECHE.exists():
            return False
        roh = _OBERFLAECHE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(roh)))
        # Waehrend der Entwicklung aendert sich die Datei staendig.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(roh)
        return True

    def do_GET(self) -> None:  # noqa: N802
        self._pfad_ohne_api()
        # Die Oberflaeche zuerst: wer die Wurzel im Browser oeffnet, will das
        # Werkzeug sehen, nicht eine JSON-Statusmeldung.
        if self.path in ("/", "/index.html") and self._sende_oberflaeche():
            return
        if self.path in ("/", "/health"):
            # Der Health-Check bleibt offen: die Plattform muss den Dienst
            # pruefen koennen, ohne den Schluessel zu kennen. Er gibt nur
            # Bereitschaftsflaggen preis, keine Daten.
            self._send_json(_bereitschaft())
            return
        if not self._zugang_ok():
            return

        if self.path.startswith("/status/"):
            self._handle_status(self.path[len("/status/"):])
        elif self.path.startswith("/projekt/export"):
            self._handle_projekt_export()
        elif self.path.startswith("/projekte") or self.path.startswith("/projekt"):
            self._handle_projekte_lesen()
        elif self.path.startswith("/umgebung"):
            self._handle_umgebung()
        elif self.path.startswith("/marktdaten"):
            self._handle_marktdaten_lesen()
        elif self.path.startswith("/sonne"):
            self._handle_sonne()
        elif self.path.startswith("/pick"):
            self._handle_pick()
        else:
            self._send_json({"ok": False, "fehler": "Nicht gefunden."}, status=404)

    def _handle_sonne(self) -> None:
        """Sonnenstand fuer einen Tag an einem Ort.

        Geliefert wird der ganze Tagesverlauf auf einmal, nicht ein einzelner
        Zeitpunkt: der Zeitschieber in der Ansicht muss fluessig laufen, und
        ein Serveraufruf je Bild waere dafuer unbrauchbar. Gerechnet wird
        trotzdem nur hier -- im Browser steht keine zweite Sonnenformel.
        """
        query = parse_qs(urlparse(self.path).query)
        try:
            lat = float((query.get("lat") or [""])[0])
            lon = float((query.get("lon") or [""])[0])
        except (TypeError, ValueError):
            self._send_json(
                {"ok": False, "fehler": "lat und lon (WGS84) sind Pflichtparameter."},
                status=400)
            return
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            self._send_json({"ok": False, "fehler": "lat/lon ausserhalb des gueltigen Bereichs."},
                            status=400)
            return

        roh_datum = ((query.get("datum") or [""])[0]).strip()
        try:
            tag = date.fromisoformat(roh_datum) if roh_datum else date.today()
        except ValueError:
            self._send_json({"ok": False, "fehler": f"Datum {roh_datum!r} ist kein JJJJ-MM-TT."},
                            status=400)
            return

        try:
            schritt = int((query.get("schritt") or ["10"])[0])
        except (TypeError, ValueError):
            schritt = 10

        try:
            daten = sonnenstand.tagesdaten(lat, lon, tag, schritt)
        except ValueError as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "sonne": daten})

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

    def _projekt_antwort(self, fehler_status: int = 400):
        """Gemeinsame Fehlerbehandlung der Projekt-Endpunkte."""
        kern_db, kern_pj = _kern_projekt()
        if kern_pj is None:
            self._send_json(
                {"ok": False, "fehler": "Datenschicht (kern) nicht verfuegbar -- "
                                        "Projekte koennen nicht gespeichert werden."},
                status=503)
            return None, None
        return kern_db, kern_pj

    def _send_datei(self, inhalt: str, dateiname: str, medientyp: str) -> None:
        """Eine Datei zum Herunterladen ausliefern."""
        roh = inhalt.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{medientyp}; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{dateiname}"')
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def _handle_projekt_export(self) -> None:
        """Projekt als JSON (wieder importierbar) oder Kennzahlen als CSV."""
        kern_db, kern_pj = self._projekt_antwort()
        if kern_pj is None:
            return
        query = parse_qs(urlparse(self.path).query)
        projekt_id = (query.get("id") or [""])[0]
        format_ = ((query.get("format") or ["json"])[0]).lower()
        con = kern_db.verbinde()

        try:
            projekt = kern_pj.lade_projekt(con, int(projekt_id))
        except (kern_pj.ProjektError, ValueError) as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=404)
            return

        stamm = "".join(
            z if (z.isalnum() or z in "-_") else "_" for z in (projekt["name"] or "projekt")
        )[:60] or "projekt"

        if format_ == "json":
            daten = kern_pj.exportiere_projekt(
                con, projekt["projekt_id"],
                mit_verlauf=bool((query.get("verlauf") or [""])[0]))
            self._send_datei(json.dumps(daten, ensure_ascii=False, indent=2),
                             f"{stamm}.json", "application/json")
            return

        if format_ == "csv":
            # Die Kennzahlen kommen aus der laufenden Rechnung, nicht aus einer
            # zweiten Quelle -- dafuer braucht es eine fertige Analyse.
            job_id = (query.get("job_id") or [""])[0].strip()
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                kontext = job.get("kontext") if job else None
            if job is None or job["status"] != "done" or not kontext:
                self._send_json(
                    {"ok": False, "fehler": "Fuer den CSV-Export ist eine abgeschlossene "
                                            "Analyse noetig (job_id fehlt oder abgelaufen)."},
                    status=400)
                return
            analyse = Analyse(ergebnis=job["ergebnis"], kontext=kontext)
            ergebnisse = {}
            for v in projekt["varianten"]:
                try:
                    ergebnisse[str(v["variante_id"])] = _rechne_variante(analyse, v)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    ergebnisse[str(v["variante_id"])] = {}
            zeilen = _variantenvergleich(projekt["varianten"], ergebnisse)
            self._send_datei(kern_pj.kennzahlen_csv(zeilen), f"{stamm}.csv", "text/csv")
            return

        self._send_json(
            {"ok": False, "fehler": f"Unbekanntes Format {format_!r} -- json oder csv."},
            status=400)

    def _handle_projekt_import(self) -> None:
        """Ein exportiertes Projekt wiederherstellen.

        Legt immer ein NEUES Projekt an -- ein Import darf keine vorhandene
        Arbeit still verdraengen.
        """
        kern_db, kern_pj = self._projekt_antwort()
        if kern_pj is None:
            return
        daten = self._lies_json_body()
        if daten is None:
            return
        con = kern_db.verbinde()
        try:
            projekt = kern_pj.importiere_projekt(
                con, daten.get("projektdatei") or daten, name=daten.get("name"))
        except kern_pj.ProjektError as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "projekt": projekt})

    def _handle_projekte_lesen(self) -> None:
        """Uebersicht 'Meine Projekte' oder ein einzelnes Projekt."""
        kern_db, kern_pj = self._projekt_antwort()
        if kern_pj is None:
            return
        query = parse_qs(urlparse(self.path).query)
        con = kern_db.verbinde()
        projekt_id = (query.get("id") or [None])[0]
        try:
            if projekt_id:
                projekt = kern_pj.lade_projekt(con, int(projekt_id))
                antwort = {"ok": True, "projekt": projekt}
                if (query.get("verlauf") or [""])[0] and projekt["aktive_variante_id"]:
                    antwort["verlauf"] = kern_pj.verlauf(con, projekt["aktive_variante_id"])
                self._send_json(antwort)
            else:
                self._send_json({"ok": True, "projekte": kern_pj.liste_projekte(con),
                                 "statistik": kern_pj.statistik(con)})
        except (kern_pj.ProjektError, ValueError) as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=404)

    def _handle_projekt_schreiben(self) -> None:
        """Projekt anlegen, umbenennen, aktive Variante setzen, Variante
        speichern, duplizieren, loeschen, Stand wiederherstellen.

        Eine Aktion je Aufruf ueber das Feld `aktion` -- so bleibt die
        Oberflaeche mit einem Endpunkt auskommend.
        """
        kern_db, kern_pj = self._projekt_antwort()
        if kern_pj is None:
            return
        daten = self._lies_json_body()
        if daten is None:
            return
        con = kern_db.verbinde()
        aktion = (daten.get("aktion") or "").strip()

        try:
            if aktion == "projekt_anlegen":
                projekt = kern_pj.erstelle_projekt(
                    con, daten.get("name") or "", daten.get("egrid") or "",
                    daten.get("adresse"), notiz=daten.get("notiz"))
            elif aktion == "projekt_umbenennen":
                projekt = kern_pj.benenne_projekt_um(
                    con, int(daten["projekt_id"]), daten.get("name") or "")
            elif aktion == "projekt_loeschen":
                geloescht = kern_pj.loesche_projekt(con, int(daten["projekt_id"]))
                self._send_json({"ok": geloescht, "geloescht": geloescht},
                                status=200 if geloescht else 404)
                return
            elif aktion == "variante_aktiv":
                projekt = kern_pj.setze_aktive_variante(
                    con, int(daten["projekt_id"]), int(daten["variante_id"]))
            elif aktion == "variante_anlegen":
                v = kern_pj.erstelle_variante(
                    con, int(daten["projekt_id"]), daten.get("name") or "",
                    daten.get("szenario_id") or "", daten.get("eingaben"))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            elif aktion == "variante_speichern":
                v = kern_pj.speichere_variante(
                    con, int(daten["variante_id"]),
                    name=daten.get("name"), szenario_id=daten.get("szenario_id"),
                    eingaben=daten.get("eingaben"),
                    eingaben_zusammenfuehren=daten.get("zusammenfuehren", True))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            elif aktion == "variante_duplizieren":
                v = kern_pj.dupliziere_variante(
                    con, int(daten["variante_id"]), daten.get("name"))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            elif aktion == "variante_loeschen":
                v = kern_pj.lade_variante(con, int(daten["variante_id"]))
                kern_pj.loesche_variante(con, int(daten["variante_id"]))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            elif aktion == "ansicht_speichern":
                # Kamera, Ebenen, Sonnenstand und Messungen. Bewusst kein
                # neuer Stand: der Blick auf das Ergebnis ist keine Annahme.
                v = kern_pj.speichere_ansicht(
                    con, int(daten["variante_id"]), daten.get("ansicht"))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            elif aktion == "stand_wiederherstellen":
                v = kern_pj.stelle_stand_wieder_her(
                    con, int(daten["variante_id"]), int(daten["stand"]))
                projekt = kern_pj.lade_projekt(con, v["projekt_id"])
            else:
                self._send_json(
                    {"ok": False, "fehler": f"Unbekannte Aktion {aktion!r}."}, status=400)
                return
        except kern_pj.ProjektError as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json({"ok": False, "fehler": f"Ungueltige Eingabe: {exc}"}, status=400)
            return

        self._send_json({"ok": True, "projekt": projekt})

    def _handle_variante_rechnen(self) -> None:
        """Eine Variante rechnen -- oder alle fuer den Vergleich.

        Braucht eine fertige Analyse (job_id): die Variante haelt bewusst
        keine amtlichen Basisdaten, sie orchestriert nur.
        """
        kern_db, kern_pj = self._projekt_antwort()
        if kern_pj is None:
            return
        daten = self._lies_json_body()
        if daten is None:
            return
        job_id = (daten.get("job_id") or "").strip()
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            kontext = job.get("kontext") if job else None
        if job is None or job["status"] != "done" or not kontext:
            self._send_json(
                {"ok": False, "fehler": "Keine abgeschlossene Analyse zu dieser job_id."},
                status=404)
            return

        con = kern_db.verbinde()
        analyse = Analyse(ergebnis=job["ergebnis"], kontext=kontext)
        try:
            if daten.get("variante_id"):
                varianten = [kern_pj.lade_variante(con, int(daten["variante_id"]))]
            else:
                projekt = kern_pj.lade_projekt(con, int(daten["projekt_id"]))
                varianten = projekt["varianten"]
        except (kern_pj.ProjektError, KeyError, TypeError, ValueError) as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return

        ergebnisse = {}
        for v in varianten:
            try:
                ergebnisse[str(v["variante_id"])] = _rechne_variante(analyse, v)
            except Exception as exc:  # noqa: BLE001 -- eine Variante darf die uebrigen nicht reissen
                traceback.print_exc()
                ergebnisse[str(v["variante_id"])] = {
                    "variante": {"variante_id": v["variante_id"], "name": v["name"],
                                 "szenario_id": v["szenario_id"]},
                    "fehler": str(exc),
                }

        antwort = {"ok": True, "ergebnisse": ergebnisse}
        if len(ergebnisse) == 1:
            antwort["ergebnis"] = next(iter(ergebnisse.values()))
        else:
            antwort["vergleich"] = _variantenvergleich(varianten, ergebnisse)
        self._send_json(antwort)

    def _handle_umgebung(self) -> None:
        """Raeumlicher Kontext fuer die 3D-Ansicht.

        Bewusst ein eigener Endpunkt statt Teil der Analyse: die Szene kostet
        rund eine Sekunde und wird nur gebraucht, wenn jemand die 3D-Ansicht
        oeffnet. Das Ergebnis wird am Job zwischengespeichert -- ein zweites
        Oeffnen laedt nichts nach.
        """
        from potenzial_engine.umgebung import UmgebungError, hole_umgebung

        query = parse_qs(urlparse(self.path).query)
        job_id = (query.get("job_id") or [""])[0].strip()
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            fertig = bool(job and job["status"] == "done")
            zwischenspeicher = job.get("umgebung") if job else None
        if not fertig:
            self._send_json(
                {"ok": False, "fehler": "Keine abgeschlossene Analyse zu dieser job_id."},
                status=404)
            return
        if zwischenspeicher is not None:
            self._send_json({"ok": True, "umgebung": zwischenspeicher, "aus_zwischenspeicher": True})
            return

        m1 = (job["ergebnis"] or {}).get("modul1_geodaten") or {}
        geo = m1.get("geocoding") or {}
        kataster = m1.get("kataster") or {}
        ring = kataster.get("parzellengeometrie")
        e, n = geo.get("lv95_e"), geo.get("lv95_n")
        if not ring or e is None or n is None:
            self._send_json(
                {"ok": False, "fehler": "Ohne Parzellengeometrie und Koordinaten keine Szene."},
                status=422)
            return

        try:
            umgebung = hole_umgebung(float(e), float(n), ring, eigenes_egrid=kataster.get("egrid"))
        except UmgebungError as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=502)
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "fehler": f"Unerwarteter Fehler: {exc}"}, status=500)
            return

        with _JOBS_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id]["umgebung"] = umgebung
        self._send_json({"ok": True, "umgebung": umgebung, "aus_zwischenspeicher": False})

    def _handle_marktdaten_lesen(self) -> None:
        """Gespeicherte Vergleichsobjekte und ihre Auswertung."""
        from potenzial_engine import marktdaten as mdt

        query = parse_qs(urlparse(self.path).query)
        einzel = lambda k: (query.get(k) or [None])[0]  # noqa: E731
        gemeinde, kanton = einzel("gemeinde"), einzel("kanton")
        objekte, fehler = _lade_vergleichsobjekte(
            gemeinde=gemeinde, kanton=kanton, objektart=einzel("objektart"))
        filter_ = mdt.Vergleichsfilter(gemeinde=gemeinde, kanton=kanton,
                                       objektart=einzel("objektart"))
        lage = {g: mdt.werte_referenzen_aus(objekte, g, filter_).to_dict()
                for g in (mdt.GROESSE_VERKAUF, mdt.GROESSE_MIETE, mdt.GROESSE_BODEN)}
        self._send_json({
            "ok": True, "fehler": fehler,
            "anzahl": len(objekte),
            "objekte": [o.to_dict() for o in objekte],
            "marktlage": lage,
        })

    def _handle_marktdaten_schreiben(self) -> None:
        """Vergleichsobjekte erfassen -- einzeln oder als CSV-Import."""
        from potenzial_engine import marktdaten as mdt

        daten = self._lies_json_body()
        if daten is None:
            return
        kern_db, kern_markt = _kern_marktdaten()
        if kern_markt is None:
            self._send_json(
                {"ok": False, "fehler": "Datenschicht (kern) nicht verfuegbar -- "
                                        "Vergleichsobjekte koennen nicht abgelegt werden."},
                status=503)
            return

        quelle = (daten.get("quelle") or "").strip()
        herkunftsart = daten.get("herkunftsart") or mdt.HERKUNFT_GEBIMO
        try:
            if daten.get("csv"):
                if not quelle:
                    self._send_json({"ok": False, "fehler": "Fuer einen CSV-Import ist 'quelle' noetig."},
                                    status=400)
                    return
                objekte, fehler = mdt.lese_csv(
                    daten["csv"], quelle=quelle, herkunftsart=herkunftsart,
                    datenstand=daten.get("datenstand"))
            else:
                eintraege = daten.get("objekte") or ([daten["objekt"]] if daten.get("objekt") else [])
                for e in eintraege:
                    e.setdefault("herkunftsart", herkunftsart)
                    if quelle:
                        e.setdefault("quelle", quelle)
                objekte, fehler = mdt.aus_dicts(eintraege)
        except mdt.MarktdatenError as exc:
            self._send_json({"ok": False, "fehler": str(exc)}, status=400)
            return

        if not objekte:
            self._send_json(
                {"ok": False, "fehler": "Kein gueltiges Vergleichsobjekt erkannt.", "details": fehler},
                status=400)
            return

        con = kern_db.verbinde()
        bilanz = kern_markt.speichere(con, objekte)
        self._send_json({"ok": True, "gespeichert": bilanz, "abgelehnt": fehler,
                         "statistik": kern_markt.statistik(con)})

    def _handle_marktdaten_loeschen(self) -> None:
        daten = self._lies_json_body()
        if daten is None:
            return
        kern_db, kern_markt = _kern_marktdaten()
        if kern_markt is None:
            self._send_json({"ok": False, "fehler": "Datenschicht (kern) nicht verfuegbar."}, status=503)
            return
        try:
            objekt_id = int(daten.get("vergleichsobjekt_id"))
        except (TypeError, ValueError):
            self._send_json({"ok": False, "fehler": "vergleichsobjekt_id fehlt oder ist keine Zahl."},
                            status=400)
            return
        con = kern_db.verbinde()
        geloescht = kern_markt.loesche(con, objekt_id)
        self._send_json({"ok": geloescht, "geloescht": geloescht,
                         "statistik": kern_markt.statistik(con)},
                        status=200 if geloescht else 404)

    def do_POST(self) -> None:  # noqa: N802
        self._pfad_ohne_api()
        if not self._zugang_ok():
            return
        if self.path == "/projekt":
            self._handle_projekt_schreiben()
            return
        if self.path == "/projekt/import":
            self._handle_projekt_import()
            return
        if self.path == "/projekt/rechnen":
            self._handle_variante_rechnen()
            return
        if self.path == "/marktdaten":
            self._handle_marktdaten_schreiben()
            return
        if self.path == "/marktdaten/loeschen":
            self._handle_marktdaten_loeschen()
            return
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
            target=self._job_ausfuehren,
            args=(job_id, adresse, verkaufspreis, verkaufspreis_total,
                  bool(daten.get("neu_rechnen"))),
            daemon=True,
        )
        thread.start()

        self._send_json({"ok": True, "job_id": job_id})

    def _zwischenspeicher_suchen(self, adresse: str) -> tuple[Optional[dict], Optional[str]]:
        """Sucht eine bereits gerechnete, noch gueltige Analyse.

        Der Schluessel ist der EGRID, nicht die Adresse: "Rosenweg 4, Buchs"
        und "Rosenweg 4, 5033 Buchs AG" sind dasselbe Grundstueck. Um ihn zu
        bekommen, kosten Geocoding und Parzellenabfrage rund eine Sekunde --
        gegen 129 Sekunden fuer die volle Analyse.

        Gibt (ergebnis, egrid) zurueck. Beides kann None sein; ein Fehler
        beim Nachschlagen fuehrt IMMER zur vollen Analyse und nie zum
        Abbruch -- ein defekter Zwischenspeicher darf das Werkzeug nicht
        unbenutzbar machen.
        """
        kern_db, _ = _kern_projekt()
        if kern_db is None:
            return None, None
        try:
            geo = geocode_address(adresse)
            if not geo or geo.get("lv95_e") is None:
                return None, None
            parzelle = get_parcel_data(geo["lv95_e"], geo["lv95_n"])
            egrid = (parzelle or {}).get("egrid")
            if not egrid:
                return None, None

            con = kern_db.verbinde()
            zeile = kern_db.juengste_analyse(con, egrid, ENGINE_VERSION, _EINGABEN_HASH)
            if zeile is None:
                return None, egrid

            alter_tage = _alter_in_tagen(zeile["erstellt_am"])
            if alter_tage is None or alter_tage > ANALYSE_CACHE_TAGE:
                return None, egrid

            ergebnis = json.loads(zeile["ergebnis_json"])
            # Der Benutzer muss SEHEN, dass dies eine gespeicherte Rechnung
            # ist und von wann. Ein Ergebnis ohne Datum waere eine Behauptung
            # ueber den heutigen Stand der amtlichen Grundlagen.
            ergebnis["zwischenspeicher"] = {
                "aus_zwischenspeicher": True,
                "gerechnet_am": zeile["erstellt_am"],
                "alter_tage": round(alter_tage, 2),
                "gueltig_bis_tage": ANALYSE_CACHE_TAGE,
            }
            return ergebnis, egrid
        except Exception:  # noqa: BLE001 -- nie am Zwischenspeicher scheitern
            traceback.print_exc()
            return None, None

    def _zwischenspeicher_ablegen(self, egrid: Optional[str], ergebnis: dict) -> None:
        """Legt eine erfolgreiche Analyse ab. Fehler bleiben draussen."""
        if not egrid:
            return
        kern_db, _ = _kern_projekt()
        if kern_db is None:
            return
        try:
            con = kern_db.verbinde()
            m1 = ergebnis.get("modul1_geodaten") or {}
            kataster = m1.get("kataster") or {}
            gemeinde = m1.get("gemeinde") or {}
            geo = m1.get("geocoding") or {}
            # Der Fremdschluessel verlangt das Grundstueck zuerst.
            kern_db.speichere_grundstueck(con, {
                "egrid": egrid,
                "parzellennummer": kataster.get("parzellennummer"),
                "flaeche_m2": kataster.get("flaeche_m2"),
                "flaeche_quelle": kataster.get("flaeche_quelle"),
                "gemeinde": gemeinde.get("gemeinde"),
                "bfs_nummer": gemeinde.get("bfs_nummer"),
                "kanton": gemeinde.get("kanton"),
                "lv95_e": (geo.get("lv95_koordinaten") or {}).get("lv95_e") or geo.get("lv95_e"),
                "lv95_n": (geo.get("lv95_koordinaten") or {}).get("lv95_n") or geo.get("lv95_n"),
            })
            kern_db.speichere_analyse(
                con, egrid, ENGINE_VERSION, _EINGABEN_HASH, "erfolgreich", ergebnis)
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    def _job_ausfuehren(
        self, job_id: str, adresse: str, verkaufspreis: Optional[float],
        verkaufspreis_total: Optional[float] = None, neu_rechnen: bool = False
    ) -> None:
        egrid = None
        try:
            if not neu_rechnen:
                gespeichert, egrid = self._zwischenspeicher_suchen(adresse)
                if gespeichert is not None:
                    # Der Kontext wird aus dem Ergebnis zurueckgebaut statt
                    # mitgespeichert. Das ist geprueft gleichwertig, nicht
                    # angenommen: kontext["modul2"] IST
                    # ergebnis["modul2_bzo_analyse"], und kontext["modul1"]
                    # unterscheidet sich von ergebnis["modul1_geodaten"] nur
                    # um die rohen API-Blobs (raw_attributes, raw,
                    # raw_extract). Die Quellenobjekte entstehen VOR dem
                    # Trimmen, und keine nachgelagerte Rechnung liest diese
                    # Felder. Das spart je Eintrag mehrere Megabyte.
                    #
                    # Wer spaeter einen Verbraucher fuer die Rohdaten baut,
                    # muss sie hier mitspeichern -- sonst rechnet eine
                    # gespeicherte Analyse anders als eine frische.
                    with _JOBS_LOCK:
                        _JOBS[job_id].update(
                            status="done", ergebnis=gespeichert,
                            kontext={"modul1": gespeichert.get("modul1_geodaten"),
                                     "modul2": gespeichert.get("modul2_bzo_analyse")})
                    return

            analyse = analysiere_grundstueck(adresse)
            analyse.ergebnis["zwischenspeicher"] = {
                "aus_zwischenspeicher": False,
                "gerechnet_am": _jetzt_iso(),
                "alter_tage": 0.0,
                "gueltig_bis_tage": ANALYSE_CACHE_TAGE,
            }
            if egrid is None:
                egrid = ((analyse.ergebnis.get("modul1_geodaten") or {})
                         .get("kataster") or {}).get("egrid")
            self._zwischenspeicher_ablegen(egrid, analyse.ergebnis)
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


# Die Analyse haengt heute nur an der Adresse -- weitere Eingaben wuerden
# hier einfliessen. Konstant, damit der Schluessel stabil bleibt.
_EINGABEN_HASH = "adresse"


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _alter_in_tagen(zeitpunkt: str) -> Optional[float]:
    """Alter eines gespeicherten Eintrags in Tagen, oder None wenn unlesbar."""
    try:
        gespeichert = datetime.fromisoformat(zeitpunkt)
    except (TypeError, ValueError):
        return None
    if gespeichert.tzinfo is None:
        gespeichert = gespeichert.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - gespeichert).total_seconds() / 86400.0


def _bereitschaft() -> dict[str, Any]:
    """Was der Dienst ueber sich selbst sagen kann.

    Die Unterscheidung, um die es geht: ERREICHBAR heisst nicht
    EINSATZBEREIT. Ein Dienst ohne LLM-Schluessel antwortet auf jeden
    Aufruf -- und scheitert dann bei jeder Analyse an derselben Stelle.
    Das gehoert hier gemeldet und nicht erst im Fehlertext einer Analyse,
    die drei Minuten gelaufen ist.
    """
    pruefungen: dict[str, Any] = {}

    # Modul 2 braucht einen Schluessel. Geprueft wird NUR, ob einer gesetzt
    # ist -- der Wert selbst wird nie ausgegeben.
    pruefungen["llm_schluessel"] = bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    try:
        import shapely  # noqa: F401
        pruefungen["geometrie"] = True
    except ImportError:
        pruefungen["geometrie"] = False

    try:
        from google import genai  # noqa: F401
        pruefungen["llm_bibliothek"] = True
    except ImportError:
        pruefungen["llm_bibliothek"] = False

    kern_db, kern_pj = _kern_projekt()
    if kern_pj is None:
        pruefungen["datenschicht"] = False
    else:
        try:
            con = kern_db.verbinde()
            con.execute("SELECT 1").fetchone()
            pruefungen["datenschicht"] = True
        except Exception:  # noqa: BLE001 -- jede Ursache heisst hier "nicht bereit"
            pruefungen["datenschicht"] = False

    with _JOBS_LOCK:
        # Der Status heisst "running" -- hier stand vorher "laeuft", und der
        # Health-Check meldete dadurch immer null laufende Jobs.
        laufend = sum(1 for j in _JOBS.values() if j.get("status") == "running")
        gesamt = len(_JOBS)

    bereit = all(pruefungen.values())
    return {
        "ok": True,                      # der Dienst antwortet
        "bereit": bereit,                # und kann auch arbeiten
        "service": "grundstueck-crawler-backend",
        "umgebung": UMGEBUNG,
        "pruefungen": pruefungen,
        "jobs": {"laufend": laufend, "bekannt": gesamt},
    }


def main() -> None:
    port = _port()
    zustand = _bereitschaft()

    # Beim Start einmal sagen, was fehlt. Im Betrieb ist das die einzige
    # Gelegenheit, einen Konfigurationsfehler zu bemerken, bevor der erste
    # Nutzer darueber stolpert.
    for name, ok in zustand["pruefungen"].items():
        if not ok:
            print(f"WARNUNG: {name} nicht verfuegbar -- betroffene Funktionen schlagen fehl.",
                  file=sys.stderr)
    if zustand["bereit"]:
        print(f"Bereitschaft vollstaendig ({UMGEBUNG}).", file=sys.stderr)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Grundstueck-Crawler-Backend ({UMGEBUNG}) laeuft auf Port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

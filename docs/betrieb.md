# Betrieb: Entwicklung und Produktion

**Stand:** 12.09.2026 · **Status:** Bestandsaufnahme und Plattformvergleich
**Ziel:** Das Werkzeug ist erreichbar, ohne dass ein lokaler PC läuft.

---

## 1 Bestand

| Teil | Wo | Zustand |
|---|---|---|
| Frontend | `dist/index.html` → Cloudflare Pages | läuft, `grundstueck-crawler.pages.dev` |
| API-Weiterleitung | `functions/api/[[path]].js` | Pages Function, proxyt `/api/*` an `env.BACKEND_URL` |
| Backend | `webapp.py`, Python-Stdlib `ThreadingHTTPServer` | kein Framework, Port aus `PORT` |
| Engine | `potenzial_engine/` | requests, shapely, google-genai |
| Datenschicht | `Crawler/kern/` (SQLite) | Pfad aus `KERN_DB_PFAD` |
| Verbindung | **Cloudflare Quick Tunnel** | **URL wechselt bei jedem Neustart — die Ursache des Problems** |
| Secrets | `GEMINI_API_KEY` als Umgebungsvariable | nie im Repo, `.gitignore` deckt `.env` ab |
| Health-Check | `GET /health` | unterscheidet *erreichbar* von *einsatzbereit* |

### Gefundene Produktionsblocker

1. **`google-genai` war in `pyproject.toml` nicht deklariert.** Ein Container-Build
   wäre gestartet, aber jede Analyse an derselben Stelle gescheitert. *Behoben.*
2. **Der Proxy warf Antwort-Header weg.** CSV- und JSON-Exporte kamen über die
   öffentliche URL als `application/json` ohne Dateinamen an. *Behoben.*
3. **Jobs liegen im Arbeitsspeicher.** Zwei Instanzen würden sich nicht kennen:
   Instanz A nimmt `POST /analyze`, Instanz B beantwortet `GET /status/<id>` mit
   „nicht gefunden". → **Genau eine Instanz**, bis Jobs in der Datenbank liegen.
4. **Port und Datenbankpfad waren fest verdrahtet.** *Behoben:* `PORT`,
   `KERN_DB_PFAD`, `UMGEBUNG`.

---

## 2 Was eine Analyse tatsächlich kostet

Gemessen an einem echten Fall (Rosenweg 4, 5033 Buchs AG), nicht geschätzt:

| Grösse | Wert |
|---|---|
| Gesamtdauer | **128.9 s** |
| Eigene CPU-Zeit | **5.2 s (4.0 %)** |
| Warten auf fremde Server | **123.7 s (96.0 %)** |
| davon 33 amtliche Abrufe | 8.3 s |
| davon 1 Gemini-Aufruf | ~115 s |
| Empfangene Daten | 28.9 MB |
| Spitzenspeicher (Python) | 176 MB |
| Ergebnis | 698 kB JSON |

**Das ist die entscheidende Zahl des ganzen Vergleichs.** Die Engine rechnet
kaum — sie wartet. Gesucht ist also keine Rechenleistung, sondern ein Ort, an
dem ein Prozess zwei Minuten billig warten darf.

### Hochrechnung

| | 10/Tag | 30/Tag | 100/Tag |
|---|---|---|---|
| Analysen/Monat | 300 | 900 | 3'000 |
| CPU-Zeit | 26 min | 78 min | 4.3 h |
| Laufzeit (Wanduhr) | 10.7 h | 32 h | 107 h |
| Eingehend (amtlich) | 8.7 GB | 26 GB | 87 GB |
| Ausgehend (Ergebnisse) | 0.2 GB | 0.6 GB | 2.1 GB |
| Gemini-Aufrufe | 300 | 900 | 3'000 |

---

## 3 Plattformvergleich

### Cloudflare Workers — **ungeeignet (Option C)**

| Grenze (Free) | Wir brauchen |
|---|---|
| **10 ms CPU je Aufruf** | 5'200 ms — Faktor 520 darüber |
| 128 MB Speicher | 176 MB allein an Python-Allokationen |
| 50 Subrequests je Request | 34 — das wäre das kleinste Problem |

Dazu: Python auf Workers läuft über Pyodide/WASM. **shapely** (C-Erweiterung
auf GEOS) und **google-genai** lassen sich so nicht betreiben. Ein Umbau wäre
eine zweite Engine — ausdrücklich ausgeschlossen.

**Cloudflare Containers** wären technisch passend (Scale-to-zero, echtes
Abbild), setzen aber den Workers-Paid-Plan von 5 $/Monat voraus. Nicht gratis.

**Cloudflare Pages bleibt trotzdem das Frontend** — daran ändert sich nichts.

### Supabase — **löst die andere Hälfte, nicht diese**

Supabase ist eine Datenbank, kein Ort für Python. Die 129 Sekunden Analyse
laufen dort nicht. Free: 500 MB Datenbank, 1 GB Dateien, **Pause nach 7 Tagen
Inaktivität**, zwei aktive Projekte.

Für *später* sinnvoll — Accounts, Rollen, Sharing (Abschnitt 8 im
[Funktionsregister](funktionsregister.md)). **Jetzt nicht nötig:** unsere
persistenten Daten sind winzig (2.8 kB je Projekt), SQLite genügt bei weitem.
Nicht verwerfen, zurückstellen.

### Google Cloud Run — **kostenlos mit technischem Nachteil (Option B)**

Free Tier: 180'000 vCPU-s, 360'000 GiB-s, 2 Mio. Requests, 1 GB Egress/Monat.

**Der Haken:** Bei der Standardabrechnung (request-based) wird die CPU
*zwischen* Requests gedrosselt. Unser Hintergrund-Thread, der die Analyse
ausführt, friert nach der Antwort auf `POST /analyze` ein. Das ist keine
Vermutung, das steht so in der Dokumentation.

Zwei Auswege, beide mit Preis:

| Weg | Preis |
|---|---|
| Instance-based billing (CPU immer an) | Leerlauf wird mitbezahlt, Free Tier schneller aufgebraucht |
| Analyse im Request statt im Thread | 129-s-Request durch den Cloudflare-Proxy — Cloudflare bricht bei ~100 s ab |

Dazu: **kein Datenträger.** SQLite müsste nach Turso (libSQL, gleicher
SQL-Dialekt, 9 GB frei) oder auf GCS-FUSE umziehen.

Rechnung bei 0.5 vCPU, synchron: 64.5 vCPU-s je Analyse.

| | Verbrauch | im Free Tier? |
|---|---|---|
| 10/Tag | 19'350 vCPU-s | ✅ |
| 30/Tag | 58'050 vCPU-s | ✅ |
| 100/Tag | 193'500 vCPU-s | ❌ knapp drüber, dazu 2.1 GB Egress gegen 1 GB frei |

### Oracle Cloud Always Free — **kostenlos und geeignet (Option A)**

2 OCPU (ARM) / 12 GB RAM / 200 GB Blockspeicher, **dauerhaft frei**, kein
Ablaufdatum. (Im Juni 2026 von 4/24 auf 2/12 reduziert — ohne Ankündigung.)

| Anforderung | Erfüllt |
|---|---|
| Python-Engine unverändert | ✅ kein Umbau |
| SQLite auf echtem Datenträger | ✅ 200 GB |
| Job-Modell unverändert | ✅ kein CPU-Throttling |
| 129-s-Analyse | ✅ kein Request-Timeout |
| 176 MB Speicherbedarf | ✅ 12 GB vorhanden — Faktor 68 Luft |
| 100 Analysen/Tag = 107 h/Monat | ✅ die Maschine läuft ohnehin 720 h |
| Kein Kaltstart | ✅ läuft durch |

**Risiken, ehrlich benannt:**

* Kreditkarte zur Identitätsprüfung nötig (Always Free wird nicht belastet)
* ARM-Kapazität ist je nach Region zeitweise nicht verfügbar
* Betriebssystem, TLS und Neustarts pflegst du selbst
* Oracle hat die Grenzen schon einmal ohne Ankündigung halbiert

### Weitere geprüfte Optionen

| Plattform | Befund |
|---|---|
| **Hugging Face Spaces** | Docker, 2 vCPU/16 GB frei, schläft nach 48 h — aber **persistenter Speicher kostet ab 5 $/Monat**. Ohne ihn sind Projekte nach jedem Schlaf weg. |
| **Render Free** | Schläft nach 15 min, ~50 s Kaltstart, Disk kostenpflichtig. |
| **Fly.io** | Kein echtes Gratiskontingent mehr, Guthabenmodell. |
| **Railway, Koyeb** | Trial-Guthaben bzw. stark begrenzt — keine Dauerlösung. |

---

## 4 Der grösste Hebel ist nicht die Plattform

`kern/db.py` hat `speichere_analyse()` mit `engine_version` und
`eingaben_hash` — offensichtlich als Zwischenspeicher gedacht. **`webapp.py`
ruft es nie auf.**

Jede Analyse desselben Grundstücks kostet erneut 129 Sekunden und einen
Gemini-Aufruf. Ein Zwischenspeicher auf dem EGRID senkt jede Wiederholung auf
Millisekunden — und die Tabelle dafür steht schon.

Das wirkt auf **jeder** Plattform und macht den Unterschied zwischen
Optionen A und B deutlich kleiner.

---

## 5 Empfehlung

**Option A: Oracle Cloud Always Free.**

Es ist die einzige dauerhaft kostenlose Möglichkeit, die bestehende Engine
**ohne Architekturwechsel** zu betreiben. Kein zweites Datenmodell, kein
Umbau des Job-Modells, keine zweite Engine — genau das, was die
Architekturprinzipien verlangen.

Cloud Run (Option B) ist die Alternative, wenn du keinen Server pflegen
willst. Preis dafür: Umbau des Job-Modells **und** Umzug der Datenbank nach
Turso. Beides machbar, beides Aufwand, der nichts am Produkt verbessert.

**Unabhängig von der Wahl zuerst:** den Analyse-Zwischenspeicher einbauen.

### Aufbau nach Option A

```
Browser
  └─ grundstueck-crawler.pages.dev        Cloudflare Pages (unverändert)
       └─ /api/*  → Pages Function        Proxy (unverändert)
            └─ BACKEND_URL                → https://api.<deine-domain>
                 └─ Caddy                 TLS automatisch
                      └─ Docker           webapp.py + potenzial_engine + kern
                           └─ /daten      SQLite auf Blockspeicher
```

---

## 6 Entwicklung und Produktion

| | Entwicklung | Produktion |
|---|---|---|
| Backend | `python webapp.py` lokal | Container auf dem Server |
| `UMGEBUNG` | `entwicklung` | `produktion` |
| Datenbank | `Crawler/kern/data/kern.db` | `/daten/kern.db` auf dem Volume |
| Frontend | lokaler Testserver | Cloudflare Pages |
| Anzeige | „Umgebung: entwicklung" in der Kopfzeile | keine Anzeige |

Die Oberfläche zeigt die Umgebung an, sobald sie **nicht** Produktion ist.
Sonst arbeitet jemand versehentlich auf der Entwicklungsumgebung und wundert
sich über fehlende Projekte.

---

## 7 Die drei Zustände

Technisch und in der Oberfläche getrennt — das war ausdrückliche Vorgabe:

| Zustand | Auslöser | Was die Oberfläche sagt |
|---|---|---|
| **Technisch** | Netzfehler, 502/503 vom Proxy, 5xx, keine JSON-Antwort | „Analyse-Server nicht erreichbar" + **„Das ist eine technische Störung, kein Befund. Über dieses Grundstück ist damit nichts gesagt."** + Knopf „Erneut versuchen" |
| **Fachlich** | Dienst antwortet, amtliche Grundlage fehlt | „Analyse nicht möglich" + Begründung + „Die Engine gibt bewusst keinen Wert aus …" |
| **Ergebnis** | Analyse durchgelaufen | das Dossier |

Vorher stand unter *jeder* Fehlermeldung derselbe Satz über die fehlende
amtliche Grundlage — auch wenn nur der Server aus war. Das ist die
schlimmste Verwechslung, die dieses Werkzeug machen kann: sie erklärt eine
Betriebsstörung zu einem Befund über ein Grundstück.

Zusätzlich prüft die Oberfläche beim Laden `GET /api/health` und zeigt an,
wenn der Dienst zwar antwortet, aber nicht einsatzbereit ist (etwa ohne
LLM-Schlüssel). Besser jetzt als nach drei Minuten Analyse.

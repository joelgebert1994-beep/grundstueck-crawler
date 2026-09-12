# Lokal benutzen — ohne Claude, ohne Oracle, ohne Tunnel

## Starten

**Doppelklick auf `start.bat`.**

Das war's. Das Fenster bleibt offen und zeigt die Serverausgabe, der Browser
öffnet sich nach drei Sekunden auf <http://localhost:8787>.

**Beenden:** Fenster schliessen oder `Strg+C`.

Wer lieber selbst tippt:

```
cd "…\Desktop\grundstueck-crawler"
python webapp.py
```

und dann <http://localhost:8787> öffnen.

---

## Einmalig einrichten

### 1 · Python

<https://www.python.org/downloads/> — beim Installieren **„Add python.exe to
PATH"** ankreuzen. `start.bat` prüft das und sagt Bescheid, wenn es fehlt.

### 2 · Pakete

Macht `start.bat` beim ersten Lauf selbst. Von Hand:

```
python -m pip install -r requirements.txt
```

### 3 · Schlüssel für die Reglementsauswertung

Modul 2 liest die kommunale Bau- und Nutzungsordnung mit einem Sprachmodell.
Dafür braucht es einen kostenlosen Schlüssel:
<https://aistudio.google.com/apikey>

Lege neben `start.bat` eine Datei **`.env.lokal`** an:

```
GEMINI_API_KEY=dein-schluessel
```

Diese Datei ist in `.gitignore` — sie landet nie im Repository.

> **Ohne Schlüssel** läuft alles ausser Modul 2. Die Analyse bricht dann mit
> einer klaren Meldung ab, statt eine Zone zu raten.

---

## Was lokal funktioniert

| | |
|---|---|
| Adresse analysieren | ✅ echte amtliche Daten |
| Karte, 3D, Sonne, Schatten, Messwerkzeuge | ✅ |
| Projekte und Varianten speichern | ✅ in `../Crawler/kern/data/kern.db` |
| Vergleichsobjekte erfassen | ✅ |
| Wirtschaftlichkeit, Szenarienvergleich | ✅ |
| Dossier, PDF, CSV, JSON | ✅ |
| Zwischenspeicher | ✅ |

Beliebig viele Grundstücke, beliebig oft. Es gibt kein Limit.

---

## Den Zwischenspeicher prüfen

1. Eine Adresse analysieren — dauert 1–3 Minuten.
2. **Dieselbe Adresse nochmals** analysieren — dauert ~1 Sekunde.
3. Oben erscheint ein gelber Hinweis: *„Dieses Ergebnis stammt aus einer
   gespeicherten Analyse vom …"* mit Knopf **Jetzt neu rechnen**.

Der Schlüssel ist der EGRID, nicht der Adresstext: „Rosenweg 4, Buchs" und
„Rosenweg 4, 5033 Buchs AG" treffen denselben Eintrag.

Gültigkeit 30 Tage. Anders einstellen:

```
set ANALYSE_CACHE_TAGE=1
python webapp.py
```

Alles verwerfen und neu rechnen lassen:

```
python -c "import sys; sys.path.insert(0, r'..\Crawler'); from kern import db; c=db.verbinde(); c.execute('DELETE FROM analyse'); c.commit(); print('Zwischenspeicher geleert')"
```

---

## Läuft es? — Selbstauskunft

<http://localhost:8787/health>

```json
{"ok": true, "bereit": true, "umgebung": "entwicklung",
 "pruefungen": {"llm_schluessel": true, "geometrie": true,
                "llm_bibliothek": true, "datenschicht": true}}
```

* `ok` — der Dienst antwortet
* `bereit` — er kann auch arbeiten
* `pruefungen` — was genau fehlt, falls nicht

In der Oberfläche steht oben **„Umgebung: entwicklung"**. Diese Anzeige
erscheint nur ausserhalb der Produktion — sie ist die Antwort auf „arbeite
ich gerade lokal oder online?".

---

## Wenn etwas klemmt

| Symptom | Ursache | Abhilfe |
|---|---|---|
| „Python wurde nicht gefunden" | nicht im PATH | Python neu installieren, Häkchen bei PATH |
| „Port 8787 ist belegt" | läuft schon | `start.bat` öffnet dann nur den Browser |
| `bereit: false`, `llm_schluessel: false` | Schlüssel fehlt | `.env.lokal` anlegen, neu starten |
| `bereit: false`, `datenschicht: false` | `Crawler`-Ordner fehlt daneben | beide Ordner müssen nebeneinander liegen |
| „Analyse-Server nicht erreichbar" | Backend aus | Fenster von `start.bat` prüfen |
| „Analyse nicht möglich" + ÖREB-Meldung | **kein** Fehler | für dieses Grundstück fehlt die amtliche Grundlage |

Die letzten beiden sehen ähnlich aus und sind grundverschieden: das eine ist
eine Betriebsstörung, das andere ein Befund. Die Oberfläche unterscheidet sie
sichtbar — technische Störungen sagen ausdrücklich *„Das ist eine technische
Störung, kein Befund"*.

---

## Verzeichnisse

```
Desktop/
  ├── grundstueck-crawler/     Engine, Backend, Oberfläche
  │     ├── start.bat          ← Doppelklick
  │     ├── webapp.py
  │     ├── .env.lokal         ← dein Schlüssel (nie im Repo)
  │     └── dist/index.html
  └── Crawler/
        └── kern/data/kern.db  Projekte, Varianten, Vergleichsobjekte
```

**Beide Ordner müssen nebeneinander liegen** — `webapp.py` findet die
Datenschicht über `../Crawler`.

---

## Verhältnis zum späteren Online-Betrieb

Es ist **dieselbe Anwendung**, nur andere Umgebungsvariablen:

| | lokal | Oracle (später) |
|---|---|---|
| `UMGEBUNG` | `entwicklung` | `produktion` |
| `PORT` | 8787 | von der Plattform |
| `KERN_DB_PFAD` | `../Crawler/kern/data/` | `/daten/` |
| `ZUGANGSSCHLUESSEL` | leer = offen | gesetzt |
| Oberfläche | vom Backend selbst | von Cloudflare Pages |

Keine zweite Engine, keine zweite Logik. Lokal braucht nichts von Oracle, und
Oracle ändert nichts am lokalen Ablauf.

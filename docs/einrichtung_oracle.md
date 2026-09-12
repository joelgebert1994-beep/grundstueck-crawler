# Einrichtung auf Oracle Always Free — Schritt für Schritt

**Ziel:** `grundstueck-crawler.pages.dev` funktioniert, ohne dass dein PC läuft.
**Kosten:** 0 CHF, ausschliesslich Always-Free-Ressourcen.
**Zeitaufwand:** ~45 Minuten, davon 15 Minuten Warten.

Technische Hintergründe stehen in [`betrieb.md`](betrieb.md). Diese Datei ist
die Anleitung zum Abarbeiten.

---

## Das Zielbild

```
Browser
  └─ grundstueck-crawler.pages.dev          Cloudflare Pages (bleibt wie es ist)
       └─ /api/*  → functions/api/[[path]].js
            │        schickt X-Gebimo-Schluessel mit
            └─ BACKEND_URL → https://api.deine-domain.ch
                 └─ Caddy            TLS automatisch, Port 443
                      └─ Docker      webapp.py + potenzial_engine + kern
                           └─ /daten SQLite, überlebt jedes Einspielen
```

---

## Vorher: was du brauchst

* Eine Kreditkarte für die Identitätsprüfung. **Always Free wird nicht
  belastet** — es gibt nur eine kurzzeitige Verifikationsbuchung.
* Optional eine eigene Domain. Ohne Domain funktioniert es auch (Schritt 5).
* Deinen Gemini-Schlüssel (`GEMINI_API_KEY`), kostenlos unter
  <https://aistudio.google.com/apikey>.

---

## Schritt 1 — Oracle-Konto anlegen

1. <https://www.oracle.com/cloud/free/> → **Start for free**
2. Land: **Schweiz**. Die **Home-Region** kannst du später **nicht mehr
   ändern** — nimm `Switzerland North (Zurich)` oder `Germany Central
   (Frankfurt)`. Always-Free-Ressourcen gibt es nur in der Home-Region.
3. Karte hinterlegen. Es wird nichts abgebucht.

> **Sofort danach auf Pay As You Go hochstufen.**
> Nur so sind die Instanzen von der automatischen Idle-Rückforderung
> ausgenommen. Always-Free-Ressourcen bleiben dabei kostenlos — berechnet
> wird ausschliesslich, was über die Always-Free-Grenzen hinausgeht.
> Menü oben rechts → **Billing & Cost Management** → **Upgrade and Payment**.

---

## Schritt 2 — VM erstellen

**Compute** → **Instances** → **Create instance**

| Feld | Wert | Warum |
|---|---|---|
| Name | `gebimo-backend` | |
| Image | **Ubuntu 22.04** oder Oracle Linux 9 | Ubuntu hat die einfachere Firewall |
| Shape | **Ampere · VM.Standard.A1.Flex** | ARM, das grosse Always-Free-Kontingent |
| OCPUs | **1** | Bedarf gemessen 5.2 s je Analyse. Grenze: 2 |
| Memory | **6 GB** | Bedarf gemessen 176 MB. Grenze: 12 |
| Boot volume | **50 GB** | Minimum. Grenze: 200 GB gesamt |
| SSH-Key | **eigenen hochladen** | den privaten Teil gut aufbewahren |

Achte darauf, dass überall **„Always Free eligible"** steht. Tut es das nicht,
stimmt die Shape oder die Region nicht.

> **„Out of host capacity"?** A1 ist regional oft knapp. Einfach später noch
> einmal versuchen — oder eine andere Verfügbarkeitsdomäne wählen.

Am Ende die **öffentliche IP-Adresse** notieren.

---

## Schritt 3 — Ports in der Oracle-Konsole öffnen

Das ist die Hürde, an der die meisten hängenbleiben — die VM hat **zwei**
Firewalls, und diese hier liegt ausserhalb der VM.

**Networking** → **Virtual Cloud Networks** → dein VCN → **Security Lists** →
**Default Security List** → **Add Ingress Rules**

| Source CIDR | Protokoll | Zielport |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

Die zweite Firewall (auf der VM selbst) erledigt das Einrichtungsskript.

---

## Schritt 4 — Einloggen

```bash
ssh -i ~/.ssh/dein_key ubuntu@<DEINE-IP>
```

Bei Oracle Linux heisst der Benutzer `opc` statt `ubuntu`.

---

## Schritt 5 — Domain festlegen

**Mit eigener Domain** (empfohlen): einen A-Record anlegen, z. B.
`api.gebimo.ch` → `<DEINE-IP>`. Bei Cloudflare als DNS-Anbieter die
Proxy-Wolke auf **grau** (DNS only) stellen — sonst kommt die
Let's-Encrypt-Prüfung nicht durch.

**Ohne eigene Domain:** `sslip.io` benutzen. Aus der IP `152.67.1.2` wird
`152-67-1-2.sslip.io`. Das löst automatisch auf und funktioniert mit
Let's Encrypt.

---

## Schritt 6 — Einrichten

```bash
sudo mkdir -p /opt/gebimo && sudo chown $USER:$USER /opt/gebimo
cd /opt/gebimo
git clone --depth 1 https://github.com/joelgebert1994-beep/grundstueck-crawler.git
bash grundstueck-crawler/deploy/einrichten.sh
```

Das Skript legt beim ersten Lauf `/opt/gebimo/.env` an und hört auf. Jetzt
ausfüllen:

```bash
nano /opt/gebimo/.env
```

```
DOMAIN=api.gebimo.ch
GEMINI_API_KEY=dein-schluessel
ZUGANGSSCHLUESSEL=<Ausgabe von: openssl rand -base64 32>
```

Den Zugangsschlüssel erzeugst du mit:

```bash
openssl rand -base64 32
```

**Diesen Wert brauchst du in Schritt 8 nochmals** — kopiere ihn dir weg.

Dann das Skript erneut starten:

```bash
bash grundstueck-crawler/deploy/einrichten.sh
```

Es klont beide Repositories, installiert Docker, öffnet die VM-Firewall,
richtet systemd samt täglicher Sicherung ein und baut das Abbild.

> **Warst du vorher nicht in der Docker-Gruppe?** Einmal ab- und wieder
> anmelden, dann das Skript nochmals starten.

---

## Schritt 7 — Prüfen

Das erste Bauen dauert auf ARM 5–10 Minuten.

```bash
# Fortschritt
docker compose -f /opt/gebimo/docker-compose.yml logs -f

# Läuft und ist einsatzbereit?
curl -s https://api.gebimo.ch/health
```

Erwartete Antwort:

```json
{"ok": true, "bereit": true, "umgebung": "produktion",
 "pruefungen": {"llm_schluessel": true, "geometrie": true,
                "llm_bibliothek": true, "datenschicht": true},
 "jobs": {"laufend": 0, "bekannt": 0}}
```

`"bereit": false` sagt dir in `pruefungen` genau, was fehlt.

**Kontingent gegenprüfen — vor dem produktiven Einsatz:**

```bash
bash /opt/gebimo/grundstueck-crawler/deploy/pruefe_kontingent.sh
```

---

## Schritt 8 — Cloudflare Pages verbinden

Cloudflare-Dashboard → **Workers & Pages** → `grundstueck-crawler` →
**Settings** → **Environment variables** → für **Production**:

| Variable | Wert |
|---|---|
| `BACKEND_URL` | `https://api.gebimo.ch` (ohne Schrägstrich am Ende) |
| `BACKEND_SCHLUESSEL` | derselbe Wert wie `ZUGANGSSCHLUESSEL` in `.env` |

**Danach neu veröffentlichen** — Umgebungsvariablen greifen erst beim
nächsten Deployment. Deployments → **Retry deployment**.

---

## Schritt 9 — Der echte Test

`https://grundstueck-crawler.pages.dev` öffnen und eine Adresse analysieren,
zum Beispiel `Rosenweg 4, 5033 Buchs AG`.

| Was | Erwartung |
|---|---|
| Kopfzeile | **keine** Umgebungsanzeige (die erscheint nur ausserhalb der Produktion) |
| Erste Analyse | 1–3 Minuten |
| Dieselbe Adresse nochmals | ~1 Sekunde, mit Hinweis „gespeicherte Analyse vom …" |
| PC ausschalten und erneut öffnen | funktioniert weiterhin |

---

## Betrieb

```bash
# Neue Version einspielen (Datenbank bleibt)
cd /opt/gebimo && git -C grundstueck-crawler pull && git -C Crawler pull
sudo systemctl reload gebimo

# Zustand
sudo systemctl status gebimo
docker compose -f /opt/gebimo/docker-compose.yml ps

# Logs
docker compose -f /opt/gebimo/docker-compose.yml logs -f backend

# Sicherungen (täglich 03:30, 14 Stück werden behalten)
systemctl list-timers gebimo-sicherung.timer
ls -lh /opt/gebimo/sicherungen/

# Von Hand sichern
bash /opt/gebimo/grundstueck-crawler/deploy/sicherung.sh
```

**Wiederherstellen:**

```bash
sudo systemctl stop gebimo
gunzip -c /opt/gebimo/sicherungen/kern-<STEMPEL>.db.gz > /opt/gebimo/daten/kern.db
sudo systemctl start gebimo
```

---

## Wenn etwas nicht geht

| Symptom | Ursache | Abhilfe |
|---|---|---|
| Kein Zertifikat, Caddy-Log zeigt Timeout | Port 80/443 zu | Schritt 3 **und** Skript-Schritt 3 prüfen |
| Kein Zertifikat, DNS stimmt nicht | A-Record fehlt oder Cloudflare-Proxy orange | Wolke auf grau stellen |
| `"bereit": false`, `llm_schluessel: false` | `GEMINI_API_KEY` leer | `.env` prüfen, `sudo systemctl reload gebimo` |
| `"bereit": false`, `datenschicht: false` | `/opt/gebimo/daten` nicht schreibbar | `sudo chown -R $USER /opt/gebimo/daten` |
| Seite zeigt „Diese Seite ist nicht berechtigt" | Schlüssel stimmt nicht | Schritt 8, beide Werte vergleichen, neu veröffentlichen |
| Seite zeigt „Analyse-Server nicht erreichbar" | Dienst aus oder `BACKEND_URL` falsch | `curl https://DOMAIN/health` |
| Analyse bricht nach ~100 s ab | Caddy-Zeitlimit zu klein | `Caddyfile`, `read_timeout` |
| Instanz weg | Idle-Rückforderung | PAYG-Upgrade aus Schritt 1 nachholen |

---

## Was ausdrücklich NICHT eingerichtet wird

| | Warum |
|---|---|
| **Load Balancer** | Caddy macht TLS direkt auf der VM. Der Always-Free-LB wäre unnötig. |
| **Zusätzliches Block Volume** | Die 50-GB-Bootplatte reicht — die Datenbank ist ~3 MB. |
| **Reservierte öffentliche IP** | Die ephemere IP der Instanz ist kostenlos und stabil, solange die Instanz existiert. |
| **Object Storage, Autonomous DB, Monitoring-Zusätze** | Nicht gebraucht. Jeder zusätzliche Dienst ist eine mögliche Kostenquelle. |
| **Zweite Instanz** | Zählt auf dieselben 2 OCPU / 12 GB. |

Grund für die Zurückhaltung: Always Free ist ein Kontingent über die **ganze
Tenancy**, nicht je Instanz. Was hier nicht eingerichtet wird, kann auch
nichts kosten.

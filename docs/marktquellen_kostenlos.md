# Kostenlose Marktdatenquellen — was wir davon wirklich nutzen dürfen

Stand: **19.09.2026**. Kein Vertrag, keine API gekauft, keine Testphase
aktiviert, nichts gescrapt. Wo eine Angabe nicht belegt ist, steht das —
und nicht eine plausible Vermutung.

Die kostenpflichtigen Anbieter bleiben in [marktquellen.md](marktquellen.md)
dokumentiert. Dieses Dokument prüft, was wir **ohne Vertrag** bekommen.

---

## Das Ergebnis in einem Satz

Die Portale sind rechtlich zu, die Statistikämter sind offen — und die
Statistikämter liefern das fachlich **bessere** Produkt: echte
Handänderungen statt Inseratspreise.

---

## Tabelle 1 — alle geprüften Quellen

Legende Datenart: **T** = Transaktion (Handänderung) · **A** = Angebot
(Inserat) · **M** = modellierter Indikator · **I** = Index

| Quelle | Datenart | Objektart | CHF/m² | Miete | Transaktionen | Gemeinde/PLZ | Aktualität | Strukturierter Zugang | Nutzungsrecht intern | Automatisch integrierbar |
|---|---|---|---|---|---|---|---|---|---|---|
| **Kanton ZH, Amt für Statistik** | **T** | EFH, ETW, Wohnbauland | nein, Gesamtpreise | nein | **ja** | **Gemeinde** | bis **2025**, jährlich | **JSON + CSV**, offen | **Freie Nutzung**, kommerziell erlaubt | **JA — geprüft** |
| **Stadt Zürich Open Data** | **T** | nach Zonenart | nein | nein | **ja** | Stadtkreis, Quartier | jährlich | CSV, offen | opendata.swiss | **ja**, noch nicht geprüft |
| **BFS IMPI** | **T → I** | EFH, ETW | nein, Index | nein | als Index | **nur Gemeindetyp**, nicht Gemeinde | quartalsweise | opendata.swiss / data.bfs.admin.ch | offen | ja, aber nur als Index |
| **AkquiseRadar** (eigen) | **A** | Haus, MFH, Bauland | teils | 6 Objekte | nein | Gemeinde | laufend | Direktzugriff | eigener Bestand | **angebunden** |
| **RealAdvisor** | **M** | Wohnung, Haus | **ja** | ja | nein | Gemeinde | monatlich | **keine** | **robots.txt: `Disallow: /`** | **NEIN** |
| **Homegate** | **A/M** | Wohnung, Haus | ja | ja | nein | Gemeinde/Region | laufend | keine öffentliche | Bot-Politik aktiv gepflegt | **NEIN** |
| **ImmoScout24** | **A/M** | Wohnung, Haus | ja | ja | nein | Gemeinde/Region | laufend | keine öffentliche | Bot-Politik aktiv gepflegt | **NEIN** |
| **Comparis** | **A** | Wohnung, EFH | ja | ja | nein | Region | laufend | keine öffentliche | 285 Zeilen Bot-Regeln | **NEIN** |
| Weitere Kantone | **T** vermutlich | vermutlich EFH/ETW/Land | ? | ? | ? | Gemeinde | ? | ? | ? | **zu prüfen** |
| Wüest · IAZI · PriceHubble | T/M | alle | ja | ja | ja | Gemeinde/Mikrolage | quartalsweise | ja, kostenpflichtig | Vertrag | später |

---

## Tabelle 2 — für unseren Crawler sofort nutzbar

Nur was ich **belegen** kann.

| Quelle | Was genau | Segmente | Beleg |
|---|---|---|---|
| **Kanton ZH — Eigentumswohnungen** | Median, q25, q75, Anzahl Verkäufe je Gemeinde und Jahr | Wohnung Bestand | 8160 Datensätze geladen, 2007–2025, 339 Gemeinden mit Median für 2025 |
| **Kanton ZH — Einfamilienhäuser** | dasselbe | EFH | gleiche Datei-Struktur |
| **Kanton ZH — Wohnbauland** | dasselbe, auch als 5-Jahres-Gleitmedian | Bauland | gleiche Struktur |
| **AkquiseRadar** | 1857 Objektangebote | EFH, MFH, Bauland | seit 18.09. produktiv |

Alles andere: **nicht integrieren, nur manuell nachschlagen.**

---

## Die Belege im Einzelnen

### Kanton Zürich — die beste kostenlose Quelle

Heruntergeladen und geprüft:

```
https://daten.statistik.zh.ch/ogd/daten/ressourcen/KTZH_00003158_00006789.json
HTTP 200 · 1'405'693 Bytes · 8160 Datensätze
Felder: geoLevelName, verkaeufe, q25, median, q75, pooling, ref_jahr, zeitraum
```

Eine echte Zeile:

```json
{"geoLevelName": "Affoltern a.A.", "verkaeufe": 82,
 "q25": 870358, "median": 1129500, "q75": 1337750, "ref_jahr": 2025}
```

**Warum das fachlich stark ist:** Grundlage sind die *Handänderungsanzeigen
der Grundbuchämter und Notariate* — jeder Eigentumswechsel. Das sind
**bezahlte Preise, keine verlangten.** Genau die Datenart, die uns beim
AkquiseRadar fehlt und für die IAZI Geld verlangt.

Und die Struktur passt zu unserem Modell: q25/median/q75 ist Spanne plus
Median, `verkaeufe` ist unsere Anzahl Referenzen.

**Was zu beachten ist, und das gehört ins Dossier:**

* **Gesamtpreise, nicht CHF/m².** 1'129'500 CHF ist der Preis der Wohnung,
  nicht ihr Quadratmeterpreis. Ohne Flächenangabe lässt sich daraus kein
  CHF/m² machen — und wir erfinden keine Fläche.
* **Nur Kanton Zürich.** Für Aarau, Buchs (AG) oder Rorschach liefert
  diese Quelle nichts.
* Die letzten drei Jahre und das laufende Jahr sind **provisorisch**
  (rückwirkende Umklassierungen).
* Unter 15 Verkäufen wird aus Datenschutzgründen **kein Preis** gezeigt —
  deshalb 339 von 480 Einträgen mit Median.
* Das Amt kündigt an, die Handänderungsstatistik zu modernisieren und das
  OGD-Angebot **neu zu strukturieren**. Eine Anbindung muss den Ausfall
  einer Ressource überstehen.

**Lizenz:** das Symbol am Datensatz lautet **„Freie Nutzung"** — die
offenste der vier Klassen von opendata.swiss: nicht kommerzielle *und*
kommerzielle Nutzung erlaubt, Quellenangabe empfohlen. Für unser internes
Werkzeug also zulässig, mit Nennung der Quelle.

### BFS IMPI — richtig, aber zu grob

Transaktionspreisindex für EFH und Eigentumswohnungen, quartalsweise.
Aufgeschlossen nach **fünf Gemeindetypen** (städtisch gross/mittel/klein,
ausserhalb Agglomeration, intermediär, ländlich) — **nicht nach konkreter
Gemeinde.**

Damit beantwortet der IMPI die Frage „wie hat sich der Markt entwickelt",
nicht „was kostet ein Haus in Buchs". Als *Entwicklungsreihe* wertvoll, als
Ortswert unbrauchbar. Der opendata.swiss-Eintrag, den ich geöffnet habe,
führt nur HTML und PDF; die maschinenlesbaren Reihen liegen auf
`data.bfs.admin.ch` — **das habe ich nicht verifiziert.**

### RealAdvisor — die Antwort ist nein, und sie ist eindeutig

Sie hatten recht, dass es öffentliche Gemeindeseiten mit Preis/m² gibt. Die
Frage war, ob wir sie automatisiert nutzen dürfen. Die `robots.txt` beantwortet
das selbst:

```
User-agent: *
Allow: /de/
...
Disallow: /de/immobilienpreise-pro-m2/*?
Disallow: /de/bewertung/
Disallow: /de/bewertungsergebnis/
Disallow: /          ← Zeile 101
```

Die Datei endet für alle Agenten auf **`Disallow: /`**. Die Preisseiten sind
zusätzlich in der Parameterform ausdrücklich gesperrt, ebenso Bewertung und
Bewertungsergebnis. Ausdrücklich erlaubt sind nur Bilder, Skripte, Sitemaps
und einzelne Makler-Teilenseiten.

Die Nutzungsbedingungen konnte ich nicht lesen (HTTP 403). Das ändert nichts:
**eine öffentlich abrufbare Zahl ist keine zur Weiterverwendung freigegebene
Zahl**, und eine offizielle Markt-API ist für RealAdvisor nicht belegt — nur
eine Inserats-Integration über CASASOFT.

→ **Nicht integrieren.** Als manuelle Nachschlagequelle dokumentiert.

### Homegate, ImmoScout24, Comparis — gleiche Antwort

Alle drei pflegen eine **aktive Bot-Politik** mit namentlich geführten
Agentenlisten (u. a. ChatGPT-User, Claude-User, PerplexityBot). Comparis
führt 285 Zeilen Regeln. Eine öffentliche Markt-API habe ich bei keinem
gefunden.

Das ist kein Grenzfall: Betreiber, die ihre Bot-Regeln auf dieser
Detailstufe pflegen, haben sich zur automatisierten Nutzung geäussert.

→ **Nicht integrieren.**

*Anmerkung:* Aus diesen Portalen fliessen bereits Daten zu uns — über die
**Suchabo-Mails** in den AkquiseRadar. Das ist ein anderer Weg: der Betreiber
schickt sie uns selbst. Diese Grenze bleibt.

### Weitere Kantone — der nächste Schritt

Wenn Zürich so etwas veröffentlicht, tun es andere Kantone vermutlich auch.
**Ich habe das nicht geprüft** und trage es deshalb nicht als Fund ein,
sondern als Auftrag. Für uns relevant wären zuerst AG, SG, BE, LU und TG.

---

## Was das für die sechs Segmente heisst

| Segment | Kanton ZH | AkquiseRadar | Portale |
|---|---|---|---|
| Wohnung Neubau | nein — Bestand | nein | gesperrt |
| Wohnung Bestand | **ja, Transaktion** | 1 Objekt | gesperrt |
| EFH | **ja, Transaktion** | **1277 Angebote** | gesperrt |
| MFH / Rendite | nein | **154 Angebote** | gesperrt |
| Bauland | **ja, Transaktion** | 96 Angebote | gesperrt |
| Miete | nein | 5 Objekte | gesperrt |

**Neubauwohnung bleibt offen.** Genau die Grösse, die die Wirtschaftlichkeit
braucht, liefert keine kostenlose Quelle — nicht weil wir nicht gesucht
hätten, sondern weil öffentliche Statistik den Bestand erfasst und Portale
Angebote zeigen. Dafür braucht es Wüest oder IAZI.

---

## Wenn mehrere Quellen dasselbe Segment füllen

Ihr Beispiel — RealAdvisor 8'500, Homegate 8'200, ImmoScout 8'350, eigene
8'100–8'700 — ist genau der Fall, in dem eine gemittelte Zahl gefährlich
wäre. Die vier sind **nicht dieselbe Grösse**: drei modellierte Indikatoren
mit je eigener Methodik plus eine Angebotsspanne.

Die Regel, die daraus folgt:

1. Jede Quelle wird **einzeln** ausgewiesen: Wert · Datenart · Stand ·
   geografische Ebene · Objektart.
2. Ein Systemvorschlag entsteht **nur innerhalb einer Datenart**.
   Transaktionen mit Transaktionen, Angebote mit Angeboten.
3. Über Datenarten hinweg gibt es **keine Zahl**, sondern eine
   Gegenüberstellung — und den Hinweis, dass Angebotspreise systematisch
   über Abschlüssen liegen.
4. Keine Quelle heisst „Transaktionspreis", wenn sie einen modellierten
   oder angebotsgestützten Wert liefert.

Für die Datenarten, die wir tatsächlich bekommen können, heisst das
konkret: **Kanton ZH (T) und AkquiseRadar (A) dürfen nicht in einen Median
laufen.** Sie stehen nebeneinander, und der Abstand zwischen ihnen ist
selbst eine Information.

---

## Empfehlung

1. **Kanton ZH anbinden.** Geprüft, offen, kommerziell nutzbar,
   maschinenlesbar, echte Transaktionen, passt auf drei unserer sechs
   Segmente. Aufwand gering, Risiko gering.
2. **Weitere Kantone suchen.** Gleiche Struktur, vervielfacht die Abdeckung.
   Vorher prüfen, nicht annehmen.
3. **BFS IMPI** als Entwicklungsreihe, nicht als Ortswert — und erst nachdem
   der maschinenlesbare Zugang verifiziert ist.
4. **Portale nicht anbinden.** Manuelle Nachschlagequelle.
5. **Neubauwohnung** bleibt die Lücke, die nur eine kommerzielle Quelle
   schliesst. Das ist das Argument für ein Wüest- oder IAZI-Angebot — kein
   Argument, heute etwas zu kaufen.

---

## Quellen

- [opendata.swiss — Immobilienpreise im Kanton Zürich](https://opendata.swiss/de/dataset/immobilienpreise-im-kanton-zurich)
- [opendata.swiss — Nutzungsbedingungen](https://opendata.swiss/de/terms-of-use)
- [Kanton Zürich — Immobilienpreise](https://www.zh.ch/de/planen-bauen/raumplanung/immobilienmarkt/immobilienpreise.html)
- [opendata.swiss — Liegenschaften-Markt Stadt Zürich](https://opendata.swiss/de/dataset/liegenschaften-markt-stadt-zurich-preisreihen-medianpreise-und-anzahl-handanderungen-in-fr-20081)
- [BFS — Wohnimmobilienpreisindex IMPI](https://www.bfs.admin.ch/bfs/de/home/statistiken/preise/erhebungen/impi.html)
- [opendata.swiss — IMPI](https://opendata.swiss/de/dataset/schweizerischer-wohnimmobilienpreisindex-impi)
- [Open Data BFS](https://www.data.bfs.admin.ch/)
- `https://realadvisor.ch/robots.txt` · `https://www.homegate.ch/robots.txt` · `https://www.immoscout24.ch/robots.txt` · `https://www.comparis.ch/robots.txt` (alle am 19.09.2026 abgerufen)

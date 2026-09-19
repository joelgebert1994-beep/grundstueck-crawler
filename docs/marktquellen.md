# Marktdatenquellen — was es gibt und was es kostet

Stand der Recherche: **18.09.2026**. Rein öffentlich zugängliche Angaben,
kein Vertrag, kein Zugang, keine Zugangsdaten. Wo eine Angabe nicht
öffentlich belegt ist, steht das hier — und nicht eine plausible Zahl.

---

## Kurzurteil

| Quelle | API belegt | Transaktionsdaten | Preis öffentlich | Nächster Schritt |
|---|---|---|---|---|
| **AkquiseRadar** (eigen) | — (Direktzugriff) | nein, nur Angebote | kostenlos | **angebunden, siehe unten** |
| **Wüest Partner** | **ja**, Dimensions API | ja im Modul, API unklar | nein | Angebot für MLI + API anfragen |
| **PriceHubble** | **ja**, „standardised API endpoints" | unklar | nein | Demo anfragen, Endpunktliste verlangen |
| **IAZI / CIFI** | nicht belegt | **ja, grösster CH-Bestand** | nein | Lizenzangebot anfragen |
| **RealAdvisor** | nur Inserats-Integration belegt | nein | nein | Partneranfrage, ob Bewertungs-API existiert |

**Keine der vier veröffentlicht einen Preis.** Alle vier verlangen eine
Kontaktaufnahme. Das ist kein Rechercheversäumnis, sondern das
Geschäftsmodell dieses Marktes.

---

## 1 · AkquiseRadar — die einzige heute angebundene Quelle

Eigener Bestand, seit Monaten gesammelt aus Suchabo-Mails von Homegate,
Comparis, ImmoScout24 und Flatfox. Dedupliziert, adressbereinigt, teilweise
amtlich angereichert.

| | |
|---|---|
| Datentyp | **ausschliesslich Angebotspreise** aus Inseraten |
| Verkaufspreise | ja, aber als Objektpreis (Haus, MFH), nicht je m² Neubauwohnung |
| Mietpreise | kaum — 6 Objekte im ganzen Bestand |
| Baulandpreise | ja, 116 Objekte |
| Transaktionsdaten | **nein** — ein Inserat nennt, was verlangt wird |
| Gemeinde-/Mikrolage | nein |
| API | entfällt, Direktzugriff auf `radar.db` |
| Kosten | keine |
| Automatisiert nutzbar | ja, eigener Bestand |

**Angebotspreise sind keine Abschlüsse.** In der Schweiz liegen sie
systematisch höher, und um wie viel, weiss ohne Handänderungsdaten niemand.
Jedes übernommene Objekt trägt deshalb `preisart="angebot"`, und das Dossier
weist es als solches aus. Das ist der Grund, warum eine Transaktionsquelle
(IAZI, Wüest) den grössten fachlichen Zugewinn brächte.

### Gemessen am 18.09.2026, nach der produktiven Anbindung

```
2617 Inserate gelesen
  704  ohne Preis oder Fläche
   56  Dubletten
 1857  als Vergleichsobjekt übernommen   (1114 Gemeinden)
```

Aber **verwertbar je Marktgrösse, schweizweit**:

```
verkauf     1 von 1857     1685 fachlich ungeeignet, 171 ohne Wert
miete       5 von 1857
boden      96 von 1857
```

An einer konkreten Lage, nach Ausweitung auf die PLZ-Region:

| Ort | Verkauf | Miete | Bauland |
|---|---|---|---|
| Aarau | 0 | 0 | 1 |
| Buchs (AG) | 0 | 0 | 1 |
| Rorschach | 0 | 0 | 3 |
| Zürich | 0 | 1 | 1 |

**Nötig für einen Systemvorschlag sind 3.** Die Anbindung liefert also
Infrastruktur und Nachweis, aber noch keine Marktwerte.

Der Grund ist kein Fehler, sondern eine Definitionslücke: 1244 „Haus" und
173 „Mehrfamilienhaus" im Radar sind **Objektangebote**. Die Engine kennt
heute nur `verkauf` im Sinne von *Preis je m² neu gebauter Wohnungen* und
weist Objektangebote korrekt ab — ein MFH-Angebotspreis ist der Preis des
Bestands, nicht der einer Neubauwohnung.

Diese Objekte passen auf **EFH** und **MFH/Rendite** — zwei Grössen, die es
im Modell noch nicht gibt. Siehe „Marktmodell" unten.

---

## 2 · Wüest Partner — Wüest Dimensions

Die einzige der drei kommerziellen Quellen, für die ein API-Zugriff
**namentlich belegt** ist.

| | |
|---|---|
| Produkt | Wüest Dimensions, Modul **Market & Location Information (MLI)** |
| API | **ja.** Belegt für Gebäudeparks CH, **Angebotsdaten**, **Gemeinderatings**, **Mikrolagen** (Wohn- und Geschäftssegment), **Naturgefahren & ESG-Ratings** |
| Angebotsdaten | ja — Vollerhebung seit 1985, rund **600 000 Objekte pro Jahr**, aus Printmedien und den grossen Internetplattformen |
| Transaktionsdaten | im Modul **ja** (CH ab Q1/2005, quartalsweise aktualisiert) — **ob über die API erreichbar, ist nicht belegt** |
| Mietpreise | ja, über die Angebotsdaten (Miet- und Preisniveaus je Gemeinde und Quartier) |
| Baulandpreise | nicht ausdrücklich genannt |
| Vergleichsobjekte | nicht als Einzelobjekte genannt; geliefert werden Niveaus und Ratings |
| Kosten | **nicht öffentlich** |
| Automatisierte interne Nutzung | **muss im Vertrag geklärt werden** — nicht öffentlich belegt |

**Was zu fragen ist:** ob die Transaktionsdaten über dieselbe API laufen,
und ob die Lizenz die Verwendung in einem internen Werkzeug mit
Dossier-Ausgabe deckt.

---

## 3 · PriceHubble

| | |
|---|---|
| Herkunft | Schweizer PropTech |
| API | **ja** — „features are available as standardised API endpoints"; ausdrücklich für tiefe Integration in bestehende Systeme gedacht |
| Bestand | über 4 Mio. Objekte in Europa, rund 11 000 Bewertungen pro Tag |
| Verkaufs-/Mietpreise | Bewertungen und Marktdaten; **welche Felder genau, ist nicht öffentlich** |
| Transaktionsdaten | nicht öffentlich belegt |
| Baulandpreise | nicht öffentlich belegt |
| Gemeinde-/Mikrolage | ja, „property insights" und Lagedaten |
| Kosten | **keine Preisliste.** Individuell nach gebuchten Werkzeugen, Unternehmensgrösse und Nutzungsumfang |
| Automatisierte interne Nutzung | im Produktzuschnitt vorgesehen; Konditionen nicht öffentlich |

**Was zu fragen ist:** die Endpunktliste mit Datenpunkten und
Datenquellen — PriceHubble bietet das auf Anfrage ausdrücklich an.

---

## 4 · IAZI / CIFI

Fachlich die interessanteste Quelle, weil sie als einzige **echte
Handänderungsdaten** in der Breite hat.

| | |
|---|---|
| Transaktionsdaten | **ja — rund 80 % aller CH-Transaktionen** bei EFH und Eigentumswohnungen |
| Modelle | hedonische Preismodelle für EFH, ETW und MFH, **quartalsweise neu kalibriert** auf aktuelle Handänderungen |
| Indizes | SWX IAZI Preisindizes, quartalsweise, zurück bis 1981 |
| Einzelwerkzeug | „HEDOlight", ausschliesslich auf echten Transaktionsdaten |
| API | **nicht öffentlich belegt.** Zugang läuft über Produkte und Lizenzen |
| Kosten | **nicht öffentlich** |
| Nutzerkreis | Hypothekarinstitute, Makler, Private, institutionelle Investoren |

**Was zu fragen ist:** ob es eine maschinelle Schnittstelle gibt oder nur
Weboberfläche und Berichte — das entscheidet, ob die Quelle für dieses
Werkzeug überhaupt in Frage kommt.

---

## 5 · RealAdvisor

| | |
|---|---|
| Rolle | Bewertungsplattform und Portal, „RealAdvisor Pro" als Maklersoftware |
| API | **nur Inserats-Integration belegt** — Übermittlung von Inseraten aus CASAONE, Rückfluss von Anfragen, über CASASOFT |
| Bewertungs-API | **nicht belegt.** Die Bewertung läuft über die eigene Oberfläche |
| Datengrundlage | Algorithmen jährlich aktualisiert, über 25 000 Transaktionen; Regressionsmodell, bezieht die Bauzone ein |
| Transaktionsdaten | nicht als Produkt angeboten |
| Kosten | **nicht öffentlich** |

**Einordnung:** RealAdvisor ist eher Abnehmer als Lieferant von Daten. Für
unseren Zweck die schwächste der vier, solange keine Bewertungs-API belegt
ist.

---

## Was das für das Marktmodell heisst

Der Radar liefert Objektangebote. Die kommerziellen Quellen liefern
Niveaus, Ratings und — bei IAZI — Transaktionen. Ein Modell mit **einer**
Grösse „Verkauf CHF/m²" kann das nicht sauber führen.

Die Grössen, die das Modell führen müsste:

| Grösse | Einheit | Wer liefert sie heute |
|---|---|---|
| Wohnung Neubau | CHF/m² | keine — Radar hat kaum ETW-Angebote |
| Wohnung Bestand | CHF/m² | Radar (ETW-Angebote), Wüest (Angebotsniveaus) |
| EFH | CHF gesamt, ggf. CHF/m² | **Radar: 1244 Haus + 58 EFH** |
| MFH / Rendite | Kaufpreis, Renditekennzahlen | **Radar: 173 MFH** |
| Bauland | CHF/m² Grundstück | **Radar: 116** |
| Miete | CHF/m²/Jahr | Radar: 6; Wüest (Angebotsniveaus) |

Die fett gesetzten Zahlen liegen **heute schon in der Produktionsdatenbank**
und werden nur deshalb nicht genutzt, weil es die Grösse nicht gibt.

**Das ist der grösste Einzelgewinn — und er kostet keinen Vertrag.**

### Umgesetzt am 18.09.2026

Die sechs Segmente stehen. Gemessen am Radar-Bestand, schweizweit:

| Segment | verwertbar | Systemvorschlag | Zweitkennzahl |
|---|---|---|---|
| Wohnung Neubau | 0 | — | — |
| Wohnung Bestand | 1 | — | — |
| **Einfamilienhaus** | **1277** | **1'290'000 CHF** | 7'368 CHF/m² aus 1229 |
| **Renditeliegenschaft** | **154** | **1'500'000 CHF** | 5'000 CHF/m² aus 140 |
| Bauland | 96 | 846 CHF/m² | — |
| Mietzins | 5 | — | — |

An einer konkreten Adresse, nach Ausweitung auf die PLZ-Region:

| Ort | EFH | MFH | Bauland |
|---|---|---|---|
| Aarau | **12** | 0 | 1 |
| Buchs (AG) | **12** | 0 | 1 |
| Rorschach | **28** | **8** | 3 |

Vorher: 0 verwertbare Referenzen in jedem Segment an jedem dieser Orte.

**Zwei Entscheidungen, die dabei getroffen wurden:**

1. `OBJEKTART_HAUS` („Haus", Art im Inserat unbestimmt) zählt zum
   Einfamilienhaus. Das ist eine Entscheidung, keine Messung: 1245 von 1380
   Häusern tragen genau dieses Wort, sie liegenzulassen hiesse 90 % des
   Segments wegzuwerfen. Die Auswertung weist aus, wie viele aus welcher
   Gruppe kommen.

2. **Ein Wohnungsinserat zählt nicht mehr als Neubaureferenz.** Bis hierher
   galt es als solche — zu grosszügig, und der eigene Kommentar des Moduls
   sagt warum: ein Angebot beantwortet „was kostet dieser Bestand", nicht
   „für wie viel lassen sich hier neu gebaute Wohnungen verkaufen". Seit es
   das Segment Wohnung Bestand gibt, hat es ein eigenes Fach. Verkauf sinkt
   damit von 1 auf 0 verwertbare Referenzen schweizweit — ein Wert, der
   ohnehin keine Aussage trug.

**Keine Rendite für MFH.** Von 173 MFH-Inseraten führen drei einen
Mietzins. Eine Bruttorendite aus drei Beobachtungen wäre eine Zahl ohne
Grundlage. Die belastbare Zweitkennzahl ist der Preis je m² Wohnfläche,
und die steht da.

### Reihenfolge, die sich daraus ergibt

1. Grössen **EFH** und **MFH/Rendite** einführen → macht rund 1475 bereits
   vorhandene Referenzen nutzbar.
2. **Wüest Dimensions MLI + API** anfragen → Angebotsniveaus und
   Gemeinderatings flächendeckend, füllt „Wohnung Bestand" und „Miete".
3. **IAZI** anfragen → Transaktionsdaten, das einzige Mittel gegen den
   systematischen Aufschlag der Angebotspreise.
4. PriceHubble als Alternative zu 2, RealAdvisor vorerst zurückstellen.

### Was dabei nie passieren darf

Kein Scraping, kein Umgehen von Login, Captcha oder Zugriffsschutz, keine
nicht autorisierte Datenübernahme. Jede kommerzielle Quelle kommt über
einen Vertrag herein oder gar nicht.

Und: **mehrere Quellen dürfen nie zu einer Zahl verschmelzen.** Jede Quelle
wird mit Wert, Bandbreite, Stand und Datentyp einzeln ausgewiesen; ein
Systemvorschlag darüber ist erlaubt, ein „Marktpreis CHF 8'600/m²" ohne
Herkunft nicht.

---

## Quellen dieser Recherche

- [Wüest Partner — Angebotsdaten](https://www.wuestpartner.com/ch-de/expertise/daten/angebotsdaten/)
- [Wüest Dimensions — Market & Location Information](https://www.wuestpartner.com/de-de/services-produkte/digitale-loesungen-fuer-immobilien/wuest-dimensions/market-location-information/)
- [Wüest Partner — Markt- und Standortinformationen](https://www.wuestpartner.com/ch-de/expertise/daten/markt-standortinformationen/)
- [PriceHubble — Real estate API](https://www.pricehubble.com/use-cases/real-estate-api)
- [PriceHubble — Lösungen](https://www.pricehubble.com/at/)
- [PriceHubble im Test 2026 — Kosten](https://makler.immo/allgemein/pricehubble/)
- [IAZI/CIFI — datenbasierte Immobilienbewertung](https://www.iazicifi.ch/en/iazi-vertrauen-in-datenbasierte-immobilienbewertung-2/)
- [IAZI AG — Real Estate Online](https://online.iazi.ch/)
- [RealAdvisor Pro — Bewertungssoftware](https://realadvisor.ch/de/pro/immobilien-bewertungssoftware)
- [CASASOFT — RealAdvisor-Integration](https://casasoft.ch/integration/realadvisor/)

# Grundstücksbezogene Fragen – vorbereitet, nicht gebaut

Stand 01.10.2026. LandScout zeigt, dass Nutzer direkt fragen wollen:
„Was kann ich hier bauen?“, „Wie hoch darf ich bauen?“, „Kann ich einen
Keller bauen?“. Ein frei antwortender KI-Chat würde hier genau das tun, was
das Zielbild verbietet: Zahlen erfinden und Herleitungen umgehen. Deshalb
gibt es **noch keinen Chat**. Diese Notiz hält fest, worauf ein späterer
Fragenbereich aufsetzen muss.

## Grundsatz

Ein Fragenbereich ist eine **zweite Ansicht derselben Analyse**, keine zweite
Engine. Er beantwortet nur, was im Analyseergebnis zum aktuellen EGRID
belegt ist, und zitiert dieselben Belege wie das Dossier. Was dort „nicht
bestimmbar“ ist, ist auch im Fragenbereich „nicht bestimmbar“.

## Was bereits vorliegt (ein Ergebnisobjekt je Analyse)

| Frage braucht | liegt im Ergebnis unter | Beleg |
|---|---|---|
| welches Grundstück | `modul1_geodaten.kataster` (EGRID, Parzelle), `geocoding.feature_id` | amtliche Vermessung, GWR-Kennung |
| was gilt hier | `zonen_zuordnung`, `modul1_geodaten.nutzungsklassifikation` | Nutzungsplanung, ÖREB |
| BZO-Werte | `zonen_zuordnung.zone.*` mit `wert`, `artikel_referenz`, `zitat`, `confidence`, `quelle_dokument` | Reglement-PDF (Artikel und Zitat) |
| wie viel | `g1_ergebnis`, Szenarien, `potenzialKurz` im Frontend | Geometrie und SIA 416 |
| Einschränkungen | `restriktionsgeometrie` (mit `fehler`), `oereb.umweltrisiken` (mit Status und Stand) | geodienste.ch, ÖREB-Kataster |
| Bestand und Energie | `gwr` (Heizung, Warmwasser), `energie` (Solar-Modell und Register) | GWR, BFE |
| Herkunft je Wert | `quellen[]` (Quellenobjekte aus `quellen.py`) | Endpunkt und Abrufdatum |

## Regeln für eine spätere Umsetzung

1. **Gebunden an EGRID und Analyse-Stand.** Wechselt die Adresse, beginnt der
   Fragenbereich neu (dieselbe Regel wie beim Variantenschutz).
2. **Antwort = Wert + Wertetyp + Beleg.** Dasselbe Vokabular wie im Dossier:
   Vorgabe BZO, laut GWR, gemessen, abgeleitet, Modell, nicht bestimmbar.
3. **Keine neue Rechnung.** Eine Frage, die das Ergebnis nicht beantwortet
   (z. B. „Keller?“ ohne Untergeschoss-Regel im Reglement), wird mit „nicht
   bestimmbar“ beantwortet, mit dem Verweis auf den Artikel, der zu prüfen ist.
4. **Unbekannt ist nicht „nein“.** Nicht abgefragte Themen (Naturgefahren,
   Denkmalschutz, Lärmbelastung) werden als solche benannt.
5. **Kosten.** Ein Sprachmodell nur mit dem kostenlosen Kontingent und nur
   über die bestehende Modul-2-Anbindung, keine zweite Modellanbindung.

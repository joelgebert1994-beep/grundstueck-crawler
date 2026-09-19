"""Zusicherungen an die Oberflaeche -- dist/index.html.

Was dieser Test PRUEFT: die Bauvertraege, die sich beim Umbau still
brechen lassen und die man im Browser erst bemerkt, wenn etwas fehlt oder
unsichtbar wird.

  1. Die Reiter und ihre Reihenfolge.
  2. Die Karte wohnt ausserhalb des Dossiers und wird vor jedem
     Neuschreiben dorthin zurueckgeholt.
  3. Jede benutzte CSS-Variable ist auch definiert.
  4. Ein einziger Ort fuer die maximale Inhaltsbreite.
  5. Keine Reste der alten Abschnittsnummerierung.
  6. Markt: drei Ebenen, Sicherheitsgrad sichtbar, keine Platzhalterwerte.
  7. Wirtschaftlichkeit: fuenf Kernkennzahlen, Annahmen vor dem Ergebnis.
  8. Daten & Quellen: Herkunft gebuendelt, Codes uebersetzt, Rohwert daneben.
  9. Ein Teilfehler sperrt keinen Reiter -- Markt und Wirtschaftlichkeit
     zeigen auch ohne Reglementsauswertung, was feststeht.

Was er NICHT pruefen kann: ob ein konkreter Wert durch die Anzeigeschicht
laeuft. Das haengt an den Daten und ist im Browser zu pruefen -- dieser
Test ersetzt den Blick auf die echte Analyse nicht.
"""
from __future__ import annotations

import pathlib
import re
import sys

WURZEL = pathlib.Path(__file__).resolve().parents[1]
SEITE = WURZEL / "dist" / "index.html"

_ok = 0
_fehler: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    """Eine Zusicherung. Das Format "[OK  ] ..." zaehlt tests/alle.py mit."""
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)


def lies() -> str:
    return SEITE.read_text(encoding="utf-8")


def test_reiter(s: str) -> None:
    """Acht Reiter, in dieser Reihenfolge -- die Navigation des Dossiers.

    "3D-Entwurf" steht nach "Potenzial": erst verstehen, was zulaessig
    ist, dann ausprobieren, was daraus entstehen koennte.
    """
    block = s[s.index("var REITER = ["):]
    block = block[: block.index("];")]
    namen = re.findall(r'\["([a-z]+)", "', block)
    erwartet = ["uebersicht", "baurecht", "karte", "potenzial", "entwurf",
                "markt", "wirtschaft", "quellen"]
    pruefe(namen == erwartet, f"Reiterfolge {erwartet} (gefunden: {namen})")

    # Jede in REITER genannte Sektion muss auch gebaut werden, sonst
    # zeigt der Reiter auf nichts.
    ids = re.findall(r'"(sec-[a-z0-9]+)"', block)
    for sid in ids:
        pruefe(f'id="{sid}"' in s, f"Reiter {sid} wird auch gebaut")


def test_karte_ausserhalb_des_dossiers(s: str) -> None:
    """Leaflet haengt an seinem Container.

    Liegt #map innerhalb von #dossier-inner, loescht das naechste
    innerHTML die Karte -- sie kommt dann erst mit einem Neuladen der
    Seite zurueck. Deshalb wohnt sie in #kartenheim und wird nur fuer die
    Dauer des Kartenreiters auf die Buehne gereicht.
    """
    pruefe('id="kartenheim"' in s, "Der Kartenparkplatz #kartenheim ist vorhanden")
    koerper = s[s.index("<body>"):s.index("</body>")]
    heim = koerper.index('id="kartenheim"')
    dossier = koerper.index('id="dossier-inner"')
    karte = koerper.index('<div id="map">')
    pruefe(heim < karte < dossier,
           "#map liegt im Markup in #kartenheim, ausserhalb von #dossier-inner")

    # Vor jedem Neuschreiben des Dossiers muss die Karte geparkt werden.
    schreiber = [m.start() for m in re.finditer(r"inner\.innerHTML =", s)]
    pruefe(len(schreiber) >= 4, f"{len(schreiber)} Schreibstellen auf das Dossier gefunden")
    for pos in schreiber:
        davor = s[max(0, pos - 120):pos]
        pruefe("parkeKarte();" in davor,
               "Vor diesem inner.innerHTML steht parkeKarte() -- "
               "die Karte ueberlebt das Neuschreiben")


def test_css_variablen(s: str) -> None:
    """Jede benutzte Variable muss auch definiert sein.

    Eine undefinierte Variable laesst die ganze Eigenschaft ausfallen:
    "background: var(--bg)" ergibt dann gar keinen Hintergrund. Auf
    weissem Grund faellt das nicht auf -- auf farbigem schon. Genau so
    lagen --bg und --bg-2 vierzehnmal im Stylesheet, ohne je definiert
    zu sein.
    """
    stil = s[s.index("<style>"):s.index("</style>")]
    # Mehrere Definitionen duerfen auf einer Zeile stehen -- deshalb am
    # Trennzeichen ansetzen und nicht am Zeilenanfang.
    definiert = set(re.findall(r"(?:^|[;{])\s*(--[a-z0-9-]+)\s*:", stil, re.M))
    benutzt = set(re.findall(r"var\((--[a-z0-9-]+)", stil))
    fehlend = sorted(benutzt - definiert)
    pruefe(not fehlend, f"Jede benutzte CSS-Variable ist definiert (offen: {fehlend})")


def test_inhaltsbreite(s: str) -> None:
    """Die Bahn hat genau einen Ort, und der liegt im vernuenftigen Bereich."""
    stil = s[s.index("<style>"):s.index("</style>")]
    treffer = re.findall(r"\.app\.nurdossier[^{]*\{[^}]*max-width:\s*(\d+)px", stil)
    pruefe(len(treffer) == 1, f"Genau eine Regel setzt die Bahnbreite (gefunden: {len(treffer)})")
    if treffer:
        breite = int(treffer[0])
        # Obergrenze 1800: die Bahn traegt Karte, Kennzahlen und Tabellen,
        # die mit Breite besser werden. Der Fliesstext DARIN bleibt auf
        # Lesebreite begrenzt (.atext/.ahinweis/.note in ch), sonst haette
        # eine breite Bahn unlesbare Absaetze zur Folge.
        pruefe(1100 <= breite <= 1800,
               f"Bahnbreite {breite}px liegt im Bereich 1100-1800px")
    # Ohne Kommentare: ein Kommentar, der eine Klasse ERWAEHNT, ist keine
    # Regel -- sonst prueft der Test die Prosa statt das Stylesheet.
    ohne = re.sub(r"/\*.*?\*/", "", stil, flags=re.S)
    for klasse in (".atext", ".ahinweis", ".note"):
        regel = re.search(r"^" + re.escape(klasse) + r"\s*\{[^}]*\}", ohne, flags=re.M)
        pruefe(bool(regel) and "ch" in regel.group(0),
               f"{klasse} begrenzt die Zeilenlaenge in Zeichen, nicht in Pixel")


def test_keine_abschnittsnummern(s: str) -> None:
    """Die Nummerierung 01/02/... war mit den Reitern bedeutungslos geworden."""
    pruefe('<span class="num">' not in s,
           "Keine Reste der alten Abschnittsnummerierung im Markup")
    pruefe("sec-entwicklung" not in s,
           "sec-entwicklung wird nirgends mehr referenziert -- die "
           "Entwicklungsdokumentation gehoert nicht in die Oberflaeche")


def test_bandbreiten_auskunft(s: str) -> None:
    """Die Spanne ist die Hauptaussage -- und sie muss belegt dastehen.

    Vier Vertraege, die sich beim naechsten Umbau still brechen lassen:

    1. Die Anordnungen stehen DIREKT unter dem Urteil, nicht unter
       "Herleitung". Sie sind der Beleg fuer die Spanne; unten versteckt
       steht die Hauptaussage unbelegt da.
    2. Uebersicht und Potenzialreiter erklaeren die Null aus DERSELBEN
       Funktion. Zwei getrennte Texte laufen garantiert auseinander --
       genau das ist an Bahnhofstrasse 4 schon einmal passiert.
    3. Die entarteten Anordnungen stecken in der gemeinsamen Auskunft
       (potenzialKurz), nicht in einer der beiden Ansichten.
    4. Beide Raender der Spanne werden ausgegeben. Eine einzelne Zahl aus
       Minimum oder Maximum waere eine Annahme ueber einen Entwurf, den es
       noch nicht gibt.
    """
    # 1. Genau eine Fundstelle von "anordnungsTabelle(g1)" -- die
    #    Funktionsdefinition. Der alte Aufruf in g1Herleitung ist weg.
    pruefe(s.count("anordnungsTabelle(g1)") == 1,
           "anordnungsTabelle steht nicht mehr in der Herleitung "
           f"(gefunden: {s.count('anordnungsTabelle(g1)')} Vorkommen von "
           "'anordnungsTabelle(g1)', erwartet 1 = nur die Definition)")
    pruefe("anordnungsTabelle(erg.g1_ergebnis)" in s,
           "anordnungsTabelle wird im Potenzialreiter direkt unter dem Urteil gerufen")
    urteil_pos = s.find("potenzialUrteil(erg) +")
    tabelle_pos = s.find("anordnungsTabelle(erg.g1_ergebnis)")
    pruefe(0 < urteil_pos < tabelle_pos,
           "die Anordnungen stehen NACH dem Urteil, nicht davor")

    # 2. Eine Quelle, zwei Laengen.
    pruefe("function nullErklaerung(" in s,
           "nullErklaerung ist die gemeinsame Quelle fuer die Null am unteren Rand")
    pruefe('nullErklaerung(kurz, "kurz")' in s,
           "die Uebersicht benutzt nullErklaerung")
    pruefe('nullErklaerung(kurz, "lang")' in s,
           "der Potenzialreiter benutzt nullErklaerung")

    # 3. Der Befund gehoert in die gemeinsame Auskunft.
    kurz_block = s[s.index("function potenzialKurz("):]
    kurz_block = kurz_block[: kurz_block.index("\nfunction ", 10)]
    for feld in ("tote:", "bebaubar:"):
        pruefe(feld in kurz_block,
               f"potenzialKurz liefert {feld} -- beide Ansichten lesen denselben Befund")
    pruefe("function istEntartet(" in s,
           "istEntartet ist eine eigene Funktion, nicht zweimal abgeschrieben")

    # 3b. Die Anordnungen sind Balken, keine Tabelle. Eine Spanne ist ein
    #     Groessenverhaeltnis -- als Zahlenspalte muss man es lesen, als
    #     Laengen sieht man es. Und eine Anordnung, die nichts ergibt, ist
    #     eine leere Bahn statt einer "0.0" zwischen anderen Zahlen.
    tab = s[s.index("function anordnungsTabelle("):]
    tab = tab[: tab.index("\nfunction ", 10)]
    pruefe('class="anordbahn"' in tab and 'class="anordfuell' in tab,
           "die Anordnungen werden als Balken gezeichnet")
    pruefe("<table" not in tab,
           "die Anordnungen stehen NICHT mehr als Tabelle")
    pruefe("maxWert" in tab,
           "der Massstab ist der groesste Wert im Feld, nicht die Spanne -- "
           "sonst haette die untere Grenze immer die Laenge null")

    # 4. Beide Raender, keine kuenstliche Einzelzahl.
    pruefe("fmt(spanne[0], 0)" in s and "fmt(spanne[1], 0)" in s,
           "der Potenzialreiter gibt beide Raender der Spanne aus")
    pruefe("fmt(kurz.spanne[0], 0)" in s and "fmt(kurz.spanne[1], 0)" in s,
           "die Uebersicht gibt beide Raender der Spanne aus")


def test_markt_und_wirtschaft_getrennt(s: str) -> None:
    """Baurecht, Markt und Wirtschaftlichkeit sind drei verschiedene Dinge.

    Die Reihenfolge ist die Reihenfolge der Fragen, die ein Makler hat:
    Was darf ich bauen -> was koennte daraus entstehen -> was ist am Markt
    plausibel -> lohnt es sich. Wirtschaftlichkeit steht deshalb NACH
    Markt: sie rechnet mit den Annahmen, die dort gesetzt werden.
    """
    # 1. Die Wirtschaftlichkeit hat einen eigenen Reiter und haengt nicht
    #    mehr im Potenzialreiter -- dort sah eine Annahme aus wie ein
    #    amtlicher Befund.
    block = s[s.index("var REITER = ["):]
    block = block[: block.index("];")]
    potenzial = block[block.index('["potenzial"'):]
    potenzial = potenzial[: potenzial.index("]]") + 2]
    pruefe("sec-wirtschaft" not in potenzial,
           "sec-wirtschaft haengt nicht mehr im Potenzialreiter")
    pruefe('["wirtschaft", "Wirtschaftlichkeit", ["sec-wirtschaft"]]' in block,
           "Wirtschaftlichkeit ist ein eigener Reiter")
    pruefe(block.index('["markt"') < block.index('["wirtschaft"'),
           "der Reiter Wirtschaftlichkeit steht NACH dem Reiter Markt")

    # 2. Auch im Dokument steht der Markt vor der Wirtschaftlichkeit --
    #    sonst springt "zum naechsten Abschnitt" rueckwaerts.
    pruefe(s.index("secMarkt(erg)") < s.index("secWirtschaft(erg)"),
           "secMarkt wird vor secWirtschaft gebaut")

    # 3. Die Annahmen stehen im Reiter Markt, gerechnet wird im Reiter
    #    Wirtschaftlichkeit. Ein Selektor auf "#sec-wirtschaft" trifft sie
    #    nicht -- ohne diese Erweiterung loest eine geaenderte Annahme
    #    keine Neuberechnung aus.
    pruefe('"#w-markt input, #w-markt select"' in s,
           "die Marktannahmen sind an die Neuberechnung verdrahtet")
    pruefe("#sec-markt input" not in s,
           "NUR die Annahmen sind verdrahtet, nicht die Erfassung der "
           "Vergleichsobjekte -- die aendern die Rechnung nicht")

    # 4. Eine Marge ohne ihre Grundlage ist keine Auskunft. Der
    #    Wirtschaftsreiter wiederholt deshalb die Annahmen mit Herkunft.
    pruefe("function wAnnahmenStreifen(" in s,
           "der Wirtschaftsreiter zeigt, mit welchen Marktannahmen gerechnet wurde")
    pruefe('<div id="w-annahmen">' in s and 'setze("w-annahmen"' in s,
           "der Annahmenstreifen wird bei jeder Neuberechnung mitgezogen")
    ann = s[s.index("function wAnnahmenStreifen("):]
    ann = ann[: ann.index("\nfunction ", 10)]
    pruefe("HERKUNFT_KURZ" in ann,
           "jeder Wert im Annahmenstreifen traegt seine Herkunft")
    pruefe("keine amtlichen Werte" in ann,
           "der Streifen sagt ausdruecklich, dass es Annahmen sind und "
           "keine amtlichen Werte")
    pruefe('reiterLink("markt"' in ann,
           "vom Ergebnis fuehrt ein Weg zurueck zu den Annahmen")


def test_uebersicht(s: str) -> None:
    """Die Uebersicht beantwortet EINE Frage: lohnt sich ein zweiter Blick?

    Vier Zahlen, eine Karte, drei kurze Antworten, ein Lageprofil. Was das
    nicht beantwortet, steht in einem anderen Reiter -- besonders die
    technischen Kennungen, die dort niemandem helfen.
    """
    block = s[s.index("function secUebersicht("):]
    block = block[: block.index("\nfunction ", 10)]
    # Geprueft wird der CODE, nicht die Kommentare. Ein Kommentar, der
    # erklaert, warum etwas NICHT hierhergehoert, darf nicht als Verstoss
    # gegen genau diese Regel zaehlen.
    ohne_kommentar = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    ohne_kommentar = re.sub(r"^\s*//.*$", "", ohne_kommentar, flags=re.M)

    # 1. Genau vier Kernzahlen, in dieser Reihenfolge.
    namen = re.findall(r'kz\("([^"]+)"', block)
    erwartet = ["Grundstück", "Ausnützungsziffer", "Bestand", "Potenzial Neubau"]
    pruefe(namen == erwartet,
           f"vier Kernzahlen in der Reihenfolge {erwartet} (gefunden: {namen})")
    pruefe(block.count(", true)") >= 1 and "haupt" in s,
           "die Potenzialkachel ist als Hauptkachel ausgezeichnet")

    # 2. Der Potenzialwert kommt aus der GEMEINSAMEN Auskunft, nicht aus
    #    einem zweiten Zugriff auf das G1-Ergebnis.
    pruefe("potenzialKurz(erg)" in block,
           "die Uebersicht liest den Potenzialwert aus potenzialKurz")
    for feld in ("kurz.wert", "kurz.spanne"):
        pruefe(feld in block, f"die Potenzialkachel benutzt {feld}")
    pruefe("g1.ergebnis.geschossflaeche" not in block
           and "geschossflaeche_m2" not in block,
           "die Uebersicht greift NICHT direkt auf die Geschossflaeche im "
           "G1-Ergebnis zu -- das waere eine zweite Quelle")

    # 3. Die Karte hat eine zweite Buehne, und zeigeReiter kennt sie. Eine
    #    zweite Leaflet-Instanz waeren zwei Wahrheiten ueber eine Parzelle.
    pruefe('id="uebuehne"' in block, "die Uebersicht hat eine Kartenbuehne")
    pruefe('"uebersicht" ? "uebuehne"' in s,
           "zeigeReiter schiebt die Karte auf die Uebersichtsbuehne")
    pruefe(s.count('id="map"') == 1,
           f"genau EIN Kartencontainer im Dokument (gefunden: {s.count('id=' + chr(34) + 'map' + chr(34))})")
    pruefe("kartenBuehneAktuell" in s,
           "der Rahmen wird nur beim Buehnenwechsel neu gesetzt, nicht bei "
           "jedem Reiterwechsel -- sonst ist die Zoomstellung jedes Mal weg")

    # 4. Keine technischen Kennungen. Sie beantworten keine Frage, die
    #    jemand beim Oeffnen eines Dossiers stellt.
    for begriff in ("EGRID", "LV95", "BFS", "EGID", "Fingerabdruck",
                    "Flaechenherkunft", "swissALTI3D"):
        pruefe(begriff not in ohne_kommentar,
               f"'{begriff}' steht NICHT in der Uebersicht (gehoert nach Daten & Quellen)")

    # 5. Lage-Kurzprofil: das ist Maklerwissen, kein Geodatenkram.
    for feld in ("oev_naechste_haltestelle", "supermarkt_naechster",
                 "schule_naechste", "aspect", "slope_deg"):
        pruefe(feld in block, f"das Lageprofil zeigt {feld}")
    pruefe("konfidenz" not in block and "t.quelle" not in block,
           "die Herkunftsangaben (Radon-Rohwert, Topografie-Quelle) bleiben "
           "in Daten & Quellen")

    # 6. Einschraenkungen als Chips, nicht als Tabelle.
    pruefe('class="chips"' in block, "die Einschraenkungen stehen als Chips")


def test_markt_drei_ebenen(s: str) -> None:
    """Markt zeigt drei Arten von Wissen, und sie duerfen nie verschmelzen.

    1 extern beobachtet -- 2 selbst erfasst -- 3 selbst angenommen.
    Gerechnet wird am Ende nur mit der dritten. Wer die Nummerierung
    aufbricht oder eine Ebene weglaesst, verwischt genau die Grenze, die
    dieser Reiter ziehen soll.
    """
    block = s[s.index("function secMarkt("):]
    block = block[: block.index("\nfunction ", 10)]

    # 1. Drei Ebenen in dieser Reihenfolge, gebaut mit demselben Kopf wie
    #    die Ebenen im Potenzialreiter.
    koepfe = re.findall(r"ebeneKopf\((\d), \"([^\"]+)\"", block)
    pruefe([n for n, _ in koepfe] == ["1", "3"],
           f"secMarkt baut Ebene 1 und 3 selbst (gefunden: {[n for n, _ in koepfe]})")
    pruefe('id="mkt-verwaltung"' in block,
           "Ebene 2 haengt an mkt-verwaltung und wird aus den Marktdaten gezeichnet")

    # 2. Ebene 2 traegt IMMER einen Kopf -- auch solange /api/marktdaten
    #    laeuft. Ohne ihn stand im Reiter "1 ... 3" mit einer Luecke.
    pruefe("function mktEbeneKopf(" in s and "function mktEbeneLeer(" in s,
           "Ebene 2 hat einen Kopf, der auch vor dem Laden schon steht")
    pruefe("mktEbeneLeer()" in block,
           "secMarkt setzt den Platzhalter fuer Ebene 2")
    zeichne = s[s.index("function mktZeichne("):]
    zeichne = zeichne[: zeichne.index("\nfunction ", 10)]
    pruefe("mktEbeneKopf()" in zeichne,
           "mktZeichne setzt denselben Kopf -- die Nummer 2 kann nicht verschwinden")
    pruefe('ebeneKopf(2, "Eigene Vergleichsobjekte"' in s,
           "Ebene 2 traegt die Nummer 2")

    # 3. Externe Marktdaten: es gibt keine angebundene Quelle, und das
    #    steht da. Ein Platzhalterwert waere hier eine erfundene Zahl.
    extern = s[s.index("function marktExternBlock("):]
    extern = extern[: extern.index("\nfunction ", 10)]
    # Geprueft wird der CODE. Ein Kommentar, der eine verbotene
    # Darstellung ZITIERT, um zu erklaeren warum sie verboten ist,
    # darf nicht als Verstoss gegen genau diese Regel zaehlen.
    extern = re.sub(r"/\*.*?\*/", "", extern, flags=re.S)
    extern = re.sub(r"^\s*//.*$", "", extern, flags=re.M)
    pruefe("keine Quelle angebunden" in extern,
           "Ebene 1 sagt ausdruecklich, dass keine externe Quelle angebunden ist")
    pruefe("eleit ruhig" in extern,
           "der fehlende Anschluss wird ruhig gezeigt, nicht als Warnung")
    pruefe(not re.search(r"\d['’]?\d{3}", extern),
           "Ebene 1 zeigt KEINE Beispielzahl -- ein Platzhalterwert waere "
           "eine erfundene Marktauskunft")


def test_markt_sicherheitsgrad(s: str) -> None:
    """Der Sicherheitsgrad ist eine Stufe, keine Messung -- und sichtbar."""
    pruefe("function sicherheitsMeter(" in s,
           "der Sicherheitsgrad wird als Balken gezeigt, nicht nur als Wort")
    meter = s[s.index("function sicherheitsMeter("):]
    meter = meter[: meter.index("\nfunction ", 10)]
    pruefe("%" not in meter,
           "der Sicherheitsgrad wird NICHT als Prozentzahl ausgegeben -- die "
           "Einstufung hat diese Genauigkeit nicht")
    for stufe in ("hoch", "mittel", "gering", "keine_daten"):
        pruefe(stufe in s[s.index("var SGRAD_TEXT"): s.index("var SGRAD_KLASSE")],
               f"die Stufe {stufe} hat einen deutschen Namen")

    groesse = s[s.index("function marktGroesse("):]
    groesse = groesse[: groesse.index("\nfunction ", 10)]
    pruefe("sicherheitsMeter(sicher)" in groesse,
           "jede Marktgroesse zeigt ihren Sicherheitsgrad")
    # Die Begruendung der Engine IST die Erklaerung der Stufe. Sie in eine
    # Klappe zu legen hiesse, die Einstufung ohne Grund zu behaupten.
    pruefe("mgrgruende" in groesse and groesse.index("mgrgruende") < groesse.index("<details"),
           "die Begruendung der Engine steht VOR der Klappe, nicht darin")


def test_markt_keine_platzhalter(s: str) -> None:
    """Fehlt ein Wert, steht das da -- nie eine Zahl an seiner Stelle."""
    groesse = s[s.index("function marktGroesse("):]
    groesse = groesse[: groesse.index("\nfunction ", 10)]
    ohne_kommentar = re.sub(r"/\*.*?\*/", "", groesse, flags=re.S)
    ohne_kommentar = re.sub(r"^\s*//.*$", "", ohne_kommentar, flags=re.M)

    pruefe("noch nicht gesetzt" in ohne_kommentar,
           "ein nicht gesetzter Wert heisst 'noch nicht gesetzt'")
    pruefe("nicht ableitbar" not in ohne_kommentar or "systemvorschlag" in ohne_kommentar,
           "ein fehlender Systemvorschlag wird als solcher gezeigt")
    # Keine Zifferngruppe im Quelltext der Marktgroesse: jede angezeigte
    # Zahl muss durch chf() aus der Serverantwort kommen.
    pruefe(not re.search(r"\d['’]?\d{3}", ohne_kommentar),
           "im Marktblock steht keine einzige eingebaute Zahl")

    # Angebotspreise sind keine Abschluesse und muessen so heissen.
    pruefe("Angebotspreis" in ohne_kommentar and "kein beurkundeter Abschluss" in ohne_kommentar,
           "Angebotspreise sind ausdruecklich als Angebotspreise gekennzeichnet")
    # Ausgeschlossene Objekte: sichtbar, aber aufgeklappt.
    # Geprueft wird die Schachtelung im ERZEUGTEN Markup, nicht die
    # Reihenfolge im Quelltext: ausHtml wird vorher gebaut und erst in
    # der Klappe eingesetzt.
    klappe = ohne_kommentar[ohne_kommentar.index("<details"):
                            ohne_kommentar.index("</details>")]
    pruefe("Nicht einbezogen" in ohne_kommentar and "ausHtml" in klappe,
           "die ausgeschlossenen Vergleichsobjekte stehen in der Klappe")

    zeichne = s[s.index("function mktZeichne("):]
    zeichne = zeichne[: zeichne.index("\nfunction ", 10)]
    pruefe('kz("Angebotspreise"' in zeichne,
           "Ebene 2 beziffert, wie viele Referenzen Angebotspreise sind")
    pruefe('kz("Verwertbar"' in zeichne and "mindestens" in zeichne,
           "Ebene 2 zeigt, wie viele Referenzen zaehlen und wie viele noetig sind")


def test_markt_eingabefelder_bleiben(s: str) -> None:
    """Die sechs Eingabefelder muessen IMMER im Dokument stehen.

    wSammleEingaben liest sie ueber getElementById. Fehlt eines, liest es
    null -- und schreibt damit eine gesetzte Annahme still auf null
    zurueck. Genau das passierte, als die Karte einer Marktgroesse ohne
    Referenz gar nicht mehr gezeichnet wurde: der Bodenpreis verschwand
    mitsamt seinem Feld, und die naechste Neuberechnung rechnete ohne ihn.
    """
    groesse = s[s.index("function marktGroesse("):]
    groesse = groesse[: groesse.index("\nfunction ", 10)]
    pruefe("if (!mw) return" not in groesse,
           "marktGroesse steigt NICHT aus, wenn keine Referenz vorliegt")
    pruefe("mw = mw || {" in groesse,
           "ohne Referenz wird ein leerer Wert gebaut, keine leere Karte")

    block = s[s.index("function marktBlock("):]
    block = block[: block.index("\nfunction ", 10)]
    for feld in ("w-verkauf", "w-miete", "w-boden"):
        pruefe(f'"{feld}"' in block, f"{feld} wird in jedem Fall gezeichnet")
    for feld in ('id="w-basis"', 'id="w-land"', 'id="w-zielmarge"'):
        pruefe(feld in block, f"{feld} steht bei den Rechnungsgrundlagen")

    # Die sechs Felder sind genau die, die wSammleEingaben erwartet.
    sammle = s[s.index("function wSammleEingaben("):]
    sammle = sammle[: sammle.index("\nfunction ", 10)]
    for feld in ("w-verkauf", "w-miete", "w-boden", "w-zielmarge", "w-basis", "w-land"):
        pruefe(f'"{feld}"' in sammle and f'"{feld}"' in block,
               f"{feld} wird gelesen UND gezeichnet")


def test_wirtschaft_kernkennzahlen(s: str) -> None:
    """Fuenf Kernkennzahlen, in der Reihenfolge der Rechnung.

    Erloes -> Investition -> Gewinn -> Marge -> tragbarer Landwert. Der
    Landwert ist die Hauptkachel: er ist die Zahl, mit der jemand in eine
    Verhandlung geht.
    """
    block = s[s.index("function ergebnisBlock("):]
    block = block[: block.index("\nfunction ", 10)]
    namen = re.findall(r'kz\("([^"]+)"', block)
    erwartet = ["Verkaufserlös", "Investition", "Gewinn", "Marge",
                "Max. tragbarer Landwert"]
    pruefe(namen == erwartet,
           f"fuenf Kernkennzahlen in der Reihenfolge {erwartet} (gefunden: {namen})")
    pruefe('"haupt"' in block,
           "der tragbare Landwert ist als Hauptkachel ausgezeichnet")
    pruefe("kzeile" in block,
           "die Wirtschaftlichkeit benutzt dieselben Kacheln wie die Uebersicht")
    # Die Bruttorendite ist eine sechste Zahl und war frueher eine eigene
    # Kachel. Sie gehoert zur Marge, nicht neben den Landwert.
    pruefe("Bruttorendite" in block and "margeFuss" in block,
           "die Bruttorendite steht bei der Marge, nicht als eigene Kachel")

    # Die Annahmen stehen VOR dem Ergebnis: eine Marge ueber einer noch
    # nicht gezeigten Grundlage ist eine Behauptung.
    wi = s[s.index("function secWirtschaft("):]
    wi = wi[: wi.index("\nfunction ", 10)]
    pruefe(wi.index('id="w-annahmen"') < wi.index('id="w-ergebnis"'),
           "der Annahmenstreifen steht ueber den Kennzahlen")


def test_daten_und_quellen(s: str) -> None:
    """Technik gehoert hierher -- uebersetzt, mit dem Rohwert daneben."""
    pruefe("function herkunftEbenen(" in s,
           "der Quellenreiter zeigt, wie das Ergebnis entstanden ist")
    q = s[s.index("function secQuellen("):]
    q = q[: q.index("\nfunction ", 10)] if "\nfunction " in q[10:] else q
    pruefe("herkunftEbenen(erg)" in q, "secQuellen benutzt die Herkunftskarten")
    pruefe("quellenNachSystem(q)" in q,
           "die Nachweise sind nach System gebuendelt, nicht 29 lose Zeilen")

    h = s[s.index("function herkunftEbenen("):]
    h = h[: h.index("\nfunction ", 10)]
    for nr, titel in ((1, "Geodaten"), (2, "Reglementsauswertung"), (3, "Stand")):
        pruefe(f'ebeneKopf({nr}, "{titel}"' in h, f"Herkunftskarte {nr}: {titel}")
    pruefe("modellKlarname(meta2.backend, meta2.model)" in h,
           "die Modellkennung wird uebersetzt")
    pruefe("meta2.model ? String(meta2.model)" in h,
           "die rohe Modellkennung bleibt als Zusatz daneben stehen")
    pruefe("sha256" in h,
           "die Pruefsumme des ausgewerteten Dokuments ist nachweisbar")

    # GWR-Codes: uebersetzt, aber immer mit dem Code daneben. Eine
    # Uebersetzung ohne ihren Ausgangswert waere nicht nachpruefbar.
    pruefe("var GWR_GKAT" in s and "var GWR_GKLAS" in s,
           "die GWR-Codes werden uebersetzt")
    gc = s[s.index("function gwrCode("):]
    gc = gc[: gc.index("\nfunction ", 10)] if "\nfunction " in gc[10:] else gc[: gc.index("\n}\n") + 3]
    pruefe('"Code " + code' in gc,
           "der Code steht immer neben der Uebersetzung")
    pruefe("nicht übersetzt" in gc,
           "ein unbekannter Code wird NICHT geraten, sondern als Code gezeigt")

    # Technische Kennungen sitzen in ihrem eigenen Block, nicht zwischen
    # den Angaben, die jemand beim Lesen braucht.
    g = s[s.index("function secGrundstueck("):]
    g = g[: g.index("\nfunction ", 10)]
    pruefe('class="kennungen"' in g and "Technische Kennungen" in g,
           "EGRID, EGID, BFS und LV95 stehen in einem eigenen Kennungsblock")
    for k in ("EGRID", "EGID", "BFS-Nummer", "Koordinaten LV95"):
        pruefe(f'kennung("{k}"' in g, f"{k} steht im Kennungsblock")

    st = s[s.index("function secStandort("):]
    st = st[: st.index("\nfunction ", 10)]
    pruefe("Rohwerte der Karten" in st,
           "die Rohwerte der Karten stehen getrennt von den Angaben darueber")
    pruefe("r.konfidenz" in st and "keine Prozentangabe" in st,
           "der Radon-Rohwert wird als Rohwert gekennzeichnet")


def test_umschrift_diphthong(s: str) -> None:
    """"ue" nach a oder e ist kein umgeschriebenes ü.

    Live beobachtet: "Die Vergleichswerte streün um 37 % des Medians."
    Die Wortliste allein reicht dafuer nicht -- sie muesste jedes Wort
    einzeln kennen.
    """
    block = s[s.index("function lesbar("):]
    block = block[: block.index("\nfunction ", 10)]
    pruefe("(?<![aeAE])ue" in block,
           "ue nach a oder e bleibt stehen (streuen, bauen, genauer)")
    pruefe("KEIN_UMLAUT" in block,
           "die Wortliste bleibt -- sie faengt Quelle, manuell, aktuell")
    # Alle drei Grossschreibungen brauchen dieselbe Ausnahme, sonst
    # entsteht sie nur fuer Kleinbuchstaben.
    pruefe(block.count("(?<![aeAE])") == 3,
           f"die Ausnahme gilt fuer ue, Ue und UE (gefunden: {block.count('(?<![aeAE])')})")


def test_teilfehler_sperrt_keinen_reiter(s: str) -> None:
    """Ein Teilfehler darf keinen Reiter leeren.

    Live beobachtet: schlaegt die Reglementsauswertung fehl -- oder ist die
    Zone nur nicht eindeutig --, zeigten Markt und Wirtschaftlichkeit je
    eine Ueberschrift, einen Satz und darunter eine leere Flaeche. Die
    Marktauswertung lag dabei bereits geladen vor: /api/marktdaten liefert
    sie unabhaengig von Zone und Reglement, und die Oberflaeche warf sie
    weg, weil EINE Zeile den ganzen Reiter an die Zonenzuordnung band.
    """
    markt = s[s.index("function secMarkt("):]
    markt = markt[: markt.index("\nfunction ", 10)]
    wirt = s[s.index("function secWirtschaft("):]
    wirt = wirt[: wirt.index("\nfunction ", 10)]

    # 1. Keine Sperre mehr: kein frueher Ausstieg, der den Reiter durch
    #    einen Satz ersetzt.
    for name, block in (("secMarkt", markt), ("secWirtschaft", wirt)):
        pruefe("zonen_zuordnung" not in block,
               f"{name} fragt die Zonenzuordnung nicht mehr selbst ab")
        pruefe(block.count("return ") == 1,
               f"{name} hat genau EINEN Rueckgabeweg -- keine Sperrseite "
               f"(gefunden: {block.count('return ')})")

    # 2. Der Marktreiter baut in JEDEM Fall seine drei Ebenen.
    for teil in ("ebeneKopf(1,", "mkt-verwaltung", "ebeneKopf(3,", 'id="w-markt"'):
        pruefe(teil in markt, f"secMarkt baut {teil} immer")

    # 3. Die Wirtschaftlichkeit behaelt Struktur und Eingaben.
    for teil in ('id="w-annahmen"', 'id="w-ergebnis"', 'id="w-mix"', 'id="w-bkp"'):
        pruefe(teil in wirt, f"secWirtschaft baut {teil} immer")
    pruefe("rechenstandBand(stand" in wirt,
           "der Grund steht als Band ueber der Struktur, nicht an ihrer Stelle")
    # Ergebnisse dagegen sind KEINE Struktur: leere Huelsen davon waeren
    # genau die weissen Flaechen, die verschwinden sollten.
    pruefe("stand.rechenbar" in wirt and "kombBlock()" in wirt,
           "Szenarienvergleich, beste Nutzung und Kombination nur, wenn "
           "gerechnet werden kann")


def test_rechenstand_eine_stelle(s: str) -> None:
    """Warum nicht gerechnet werden kann, entscheidet EINE Funktion.

    Sonst nennen zwei Reiter zwei verschiedene Gruende fuer denselben
    Sachverhalt -- und der Benutzer muss raten, welcher gilt.
    """
    pruefe("function rechenstand(" in s, "es gibt eine gemeinsame Zustandsauskunft")
    block = s[s.index("function rechenstand("):]
    block = block[: block.index("\nfunction ", 10)]

    # Vier Zustaende, und sie sind nicht dasselbe.
    for art in ("reglement_offen", "zone_nicht_eindeutig", "kein_szenario", "bereit"):
        pruefe('"' + art + '"' in block, f"Zustand {art} wird unterschieden")

    # Der Unterschied zwischen den ersten beiden ist technisch: bei
    # fehlender Reglementsauswertung ist der Auftrag nicht "done" und
    # /api/entwicklung antwortet mit 404.
    pruefe("zz === null || zz === undefined" in block,
           "ein fehlendes zonen_zuordnung ist das Teilergebnis nach Modul 1")
    pruefe('zz.status !== "gefunden"' in block,
           "eine vorhandene, aber nicht eindeutige Zone ist etwas anderes")
    pruefe("sondernutzungsplan_massgebend" in block
           and "mehrere_gleich_gute_kandidaten" in block,
           "der Grund benennt den konkreten Fall, nicht nur 'nicht eindeutig'")

    # Beide Reiter fragen dieselbe Stelle.
    for name in ("secMarkt", "secWirtschaft"):
        block2 = s[s.index("function " + name + "("):]
        block2 = block2[: block2.index("\nfunction ", 10)]
        pruefe("rechenstand(erg)" in block2, f"{name} fragt rechenstand()")

    # Und wRechne ruft nicht an, wenn niemand abnehmen kann.
    wr = s[s.index("function wRechne("):]
    wr = wr[: wr.index("\nfunction ", 10)]
    pruefe('stand.art === "reglement_offen"' in wr,
           "wRechne ruft /api/entwicklung NICHT auf, wenn der Auftrag nicht "
           "abgeschlossen ist -- die 404-Antwort ueberschrieb sonst den "
           "fachlichen Grund mit einer Meldung ueber die job_id")


def test_marktauswertung_zwei_wege(s: str) -> None:
    """Dieselbe Auswertung, zwei Zustellwege -- und keine zweite Logik.

    werte_mit_ausweitung() im Server liefert die Referenzlage sowohl an
    /api/entwicklung (mit den Szenarien) als auch an /api/marktdaten
    (allein). Die Oberflaeche las nur den ersten Weg -- und der braucht
    einen abgeschlossenen Auftrag.
    """
    lage = s[s.index("function wLage("):]
    lage = lage[: lage.index("\nfunction ", 10)]
    pruefe("wErgebnis" in lage and "mktLage" in lage,
           "wLage liest beide Zustellwege")
    pruefe(lage.index("wErgebnis") < lage.index("mktLage"),
           "die Rechnung hat Vorrang, die Marktabfrage ist der Ersatz")

    geb = s[s.index("function wGebiet("):]
    geb = geb[: geb.index("\nfunction ", 10)]
    pruefe("mktGebiete" in geb, "wGebiet ebenso")
    pruefe("var mktGebiete" in s and "a.daten.referenzgebiet" in s,
           "mktLaden behaelt das Referenzgebiet -- es wurde bisher verworfen")


def test_markt_ohne_standortdaten(s: str) -> None:
    """Der Marktreiter beantwortet nur: Was ist am Markt plausibel?

    Hangneigung, Ausrichtung, Hoehe und Radon sind Standortangaben. Die
    wichtigen stehen in der Uebersicht, die technischen in Daten &
    Quellen. Im Markt haben sie nichts verloren -- sie wuerden eine
    Marktaussage wie eine Standortanalyse aussehen lassen.
    """
    teile = []
    for name in ("secMarkt", "marktBlock", "marktGroesse", "mktZeichne", "marktExternBlock"):
        block = s[s.index("function " + name + "("):]
        teile.append(block[: block.index("\nfunction ", 10)])
    markt = "\n".join(teile)
    # Geprueft wird der CODE, nicht die Kommentare.
    markt = re.sub(r"/\*.*?\*/", "", markt, flags=re.S)
    markt = re.sub(r"^\s*//.*$", "", markt, flags=re.M)

    for feld in ("slope_deg", "slope_pct", "aspect", "hoehe_m", "radon",
                 "topographie", "wahrscheinlichkeit_prozent", "konfidenz",
                 "lv95", "egrid", "swissALTI3D"):
        pruefe(feld not in markt,
               f"'{feld}' steht NICHT im Marktreiter (Übersicht bzw. Daten & Quellen)")


def test_marktsatz_stimmt_mit_der_engine(s: str) -> None:
    """Der einleitende Satz im Markt muss die Rechenregel treffen.

    Er sagte: "In die Wirtschaftlichkeit geht am Ende nur das Dritte ein."
    Gemessen an wirtschaftlichkeit.Marktwert.wert ist das falsch -- ohne
    eigene Annahme rechnet die Engine mit dem Systemvorschlag:

        return self.benutzerannahme if self.benutzerannahme is not None                else self.systemvorschlag

    Ein Satz ueber die Rechnung, den die Rechnung nicht deckt, ist
    schlimmer als kein Satz.
    """
    block = s[s.index("function secMarkt("):]
    block = block[: block.index(chr(10) + "function ", 10)]
    pruefe("nur das Dritte ein" not in block,
           "der falsche Satz ist weg")
    pruefe("Systemvorschlag" in block and "Vorrang" in block,
           "der Satz nennt Systemvorschlag UND den Vorrang der eigenen Annahme")

    # Und die Reihenfolge stimmt: erst der Vorschlag, dann das Ueberschreiben.
    pruefe(block.index("Systemvorschlag") < block.index("Vorrang"),
           "erst der Systemvorschlag, dann sein Ueberschreiben")


def test_qualitaetsauswahl_passt_zur_engine(s: str) -> None:
    """Die Auswahl im Formular muss speicherbar sein.

    Sie war es nicht: das Formular bot "geprueft / angegeben /
    geschaetzt / unbekannt", die Engine kennt "hoch / mittel / gering /
    unbekannt". Drei von vier Auswahlen wurden abgewiesen, darunter die
    Vorauswahl.
    """
    pruefe("var MKT_QUALITAET = [" in s, "die Skala steht an einer Stelle")
    block = s[s.index("var MKT_QUALITAET = ["):]
    block = block[: block.index("];") + 2]
    werte = re.findall(r'\["([a-z]+)",', block)
    erwartet = ["hoch", "mittel", "gering", "unbekannt"]
    pruefe(werte == erwartet,
           f"die Auswahl fuehrt genau die kanonischen Stufen {erwartet} "
           f"(gefunden: {werte})")

    # Die alten Woerter duerfen nicht mehr als Auswahlwert auftauchen --
    # sie leben nur noch in der Synonymtabelle der Engine.
    formular = s[s.index("function mktZeichne("):]
    formular = formular[: formular.index(chr(10) + "function ", 10)]
    for wort in ('"geprueft"', '"angegeben"', '"geschaetzt"'):
        pruefe(wort not in formular,
               f"{wort} steht nicht mehr im Formular")

    pruefe('"unbekannt" ? " selected"' in formular,
           "vorbelegt ist 'unbekannt' -- derselbe Vorgabewert wie im Datenmodell; "
           "eine Stufe, die niemand gewaehlt hat, waere eine erfundene Einschaetzung")

    # Wird eine Stufe beim Import ersetzt, muss der Rohwert sichtbar sein.
    pruefe("datenqualitaet_roh" in s,
           "ein ersetzter Rohwert wird angezeigt, nicht verschwiegen")


def test_quellen_nie_vermischt(s: str) -> None:
    """Mehrere Quellen duerfen nie zu einer Zahl verschmelzen.

    Sobald neben dem AkquiseRadar eine zweite Quelle steht, waere genau
    das die bequemste Darstellung: ein "Marktpreis CHF 8'600/m2" ohne
    Herkunft. Jede Quelle wird deshalb einzeln ausgewiesen -- mit Anzahl,
    Datentyp und Stand.
    """
    pruefe("function quellenAufteilung(" in s and "function quellenBlock(" in s,
           "es gibt eine Aufteilung nach Quelle")
    block = s[s.index("function quellenAufteilung("):]
    block = block[: block.index(chr(10) + "function ", 10)]
    pruefe("o.quelle" in block,
           "gruppiert wird nach der Quelle des Objekts, nicht nach Herkunftsart")
    pruefe("q.von" in block and "q.bis" in block,
           "je Quelle wird der Datenstand mitgefuehrt")

    # Angebotspreis und Abschluss duerfen nicht zu einer Summe werden.
    typ = s[s.index("var MKT_DATENTYP = {"):]
    typ = typ[: typ.index("};") + 2]
    for art in ("angebot", "abschluss", "unbekannt"):
        pruefe(art in typ, f"der Datentyp '{art}' ist benannt")
    pruefe("Angebotspreis" in typ and "Abschluss" in typ,
           "Angebotspreise und Abschluesse werden getrennt benannt")

    # Beide Ebenen zeigen die Aufteilung -- Ebene 2 fuer alles Erfasste,
    # Ebene 3 fuer das tatsaechlich Verwendete.
    zeichne = s[s.index("function mktZeichne("):]
    zeichne = zeichne[: zeichne.index(chr(10) + "function ", 10)]
    pruefe("quellenBlock(mktObjekte" in zeichne,
           "Ebene 2 zeigt, woher die erfassten Objekte stammen")
    groesse = s[s.index("function marktGroesse("):]
    groesse = groesse[: groesse.index(chr(10) + "function ", 10)]
    pruefe("quellenBlock(objekte" in groesse,
           "Ebene 3 zeigt, woher die VERWENDETEN Referenzen stammen")


def test_sechs_marktsegmente(s: str) -> None:
    """Sechs Segmente, und drei davon rechnen nicht mit.

    Der Grund fuer die Aufteilung steht in den Daten: der AkquiseRadar
    fuehrt 1245 "Haus" und 173 "Mehrfamilienhaus", aber nur 2 "Wohnung".
    Mit einer einzigen Groesse "Verkaufspreis CHF/m2" blieb davon EINE
    verwertbar -- nicht weil die Objekte schlecht sind, sondern weil das
    Fach fehlte, in das sie gehoeren.
    """
    block = s[s.index("function marktBlock("):]
    block = block[: block.index(chr(10) + "function ", 10)]

    # Die Reihenfolge ist die der Engine (GROESSEN_REIHENFOLGE).
    namen = re.findall(r'markt(?:Groesse|Segment)\([^,]+, "([^"]+)"', block)
    erwartet = ["Wohnung Neubau", "Wohnung Bestand", "Einfamilienhaus",
                "Renditeliegenschaft", "Bauland", "Mietzins"]
    pruefe(namen == erwartet,
           f"sechs Segmente in der Reihenfolge {erwartet} (gefunden: {namen})")

    # Genau drei tragen ein Eingabefeld -- die drei, mit denen die
    # Wirtschaftlichkeit rechnet. Ein Feld, das nichts bewirkt, waere ein
    # Versprechen ohne Deckung.
    mitFeld = re.findall(r'marktGroesse\([^;]*?"(w-[a-z]+)"', block, re.S)
    pruefe(sorted(mitFeld) == ["w-boden", "w-miete", "w-verkauf"],
           f"genau Wohnung Neubau, Bauland und Mietzins haben ein Feld "
           f"(gefunden: {sorted(mitFeld)})")
    pruefe(block.count("marktSegment(") == 3,
           "die drei Referenzsegmente haben keines")

    seg = s[s.index("function marktSegment("):]
    seg = seg[: seg.index(chr(10) + "function ", 10)]
    pruefe('"badge mute">Referenz' in seg,
           "ein Referenzsegment ist als solches gekennzeichnet")
    pruefe("Systemvorschlag" in seg and "Gerechnet mit" not in seg,
           "es zeigt den Systemvorschlag, nicht 'Gerechnet mit' -- es wird "
           "ja nichts damit gerechnet")
    pruefe("zweitkennzahl" in seg,
           "die Zweitkennzahl (CHF je m2) ordnet den Gesamtpreis ein")
    pruefe("Angebotspreis" in seg and "nicht der, der bezahlt wurde" in seg,
           "Angebotspreise sind auch hier ausdruecklich Angebotspreise")

    ohne_kommentar = re.sub(r"/\*.*?\*/", "", seg, flags=re.S)
    ohne_kommentar = re.sub(r"^\s*//.*$", "", ohne_kommentar, flags=re.M)
    pruefe(not re.search(r"\d['’]?\d{3}", ohne_kommentar),
           "im Referenzsegment steht keine eingebaute Zahl")


def test_entwurf_reiter(s: str) -> None:
    """Die 3D-Ansicht gab es schon -- gefunden hat sie niemand.

    Sie lag 2770 Pixel tief im Potenzialreiter, war 380 Pixel hoch und
    verschwand vollstaendig, sobald kein Szenario berechenbar war. Live
    geprueft: bei einem Sondernutzungsplan existierte #view3d gar nicht,
    obwohl Gelaende, 90 Nachbargebaeude, Parzelle und Baubereich vorlagen.
    """
    block = s[s.index("function secEntwurf("):]
    block = block[: block.index(chr(10) + "function ", 10)]

    # 1. Genau EINE Buehne im Dokument. Zwei waeren zwei Leinwaende fuer
    #    einen Renderer -- die zweite bliebe fuer immer schwarz.
    pruefe(s.count('id="view3d"') == 1,
           f"genau eine 3D-Buehne im Dokument (gefunden: {s.count(chr(34) + 'view3d' + chr(34))})")
    pruefe('id="view3d"' in block, "und sie steht im Entwurfsreiter")
    szen = s[s.index("function secSzenarien("):]
    szen = szen[: szen.index(chr(10) + "function ", 10)]
    pruefe("view3d" not in szen,
           "secSzenarien traegt die Buehne NICHT mehr -- verschoben, nicht verdoppelt")
    pruefe('reiterLink("entwurf"' in szen,
           "vom Potenzialreiter fuehrt ein Weg zur 3D-Ansicht")

    # 2. Der Abschnitt haengt NICHT am Szenarienstand. Das ist der Kern.
    pruefe("parzellengeometrie" in block,
           "gepruoft wird die Parzellenkontur -- ohne Raum kein Raumbild")
    pruefe("Kein belastbares Entwicklungsszenario berechnet" in block,
           "fehlt ein Szenario, sagt der Reiter das -- statt zu verschwinden")
    pruefe("nicht erfunden" in block,
           "und er sagt ausdruecklich, dass kein Koerper erfunden wird")
    # Ein frueher Ausstieg darf es nur fuer die fehlende Parzelle geben.
    # Gezaehlt werden die Abschnittsrueckgaben, nicht jedes return in
    # einem map()-Rumpf.
    abschnitte = block.count("return '<section")
    pruefe(abschnitte == 2,
           f"genau zwei Rueckgabewege: ohne Parzelle und sonst "
           f"(gefunden: {abschnitte})")

    # 3. Die vorhandenen Werkzeuge ziehen mit um, statt neu gebaut zu werden.
    for teil in ('d3schalter("terrain"', 'd3schalter("gebaeude"', 'd3schalter("projekt"',
                 'data-mess="distanz"', 'id="sonne-an"', 'id="view3d-legende"'):
        pruefe(teil in block, f"{teil} ist mitgezogen")

    # 4. Freie Navigation.
    pruefe("window.setze3DBlick" in s and "var BLICK = {" in s,
           "feste Blickrichtungen sind waehlbar")
    for r in ("sued", "west", "nord", "ost", "oben", "start"):
        pruefe(f'data-blick="{r}"' in block, f"Blickrichtung {r}")
    pruefe("var blickpunkt" in s and "blickpunkt.set(0, 0, 0)" in s,
           "der Blickpunkt ist verschiebbar und zuruecksetzbar")
    pruefe("kamera.lookAt(z0.x, z0.y, z0.z)" in s,
           "die Kamera kreist um den Blickpunkt, nicht mehr fest um den Nullpunkt")

    # 5. Die Messung darf dabei nicht kaputtgehen.
    pruefe("messModus && e.button === 0" in s,
           "gemessen wird nur mit der linken Taste -- sonst loeste auch das "
           "Loslassen nach dem Verschieben eine Messung aus")
    pruefe("schiebtGerade = e.button === 2 || e.shiftKey" in s,
           "verschoben wird mit rechter Taste oder Umschalt")

    # 6. Eine verborgene Buehne ist 0 x 0 gross. Ohne Nachmessen beim
    #    Sichtbarwerden bliebe die Szene leer.
    pruefe("window.passe3DAn" in s, "die Buehne misst sich beim Sichtbarwerden nach")
    pruefe('name === "entwurf" && window.zeichne3D' in s,
           "und wird beim Oeffnen des Reiters gezeichnet -- bisher stiess nur "
           "die Szenarienwahl das Zeichnen an")

    # 7. Zwei Fehler, die erst auffielen, als die Ansicht erreichbar war.
    #    Beide traten bei der ZWEITEN Analyse in derselben Sitzung auf.
    pruefe("renderer.domElement.parentNode !== el" in s,
           "die Leinwand wird an den neuen Container gehaengt -- renderDossier "
           "ersetzt #view3d bei jeder Analyse, die alte Leinwand haengt sonst "
           "an einem entfernten Element und die Buehne bleibt leer")
    pruefe("var umgebungFuerJob" in s and "umgebungFuerJob !== jobIdAktuell" in s,
           "die Umgebung wird je Auftrag neu geladen -- sonst zeichnet die "
           "zweite Analyse das Gelaende und die Nachbargebaeude der ersten")


def main() -> int:
    if not SEITE.exists():
        print(f"FEHLT: {SEITE}")
        return 1
    s = lies()
    for fn in (test_reiter, test_karte_ausserhalb_des_dossiers, test_css_variablen,
               test_inhaltsbreite, test_keine_abschnittsnummern,
               test_bandbreiten_auskunft, test_markt_und_wirtschaft_getrennt,
               test_uebersicht, test_markt_drei_ebenen, test_markt_sicherheitsgrad,
               test_markt_keine_platzhalter, test_markt_eingabefelder_bleiben,
               test_wirtschaft_kernkennzahlen,
               test_daten_und_quellen, test_umschrift_diphthong,
               test_teilfehler_sperrt_keinen_reiter, test_rechenstand_eine_stelle,
               test_marktauswertung_zwei_wege, test_markt_ohne_standortdaten,
               test_marktsatz_stimmt_mit_der_engine,
               test_qualitaetsauswahl_passt_zur_engine,
               test_quellen_nie_vermischt, test_sechs_marktsegmente,
               test_entwurf_reiter):
        fn(s)

    if _fehler:
        print(f"OBERFLAECHEN-TESTS: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print("  NICHT ERFUELLT:", f)
        return 1
    print(f"ALLE OBERFLAECHEN-TESTS BESTANDEN ({_ok} OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    """Sechs Reiter, in dieser Reihenfolge -- die Navigation des Dossiers."""
    block = s[s.index("var REITER = ["):]
    block = block[: block.index("];")]
    namen = re.findall(r'\["([a-z]+)", "', block)
    erwartet = ["uebersicht", "baurecht", "karte", "potenzial", "markt",
                "wirtschaft", "quellen"]
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
        pruefe(1100 <= breite <= 1400,
               f"Bahnbreite {breite}px liegt im Bereich 1100-1400px")


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


def main() -> int:
    if not SEITE.exists():
        print(f"FEHLT: {SEITE}")
        return 1
    s = lies()
    for fn in (test_reiter, test_karte_ausserhalb_des_dossiers, test_css_variablen,
               test_inhaltsbreite, test_keine_abschnittsnummern,
               test_bandbreiten_auskunft, test_markt_und_wirtschaft_getrennt):
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

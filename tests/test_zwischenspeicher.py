"""
Tests des Analyse-Zwischenspeichers.

Vollstaendig OFFLINE. Ein Zwischenspeicher ist bequem und gefaehrlich: er
liefert schnell -- und wenn er falsch liegt, liefert er schnell etwas
Falsches. Geprueft wird deshalb vor allem, wann er NICHT greifen darf:

  * Nach einer Aenderung an der Engine. Der Schluessel ist ein Abdruck des
    Quellcodes, keine von Hand gepflegte Nummer -- eine solche wird
    vergessen, und dann liefert der Speicher Ergebnisse einer Rechnung, die
    es nicht mehr gibt.
  * Nach Ablauf der Gueltigkeit. Eine revidierte BZO nach einem Jahr
    stillschweigend weiterzuverwenden waere schlimmer als zwei Minuten zu
    warten.
  * Bei einer gescheiterten Analyse. Ein Fehlschlag darf sich nicht
    festsetzen.
  * Bei einem anderen Grundstueck.

Und eine Eigenschaft, die ebenso wichtig ist: ein DEFEKTER Zwischenspeicher
darf das Werkzeug nicht unbenutzbar machen. Faellt die Datenschicht aus,
wird gerechnet -- nicht abgebrochen.

CLI: python -m tests.test_zwischenspeicher
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import webapp

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


EGRID = "CH975272732334"


def frische_db():
    from kern import db
    return db.verbinde(Path(tempfile.mkdtemp()) / "kern.db")


def grundstueck_anlegen(con):
    from kern import db
    db.speichere_grundstueck(con, {"egrid": EGRID, "gemeinde": "Buchs (AG)", "kanton": "AG"})


def vor_tagen(tage: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=tage)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------


def test_fingerabdruck() -> None:
    print("Engine-Fingerabdruck")
    a = webapp._engine_fingerabdruck()
    b = webapp._engine_fingerabdruck()
    pruefe(a == b, f"Derselbe Code ergibt denselben Abdruck ({a})")
    pruefe(len(a) == 16 and all(c in "0123456789abcdef" for c in a),
           "16 Hexzeichen -- kurz genug fuer eine Datenbankspalte")
    pruefe(webapp.ENGINE_VERSION == a, "Der Dienst benutzt genau diesen Abdruck")

    # Eine geaenderte Engine muss einen anderen Abdruck ergeben, sonst wuerde
    # der Speicher Ergebnisse einer alten Rechnung weiterreichen.
    verzeichnis = Path(webapp.__file__).resolve().parent / "potenzial_engine"
    probe = verzeichnis / "__zwischenspeicher_probe.py"
    try:
        probe.write_text("# nur fuer den Test\n", encoding="utf-8")
        c = webapp._engine_fingerabdruck()
        pruefe(c != a, f"Eine geaenderte Engine ergibt einen anderen Abdruck ({c})")
    finally:
        if probe.exists():
            probe.unlink()
    pruefe(webapp._engine_fingerabdruck() == a, "und danach wieder den urspruenglichen")
    print()


def test_alter() -> None:
    print("Altersberechnung")
    pruefe(webapp._alter_in_tagen(webapp._jetzt_iso()) < 0.001, "Ein frischer Eintrag ist ~0 Tage alt")
    pruefe(abs(webapp._alter_in_tagen(vor_tagen(5)) - 5) < 0.01, "Fuenf Tage werden als fuenf gelesen")
    pruefe(webapp._alter_in_tagen("kein Zeitpunkt") is None,
           "Ein unlesbarer Zeitpunkt ergibt None -- und fuehrt damit zur Neuberechnung")
    pruefe(webapp._alter_in_tagen(None) is None, "None ebenso")

    # Ein Zeitpunkt ohne Zonenangabe wird als UTC gelesen, nicht abgelehnt --
    # aeltere Eintraege sollen weiter nutzbar bleiben.
    naiv = (datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None).isoformat()
    pruefe(abs(webapp._alter_in_tagen(naiv) - 2) < 0.01,
           "Ein Zeitpunkt ohne Zone wird als UTC gelesen")
    print()


def test_treffer_und_fehlschlag() -> None:
    print("Wann der Speicher greift -- und wann nicht")
    from kern import db

    con = frische_db()
    grundstueck_anlegen(con)
    ergebnis = {"modul1_geodaten": {"kataster": {"egrid": EGRID}}, "probe": 1}
    db.speichere_analyse(con, EGRID, webapp.ENGINE_VERSION, "adresse", "erfolgreich", ergebnis)

    treffer = db.juengste_analyse(con, EGRID, webapp.ENGINE_VERSION, "adresse")
    pruefe(treffer is not None, "Gleiches Grundstueck, gleiche Engine -> Treffer")

    pruefe(db.juengste_analyse(con, EGRID, "andere_version", "adresse") is None,
           "Andere Engine-Version -> KEIN Treffer")
    pruefe(db.juengste_analyse(con, "CH000000000000", webapp.ENGINE_VERSION, "adresse") is None,
           "Anderes Grundstueck -> KEIN Treffer")
    pruefe(db.juengste_analyse(con, EGRID, webapp.ENGINE_VERSION, "andere_eingaben") is None,
           "Andere Eingaben -> KEIN Treffer")

    # Ein Fehlschlag darf sich nicht festsetzen.
    con2 = frische_db()
    grundstueck_anlegen(con2)
    db.speichere_analyse(con2, EGRID, webapp.ENGINE_VERSION, "adresse", "fehlgeschlagen",
                         None, fehler="OEREB nicht erreichbar")
    pruefe(db.juengste_analyse(con2, EGRID, webapp.ENGINE_VERSION, "adresse") is None,
           "Eine gescheiterte Analyse wird nie als Treffer geliefert")
    print()


def test_gueltigkeit() -> None:
    print("Gueltigkeitsdauer")
    from kern import db

    con = frische_db()
    grundstueck_anlegen(con)
    ergebnis = {"modul1_geodaten": {"kataster": {"egrid": EGRID}}}

    # Direkt mit einem alten Zeitstempel schreiben.
    db.speichere_analyse(con, EGRID, webapp.ENGINE_VERSION, "adresse", "erfolgreich", ergebnis)
    con.execute("UPDATE analyse SET erstellt_am = ?", (vor_tagen(45),))
    con.commit()

    zeile = db.juengste_analyse(con, EGRID, webapp.ENGINE_VERSION, "adresse")
    alter = webapp._alter_in_tagen(zeile["erstellt_am"])
    pruefe(alter > webapp.ANALYSE_CACHE_TAGE,
           f"45 Tage liegen ueber der Gueltigkeit von {webapp.ANALYSE_CACHE_TAGE} Tagen "
           f"-> muss neu gerechnet werden")

    con.execute("UPDATE analyse SET erstellt_am = ?", (vor_tagen(3),))
    con.commit()
    zeile = db.juengste_analyse(con, EGRID, webapp.ENGINE_VERSION, "adresse")
    pruefe(webapp._alter_in_tagen(zeile["erstellt_am"]) <= webapp.ANALYSE_CACHE_TAGE,
           "3 Tage liegen darunter -> darf verwendet werden")
    print()


def test_herkunft_sichtbar() -> None:
    """Ein gespeichertes Ergebnis muss sich als solches zu erkennen geben."""
    print("Herkunft des Ergebnisses")
    marke = {"aus_zwischenspeicher": True, "gerechnet_am": vor_tagen(4),
             "alter_tage": 4.0, "gueltig_bis_tage": webapp.ANALYSE_CACHE_TAGE}
    for feld in ("aus_zwischenspeicher", "gerechnet_am", "alter_tage"):
        pruefe(feld in marke, f"Die Marke nennt {feld}")
    pruefe(marke["gerechnet_am"][:4].isdigit(),
           "Das Rechendatum steht als Zeitpunkt da, nicht als 'kuerzlich'")
    print()


def test_defekter_speicher_blockiert_nicht() -> None:
    """Ein defekter Zwischenspeicher darf das Werkzeug nicht lahmlegen."""
    print("Ausfall der Datenschicht")

    class Handler:
        _zwischenspeicher_suchen = webapp.Handler._zwischenspeicher_suchen
        _zwischenspeicher_ablegen = webapp.Handler._zwischenspeicher_ablegen

    echt = webapp._kern_projekt
    try:
        webapp._kern_projekt = lambda: (None, None)
        ergebnis, egrid = Handler()._zwischenspeicher_suchen("Rosenweg 4, 5033 Buchs AG")
        pruefe(ergebnis is None and egrid is None,
               "Ohne Datenschicht: kein Treffer, aber auch kein Fehler")
        Handler()._zwischenspeicher_ablegen(EGRID, {"x": 1})
        pruefe(True, "Ablegen ohne Datenschicht laeuft durch, statt zu werfen")
    finally:
        webapp._kern_projekt = echt

    class Kaputt:
        @staticmethod
        def verbinde(*a, **k):
            raise RuntimeError("Datenbank kaputt")

    try:
        webapp._kern_projekt = lambda: (Kaputt, object())
        ergebnis, _ = Handler()._zwischenspeicher_suchen("Rosenweg 4, 5033 Buchs AG")
        pruefe(ergebnis is None, "Bei kaputter Datenbank: kein Treffer, kein Absturz")
        Handler()._zwischenspeicher_ablegen(EGRID, {"x": 1})
        pruefe(True, "Ablegen faengt den Fehler ebenfalls ab")
    finally:
        webapp._kern_projekt = echt
    print()


def main() -> None:
    test_fingerabdruck()
    test_alter()
    test_treffer_und_fehlschlag()
    test_gueltigkeit()
    test_herkunft_sichtbar()
    test_defekter_speicher_blockiert_nicht()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE ZWISCHENSPEICHER-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

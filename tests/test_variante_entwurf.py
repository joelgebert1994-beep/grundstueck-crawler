"""Der Entwurfszustand einer Variante.

Eine Variante haelt jetzt auch den gezeichneten Projektkoerper fest --
Lage, Masse, Geschosse und die Engine-Anordnung, gegen die er geprueft
wurde. Geprueft wird vor allem zweierlei:

  * dass beim Laden EXAKT derselbe Zustand zurueckkommt
  * dass KEINE gerechnete Fachzahl mitgespeichert wird

Der zweite Punkt ist der wichtigere. Eine gespeicherte aGF stuende beim
naechsten Oeffnen als Tatsache da, auch wenn das Flaechenmodell inzwischen
anders rechnet.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Crawler"))

from kern import db, projekt as pj  # noqa: E402

_ok = 0
_fehler: list[str] = []


def pruefe(bedingung: bool, was: str) -> None:
    global _ok
    if bedingung:
        _ok += 1
        print(f"[OK  ] {was}")
    else:
        _fehler.append(was)
        print(f"[FEHL] {was}")


def frisch():
    """Eine leere Datenbank mit einem Projekt und einer Variante."""
    pfad = Path(tempfile.mkdtemp()) / "test.db"
    con = db.verbinde(str(pfad))
    p = pj.erstelle_projekt(con, name="Testparzelle", egrid="CH000000000000",
                            adresse="Teststrasse 1")
    return con, p


ENTWURF_A = {
    "szenario": "ersatzneubau",
    "anordnung": "alle_kanten_gross",
    "rahmen": {"mx": 2754713.4, "my": 1260724.15, "basis": 462.0},
    "koerper": [{
        "id": "k1", "name": "Baukörper 1",
        "mitte": [-4.25, 11.8], "breite": 14.0, "tiefe": 22.0,
        "drehung": 0.3141, "geschosse": 3, "geschosshoehe": 3.0,
        "hoeheAngenommen": False, "geschosseAngenommen": False,
    }],
}


def test_speichern_und_laden() -> None:
    """Was gespeichert wurde, kommt unveraendert zurueck."""
    print("\n=== Speichern und laden ===")

    con, p = frisch()
    v = p["varianten"][0]

    ohne = pj.lade_variante(con, v["variante_id"])
    pruefe(ohne["entwurf"] == {} and ohne["hat_entwurf"] is False,
           "eine neue Variante hat keinen Entwurf -- und das ist kein Fehler")

    nachher = pj.speichere_entwurf(con, v["variante_id"], ENTWURF_A)
    pruefe(nachher["hat_entwurf"] is True, "nach dem Speichern hat sie einen")

    geladen = pj.lade_variante(con, v["variante_id"])["entwurf"]
    pruefe(geladen == ENTWURF_A, "und er kommt Feld fuer Feld unveraendert zurueck")

    k = geladen["koerper"][0]
    for feld in ("mitte", "breite", "tiefe", "drehung", "geschosse", "geschosshoehe"):
        pruefe(k[feld] == ENTWURF_A["koerper"][0][feld], f"{feld} unveraendert")
    pruefe(geladen["anordnung"] == "alle_kanten_gross",
           "die Anordnung ist Teil des Zustands -- ohne sie spraenge die Pruefung "
           "beim Laden auf eine andere Geometrie")
    pruefe(geladen["rahmen"]["mx"] == 2754713.4,
           "der Bezugsrahmen ebenso -- sonst laege der Koerper verschoben")


def test_keine_fachzahl_wird_gespeichert() -> None:
    """Gerechnete Werte werden verworfen, nicht mitgespeichert.

    Kaeme aGF oder NWF hier an, stuende es beim naechsten Oeffnen als
    Tatsache da -- auch wenn das Flaechenmodell inzwischen anders rechnet.
    """
    print("\n=== Keine gerechnete Zahl im Entwurf ===")

    con, p = frisch()
    v = p["varianten"][0]

    verseucht = dict(ENTWURF_A)
    verseucht.update({
        "agf_m2": 924.0, "nwf_m2": 610.0, "ausnuetzung": 0.62,
        "wohnflaeche_m2": 610.0, "flaechen": {"geschossflaeche_gf": {"wert": 924.0}},
    })
    gespeichert = pj.speichere_entwurf(con, v["variante_id"], verseucht)["entwurf"]

    for feld in ("agf_m2", "nwf_m2", "ausnuetzung", "wohnflaeche_m2", "flaechen"):
        pruefe(feld not in gespeichert, f"{feld} wird verworfen")
    pruefe(set(gespeichert) <= pj.ERLAUBTER_ENTWURF,
           "gespeichert wird ausschliesslich, was zum Entwurfszustand gehoert")
    pruefe(gespeichert["koerper"] == ENTWURF_A["koerper"],
           "der Koerper selbst bleibt vollstaendig")


def test_abstammung_nimmt_den_entwurf_mit() -> None:
    """Eine abgeleitete Variante beginnt beim Koerper der Vorgaengerin.

    Die vorhandene Abstammungslogik wird benutzt, nicht eine neue gebaut:
    basiert_auf_variante_id kommt aus dupliziere_variante().
    """
    print("\n=== Abstammung ===")

    con, p = frisch()
    a = p["varianten"][0]
    pj.speichere_entwurf(con, a["variante_id"], ENTWURF_A)

    b = pj.dupliziere_variante(con, a["variante_id"], "Variante B")
    pruefe(b["basiert_auf_variante_id"] == a["variante_id"],
           "B weiss, dass sie aus A entstanden ist")
    pruefe(b["entwurf"] == ENTWURF_A,
           "und beginnt beim Koerper von A")

    # B abwandeln -- A darf sich dabei nicht aendern.
    anders = {"szenario": "ersatzneubau", "anordnung": "alle_kanten_klein",
              "rahmen": ENTWURF_A["rahmen"],
              "koerper": [dict(ENTWURF_A["koerper"][0], breite=25.2, geschosse=4)]}
    pj.speichere_entwurf(con, b["variante_id"], anders)

    a_neu = pj.lade_variante(con, a["variante_id"])["entwurf"]
    b_neu = pj.lade_variante(con, b["variante_id"])["entwurf"]
    pruefe(a_neu == ENTWURF_A, "A behaelt ihren eigenen Entwurf")
    pruefe(b_neu["koerper"][0]["breite"] == 25.2 and b_neu["koerper"][0]["geschosse"] == 4,
           "B traegt die Abwandlung")
    pruefe(a_neu["anordnung"] == "alle_kanten_gross"
           and b_neu["anordnung"] == "alle_kanten_klein",
           "und beide behalten ihre EIGENE Anordnung -- beim Wechsel darf die "
           "Pruefung nicht auf die der anderen springen")

    c = pj.dupliziere_variante(con, b["variante_id"], "Variante C")
    pruefe(c["basiert_auf_variante_id"] == b["variante_id"]
           and c["entwurf"]["anordnung"] == "alle_kanten_klein",
           "C basiert auf B und erbt deren Anordnung")


def test_kein_neuer_stand_und_kein_verlaufseintrag() -> None:
    """Ein verschobener Baukoerper erzeugt keinen Stand.

    Dieselbe Begruendung wie bei der Ansicht: wuerde jede Verschiebung
    einen Stand erzeugen, waere der Verlauf nach einer Minute Arbeit
    unbrauchbar und das spaetere Undo wertlos.
    """
    print("\n=== Kein Stand fuer eine Verschiebung ===")

    con, p = frisch()
    v = p["varianten"][0]
    vorher = pj.lade_variante(con, v["variante_id"])["stand"]

    for i in range(5):
        bewegt = {"koerper": [dict(ENTWURF_A["koerper"][0], mitte=[i * 1.0, 0.0])]}
        pj.speichere_entwurf(con, v["variante_id"], bewegt)

    nachher = pj.lade_variante(con, v["variante_id"])["stand"]
    pruefe(nachher == vorher, "der Stand bleibt, wo er war")
    n = con.execute("SELECT COUNT(*) AS n FROM variante_verlauf WHERE variante_id = ?",
                    (v["variante_id"],)).fetchone()["n"]
    pruefe(n <= 1, f"und der Verlauf waechst nicht mit (Eintraege: {n})")

    # Eine echte Benutzerannahme dagegen erzeugt sehr wohl einen Stand.
    pj.speichere_variante(con, v["variante_id"], eingaben={"zielmarge": 0.18})
    pruefe(pj.lade_variante(con, v["variante_id"])["stand"] > vorher,
           "eine Benutzerannahme erzeugt weiterhin einen Stand")


def test_entwurf_laesst_sich_verwerfen() -> None:
    """None loescht den gespeicherten Entwurf wieder."""
    print("\n=== Verwerfen ===")

    con, p = frisch()
    v = p["varianten"][0]
    pj.speichere_entwurf(con, v["variante_id"], ENTWURF_A)
    leer = pj.speichere_entwurf(con, v["variante_id"], None)
    pruefe(leer["entwurf"] == {} and leer["hat_entwurf"] is False,
           "der Entwurf ist weg, die Variante bleibt")


def test_migration_ergaenzt_die_spalte() -> None:
    """Eine Datenbank aus der Zeit vor der Projektstudie bekommt die Spalte.

    CREATE TABLE IF NOT EXISTS legt eine vorhandene Tabelle nicht neu an --
    eine neue Spalte kaeme dort nie an. Dieselbe Lage wie bei ansicht_json.
    """
    print("\n=== Migration ===")

    pfad = Path(tempfile.mkdtemp()) / "alt.db"
    con = db.verbinde(str(pfad))
    con.execute("ALTER TABLE variante DROP COLUMN entwurf_json")
    con.commit()
    spalten = {z["name"] for z in con.execute("PRAGMA table_info(variante)")}
    pruefe("entwurf_json" not in spalten, "Ausgangslage: die Spalte fehlt")

    pruefe(db._migriere_entwurf(con) is True, "die Migration greift")
    spalten = {z["name"] for z in con.execute("PRAGMA table_info(variante)")}
    pruefe("entwurf_json" in spalten, "und die Spalte ist da")
    pruefe(db._migriere_entwurf(con) is False, "ein zweiter Lauf tut nichts mehr")

    # Und eine Variante aus dieser Datenbank laesst sich lesen.
    p = pj.erstelle_projekt(con, name="Alt", egrid="CH1", adresse="A")
    pruefe(pj.lade_variante(con, p["varianten"][0]["variante_id"])["entwurf"] == {},
           "eine Variante ohne Entwurf laedt ohne Fehler")


def main() -> int:
    for fn in (test_speichern_und_laden, test_keine_fachzahl_wird_gespeichert,
               test_abstammung_nimmt_den_entwurf_mit,
               test_kein_neuer_stand_und_kein_verlaufseintrag,
               test_entwurf_laesst_sich_verwerfen,
               test_migration_ergaenzt_die_spalte):
        fn()
    if _fehler:
        print(f"\nVARIANTE-ENTWURF: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print("  NICHT ERFUELLT:", f)
        return 1
    print(f"\nALLE VARIANTE-ENTWURF-TESTS BESTANDEN ({_ok} OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

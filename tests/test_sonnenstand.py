"""
Tests der Sonnenstandsberechnung.

Vollstaendig OFFLINE und ohne Referenztabelle. Geprueft wird gegen
**Himmelsmechanik**, nicht gegen abgeschriebene Zahlen: die folgenden
Beziehungen gelten unabhaengig vom Rechenverfahren, und ein Verfahren, das
sie alle erfuellt, kann nicht grob falsch sein.

  * Zur Sonnenwende erreicht die Sonne 90 Grad - Breite +/- 23.44 Grad. Das
    ist keine Naeherung, sondern die Definition der Wende.
  * Auf- und Untergang liegen symmetrisch um den Hoechststand.
  * Zur Tagundnachtgleiche geht die Sonne ueberall im Osten auf und im Westen
    unter, und der Tag dauert rund zwoelf Stunden -- etwas laenger, weil die
    Lufthuelle die Sonne anhebt.
  * Auf der Nordhalbkugel steht die Sonne mittags im Sueden, auf der
    Suedhalbkugel im Norden. Wer hier ein Vorzeichen dreht, baut Schatten in
    die falsche Richtung -- und genau das faellt sonst niemandem auf.
  * Der Richtungsvektor muss zu Azimut und Hoehe passen und Laenge 1 haben.

Dazu die beiden Fallen, die im Betrieb wehtun:

  * Sommerzeit. Zwischen 13:29 MESZ und 13:29 MEZ liegt eine volle Stunde
    Schattenwurf. Ein Zeitpunkt ohne Zonenangabe wird deshalb abgewiesen.
  * Die Umstellungstage haben 23 bzw. 25 Stunden. Ein Tagesverlauf mit fest
    verdrahteten 1440 Minuten waere an zwei Tagen im Jahr falsch.

CLI: python -m tests.test_sonnenstand
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, timedelta, timezone

from potenzial_engine import sonnenstand as so

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def nahe(a: float, b: float, toleranz: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= toleranz


# Buchs AG, Rosenweg 4 -- der Referenzfall der Engine.
LAT, LON = 47.3876, 8.0698
CH = so.ZEITZONE_CH


def ortszeit(j: int, m: int, t: int, std: int = 12, minute: int = 0) -> datetime:
    return datetime(j, m, t, std, minute, tzinfo=CH)


def hoechststand(tag: date, lat: float = LAT, lon: float = LON) -> so.Sonnenstand:
    """Die hoechste Stuetzstelle eines Tages, minutengenau gesucht."""
    besser = max(so.tagesverlauf(lat, lon, tag, 1, CH), key=lambda s: s.hoehe_geometrisch_grad)
    return besser


# ---------------------------------------------------------------------------


def test_sonnenwenden() -> None:
    """Die Wendepunkte sind der schaerfste Test, den es ohne Tabelle gibt."""
    print("Sonnenwenden und Tagundnachtgleiche")

    sommer = hoechststand(date(2026, 6, 21))
    erwartet_sommer = 90.0 - LAT + 23.44
    pruefe(nahe(sommer.hoehe_geometrisch_grad, erwartet_sommer, 0.25),
           f"Sommerwende: {sommer.hoehe_geometrisch_grad:.2f} Grad, "
           f"erwartet {erwartet_sommer:.2f} (90 - Breite + Schiefe)")

    winter = hoechststand(date(2026, 12, 21))
    erwartet_winter = 90.0 - LAT - 23.44
    pruefe(nahe(winter.hoehe_geometrisch_grad, erwartet_winter, 0.25),
           f"Winterwende: {winter.hoehe_geometrisch_grad:.2f} Grad, "
           f"erwartet {erwartet_winter:.2f} (90 - Breite - Schiefe)")

    gleiche = hoechststand(date(2026, 3, 20))
    pruefe(nahe(gleiche.hoehe_geometrisch_grad, 90.0 - LAT, 0.6),
           f"Tagundnachtgleiche: {gleiche.hoehe_geometrisch_grad:.2f} Grad, "
           f"erwartet {90.0 - LAT:.2f} (90 - Breite)")

    pruefe(sommer.hoehe_geometrisch_grad - winter.hoehe_geometrisch_grad > 46.0,
           "Zwischen den Wenden liegen ueber 46 Grad Sonnenhoehe "
           f"({sommer.hoehe_geometrisch_grad - winter.hoehe_geometrisch_grad:.1f})")

    pruefe(nahe(sommer.azimut_grad, 180.0, 1.5),
           f"Mittags steht die Sonne im Sueden ({sommer.azimut_grad:.1f} Grad)")
    print()


def test_tagundnachtgleiche_ost_west() -> None:
    """Zur Tagundnachtgleiche geht die Sonne ueberall im Osten auf."""
    print("Tagundnachtgleiche: Auf- und Untergangsrichtung")
    for name, lat, lon in [("Buchs AG", LAT, LON), ("Tromsoe", 69.65, 18.96),
                           ("Nairobi", -1.29, 36.82)]:
        verlauf = so.tagesverlauf(lat, lon, date(2026, 3, 20), 1, timezone.utc)
        ueber = [s for s in verlauf if s.hoehe_geometrisch_grad > 0]
        if not ueber:
            pruefe(False, f"{name}: kein Sonnenaufgang gefunden")
            continue
        auf, unter = ueber[0], ueber[-1]
        pruefe(nahe(auf.azimut_grad, 90.0, 2.0),
               f"{name}: Aufgang im Osten ({auf.azimut_grad:.1f} Grad)")
        pruefe(nahe(unter.azimut_grad, 270.0, 2.0),
               f"{name}: Untergang im Westen ({unter.azimut_grad:.1f} Grad)")

    z = so.sonnenzeiten(LAT, LON, date(2026, 3, 20), CH)
    pruefe(720 <= z["tageslaenge_min"] <= 740,
           f"Der Tag dauert rund 12 Stunden, etwas mehr durch Refraktion "
           f"({z['tageslaenge_min']} min)")
    print()


def test_symmetrie() -> None:
    """Auf- und Untergang liegen gleich weit vom Hoechststand entfernt."""
    print("Symmetrie um den Hoechststand")
    for tag in [date(2026, 2, 3), date(2026, 6, 21), date(2026, 9, 15), date(2026, 11, 30)]:
        z = so.sonnenzeiten(LAT, LON, tag, CH)
        auf = datetime.fromisoformat(z["aufgang"])
        unter = datetime.fromisoformat(z["untergang"])
        mittag = datetime.fromisoformat(z["hoechststand"])
        vor = (mittag - auf).total_seconds() / 60.0
        nach = (unter - mittag).total_seconds() / 60.0
        pruefe(abs(vor - nach) < 1.5,
               f"{tag}: {vor:.1f} min vor, {nach:.1f} min nach dem Hoechststand")
        pruefe(auf < mittag < unter, f"{tag}: Aufgang vor Mittag vor Untergang")
    print()


def test_suedhalbkugel() -> None:
    """Auf der Suedhalbkugel steht die Mittagssonne im Norden."""
    print("Suedhalbkugel")
    # Sydney, Hochsommer der Suedhalbkugel.
    sued = max(so.tagesverlauf(-33.87, 151.21, date(2026, 12, 21), 5, timezone.utc),
               key=lambda s: s.hoehe_geometrisch_grad)
    pruefe(sued.azimut_grad < 45.0 or sued.azimut_grad > 315.0,
           f"Sydney mittags im Norden ({sued.azimut_grad:.1f} Grad)")
    # Steht die Sonne hoch, ist die WAAGRECHTE Komponente klein -- der Vektor
    # zeigt fast senkrecht nach oben. Gepruefte Groesse ist deshalb die
    # Himmelsrichtung, nicht der Betrag.
    pruefe(sued.nord / math.hypot(sued.ost, sued.nord) > 0.9,
           f"und die Himmelsrichtung zeigt nach Norden "
           f"(nord/waagrecht={sued.nord / math.hypot(sued.ost, sued.nord):.2f})")
    pruefe(nahe(sued.hoehe_geometrisch_grad, 90.0 - 33.87 + 23.44, 0.4),
           f"mit der erwarteten Hoehe ({sued.hoehe_geometrisch_grad:.2f} Grad)")

    # Dieselbe Rechnung auf der Nordhalbkugel muss das Gegenteil ergeben.
    nord = hoechststand(date(2026, 6, 21))
    pruefe(nord.nord / math.hypot(nord.ost, nord.nord) < -0.9,
           f"Buchs AG zeigt mittags nach Sueden "
           f"(nord/waagrecht={nord.nord / math.hypot(nord.ost, nord.nord):.2f})")
    print()


def test_richtungsvektor() -> None:
    """Der Vektor muss zu Azimut und Hoehe passen -- sonst zeigt der Schatten
    woandershin als die Sonnenstandsangabe im Text."""
    print("Richtungsvektor")
    proben = [ortszeit(2026, 6, 21, 8), ortszeit(2026, 6, 21, 13, 30),
              ortszeit(2026, 6, 21, 19), ortszeit(2026, 12, 21, 12),
              ortszeit(2026, 3, 20, 6, 45)]
    for moment in proben:
        s = so.sonnenstand(LAT, LON, moment)
        laenge = math.sqrt(s.ost ** 2 + s.nord ** 2 + s.hoch ** 2)
        pruefe(nahe(laenge, 1.0, 1e-4),
               f"{moment:%H:%M}: Einheitsvektor (Laenge {laenge:.6f})")
        pruefe(nahe(math.degrees(math.asin(max(-1.0, min(1.0, s.hoch)))), s.hoehe_grad, 0.01),
               f"{moment:%H:%M}: hoch entspricht der Hoehe {s.hoehe_grad:.2f} Grad")
        az = math.degrees(math.atan2(s.ost, s.nord)) % 360.0
        pruefe(nahe(az, s.azimut_grad, 0.05) or nahe(abs(az - s.azimut_grad), 360.0, 0.05),
               f"{moment:%H:%M}: ost/nord entsprechen dem Azimut {s.azimut_grad:.1f} Grad")

    vormittag = so.sonnenstand(LAT, LON, ortszeit(2026, 6, 21, 8))
    nachmittag = so.sonnenstand(LAT, LON, ortszeit(2026, 6, 21, 18))
    pruefe(vormittag.ost > 0.4, f"Vormittags steht die Sonne im Osten (ost={vormittag.ost:.2f})")
    pruefe(nachmittag.ost < -0.4, f"Nachmittags im Westen (ost={nachmittag.ost:.2f})")
    print()


def test_zeitzone() -> None:
    """Sommerzeit ist kein Randfall -- sie gilt das halbe Jahr."""
    print("Zeitzone und Sommerzeit")

    geworfen = None
    try:
        so.sonnenstand(LAT, LON, datetime(2026, 6, 21, 12))
    except ValueError as exc:
        geworfen = exc
    pruefe(geworfen is not None,
           "Ein Zeitpunkt ohne Zonenangabe wird abgewiesen statt geraten")

    # Derselbe Augenblick, zweimal ausgedrueckt: das Ergebnis muss gleich sein.
    lokal = datetime(2026, 6, 21, 14, 0, tzinfo=CH)
    utc = lokal.astimezone(timezone.utc)
    a, b = so.sonnenstand(LAT, LON, lokal), so.sonnenstand(LAT, LON, utc)
    pruefe(a.azimut_grad == b.azimut_grad and a.hoehe_grad == b.hoehe_grad,
           "Ortszeit und UTC desselben Augenblicks ergeben denselben Sonnenstand")

    # Sommer- gegen Winterzeit: 13:30 Uhr ist nicht gleich 13:30 Uhr.
    sommer = so.sonnenstand(LAT, LON, datetime(2026, 6, 21, 13, 30, tzinfo=CH))
    winter = so.sonnenstand(LAT, LON, datetime(2026, 12, 21, 13, 30, tzinfo=CH))
    pruefe(sommer.zeit_lokal.endswith("+02:00"), f"Juni laeuft auf MESZ ({sommer.zeit_lokal})")
    pruefe(winter.zeit_lokal.endswith("+01:00"), f"Dezember auf MEZ ({winter.zeit_lokal})")

    z = so.sonnenzeiten(LAT, LON, date(2026, 6, 21), CH)
    pruefe(z["hoechststand"].endswith("+02:00") and "13:" in z["hoechststand"],
           f"Der Hoechststand liegt im Sommer nach 13 Uhr Ortszeit ({z['hoechststand']})")
    print()


def test_umstellungstage() -> None:
    """Die beiden Tage im Jahr, an denen 24 Stunden falsch waeren."""
    print("Umstellungstage")
    # 2026: Beginn der Sommerzeit am 29.03., Ende am 25.10.
    kurz = so.tagesverlauf(LAT, LON, date(2026, 3, 29), 60, CH)
    lang = so.tagesverlauf(LAT, LON, date(2026, 10, 25), 60, CH)
    normal = so.tagesverlauf(LAT, LON, date(2026, 6, 15), 60, CH)

    def spanne_h(v):
        return round((datetime.fromisoformat(v[-1].zeit_lokal)
                      - datetime.fromisoformat(v[0].zeit_lokal)).total_seconds() / 3600)

    pruefe(spanne_h(normal) == 24, f"Ein normaler Tag hat 24 Stunden ({spanne_h(normal)})")
    pruefe(spanne_h(kurz) == 23, f"Der Umstellungstag im Fruehling 23 ({spanne_h(kurz)})")
    pruefe(spanne_h(lang) == 25, f"Der im Herbst 25 ({spanne_h(lang)})")
    # Der Test, der den Fehler gefunden hat: die Stuetzstellen muessen in
    # ECHTEN Minuten gleich weit auseinanderliegen, nicht in Wanduhrzeit.
    pruefe(len(kurz) == 24 and len(normal) == 25 and len(lang) == 26,
           "und entsprechend weniger bzw. mehr Stuetzstellen "
           f"({len(kurz)}/{len(normal)}/{len(lang)}, erwartet 24/25/26)")
    for name, verlauf in [("Fruehling", kurz), ("Herbst", lang)]:
        zeiten = [datetime.fromisoformat(s.zeit_utc) for s in verlauf]
        abstaende = {round((zeiten[i + 1] - zeiten[i]).total_seconds() / 60)
                     for i in range(len(zeiten) - 1)}
        pruefe(abstaende == {60},
               f"{name}: alle Schritte sind echte 60 Minuten ({sorted(abstaende)})")
    print()


def test_nacht_und_refraktion() -> None:
    print("Nacht, Horizont und Refraktion")
    mitternacht = so.sonnenstand(LAT, LON, ortszeit(2026, 12, 21, 0, 0))
    pruefe(mitternacht.hoehe_grad < 0 and not mitternacht.ueber_horizont,
           f"Um Mitternacht steht die Sonne unter dem Horizont ({mitternacht.hoehe_grad:.1f} Grad)")
    pruefe(mitternacht.hoch < 0, "und der Richtungsvektor zeigt nach unten")

    mittag = so.sonnenstand(LAT, LON, ortszeit(2026, 6, 21, 13, 30))
    pruefe(mittag.ueber_horizont, "Mittags darueber")

    # Refraktion hebt die Sonne -- am Horizont stark, im Zenit nicht.
    verlauf = so.tagesverlauf(LAT, LON, date(2026, 6, 21), 5, CH)
    flach = min((s for s in verlauf if abs(s.hoehe_geometrisch_grad) < 1.0),
                key=lambda s: abs(s.hoehe_geometrisch_grad))
    pruefe(flach.hoehe_grad - flach.hoehe_geometrisch_grad > 0.4,
           f"Am Horizont hebt die Refraktion um ueber 0.4 Grad "
           f"({flach.hoehe_grad - flach.hoehe_geometrisch_grad:.2f})")
    hoch = max(verlauf, key=lambda s: s.hoehe_geometrisch_grad)
    pruefe(hoch.hoehe_grad - hoch.hoehe_geometrisch_grad < 0.02,
           "hoch am Himmel praktisch nicht "
           f"({hoch.hoehe_grad - hoch.hoehe_geometrisch_grad:.3f})")
    print()


def test_polargebiete() -> None:
    """Kein Absturz, wo die Sonne nicht auf- oder untergeht."""
    print("Polartag und Polarnacht")
    tag = so.sonnenzeiten(78.22, 15.65, date(2026, 6, 21), timezone.utc)      # Longyearbyen
    nacht = so.sonnenzeiten(78.22, 15.65, date(2026, 12, 21), timezone.utc)
    pruefe(tag["polartag"] and tag["aufgang"] is None,
           "Polartag wird als solcher gemeldet, nicht als fehlender Aufgang")
    pruefe(tag["tageslaenge_min"] == 1440, "mit 24 Stunden Tageslaenge")
    pruefe(nacht["polarnacht"] and nacht["tageslaenge_min"] == 0,
           "Polarnacht ebenso, mit 0 Minuten")
    pruefe(not tag["polarnacht"] and not nacht["polartag"],
           "und die beiden werden nicht verwechselt")
    print()


def test_tagesdaten() -> None:
    """Was die Ansicht bekommt."""
    print("Tagesdaten fuer die Ansicht")
    d = so.tagesdaten(LAT, LON, date(2026, 6, 21), 10, CH)

    pruefe(d["datum"] == "2026-06-21", "Das Datum steht in der Antwort")
    pruefe(d["utc_versatz_min"] == 120, f"Sommerzeitversatz 120 min ({d['utc_versatz_min']})")
    pruefe(len(d["verlauf"]) == 145,
           f"145 Stuetzstellen bei 10 Minuten Schrittweite ({len(d['verlauf'])})")
    pruefe(d["verlauf"][0]["zeit_lokal"].endswith("00:00+02:00"),
           "Der Verlauf beginnt an der lokalen Mitternacht")
    pruefe(all(isinstance(s["azimut_grad"], float) for s in d["verlauf"]),
           "Alle Stuetzstellen tragen einen Azimut")
    pruefe(d["quelle"].startswith("Berechnet nach"),
           "Die Herkunft der Rechnung ist benannt")

    hoehen = [s["hoehe_grad"] for s in d["verlauf"]]
    pruefe(max(hoehen) > 60 and min(hoehen) < -15,
           f"Der Tag laeuft von {min(hoehen):.1f} bis {max(hoehen):.1f} Grad")

    # Zwischen zwei Stuetzstellen darf sich die Sonne nicht sprunghaft bewegen,
    # sonst ruckelt die Interpolation in der Ansicht.
    groesster = max(abs(hoehen[i + 1] - hoehen[i]) for i in range(len(hoehen) - 1))
    pruefe(groesster < 2.5,
           f"Zwischen zwei Stuetzstellen aendert sich die Hoehe um hoechstens "
           f"{groesster:.2f} Grad -- fuer eine Zwischenwertbildung fein genug")

    geworfen = None
    try:
        so.tagesverlauf(LAT, LON, date(2026, 6, 21), 0, CH)
    except ValueError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "Eine unsinnige Schrittweite wird abgewiesen")
    print()


def test_schattenrichtung() -> None:
    """Der Schatten faellt der Sonne entgegen -- die Probe aufs Exempel."""
    print("Schattenrichtung")
    morgens = so.sonnenstand(LAT, LON, ortszeit(2026, 6, 21, 7))
    pruefe(morgens.ost > 0 and -morgens.ost < 0,
           f"Morgens steht die Sonne im Osten, der Schatten faellt nach Westen "
           f"(Sonne ost={morgens.ost:.2f})")

    mittags = so.sonnenstand(LAT, LON, ortszeit(2026, 6, 21, 13, 30))
    pruefe(mittags.nord < 0,
           f"Mittags steht sie im Sueden, der Schatten faellt nach Norden "
           f"(Sonne nord={mittags.nord:.2f})")

    # Die Schattenlaenge eines 10 m hohen Koerpers: 10 / tan(Hoehe).
    winter = hoechststand(date(2026, 12, 21))
    sommer = hoechststand(date(2026, 6, 21))
    l_winter = 10.0 / math.tan(math.radians(winter.hoehe_grad))
    l_sommer = 10.0 / math.tan(math.radians(sommer.hoehe_grad))
    pruefe(l_winter > 25.0,
           f"Ein 10-m-Haus wirft zur Winterwende mittags ueber 25 m Schatten "
           f"({l_winter:.1f} m)")
    pruefe(l_sommer < 5.0,
           f"zur Sommerwende unter 5 m ({l_sommer:.1f} m)")
    print()


def main() -> None:
    test_sonnenwenden()
    test_tagundnachtgleiche_ost_west()
    test_symmetrie()
    test_suedhalbkugel()
    test_richtungsvektor()
    test_zeitzone()
    test_umstellungstage()
    test_nacht_und_refraktion()
    test_polargebiete()
    test_tagesdaten()
    test_schattenrichtung()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE SONNENSTANDS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

"""
Regressionstests fuer den raeumlichen Kontext der 3D-Ansicht.

Vollstaendig OFFLINE -- die Netzabfragen werden durch Doubles ersetzt.

Geprueft wird, was fachlich schiefgehen kann:

  * Gebaeudehoehen duerfen NICHT geraten werden. Ohne GWR-Geschosszahl bleibt
    die Hoehe `None` und wird als solche gekennzeichnet.
  * Eigene und fremde Gebaeude muessen zuverlaessig getrennt werden -- sonst
    erscheint der Bestand doppelt (einmal aus dem Szenario, einmal aus der
    Umgebung).
  * Die Terrain-Interpolation muss auch dann einen Wert liefern, wenn der
    Hoehendienst einzelne Rasterpunkte nicht geliefert hat -- aber nie einen
    erfundenen, wenn gar nichts da ist.
  * Ein selbstschneidendes Katasterpolygon darf die Szene nicht kippen (live
    beobachtet: buffer(0) lieferte ein MultiPolygon ohne `exterior`).

CLI: python -m tests.test_umgebung
"""

from __future__ import annotations

import sys

from potenzial_engine import umgebung as um

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


OX, OY = 2600000.0, 1200000.0


def p(x: float, y: float) -> list[float]:
    return [OX + x, OY + y]


def terrain(hoehen, schritt=10.0, x0=None, y0=None):
    return {
        "hoehen": hoehen,
        "schrittweite_m": schritt,
        "ursprung_lv95": [x0 if x0 is not None else OX, y0 if y0 is not None else OY],
        "raster": len(hoehen),
    }


def gwr_punkt(x, y, **attrs):
    return {"geometry": {"type": "Point", "coordinates": p(x, y)},
            "properties": attrs}


def grundriss(ecken):
    return {"geometry": {"type": "Polygon", "coordinates": [[p(x, y) for x, y in ecken]]},
            "properties": {}}


# ---------------------------------------------------------------------------
# 1. Terrain-Interpolation
# ---------------------------------------------------------------------------

def test_hoehe_an() -> None:
    print("=== Terrain: bilinear, randfest, ohne erfundene Werte ===")
    # Ebene Flaeche auf 400 m.
    flach = terrain([[400.0] * 3 for _ in range(3)])
    pruefe(um.hoehe_an(flach, OX, OY) == 400.0, "Rasterpunkt trifft exakt")
    pruefe(um.hoehe_an(flach, OX + 5, OY + 5) == 400.0, "zwischen den Punkten ebenfalls 400")

    # Rampe: 400 unten, 410 oben (nach y).
    rampe = terrain([[400.0, 400.0], [410.0, 410.0]], schritt=10.0)
    pruefe(um.hoehe_an(rampe, OX, OY) == 400.0, "unten 400")
    pruefe(um.hoehe_an(rampe, OX, OY + 10) == 410.0, "oben 410")
    pruefe(um.hoehe_an(rampe, OX, OY + 5) == 405.0,
           f"in der Mitte 405 ({um.hoehe_an(rampe, OX, OY + 5)})")

    # Ausserhalb: auf den Rand klemmen, nicht extrapolieren.
    pruefe(um.hoehe_an(rampe, OX, OY + 500) == 410.0, "weit oberhalb wird auf den Rand geklemmt")
    pruefe(um.hoehe_an(rampe, OX, OY - 500) == 400.0, "weit unterhalb ebenso")

    # Fehlende Rasterpunkte: aus den vorhandenen Nachbarn, nicht geraten.
    loch = terrain([[400.0, None], [None, 410.0]], schritt=10.0)
    wert = um.hoehe_an(loch, OX + 5, OY + 5)
    pruefe(wert is not None and 400.0 <= wert <= 410.0,
           f"bei Loechern wird aus den vorhandenen Ecken gemittelt ({wert})")

    leer = terrain([[None, None], [None, None]])
    pruefe(um.hoehe_an(leer, OX, OY) is None,
           "ohne einen einzigen Hoehenwert gibt es keine Hoehe statt einer erfundenen")
    pruefe(um.hoehe_an({}, OX, OY) is None, "ohne Terrain ebenfalls None")
    print()


# ---------------------------------------------------------------------------
# 2. Gebaeude: Hoehe nur aus Geschossen, eigen von fremd getrennt
# ---------------------------------------------------------------------------

PARZELLE = [(OX, OY), (OX + 20, OY), (OX + 20, OY + 20), (OX, OY + 20)]


def test_gebaeude() -> None:
    print("=== Gebaeude: Hoehe nur aus Geschossen, eigen getrennt von fremd ===")
    gwr = [
        gwr_punkt(10, 10, egid="111", gastw="2", gbauj="1918", strname_deinr="Rosenweg 4"),
        gwr_punkt(50, 10, egid="222", gastw="4"),
        # Zweiter Eintrag im selben Nachbargebaeude, weniger Geschosse.
        gwr_punkt(52, 12, egid="223", gastw="2"),
    ]
    grundrisse = [
        grundriss([(5, 5), (15, 5), (15, 15), (5, 15)]),        # auf der Parzelle
        grundriss([(45, 5), (60, 5), (60, 20), (45, 20)]),      # Nachbar mit GWR
        grundriss([(80, 5), (90, 5), (90, 15), (80, 15)]),      # Nachbar OHNE GWR
    ]
    gebaeude = um.werte_gebaeude_aus(gwr, grundrisse, PARZELLE, geschosshoehe_m=3.0)
    pruefe(len(gebaeude) == 3, f"3 Gebaeude ausgewertet ({len(gebaeude)})")

    eigen = [g for g in gebaeude if g["eigen"]]
    fremd = [g for g in gebaeude if not g["eigen"]]
    pruefe(len(eigen) == 1, f"genau ein eigenes Gebaeude ({len(eigen)})")
    pruefe(eigen[0]["egid"] == "111", f"und zwar das richtige ({eigen[0]['egid']})")
    pruefe(eigen[0]["hoehe_m"] == 6.0, f"2 Geschosse x 3.0 m = 6.0 m ({eigen[0]['hoehe_m']})")
    pruefe(eigen[0]["baujahr"] == 1918, "Baujahr uebernommen")
    pruefe(eigen[0]["adresse"] == "Rosenweg 4", "Adresse uebernommen")
    pruefe(len(fremd) == 2, f"zwei Nachbargebaeude ({len(fremd)})")

    mit_gwr = next(g for g in fremd if g["egid"])
    pruefe(mit_gwr["geschosse"] == 4,
           f"von mehreren Eintraegen gilt die groesste Geschosszahl ({mit_gwr['geschosse']})")
    pruefe(mit_gwr["hoehe_m"] == 12.0, "und daraus die Hoehe")

    ohne_gwr = next(g for g in fremd if not g["egid"])
    pruefe(ohne_gwr["hoehe_m"] is None, "ohne GWR-Eintrag KEINE Hoehe")
    pruefe(ohne_gwr["hoehe_quelle"] == um.HOEHE_NICHT_BESTIMMBAR,
           f"und das ist gekennzeichnet ({ohne_gwr['hoehe_quelle']})")
    pruefe(ohne_gwr["geschosse"] is None, "auch keine erfundene Geschosszahl")
    pruefe(mit_gwr["hoehe_quelle"] == um.HOEHE_AUS_GESCHOSSEN, "bekannte Hoehe nennt ihre Quelle")

    # Eine andere Geschosshoehen-Annahme schlaegt durch.
    hoeher = um.werte_gebaeude_aus(gwr, grundrisse, PARZELLE, geschosshoehe_m=3.5)
    pruefe(next(g for g in hoeher if g["eigen"])["hoehe_m"] == 7.0,
           "geaenderte Geschosshoehe wirkt auf die Hoehe")

    # Winzige Splitter sind keine Gebaeude.
    splitter = um.werte_gebaeude_aus([], [grundriss([(0, 0), (1, 0), (1, 1), (0, 1)])], PARZELLE)
    pruefe(splitter == [], "ein 1 m2 grosser Splitter wird nicht als Gebaeude gefuehrt")
    print()


# ---------------------------------------------------------------------------
# 3. Gesamtszene mit Doubles
# ---------------------------------------------------------------------------

def test_szene() -> None:
    print("=== Gesamtszene: alles auf dem Terrain, Fehlendes benannt ===")

    def identify_double(e, n, layer, tolerance=5, return_geometry=False):
        from potenzial_engine.bestand import LAYER_GEBAEUDE_GRUNDRISS
        from potenzial_engine.modul1_geodata import LAYER_CADASTRE_GEOM, LAYER_GWR
        if layer == LAYER_GWR:
            return [gwr_punkt(10, 10, egid="111", gastw="2")]
        if layer == LAYER_GEBAEUDE_GRUNDRISS:
            return [grundriss([(5, 5), (15, 5), (15, 15), (5, 15)]),
                    grundriss([(45, 5), (60, 5), (60, 20), (45, 20)])]
        if layer == LAYER_CADASTRE_GEOM:
            return [
                {"geometry": {"type": "Polygon",
                              "coordinates": [[p(x, y) for x, y in
                                               [(0, 0), (20, 0), (20, 20), (0, 20)]]]},
                 "properties": {"number": "100", "egris_egrid": "CH000000000001"}},
                {"geometry": {"type": "Polygon",
                              "coordinates": [[p(x, y) for x, y in
                                               [(40, 0), (70, 0), (70, 30), (40, 30)]]]},
                 "properties": {"number": "101", "egris_egrid": "CH000000000002"}},
                # Selbstschneidend -- buffer(0) liefert ein MultiPolygon.
                {"geometry": {"type": "Polygon",
                              "coordinates": [[p(x, y) for x, y in
                                               [(0, 40), (20, 60), (20, 40), (0, 60), (0, 40)]]]},
                 "properties": {"number": "102", "egris_egrid": "CH000000000003"}},
            ]
        if layer == um.LAYER_STRASSEN:
            return [{"geometry": {"type": "LineString",
                                  "coordinates": [p(-10, 30), p(80, 30)]},
                     "properties": {"strassenname": "Dorfstrasse", "objektart": 11}}]
        return []

    def terrain_double(e, n, radius_m=um.STANDARD_RADIUS_M, raster=um.STANDARD_RASTER):
        return {
            "gefunden": True, "raster": 4, "radius_m": radius_m, "schrittweite_m": 40.0,
            "ursprung_lv95": [OX - 40, OY - 40],
            "hoehen": [[400.0 + i for _ in range(4)] for i in range(4)],
            "min_hoehe_m": 400.0, "max_hoehe_m": 403.0,
            "quelle": "Testdouble", "hinweise": [],
        }

    o_identify, o_terrain = um._identify, um.hole_terrain
    um._identify, um.hole_terrain = identify_double, terrain_double
    try:
        szene = um.hole_umgebung(OX + 10, OY + 10, PARZELLE,
                                 eigenes_egrid="CH000000000001")
    finally:
        um._identify, um.hole_terrain = o_identify, o_terrain

    st = szene["statistik"]
    pruefe(st["gebaeude"] == 2, f"2 Gebaeude ({st['gebaeude']})")
    pruefe(st["gebaeude_eigen"] == 1, f"eines davon eigen ({st['gebaeude_eigen']})")
    pruefe(st["gebaeude_ohne_hoehe"] == 1, f"eines ohne Hoehe ({st['gebaeude_ohne_hoehe']})")
    pruefe(st["nachbarparzellen"] == 2,
           f"2 Nachbarparzellen -- die eigene ist raus ({st['nachbarparzellen']})")
    pruefe(st["strassenabschnitte"] == 1, "1 Strassenabschnitt")

    pruefe(all(g["terrain_hoehe_m"] is not None for g in szene["gebaeude"]),
           "jedes Gebaeude sitzt auf einer Terrainhoehe")
    pruefe(all(p_["terrain_hoehe_m"] is not None for p_ in szene["nachbarparzellen"]),
           "jede Nachbarparzelle ebenfalls")
    strasse = szene["strassen"][0]
    pruefe(len(strasse["hoehen_m"]) == len(strasse["koordinaten"]),
           "jede Strassenstuetzstelle hat ihre Hoehe")
    pruefe(len(szene["parzelle"]["terrain_hoehen_m"]) == len(PARZELLE),
           "die eigene Parzelle folgt dem Gelaende")

    pruefe(any("ohne bekannte Geschosszahl" in h for h in szene["hinweise"]),
           "fehlende Gebaeudehoehen stehen in den Hinweisen")
    pruefe("terrain" in szene["quellen"] and "strassen" in szene["quellen"],
           "jede Quelle ist benannt")

    # Das selbstschneidende Polygon hat die Szene nicht gekippt.
    pruefe(st["nachbarparzellen"] == 2,
           "das selbstschneidende Katasterpolygon wurde repariert oder verworfen, nicht geworfen")

    geworfen = None
    try:
        um.hole_umgebung(OX, OY, [])
    except um.UmgebungError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "ohne Parzellengeometrie wird sauber abgelehnt")
    print()


def test_terrain_raster() -> None:
    print("=== Terrainraster: Aufbau und Fehlerfall ===")
    gerufen = []

    def profil_double(x_von, x_bis, y, punkte):
        gerufen.append(y)
        return [400.0 + i for i in range(punkte)]

    original = um._profil_zeile
    um._profil_zeile = profil_double
    try:
        t = um.hole_terrain(OX, OY, radius_m=100.0, raster=5)
    finally:
        um._profil_zeile = original

    pruefe(len(gerufen) == 5, f"eine Anfrage je Rasterzeile, nicht je Punkt ({len(gerufen)})")
    pruefe(t["raster"] == 5 and len(t["hoehen"]) == 5, "5x5-Raster aufgebaut")
    pruefe(t["schrittweite_m"] == 50.0, f"Maschenweite 200/4 = 50 m ({t['schrittweite_m']})")
    pruefe(t["ursprung_lv95"] == [OX - 100, OY - 100], "Ursprung unten links")
    pruefe(t["min_hoehe_m"] == 400.0 and t["max_hoehe_m"] == 404.0, "Hoehenbereich stimmt")

    def leer_double(x_von, x_bis, y, punkte):
        return [None] * punkte

    um._profil_zeile = leer_double
    try:
        geworfen = None
        try:
            um.hole_terrain(OX, OY, raster=4)
        except um.UmgebungError as exc:
            geworfen = exc
        pruefe(geworfen is not None,
               "liefert der Hoehendienst gar nichts, wird die Szene nicht aufgebaut")
    finally:
        um._profil_zeile = original

    geworfen = None
    try:
        um.hole_terrain(OX, OY, raster=1)
    except um.UmgebungError as exc:
        geworfen = exc
    pruefe(geworfen is not None, "ein Raster unter 2 wird abgelehnt")
    print()


def main() -> None:
    test_hoehe_an()
    test_gebaeude()
    test_terrain_raster()
    test_szene()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE UMGEBUNGS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

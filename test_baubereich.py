"""
G1-Testmatrix fuer den Geometrie-Kernel (baubereich.py).

Laueft komplett OHNE Netzwerkzugriff -- alle Parzellen-/Restriktions-
geometrien sind synthetisch (lokale Koordinaten, keine echten LV95-Punkte
noetig, da der Kernel selbst netzwerkfrei ist).

Testfaelle (Nummerierung folgt der mit dem Nutzer abgestimmten Testmatrix):
  T1  Rechteck, einheitlicher Grenzabstand
  T2  L-Form (konkav), einheitlicher Grenzabstand
  T3  Rechteck, unterschiedliche Grenzabstaende je Kante
  T4  Restriktionsflaeche (synthetischer Gewaesserraum) wird abgezogen
  T5  Sondernutzungsplan-Blockierung -- bereits vollstaendig in
      test_klassifikation.py abgedeckt (22/22 gruen), hier nicht dupliziert,
      da G1 rein geometrisch ist und die SNP-Sperre in Modul 3 sitzt.
  T6  Ueberbauungsziffer (UZ) limitiert den Fussabdruck staerker als die Geometrie
  T7  Baumassenziffer (BMZ) limitiert die Geschossflaeche staerker als AZ
  T8  Gebaeudehoehe limitiert die Geschosszahl staerker als Vollgeschosse
  T9  Ausnuetzungsziffer (AZ) limitiert die Geschossflaeche staerker als die Geometrie
  T10 Mehrlaengenzuschlag erhoeht den effektiven Grenzabstand einer langen Kante

CLI: python test_baubereich.py
"""

from __future__ import annotations

import sys

from shapely.geometry import Polygon

from baubereich import berechne_baubereich_polygon, berechne_potenzial

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    status = "OK  " if bedingung else "FAIL"
    print(f"  [{status}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def nahe(a: float, b: float, toleranz: float = 0.05) -> bool:
    return abs(a - b) <= toleranz


def test_t1_rechteck_einheitlich() -> None:
    print("=== T1: Rechteck 40x30, einheitlicher Grenzabstand 5m ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]
    baubereich, protokoll = berechne_baubereich_polygon(rechteck, [5, 5, 5, 5])
    erwartet = 30 * 20  # (40-2*5) x (30-2*5)
    pruefe(nahe(baubereich.area, erwartet), f"Baubereich-Flaeche = {baubereich.area:.1f} m2 (erwartet {erwartet})")

    # Unabhaengige Gegenprobe: fuer achsenparallele Rechtecke mit EINHEITLICHEM
    # Abstand entspricht der Halbebenen-Schnitt exakt einem negativen Buffer
    # mit rechtwinkligem (mitre) Join -- andere Berechnungsmethode als Kontrolle.
    ref = Polygon(rechteck).buffer(-5, join_style=2)
    pruefe(nahe(baubereich.area, ref.area), f"Deckt sich mit unabhaengiger buffer(-5)-Gegenprobe ({ref.area:.1f} m2)")

    ergebnis = berechne_potenzial(
        rechteck, [5, 5, 5, 5], ausnuetzungsziffer_az=0.5, vollgeschosse_max=3,
    )
    pruefe(nahe(ergebnis.fussabdruck_m2, erwartet), f"Fussabdruck = {ergebnis.fussabdruck_m2} m2")
    pruefe(ergebnis.fussabdruck_limitiert_durch == "geometrie", "Fussabdruck limitiert durch Geometrie (keine UZ vorgegeben)")
    pruefe(ergebnis.geschosszahl == 3, "Geschosszahl = 3 (nur Vollgeschosse vorgegeben)")
    pruefe(
        nahe(ergebnis.geschossflaeche_m2, 0.5 * 1200),
        f"Geschossflaeche = {ergebnis.geschossflaeche_m2} m2 (AZ 0.5 x 1200 m2 Parzelle = 600)",
    )
    pruefe(ergebnis.geschossflaeche_limitiert_durch == "ausnuetzung_az", "Geschossflaeche limitiert durch AZ (600 < 600*3 Geometrie)")
    print()


def test_t2_l_form_konkav() -> None:
    print("=== T2: L-Form (konkav), einheitlicher Grenzabstand 2m ===")
    # Aussenquadrat 20x20 minus 10x10-Kerbe oben rechts -> Flaeche 300 m2, konkav.
    l_form = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]
    pruefe(nahe(Polygon(l_form).area, 300), "Testpolygon selbst hat Flaeche 300 m2 (Sanity-Check)")

    baubereich, protokoll = berechne_baubereich_polygon(l_form, [2, 2, 2, 2, 2, 2])
    pruefe(not baubereich.is_empty, "Baubereich nicht leer")
    pruefe(baubereich.is_valid, "Baubereich ist ein valides Polygon")

    # Unabhaengige Gegenprobe wie bei T1: bei EINHEITLICHEM Abstand und einer
    # rechtwinklig-konkaven Parzelle (90 Grad Reflex-Ecke) entspricht der
    # Halbebenen-Schnitt weiterhin exakt einem negativen Mitre-Buffer.
    ref = Polygon(l_form).buffer(-2, join_style=2)
    pruefe(
        nahe(baubereich.area, ref.area, toleranz=0.5),
        f"Flaeche {baubereich.area:.2f} m2 deckt sich mit unabhaengiger buffer(-2)-Gegenprobe ({ref.area:.2f} m2)",
    )
    # Konkave Ecke (10,10) muss weiterhin nach innen (Richtung Parzelleninneres)
    # eingezogen sein, nicht nach aussen ausgebeult -- Test der korrekten
    # Normalen-Richtungsbestimmung an der Reflex-Ecke.
    pruefe(baubereich.area < 300, "Baubereich kleiner als Ausgangsparzelle (Erosion hat gewirkt)")
    print()


def test_t3_rechteck_ungleiche_abstaende() -> None:
    print("=== T3: Rechteck 40x30, unterschiedliche Grenzabstaende je Kante ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]
    # Kante0 unten (+y rein) =5, Kante1 rechts (-x rein) =8, Kante2 oben (-y rein) =2, Kante3 links (+x rein) =3
    baubereich, protokoll = berechne_baubereich_polygon(rechteck, [5, 8, 2, 3])
    minx, miny, maxx, maxy = baubereich.bounds
    pruefe(nahe(minx, 3), f"x_min = {minx:.2f} (erwartet 3, Kante links=3)")
    pruefe(nahe(maxx, 32), f"x_max = {maxx:.2f} (erwartet 32 = 40-8, Kante rechts=8)")
    pruefe(nahe(miny, 5), f"y_min = {miny:.2f} (erwartet 5, Kante unten=5)")
    pruefe(nahe(maxy, 28), f"y_max = {maxy:.2f} (erwartet 28 = 30-2, Kante oben=2)")
    erwartete_flaeche = (32 - 3) * (28 - 5)
    pruefe(nahe(baubereich.area, erwartete_flaeche), f"Flaeche = {baubereich.area:.1f} m2 (erwartet {erwartete_flaeche})")
    print()


def test_t4_restriktionsflaeche() -> None:
    print("=== T4: Rechteck mit synthetischer Restriktionsflaeche (Gewaesserraum) ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]
    baubereich_ohne, _ = berechne_baubereich_polygon(rechteck, [2, 2, 2, 2])
    # baubereich_ohne = (40-4)x(30-4) = 36x26, Bounds x:[2,38] y:[2,28]

    # Restriktion: 5x5-Streifen vollstaendig innerhalb des Baubereichs, ohne
    # dessen Rand zu beruehren -> einfache, exakt vorhersagbare Ueberlappung.
    restriktion = [(10, 10), (15, 10), (15, 15), (10, 15)]

    ergebnis = berechne_potenzial(
        rechteck, [2, 2, 2, 2],
        restriktionsflaechen=[restriktion],
        ausnuetzungsziffer_az=0.4,
        vollgeschosse_max=2,
    )
    pruefe(
        nahe(ergebnis.baubereich_vor_restriktion_m2, baubereich_ohne.area),
        f"Baubereich vor Restriktion unveraendert ({ergebnis.baubereich_vor_restriktion_m2} m2)",
    )
    erwartet_nach = baubereich_ohne.area - 25  # 5x5 Restriktion komplett abgezogen
    pruefe(
        nahe(ergebnis.baubereich_m2, erwartet_nach),
        f"Baubereich nach Restriktion = {ergebnis.baubereich_m2} m2 (erwartet {erwartet_nach})",
    )
    pruefe(
        nahe(ergebnis.anrechenbare_landflaeche_m2, 1200 - 25),
        f"Anrechenbare Landflaeche = {ergebnis.anrechenbare_landflaeche_m2} m2 (1200 Parzelle - 25 Restriktion)",
    )
    pruefe(
        any("Restriktionsflaechen" in h for h in ergebnis.hinweise),
        "Hinweis zur Restriktions-Annahme wird transparent ausgewiesen",
    )
    print()


def test_t6_ueberbauungsziffer_limitiert() -> None:
    print("=== T6: Ueberbauungsziffer (UZ) limitiert den Fussabdruck ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]  # Parzelle 1200 m2
    ergebnis = berechne_potenzial(
        rechteck, [1, 1, 1, 1],  # kleiner Abstand -> grosser geometrischer Baubereich (~1224*... )
        ueberbauungsziffer_uz=0.2,  # UZ-Deckel = 0.2*1200 = 240 m2, deutlich kleiner als Geometrie
        ausnuetzungsziffer_az=0.8,
        vollgeschosse_max=3,
    )
    pruefe(ergebnis.fussabdruck_limitiert_durch == "ueberbauungsziffer", f"Fussabdruck limitiert durch UZ (kandidaten={ergebnis.fussabdruck_kandidaten})")
    pruefe(nahe(ergebnis.fussabdruck_m2, 240), f"Fussabdruck = {ergebnis.fussabdruck_m2} m2 (erwartet 240)")
    print()


def test_t7_baumassenziffer_limitiert() -> None:
    print("=== T7: Baumassenziffer (BMZ) limitiert die Geschossflaeche ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]  # 1200 m2
    ergebnis = berechne_potenzial(
        rechteck, [2, 2, 2, 2],
        ausnuetzungsziffer_az=5.0,  # bewusst sehr hoch -> AZ bindet nicht
        baumassenziffer_bmz=1.5,  # BMZ-Deckel (Flaeche) = 1.5*1200/3.0 = 600 m2
        vollgeschosse_max=10,
        geschosshoehe_m=3.0,
    )
    pruefe(ergebnis.geschossflaeche_limitiert_durch == "baumasse", f"Geschossflaeche limitiert durch BMZ (kandidaten={ergebnis.geschossflaeche_kandidaten})")
    pruefe(nahe(ergebnis.geschossflaeche_m2, 600), f"Geschossflaeche = {ergebnis.geschossflaeche_m2} m2 (erwartet 600)")
    print()


def test_t8_hoehe_limitiert_geschosszahl() -> None:
    print("=== T8: Gebaeudehoehe limitiert die Geschosszahl staerker als Vollgeschosse ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]
    ergebnis = berechne_potenzial(
        rechteck, [2, 2, 2, 2],
        vollgeschosse_max=6,  # erlaubt 6 Geschosse
        gebaeudehoehe_m=9.5,  # bei 3.0m Geschosshoehe nur 3 Geschosse
        geschosshoehe_m=3.0,
        ausnuetzungsziffer_az=5.0,  # AZ bewusst hoch -> bindet nicht
    )
    pruefe(ergebnis.geschosszahl_limitiert_durch == "hoehe", f"Geschosszahl limitiert durch Hoehe (kandidaten={ergebnis.geschosszahl_kandidaten})")
    pruefe(ergebnis.geschosszahl == 3, f"Geschosszahl = {ergebnis.geschosszahl} (erwartet 3 = floor(9.5/3.0))")
    pruefe(
        ergebnis.geschossflaeche_limitiert_durch == "fussabdruck_x_geschosse",
        "Geschossflaeche folgt aus Fussabdruck x Geschosszahl (nicht aus AZ, die bewusst nicht bindet)",
    )
    print()


def test_t9_az_limitiert_staerker_als_geometrie() -> None:
    print("=== T9: Ausnuetzungsziffer (AZ) limitiert staerker als Geometrie/Hoehe ===")
    rechteck = [(0, 0), (40, 0), (40, 30), (0, 30)]  # 1200 m2
    ergebnis = berechne_potenzial(
        rechteck, [1, 1, 1, 1],  # kleiner Abstand -> grosser Fussabdruck
        vollgeschosse_max=8,
        gebaeudehoehe_m=30.0,
        geschosshoehe_m=3.0,  # 10 Geschosse aus Hoehe, 8 aus Vollgeschossen -> min=8
        ausnuetzungsziffer_az=0.3,  # AZ-Deckel = 0.3*1200 = 360 m2, klar restriktiver
    )
    pruefe(ergebnis.geschosszahl == 8, f"Geschosszahl = {ergebnis.geschosszahl} (Vollgeschosse bindet vor Hoehe)")
    pruefe(
        ergebnis.geschossflaeche_limitiert_durch == "ausnuetzung_az",
        f"Geschossflaeche limitiert durch AZ (kandidaten={ergebnis.geschossflaeche_kandidaten})",
    )
    pruefe(nahe(ergebnis.geschossflaeche_m2, 360), f"Geschossflaeche = {ergebnis.geschossflaeche_m2} m2 (erwartet 360)")
    print()


def test_t10_mehrlaengenzuschlag() -> None:
    print("=== T10: Mehrlaengenzuschlag erhoeht effektiven Grenzabstand einer langen Kante ===")
    # Lange Parzelle: eine Kante (unten, 60m) ueberschreitet die Schwelle von 25m.
    rechteck = [(0, 0), (60, 0), (60, 20), (0, 20)]
    ohne_zuschlag = berechne_potenzial(rechteck, [4, 4, 4, 4])
    mit_zuschlag = berechne_potenzial(
        rechteck, [4, 4, 4, 4],
        mehrlaengenzuschlag_schwelle_m=25.0,
        mehrlaengenzuschlag_zuschlag_pro_m=0.1,  # +0.1m Abstand je Meter Ueberlaenge
    )
    erwarteter_effektiver_abstand = 4 + (60 - 25) * 0.1  # = 7.5
    pruefe(
        nahe(mit_zuschlag.effektive_kanten_abstaende[0], erwarteter_effektiver_abstand),
        f"Effektiver Abstand Kante 0 = {mit_zuschlag.effektive_kanten_abstaende[0]:.2f} m (erwartet {erwarteter_effektiver_abstand:.2f})",
    )
    pruefe(
        mit_zuschlag.baubereich_m2 < ohne_zuschlag.baubereich_m2,
        f"Baubereich mit Zuschlag ({mit_zuschlag.baubereich_m2} m2) kleiner als ohne ({ohne_zuschlag.baubereich_m2} m2)",
    )
    pruefe(
        any("Mehrlaengenzuschlag" in h for h in mit_zuschlag.hinweise),
        "Mehrlaengenzuschlag-Naeherung wird transparent als Hinweis ausgewiesen",
    )
    # Kurze Kanten (Seiten, 20m < Schwelle 25m) bleiben unveraendert.
    pruefe(
        nahe(mit_zuschlag.effektive_kanten_abstaende[1], 4.0),
        "Kurze Kante (< Schwelle) bleibt beim Basis-Grenzabstand",
    )
    print()


def main() -> None:
    test_t1_rechteck_einheitlich()
    test_t2_l_form_konkav()
    test_t3_rechteck_ungleiche_abstaende()
    test_t4_restriktionsflaeche()
    test_t6_ueberbauungsziffer_limitiert()
    test_t7_baumassenziffer_limitiert()
    test_t8_hoehe_limitiert_geschosszahl()
    test_t9_az_limitiert_staerker_als_geometrie()
    test_t10_mehrlaengenzuschlag()

    print("=" * 60)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE G1-TESTS BESTANDEN (9/9 synthetisch + T5 bereits in test_klassifikation.py)")


if __name__ == "__main__":
    main()

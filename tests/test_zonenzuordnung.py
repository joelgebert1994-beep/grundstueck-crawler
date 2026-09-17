"""
Zonenzuordnung: amtliche Bezeichnung <-> Zonentabelle des Reglements.

Vollstaendig OFFLINE. Beide Zonentabellen sind echte Auswertungen echter
Baureglemente (Rheineck SG und Rorschach SG, aus dem Zwischenspeicher der
Datenschicht uebernommen), die Geometrien stammen aus der echten Abfrage
zur Parzelle 160 in Rheineck.

Der Fall, an dem der Fehler sichtbar wurde
------------------------------------------
Buhofstrasse 55, 9424 Rheineck. Amtlich ist die Parzelle "BauG_Wohnzone W2",
das Reglement fuehrt "Wohnzone, 2 Vollgeschosse (W2)" mit Ausnuetzungsziffer
0.45. Dieselbe Zone, zwei Schreibweisen -- die Zuordnung scheiterte trotzdem:

    normiert  "baug wohnzone w2"             (16 Zeichen)
    normiert  "wohnzone 2 vollgeschosse w2"  (27 Zeichen)
    gemeinsam "wohnzone " (9) + "w2" (2)     = 11 Zeichen
    difflib   2 * 11 / 43                    = 0.51   <  Schwelle 0.55

Von diesen 0.51 entfallen auf das "w2" -- das Einzige, was die Zone
ueberhaupt entscheidet -- 0.09. Den Rest bestimmt Beiwerk: das kantonale
Praefix "BauG_" auf der einen, die ausgeschriebene Geschosszahl auf der
anderen Seite.

Warum die Schwelle NICHT die Stellschraube ist
----------------------------------------------
In Rorschach erreicht "G - Gruenzone" gegen "BauG_Wohnzone W2" eine
Aehnlichkeit von 0.54 -- ein Hundertstel unter der Schwelle. Wer sie auf
0.50 senkt, ordnet einer Wohnparzelle eine Gruenzone zu und rechnet
anschliessend eine vollstaendige, aber falsche Kennzahlentabelle daraus.
Das ist schlimmer als ein ehrliches "unsicher".

Die Regel, die stattdessen gilt
-------------------------------
Das Zonenkuerzel ist exakt. Steht auf beiden Seiten "W2", ist es dieselbe
Zone -- unabhaengig davon, wie die Gemeinde sie ausschreibt und an welcher
Stelle sie das Kuerzel setzt. Gibt es kein Kuerzel, oder fuehren mehrere
Zonen dasselbe, entscheidet weiterhin der Text bzw. es bleibt offen.

CLI: python -m tests.test_zonenzuordnung
"""

from __future__ import annotations

import sys

from potenzial_engine.modul3_financial import (
    ZONE_MATCH_MIN_SIMILARITY,
    _ermittle_basiszone_bezeichnung,
    _zonencodes,
    match_zone,
)

FEHLER: list[str] = []


def pruefe(bedingung: bool, beschreibung: str) -> None:
    print(f"  [{'OK  ' if bedingung else 'FAIL'}] {beschreibung}")
    if not bedingung:
        FEHLER.append(beschreibung)


def amtlich(name: str) -> list[dict]:
    return [{"zonenbezeichnung": name, "ist_wahrscheinlich_basiszone": True}]


# --- Echte Zonentabelle Rheineck SG (Baureglement Stadt Rheineck) -----------
# Kuerzel in Klammern am Ende.
RHEINECK_ZONEN = [
    {"zonenbezeichnung": 'Kernzone (K)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Wohnzone, 2 Vollgeschosse (W2)',
     "ausnuetzungsziffer_az": {"wert": 0.45}},
    {"zonenbezeichnung": 'Wohnzone Hanglage, 2 Vollgeschosse (W2H)',
     "ausnuetzungsziffer_az": {"wert": 0.4}},
    {"zonenbezeichnung": 'Wohnzone, 3 Vollgeschosse (W3)',
     "ausnuetzungsziffer_az": {"wert": 0.65}},
    {"zonenbezeichnung": 'Wohnzone, 4 Vollgeschosse (W4)',
     "ausnuetzungsziffer_az": {"wert": 0.75}},
    {"zonenbezeichnung": 'Wohn-Gewerbezone, 2 Vollgeschosse (WG2)',
     "ausnuetzungsziffer_az": {"wert": 0.55}},
    {"zonenbezeichnung": 'Wohn-Gewerbezone, 3 Vollgeschosse (WG3)',
     "ausnuetzungsziffer_az": {"wert": 0.75}},
    {"zonenbezeichnung": 'Gewerbe-Industriezone (GI)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Industriezone (IZ)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Zone für öffentliche Bauten und Anlagen (OeZ / OeBA)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Grünzone Freihaltung (GF)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Grünzone Gärten (GG)',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Landwirtschaftszone / Übriges Gemeindegebiet (LW / UeG)',
     "ausnuetzungsziffer_az": {"wert": None}},
]

# --- Echte Zonentabelle Rorschach SG ---------------------------------------
# Kuerzel VORANGESTELLT -- dieselbe Information, andere Schreibweise. Genau
# darum darf die Erkennung nicht an der Position des Kuerzels haengen.
RORSCHACH_ZONEN = [
    {"zonenbezeichnung": 'W2 - Wohnzone 2 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": 0.4}},
    {"zonenbezeichnung": 'W3 - Wohnzone 3 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": 0.7}},
    {"zonenbezeichnung": 'W4 - Wohnzone 4 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": 0.85}},
    {"zonenbezeichnung": 'WZ3 - Wohnzone für zentrumsnahes Wohnen 3 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'WZ4 - Wohnzone für zentrumsnahes Wohnen 4 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'WG3 - Wohn-Gewerbezone 3 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": 0.7}},
    {"zonenbezeichnung": 'WG4 - Wohn-Gewerbezone 4 Vollgeschosse',
     "ausnuetzungsziffer_az": {"wert": 0.85}},
    {"zonenbezeichnung": 'GI - Gewerbe-Industriezone',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'K - Kernzone',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'KA - Kernzone Altstadt',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'KO - Kernzone Ost',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'SPZF - Schwerpunktzone Feldmühle-Areal',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'SPZS - Schwerpunktzone Stadtbahnhof Süd',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'KU - Kurzone',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'G - Grünzone',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'Oe - Zone für öffentliche Bauten und Anlagen',
     "ausnuetzungsziffer_az": {"wert": None}},
    {"zonenbezeichnung": 'UeG - Übriges Gemeindegebiet',
     "ausnuetzungsziffer_az": {"wert": None}},
]

# --- Echte Geometrie: Parzelle 160 und die beiden Grundnutzungen -----------
# Die Punktabfrage von Modul 1b fand hier ZWEI rechtskraeftige
# Grundnutzungen, weil die Zonengrenze direkt an der Parzelle verlaeuft.
RHEINECK_PARZELLE = [
    [2761214.8, 1259841.5], [2761230.6, 1259842.8], [2761231.8, 1259824.6], [2761215.8,
    1259823.5], [2761214.8, 1259841.5]
]
RHEINECK_WOHNZONE_W2 = [
    [2761215.773, 1259823.52], [2761207.335, 1259815.231], [2761192.007, 1259830.92],
    [2761193.159, 1259831.883], [2761193.016, 1259832.003], [2761192.878, 1259832.128],
    [2761192.745, 1259832.26], [2761192.618, 1259832.396], [2761192.496, 1259832.537],
    [2761192.38, 1259832.683], [2761192.27, 1259832.833], [2761192.166, 1259832.988],
    [2761192.068, 1259833.147], [2761191.977, 1259833.31], [2761191.892, 1259833.476],
    [2761191.814, 1259833.645], [2761191.743, 1259833.817], [2761191.679, 1259833.992],
    [2761191.621, 1259834.17], [2761191.571, 1259834.35], [2761191.528, 1259834.531],
    [2761191.493, 1259834.714], [2761191.465, 1259834.899], [2761191.444, 1259835.084],
    [2761191.431, 1259835.27], [2761191.425, 1259835.456], [2761191.427, 1259835.643],
    [2761191.436, 1259835.829], [2761191.452, 1259836.015], [2761191.476, 1259836.2],
    [2761191.507, 1259836.384], [2761191.546, 1259836.566], [2761191.592, 1259836.747],
    [2761191.646, 1259836.928], [2761191.707, 1259837.107], [2761191.776, 1259837.283],
    [2761191.851, 1259837.456], [2761191.934, 1259837.626], [2761192.023, 1259837.792],
    [2761192.119, 1259837.955], [2761192.221, 1259838.113], [2761192.33, 1259838.268],
    [2761192.445, 1259838.418], [2761192.566, 1259838.563], [2761192.693, 1259838.703],
    [2761192.825, 1259838.838], [2761192.963, 1259838.967], [2761193.106, 1259839.091],
    [2761193.253, 1259839.208], [2761193.406, 1259839.32], [2761193.562, 1259839.425],
    [2761193.723, 1259839.524], [2761193.888, 1259839.617], [2761194.056, 1259839.702],
    [2761194.228, 1259839.781], [2761194.403, 1259839.853], [2761194.58, 1259839.917],
    [2761194.76, 1259839.974], [2761194.942, 1259840.024], [2761195.126, 1259840.067],
    [2761195.312, 1259840.102], [2761214.807, 1259841.464], [2761230.617, 1259842.836],
    [2761248.672, 1259844.412], [2761264.527, 1259845.795], [2761281.637, 1259847.291],
    [2761282.987, 1259827.955], [2761265.87, 1259826.798], [2761249.912, 1259825.849],
    [2761231.804, 1259824.631], [2761215.773, 1259823.52]
]
RHEINECK_LANDWIRTSCHAFT = [
    [2761215.773, 1259823.52], [2761231.804, 1259824.631], [2761249.912, 1259825.849],
    [2761265.87, 1259826.798], [2761282.987, 1259827.955], [2761308.328, 1259829.32],
    [2761320.328, 1259829.975], [2761331.16, 1259830.375], [2761364.279, 1259833.267],
    [2761421.837, 1259838.365], [2761425.337, 1259838.716], [2761441.68, 1259840.112],
    [2761468.579, 1259842.38], [2761486.624, 1259843.95], [2761482.231, 1259837.56],
    [2761462.376, 1259808.663], [2761458.686, 1259803.485], [2761442.521, 1259779.904],
    [2761434.218, 1259767.866], [2761420.055, 1259747.336], [2761405.071, 1259725.615],
    [2761403.549, 1259723.03], [2761326.791, 1259777.291], [2761265.101, 1259733.664],
    [2761262.768, 1259736.684], [2761258.085, 1259745.451], [2761245.577, 1259772.281],
    [2761239.572, 1259781.742], [2761232.072, 1259790.072], [2761207.335, 1259815.231],
    [2761215.773, 1259823.52]
]


def rheineck_modul1() -> dict:
    """Modul-1-Ergebnis wie im Livelauf -- mehrdeutige Grundnutzung."""
    return {
        "kataster": {"parzellengeometrie": RHEINECK_PARZELLE, "flaeche_m2": 289.1,
                     "parzellennummer": "160", "found": True},
        "nutzungsklassifikation": {
            "gefunden": True,
            "quelle": "geodienste",
            "basiszone_status": "mehrdeutig_mehrere_grundnutzungen_im_radius",
            "basiszone": {"typ_kommunal_bezeichnung": "BauG_Wohnzone W2"},
            "grundnutzungen": [
                {"typ_kommunal_bezeichnung": "BauG_Wohnzone W2",
                 "typ_kantonal_bezeichnung": "BauG_Wohnzone",
                 "typ_kommunal_code": "1104101", "hauptnutzung_code": "11",
                 "geometrie_koordinaten": [RHEINECK_WOHNZONE_W2]},
                {"typ_kommunal_bezeichnung": "BauG_Landwirtschaftszone",
                 "typ_kantonal_bezeichnung": "BauG_Landwirtschaftszone",
                 "typ_kommunal_code": "2102001", "hauptnutzung_code": "21",
                 "geometrie_koordinaten": [RHEINECK_LANDWIRTSCHAFT]},
            ],
            "sondernutzungsplaene_massgebend": [],
        },
        "oereb": {"amtliche_zonenbezeichnungen": [
            {"zonenbezeichnung": "BauG Wohnzone W2", "ist_wahrscheinlich_basiszone": True}]},
    }


# ---------------------------------------------------------------------------


def test_kuerzelerkennung() -> None:
    print("=== Was als Zonenkuerzel gilt ===")
    pruefe(_zonencodes("BauG_Wohnzone W2") == {"w2"},
           "am Ende: BauG_Wohnzone W2 -> w2")
    pruefe(_zonencodes("Wohnzone, 2 Vollgeschosse (W2)") == {"w2"},
           "in Klammern: Wohnzone, 2 Vollgeschosse (W2) -> w2  "
           "(die ausgeschriebene '2' zaehlt NICHT als Kuerzel)")
    pruefe(_zonencodes("W2 - Wohnzone 2 Vollgeschosse") == {"w2"},
           "vorangestellt: W2 - Wohnzone 2 Vollgeschosse -> w2")
    pruefe(_zonencodes("Zentrum drei- bis sechsgeschossig (ZE3, ZE4, ZE5, ZE6)")
           == {"ze3", "ze4", "ze5", "ze6"},
           "mehrere Kuerzel in einer Zeile werden alle erkannt (Aarau)")

    print("  -- und was ausdruecklich NICHT:")
    pruefe(_zonencodes("Kernzone (K)") == set(),
           "Kuerzel ohne Ziffer bleiben aussen vor: Kernzone (K)")
    pruefe(_zonencodes("Gewerbe-Industriezone (GI)") == set(),
           "auch zweibuchstabige: Gewerbe-Industriezone (GI)")
    pruefe(_zonencodes("Wohnzone a (W a)") == set(),
           "Buchs AG unterscheidet mit Buchstaben statt Ziffern: Wohnzone a (W a)")
    pruefe(_zonencodes("BauG_Wohnzone W2, 1995-1510") == {"w2"},
           "Jahreszahlen sind keine Kuerzel (1995-1510 wird nicht gelesen)")
    pruefe(_zonencodes("Landwirtschaftszone / Uebriges Gemeindegebiet (LW / UeG)") == set(),
           "Listen ohne Ziffer ebenfalls nicht")
    print()


def test_rheineck_der_fall() -> None:
    print("=== Der Fall Rheineck: BauG_Wohnzone W2 ===")
    ergebnis = match_zone(amtlich("BauG_Wohnzone W2"), RHEINECK_ZONEN)

    pruefe(ergebnis["status"] == "gefunden",
           f"zugeordnet statt unsicher ({ergebnis['status']})")
    pruefe(ergebnis.get("zuordnung_regel") == "zonencode",
           "entschieden hat das Zonenkuerzel, nicht die Textaehnlichkeit")
    pruefe(ergebnis.get("zonencode") == "W2", f"Kuerzel W2 ({ergebnis.get('zonencode')})")
    pruefe((ergebnis.get("zone") or {}).get("zonenbezeichnung") == "Wohnzone, 2 Vollgeschosse (W2)",
           f"richtige Zone ({(ergebnis.get('zone') or {}).get('zonenbezeichnung')})")
    pruefe(((ergebnis.get("zone") or {}).get("ausnuetzungsziffer_az") or {}).get("wert") == 0.45,
           "Ausnuetzungsziffer 0.45 kommt damit an")

    # Der Textwert bleibt sichtbar -- er ist der Grund, warum es den
    # Kuerzelweg ueberhaupt braucht, und er darf nicht verschwinden.
    pruefe(ergebnis.get("namensaehnlichkeit") == 0.51,
           f"reine Textaehnlichkeit weiterhin ausgewiesen: "
           f"{ergebnis.get('namensaehnlichkeit')} -- unter der Schwelle "
           f"{ZONE_MATCH_MIN_SIMILARITY}")
    pruefe("W2" in (ergebnis.get("hinweis") or ""),
           "der Hinweis nennt das Kuerzel, damit die Zuordnung nachvollziehbar ist")

    # Dieselbe Zone, wie der OEREB-Legendentext sie schreibt (ohne Unterstrich).
    aus_oereb = match_zone(amtlich("BauG Wohnzone W2"), RHEINECK_ZONEN)
    pruefe(aus_oereb["status"] == "gefunden" and aus_oereb.get("zonencode") == "W2",
           "auch die OEREB-Schreibweise 'BauG Wohnzone W2' fuehrt auf dieselbe Zone")
    print()


def test_schwelle_senken_waere_falsch() -> None:
    """Der Beleg dafuer, dass die Schwelle nicht die Stellschraube ist."""
    print("=== Warum eine niedrigere Schwelle die falsche Antwort waere ===")
    import difflib

    from potenzial_engine.modul3_financial import _normalize_zone_name

    ziel = _normalize_zone_name("BauG_Wohnzone W2")
    bewertet = sorted(
        ((difflib.SequenceMatcher(None, ziel, _normalize_zone_name(z["zonenbezeichnung"])).ratio(),
          z["zonenbezeichnung"]) for z in RORSCHACH_ZONEN),
        reverse=True)
    bester_score, bester_name = bewertet[0]
    print(f"      bester reiner Texttreffer in Rorschach: {bester_name!r} mit {bester_score:.2f}")

    pruefe(not bester_name.startswith("W2"),
           f"der beste Texttreffer ist NICHT die W2, sondern {bester_name!r}")
    pruefe(0.50 <= bester_score < ZONE_MATCH_MIN_SIMILARITY,
           f"er liegt mit {bester_score:.2f} knapp unter der Schwelle "
           f"{ZONE_MATCH_MIN_SIMILARITY} -- eine Schwelle von 0.50 wuerde ihn durchlassen")

    ergebnis = match_zone(amtlich("BauG_Wohnzone W2"), RORSCHACH_ZONEN)
    pruefe((ergebnis.get("zone") or {}).get("zonenbezeichnung") == "W2 - Wohnzone 2 Vollgeschosse",
           "ueber das Kuerzel landet dieselbe Anfrage auf der richtigen Zone")
    print()


def test_rorschach_alle_kuerzel() -> None:
    """Zweite Gemeinde, andere Schreibweise: Kuerzel vorangestellt."""
    print("=== Zweite Gemeinde: Rorschach SG (Kuerzel vorangestellt) ===")
    erwartet = {
        "BauG_Wohnzone W2": ("W2 - Wohnzone 2 Vollgeschosse", 0.4),
        "BauG_Wohnzone W3": ("W3 - Wohnzone 3 Vollgeschosse", 0.7),
        "BauG_Wohnzone W4": ("W4 - Wohnzone 4 Vollgeschosse", 0.85),
        "BauG_Wohnzone WZ3": ("WZ3 - Wohnzone fuer zentrumsnahes Wohnen 3 Vollgeschosse", None),
        "BauG_Wohn-Gewerbezone WG3": ("WG3 - Wohn-Gewerbezone 3 Vollgeschosse", None),
        "BauG_Wohn-Gewerbezone WG4": ("WG4 - Wohn-Gewerbezone 4 Vollgeschosse", None),
    }
    for name, (zonenanfang, az) in erwartet.items():
        ergebnis = match_zone(amtlich(name), RORSCHACH_ZONEN)
        getroffen = (ergebnis.get("zone") or {}).get("zonenbezeichnung") or ""
        pruefe(ergebnis["status"] == "gefunden" and getroffen.startswith(zonenanfang[:4]),
               f"{name} -> {getroffen!r}")
        if az is not None:
            pruefe(((ergebnis.get("zone") or {}).get("ausnuetzungsziffer_az") or {}).get("wert") == az,
                   f"   mit Ausnuetzungsziffer {az}")

    # W3 gegen WZ3 gegen WG3: drei Zonen, die sich im Text kaum unterscheiden.
    w3 = match_zone(amtlich("BauG_Wohnzone W3"), RORSCHACH_ZONEN)
    wz3 = match_zone(amtlich("BauG_Wohnzone WZ3"), RORSCHACH_ZONEN)
    pruefe((w3.get("zone") or {}).get("zonenbezeichnung")
           != (wz3.get("zone") or {}).get("zonenbezeichnung"),
           "W3 und WZ3 landen auf verschiedenen Zonen -- der Text allein "
           "unterscheidet sie nicht zuverlaessig")
    print()


def test_kuerzel_ohne_ziffer_unveraendert() -> None:
    print("=== Zonen ohne Ziffernkuerzel: unveraendert ueber den Text ===")
    for name, erwartet in (("BauG_Kernzone", "Kernzone (K)"),
                           ("BauG_Industriezone", "Industriezone (IZ)")):
        ergebnis = match_zone(amtlich(name), RHEINECK_ZONEN)
        pruefe(ergebnis["status"] == "gefunden"
               and (ergebnis.get("zone") or {}).get("zonenbezeichnung") == erwartet,
               f"{name} -> {erwartet}")
        pruefe(ergebnis.get("zuordnung_regel") == "namensaehnlichkeit",
               "   und zwar ueber die Namensaehnlichkeit, wie bisher")
    print()


def test_kein_kuerzel_keine_erfindung() -> None:
    print("=== Kein Treffer bleibt kein Treffer ===")
    # W5 gibt es in Rheineck nicht. Der Kuerzelweg darf daraus nichts machen.
    ergebnis = match_zone(amtlich("BauG_Wohnzone W5"), RHEINECK_ZONEN)
    pruefe(ergebnis["status"] == "unsicher",
           f"W5 existiert im Reglement nicht -> {ergebnis['status']}")
    pruefe(ergebnis.get("zone") is None, "und es wird keine Zone ausgegeben")
    pruefe("Zonenkuerzel" in (ergebnis.get("hinweis") or "")
           or "Kuerzel" in (ergebnis.get("hinweis") or ""),
           "der Hinweis sagt, dass ueber das Kuerzel nichts zu finden war")

    # Der benachbarte Subtyp W2H darf NICHT als W2 durchgehen.
    w2h = match_zone(amtlich("BauG_Wohnzone W2H"), RHEINECK_ZONEN)
    pruefe((w2h.get("zone") or {}).get("zonenbezeichnung")
           == "Wohnzone Hanglage, 2 Vollgeschosse (W2H)",
           "W2H trifft die Hanglagenzone und nicht die W2 -- Kuerzel werden "
           "exakt verglichen, nicht als Wortanfang")
    print()


def test_gleiches_kuerzel_mehrfach() -> None:
    print("=== Dasselbe Kuerzel in mehreren Zonen: bleibt offen ===")
    doppelt = [
        {"zonenbezeichnung": "Wohnzone W2 (Altbestand)", "ausnuetzungsziffer_az": {"wert": 0.4}},
        {"zonenbezeichnung": "Wohnzone W2 (Neubaugebiet)", "ausnuetzungsziffer_az": {"wert": 0.6}},
    ]
    ergebnis = match_zone(amtlich("BauG_Wohnzone W2"), doppelt)
    pruefe(ergebnis["status"] == "mehrere_gleich_gute_kandidaten",
           f"zwei Zonen mit demselben Kuerzel -> {ergebnis['status']}")
    pruefe(ergebnis.get("zone") is None,
           "keine der beiden wird gewaehlt -- 0.4 und 0.6 sind nicht dasselbe")
    pruefe(len(ergebnis.get("kandidaten") or []) == 2, "beide werden genannt")
    print()


def test_basiszone_ueber_flaechenanteil() -> None:
    print("=== Mehrere Grundnutzungen im Radius: die Parzelle entscheidet ===")
    modul1 = rheineck_modul1()
    bezeichnungen, quelle = _ermittle_basiszone_bezeichnung(modul1)

    pruefe(quelle == "nutzungsklassifikation_flaechenanteil",
           f"aufgeloest ueber den Flaechenanteil statt Rueckfall auf den "
           f"OEREB-Legendentext ({quelle})")
    pruefe(bezeichnungen[0]["zonenbezeichnung"] == "BauG_Wohnzone W2",
           f"die Wohnzone deckt die Parzelle ({bezeichnungen[0]['zonenbezeichnung']})")
    anteil = bezeichnungen[0].get("flaechenanteil_prozent")
    pruefe(anteil is not None and anteil > 99,
           f"und zwar zu {anteil} % -- die Landwirtschaftszone beruehrt sie nur "
           "entlang der gemeinsamen Kante")

    # Die ganze Kette: Geometrie loest die Grundnutzung, das Kuerzel die Zone.
    from potenzial_engine.modul3_financial import ermittle_zonenzuordnung
    kette = ermittle_zonenzuordnung(modul1, {"erkannte_zonen": RHEINECK_ZONEN})
    pruefe(kette["status"] == "gefunden"
           and (kette.get("zone") or {}).get("zonenbezeichnung") == "Wohnzone, 2 Vollgeschosse (W2)",
           "durchgehend: amtliche Daten -> Grundnutzung -> Reglementszone")
    pruefe(((kette.get("zone") or {}).get("ausnuetzungsziffer_az") or {}).get("wert") == 0.45,
           "Ausnuetzungsziffer 0.45")
    print()


def test_parzelle_ueber_zonengrenze() -> None:
    """Gegenprobe: liegt die Parzelle WIRKLICH in zwei Zonen, bleibt es offen."""
    print("=== Gegenprobe: Parzelle ueber einer echten Zonengrenze ===")
    modul1 = rheineck_modul1()
    # Die Landwirtschaftszone wird durch ein Rechteck ersetzt, das die halbe
    # Parzelle deckt. Dann ist die Frage nicht mehr geometrisch entscheidbar.
    haelfte = [[2761214.0, 1259815.0], [2761224.0, 1259815.0],
               [2761224.0, 1259845.0], [2761214.0, 1259845.0]]
    modul1["nutzungsklassifikation"]["grundnutzungen"][1]["geometrie_koordinaten"] = [haelfte]

    bezeichnungen, quelle = _ermittle_basiszone_bezeichnung(modul1)
    pruefe(quelle == "oereb_legendtext_fallback",
           f"kein geometrischer Freispruch, wenn beide Zonen die Parzelle "
           f"nennenswert decken ({quelle})")
    print()


def main() -> None:
    test_kuerzelerkennung()
    test_rheineck_der_fall()
    test_schwelle_senken_waere_falsch()
    test_rorschach_alle_kuerzel()
    test_kuerzel_ohne_ziffer_unveraendert()
    test_kein_kuerzel_keine_erfindung()
    test_gleiches_kuerzel_mehrfach()
    test_basiszone_ueber_flaechenanteil()
    test_parzelle_ueber_zonengrenze()

    print("=" * 70)
    if FEHLER:
        print(f"{len(FEHLER)} FEHLGESCHLAGEN:")
        for f in FEHLER:
            print(" -", f)
        sys.exit(1)
    print("ALLE ZONENZUORDNUNGS-TESTS BESTANDEN")


if __name__ == "__main__":
    main()

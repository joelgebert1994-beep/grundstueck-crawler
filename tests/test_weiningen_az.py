"""Weiningen, Hogerwiesstrasse 1: die Ausnuetzungsziffer ging im Potenzial verloren.

Befund (01.10.2026, live): Baurecht zeigte AZ 0.3 ("Ausnuetzungsziffer max.
30 %", Art. 22), das Potenzial schrieb "Es gibt keine belastbare
Ausnuetzungsziffer" und "nicht bestimmbar".

Ursache war NICHT die Einheit. Das Reglement fuehrt den Wert als 0.3
(Verhaeltniszahl, Etikett "Prozent") und G1 rechnet damit richtig: 0.30 x
1'168.1 m2 = 350.42 m2, in beiden Abstandsraendern begrenzend. Weil die
Parzellenkanten nicht zugeordnet werden konnten, lief G1 im Rueckfallmodus
`bandbreite_grenzabstand_kante_nicht_differenziert` -- und nur dieser Zweig
lieferte weder `gf_nach_ausnuetzungsziffer_m2` noch `eindeutigkeit`.

Eingaben: unveraendert aus dem Live-Ergebnis ausgeschnitten
(tests/daten/weiningen/g1_eingaben_hogerwies.json).

Aufruf: python -m tests.test_weiningen_az
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from potenzial_engine.g1_verdrahtung import berechne_g1_fuer_fall  # noqa: E402
from potenzial_engine.pipeline import _bestand_und_neubaugeometrie  # noqa: E402

E = json.loads((Path(__file__).resolve().parent / "daten" / "weiningen" /
                "g1_eingaben_hogerwies.json").read_text(encoding="utf-8"))

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


def test_beleg_unveraendert() -> None:
    print("=== Der Beleg aus dem Reglement bleibt, wie er ist ===")
    az = E["zone"]["ausnuetzungsziffer_az"]
    pruefe(az["wert"] == 0.3 and az["einheit"] == "Prozent", "Kennzahl wie ausgelesen: 0.3, Etikett 'Prozent'")
    pruefe(az["zitat"] == "Ausnützungsziffer max. 30 %" and az["artikel_referenz"] == "Art. 22",
           "Originaltext und Artikel bleiben erhalten")
    pruefe(E["g1_live"]["modus"] == "bandbreite_grenzabstand_kante_nicht_differenziert",
           "der Live-Fall lief im Rueckfallmodus (Kanten nicht zugeordnet)")
    pruefe(any("keine belastbare Ausnuetzungsziffer" in p for p in E["potenzial_live_vorher"]["offene_punkte"]),
           "vorher (live): 'keine belastbare Ausnuetzungsziffer'")


def test_g1() -> None:
    print("\n=== G1 im Rueckfallmodus ===")
    g = berechne_g1_fuer_fall(E["modul1"], E["zone"], kantenklassifikation=E["kantenklassifikation"])
    pruefe(g["modus"] == "bandbreite_grenzabstand_kante_nicht_differenziert", "derselbe Modus wie live")
    pruefe(g.get("gf_nach_ausnuetzungsziffer_m2") == 350.42,
           f"GF nach AZ = 0.30 x 1'168.1 m2 = 350.42 m2 (nicht 30 x, nicht 0.003 x): {g.get('gf_nach_ausnuetzungsziffer_m2')}")
    pruefe("0.3 x 1,168.1" in (g.get("gf_nach_ausnuetzungsziffer_rechnung") or ""),
           "die Rechnung nennt Ziffer und Landflaeche")
    s = g["szenarien"]
    pruefe(s["alle_kanten_klein"]["geschossflaeche_m2"] == 350.42 == s["alle_kanten_gross"]["geschossflaeche_m2"],
           "beide Raender: 350.42 m2")
    ein = g.get("eindeutigkeit") or {}
    pruefe(ein.get("geschossflaeche_eindeutig") is True and ein.get("geschossflaeche_m2") == 350.42,
           "die Geschossflaeche ist eindeutig: 350.42 m2")
    pruefe(ein.get("bindend") == "ausnuetzung_az", "begrenzend ist die Ausnuetzungsziffer")
    pruefe(ein.get("baubereich_spanne_m2") == [188.43, 613.78] and "ergebnis" not in g,
           "der Baubereich bleibt offen (188-614 m2), kein Einzelergebnis erfunden")
    pruefe(ein.get("vertreter_anordnung") is None and ein.get("grundlage") == "raender_der_kantenzuordnung",
           "keine Anordnung als Vertreter ausgegeben -- die Raender sind keine zulaessigen Anordnungen")
    return g


def test_pipeline(g: dict) -> None:
    print("\n=== Potenzial: dieselbe Rechtsgrundlage ===")
    b = _bestand_und_neubaugeometrie(E["modul1"], g)
    pruefe(b["heutiger_rechtsrahmen"]["gf_nach_ausnuetzungsziffer_m2"] == 350.42,
           "der Rechtsrahmen im Potenzial rechnet mit 350.42 m2")
    offen = b["zusaetzliches_potenzial"].get("offene_punkte") or []
    pruefe(not any("keine belastbare Ausnuetzungsziffer" in p for p in offen),
           "'keine belastbare Ausnuetzungsziffer' ist weg")
    pruefe(any("GENAEHERT" in p for p in offen),
           "das ZUSAETZLICHE Potenzial bleibt offen, weil der Bestand nur genaehert ist (unveraendert)")


def test_nicht_eindeutig_bleibt_spanne() -> None:
    print("\n=== Andere Faelle bleiben, wie sie sind ===")
    zone = copy.deepcopy(E["zone"])
    zone["ausnuetzungsziffer_az"] = dict(zone["ausnuetzungsziffer_az"], wert=2.0)
    g = berechne_g1_fuer_fall(E["modul1"], zone, kantenklassifikation=E["kantenklassifikation"])
    gf = {k: v["geschossflaeche_m2"] for k, v in g["szenarien"].items()}
    pruefe(len(set(gf.values())) == 2 and "eindeutigkeit" not in g,
           f"begrenzt die Geometrie, unterscheiden sich die Raender -> KEINE Eindeutigkeit: {gf}")
    land = g["szenarien"]["alle_kanten_klein"]["anrechenbare_landflaeche_m2"]
    pruefe(g.get("gf_nach_ausnuetzungsziffer_m2") == round(2.0 * land, 2),
           "die AZ-Geschossflaeche wird trotzdem genannt")
    ohne = copy.deepcopy(E["zone"])
    ohne["ausnuetzungsziffer_az"] = None
    g = berechne_g1_fuer_fall(E["modul1"], ohne, kantenklassifikation=E["kantenklassifikation"])
    pruefe("gf_nach_ausnuetzungsziffer_m2" not in g, "ohne AZ wird keine AZ-Geschossflaeche erfunden")


def main() -> None:
    test_beleg_unveraendert()
    g = test_g1()
    test_pipeline(g)
    test_nicht_eindeutig_bleibt_spanne()
    print()
    if _fehler:
        print(f"WEININGEN-AZ: {len(_fehler)} Abweichung(en)")
        for f in _fehler:
            print(f" - {f}")
        sys.exit(1)
    print(f"ALLE WEININGEN-AZ-TESTS BESTANDEN ({_ok} OK)")


if __name__ == "__main__":
    main()

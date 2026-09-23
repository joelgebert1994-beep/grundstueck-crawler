"""Fuehrt alle Testsuiten der Engine aus und fasst sie in einer Zeile je Suite
zusammen.

Bisher wurde dieser Lauf jedes Mal ad hoc zusammengesetzt -- damit war "alle
Tests gruen" nicht reproduzierbar nachvollziehbar. Diese Datei ist die
verbindliche Liste.

Zwei Suiten brauchen Netzzugang (`test_klassifikation`, teilweise
`test_quellen`); keine braucht einen API-Key.

CLI:
    python -m tests.alle            # alle Suiten
    python -m tests.alle --offline  # nur die Suiten ohne Netzzugang
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# (Modulname, braucht_netz)
SUITEN: list[tuple[str, bool]] = [
    ("tests.test_baubereich", False),
    ("tests.test_abstandsgeometrie", False),
    ("tests.test_sia416_flaechen", False),
    ("tests.test_quellen", True),
    ("tests.test_entwicklungsszenarien", False),
    ("tests.test_referenzprojekte", False),
    ("tests.test_abrufmechanik", False),
    ("tests.test_kantenklassifikation", False),
    ("tests.test_zonenzuordnung", False),
    ("tests.test_reglement_zwischenspeicher", False),
    ("tests.test_flaechenmodell", False),
    ("tests.test_szenarien", False),
    ("tests.test_wirtschaftlichkeit", False),
    ("tests.test_marktdaten", False),
    ("tests.test_umgebung", False),
    ("tests.test_sonnenstand", False),
    ("tests.test_zwischenspeicher", False),
    ("tests.test_projektstudie_flaechen", False),
    ("tests.test_oberflaeche", False),
    ("tests.test_klassifikation", True),
]


def main() -> None:
    nur_offline = "--offline" in sys.argv
    ausgewaehlt = [(m, n) for m, n in SUITEN if not (nur_offline and n)]

    gescheitert: list[str] = []
    gesamt_ok = 0

    for modul, braucht_netz in ausgewaehlt:
        lauf = subprocess.run(
            [sys.executable, "-m", modul],
            cwd=WURZEL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ausgabe = (lauf.stdout or "") + (lauf.stderr or "")
        anzahl_ok = ausgabe.count("[OK  ]") + ausgabe.count("[OK]")
        gesamt_ok += anzahl_ok
        schlusszeile = next(
            (z.strip() for z in reversed(ausgabe.splitlines()) if "BESTANDEN" in z or "FEHLGESCHLAGEN" in z),
            "keine Schlusszeile",
        )
        kurz = modul.split(".")[-1]
        netz = " (Netz)" if braucht_netz else ""
        if lauf.returncode == 0:
            print(f"  {kurz:28s} {schlusszeile[:46]:46s} ({anzahl_ok} OK){netz}")
        else:
            print(f"  {kurz:28s} FEHLGESCHLAGEN (Exitcode {lauf.returncode}){netz}")
            for zeile in ausgabe.splitlines():
                if "[FAIL]" in zeile or zeile.startswith(" - "):
                    print(f"      {zeile.strip()}")
            gescheitert.append(kurz)

    print("-" * 92)
    if gescheitert:
        print(f"{len(gescheitert)} von {len(ausgewaehlt)} Suiten FEHLGESCHLAGEN: {', '.join(gescheitert)}")
        sys.exit(1)
    print(f"{len(ausgewaehlt)}/{len(ausgewaehlt)} Suiten bestanden, {gesamt_ok} einzelne Zusicherungen.")


if __name__ == "__main__":
    main()

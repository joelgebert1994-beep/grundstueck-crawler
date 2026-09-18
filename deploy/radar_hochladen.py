"""Den AkquiseRadar auf die Produktions-VM bringen -- wiederholbar.

Warum ueberhaupt ein Skript und kein `scp`?

Drei Dinge gehen beim Kopieren einer laufenden SQLite-Datei schief, und
alle drei sind still:

1. **Ein halber Stand.** Der Radar schreibt, waehrend kopiert wird. Ein
   roher Dateikopie-Vorgang erwischt dann eine Datei mit halb
   geschriebenen Seiten. `VACUUM INTO` erzeugt stattdessen einen
   konsistenten Abzug -- und verdichtet ihn nebenbei.

2. **Ein halb angekommener Stand.** Wird direkt auf die Zieldatei
   geschrieben, liest der Dienst waehrend der Uebertragung eine
   unvollstaendige Datenbank. Deshalb wird neben die Zieldatei geladen und
   erst am Schluss umbenannt -- ein Umbenennen im selben Dateisystem ist
   unteilbar.

3. **Ein Stand, den der Container nie sieht.** Haengt man eine einzelne
   DATEI ein, behaelt der Container die alte Inode, auch nachdem die Datei
   ersetzt wurde. Deshalb haengt docker-compose.yml das VERZEICHNIS ein.

Der Radar selbst wird nur gelesen. Er bleibt unveraendert.

Aufruf:

    python deploy/radar_hochladen.py                  # Abzug, Upload, Import
    python deploy/radar_hochladen.py --nur-abzug      # nur lokal pruefen
    python deploy/radar_hochladen.py --ohne-import    # hochladen, nicht importieren

Gedacht fuer die Aufgabenplanung: derselbe Aufruf nach jedem Radar-Lauf.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Der Radar liegt im Nachbarrepo. Beide Pfade lassen sich ueberschreiben,
# damit das Skript auch auf einem anderen Rechner laeuft.
RADAR_DB = Path(os.environ.get("RADAR_DB")
                or Path(__file__).resolve().parents[2] / "Crawler" / "akquiseradar" / "data" / "radar.db")
VM_HOST = os.environ.get("GEBIMO_VM", "ubuntu@140.238.215.236")
VM_KEY = os.environ.get("GEBIMO_VM_KEY", str(Path.home() / ".ssh" / "oracle_gebimo.key"))
ZIEL_VERZEICHNIS = "/opt/gebimo/radar"


def melde(text: str) -> None:
    print(text, flush=True)


def abzug_erstellen(quelle: Path, ziel: Path) -> int:
    """Konsistenter, verdichteter Abzug -- auch waehrend der Radar schreibt."""
    if not quelle.exists():
        raise SystemExit(f"radar.db nicht gefunden: {quelle}")
    if ziel.exists():
        ziel.unlink()
    # Schreibgeschuetzt oeffnen: dieses Skript darf den Radar nicht anfassen.
    con = sqlite3.connect(f"file:{quelle.as_posix()}?mode=ro", uri=True)
    try:
        con.execute("VACUUM INTO ?", (str(ziel),))
    finally:
        con.close()
    return ziel.stat().st_size


def zaehle(pfad: Path) -> int:
    con = sqlite3.connect(f"file:{pfad.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT count(*) FROM objects").fetchone()[0]
    finally:
        con.close()


def ssh(*befehl: str) -> str:
    fertig = subprocess.run(
        ["ssh", "-i", VM_KEY, "-o", "ConnectTimeout=20", VM_HOST, *befehl],
        capture_output=True, text=True)
    if fertig.returncode != 0:
        raise SystemExit(f"ssh fehlgeschlagen: {fertig.stderr.strip() or fertig.stdout.strip()}")
    return fertig.stdout.strip()


def hochladen(abzug: Path) -> None:
    ssh("mkdir", "-p", ZIEL_VERZEICHNIS)
    ziel_neu = f"{ZIEL_VERZEICHNIS}/radar.db.neu"
    fertig = subprocess.run(
        ["scp", "-i", VM_KEY, "-o", "ConnectTimeout=20",
         str(abzug), f"{VM_HOST}:{ziel_neu}"],
        capture_output=True, text=True)
    if fertig.returncode != 0:
        raise SystemExit(f"scp fehlgeschlagen: {fertig.stderr.strip()}")
    # Unteilbar umbenennen: der Dienst sieht entweder den alten oder den
    # neuen Stand, nie einen halben.
    ssh("mv", "-f", ziel_neu, f"{ZIEL_VERZEICHNIS}/radar.db")
    # Lesbar fuer den Dienstbenutzer im Container (uid 10001).
    ssh("chmod", "644", f"{ZIEL_VERZEICHNIS}/radar.db")


def importieren() -> None:
    """Loest /marktdaten/radar auf der VM aus -- ueber den Dienst selbst.

    Bewusst von innen (`docker exec`) und nicht ueber das oeffentliche
    Netz: der Zugangsschluessel muss dafuer nirgends ausserhalb der VM
    liegen.
    """
    ausgabe = ssh(
        "docker", "exec", "gebimo-backend", "python", "-c",
        "'import urllib.request,json;"
        "r=urllib.request.Request(\"http://127.0.0.1:8787/marktdaten/radar\","
        "data=b\"{}\",headers={\"Content-Type\":\"application/json\"},method=\"POST\");"
        "print(urllib.request.urlopen(r,timeout=120).read().decode())'")
    melde("  Antwort des Dienstes: " + ausgabe[:400])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nur-abzug", action="store_true", help="nur den Abzug erstellen")
    p.add_argument("--ohne-import", action="store_true", help="hochladen, aber nicht importieren")
    args = p.parse_args()

    arbeitsordner = Path(tempfile.mkdtemp(prefix="radar_"))
    abzug = arbeitsordner / "radar.db"
    try:
        melde(f"Abzug aus {RADAR_DB} …")
        groesse = abzug_erstellen(RADAR_DB, abzug)
        melde(f"  {zaehle(abzug)} Objekte, {groesse / 1_048_576:.1f} MB "
              f"(Original {RADAR_DB.stat().st_size / 1_048_576:.1f} MB)")
        if args.nur_abzug:
            behalten = RADAR_DB.with_name("radar_abzug.db")
            shutil.copy2(abzug, behalten)
            melde(f"  abgelegt: {behalten}")
            return 0

        melde(f"Hochladen nach {VM_HOST}:{ZIEL_VERZEICHNIS} …")
        hochladen(abzug)
        melde("  " + ssh("ls", "-la", f"{ZIEL_VERZEICHNIS}/radar.db"))

        if args.ohne_import:
            return 0
        melde("Import im Dienst auslösen …")
        importieren()
        return 0
    finally:
        shutil.rmtree(arbeitsordner, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

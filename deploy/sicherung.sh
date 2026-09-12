#!/usr/bin/env bash
# Sicherung der Datenbank.
#
# Nicht einfach kopieren: eine SQLite-Datei, die gerade beschrieben wird,
# ergibt kopiert eine kaputte Sicherung. `.backup` nimmt einen konsistenten
# Stand, auch waehrend der Dienst laeuft.
#
# Laeuft taeglich ueber gebimo-sicherung.timer.

set -euo pipefail

DATEN=/opt/gebimo/daten
ZIEL=/opt/gebimo/sicherungen
BEHALTEN=14

mkdir -p "$ZIEL"

if [ ! -f "$DATEN/kern.db" ]; then
	echo "Keine Datenbank unter $DATEN/kern.db -- nichts zu sichern."
	exit 0
fi

STEMPEL=$(date -u +%Y-%m-%dT%H%M%SZ)
ZIELDATEI="$ZIEL/kern-$STEMPEL.db"

# sqlite3 im Backend-Container benutzen -- so braucht die VM das Werkzeug
# nicht selbst, und es ist garantiert dieselbe Version.
docker exec gebimo-backend python -c "
import sqlite3
quelle = sqlite3.connect('/daten/kern.db')
ziel = sqlite3.connect('/daten/.sicherung.tmp')
quelle.backup(ziel)
ziel.close(); quelle.close()
"
mv "$DATEN/.sicherung.tmp" "$ZIELDATEI"
gzip -9 "$ZIELDATEI"

# Alte Sicherungen aufraeumen. Ohne das laeuft die Bootplatte irgendwann voll
# -- und dann steht der Dienst wegen seiner eigenen Sicherungen.
ls -1t "$ZIEL"/kern-*.db.gz 2>/dev/null | tail -n +$((BEHALTEN + 1)) | xargs -r rm --

echo "Gesichert: $ZIELDATEI.gz ($(du -h "$ZIELDATEI.gz" | cut -f1))"
echo "Vorhanden: $(ls -1 "$ZIEL"/kern-*.db.gz 2>/dev/null | wc -l) Sicherungen"

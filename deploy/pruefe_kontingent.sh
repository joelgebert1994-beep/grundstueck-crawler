#!/usr/bin/env bash
# Prueft VOR dem Deploy, ob die laufende VM vollstaendig im Oracle-
# Always-Free-Kontingent liegt. Laeuft AUF der VM.
#
#   bash grundstueck-crawler/deploy/pruefe_kontingent.sh
#
# Grundlage sind die Always-Free-Grenzen laut Oracle-Dokumentation
# (Stand 12.09.2026):
#
#   Ampere A1        1'500 OCPU-Std. + 9'000 GB-Std./Monat
#                    = 2 OCPU + 12 GB durchgehend
#   Blockspeicher    200 GB gesamt (Boot + Block)
#   Ausgehend        10 TB/Monat
#   Load Balancer    1 flexibler, 10 Mbps
#
# Das Skript kann NICHT sehen, ob weitere Instanzen im selben Konto laufen.
# Die Grenzen gelten fuer die ganze Tenancy -- zwei VMs mit je 2 OCPU sind
# zusammen doppelt so viel wie erlaubt.

set -uo pipefail

GRUEN=$'\033[32m'; ROT=$'\033[31m'; GELB=$'\033[33m'; AUS=$'\033[0m'
warnungen=0

sage() { printf '  %s %s\n' "$1" "$2"; }
ok()   { sage "${GRUEN}OK  ${AUS}" "$1"; }
warn() { sage "${GELB}ACHT${AUS}" "$1"; warnungen=$((warnungen + 1)); }
fehl() { sage "${ROT}NEIN${AUS}" "$1"; warnungen=$((warnungen + 1)); }

echo
echo "Always-Free-Kontingent -- Pruefung dieser VM"
echo "============================================"

# --- Gestalt (Shape) --------------------------------------------------
# Die Always-Free-Grenzen haengen an der Gestalt, nicht an der Architektur.
# Es gibt zwei voellig verschiedene Kontingente:
#
#   VM.Standard.A1.Flex      aarch64, bis 4 OCPU / 24 GB verteilbar,
#                            davon 2 OCPU + 12 GB durchgehend gratis
#   VM.Standard.E2.1.Micro   x86_64, 1/8 OCPU + 1 GB, zwei Stueck gratis
#
# Die Gestalt steht im Metadatendienst der Instanz. `uname -m` kann sie
# nicht unterscheiden, weil beide AMD-Gestalten x86_64 melden.
GESTALT=$(curl -s -m 3 -H "Authorization: Bearer Oracle" \
	http://169.254.169.254/opc/v2/instance/shape 2>/dev/null)
[ -z "$GESTALT" ] && GESTALT="unbekannt ($(uname -m))"

SPEICHER_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
KERNE=$(nproc)

# Gemessener Spitzenbedarf einer Analyse plus Grundlast der VM.
# Quelle: deploy/../docs/einrichtung_oracle.md, Messung vom 18.09.2026.
BEDARF_MB=176
GRUNDLAST_MB=330   # Ubuntu minimal + Docker-Daemon + Caddy

case "$GESTALT" in
	VM.Standard.A1.Flex)
		ok "Gestalt $GESTALT (Ampere A1)"
		# Bei Ampere entspricht 1 OCPU einem Kern (kein SMT).
		if [ "$KERNE" -le 2 ]; then
			ok "$KERNE OCPU (Grenze: 2 durchgehend gratis)"
		else
			fehl "$KERNE OCPU -- ueber der Always-Free-Grenze von 2. Kostenpflichtig!"
		fi
		if [ "$SPEICHER_MB" -le 12288 ]; then
			ok "${SPEICHER_MB} MB RAM (Grenze: 12288 durchgehend gratis)"
		else
			fehl "${SPEICHER_MB} MB RAM -- ueber der Always-Free-Grenze von 12288. Kostenpflichtig!"
		fi
		;;
	VM.Standard.E2.1.Micro)
		ok "Gestalt $GESTALT (AMD Micro, immer gratis, zwei Stueck je Konto)"
		# E2.1.Micro hat 1/8 OCPU. `nproc` meldet trotzdem 2 -- das sind
		# Threads, keine OCPU. Hier gibt es nichts zu ueberschreiten: die
		# Gestalt ist unveraenderlich und per Definition im Kontingent.
		sage "    " "$KERNE vCPU-Threads auf 1/8 OCPU -- durch die Gestalt fest, nicht regelbar"
		# Entscheidend ist hier nicht die Grenze, sondern ob es reicht.
		BRAUCHT=$((BEDARF_MB + GRUNDLAST_MB))
		if [ "$SPEICHER_MB" -ge "$BRAUCHT" ]; then
			ok "${SPEICHER_MB} MB RAM -- gemessener Bedarf ${BRAUCHT} MB (Analyse ${BEDARF_MB} + Grundlast ${GRUNDLAST_MB}), reicht"
		else
			warn "${SPEICHER_MB} MB RAM -- gemessener Bedarf ${BRAUCHT} MB. Zu knapp; auf A1 wechseln, sobald Kapazitaet frei ist."
		fi
		;;
	*)
		warn "Gestalt $GESTALT -- nicht als Always-Free-Gestalt erkannt. In der Oracle-Konsole gegenpruefen, ob sie das Etikett 'Always Free eligible' traegt."
		sage "    " "$KERNE vCPU, ${SPEICHER_MB} MB RAM"
		;;
esac

# --- Blockspeicher ----------------------------------------------------
SUMME=0
while read -r name groesse typ; do
	[ "$typ" = "disk" ] || continue
	SUMME=$((SUMME + groesse))
done < <(lsblk -bdno NAME,SIZE,TYPE 2>/dev/null)
SPEICHER_GB=$((SUMME / 1024 / 1024 / 1024))
if [ "$SPEICHER_GB" -le 200 ]; then
	ok "${SPEICHER_GB} GB Blockspeicher (Grenze: 200 gesamt)"
else
	fehl "${SPEICHER_GB} GB Blockspeicher -- ueber der Grenze von 200."
fi

# --- Was der Dienst wirklich braucht ---------------------------------
echo
echo "Bedarf des Dienstes (gemessen, nicht geschaetzt)"
echo "------------------------------------------------"
sage "    " "Spitzenspeicher je Analyse : 176 MB"
sage "    " "CPU-Zeit je Analyse        : 5.2 s"
sage "    " "Datenbank heute            : ~3 MB"
sage "    " "Ausgehend bei 100 Analysen/Tag: ~2.1 GB/Monat (Grenze 10 TB)"

# --- Kostenfallen -----------------------------------------------------
echo
echo "Haeufige versteckte Kosten"
echo "---------------------------"
if command -v docker >/dev/null 2>&1; then
	ok "Docker vorhanden"
else
	warn "Docker fehlt -- siehe Einrichtungsanleitung"
fi
sage "    " "Load Balancer      : NICHT noetig. Caddy macht TLS direkt auf der VM."
sage "    " "Zweite Instanz     : zaehlt auf dieselben 2 OCPU / 12 GB."
sage "    " "Block Volume extra : nicht noetig -- die Bootplatte reicht."
sage "    " "Reservierte IP     : die ephemere oeffentliche IP ist frei."
sage "    " "Object Storage     : wird von diesem Dienst nicht benutzt."

echo
if [ "$warnungen" -eq 0 ]; then
	echo "${GRUEN}Alles innerhalb des Always-Free-Kontingents.${AUS}"
else
	echo "${GELB}${warnungen} Punkt(e) pruefen, bevor es weitergeht.${AUS}"
fi
echo
echo "Nicht pruefbar von hier: ob im selben Konto weitere Instanzen laufen."
echo "Die Grenzen gelten fuer die ganze Tenancy. In der Oracle-Konsole unter"
echo "Governance -> Limits, Quotas and Usage gegenpruefen."
echo
exit 0

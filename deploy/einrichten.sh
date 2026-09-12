#!/usr/bin/env bash
# Richtet den Dienst auf einer frischen Oracle-Always-Free-VM ein.
# Laeuft AUF der VM, als Benutzer mit sudo-Recht.
#
#   bash grundstueck-crawler/deploy/einrichten.sh
#
# Das Skript ist mehrfach ausfuehrbar: es ueberschreibt keine .env und keine
# Datenbank. Was schon da ist, bleibt.

set -euo pipefail

WURZEL=/opt/gebimo
GRUEN=$'\033[32m'; GELB=$'\033[33m'; AUS=$'\033[0m'
schritt() { printf '\n%s>> %s%s\n' "$GRUEN" "$1" "$AUS"; }

[ "$(id -u)" -eq 0 ] && { echo "Bitte NICHT als root -- das Skript ruft sudo selbst auf."; exit 1; }

schritt "1/7  Systempakete"
if command -v dnf >/dev/null 2>&1; then
	sudo dnf install -y git curl
elif command -v apt-get >/dev/null 2>&1; then
	sudo apt-get update -qq && sudo apt-get install -y git curl
fi

schritt "2/7  Docker"
if command -v docker >/dev/null 2>&1; then
	echo "    schon vorhanden: $(docker --version)"
else
	curl -fsSL https://get.docker.com | sudo sh
	sudo usermod -aG docker "$USER"
	echo "${GELB}    Neu in der Docker-Gruppe -- nach diesem Skript einmal ab- und wieder anmelden.${AUS}"
fi
sudo systemctl enable --now docker

schritt "3/7  Firewall der VM"
# Der haeufigste Grund, warum Caddy kein Zertifikat bekommt: die
# VCN-Sicherheitsliste ist offen, die Firewall AUF der VM aber nicht.
if command -v firewall-cmd >/dev/null 2>&1; then
	sudo firewall-cmd --permanent --add-service=http  >/dev/null
	sudo firewall-cmd --permanent --add-service=https >/dev/null
	sudo firewall-cmd --reload >/dev/null
	echo "    firewalld: 80 und 443 offen"
elif command -v ufw >/dev/null 2>&1; then
	sudo ufw allow 80/tcp >/dev/null && sudo ufw allow 443/tcp >/dev/null
	echo "    ufw: 80 und 443 offen"
else
	# Oracle-Linux-Abbilder bringen iptables-Regeln mit, die alles ausser SSH
	# verwerfen -- und zwar VOR den Docker-Regeln.
	sudo iptables -I INPUT 1 -p tcp --dport 80  -j ACCEPT
	sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
	command -v netfilter-persistent >/dev/null 2>&1 && sudo netfilter-persistent save || \
		sudo sh -c 'iptables-save > /etc/iptables/rules.v4' 2>/dev/null || true
	echo "    iptables: 80 und 443 offen"
fi
echo "${GELB}    NICHT VERGESSEN: dieselben Ports in der Oracle-Konsole unter${AUS}"
echo "${GELB}    Networking -> VCN -> Security List als Ingress-Regel freigeben.${AUS}"

schritt "4/7  Verzeichnisse"
sudo mkdir -p "$WURZEL"
sudo chown "$USER":"$USER" "$WURZEL"
mkdir -p "$WURZEL"/{daten,caddy/data,caddy/config,sicherungen}
echo "    $WURZEL angelegt"

schritt "5/7  Quellcode"
cd "$WURZEL"
for repo in \
	"grundstueck-crawler https://github.com/joelgebert1994-beep/grundstueck-crawler.git" \
	"Crawler https://github.com/joelgebert1994-beep/akquiseradar.git"
do
	set -- $repo
	if [ -d "$1/.git" ]; then
		echo "    $1: aktualisieren"
		git -C "$1" pull --ff-only
	else
		echo "    $1: klonen"
		git clone --depth 1 "$2" "$1"
	fi
done

schritt "6/7  Konfiguration"
cp -f grundstueck-crawler/deploy/docker-compose.yml "$WURZEL/docker-compose.yml"
# .dockerignore muss an der Wurzel des Bau-Kontexts liegen, nicht im Repo.
cp -f grundstueck-crawler/.dockerignore "$WURZEL/.dockerignore"
if [ -f "$WURZEL/.env" ]; then
	echo "    .env vorhanden -- wird NICHT ueberschrieben"
else
	cp grundstueck-crawler/deploy/env.beispiel "$WURZEL/.env"
	chmod 600 "$WURZEL/.env"
	echo "${GELB}    .env aus der Vorlage angelegt. JETZT ausfuellen:${AUS}"
	echo "${GELB}      nano $WURZEL/.env${AUS}"
	echo "${GELB}    Danach dieses Skript erneut ausfuehren.${AUS}"
	exit 0
fi

# Pflichtwerte pruefen, bevor gebaut wird.
set -a; . "$WURZEL/.env"; set +a
fehlt=0
for name in DOMAIN GEMINI_API_KEY ZUGANGSSCHLUESSEL; do
	wert="${!name:-}"
	if [ -z "$wert" ] || [ "$wert" = "api.beispiel.ch" ]; then
		echo "${GELB}    $name fehlt oder ist noch die Vorlage${AUS}"
		fehlt=1
	fi
done
[ "$fehlt" -eq 1 ] && { echo "Bitte $WURZEL/.env vervollstaendigen."; exit 1; }
# Der Schluessel selbst wird nie ausgegeben -- nur, dass er da ist.
echo "    DOMAIN=$DOMAIN, Schluessel gesetzt"

schritt "7/7  Dienst starten"
sudo cp grundstueck-crawler/deploy/gebimo.service /etc/systemd/system/
sudo cp grundstueck-crawler/deploy/gebimo-sicherung.service /etc/systemd/system/
sudo cp grundstueck-crawler/deploy/gebimo-sicherung.timer /etc/systemd/system/
chmod +x grundstueck-crawler/deploy/sicherung.sh
sudo systemctl daemon-reload
sudo systemctl enable --now gebimo
sudo systemctl enable --now gebimo-sicherung.timer

echo
echo "${GRUEN}Fertig.${AUS} Das erste Bauen dauert auf ARM einige Minuten."
echo
echo "  Fortschritt   : docker compose -f $WURZEL/docker-compose.yml logs -f"
echo "  Zustand       : curl -s https://$DOMAIN/health"
echo "  Kontingent    : bash $WURZEL/grundstueck-crawler/deploy/pruefe_kontingent.sh"
echo
echo "Danach in Cloudflare Pages hinterlegen:"
echo "  BACKEND_URL         = https://$DOMAIN"
echo "  BACKEND_SCHLUESSEL  = (derselbe Wert wie ZUGANGSSCHLUESSEL in .env)"
echo

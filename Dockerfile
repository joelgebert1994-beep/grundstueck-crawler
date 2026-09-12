# Backend der Potenzial-Engine als Container.
#
# WICHTIG -- Bau-Kontext:
# Der Dienst braucht ZWEI Verzeichnisse, die nebeneinander liegen:
#
#   <eltern>/grundstueck-crawler/   Engine und Webdienst
#   <eltern>/Crawler/kern/          Datenschicht (Projekte, Varianten, Markt)
#
# webapp.py sucht die Datenschicht ueber `../Crawler`. Damit dieselbe
# Auffindung im Container gilt, wird aus dem ELTERNVERZEICHNIS gebaut:
#
#   docker build -f grundstueck-crawler/Dockerfile -t potenzial-engine .
#
# Ein Bau aus grundstueck-crawler/ heraus wuerde starten, aber ohne
# Projektablage laufen -- und das faellt erst auf, wenn jemand ein Projekt
# speichern will.

FROM python:3.12-slim

# Nicht als root laufen. GEOS wird von shapely als Rad mitgeliefert, es
# braucht also keine Systempakete -- das haelt das Abbild klein.
RUN useradd --create-home --uid 10001 dienst

WORKDIR /app

# Zuerst nur die Abhaengigkeiten: diese Ebene bleibt zwischengespeichert,
# solange sich requirements.txt nicht aendert.
COPY grundstueck-crawler/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Dann der Code. Die Verzeichnisnamen bleiben, damit `../Crawler` stimmt.
COPY grundstueck-crawler/ /app/grundstueck-crawler/
COPY Crawler/kern/ /app/Crawler/kern/

# Die Datenbank liegt NICHT im Abbild, sondern auf einem persistenten
# Datentraeger. Ein Abbild wird bei jedem Einspielen ersetzt -- Projekte,
# Varianten und Vergleichsobjekte duerfen das nicht sein.
ENV KERN_DB_PFAD=/daten/kern.db \
    UMGEBUNG=produktion \
    PORT=8787 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /daten && chown -R dienst:dienst /daten /app

USER dienst
WORKDIR /app/grundstueck-crawler
EXPOSE 8787

# Der Health-Check unterscheidet erreichbar von einsatzbereit -- genau das,
# was die Plattform wissen muss, bevor sie Verkehr schickt.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,json,os,sys; \
d=json.load(urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8787')+'/health', timeout=4)); \
sys.exit(0 if d.get('ok') else 1)"

CMD ["python", "webapp.py"]

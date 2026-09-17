@echo off
REM ====================================================================
REM  gebimo Potenzial-Engine -- lokal starten
REM
REM  Doppelklick genuegt. Startet das Backend, oeffnet den Browser.
REM  Kein Tunnel, kein Oracle, kein Claude noetig.
REM
REM  Beenden: dieses Fenster schliessen oder Strg+C.
REM ====================================================================

setlocal
cd /d "%~dp0"
title gebimo Potenzial-Engine (lokal)

echo.
echo   gebimo Potenzial-Engine -- lokaler Start
echo   =========================================
echo.

REM --- Python vorhanden? ---------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo   FEHLER: Python wurde nicht gefunden.
    echo   Installieren von https://www.python.org/downloads/
    echo   Dabei "Add python.exe to PATH" ankreuzen.
    echo.
    pause
    exit /b 1
)

REM --- Abhaengigkeiten vorhanden? ------------------------------------
python -c "import requests, shapely, google.genai" >nul 2>&1
if errorlevel 1 (
    echo   Es fehlen Pakete. Werden jetzt installiert ...
    echo.
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   FEHLER: Installation fehlgeschlagen.
        pause
        exit /b 1
    )
    echo   Fertig.
    echo.
)

REM --- Schluessel fuer die Reglementsauswertung ----------------------
REM  Ohne ihn laeuft alles ausser Modul 2 -- die Analyse bricht dann mit
REM  einer klaren Meldung ab, statt eine Zone zu raten.
if "%GEMINI_API_KEY%"=="" (
    if exist "%~dp0.env.lokal" (
        for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env.lokal") do (
            if /i "%%a"=="GEMINI_API_KEY" set "GEMINI_API_KEY=%%b"
        )
    )
)

REM --- Zugangsschluessel fuer den oeffentlichen Weg -------------------
REM  Ist das Backend ueber einen Tunnel oeffentlich erreichbar, ist dies
REM  der einzige Riegel davor, dass jeder im Internet /analyze aufrufen
REM  kann -- und jeder Aufruf kostet Rechenzeit und LLM-Kontingent.
REM  /marktdaten/loeschen liegt hinter demselben Riegel.
REM  Ohne Schluessel laeuft alles lokal ganz normal weiter; der Riegel
REM  greift nur, wenn einer gesetzt ist.
REM  Derselbe Wert gehoert in Cloudflare Pages als BACKEND_SCHLUESSEL.
if "%ZUGANGSSCHLUESSEL%"=="" (
    if exist "%~dp0.env.lokal" (
        for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env.lokal") do (
            if /i "%%a"=="ZUGANGSSCHLUESSEL" set "ZUGANGSSCHLUESSEL=%%b"
        )
    )
)
if "%GEMINI_API_KEY%"=="" (
    echo   HINWEIS: GEMINI_API_KEY ist nicht gesetzt.
    echo   Die Auswertung der Bau- und Nutzungsordnung wird fehlschlagen.
    echo.
    echo   Kostenlos holen:  https://aistudio.google.com/apikey
    echo   Dann eine Datei .env.lokal neben diese .bat legen mit der Zeile:
    echo       GEMINI_API_KEY=dein-schluessel
    echo.
)

REM --- Port frei? ----------------------------------------------------
REM  NICHT ueber netstat pruefen: die Zustandsbezeichnung ist uebersetzt.
REM  Auf einem deutschen Windows steht dort ABHOEREN, nicht LISTENING --
REM  eine Suche nach "LISTENING" findet nie etwas, start.bat wuerde einen
REM  zweiten Server starten und Python mit "address already in use"
REM  abbrechen. Python selbst zu fragen ist sprachunabhaengig und exakt.
set PORT=8787
python -c "import socket,sys; s=socket.socket(); r=s.connect_ex(('127.0.0.1',%PORT%)); s.close(); sys.exit(0 if r==0 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo   Port %PORT% ist belegt -- laeuft das Werkzeug schon?
    echo   Browser oeffnen: http://localhost:%PORT%
    echo.
    start "" "http://localhost:%PORT%"
    pause
    exit /b 0
)

echo   Backend startet auf http://localhost:%PORT%
echo   Der Browser oeffnet sich gleich von selbst.
echo.
echo   Zum Beenden dieses Fenster schliessen.
echo   ---------------------------------------------------------------
echo.

REM Browser mit kurzer Verzoegerung, damit der Dienst zuerst hoert.
start "" /b cmd /c "timeout /t 3 >nul & start "" "http://localhost:%PORT%""

python webapp.py

echo.
echo   Backend beendet.
pause

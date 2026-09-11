"""Potenzial-Engine -- Grundstuecks-Potenzialanalyse fuer die Schweiz.

Zustandslos: dieses Paket fuehrt keine Datenbank, kennt keinen Scheduler und
speichert nichts. Es rechnet aus amtlichen Geodaten und kommunalen Reglementen
das bauliche Potenzial einer Parzelle und liefert zu jedem Wert einen
Quellennachweis.

Module:
    modul1_geodata                 Geocoding, Parzelle, GWR, OEREB, Umgebung
    modul1b_nutzungsklassifikation Grundnutzung/Sondernutzungsplan (MGDM)
    modul2_bzo_analysis            LLM-Auswertung kommunaler BZO-Dokumente
    modul3_financial               Zonen-Matching, Residualwert, Szenarien
    modul4_export                  Dossier-Export (zurueckgestellt)
    baubereich                     Baubereichs-Polygon, Grenzabstaende (G1)
    restriktionsgeometrie          Gewaesserraum, Waldabstand, Baulinien
    g1_verdrahtung                 Verdrahtung Modul 1/2 -> G1
    sia416_flaechen                SIA-416-Flaechenkaskade
    quellen                        Quellennachweis pro Einzelwert
    referenzprojekte               Referenzdaten fuer Flaechenverhaeltnisse
    entwicklungsszenarien          Szenario-Taxonomie (ohne Rechenlogik)

Die oeffentliche Aufrufschnittstelle (analysiere_grundstueck,
berechne_wirtschaftlichkeit) wird in Phase 0.4 hier ergaenzt; bis dahin werden
die Module einzeln importiert.
"""

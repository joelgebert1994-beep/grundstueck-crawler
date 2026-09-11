"""
Modul 4: Ergebnis-Export (JSON / HTML-Dossier)
====================================================
Nimmt das fertige Ergebnis von run_full_pipeline() (Modul 1+2+3) entgegen und
schreibt es als:
  - JSON (strukturiert, fuer Weiterverarbeitung/Archivierung)
  - HTML (druckbares Dossier fuer Kunden/Eigentuemer -- im Browser oeffnen und
    ueber "Drucken -> Als PDF speichern" zu einem PDF machen; kein zusaetzlicher
    PDF-Renderer/keine Systemabhaengigkeit wie WeasyPrint noetig)

WICHTIG: Der Export bildet nur ab, was die Engine tatsaechlich berechnet hat --
inkl. Bandbreiten-Faellen (mehrdeutige Zonen-Zuordnung) und allen Kostenraten-
Annahmen. Es werden keine zusaetzlichen Werte erfunden oder geglaettet.

CLI:
    python modul4_export.py --address "Bahnhofstrasse 1, 8001 Zuerich" --verkaufspreis-m2 13000 --out dossier.html
    python modul4_export.py --from-json ergebnis.json --out dossier.html

Als Bibliothek:
    from modul4_export import render_html_dossier
    html = render_html_dossier(pipeline_result)
"""

from __future__ import annotations

import argparse
import html as html_escape_mod
import json
import sys
from datetime import datetime
from typing import Any, Optional


def _esc(value: Any) -> str:
    """HTML-escaped String-Repraesentation, None wird als Gedankenstrich dargestellt."""
    if value is None:
        return "–"
    return html_escape_mod.escape(str(value))


def _fmt_chf(value: Optional[float]) -> str:
    if value is None:
        return "–"
    return f"{value:,.0f}".replace(",", "'") + " CHF"


def _fmt_m2(value: Optional[float]) -> str:
    if value is None:
        return "–"
    return f"{value:,.1f}".replace(",", "'") + " m²"


CSS = """
body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; color: #1a1a1a; max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5; }
h1 { font-size: 1.6rem; border-bottom: 3px solid #1a3d5c; padding-bottom: 0.5rem; }
h2 { font-size: 1.2rem; color: #1a3d5c; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; }
h3 { font-size: 1.0rem; color: #333; margin-top: 1.2rem; }
table { width: 100%; border-collapse: collapse; margin: 0.8rem 0; font-size: 0.92rem; }
th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
th { background: #f4f6f8; font-weight: 600; }
.meta { color: #666; font-size: 0.85rem; }
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 3px; font-size: 0.78rem; font-weight: 600; }
.badge-warn { background: #fff3cd; color: #664d03; }
.badge-ok { background: #d1e7dd; color: #0a3622; }
.badge-info { background: #cfe2ff; color: #084298; }
.callout { background: #fff8e1; border-left: 4px solid #f0ad4e; padding: 0.8rem 1rem; margin: 1rem 0; font-size: 0.92rem; }
.disclaimer { background: #f4f6f8; border-left: 4px solid #999; padding: 0.9rem 1.1rem; margin-top: 2.5rem; font-size: 0.85rem; color: #444; }
.szenario-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin: 1rem 0; }
.szenario-card { border: 1px solid #ddd; border-radius: 6px; padding: 0.9rem 1rem; }
.szenario-card h4 { margin: 0 0 0.5rem 0; font-size: 0.95rem; }
.residualwert { font-size: 1.3rem; font-weight: 700; color: #1a3d5c; }
.quelle-liste { font-size: 0.8rem; color: #777; }
@media print {
  body { margin: 0; max-width: none; }
  .no-print { display: none; }
}
"""


def _render_szenario_block(szenario_name: str, szenario_daten: dict[str, Any]) -> str:
    bgf = szenario_daten["sia416_bgf"]
    bkp = szenario_daten["bkp_kosten"]
    res = szenario_daten["residualwert"]
    delta = bgf.get("delta_zum_bestand")

    delta_html = ""
    if delta:
        delta_html = f"""
        <tr><td>Bestand (Referenz)</td><td>{_fmt_m2(delta['bestand_bgf_m2'])}</td></tr>
        <tr><td>Delta zum Potenzial</td><td>{_fmt_m2(delta['delta_bgf_m2'])} ({delta['delta_prozent']:.0%})</td></tr>
        <tr><td>Empfehlung</td><td><span class="badge badge-info">{_esc(delta['empfehlung'])}</span></td></tr>
        """

    return f"""
    <div class="szenario-card">
      <h4>{_esc(szenario_name)}</h4>
      <table>
        <tr><td>Effektive AZ</td><td>{bgf['effektive_az']}</td></tr>
        <tr><td>Max. BGF</td><td>{_fmt_m2(bgf['max_realisierbare_bgf_m2'])}</td></tr>
        <tr><td>Realisierbare NNF</td><td>{_fmt_m2(bgf['realisierbare_nnf_m2'])}</td></tr>
        {delta_html}
        <tr><td>Baukosten BKP 1-9</td><td>{_fmt_chf(bkp['gesamtbaukosten_bkp1_9_chf'])}</td></tr>
        <tr><td>Ausbaustandard</td><td>{_esc(bkp['annahmen']['ausbaustandard'])}</td></tr>
        <tr><td>GDV (Soll-Erloes)</td><td>{_fmt_chf(res['gdv_soll_erloes_chf'])}</td></tr>
        <tr><td>Marge ({res['marge_prozent_vom_gdv']:.0%})</td><td>{_fmt_chf(res['marge_chf'])}</td></tr>
      </table>
      <div class="residualwert">{_fmt_chf(res['residualwert_max_landkaufpreis_chf'])}</div>
      <div class="meta">max. Landkaufpreis</div>
    </div>
    """


def render_html_dossier(pipeline_result: dict[str, Any]) -> str:
    """Rendert das komplette Pipeline-Ergebnis (Modul 1+2+3) als eigenstaendiges
    HTML-Dossier. Enthaelt sowohl den eindeutigen Fall als auch den
    Bandbreiten-Fall (mehrdeutige Zonenzuordnung, siehe modul3_financial.match_zone).
    """
    adresse = pipeline_result.get("adresse", "?")
    m1 = pipeline_result.get("modul1_geodaten", {})
    m2 = pipeline_result.get("modul2_bzo_analyse", {})
    m3 = pipeline_result.get("modul3_financial", {})

    kataster = m1.get("kataster", {})
    gemeinde = m1.get("gemeinde", {})
    gwr = m1.get("gwr", {})
    oereb = m1.get("oereb", {})

    grunddaten_html = f"""
    <table>
      <tr><th>Adresse</th><td>{_esc(adresse)}</td></tr>
      <tr><th>Gemeinde / Kanton</th><td>{_esc(gemeinde.get('gemeinde'))} / {_esc(oereb.get('kanton'))}</td></tr>
      <tr><th>EGRID</th><td>{_esc(kataster.get('egrid'))}</td></tr>
      <tr><th>Parzellenfläche</th><td>{_fmt_m2(kataster.get('flaeche_m2'))} <span class="meta">(Quelle: {_esc(kataster.get('flaeche_quelle'))})</span></td></tr>
      <tr><th>GWR-Bestand</th><td>Baujahr {_esc(gwr.get('baujahr'))}, {_esc(gwr.get('anzahl_geschosse'))} Geschosse, {_fmt_m2(gwr.get('grundflaeche_m2'))} Grundfläche</td></tr>
      <tr><th>Amtliche Zone(n)</th><td>{', '.join(_esc(z.get('zonenbezeichnung')) for z in oereb.get('amtliche_zonenbezeichnungen', [])) or '–'}</td></tr>
    </table>
    """

    sonderregelungen = m2.get("sonderregelungen", [])
    sonder_html = ""
    if sonderregelungen:
        rows = "".join(
            f"<tr><td>{_esc(s.get('typ'))}</td><td>{_esc(s.get('titel'))}</td>"
            f"<td>{_esc(s.get('bonus_effekt'))}</td><td>{_esc(s.get('artikel_referenz'))}</td></tr>"
            for s in sonderregelungen
        )
        sonder_html = f"""
        <h2>Sonderregelungen &amp; Ausnahmen (aus der BZO)</h2>
        <table>
          <tr><th>Typ</th><th>Titel</th><th>Effekt</th><th>Artikel</th></tr>
          {rows}
        </table>
        """

    meta = m3.get("_meta", {})
    modus = meta.get("auflösungsmodus", "?")

    if modus == "bandbreite_mehrdeutig":
        zusammenfassung = m3["bandbreite_zusammenfassung"]
        callout = f"""
        <div class="callout">
          <span class="badge badge-warn">Bandbreite statt Einzelwert</span><br><br>
          {_esc(zusammenfassung['hinweis'])}<br><br>
          <strong>Residualwert-Spanne (Base Case): {_fmt_chf(zusammenfassung['minimum_residualwert_base_case_chf'])}
          bis {_fmt_chf(zusammenfassung['maximum_residualwert_base_case_chf'])}</strong>
        </div>
        """
        szenarien_html = "<h2>Finanzielle Szenarien pro moeglichem Zonen-Subtyp</h2>"
        for subtyp, run in m3["bandbreite_je_subtyp"].items():
            szenarien_html += f"<h3>Subtyp: {_esc(subtyp)} (AZ={_esc(run['zone'].get('ausnuetzungsziffer_az'))})</h3>"
            szenarien_html += '<div class="szenario-cols">'
            for szenario_name, szenario_daten in run["szenarien"].items():
                szenarien_html += _render_szenario_block(szenario_name, szenario_daten)
            szenarien_html += "</div>"
    elif modus == "eindeutig":
        callout = ""
        zonen_zuordnung = m3.get("zonen_zuordnung", {})
        callout = f"""
        <div class="callout" style="background:#f0f7f1;border-left-color:#4caf50;">
          <span class="badge badge-ok">Zone eindeutig zugeordnet</span><br><br>
          Amtliche Zone {_esc(zonen_zuordnung.get('amtliche_zonenbezeichnung'))} &rarr;
          BZO-Zone {_esc(zonen_zuordnung.get('zone', {}).get('zonenbezeichnung'))}
          (Ähnlichkeit: {zonen_zuordnung.get('aehnlichkeit')})
        </div>
        """
        szenarien_html = '<h2>Finanzielle Szenarien</h2><div class="szenario-cols">'
        for szenario_name, szenario_daten in m3.get("szenarien", {}).items():
            szenarien_html += _render_szenario_block(szenario_name, szenario_daten)
        szenarien_html += "</div>"
    else:
        callout = f'<div class="callout"><span class="badge badge-warn">Keine Finanzberechnung</span><br>{_esc(m3.get("error", "Unbekannter Zustand"))}</div>'
        szenarien_html = ""

    generiert_am = datetime.now().strftime("%d.%m.%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Immo-Potenzial-Dossier -- {_esc(adresse)}</title>
<style>{CSS}</style>
</head>
<body>
  <h1>Immo-Potenzial-Dossier</h1>
  <p class="meta">Generiert am {generiert_am} &middot; Immo-Potenzial-Engine (Modul 1-3)</p>

  <h2>Grunddaten</h2>
  {grunddaten_html}

  {sonder_html}

  {callout}

  {szenarien_html}

  <div class="disclaimer">
    <strong>Rechtlicher/fachlicher Hinweis:</strong> Dies ist eine KI-gestuetzte
    Grobschaetzung (Vorprojekt-Genauigkeit, SIA 102 Kostengenauigkeitsstufe
    ±15-25%), keine Rechtsberatung, keine Kostenplanung und keine Bewertung
    nach anerkannten Bewertungsstandards. Zonendaten stammen aus einer
    automatisierten Lektuere der kommunalen Bau-/Zonenordnung (Modul 2) und
    sind vor einer Kaufentscheidung durch einen Fachplaner/Bewerter sowie
    anhand des amtlichen Zonenplans zu verifizieren. Alle Kostenraten
    (BKP-Ansaetze, Marge, Wirkungsgrad) sind transparente Modellannahmen,
    keine verifizierten Marktdaten -- siehe 'annahmen' im JSON-Export fuer die
    vollstaendigen Parameter.
  </div>
</body>
</html>"""


def export_json(pipeline_result: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pipeline_result, f, ensure_ascii=False, indent=2)


def export_html(pipeline_result: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html_dossier(pipeline_result))


def main() -> None:
    parser = argparse.ArgumentParser(description="Modul 4: Ergebnis-Export (JSON/HTML-Dossier)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--address", help="Fuehrt die komplette Pipeline aus (Modul 1->2->3)")
    source.add_argument("--from-json", help="Nutzt ein bereits vorhandenes Pipeline-Ergebnis (JSON-Datei)")
    parser.add_argument("--verkaufspreis-m2", type=float, help="Erforderlich bei --address")
    parser.add_argument("--backend", choices=["gemini", "claude"], default=None)
    parser.add_argument("--out", required=True, help="Ausgabepfad, Endung .html oder .json bestimmt das Format")
    args = parser.parse_args()

    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as f:
            pipeline_result = json.load(f)
    else:
        if args.verkaufspreis_m2 is None:
            print(json.dumps({"error": "--verkaufspreis-m2 ist bei --address erforderlich."}, ensure_ascii=False))
            sys.exit(1)
        from modul3_financial import run_full_pipeline

        pipeline_result = run_full_pipeline(args.address, verkaufspreis_chf_pro_m2=args.verkaufspreis_m2, backend=args.backend)

    if args.out.lower().endswith(".json"):
        export_json(pipeline_result, args.out)
    else:
        export_html(pipeline_result, args.out)

    print(f"Exportiert nach: {args.out}")


if __name__ == "__main__":
    main()

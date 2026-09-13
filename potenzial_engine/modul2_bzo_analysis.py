"""
Modul 2: Deep Context & AI Analysis (Gemini/Claude Engine, austauschbar)
========================================================
Nimmt eine kommunale Bau- und Zonenordnung (BZO) als PDF entgegen (typischerweise
die "rechtsvorschriften"-URL, die Modul 1 aus dem OEREB-Extrakt ermittelt hat) und
liefert strukturierte, schema-validierte Kennzahlen zurueck:

ZWEI AUSTAUSCHBARE BACKENDS (identisches Output-Schema, damit Modul 3
unveraendert bleibt):
  - "gemini" (STANDARD): Google Gemini API, kostenloses Tier ueber Google AI
    Studio (aistudio.google.com/apikey) -- kein Guthaben/Kreditkarte noetig,
    verifiziert ueber die offizielle Pricing-Seite (Stand 2026-08-26: Ein-
    und Ausgabe "Free of charge" fuer gemini-2.5-flash/gemini-3.7-flash).
    Braucht die Umgebungsvariable GEMINI_API_KEY.
  - "claude": Anthropic Claude API (kostenpflichtig, praeziseres Modell).
    Braucht ANTHROPIC_API_KEY. Ueber backend="claude" explizit waehlbar.

Der Standard ist bewusst "gemini", damit die Pipeline ohne Anthropic-Kosten
laeuft -- es gibt KEINEN stillen Fallback auf Claude, falls GEMINI_API_KEY
fehlt (das wuerde ungewollt Kosten verursachen), sondern eine klare
Fehlermeldung, die auf den fehlenden Key hinweist.

  1. BZO-Text-Extraction: liest das komplette PDF in einem Durchgang (Claude
     verarbeitet das Dokument direkt, kein Chunking/OCR noetig).
  2. Delta-Finder: sucht gezielt nach Basis-Kennzahlen (AZ, aBGF, BMZ,
     Gesamthoehe, Grenzabstaende) je erkannter Zone UND nach Sonderrechten
     (Minergie-/Energieboni, Arealueberbauung, Attika-Anrechnung, Hanglagen-
     Privilegien).
  3. Structured JSON Output: erzwungen per output_config.format (json_schema),
     damit Modul 3 direkt ohne Freitext-Parsing weiterarbeiten kann.

WICHTIG zum Scope: Dieses Modul extrahiert ALLE in der BZO definierten Zonen
und Sonderregelungen. Welche Zone konkret auf eine bestimmte Parzelle zutrifft,
ergibt sich aus den OEREB-Themen/PublicLawRestrictions von Modul 1 -- der
Abgleich "Zone X gilt fuer Parzelle Y" ist bewusst NICHT Teil dieses Moduls
(das ist ein einfacher Nachschlage-Schritt in der Orchestrierung / Modul 3).

Rechtlicher Hinweis: Die Extraktion ist eine KI-gestuetzte Lesehilfe, keine
Rechtsberatung. Jeder Wert traegt ein Zitat + Artikel-Referenz zur Verifikation,
und Unklarheiten werden explizit als solche ausgewiesen statt geraten.

CLI:
    python modul2_bzo_analysis.py --url "https://oerebdocs.zh.ch/getDoc?docid=6"
    python modul2_bzo_analysis.py --file "./bauordnung.pdf"

Als Bibliothek:
    from potenzial_engine.modul2_bzo_analysis import analyze_bzo_document
    result = analyze_bzo_document(pdf_bytes=..., gemeinde="Zuerich", kanton="ZH")
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from typing import Any, Optional

import requests

# Gemeinsame Abrufmechanik (Wiederholung, Browser-User-Agent als Zweitversuch).
# Modul 1 importiert Modul 2 nicht -- kein Zyklus.
from .modul1_geodata import _get_mit_wiederholung

DEFAULT_BACKEND = "gemini"
GEMINI_MODEL = "gemini-3.6-flash"  # gemini-2.5-flash ist fuer neue Nutzer nicht mehr verfuegbar (live per API-Fehler bestaetigt, 2026-08-26)
CLAUDE_MODEL = "claude-opus-5"
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB roh -- bleibt nach Base64 (~+33%) sicher unter dem 32-MB-Requestlimit
DEFAULT_TIMEOUT = 60
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_DELAY_S = 8  # kostenloses Tier hat niedrige Requests/Minute -- 429 ist erwartbar, kein Fehler


class Modul2Error(Exception):
    """Fehler innerhalb der BZO-Analyse-Pipeline."""


# ---------------------------------------------------------------------------
# PDF-Beschaffung
# ---------------------------------------------------------------------------

def download_pdf(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """Laedt ein BZO-/Reglements-PDF von einer URL (z.B. aus Modul 1s
    'rechtsvorschriften') und validiert Content-Type sowie Groesse.

    Nutzt dieselbe Wiederholungslogik wie Modul 1: Gemeinde-Websites weisen
    unbekannte User-Agents teils ab (live beobachtet: Berlingen TG, HTTP 403
    -- ein ganzer Analyselauf scheiterte daran, obwohl das Dokument
    oeffentlich ist). Beim zweiten Versuch wird ein Browser-User-Agent
    verwendet.
    """
    resp = _get_mit_wiederholung(url, timeout=timeout)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower():
        raise Modul2Error(
            f"URL liefert kein PDF (Content-Type: {content_type!r}) -- {url}"
        )

    data = resp.content
    if len(data) > MAX_PDF_BYTES:
        raise Modul2Error(
            f"PDF zu gross ({len(data) / 1024 / 1024:.1f} MB > "
            f"{MAX_PDF_BYTES / 1024 / 1024:.0f} MB Limit) -- {url}"
        )
    return data


# ---------------------------------------------------------------------------
# JSON-Schema fuer den erzwungenen strukturierten Output
# ---------------------------------------------------------------------------

_BEDINGTER_WERT_SCHEMA = {
    "type": "object",
    "properties": {
        "bedingung_text": {
            "type": "string",
            "description": (
                "Woertliche/knappe Beschreibung der Bedingung, unter der der "
                "alternative Wert gilt, z.B. 'Schraegdach mit First mind. 2.50 m "
                "von der Fassade zurueckversetzt, traufseitige Fassadenhoehe "
                "max. 10.00 m'."
            ),
        },
        "wert_unter_bedingung": {"type": ["number", "null"]},
        "artikel_referenz": {"type": ["string", "null"]},
    },
    "required": ["bedingung_text", "wert_unter_bedingung", "artikel_referenz"],
    "additionalProperties": False,
}

# Eine einzelne baurechtliche Kennzahl mit vollstaendiger Herkunfts- und
# Unsicherheitsangabe. "wert" ist AUSSCHLIESSLICH der Normalfall (ohne
# Sonderbedingung) -- ein Dokument, das z.B. "10.00 m normal / 11.50 m bei
# Schraegdach mit Zusatzbedingungen" nennt, darf NICHT durch Auswahl des
# hoeheren oder tieferen Werts aufgeloest werden. Der bedingte Wert gehoert
# strukturiert in "bedingungen", damit er spaeter (G1) verfuegbar bleibt,
# statt beim Parsen verloren zu gehen.
_KENNZAHL_SCHEMA = {
    "type": "object",
    "properties": {
        "wert": {
            "type": ["number", "null"],
            "description": "Regelwert OHNE Sonderbedingung. null falls nicht bestimmbar -- niemals schaetzen oder einen Default einsetzen.",
        },
        "einheit": {
            "type": ["string", "null"],
            "description": "z.B. 'm', '%'. null bei dimensionslosen Ziffern (AZ/aBGF/BMZ/UEZ) oder falls wert null ist.",
        },
        "quelle_dokument": {
            "type": ["string", "null"],
            "description": "Titel des Dokuments, aus dem dieser Wert stammt (wichtig, wenn mehrere Dokumente gemeinsam analysiert wurden).",
        },
        "artikel_referenz": {
            "type": ["string", "null"],
            "description": "Paragraph/Artikel-Nummer der BZO, z.B. '§ 18 Abs. 2'.",
        },
        "zitat": {
            "type": ["string", "null"],
            "description": "Kurzes woertliches Zitat aus dem Dokument als Beleg (max. ~40 Woerter).",
        },
        "confidence": {
            "type": "string",
            "enum": ["hoch", "mittel", "niedrig", "nicht_bestimmbar"],
            "description": (
                "'hoch': expliziter Zahlenwert in einer eindeutig dieser Zone zugeordneten "
                "Tabelle/einem Artikel gefunden. 'mittel': Wert musste abgeleitet/aus anderen "
                "Angaben berechnet werden, oder stammt aus einem nur indirekt zugeordneten "
                "Dokument (z.B. kantonales Rahmenrecht statt kommunalem Reglement). "
                "'niedrig': Wert gefunden, aber mit relevanter Restunsicherheit (mehrdeutige "
                "Zuordnung, widerspruechliche Dokumente). 'nicht_bestimmbar': kein Wert "
                "gefunden -- dann MUSS wert=null sein."
            ),
        },
        "bedingungen": {
            "type": "array",
            "items": _BEDINGTER_WERT_SCHEMA,
            "description": "Alternative Werte unter spezifischen Bedingungen (z.B. andere Dachform, andere Nutzung). Leeres Array falls es keine gibt.",
        },
        "unklarheit": {
            "type": ["string", "null"],
            "description": "Kurze Begruendung, falls der Wert unsicher/mehrdeutig ist oder gar nicht bestimmt werden konnte. null falls keine Unklarheit besteht.",
        },
    },
    "required": ["wert", "einheit", "quelle_dokument", "artikel_referenz", "zitat", "confidence", "bedingungen", "unklarheit"],
    "additionalProperties": False,
}

# Zonenkennzahlen, die jeweils als vollstaendiges _KENNZAHL_SCHEMA-Objekt
# (nicht als blosse Zahl) im Output erscheinen.
_ZONE_KENNZAHL_FELDER = (
    "ausnuetzungsziffer_az", "anrechenbare_geschossflaechenziffer_abgf",
    "baumassenziffer_bmz", "ueberbauungsziffer_uz", "gesamthoehe_m",
    "gebaeudehoehe_m", "grenzabstand_klein_m", "grenzabstand_gross_m",
    "strassenabstand_m", "vollgeschosse_max",
)

_ZONE_SCHEMA = {
    "type": "object",
    "properties": {
        "zonenbezeichnung": {
            "type": "string",
            "description": "Wortlaut der Zonenbezeichnung, z.B. 'W2', 'Kernzone', 'Zentrumszone Z4'.",
        },
        **{feld: _KENNZAHL_SCHEMA for feld in _ZONE_KENNZAHL_FELDER},
    },
    "required": ["zonenbezeichnung", *_ZONE_KENNZAHL_FELDER],
    "additionalProperties": False,
}

_SONDERREGELUNG_SCHEMA = {
    "type": "object",
    "properties": {
        "typ": {
            "type": "string",
            "enum": [
                "minergie_energiebonus",
                "arealueberbauung",
                "attika_anrechnung",
                "hanglagen_privileg",
                "denkmalschutz_ausnahme",
                "sonstiges",
            ],
        },
        "titel": {"type": "string"},
        "beschreibung": {"type": "string"},
        "bonus_effekt": {
            "type": ["string", "null"],
            "description": "Konkreter Effekt, z.B. '+10% AZ' oder 'zusaetzliches Vollgeschoss anrechenbar'.",
        },
        "gilt_fuer_zonen": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Zonenbezeichnungen, fuer die die Regel gilt; leer falls zonenuebergreifend.",
        },
        "voraussetzungen": {"type": ["string", "null"]},
        "artikel_referenz": {"type": ["string", "null"]},
        "zitat": {"type": ["string", "null"]},
    },
    "required": [
        "typ", "titel", "beschreibung", "bonus_effekt", "gilt_fuer_zonen",
        "voraussetzungen", "artikel_referenz", "zitat",
    ],
    "additionalProperties": False,
}

BZO_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "dokument_titel": {"type": ["string", "null"]},
        "gemeinde": {"type": ["string", "null"]},
        "stand_datum": {
            "type": ["string", "null"],
            "description": "Stand/Genehmigungsdatum des Reglements, falls im Dokument angegeben.",
        },
        "erkannte_zonen": {"type": "array", "items": _ZONE_SCHEMA},
        "sonderregelungen": {"type": "array", "items": _SONDERREGELUNG_SCHEMA},
        "unklarheiten_und_pruefhinweise": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Stellen, an denen das Dokument mehrdeutig ist oder manuelle Pruefung noetig ist.",
        },
    },
    "required": [
        "dokument_titel", "gemeinde", "stand_datum",
        "erkannte_zonen", "sonderregelungen", "unklarheiten_und_pruefhinweise",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Dieselben Felder als Pydantic-Modelle fuer Gemini (response_json_schema
# akzeptiert laut Google-Dokumentation Pydantic-generierte Schemas "out of
# the box" -- eigene Modelle statt den Claude-Rohschema-Dict wiederzuverwenden,
# weil Gemini "additionalProperties": false / Union-Typen ["string","null"]
# nicht garantiert gleich interpretiert wie Claudes striktes json_schema).
# Feldnamen sind 1:1 identisch zu _ZONE_SCHEMA/_SONDERREGELUNG_SCHEMA, damit
# Modul 3 unabhaengig vom gewaehlten Backend dieselbe Struktur bekommt.
# ---------------------------------------------------------------------------
try:
    from typing import Literal

    from pydantic import BaseModel as _GeminiBaseModel
except ImportError:  # pydantic ist bereits ueber Modul 1 (Topographie/Umgebung) Pflicht, aber defensiv pruefen
    _GeminiBaseModel = None

if _GeminiBaseModel is not None:
    class _BedingterWertGemini(_GeminiBaseModel):
        bedingung_text: str
        wert_unter_bedingung: Optional[float] = None
        artikel_referenz: Optional[str] = None

    class _KennzahlGemini(_GeminiBaseModel):
        wert: Optional[float] = None
        einheit: Optional[str] = None
        quelle_dokument: Optional[str] = None
        artikel_referenz: Optional[str] = None
        zitat: Optional[str] = None
        confidence: Literal["hoch", "mittel", "niedrig", "nicht_bestimmbar"]
        bedingungen: list[_BedingterWertGemini] = []
        unklarheit: Optional[str] = None

    class _ZoneGemini(_GeminiBaseModel):
        zonenbezeichnung: str
        ausnuetzungsziffer_az: _KennzahlGemini
        anrechenbare_geschossflaechenziffer_abgf: _KennzahlGemini
        baumassenziffer_bmz: _KennzahlGemini
        ueberbauungsziffer_uz: _KennzahlGemini
        gesamthoehe_m: _KennzahlGemini
        gebaeudehoehe_m: _KennzahlGemini
        grenzabstand_klein_m: _KennzahlGemini
        grenzabstand_gross_m: _KennzahlGemini
        strassenabstand_m: _KennzahlGemini
        vollgeschosse_max: _KennzahlGemini

    class _SonderregelungGemini(_GeminiBaseModel):
        typ: Literal[
            "minergie_energiebonus", "arealueberbauung", "attika_anrechnung",
            "hanglagen_privileg", "denkmalschutz_ausnahme", "sonstiges",
        ]
        titel: str
        beschreibung: str
        bonus_effekt: Optional[str] = None
        gilt_fuer_zonen: list[str] = []
        voraussetzungen: Optional[str] = None
        artikel_referenz: Optional[str] = None
        zitat: Optional[str] = None

    class _BzoAnalyseGemini(_GeminiBaseModel):
        dokument_titel: Optional[str] = None
        gemeinde: Optional[str] = None
        stand_datum: Optional[str] = None
        erkannte_zonen: list[_ZoneGemini] = []
        sonderregelungen: list[_SonderregelungGemini] = []
        unklarheiten_und_pruefhinweise: list[str] = []


SYSTEM_PROMPT = (
    "Du bist ein Experte fuer Schweizer Bau- und Zonenordnungen (BZO) und "
    "kommunales Baurecht. Du liest die vollstaendigen beigefuegten Dokumente "
    "und extrahierst NUR, was tatsaechlich darin steht -- erfinde keine "
    "Zahlen und setze NIE einen Default-/Schaetzwert ein. Suche systematisch "
    "nach ALLEN Zonentypen (Wohnzonen, Kernzonen, Zentrumszonen, "
    "Gewerbezonen etc.) mit ihren jeweiligen Kennzahlen: Ausnuetzungsziffer "
    "AZ, anrechenbare Geschossflaechenziffer aBGF, Baumassenziffer BMZ, "
    "Ueberbauungsziffer/Grundflaechenziffer UEZ/GFZ, Gesamthoehe, "
    "Gebaeudehoehe, kleiner und grosser Grenzabstand, Strassenabstand, "
    "max. Vollgeschosse. "
    "WICHTIG zum Strassenabstand ('strassenabstand_m'): das ist der "
    "Abstand gegenueber einer Strasse/einem oeffentlichen Verkehrsraum -- "
    "eine EIGENSTAENDIGE Groesse, oft im kantonalen Strassengesetz oder "
    "Baugesetz geregelt (z.B. 'Strassenabstand', 'Abstand von Strassen', "
    "'Abstand zur Strassengrenze', 'Vorgarten'), nicht zwingend im "
    "Zonenschema der Gemeinde. Kleiner und grosser Grenzabstand "
    "unterscheiden dagegen schmale und breite Gebaeudeseite gegenueber "
    "NACHBARgrundstuecken. Leite den Strassenabstand deshalb NIEMALS aus "
    "dem kleinen oder grossen Grenzabstand ab und setze ihn nicht mit "
    "ihnen gleich. Findest du keinen eigenstaendigen Strassenabstand, MUSS "
    "'wert' null und 'confidence' 'nicht_bestimmbar' sein. Gilt statt "
    "eines Abstandsmasses eine Baulinie, vermerke das in 'unklarheit' -- "
    "Baulinien werden separat aus den Geodaten uebernommen. "
    "Suche zusaetzlich gezielt nach Sonderrechten und Ausnahmeregelungen: "
    "Minergie-/Energieboni, Arealueberbauungsprivilegien, Attikageschoss-"
    "Anrechenbarkeit, Hanglagen-Boni, Denkmalschutz-Ausnahmen.\n\n"
    "JEDE Zonenkennzahl ist ein eigenes Objekt mit wert/einheit/"
    "quelle_dokument/artikel_referenz/zitat/confidence/bedingungen/"
    "unklarheit -- NIEMALS nur eine blosse Zahl:\n"
    "- 'wert' ist AUSSCHLIESSLICH der Normalfall-Wert ohne Sonderbedingung. "
    "Findest du im selben Dokument einen ALTERNATIVEN Wert unter einer "
    "spezifischen Bedingung (z.B. 'Gesamthoehe 10.00 m, bei Schraegdach mit "
    "First mind. 2.50 m Rueckversatz 11.50 m'), waehle NICHT einfach den "
    "hoeheren oder tieferen Wert -- der Normalfall gehoert in 'wert', der "
    "bedingte Wert MIT der genauen Bedingung in 'bedingungen'.\n"
    "- 'confidence' ehrlich einschaetzen: 'hoch' nur bei einem expliziten "
    "Zahlenwert in einer eindeutig dieser Zone zugeordneten Tabelle/einem "
    "Artikel. 'mittel' wenn der Wert abgeleitet/berechnet werden musste oder "
    "aus einem nur indirekt zugeordneten Dokument stammt (z.B. kantonales "
    "Rahmenrecht statt kommunalem Reglement). 'niedrig' bei gefundenem, aber "
    "unsicherem/mehrdeutigem Wert. 'nicht_bestimmbar', wenn du den Wert "
    "NICHT findest -- dann MUSS 'wert' null sein und 'unklarheit' kurz "
    "erklaeren, warum (z.B. 'nur im grafischen Zonenplan enthalten, nicht "
    "im Text' oder 'diese Zone kennt keine Ausnuetzungsziffer'). Rate NIE "
    "einen Wert, nur um 'wert' zu befuellen, und erhoehe die Confidence NIE "
    "kuenstlich, um Vollstaendigkeit vorzutaeuschen.\n"
    "- 'quelle_dokument' nennt den Titel des Dokuments, aus dem der Wert "
    "stammt -- wichtig, da dir mehrere Dokumente gleichzeitig vorliegen "
    "koennen (kommunales Reglement plus evtl. kantonales Rahmenrecht).\n"
    "- Widersprechen sich mehrere beigefuegte Dokumente in einem Wert, nenne "
    "das explizit in 'unklarheit' UND unter 'unklarheiten_und_pruefhinweise'."
)


# ---------------------------------------------------------------------------
# Gemini-Aufruf (Standard-Backend, kostenlos)
# ---------------------------------------------------------------------------

def _analyze_bzo_documents_gemini(
    pdf_documents: list[bytes],
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
) -> dict[str, Any]:
    """Analysiert BZO-PDF(s) mit Gemini (kostenloses Tier) und liefert
    dasselbe JSON-Schema wie die Claude-Variante (siehe _BzoAnalyseGemini).
    """
    if _GeminiBaseModel is None:
        raise Modul2Error("pydantic ist nicht installiert -- fuer das Gemini-Backend erforderlich (`pip install pydantic`).")
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        raise Modul2Error(
            "GEMINI_API_KEY ist nicht gesetzt. Kostenlosen Key ohne Kreditkarte holen unter "
            "https://aistudio.google.com/apikey und als Umgebungsvariable GEMINI_API_KEY setzen."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise Modul2Error("google-genai ist nicht installiert (`pip install google-genai`).") from exc

    client = genai.Client()  # liest GEMINI_API_KEY/GOOGLE_API_KEY automatisch aus der Umgebung

    kontext = ""
    if gemeinde or kanton:
        kontext = f"\n\nKontext: Gemeinde={gemeinde or '?'}, Kanton={kanton or '?'}."

    document_parts = [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        for pdf_bytes in pdf_documents
    ]
    prompt_text = (
        f"Die {len(document_parts)} beigefuegten Dokumente bilden zusammen die "
        "rechtsverbindlichen Bau-/Zonenvorschriften fuer diesen Standort. "
        "Analysiere sie gemeinsam gemaess Systemanweisung -- widersprechen sich "
        "Dokumente, nenne das unter 'unklarheiten_und_pruefhinweise'." + kontext
    )

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_json_schema=_BzoAnalyseGemini.model_json_schema(),
    )

    last_exc: Optional[Exception] = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[*document_parts, prompt_text],
                config=config,
            )
            break
        except Exception as exc:  # noqa: BLE001 -- SDK-Exception-Taxonomie nicht zuverlaessig dokumentiert, siehe unten
            last_exc = exc
            msg = str(exc)
            is_transient = (
                "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate limit" in msg.lower()
                or "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()
                or "high demand" in msg.lower()
            )
            if is_transient and attempt < GEMINI_MAX_RETRIES:
                # Kostenloses Tier hat niedrige Requests/Minute (429) und der
                # Dienst meldet unter Last auch mal 503 UNAVAILABLE ("high
                # demand", live beobachtet 2026-08-26) -- beides erwartbares,
                # transientes Verhalten, kein Fehler. Exponentielles Backoff.
                time.sleep(GEMINI_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
                continue
            raise Modul2Error(f"Gemini-API-Fehler: {exc}") from exc
    else:
        raise Modul2Error(f"Gemini-API-Fehler nach {GEMINI_MAX_RETRIES} Versuchen: {last_exc}") from last_exc

    finish_reason = getattr(response.candidates[0], "finish_reason", None) if response.candidates else None
    if finish_reason and str(finish_reason).upper() not in ("STOP", "1", "FINISHREASON.STOP"):
        raise Modul2Error(f"Gemini hat die Antwort nicht regulaer abgeschlossen (finish_reason={finish_reason}).")

    try:
        result = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise Modul2Error(f"Gemini-Antwort war kein valides JSON: {exc}") from exc

    usage = getattr(response, "usage_metadata", None)
    result["_meta"] = {
        "modul": "Modul 2 - BZO-Parsing & Delta-Finder",
        "backend": "gemini",
        "model": GEMINI_MODEL,
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
    }
    return result


# ---------------------------------------------------------------------------
# Claude-Aufruf (optionales Backend, kostenpflichtig)
# ---------------------------------------------------------------------------

def _analyze_bzo_documents_claude(
    pdf_documents: list[bytes],
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """Analysiert eines oder mehrere BZO-/Reglement-PDFs gemeinsam mit Claude und
    liefert ein einziges schema-validiertes JSON.

    Mehrere Dokumente werden unterstuetzt, weil nicht jeder Kanton eine
    konsolidierte "Bauordnung" fuehrt: manche (z.B. BL, SZ via oereblex)
    verteilen die rechtsverbindlichen Kennzahlen auf ein Grundgesetz PLUS
    mehrere kleine zonenspezifische Beschluss-PDFs. Claude liest alle
    beigefuegten Dokumente im selben Kontext und fasst sie zu einem
    konsistenten Ergebnis zusammen.

    Erzwingt die Antwortstruktur ueber output_config.format (json_schema),
    sodass Modul 3 das Ergebnis ohne Freitext-Parsing direkt konsumieren kann.
    """
    import anthropic  # lazy import, analog zum bestehenden llm/claude_analysis.py Muster

    client = anthropic.Anthropic()

    kontext = ""
    if gemeinde or kanton:
        kontext = f"\n\nKontext: Gemeinde={gemeinde or '?'}, Kanton={kanton or '?'}."

    document_blocks = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
            },
        }
        for pdf_bytes in pdf_documents
    ]

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": BZO_ANALYSIS_SCHEMA},
            },
            messages=[{
                "role": "user",
                "content": [
                    *document_blocks,
                    {
                        "type": "text",
                        "text": (
                            f"Die {len(document_blocks)} beigefuegten Dokumente bilden "
                            "zusammen die rechtsverbindlichen Bau-/Zonenvorschriften fuer "
                            "diesen Standort. Analysiere sie gemeinsam gemaess "
                            "Systemanweisung -- widersprechen sich Dokumente, nenne das "
                            "unter 'unklarheiten_und_pruefhinweise'." + kontext
                        ),
                    },
                ],
            }],
        )
    except anthropic.APIStatusError as exc:
        raise Modul2Error(f"Claude-API-Fehler ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise Modul2Error(f"Verbindung zur Claude-API fehlgeschlagen: {exc}") from exc
    except TypeError as exc:
        # Die SDK wirft hier (nicht als anthropic.APIStatusError, sondern als
        # rohen TypeError) wenn keinerlei Credentials aufgeloest werden konnten
        # (weder ANTHROPIC_API_KEY noch ANTHROPIC_AUTH_TOKEN noch ein `ant
        # auth login`-Profil) -- klare Fehlermeldung statt rohem Traceback.
        if "authentication" in str(exc).lower() or "api_key" in str(exc).lower():
            raise Modul2Error(
                "Keine Claude-API-Credentials gefunden (ANTHROPIC_API_KEY nicht "
                f"gesetzt, kein `ant auth login`-Profil). Original: {exc}"
            ) from exc
        raise

    if response.stop_reason == "refusal":
        raise Modul2Error("Claude hat die Analyse aus Sicherheitsgruenden abgelehnt.")
    if response.stop_reason == "max_tokens":
        raise Modul2Error(
            f"Antwort wurde bei max_tokens={max_tokens} abgeschnitten -- "
            "max_tokens erhoehen (grosses/komplexes Reglement)."
        )

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise Modul2Error("Keine Textantwort von Claude erhalten.")

    result = json.loads(text_block.text)
    result["_meta"] = {
        "modul": "Modul 2 - BZO-Parsing & Delta-Finder",
        "backend": "claude",
        "model": CLAUDE_MODEL,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return result


# ---------------------------------------------------------------------------
# Dispatcher: waehlt zwischen Gemini (Standard) und Claude
# ---------------------------------------------------------------------------

def analyze_bzo_documents(
    pdf_documents: list[bytes],
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
    max_tokens: int = 8000,
    backend: Optional[str] = None,
) -> dict[str, Any]:
    """Analysiert eines oder mehrere BZO-/Reglement-PDFs und liefert ein
    einziges schema-validiertes JSON -- unabhaengig vom gewaehlten Backend.

    backend: "gemini" (Standard, kostenlos) oder "claude" (kostenpflichtig).
    Kein automatischer Fallback zwischen den Backends -- wuerde sonst
    ungewollt Kosten verursachen bzw. eine bewusste Wahl unterlaufen.
    """
    if not pdf_documents:
        raise Modul2Error("Keine PDF-Dokumente uebergeben.")

    chosen_backend = backend or DEFAULT_BACKEND
    if chosen_backend == "gemini":
        return _analyze_bzo_documents_gemini(pdf_documents, gemeinde=gemeinde, kanton=kanton)
    if chosen_backend == "claude":
        return _analyze_bzo_documents_claude(pdf_documents, gemeinde=gemeinde, kanton=kanton, max_tokens=max_tokens)
    raise Modul2Error(f"Unbekanntes backend {chosen_backend!r} -- erlaubt: 'gemini', 'claude'.")


def analyze_bzo_document(
    pdf_bytes: bytes,
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
    max_tokens: int = 8000,
    backend: Optional[str] = None,
) -> dict[str, Any]:
    """Bequemlichkeits-Wrapper fuer den Einzeldokument-Fall."""
    return analyze_bzo_documents([pdf_bytes], gemeinde=gemeinde, kanton=kanton, max_tokens=max_tokens, backend=backend)


def analyze_bzo_from_urls(
    urls: list[str],
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
    backend: Optional[str] = None,
) -> dict[str, Any]:
    """Laedt mehrere PDFs von URLs herunter und analysiert sie gemeinsam.

    Nicht jede Rechtsvorschrift-URL ist ein PDF -- kantonale Gesetze (z.B. das
    PBG) verweisen oft auf eine HTML-Seite der Gesetzessammlung statt auf ein
    Dokument. Ein einzelner nicht ladbarer Link darf die restliche Analyse
    nicht zum Absturz bringen: fehlschlagende URLs werden uebersprungen und
    unter '_meta.uebersprungene_dokumente' transparent ausgewiesen. Nur wenn
    KEINE der URLs ein PDF liefert, wird abgebrochen.
    """
    pdf_documents = []
    skipped = []
    for url in urls:
        try:
            pdf_documents.append(download_pdf(url))
        except Modul2Error as exc:
            skipped.append({"url": url, "grund": str(exc)})
        except requests.exceptions.RequestException as exc:
            # Netz-/HTTP-Fehler beim einzelnen Dokument -- z.B. eine
            # Gemeinde-Website, die den Abruf sperrt (live beobachtet:
            # Berlingen TG, HTTP 403 auch mit Browser-User-Agent). Frueher
            # riss das die gesamte Analyse mit, obwohl der Docstring oben
            # bereits das Ueberspringen vorsah: raise_for_status() wirft
            # HTTPError, nicht Modul2Error.
            skipped.append({"url": url, "grund": f"{type(exc).__name__}: {exc}"})

    if not pdf_documents:
        raise Modul2Error(
            f"Keine der {len(urls)} URLs lieferte ein ladbares PDF. "
            f"Details: {skipped}"
        )

    result = analyze_bzo_documents(pdf_documents, gemeinde=gemeinde, kanton=kanton, backend=backend)
    result["_meta"]["source_urls"] = urls
    result["_meta"]["uebersprungene_dokumente"] = skipped
    return result


def analyze_bzo_from_url(
    url: str, gemeinde: Optional[str] = None, kanton: Optional[str] = None, backend: Optional[str] = None
) -> dict[str, Any]:
    return analyze_bzo_from_urls([url], gemeinde=gemeinde, kanton=kanton, backend=backend)


def waehle_bzo_dokumente(
    oereb_result: dict[str, Any], max_documents: int = 5,
) -> list[dict[str, Any]]:
    """Welche Reglementsdokumente werden ausgewertet?

    Herausgeloest, damit derselbe Satz Dokumente auch OHNE Auswertung
    bestimmbar ist -- der Zwischenspeicher braucht ihn als Schluessel, und
    zwei Stellen, die verschieden auswaehlen, waeren ein stiller Fehler.
    """
    provisions = oereb_result.get("rechtsvorschriften", [])
    if not provisions:
        raise Modul2Error("Keine Rechtsvorschriften im OEREB-Ergebnis von Modul 1 vorhanden.")
    likely = [p for p in provisions if p.get("ist_wahrscheinlich_bzo_reglement")]
    return (likely or provisions)[:max_documents]


def analyze_from_oereb_result(
    oereb_result: dict[str, Any],
    gemeinde: Optional[str] = None,
    kanton: Optional[str] = None,
    max_documents: int = 5,
    backend: Optional[str] = None,
) -> dict[str, Any]:
    """Orchestrierungs-Helfer: nimmt direkt den 'oereb'-Teil aus Modul 1s
    run_modul1()-Ergebnis entgegen, waehlt die wahrscheinlichsten BZO-/
    Reglement-Dokumente aus und analysiert sie (Standard: Gemini, kostenlos).

    Nimmt zuerst alle Eintraege mit ist_wahrscheinlich_bzo_reglement=True --
    das Flag wird in Modul 1 (_extract_legal_provisions) STRUKTURELL bestimmt
    (Theme-Zugehoerigkeit + Hosting-Plattform der Dokument-URL), nicht ueber
    Titel-Stichworte. Dadurch koennen pro Adresse mehrere echte Kandidaten
    durchkommen (kommunales Reglement + evtl. kantonales Rahmenrecht) --
    max_documents auf 5 erhoeht (vorher 3), damit das nicht vorschnell
    abgeschnitten wird. Modul 2 analysiert alle uebergebenen Dokumente
    GEMEINSAM in einem Call und synthetisiert selbst, welches die tatsaechlich
    zonenrelevanten Zahlen enthaelt. Findet die Vorauswahl gar nichts (z.B.
    weil eine Gemeinde ihre Vorschriften ausschliesslich als kleine zonen-
    spezifische Einzelbeschluesse fuehrt), fallen wir auf die ersten
    max_documents Eintraege insgesamt zurueck, statt mit einem Fehler
    abzubrechen.
    """
    chosen = waehle_bzo_dokumente(oereb_result, max_documents=max_documents)
    urls = [p["url"] for p in chosen]

    result = analyze_bzo_from_urls(urls, gemeinde=gemeinde, kanton=kanton, backend=backend)
    result["_meta"]["source_dokumente"] = [{"titel": p["titel"], "url": p["url"]} for p in chosen]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Modul 2: BZO-PDF-Analyse via Gemini (Standard, kostenlos) oder Claude")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="URL zum BZO-/Reglement-PDF")
    source.add_argument("--file", help="Lokaler Pfad zu einem BZO-PDF")
    source.add_argument("--address", help="Schweizer Adresse -- ruft zuerst Modul 1 auf, um die BZO-Links zu ermitteln")
    parser.add_argument("--gemeinde", default=None)
    parser.add_argument("--kanton", default=None)
    parser.add_argument(
        "--backend", choices=["gemini", "claude"], default=None,
        help=f"Standard: {DEFAULT_BACKEND} (braucht GEMINI_API_KEY). 'claude' braucht ANTHROPIC_API_KEY.",
    )
    args = parser.parse_args()

    try:
        if args.url:
            result = analyze_bzo_from_url(args.url, gemeinde=args.gemeinde, kanton=args.kanton, backend=args.backend)
        elif args.file:
            with open(args.file, "rb") as f:
                pdf_bytes = f.read()
            result = analyze_bzo_document(pdf_bytes, gemeinde=args.gemeinde, kanton=args.kanton, backend=args.backend)
        else:
            from .modul1_geodata import run_modul1

            modul1_result = run_modul1(args.address)
            oereb = modul1_result.get("oereb", {})
            if not oereb.get("found"):
                raise Modul2Error(f"Modul 1 lieferte keine OEREB-Daten: {oereb.get('reason')}")
            gemeinde = args.gemeinde or modul1_result.get("gemeinde", {}).get("gemeinde")
            kanton = args.kanton or oereb.get("kanton")
            result = analyze_from_oereb_result(oereb, gemeinde=gemeinde, kanton=kanton, backend=args.backend)
    except Modul2Error as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

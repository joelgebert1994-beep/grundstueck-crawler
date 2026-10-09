"""
Plausibilitaetspruefung der Reglementwerte (A3).

Modul 2 liest die Zonenkennzahlen mit einem Sprachmodell aus den PDF. Jede
Kennzahl kommt mit Beleg: wert, einheit, zitat, artikel_referenz,
quelle_dokument, confidence. Bisher ging `wert` ungeprueft in die Rechnung
-- auch dann, wenn der eigene Beleg ihm widerspricht. Live beobachtet:
"AZ=20.0" in Russikon, wo das Reglement "20 %" meint.

Diese Pruefung vergleicht den Wert mit SEINEM EIGENEN Beleg. Sie kennt
bewusst keine Wertebereiche: eine ungewoehnlich hohe oder tiefe Ziffer ist
kein Fehler, wenn Originaltext und Einheit sie tragen. Auffaellig ist nur,
was sich widerspricht:

  * die Einheit passt nicht zur Kennzahl (ein Abstand in %, eine Ziffer in m)
  * der Originaltext nennt "30 %", der Wert ist 30 statt 0.30
  * der Originaltext nennt "0.3 m", der Wert ist 30 (Komma verrutscht)
  * die Einheit "Prozent" steht da, aber nichts belegt, ob der Wert schon
    umgerechnet ist (0.3 kann 0.3 % oder 30 % heissen)
  * der Originaltext nennt fuer diese Groesse ein anderes Mass
  * der Wert ist mathematisch unmoeglich (negativ, halbe Vollgeschosse,
    grosser Grenzabstand kleiner als der kleine)
  * Wert gesetzt, obwohl die Auswertung selbst "nicht bestimmbar" meldet

Was sie NICHT tut: sie korrigiert keine Zahl. Ein auffaelliger Wert wird
nicht durch 100 geteilt und nicht ersetzt, sondern zurueckgehalten: in der
Kopie der Zone, mit der gerechnet wird, steht `wert: None` -- derselbe Weg,
den jede fehlende Kennzahl schon heute nimmt (nicht bestimmbar, manuelle
Pruefung). Der ausgelesene Wert bleibt als `wert_extrahiert` daneben, Zitat,
Artikel, Quelle, Einheit und Confidence bleiben unveraendert, und die
Modul-2-Auswertung selbst wird nicht angefasst.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional

STATUS_PRUEFBEDUERFTIG = "pruefbeduerftig"

# Was eine Kennzahl ihrer Art nach ist.
_ZIFFER = "ziffer"          # Verhaeltniszahl Geschossflaeche/Landflaeche usw.
_VOLUMENZIFFER = "volumen"  # m3 je m2 Landflaeche
_LAENGE = "laenge"          # Meter
_ANZAHL = "anzahl"          # Geschosse

KENNZAHL_ART: dict[str, str] = {
    "ausnuetzungsziffer_az": _ZIFFER,
    "anrechenbare_geschossflaechenziffer_abgf": _ZIFFER,
    "ueberbauungsziffer_uz": _ZIFFER,
    "baumassenziffer_bmz": _VOLUMENZIFFER,
    "gesamthoehe_m": _LAENGE,
    "gebaeudehoehe_m": _LAENGE,
    "grenzabstand_klein_m": _LAENGE,
    "grenzabstand_gross_m": _LAENGE,
    "strassenabstand_m": _LAENGE,
    "vollgeschosse_max": _ANZAHL,
}

# Einheit, wie das Modell sie hinschreibt -> Dimension. Unbekanntes bleibt
# None und wird nicht beanstandet: was sich nicht lesen laesst, ist kein
# Widerspruch.
_E_PROZENT, _E_VERHAELTNIS, _E_METER, _E_ZENTIMETER = "prozent", "verhaeltnis", "meter", "zentimeter"
_E_FLAECHE, _E_VOLUMEN, _E_VOLUMEN_JE_FLAECHE, _E_ANZAHL = "flaeche", "volumen", "volumen_je_flaeche", "anzahl"

_ERLAUBT: dict[str, set[str]] = {
    _ZIFFER: {_E_VERHAELTNIS, _E_PROZENT},
    _VOLUMENZIFFER: {_E_VOLUMEN_JE_FLAECHE, _E_VERHAELTNIS},
    _LAENGE: {_E_METER},
    _ANZAHL: {_E_ANZAHL, _E_VERHAELTNIS},
}


def einheit_dimension(einheit: Any) -> Optional[str]:
    if einheit is None:
        return _E_VERHAELTNIS
    t = str(einheit).strip().lower()
    if t in ("", "-", "–", "keine", "ohne", "ohne einheit"):
        return _E_VERHAELTNIS
    if "%" in t or "prozent" in t or "percent" in t:
        return _E_PROZENT
    if re.search(r"m\s*(?:3|³)\s*/\s*m\s*(?:2|²)", t):
        return _E_VOLUMEN_JE_FLAECHE
    if re.search(r"m\s*(?:2|²)\s*/\s*m\s*(?:2|²)", t):
        return _E_VERHAELTNIS
    if re.search(r"\bcm\b|zentimeter", t):
        return _E_ZENTIMETER
    if re.search(r"m\s*(?:3|³)|kubik", t):
        return _E_VOLUMEN
    if re.search(r"m\s*(?:2|²)|quadratmeter", t):
        return _E_FLAECHE
    # Vor "geschoss": eine Geschossflaechenziffer ist eine Ziffer, keine Anzahl.
    if any(w in t for w in ("verhält", "verhaelt", "ziffer", "faktor", "dimensionslos", "anteil")):
        return _E_VERHAELTNIS
    if "geschoss" in t or "anzahl" in t or "stück" in t or "stueck" in t:
        return _E_ANZAHL
    if re.fullmatch(r"m\.?|meter", t) or t.startswith("m ") or "meter" in t:
        return _E_METER
    return None


# Zahlen im Originaltext. Artikel-, Absatz- und Ziffernverweise sind keine
# Masse ("Art. 22", "Abs. 2", "§ 16"), Zonenkuerzel auch nicht ("W2", "K3").
_VERWEIS = re.compile(
    r"(?:\bArt(?:ikel)?\.?|\bAbs(?:atz)?\.?|§+|\bZiff(?:er)?\.?|\blit\.?|\bAnhang|\bAnh\.?|\bTab(?:elle)?\.?|\bNr\.?)"
    r"\s*\d+(?:\s*[a-z]\b)?(?:\s*(?:Abs\.?|lit\.?|Ziff\.?)\s*\d+)*",
    re.IGNORECASE)
_ZAHL = re.compile(
    r"(?<![\w.,'’])(\d{1,3}(?:['’]\d{3})+|\d+)(?:[.,](\d+))?(?![\w'’])"
    # "m2" nur ohne Leerschlag: in "5.0 m 2)" ist die 2 eine Fussnote.
    r"\s*(%|prozent|cm|m(?:2|²|3|³)(?!\d)|m(?![a-zäöü\d]))?",
    re.IGNORECASE)


def zahlen_im_text(text: Any) -> list[tuple[float, Optional[str]]]:
    """Alle Masse im Text als (Zahl, Einheit) -- Einheit wie im Text."""
    if not text:
        return []
    t = _VERWEIS.sub(" ", str(text))
    gefunden = []
    for m in _ZAHL.finditer(t):
        ganz = re.sub(r"['’]", "", m.group(1))
        zahl = float(ganz + ("." + m.group(2) if m.group(2) else ""))
        einheit = m.group(3)
        if einheit:
            e = re.sub(r"\s+", "", einheit.lower())
            einheit = ({"prozent": "%", "m²": "m2", "m³": "m3"}).get(e, e)
        gefunden.append((zahl, einheit))
    return gefunden


def _gleich(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def _verschoben(wert: float, zahl: float) -> Optional[str]:
    for faktor, wort in ((100.0, "100-fach"), (10.0, "10-fach"), (1000.0, "1000-fach")):
        if _gleich(wert, zahl * faktor):
            return f"{wort} zu gross"
        if _gleich(wert, zahl / faktor):
            return f"{wort} zu klein"
    return None


def _befund(art: str, hinweis: str) -> dict[str, str]:
    return {"art": art, "hinweis": hinweis}


def _pruefe_beleg(art: str, wert: float, kz: dict[str, Any]) -> list[dict[str, str]]:
    """Wert gegen den Originaltext. Ohne Zahl im Text: nichts zu pruefen."""
    zahlen = zahlen_im_text(kz.get("zitat"))
    if not zahlen:
        return []

    if art == _ZIFFER:
        # Belegt sind: eine nackte Zahl gleich dem Wert, oder "N %" mit Wert N/100.
        belegt = any((e is None and _gleich(wert, z)) or (e == "%" and _gleich(wert, z / 100.0))
                     for z, e in zahlen)
        if belegt:
            return []
        for z, e in zahlen:
            if e == "%" and _gleich(wert, z):
                return [_befund("prozent_nicht_umgerechnet",
                                f"Der Originaltext nennt {z:g} %, der Wert ist {wert:g} statt "
                                f"{z / 100.0:g}. Als Verhaeltniszahl waere das das {z:g}-fache "
                                "der Landflaeche.")]
        for z, e in zahlen:
            if e is None and (v := _verschoben(wert, z)):
                return [_befund("dezimalfehler",
                                f"Der Originaltext nennt {z:g}, der Wert ist {wert:g} ({v}).")]
        massgebend = [(z, e) for z, e in zahlen if e in (None, "%")]
        if massgebend:
            nennt = ", ".join(f"{z:g}{' %' if e == '%' else ''}" for z, e in massgebend[:4])
            return [_befund("originaltext_widerspricht",
                            f"Der Originaltext nennt {nennt} -- der Wert {wert:g} kommt darin nicht vor.")]
        return []

    if art == _LAENGE:
        meter = [z for z, e in zahlen if e == "m"]
        nackt = [z for z, e in zahlen if e is None]
        if any(_gleich(wert, z) for z in meter + nackt):
            return []
        for z, e in zahlen:
            if e == "cm" and _gleich(wert, z):
                return [_befund("zentimeter_nicht_umgerechnet",
                                f"Der Originaltext nennt {z:g} cm, der Wert ist {wert:g} statt {z / 100.0:g} m.")]
            if e == "cm" and _gleich(wert, z / 100.0):
                return []
        for z in meter:
            if v := _verschoben(wert, z):
                return [_befund("dezimalfehler",
                                f"Der Originaltext nennt {z:g} m, der Wert ist {wert:g} m ({v}).")]
        for z, e in zahlen:
            if e in ("%", "m2", "m3") and _gleich(wert, z):
                return [_befund("einheit_widerspricht",
                                f"Der Originaltext nennt {z:g} {e} -- das ist kein Laengenmass.")]
        if meter:
            nennt = ", ".join(f"{z:g} m" for z in meter[:4])
            return [_befund("originaltext_widerspricht",
                            f"Der Originaltext nennt {nennt} -- der Wert {wert:g} m kommt darin nicht vor.")]
        return []

    if art == _VOLUMENZIFFER:
        if any(_gleich(wert, z) for z, e in zahlen if e in (None, "m3")):
            return []
        for z, e in zahlen:
            if e == "%" and _gleich(wert, z):
                return [_befund("einheit_widerspricht",
                                f"Der Originaltext nennt {z:g} % -- eine Baumassenziffer ist kein Prozentwert.")]
        for z, e in zahlen:
            if e is None and (v := _verschoben(wert, z)):
                return [_befund("dezimalfehler",
                                f"Der Originaltext nennt {z:g}, der Wert ist {wert:g} ({v}).")]
        return []

    return []


def pruefe_kennzahl(feld: str, kz: Any) -> list[dict[str, str]]:
    """Befunde zu EINER Kennzahl. Leer heisst: nichts widerspricht sich."""
    art = KENNZAHL_ART.get(feld)
    if art is None or not isinstance(kz, dict) or kz.get("wert") is None:
        return []
    roh = kz.get("wert")
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return [_befund("kein_zahlenwert", f"Der Wert {roh!r} ist keine Zahl.")]

    befunde: list[dict[str, str]] = []
    if wert < 0:
        befunde.append(_befund("negativ", f"Ein negativer Wert ({wert:g}) ist fuer diese Groesse nicht moeglich."))
    if art == _ANZAHL and not float(wert).is_integer():
        befunde.append(_befund("keine_ganze_zahl",
                               f"{wert:g} Vollgeschosse -- Geschosse lassen sich nur ganz zaehlen."))
    if kz.get("confidence") == "nicht_bestimmbar":
        befunde.append(_befund("status_widerspricht",
                               "Die Auswertung meldet 'nicht bestimmbar' und setzt trotzdem einen Wert."))

    dimension = einheit_dimension(kz.get("einheit"))
    if dimension is not None and dimension not in _ERLAUBT[art]:
        befunde.append(_befund("einheit_unpassend",
                               f"Einheit '{kz.get('einheit')}' passt nicht zu dieser Kennzahl."))
        return befunde

    beleg = _pruefe_beleg(art, wert, kz)
    befunde += beleg
    # "Prozent" ohne Beleg: 0.3 kann 0.3 % oder schon umgerechnete 30 % sein.
    if art == _ZIFFER and dimension == _E_PROZENT and not beleg:
        zahlen = zahlen_im_text(kz.get("zitat"))
        if any(e is None and _gleich(wert, z) and wert > 1 for z, e in zahlen):
            # "Ausnuetzungsziffer % max. 20" mit Wert 20: die Prozentzahl
            # selbst, nicht umgerechnet.
            befunde.append(_befund("prozent_nicht_umgerechnet",
                                   f"Einheit 'Prozent' und Originaltext nennen {wert:g} -- als "
                                   f"Verhaeltniszahl waere das das {wert:g}-fache der Landflaeche "
                                   f"statt {wert / 100.0:g}."))
        elif not any(e == "%" and _gleich(wert, z / 100.0) for z, e in zahlen):
            befunde.append(_befund("einheit_mehrdeutig",
                                   f"Einheit 'Prozent', Wert {wert:g} -- ohne Originaltext ist offen, ob "
                                   f"{wert:g} % oder bereits umgerechnet gemeint ist."))
    return befunde


def _zahl(kz: Any) -> Optional[float]:
    try:
        return float(kz.get("wert")) if isinstance(kz, dict) and kz.get("wert") is not None else None
    except (TypeError, ValueError):
        return None


def _paarbefunde(zone: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Was sich nur im Paar widerspricht."""
    befunde: dict[str, list[dict[str, str]]] = {}
    klein, gross = _zahl(zone.get("grenzabstand_klein_m")), _zahl(zone.get("grenzabstand_gross_m"))
    if klein is not None and gross is not None and gross < klein:
        b = _befund("paar_widerspricht",
                    f"Grosser Grenzabstand {gross:g} m ist kleiner als der kleine {klein:g} m.")
        befunde.setdefault("grenzabstand_klein_m", []).append(b)
        befunde.setdefault("grenzabstand_gross_m", []).append(b)
    gebaeude, gesamt = _zahl(zone.get("gebaeudehoehe_m")), _zahl(zone.get("gesamthoehe_m"))
    if gebaeude is not None and gesamt is not None and gesamt < gebaeude:
        b = _befund("paar_widerspricht",
                    f"Gesamthoehe {gesamt:g} m ist kleiner als die Gebaeudehoehe {gebaeude:g} m.")
        befunde.setdefault("gebaeudehoehe_m", []).append(b)
        befunde.setdefault("gesamthoehe_m", []).append(b)
    return befunde


def pruefe_zone(zone: Any) -> Any:
    """Die Zone, mit der gerechnet werden darf.

    Ohne Befund: DIESELBE Zone, unveraendert. Mit Befund: eine Kopie, in der
    jede auffaellige Kennzahl `wert: None` traegt, daneben `wert_extrahiert`
    (der ausgelesene Wert) und `plausibilitaet` (Status und Befunde). Alles
    andere an der Kennzahl -- Zitat, Artikel, Quelle, Einheit, Confidence,
    Bedingungen, Unklarheit -- bleibt, wie Modul 2 es geliefert hat.
    """
    if not isinstance(zone, dict):
        return zone
    befunde = _paarbefunde(zone)
    for feld in KENNZAHL_ART:
        if b := pruefe_kennzahl(feld, zone.get(feld)):
            befunde.setdefault(feld, [])[:0] = b
    if not befunde:
        return zone
    geprueft = copy.copy(zone)
    for feld, liste in befunde.items():
        kz = dict(zone[feld])
        kz["wert_extrahiert"] = kz.get("wert")
        kz["wert"] = None
        kz["plausibilitaet"] = {
            "status": STATUS_PRUEFBEDUERFTIG,
            "in_rechnung": False,
            "befunde": liste,
            "hinweis": ("Ausgelesener Wert widerspricht seinem Beleg -- nicht korrigiert, "
                        "nicht in der Rechnung. Reglement pruefen."),
        }
        geprueft[feld] = kz
    return geprueft


def plausibilitaetsbefunde(zone: Any) -> list[dict[str, Any]]:
    """Alle Befunde einer bereits geprueften Zone, flach -- fuer Hinweise."""
    if not isinstance(zone, dict):
        return []
    aus = []
    for feld in KENNZAHL_ART:
        kz = zone.get(feld)
        p = kz.get("plausibilitaet") if isinstance(kz, dict) else None
        if p:
            aus.append({"feld": feld, "wert_extrahiert": kz.get("wert_extrahiert"),
                        "befunde": p.get("befunde") or []})
    return aus

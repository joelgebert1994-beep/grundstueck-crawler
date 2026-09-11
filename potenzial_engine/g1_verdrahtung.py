"""
G1-Verdrahtung: verbindet den reinen Geometrie-Kern (baubereich.py) mit den
echten Datenquellen (Modul 1 Parzellengeometrie + Restriktionsgeometrie,
Modul 2 Zonenkennzahlen). Enthaelt KEINE eigene Berechnungslogik -- reine
Datenaufbereitung/Uebergabe, damit baubereich.py netzwerkfrei bleiben kann
und modul3_financial.py (SIA-416/BKP/Residualwert) unveraendert bleibt.

Bewusst NICHT Teil dieses Schritts (siehe Vorgabe):
  - Automatische Erkennung, welche Parzellenkante Strasse/Nachbar/Rueckseite
    ist -- Modul 2 liefert nur EINEN Wert je "klein"/"gross", nicht pro
    einzelner Kante. Ohne echte Kantenklassifikation wird deshalb eine
    Bandbreite berechnet (alle Kanten klein vs. alle Kanten gross), siehe
    _grenzabstand_bandbreite_pro_kante(). Ein expliziter Kanten-Override ist
    moeglich (kanten_abstaende_override), fuer Faelle, in denen die
    Kantenzuordnung manuell bekannt ist.
  - Automatische Ableitung des Mehrlaengenzuschlags aus Modul 2s
    Sonderregelungen (Freitext, keine strukturierten Schwelle/Zuschlag-Werte)
    -- bleibt bewusst deaktiviert (None), bis eine strukturierte Quelle
    existiert. Siehe baubereich.py fuer die synthetisch getestete Stufe-1-
    Naeherung.
"""

from __future__ import annotations

from typing import Any, Optional

from .baubereich import berechne_potenzial


class G1VerdrahtungError(Exception):
    """Fehler bei der Datenaufbereitung fuer G1 (fehlende Pflichtdaten)."""


def _kennzahl_wert(v: Any) -> Any:
    """Liest 'wert' aus einer Modul-2-Kennzahl (Schema mit wert/einheit/
    confidence/bedingungen/unklarheit) ODER akzeptiert weiterhin eine blosse
    Zahl (altes flaches Schema, z.B. synthetische Testdaten) -- reine
    Abwaertskompatibilitaet, keine neue Rechenlogik."""
    return v.get("wert") if isinstance(v, dict) else v


def _kennzahl_hinweis(feldname: str, v: Any) -> Optional[str]:
    """Verdichtet Confidence/Unklarheit/Bedingungen einer Modul-2-Kennzahl zu
    einem menschenlesbaren Hinweis, damit diese Information beim Einlesen
    NICHT verloren geht -- insbesondere Bedingungen (alternative Werte unter
    einer Sonderbedingung) bleiben so sichtbar/nachvollziehbar, auch wenn G1
    sie (bewusst, um nichts zu erraten) nicht automatisch anwendet. None bei
    einer blossen Zahl (altes Schema) oder wenn nichts Bemerkenswertes vorliegt.
    """
    if not isinstance(v, dict):
        return None
    teile = []
    confidence = v.get("confidence")
    if confidence and confidence != "hoch":
        teile.append(f"Confidence={confidence}")
    if v.get("unklarheit"):
        teile.append(f"Unklarheit: {v['unklarheit']}")
    for b in v.get("bedingungen") or []:
        teile.append(
            f"Alternativwert {b.get('wert_unter_bedingung')} falls Bedingung zutrifft "
            f"('{b.get('bedingung_text')}', {b.get('artikel_referenz') or 'keine Artikel-Referenz'}) "
            "-- NICHT automatisch angewendet, siehe Modul 2s Kennzahl-Schema"
        )
    if not teile:
        return None
    return f"{feldname}: " + " | ".join(teile)


def _anzahl_kanten(parzelle_ring: list[tuple[float, float]]) -> int:
    ring = list(parzelle_ring)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    return len(ring)


def laengste_kante_index(parzelle_ring: list[tuple[float, float]]) -> int:
    """Hilfsfunktion fuer den Grenzabstand-Override-Demofall: liefert den
    Index der laengsten Parzellenkante. Reine Illustrations-Heuristik ("die
    laengste Kante ist oft die Strassenseite bei einfachen Rechtecklots") --
    KEINE belastbare rechtliche Regel, da niemand automatisch weiss, welche
    Kante tatsaechlich zur Strasse zeigt, ohne die Strassenparzelle separat
    zu identifizieren (bewusst nicht Teil dieses Schritts)."""
    ring = list(parzelle_ring)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    n = len(ring)
    laengen = [
        ((ring[(i + 1) % n][0] - ring[i][0]) ** 2 + (ring[(i + 1) % n][1] - ring[i][1]) ** 2) ** 0.5
        for i in range(n)
    ]
    return max(range(n), key=lambda i: laengen[i])


def _grenzabstand_bandbreite_pro_kante(zone: dict[str, Any], anzahl_kanten: int) -> dict[str, list[float]]:
    klein = _kennzahl_wert(zone.get("grenzabstand_klein_m"))
    gross = _kennzahl_wert(zone.get("grenzabstand_gross_m"))
    szenarien: dict[str, list[float]] = {}
    if klein is not None:
        szenarien["alle_kanten_klein"] = [klein] * anzahl_kanten
    if gross is not None and gross != klein:
        szenarien["alle_kanten_gross"] = [gross] * anzahl_kanten
    return szenarien


def berechne_g1_fuer_fall(
    modul1_result: dict[str, Any],
    zone: dict[str, Any],
    *,
    kanten_abstaende_override: Optional[list[float]] = None,
) -> dict[str, Any]:
    """Fuehrt die G1-Kaskade mit REALER Parzellengeometrie/Restriktionen aus
    Modul 1 und den Zonenkennzahlen aus Modul 2 (`zone`, ein Eintrag aus
    `erkannte_zonen`) aus.

    Ohne `kanten_abstaende_override` wird -- mangels Kantenklassifikation --
    eine Bandbreite ueber "alle Kanten = Grenzabstand klein" (optimistisch)
    und "alle Kanten = Grenzabstand gross" (konservativ) berechnet, sofern
    beide Werte vorhanden und unterschiedlich sind.
    """
    kataster = modul1_result.get("kataster", {})
    parzelle_ring = kataster.get("parzellengeometrie")
    if not parzelle_ring:
        raise G1VerdrahtungError("Keine Parzellengeometrie in modul1_result['kataster'] vorhanden -- G1 kann nicht rechnen.")

    parzellenflaeche_amtlich_m2 = kataster.get("flaeche_m2")

    restriktionen = modul1_result.get("restriktionsgeometrie", {})
    restriktionsflaechen = restriktionen.get("restriktionsflaechen_fuer_g1") or None

    anzahl_kanten = _anzahl_kanten(parzelle_ring)

    vollgeschosse_wert = _kennzahl_wert(zone.get("vollgeschosse_max"))

    gemeinsame_kwargs = dict(
        restriktionsflaechen=restriktionsflaechen,
        ausnuetzungsziffer_az=_kennzahl_wert(zone.get("ausnuetzungsziffer_az")),
        anrechenbare_geschossflaechenziffer_abgf=_kennzahl_wert(zone.get("anrechenbare_geschossflaechenziffer_abgf")),
        baumassenziffer_bmz=_kennzahl_wert(zone.get("baumassenziffer_bmz")),
        ueberbauungsziffer_uz=_kennzahl_wert(zone.get("ueberbauungsziffer_uz")),
        vollgeschosse_max=int(vollgeschosse_wert) if vollgeschosse_wert is not None else None,
        gebaeudehoehe_m=_kennzahl_wert(zone.get("gebaeudehoehe_m")) or _kennzahl_wert(zone.get("gesamthoehe_m")),
    )

    # Confidence/Unklarheit/Bedingungen aller 9 Kennzahlenfelder einsammeln,
    # damit sie beim Einlesen sichtbar bleiben (siehe _kennzahl_hinweis()) --
    # unabhaengig davon, ob das Feld hier tatsaechlich verwendet wird, denn
    # z.B. eine "nicht_bestimmbar"-Ausnuetzungsziffer ist auch dann relevant,
    # wenn am Ende die Baumassenziffer bindet.
    kennzahl_felder = (
        "ausnuetzungsziffer_az", "anrechenbare_geschossflaechenziffer_abgf", "baumassenziffer_bmz",
        "ueberbauungsziffer_uz", "gesamthoehe_m", "gebaeudehoehe_m", "grenzabstand_klein_m",
        "grenzabstand_gross_m", "vollgeschosse_max",
    )
    kennzahl_hinweise = [
        h for feld in kennzahl_felder if (h := _kennzahl_hinweis(feld, zone.get(feld))) is not None
    ]

    basis_info = {
        "parzellenflaeche_amtlich_m2": parzellenflaeche_amtlich_m2,
        "restriktionsquellen": {
            "gewaesserraum_flaechen": len(restriktionen.get("gewaesserraum_flaechen", [])),
            "waldgrenze_min_abstand_m": restriktionen.get("waldgrenze_min_abstand_m"),
            "waldabstand_m_verwendet": restriktionen.get("waldabstand_m_verwendet"),
            "baulinien_gefunden": len(restriktionen.get("baulinien_gefunden", [])),
            "hinweise": restriktionen.get("hinweise", []),
        },
        "kennzahl_hinweise": kennzahl_hinweise,
    }

    if kanten_abstaende_override is not None:
        if len(kanten_abstaende_override) != anzahl_kanten:
            raise G1VerdrahtungError(
                f"kanten_abstaende_override braucht {anzahl_kanten} Werte (eine je Kante), "
                f"erhalten: {len(kanten_abstaende_override)}."
            )
        ergebnis = berechne_potenzial(parzelle_ring, kanten_abstaende_override, **gemeinsame_kwargs)
        return {"modus": "manueller_kanten_override", **basis_info, "ergebnis": ergebnis.to_dict()}

    bandbreite_szenarien = _grenzabstand_bandbreite_pro_kante(zone, anzahl_kanten)
    if not bandbreite_szenarien:
        raise G1VerdrahtungError(
            f"Zone {zone.get('zonenbezeichnung')!r} hat weder grenzabstand_klein_m noch "
            "grenzabstand_gross_m -- G1 kann ohne Grenzabstand nicht rechnen."
        )

    ergebnisse = {name: berechne_potenzial(parzelle_ring, kanten, **gemeinsame_kwargs).to_dict()
                  for name, kanten in bandbreite_szenarien.items()}

    if len(ergebnisse) == 1:
        return {"modus": "einheitlicher_grenzabstand", **basis_info, "ergebnis": next(iter(ergebnisse.values()))}

    return {
        "modus": "bandbreite_grenzabstand_kante_nicht_differenziert",
        **basis_info,
        "hinweis": (
            "Modul 2 liefert nur EINEN Wert je 'klein'/'gross', nicht pro einzelner "
            "Parzellenkante -- welche Kante Strassenseite/Nachbarseite ist, ist noch keine "
            "automatisierte Information (bewusst nicht Teil dieses Verdrahtungsschritts). "
            "Bandbreite: 'alle_kanten_klein' (optimistisch, groesster Baubereich) vs. "
            "'alle_kanten_gross' (konservativ, kleinster Baubereich). Das reale Ergebnis "
            "liegt dazwischen, abhaengig von der tatsaechlichen Kantenzuordnung."
        ),
        "szenarien": ergebnisse,
    }

"""
G1-Verdrahtung: verbindet den reinen Geometrie-Kern (baubereich.py) mit den
echten Datenquellen (Modul 1 Parzellengeometrie + Restriktionsgeometrie,
Modul 2 Zonenkennzahlen). Enthaelt KEINE eigene Berechnungslogik -- reine
Datenaufbereitung/Uebergabe, damit baubereich.py netzwerkfrei bleiben kann
und modul3_financial.py (SIA-416/BKP/Residualwert) unveraendert bleibt.

Kantenzuordnung (Stufe 2, kantenklassifikation.py):
  - `kantenklassifikation` liefert je Kante "strasse"/"nachbarparzelle"/
    "unbestimmt" mit geometrischem Nachweis. Daraus wird pro Kante der
    passende Abstand gesetzt: Strassenkante -> strassenabstand_m,
    Nachbarkante -> grenzabstand_gross_m (der striktere der beiden Werte,
    weil ohne Fassadenorientierung nicht entscheidbar ist, welche Seite
    "klein" sein darf -- die Bandbreite bleibt als Kontrolle daneben stehen).
  - Fehlt der Strassenabstand oder ist eine Kante "unbestimmt", wird KEIN
    Ersatzwert eingesetzt. Dann bleibt es bei der Bandbreite, und die
    betroffenen Kanten werden einzeln als nicht bestimmbar ausgewiesen.
    Der Strassenabstand wird NIE aus grenzabstand_klein_m/gross_m abgeleitet
    -- klein/gross unterscheidet schmale und breite Gebaeudeseite gegenueber
    NACHBARN, nicht Strasse gegen Nachbar.
  - Ein expliziter Kanten-Override bleibt moeglich
    (kanten_abstaende_override), fuer manuell bekannte Zuordnungen.

Bewusst NICHT Teil dieses Schritts (siehe Vorgabe):
  - Automatische Ableitung des Mehrlaengenzuschlags aus Modul 2s
    Sonderregelungen (Freitext, keine strukturierten Schwelle/Zuschlag-Werte)
    -- bleibt bewusst deaktiviert (None), bis eine strukturierte Quelle
    existiert. Siehe baubereich.py fuer die synthetisch getestete Stufe-1-
    Naeherung.
"""

from __future__ import annotations

from typing import Any, Optional

from .baubereich import berechne_potenzial
from .kantenklassifikation import ART_NACHBARPARZELLE, ART_STRASSE


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


# Ab welchem Verhaeltnis die Untergrenze als zusammengefallen GILT. Beide
# Werte steuern ausschliesslich den ERKLAERTEXT -- gerechnet wird damit
# nichts, und die Entscheidung, keinen Einzelwert auszugeben, haengt nicht
# daran, sondern allein an der Unentscheidbarkeit der Zuordnung.
ENTARTET_ANTEIL = 0.02
ENTARTET_M2 = 15.0


def _nachbarkanten(kantenklassifikation: dict[str, Any]) -> list[int]:
    return [i for i, k in enumerate(kantenklassifikation.get("kanten") or [])
            if k.get("art") == ART_NACHBARPARZELLE and k.get("relevant", True)]


def nachbarabstand_unentscheidbar(
    zone: dict[str, Any], kantenklassifikation: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Laesst sich bestimmen, welche Nachbarseite den grossen Abstand traegt?

    Nein -- und das ist keine Luecke in den Daten, sondern eine Eigenschaft
    der Sache: der grosse Grenzabstand gilt in aller Regel fuer EINE Seite
    (die Hauptwohnseite), die uebrigen tragen den kleinen. Welche das ist,
    entscheidet die Fassadenorientierung des Gebaeudes -- und das Gebaeude
    ist noch nicht entworfen.

    Bisher hat die Verdrahtung deshalb auf ALLEN Nachbarkanten den grossen
    Abstand angesetzt. Das ist nicht der wahrscheinliche Fall, sondern die
    strengste denkbare Anordnung: eine UNTERGRENZE, die als Einzelwert
    ausgegeben wurde.

    Live sichtbar geworden an Buhofstrasse 55, Rheineck (Parzelle 160,
    289 m2): die beiden Nachbarkanten liegen sich ueber die 16 m schmale
    Seite gegenueber. 16 - 8 - 8 = 0 -- die Huelle fiel auf 0.69 m2
    zusammen, und daraus wurde "Geschossflaeche 1.38 m2". Rechnerisch
    richtig, als Potenzialaussage unbrauchbar.

    Gibt None zurueck, wenn die Zuordnung eindeutig ist (beide Abstaende
    gleich, oder gar keine Nachbarkante), sonst die Angaben fuer die
    Bandbreite.
    """
    if kantenklassifikation is None:
        return None
    klein = _kennzahl_wert(zone.get("grenzabstand_klein_m"))
    gross = _kennzahl_wert(zone.get("grenzabstand_gross_m"))
    if klein is None or gross is None or klein == gross:
        return None
    indizes = _nachbarkanten(kantenklassifikation)
    if not indizes:
        return None
    return {"klein": float(klein), "gross": float(gross), "kanten": indizes}


def _mit_nachbarabstand(
    basis: list[float], indizes: list[int], wert: float,
) -> list[float]:
    """Dieselben Abstaende, nur an den Nachbarkanten ausgetauscht.

    Die Strassenkanten behalten ihren klassifizierten Strassenabstand -- DIE
    Zuordnung ist eindeutig (eine Strassenachse fuehrt durch das Polygon
    hinter der Kante) und darf nicht mit variiert werden.
    """
    abstaende = list(basis)
    for i in indizes:
        abstaende[i] = wert
    return abstaende

def _kantenabstaende_aus_klassifikation(
    zone: dict[str, Any],
    klassifikation: dict[str, Any],
    anzahl_kanten: int,
    baulinien_gefunden: int = 0,
) -> tuple[Optional[list[float]], list[dict[str, Any]], list[str]]:
    """Ordnet jeder Kante den Abstand zu, der fuer ihre Art tatsaechlich gilt.

    Liefert (abstaende, kantenprotokoll, offene_punkte). `abstaende` ist None,
    sobald auch nur eine massgebende Kante keinen belastbaren Wert bekommt --
    dann wird NICHT gerechnet, statt eine Zahl zu erzeugen, die es nicht gibt.
    Das Kantenprotokoll entsteht in jedem Fall und weist jede Kante einzeln
    aus, auch die offenen.

    Zuordnung:
      strasse         -> strassenabstand_m (eigenstaendiger Wert aus Modul 2;
                         NIE aus grenzabstand_klein/gross abgeleitet)
      nachbarparzelle -> grenzabstand_gross_m, ersatzweise klein, falls gross
                         fehlt. Gross ist der striktere der beiden: welche
                         Seite als "klein" gelten darf, haengt an der
                         Fassadenorientierung des noch nicht entworfenen
                         Gebaeudes und ist hier nicht entscheidbar.
      unbestimmt      -> kein Wert
    """
    strassenabstand_kz = zone.get("strassenabstand_m")
    strassenabstand = _kennzahl_wert(strassenabstand_kz)
    # Vorbehalte am Strassenabstand betreffen JEDE Strassenkante -- z.B. staffelt
    # der Kanton Aargau nach Strassenklasse (§ 111 BauG: Kantonsstrasse 6 m,
    # Gemeindestrasse 4 m). Welche Klasse die konkrete Strasse hat, wird noch
    # nicht ausgewertet (die Objektart der Achse liegt in der Klassifikation
    # bereit). Der Wert bleibt stehen, der Vorbehalt wird sichtbar.
    strassen_vorbehalte: list[str] = []
    if isinstance(strassenabstand_kz, dict) and strassenabstand is not None:
        confidence = strassenabstand_kz.get("confidence")
        if confidence and confidence != "hoch":
            strassen_vorbehalte.append(f"Strassenabstand mit Confidence '{confidence}' extrahiert")
        if strassenabstand_kz.get("unklarheit"):
            strassen_vorbehalte.append(str(strassenabstand_kz["unklarheit"]))
        for b in strassenabstand_kz.get("bedingungen") or []:
            strassen_vorbehalte.append(
                f"Alternativwert {b.get('wert_unter_bedingung')} unter Bedingung "
                f"'{b.get('bedingung_text')}' -- nicht automatisch angewendet"
            )
    grenz_gross = _kennzahl_wert(zone.get("grenzabstand_gross_m"))
    grenz_klein = _kennzahl_wert(zone.get("grenzabstand_klein_m"))
    nachbarabstand = grenz_gross if grenz_gross is not None else grenz_klein
    nachbar_feld = "grenzabstand_gross_m" if grenz_gross is not None else "grenzabstand_klein_m"

    kanten = klassifikation.get("kanten") or []
    if len(kanten) != anzahl_kanten:
        raise G1VerdrahtungError(
            f"Kantenklassifikation beschreibt {len(kanten)} Kanten, die Parzellengeometrie "
            f"hat {anzahl_kanten} -- Zuordnung nicht moeglich."
        )

    abstaende: list[float] = []
    protokoll: list[dict[str, Any]] = []
    offene: list[str] = []
    vollstaendig = True

    for kante in kanten:
        eintrag = {
            "nr": kante.get("nr"),
            "laenge_m": kante.get("laenge_m"),
            "art": kante.get("art"),
            "begruendung": kante.get("begruendung"),
            "nachbar_egrid": kante.get("nachbar_egrid"),
            "nachbar_nummer": kante.get("nachbar_nummer"),
            "strassenname": kante.get("strassenname"),
            "strassen_objektart": kante.get("strassen_objektart"),
            "abstand_m": None,
            "abstand_feld": None,
            "unsicherheit": None,
        }

        if not kante.get("relevant"):
            # Kurze Kante: praegt den Baubereich nicht. Sie braucht trotzdem
            # einen Wert fuer die Mitre-Konstruktion -- der Nachbarabstand ist
            # dort die zurueckhaltende Wahl.
            eintrag["abstand_m"] = nachbarabstand
            eintrag["abstand_feld"] = nachbar_feld if nachbarabstand is not None else None
            eintrag["unsicherheit"] = (
                "Kante unter der Relevanzschwelle -- nicht klassifiziert, "
                "rechnerisch mit dem Nachbarabstand belegt."
            )
            if nachbarabstand is None:
                vollstaendig = False
            else:
                abstaende.append(float(nachbarabstand))
            protokoll.append(eintrag)
            continue

        if kante.get("art") == ART_STRASSE:
            if strassenabstand is None:
                eintrag["unsicherheit"] = (
                    "Strassenkante, aber Modul 2 hat keinen eigenstaendigen Strassenabstand "
                    "gefunden. Kein Ersatzwert eingesetzt -- der Grenzabstand gegenueber "
                    "Nachbarn gilt hier rechtlich nicht."
                )
                offene.append(f"Kante {kante.get('nr')}: Strassenabstand nicht bestimmbar")
                vollstaendig = False
            else:
                eintrag["abstand_m"] = float(strassenabstand)
                eintrag["abstand_feld"] = "strassenabstand_m"
                vorbehalte = list(strassen_vorbehalte)
                if baulinien_gefunden:
                    # Eine Baulinie tritt an die Stelle des Abstandsmasses und
                    # kann strenger sein. Welche Baulinie welcher Kante
                    # zugeordnet ist, wird hier noch nicht bestimmt -- der
                    # Wert bleibt stehen, der Vorbehalt wird sichtbar gemacht,
                    # statt ein zu grosses Ergebnis unkommentiert auszugeben.
                    vorbehalte.append(
                        f"{baulinien_gefunden} Baulinie(n) auf der Parzelle gefunden. Eine Baulinie "
                        "tritt an die Stelle des Strassenabstands und kann strenger sein -- die "
                        "Zuordnung Baulinie/Kante ist noch nicht automatisiert."
                    )
                if vorbehalte:
                    eintrag["unsicherheit"] = " | ".join(vorbehalte)
                if kante.get("strassen_objektart") is not None:
                    eintrag["strassen_objektart"] = kante.get("strassen_objektart")
                abstaende.append(float(strassenabstand))
        elif kante.get("art") == ART_NACHBARPARZELLE:
            if nachbarabstand is None:
                eintrag["unsicherheit"] = "Nachbarkante, aber kein Grenzabstand in den Zonendaten."
                offene.append(f"Kante {kante.get('nr')}: Grenzabstand nicht bestimmbar")
                vollstaendig = False
            else:
                eintrag["abstand_m"] = float(nachbarabstand)
                eintrag["abstand_feld"] = nachbar_feld
                if nachbar_feld == "grenzabstand_klein_m":
                    eintrag["unsicherheit"] = (
                        "grenzabstand_gross_m fehlt -- ersatzweise der kleine Grenzabstand, "
                        "damit das Ergebnis eher zu gross als zu klein ausfaellt."
                    )
                abstaende.append(float(nachbarabstand))
        else:
            eintrag["unsicherheit"] = (
                "Kantenart nicht belastbar bestimmbar -- manuelle Pruefung erforderlich."
            )
            offene.append(f"Kante {kante.get('nr')}: Art unbestimmt")
            vollstaendig = False

        protokoll.append(eintrag)

    return (abstaende if vollstaendig else None), protokoll, offene


def berechne_g1_fuer_fall(
    modul1_result: dict[str, Any],
    zone: dict[str, Any],
    *,
    kanten_abstaende_override: Optional[list[float]] = None,
    kantenklassifikation: Optional[dict[str, Any]] = None,
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
        "grenzabstand_gross_m", "strassenabstand_m", "vollgeschosse_max",
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

    # Stufe 2: echte Kantenzuordnung, sofern vorhanden. Die Bandbreite wird
    # trotzdem immer mitberechnet und bleibt als Kontrollergebnis daneben
    # stehen -- ein klassifiziertes Ergebnis, das ausserhalb der Bandbreite
    # laege, waere ein Hinweis auf einen Fehler, kein Fortschritt.
    kanten_protokoll: Optional[list[dict[str, Any]]] = None
    kanten_abstaende: Optional[list[float]] = None
    kanten_offene: list[str] = []
    if kantenklassifikation is not None:
        kanten_abstaende, kanten_protokoll, kanten_offene = _kantenabstaende_aus_klassifikation(
            zone,
            kantenklassifikation,
            anzahl_kanten,
            baulinien_gefunden=len(restriktionen.get("baulinien_gefunden") or []),
        )
        basis_info["kantenprotokoll"] = kanten_protokoll
        basis_info["kantenklassifikation_statistik"] = kantenklassifikation.get("statistik")
        basis_info["kantenklassifikation_hinweise"] = kantenklassifikation.get("hinweise", [])

    bandbreite_szenarien = _grenzabstand_bandbreite_pro_kante(zone, anzahl_kanten)

    if kanten_abstaende is not None:
        # Welche Nachbarseite den grossen Grenzabstand traegt, entscheidet die
        # Fassadenorientierung des noch nicht entworfenen Gebaeudes. Bisher
        # wurde dann stillschweigend auf ALLEN Nachbarkanten der grosse
        # Abstand angesetzt -- das ist die strengste denkbare Anordnung, also
        # eine Untergrenze, die als Einzelwert ausgegeben wurde. Jetzt wird
        # sie als das ausgewiesen, was sie ist: der eine Rand einer Bandbreite.
        offen = nachbarabstand_unentscheidbar(zone, kantenklassifikation)
        if offen is not None:
            unten = berechne_potenzial(
                parzelle_ring, _mit_nachbarabstand(kanten_abstaende, offen["kanten"], offen["gross"]),
                **gemeinsame_kwargs).to_dict()
            oben = berechne_potenzial(
                parzelle_ring, _mit_nachbarabstand(kanten_abstaende, offen["kanten"], offen["klein"]),
                **gemeinsame_kwargs).to_dict()

            parzflaeche = unten.get("parzellenflaeche_m2") or 0.0
            entartet = bool(parzflaeche) and (
                unten.get("baubereich_m2", 0.0) <= ENTARTET_M2
                and unten.get("baubereich_m2", 0.0) <= ENTARTET_ANTEIL * parzflaeche)

            az = _kennzahl_wert(zone.get("ausnuetzungsziffer_az"))
            landflaeche = unten.get("anrechenbare_landflaeche_m2")

            antwort = {
                "modus": "bandbreite_nachbarabstand_nicht_zuordenbar",
                **basis_info,
                # KEIN "ergebnis": die nachgelagerte Flaechenkaskade liest
                # genau dieses Feld und meldet ohne es "nicht bestimmbar" --
                # statt sich einen der beiden Raender auszusuchen.
                "baubereich_belastbar": False,
                "grund_nicht_belastbar": (
                    "Die zulaessige Abstandszuordnung an den Nachbargrenzen ist ohne "
                    "konkreten Gebaeudekoerper nicht eindeutig bestimmbar. Eine einzelne "
                    "Geometrie waere hier eine Annahme und deshalb keine belastbare "
                    "Potenzialzahl."
                ),
                "hinweis": (
                    f"Der grosse Grenzabstand ({offen['gross']:g} m) gilt in der Regel fuer "
                    f"EINE Seite, die uebrigen tragen den kleinen ({offen['klein']:g} m). "
                    "Welche Seite das ist, haengt an der Fassadenorientierung des noch nicht "
                    "entworfenen Gebaeudes. Die Strassenkanten behalten in beiden Faellen "
                    "ihren klassifizierten Strassenabstand -- die Zuordnung ist dort "
                    "eindeutig."
                ),
                "szenarien": {"nachbarn_gross": unten, "nachbarn_klein": oben},
                "bandbreite": {
                    "untergrenze_szenario": "nachbarn_gross",
                    "obergrenze_szenario": "nachbarn_klein",
                    "baubereich_m2": [unten.get("baubereich_m2"), oben.get("baubereich_m2")],
                    "geschossflaeche_m2": [unten.get("geschossflaeche_m2"),
                                           oben.get("geschossflaeche_m2")],
                    "bedeutung": (
                        "Sensitivitaet der Geometrie, nicht ein baurechtlich bestimmtes "
                        "Potenzial: die Untergrenze entspricht dem grossen Abstand auf allen "
                        "Nachbarseiten (strenger als jede zulaessige Anordnung), die "
                        "Obergrenze dem kleinen auf allen."
                    ),
                },
                "betroffene_nachbarkanten": offen["kanten"],
            }
            if az is not None and landflaeche:
                # Die Ausnuetzungsziffer haengt NICHT an der Abstandszuordnung --
                # sie bleibt belastbar und wird deshalb getrennt genannt.
                antwort["zulaessige_geschossflaeche_az_m2"] = round(az * landflaeche, 2)
                antwort["zulaessige_geschossflaeche_az_rechnung"] = (
                    f"Ausnuetzungsziffer {az:g} x {landflaeche:,.1f} m2 anrechenbare "
                    f"Landflaeche")
            if entartet:
                antwort["untergrenze_entartet"] = {
                    "baubereich_m2": unten.get("baubereich_m2"),
                    "anteil_parzelle": round((unten.get("baubereich_m2") or 0.0) / parzflaeche, 4),
                    "erklaerung": (
                        "Bei grossem Abstand auf allen Nachbarseiten faellt die Huelle "
                        "praktisch zusammen -- die Parzelle ist an der schmalsten Stelle "
                        "schmaler als zwei gegenueberliegende grosse Grenzabstaende "
                        "zusammen. Das ist kein Befund ueber das Grundstueck, sondern "
                        "die Folge der strengsten Annahme."
                    ),
                }
            return antwort

        ergebnis = berechne_potenzial(parzelle_ring, kanten_abstaende, **gemeinsame_kwargs)
        kontrolle = {
            name: berechne_potenzial(parzelle_ring, kanten, **gemeinsame_kwargs).to_dict()
            for name, kanten in bandbreite_szenarien.items()
        }
        return {
            "modus": "kantenklassifikation",
            **basis_info,
            "hinweis": (
                "Jede massgebende Kante wurde geometrisch zugeordnet (Strassenachse durch das "
                "Polygon hinter der Kante = Strassenparzelle) und mit dem fuer ihre Art "
                "geltenden Abstand gerechnet. Die frueheren Bandbreiten-Szenarien stehen "
                "unter 'kontrolle_bandbreite' weiterhin daneben."
            ),
            "ergebnis": ergebnis.to_dict(),
            "kontrolle_bandbreite": kontrolle,
        }

    if kantenklassifikation is not None and not bandbreite_szenarien:
        raise G1VerdrahtungError(
            "Kantenklassifikation liegt vor, aber weder ein kantenweise belastbarer Abstand "
            f"noch ein Grenzabstand fuer die Bandbreite. Offen: {kanten_offene or 'keine Zonenwerte'}."
        )
    if not bandbreite_szenarien:
        raise G1VerdrahtungError(
            f"Zone {zone.get('zonenbezeichnung')!r} hat weder grenzabstand_klein_m noch "
            "grenzabstand_gross_m -- G1 kann ohne Grenzabstand nicht rechnen."
        )

    ergebnisse = {name: berechne_potenzial(parzelle_ring, kanten, **gemeinsame_kwargs).to_dict()
                  for name, kanten in bandbreite_szenarien.items()}

    if kanten_offene:
        basis_info["kantenzuordnung_offen"] = kanten_offene

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

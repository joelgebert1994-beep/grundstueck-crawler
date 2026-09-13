"""Parzellenkombination: bringt A+B mehr als A allein?

Dieses Modul RECHNET KEINE ZWEITE KETTE. Es tut zwei Dinge:

  1. Es vereinigt zwei Parzellenkonturen zu einer und prueft, ob eine
     Kombination ueberhaupt in Frage kommt (angrenzend, gleiche Zone,
     erschlossen).
  2. Es vergleicht zwei bereits gerechnete Ergebnisse -- eines fuer A,
     eines fuer A+B -- und beantwortet daraus die einzige Frage, um die es
     geht: **bringt die zusaetzliche Flaeche tatsaechlich zusaetzliches
     Potenzial, und lohnt sie sich zum Preis von B?**

Die Kette selbst (G1 -> SIA 416 -> Szenarien -> Wirtschaftlichkeit -> HBU)
laeuft zweimal durch DIESELBEN Funktionen. Eine zweite Rechenlogik gaebe es
sonst genau hier, und sie wuerde mit der ersten auseinanderlaufen.

Warum mehr Land nicht automatisch mehr Potenzial ist
-----------------------------------------------------
Die Geschossflaeche haengt an der Ausnuetzungsziffer, ABER auch an der
Geometrie (Grenzabstaende, Baubereich) und an der Vollgeschosszahl. Welche
dieser Grenzen bindet, steht in jedem G1-Ergebnis als
`geschossflaeche_limitiert_durch`. Drei Faelle:

  * Bindet bei A und bei A+B die Ausnuetzungsziffer, waechst die
    Geschossflaeche ungefaehr proportional zur Flaeche -- B bringt, was es
    verspricht.
  * Bindet bei A+B stattdessen die Geometrie oder die Geschosszahl, bringt
    B weniger als seine Flaeche verspricht. Manchmal gar nichts.
  * Umgekehrt kann A+B UEBERproportional gewinnen: an der gemeinsamen
    Grenze faellt ein Grenzabstand weg, der bei A noch Baubereich gekostet
    hat.

Gemessen wird das als **Ausbeute**: wie gut wird die zugekaufte Flaeche
ausgenutzt, verglichen damit, wie gut A selbst ausgenutzt wird.

    ausbeute = (dGF / Flaeche_B) / (GF_A / Flaeche_A)

Eine Ausbeute von 1.0 heisst: B traegt genauso viel Geschossflaeche je
Quadratmeter wie A. Diese Schwelle ist nicht gesetzt, sondern der
naheliegende Massstab -- A selbst. Alles darunter wird nicht in "viel" und
"wenig" eingeteilt, sondern beziffert: "B wird nur zu 34 % so gut ausgenutzt
wie A" sagt mehr als jede erfundene Grenze.

Der wirtschaftliche Zusatznutzen
---------------------------------
    Residualwert(A+B) - Residualwert(A)  =  was B hoechstens kosten darf
                                         -  tatsaechlicher Kaufpreis B
                                         -  zusaetzliche Kosten
                                         =  wirtschaftlicher Zusatznutzen

Das geht auf, weil der Residualwert vom tatsaechlich bezahlten Landpreis
unabhaengig ist: er sagt, was das Land TRAGEN kann. Die Differenz ist damit
der maximal tragbare Preis fuer B -- ohne dass irgendwo ein Bodenwert
erfunden werden muesste. Kaufpreis und Zusatzkosten sind Benutzerannahmen;
fehlen sie, wird der Mehrwert ausgewiesen und der Zusatznutzen bleibt offen.
"""
from __future__ import annotations

from typing import Any, Optional

from shapely.geometry import Polygon
from shapely.ops import unary_union

__all__ = [
    "STATUS_MOEGLICH", "STATUS_NICHT_ZULAESSIG", "STATUS_NICHT_BESTIMMBAR",
    "POTENZIAL_ZUSATZ", "POTENZIAL_WENIG", "POTENZIAL_KEIN",
    "vereinige", "pruefe_zonen", "ist_strassenparzelle", "vergleiche",
]

STATUS_MOEGLICH = "moeglich"
STATUS_NICHT_ZULAESSIG = "nicht_zulaessig"
STATUS_NICHT_BESTIMMBAR = "nicht_bestimmbar"

POTENZIAL_ZUSATZ = "zusatzpotenzial"
POTENZIAL_WENIG = "wenig_zusatzpotenzial"
POTENZIAL_KEIN = "kein_zusatzpotenzial"

# Wie weit zwei Parzellenkonturen auseinanderliegen duerfen und trotzdem als
# angrenzend gelten. Die amtliche Vermessung liefert die gemeinsame Grenze
# aus zwei getrennt digitalisierten Polygonen; identische Stuetzpunkte sind
# die Regel, aber nicht garantiert. 0.5 m ist enger als jede Parzelle und
# weiter als jede Digitalisierungsabweichung.
BERUEHRUNG_TOLERANZ_M = 0.5

# Wie lang die gemeinsame Grenze mindestens sein muss. Zwei Parzellen, die
# sich nur in einem Punkt beruehren (Eckberuehrung), sind baulich keine
# zusammenhaengende Flaeche.
MIN_BERUEHRUNGSLAENGE_M = 1.0


def _polygon(ring: Optional[list]) -> Optional[Polygon]:
    if not ring or len(ring) < 3:
        return None
    try:
        p = Polygon([(float(x), float(y)) for x, y in ring])
    except (TypeError, ValueError):
        return None
    if not p.is_valid:
        p = p.buffer(0)
    return p if (not p.is_empty and p.area > 0) else None


def _aussenring(geom) -> list[list[float]]:
    return [[round(x, 3), round(y, 3)] for x, y in geom.exterior.coords[:-1]]


def vereinige(
    ring_a: Optional[list],
    ring_b: Optional[list],
    *,
    toleranz_m: float = BERUEHRUNG_TOLERANZ_M,
) -> dict[str, Any]:
    """Vereinigt zwei Parzellenkonturen -- wenn sie ueberhaupt zusammengehoeren.

    Reine Geometrie, kein Netzzugriff. Liefert Status, die vereinigte Kontur
    und die Laenge der gemeinsamen Grenze. Letztere ist nicht nur Statistik:
    genau an dieser Grenze faellt bei einer Kombination der Grenzabstand weg,
    und daher stammt ein etwaiger ueberproportionaler Gewinn.
    """
    pa, pb = _polygon(ring_a), _polygon(ring_b)
    if pa is None or pb is None:
        fehlt = "A" if pa is None else "B"
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": f"Fuer Parzelle {fehlt} liegt keine brauchbare Kontur vor -- "
                     "ohne Geometrie laesst sich nichts vereinigen.",
        }

    ueberlappung = pa.intersection(pb).area
    if ueberlappung > max(pa.area, pb.area) * 0.01:
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": (f"Die beiden Konturen ueberlappen sich um {ueberlappung:,.0f} m2. "
                      "Das sind keine zwei Nachbarparzellen, sondern zweimal dieselbe "
                      "oder eine fehlerhafte Geometrie."),
        }

    # Beruehrungslaenge ueber einen schmalen Puffer: identische Stuetzpunkte
    # sind in der amtlichen Vermessung die Regel, aber nicht garantiert.
    gemeinsam = pa.buffer(toleranz_m).intersection(pb.buffer(toleranz_m))
    laenge = 0.0
    if not gemeinsam.is_empty and gemeinsam.area > 0:
        # Die Pufferflaeche ist rund (Beruehrungslaenge x 2 x Toleranz);
        # daraus die Laenge zurueckrechnen.
        laenge = gemeinsam.area / (2 * toleranz_m)

    if laenge < MIN_BERUEHRUNGSLAENGE_M:
        return {
            "status": STATUS_NICHT_ZULAESSIG,
            "grund": (f"Die Parzellen grenzen nicht aneinander (gemeinsame Grenze "
                      f"{laenge:.1f} m, noetig mindestens {MIN_BERUEHRUNGSLAENGE_M:.0f} m). "
                      "Zwei getrennte Grundstuecke ergeben keine gemeinsame Bauflaeche."),
            "beruehrungslaenge_m": round(laenge, 1),
        }

    vereinigt = unary_union([pa, pb])
    if vereinigt.geom_type == "Polygon":
        # Die Vereinigung behaelt die Stuetzpunkte der gemeinsamen Grenze,
        # auch wenn sie jetzt mitten auf einer geraden Kante liegen. Aus zwei
        # Rechtecken wuerde sonst ein Sechseck mit zwei Scheinkanten -- und
        # jede Scheinkante kostet einen Klassifikationsaufruf und verzerrt die
        # Mitre-Konstruktion des Baubereichs.
        vereinfacht = vereinigt.simplify(0.01, preserve_topology=True)
        if not vereinfacht.is_empty and vereinfacht.geom_type == "Polygon":
            vereinigt = vereinfacht
    if vereinigt.geom_type != "Polygon":
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": ("Die Vereinigung ergibt keine einzelne zusammenhaengende Flaeche "
                      f"({vereinigt.geom_type}). Ohne eine Kontur rechnet G1 nicht."),
            "beruehrungslaenge_m": round(laenge, 1),
        }
    if list(vereinigt.interiors):
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": ("Die Vereinigung enthaelt ein Loch -- zwischen den Parzellen liegt "
                      "eine dritte Flaeche. Das ist keine durchgehende Bauparzelle."),
            "beruehrungslaenge_m": round(laenge, 1),
        }

    return {
        "status": STATUS_MOEGLICH,
        "ring": _aussenring(vereinigt),
        "flaeche_m2": round(vereinigt.area, 1),
        "flaeche_a_m2": round(pa.area, 1),
        "flaeche_b_m2": round(pb.area, 1),
        "beruehrungslaenge_m": round(laenge, 1),
        "hinweis": (
            f"Gemeinsame Grenze {laenge:.1f} m. An dieser Grenze entfaellt bei einer "
            "Kombination der Grenzabstand -- daher kann der Baubereich staerker wachsen "
            "als die Flaeche."
        ),
    }


def ist_strassenparzelle(
    kantenklassifikation_a: Optional[dict],
    egrid_b: Optional[str],
    nummer_b: Optional[str] = None,
) -> Optional[str]:
    """Ist B eine Strassenparzelle? Gibt den Ausschlussgrund oder None.

    Die Kantenklassifikation von A weiss das bereits: sie markiert eine
    Nachbarkante als "strasse", wenn durch die dahinterliegende Parzelle eine
    Strassenachse laeuft. Diese Information wird hier nur gelesen -- keine
    neue Abfrage.

    Warum die Zonenpruefung das nicht abfaengt: Zonenplaene legen die Bauzone
    regelmaessig ueber die Strassenflaeche mit. Real beobachtet an Rosenweg 4
    (Buchs AG): die Strassenparzelle 1143 liegt laut Klassifikation in
    derselben Gartenstadtzone wie das Grundstueck und ergab dadurch
    385'071 CHF "Mehrwert" -- fuer eine Flaeche, die niemand kaufen und
    ueberbauen kann.
    """
    if not egrid_b:
        return None
    for kante in ((kantenklassifikation_a or {}).get("kanten") or []):
        if kante.get("art") == "strasse" and kante.get("nachbar_egrid") == egrid_b:
            name = nummer_b or kante.get("nachbar_nummer") or egrid_b
            return (
                f"Parzelle {name} ist eine Strassenparzelle -- durch sie fuehrt eine "
                "Strassenachse. Oeffentliche Verkehrsflaeche laesst sich nicht zur "
                "Bauparzelle schlagen, auch wenn der Zonenplan die Zone darueberlegt."
            )
    return None


def _bezeichnungen(zonen: Any) -> set[str]:
    """Normalisiert Zonenbezeichnungen fuer den Vergleich."""
    if not zonen:
        return set()
    # Ein einzelnes Zonen-Dict darf nicht wie eine Liste behandelt werden:
    # ueber ein dict zu iterieren liefert die SCHLUESSEL, und damit waeren
    # zwei voellig verschiedene Zonen "gleich", weil beide das Feld
    # typ_kommunal_bezeichnung tragen. Genau das ist beim ersten Lauf
    # passiert -- Wohnzone W2 und Gewerbezone G galten als dieselbe Zone.
    if isinstance(zonen, (str, dict)):
        zonen = [zonen]
    namen = set()
    for z in zonen:
        text = z if isinstance(z, str) else (
            (z or {}).get("typ_kommunal_bezeichnung")
            or (z or {}).get("typ_kantonal_bezeichnung")
            or (z or {}).get("bezeichnung"))
        if text:
            namen.add(" ".join(str(text).split()).casefold())
    return namen


def pruefe_zonen(zonen_a: Any, zonen_b: Any) -> dict[str, Any]:
    """Liegen beide Parzellen in derselben Bauzone?

    Das ist kein Formalismus: Ausnuetzungsziffer, Grenzabstaende und
    Geschosszahl gelten je Zone. Liegt B in einer anderen Zone, muesste die
    Ausnuetzung je Zonenanteil gerechnet werden -- das leistet diese Engine
    heute nicht, und eine mit A's Kennzahlen durchgerechnete Gesamtflaeche
    waere schlicht falsch.

    Ausdruecklich NICHT "unzulaessig": eine Kombination ueber eine
    Zonengrenze ist rechtlich moeglich. Sie ist hier nur nicht bestimmbar.
    """
    a, b = _bezeichnungen(zonen_a), _bezeichnungen(zonen_b)
    if not a or not b:
        fehlt = "A" if not a else "B"
        return {
            "gleich": None,
            "status": STATUS_NICHT_BESTIMMBAR,
            "zonen_a": sorted(a), "zonen_b": sorted(b),
            "grund": (f"Fuer Parzelle {fehlt} ist keine amtliche Zonenbezeichnung "
                      "verfuegbar. Ohne sie laesst sich nicht feststellen, ob dieselben "
                      "Nutzungsziffern gelten."),
        }
    if a & b:
        return {
            "gleich": True,
            "status": STATUS_MOEGLICH,
            "zonen_a": sorted(a), "zonen_b": sorted(b),
            "grund": f"Beide Parzellen liegen in derselben Zone ({sorted(a & b)[0]}).",
        }
    return {
        "gleich": False,
        "status": STATUS_NICHT_BESTIMMBAR,
        "zonen_a": sorted(a), "zonen_b": sorted(b),
        "grund": (
            f"A liegt in {', '.join(sorted(a))}, B in {', '.join(sorted(b))}. "
            "Ausnuetzung, Grenzabstaende und Geschosszahl gelten je Zone; die "
            "kombinierte Flaeche muesste je Zonenanteil gerechnet werden. Das "
            "leistet diese Engine nicht -- eine mit den Kennzahlen von A "
            "durchgerechnete Gesamtflaeche waere falsch, nicht nur ungenau."
        ),
    }


def _g1_werte(g1_ergebnis: Optional[dict]) -> dict[str, Any]:
    """Baubereich, Fussabdruck und Geschosszahl aus einem G1-Ergebnis.

    Der Baubereich ist hier oft die sprechendste Zahl: an der gemeinsamen
    Grenze faellt der Grenzabstand weg, und die bebaubare Flaeche waechst
    dadurch staerker als das Grundstueck. Real gemessen an Rosenweg 4:
    117 m2 bebaubar bei A allein, 683 m2 bei A+B -- bei nur 2.4-facher
    Grundstuecksflaeche.
    """
    if not g1_ergebnis or g1_ergebnis.get("modus") ==             "bandbreite_grenzabstand_kante_nicht_differenziert":
        return {}
    e = g1_ergebnis.get("ergebnis") or {}
    return {
        "baubereich_m2": e.get("baubereich_m2"),
        "fussabdruck_m2": e.get("fussabdruck_m2"),
        "fussabdruck_limitiert_durch": e.get("fussabdruck_limitiert_durch"),
        "geschosszahl": e.get("geschosszahl"),
    }


def _geschossflaeche(g1_ergebnis: Optional[dict]) -> tuple[Optional[float], Optional[str]]:
    """Geschossflaeche und die bindende Grenze aus einem G1-Ergebnis.

    Bei einer Bandbreite (Kantenzuordnung offen) gibt es keine einzelne
    Zahl -- dann auch keine, die sich vergleichen liesse.
    """
    if not g1_ergebnis:
        return None, None
    if g1_ergebnis.get("modus") == "bandbreite_grenzabstand_kante_nicht_differenziert":
        return None, "bandbreite"
    e = g1_ergebnis.get("ergebnis") or {}
    return e.get("geschossflaeche_m2"), e.get("geschossflaeche_limitiert_durch")


def _bester_residualwert(wirtschaft: Optional[dict]) -> tuple[Optional[float], Optional[str]]:
    """Der hoechste tragbare Landwert ueber alle gerechneten Szenarien."""
    szenarien = (wirtschaft or {}).get("szenarien") or {}
    bester, wer = None, None
    for name, s in szenarien.items():
        wert = ((s or {}).get("residualwert") or {}).get("max_landwert_chf")
        if wert is not None and (bester is None or wert > bester):
            bester, wer = wert, name
    return bester, wer


def _hbu_empfehlung(wirtschaft: Optional[dict]) -> Optional[str]:
    hbu = (wirtschaft or {}).get("hbu") or {}
    return ((hbu.get("empfehlung") or {}).get("id")) if hbu.get("status") == "empfohlen" else None


def vergleiche(
    a: dict[str, Any],
    ab: dict[str, Any],
    *,
    flaeche_a_m2: Optional[float],
    flaeche_b_m2: Optional[float],
    kaufpreis_b_chf: Optional[float] = None,
    zusatzkosten_chf: Optional[float] = None,
) -> dict[str, Any]:
    """Stellt zwei fertig gerechnete Ergebnisse gegenueber.

    `a` und `ab` sind je {"g1": ..., "szenarien": ..., "wirtschaft": ...} --
    genau die Strukturen, die die Pipeline ohnehin erzeugt. Hier wird nichts
    nachgerechnet, nur verglichen.
    """
    gf_a, grenze_a = _geschossflaeche(a.get("g1"))
    gf_ab, grenze_ab = _geschossflaeche(ab.get("g1"))

    ergebnis: dict[str, Any] = {
        "flaeche": {
            "a_m2": flaeche_a_m2,
            "b_m2": flaeche_b_m2,
            "ab_m2": (round(flaeche_a_m2 + flaeche_b_m2, 1)
                      if flaeche_a_m2 is not None and flaeche_b_m2 is not None else None),
            "zuwachs_anteil": (round(flaeche_b_m2 / flaeche_a_m2, 4)
                               if flaeche_a_m2 and flaeche_b_m2 else None),
        },
        "baubereich": {
            "a": _g1_werte(a.get("g1")),
            "ab": _g1_werte(ab.get("g1")),
        },
        "geschossflaeche": {
            "a_m2": gf_a, "ab_m2": gf_ab,
            "zuwachs_m2": (round(gf_ab - gf_a, 1)
                           if gf_a is not None and gf_ab is not None else None),
            "limitiert_durch_a": grenze_a,
            "limitiert_durch_ab": grenze_ab,
        },
    }

    # --- Bringt B zusaetzliches Potenzial? --------------------------------
    if gf_a is None or gf_ab is None or not flaeche_a_m2 or not flaeche_b_m2:
        offen = []
        if gf_a is None:
            offen.append("fuer A" + (" (Baubereich nur als Bandbreite)"
                                     if grenze_a == "bandbreite" else ""))
        if gf_ab is None:
            offen.append("fuer A+B" + (" (Baubereich nur als Bandbreite)"
                                       if grenze_ab == "bandbreite" else ""))
        ergebnis["potenzial"] = {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": ("Keine vergleichbare Geschossflaeche "
                      + " und ".join(offen) + ". Ohne beide Zahlen laesst sich nicht "
                      "sagen, ob die zusaetzliche Flaeche etwas bringt."),
        }
    else:
        zuwachs = gf_ab - gf_a
        dichte_a = gf_a / flaeche_a_m2
        ausbeute = (zuwachs / flaeche_b_m2) / dichte_a if dichte_a else None

        if zuwachs <= 0:
            status = POTENZIAL_KEIN
            satz = (
                f"Die zusaetzlichen {flaeche_b_m2:,.0f} m2 bringen keine zusaetzliche "
                f"Geschossflaeche ({zuwachs:+,.0f} m2). "
                + (f"Bei A+B bindet '{grenze_ab}' -- nicht die Flaeche."
                   if grenze_ab else "")
            )
        # Verglichen wird die GERUNDETE Ausbeute. Sie wird ohnehin nur auf
        # Prozent genau ausgewiesen; eine Ausbeute von 0.9995 als "wenig"
        # zu fuehren, waere eine Scheingenauigkeit in die andere Richtung.
        elif ausbeute is not None and round(ausbeute, 2) >= 1.0:
            status = POTENZIAL_ZUSATZ
            satz = (
                f"Die zusaetzlichen {flaeche_b_m2:,.0f} m2 bringen {zuwachs:,.0f} m2 "
                f"Geschossflaeche. Das entspricht {ausbeute:.0%} der Dichte, mit der A "
                "selbst ausgenutzt wird -- B traegt also mindestens so viel wie A."
            )
        else:
            status = POTENZIAL_WENIG
            satz = (
                f"Die zusaetzlichen {flaeche_b_m2:,.0f} m2 bringen nur {zuwachs:,.0f} m2 "
                f"Geschossflaeche. B wird damit zu {ausbeute:.0%} so gut ausgenutzt wie A. "
                + (f"Bei A allein bindet '{grenze_a}', bei A+B '{grenze_ab}'."
                   if grenze_a and grenze_ab and grenze_a != grenze_ab
                   else f"Gebunden wird in beiden Faellen durch '{grenze_ab}'."
                   if grenze_ab else "")
            )

        ergebnis["potenzial"] = {
            "status": status,
            "zuwachs_geschossflaeche_m2": round(zuwachs, 1),
            "ausbeute": round(ausbeute, 4) if ausbeute is not None else None,
            "dichte_a_gf_pro_m2": round(dichte_a, 4),
            "dichte_b_gf_pro_m2": round(zuwachs / flaeche_b_m2, 4),
            "begruendung": satz,
        }

    # --- Lohnt sich B wirtschaftlich? -------------------------------------
    res_a, szen_a = _bester_residualwert(a.get("wirtschaft"))
    res_ab, szen_ab = _bester_residualwert(ab.get("wirtschaft"))
    wirtschaft: dict[str, Any] = {
        "residualwert_a_chf": res_a,
        "residualwert_ab_chf": res_ab,
        "bestes_szenario_a": szen_a,
        "bestes_szenario_ab": szen_ab,
        "kaufpreis_b_chf": kaufpreis_b_chf,
        "zusatzkosten_chf": zusatzkosten_chf,
    }
    if res_a is None or res_ab is None:
        wirtschaft.update(
            status=STATUS_NICHT_BESTIMMBAR,
            grund=("Der maximal tragbare Landwert fehlt "
                   + ("fuer A" if res_a is None else "")
                   + (" und " if res_a is None and res_ab is None else "")
                   + ("fuer A+B" if res_ab is None else "")
                   + ". Ohne beide laesst sich nicht sagen, was B wert sein darf."),
        )
    else:
        mehrwert = res_ab - res_a
        wirtschaft["mehrwert_chf"] = round(mehrwert, 0)
        wirtschaft["mehrwert_pro_m2_b"] = (round(mehrwert / flaeche_b_m2, 0)
                                           if flaeche_b_m2 else None)
        wirtschaft["rechnung"] = (
            f"{res_ab:,.0f} CHF tragbarer Landwert fuer A+B minus {res_a:,.0f} CHF fuer A "
            f"allein = {mehrwert:,.0f} CHF. So viel darf B hoechstens kosten, damit die "
            "Kombination gegenueber A allein nicht schlechter dasteht."
        )
        if kaufpreis_b_chf is None:
            wirtschaft.update(
                status=STATUS_NICHT_BESTIMMBAR,
                grund=("Der Kaufpreis fuer B ist nicht gesetzt. Der Mehrwert steht, der "
                       "Zusatznutzen bleibt offen -- ein Preis wird hier nicht "
                       "geschaetzt."),
            )
        else:
            zusatznutzen = mehrwert - kaufpreis_b_chf - (zusatzkosten_chf or 0.0)
            wirtschaft.update(
                status=STATUS_MOEGLICH,
                zusatznutzen_chf=round(zusatznutzen, 0),
                lohnt_sich=zusatznutzen > 0,
                grund=(
                    f"{mehrwert:,.0f} CHF Mehrwert minus {kaufpreis_b_chf:,.0f} CHF Kaufpreis"
                    + (f" minus {zusatzkosten_chf:,.0f} CHF zusaetzliche Kosten"
                       if zusatzkosten_chf else "")
                    + f" = {zusatznutzen:,.0f} CHF."
                    + (" Die Kombination traegt sich." if zusatznutzen > 0
                       else " Zu diesem Preis traegt sich die Kombination nicht.")
                ),
            )
    ergebnis["wirtschaft"] = wirtschaft

    # --- Aendert sich die beste Nutzung? ----------------------------------
    hbu_a, hbu_ab = _hbu_empfehlung(a.get("wirtschaft")), _hbu_empfehlung(ab.get("wirtschaft"))
    ergebnis["hbu"] = {
        "empfehlung_a": hbu_a,
        "empfehlung_ab": hbu_ab,
        "aendert_sich": (hbu_a != hbu_ab) if (hbu_a and hbu_ab) else None,
        "hinweis": (
            f"Mit B wird nicht mehr '{hbu_a}' empfohlen, sondern '{hbu_ab}'."
            if hbu_a and hbu_ab and hbu_a != hbu_ab
            else f"Die beste Nutzung bleibt '{hbu_a}'." if hbu_a and hbu_a == hbu_ab
            else "Fuer mindestens eine der beiden Varianten gibt es keine Empfehlung -- "
                 "ein Vergleich der besten Nutzung ist damit nicht moeglich."
        ),
    }

    # --- Szenario fuer Szenario -------------------------------------------
    sz_a = (a.get("wirtschaft") or {}).get("szenarien") or {}
    sz_ab = (ab.get("wirtschaft") or {}).get("szenarien") or {}
    # Die Bezeichnung stammt aus dem Szenarienergebnis, nicht aus einer
    # zweiten Liste in der Oberflaeche: sonst heisst dasselbe Szenario an
    # zwei Stellen verschieden, sobald eines dazukommt.
    namen = {}
    for quelle in ((a.get("szenarien") or {}).get("szenarien") or {},
                   (ab.get("szenarien") or {}).get("szenarien") or {}):
        for schluessel, eintrag in quelle.items():
            if (eintrag or {}).get("bezeichnung"):
                namen.setdefault(schluessel, eintrag["bezeichnung"])
    zeilen = []
    for name in sorted(set(sz_a) | set(sz_ab)):
        wert_a = ((sz_a.get(name) or {}).get("residualwert") or {}).get("max_landwert_chf")
        wert_ab = ((sz_ab.get(name) or {}).get("residualwert") or {}).get("max_landwert_chf")
        zeilen.append({
            "id": name,
            "bezeichnung": namen.get(name),
            "residualwert_a_chf": wert_a,
            "residualwert_ab_chf": wert_ab,
            "differenz_chf": (round(wert_ab - wert_a, 0)
                              if wert_a is not None and wert_ab is not None else None),
        })
    ergebnis["szenarien"] = zeilen
    return ergebnis

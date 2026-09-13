"""Highest & Best Use: die vorhandenen Ergebnisse zu einer Empfehlung fuehren.

Dieses Modul RECHNET NICHTS NEU. Es liest, was Szenarien, Wirtschaftlichkeit
und Marktauswertung ohnehin ergeben haben, und beantwortet daraus eine
einzige Frage: **welche Nutzung ist die beste -- und ist die Datenlage
ueberhaupt gut genug, um das zu sagen?**

Die vier Pruefstufen sind die klassische HBU-Definition, in genau der
Reihenfolge, in der die Engine ohnehin arbeitet:

    1  rechtlich zulaessig       machbarkeit, Konflikte mit schwere=ausschluss
    2  physisch moeglich         Baukoerper aus dem G1-Baubereich
    3  finanziell durchfuehrbar  Zielmarge erreicht, Residualwert positiv
    4  hoechster Wert            Residualwert (max. tragbarer Landwert)

Warum der Residualwert und nicht der Gewinn
-------------------------------------------
HBU fragt, welche Nutzung DAS GRUNDSTUECK am wertvollsten macht. Genau das
ist der maximal tragbare Landwert: er ist unabhaengig davon, was tatsaechlich
fuer das Land bezahlt wurde, und macht Nutzungen damit fair vergleichbar.

Der absolute Gewinn bevorzugt immer das groesste Projekt, die Marge immer das
kleinste -- beide beantworten die Frage nicht.

Filter, kein Score
------------------
Ein Szenario, das eine Stufe nicht besteht, wird mit Grund AUSGESCHIEDEN --
nicht schlechter bewertet. Es gibt keine Punktzahl und keine Gewichtung:
eine gewichtete Kennzahl wuerde rechtliche Unzulaessigkeit gegen einen
hoeheren Gewinn aufrechenbar machen, und das ist sie nicht.

Wann KEINE Empfehlung ausgesprochen wird
-----------------------------------------
* Kein Szenario besteht alle vier Stufen.
* Der Residualwert der Spitzenkandidaten ist nicht bestimmbar.
* Der Abstand zwischen Platz 1 und 2 ist kleiner als die Streuung der
  Marktreferenz -- dann sind sie praktisch gleichwertig, und eine Rangfolge
  waere Scheingenauigkeit.

Die Schwelle im letzten Punkt wird AUS DEN DATEN abgeleitet, nicht gesetzt:
streuen die erfassten Vergleichsobjekte um +/-3 % um ihren Median, ist ein
Unterschied unterhalb dieser Bandbreite nicht unterscheidbar. Gibt es keine
Vergleichsobjekte, gibt es auch keine abgeleitete Schwelle -- dann wird
gereiht, aber ausdruecklich als nicht belastbar gekennzeichnet.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "STATUS_EMPFOHLEN", "STATUS_GLEICHWERTIG", "STATUS_NICHT_BESTIMMBAR",
    "STUFEN", "bestimme_hbu",
]

STATUS_EMPFOHLEN = "empfohlen"
STATUS_GLEICHWERTIG = "gleichwertig"
STATUS_NICHT_BESTIMMBAR = "nicht_bestimmbar"

# Die vier Stufen, in Pruefreihenfolge.
STUFEN = (
    ("rechtlich", "rechtlich zulaessig"),
    ("physisch", "physisch moeglich"),
    ("finanziell", "finanziell durchfuehrbar"),
    ("wert", "hoechster Wert"),
)

# Machbarkeitswerte, die eine rechtliche Zulaessigkeit bedeuten. "besteht"
# gehoert dazu: der Bestand steht ja bereits rechtmaessig.
_RECHTLICH_OK = {"moeglich", "eingeschraenkt_moeglich", "besteht"}

# Ohne Marktreferenz laesst sich keine Unterscheidungsschwelle ableiten.
# Dann wird gereiht, aber die Rangfolge gilt als nicht belastbar.
_OHNE_REFERENZ_HINWEIS = (
    "Ohne erfasste Vergleichsobjekte laesst sich nicht bestimmen, ab welchem "
    "Abstand zwei Nutzungen wirklich unterscheidbar sind. Die Rangfolge "
    "beruht dann allein auf eigenen Annahmen und ist nicht marktseitig "
    "belegt."
)


def _streuung_aus_markt(marktlage: Optional[dict[str, Any]]) -> Optional[float]:
    """Relative Streuung der Verkaufsreferenzen um ihren Median.

    Das ist die einzige Groesse in diesem Modul, die aus Daten stammt statt
    aus einer Setzung -- und sie entscheidet, ab wann zwei Nutzungen als
    unterscheidbar gelten. Fehlen Referenzen, gibt es keine Schwelle.
    """
    verkauf = (marktlage or {}).get("verkauf") or {}
    spanne = verkauf.get("spanne")
    median = verkauf.get("median")
    if not spanne or len(spanne) != 2 or not median:
        return None
    halbe_breite = (spanne[1] - spanne[0]) / 2.0
    if halbe_breite <= 0:
        return None
    return round(halbe_breite / median, 4)


def _pruefe_szenario(
    szenario: dict[str, Any], wirtschaft: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Welche der vier Stufen erreicht dieses Szenario -- und woran scheitert es?"""
    id_ = szenario.get("id")
    eintrag: dict[str, Any] = {
        "id": id_,
        "bezeichnung": szenario.get("bezeichnung"),
        "erreichte_stufe": None,
        "gescheitert_an": None,
        "nicht_beurteilbar": False,
        "grund": None,
        "max_landwert_chf": None,
    }

    # --- 1 rechtlich ------------------------------------------------------
    machbarkeit = szenario.get("machbarkeit")
    ausschluesse = [k for k in (szenario.get("konflikte") or [])
                    if k.get("schwere") == "ausschluss"]
    if machbarkeit == "nicht_bestimmbar":
        # WICHTIG: "nicht bestimmbar" heisst nicht "unzulaessig". Am echten
        # Fall (Rosenweg 4) traegt die Sanierung genau diesen Wert, obwohl
        # ihre eigene Begruendung "baulich moeglich" sagt -- unbestimmt ist
        # dort die Wirtschaftlichkeit, nicht das Baurecht. Wer das als
        # Scheitern an Stufe 1 fuehrt, behauptet in einem Investorenbericht
        # eine rechtliche Unzulaessigkeit, die niemand festgestellt hat.
        # Solche Szenarien sind deshalb NICHT BEURTEILBAR -- weder in der
        # Rangfolge noch ausgeschieden.
        eintrag.update(nicht_beurteilbar=True,
                       grund=f"Machbarkeit nicht bestimmbar: {szenario.get('begruendung') or '-'}")
        return eintrag
    if machbarkeit not in _RECHTLICH_OK:
        eintrag.update(gescheitert_an="rechtlich",
                       grund=szenario.get("begruendung") or "Baurechtlich nicht moeglich.")
        return eintrag
    if ausschluesse:
        eintrag.update(gescheitert_an="rechtlich",
                       grund="; ".join(k.get("meldung", "") for k in ausschluesse))
        return eintrag
    eintrag["erreichte_stufe"] = "rechtlich"

    # --- 2 physisch -------------------------------------------------------
    # Ein Szenario ohne Baukoerper hat keine Geometrie, auf die sich eine
    # Aussage stuetzen liesse. "bestand" und "sanierung" haben den
    # Bestandskoerper, alles andere einen berechneten.
    if not (szenario.get("baukoerper") or []):
        eintrag.update(gescheitert_an="physisch",
                       grund="Kein Baukoerper vorhanden -- ohne Geometrie keine belastbare "
                             "Aussage ueber die Nutzung.")
        return eintrag
    eintrag["erreichte_stufe"] = "physisch"

    # --- 3 finanziell -----------------------------------------------------
    if not wirtschaft:
        eintrag.update(gescheitert_an="finanziell",
                       grund="Keine Wirtschaftlichkeitsrechnung fuer dieses Szenario.")
        return eintrag

    residual = wirtschaft.get("residualwert") or {}
    landwert = residual.get("max_landwert_chf")
    if landwert is None:
        eintrag.update(gescheitert_an="finanziell",
                       grund=residual.get("grund") or "Residualwert nicht bestimmbar.")
        return eintrag
    eintrag["max_landwert_chf"] = landwert
    eintrag["max_landwert_chf_pro_m2"] = residual.get("max_landwert_chf_pro_m2")

    if landwert <= 0:
        eintrag.update(gescheitert_an="finanziell",
                       grund=f"Der maximal tragbare Landwert ist {landwert:,.0f} CHF -- "
                             "zu den gesetzten Annahmen traegt diese Nutzung keinen "
                             "Landpreis.")
        return eintrag

    ergebnis = wirtschaft.get("ergebnis") or {}
    eintrag["marge"] = ergebnis.get("marge")
    eintrag["zielmarge_erreicht"] = ergebnis.get("zielmarge_erreicht")
    eintrag["gewinn_chf"] = ergebnis.get("gewinn_chf")
    eintrag["kosten_vollstaendig"] = (wirtschaft.get("kosten") or {}).get("vollstaendig")
    eintrag["erreichte_stufe"] = "finanziell"
    return eintrag


def bestimme_hbu(
    szenarien_ergebnis: Optional[dict[str, Any]],
    wirtschaft_ergebnis: Optional[dict[str, Any]],
    marktlage: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fuehrt die vorhandenen Ergebnisse zu einer Empfehlung zusammen.

    Liest ausschliesslich bereits gerechnete Werte. Gibt es sie nicht, wird
    das gesagt -- nicht ersatzweise geschaetzt.
    """
    szenarien = (szenarien_ergebnis or {}).get("szenarien") or {}
    if not szenarien:
        return {
            "status": STATUS_NICHT_BESTIMMBAR,
            "grund": (szenarien_ergebnis or {}).get("grund")
                     or "Keine Entwicklungsszenarien vorhanden.",
            "stufen": [{"schluessel": k, "bezeichnung": b} for k, b in STUFEN],
        }

    wirtschaft = (wirtschaft_ergebnis or {}).get("szenarien") or {}

    geprueft = [_pruefe_szenario(dict(s, id=s.get("id") or name), wirtschaft.get(name))
                for name, s in szenarien.items()]

    bestanden = [e for e in geprueft if e["erreichte_stufe"] == "finanziell"]
    # Drei Gruppen, nicht zwei: bestanden, an einer Stufe ausgeschieden, und
    # gar nicht beurteilbar. Die dritte Gruppe darf nicht in die zweite
    # gerechnet werden -- "unbekannt" ist kein Mangel des Szenarios.
    nicht_beurteilbar = [e for e in geprueft if e.get("nicht_beurteilbar")]
    ausgeschieden = [e for e in geprueft
                     if e["erreichte_stufe"] != "finanziell" and not e.get("nicht_beurteilbar")]

    ergebnis: dict[str, Any] = {
        "stufen": [{"schluessel": k, "bezeichnung": b} for k, b in STUFEN],
        "geprueft": geprueft,
        "ausgeschieden": ausgeschieden,
        "nicht_beurteilbar": nicht_beurteilbar,
        "kriterium": {
            "groesse": "max_landwert_chf",
            "bezeichnung": "maximal tragbarer Landwert",
            "begruendung": (
                "Highest & Best Use fragt, welche Nutzung das GRUNDSTUECK am wertvollsten "
                "macht -- das ist der maximal tragbare Landwert. Er ist unabhaengig davon, "
                "was tatsaechlich fuer das Land bezahlt wurde, und macht die Nutzungen "
                "dadurch vergleichbar. Der absolute Gewinn bevorzugte immer das groesste "
                "Projekt, die Marge immer das kleinste."
            ),
        },
    }

    if not bestanden:
        ergebnis.update(
            status=STATUS_NICHT_BESTIMMBAR,
            grund=(
                "Kein Szenario besteht alle Pruefstufen. Damit gibt es keine beste "
                "Nutzung, die sich benennen liesse -- was jeweils fehlt, steht bei den "
                "ausgeschiedenen Szenarien."
                + (f" {len(nicht_beurteilbar)} weitere Szenarien waren gar nicht "
                   "beurteilbar; ob eines davon besser abschneidet, ist offen."
                   if nicht_beurteilbar else "")
            ),
            rangfolge=[],
        )
        return ergebnis

    rangfolge = sorted(bestanden, key=lambda e: e["max_landwert_chf"], reverse=True)
    # Gleiche Werte teilen sich den Platz (1, 2, 2, 2). Am echten Fall ergeben
    # Anbau, Aufstockung und Bestand+Neubau denselben Landwert, weil in allen
    # drei Faellen dieselbe ungenutzte Ausnuetzung die bindende Groesse ist.
    # Sie durchzunummerieren behauptete eine Reihenfolge, die die Zahlen nicht
    # hergeben.
    platz, letzter = 0, None
    for i, e in enumerate(rangfolge, start=1):
        if letzter is None or e["max_landwert_chf"] != letzter:
            platz, letzter = i, e["max_landwert_chf"]
        e["platz"] = platz
    ergebnis["rangfolge"] = rangfolge

    # --- Ist der Vorsprung ueberhaupt unterscheidbar? ---------------------
    streuung = _streuung_aus_markt(marktlage)
    erster = rangfolge[0]
    zweiter = rangfolge[1] if len(rangfolge) > 1 else None

    belastbarkeit: dict[str, Any] = {
        "marktreferenz_vorhanden": streuung is not None,
        "streuung_marktreferenz": streuung,
        "sicherheit_verkauf": ((marktlage or {}).get("verkauf") or {}).get("sicherheit"),
    }

    if zweiter is not None and erster["max_landwert_chf"] > 0:
        abstand = (erster["max_landwert_chf"] - zweiter["max_landwert_chf"]) \
            / erster["max_landwert_chf"]
        belastbarkeit["abstand_zum_zweiten"] = round(abstand, 4)
        # Ein exakter Gleichstand macht die Spitze auch ohne Marktreferenz
        # ununterscheidbar -- dann gaebe die Sortierreihenfolge den Ausschlag,
        # und das waere reine Willkuer.
        if abstand <= 0 or (streuung is not None and abstand < streuung):
            ergebnis.update(
                status=STATUS_GLEICHWERTIG,
                empfehlung=None,
                grund=(
                    f"{erster['bezeichnung']} und {zweiter['bezeichnung']} liegen im "
                    + (f"maximal tragbaren Landwert gleichauf."
                       if abstand <= 0 else
                       f"maximal tragbaren Landwert nur {abstand:.1%} auseinander. Die "
                       f"erfassten Vergleichsobjekte streuen selbst um {streuung:.1%} -- "
                       "ein Unterschied unterhalb dieser Bandbreite ist nicht "
                       "unterscheidbar.")
                    + " Beide Nutzungen sind praktisch gleichwertig; die "
                      "Entscheidung faellt an Risiko, Bauzeit und Aufwand, nicht an "
                      "dieser Rechnung."
                ),
                belastbarkeit=belastbarkeit,
            )
            return ergebnis

    if streuung is None:
        belastbarkeit["hinweis"] = _OHNE_REFERENZ_HINWEIS

    offene = [e for e in (erster.get("grund"),) if e]
    unvollstaendige_kosten = erster.get("kosten_vollstaendig") is False

    begruendung = (
        f"{erster['bezeichnung']} ergibt mit {erster['max_landwert_chf']:,.0f} CHF den "
        f"hoechsten maximal tragbaren Landwert"
        + (f" ({erster['max_landwert_chf_pro_m2']:,.0f} CHF/m2 Grundstueck)"
           if erster.get("max_landwert_chf_pro_m2") else "")
        + ". Das Szenario ist baurechtlich zulaessig, hat eine berechnete Geometrie und "
          "traegt zu den gesetzten Annahmen einen positiven Landwert."
        + (f" Der Vorsprung auf {zweiter['bezeichnung']} betraegt "
           f"{belastbarkeit.get('abstand_zum_zweiten', 0):.1%}." if zweiter else
           " Es ist das einzige Szenario, das alle Pruefstufen besteht.")
    )

    vorbehalte = []
    if nicht_beurteilbar:
        # Ohne diesen Satz laese sich die Empfehlung als "das Beste von allem"
        # verstehen. Sie ist das Beste von dem, was beurteilbar war.
        vorbehalte.append(
            "Nicht beurteilbar waren: "
            + ", ".join(e["bezeichnung"] or e["id"] for e in nicht_beurteilbar)
            + ". Die Empfehlung gilt fuer die beurteilbaren Szenarien -- ob eines der "
              "uebrigen besser abschneidet, ist offen."
        )
    if unvollstaendige_kosten:
        vorbehalte.append(
            "Die Baukosten sind unvollstaendig -- einzelne BKP-Positionen konnten nicht "
            "gerechnet werden. Der Landwert faellt dadurch zu hoch aus."
        )
    if erster.get("zielmarge_erreicht") is False:
        vorbehalte.append(
            "Zum aktuell gesetzten Landpreis wird die Zielmarge nicht erreicht. Der "
            "Landwert sagt, was tragbar waere -- nicht, dass der heutige Preis es ist. "
            "Was sich dafuer aendern muesste, steht in der Rueckwaertsrechnung."
        )
    if streuung is None:
        vorbehalte.append(_OHNE_REFERENZ_HINWEIS)
    elif belastbarkeit.get("sicherheit_verkauf") in ("gering", "keine_daten"):
        vorbehalte.append(
            f"Die Marktreferenz ist als '{belastbarkeit['sicherheit_verkauf']}' eingestuft "
            "-- die Rangfolge steht und faellt mit dem angenommenen Verkaufspreis."
        )

    ergebnis.update(
        status=STATUS_EMPFOHLEN,
        empfehlung={
            "id": erster["id"],
            "bezeichnung": erster["bezeichnung"],
            "max_landwert_chf": erster["max_landwert_chf"],
            "max_landwert_chf_pro_m2": erster.get("max_landwert_chf_pro_m2"),
            "marge": erster.get("marge"),
            "zielmarge_erreicht": erster.get("zielmarge_erreicht"),
        },
        begruendung=begruendung,
        vorbehalte=vorbehalte,
        belastbarkeit=belastbarkeit,
    )
    return ergebnis

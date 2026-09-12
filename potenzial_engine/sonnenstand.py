"""Sonnenstand fuer einen Ort und einen Zeitpunkt.

Rechnet nach dem Verfahren des NOAA Solar Calculator (Astronomical Algorithms,
Jean Meeus). Fuer Verschattungsfragen im Hochbau ist das deutlich genauer als
noetig: der Fehler liegt bei Bruchteilen eines Grades, waehrend die Gebaeude-
hoehen aus dem Gebaeuderegister auf ganze Meter gerundet sind.

Warum das hier und nicht im Browser steht
-----------------------------------------
Der Zeitschieber braucht fluessige Bewegung, ein Serveraufruf je Bild waere
unbrauchbar. Trotzdem gehoert die Astronomie an eine Stelle, die sich testen
laesst. Deshalb liefert der Server den **Tagesverlauf** -- eine Stuetzstelle
alle paar Minuten -- und der Browser bewegt sich nur noch zwischen diesen
Stuetzstellen. Eine zweite Sonnenrechnung im Browser gibt es nicht.

Zeitzone
--------
Gerechnet wird durchgehend in UTC. Die Umrechnung von und nach Schweizer
Ortszeit macht ``zoneinfo`` mit der echten Sommerzeitregel -- eine von Hand
gepflegte Regel waere eine Fehlerquelle ohne Gegenwert.

Was dieses Modul NICHT tut
--------------------------
Es beurteilt keine Besonnung und keine Verschattung. Es sagt, wo die Sonne
steht. Ob ein Fenster besonnt ist, entscheidet die Geometrie in der Ansicht --
und dort auf derselben Hoehen- und Gebaeudegrundlage wie alles andere.

CLI: python -m potenzial_engine.sonnenstand 47.3876 8.0698 2026-06-21
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
    ZEITZONE_CH = ZoneInfo("Europe/Zurich")
except Exception:  # pragma: no cover -- ohne tzdata faellt alles auf UTC zurueck
    ZEITZONE_CH = timezone.utc

# Zenitwinkel, bei dem die Sonnenscheibe als auf-/untergegangen gilt.
# 90.833 Grad = 90 Grad + Halbmesser der Sonnenscheibe + mittlere Refraktion.
ZENIT_AUFGANG = 90.833

SCHRITT_MIN = 10


@dataclass
class Sonnenstand:
    """Die Sonne zu einem Zeitpunkt, von einem Ort aus gesehen."""

    zeit_lokal: str          # ISO 8601 mit Zonenangabe
    zeit_utc: str
    azimut_grad: float       # 0 = Nord, 90 = Ost, 180 = Sued, 270 = West
    hoehe_grad: float        # scheinbare Hoehe ueber dem Horizont (mit Refraktion)
    hoehe_geometrisch_grad: float
    ueber_horizont: bool
    # Einheitsvektor ZUR Sonne in einem Rechtssystem aus Ost, Nord und Hoch.
    # Die Ansicht bildet ihn auf ihre eigenen Achsen ab; damit ist die
    # Himmelsrichtung an genau einer Stelle festgelegt und pruefbar.
    ost: float
    nord: float
    hoch: float

    def als_dict(self) -> dict[str, Any]:
        return asdict(self)


def _julianisches_datum(moment: datetime) -> float:
    """Julianisches Datum eines UTC-Zeitpunkts."""
    m = moment.astimezone(timezone.utc)
    j, mo = m.year, m.month
    if mo <= 2:
        j -= 1
        mo += 12
    a = j // 100
    b = 2 - a + a // 4
    tag = (m.day + (m.hour + (m.minute + (m.second + m.microsecond / 1e6) / 60) / 60) / 24)
    return (math.floor(365.25 * (j + 4716)) + math.floor(30.6001 * (mo + 1))
            + tag + b - 1524.5)


def _sonnenparameter(jd: float) -> tuple[float, float]:
    """Deklination (Grad) und Zeitgleichung (Minuten) zum julianischen Datum."""
    jc = (jd - 2451545.0) / 36525.0

    mittlere_laenge = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    mittlere_anomalie = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    exzentrizitaet = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)

    mittelpunktsgleichung = (
        math.sin(math.radians(mittlere_anomalie)) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(math.radians(2 * mittlere_anomalie)) * (0.019993 - 0.000101 * jc)
        + math.sin(math.radians(3 * mittlere_anomalie)) * 0.000289
    )
    wahre_laenge = mittlere_laenge + mittelpunktsgleichung
    scheinbare_laenge = (wahre_laenge - 0.00569
                         - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * jc)))

    mittlere_schiefe = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    schiefe = mittlere_schiefe + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * jc))

    deklination = math.degrees(math.asin(
        math.sin(math.radians(schiefe)) * math.sin(math.radians(scheinbare_laenge))))

    y = math.tan(math.radians(schiefe / 2.0)) ** 2
    zeitgleichung = 4.0 * math.degrees(
        y * math.sin(2 * math.radians(mittlere_laenge))
        - 2 * exzentrizitaet * math.sin(math.radians(mittlere_anomalie))
        + 4 * exzentrizitaet * y * math.sin(math.radians(mittlere_anomalie))
        * math.cos(2 * math.radians(mittlere_laenge))
        - 0.5 * y * y * math.sin(4 * math.radians(mittlere_laenge))
        - 1.25 * exzentrizitaet * exzentrizitaet * math.sin(2 * math.radians(mittlere_anomalie))
    )
    return deklination, zeitgleichung


def _refraktion(hoehe_grad: float) -> float:
    """Anhebung der Sonne durch die Lufthuelle, in Grad.

    Am Horizont betraegt sie gut ein halbes Grad -- mehr als der Durchmesser
    der Sonnenscheibe. Ohne sie faellt der Sonnenuntergang mehrere Minuten zu
    frueh aus.
    """
    if hoehe_grad > 85.0:
        return 0.0
    t = math.tan(math.radians(hoehe_grad))
    if hoehe_grad > 5.0:
        bogensekunden = 58.1 / t - 0.07 / t ** 3 + 0.000086 / t ** 5
    elif hoehe_grad > -0.575:
        bogensekunden = 1735.0 + hoehe_grad * (-518.2 + hoehe_grad * (
            103.4 + hoehe_grad * (-12.79 + hoehe_grad * 0.711)))
    else:
        bogensekunden = -20.772 / t
    return bogensekunden / 3600.0


def sonnenstand(lat: float, lon: float, moment: datetime) -> Sonnenstand:
    """Sonnenstand an einem Ort zu einem Zeitpunkt.

    ``moment`` muss eine Zonenangabe tragen -- eine nackte Uhrzeit waere
    mehrdeutig, und zwischen Winter- und Sommerzeit liegt eine volle Stunde
    Schattenwurf.
    """
    if moment.tzinfo is None:
        raise ValueError("Der Zeitpunkt braucht eine Zeitzone (naiv ist mehrdeutig).")
    utc = moment.astimezone(timezone.utc)

    jd = _julianisches_datum(utc)
    deklination, zeitgleichung = _sonnenparameter(jd)

    minuten_utc = utc.hour * 60 + utc.minute + utc.second / 60.0
    wahre_sonnenzeit = (minuten_utc + zeitgleichung + 4.0 * lon) % 1440.0
    stundenwinkel = wahre_sonnenzeit / 4.0 - 180.0
    if stundenwinkel < -180.0:
        stundenwinkel += 360.0

    lat_r = math.radians(lat)
    dek_r = math.radians(deklination)
    sw_r = math.radians(stundenwinkel)

    cos_zenit = (math.sin(lat_r) * math.sin(dek_r)
                 + math.cos(lat_r) * math.cos(dek_r) * math.cos(sw_r))
    cos_zenit = max(-1.0, min(1.0, cos_zenit))
    zenit = math.degrees(math.acos(cos_zenit))
    hoehe_geometrisch = 90.0 - zenit
    hoehe = hoehe_geometrisch + _refraktion(hoehe_geometrisch)

    sin_zenit = math.sin(math.radians(zenit))
    if abs(sin_zenit) < 1e-9 or abs(math.cos(lat_r)) < 1e-9:
        azimut = 180.0     # Sonne im Zenit oder Pol: die Richtung ist entartet
    else:
        wert = ((math.sin(lat_r) * cos_zenit - math.sin(dek_r))
                / (math.cos(lat_r) * sin_zenit))
        wert = max(-1.0, min(1.0, wert))
        bogen = math.degrees(math.acos(wert))
        azimut = (bogen + 180.0) % 360.0 if stundenwinkel > 0 else (540.0 - bogen) % 360.0

    az_r = math.radians(azimut)
    h_r = math.radians(hoehe)
    return Sonnenstand(
        zeit_lokal=moment.isoformat(timespec="minutes"),
        zeit_utc=utc.isoformat(timespec="minutes"),
        azimut_grad=round(azimut, 3),
        hoehe_grad=round(hoehe, 3),
        hoehe_geometrisch_grad=round(hoehe_geometrisch, 3),
        ueber_horizont=hoehe > 0.0,
        ost=round(math.cos(h_r) * math.sin(az_r), 6),
        nord=round(math.cos(h_r) * math.cos(az_r), 6),
        hoch=round(math.sin(h_r), 6),
    )


def _minuten_zu_zeit(tag: date, minuten_utc: float) -> datetime:
    """UTC-Minuten seit Mitternacht in einen Zeitpunkt, Tagesuebertrag inklusive."""
    basis = datetime(tag.year, tag.month, tag.day, tzinfo=timezone.utc)
    return basis + timedelta(minutes=minuten_utc)


def sonnenzeiten(lat: float, lon: float, tag: date,
                 zeitzone: Any = ZEITZONE_CH) -> dict[str, Any]:
    """Aufgang, Hoechststand und Untergang fuer einen Tag.

    Deklination und Zeitgleichung werden am Mittag des Tages ausgewertet und
    einmal nachgefuehrt; der Rest des Verfahrens ist geschlossen. Der Fehler
    bleibt unter einer Minute.
    """
    mittag_utc = datetime(tag.year, tag.month, tag.day, 12, tzinfo=timezone.utc)
    _, zeitgleichung = _sonnenparameter(_julianisches_datum(mittag_utc))
    sonnenmittag_min = 720.0 - 4.0 * lon - zeitgleichung
    deklination, zeitgleichung = _sonnenparameter(
        _julianisches_datum(_minuten_zu_zeit(tag, sonnenmittag_min)))
    sonnenmittag_min = 720.0 - 4.0 * lon - zeitgleichung

    lat_r, dek_r = math.radians(lat), math.radians(deklination)
    nenner = math.cos(lat_r) * math.cos(dek_r)
    hoechststand = _minuten_zu_zeit(tag, sonnenmittag_min).astimezone(zeitzone)
    max_hoehe = round(90.0 - abs(lat - deklination), 3)

    if abs(nenner) < 1e-12:
        wert = 2.0
    else:
        wert = math.cos(math.radians(ZENIT_AUFGANG)) / nenner - math.tan(lat_r) * math.tan(dek_r)

    if wert >= 1.0:                     # Sonne bleibt unter dem Horizont
        return {"aufgang": None, "untergang": None, "polartag": False, "polarnacht": True,
                "hoechststand": hoechststand.isoformat(timespec="minutes"),
                "max_hoehe_grad": max_hoehe, "tageslaenge_min": 0}
    if wert <= -1.0:                    # Sonne bleibt ueber dem Horizont
        return {"aufgang": None, "untergang": None, "polartag": True, "polarnacht": False,
                "hoechststand": hoechststand.isoformat(timespec="minutes"),
                "max_hoehe_grad": max_hoehe, "tageslaenge_min": 1440}

    stundenwinkel = math.degrees(math.acos(max(-1.0, min(1.0, wert))))
    aufgang = _minuten_zu_zeit(tag, sonnenmittag_min - 4.0 * stundenwinkel).astimezone(zeitzone)
    untergang = _minuten_zu_zeit(tag, sonnenmittag_min + 4.0 * stundenwinkel).astimezone(zeitzone)
    return {
        "aufgang": aufgang.isoformat(timespec="minutes"),
        "untergang": untergang.isoformat(timespec="minutes"),
        "hoechststand": hoechststand.isoformat(timespec="minutes"),
        "max_hoehe_grad": max_hoehe,
        "tageslaenge_min": round(8.0 * stundenwinkel),
        "polartag": False,
        "polarnacht": False,
    }


def tagesverlauf(lat: float, lon: float, tag: date, schrittweite_min: int = SCHRITT_MIN,
                 zeitzone: Any = ZEITZONE_CH) -> list[Sonnenstand]:
    """Stuetzstellen ueber einen ganzen Tag, in Ortszeit.

    Der Tag beginnt und endet an der lokalen Mitternacht. An den beiden
    Umstellungstagen hat er dadurch 23 bzw. 25 Stunden -- das ist richtig so
    und genau der Grund, weshalb hier nicht mit festen 1440 Minuten gerechnet
    wird.
    """
    if schrittweite_min < 1 or schrittweite_min > 120:
        raise ValueError("Schrittweite zwischen 1 und 120 Minuten.")

    naechster = tag + timedelta(days=1)
    # Gezaehlt wird in UTC, angezeigt in Ortszeit. Der Grund ist die
    # Zeitumstellung: timedelta auf einer zonenbehafteten Ortszeit rechnet in
    # WANDUHRZEIT, nicht in echten Minuten. Ueber die Umstellung hinweg waeren
    # die Stuetzstellen dann ungleich weit auseinander -- und der Zeitschieber
    # liefe an zwei Tagen im Jahr um eine Stunde daneben.
    beginn = datetime(tag.year, tag.month, tag.day, tzinfo=zeitzone).astimezone(timezone.utc)
    ende = datetime(naechster.year, naechster.month, naechster.day,
                    tzinfo=zeitzone).astimezone(timezone.utc)

    verlauf: list[Sonnenstand] = []
    moment = beginn
    while moment <= ende:
        verlauf.append(sonnenstand(lat, lon, moment.astimezone(zeitzone)))
        moment += timedelta(minutes=schrittweite_min)
    return verlauf


def tagesdaten(lat: float, lon: float, tag: date, schrittweite_min: int = SCHRITT_MIN,
               zeitzone: Any = ZEITZONE_CH) -> dict[str, Any]:
    """Alles, was die Ansicht fuer einen Tag braucht, in einer Antwort."""
    verlauf = tagesverlauf(lat, lon, tag, schrittweite_min, zeitzone)
    beginn = datetime(tag.year, tag.month, tag.day, tzinfo=zeitzone)
    return {
        "datum": tag.isoformat(),
        "lat": lat,
        "lon": lon,
        "zeitzone": str(zeitzone),
        "utc_versatz_min": round(beginn.utcoffset().total_seconds() / 60) if beginn.utcoffset() else 0,
        "schrittweite_min": schrittweite_min,
        "zeiten": sonnenzeiten(lat, lon, tag, zeitzone),
        "verlauf": [s.als_dict() for s in verlauf],
        "quelle": "Berechnet nach NOAA Solar Calculator (Meeus, Astronomical Algorithms).",
    }


def _cli() -> None:  # pragma: no cover
    import sys

    if len(sys.argv) < 4:
        print("python -m potenzial_engine.sonnenstand <lat> <lon> <JJJJ-MM-TT>")
        raise SystemExit(2)
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    tag = date.fromisoformat(sys.argv[3])
    z = sonnenzeiten(lat, lon, tag)
    print(f"{tag}  {lat:.4f} / {lon:.4f}")
    print(f"  Aufgang      {z['aufgang']}")
    print(f"  Hoechststand {z['hoechststand']}  ({z['max_hoehe_grad']} Grad)")
    print(f"  Untergang    {z['untergang']}")
    print(f"  Tageslaenge  {z['tageslaenge_min'] // 60} h {z['tageslaenge_min'] % 60} min")
    for s in tagesverlauf(lat, lon, tag, 60):
        if s.ueber_horizont:
            print(f"  {s.zeit_lokal[11:16]}  Azimut {s.azimut_grad:6.1f}  Hoehe {s.hoehe_grad:5.1f}")


if __name__ == "__main__":  # pragma: no cover
    _cli()

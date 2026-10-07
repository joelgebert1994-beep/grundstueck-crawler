/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   07.10.2026 -- drei zusammenhaengende Befunde, geprueft mit den echten
   Funktionen aus dist/index.html:

   A1  Abstand je Kante: nur an Kanten ohne Wert ein Eingabefeld; ein
       manueller Wert steht als "meine Annahme"; leere Felder bleiben leer.
   A2  "in Vorbereitung, wird als naechster Block ergaenzt" ist weg.
   B   Bestand != moeglicher Baukoerper != bebaubare Flaeche:
         - der Ersatzneubau traegt nicht mehr das Gruen der bebaubaren Flaeche
         - ein Szenario "nicht moeglich" zeigt keinen neuen Baukoerper
           (Rheineck, Buhofstrasse 54: "Neubau Osten" bei "nicht moeglich")
         - die Ebene heisst nicht mehr "Geplantes Gebaeude"
   C   "Hinweis.Zonenanpassung in Erarbeitung" (Rapperswil-Jona) steht nicht
       als rechtskraeftige Ueberlagerung da.

   Aufruf: node tests/js/kanten_karte.test.js
*/

const fs = require("fs");
const path = require("path");

const quelltext = fs.readFileSync(path.join(__dirname, "..", "..", "dist", "index.html"), "utf8");
const weiningen = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "daten", "weiningen", "g1_eingaben_hogerwies.json"), "utf8"));

function extrahiere(name) {
  const start = quelltext.indexOf("function " + name + "(");
  if (start < 0) throw new Error("Funktion nicht gefunden: " + name);
  let tiefe = 0, i = quelltext.indexOf("{", start);
  for (; i < quelltext.length; i++) {
    if (quelltext[i] === "{") tiefe++;
    else if (quelltext[i] === "}") { tiefe--; if (tiefe === 0) break; }
  }
  return quelltext.slice(start, i + 1);
}
function extrahiereVar(name, ende) {
  const start = quelltext.indexOf("var " + name + " =");
  if (start < 0) throw new Error("Variable nicht gefunden: " + name);
  const e = ende || "};";
  return quelltext.slice(start, quelltext.indexOf(e, start) + e.length);
}
// Nur Schreibweise -- fuer diese Pruefungen ohne Bedeutung.
function begriff(t) { return String(t); }
function satz(t) { return String(t); }
function klartext(t) { return String(t); }
function lesbar(t) { return t; }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("fmt"));
eval(extrahiere("istZahlenwert"));
eval(extrahiere("kvRows"));
eval(extrahiereVar("WTYP"));
eval(extrahiere("wtyp"));
eval(extrahiereVar("KANTEN_ART_TEXT"));
eval(extrahiere("kantenprotokoll"));
eval(extrahiere("kantenManuellSteuerung"));
eval(extrahiere("kantenManuellHinweis"));
eval(extrahiere("kantenManuellLesen"));
eval(extrahiereVar("BAUKOERPER_FARBE"));
eval(extrahiere("sichtbareKoerper"));
eval(extrahiere("koerperName"));
eval(extrahiere("koerperTitel"));
eval(extrahiere("istHinweisFestlegung"));
eval(extrahiereVar("LAUFENDE_PLANUNG", ";"));
eval(extrahiere("festlegungStatus"));
/* eslint-enable no-eval */

let ok = 0;
const fehler = [];
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler.push(was); console.log("[FAIL] " + was); }
}

// Das Kantenprotokoll, wie G1 es fuer Weiningen liefert -- einmal ohne,
// einmal mit eigenen Abstaenden an Kante 4 und 5.
function protokoll(manuell) {
  return weiningen.kantenklassifikation.kanten.map(function (k) {
    var e = { nr: k.nr, laenge_m: k.laenge_m, art: k.art, begruendung: "", abstand_m: null, abstand_feld: null };
    if (k.art === "nachbarparzelle" || !k.relevant) { e.abstand_m = 8; e.abstand_feld = "grenzabstand_gross_m"; }
    if (k.art === "strasse" && manuell && manuell[k.nr] !== undefined) {
      e.abstand_m = manuell[k.nr]; e.abstand_feld = "manuell"; e.herkunft = "benutzerannahme";
    }
    return e;
  });
}
const m1 = { kantenklassifikation: weiningen.kantenklassifikation };

console.log("=== A1: Eingabefeld nur an Kanten ohne Wert ===");
{
  const html = kantenprotokoll({ g1_ergebnis: { kantenprotokoll: protokoll(),
    kantenzuordnung_offen: ["Kante 4: Strassenabstand nicht bestimmbar", "Kante 5: Strassenabstand nicht bestimmbar"] } }, m1);
  const felder = [...html.matchAll(/data-kante-manuell="(\d+)" value="([^"]*)"/g)].map((m) => [m[1], m[2]]);
  pruefe(JSON.stringify(felder) === JSON.stringify([["4", ""], ["5", ""]]),
    "genau zwei leere Felder: Kante 4 und 5 " + JSON.stringify(felder));
  pruefe(/id="kanten-neu"/.test(html) && !/id="kanten-weg"/.test(html),
    "Knopf 'neu rechnen', noch kein 'entfernen'");
  pruefe(/als eigene Annahme setzen/.test(html), "der Hinweis bei den offenen Kanten verweist auf die Eingabe");
  pruefe(/nicht als amtliche Analyse gespeichert/.test(html), "es steht dabei, dass der Wert eine Annahme ist");
}
{
  const html = kantenprotokoll({ g1_ergebnis: { kantenprotokoll: protokoll({ 4: 6, 5: 6 }) } }, m1);
  pruefe((html.match(/meine Annahme/g) || []).length === 2, "beide manuellen Werte tragen 'meine Annahme'");
  pruefe(/data-kante-manuell="4" value="6"/.test(html), "das Feld zeigt den gesetzten Wert zum Ändern");
  pruefe(/id="kanten-weg"/.test(html), "eigene Abstände lassen sich wieder entfernen");
  const nachbarFelder = [...html.matchAll(/data-kante-manuell="(\d+)"/g)].map((m) => m[1]);
  pruefe(nachbarFelder.every((n) => n === "4" || n === "5"), "Nachbarkanten mit amtlichem Wert bekommen kein Feld");
}
{
  const p = protokoll();
  p[0].manuell_nicht_uebernommen = 1;
  const html = kantenprotokoll({ g1_ergebnis: { kantenprotokoll: p } }, m1);
  pruefe(/Eigener Wert 1 m nicht übernommen/.test(html), "ein nicht übernommener Wert wird angezeigt");
}
{
  const h = kantenManuellHinweis({ kantenabstaende_manuell: { angewendet: { 4: 6, 5: 6 } } });
  pruefe(/Gerechnet mit eigenen Abständen/.test(h) && /Kante 4: 6\.0 m · Kante 5: 6\.0 m/.test(h) && /kein amtlicher Wert/.test(h),
    "Kopfhinweis auf jedem Reiter: Kanten, Werte, kein amtlicher Wert");
  pruefe(kantenManuellHinweis({}) === "" && kantenManuellHinweis({ kantenabstaende_manuell: { angewendet: {} } }) === "",
    "ohne eigene Werte kein Hinweis");
}
{
  global.document = { querySelectorAll: () => [
    { value: "6", dataset: { kanteManuell: "4" } },
    { value: "", dataset: { kanteManuell: "5" } },
    { value: "5,5", dataset: { kanteManuell: "7" } }] };
  let r = kantenManuellLesen();
  pruefe(JSON.stringify(r.werte) === '{"4":6,"7":5.5}' && !r.fehler,
    "leere Felder gehen nicht mit, Dezimalkomma wird gelesen " + JSON.stringify(r.werte));
  global.document = { querySelectorAll: () => [{ value: "0", dataset: { kanteManuell: "4" } }] };
  r = kantenManuellLesen();
  pruefe(!!r.fehler, "0 m wird abgelehnt, nicht korrigiert");
}

console.log("\n=== A2: kein 'in Vorbereitung' mehr ===");
{
  // Nur der Code, nicht die Kommentare -- einer erklaert, was vorher dastand.
  const sz = extrahiere("secSzenarien").replace(/^\s*\/\/.*$/gm, "");
  pruefe(sz.indexOf("in Vorbereitung") < 0 && !/n(ä|\\u00e4)chster fachlicher Block/.test(sz),
    "der falsche Text ist weg");
  pruefe(/Geometrie des Grundst(ü|\\u00fc)cks eindeutig/.test(sz), "stattdessen: rechnet, sobald die Geometrie eindeutig ist");
}

console.log("\n=== B: Bestand ≠ möglicher Baukörper ≠ bebaubare Fläche ===");
{
  const stil = quelltext.slice(quelltext.indexOf("var STIL = {"), quelltext.indexOf("};", quelltext.indexOf("var STIL = {")));
  const baubereichFarbe = /baubereich:\{ color: "(#[0-9a-f]+)"/.exec(stil)[1];
  pruefe(BAUKOERPER_FARBE.ersatzneubau !== baubereichFarbe,
    "der Ersatzneubau hat nicht mehr die Farbe der bebaubaren Fläche (" + baubereichFarbe + ")");
  pruefe(BAUKOERPER_FARBE.bestand !== BAUKOERPER_FARBE.ersatzneubau && BAUKOERPER_FARBE.bestand !== baubereichFarbe,
    "Bestand hat eine eigene Farbe");
  pruefe(/baubereich:\{[^}]*dashArray/.test(stil), "die bebaubare Fläche ist gestrichelt (errechnet)");
  pruefe(quelltext.indexOf(">Geplantes Geb&auml;ude<") < 0 && /M&ouml;glicher Baukörper \(Szenario\)/.test(quelltext),
    "die Ebene heisst 'Möglicher Baukörper (Szenario)', nicht 'Geplantes Gebäude'");
  pruefe(/Heutige Geb&auml;ude \(vereinfacht\)/.test(quelltext), "der Bestandsumriss ist als vereinfacht bezeichnet");

  const bestandPlusNeubau = { machbarkeit: "nicht_moeglich", baukoerper: [
    { name: "Neubau Osten", art: "neubau" }, { name: "Bestand (bleibt)", art: "bestand" }] };
  const sicht = sichtbareKoerper(bestandPlusNeubau);
  pruefe(sicht.length === 1 && sicht[0].art === "bestand",
    "Bestand + Neubau 'nicht möglich': kein 'Neubau Osten', nur der Bestand");
  const moeglich = { machbarkeit: "eingeschraenkt_moeglich", baukoerper: bestandPlusNeubau.baukoerper };
  pruefe(sichtbareKoerper(moeglich).length === 2, "ein mögliches Szenario zeigt weiter beide Körper");
  pruefe(koerperTitel({ name: "Baubereich (moegliche Lage)", art: "ersatzneubau" }) ===
         "Ersatzneubau (mögliche Lage im Baubereich)", "der Ersatzneubau heisst nicht 'Baubereich'");
  pruefe(koerperTitel({ name: "Neubau Osten", art: "neubau" }) === "Neubau Osten", "andere Namen bleiben");
  const zeichnen = extrahiere("zeichneSzenario");
  pruefe(zeichnen.indexOf("sichtbareKoerper(s)") > 0 && /sichtbareKoerper\(sz\)/.test(quelltext),
    "Karte und 3D zeichnen dieselben sichtbaren Körper");
}

console.log("\n=== C: Hinweis auf laufende Planung ist keine geltende Vorschrift ===");
{
  const jona = { typ_kommunal_bezeichnung: "Hinweis.Zonenanpassung in Erarbeitung", ist_rechtskraeftig: true };
  pruefe(istHinweisFestlegung(jona), "als Hinweis erkannt");
  pruefe(festlegungStatus(jona) === "Hinweis auf laufende Planung — gilt noch nicht, nicht in der Berechnung",
    "Status: laufende Planung, gilt noch nicht");
  pruefe(festlegungStatus({ typ_kommunal_bezeichnung: "Kulturobjekt Gebäude" }) === "überlagert die Parzelle · rechtskräftig",
    "eine echte Überlagerung bleibt 'rechtskräftig'");
  pruefe(festlegungStatus({ typ_kommunal_bezeichnung: "Hinweis.Verkehrsflaeche iB" }) === "Hinweis im ÖREB-Kataster — keine Vorschrift",
    "andere Hinweise: keine Vorschrift");
}

console.log("------------------------------------------------------------------");
if (fehler.length) { console.log("KANTEN-KARTE: " + fehler.length + " Abweichung(en)"); process.exit(1); }
console.log("ALLE KANTEN-KARTE-TESTS BESTANDEN (" + ok + " OK)");

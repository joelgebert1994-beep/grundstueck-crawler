/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Wirtschaftlichkeit: Marktannahmen direkt im Reiter (09.10.2026).

   Rosenweg 4, Buchs AG: der Reiter bestand aus fuenf Kacheln "nicht
   berechenbar", die Preise liessen sich nur im Reiter Markt setzen. Jetzt
   stehen Verkaufspreis, Bodenpreis und Mietzins als Felder im Reiter -- auf
   DENSELBEN Schluessel in wEingaben wie im Reiter Markt. Geprueft werden die
   drei Lagen:
     A  es fehlen Marktannahmen       -> welche und wofuer, keine Strichkacheln
     B  die Grundlage fehlt           -> nichts im Ergebnis, auch mit Preisen
     C  es wird gerechnet             -> Kacheln und Herkunft jeder Annahme

   Aufruf: node tests/js/wirtschaft_eingaben.test.js
*/

const fs = require("fs");
const path = require("path");

const quelltext = fs.readFileSync(path.join(__dirname, "..", "..", "dist", "index.html"), "utf8");
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
  return quelltext.slice(start, quelltext.indexOf(ende, start) + ende.length);
}

// Umgebung: was die Funktionen lesen, hier gesteuert.
var wErgebnis = null, ergebnisAktuell = {}, _wAktiv = null;
var wEingaben = { verkauf_chf_pro_m2: null, miete_chf_pro_m2_jahr: null, bodenpreis_chf_pro_m2: null,
                  zielmarge: 0.15, land_ansatz: "kauf" };
var STAND = { rechenbar: true };
function rechenstand() { return STAND; }
var LAGE = {};
function wLage(g) { return LAGE[g] || null; }
function reiterLink(r, t) { return '<a data-reiter="' + r + '">' + t + "</a>"; }
function satz(t) { return String(t); }
function rueckwaertsBlock() { return ""; }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("chf"));
eval(extrahiere("proz"));
eval(extrahiere("fmt"));
eval(extrahiereVar("HERKUNFT_KURZ", "};"));
eval(extrahiereVar("WA_GROESSEN", "];"));
eval(extrahiere("nurReferenz"));
eval(extrahiere("wAktivesSzenario"));
eval(extrahiere("wSzenarioErgebnis"));
eval(extrahiere("waMarktwert"));
eval(extrahiere("waInRechnung"));
eval(extrahiere("wFehlendeEingaben"));
eval(extrahiere("wAnnahmenStreifen"));
eval(extrahiere("ergebnisBlock"));
eval(extrahiere("wErgebnisBereich"));

let ok = 0, fehler = 0;
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler++; console.log("[FEHL] " + was); }
}
function text(html) { return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " "); }
function zeile(html, label) {
  const t = text(html);
  const i = t.indexOf(label);
  return i < 0 ? "" : t.slice(i, i + 190);
}

// Antwort der Rechnung -- Form wie /api/entwicklung (Buchs AG, 09.10.2026).
function szenarioErgebnis(o) {
  o = o || {};
  return {
    bezeichnung: o.bezeichnung || "Ersatzneubau",
    verkauf: o.verkauf === undefined ? { erloes_chf: null, grund: "Kein Verkaufspreis je m2 gesetzt." } : o.verkauf,
    miete: o.miete || { jahresertrag_chf: null },
    land: o.land || { wert_chf: null, herkunft: "nicht_bestimmbar",
                      bodenpreis: { wert: null, herkunft: "nicht_bestimmbar", systemvorschlag: null,
                                    benutzerannahme: null, anzahl_referenzen: 1, referenzspanne: [745, 745] } },
    ergebnis: Object.assign({ verkaufserloes_chf: null, gesamtinvestition_chf: null, gewinn_chf: null,
                              marge: null, zielmarge: 0.15 }, o.ergebnis || {}),
    residualwert: o.residualwert || { status: "nicht_bestimmbar" },
    offene_punkte: o.offene_punkte || []
  };
}
function setzeErgebnis(szen) {
  wErgebnis = { szenarien: { ersatzneubau: szen }, vergleich: [{ id: "ersatzneubau" }] };
}

// ---------------------------------------------------------------- A
console.log("=== A: es fehlen Marktannahmen (Buchs ohne Preise) ===");
LAGE = { boden: { anzahl: 1, systemvorschlag: null, mindestanforderung: { min_objekte: 3 } } };
setzeErgebnis(szenarioErgebnis());
let streifen = wAnnahmenStreifen();
pruefe(/id="wa-verkauf"/.test(streifen) && /id="wa-boden"/.test(streifen) && /id="wa-miete"/.test(streifen),
       "die drei Eingabefelder stehen im Reiter");
pruefe(/data-wa="verkauf_chf_pro_m2"/.test(streifen) && /data-markt="w-verkauf"/.test(streifen),
       "Feld zeigt auf denselben Schlüssel wie im Reiter Markt");
pruefe(zeile(streifen, "Verkaufspreis").indexOf("fehlt") >= 0, "Verkaufspreis: fehlt");
pruefe(zeile(streifen, "Bodenpreis").indexOf("fehlt") >= 0 &&
       zeile(streifen, "Bodenpreis").indexOf("1 von 3 nötigen Referenzen") >= 0,
       "Bodenpreis: fehlt, kein Vorschlag (1 von 3 Referenzen)");
pruefe(zeile(streifen, "Mietzins").indexOf("optional") >= 0, "Mietzins: optional (nur Bruttorendite)");
pruefe(streifen.indexOf("übernehmen") < 0, "ohne Systemvorschlag kein Übernehmen-Knopf");
let bereich = wErgebnisBereich();
pruefe(text(bereich).indexOf("Es fehlen Marktannahmen") >= 0, "Ergebnis: 'Es fehlen Marktannahmen'");
pruefe(text(bereich).indexOf("Verkaufspreis") >= 0 && text(bereich).indexOf("Bodenpreis") >= 0 &&
       text(bereich).indexOf("Mietzins") < 0, "genannt: Verkaufspreis und Bodenpreis, nicht der Mietzins");
pruefe(bereich.indexOf("kzeile") < 0 && text(bereich).indexOf("nicht berechenbar") < 0,
       "keine Kacheln voller 'nicht berechenbar'");

// ------------------------------------------------- Systemvorschlag
console.log("\n=== Systemvorschlag: angezeigt, erst nach Übernahme gerechnet ===");
const bodenMitVorschlag = { wert: 745, herkunft: "systemannahme", systemvorschlag: 745,
  benutzerannahme: null, anzahl_referenzen: 3, referenzspanne: [700, 800],
  referenzen: [{ wert: 700 }, { wert: 745 }, { wert: 800 }] };
const vorher = JSON.stringify(bodenMitVorschlag);
setzeErgebnis(szenarioErgebnis({ land: { wert_chf: null, herkunft: "nicht_bestimmbar", bodenpreis: bodenMitVorschlag } }));
streifen = wAnnahmenStreifen();
pruefe(zeile(streifen, "Bodenpreis").indexOf("Vorschlag nicht übernommen") >= 0,
       "Bodenpreis: 'Vorschlag nicht übernommen' -- nicht 'gerechnet'");
pruefe(/data-wa-uebernehmen="wa-boden" data-wert="745"/.test(streifen), "Übernehmen-Knopf mit genau 745");
pruefe(zeile(streifen, "Bodenpreis").indexOf("gerechnet mit") < 0, "kein 'gerechnet mit' vor der Übernahme");
pruefe(JSON.stringify(bodenMitVorschlag) === vorher, "Referenzen und Vorschlag bleiben unverändert");

wEingaben.bodenpreis_chf_pro_m2 = 745;
setzeErgebnis(szenarioErgebnis({ land: { wert_chf: 446173, herkunft: "benutzerannahme",
  bodenpreis: Object.assign({}, bodenMitVorschlag, { benutzerannahme: 745, wert: 745, herkunft: "benutzerannahme" }) } }));
streifen = wAnnahmenStreifen();
pruefe(zeile(streifen, "Bodenpreis").indexOf("meine Annahme") >= 0 &&
       zeile(streifen, "Bodenpreis").indexOf("gerechnet mit 745") >= 0,
       "nach Übernahme und Rechnung: 'meine Annahme', gerechnet mit 745");
pruefe(streifen.indexOf('data-wa-uebernehmen="wa-boden"') < 0, "übernommen: kein Knopf mehr");

// ------------------------------------------------- manuell / vorgemerkt
console.log("\n=== Manuell angepasst: vorgemerkt, bis die Rechnung ihn verwendet ===");
wEingaben.bodenpreis_chf_pro_m2 = 900;
streifen = wAnnahmenStreifen();
pruefe(zeile(streifen, "Bodenpreis").indexOf("vorgemerkt") >= 0,
       "900 eingetragen, Rechnung noch mit 745: 'vorgemerkt'");
pruefe(/id="wa-boden"[^>]*value="900"/.test(streifen), "das Feld zeigt die Eingabe (900)");
pruefe(/data-wa-uebernehmen="wa-boden" data-wert="745"/.test(streifen), "zurück zum Vorschlag möglich");

// ------------------------------------------------- C: Rechnung
console.log("\n=== C: es wird gerechnet -- Kacheln und Herkunft ===");
wEingaben.verkauf_chf_pro_m2 = 9000;
LAGE = {};
setzeErgebnis(szenarioErgebnis({
  verkauf: { erloes_chf: 1350000, preis: { wert: 9000, herkunft: "benutzerannahme", benutzerannahme: 9000, systemvorschlag: null } },
  land: { wert_chf: 539001, herkunft: "benutzerannahme",
          bodenpreis: { wert: 900, herkunft: "benutzerannahme", benutzerannahme: 900, systemvorschlag: 745, anzahl_referenzen: 3 } },
  ergebnis: { verkaufserloes_chf: 1350000, gesamtinvestition_chf: 1475976, gewinn_chf: -125976, marge: -0.0933 },
  residualwert: { status: "berechnet", max_landwert_chf: 150644, max_landwert_chf_pro_m2: 252 }
}));
streifen = wAnnahmenStreifen();
bereich = wErgebnisBereich();
pruefe(zeile(streifen, "Verkaufspreis").indexOf("meine Annahme") >= 0 &&
       zeile(streifen, "Verkaufspreis").indexOf("gerechnet mit 9") >= 0, "Verkaufspreis: meine Annahme, gerechnet");
pruefe(bereich.indexOf("kzeile") >= 0 && text(bereich).indexOf("Es fehlen") < 0,
       "alle Pflichtwerte gesetzt: Kacheln, kein Fehlt-Hinweis");
pruefe(text(bereich).indexOf("150") >= 0 && text(bereich).indexOf("Max. tragbarer Landwert") >= 0,
       "tragbarer Landwert wird gezeigt");

console.log("\n=== Systemannahme beim Verkaufspreis: gerechnet und so benannt ===");
wEingaben.verkauf_chf_pro_m2 = null;
setzeErgebnis(szenarioErgebnis({
  verkauf: { erloes_chf: 1300000, preis: { wert: 8700, herkunft: "systemannahme", benutzerannahme: null, systemvorschlag: 8700, anzahl_referenzen: 5 } },
  ergebnis: { verkaufserloes_chf: 1300000 }, residualwert: { status: "berechnet", max_landwert_chf: 100000 }
}));
streifen = wAnnahmenStreifen();
pruefe(zeile(streifen, "Verkaufspreis").indexOf("Systemannahme") >= 0 &&
       zeile(streifen, "Verkaufspreis").indexOf("gerechnet mit 8") >= 0,
       "Verkaufspreis aus Referenzen: 'Systemannahme', gerechnet mit 8'700");
bereich = wErgebnisBereich();
pruefe(text(bereich).indexOf("Bodenpreis") >= 0 && bereich.indexOf("kzeile") >= 0,
       "Bodenpreis fehlt: Hinweis UND die Kacheln, die schon eine Zahl haben");

// ------------------------------------------------- B: keine Grundlage
console.log("\n=== B: Grundlage nicht bestimmbar -- Preise ändern daran nichts ===");
STAND = { rechenbar: false, art: "kein_szenario" };
wEingaben.verkauf_chf_pro_m2 = 9000; wEingaben.bodenpreis_chf_pro_m2 = 900;
wErgebnis = { status: "nicht_bestimmbar", szenarien: {} };
bereich = wErgebnisBereich();
streifen = wAnnahmenStreifen();
pruefe(bereich === "", "kein Ergebnisbereich, keine Kachel -- das Band oben erklärt den Grund");
pruefe(zeile(streifen, "Verkaufspreis").indexOf("vorgemerkt") >= 0 &&
       zeile(streifen, "Bodenpreis").indexOf("vorgemerkt") >= 0,
       "eingegebene Preise: 'vorgemerkt', nicht 'gerechnet'");
pruefe(streifen.indexOf("gerechnet mit") < 0, "nirgends 'gerechnet mit'");

// ------------------------------------------------- Quelltext
console.log("\n=== Verdrahtung ===");
const verdr = extrahiere("verdrahteWirtschaft");
pruefe(verdr.indexOf('"#sec-wirtschaft input:not(.wa-feld)') >= 0,
       "die neuen Felder laufen nicht durch die allgemeine Verdrahtung (die läse das Marktfeld)");
pruefe(/gegen\.value = roh/.test(verdr) && /wEingaben\[schluessel\] =/.test(verdr) && /wAngestossen\(\)/.test(verdr),
       "Eingabe schreibt wEingaben, gleicht das Marktfeld ab und rechnet neu");
const rechne = extrahiere("wRechne");
pruefe(/wNochmal = true/.test(rechne) && /if \(wNochmal\)/.test(rechne),
       "eine Änderung während der Rechnung wird danach gerechnet, nicht verworfen");
const neu = extrahiere("wZeichneNeu");
pruefe(neu.indexOf('setze("w-ergebnis", wErgebnisBereich())') >= 0 && neu.indexOf('setze("w-annahmen", wAnnahmenStreifen())') >= 0,
       "nach der Rechnung werden Streifen und Ergebnis neu gezeichnet");

console.log("\n" + (fehler ? fehler + " FEHLER" : "ALLE WIRTSCHAFT-EINGABEN-JS-TESTS BESTANDEN (" + ok + " OK)"));
process.exit(fehler ? 1 : 0);

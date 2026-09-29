/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js fuer die
   Begruendung (direktes eval() im Strict-Modus bekommt einen eigenen
   Gueltigkeitsbereich).

   Regressionstest fuer "Markt MVP 1 -- Frontend absichern" (dist/index.html).

   Entscheidung 2 (dieser Teil): wEingaben (Verkaufspreis-, Miet- und
   Bodenpreis-Annahme, Wohnungsmix, ...) ist eine globale Variable, die
   bisher NIE auf eine neue Adresse zurueckgesetzt wurde. starteAnalyse()
   setzt jetzt bei einem echten Adresswechsel (nicht bei "neu rechnen" fuer
   dieselbe Adresse) wEingaben = wEingabenStandard() und wBeruehrt = {}.
   Bereits gespeicherte Varianten bleiben unberuehrt: sie laden ihre
   eigenen Werte weiterhin ueber uebernehmeVariantenEingaben() beim
   Oeffnen (unveraendert).

   Aufruf: node tests/js/markt_mvp1.test.js
*/

const fs = require("fs");
const path = require("path");

const DIST = path.join(__dirname, "..", "..", "dist", "index.html");
const quelltext = fs.readFileSync(DIST, "utf8");

function extrahiere(name) {
  const marker = "function " + name + "(";
  const start = quelltext.indexOf(marker);
  if (start < 0) throw new Error("Funktion nicht gefunden in dist/index.html: " + name);
  const klammerStart = quelltext.indexOf("{", start);
  let tiefe = 0, i = klammerStart;
  for (; i < quelltext.length; i++) {
    if (quelltext[i] === "{") tiefe++;
    else if (quelltext[i] === "}") { tiefe--; if (tiefe === 0) break; }
  }
  if (tiefe !== 0) throw new Error("Klammern nicht ausgeglichen fuer: " + name);
  return quelltext.slice(start, i + 1);
}

let wEingaben = null;
let wBeruehrt = {};

eval(extrahiere("wEingabenStandard")); // eslint-disable-line no-eval -- Testabsicht: echten Code pruefen
eval(extrahiere("uebernehmeVariantenEingaben")); // eslint-disable-line no-eval

wEingaben = wEingabenStandard();

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}

// ---------------------------------------------------------------------
// A/B/C: Analyse A setzt eigene Annahmen, Analyse B (Reset) darf sie
// nicht mehr sehen. Der Reset selbst ist wEingaben = wEingabenStandard() --
// exakt das, was starteAnalyse() bei einem Adresswechsel jetzt tut (siehe
// Quelltext-Zusicherung weiter unten).
// ---------------------------------------------------------------------
wEingaben.verkauf_chf_pro_m2 = 9800;   // A: eigene Verkaufspreisannahme
wEingaben.miete_chf_pro_m2_jahr = 270; // A: eigene Mietannahme
wEingaben.bodenpreis_chf_pro_m2 = 1050; // A: eigene Bodenpreisannahme
wEingaben.wohnungsmix[0].anteil = 0.99; // A: auch der Wohnungsmix ist beruehrt
wBeruehrt.verkauf_chf_pro_m2 = true;
wBeruehrt.miete_chf_pro_m2_jahr = true;
wBeruehrt.bodenpreis_chf_pro_m2 = true;
pruefe(wEingaben.verkauf_chf_pro_m2 === 9800 && wEingaben.miete_chf_pro_m2_jahr === 270
       && wEingaben.bodenpreis_chf_pro_m2 === 1050,
  "Analyse A: alle drei eigenen Annahmen sind gesetzt");

// Der Reset, wie starteAnalyse() ihn bei einem echten Adresswechsel ausfuehrt.
wEingaben = wEingabenStandard();
wBeruehrt = {};

pruefe(wEingaben.verkauf_chf_pro_m2 === null,
  "A: Verkaufspreis von A ist nach dem Reset nicht mehr vorhanden");
pruefe(wEingaben.miete_chf_pro_m2_jahr === null,
  "B: Mietannahme von A ist nach dem Reset leer");
pruefe(wEingaben.bodenpreis_chf_pro_m2 === null,
  "C: Bodenpreis von A ist nach dem Reset leer");
pruefe(wEingaben.wohnungsmix[0].anteil === 0.20,
  "auch der veraenderte Wohnungsmix ist wieder der Standard (kein geteiltes Array)");
pruefe(Object.keys(wBeruehrt).length === 0,
  "wBeruehrt ist ebenfalls zurueckgesetzt -- sonst gaelte eine laengst geloeschte Eingabe noch als 'beruehrt'");

// ---------------------------------------------------------------------
// D: Variante A hat eigene, gespeicherte Werte. Nach dem Reset fuer
// Analyse B sind die globalen Eingaben leer (s.o.). Wird Variante A
// SPAETER wieder geoeffnet, muessen ihre eigenen Werte trotzdem da sein --
// uebernehmeVariantenEingaben() ist unveraendert und unabhaengig vom
// Analyse-Reset.
// ---------------------------------------------------------------------
const varianteAEingaben = {
  verkauf_chf_pro_m2: 9800, miete_chf_pro_m2_jahr: 270, bodenpreis_chf_pro_m2: 1050,
  zielmarge: 0.18, land_ansatz: "kauf", verkauf_basis: "nwf", restflaeche_verteilen: false,
};
uebernehmeVariantenEingaben(varianteAEingaben);
pruefe(wEingaben.verkauf_chf_pro_m2 === 9800 && wEingaben.miete_chf_pro_m2_jahr === 270
       && wEingaben.bodenpreis_chf_pro_m2 === 1050,
  "D: Variante A wieder geoeffnet -- ihre gespeicherten Werte sind da, obwohl die globalen Eingaben zwischenzeitlich leer waren");

// Und ein erneuter Analyse-Reset (z.B. eine dritte Adresse C) wirft auch
// die geladene Variante wieder weg -- keine kumulierten Altwerte.
wEingaben = wEingabenStandard();
pruefe(wEingaben.bodenpreis_chf_pro_m2 === null,
  "nach einem weiteren Reset ist auch der aus der Variante geladene Bodenpreis wieder leer");

// ---------------------------------------------------------------------
// Quelltext-Zusicherungen: der Reset sitzt tatsaechlich in starteAnalyse(),
// gegen einen echten Adresswechsel gewacht (nicht bei "neu rechnen" fuer
// dieselbe Adresse -- sonst wirft ein Klick auf "neu rechnen" versehentlich
// die gerade eingetippten Marktannahmen fuer DIESELBE Adresse weg).
// ---------------------------------------------------------------------
{
  const fn = extrahiere("starteAnalyse");
  pruefe(/if\s*\(gewaehlteAdresse !== wEingabenAdresse\)/.test(fn),
    "der Reset ist an einen echten Adresswechsel gebunden, nicht an jeden Analyse-Start");
  const block = fn.slice(fn.indexOf("if (gewaehlteAdresse !== wEingabenAdresse)"));
  pruefe(/wEingaben = wEingabenStandard\(\);/.test(block),
    "wEingaben wird beim Adresswechsel zurueckgesetzt");
  pruefe(/wBeruehrt = \{\};/.test(block),
    "wBeruehrt wird beim Adresswechsel mit zurueckgesetzt");
  pruefe(/wErgebnis = null;/.test(block),
    "wErgebnis wird im selben Block zurueckgesetzt (siehe markt_plz.test.js)");
}

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " MARKT-MVP1-Pruefungen (Reset) FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE MARKT-MVP1-TESTS (Reset) BESTANDEN (" + ok + " OK)");

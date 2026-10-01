/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Heizung & Energie laut GWR (dist/index.html): Uebersetzung nach dem
   amtlichen Merkmalskatalog des BFS (Version 4.3), Code daneben, Datum und
   Quelle der Angabe sichtbar, ein unbekannter Code wird nicht geraten.

   Daten: der am 30.09.2026 eingefrorene echte GWR-Datensatz von
   Hogerwiesstrasse 1, 8104 Weiningen ZH (EGID 123952).

   Aufruf: node tests/js/heizung.test.js
*/

const fs = require("fs");
const path = require("path");

const DIST = path.join(__dirname, "..", "..", "dist", "index.html");
const quelltext = fs.readFileSync(DIST, "utf8");
const gwr = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "daten", "adresse", "gwr_123952_0.json"), "utf8")).feature.properties;

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
function extrahiereVar(name) {
  const start = quelltext.indexOf("var " + name + " =");
  if (start < 0) throw new Error("Variable nicht gefunden: " + name);
  return quelltext.slice(start, quelltext.indexOf("};", start) + 2);
}
function leer(v) { return v === null || v === undefined || v === "" || (typeof v === "number" && isNaN(v)); }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiereVar("GWR_WAERMEERZEUGER_HEIZUNG"));
eval(extrahiereVar("GWR_WAERMEERZEUGER_WARMWASSER"));
eval(extrahiereVar("GWR_ENERGIEQUELLE"));
eval(extrahiereVar("GWR_INFORMATIONSQUELLE"));
eval(extrahiere("gwrCode"));
eval(extrahiere("waermeText"));
eval(extrahiere("angabeAlterJahre"));
/* eslint-enable no-eval */

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}

const heizung = { waermeerzeuger_code: gwr.gwaerzh1, energiequelle_code: gwr.genh1,
                  informationsquelle_code: gwr.gwaersceh1, aktualisiert_am: gwr.gwaerdath1 };
const warmwasser = { waermeerzeuger_code: gwr.gwaerzw1, energiequelle_code: gwr.genw1,
                     informationsquelle_code: gwr.gwaerscew1, aktualisiert_am: gwr.gwaerdatw1 };

const h = waermeText(heizung, GWR_WAERMEERZEUGER_HEIZUNG);
pruefe(h.indexOf("Heizkessel (generisch) für ein Gebäude (Code 7430)") === 0,
  "Wärmeerzeuger nach Katalog übersetzt, Code daneben: " + h);
pruefe(h.indexOf("Heizöl (Code 7530)") > 0, "Energieträger Heizöl mit Code");
pruefe(h.indexOf("laut GWR") > 0 && h.indexOf("Angabe vom 29.11.2001") > 0,
  "Herkunft und Datum der Angabe stehen dabei");
pruefe(h.indexOf("Quelle: Volkszählung 2000") > 0, "Informationsquelle übersetzt (Code 860)");
pruefe(angabeAlterJahre(heizung) > 24, "das Alter der Angabe wird erkannt (über 24 Jahre)");

const w = waermeText(warmwasser, GWR_WAERMEERZEUGER_WARMWASSER);
pruefe(w.indexOf("Zentraler Elektroboiler (Code 7650)") === 0 && w.indexOf("Elektrizität (Code 7560)") > 0,
  "Warmwasser: Elektroboiler, Elektrizität");

const unbekannt = waermeText({ waermeerzeuger_code: 7999, energiequelle_code: null }, GWR_WAERMEERZEUGER_HEIZUNG);
pruefe(unbekannt.indexOf("Code 7999 — nicht übersetzt") === 0, "ein unbekannter Code wird nicht geraten");
pruefe(waermeText(null, GWR_WAERMEERZEUGER_HEIZUNG) === null, "ohne Angabe keine Zeile");

console.log("------------------------------------------------------------------");
if (fehler.length) { console.log("HEIZUNG: " + fehler.length + " Abweichung(en)"); process.exit(1); }
console.log("ALLE HEIZUNGS-TESTS BESTANDEN (" + ok + " OK)");

/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   A3 (09.10.2026): eine Reglementkennzahl, die ihrem eigenen Beleg
   widerspricht, wird nicht gerechnet und nicht korrigiert. Die Kachel muss
   den ausgelesenen Wert, den Grund und den Originaltext trotzdem zeigen.

   Aufruf: node tests/js/reglement_plausibilitaet.test.js
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
// Nur Schreibweise -- fuer diese Pruefung ohne Bedeutung.
function satz(t) { return String(t); }
function begriff(t) { return String(t); }
function wtyp(art, zusatz) { return art + (zusatz ? " " + zusatz : ""); }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("plausibilitaetHinweis"));
eval(extrahiere("kennzahlBlock"));

let ok = 0, fehler = 0;
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler++; console.log("[FEHL] " + was); }
}

const auffaellig = {
  wert: null, wert_extrahiert: 70, einheit: "%", zitat: "Ausnützungsziffer max. 70 %",
  artikel_referenz: "Art. 7", quelle_dokument: "Bau- und Zonenordnung", confidence: "hoch",
  bedingungen: [], unklarheit: null,
  plausibilitaet: { status: "pruefbeduerftig", in_rechnung: false,
    befunde: [{ art: "prozent_nicht_umgerechnet", hinweis: "Der Originaltext nennt 70 %, der Wert ist 70 statt 0.7." }] }
};
const html = kennzahlBlock("Ausnützungsziffer (AZ)", auffaellig, "");
pruefe(html.indexOf("prüfbedürftig – nicht in der Rechnung") >= 0, "Kachel: prüfbedürftig, nicht in der Rechnung");
pruefe(html.indexOf("Ausgelesen: 70") >= 0 && html.indexOf("Einheit „%“") >= 0, "ausgelesener Wert und Einheit sichtbar");
pruefe(html.indexOf("statt 0.7") >= 0, "der Grund steht da");
pruefe(html.indexOf("Ausnützungsziffer max. 70 %") >= 0 && html.indexOf("Art. 7") >= 0,
       "Originaltext und Artikel bleiben sichtbar");
pruefe(html.indexOf('class="bigval na"') >= 0, "keine Zahl als Ergebnis in der Kachel");

const normal = { wert: 0.3, einheit: "Prozent", zitat: "Ausnützungsziffer max. 30 %", artikel_referenz: "Art. 22",
                 confidence: "hoch", bedingungen: [] };
const h2 = kennzahlBlock("Ausnützungsziffer (AZ)", normal, "");
pruefe(h2.indexOf("Prüfbedürftig") < 0 && h2.indexOf('<div class="bigval">0.3') >= 0,
       "Weiningen 0.3: unverändert, ohne Prüfhinweis");

console.log("\n" + (fehler ? fehler + " FEHLER" : "ALLE OK (" + ok + ")"));
process.exit(fehler ? 1 : 0);

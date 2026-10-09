/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Buchs AG, Rosenweg 4 (09.10.2026): "Grundstueck & Bestand" zeigte ein
   Gebaeude mit 9 m2 ohne Wohnnutzung, die Uebersicht 98 m2 und drei
   Gebaeude, die Szenarien 135 m2 belegt und 164 m2 "verbleibend". Jede Zahl
   muss sagen, was sie ist: Gebaeude der Adresse, Grundflaeche aller
   Gebaeude, Geschossflaeche der Wohngebaeude (Naeherung), rechnerische
   Reserve (Naeherung).

   Aufruf: node tests/js/bestand_konsistenz.test.js
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
function lesbar(t) { return String(t); }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("fmt"));
eval(extrahiere("gebaeudeAnDerAdresseHinweis"));
eval(extrahiere("nichtEingerechnetHinweis"));

let ok = 0, fehler = 0;
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler++; console.log("[FEHL] " + was); }
}

const bestand = { gebaeude: [{ egid: "263070701" }, { egid: "524242" }, { egid: "263024777" }] };
let h = gebaeudeAnDerAdresseHinweis({ found: true, zuordnung: "egid_der_adresse" }, bestand);
pruefe(h.indexOf("Eines von 3 Gebäuden auf der Parzelle") >= 0 && h.indexOf("das Gebäude der Adresse") >= 0,
       "Grundstück & Bestand: sagt, dass es eines von drei Gebäuden ist");
pruefe(h.indexOf("Nicht über die Adresse zugeordnet") < 0, "über die Adresse zugeordnet: keine Warnung");
h = gebaeudeAnDerAdresseHinweis({ found: true, zuordnung: "erster_treffer_im_umkreis" }, { gebaeude: [{}] });
pruefe(h.indexOf("Nicht über die Adresse zugeordnet") >= 0, "erster Treffer im Umkreis: gekennzeichnet");

const ab = { wert_m2: 135.4, nicht_eingerechnet: [
  { egid: "263070701", flaeche_m2: 20.8, grund: "ohne Wohnnutzung" },
  { egid: "263024777", flaeche_m2: 9.1, grund: "ohne Wohnnutzung" }] };
const n = nichtEingerechnetHinweis(ab);
pruefe(n.indexOf("EGID 263070701") >= 0 && n.indexOf("EGID 263024777") >= 0 && n.indexOf("ohne Wohnnutzung") >= 0,
       "nicht eingerechnete Nebengebäude einzeln genannt");
pruefe(n.indexOf("hier nicht geprüft") >= 0, "Anrechenbarkeit ausdrücklich nicht geprüft");
pruefe(nichtEingerechnetHinweis({ nicht_eingerechnet: [] }) === "", "ohne Nebengebäude kein Hinweis");

const szen = extrahiere("secSzenarien");
pruefe(szen.indexOf('"rechnerische Reserve (Näherung)"') >= 0 && szen.indexOf('["verbleibend",') < 0,
       "Szenarien: 'rechnerische Reserve (Näherung)' statt 'verbleibend'");
pruefe(szen.indexOf("Keine geprüfte Ausnützungsreserve") >= 0, "mit Erklärung, was die Reserve nicht ist");
pruefe(szen.indexOf('"Bestand, Wohngebäude (Näherung)"') >= 0, "Bestand als Wohngebäude-Näherung benannt");
pruefe(quelltext.indexOf('"Grundfläche (alle Gebäude)"') >= 0, "Übersicht: Grundfläche aller Gebäude benannt");
pruefe(quelltext.indexOf('"Geschossfläche (Wohngebäude)"') >= 0, "Übersicht: Geschossfläche der Wohngebäude benannt");

console.log("\n" + (fehler ? fehler + " FEHLER" : "ALLE BESTAND-KONSISTENZ-JS-TESTS BESTANDEN (" + ok + " OK)"));
process.exit(fehler ? 1 : 0);

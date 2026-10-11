/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   BKP-Eingaben: nur was der Benutzer selbst aendert, wird eigene Annahme
   (11.10.2026).

   Befund Rosenweg 4, Buchs AG: wSammleEingaben() las bei JEDER Eingabe alle
   sichtbaren BKP-Felder aus. Sie zeigten die Ansaetze von "Bestand erhalten"
   -- darunter Aushub 0 --, und der Server uebernahm sie als Benutzerannahme
   fuer alle Szenarien. Der Ersatzneubau verlor seine Baugrube: Landwert
   169'363 statt 150'644 CHF.

   Ausgefuehrt wird der echte Code gegen ein minimales Fake-DOM.

   Aufruf: node tests/js/bkp_eingaben.test.js
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

// --- Fake-DOM: Felder wie im Reiter, mit den Werten, die das BKP-Formular
//     bei "Bestand erhalten" zeigt (Buchs AG, 09.10.2026).
function feld(id, value, extra) {
  return Object.assign({ id: id, value: value, dataset: {}, checked: false }, extra || {});
}
function bkpFeld(k, value, prozent) {
  return feld("", value, { dataset: Object.assign({ k: k }, prozent ? { prozent: "1" } : {}),
                           classList: { contains: function (c) { return c === "w-bkp"; } },
                           className: "w-bkp" });
}
var FELDER = {
  "w-verkauf": feld("w-verkauf", ""), "w-miete": feld("w-miete", ""), "w-boden": feld("w-boden", ""),
  "w-zielmarge": feld("w-zielmarge", "15"), "w-basis": feld("w-basis", "nwf"), "w-land": feld("w-land", "kauf")
};
var BKP = [
  bkpFeld("bkp1_aushub", "0"), bkpFeld("bkp2_gebaeude", "2400"), bkpFeld("bkp3_betriebseinrichtungen", "0"),
  bkpFeld("bkp4_umgebung", "5.0", true), bkpFeld("bkp5_baunebenkosten", "11.0", true),
  bkpFeld("bkp6_reserve", "10.0", true), bkpFeld("finanzierung", "2.5", true), bkpFeld("vermarktung", "2.5", true)
];
var document = {
  getElementById: function (id) { return FELDER[id] || null; },
  querySelectorAll: function (sel) {
    if (sel === ".w-bkp") return BKP;
    return [];
  }
};
var wEingaben = { verkauf_chf_pro_m2: null, miete_chf_pro_m2_jahr: null, bodenpreis_chf_pro_m2: null,
                  zielmarge: 0.15, verkauf_basis: "nwf", land_ansatz: "kauf", bkp: {},
                  restflaeche_verteilen: false, wohnungsmix: [] };

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("wSammleEingaben"));
eval(extrahiere("bkpFeldUebernehmen"));

let ok = 0, fehler = 0;
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler++; console.log("[FEHL] " + was); }
}

console.log("=== 1-3: Preisänderungen übermitteln keine unberührten BKP-Werte ===");
FELDER["w-verkauf"].value = "9000";
wSammleEingaben();
pruefe(wEingaben.verkauf_chf_pro_m2 === 9000, "Verkaufspreis 9000 übernommen");
pruefe(JSON.stringify(wEingaben.bkp) === "{}", "Verkaufspreis geändert: bkp bleibt leer");
FELDER["w-boden"].value = "800";
FELDER["w-miete"].value = "280";
wSammleEingaben();
pruefe(wEingaben.bodenpreis_chf_pro_m2 === 800 && wEingaben.miete_chf_pro_m2_jahr === 280,
       "Bodenpreis 800 und Mietzins 280 übernommen");
pruefe(JSON.stringify(wEingaben.bkp) === "{}", "Bodenpreis/Mietzins geändert: bkp bleibt leer");
pruefe(!("bkp1_aushub" in wEingaben.bkp), "der angezeigte Aushub 0 geht NICHT in den Request");
const body = JSON.parse(JSON.stringify(Object.assign({ job_id: "x" }, wEingaben)));
pruefe(Object.keys(body.bkp).length === 0, "der Request-Body trägt keine BKP-Annahme");

console.log("\n=== 4: eine bewusst geänderte BKP-Position wird übermittelt ===");
BKP[1].value = "2600";
bkpFeldUebernehmen(BKP[1]);
wSammleEingaben();
pruefe(JSON.stringify(wEingaben.bkp) === JSON.stringify({ bkp2_gebaeude: 2600 }),
       "nur bkp2_gebaeude = 2600, kein anderes Feld");
BKP[5].value = "12";
bkpFeldUebernehmen(BKP[5]);
pruefe(wEingaben.bkp.bkp6_reserve === 0.12, "Prozentfeld: 12 % wird 0.12");
pruefe(!("bkp1_aushub" in wEingaben.bkp) && !("bkp5_baunebenkosten" in wEingaben.bkp),
       "unberührte Felder bleiben draussen");
BKP[1].value = "";
bkpFeldUebernehmen(BKP[1]);
pruefe(!("bkp2_gebaeude" in wEingaben.bkp), "Feld geleert: zurück zum Systemansatz");

console.log("\n=== Verdrahtung ===");
const verdr = extrahiere("verdrahteWirtschaft");
pruefe(/el\.classList\.contains\("w-bkp"\)\) bkpFeldUebernehmen\(el\)/.test(verdr),
       "beim Eingabeereignis wird genau das betroffene BKP-Feld übernommen");
pruefe(verdr.indexOf('el.className.indexOf("bkp-") === 0) wBeruehrt.bkp = true') >= 0,
       "die Variantenmarkierung (wBeruehrt.bkp) ist unverändert");
pruefe(extrahiere("wSammleEingaben").indexOf('querySelectorAll(".w-bkp")') < 0,
       "wSammleEingaben liest die BKP-Felder nicht mehr pauschal aus");

console.log("\n" + (fehler ? fehler + " FEHLER" : "ALLE BKP-EINGABE-TESTS BESTANDEN (" + ok + " OK)"));
process.exit(fehler ? 1 : 0);

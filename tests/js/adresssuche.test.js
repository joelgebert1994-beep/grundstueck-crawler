/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Regressionstest fuer die Adresssuche im Browser (dist/index.html).

   Anlass (30.09.2026, Weiningen): "Horgenwiesstrasse 1, 8104 Weiningen ZH"
   -- die Strasse heisst "Hogerwiesstrasse". Fuer die Teileingabe
   "Horgenwiesstrasse 1, 8104" liefert der Suchdienst "Puentenstrasse 2b"
   an erster Stelle. Ohne Laufnummer konnte diese VERSPAETETE Antwort die
   Liste zur vollstaendigen Eingabe ueberschreiben, und nichts zeigte an,
   dass die Vorschlaege eine andere Strasse sind.

   Geprueft mit den echten Funktionen (herausgeschnitten, nicht nachgebaut)
   und den am 30.09.2026 eingefrorenen echten Suchantworten:

     E  eine verspaetete Antwort ueberschreibt die aktuelle Liste nicht
     -  Vorschlaege sind als "andere Strasse/Hausnummer" gekennzeichnet
     -  ohne exakten Treffer steht "Keine passende Adresse gefunden" darueber
     -  ein Klick gibt Kennung, EGAID und LV95-Koordinate mit

   Aufruf: node tests/js/adresssuche.test.js
*/

const fs = require("fs");
const path = require("path");

const DIST = path.join(__dirname, "..", "..", "dist", "index.html");
const quelltext = fs.readFileSync(DIST, "utf8");
const DATEN = path.join(__dirname, "..", "daten", "adresse");
const lade = (n) => JSON.parse(fs.readFileSync(path.join(DATEN, n), "utf8"));

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
  return quelltext.slice(start, i + 1);
}
function extrahiereVar(name) {
  const start = quelltext.indexOf("var " + name + " =");
  if (start < 0) throw new Error("Variable nicht gefunden: " + name);
  return quelltext.slice(start, quelltext.indexOf("};", start) + 2);
}

// --- Minimales DOM: genau das, was sucheAdresse() anfasst ---------------
function element(tag) {
  return {
    tag, kinder: [], textContent: "", className: "", disabled: false, value: "",
    klassen: new Set(), lauscher: {},
    classList: {
      add(k) { this._el.klassen.add(k); }, remove(k) { this._el.klassen.delete(k); },
      _el: null
    },
    appendChild(k) { this.kinder.push(k); return k; },
    addEventListener(art, fn) { this.lauscher[art] = fn; },
    set innerHTML(v) { this.kinder = []; },
    get innerHTML() { return ""; }
  };
}
function neuesElement(tag) { const e = element(tag); e.classList._el = e; return e; }
const document = { createElement: neuesElement };
const inputEl = neuesElement("input");
const suggestEl = neuesElement("div");
const goBtn = neuesElement("button");
const map = { setView() {}, removeLayer() {} };
const L = { circleMarker() { return { addTo() { return this; } }; } };
function lv95ToWgs84(e, n) { return [47, 8]; }
var adressMarker = null;
var adressWahlInfo = null;
var gewaehlteAdresse = null, gewaehlteAuswahl = null, sucheLauf = 0;
const GEOADMIN_SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer";

// fetch, dessen Antworten der Test in beliebiger Reihenfolge freigibt.
const offen = [];
function fetch(url) {
  const q = decodeURIComponent(/searchText=([^&]*)/.exec(url)[1]);
  return new Promise((ok) => offen.push({ q, freigeben: (daten) => ok({ json: () => daten }) }));
}
const warte = () => new Promise((r) => setTimeout(r, 0));

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen, nicht nachbauen */
eval(extrahiereVar("ADRESS_UMLAUT"));
eval(extrahiereVar("ADRESS_PASSUNG_TEXT"));
eval(extrahiere("adressStrasse"));
eval(extrahiere("adressTeile"));
eval(extrahiere("adressPassung"));
eval(extrahiere("adressEgaid"));
eval(extrahiere("sucheAdresse"));
/* eslint-enable no-eval */

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}
const listenText = () => suggestEl.kinder.map((k) => k.textContent + (k.kinder[0] ? " [" + k.kinder[0].textContent + "]" : ""));
const knoepfe = () => suggestEl.kinder.filter((k) => k.tag === "button");

(async function () {
  console.log("=== Passung gegen die Eingabe ===");
  pruefe(adressPassung("Horgenwiesstrasse 1, 8104", "Püntenstrasse 2b 8104 Weiningen ZH") === "andere_strasse",
    "Horgenwiesstrasse vs. Puentenstrasse -> andere Strasse");
  pruefe(adressPassung("Horgenwiesstrasse 1", "Hogerwiesstrasse 1 8104 Weiningen ZH") === "andere_strasse",
    "Horgenwiesstrasse vs. Hogerwiesstrasse -> andere Strasse (nicht 'aehnlich genug')");
  pruefe(adressPassung("Hogerwiesstr. 1, 8104", "Hogerwiesstrasse 1 8104 Weiningen ZH") === "exakt",
    "Abkuerzung 'str.' -> exakt");
  pruefe(adressPassung("Hogerwies 1", "Hogerwiesstrasse 1 8104 Weiningen ZH") === "exakt",
    "beim Tippen abgekuerzte Strasse -> exakt");
  pruefe(adressPassung("Hogerwiesstrasse 1", "Hogerwiesstrasse 11 8104 Weiningen ZH") === "andere_nummer",
    "1 vs. 11 -> andere Hausnummer");
  pruefe(adressPassung("Rosenweg 4", "Rosenweg 4.1 5033 Buchs AG") === "andere_nummer",
    "4 vs. 4.1 -> andere Hausnummer");
  pruefe(adressPassung("Hogerw", "Hogerwiesstrasse 1 8104 Weiningen ZH") === "unbestimmt",
    "ohne Hausnummer -> keine Kennzeichnung (noch am Tippen)");

  console.log("\n=== E: verspaetete Antwort ueberschreibt die aktuelle Liste nicht ===");
  inputEl.value = "Horgenwiesstrasse 1, 8104";
  sucheAdresse("Horgenwiesstrasse 1, 8104");                 // alt -- antwortet spaeter
  inputEl.value = "Horgenwiesstrasse 1, 8104 Weiningen ZH";
  sucheAdresse("Horgenwiesstrasse 1, 8104 Weiningen ZH");    // neu
  const [alt, neu] = offen.splice(0, 2);
  neu.freigeben(lade("suche_horgenwiesstrasse_voll_limit6.json"));
  await warte();
  const nachNeu = listenText();
  alt.freigeben(lade("suche_horgenwiesstrasse_teil_limit6.json"));   // kommt zu spaet
  await warte();
  pruefe(JSON.stringify(listenText()) === JSON.stringify(nachNeu),
    "die spaete Antwort zur Teileingabe aendert die Liste nicht");
  pruefe(!knoepfe()[0].textContent.startsWith("Püntenstrasse"),
    "oben steht NICHT Puentenstrasse 2b (das war der erste Treffer der veralteten Antwort)");

  console.log("\n=== Kennzeichnung und 'keine passende Adresse' ===");
  pruefe(suggestEl.kinder[0].textContent.indexOf("Keine passende Adresse gefunden") === 0,
    "ohne exakten Treffer steht 'Keine passende Adresse gefunden' ueber der Liste");
  pruefe(knoepfe().every((b) => b.className === "abweichend" && b.kinder[0].textContent === "andere Strasse"),
    "jeder Vorschlag traegt 'andere Strasse'");

  console.log("\n=== Exakter Treffer: Kennung und Koordinate gehen mit ===");
  inputEl.value = "Hogerwiesstrasse 1 8104 Weiningen ZH";
  sucheAdresse("Hogerwiesstrasse 1 8104 Weiningen ZH");
  offen.shift().freigeben(lade("suche_hogerwiesstrasse_limit6.json"));
  await warte();
  pruefe(suggestEl.kinder[0].tag === "button", "bei exaktem Treffer keine Warnzeile");
  const erster = knoepfe()[0];
  pruefe(erster.className === "", "der exakte Treffer ist nicht als abweichend markiert");
  erster.lauscher.click();
  pruefe(gewaehlteAdresse === "Hogerwiesstrasse 1 8104 Weiningen ZH", "Klick setzt die Adresse");
  pruefe(gewaehlteAuswahl && gewaehlteAuswahl.feature_id === "123952_0",
    "Klick gibt die Kennung mit (featureId 123952_0)");
  pruefe(gewaehlteAuswahl && gewaehlteAuswahl.egaid === "100121031", "und die EGAID 100121031");
  pruefe(gewaehlteAuswahl && Math.abs(gewaehlteAuswahl.lv95_e - 2675063.7) < 0.5 &&
         Math.abs(gewaehlteAuswahl.lv95_n - 1252760.9) < 0.5,
    "und die LV95-Koordinate des Treffers (E in 'y', N in 'x')");
  pruefe(adressWahlInfo && adressWahlInfo.passung === "exakt", "die Passung wird fuer den Dossierkopf gemerkt");

  console.log("\n=== Eingabe aendert sich waehrend die Suche laeuft ===");
  inputEl.value = "Rosenweg 4, 5033 Buchs";
  sucheAdresse("Rosenweg 4, 5033 Buchs");
  inputEl.value = "Rosenweg 4, 5033 Buch";   // weiter getippt, ohne neue Suche
  offen.shift().freigeben(lade("suche_rosenweg_buchs_limit6.json"));
  await warte();
  pruefe(knoepfe()[0].textContent.indexOf("Hogerwiesstrasse") === 0,
    "eine Antwort auf einen inzwischen veraenderten Text wird verworfen");

  console.log("------------------------------------------------------------------");
  if (fehler.length) {
    console.log("ADRESSSUCHE: " + fehler.length + " Abweichung(en)");
    process.exit(1);
  }
  console.log("ALLE ADRESSSUCHE-TESTS BESTANDEN (" + ok + " OK)");
})();

/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js fuer die
   Begruendung (direktes eval() im Strict-Modus bekommt einen eigenen
   Gueltigkeitsbereich).

   Regressionstest fuer den Markt-PLZ-Fehler (dist/index.html).

   Befund: wErgebnis (Wirtschaftlichkeit der zuletzt gerechneten Analyse,
   samt referenzgebiet.plz) ist eine globale Variable, die nur an zwei
   Stellen neu gesetzt wird -- beim Variantenwechsel und wenn wRechne()
   fuer die AKTUELLE Analyse asynchron antwortet. Eine neue Analyse
   (starteAnalyse()) setzte bisher ergebnisAktuell = null zurueck, aber
   NICHT wErgebnis. verdrahteWirtschaft() laeuft synchron direkt nach dem
   Rendern des neuen Dossiers und liest ueber mktGebiet() schon dort
   wErgebnis.referenzgebiet.plz fuer die erste Marktabfrage -- zu diesem
   Zeitpunkt war wErgebnis noch die Wirtschaftlichkeit der VORIGEN Analyse.
   Live beobachtet: nach Buchs AG (PLZ 5033) ging Rorschachs erste
   Marktanfrage noch mit plz=5033 hinaus, waehrend gemeinde/kanton (die aus
   ergebnisAktuell kommen, welches korrekt zurueckgesetzt wird) bereits
   Rorschach/SG waren.

   Fix: starteAnalyse() setzt jetzt zusaetzlich wErgebnis = null, direkt
   neben dem bestehenden ergebnisAktuell = null.

   Aufruf: node tests/js/markt_plz.test.js
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

let ergebnisAktuell = null;
let wErgebnis = null;

eval(extrahiere("mktGebiet")); // eslint-disable-line no-eval -- Testabsicht: echten Code pruefen

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}

function setzeAnalyse(gemeinde, kanton) {
  ergebnisAktuell = { modul1_geodaten: { gemeinde: { gemeinde: gemeinde, kanton: kanton } } };
}

// ---------------------------------------------------------------------
// 1. Analyse A: Buchs AG, PLZ 5033 (Wirtschaftlichkeit bereits gerechnet)
// ---------------------------------------------------------------------
setzeAnalyse("Buchs (AG)", "AG");
wErgebnis = { referenzgebiet: { plz: "5033" } };
{
  const g = mktGebiet();
  pruefe(g.plz === "5033" && g.gemeinde === "Buchs (AG)" && g.kanton === "AG",
    "Analyse A: eigene PLZ und Gemeinde korrekt (\"" + JSON.stringify(g) + "\")");
}

// ---------------------------------------------------------------------
// 2. Neue Analyse B beginnt -- derselbe Reset, den starteAnalyse() jetzt
//    synchron VOR dem eigentlichen /api/analyze-Aufruf durchfuehrt.
// ---------------------------------------------------------------------
ergebnisAktuell = null;
wErgebnis = null;
{
  const g = mktGebiet();
  pruefe(g.plz === "" && g.gemeinde === "" && g.kanton === "",
    "Reset beim Start einer neuen Analyse: keine Altwerte aus A mehr vorhanden");
}

// ---------------------------------------------------------------------
// 3. Analyse B liefert ihr Teilergebnis (renderDossier laeuft,
//    verdrahteWirtschaft() ruft mktGebiet() auf) -- die Wirtschaftlichkeit
//    fuer B (wRechne()) ist zu diesem Zeitpunkt noch NICHT zurueck. Genau
//    dieses Zeitfenster loeste bisher die falsche Anfrage aus.
// ---------------------------------------------------------------------
setzeAnalyse("Rorschach", "SG");
{
  const g = mktGebiet();
  pruefe(g.plz === "", "Marktanfrage fuer B vor wRechne(): keine PLZ -- insbesondere NICHT 5033");
  pruefe(g.plz !== "5033", "Marktanfrage fuer B uebernimmt nicht die PLZ von A");
  pruefe(g.gemeinde === "Rorschach" && g.kanton === "SG",
    "Gemeinde/Kanton von B sind bereits korrekt, weil ergebnisAktuell bereits neu ist");
}

// ---------------------------------------------------------------------
// 4. wRechne() fuer B kommt zurueck, referenzgebiet wird gesetzt.
// ---------------------------------------------------------------------
wErgebnis = { referenzgebiet: { plz: "9400" } }; // Rorschachs tatsaechliche PLZ
{
  const g = mktGebiet();
  pruefe(g.plz === "9400", "Marktanfrage fuer B nach wRechne(): eigene PLZ (9400), nicht 5033");
}

// ---------------------------------------------------------------------
// 5. Mehrere Analysen hintereinander (A -> B -> C): jede neue Analyse
//    faengt wieder bei null an, keine kumulierten Altwerte.
// ---------------------------------------------------------------------
ergebnisAktuell = null;
wErgebnis = null;
setzeAnalyse("Musterwil", "ZH");
wErgebnis = { referenzgebiet: { plz: "8000" } };
{
  const g = mktGebiet();
  pruefe(g.plz === "8000" && g.plz !== "5033" && g.plz !== "9400",
    "Dritte Analyse C: eigene PLZ, keine Reste weder von A noch von B");
}

// ---------------------------------------------------------------------
// 6. Neuer Analyse-Start OHNE vorherige Analyse (allererster Aufruf) --
//    darf nicht abstuerzen und liefert leere Werte, keine erfundenen.
// ---------------------------------------------------------------------
ergebnisAktuell = null;
wErgebnis = null;
{
  const g = mktGebiet();
  pruefe(g.plz === "" && g.gemeinde === "" && g.kanton === "",
    "Erster Aufruf ohne jede vorherige Analyse: leere, keine erfundenen Werte");
}

// ---------------------------------------------------------------------
// Quelltext-Zusicherung: der Fix sitzt tatsaechlich in starteAnalyse(),
// als Teil des SYNCHRONEN Codes vor dem eigentlichen Netzwerkaufruf --
// sonst waere die Race Condition nicht behoben, sondern nur verschoben.
// ---------------------------------------------------------------------
{
  const fn = extrahiere("starteAnalyse");
  const vorAbruf = fn.slice(0, fn.indexOf("apiAbruf("));
  pruefe(fn.indexOf("apiAbruf(") > 0, "starteAnalyse() enthaelt den erwarteten /api/analyze-Aufruf");
  pruefe(/\bwErgebnis\s*=\s*null\s*;/.test(vorAbruf),
    "wErgebnis wird in starteAnalyse() zurueckgesetzt, SYNCHRON vor dem Netzwerkaufruf");
  pruefe(/\bergebnisAktuell\s*=\s*null\s*;/.test(vorAbruf),
    "der bestehende ergebnisAktuell-Reset ist weiterhin vorhanden (unveraendertes Verhalten)");
}

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " MARKT-PLZ-Pruefungen FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE MARKT-PLZ-TESTS BESTANDEN (" + ok + " OK)");

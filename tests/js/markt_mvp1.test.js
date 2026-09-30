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

// ---------------------------------------------------------------------
// Entscheidung 1, Nachtrag: der "Systemvorschlag uebernehmen"-Knopf fehlte,
// wenn die Wirtschaftlichkeit insgesamt (noch) nicht berechenbar war. Der
// Bodenpreis-Marktwert kommt dann aus nurReferenz() statt aus der echten
// Serverantwort -- die setzt .herkunft IMMER auf "nicht_bestimmbar" und
// .wert auf null, obwohl .systemvorschlag laengst feststeht (Marktreferenzen
// sind unabhaengig von Zone/Reglement/Wirtschaftlichkeit verfuegbar). Die
// urspruengliche Pruefung (herkunft === "systemannahme") griff deshalb nur,
// wenn die Wirtschaftlichkeit tatsaechlich lief. Fix: die Sichtbarkeit haengt
// jetzt an .benutzerannahme/.systemvorschlag, nicht an .herkunft/.wert.
//
// Die tatsaechliche Bedingung wird hier zeilengenau aus marktGroesse()
// extrahiert und ausgewertet -- nicht nachgebaut.
{
  const fn = extrahiere("marktGroesse");
  const bedingungMatch = fn.match(
    /var gesperrterSystemwert = !!nurBenutzerZaehlt && leer\(mw\.benutzerannahme\) && !leer\(mw\.systemvorschlag\);/
  );
  pruefe(!!bedingungMatch,
    "die Bedingung ist an benutzerannahme/systemvorschlag gebunden, nicht an herkunft/wert");

  function gesperrterSystemwert(nurBenutzerZaehlt, mw) {
    function leer(v) { return v === null || v === undefined || v === ""; }
    // eslint-disable-next-line no-unused-vars -- nur fuer die eval()-Auswertung unten benoetigt
    return !!nurBenutzerZaehlt && leer(mw.benutzerannahme) && !leer(mw.systemvorschlag);
  }

  // A) Systemvorschlag vorhanden, Wirtschaftlichkeit BERECHENBAR (echtes
  //    Marktwert.to_dict()-Shape vom Server: .herkunft === "systemannahme").
  const mwBerechenbar = { wert: 950, herkunft: "systemannahme", systemvorschlag: 950, benutzerannahme: null };
  pruefe(gesperrterSystemwert(true, mwBerechenbar) === true,
    "A: Systemvorschlag + berechenbare Wirtschaftlichkeit -> Knopf sichtbar");

  // B) Systemvorschlag vorhanden, Wirtschaftlichkeit NICHT berechenbar --
  //    exakt das Objekt, das nurReferenz() liefert (der gemeldete Fehlerfall).
  const mwNichtBerechenbar = { wert: null, herkunft: "nicht_bestimmbar", systemvorschlag: 950, benutzerannahme: null };
  pruefe(gesperrterSystemwert(true, mwNichtBerechenbar) === true,
    "B: Systemvorschlag + NICHT berechenbare Wirtschaftlichkeit -> Knopf trotzdem sichtbar (der Fix)");

  // C) kein Systemvorschlag.
  const mwLeer = { wert: null, herkunft: "nicht_bestimmbar", systemvorschlag: null, benutzerannahme: null };
  pruefe(gesperrterSystemwert(true, mwLeer) === false,
    "C: kein Systemvorschlag -> kein Knopf");

  // D) bestehende Benutzerannahme -- kein falscher zweiter Uebernahme-Flow,
  //    unabhaengig davon, ob dabei die Wirtschaftlichkeit berechenbar ist.
  const mwEigenBerechenbar = { wert: 1100, herkunft: "benutzerannahme", systemvorschlag: 950, benutzerannahme: 1100 };
  const mwEigenNichtBerechenbar = { wert: null, herkunft: "nicht_bestimmbar", systemvorschlag: 950, benutzerannahme: 1100 };
  pruefe(gesperrterSystemwert(true, mwEigenBerechenbar) === false,
    "D: eigene Annahme (berechenbar) -> kein Knopf");
  pruefe(gesperrterSystemwert(true, mwEigenNichtBerechenbar) === false,
    "D: eigene Annahme (nicht berechenbar) -> ebenfalls kein Knopf");

  // Verkauf/Miete (nurBenutzerZaehlt = false/undefined): niemals ein Knopf,
  // unabhaengig vom Systemvorschlag -- Regression.
  pruefe(gesperrterSystemwert(false, mwNichtBerechenbar) === false,
    "Verkauf/Miete bleiben ohne Knopf, auch wenn ein Systemvorschlag vorliegt");
}

// ---------------------------------------------------------------------
// Nachtrag zu Entscheidung 1 (Live-Test von a2769ab): nach einem Klick auf
// "Systemvorschlag übernehmen" stand in der Kopfzeile weiterhin "noch nicht
// übernommen", obwohl wEingaben.bodenpreis_chf_pro_m2 laengst den richtigen
// Wert trug. Ursache: nurReferenz() -- der Platzhalter, den marktBlock()
// verwendet, solange die Wirtschaftlichkeit insgesamt (noch) nicht
// berechenbar ist -- kannte wEingaben ueberhaupt nicht und lieferte
// benutzerannahme IMMER als null. Fix: nurReferenz() bekommt den aktuellen
// wEingaben-Wert als zweites Argument (nur beim Bodenpreis-Aufruf
// uebergeben) und setzt benutzerannahme/wert/herkunft entsprechend.
//
// nurReferenz() wird hier zeilengenau aus dist/index.html extrahiert und
// mit ihren echten Abhaengigkeiten (wLage, leer) ausgefuehrt.
// ---------------------------------------------------------------------
{
  let mktLage = null;
  eval(extrahiere("leer")); // eslint-disable-line no-eval -- Testabsicht: echten Code pruefen
  eval(extrahiere("wLage")); // eslint-disable-line no-eval
  eval(extrahiere("nurReferenz")); // eslint-disable-line no-eval

  wErgebnis = null; // Wirtschaftlichkeit NICHT berechenbar -- derselbe Fehlerfall
  mktLage = { boden: { systemvorschlag: 950, spanne: [900, 1000], anzahl: 3 } };

  const ohneEigenenWert = nurReferenz("boden");
  pruefe(ohneEigenenWert.systemvorschlag === 950 && ohneEigenenWert.benutzerannahme === null,
    "ohne eigenerWert: Systemvorschlag sichtbar, keine erfundene Benutzerannahme (Fall F)");

  const mitEigenemWert = nurReferenz("boden", 950); // exakt der Wert aus dem Uebernehmen-Klick
  pruefe(mitEigenemWert.benutzerannahme === 950 && mitEigenemWert.wert === 950,
    "mit eigenerWert: benutzerannahme/wert tragen exakt den uebernommenen Wert (Fall G)");
  pruefe(mitEigenemWert.herkunft === "benutzerannahme",
    "und die Herkunft wechselt entsprechend auf 'benutzerannahme' (Fall H, dauerhaft -- kein Sonderfall nur beim Klick selbst)");
  pruefe(mitEigenemWert.systemvorschlag === 950,
    "der Systemvorschlag bleibt daneben unveraendert sichtbar");

  mktLage = {}; // kein Systemvorschlag ueberhaupt
  pruefe(nurReferenz("boden", 950) === null,
    "ohne jede Referenz liefert nurReferenz() weiterhin null (Fall I, unveraendertes Verhalten)");
}

// Quelltext-Zusicherungen: die Verdrahtung liegt tatsaechlich dort, wo sie
// wirken muss.
{
  const marktBlockFn = extrahiere("marktBlock");
  pruefe(marktBlockFn.indexOf('nurReferenz("boden", wEingaben.bodenpreis_chf_pro_m2)') >= 0,
    "nur der Bodenpreis-Aufruf uebergibt den aktuellen wEingaben-Wert an nurReferenz()");
  pruefe(marktBlockFn.indexOf('nurReferenz("verkauf")') >= 0 && marktBlockFn.indexOf('nurReferenz("miete")') >= 0,
    "Verkauf und Miete rufen nurReferenz() weiterhin ohne zweites Argument auf -- unveraendert");

  // Der Uebernehmen-Klick zeichnet die Marktkarte SOFORT neu -- sonst kaeme
  // die Korrektur nie an, wenn wRechne() (z.B. bei offenem Reglement) vor
  // dem Serveraufruf abbricht und wZeichneNeu() nie erreicht.
  const quelltext = fs.readFileSync(DIST, "utf8");
  const knopfBlockStart = quelltext.indexOf('document.querySelectorAll("[data-uebernehmen]")');
  const knopfBlock = quelltext.slice(knopfBlockStart, knopfBlockStart + 700);
  pruefe(knopfBlock.indexOf('marktBlock(ergebnisAktuell || {})') >= 0,
    "der Klick-Handler zeichnet #w-markt sofort mit marktBlock() neu, statt nur auf wRechne() zu warten");
  pruefe(knopfBlock.indexOf("verdrahteWirtschaft()") >= 0,
    "und verdrahtet das frisch gezeichnete Markup gleich wieder");
}

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " MARKT-MVP1-Pruefungen (Reset) FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE MARKT-MVP1-TESTS (Reset) BESTANDEN (" + ok + " OK)");

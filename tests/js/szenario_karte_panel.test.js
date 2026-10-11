/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (eval() im
   Strict-Modus bekommt einen eigenen Gueltigkeitsbereich).

   Regressionstest fuer zwei Bedienfehler (dist/index.html):

   1. "Auf Karte und in 3D zeigen" (Szenariokarte im Reiter Potenzial)
      setzte nur aktivesSzenario. Man blieb im Reiter, die Ebene "Moeglicher
      Baukoerper" blieb aus, es gab keine Rueckmeldung. Geprueft wird die
      ECHTE Funktion szenarioAufKarteZeigen() -- zeilengenau aus der Datei
      geschnitten, mit Stubs fuer Karte, Reiter und Panel.
   2. Verklebte Texte im Karten-Panel ("Parzelle 1145598.9 m²"): <b>-Titel
      und <span class="m"> sind Inline-Elemente; im Panel fehlte die
      Block-Regel, die das Popup hatte. Geprueft werden die CSS-Regeln und
      die Texte, auf die sie wirken.

   Aufruf: node tests/js/szenario_karte_panel.test.js
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

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}

// ---------------------------------------------------------------------
// 1. szenarioAufKarteZeigen() -- Ablauf mit Stubs
// ---------------------------------------------------------------------
var protokoll, aktivesSzenario, ergebnisAktuell, gruppen, map, kartenRahmenGesetzt;
var feldSz, panelHtml, zu3dKnopf, fitBoundsArgs, zeitgeber;

function esc(s) { return String(s); }
function szenarioKarte(id) { protokoll.push("szenarioKarte:" + id); aktivesSzenario = id; }
function zeigeReiter(n) { protokoll.push("reiter:" + n); }
function zeigeKarteninfo(h) { protokoll.push("panel"); panelHtml = h; }
var document = {
  getElementById: function (id) {
    if (id === "lay-szenario") return feldSz;
    if (id === "sz-zu-3d") return zu3dKnopf;
    return null;
  }
};
function setTimeout(fn) { zeitgeber.push(fn); }

eval(extrahiere("szenarioAufKarteZeigen")); // eslint-disable-line no-eval -- echten Code pruefen

function neu(opts) {
  protokoll = []; aktivesSzenario = null; zeitgeber = []; fitBoundsArgs = null;
  panelHtml = ""; kartenRahmenGesetzt = false;
  var layers = opts.koerper ? [{ getBounds: function () { return { extend: function () { return this; } }; } }] : [];
  var imMap = false;
  gruppen = { szenario: {
    getLayers: function () { return layers; },
    addTo: function () { imMap = true; protokoll.push("addTo"); }
  } };
  map = {
    hasLayer: function () { return imMap; },
    fitBounds: function (b, o) { fitBoundsArgs = [b, o]; }
  };
  feldSz = { checked: false, disabled: !opts.koerper };
  zu3dKnopf = { addEventListener: function (e, fn) { this.klick = fn; } };
  ergebnisAktuell = { szenarien: { szenarien: { a: { bezeichnung: "Ersatzneubau" } } } };
}

// A: Szenario mit Baukoerper
neu({ koerper: true });
szenarioAufKarteZeigen("a");
pruefe(aktivesSzenario === "a" && protokoll[0] === "szenarioKarte:a",
  "A: das gewaehlte Szenario wird aktiviert (Karte und 3D lesen dasselbe aktivesSzenario)");
pruefe(feldSz.checked === true && protokoll.indexOf("addTo") >= 0,
  "A: die Ebene 'Moeglicher Baukoerper' wird eingeschaltet (Checkbox UND Kartenebene)");
pruefe(protokoll.indexOf("reiter:karte") > protokoll.indexOf("szenarioKarte:a"),
  "A: danach oeffnet der Kartenreiter -- der Benutzer bleibt nicht im Potenzial-Reiter");
pruefe(/Ersatzneubau/.test(panelHtml) && /eingeschaltet/.test(panelHtml),
  "A: das Panel meldet Szenarioname und eingeschaltete Ebene");
pruefe(/3D-Ansicht zeigt dasselbe Szenario/.test(panelHtml),
  "A: das Panel sagt, dass die 3D-Szene dasselbe Szenario verwendet");
pruefe(/id="sz-zu-3d"/.test(panelHtml) && typeof zu3dKnopf.klick === "function",
  "A: das Panel bietet den Weg in die 3D-Ansicht an und verdrahtet ihn");
zu3dKnopf.klick();
pruefe(protokoll[protokoll.length - 1] === "reiter:entwurf",
  "A: 'In 3D ansehen' oeffnet den 3D-Reiter (Entwurf)");
zeitgeber.forEach(function (f) { f(); });
pruefe(!!fitBoundsArgs, "A: die Karte passt sich nach dem Oeffnen auf den Baukoerper ein");

// B: Ebene war schon an -- nicht doppelt hinzufuegen
neu({ koerper: true });
szenarioAufKarteZeigen("a");
var anzahlAdd = protokoll.filter(function (p) { return p === "addTo"; }).length;
szenarioAufKarteZeigen("a");
pruefe(protokoll.filter(function (p) { return p === "addTo"; }).length === anzahlAdd,
  "B: zweiter Klick fuegt die Ebene nicht erneut hinzu");

// C: Szenario ohne zeichenbaren Koerper -- ehrliche Rueckmeldung statt Stille
neu({ koerper: false });
szenarioAufKarteZeigen("a");
pruefe(feldSz.checked === false && protokoll.indexOf("addTo") < 0,
  "C: ohne Baukoerper wird keine leere Ebene eingeschaltet");
pruefe(/keinen Baukörper/.test(panelHtml) && protokoll.indexOf("reiter:karte") >= 0,
  "C: stattdessen sagt das Panel, dass es nichts zu zeichnen gibt");
pruefe(aktivesSzenario === "a", "C: das Szenario ist trotzdem aktiv (3D verwendet es)");

// D: Verdrahtung -- nur der Knopf der Szenariokarte nimmt den neuen Weg
const verdr = extrahiere("verdrahteSzenarien");
pruefe(/closest\("\.szaktion"\)/.test(verdr) && /szenarioAufKarteZeigen\(id\)/.test(verdr),
  "D: verdrahteSzenarien() ruft den neuen Weg nur fuer den Knopf in .szaktion auf");
pruefe(/else szenarioKarte\(id\)/.test(verdr),
  "D: alle uebrigen Szenarioknoepfe (Chips, Tabellenzeilen) behalten ihr Verhalten");
pruefe(/<div class="szaktion"><button class="szbtn" data-szenario="[^>]*>Auf Karte und in 3D zeigen/.test(quelltext),
  "D: der beschriftete Knopf sitzt in .szaktion");

// ---------------------------------------------------------------------
// 2. Karten-Panel: verklebte Texte
// ---------------------------------------------------------------------
pruefe(/#karte-inspektor > b \{ display: block;/.test(quelltext),
  "E: Titel (<b>) auf oberster Ebene im Panel ist ein Block -- wie im Popup");
pruefe(!/#karte-inspektor b \{/.test(quelltext),
  "E: die Regel trifft nicht jedes <b> -- Hervorhebungen im Fliesstext bleiben inline");
// Keine Regel, die <br> im Panel ausblendet: "b + br" ueberspringt Textknoten
// und ":first-child" zaehlt nur Elemente -- beides wuerde echte Umbrueche in
// den Detailzeilen verschlucken.
pruefe(!/#karte-inspektor[^{]*br[^{]*\{[^}]*display:\s*none/.test(quelltext),
  "E: keine CSS-Regel blendet <br> im Panel aus");
// Mit Block-Titel ergaebe ein <br> direkt dahinter eine Leerzeile.
pruefe(quelltext.indexOf('zeigeKarteninfo("<b>An dieser Stelle</b>" + zeilen') >= 0,
  "E: Direktabfrage: kein <br> zwischen Titel und erster Zeile");
pruefe(quelltext.indexOf('<b>Zulässige Abstandsanordnung</b><span class=\\"m\\"><br>') < 0 &&
       quelltext.indexOf('<b>Bebaubare Fläche</b><span class=\\"m\\">" +\n          (name ? "<br>"') < 0,
  "E: Anordnungs- und Baubereich-Text beginnen nicht mehr mit <br> hinter dem Titel");

// Die betroffenen Texte haben alle die Form <b>Titel</b><span class="m">...
// -- genau auf diese Form wirkt die Regel.
["Parzelle \" + esc(pz.parzellennummer) + \"</b><span class=\\\"m\\\">",
 "<b>\" + esc(zName) + \"</b><span class=\\\"m\\\">",
 "<b>Geplant (projektiert)</b><span class=\\\"m\\\">",
 "<b>Gewässerraum</b><span class=\\\"m\\\">"].forEach(function (muster) {
  pruefe(quelltext.indexOf(muster) >= 0, "F: Panel-Text hat die Form <b>Titel</b><span class=m>: " + muster.slice(0, 40));
});

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " SZENARIO-KARTE-PANEL-Pruefungen FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE SZENARIO-KARTE-PANEL-TESTS BESTANDEN (" + ok + " OK)");

/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js fuer die
   Begruendung (direktes eval() im Strict-Modus bekommt einen eigenen
   Gueltigkeitsbereich).

   Regressionstest fuer den Varianten-Datenverlust bei Adresswechsel
   (dist/index.html, wRechne()).

   Befund: Ist ein Projekt geoeffnet und wird eine ANDERE Adresse
   analysiert, blieb das Projekt einfach offen -- niemand hatte es
   geschlossen. wRechne() (durch das Rendern des Wirtschaftlichkeits-
   Reiters automatisch angestossen) speicherte danach trotzdem in die
   aktive Variante des offenen (aber zu einem ANDEREN Grundstueck
   gehoerenden) Projekts -- mit dem inzwischen auf die neue Adresse
   zurueckgesetzten (leeren) wEingaben. Live reproduziert: Variante 15
   "MVP1-Test Marktwerte" (Verkauf 9100, Boden 1000) wurde nach einem
   Adresswechsel leer ueberschrieben.

   Fix: das automatische Speichern greift nur noch, wenn das offene
   Projekt zum GERADE ANALYSIERTEN Grundstueck gehoert (EGRID-Abgleich).

   Dieser Test extrahiert die tatsaechliche Bedingung aus wRechne() (kein
   Nachbau) und prueft sie gegen alle im Live-Test verlangten Faelle.
   Die volle End-zu-Ende-Kette (echtes wRechne() mit gemocktem fetch())
   wurde zusaetzlich im Browser mit den echten, aus dist/index.html
   geladenen Funktionen verifiziert (siehe Bericht).

   Aufruf: node tests/js/variante_egrid_schutz.test.js
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
// 1. Die Bedingung selbst -- zeilengenau aus wRechne() extrahiert, nicht
//    nachgebaut. Schlaegt jemand die EGRID-Pruefung spaeter versehentlich
//    wieder heraus, faellt dieser Test durch einen leeren Match.
// ---------------------------------------------------------------------
const wRechneQuelle = extrahiere("wRechne");
const bedingungMatch = wRechneQuelle.match(
  /if\s*\(vAktiv[^)]*&&[^)]*projektAktuell[^)]*&&[^)]*egridJetzt[^)]*&&[^)]*projektAktuell\.egrid === egridJetzt\)/
);
pruefe(!!bedingungMatch, "wRechne() enthaelt die EGRID-Vorbedingung vor dem Autospeichern");
pruefe(wRechneQuelle.indexOf("var egridJetzt = (((ergebnisAktuell || {}).modul1_geodaten || {}).kataster || {}).egrid;") >= 0,
  "egridJetzt kommt aus ergebnisAktuell -- also aus dem GERADE analysierten Grundstueck, nicht aus dem Projekt");

// Die Bedingung liegt VOR dem projektAktion(...)-Aufruf, der speichert --
// sonst waere die Absicherung wirkungslos (Speichern zuerst, Pruefung danach).
const speichernIndex = wRechneQuelle.indexOf('aktion: "variante_speichern"');
pruefe(bedingungMatch && wRechneQuelle.indexOf(bedingungMatch[0]) < speichernIndex,
  "die EGRID-Pruefung steht VOR dem Speicheraufruf, nicht danach");

// ---------------------------------------------------------------------
// 2. Dieselbe Bedingung, jetzt tatsaechlich ausgewertet (nicht nur als
//    Text gepruefte) -- mit genau den Faellen aus dem Live-Test.
// ---------------------------------------------------------------------
function darfAutoSpeichern(vAktiv, projektAktuell, ergebnisAktuell) {
  var egridJetzt = (((ergebnisAktuell || {}).modul1_geodaten || {}).kataster || {}).egrid;
  // Dieselbe, woertlich aus dem Quelltext gezogene Bedingung -- nicht von
  // Hand nachformuliert.
  return !!eval(bedingungMatch[0].replace(/^if\s*\(/, "").replace(/\)$/, ""));
}

var vA = { variante_id: 15, name: "MVP1-Test Marktwerte" };
var projektA = { projekt_id: "p1", egrid: "EGRID-A", varianten: [vA], aktive_variante_id: 15 };
var ergA = { modul1_geodaten: { kataster: { egrid: "EGRID-A" } } };
var ergB = { modul1_geodaten: { kataster: { egrid: "EGRID-B" } } };

pruefe(darfAutoSpeichern(vA, projektA, ergA) === true,
  "10/11: dieselbe EGRID erneut gerechnet -- Autospeichern bleibt aktiv");
pruefe(darfAutoSpeichern(vA, projektA, ergB) === false,
  "Kernfall: Projekt A bleibt offen, EGRID B wird analysiert -- KEIN Autospeichern");
pruefe(darfAutoSpeichern(vA, null, ergB) === false,
  "neue Adresse ohne jedes Projekt -- kein Absturz, kein Speichern");
pruefe(darfAutoSpeichern(null, projektA, ergA) === false,
  "Projekt offen, aber keine aktive Variante -- kein Speichern");
pruefe(darfAutoSpeichern(vA, projektA, {}) === false,
  "ergebnisAktuell ohne Kataster/EGRID (z.B. waehrend eine neue Analyse noch laeuft) -- kein Speichern");
pruefe(darfAutoSpeichern(vA, projektA, ergA) === true,
  "Wechsel zurueck auf die urspruengliche Adresse A -- Autospeichern greift wieder");

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " VARIANTE-EGRID-Pruefungen FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE VARIANTE-EGRID-TESTS BESTANDEN (" + ok + " OK)");

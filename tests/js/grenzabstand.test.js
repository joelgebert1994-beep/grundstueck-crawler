/* Bewusst OHNE "use strict": ein direktes eval() im Strict-Modus bekommt
   einen eigenen Gueltigkeitsbereich, und die per eval() geladenen
   Funktionen (grenzabstandBefund & Co., siehe unten) waeren dann von
   hier aus nicht mehr aufrufbar.

   Regressionstest fuer grenzabstandBefund() (dist/index.html).

   Warum ein eigener Node-Test statt eines Python-Tests: die Pruefung
   selbst existiert nur im Browser-JavaScript, es gibt keine Python-
   Entsprechung. Die hier gepruefte Funktion wird ZEILENGENAU aus der
   echten dist/index.html herausgeschnitten (siehe extrahiere() unten) --
   es wird also nie eine zweite, von Hand nachgebaute Kopie der Logik
   getestet, die unbemerkt vom echten Code abweichen koennte.

   Hintergrund des Befundes: naehesteVerbindung() misst den Abstand
   eines Baukoerpers zu jeder einzelnen Parzellenkante als reine
   Streckengeometrie -- ihr ist gleichgueltig, auf welcher Seite der
   Kante der Koerper liegt. Ein Koerper, der vollstaendig ausserhalb
   der Parzelle steht, konnte deshalb zu einer einzelnen, zufaellig
   weit entfernten Kante einen grossen Abstand haben und als
   "eingehalten" erscheinen -- waehrend die Gesamtpruefung (gegen den
   Baubereich) fuer denselben Koerper bereits "verletzt" meldete. Der
   Fix ergaenzt dieselbe ringGanzIn()-Vorpruefung, die pruefeBaubereich()
   bereits gegen den Baubereich verwendet, hier zusaetzlich gegen die
   Parzelle selbst.

   Aufruf: node tests/js/grenzabstand.test.js
*/

const fs = require("fs");
const path = require("path");

const DIST = path.join(__dirname, "..", "..", "dist", "index.html");
const quelltext = fs.readFileSync(DIST, "utf8");

/* Schneidet "function name(...) { ... }" per Klammerzaehlung aus dem
   Quelltext -- robuster als ein zeilenbasierter Regex, weil die
   Funktionen selbst verschachtelte geschweifte Klammern enthalten. */
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

const NAMEN = [
  "imPolygon", "streckenKreuzen", "ringeKreuzen", "ringGanzIn",
  "koerperAchsen", "koerperEcken", "naehesteVerbindung", "grenzabstandBefund",
];
const extrahierterCode = NAMEN.map(extrahiere).join("\n\n");

/* entwurfRaum ist im echten Code eine Closure-Variable des 3D-Moduls;
   hier als veraenderliche globale Variable bereitgestellt, wie es die
   extrahierten Funktionen unveraendert erwarten. klartext() ist reine
   Textkosmetik aus einem anderen Teil der Datei und fuer die Pruefung
   selbst ohne Bedeutung -- ein Identitaets-Stub reicht. */
let entwurfRaum = null;
function klartext(s) { return s; }

eval(extrahierterCode); // eslint-disable-line no-eval -- Testabsicht: echten Code pruefen, nicht nachbauen

// ---------------------------------------------------------------------
// Testgeruest
// ---------------------------------------------------------------------
let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}

// Parzelle 30 x 20 m, Grenzabstand 4 m an allen vier Kanten -- derselbe
// Aufbau, den auch pruefeBaubereich() ueber ringGanzIn() gegen den
// Baubereich prueft, hier gegen die Parzelle selbst.
const PARZELLE = [[0, 0], [30, 0], [30, 20], [0, 20]];
const KANTEN = [
  { nr: 1, soll: 4, a: [0, 0], b: [30, 0] },
  { nr: 2, soll: 4, a: [30, 0], b: [30, 20] },
  { nr: 3, soll: 4, a: [30, 20], b: [0, 20] },
  { nr: 4, soll: 4, a: [0, 20], b: [0, 0] },
];
function raum(mitParzelle) {
  const r = { kanten: KANTEN, anordnung: null, anordnungen: 1 };
  if (mitParzelle !== false) r.parzelle = PARZELLE;
  return r;
}
function koerper(mitte, breite, tiefe, drehung) {
  return { mitte: mitte, breite: breite, tiefe: tiefe, drehung: drehung || 0 };
}

// --- A: vollstaendig innerhalb, Grenzabstand eingehalten -----------------
// Ecken x 10..20, z 7..13 -> 7 m Abstand an allen vier Kanten, gefordert 4 m.
entwurfRaum = raum();
{
  const ga = grenzabstandBefund(koerper([15, 10], 10, 6));
  pruefe(ga.art === "ok", "A: vollstaendig innerhalb, eingehaltener Grenzabstand -> art 'ok'");
  // Seit 30.09.2026 ausgeschrieben: "x / y" bedeutete hier gemessen/gefordert,
  // in der Uebersicht aber klein/gross der BZO -- dieselbe Schreibweise fuer
  // zwei verschiedene Aussagen.
  pruefe(/^\d+\.\d m, gefordert 4\.0 m$/.test(ga.kurz),
    "A: kurz nennt Ist- und Sollmass ausgeschrieben (\"" + ga.kurz + "\")");
  pruefe(ga.verletzte.length === 0, "A: keine verletzten Kanten");
}

// --- D: innerhalb, aber Grenzabstand unterschritten (bestehendes Verhalten,
//        unveraendert -- Regression fuer den "echten" Verletzungsfall) ----
// Ecken x 1..5, z 7..13 -> nur 1 m zur linken Kante (x=0), gefordert 4 m.
entwurfRaum = raum();
{
  const ga = grenzabstandBefund(koerper([3, 10], 4, 6));
  pruefe(ga.art === "verletzt", "D: innerhalb, aber Grenzabstand unterschritten -> art 'verletzt'");
  pruefe(/statt 4\.0 m/.test(ga.kurz),
    "D: kurz nennt weiterhin das tatsaechliche Mass (\"" + ga.kurz + "\")");
  pruefe(ga.verletzte.length === 1, "D: genau eine verletzte Kante gemeldet");
  pruefe(ga.kritisch !== null, "D: kritische Kante fuer die Massdarstellung in der Szene gesetzt");
}

// --- B: teilweise ausserhalb (zwei von vier Ecken ragen ueber die
//        Parzellengrenze bei x=30 hinaus) ---------------------------------
entwurfRaum = raum();
{
  const ga = grenzabstandBefund(koerper([28, 10], 8, 6));
  pruefe(ga.art === "verletzt", "B: teilweise ausserhalb -> art 'verletzt'");
  pruefe(!/ \/ /.test(ga.kurz),
    "B: kurz zeigt nicht das Ist/Soll-Format, das wie 'eingehalten' aussieht (\"" + ga.kurz + "\")");
  // Nicht auf blosses "eingehalten" pruefen: der Text sagt hier absichtlich
  // "nicht eingehalten" -- das WORT kommt also vor, die BEHAUPTUNG nicht.
  // Geprueft wird deshalb gegen die exakte positive Formulierung, die die
  // "ok"-Antwort verwendet ("… — eingehalten über …", siehe Fall A).
  pruefe(!/— eingehalten/.test(ga.text), "B: Text behauptet nicht die positive Formulierung '— eingehalten'");
  pruefe(ga.kritisch === null && ga.verletzte.length === 0,
    "B: keine erfundene Einzelmessung -- kritisch/verletzte bleiben leer");
}

// --- C: vollstaendig ausserhalb der Parzelle ------------------------------
entwurfRaum = raum();
{
  const ga = grenzabstandBefund(koerper([50, 10], 8, 6));
  pruefe(ga.art === "verletzt", "C: vollstaendig ausserhalb -> art 'verletzt'");
  // Dieselbe Praezisierung wie bei Fall B: gegen die positive Formulierung
  // pruefen, nicht gegen das blosse Wort (der Text sagt korrekt "nicht
  // eingehalten").
  pruefe(!/— eingehalten/.test(ga.text) && !/ \/ /.test(ga.kurz),
    "C: keine Anzeige 'Grenzabstand eingehalten' (kurz=\"" + ga.kurz + "\")");
  pruefe(ga.kritisch === null && ga.verletzte.length === 0,
    "C: keine erfundene Einzelmessung -- kritisch/verletzte bleiben leer");
}

// --- Rueckwaertskompatibilitaet: fehlt die Parzellengeometrie (aeltere
//     Zwischenspeicher-Daten o.ae.), greift die neue Vorpruefung nicht --
//     das bestehende Verhalten bleibt unveraendert massgeblich. ----------
entwurfRaum = raum(false);
{
  const ga = grenzabstandBefund(koerper([50, 10], 8, 6)); // dieselbe Lage wie Fall C
  pruefe(typeof ga.art === "string" && ga.art.length > 0,
    "Ohne parzelle-Feld: bestehende Logik laeuft unveraendert weiter, kein Absturz");
}

console.log("-".repeat(78));
if (fehler.length) {
  console.log(fehler.length + " von " + (ok + fehler.length) + " GRENZABSTAND-Pruefungen FEHLGESCHLAGEN");
  process.exit(1);
}
console.log("ALLE GRENZABSTAND-TESTS BESTANDEN (" + ok + " OK)");

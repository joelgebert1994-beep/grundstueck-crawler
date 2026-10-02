/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Weiningen, Hogerwiesstrasse 1 (02.10.2026): G1 liefert im Rueckfallmodus
   (Kanten nicht zugeordnet) jetzt eine eindeutige Geschossflaeche von
   350.42 m2, begrenzt durch die Ausnuetzungsziffer. Die Potenzialkachel muss
   sie zeigen -- und der Satz darunter darf nicht "Alle 0 zulaessigen
   Abstandsvarianten" lauten, denn hier gibt es keine Anordnungsliste.

   Aufruf: node tests/js/potenzial_eindeutig.test.js
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
function extrahiereVar(name) {
  const start = quelltext.indexOf("var " + name + " =");
  if (start < 0) throw new Error("Variable nicht gefunden: " + name);
  return quelltext.slice(start, quelltext.indexOf("};", start) + 2);
}
// Nur Schreibweise -- fuer diese Pruefung ohne Bedeutung.
function lesbar(t) { return t; }
function klartext(t) { return t; }
function istEntartet() { return false; }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiereVar("BINDEND_TEXT"));
eval(extrahiere("bindendText"));
eval(extrahiere("eindeutigSatz"));
eval(extrahiere("potenzialKurz"));
/* eslint-enable no-eval */

let ok = 0;
const fehler = [];
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler.push(was); console.log("[FAIL] " + was); }
}

// So, wie die Engine es fuer Weiningen jetzt liefert (tests/test_weiningen_az.py).
const erklaerung = "Welche Kante den kleinen oder grossen Grenzabstand traegt, ist nicht " +
  "zugeordnet. Beide Raender -- kleiner Abstand an allen Kanten und grosser an allen -- " +
  "ergeben dieselbe Geschossflaeche (350.42 m2). Jede tatsaechliche Zuordnung liegt " +
  "dazwischen und fuehrt deshalb auf denselben Wert. Der Baubereich selbst bleibt offen.";
const weiningen = {
  g1_ergebnis: {
    modus: "bandbreite_grenzabstand_kante_nicht_differenziert",
    gf_nach_ausnuetzungsziffer_m2: 350.42,
    eindeutigkeit: { geschossflaeche_eindeutig: true, geschossflaeche_m2: 350.42,
                     bindend: "ausnuetzung_az", vertreter_anordnung: null,
                     baubereich_spanne_m2: [188.43, 613.78], erklaerung: erklaerung },
    szenarien: {}
  },
  bestand_und_neubaugeometrie: { zusaetzliches_potenzial: { status: "nicht_abschliessend_bestimmbar" } }
};

const kurz = potenzialKurz(weiningen);
pruefe(kurz.art === "eindeutig" && kurz.wert === 350.42,
  "Potenzialkachel: eindeutig 350.42 m² statt 'nicht bestimmbar' (" + kurz.art + ")");
const satz = eindeutigSatz(kurz);
pruefe(satz.indexOf("Alle 0") < 0, "kein 'Alle 0 zulässigen Abstandsvarianten'");
pruefe(satz.indexOf("Beide Raender") >= 0 && /Begrenzend ist .+\.$/.test(satz),
  "der Satz nennt die Begründung der Engine und was begrenzt: " + satz);

const mitAnordnungen = potenzialKurz({ g1_ergebnis: { anordnungen: [{}, {}, {}],
  eindeutigkeit: { geschossflaeche_eindeutig: true, geschossflaeche_m2: 378, bindend: "ausnuetzung_az" } } });
pruefe(/^Alle 3 baurechtlich zulässigen Abstandsvarianten ergeben dasselbe Ergebnis\. Begrenzend ist /.test(
  eindeutigSatz(mitAnordnungen)), "mit Anordnungen bleibt der bisherige Satz unverändert");

console.log("------------------------------------------------------------------");
if (fehler.length) { console.log("POTENZIAL-EINDEUTIG: " + fehler.length + " Abweichung(en)"); process.exit(1); }
console.log("ALLE POTENZIAL-EINDEUTIG-TESTS BESTANDEN (" + ok + " OK)");

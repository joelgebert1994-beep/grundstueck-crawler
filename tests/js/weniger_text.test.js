/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Bestand und Potenzial: weniger sichtbarer Text, Details auf Abruf
   (09.10.2026). Eingaben: das echte Ergebnis von Rosenweg 4, Buchs AG.

   Geprueft wird die NORMALE Ansicht -- ohne eingeklappte Details --, dass
     * Rechnung, Quellen und Liste der nicht eingerechneten Gebaeude dort
       nicht stehen, aber im Detail erreichbar sind,
     * die Unsicherheit ("Näherung", "nicht abschliessend bestimmbar") an
       der betroffenen Kennzahl sichtbar bleibt und
     * Grundfläche aller Gebäude, Geschossfläche der Wohngebäude und
       rechnerische Reserve auseinandergehalten bleiben.

   Aufruf: node tests/js/weniger_text.test.js
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
function lesbar(t) {
  return String(t).replace(/m2/g, "m²").replace(/ x /g, " × ").replace(/Naeherung/g, "Näherung")
    .replace(/Gebaeude/g, "Gebäude").replace(/GENAEHERT/g, "GENÄHERT");
}
function klartext(t) { return String(t); }
function zoneKlarname(t) { return String(t || ""); }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("fmt"));
eval(extrahiere("ebeneZeile"));
eval(extrahiere("ebeneKopf"));
eval(extrahiere("ebeneLeit"));
eval(extrahiere("ebeneBestand"));
eval(extrahiere("ebeneZusatz"));
eval(extrahiere("zusatzBegruendung"));
eval(extrahiere("detailBlock"));
eval(extrahiere("nichtEingerechnetHinweis"));

let ok = 0, fehler = 0;
function pruefe(b, was) {
  if (b) { ok++; console.log("[OK  ] " + was); } else { fehler++; console.log("[FEHL] " + was); }
}

/* Was die Normalansicht zeigt: Text ohne den Inhalt eingeklappter <details>. */
function sichtbar(html) {
  return html.replace(/<details[^>]*>\s*<summary>[\s\S]*?<\/summary>[\s\S]*?<\/details>/g,
    function (d) { return (d.match(/<summary>([\s\S]*?)<\/summary>/) || [, ""])[1]; })
    .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
function inDetails(html) {
  return (html.match(/<details[^>]*>[\s\S]*?<\/details>/g) || []).join(" ")
    .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
}

// Rosenweg 4, Buchs AG -- Livewerte vom 09.10.2026.
const bestand = {
  gebaeude: 3,
  grundflaeche: { wert_m2: 98, status: "gemessen" },
  grundriss_kataster: { quelle: "Amtliche Vermessung, Bodenbedeckung Gebäude (geodienste.ch, AV Situationsplan)" },
  geschosse: { wert: [2], status: "unvollstaendig" },
  geschossflaeche_abgeleitet: {
    wert_m2: 135.4, status: "abgeleitet", rechnung: "67.7 m2 x 2 Geschosse", grund: null,
    nicht_eingerechnet: [
      { egid: "263070701", flaeche_m2: 20.8, grund: "ohne Wohnnutzung" },
      { egid: "263024777", flaeche_m2: 9.1, grund: "ohne Wohnnutzung" }]
  }
};
const zusatz = {
  status: "nicht_abschliessend_bestimmbar",
  grund: "Bestandessituation und Abstands-/Geometriefrage muessen getrennt vom theoretischen Neubauwert beurteilt werden.",
  offene_punkte: ["Der Bestand ist mit rund 135 m2 nur GENAEHERT bekannt (Grundflaeche x Geschosszahl)."]
};

const e1 = ebeneBestand(bestand);
const n1 = sichtbar(e1), d1 = inDetails(e1);
pruefe(n1.indexOf("98") >= 0 && n1.indexOf("Grundfläche aller 3 Gebäude") >= 0, "Bestand: 98 m² als Grundfläche aller 3 Gebäude");
pruefe(n1.indexOf("ca. 135 m²") >= 0 && n1.indexOf("Näherung") >= 0 && n1.indexOf("Geschossfläche (Wohngebäude)") >= 0,
       "Bestand: Geschossfläche der Wohngebäude, sichtbar als Näherung");
pruefe(n1.indexOf("nur Wohngebäude (2 nicht eingerechnet)") >= 0, "Bestand: 'nur Wohngebäude, 2 nicht eingerechnet' bleibt sichtbar");
pruefe(n1.indexOf("67.7") < 0 && n1.indexOf("EGID") < 0 && n1.indexOf("Vermessung") < 0 && n1.indexOf("Nicht gemessen") < 0,
       "Bestand: keine Rechnung, keine EGID-Liste, keine Quelle in der Normalansicht");
pruefe(d1.indexOf("67.7 m² × 2 Geschosse") >= 0, "Detail: die Rechnung");
pruefe(d1.indexOf("EGID 263070701") >= 0 && d1.indexOf("EGID 263024777") >= 0 && d1.indexOf("ohne Wohnnutzung") >= 0,
       "Detail: die nicht eingerechneten Gebäude mit Grund");
pruefe(d1.indexOf("Amtliche Vermessung") >= 0 && d1.indexOf("Gebäude- und Wohnungsregister") >= 0, "Detail: Quellen");
pruefe(d1.indexOf("Nicht gemessen") >= 0, "Detail: 'nicht gemessen'-Hinweis");

const ohneAb = JSON.parse(JSON.stringify(bestand));
ohneAb.geschossflaeche_abgeleitet = { wert_m2: null, status: "nicht_bestimmbar", nicht_eingerechnet: [],
  grund: "Fuer ein Wohngebaeude fehlt eine Angabe." };
const e2 = ebeneBestand(ohneAb);
pruefe(sichtbar(e2).indexOf("nicht verfügbar") >= 0 && sichtbar(e2).indexOf("Näherung") < 0,
       "ohne Geschossfläche: 'nicht verfügbar' statt einer Zahl");
pruefe(inDetails(e2).indexOf("nicht ableitbar") >= 0, "der Grund steht im Detail");

const e3 = ebeneZusatz(zusatz, { art: "eindeutig" });
pruefe(sichtbar(e3).indexOf("Nicht abschliessend bestimmbar") >= 0, "Zusatz: 'nicht abschliessend bestimmbar' bleibt sichtbar");
pruefe(sichtbar(e3).indexOf("GENÄHERT") < 0 && sichtbar(e3).indexOf("theoretischen Neubauwert") < 0,
       "Zusatz: die Begründung steht nicht in der Normalansicht");
pruefe(inDetails(e3).indexOf("GENÄHERT") >= 0 && inDetails(e3).indexOf("zusätzlich") >= 0,
       "Zusatz: die Begründung ist im Detail erreichbar");
pruefe(sichtbar(e3).indexOf("Warum nicht abschliessend bestimmbar?") >= 0, "Zusatz: Detail ist beschriftet");

const offen = zusatzBegruendung(zusatz, { art: "offen" }).replace(/<[^>]+>/g, " ");
pruefe(offen.indexOf("theoretischen Neubauwert") < 0 && offen.indexOf("GENÄHERT") >= 0,
       "ist das Urteil selbst 'nicht abschliessend', steht der Grundsatz nicht doppelt");

// Quelltext: Urteil und Szenarien
const urteil = extrahiere("potenzialUrteil");
pruefe(urteil.indexOf("grundBlock") < 0, "Urteil: die Zusatz-Begründung steht nicht mehr unter dem Neubauwert");
pruefe(urteil.indexOf("Einzelwert daraus") < 0, "Urteil: der lange Spannen-Absatz ist raus");
pruefe(extrahiere("anordnungsTabelle").indexOf("Warum eine Spanne?") >= 0, "Belegbalken bleiben, die Erklärung ist ein Detail");
const szen = extrahiere("secSzenarien");
pruefe(szen.indexOf("bindendText(b.limitierend)") >= 0 && szen.indexOf('["limitierende Grösse", b.limitierend]') < 0,
       "Szenarien: kein interner Schlüssel mehr ('ausnuetzung_az') sichtbar");
pruefe(szen.indexOf('detailBlock("Herleitung der Reserve"') >= 0, "Szenarien: Herleitung der Reserve auf Abruf");
pruefe(szen.indexOf("Keine geprüfte Ausnützungsreserve") >= 0, "Szenarien: 'keine geprüfte Reserve' bleibt sichtbar");
const gs = extrahiere("secGrundstueck");
pruefe(gs.indexOf('detailBlock("Amtliche Kennungen und Herkunft"') >= 0 && gs.indexOf("energieDetail(") >= 0,
       "Grundstück & Bestand: Kennungen und Energie auf Abruf");

console.log("\n" + (fehler ? fehler + " FEHLER" : "ALLE WENIGER-TEXT-TESTS BESTANDEN (" + ok + " OK)"));
process.exit(fehler ? 1 : 0);

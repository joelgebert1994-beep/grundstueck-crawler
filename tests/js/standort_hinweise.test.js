/* Bewusst OHNE "use strict" -- siehe grenzabstand.test.js (direktes eval()).

   Was ist zu beachten? / Standort & Umwelt / Solar (dist/index.html).

   Geprueft mit den echten Funktionen und den am 01.10.2026 eingefrorenen
   echten Antworten fuer Hogerwiesstrasse 1, 8104 Weiningen ZH
   (tests/daten/standort/modul1_hogerwies.json):

     - jeder Hinweis traegt Aussage, Status und Quelle (mit Stand)
     - eine GESCHEITERTE Abfrage steht nie unter "nicht betroffen"
     - die OEREB-Umweltthemen zeigen ihren echten Status (vorher stand bei
       jedem Thema "vorhanden", weil Felder gelesen wurden, die es nicht gibt)
     - Naehe: gefunden / nichts im Umkreis / Fehler sehen verschieden aus
     - Solar: Eignung (Modell) und Anlage (Register) sind getrennte Zeilen

   Aufruf: node tests/js/standort_hinweise.test.js
*/

const fs = require("fs");
const path = require("path");

const DIST = path.join(__dirname, "..", "..", "dist", "index.html");
const quelltext = fs.readFileSync(DIST, "utf8");
const echt = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "daten", "standort", "modul1_hogerwies.json"), "utf8"));

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
function extrahiereVar(name, ende) {
  const start = quelltext.indexOf("var " + name + " =");
  if (start < 0) throw new Error("Variable nicht gefunden: " + name);
  return quelltext.slice(start, quelltext.indexOf(ende || "};", start) + (ende ? ende.length : 2));
}

// Ueberlagerungen kommen in diesen Daten nicht vor -- nur Namensaufbereitung.
function zoneKlarname(s) { return s || ""; }
function chipKlarname(s) { return s; }

/* eslint-disable no-eval -- Testabsicht: echten Code pruefen */
eval(extrahiere("esc"));
eval(extrahiere("leer"));
eval(extrahiere("alsListe"));
eval(extrahiere("fmt"));
eval(extrahiereVar("WTYP"));
eval(extrahiere("wtyp"));
eval(extrahiere("ueberlagerungenVon"));
eval(extrahiereVar("HINWEIS_NICHT_ABGEFRAGT", "];"));
eval(extrahiere("isoDatum"));
eval(extrahiere("beachtenHinweise"));
eval(extrahiereVar("HINWEIS_SYMBOL"));
eval(extrahiere("hinweisZeile"));
eval(extrahiere("hinweisBlock"));
eval(extrahiereVar("UMWELT_THEMA"));
eval(extrahiere("umweltZeilenHtml"));
eval(extrahiere("naheAngabe"));
eval(extrahiere("gueteAngabe"));
eval(extrahiere("solarBlock"));
/* eslint-enable no-eval */

let ok = 0;
const fehler = [];
function pruefe(bedingung, was) {
  if (bedingung) { ok++; console.log("[OK  ] " + was); }
  else { fehler.push(was); console.log("[FAIL] " + was); }
}
const kopie = (o) => JSON.parse(JSON.stringify(o));
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/&#39;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ");

// Restriktionsabfrage, so wie sie fuer diese Parzelle durchlief: nichts gefunden.
const restriktionOk = { gefunden: true, gewaesserraum_flaechen: [], waldgrenze_min_abstand_m: null,
                        baulinien_gefunden: [], fehler: {},
                        suchumkreis_m: { gewaesserraum: 50, wald: 50, baulinien: 60 } };
function m1Mit(restriktion) {
  const m1 = kopie(echt);
  m1.restriktionsgeometrie = restriktion;
  m1.nutzungsklassifikation = { festlegungen: [] };
  return m1;
}

console.log("=== Hinweise mit echten OEREB-Daten ===");
{
  const h = beachtenHinweise(m1Mit(restriktionOk), { status: "gefunden" });
  const belastet = h.befunde.find((b) => b.titel === "Belasteter Standort");
  pruefe(belastet && belastet.art === "warn" &&
         belastet.status === "Belastet, keine schädlichen oder lästigen Einwirkungen zu erwarten (11 % der Fläche)",
    "⚠ Belasteter Standort mit amtlichem Wortlaut und Flächenanteil");
  pruefe(belastet && belastet.quelle === "ÖREB-Kataster ZH · Stand 01.10.2026",
    "die Quelle nennt Kataster, Kanton und Stand: " + (belastet || {}).quelle);
  const es = h.befunde.find((b) => /^Lärmempfindlichkeitsstufe/.test(b.titel));
  pruefe(es && es.titel === "Lärmempfindlichkeitsstufe II" && es.art === "info",
    "ℹ Lärmempfindlichkeitsstufe II ist eine Information, keine Warnung");
  pruefe(h.befunde[0].art === "warn", "Warnungen stehen vor Informationen");
  const geo = h.ok.find((g) => /geodienste/.test(g.quelle));
  pruefe(geo && geo.namen.join("|") === "Gewässerraum|Wald im Umkreis von 50 m|Baulinien",
    "✓ nicht betroffen (geprüft): Gewässerraum, Wald im Umkreis, Baulinien");
  const oereb = h.ok.find((g) => /ÖREB/.test(g.quelle));
  pruefe(oereb && oereb.namen.join("|") === "Grundwasserschutz", "✓ Grundwasserschutz laut ÖREB nicht betroffen");
  pruefe(h.offen.length === 0, "nichts unbestimmt, wenn alle Abfragen gelangen");
  pruefe(h.nichtAbgefragt.indexOf("Naturgefahren (Gefahrenkarte)") >= 0,
    "Naturgefahren stehen als 'nicht abgefragt' da -- nicht als 'kein Risiko'");
  const html = text(hinweisBlock(h));
  pruefe(!/score|Eignung \d|%\s*bebaubar/i.test(html), "keine Gesamtnote, kein Eignungsscore");
  pruefe(/Nicht abgefragt Naturgefahren/.test(html) && /kantonale Karten prüfen/.test(html),
    "'Nicht abgefragt' mit Hinweis auf die kantonalen Karten");
}

console.log("\n=== Eine gescheiterte Abfrage ist nicht 'nicht betroffen' ===");
{
  const r = kopie(restriktionOk);
  r.fehler = { baulinien: "geodienste.ch 502", wald: "Timeout" };
  const h = beachtenHinweise(m1Mit(r), {});
  const okNamen = h.ok.map((g) => g.namen.join("|")).join("|");
  pruefe(okNamen.indexOf("Baulinien") < 0 && okNamen.indexOf("Wald") < 0,
    "Baulinien und Wald stehen NICHT unter 'nicht betroffen'");
  pruefe(h.offen.indexOf("Baulinien") >= 0 && h.offen.indexOf("Waldabstand") >= 0,
    "sondern unter 'nicht bestimmbar'");
  pruefe(/Abfrage nicht möglich oder fehlgeschlagen/.test(text(hinweisBlock(h))),
    "mit dem Grund, und dass unbekannt nicht 'nicht betroffen' heisst");

  const r2 = kopie(restriktionOk);
  r2.fehler = { gewaesserraum: "Timeout" };
  const h2 = beachtenHinweise(m1Mit(r2), {});
  const oe = h2.ok.find((g) => /ÖREB/.test(g.quelle));
  pruefe(oe && oe.namen.indexOf("Gewässerraum") >= 0,
    "Gewässerraum-Abfrage gescheitert -> der ÖREB-Kataster (nicht betroffen) springt ein, mit seiner Quelle");

  const ohneOereb = m1Mit(restriktionOk);
  ohneOereb.oereb = { found: false };
  const h3 = beachtenHinweise(ohneOereb, {});
  pruefe(h3.offen.indexOf("ÖREB-Themen (Kataster nicht abrufbar)") >= 0,
    "ÖREB nicht abrufbar -> Themen nicht bestimmbar, nicht 'nicht betroffen'");

  const ohneRestriktion = m1Mit({});
  const h4 = beachtenHinweise(ohneRestriktion, {});
  pruefe(h4.offen.indexOf("Baulinien") >= 0, "ohne Restriktionsabfrage: Baulinien nicht bestimmbar");
}

console.log("\n=== Umweltthemen zeigen den echten Status ===");
{
  const t = text(umweltZeilenHtml(m1Mit(restriktionOk)));
  pruefe(t.indexOf("vorhanden") < 0, "kein pauschales 'vorhanden' mehr");
  pruefe(/Grundwasserschutz nicht betroffen/.test(t) && /Gewässerraum nicht betroffen/.test(t),
    "Grundwasserschutz und Gewässerraum: nicht betroffen");
  pruefe(/Belastete Standorte Belastet, keine schädlichen/.test(t), "Belastete Standorte: amtlicher Wortlaut");
  pruefe(/Stand 01\.10\.2026/.test(t), "Stand des Katasters steht dabei");
}

console.log("\n=== Nähe ===");
{
  const u = echt.umgebung;
  const s = naheAngabe(u, "schule_naechste");
  pruefe(s.val === "378 m" && s.sub === "Primarschule Weiningen · Luftlinie",
    "Schule 378 m, Primarschule Weiningen, als Luftlinie bezeichnet");
  const b = naheAngabe(u, "bahnhof_naechster");
  pruefe(/^2.688 m$/.test(b.val) && /^Schlieren/.test(b.sub), "Bahnhof Schlieren: " + b.val);
  const g = gueteAngabe(u);
  pruefe(g.val === "Klasse C" && g.sub === "mittelmässige Erschliessung", "ÖV-Güteklasse C");
  const fehlt = kopie(u); fehlt.schule_naechste = null; fehlt.fehler = { schule_naechste: "504" };
  pruefe(naheAngabe(fehlt, "schule_naechste").val === "nicht bestimmbar",
    "Overpass-Ausfall -> 'nicht bestimmbar', nicht 'keine Schule'");
  const keine = kopie(u); keine.spital_naechstes = null;
  const k = naheAngabe(keine, "spital_naechstes");
  pruefe(k.val === "keine im Umkreis" && k.sub === "von 3 km (Luftlinie)",
    "gelungene Suche ohne Treffer -> 'keine im Umkreis von 3 km'");
  const alt = { schule_naechste: null, fehler: {} };
  pruefe(naheAngabe(alt, "schule_naechste") === null,
    "ältere Analyse ohne Suchradius -> 'nicht verfügbar', nicht 'keine im Umkreis'");
  const ausserhalb = { oev_gueteklasse: { klasse: null, bezeichnung: null }, fehler: {} };
  pruefe(gueteAngabe(ausserhalb).val === "keine Klasse", "ausserhalb A–D -> 'keine Klasse'");
}

console.log("\n=== Solar: Eignung und Anlage getrennt ===");
{
  const t = text(solarBlock(echt.energie));
  pruefe(/Solareignung des Daches: 2 × sehr gut \(152 m²\) · 2 × mittel \(50 m²\)/.test(t),
    "Eignung nach Klasse zusammengefasst");
  pruefe(/ca\. 36.539 kWh\/Jahr/.test(t), "Stromertrag aller Dachflächen (Modell)");
  pruefe(/Modell, Stand 08\.12\.2021/.test(t), "als Modell gekennzeichnet, mit Stand");
  pruefe(/Installierte Anlage für dieses Gebäude im Register keine erfasst — das heisst nicht, dass keine besteht/.test(t),
    "keine Anlage im Register -- ohne zu behaupten, es gebe keine");
  const mitAnlage = kopie(echt.energie);
  mitAnlage.anlagen = [{ kategorie: "Photovoltaik", leistung: "10.88 kW", in_betrieb_seit: "08.09.2020", bauart: "Angebaut" }];
  const t2 = text(solarBlock(mitAnlage));
  pruefe(/Installierte Anlage: Photovoltaik 10\.88 kW in Betrieb seit 08\.09\.2020/.test(t2),
    "eine erfasste Anlage steht als eigene Zeile da");
  const neu = kopie(echt.energie); neu.solar_dach = { gefunden: false, flaechen: [] };
  pruefe(/Solareignung des Daches nicht bestimmbar/.test(text(solarBlock(neu))),
    "Gebäude nicht im Modell -> 'nicht bestimmbar', nicht 'ungeeignet'");
  pruefe(solarBlock({ abgefragt: false }) === "" && solarBlock(undefined) === "",
    "ohne Gebäude / ältere Analyse: kein Block");
}

console.log("------------------------------------------------------------------");
if (fehler.length) { console.log("STANDORT/HINWEISE: " + fehler.length + " Abweichung(en)"); process.exit(1); }
console.log("ALLE STANDORT-/HINWEIS-TESTS BESTANDEN (" + ok + " OK)");

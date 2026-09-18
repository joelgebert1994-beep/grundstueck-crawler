// Duenner, generischer Cloudflare-Pages-Function-Proxy: leitet JEDEN Request
// unter /api/* unveraendert an das Python-Backend weiter (webapp.py, ruft
// ausschliesslich unveraenderte Modul-1/2/3-Fachlogik auf). Keine Fachlogik
// hier -- reiner Proxy, damit grundstueck-crawler.pages.dev die echte Analyse
// zeigen kann, obwohl Cloudflare Pages selbst kein Python ausfuehrt.
//
// BACKEND_URL ist eine Cloudflare-Pages-Umgebungsvariable und zeigt auf den
// dauerhaft laufenden Dienst. Siehe docs/betrieb.md.
//
// Zwei Dinge, die dieser Proxy NICHT tun darf:
//
//   1. Antwort-Header wegwerfen. Das Backend liefert CSV und JSON zum
//      Herunterladen mit eigenem Content-Type und Content-Disposition. Wer
//      hier pauschal application/json setzt, macht aus jedem Export eine
//      Datei mit falschem Typ und ohne Namen.
//   2. Einen Verbindungsfehler wie einen Fachbefund aussehen lassen. "Der
//      Server ist aus" und "die amtliche Grundlage fehlt" sind zwei voellig
//      verschiedene Aussagen. Jede Fehlerantwort von hier traegt deshalb ein
//      maschinenlesbares `art`-Feld, an dem die Oberflaeche sie
//      auseinanderhaelt.

const WEITERGEREICHTE_HEADER = [
  "content-type",
  "content-disposition",
  "content-length",
  "cache-control",
];

// Secrets kommen als Text an, und wie dieser Text gesetzt wurde, sieht man
// ihm nicht an. `wrangler ... secret put` liest von der Standardeingabe --
// wer den Wert aus PowerShell hineinleitet, schickt ein CRLF mit, und das
// steht dann IM Secret.
//
// Beim Ziel-URL faellt das nicht auf: der URL-Parser entfernt Zeilenumbrueche.
// Beim Kopfzeilenwert schon -- workerd lehnt CR/LF darin ab (Header-Injection),
// `fetch` wirft, und der catch weiter unten macht daraus "Der Analyse-Server
// ist gerade nicht erreichbar". Am 18.09.2026 hat genau das zwei Stunden lang
// wie ein Ausfall der Plattform ausgesehen: die Seite lief, der Dienst lief,
// der Tunnel lief -- nur der Proxy scheiterte an einem unsichtbaren Zeichen.
//
// Deshalb: beide Werte trimmen, statt sich auf die Eingabe zu verlassen.
function sauber(wert) {
  return String(wert || "").trim();
}

export async function onRequest({ request, env, params }) {
  const backendUrl = sauber(env.BACKEND_URL).replace(/\/+$/, "");
  if (!backendUrl) {
    return fehler(
      "nicht_konfiguriert",
      "Für diese Seite ist kein Analyse-Server hinterlegt (BACKEND_URL fehlt).",
      503
    );
  }

  const segments = Array.isArray(params.path) ? params.path.join("/") : (params.path || "");
  // Query-String mitnehmen -- /api/pick?e=..&n=.. braucht die Parameter,
  // sonst kommt der Request ohne Koordinaten beim Backend an.
  const query = new URL(request.url).search;
  const target = `${backendUrl}/${segments}${query}`;

  const init = { method: request.method, headers: {} };

  // Gemeinsames Geheimnis. Ohne diesen Riegel kann jeder im Internet
  // /analyze aufrufen -- und jeder Aufruf kostet zwei Minuten Rechenzeit und
  // einen LLM-Aufruf aus unserem Kontingent. Der Schluessel steht in den
  // Pages-Umgebungsvariablen, nie im Code.
  const schluessel = sauber(env.BACKEND_SCHLUESSEL);
  if (schluessel) {
    init.headers["X-Gebimo-Schluessel"] = schluessel;
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.headers["Content-Type"] = request.headers.get("Content-Type") || "application/json";
    init.body = await request.text();
  }

  let resp;
  try {
    resp = await fetch(target, init);
  } catch (err) {
    return fehler("backend_offline", "Der Analyse-Server ist gerade nicht erreichbar.", 502);
  }

  // Ein 401 heisst: die Seite ist falsch konfiguriert. Das ist eine
  // technische Stoerung und darf nicht wie ein Befund ueber das Grundstueck
  // aussehen.
  if (resp.status === 401) {
    return fehler(
      "nicht_konfiguriert",
      "Diese Seite ist nicht berechtigt, den Analyse-Server zu nutzen " +
      "(Zugangsschlüssel fehlt oder stimmt nicht).",
      401
    );
  }

  const headers = new Headers();
  for (const name of WEITERGEREICHTE_HEADER) {
    const wert = resp.headers.get(name);
    if (wert) headers.set(name, wert);
  }
  if (!headers.has("content-type")) {
    headers.set("content-type", "application/json; charset=utf-8");
  }

  return new Response(resp.body, { status: resp.status, headers });
}

function fehler(art, text, status) {
  return new Response(
    JSON.stringify({ ok: false, art: art, technisch: true, fehler: text }),
    { status, headers: { "Content-Type": "application/json; charset=utf-8" } }
  );
}

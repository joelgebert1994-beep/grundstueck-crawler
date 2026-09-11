// Duenner, generischer Cloudflare-Pages-Function-Proxy: leitet JEDEN
// Request unter /api/* unveraendert an den echten Python-Backend
// (webapp.py, ruft ausschliesslich unveraenderte Modul-1/2/3-Fachlogik auf)
// weiter. Keine Fachlogik hier -- reiner Proxy, damit
// grundstueck-crawler.pages.dev die echte Analyse zeigen kann, obwohl
// Cloudflare Pages selbst kein Python ausfuehren kann.
//
// BACKEND_URL ist eine Cloudflare-Pages-Umgebungsvariable (aktuell eine
// Cloudflare-Quick-Tunnel-URL zum lokalen Python-Prozess -- aendert sich
// bei jedem Neustart des Tunnels, siehe Betriebsanleitung).
export async function onRequest({ request, env, params }) {
  const backendUrl = env.BACKEND_URL;
  if (!backendUrl) {
    return json({ ok: false, fehler: "Backend nicht konfiguriert (BACKEND_URL fehlt)." }, 503);
  }

  const segments = Array.isArray(params.path) ? params.path.join("/") : (params.path || "");
  // Query-String mitnehmen -- /api/pick?e=..&n=.. braucht die Parameter,
  // sonst kommt der Request ohne Koordinaten beim Backend an.
  const query = new URL(request.url).search;
  const target = `${backendUrl}/${segments}${query}`;

  const init = { method: request.method, headers: { "Content-Type": "application/json" } };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  let resp;
  try {
    resp = await fetch(target, init);
  } catch (err) {
    return json({ ok: false, fehler: "Der Analyse-Server ist gerade nicht erreichbar (Tunnel/Backend offline)." }, 502);
  }

  const body = await resp.text();
  return new Response(body, {
    status: resp.status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

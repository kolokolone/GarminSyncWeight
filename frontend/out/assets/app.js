const state = { status: null, garmin: null, withings: null, withingsConfig: null, route: "home" };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) throw new Error(body?.detail || body?.message || `Erreur HTTP ${response.status}`);
  return body;
}

function setRoute(route, push = true) {
  state.route = route || "home";
  if (push) history.pushState({}, "", state.route === "home" ? "/" : `/${state.route}`);
  document.querySelectorAll("[data-route]").forEach((el) => el.classList.toggle("active", el.dataset.route === state.route));
  render();
}

function routeFromPath() { return location.pathname.replace(/^\//, "").split("/")[0] || "home"; }
function badgeClass(ok, warn = false) { return ok ? "ok" : (warn ? "warn" : "bad"); }

function btn(label, onClick, className = "") {
  const el = document.createElement("button");
  el.textContent = label;
  el.className = className;
  el.addEventListener("click", onClick);
  return el;
}

function link(label, href, className = "button secondary") {
  const el = document.createElement("a");
  el.textContent = label;
  el.href = href;
  el.className = className;
  return el;
}

function card({ eyebrow, title, badge, badgeKind, message, actions = [] }) {
  const tpl = $("#tpl-card").content.cloneNode(true);
  tpl.querySelector(".eyebrow").textContent = eyebrow;
  tpl.querySelector("h2").textContent = title;
  const badgeEl = tpl.querySelector(".badge");
  badgeEl.textContent = badge;
  badgeEl.classList.add(badgeKind);
  tpl.querySelector(".message").textContent = message;
  actions.forEach((action) => tpl.querySelector(".actions").append(action));
  return tpl;
}

async function refreshStatus() {
  const [status, garmin, withings, withingsConfig] = await Promise.all([
    api("/api/status"),
    api("/api/garmin/auth/status"),
    api("/api/withings/auth/status"),
    api("/api/withings/auth/config"),
  ]);
  state.status = status;
  state.garmin = garmin;
  state.withings = withings;
  state.withingsConfig = withingsConfig;
}

async function safeRefresh() { try { await refreshStatus(); } catch (error) { console.error(error); } }

function renderHome() {
  const s = state.status || {};
  const g = state.garmin || {};
  const w = state.withings || {};
  const grid = document.createElement("section");
  grid.className = "grid three";
  grid.append(
    card({
      eyebrow: "Application",
      title: "GarminSyncWeight",
      badge: s.state || "unknown",
      badgeKind: badgeClass(s.state === "ready", s.state === "needs_auth" || s.state === "not_configured"),
      message: s.message || "Statut indisponible.",
      actions: [btn("Actualiser", async () => { await safeRefresh(); render(); }, "secondary"), link("Synchroniser", "/sync")],
    }),
    card({
      eyebrow: "Withings",
      title: "Connexion vérifiée",
      badge: w.state || "unknown",
      badgeKind: badgeClass(Boolean(w.connected), Boolean(s.withings_configured)),
      message: w.message || "Statut Withings indisponible.",
      actions: [link("Ouvrir Withings", "/withings")],
    }),
    card({
      eyebrow: "Garmin",
      title: "MCP Taxuspt",
      badge: g.state || "unknown",
      badgeKind: badgeClass(g.token_valid, g.token_found),
      message: g.message || "Statut Garmin indisponible.",
      actions: [link("Ouvrir Garmin", "/garmin")],
    }),
  );
  return grid;
}

function renderWithings() {
  const w = state.withings || {};
  const config = state.withingsConfig || {};
  const params = new URLSearchParams(location.search);
  const authResult = params.get("withings_auth");
  const authMessage = authResult === "success" ? "Connexion Withings réussie. Le token est stocké localement et sera rafraîchi automatiquement." : params.get("message");
  const panel = document.createElement("section");
  panel.className = "grid";
  panel.append(card({
    eyebrow: "Withings",
    title: "OAuth2 Body Cardio",
    badge: w.state || "unknown",
    badgeKind: badgeClass(Boolean(w.connected), config.configured),
    message: authMessage || w.message || "Configure puis connecte Withings.",
    actions: [
      link("Connecter Withings", "/api/withings/auth/start", "button"),
      btn("Tester", async () => { alert(JSON.stringify(await api("/api/withings/auth/test", { method: "POST", body: "{}" }), null, 2)); await safeRefresh(); render(); }, "secondary"),
      btn("Déconnecter", async () => { await api("/api/withings/auth/disconnect", { method: "POST", body: "{}" }); await safeRefresh(); render(); }, "danger"),
    ],
  }));
  const setup = document.createElement("article");
  setup.className = "card";
  const callbackUrl = config.redirect_uri || `${location.origin}/api/withings/auth/callback`;
  setup.innerHTML = `
    <div class="card-head"><div><p class="eyebrow">Configuration</p><h2>Application Withings</h2></div><span class="badge ${config.configured ? "ok" : "warn"}">${config.configured ? "configurée" : "à faire"}</span></div>
    <p class="message">Le client secret reste côté backend local. Le scope user.metrics est obligatoire.</p>
    <div class="form">
      <label>Callback URL<input readonly value="${callbackUrl}" /></label>
      <label>Client ID Withings<input id="withings-client-id" autocomplete="off" /></label>
      <label>Client Secret Withings<input id="withings-client-secret" type="password" autocomplete="off" /></label>
      <label>Scope<input id="withings-scope" value="${config.scope || "user.metrics"}" /></label>
      <div class="actions"><button id="withings-save-config">Enregistrer</button><a class="button secondary" href="https://developer.withings.com/dashboard/" target="_blank" rel="noreferrer">Dashboard Withings</a></div>
      <textarea id="withings-config-output" readonly></textarea>
    </div>`;
  panel.append(setup);
  setTimeout(bindWithingsSetupForm, 0);
  return panel;
}

function bindWithingsSetupForm() {
  $("#withings-save-config")?.addEventListener("click", async () => {
    const out = $("#withings-config-output");
    try {
      const result = await api("/api/withings/auth/config", {
        method: "POST",
        body: JSON.stringify({
          client_id: $("#withings-client-id").value,
          client_secret: $("#withings-client-secret").value,
          redirect_uri: `${location.origin}/api/withings/auth/callback`,
          scope: $("#withings-scope").value || "user.metrics",
        }),
      });
      out.value = `Configuration enregistrée dans ${result.env_path}. Clique sur Connecter Withings.`;
      await safeRefresh(); render();
    } catch (error) { out.value = error.message; }
  });
}

function renderGarmin() {
  const g = state.garmin || {};
  const wrap = document.createElement("section");
  wrap.className = "grid";
  const login = document.createElement("article");
  login.className = "card";
  login.innerHTML = `
    <div class="card-head"><div><p class="eyebrow">Garmin</p><h2>Connexion locale Taxuspt/garmin_mcp</h2></div><span class="badge ${badgeClass(g.token_valid, g.token_found)}">${g.state || "unknown"}</span></div>
    <p class="message">Les tokens sont ceux de garmin-mcp-auth. Les identifiants ne sont jamais stockés.</p>
    <div class="form">
      <label>Email Garmin<input id="garmin-email" autocomplete="username" /></label>
      <label>Mot de passe Garmin<input id="garmin-password" type="password" autocomplete="current-password" /></label>
      <label>Code OTP/MFA si demandé<input id="garmin-otp" autocomplete="one-time-code" /></label>
      <div class="actions"><button id="garmin-login">Connecter Garmin</button><button id="garmin-assisted" class="secondary">Commande assistée</button><button id="garmin-verify" class="secondary">Vérifier</button><button id="garmin-disconnect" class="danger">Déconnecter</button></div>
      <textarea id="garmin-output" readonly>${g.token_dir ? `Dossier token: ${g.token_dir}` : ""}</textarea>
    </div>`;
  wrap.append(login);
  setTimeout(bindGarminForm, 0);
  return wrap;
}

function bindGarminForm() {
  const output = $("#garmin-output");
  const show = (value) => { output.value = typeof value === "string" ? value : JSON.stringify(value, null, 2); };
  $("#garmin-login")?.addEventListener("click", async () => {
    try { show(await api("/api/garmin/auth/login", { method: "POST", body: JSON.stringify({ email: $("#garmin-email").value || null, password: $("#garmin-password").value || null, otp: $("#garmin-otp").value || null }) })); await safeRefresh(); render(); }
    catch (error) { show(error.message); }
  });
  $("#garmin-assisted")?.addEventListener("click", async () => { try { show(await api("/api/garmin/auth/reauthenticate", { method: "POST", body: "{}" })); } catch (error) { show(error.message); } });
  $("#garmin-verify")?.addEventListener("click", async () => { try { show(await api("/api/garmin/auth/verify", { method: "POST", body: "{}" })); await safeRefresh(); render(); } catch (error) { show(error.message); } });
  $("#garmin-disconnect")?.addEventListener("click", async () => { if (!confirm("Supprimer les tokens Garmin locaux ?")) return; try { show(await api("/api/garmin/auth/disconnect", { method: "POST", body: JSON.stringify({ confirm: true }) })); await safeRefresh(); render(); } catch (error) { show(error.message); } });
}

function renderSync() {
  const s = state.status || {};
  const ready = s.state === "ready";
  const panel = document.createElement("section");
  panel.className = "panel";
  const today = new Date().toISOString().slice(0, 10);
  panel.innerHTML = `
    <p class="eyebrow">Synchronisation</p><h2>Synchroniser Withings → Garmin</h2>
    <p class="message">${ready ? "Les prérequis sont vérifiés. La synchronisation écrit uniquement les mesures manquantes." : `Synchronisation désactivée: ${s.message || "pré requis non satisfaits"}`}</p>
    <div class="form">
      <label>Période<select id="period"><option value="today">Aujourd'hui</option><option value="7">7 derniers jours</option><option value="30">30 derniers jours</option><option value="custom">Personnalisée</option></select></label>
      <label>Date début<input id="start-date" type="date" value="${today}" /></label>
      <label>Date fin<input id="end-date" type="date" value="${today}" /></label>
      <label>Timezone<input id="tz" value="Europe/Paris" /></label>
      <div class="actions"><button id="run-sync" ${ready ? "" : "disabled"}>Synchroniser maintenant</button><button id="latest-report" class="secondary">Dernier rapport</button></div>
      <pre id="sync-output" class="report"></pre>
    </div>`;
  setTimeout(bindSyncForm, 0);
  return panel;
}

function bindSyncForm() {
  const out = $("#sync-output");
  const period = $("#period");
  period?.addEventListener("change", () => {
    const end = new Date();
    const start = new Date();
    if (period.value === "7") start.setDate(end.getDate() - 6);
    if (period.value === "30") start.setDate(end.getDate() - 29);
    if (period.value !== "custom") {
      $("#start-date").value = start.toISOString().slice(0, 10);
      $("#end-date").value = end.toISOString().slice(0, 10);
    }
  });
  $("#run-sync")?.addEventListener("click", async () => {
    try {
      out.textContent = "Synchronisation en cours...";
      const result = await api("/api/sync/run", { method: "POST", body: JSON.stringify({ start_date: $("#start-date").value, end_date: $("#end-date").value, timezone: $("#tz").value }) });
      out.textContent = JSON.stringify(result, null, 2);
      await safeRefresh();
    } catch (error) { out.textContent = error.message; }
  });
  $("#latest-report")?.addEventListener("click", async () => { try { out.textContent = JSON.stringify(await api("/api/sync/reports/latest"), null, 2); } catch (error) { out.textContent = error.message; } });
}

function renderLogs() {
  const panel = document.createElement("section");
  panel.className = "panel";
  panel.innerHTML = `<p class="eyebrow">Observabilité</p><h2>Logs redacted</h2><div class="actions">${["backend", "withings", "garmin", "sync", "security"].map((name) => `<button class="secondary" data-log="${name}">${name}</button>`).join("")}</div><pre id="log-output" class="report"></pre>`;
  setTimeout(() => {
    const out = $("#log-output");
    document.querySelectorAll("[data-log]").forEach((el) => el.addEventListener("click", async () => { try { const result = await api(`/api/logs/${el.dataset.log}`); out.textContent = result.lines.join("\n") || "Aucun log."; } catch (error) { out.textContent = error.message; } }));
  }, 0);
  return panel;
}

function render() {
  const view = $("#view");
  view.innerHTML = "";
  if (state.route === "withings") view.append(renderWithings());
  else if (state.route === "garmin") view.append(renderGarmin());
  else if (state.route === "sync") view.append(renderSync());
  else if (state.route === "logs") view.append(renderLogs());
  else view.append(renderHome());
}

document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-route]");
  if (!anchor) return;
  event.preventDefault();
  setRoute(anchor.dataset.route);
});
window.addEventListener("popstate", () => setRoute(routeFromPath(), false));
safeRefresh().finally(() => setRoute(routeFromPath(), false));

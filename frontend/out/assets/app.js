/* GarminSyncWeight — Dashboard-centric frontend
 * Navigation: Dashboard / Historique / Réglages / Logs
 * Respecte UI_STYLE_GUIDE.md : fond sombre, cartes translucides,
 * badges arrondis, palette vert/noir/cyan.
 */

const state = {
  status: null, garmin: null, withings: null, withingsConfig: null,
  preview: null, recent: null, syncResult: null,
  route: "dashboard",
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

/* ── API helper ──────────────────────────────────────────────── */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let body;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) throw new Error(body?.detail || body?.message || `Erreur HTTP ${res.status}`);
  return body;
}

/* ── SPA routing ─────────────────────────────────────────────── */

function setRoute(route, push = true) {
  // Redirect /sync and /withings legacy routes
  if (route === "sync" || route === "withings" || route === "garmin") {
    route = route === "sync" ? "dashboard" : "reglages";
  }
  state.route = route || "dashboard";
  const href = state.route === "dashboard" ? "/" : `/${state.route}`;
  if (push) history.pushState({}, "", href);
  $$("[data-route]").forEach((el) =>
    el.classList.toggle("active", el.dataset.route === state.route)
  );
  render();
}

function routeFromPath() {
  const p = location.pathname.replace(/^\//, "").split("/")[0];
  if (["dashboard", "historique", "reglages", "logs"].includes(p)) return p;
  return "dashboard";
}

/* ── Helpers ──────────────────────────────────────────────────── */

function badgeClass(ok, warn = false) {
  return ok ? "ok" : (warn ? "warn" : "bad");
}

function btn(label, onClick, cls = "") {
  const el = document.createElement("button");
  el.textContent = label;
  el.className = cls;
  el.addEventListener("click", onClick);
  return el;
}

function link(label, href, cls = "button secondary") {
  const el = document.createElement("a");
  el.textContent = label;
  el.href = href;
  el.className = cls;
  return el;
}

function cpy(tplId) {
  return $(`#${tplId}`).content.cloneNode(true);
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  children.forEach((c) => e.append(c));
  return e;
}

function getLocalDate() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/* ── Status refresh ──────────────────────────────────────────── */

async function refreshStatus() {
  const [status, garmin, withings, cfg] = await Promise.all([
    api("/api/status"),
    api("/api/garmin/auth/status"),
    api("/api/withings/auth/status"),
    api("/api/withings/auth/config"),
  ]);
  state.status = status;
  state.garmin = garmin;
  state.withings = withings;
  state.withingsConfig = cfg;
}

async function safeRefresh() {
  try { await refreshStatus(); } catch (e) { console.error(e); }
}

/* ── Loading / Empty / Error components ──────────────────────── */

function loadingState(msg = "Chargement en cours") {
  const div = document.createElement("div");
  div.className = "loading-pulse";
  div.textContent = msg;
  return div;
}

function emptyState(title, detail = "", action = null) {
  const div = document.createElement("div");
  div.className = "empty-state";
  if (title) { const t = document.createElement("div"); t.className = "empty-title"; t.textContent = title; div.append(t); }
  if (detail) { const p = document.createElement("p"); p.textContent = detail; div.append(p); }
  if (action) { const wrap = document.createElement("div"); wrap.className = "empty-action"; wrap.append(action); div.append(wrap); }
  return div;
}

function errorState(title, detail = "") {
  const div = document.createElement("div");
  div.className = "error-state";
  const t = document.createElement("div"); t.className = "error-title"; t.textContent = title || "Erreur";
  div.append(t);
  if (detail) { const d = document.createElement("div"); d.className = "error-detail"; d.textContent = detail; div.append(d); }
  return div;
}

/* ── TechnicalDetailsAccordion ───────────────────────────────── */

function technicalAccordion(label, content) {
  const details = document.createElement("details");
  details.className = "technical-details";
  const sum = document.createElement("summary");
  sum.textContent = label || "Voir détails techniques";
  details.append(sum);
  const div = document.createElement("div");
  div.className = "tech-content";
  const pre = document.createElement("pre");
  pre.textContent = typeof content === "string" ? content : JSON.stringify(content, null, 2);
  div.append(pre);
  details.append(div);
  return details;
}

/* ── StatusBar ───────────────────────────────────────────────── */

function renderStatusBar() {
  const s = state.status || {};
  const w = state.withings || {};
  const g = state.garmin || {};

  const bar = document.createElement("div");
  bar.className = "status-bar";

  function addBadge(text, kind) {
    const b = document.createElement("span");
    b.className = `badge ${kind}`;
    b.textContent = text;
    bar.append(b);
    const sep = document.createElement("span");
    sep.className = "sep";
    sep.textContent = "·";
    bar.append(sep);
  }

  function addText(text) {
    const span = document.createElement("span");
    span.className = "text";
    span.textContent = text;
    bar.append(span);
    const sep = document.createElement("span");
    sep.className = "sep";
    sep.textContent = "·";
    bar.append(sep);
  }

  // Withings
  if (w.connected) addBadge("Withings connecté", "ok");
  else if (state.withingsConfig?.configured) addBadge("Withings non connecté", "bad");
  else addBadge("Withings non configuré", "bad");

  // Garmin
  if (g.token_valid) addBadge("Garmin prêt", "ok");
  else if (g.token_found) addBadge("Garmin invalide", "warn");
  else addBadge("Garmin non configuré", "bad");

  // Latest measurement from preview
  const p = state.preview;
  if (p?.latest_measurement) {
    const dt = p.latest_measurement.measured_at || "";
    const dateStr = dt ? new Date(dt).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
    addText(`Dernière mesure : ${dateStr}`);
  } else {
    addText("Aucune mesure récente");
  }

  // Last sync
  if (s.last_sync) {
    const syncDate = new Date(s.last_sync).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    addText(`Dernière sync : ${syncDate}`);
  }

  // Remove trailing sep if any
  const last = bar.lastElementChild;
  if (last?.className === "sep") last.remove();

  return bar;
}

/* ── MetricTile ──────────────────────────────────────────────── */

function metricTile(label, value, unit = "") {
  const tpl = cpy("tpl-metric-tile");
  tpl.querySelector(".metric-tile-label").textContent = label;
  const valEl = tpl.querySelector(".metric-tile-value");
  valEl.textContent = value != null ? `${value}${unit ? " " + unit : ""}` : "—";
  return tpl;
}

/* ── LatestMeasurementCard ───────────────────────────────────── */

function renderLatestMeasurement(preview) {
  const lm = preview.latest_measurement;
  if (!lm) return emptyState("Aucune mesure", "Connecte Withings pour récupérer tes mesures.");

  const card = document.createElement("div");
  card.className = "latest-measurement";

  // Header
  const head = document.createElement("div");
  head.className = "lm-head";
  const eye = document.createElement("p");
  eye.className = "eyebrow";
  eye.textContent = "Dernière mesure détectée";
  head.append(eye);

  const dev = document.createElement("div");
  dev.className = "lm-device";
  dev.textContent = `${lm.device || "Body Cardio+"} · ${lm.measured_at ? new Date(lm.measured_at).toLocaleString("fr-FR", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "date inconnue"}`;
  head.append(dev);

  // Weight
  if (lm.weight_kg != null) {
    const w = document.createElement("div");
    w.className = "lm-weight";
    w.textContent = `${lm.weight_kg.toFixed(1)}`;
    const unit = document.createElement("span");
    unit.className = "lm-weight-unit";
    unit.textContent = "kg";
    w.append(unit);
    head.append(w);
  }

  card.append(head);

  // Metric tiles
  const grid = document.createElement("div");
  grid.className = "metric-grid";

  const tiles = [
    ["Masse grasse", lm.fat_percent, "%"],
    ["Masse musculaire", lm.muscle_mass_kg, "kg"],
    ["Masse osseuse", lm.bone_mass_kg, "kg"],
    ["IMC", lm.bmi],
    ["Métabolisme basal", lm.basal_metabolic_rate_kcal, "kcal"],
    ["Âge métabolique", lm.metabolic_age, "ans"],
    ["Graisse viscérale", lm.visceral_fat_rating],
  ];
  for (const [label, val, unit] of tiles) {
    grid.append(metricTile(label, val, unit));
  }
  card.append(grid);

  return card;
}

/* ── Sparkline (SVG) ─────────────────────────────────────────── */

function renderSparkline(items) {
  const wrapper = document.createElement("div");
  wrapper.className = "sparkline-wrapper";

  const head = document.createElement("div");
  head.className = "card-head";
  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Évolution récente";
  head.append(eye);
  wrapper.append(head);

  if (!items || items.length < 2) {
    const empty = document.createElement("div");
    empty.className = "sparkline-empty";
    empty.textContent = "Pas assez de données pour afficher le graphique.";
    wrapper.append(empty);
    return wrapper;
  }

  const W = 600, H = 180, PAD = 20;
  const values = items.map((i) => i.weight_kg).filter((v) => v != null);
  if (values.length < 2) {
    const empty = document.createElement("div");
    empty.className = "sparkline-empty";
    empty.textContent = "Pas assez de mesures de poids disponibles.";
    wrapper.append(empty);
    return wrapper;
  }

  const min = Math.min(...values) - 1;
  const max = Math.max(...values) + 1;
  const range = max - min || 1;

  function x(i) { return PAD + (i / (values.length - 1)) * (W - 2 * PAD); }
  function y(v) { return H - PAD - ((v - min) / range) * (H - 2 * PAD); }

  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const lastVal = values[values.length - 1];
  const lastX = x(values.length - 1);
  const lastY = y(lastVal);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.style.height = "160px";

  // Area fill
  const area = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  const areaPts = `${PAD},${H - PAD} ${pts} ${lastX},${H - PAD}`;
  area.setAttribute("points", areaPts);
  area.setAttribute("fill", "rgba(140,255,181,.08)");
  svg.append(area);

  // Line
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("points", pts);
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "var(--green)");
  poly.setAttribute("stroke-width", "2.5");
  poly.setAttribute("stroke-linejoin", "round");
  poly.setAttribute("stroke-linecap", "round");
  svg.append(poly);

  // Dot on last
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("cx", String(lastX));
  dot.setAttribute("cy", String(lastY));
  dot.setAttribute("r", "4");
  dot.setAttribute("fill", "var(--green)");
  svg.append(dot);

  // Last value label
  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", String(lastX + 8));
  label.setAttribute("y", String(lastY - 8));
  label.setAttribute("fill", "var(--green)");
  label.setAttribute("font-size", "13");
  label.setAttribute("font-weight", "700");
  label.textContent = `${lastVal.toFixed(1)} kg`;
  svg.append(label);

  wrapper.append(svg);
  return wrapper;
}

/* ── MappingPreviewTable ─────────────────────────────────────── */

function renderMappingTable(preview) {
  const wrapper = document.createElement("div");
  wrapper.className = "mapping-table-wrapper";

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Aperçu avant synchronisation";
  wrapper.append(eye);
  const msg = document.createElement("p"); msg.className = "message"; msg.textContent = "Données Withings → Garmin. Aucune écriture tant que tu ne cliques pas sur Synchroniser.";
  wrapper.append(msg);

  const fields = preview?.field_mapping;
  if (!fields || fields.length === 0) {
    wrapper.append(emptyState("Aucune donnée à afficher", "Aucune mesure Withings disponible pour l'aperçu."));
    return wrapper;
  }

  const table = document.createElement("table");
  table.className = "mapping-table";
  table.innerHTML = `
    <thead><tr>
      <th>Champ</th>
      <th>Withings</th>
      <th>Garmin prévu</th>
      <th>Décision</th>
    </tr></thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector("tbody");

  const statusLabels = {
    will_sync: "Sera envoyé",
    calculated: "Calculé",
    ignored: "Ignoré volontairement",
    absent: "Non mesuré",
    conflict: "Conflit",
    unsupported: "Non supporté",
  };

  for (const f of fields) {
    const row = document.createElement("tr");
    const label = document.createElement("td"); label.className = "field-label"; label.textContent = f.label;
    const wv = document.createElement("td"); wv.className = "field-withings"; wv.textContent = f.withings_value || "—";
    const gv = document.createElement("td"); gv.className = "field-garmin"; gv.textContent = f.garmin_value || "—";
    const dc = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `field-decision ${f.status}`;
    const labelText = statusLabels[f.status] || f.status;
    badge.textContent = f.message || labelText;
    dc.append(badge);

    row.append(label, wv, gv, dc);
    tbody.append(row);
  }

  wrapper.append(table);

  if (preview?.warnings?.length) {
    const warnDiv = document.createElement("div");
    warnDiv.style.marginTop = "12px";
    for (const w of preview.warnings) {
      const p = document.createElement("p");
      p.style.color = "var(--amber)";
      p.style.fontSize = "12px";
      p.style.margin = "4px 0";
      p.textContent = `⚠ ${w}`;
      warnDiv.append(p);
    }
    wrapper.append(warnDiv);
  }

  return wrapper;
}

/* ── SyncActionPanel ─────────────────────────────────────────── */

function renderSyncActions(preview) {
  const panel = document.createElement("div");
  panel.className = "sync-panel";

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Synchronisation";
  panel.append(eye);

  const w = state.withings || {};
  const g = state.garmin || {};
  const decision = preview?.decision;

  if (!w.connected || !g.token_valid) {
    const msg = document.createElement("p");
    msg.className = "sync-message";
    msg.textContent = "Connecte Withings et Garmin dans les Réglages pour pouvoir synchroniser.";
    panel.append(msg);
    return panel;
  }

  if (!preview || preview.status !== "ready") {
    const msg = document.createElement("p");
    msg.className = "sync-message";
    msg.textContent = preview?.message || "Prévisualisation indisponible.";
    panel.append(msg);
    return panel;
  }

  const msg = document.createElement("p");
  msg.className = "sync-message";
  msg.textContent = decision?.message || "Les données affichées seront envoyées à Garmin Connect.";
  panel.append(msg);

  const actions = document.createElement("div");
  actions.className = "actions";

  const syncBtn = document.createElement("button");
  syncBtn.textContent = "Synchroniser cette mesure";
  syncBtn.disabled = !decision?.can_sync;
  if (!decision?.can_sync) syncBtn.title = "Aucune nouvelle mesure à synchroniser.";
  syncBtn.addEventListener("click", async () => {
    syncBtn.disabled = true;
    syncBtn.textContent = "Synchronisation en cours…";
    state.syncResult = null;
    render(); // will clear old result

    try {
      const today = getLocalDate();
      const result = await api("/api/sync/run", {
        method: "POST",
        body: JSON.stringify({ start_date: today, end_date: today, timezone: "Europe/Paris" }),
      });
      state.syncResult = result;
      await safeRefresh();
      // Re-fetch preview
      try { state.preview = await api("/api/measurements/latest?days=30"); } catch {}
    } catch (err) {
      state.syncResult = { error: err.message };
    }
    render();
  });
  actions.append(syncBtn);

  // Secondary buttons
  const refreshBtn = btn("Rafraîchir les mesures", async () => {
    try {
      state.preview = null;
      render();
      state.preview = await api("/api/measurements/latest?days=30");
      state.recent = await api("/api/measurements/recent?days=30");
    } catch {}
    render();
  }, "secondary");
  actions.append(refreshBtn);

  panel.append(actions);

  // Period selection
  const periodBar = document.createElement("div");
  periodBar.style.marginTop = "12px";
  periodBar.style.display = "flex";
  periodBar.style.flexWrap = "wrap";
  periodBar.style.gap = "8px";
  periodBar.style.alignItems = "center";

  const periodLabel = document.createElement("span");
  periodLabel.style.color = "var(--muted)";
  periodLabel.style.fontSize = "12px";
  periodLabel.textContent = "Choisir une période :";
  periodBar.append(periodLabel);

  const quickBtns = [
    ["Aujourd'hui", 1],
    ["7 jours", 7],
    ["30 jours", 30],
  ];
  for (const [label, days] of quickBtns) {
    const b = btn(label, async () => {
      const end = getLocalDate();
      const start = new Date(Date.now() - (days - 1) * 86400000);
      const sy = start.getFullYear();
      const sm = String(start.getMonth() + 1).padStart(2, "0");
      const sd = String(start.getDate()).padStart(2, "0");
      const startStr = `${sy}-${sm}-${sd}`;

      try {
        const result = await api("/api/sync/run", {
          method: "POST",
          body: JSON.stringify({ start_date: startStr, end_date: end, timezone: "Europe/Paris" }),
        });
        state.syncResult = result;
        await safeRefresh();
        try { state.preview = await api("/api/measurements/latest?days=30"); } catch {}
      } catch (err) {
        state.syncResult = { error: err.message };
      }
      render();
    }, "secondary");
    periodBar.append(b);
  }

  panel.append(periodBar);

  return panel;
}

/* ── SyncResultCard ──────────────────────────────────────────── */

function renderSyncResult() {
  const r = state.syncResult;
  if (!r) return null;

  const card = document.createElement("div");
  card.className = "sync-result";

  if (r.error) {
    const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Erreur de synchronisation";
    card.append(eye);
    const err = document.createElement("p");
    err.style.color = "var(--red)";
    err.style.fontSize = "14px";
    err.textContent = r.error;
    card.append(err);
    card.append(technicalAccordion("Détails techniques", r));
    return card;
  }

  const summary = r.summary || {};

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Résultat de la synchronisation";
  card.append(eye);

  const sumDiv = document.createElement("div");
  sumDiv.className = "sr-summary";

  const stats = [
    ["Synchronisées", summary.synced_count, ""],
    ["Doublons", summary.skipped_existing_count, "warn"],
    ["Conflits", summary.conflicts_count, "warn"],
    ["Invalides", summary.invalid_count, "bad"],
    ["Échecs", summary.failed_count, "bad"],
  ];

  for (const [label, val, cls] of stats) {
    const stat = document.createElement("div");
    stat.className = `sr-stat ${cls}`;
    const strong = document.createElement("strong");
    strong.textContent = val != null ? String(val) : "0";
    stat.append(strong);
    const span = document.createElement("span");
    span.textContent = label;
    stat.append(span);
    sumDiv.append(stat);
  }
  card.append(sumDiv);

  // Candidates detail
  if (r.candidates && r.candidates.length > 0) {
    const list = document.createElement("div");
    list.style.marginTop = "12px";
    for (const c of r.candidates) {
      const item = document.createElement("div");
      item.style.padding = "6px 0";
      item.style.borderBottom = "1px solid var(--line)";
      item.style.fontSize = "13px";
      item.style.color = "var(--muted)";

      const date = c.measured_at_local || c.date || "";
      const weight = c.mapped_fields?.weight != null ? `${c.mapped_fields.weight} kg` : "";
      const statusLabel = c.decision === "synced" ? "✅ synchronisé" :
                          c.decision === "skipped_existing" ? "⏭ déjà présent" :
                          c.decision === "skipped_conflict" ? "⚠ conflit" :
                          c.decision === "failed" ? "❌ échec" :
                          c.decision === "invalid" ? "⛔ invalide" : c.decision;
      item.textContent = `${date} — ${weight} — ${statusLabel}`;
      if (c.reason) {
        const reason = document.createElement("div");
        reason.style.color = "var(--amber)";
        reason.style.fontSize = "11px";
        reason.textContent = c.reason;
        item.append(reason);
      }
      list.append(item);
    }
    card.append(list);
  }

  // Technical details
  card.append(technicalAccordion("Voir détails techniques", r));

  return card;
}

/* ── Dashboard ───────────────────────────────────────────────── */

function renderDashboard() {
  const view = document.createElement("div");

  // 1. Status bar
  view.append(renderStatusBar());

  // 2. Latest measurement card
  if (state.preview) {
    view.append(renderLatestMeasurement(state.preview));
  } else {
    const w = state.withings || {};
    const g = state.garmin || {};
    if (!w.connected || !g.token_valid) {
      view.append(emptyState(
        "Configuration requise",
        w.connected ? "Garmin n'est pas encore prêt. Va dans Réglages." : "Connecte Withings dans les Réglages pour récupérer tes mesures.",
        link("Ouvrir les réglages", "/reglages")
      ));
    } else {
      view.append(loadingState("Chargement des mesures…"));
    }
  }

  // 3. Sparkline
  if (state.recent && state.recent.items && state.recent.items.length >= 2) {
    view.append(renderSparkline(state.recent.items));
  } else if (state.preview?.status === "ready") {
    // Show empty sparkline placeholder
    const wrap = document.createElement("div");
    wrap.className = "sparkline-wrapper";
    const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Évolution récente";
    wrap.append(eye);
    wrap.append(emptyState("Données insuffisantes", "Au moins 2 mesures sont nécessaires pour le graphique."));
    view.append(wrap);
  }

  // 4. Mapping table
  if (state.preview && state.preview.status === "ready") {
    view.append(renderMappingTable(state.preview));
  }

  // 5. Sync actions
  if (state.preview && state.preview.status === "ready") {
    view.append(renderSyncActions(state.preview));
  }

  // 6. Sync result
  const syncRes = renderSyncResult();
  if (syncRes) view.append(syncRes);

  return view;
}

/* ── Dashboard data loading ──────────────────────────────────── */

async function loadDashboardData() {
  const w = state.withings || {};
  const g = state.garmin || {};
  if (!w.connected || !g.token_valid) return;

  try {
    state.preview = await api("/api/measurements/latest?days=30");
  } catch { state.preview = null; }

  try {
    state.recent = await api("/api/measurements/recent?days=30");
  } catch { state.recent = null; }

  render();
}

/* ── Historique ──────────────────────────────────────────────── */

function renderHistorique() {
  const view = document.createElement("div");

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Mesures récentes";
  view.append(eye);
  const h = document.createElement("h1");
  h.textContent = "Historique des mesures";
  view.append(h);

  const p = state.preview;
  const w = state.withings || {};

  if (!w.connected) {
    view.append(emptyState("Withings non connecté", "Connecte Withings dans les Réglages pour voir l'historique.", link("Ouvrir les réglages", "/reglages")));
    return view;
  }

  const recent = state.recent;
  if (!recent || !recent.items || recent.items.length === 0) {
    view.append(emptyState("Aucune mesure", "Aucune mesure Withings trouvée pour la période récente."));
    if (state.preview?.latest_measurement) {
      // We have at least one measurement via preview
    } else {
      view.append(btn("Rafraîchir", async () => {
        try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}
        render();
      }, "secondary"));
    }
    return view;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "history-table-wrapper";

  const table = document.createElement("table");
  table.className = "history-table";
  table.innerHTML = `<thead><tr>
    <th>Date</th>
    <th>Poids</th>
    <th>Masse grasse</th>
    <th>Statut Garmin</th>
    <th>Décision</th>
  </tr></thead><tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  // Get dedup info from preview if available
  const dedupStatus = state.preview?.deduplication?.status || "unknown";

  for (const item of (recent.items || []).reverse()) {
    const row = document.createElement("tr");
    const dt = item.measured_at ? new Date(item.measured_at).toLocaleString("fr-FR", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
    row.innerHTML = `
      <td>${dt}</td>
      <td>${item.weight_kg != null ? item.weight_kg.toFixed(1) + " kg" : "—"}</td>
      <td>${item.fat_percent != null ? item.fat_percent.toFixed(1) + " %" : "—"}</td>
      <td><span class="badge">non vérifié</span></td>
      <td><span class="field-decision">—</span></td>
    `;
    tbody.append(row);
  }

  wrapper.append(table);
  view.append(wrapper);

  const refreshBtn = btn("Rafraîchir les mesures", async () => {
    try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}
    render();
  }, "secondary");
  refreshBtn.style.marginTop = "12px";
  view.append(refreshBtn);

  return view;
}

/* ── Réglages ────────────────────────────────────────────────── */

function renderReglages() {
  const view = document.createElement("div");

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Configuration";
  view.append(eye);
  const h = document.createElement("h1");
  h.textContent = "Réglages";
  view.append(h);

  const grid = document.createElement("div");
  grid.className = "settings-grid";

  // ── Withings card ────────────────────────────────────────────
  const wCard = document.createElement("div");
  wCard.className = "settings-card";

  const w = state.withings || {};
  const wCfg = state.withingsConfig || {};

  const wHead = document.createElement("div");
  wHead.className = "card-head";
  const wTitle = document.createElement("h2");
  wTitle.textContent = "Withings";
  const wBadge = document.createElement("span");
  wBadge.className = `badge ${badgeClass(Boolean(w.connected), Boolean(wCfg.configured && !w.connected))}`;
  wBadge.textContent = w.connected ? "connecté" : (wCfg.configured ? "non connecté" : "non configuré");
  wHead.append(wTitle, wBadge);
  wCard.append(wHead);

  const wSub = document.createElement("p");
  wSub.className = "sc-subtitle";
  wSub.textContent = "Withings fournit les mesures de poids et composition corporelle.";
  wCard.append(wSub);

  const wMsg = document.createElement("p");
  wMsg.className = "sc-info";
  wMsg.textContent = w.message || "Configure puis connecte Withings pour commencer.";
  wCard.append(wMsg);

  const wActions = document.createElement("div");
  wActions.className = "actions";

  if (wCfg.configured) {
    wActions.append(link("Connecter Withings", "/api/withings/auth/start", "button"));
    wActions.append(btn("Vérifier", async () => {
      try {
        const r = await api("/api/withings/auth/test", { method: "POST", body: "{}" });
        state.withings = { ...state.withings, ...r };
        render();
      } catch (e) {
        alert(e.message);
      }
    }, "secondary"));
    if (w.connected) {
      wActions.append(btn("Déconnecter", async () => {
        await api("/api/withings/auth/disconnect", { method: "POST", body: "{}" });
        await safeRefresh();
        render();
      }, "danger"));
    }
  } else {
    wActions.append(btn("Configurer", () => {
      // Open form inline
      const existing = wCard.querySelector(".withings-setup");
      if (existing) { existing.classList.toggle("hidden"); return; }
      const form = document.createElement("div");
      form.className = "withings-setup form";
      form.style.marginTop = "12px";
      form.innerHTML = `
        <label>Client ID Withings<input id="w-client-id" autocomplete="off" /></label>
        <label>Client Secret Withings<input id="w-client-secret" type="password" autocomplete="off" /></label>
        <div class="actions">
          <button id="w-save-config">Enregistrer</button>
          <a class="button secondary" href="https://developer.withings.com/dashboard/" target="_blank" rel="noreferrer">Dashboard Withings</a>
        </div>
        <textarea id="w-config-output" readonly style="min-height:60px"></textarea>
      `;
      wCard.append(form);
      form.querySelector("#w-save-config").addEventListener("click", async () => {
        const out = form.querySelector("#w-config-output");
        try {
          const result = await api("/api/withings/auth/config", {
            method: "POST",
            body: JSON.stringify({
              client_id: form.querySelector("#w-client-id").value,
              client_secret: form.querySelector("#w-client-secret").value,
              redirect_uri: `${location.origin}/api/withings/auth/callback`,
              scope: "user.metrics",
            }),
          });
          out.value = "Configuration enregistrée. Clique sur Connecter Withings.";
          await safeRefresh();
          render();
        } catch (err) { out.value = err.message; }
      });
    }, "secondary"));
  }
  wCard.append(wActions);

  // Technical details
  const wTech = document.createElement("details");
  wTech.className = "technical-details";
  wTech.innerHTML = `<summary>Détails techniques</summary>
    <div class="tech-content"><pre>Redirect URI: ${wCfg.redirect_uri || "—"}
Scope: ${wCfg.scope || "—"}
Configuré: ${wCfg.configured ? "oui" : "non"}
Token présent: ${w.connected ? "oui" : "non"}
Dernière vérification: ${w.message || "—"}</pre></div>`;
  wCard.append(wTech);

  grid.append(wCard);

  // ── Garmin card ──────────────────────────────────────────────
  const gCard = document.createElement("div");
  gCard.className = "settings-card";

  const g = state.garmin || {};

  const gHead = document.createElement("div");
  gHead.className = "card-head";
  const gTitle = document.createElement("h2");
  gTitle.textContent = "Garmin Connect";
  const gBadge = document.createElement("span");
  gBadge.className = `badge ${badgeClass(g.token_valid, g.token_found)}`;
  gBadge.textContent = g.token_valid ? "prêt" : (g.token_found ? "invalide" : "non configuré");
  gHead.append(gTitle, gBadge);
  gCard.append(gHead);

  const gSub = document.createElement("p");
  gSub.className = "sc-subtitle";
  gSub.textContent = "Garmin prêt pour recevoir les mesures corporelles.";
  gCard.append(gSub);

  const gMsg = document.createElement("p");
  gMsg.className = "sc-info";
  gMsg.textContent = g.token_valid
    ? "Token Garmin valide. L'écriture des mesures corporelles est disponible."
    : (g.message || "Connecte Garmin pour activer la synchronisation.");
  gCard.append(gMsg);

  const gActions = document.createElement("div");
  gActions.className = "actions";

  gActions.append(btn("Vérifier", async () => {
    try {
      const r = await api("/api/garmin/auth/verify", { method: "POST", body: "{}" });
      state.garmin = { ...state.garmin, ...r };
      render();
    } catch (e) { alert(e.message); }
  }, "button"));

  if (!g.token_valid) {
    // Login form
    const loginForm = document.createElement("div");
    loginForm.className = "form";
    loginForm.style.marginTop = "12px";
    loginForm.innerHTML = `
      <label>Email Garmin<input id="g-email" autocomplete="username" /></label>
      <label>Mot de passe<input id="g-pass" type="password" autocomplete="current-password" /></label>
      <label>Code OTP (si MFA)<input id="g-otp" autocomplete="one-time-code" /></label>
      <div class="actions">
        <button id="g-login-btn">Connecter Garmin</button>
        <button id="g-assisted-btn" class="secondary">Assisté</button>
      </div>
      <textarea id="g-output" readonly style="min-height:60px"></textarea>
    `;
    gCard.append(loginForm);

    setTimeout(() => {
      $("#g-login-btn")?.addEventListener("click", async () => {
        const out = $("#g-output");
        try {
          const r = await api("/api/garmin/auth/login", {
            method: "POST",
            body: JSON.stringify({
              email: $("#g-email").value || null,
              password: $("#g-pass").value || null,
              otp: $("#g-otp").value || null,
            }),
          });
          out.value = r.message || JSON.stringify(r, null, 2);
          await safeRefresh();
          render();
        } catch (e) { out.value = e.message; }
      });
      $("#g-assisted-btn")?.addEventListener("click", async () => {
        const out = $("#g-output");
        try {
          const r = await api("/api/garmin/auth/reauthenticate", { method: "POST", body: "{}" });
          out.value = r.command ? `Exécute cette commande dans ton terminal :\n${r.command.join(" ")}` : (r.message || JSON.stringify(r, null, 2));
        } catch (e) { out.value = e.message; }
      });
    }, 0);
  }

  if (g.token_found) {
    gActions.append(btn("Déconnecter", async () => {
      if (!confirm("Supprimer les tokens Garmin locaux ?")) return;
      try {
        await api("/api/garmin/auth/disconnect", { method: "POST", body: JSON.stringify({ confirm: true }) });
        await safeRefresh();
        render();
      } catch (e) { alert(e.message); }
    }, "danger"));
  }

  gCard.append(gActions);

  // Technical details
  const gTech = document.createElement("details");
  gTech.className = "technical-details";
  const techInfo = {
    "Méthode": "Taxuspt/garmin_mcp",
    "État token": g.state || "unknown",
    "Token présent": g.token_found ? "oui" : "non",
    "Token valide": g.token_valid ? "oui" : "non",
    "Dossier tokens": g.token_dir || "—",
    "Message": g.message || "—",
  };
  gTech.innerHTML = `<summary>Détails techniques</summary>
    <div class="tech-content"><pre>${Object.entries(techInfo).map(([k, v]) => `${k}: ${v}`).join("\n")}</pre></div>`;

  // API link
  const apiLink = document.createElement("a");
  apiLink.href = "/docs";
  apiLink.target = "_blank";
  apiLink.rel = "noreferrer";
  apiLink.className = "button secondary";
  apiLink.textContent = "API";
  apiLink.style.marginTop = "12px";
  gTech.append(apiLink);

  gCard.append(gTech);

  grid.append(gCard);

  view.append(grid);
  return view;
}

/* ── Logs ────────────────────────────────────────────────────── */

function renderLogs() {
  const view = document.createElement("div");

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Observabilité";
  view.append(eye);
  const h = document.createElement("h1");
  h.textContent = "Logs";
  view.append(h);

  const wrapper = document.createElement("div");
  wrapper.className = "mapping-table-wrapper";

  const actions = document.createElement("div");
  actions.className = "actions";
  const logNames = ["backend", "withings", "garmin", "sync", "security"];
  for (const name of logNames) {
    const b = btn(name, async () => {
      const out = wrapper.querySelector(".log-content");
      try {
        const result = await api(`/api/logs/${name}`);
        out.textContent = (result.lines || []).join("\n") || "Aucun log.";
      } catch (err) { out.textContent = `Erreur : ${err.message}`; }
    }, "secondary");
    actions.append(b);
  }
  wrapper.append(actions);

  const logDiv = document.createElement("div");
  logDiv.className = "log-content tech-content";
  logDiv.style.marginTop = "12px";
  logDiv.textContent = "Clique sur un service pour afficher les logs.";
  wrapper.append(logDiv);

  view.append(wrapper);
  return view;
}

/* ── Main render ─────────────────────────────────────────────── */

function render() {
  const view = $("#view");
  view.innerHTML = "";

  // Handle legacy redirect params
  if (state.route === "dashboard") {
    const params = new URLSearchParams(location.search);
    if (params.get("withings_auth") === "success") {
      state.route = "reglages";
      history.replaceState({}, "", "/reglages");
    }
  }

  switch (state.route) {
    case "historique":
      view.append(renderHistorique());
      break;
    case "reglages":
      view.append(renderReglages());
      break;
    case "logs":
      view.append(renderLogs());
      break;
    default:
      view.append(renderDashboard());
      break;
  }
}

/* ── SPA click handler ───────────────────────────────────────── */

document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-route]");
  if (!anchor) return;
  event.preventDefault();
  setRoute(anchor.dataset.route);
});

window.addEventListener("popstate", () => setRoute(routeFromPath(), false));

/* ── Bootstrap ───────────────────────────────────────────────── */

(async function boot() {
  await safeRefresh();

  // Check legacy redirects
  const params = new URLSearchParams(location.search);
  const initialRoute = routeFromPath();
  if (params.get("withings_auth") === "success") {
    // Will show reglages via render()
  }

  setRoute(initialRoute, false);

  // Load dashboard data in background
  if (initialRoute === "dashboard" || location.pathname === "/") {
    loadDashboardData();
  } else if (initialRoute === "historique") {
    // Preload recent for history
    try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}
    render();
  }
})();

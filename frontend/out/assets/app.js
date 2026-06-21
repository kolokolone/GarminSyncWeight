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
    ["Métabo. basal", lm.basal_metabolic_rate_kcal, "kcal"],
    ["Âge métabo.", lm.metabolic_age, "ans"],
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

  // Subtitle context
  const sub = document.createElement("p");
  sub.style.color = "var(--muted)";
  sub.style.fontSize = "12px";
  sub.style.marginTop = "4px";
  sub.textContent = items.length >= 30 ? "30 derniers jours" : `${items.length} dernières mesures`;
  wrapper.append(sub);

  if (!items || items.length < 2) {
    const empty = document.createElement("div");
    empty.className = "sparkline-empty";
    empty.textContent = "Pas assez de données pour afficher le graphique.";
    wrapper.append(empty);
    return wrapper;
  }

  const W = 600, H = 180, PAD = 20, LABEL_W = 60;
  const values = items.map((i) => i.weight_kg).filter((v) => v != null);
  const dates = items.filter((i) => i.weight_kg != null).map((i) => i.measured_at);
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

  function x(i) { return PAD + (i / (values.length - 1)) * (W - PAD - LABEL_W); }
  function y(v) { return H - PAD - ((v - min) / range) * (H - 2 * PAD); }

  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const firstVal = values[0];
  const lastVal = values[values.length - 1];
  const lastX = x(values.length - 1);
  const lastY = y(lastVal);

  // ── Create SVG ──────────────────────────────────────────────
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.className = "sparkline-svg";

  // Gradient definition
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const grad = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
  grad.id = "weightGradient";
  grad.setAttribute("x1", "0"); grad.setAttribute("y1", "0");
  grad.setAttribute("x2", "0"); grad.setAttribute("y2", "1");
  const stop1 = document.createElementNS("http://www.w3.org/2000/svg", "stop");
  stop1.setAttribute("offset", "0%");
  stop1.setAttribute("stop-color", "var(--green)");
  stop1.setAttribute("stop-opacity", "0.35");
  const stop2 = document.createElementNS("http://www.w3.org/2000/svg", "stop");
  stop2.setAttribute("offset", "100%");
  stop2.setAttribute("stop-color", "var(--green)");
  stop2.setAttribute("stop-opacity", "0.02");
  grad.append(stop1, stop2);
  defs.append(grad);
  svg.append(defs);

  // Area fill (with gradient)
  const area = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  const areaPts = `${x(0)},${y(firstVal)} ${pts} ${lastX},${H - PAD} ${x(0)},${H - PAD}`;
  area.setAttribute("points", areaPts);
  area.setAttribute("fill", "url(#weightGradient)");
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

  // Points on every data value + hover
  for (let i = 0; i < values.length; i++) {
    const cx = x(i), cy = y(values[i]);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(cx));
    circle.setAttribute("cy", String(cy));
    circle.setAttribute("r", "3.5");
    circle.setAttribute("fill", "var(--green)");
    circle.setAttribute("stroke", "rgba(7,17,14,0.9)");
    circle.setAttribute("stroke-width", "2");
    circle.setAttribute("class", "sparkline-point");
    circle.setAttribute("data-idx", String(i));

    // Hover tooltip via mouseenter/leave on wrapper
    circle.addEventListener("mouseenter", (e) => {
      const dt = dates[i] ? new Date(dates[i]).toLocaleString("fr-FR", {
        day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      }) : "";
      showSparklineTooltip(wrapper, e, dt, values[i]);
    });
    circle.addEventListener("mouseleave", () => hideSparklineTooltip(wrapper));
    // Also mark this as last-point special
    if (i === values.length - 1) {
      circle.setAttribute("r", "5");
      circle.setAttribute("class", "sparkline-point is-active");
    }
    svg.append(circle);
  }

  // Last value label — placed to the right with enough room
  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", String(W - 4));
  label.setAttribute("y", String(lastY));
  label.setAttribute("fill", "var(--green)");
  label.setAttribute("font-size", "14");
  label.setAttribute("font-weight", "800");
  label.setAttribute("text-anchor", "end");
  label.setAttribute("dominant-baseline", "middle");
  label.textContent = `${lastVal.toFixed(1)} kg`;
  svg.append(label);

  // Min value label (discreet)
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  if (minVal !== lastVal) {
    const minLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    minLabel.setAttribute("x", String(PAD));
    minLabel.setAttribute("y", String(y(minVal) - 8));
    minLabel.setAttribute("fill", "var(--muted)");
    minLabel.setAttribute("font-size", "10");
    minLabel.setAttribute("font-weight", "600");
    minLabel.setAttribute("dominant-baseline", "middle");
    minLabel.textContent = `${minVal.toFixed(1)} min`;
    svg.append(minLabel);
  }
  if (maxVal !== lastVal && maxVal !== minVal) {
    const maxLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    maxLabel.setAttribute("x", String(PAD));
    maxLabel.setAttribute("y", String(y(maxVal) + 14));
    maxLabel.setAttribute("fill", "var(--muted)");
    maxLabel.setAttribute("font-size", "10");
    maxLabel.setAttribute("font-weight", "600");
    maxLabel.setAttribute("dominant-baseline", "middle");
    maxLabel.textContent = `${maxVal.toFixed(1)} max`;
    svg.append(maxLabel);
  }

  wrapper.append(svg);
  return wrapper;
}

/* ── Sparkline tooltip helpers ───────────────────────────────── */

function showSparklineTooltip(wrapper, event, dateStr, weight) {
  let tip = wrapper.querySelector(".sparkline-tooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "sparkline-tooltip";
    wrapper.appendChild(tip);
  }
  const rect = wrapper.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  tip.innerHTML = `<strong>${weight.toFixed(1)} kg</strong> · ${dateStr}`;
  tip.style.left = x + "px";
  tip.style.top = Math.max(y - 50, 8) + "px";
}

function hideSparklineTooltip(wrapper) {
  const tip = wrapper.querySelector(".sparkline-tooltip");
  if (tip) tip.remove();
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
    const details = document.createElement("details");
    details.className = "dedup-warnings";
    details.style.marginTop = "12px";
    const summary = document.createElement("summary");
    const count = preview.warnings.length;
    summary.textContent = `⚠ ${count} avertissement${count > 1 ? "s" : ""}`;
    details.append(summary);
    for (const w of preview.warnings) {
      const p = document.createElement("p");
      p.style.color = "var(--amber)";
      p.style.fontSize = "12px";
      p.style.margin = "4px 0 4px 16px";
      p.textContent = w;
      details.append(p);
    }
    wrapper.append(details);
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

  // ── Two-column grid ──────────────────────────────────────────
  const grid = document.createElement("div");
  grid.className = "sync-actions-grid";

  // ── Block A: Dernière mesure ─────────────────────────────────
  const blockA = document.createElement("div");
  blockA.className = "sync-action-block";

  const aTitle = document.createElement("div");
  aTitle.style.fontSize = "15px";
  aTitle.style.fontWeight = "700";
  aTitle.style.marginBottom = "6px";
  aTitle.textContent = "Dernière mesure";
  blockA.append(aTitle);

  const aDesc = document.createElement("p");
  aDesc.style.color = "var(--muted)";
  aDesc.style.fontSize = "13px";
  aDesc.style.margin = "0 0 12px";
  aDesc.textContent = decision?.message || "Synchronise uniquement la mesure affichée en haut du dashboard.";
  blockA.append(aDesc);

  const syncBtn = document.createElement("button");
  syncBtn.textContent = "Synchroniser cette mesure";
  syncBtn.disabled = !decision?.can_sync;
  if (!decision?.can_sync) syncBtn.title = "Aucune nouvelle mesure à synchroniser.";
  syncBtn.addEventListener("click", () => runSync("latest"));
  blockA.append(syncBtn);

  grid.append(blockA);

  // ── Block B: Période ─────────────────────────────────────────
  const blockB = document.createElement("div");
  blockB.className = "sync-action-block";

  const bTitle = document.createElement("div");
  bTitle.style.fontSize = "15px";
  bTitle.style.fontWeight = "700";
  bTitle.style.marginBottom = "6px";
  bTitle.textContent = "Période";
  blockB.append(bTitle);

  const bDesc = document.createElement("p");
  bDesc.style.color = "var(--muted)";
  bDesc.style.fontSize = "13px";
  bDesc.style.margin = "0 0 10px";
  bDesc.textContent = "Choisis une période, puis lance la synchronisation.";
  blockB.append(bDesc);

  // Period picker (pills, selection only — no auto sync)
  const picker = document.createElement("div");
  picker.className = "period-picker";

  if (!state._periodDays) state._periodDays = 1;
  const periodOpts = [
    ["Aujourd'hui", 1],
    ["7 jours", 7],
    ["30 jours", 30],
  ];
  for (const [label, days] of periodOpts) {
    const pill = document.createElement("button");
    pill.className = "period-pill";
    if (state._periodDays === days) pill.classList.add("is-active");
    pill.textContent = label;
    pill.addEventListener("click", () => {
      state._periodDays = days;
      // Re-render just the sync panel area
      const parent = panel.parentElement;
      if (parent) {
        const idx = Array.from(parent.children).indexOf(panel);
        // Find our position and re-render
        render();
      } else {
        render();
      }
    });
    picker.append(pill);
  }
  blockB.append(picker);

  // Period date summary
  const periodSummary = document.createElement("div");
  periodSummary.className = "sync-period-summary";
  const pEnd = getLocalDate();
  const pStart = new Date(Date.now() - (state._periodDays - 1) * 86400000);
  const pStartStr = pStart.toISOString().slice(0, 10);
  const fmt = (s) => { const d = new Date(s + "T00:00:00"); return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }); };
  periodSummary.textContent = `Période sélectionnée : ${fmt(pStartStr)} → ${fmt(pEnd)}`;
  blockB.append(periodSummary);

  const periodSyncBtn = document.createElement("button");
  periodSyncBtn.className = "secondary";
  periodSyncBtn.textContent = "Synchroniser la période";
  periodSyncBtn.style.marginTop = "12px";
  periodSyncBtn.addEventListener("click", () => runSync("period"));
  blockB.append(periodSyncBtn);

  grid.append(blockB);
  panel.append(grid);

  // Refresh button
  const refreshBtn = btn("Rafraîchir les mesures", async () => {
    try {
      state.preview = null;
      render();
      state.preview = await api("/api/measurements/latest?days=30");
      state.recent = await api("/api/measurements/recent?days=30");
    } catch {}
    render();
  }, "secondary");
  refreshBtn.style.marginTop = "14px";
  panel.append(refreshBtn);

  return panel;
}

/* ── Sync execution with progress bar ───────────────────────── */

let _syncRunning = false;

async function runSync(mode) {
  if (_syncRunning) return;
  _syncRunning = true;
  state.syncResult = null;
  state._showProgress = true;
  render();

  try {
    let startDate, endDate;
    if (mode === "latest") {
      const previewDate = state.preview?.latest_measurement?.measured_at;
      startDate = previewDate ? previewDate.slice(0, 10) : getLocalDate();
      endDate = startDate;
    } else {
      endDate = getLocalDate();
      const days = state._periodDays || 1;
      const s = new Date(Date.now() - (days - 1) * 86400000);
      startDate = s.toISOString().slice(0, 10);
    }

    const result = await api("/api/sync/run", {
      method: "POST",
      body: JSON.stringify({ start_date: startDate, end_date: endDate, timezone: "Europe/Paris" }),
    });
    state.syncResult = result;
    await safeRefresh();
    try { state.preview = await api("/api/measurements/latest?days=30"); } catch {}
    try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}
  } catch (err) {
    state.syncResult = { error: err.message };
  }

  state._showProgress = false;
  _syncRunning = false;
  render();
}

/* ── Sync progress bar ──────────────────────────────────────── */

function renderProgressBar() {
  if (!state._showProgress) return null;

  const wrap = document.createElement("div");
  wrap.className = "progress-wrap";

  const bar = document.createElement("div");
  bar.className = "progress-bar";
  wrap.append(bar);

  const text = document.createElement("div");
  text.className = "sync-loading-text";
  text.textContent = "Synchronisation en cours…";
  wrap.append(text);

  return wrap;
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
      const decisionMeta = {
        synced: { cls: "will_sync", txt: "Synchronisé" },
        skipped_existing: { cls: "ignored", txt: "Déjà présent" },
        skipped_conflict: { cls: "conflict", txt: "Conflit" },
        failed: { cls: "conflict", txt: "Échec" },
        invalid: { cls: "absent", txt: "Invalide" },
      };
      const meta = decisionMeta[c.decision] || { cls: "absent", txt: c.decision };
      const badge = document.createElement("span");
      badge.className = `field-decision ${meta.cls}`;
      badge.textContent = meta.txt;
      const line = document.createElement("div");
      line.style.display = "flex";
      line.style.alignItems = "center";
      line.style.gap = "8px";
      line.style.padding = "6px 0";
      line.style.borderBottom = "1px solid var(--line)";
      line.style.fontSize = "13px";
      line.style.color = "var(--muted)";
      const textSpan = document.createElement("span");
      textSpan.textContent = `${date} — ${weight}`;
      line.append(textSpan, badge);
      item.append(line);
      if (c.reason) {
        const reason = document.createElement("div");
        reason.style.color = "var(--amber)";
        reason.style.fontSize = "11px";
        reason.style.marginLeft = "8px";
        reason.style.marginBottom = "6px";
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

  // 5b. Progress bar during sync
  const prog = renderProgressBar();
  if (prog) view.append(prog);

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

  // Session cache: skip refetch if fetched < 10s ago
  const now = Date.now();
  const CACHE_TTL = 10000;
  if (state._dashboardFetchedAt && (now - state._dashboardFetchedAt) < CACHE_TTL) {
    // stale enough to refetch in background?
    // For now, just skip to avoid flash re-renders during fast nav
    return;
  }

  const [previewResult, recentResult] = await Promise.allSettled([
    api("/api/measurements/latest?days=30"),
    api("/api/measurements/recent?days=30"),
  ]);

  if (previewResult.status === "fulfilled") state.preview = previewResult.value;
  else state.preview = null;

  if (recentResult.status === "fulfilled") state.recent = recentResult.value;
  else state.recent = null;

  state._dashboardFetchedAt = Date.now();
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

  const w = state.withings || {};

  // Auto-load history data on first visit
  if (state._historyItems === undefined && state._historyLoading !== true && w.connected) {
    state._historyLoading = true;
    loadHistory().then(() => { try { render(); } catch(e) {} }).catch(() => {});
  }

  if (!w.connected) {
    view.append(emptyState("Withings non connecté", "Connecte Withings dans les Réglages pour voir l'historique.", link("Ouvrir les réglages", "/reglages")));
    return view;
  }

  // ── Load history data if not cached ─────────────────────────
  const items = state._historyItems;
  const summary = state._historySummary;
  const loading = state._historyLoading;

  // Summary bar
  if (summary && summary.count > 0) {
    const sumBar = document.createElement("div");
    sumBar.style.display = "flex";
    sumBar.style.flexWrap = "wrap";
    sumBar.style.gap = "12px";
    sumBar.style.marginBottom = "14px";
    sumBar.style.fontSize = "12px";
    sumBar.style.color = "var(--muted)";
    const parts = [];
    if (summary.new_count > 0) parts.push(`<span style="color:var(--green)">${summary.new_count} nouveau${summary.new_count > 1 ? "x" : ""}</span>`);
    if (summary.already_synced_count > 0) parts.push(`<span>${summary.already_synced_count} synchronisé${summary.already_synced_count > 1 ? "s" : ""}</span>`);
    if (summary.conflict_count > 0) parts.push(`<span style="color:var(--amber)">${summary.conflict_count} conflit${summary.conflict_count > 1 ? "s" : ""}</span>`);
    if (summary.failed_count > 0) parts.push(`<span style="color:var(--red)">${summary.failed_count} échec${summary.failed_count > 1 ? "s" : ""}</span>`);
    sumBar.innerHTML = parts.join(" · ");
    view.append(sumBar);
  }

  if (loading) {
    view.append(loadingState("Vérification des statuts Garmin…"));
  } else if (!items || items.length === 0) {
    view.append(emptyState("Aucune mesure", "Aucune mesure Withings trouvée pour la période récente."));
    if (state.preview?.latest_measurement) {
      // We have at least one measurement via preview — show refresh
    } else {
      const firstLoadBtn = btn("Charger l'historique", async () => {
        state._historyLoading = true;
        render();
        await loadHistory();
        render();
      }, "secondary");
      view.append(firstLoadBtn);
    }
  } else {
    // ── Table ──────────────────────────────────────────────────
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
      <th>Action</th>
    </tr></thead><tbody></tbody>`;
    const tbody = table.querySelector("tbody");

    // Status → UI badge mapping
    const garminStatusMap = {
      new: { cls: "status-badge is-new", txt: "Nouveau" },
      already_synced_by_garminsync: { cls: "status-badge is-synced", txt: "Synchronisé" },
      already_present: { cls: "status-badge is-duplicate", txt: "Déjà présent" },
      possible_duplicate: { cls: "status-badge is-duplicate", txt: "Doublon ?" },
      conflict_same_day: { cls: "status-badge is-conflict", txt: "Conflit" },
      failed: { cls: "status-badge is-failed", txt: "Échec" },
      unchecked: { cls: "status-badge", txt: "Non vérifié" },
    };
    const decisionMap = {
      ready_to_sync: { cls: "status-badge is-new", txt: "Prêt" },
      already_synced: { cls: "status-badge is-synced", txt: "Déjà synchronisé" },
      conflict: { cls: "status-badge is-warning", txt: "À vérifier" },
      failed: { cls: "status-badge is-failed", txt: "Échec" },
      unchecked: { cls: "status-badge", txt: "—" },
    };

    for (const item of items) {
      const row = document.createElement("tr");
      const dt = item.measured_at_local ? new Date(item.measured_at_local).toLocaleString("fr-FR", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
      const key = item.date || "";

      const gs = garminStatusMap[item.garmin_status] || garminStatusMap.unchecked;
      const ds = decisionMap[item.decision] || decisionMap.unchecked;

      row.innerHTML = `
        <td>${dt}</td>
        <td>${item.weight_kg != null ? item.weight_kg.toFixed(1) + " kg" : "—"}</td>
        <td>${item.fat_percent != null ? item.fat_percent.toFixed(1) + " %" : "—"}</td>
        <td><span class="${gs.cls}">${gs.txt}</span></td>
        <td><span class="${ds.cls}">${ds.txt}</span></td>
        <td><button class="btn-secondary" style="font-size:11px;padding:2px 8px">Sync</button></td>
      `;
      const syncBtn = row.querySelector("button");
      if (key) {
        syncBtn.addEventListener("click", async () => {
          if (_syncRunning) return;
          state.syncResult = null;
          state._showProgress = true;
          render();
          try {
            const result = await api("/api/sync/run", {
              method: "POST",
              body: JSON.stringify({ start_date: key, end_date: key, timezone: "Europe/Paris" }),
            });
            state.syncResult = result;
            await safeRefresh();
            try { state.preview = await api("/api/measurements/latest?days=30"); } catch {}
            // Refresh history
            await loadHistory();
          } catch (err) {
            state.syncResult = { error: err.message };
          }
          state._showProgress = false;
          render();
        });
      } else {
        syncBtn.disabled = true;
        syncBtn.title = "Date inconnue";
      }
      tbody.append(row);
    }

    wrapper.append(table);
    view.append(wrapper);
  }

  // ── Actions ──────────────────────────────────────────────────
  const actionRow = document.createElement("div");
  actionRow.className = "actions";

  const refreshBtn = btn("Vérifier les statuts Garmin", async () => {
    state._historyLoading = true;
    render();
    await loadHistory();
    render();
  }, "secondary");
  actionRow.append(refreshBtn);

  const loadBtn = btn("Rafraîchir les mesures", async () => {
    try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}
    state._historyItems = null;
    state._historySummary = null;
    render();
  }, "secondary");
  actionRow.append(loadBtn);

  view.append(actionRow);

  return view;
}

/* ── History data loader ─────────────────────────────────────── */

async function loadHistory() {
  try {
    state._historyLoading = true;
    const res = await api("/api/measurements/history?days=30&include_garmin_status=true");
    state._historyItems = res.items || [];
    state._historySummary = res.summary || null;
    state._historyLoading = false;
    state._historyFetchedAt = Date.now();
    return res;
  } catch (err) {
    state._historyItems = [];
    state._historySummary = null;
    state._historyLoading = false;
    console.error("History load failed:", err);
    return null;
  }
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
        // Auto-scroll to bottom
        out.scrollTop = out.scrollHeight;
      } catch (err) { out.textContent = `Erreur : ${err.message}`; }
    }, "secondary");
    actions.append(b);
  }
  wrapper.append(actions);

  const logDiv = document.createElement("div");
  logDiv.className = "log-content tech-content";
  logDiv.style.marginTop = "12px";
  logDiv.style.maxHeight = "60vh";
  logDiv.style.overflowY = "auto";
  logDiv.style.fontSize = "12px";
  logDiv.style.lineHeight = "1.5";
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
    case "historique": {
      const wrap = document.createElement("div");
      wrap.className = "secondary-page";
      wrap.append(renderHistorique());
      view.append(wrap);
      break;
    }
    case "reglages": {
      const wrap = document.createElement("div");
      wrap.className = "secondary-page";
      wrap.append(renderReglages());
      view.append(wrap);
      break;
    }
    case "logs": {
      const wrap = document.createElement("div");
      wrap.className = "secondary-page";
      wrap.append(renderLogs());
      view.append(wrap);
      break;
    }
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

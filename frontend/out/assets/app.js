/* GarminSyncWeight — Dashboard-centric frontend
 * Navigation: Dashboard / Historique / Réglages / Logs
 * Respecte UI_STYLE_GUIDE.md : fond sombre, cartes translucides,
 * badges arrondis, palette vert/noir/cyan.
 */

const state = {
  status: null, garmin: null, withings: null, withingsConfig: null,
  preview: null, recent: null, syncResult: null,
  page: "dashboard",
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

/* ── SPA routing (flat pages) ────────────────────────────────── */

const PAGE_URLS = {
  dashboard: "/",
  history: "/historique",
  stats: "/statistiques",
  settings: "/reglages",
  logs: "/logs",
};

const PATH_TO_PAGE = {
  "": "dashboard",
  "/": "dashboard",
  "dashboard": "dashboard",
  "historique": "history",
  "statistiques": "stats",
  "reglages": "settings",
  "logs": "logs",
};

const VALID_PAGES = ["dashboard", "history", "stats", "settings", "logs"];

function setRoute(page, push = true) {
  if (!VALID_PAGES.includes(page)) page = "dashboard";
  state.page = page;

  const href = PAGE_URLS[page] || "/";
  if (push) history.pushState({}, "", href);

  // Update nav link active state
  $$("[data-route]").forEach((el) =>
    el.classList.toggle("active", el.dataset.route === page)
  );

  render();
}

function routeFromPath() {
  const p = location.pathname.replace(/^\//, "").split("/").filter(Boolean);
  const key = p[0] || "/";
  return PATH_TO_PAGE[key] || "dashboard";
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

  // BMI calculé localement si Withings ne le fournit pas
  const lm = preview.latest_measurement;
  const localBmi = (() => {
    if (lm?.weight_kg == null) return null;
    const hCm = state._heightCm;
    if (hCm && hCm > 0) {
      const hM = hCm / 100;
      return Math.round((lm.weight_kg / (hM * hM)) * 10) / 10;
    }
    return null;
  })();

  for (const f of fields) {
    const row = document.createElement("tr");
    const label = document.createElement("td"); label.className = "field-label"; label.textContent = f.label;

    // Calcul local IMC si manquant
    let wvText = f.withings_value || "—";
    let gvText = f.garmin_value || "—";
    let status = f.status;
    let msg = f.message || statusLabels[f.status] || f.status;

    if (f.label === "IMC" && !f.withings_value && localBmi != null) {
      wvText = `${localBmi}`;
      gvText = wvText;
      status = "calculated";
      msg = "Calculé (taille + poids)";
    }

    const wv = document.createElement("td"); wv.className = "field-withings"; wv.textContent = wvText;
    const gv = document.createElement("td"); gv.className = "field-garmin"; gv.textContent = gvText;
    const dc = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `field-decision ${status}`;
    badge.textContent = msg;
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
    if (!w.connected) msg.textContent = "Connexion Withings absente — va dans Réglages.";
    else msg.textContent = "Connexion Garmin absente ou expirée — va dans Réglages.";
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

/* ── Sync execution with SSE streaming ───────────────────────── */

let _syncRunning = false;

async function runSync(mode) {
  if (_syncRunning) return;
  _syncRunning = true;
  state.syncResult = null;
  state._showProgress = true;
  state._syncLog = [];
  render();

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

  // Open SSE stream
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, timezone: "Europe/Paris" });
  const es = new EventSource(`/api/sync/stream?${params}`);

  let closed = false;

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      state._syncLog.push(data);

      if (data.type === "complete") {
        // Final progress — keep listening for the report event
        const parts = [];
        if (data.synced > 0) parts.push(`${data.synced} envoyée(s)`);
        if (data.existing > 0) parts.push(`${data.existing} déjà présent(es)`);
        if (data.conflicts > 0) parts.push(`${data.conflicts} conflit(s)`);
        if (data.invalid > 0) parts.push(`${data.invalid} invalide(s)`);
        if (data.failed > 0) parts.push(`${data.failed} échec(s)`);
        state._syncLog.push({ type: "info", message: `✅ Sync terminée : ${parts.join(", ") || "aucune mesure"}` });
        render();
      } else if (data.type === "report") {
        // Full report received — close and finish
        state.syncResult = data.report;
        es.close();
        closed = true;
        finishSync(startDate, endDate);
      } else if (data.type === "error") {
        state.syncResult = { error: data.message };
        state._syncLog.push({ type: "error", message: `❌ Erreur : ${data.message}` });
        es.close();
        closed = true;
        finishSync(startDate, endDate);
      } else if (data.type === "start") {
        state._syncLog.push({ type: "info", message: `🚀 Sync lancée : ${data.period}` });
        render();
      } else if (data.type === "parsed") {
        state._syncLog.push({ type: "info", message: `📊 ${data.count} mesures Withings parsées` });
        render();
      } else if (data.type === "garmin_fetched") {
        state._syncLog.push({ type: "info", message: `📡 ${data.weigh_ins} weigh-ins, ${data.body_comp} compositions Garmin chargées` });
        render();
      } else if (data.type === "candidate") {
        const idx = `${data.index}/${data.total}`;
        const labelMap = {
          synced: "✅ Nouvelle mesure envoyée à Garmin",
          skipped_existing: "⏭️ Mesure déjà synchronisée",
          skipped_conflict: "⚠️ Conflit : mesure Garmin existante différente",
          failed: "❌ Échec technique",
          invalid: "ℹ️ Mesure Withings incomplète ou invalide",
        };
        const label = labelMap[data.decision] || `ℹ️ ${data.decision}`;
        const w = data.weight_kg ? `${data.weight_kg} kg` : "—";
        state._syncLog.push({ type: "candidate", message: `[${idx}] ${data.date} — ${w} → ${label}` });
        render();
      }
    } catch (e) {
      // ignore parse errors
    }
  };

  es.onerror = () => {
    if (!closed) {
      closed = true;
      es.close();
      // Fallback: if we never got a report but the stream ended
      if (!state.syncResult) {
        state.syncResult = { error: "La connexion temps réel s'est interrompue." };
      }
      state._syncLog.push({ type: "error", message: "❌ Connexion SSE interrompue" });
      finishSync(startDate, endDate);
    }
  };

  // Safety timeout: close after 120s even if stream hasn't ended
  setTimeout(() => {
    if (!closed) {
      closed = true;
      es.close();
      if (!state.syncResult) {
        state.syncResult = { error: "Délai de synchronisation dépassé (120s)." };
      }
      finishSync(startDate, endDate);
    }
  }, 120000);
}

async function finishSync(startDate, endDate) {
  await safeRefresh();
  try { state.preview = await api("/api/measurements/latest?days=30"); } catch {}
  try { state.recent = await api("/api/measurements/recent?days=30"); } catch {}

  state._showProgress = false;
  _syncRunning = false;
  render();
  showToast("Sync terminée", state.syncResult?.error ? "Échec de la synchronisation" : "Synchronisation réussie", state.syncResult?.error ? "error" : "success");
}

/* ── Sync progress bar ──────────────────────────────────────── */

function renderProgressBar() {
  if (!state._showProgress) return null;

  const wrap = document.createElement("div");
  wrap.className = "progress-wrap";

  const track = document.createElement("div");
  track.className = "progress-track";

  const bar = document.createElement("div");
  bar.className = "progress-bar";
  track.append(bar);
  wrap.append(track);

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
    ["Nouvelle mesure envoyée à Garmin", summary.synced_count, ""],
    ["Mesure déjà synchronisée", summary.skipped_existing_count, "warn"],
    ["Conflit : mesure Garmin existante différente", summary.conflicts_count, "warn"],
    ["Mesure Withings incomplète ou invalide", summary.invalid_count, "bad"],
    ["Échec technique", summary.failed_count, "bad"],
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
        synced: { cls: "will_sync", txt: "Nouvelle mesure envoyée à Garmin" },
        skipped_existing: { cls: "ignored", txt: "Mesure déjà synchronisée" },
        skipped_conflict: { cls: "conflict", txt: "Conflit : mesure Garmin existante différente" },
        failed: { cls: "conflict", txt: "Échec technique" },
        invalid: { cls: "absent", txt: "Mesure Withings incomplète ou invalide" },
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

/* ── Sync log (SSE streaming) ───────────────────────────────── */

function renderSyncLog() {
  const log = state._syncLog;
  if (!log || log.length === 0) return null;

  const wrap = document.createElement("div");
  wrap.className = "sync-log-wrap";

  const head = document.createElement("div");
  head.style.display = "flex";
  head.style.justifyContent = "space-between";
  head.style.alignItems = "center";
  head.style.marginBottom = "6px";
  const title = document.createElement("span");
  title.style.fontSize = "11px";
  title.style.fontWeight = "700";
  title.style.textTransform = "uppercase";
  title.style.letterSpacing = ".08em";
  title.style.color = "var(--muted)";
  title.textContent = "Journal temps réel";
  head.append(title);

  const clearBtn = document.createElement("button");
  clearBtn.textContent = "×";
  clearBtn.style.background = "none";
  clearBtn.style.border = "none";
  clearBtn.style.color = "var(--muted)";
  clearBtn.style.cursor = "pointer";
  clearBtn.style.fontSize = "16px";
  clearBtn.style.padding = "0 4px";
  clearBtn.title = "Effacer le journal";
  clearBtn.addEventListener("click", () => {
    state._syncLog = [];
    render();
  });
  head.append(clearBtn);
  wrap.append(head);

  const box = document.createElement("div");
  box.className = "sync-log-box";
  box.style.maxHeight = "240px";
  box.style.overflowY = "auto";
  box.style.fontSize = "11px";
  box.style.lineHeight = "1.6";
  box.style.fontFamily = "Consolas, monospace";
  box.style.color = "#dcecdf";
  box.style.background = "rgba(0,0,0,.22)";
  box.style.borderRadius = "10px";
  box.style.padding = "10px 12px";

  for (const entry of log) {
    const line = document.createElement("div");
    if (entry.type === "candidate") {
      line.textContent = entry.message || "";
    } else if (entry.type === "error") {
      line.style.color = "var(--red)";
      line.textContent = entry.message || entry.error || "";
    } else if (entry.type === "info") {
      line.style.color = "var(--muted)";
      line.textContent = entry.message || "";
    } else if (entry.type === "start") {
      line.style.color = "var(--cyan)";
      line.textContent = `Sync : ${entry.period}`;
    } else if (entry.type === "parsed") {
      line.style.color = "var(--muted)";
      line.textContent = `${entry.count} mesures parsées`;
    } else if (entry.type === "garmin_fetched") {
      line.style.color = "var(--muted)";
      line.textContent = `Garmin : ${entry.weigh_ins} weigh-ins, ${entry.body_comp} compositions`;
    } else if (entry.type === "complete") {
      line.style.color = "var(--green)";
      const parts = [];
      if (entry.synced > 0) parts.push(`${entry.synced} envoyée(s)`);
      if (entry.existing > 0) parts.push(`${entry.existing} déjà présent(es)`);
      if (entry.conflicts > 0) parts.push(`${entry.conflicts} conflit(s)`);
      if (entry.invalid > 0) parts.push(`${entry.invalid} invalide(s)`);
      if (entry.failed > 0) parts.push(`${entry.failed} échec(s)`);
      line.textContent = `✅ Terminé : ${parts.join(", ") || "aucune mesure à traiter"}`;
    } else {
      line.textContent = JSON.stringify(entry);
    }
    box.append(line);

    // Auto-scroll to bottom
    box.scrollTop = box.scrollHeight;
  }
  wrap.append(box);
  return wrap;
}

/* ── Dashboard (2-column layout) ──────────────────────────────── */

function renderDashboard() {
  const view = document.createElement("div");

  // 1. Status bar (full width)
  view.append(renderStatusBar());

  const w = state.withings || {};
  const g = state.garmin || {};

  // If services not connected, show setup prompt
  if (!w.connected || !g.token_valid) {
    view.append(emptyState(
      "Configuration requise",
      w.connected ? "Garmin n'est pas encore prêt. Va dans Réglages." : "Connecte Withings dans les Réglages pour récupérer tes mesures.",
      link("Ouvrir les réglages", "/reglages")
    ));
    return view;
  }

  // Auto-load data if needed
  const needsLoad = state._dashboardFetchedAt == null
    || (Date.now() - state._dashboardFetchedAt) > 10000;
  if (needsLoad && !state._dashboardLoading && !state.preview) {
    loadDashboardData();
  }

  // Show loading state if still loading and no data
  if (state._dashboardLoading && !state.preview) {
    const loadView = loadingState("Chargement des mesures");
    view.append(loadView);
    if (state._dashboardFetchedAt != null && !state.preview) {
      const retryBtn = btn("Réessayer", async () => {
        state._dashboardFetchedAt = null;
        render();
        await loadDashboardData();
        render();
      }, "secondary");
      retryBtn.style.marginTop = "12px";
      view.append(retryBtn);
    }
    return view;
  }

  // ── Single column flow ────────────────────────────────────────
  const flow = document.createElement("div");
  flow.className = "dashboard-flow";

  // Compact preview + sparkline + compact history
  if (state.preview) {
    flow.append(renderCompactPreview(state.preview));
  }

  // Sparkline
  if (state.recent && state.recent.items) {
    flow.append(renderSparkline(state.recent.items));
  } else if (state.preview?.status === "ready") {
    const wrap = document.createElement("div");
    wrap.className = "sparkline-wrapper";
    const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Évolution récente";
    wrap.append(eye);
    wrap.append(emptyState("Données insuffisantes", "Au moins 2 mesures sont nécessaires pour le graphique."));
    flow.append(wrap);
  }

  // Mapping table
  if (state.preview && state.preview.status === "ready" && state.preview.field_mapping?.length) {
    flow.append(renderMappingTable(state.preview));
  }

  // Sync panel below mapping table
  if (state.preview && state.preview.status === "ready") {
    flow.append(renderCompactSyncPanel(state.preview));
  }

  // Progress bar during sync
  const prog = renderProgressBar();
  if (prog) flow.append(prog);

  // Sync result
  const syncRes = renderSyncResult();
  if (syncRes) flow.append(syncRes);

  // Sync log (SSE streaming)
  const syncLog = renderSyncLog();
  if (syncLog) flow.append(syncLog);

  view.append(flow);

  return view;
}

/* ── Compact preview (big weight + metric tiles) ─────────────── */

function renderCompactPreview(preview) {
  const lm = preview.latest_measurement;
  if (!lm) return null;

  const card = document.createElement("div");
  card.className = "compact-preview";

  // Head : eyebrow + device/date
  const head = document.createElement("div");
  head.className = "cp-head";
  const eye = document.createElement("p");
  eye.className = "eyebrow";
  eye.textContent = "Dernière mesure détectée";
  head.append(eye);
  const dev = document.createElement("div");
  dev.className = "cp-device";
  const dateStr = lm.measured_at
    ? new Date(lm.measured_at).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "date inconnue";
  dev.textContent = `${lm.device || "Body Cardio+"} · ${dateStr}`;
  head.append(dev);
  card.append(head);

  // Body row : weight (left) + metric tiles (right)
  const body = document.createElement("div");
  body.className = "cp-body";

  // Weight (big, left side)
  if (lm.weight_kg != null) {
    const w = document.createElement("div");
    w.className = "cp-weight";
    w.innerHTML = `${lm.weight_kg.toFixed(1)} <span class="cp-weight-unit">kg</span>`;
    body.append(w);
  }

  // Metric tiles (right side)
  if (lm.weight_kg != null) {
    const grid = document.createElement("div");
    grid.className = "metric-grid";

    const tiles = [];
    if (lm.fat_percent != null) tiles.push(["Masse grasse", lm.fat_percent, "%"]);
    if (lm.muscle_mass_kg != null) tiles.push(["Masse musculaire", lm.muscle_mass_kg, "kg"]);
    if (lm.bone_mass_kg != null) tiles.push(["Masse osseuse", lm.bone_mass_kg, "kg"]);

    // BMI : calcul local depuis la taille stockée + poids
    const hCm = state._heightCm;
    if (hCm && hCm > 0) {
      const hM = hCm / 100;
      const bmi = lm.weight_kg / (hM * hM);
      tiles.push(["IMC", Math.round(bmi * 10) / 10]);
    } else if (lm.bmi != null) {
      tiles.push(["IMC", lm.bmi]);
    }

    if (lm.basal_metabolic_rate_kcal != null) tiles.push(["Métabo. basal", lm.basal_metabolic_rate_kcal, "kcal"]);
    if (lm.metabolic_age != null) tiles.push(["Âge métabo.", lm.metabolic_age, "ans"]);
    if (lm.visceral_fat_rating != null) tiles.push(["Graisse viscérale", lm.visceral_fat_rating]);

    for (const [label, val, unit] of tiles) {
      grid.append(metricTile(label, val, unit));
    }
    body.append(grid);
  }

  card.append(body);

  // Tags (dedup status, decision)
  const tags = document.createElement("div");
  tags.className = "cp-tags";
  if (preview.deduplication) {
    const tag = document.createElement("span");
    tag.className = `cp-tag ${preview.decision?.can_sync ? 'ok' : (preview.deduplication.status === 'conflict' ? 'warn' : '')}`;
    tag.textContent = preview.deduplication.message || preview.deduplication.status;
    tags.append(tag);
  }
  if (preview.decision && !preview.decision.can_sync && preview.decision.status !== "blocked") {
    const tag = document.createElement("span");
    tag.className = "cp-tag warn";
    tag.textContent = preview.decision.message || "Non synchronisable";
    tags.append(tag);
  }
  card.append(tags);

  return card;
}

/* ── Compact history (last 10 items, inline) ─────────────────── */

function renderCompactHistory(items) {
  const wrapper = document.createElement("div");
  wrapper.className = "compact-history";

  const head = document.createElement("div");
  head.style.display = "flex";
  head.style.justifyContent = "space-between";
  head.style.alignItems = "center";
  head.style.marginBottom = "8px";

  const title = document.createElement("span");
  title.style.fontSize = "12px";
  title.style.fontWeight = "700";
  title.style.textTransform = "uppercase";
  title.style.letterSpacing = ".08em";
  title.style.color = "var(--muted)";
  title.textContent = "Mesures récentes";
  head.append(title);

  const count = document.createElement("span");
  count.style.fontSize = "11px";
  count.style.color = "var(--muted)";
  count.textContent = `${items.length} mesure${items.length > 1 ? "s" : ""}`;
  head.append(count);
  wrapper.append(head);

  // Limit to last 10 items
  const display = items.slice(-10);

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>
    <th>Date</th>
    <th>Poids</th>
    <th>MG</th>
    <th>Statut</th>
  </tr></thead><tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  const garminStatusMap = {
    new: { cls: "ok", txt: "Nouveau" },
    already_synced_by_garminsync: { cls: "ok", txt: "Sync" },
    already_present: { cls: "", txt: "Présent" },
    possible_duplicate: { cls: "warn", txt: "?" },
    conflict_same_day: { cls: "bad", txt: "Conflit" },
    failed: { cls: "bad", txt: "Échec" },
    unchecked: { cls: "", txt: "—" },
  };

  for (const item of display) {
    const row = document.createElement("tr");
    const dt = item.measured_at_local
      ? new Date(item.measured_at_local).toLocaleString("fr-FR", { day: "numeric", month: "short" })
      : "";
    const gs = garminStatusMap[item.garmin_status] || garminStatusMap.unchecked;
    row.innerHTML = `
      <td>${dt}</td>
      <td>${item.weight_kg != null ? item.weight_kg.toFixed(1) + " kg" : "—"}</td>
      <td>${item.fat_percent != null ? item.fat_percent.toFixed(1) + "%" : "—"}</td>
      <td><span style="color:var(--${gs.cls || 'muted'})">${gs.txt}</span></td>
    `;
    tbody.append(row);
  }
  wrapper.append(table);

  return wrapper;
}

/* ── Compact sync panel — deux sous-cartes ──────────────────── */

function renderCompactSyncPanel(preview) {
  const panel = document.createElement("div");
  panel.className = "sync-panel-compact";

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Synchronisation";
  panel.append(eye);

  const w = state.withings || {};
  const g = state.garmin || {};
  const decision = preview?.decision;

  if (!w.connected || !g.token_valid) {
    const msg = document.createElement("p");
    msg.className = "spc-info";
    if (!w.connected) msg.textContent = "Connexion Withings absente — va dans Réglages.";
    else msg.textContent = "Connexion Garmin absente ou expirée — va dans Réglages.";
    panel.append(msg);
    return panel;
  }

  if (!preview || preview.status !== "ready") {
    const msg = document.createElement("p");
    msg.className = "spc-info";
    msg.textContent = preview?.message || "Prévisualisation indisponible.";
    panel.append(msg);
    return panel;
  }

  // ── Two-column grid ──────────────────────────────────────
  const grid = document.createElement("div");
  grid.className = "sync-actions-grid";

  // ── Block A: Dernière mesure ─────────────────────────────
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
  aDesc.textContent = decision?.message || "Synchronise uniquement la mesure affichée en haut.";
  blockA.append(aDesc);

  const syncBtn = document.createElement("button");
  syncBtn.textContent = "Synchroniser cette mesure";
  syncBtn.disabled = !decision?.can_sync;
  if (!decision?.can_sync) syncBtn.title = "Aucune nouvelle mesure à synchroniser.";
  syncBtn.addEventListener("click", () => runSync("latest"));
  blockA.append(syncBtn);

  grid.append(blockA);

  // ── Block B: Période ─────────────────────────────────────
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

  // Period picker (pills)
  const picker = document.createElement("div");
  picker.className = "period-picker";

  if (!state._periodDays) state._periodDays = 1;
  const periodOpts = [
    ["1j", 1],
    ["7j", 7],
    ["30j", 30],
  ];
  for (const [label, days] of periodOpts) {
    const pill = document.createElement("button");
    pill.className = "period-pill";
    if (state._periodDays === days) pill.classList.add("is-active");
    pill.textContent = label;
    pill.addEventListener("click", () => {
      state._periodDays = days;
      render();
    });
    picker.append(pill);
  }
  blockB.append(picker);

  // Period summary
  const pEnd = getLocalDate();
  const pStart = new Date(Date.now() - (state._periodDays - 1) * 86400000);
  const pStartStr = pStart.toISOString().slice(0, 10);
  const fmt = (s) => { const d = new Date(s + "T00:00:00"); return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }); };
  const periodSummary = document.createElement("div");
  periodSummary.className = "sync-period-summary";
  periodSummary.textContent = `Période sélectionnée : ${fmt(pStartStr)} → ${fmt(pEnd)}`;
  blockB.append(periodSummary);

  const periodSyncBtn = document.createElement("button");
  periodSyncBtn.textContent = "Synchroniser la période";
  periodSyncBtn.style.marginTop = "10px";
  periodSyncBtn.addEventListener("click", () => runSync("period"));
  blockB.append(periodSyncBtn);

  grid.append(blockB);
  panel.append(grid);

  // Footer : last sync + manual + refresh
  const s = state.status || {};
  const footer = document.createElement("div");
  footer.style.marginTop = "14px";
  footer.style.paddingTop = "14px";
  footer.style.borderTop = "1px solid var(--line)";
  footer.style.fontSize = "12px";
  footer.style.color = "var(--muted)";
  footer.style.display = "flex";
  footer.style.flexWrap = "wrap";
  footer.style.gap = "8px";
  footer.style.alignItems = "center";

  if (s.last_sync) {
    const syncDate = new Date(s.last_sync).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    const label = document.createElement("span");
    label.textContent = `Dernière sync : ${syncDate}`;
    if (s.sync_count != null) label.textContent += ` · ${s.sync_count} mesure${s.sync_count > 1 ? "s" : ""}`;
    footer.append(label);
  }

  const manualBtn = document.createElement("button");
  manualBtn.className = "secondary";
  manualBtn.textContent = "+ Ajout manuel";
  manualBtn.style.fontSize = "12px";
  manualBtn.style.padding = "7px 12px";
  manualBtn.addEventListener("click", () => showManualModal());
  footer.append(manualBtn);

  const refreshBtn = document.createElement("button");
  refreshBtn.className = "secondary";
  refreshBtn.textContent = "↻ Recharger";
  refreshBtn.style.fontSize = "12px";
  refreshBtn.style.padding = "7px 12px";
  refreshBtn.addEventListener("click", async () => {
    state._dashboardFetchedAt = null;
    render();
    await loadDashboardData();
    render();
  });
  footer.append(refreshBtn);

  panel.append(footer);
  return panel;
}

/* ── Manual measurement modal ─────────────────────────────────── */

function showManualModal() {
  // Remove existing modal if any
  const existing = document.querySelector(".manual-modal-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.className = "manual-modal-overlay";
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
  `;
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

  const modal = document.createElement("div");
  modal.style.cssText = `
    background: var(--bg); border: 1px solid var(--line);
    border-radius: 24px; padding: 28px; width: min(420px, 90vw);
    box-shadow: 0 32px 80px rgba(0,0,0,.45);
  `;

  const title = document.createElement("h2");
  title.style.margin = "0 0 18px";
  title.textContent = "Ajouter une mesure";
  modal.append(title);

  const form = document.createElement("div");
  form.className = "form";

  function field(labelText, id, type = "text", placeholder = "", attrs = {}) {
    const wrap = document.createElement("label");
    wrap.textContent = labelText;
    const input = document.createElement("input");
    input.id = id;
    input.type = type;
    if (placeholder) input.placeholder = placeholder;
    for (const [k, v] of Object.entries(attrs)) input[k] = v;
    wrap.append(input);
    return wrap;
  }

  form.append(field("Date", "mm-date", "date", "", { value: getLocalDate() }));
  form.append(field("Poids (kg)", "mm-weight", "number", "78.5", { step: "0.1", min: "20", max: "300" }));
  form.append(field("Masse grasse (%)", "mm-fat", "number", "22.0", { step: "0.1", min: "5", max: "70" }));
  form.append(field("Masse musculaire (kg)", "mm-muscle", "number", "", { step: "0.1" }));
  form.append(field("Note", "mm-note", "text", "Optionnel"));

  const actions = document.createElement("div");
  actions.className = "actions";

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Enregistrer";
  saveBtn.addEventListener("click", async () => {
    const payload = {
      date: document.getElementById("mm-date")?.value || getLocalDate(),
      weight_kg: parseFloat(document.getElementById("mm-weight")?.value) || null,
      fat_percent: parseFloat(document.getElementById("mm-fat")?.value) || null,
      muscle_mass_kg: parseFloat(document.getElementById("mm-muscle")?.value) || null,
      bone_mass_kg: null,
      note: document.getElementById("mm-note")?.value || null,
    };
    if (!payload.weight_kg && !payload.fat_percent) {
      showToast("Erreur", "Au moins le poids ou le % de masse grasse est requis.", "error");
      return;
    }
    try {
      const result = await api("/api/measurements/manual", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Mesure ajoutée", `${payload.weight_kg || "—"} kg enregistré.`, "success");
      overlay.remove();
      // Refresh dashboard
      state.preview = null;
      state.recent = null;
      render();
      loadDashboardData();
    } catch (err) {
      showToast("Erreur", err.message, "error");
    }
  });
  actions.append(saveBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "secondary";
  cancelBtn.textContent = "Annuler";
  cancelBtn.addEventListener("click", () => overlay.remove());
  actions.append(cancelBtn);

  form.append(actions);
  modal.append(form);
  overlay.append(modal);
  document.body.append(overlay);

  // Focus weight field
  setTimeout(() => document.getElementById("mm-weight")?.focus(), 100);
}

/* ── Dashboard data loading ──────────────────────────────────── */

async function loadDashboardData() {
  if (state._dashboardLoading) return;
  const w = state.withings || {};
  const g = state.garmin || {};

  // Si les services ne sont pas prêts, on ne bloque pas l'affichage
  if (!w.connected || !g.token_valid) {
    // Nettoyer tout état bloqué
    state._dashboardLoading = false;
    state._dashboardFetchedAt = Date.now();
    render();
    return;
  }

  state._dashboardLoading = true;

  // Session cache: skip refetch if fetched < 10s ago
  const now = Date.now();
  const CACHE_TTL = 10000;
  if (state._dashboardFetchedAt && (now - state._dashboardFetchedAt) < CACHE_TTL) {
    state._dashboardLoading = false;
    return;
  }

  try {
    // Timeout de sécurité 15s pour éviter le blocage permanent
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 15000);

    const [previewResult, recentResult] = await Promise.allSettled([
      fetch("/api/measurements/latest?days=30", { signal: ac.signal }).then(r => r.json()),
      fetch("/api/measurements/recent?days=30", { signal: ac.signal }).then(r => r.json()),
    ]);

    clearTimeout(t);

    if (previewResult.status === "fulfilled") state.preview = previewResult.value;
    else state.preview = null;

    if (recentResult.status === "fulfilled") state.recent = recentResult.value;
    else state.recent = null;

    state._dashboardFetchedAt = Date.now();
  } catch (e) {
    // AbortController peut jeter, on ignore
    state.preview = null;
    state.recent = null;
    state._dashboardFetchedAt = Date.now();
  } finally {
    state._dashboardLoading = false;
    render();
  }
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
    view.append(loadingState("Vérification des statuts Garmin"));
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

  // ── Profil card (taille) ──────────────────────────────────────
  const pCard = document.createElement("div");
  pCard.className = "settings-card";

  const pHead = document.createElement("div");
  pHead.className = "card-head";
  const pTitle = document.createElement("h2");
  pTitle.textContent = "Profil";
  const pBadge = document.createElement("span");
  pBadge.className = "badge ok";
  pBadge.textContent = "local";
  pHead.append(pTitle, pBadge);
  pCard.append(pHead);

  const pSub = document.createElement("p");
  pSub.className = "sc-subtitle";
  pSub.textContent = "Utilisé pour le calcul contextuel de l'IMC et des métriques.";
  pCard.append(pSub);

  const pForm = document.createElement("div");
  pForm.className = "form";
  pForm.style.marginTop = "12px";

  const heightLabel = document.createElement("label");
  heightLabel.textContent = "Taille (cm)";
  const heightInput = document.createElement("input");
  heightInput.id = "settings-height";
  heightInput.type = "number";
  heightInput.step = "1";
  heightInput.min = "100";
  heightInput.max = "250";
  heightInput.placeholder = "175";
  heightInput.value = state._heightCm || "";
  heightInput.addEventListener("input", () => {
    state._heightCm = heightInput.value ? parseFloat(heightInput.value) : null;
    savePrefs();
  });
  heightLabel.append(heightInput);
  pForm.append(heightLabel);

  const weightLabel = document.createElement("label");
  weightLabel.textContent = "Poids objectif (kg)";
  const weightInput = document.createElement("input");
  weightInput.id = "settings-target-weight";
  weightInput.type = "number";
  weightInput.step = "0.1";
  weightInput.min = "40";
  weightInput.max = "200";
  weightInput.placeholder = "—";
  weightInput.value = state._targetWeightKg || "";
  weightInput.addEventListener("input", () => {
    state._targetWeightKg = weightInput.value ? parseFloat(weightInput.value) : null;
    savePrefs();
  });
  weightLabel.append(weightInput);
  pForm.append(weightLabel);

  pCard.append(pForm);
  grid.append(pCard);

  view.append(grid);
  view.append(renderPreferences());
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

  // Handle withings OAuth redirect
  const params = new URLSearchParams(location.search);
  if (params.get("withings_auth") === "success") {
    state.page = "settings";
    history.replaceState({}, "", "/reglages");
    $$("[data-route]").forEach((el) =>
      el.classList.toggle("active", el.dataset.route === "settings")
    );
    // Fall through to render settings
  }

  const page = state.page || "dashboard";

  switch (page) {
    case "history":
      view.append(renderHistorique());
      break;
    case "stats":
      view.append(renderStats());
      break;
    case "settings":
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
  const routeLink = event.target.closest("[data-route]");
  if (routeLink) {
    event.preventDefault();
    setRoute(routeLink.dataset.route);
    return;
  }
});

window.addEventListener("popstate", () => setRoute(routeFromPath(), false));

/* ── Statistiques ──────────────────────────────────────────────── */

function renderStats() {
  const view = document.createElement("div");

  const eye = document.createElement("p"); eye.className = "eyebrow"; eye.textContent = "Synthèse";
  view.append(eye);
  const h = document.createElement("h1");
  h.textContent = "Statistiques";
  view.append(h);

  // ── Load aggregated stats from /api/sync/stats ─────────────────
  const statsDiv = document.createElement("div");
  statsDiv.style.marginTop = "16px";

  (async () => {
    try {
      const data = await api("/api/sync/stats");

      // ── Overview cards ─────────────────────────────────────────
      const grid = document.createElement("div");
      grid.className = "grid three";

      const lastSync = data.last_sync
        ? new Date(data.last_sync).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
        : "—";

      const overviewCards = [
        ["Dernière sync", lastSync, ""],
        ["Tentatives réussies", data.successful_attempts != null ? String(data.successful_attempts) : "0", "ok"],
        ["Mesures envoyées", (data.cumulative?.synced_count ?? 0) > 0 ? String(data.cumulative.synced_count) : "0", ""],
      ];

      for (const [label, val, cls] of overviewCards) {
        const card = document.createElement("div");
        card.className = "safe-card";
        card.innerHTML = `<span>${label}</span><strong class="${cls}">${val}</strong>`;
        grid.append(card);
      }
      statsDiv.append(grid);

      // ── Cumulative stats grid ──────────────────────────────────
      const subTitle = document.createElement("p");
      subTitle.className = "eyebrow";
      subTitle.style.marginTop = "20px";
      subTitle.textContent = "Cumul toutes synchronisations";
      statsDiv.append(subTitle);

      const cumul = data.cumulative || {};
      const cumulGrid = document.createElement("div");
      cumulGrid.className = "grid three";
      cumulGrid.style.marginTop = "8px";

      const cumulItems = [
        ["Synchronisées", cumul.synced_count ?? 0, "ok"],
        ["Doublons", cumul.skipped_existing_count ?? 0, "warn"],
        ["Conflits", cumul.conflicts_count ?? 0, "warn"],
        ["Invalides", cumul.invalid_count ?? 0, "bad"],
        ["Échecs", cumul.failed_count ?? 0, "bad"],
        ["Candidates", cumul.candidates_count ?? 0, ""],
      ];
      for (const [label, val, cls] of cumulItems) {
        const card = document.createElement("div");
        card.className = "safe-card";
        card.innerHTML = `<span>${label}</span><strong class="${cls}">${String(val)}</strong>`;
        cumulGrid.append(card);
      }
      statsDiv.append(cumulGrid);

      // ── Latest sync detail ─────────────────────────────────────
      if (data.latest_summary) {
        const latestTitle = document.createElement("p");
        latestTitle.className = "eyebrow";
        latestTitle.style.marginTop = "20px";
        latestTitle.textContent = "Dernière synchronisation";
        statsDiv.append(latestTitle);

        const ls = data.latest_summary;
        const latestGrid = document.createElement("div");
        latestGrid.className = "grid three";
        latestGrid.style.marginTop = "8px";
        const latestItems = [
          ["Synchronisées", ls.synced_count ?? 0, "ok"],
          ["Doublons", ls.skipped_existing_count ?? 0, "warn"],
          ["Conflits", ls.conflicts_count ?? 0, "warn"],
          ["Invalides", ls.invalid_count ?? 0, "bad"],
          ["Échecs", ls.failed_count ?? 0, "bad"],
          ["Candidates", ls.candidates_count ?? 0, ""],
        ];
        for (const [label, val, cls] of latestItems) {
          const card = document.createElement("div");
          card.className = "safe-card";
          card.innerHTML = `<span>${label}</span><strong class="${cls}">${String(val)}</strong>`;
          latestGrid.append(card);
        }
        statsDiv.append(latestGrid);

        // ── Attempts summary ─────────────────────────────────────
        const attemptTitle = document.createElement("p");
        attemptTitle.className = "eyebrow";
        attemptTitle.style.marginTop = "20px";
        attemptTitle.textContent = "Tentatives de synchronisation";
        statsDiv.append(attemptTitle);

        const attemptGrid = document.createElement("div");
        attemptGrid.className = "grid three";
        attemptGrid.style.marginTop = "8px";
        const attemptItems = [
          ["Totale", data.total_attempts ?? 0, ""],
          ["Réussies", data.successful_attempts ?? 0, "ok"],
          ["Échouées", data.failed_attempts ?? 0, "bad"],
        ];
        for (const [label, val, cls] of attemptItems) {
          const card = document.createElement("div");
          card.className = "safe-card";
          card.innerHTML = `<span>${label}</span><strong class="${cls}">${String(val)}</strong>`;
          attemptGrid.append(card);
        }
        statsDiv.append(attemptGrid);
      } else {
        const note = document.createElement("p");
        note.style.color = "var(--muted)";
        note.style.fontSize = "14px";
        note.style.marginTop = "12px";
        note.textContent = "Aucune synchronisation effectuée pour le moment.";
        statsDiv.append(note);
      }

      // ── Raw data accordion ─────────────────────────────────────
      statsDiv.append(technicalAccordion("Données brutes", data));
    } catch {
      statsDiv.append(technicalAccordion("Statistiques", "Impossible de charger les statistiques."));
    }
  })();

  view.append(statsDiv);
  return view;
}

/* ── Preferences panel ──────────────────────────────────────────── */

function renderPreferences() {
  const card = document.createElement("div");
  card.className = "settings-card";
  card.style.marginTop = "18px";

  const head = document.createElement("div");
  head.className = "card-head";
  const title = document.createElement("h2");
  title.textContent = "Préférences";
  head.append(title);
  card.append(head);

  const sub = document.createElement("p");
  sub.className = "sc-subtitle";
  sub.textContent = "Sauvegardées automatiquement dans le navigateur.";
  card.append(sub);

  // Theme toggle
  const themeRow = document.createElement("div");
  themeRow.style.display = "flex";
  themeRow.style.alignItems = "center";
  themeRow.style.justifyContent = "space-between";
  themeRow.style.marginTop = "12px";
  themeRow.style.padding = "10px 0";
  themeRow.style.borderBottom = "1px solid var(--line)";

  const themeLabel = document.createElement("span");
  themeLabel.style.fontSize = "13px";
  themeLabel.textContent = "Thème sombre";
  themeRow.append(themeLabel);

  // Simple checkbox toggle
  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.checked = true; // always dark mode
  toggle.disabled = true;
  toggle.style.accentColor = "var(--green)";
  themeRow.append(toggle);
  card.append(themeRow);

  // Auto-refresh indicator
  const refreshRow = document.createElement("div");
  refreshRow.style.display = "flex";
  refreshRow.style.alignItems = "center";
  refreshRow.style.justifyContent = "space-between";
  refreshRow.style.padding = "10px 0";
  refreshRow.style.borderBottom = "1px solid var(--line)";

  const refreshLabel = document.createElement("span");
  refreshLabel.style.fontSize = "13px";
  refreshLabel.textContent = "Auto-refresh (30s)";
  refreshRow.append(refreshLabel);

  const refreshBadge = document.createElement("span");
  refreshBadge.className = "badge ok";
  refreshBadge.textContent = "Actif";
  refreshRow.append(refreshBadge);
  card.append(refreshRow);

  // Storage info
  const storageRow = document.createElement("div");
  storageRow.style.padding = "10px 0";
  storageRow.style.fontSize = "12px";
  storageRow.style.color = "var(--muted)";

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const prefs = JSON.parse(raw);
      const parts = [`période ${prefs._periodDays || 1}j`];
      if (prefs._heightCm) parts.push(`taille ${prefs._heightCm}cm`);
      if (prefs._targetWeightKg) parts.push(`objectif ${prefs._targetWeightKg}kg`);
      storageRow.textContent = `Préférences : ${parts.join(" · ")}`;
    } else {
      storageRow.textContent = "Aucune préférence sauvegardée.";
    }
  } catch {
    storageRow.textContent = "localStorage non disponible.";
  }
  card.append(storageRow);

  return card;
}

/* ── Toast system ──────────────────────────────────────────────── */

function ensureToastContainer() {
  let tc = document.querySelector(".toast-container");
  if (!tc) {
    tc = document.createElement("div");
    tc.className = "toast-container";
    document.body.append(tc);
  }
  return tc;
}

function showToast(title, msg = "", kind = "info", duration = 4000) {
  const tc = ensureToastContainer();
  const t = document.createElement("div");
  t.className = `toast toast-${kind}`;
  t.innerHTML = `<div class="toast-title">${title}</div>${msg ? `<div class="toast-msg">${msg}</div>` : ""}`;
  tc.append(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, duration);
}

/* ── localStorage persistence ──────────────────────────────────── */

const STORAGE_KEY = "garminsyncweight_prefs";

function savePrefs() {
  try {
    const prefs = {
      _periodDays: state._periodDays,
      _heightCm: state._heightCm,
      _targetWeightKg: state._targetWeightKg,
      theme: document.documentElement.getAttribute("data-theme"),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {}
}

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const prefs = JSON.parse(raw);
    if (prefs._periodDays != null) state._periodDays = prefs._periodDays;
    if (prefs._heightCm != null) state._heightCm = prefs._heightCm;
    if (prefs._targetWeightKg != null) state._targetWeightKg = prefs._targetWeightKg;
    if (prefs.theme) document.documentElement.setAttribute("data-theme", prefs.theme);
  } catch {}
}

/* ── Bootstrap ───────────────────────────────────────────────── */

(async function boot() {
  loadPrefs();
  await safeRefresh();

  // Check legacy redirects
  const params = new URLSearchParams(location.search);
  const initialRoute = routeFromPath();

  setRoute(initialRoute, false);

  // Load dashboard data in background
  if (state.page === "dashboard") {
    loadDashboardData();
  }

  // Auto-refresh every 30s on dashboard
  setInterval(() => {
    if (state.page === "dashboard") {
      loadDashboardData();
    }
  }, 30000);
})();

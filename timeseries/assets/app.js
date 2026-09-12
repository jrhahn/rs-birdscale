// Dashboard. No dependencies: one fetch loop, one canvas, and the three
// endpoints in ../src/web.rs.
//
// The chart draws what the API returns and nothing more -- a min/max band and
// the mean through it. That shape is the same whether the numbers came from the
// raw table or from a rollup view, which is the point of the rollups: zooming
// out changes the resolution, never the reading.

const RANGES = [
  { key: "1h", label: "1 h", ms: 3600e3 },
  { key: "6h", label: "6 h", ms: 6 * 3600e3 },
  { key: "24h", label: "24 h", ms: 24 * 3600e3 },
  { key: "7d", label: "7 T", ms: 7 * 24 * 3600e3 },
  { key: "30d", label: "30 T", ms: 30 * 24 * 3600e3 },
  { key: "1y", label: "1 J", ms: 365 * 24 * 3600e3 },
  { key: "3y", label: "3 J", ms: 3 * 365 * 24 * 3600e3 },
];

const REFRESH_MS = 30000;
const num = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

const state = {
  channels: [],
  selected: null, // { node, sensor }
  range: "24h",
  series: null,
  hover: null,
};

// What is on screen lives in the URL fragment: `#<node>/<sensor>/<range>`. A
// reload keeps the chart, and a chart worth showing someone is a link.
function readHash() {
  const [node, sensor, range] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (node && sensor) state.selected = { node, sensor };
  if (RANGES.some((r) => r.key === range)) state.range = range;
}

function writeHash() {
  if (!state.selected) return;
  const { node, sensor } = state.selected;
  const next = `#${encodeURIComponent(node)}/${encodeURIComponent(sensor)}/${state.range}`;
  if (location.hash !== next) history.replaceState(null, "", next);
}

const el = {
  sidebar: document.getElementById("sidebar"),
  ranges: document.getElementById("ranges"),
  title: document.getElementById("chart-title"),
  sub: document.getElementById("chart-sub"),
  foot: document.getElementById("chart-foot"),
  canvas: document.getElementById("chart"),
  tooltip: document.getElementById("tooltip"),
  health: document.getElementById("health"),
};

// --- data ------------------------------------------------------------------

async function getJSON(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || response.statusText);
  return body;
}

async function loadChannels() {
  try {
    state.channels = await getJSON("/api/channels");
  } catch (e) {
    el.sidebar.innerHTML = `<p class="hint error">Kanäle nicht abrufbar: ${escapeHtml(e.message)}</p>`;
    return;
  }
  if (!state.selected && state.channels.length) {
    const first = state.channels[0];
    state.selected = { node: first.node, sensor: first.sensor };
    loadSeries();
  }
  renderSidebar();
}

async function loadSeries() {
  if (!state.selected) return;
  writeHash();
  const range = RANGES.find((r) => r.key === state.range);
  const to = Date.now();
  const from = to - range.ms;
  const { node, sensor } = state.selected;
  const points = Math.max(200, Math.floor(el.canvas.clientWidth || 800));
  const query = new URLSearchParams({ node, sensor, from, to, points });
  el.foot.textContent = "Lade …";
  try {
    // `from`/`to` come back from the API, not from the request: the server
    // rounds the window out to whole buckets, and the axis has to match the
    // bars or the first and last one hang off the edge.
    state.series = await getJSON(`/api/series?${query}`);
    renderChart();
  } catch (e) {
    state.series = null;
    el.foot.innerHTML = `<span class="error">${escapeHtml(e.message)}</span>`;
    clearCanvas();
  }
}

async function loadHealth() {
  try {
    const h = await getJSON("/api/health");
    const dot = (ok) => `<span class="dot ${ok ? "up" : "down"}"></span>`;
    const retention = h.retention ? `Aufbewahrung ${h.retention}` : "ohne Verfall";
    el.health.innerHTML =
      `<span>${dot(h.broker_connected)}Broker</span>` +
      `<span>${dot(h.database_reachable)}QuestDB</span>` +
      `<span>${escapeHtml(retention)}, ${h.views.length} Rollups</span>` +
      `<span>${num.format(h.rows_written)} Zeilen geschrieben</span>`;
  } catch (e) {
    el.health.innerHTML = `<span class="error">${escapeHtml(e.message)}</span>`;
  }
}

// --- rendering -------------------------------------------------------------

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function channelLabel(c) {
  // The discovery payload's name already carries the node prefix in Home
  // Assistant, but here the node is the group heading, so the raw key is the
  // better fallback.
  return c.name || c.sensor;
}

function formatValue(c) {
  if (c.last_value === null || c.last_value === undefined) return "—";
  const unit = c.unit ? ` ${c.unit}` : "";
  return `${num.format(c.last_value)}${unit}`;
}

function renderSidebar() {
  if (!state.channels.length) {
    el.sidebar.innerHTML = `<p class="hint">Noch keine Kanäle. Sobald ein Knoten
      veröffentlicht, erscheint er hier.</p>`;
    return;
  }
  const byNode = new Map();
  for (const c of state.channels) {
    if (!byNode.has(c.node)) byNode.set(c.node, []);
    byNode.get(c.node).push(c);
  }

  const parts = [];
  for (const [node, channels] of byNode) {
    const nodeName = channels.find((c) => c.node_name)?.node_name || node;
    const online = channels.find((c) => c.online !== null && c.online !== undefined)?.online;
    const dot = online === undefined || online === null ? "" : `<span class="dot ${online ? "up" : "down"}"></span>`;
    parts.push(`<div class="node-name">${dot}${escapeHtml(nodeName)}</div>`);
    for (const c of channels) {
      const current =
        state.selected && state.selected.node === c.node && state.selected.sensor === c.sensor;
      const stale = c.last_at_ms && Date.now() - c.last_at_ms > 3600e3 ? " stale" : "";
      parts.push(
        `<button class="channel" aria-current="${current}" data-node="${escapeHtml(c.node)}"` +
          ` data-sensor="${escapeHtml(c.sensor)}">` +
          `<span>${escapeHtml(channelLabel(c))}</span>` +
          `<span class="value${stale}">${escapeHtml(formatValue(c))}</span>` +
          `</button>`,
      );
    }
  }
  el.sidebar.innerHTML = parts.join("");
  for (const button of el.sidebar.querySelectorAll("button.channel")) {
    button.addEventListener("click", () => {
      state.selected = { node: button.dataset.node, sensor: button.dataset.sensor };
      renderSidebar();
      loadSeries();
    });
  }
}

function renderRanges() {
  el.ranges.innerHTML = RANGES.map(
    (r) =>
      `<button data-range="${r.key}" aria-pressed="${r.key === state.range}">${r.label}</button>`,
  ).join("");
  for (const button of el.ranges.querySelectorAll("button")) {
    button.addEventListener("click", () => {
      state.range = button.dataset.range;
      renderRanges();
      loadSeries();
    });
  }
}

function selectedChannel() {
  if (!state.selected) return null;
  return (
    state.channels.find(
      (c) => c.node === state.selected.node && c.sensor === state.selected.sensor,
    ) || null
  );
}

function clearCanvas() {
  const ctx = el.canvas.getContext("2d");
  ctx.clearRect(0, 0, el.canvas.width, el.canvas.height);
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function niceTicks(lo, hi, count) {
  if (!isFinite(lo) || !isFinite(hi)) return [];
  if (lo === hi) return [lo];
  const raw = (hi - lo) / count;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) || magnitude * 10;
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step / 1e6; v += step) ticks.push(v);
  return ticks;
}

function formatTime(ms, spanMs) {
  const d = new Date(ms);
  if (spanMs <= 2 * 24 * 3600e3) {
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }
  if (spanMs <= 120 * 24 * 3600e3) {
    return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
  }
  return d.toLocaleDateString("de-DE", { month: "2-digit", year: "2-digit" });
}

function renderChart() {
  const channel = selectedChannel();
  const series = state.series;
  el.title.textContent = channel ? channelLabel(channel) : "Kein Kanal gewählt";
  el.sub.textContent = channel
    ? `${channel.node_name || channel.node} · ${channel.sensor}${channel.unit ? ` · ${channel.unit}` : ""}`
    : "";

  const canvas = el.canvas;
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  if (!series || !series.points.length) {
    el.foot.textContent = series ? "Keine Daten in diesem Zeitraum." : "";
    state.hover = null;
    return;
  }

  const pad = { left: 52, right: 12, top: 12, bottom: 26 };
  const plot = {
    x: pad.left,
    y: pad.top,
    w: Math.max(10, width - pad.left - pad.right),
    h: Math.max(10, height - pad.top - pad.bottom),
  };

  let lo = Infinity;
  let hi = -Infinity;
  for (const p of series.points) {
    lo = Math.min(lo, p.lo);
    hi = Math.max(hi, p.hi);
  }
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const headroom = (hi - lo) * 0.08;
  lo -= headroom;
  hi += headroom;

  const t0 = series.from;
  const t1 = series.to;
  const sx = (t) => plot.x + ((t - t0) / (t1 - t0)) * plot.w;
  const sy = (v) => plot.y + plot.h - ((v - lo) / (hi - lo)) * plot.h;

  const line = cssVar("--line");
  const muted = cssVar("--muted");
  const accent = cssVar("--accent");
  const band = cssVar("--band");

  // Horizontal grid + value axis.
  ctx.strokeStyle = line;
  ctx.fillStyle = muted;
  ctx.lineWidth = 1;
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const tick of niceTicks(lo, hi, 5)) {
    const y = Math.round(sy(tick)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(plot.x, y);
    ctx.lineTo(plot.x + plot.w, y);
    ctx.stroke();
    ctx.fillText(num.format(tick), plot.x - 8, y);
  }

  // Time axis. The outermost labels are anchored inwards, or half of the last
  // one hangs off the canvas and is clipped.
  ctx.textBaseline = "top";
  const steps = Math.max(2, Math.min(7, Math.floor(plot.w / 90)));
  for (let i = 0; i <= steps; i++) {
    const t = t0 + ((t1 - t0) * i) / steps;
    ctx.textAlign = i === 0 ? "left" : i === steps ? "right" : "center";
    ctx.fillText(formatTime(t, t1 - t0), sx(t), plot.y + plot.h + 6);
  }
  ctx.textAlign = "center";

  // min/max envelope.
  ctx.beginPath();
  series.points.forEach((p, i) => {
    const x = sx(p.t);
    i === 0 ? ctx.moveTo(x, sy(p.hi)) : ctx.lineTo(x, sy(p.hi));
  });
  for (let i = series.points.length - 1; i >= 0; i--) {
    const p = series.points[i];
    ctx.lineTo(sx(p.t), sy(p.lo));
  }
  ctx.closePath();
  ctx.fillStyle = band;
  ctx.fill();

  // Mean.
  ctx.beginPath();
  series.points.forEach((p, i) => {
    const x = sx(p.t);
    const y = sy(p.av);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = accent;
  ctx.lineWidth = 1.6;
  ctx.stroke();

  // Hover marker.
  if (state.hover) {
    const p = state.hover;
    ctx.strokeStyle = muted;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(sx(p.t)) + 0.5, plot.y);
    ctx.lineTo(Math.round(sx(p.t)) + 0.5, plot.y + plot.h);
    ctx.stroke();
    ctx.fillStyle = accent;
    ctx.beginPath();
    ctx.arc(sx(p.t), sy(p.av), 3, 0, Math.PI * 2);
    ctx.fill();
  }

  const unit = channel && channel.unit ? ` ${channel.unit}` : "";
  el.foot.textContent =
    `${series.points.length} Punkte à ${series.bucket} aus ${series.source}` +
    ` · Spanne ${num.format(lo + headroom)}${unit} … ${num.format(hi - headroom)}${unit}`;

  canvas._scale = { sx, sy, plot, t0, t1 };
}

// --- interaction -----------------------------------------------------------

el.canvas.addEventListener("mousemove", (event) => {
  const series = state.series;
  const scale = el.canvas._scale;
  if (!series || !series.points.length || !scale) return;
  const rect = el.canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const t = scale.t0 + ((x - scale.plot.x) / scale.plot.w) * (scale.t1 - scale.t0);

  let nearest = series.points[0];
  for (const p of series.points) {
    if (Math.abs(p.t - t) < Math.abs(nearest.t - t)) nearest = p;
  }
  state.hover = nearest;
  renderChart();

  const channel = selectedChannel();
  const unit = channel && channel.unit ? ` ${channel.unit}` : "";
  const when = new Date(nearest.t).toLocaleString("de-DE");
  el.tooltip.hidden = false;
  el.tooltip.innerHTML =
    `<strong>${num.format(nearest.av)}${escapeHtml(unit)}</strong><br />` +
    `min ${num.format(nearest.lo)} · max ${num.format(nearest.hi)}<br />` +
    `<span style="color:var(--muted)">${escapeHtml(when)}</span>`;
  const left = Math.min(scale.sx(nearest.t) + 12, rect.width - el.tooltip.offsetWidth - 6);
  el.tooltip.style.left = `${Math.max(0, left)}px`;
  el.tooltip.style.top = `${Math.max(0, scale.sy(nearest.av) - 46)}px`;
});

el.canvas.addEventListener("mouseleave", () => {
  state.hover = null;
  el.tooltip.hidden = true;
  renderChart();
});

window.addEventListener("resize", () => {
  if (state.series) renderChart();
});

// --- start -----------------------------------------------------------------

readHash();
renderRanges();
loadChannels();
loadHealth();
if (state.selected) loadSeries();
setInterval(() => {
  loadChannels();
  loadHealth();
  loadSeries();
}, REFRESH_MS);

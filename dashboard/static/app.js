/* Dashboard giám sát đường sắt — logic hiển thị, không phụ thuộc framework. */
"use strict";

// Ngưỡng cảnh báo theo loại cảm biến (có thể chỉnh theo thực tế)
const THRESHOLDS = {
  tilt:       { max: 8,  unit: "deg" },
  vibration:  { max: 10, unit: "mm/s" },
  water:      { max: 50, unit: "cm" },
  default:    { max: Infinity },
};

const REFRESH_MS = 3000;
let timer = null;

const $ = (id) => document.getElementById(id);

/* ---------- tiện ích ---------- */

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { hour12: false });
}

function levelFor(type, value) {
  const t = THRESHOLDS[type] || THRESHOLDS.default;
  if (value > t.max) return "danger";
  if (value > t.max * 0.8) return "warn";
  return "ok";
}

/* ---------- sparkline (canvas thuần) ---------- */

function drawSparkline(canvas, history) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!history || history.length < 2) {
    ctx.fillStyle = "#8296b8";
    ctx.font = "10px sans-serif";
    ctx.fillText("chưa đủ dữ liệu", 4, h - 4);
    return;
  }
  const vals = history.map((p) => Number(p.v));
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  ctx.beginPath();
  history.forEach((p, i) => {
    const x = (i / (history.length - 1)) * (w - 2) + 1;
    const y = h - 2 - ((Number(p.v) - min) / span) * (h - 6);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#4aa3f5";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

/* ---------- render ---------- */

function renderSensors(sensors) {
  const box = $("sensors");
  box.innerHTML = "";
  let alerting = 0;
  sensors.forEach((s) => {
    const level = levelFor(s.type, s.value);
    if (level === "danger") alerting += 1;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="sensor-head">
        <span class="sensor-id">${escapeHtml(s.sensor_id)}</span>
        <span class="pill ${level}">${level === "ok" ? "bình thường" : level === "warn" ? "gần ngưỡng" : "vượt ngưỡng"}</span>
      </div>
      <div class="sensor-type">${escapeHtml(s.type || "unknown")}</div>
      <div class="value">${fmtNum(s.value)} <small>${escapeHtml(s.unit || "")}</small></div>
      <div class="updated">cập nhật ${fmtTime(s.updated_at)}</div>
      <canvas></canvas>
    `;
    box.appendChild(card);
    drawSparkline(card.querySelector("canvas"), s.history);
  });
  if (sensors.length === 0) {
    box.innerHTML = '<div class="empty" style="color:var(--muted)">Chưa có dữ liệu cảm biến — đang chờ MQTT/API…</div>';
  }
  $("stat-sensors").textContent = sensors.length;
  $("stat-alerting").textContent = alerting;
}

function renderAlerts(alerts) {
  const ul = $("alerts");
  ul.innerHTML = "";
  if (alerts.length === 0) {
    ul.innerHTML = '<li class="empty">Chưa có cảnh báo</li>';
    return;
  }
  alerts.slice().reverse().forEach((a) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="t">${fmtTime(a.time)} · ${escapeHtml(a.sensor_id || "hệ thống")}</span>
      <span class="lv lv-${escapeHtml(a.level)}">[${escapeHtml(a.level)}]</span>
      ${escapeHtml(a.message)}
    `;
    ul.appendChild(li);
  });
  $("stat-alerts").textContent = alerts.length;
}

function renderDetections(detections) {
  const ul = $("detections");
  ul.innerHTML = "";
  if (detections.length === 0) {
    ul.innerHTML = '<li class="empty">Chưa có kết quả phát hiện</li>';
    return;
  }
  detections.slice().reverse().forEach((d) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="t">${fmtTime(d.time)} · ${escapeHtml(d.mode || "unknown")}</span>
      <span class="lv lv-${escapeHtml(d.severity)}">${escapeHtml(d.severity)}</span>
      ${escapeHtml(d.message || "")}
    `;
    ul.appendChild(li);
  });
  $("stat-detections").textContent = detections.length;
}

/* ---------- fetch ---------- */

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

async function refresh() {
  try {
    const [s, a, d] = await Promise.all([
      fetchJSON("/api/sensors"),
      fetchJSON("/api/alerts?limit=50"),
      fetchJSON("/api/detections?limit=50"),
    ]);
    renderSensors(s.sensors || []);
    renderAlerts(a.alerts || []);
    renderDetections(d.detections || []);
    setHealth("ok", "trực tuyến");
  } catch (err) {
    setHealth("err", "mất kết nối");
    console.error(err);
  }
}

function setHealth(cls, text) {
  const el = $("health");
  el.className = `badge ${cls}`;
  el.textContent = text;
}

/* ---------- khởi động ---------- */

function tickClock() {
  $("clock").textContent = new Date().toLocaleTimeString("vi-VN", { hour12: false });
}

$("refresh").addEventListener("click", () => {
  const btn = $("refresh");
  btn.classList.add("spinning");
  refresh().finally(() => btn.classList.remove("spinning"));
});

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("vi-VN", { maximumFractionDigits: 2 }) : "—";
}

tickClock();
setInterval(tickClock, 1000);
refresh();
timer = setInterval(refresh, REFRESH_MS);

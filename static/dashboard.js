const BASE = (document.querySelector('meta[name="app-base"]')?.content || "").replace(/\/$/, "");
const apiUrl = (path) => `${BASE}${path}`;

const COLORS = { keiko: "#3b82f6", sanchez: "#f97316", neutral: "#64748b", pending: "#334155" };
const GEO_TO_UBIGEO = {
  Amazonas: "010000",
  Ancash: "020000",
  "Apurímac": "030000",
  Arequipa: "040000",
  Ayacucho: "050000",
  Cajamarca: "060000",
  "El Callao": "240000",
  Callao: "240000",
  Cusco: "070000",
  Huancavelica: "080000",
  "Huánuco": "090000",
  Ica: "100000",
  "Junín": "110000",
  "La Libertad": "120000",
  Lambayeque: "130000",
  Lima: "140000",
  "Municipalidad Metropolitana de Lima": "140000",
  Loreto: "150000",
  "Madre de Dios": "160000",
  Moquegua: "170000",
  Pasco: "180000",
  Piura: "190000",
  Puno: "200000",
  "San Martín": "210000",
  Tacna: "220000",
  Tumbes: "230000",
  Ucayali: "250000",
};

let appData = null;
let viewMode = "real";
let selectedUbigeo = null;
let map = null;
let geoLayer = null;
let pollTimer = null;
let pollIntervalSec = 60;
let charts = {};

function fmt(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString("es-PE");
}
function fmtPct(n) {
  if (n == null) return "—";
  return `${Number(n).toFixed(2)}%`;
}
function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "medium" });
}
function shortName(n) {
  if (!n) return "—";
  const p = n.split(" ");
  return p.length >= 2 ? `${p[0]} ${p[1]}` : n;
}
function isKeiko(n) { return (n || "").toUpperCase().includes("FUJIMORI"); }
function candColor(n) { return isKeiko(n) ? COLORS.keiko : COLORS.sanchez; }

function getProcesamiento(r) { return r?.procesamiento || r?.actas || {}; }
function getMapa() { return appData?.proyeccion?.mapa || appData?.nacional?.proyeccion?.mapa || {}; }
function getProy() { return appData?.proyeccion || appData?.nacional?.proyeccion || {}; }
function getComp2021() { return appData?.comparacion_2021 || appData?.nacional?.comparacion_2021 || {}; }

function getDeptLeader(dept, mode) {
  if (!dept) return null;
  if (mode === "real") return dept.lider_real || dept.lider_departamento;
  if (mode === "proyectado") return dept.lider_proyectado || dept.lider_departamento;
  const ext = getProy().extranjero;
  if (!ext?.candidatos?.length) return dept.lider_proyectado;
  return ext.ganador_proyectado_con_extranjero;
}

function getDeptColor(dept, mode) {
  const leader = getDeptLeader(dept, mode);
  if (!leader) return COLORS.pending;
  return candColor(leader);
}

function setStatus(state, label, meta) {
  document.getElementById("statusDot").className = "status-dot " + state;
  document.getElementById("statusLabel").textContent = label;
  document.getElementById("statusMeta").textContent = meta;
}
function showAlert(msg) {
  const box = document.getElementById("alertBox");
  if (!msg) { box.classList.add("hidden"); return; }
  box.textContent = msg;
  box.classList.remove("hidden");
}

/* ── Mapa Leaflet ── */
async function initMap() {
  if (map) return;
  map = L.map("mapPeru", { scrollWheelZoom: true, zoomControl: true }).setView([-9.5, -75.5], 5);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OSM &copy; CARTO", maxZoom: 12,
  }).addTo(map);

  const resp = await fetch(apiUrl("/static/peru-departamentos.geojson"));
  const geo = await resp.json();

  geoLayer = L.geoJSON(geo, {
    style: (f) => styleFeature(f),
    onEachFeature: (f, layer) => {
      layer.on({
        click: () => selectRegion(featureUbigeo(f)),
        mouseover: (e) => e.target.setStyle({ weight: 2, fillOpacity: 0.85 }),
        mouseout: (e) => geoLayer.resetStyle(e.target),
      });
    },
  }).addTo(map);
  map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
  updateMapLegend();
}

function featureUbigeo(f) {
  return GEO_TO_UBIGEO[f.properties.shapeName] || null;
}

function styleFeature(f) {
  const ubigeo = featureUbigeo(f);
  const dept = getMapa()[ubigeo];
  const color = getDeptColor(dept, viewMode);
  const selected = ubigeo === selectedUbigeo;
  return {
    fillColor: color,
    weight: selected ? 3 : 1,
    opacity: 1,
    color: selected ? "#fff" : "rgba(255,255,255,0.25)",
    fillOpacity: dept ? 0.72 : 0.25,
  };
}

function refreshMapStyles() {
  if (!geoLayer) return;
  geoLayer.eachLayer((layer) => layer.setStyle(styleFeature(layer.feature)));
  updateMapLegend();
}

function updateMapLegend() {
  const labels = { real: "Resultado oficial", proyectado: "Proyección Perú", final: "Proyección + extranjero" };
  document.getElementById("mapLegend").innerHTML = `
    <span class="legend-item"><span class="legend-swatch" style="background:${COLORS.keiko}"></span>Keiko</span>
    <span class="legend-item"><span class="legend-swatch" style="background:${COLORS.sanchez}"></span>Sánchez</span>
    <span class="legend-mode">${labels[viewMode] || ""}</span>`;
}

function selectRegion(ubigeo) {
  selectedUbigeo = ubigeo;
  refreshMapStyles();
  renderRegionDetail(ubigeo);
}

/* ── Paneles ── */
function renderNationalSummary() {
  const proy = getProy();
  const ext = proy.extranjero || {};
  const n = appData.nacional || {};
  const cands = proy.candidatos || n.candidatos || [];

  let html = "";
  if (viewMode === "real") {
    html = summaryBlock("Líder oficial", shortName(proy.ganador_actual), proy.margen_actual_pct, cands, "porcentaje_actual", "votos_actuales");
  } else if (viewMode === "proyectado") {
    html = summaryBlock("Proyección Perú", shortName(proy.ganador_proyectado), proy.margen_proyectado_pct, cands, "porcentaje_proyectado", "votos_proyectados");
  } else {
    const ec = ext.candidatos || cands;
    html = summaryBlock("Proyección final", shortName(ext.ganador_proyectado_con_extranjero), ext.margen_con_extranjero_pct, ec, "porcentaje_proyectado_con_extranjero", "votos_proyectados_con_extranjero");
  }

  const proc = n.procesamiento || {};
  html += `<div class="mini-stats">
    <div><span>Votos contabilizados</span><strong>${fmt(proy.totales?.votos_actuales || n.total_votos)}</strong></div>
    <div><span>Actas procesadas</span><strong>${fmtPct(proc.porcentaje_contabilizadas || n.actas_sum?.porcentaje)}</strong></div>
    <div><span>Deptos. en conteo</span><strong>${proy.departamentos_en_conteo ?? "—"}</strong></div>
  </div>`;
  document.getElementById("nationalSummary").innerHTML = html;
}

function summaryBlock(title, leader, margin, cands, pctKey, votesKey) {
  const rows = cands.map((c) => `
    <div class="cand-row">
      <span class="cand-name" style="color:${candColor(c.nombre)}">${shortName(c.nombre)}</span>
      <span class="cand-pct">${fmtPct(c[pctKey])}</span>
      <span class="cand-votes">${fmt(c[votesKey])}</span>
    </div>`).join("");
  return `<p class="summary-label">${title}</p>
    <p class="summary-leader">${leader}</p>
    <p class="summary-margin">Margen: ${fmtPct(margin)}</p>
    <div class="cand-list">${rows}</div>`;
}

function renderExtranjeroSummary() {
  const ext = getProy().extranjero || {};
  if (!ext.activo) {
    document.getElementById("extranjeroSummary").innerHTML = "<p class='muted'>Sin datos</p>";
    return;
  }
  const modo = ext.modo === "real" ? "Datos reales ONPE" : "Estático (350k · 65/35)";
  const badge = ext.modo === "real" ? "badge ok" : "badge warn";
  document.getElementById("extranjeroSummary").innerHTML = `
    <p><span class="${badge}">${modo}</span></p>
    <p class="ext-nota">${ext.nota || ""}</p>
    <div class="mini-stats">
      <div><span>Votos extranjero</span><strong>${fmt(ext.votos_extranjero_total)}</strong></div>
      <div><span>Keiko</span><strong>${fmt(ext.votos_keiko_estimados)} (${fmtPct(ext.keiko_pct)})</strong></div>
      <div><span>Sánchez</span><strong>${fmt(ext.votos_sanchez_estimados)} (${fmtPct(ext.sanchez_pct)})</strong></div>
      <div><span>Ventaja Keiko</span><strong>+${fmt(ext.ventaja_neta_keiko)}</strong></div>
      <div><span>Actas ext.</span><strong>${fmt(ext.actas_extranjero_contabilizadas)} / ${fmt(ext.actas_extranjero_total)}</strong></div>
    </div>
    ${ext.cambia_ganador ? `<p class="impact-text">⚡ El extranjero invierte el ganador proyectado</p>` : ""}`;
}

function renderRegionDetail(ubigeo) {
  const card = document.getElementById("regionDetailCard");
  const dept = getMapa()[ubigeo];
  if (!dept) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  document.getElementById("regionDetailTitle").textContent = dept.region;

  const cands = (dept.candidatos || []).map((c) => {
    const pctProy = dept.votos_proyectados
      ? ((c.votos_proyectados / dept.votos_proyectados) * 100).toFixed(2)
      : "—";
    return `
    <div class="cand-row">
      <span>${shortName(c.nombre)}</span>
      <span>${fmtPct(c.pct_actual)} → ${pctProy !== "—" ? pctProy + "%" : "—"}</span>
    </div>
    <div class="cand-sub">${fmt(c.votos_actuales)} oficial · ${fmt(c.votos_proyectados)} proy.</div>`;
  }).join("");

  document.getElementById("regionDetail").innerHTML = `
    <div class="mini-stats">
      <div><span>Procesado</span><strong>${fmtPct(dept.pct_procesado)}</strong></div>
      <div><span>Actas pend.</span><strong>${fmt(dept.actas_pendientes)}</strong></div>
      <div><span>Líder oficial</span><strong style="color:${candColor(dept.lider_real)}">${shortName(dept.lider_real)}</strong></div>
      <div><span>Líder proyectado</span><strong style="color:${candColor(dept.lider_proyectado)}">${shortName(dept.lider_proyectado)}</strong></div>
    </div>
    <div class="cand-list" style="margin-top:.75rem">${cands}</div>`;
}

function renderTable() {
  const mapa = getMapa();
  const q = (document.getElementById("searchDepto")?.value || "").toLowerCase();
  const rows = Object.values(mapa)
    .filter((d) => !q || d.region.toLowerCase().includes(q))
    .map((d) => `<tr data-ubigeo="${d.ubigeo}" class="${d.ubigeo === selectedUbigeo ? "selected" : ""}">
      <td><strong>${d.region}</strong></td>
      <td>${fmt(d.votos_actuales)}</td>
      <td>${fmt(d.votos_proyectados)}</td>
      <td>${renderProcBar(d.pct_procesado)}</td>
      <td>${fmt(d.actas_total ? (d.actas_total - (d.actas_pendientes || 0)) : null)} / ${fmt(d.actas_total)}</td>
      <td style="color:${candColor(d.lider_real)}">${shortName(d.lider_real)}</td>
      <td style="color:${candColor(d.lider_proyectado)}">${shortName(d.lider_proyectado)}</td>
    </tr>`).join("");
  document.getElementById("tableBody").innerHTML = rows;
  document.querySelectorAll("#tableBody tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      selectRegion(tr.dataset.ubigeo);
      document.querySelector('[data-tab="general"]').click();
    });
  });
}

function renderProcBar(pct) {
  if (pct == null) return "—";
  return `<div class="proc-cell"><div class="proc-bar-mini"><span style="width:${Math.min(pct, 100)}%"></span></div><span class="proc-pct">${fmtPct(pct)}</span></div>`;
}

function renderAnalysis() {
  const proy = getProy();
  document.getElementById("analysisDisclaimer").textContent = proy.disclaimer || "";
  const ext = proy.extranjero || {};
  document.getElementById("analysisHero").innerHTML = `
    <article class="prediction-card"><span class="kpi-label">Oficial</span><span class="prediction-name">${shortName(proy.ganador_actual)}</span><span class="prediction-margin">${fmtPct(proy.margen_actual_pct)}</span></article>
    <article class="prediction-card secondary"><span class="kpi-label">Proy. Perú</span><span class="prediction-name">${shortName(proy.ganador_proyectado)}</span><span class="prediction-margin">${fmtPct(proy.margen_proyectado_pct)} · ${fmt(proy.diferencia_votos_proyectada)} votos</span></article>
    <article class="prediction-card ${ext.cambia_ganador ? "ext-flip" : "stats"}"><span class="kpi-label">Proy. final</span><span class="prediction-name">${shortName(ext.ganador_proyectado_con_extranjero)}</span><span class="prediction-margin">${fmtPct(ext.margen_con_extranjero_pct)} · ${fmt(ext.diferencia_votos_con_extranjero)} votos</span></article>`;

  renderChart("chartProyeccion", proy.candidatos, [
    { key: "porcentaje_actual", label: "Oficial", color: "rgba(100,116,139,0.8)" },
    { key: "porcentaje_proyectado", label: "Proyectado", color: "rgba(168,85,247,0.85)" },
  ]);
  const ec = ext.candidatos || [];
  renderChart("chartExtranjero", ec.length ? ec : proy.candidatos, [
    { key: "porcentaje_proyectado", label: "Solo Perú", color: "rgba(100,116,139,0.8)" },
    { key: "porcentaje_proyectado_con_extranjero", label: "+ Extranjero", color: "rgba(34,197,94,0.85)" },
  ], ec.length ? ec : proy.candidatos);

  const pend = proy.departamentos_pendientes || [];
  destroyChart("chartImpacto");
  if (pend.length) {
    const ctx = document.getElementById("chartImpacto");
    charts.chartImpacto = new Chart(ctx, {
      type: "bar",
      data: {
        labels: pend.slice(0, 12).map((d) => d.region),
        datasets: [{ label: "Votos pendientes est.", data: pend.slice(0, 12).map((d) => d.votos_pendientes_estimados), backgroundColor: "rgba(249,115,22,0.75)" }],
      },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });
  }
}

function renderChart(id, cands, datasets, source) {
  destroyChart(id);
  const data = source || cands;
  const ctx = document.getElementById(id);
  if (!ctx || !data?.length) return;
  charts[id] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((c) => shortName(c.nombre)),
      datasets: datasets.map((ds) => ({
        label: ds.label,
        data: data.map((c) => c[ds.key] || 0),
        backgroundColor: ds.color,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { max: 100, ticks: { callback: (v) => v + "%" } } },
      plugins: { legend: { labels: { color: "#8b9bbf" } } },
    },
  });
}

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

async function renderHistorial() {
  const resp = await fetch(apiUrl("/api/historial?limit=100"));
  const data = await resp.json();
  const entries = data.entries || [];
  document.getElementById("histMeta").textContent =
    `${data.state?.entry_count || 0} registros · último cambio: ${fmtDate(data.state?.last_timestamp)}`;

  document.getElementById("histBody").innerHTML = entries.map((e) => `<tr>
    <td>${fmtDate(e.timestamp)}</td>
    <td>${shortName(e.real?.ganador)} (${fmtPct(e.real?.margen_pct)})</td>
    <td>${shortName(e.proyectado_peru?.ganador)} (${fmtPct(e.proyectado_peru?.margen_pct)})</td>
    <td>${shortName(e.proyectado_final?.ganador)} (${fmtPct(e.proyectado_final?.margen_pct)})</td>
    <td><span class="badge ${e.proyectado_final?.extranjero_modo === "real" ? "ok" : "warn"}">${e.proyectado_final?.extranjero_modo || "—"}</span></td>
    <td>${fmtPct(e.proyectado_final?.margen_pct)}</td>
  </tr>`).join("") || `<tr><td colspan="6" style="text-align:center;color:var(--muted)">Sin registros aún — se guardará al cambiar los datos</td></tr>`;

  destroyChart("chartHistorial");
  if (entries.length < 2) return;
  const rev = [...entries].reverse();
  charts.chartHistorial = new Chart(document.getElementById("chartHistorial"), {
    type: "line",
    data: {
      labels: rev.map((e) => fmtDate(e.timestamp)),
      datasets: [
        { label: "Margen oficial", data: rev.map((e) => e.real?.margen_pct), borderColor: COLORS.neutral, tension: 0.3 },
        { label: "Margen proy. Perú", data: rev.map((e) => e.proyectado_peru?.margen_pct), borderColor: "#a855f7", tension: 0.3 },
        { label: "Margen proy. final", data: rev.map((e) => e.proyectado_final?.margen_pct), borderColor: COLORS.keiko, tension: 0.3 },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: "#8b9bbf" } } } },
  });
}

function renderComparacion2021() {
  const comp = getComp2021();
  if (!comp.departamentos?.length) return;

  const n21 = comp.nacional_2021 || {};
  const n26 = comp.nacional_2026 || {};
  const res = comp.resumen || {};
  const ext = comp.extranjero_comparacion || {};

  document.getElementById("compResumen").innerHTML = `
    <article class="comp-stat"><span class="label">2021 — Fujimori nacional</span><span class="value">${fmtPct(n21.fujimori_pct)}</span><span class="sub">Ganó Castillo ${fmtPct(n21.castillo_pct)}</span></article>
    <article class="comp-stat"><span class="label">2026 — Keiko actual</span><span class="value">${fmtPct(n26.keiko_pct_actual)}</span><span class="sub">${n26.delta_keiko_vs_2021_actual > 0 ? "+" : ""}${fmtPct(n26.delta_keiko_vs_2021_actual)} pp vs 2021</span></article>
    <article class="comp-stat"><span class="label">2026 — Keiko proyectado</span><span class="value">${fmtPct(n26.keiko_pct_proyectado)}</span><span class="sub">${n26.delta_keiko_vs_2021_proyectado > 0 ? "+" : ""}${fmtPct(n26.delta_keiko_vs_2021_proyectado)} pp vs 2021</span></article>
    <article class="comp-stat"><span class="label">Extranjero Fujimori/Keiko</span><span class="value">${fmtPct(ext["2021_fujimori_pct"])} → ${fmtPct(ext["2026_keiko_pct_estimado"])}</span><span class="sub">${ext.delta_pp > 0 ? "+" : ""}${fmtPct(ext.delta_pp)} pp</span></article>
    <article class="comp-stat"><span class="label">Similitud perfil regional</span><span class="value">${res.similitud_promedio_perfil || "—"}%</span><span class="sub">${res.departamentos_cambio_linea_fujimori} deptos. cambian control Fujimori→Keiko</span></article>
    <article class="comp-stat"><span class="label">Proy. final 2026</span><span class="value">${shortName(n26.ganador_proyectado_final)}</span><span class="sub">Keiko mejora en ${res.departamentos_keiko_mejora} / cae en ${res.departamentos_keiko_caida}</span></article>`;

  document.getElementById("compImpacto").textContent = comp.impacto || "";

  const depts = comp.departamentos.slice(0, 15);
  destroyChart("chartComp2021");
  charts.chartComp2021 = new Chart(document.getElementById("chartComp2021"), {
    type: "bar",
    data: {
      labels: depts.map((d) => d.region),
      datasets: [
        { label: "Fujimori 2021", data: depts.map((d) => d["2021"].fujimori_pct), backgroundColor: "rgba(249,115,22,0.6)" },
        { label: "Keiko 2026", data: depts.map((d) => d["2026_actual"].keiko_pct), backgroundColor: "rgba(59,130,246,0.75)" },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      scales: { x: { max: 100, ticks: { callback: (v) => v + "%" } } },
      plugins: { legend: { labels: { color: "#8b9bbf" } } },
    },
  });

  destroyChart("chartCompDelta");
  charts.chartCompDelta = new Chart(document.getElementById("chartCompDelta"), {
    type: "bar",
    data: {
      labels: depts.map((d) => d.region),
      datasets: [{
        label: "Δ Keiko vs Fujimori 2021 (pp)",
        data: depts.map((d) => d.delta_keiko_pp_actual),
        backgroundColor: depts.map((d) => d.delta_keiko_pp_actual >= 0 ? "rgba(34,197,94,0.75)" : "rgba(239,68,68,0.75)"),
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false } },
    },
  });

  document.getElementById("compTableBody").innerHTML = comp.departamentos.map((d) => {
    const delta = d.delta_keiko_pp_actual;
    const cls = delta >= 0 ? "delta-pos" : "delta-neg";
    return `<tr>
      <td><strong>${d.region}</strong></td>
      <td>${fmtPct(d["2021"].fujimori_pct)}</td>
      <td>${fmtPct(d["2026_actual"].keiko_pct)}</td>
      <td>${fmtPct(d["2026_proyectado"].keiko_pct)}</td>
      <td class="${cls}">${delta > 0 ? "+" : ""}${fmtPct(delta)}</td>
      <td>${d.similitud_perfil_actual}%</td>
      <td>${d["2021"].ganador}</td>
      <td>${d["2026_proyectado"].ganador}${d.cambio_linea_fujimori ? " ⚡" : ""}</td>
    </tr>`;
  }).join("");
}

function renderAll() {
  renderNationalSummary();
  renderExtranjeroSummary();
  if (selectedUbigeo) renderRegionDetail(selectedUbigeo);
  refreshMapStyles();
  renderTable();
  renderAnalysis();
  renderComparacion2021();
}

async function loadData(manual = false) {
  const btn = document.getElementById("btnRefresh");
  if (manual) btn.disabled = true;
  try {
    if (manual) await fetch(apiUrl("/api/refresh"), { method: "POST" });
    const res = await fetch(apiUrl("/api/data"));
    appData = await res.json();
    pollIntervalSec = appData.poll_interval_seconds || 60;
    document.getElementById("pollInterval").textContent = pollIntervalSec;

    if (!map) await initMap();
    renderAll();
    await renderHistorial();

    setStatus("live", "Datos actualizados", fmtDate(appData.updated_at));
    showAlert(appData.last_error ? `Advertencia: ${appData.last_error}` : null);
  } catch (err) {
    setStatus("err", "Error", String(err));
    showAlert("Error al cargar datos");
  } finally {
    if (manual) btn.disabled = false;
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => loadData(false), pollIntervalSec * 1000);
}

/* Eventos */
document.querySelectorAll(".view-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    viewMode = btn.dataset.view;
    renderNationalSummary();
    refreshMapStyles();
  });
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "historial") renderHistorial();
    if (tab.dataset.tab === "comparacion") renderComparacion2021();
    setTimeout(() => map?.invalidateSize(), 200);
  });
});

document.getElementById("btnRefresh").addEventListener("click", () => loadData(true));
document.getElementById("searchDepto")?.addEventListener("input", renderTable);

(async () => {
  await loadData(false);
  startPolling();
})();

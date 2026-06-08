const COLORS = { keiko: "#3b82f6", sanchez: "#f97316", neutral: "#64748b", pending: "#334155" };
const GEO_TO_UBIGEO = {
  Amazonas: "010000", Ancash: "020000", "Apurímac": "030000", Arequipa: "040000",
  Ayacucho: "050000", Cajamarca: "060000", "El Callao": "070000", Cusco: "080000",
  Huancavelica: "090000", "Huánuco": "100000", Ica: "110000", "Junín": "120000",
  "La Libertad": "130000", Lambayeque: "140000", Lima: "150000",
  "Municipalidad Metropolitana de Lima": "150000", Loreto: "160000",
  "Madre de Dios": "170000", Moquegua: "180000", Pasco: "190000", Piura: "200000",
  Puno: "210000", "San Martín": "220000", Tacna: "230000", Tumbes: "240000", Ucayali: "250000",
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

  const resp = await fetch("/static/peru-departamentos.geojson");
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
  const resp = await fetch("/api/historial?limit=100");
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

function renderAll() {
  renderNationalSummary();
  renderExtranjeroSummary();
  if (selectedUbigeo) renderRegionDetail(selectedUbigeo);
  refreshMapStyles();
  renderTable();
  renderAnalysis();
}

async function loadData(manual = false) {
  const btn = document.getElementById("btnRefresh");
  if (manual) btn.disabled = true;
  try {
    if (manual) await fetch("/api/refresh", { method: "POST" });
    const res = await fetch("/api/data");
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
    setTimeout(() => map?.invalidateSize(), 200);
  });
});

document.getElementById("btnRefresh").addEventListener("click", () => loadData(true));
document.getElementById("searchDepto")?.addEventListener("input", renderTable);

(async () => {
  await loadData(false);
  startPolling();
})();

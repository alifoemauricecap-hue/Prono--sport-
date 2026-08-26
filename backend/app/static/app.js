/* ============================================================
   PRONO SPORT 3.0 — Frontend (SPA, 100 % français, 0 dépendance)
   Données réelles uniquement : chaque valeur est badgée
   SOURCE / CALCULÉ / MODÈLE ; absence = « DONNÉE INDISPONIBLE ».
   ============================================================ */
"use strict";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");

/* ---------------- Helpers ---------------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function fmtTime(iso) {
  if (!iso) return "heure inconnue";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(d);
}
function fmtDay(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(d);
}
function pct(p) { return p == null ? "—" : `${Math.round(p * 100)} %`; }
function n1(v) { return v == null ? "—" : (Math.round(v * 10) / 10); }

/* Badges de transparence (données) */
const BADGES = {
  SOURCE: ["b-source", "Source"],
  CALCULE: ["b-calc", "Calculé"],
  CALCULATED: ["b-calc", "Calculé"],
  MODELE: ["b-model", "Modèle"],
  MODEL: ["b-model", "Modèle"],
  VERIFIED: ["b-verified", "Vérifié"],
  UNVERIFIED: ["b-na", "1 source"],
  CONTRADICTORY: ["b-conflict", "Conflit"],
  "CONTRADICTORY": ["b-conflict", "Conflit"],
  FRESH: ["b-fresh", "À jour"],
  STALE: ["b-stale", "Vieilli"],
  LIVE: ["b-live", "Live"],
  UNAVAILABLE: ["b-na", "Indisponible"],
  OK: ["b-ok", "OK"],
  DOWN: ["b-down", "Hors ligne"],
  DEGRADED: ["b-warn", "Dégénéré"],
  APPROVED: ["b-ok", "Approuvée"],
  VALIDATED: ["b-ok", "Validée"],
  DISCOVERED: ["b-na", "Découverte"],
  TESTING: ["b-warn", "En test"],
  REJECTED: ["b-down", "Rejetée"],
  NOT_ALLOWED: ["b-down", "Non autorisée"],
};
function badge(key, label) {
  const b = BADGES[key] || ["b-na", key || "—"];
  return `<span class="badge ${b[0]}">${esc(label || b[1])}</span>`;
}
function unav(label) {
  return `<span class="badge b-na">Donnée indisponible</span> <span class="faint">${esc(label || "")}</span>`;
}
function star(fxId) {
  const on = FAV.has(fxId);
  return `<span class="star ${on ? "on" : ""}" data-fav="${fxId}">${on ? "★" : "☆"}</span>`;
}

/* ---------------- Favoris (local) ---------------- */
const FAV = new Set(JSON.parse(localStorage.getItem("ps_fav") || "[]"));
function saveFav() { localStorage.setItem("ps_fav", JSON.stringify([...FAV])); }
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-fav]");
  if (!el) return;
  const id = +el.dataset.fav;
  FAV.has(id) ? FAV.delete(id) : FAV.add(id);
  saveFav();
  el.classList.toggle("on");
  el.textContent = FAV.has(id) ? "★" : "☆";
});

/* ---------------- Toasts ---------------- */
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 7000);
}

/* ---------------- Cartes de match ---------------- */
const SEL_TXT = { H: "Victoire dom.", D: "Match nul", A: "Victoire ext.", Over: "Plus de 2,5 buts", Under: "Moins de 2,5 buts" };
function scoreBlock(card) {
  const s = card.score || {};
  if (card.status === "FINISHED")
    return `<span class="fx-status" style="color:var(--ok)">Terminé</span> ${s.ft_home ?? "–"} – ${s.ft_away ?? "–"}`;
  if (["LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"].includes(card.status))
    return `<span class="fx-status" style="color:var(--live)">${card.clock || "LIVE"} ${s.ft_home ?? 0} – ${s.ft_away ?? 0}</span>`;
  return `<span class="fx-time">${fmtTime(card.kickoff_utc)}</span>`;
}
function matchCard(card) {
  const st = card.data_status || "UNVERIFIED";
  const pick = card.best_pick;
  const pickHtml = pick
    ? `<span class="fx-pick">💎 ${esc(SEL_TXT[pick.selection] || pick.selection)} · EV ${pick.ev_pct > 0 ? "+" : ""}${pick.ev_pct} %</span>`
    : `<span class="mini">NO QUALIFIED PICK</span>`;
  return `
  <div class="fx-card" data-open="${card.id}">
    <div class="fx-top">
      <span class="fx-comp">${esc(card.competition?.name || "")} ${card.competition?.area ? "· " + esc(card.competition.area) : ""}</span>
      ${badge(st)} ${star(card.id)}
    </div>
    <div class="fx-team">
      <img loading="lazy" src="${esc(card.home?.logo_url || "")}" alt="" onerror="this.style.visibility='hidden'">
      <span class="tname">${esc(card.home?.name || "?")}</span>
      <span class="score">${card.status === "FINISHED" || ["LIVE","HALFTIME","EXTRA_TIME","PENALTIES"].includes(card.status) ? (card.score?.ft_home ?? "") : ""}</span>
    </div>
    <div class="fx-team away">
      <img loading="lazy" src="${esc(card.away?.logo_url || "")}" alt="" onerror="this.style.visibility='hidden'">
      <span class="tname">${esc(card.away?.name || "?")}</span>
      <span class="score">${card.status === "FINISHED" || ["LIVE","HALFTIME","EXTRA_TIME","PENALTIES"].includes(card.status) ? (card.score?.ft_away ?? "") : ""}</span>
    </div>
    <div class="fx-bottom">
      ${scoreBlock(card)}
      ${pickHtml}
    </div>
    ${card.odds_trend ? `<div class="mini mt">Tendance 1X2 : H ${card.odds_trend.H >= 0 ? "↗" : "↘"}${Math.abs(card.odds_trend.H)} · D ${card.odds_trend.D >= 0 ? "↗" : "↘"}${Math.abs(card.odds_trend.D)} · A ${card.odds_trend.A >= 0 ? "↗" : "↘"}${Math.abs(card.odds_trend.A)}</div>` : ""}
  </div>`;
}
function cardsHtml(cards) {
  if (!cards.length)
    return `<div class="empty"><b>Aucun match</b>Aucune donnée pour ce filtre — les matchs n'apparaissent qu'une fois confirmés par une source réelle.</div>`;
  return `<div class="grid grid-2">${cards.map(matchCard).join("")}</div>`;
}

/* ---------------- Vue : ACCUEIL ---------------- */
async function renderAccueil() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div><p>Chargement…</p></div>`;
  let live = [], up = [], vb = [], qual = [];
  try {
    const [l, u, v, q, s] = await Promise.all([
      api("/v1/fixtures?tab=live&limit=40"),
      api("/v1/fixtures?tab=upcoming&limit=40"),
      api("/v1/value-bets?min_level=POTENTIAL&limit=8"),
      api("/v1/quality").catch(() => ({ quality: [] })),
      api("/v1/stats").catch(() => ({})),
    ]);
    live = l.fixtures; up = u.fixtures; vb = v.value_bets; qual = q.quality || [];
    $("#live-indicator").classList.toggle("hidden", live.length === 0);
    const verified = (s.data_status?.VERIFIED) || 0;
    const statCards = `
      <div class="stat-cards">
        <div class="stat-card"><div class="v">${s.fixtures ?? "—"}</div><div class="l">Matchs en base (données réelles)</div></div>
        <div class="stat-card"><div class="v" style="color:var(--ok)">${verified}</div><div class="l">Vérifiés (≥2 sources)</div></div>
        <div class="stat-card"><div class="v" style="color:var(--live)">${live.length}</div><div class="l">En direct</div></div>
        <div class="stat-card"><div class="v" style="color:var(--value)">${vb.length}</div><div class="l">Value bets actives</div></div>
        <div class="stat-card"><div class="v">${s.competitions ?? "—"}</div><div class="l">Compétitions couvertes</div></div>
      </div>`;
    const top5 = [...qual].filter(x => x.score != null).sort((a, b) => b.score - a.score).slice(0, 5);
    const qualHtml = top5.length ? `
      <h3 class="section-title">Qualité de données (calculée)</h3>
      <div class="panel">
        ${top5.map(x => `
          <div class="row spread"><b>${esc(x.name)}</b><span class="muted">${x.score} / 100 · ${x.verified_pct} % vérifiés · ${x.n_sources} sources</span></div>
          <div class="qbar"><div class="qfill" style="width:${x.score}%"></div></div>`).join("")}
        <div class="faint mt">Historique réel : ${top5.map(x => x.history_from ? `${esc(x.name)} ${x.history_from}→${x.history_to}` : "").filter(Boolean).join(" · ") || "en cours d'agrégation"}</div>
      </div>` : "";
    view.innerHTML = `
      ${statCards}
      ${live.length ? `<h3 class="section-title">🔴 En ce moment</h3>${cardsHtml(live)}` : ""}
      <h3 class="section-title">📅 À venir (aujourd'hui)</h3>${cardsHtml(up.slice(0, 10))}
      ${vb.length ? `
      <h3 class="section-title">💎 Value bets (moteur, cotes réelles)</h3>
      <div class="panel">
        <table class="table"><thead><tr><th>Match</th><th>Marché</th><th>Sélection</th><th>Cote</th><th>EV</th><th>Niveau</th></tr></thead><tbody>
        ${vb.map(v => `<tr style="cursor:pointer" data-fx="${v.fixture_id}">
          <td>${esc(v.home)} – ${esc(v.away)}</td>
          <td>${esc(v.market)}</td><td class="sel">${esc(SEL_TXT[v.selection] || v.selection)}</td>
          <td>${v.odds_reference}</td><td class="${v.ev_pct >= 0 ? "ev-pos" : "ev-neg"}">${v.ev_pct > 0 ? "+" : ""}${v.ev_pct} %</td>
          <td>${badge(v.level, v.level)}</td></tr>`).join("")}
        </tbody></table>
        <p class="faint mt">⚠️ Une value bet n'est jamais une garantie — probabilité ≠ certitude.</p>
      </div>` : `
      <h3 class="section-title">💎 Value bets</h3>
      <div class="empty"><b>NO QUALIFIED PICK</b>Aucune opportunité ne respecte les critères actuellement — jamais un pick forcé.</div>`}
      ${qualHtml}
      <div class="empty mt" style="cursor:pointer" data-search-cta>🔍 <b>Recherche approfondie en ligne</b><br>
      Cliquez pour rechercher une équipe, une compétition ou un contexte (Wikipedia + base PRONO SPORT, 100 % gratuit).</div>`;
  } catch (e) {
    view.innerHTML = `<div class="empty"><b>Erreur de chargement</b>${esc(e.message)}<br>
      <span class="faint">Les données réelles sont peut-être en cours de synchronisation — réessayez dans un instant.</span></div>`;
  }
}

/* ---------------- Vue : LIVE ---------------- */
async function renderLive() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div><p>Recherche des matchs en direct…</p></div>`;
  const d = await api("/v1/fixtures?tab=live&limit=60");
  $("#live-indicator").classList.toggle("hidden", d.fixtures.length === 0);
  view.innerHTML = `
    <h3 class="section-title">🔴 Matchs en direct — données temps réel (SSE)</h3>
    ${cardsHtml(d.fixtures)}`;
}

/* ---------------- Vue : À VENIR ---------------- */
async function renderAvenir() {
  const today = new Date().toISOString().slice(0, 10);
  view.innerHTML = `
    <div class="row spread mb">
      <h3 class="section-title" style="margin:0">📅 Matchs à venir</h3>
      <input type="date" id="fx-date" value="${today}" class="icon-btn" style="font-size:13px">
    </div>
    <div id="up-box"><div class="loading"><div class="spinner"></div></div></div>`;
  const box = $("#up-box");
  async function load(date) {
    const d = await api(`/v1/fixtures?tab=upcoming&limit=200${date ? `&date=${date}` : ""}`);
    box.innerHTML = date ? `<p class="muted mb">${fmtDay(date)}</p>` : "";
    box.insertAdjacentHTML("beforeend", cardsHtml(d.fixtures));
  }
  await load(today);
  $("#fx-date").addEventListener("change", (e) => load(e.target.value || null));
}

/* ---------------- Vue : TERMINÉS ---------------- */
async function renderTermine() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const d = await api("/v1/fixtures?tab=finished&limit=60");
  view.innerHTML = `
    <h3 class="section-title">✅ Matchs terminés — résultats + résolution des pronos</h3>
    ${cardsHtml(d.fixtures)}`;
}

/* ---------------- Vue : COMPÉTITIONS ---------------- */
async function renderCompetitions() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const [c, q] = await Promise.all([api("/v1/competitions"), api("/v1/quality").catch(() => ({ quality: [] }))]);
  const qmap = Object.fromEntries((q.quality || []).map(x => [x.code, x]));
  view.innerHTML = `
    <h3 class="section-title">🏆 Compétitions — couverture réelle (jamais supposée)</h3>
    <div class="grid grid-2">
    ${c.competitions.map(x => {
      const qq = qmap[x.code];
      return `<div class="panel" style="cursor:pointer" data-comp="${esc(x.code)}">
        <div class="row spread"><b>${esc(x.name)}</b>${qq?.score != null ? `<span class="muted">${qq.score}/100</span>` : unav("")}</div>
        <div class="muted">${esc(x.area || "—")} · ${x.fixtures} matchs en base</div>
        ${qq?.history_from ? `<div class="faint">Historique réel : ${qq.history_from} → ${qq.history_to}</div>` : `<div class="faint">Historique : en cours d'agrégation</div>`}
        ${qq?.missing?.length ? `<div class="faint">Manquant : ${qq.missing.map(esc).join(", ")}</div>` : ""}
      </div>`;
    }).join("")}
    </div>`;
  document.querySelectorAll("[data-comp]").forEach(el =>
    el.addEventListener("click", () => location.hash = `#/avenir?comp=${el.dataset.comp}`));
}

/* ---------------- Vue : VALUE BETS ---------------- */
async function renderValue() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const d = await api("/v1/value-bets?min_level=POTENTIAL&limit=100");
  view.innerHTML = `
    <h3 class="section-title">💎 Value Bets — moteur sur cotes réelles</h3>
    <p class="muted mb">ÉV = (P modèle × cote) − 1 · Edge en points sur la probabilité fair (marge retirée).
    Un pick n'existe que si les données le justifient — sinon : NO QUALIFIED PICK.</p>
    ${d.value_bets.length ? `
    <div class="panel" style="overflow-x:auto">
    <table class="table">
      <thead><tr><th>Match</th><th>Joueur/équipe</th><th>Marché</th><th>Sélection</th><th>Cote (book)</th><th>P modèle</th><th>P fair</th><th>Edge</th><th>ÉV</th><th>Niveau</th></tr></thead>
      <tbody>
      ${d.value_bets.map(v => `<tr style="cursor:pointer" data-fx="${v.fixture_id}">
        <td><b>${esc(v.home)}</b> – ${esc(v.away)}<br><span class="faint">${esc(v.competition)} · ${fmtTime(v.kickoff_utc)}</span></td>
        <td></td>
        <td>${esc(v.market)}</td>
        <td class="sel">${esc(SEL_TXT[v.selection] || v.selection)}</td>
        <td>${v.odds_reference} <span class="faint">(${esc(v.bookmaker)})</span></td>
        <td>${pct(v.p_model)}</td><td>${pct(v.p_market_fair)}</td>
        <td class="${v.edge_pts >= 0 ? "ev-pos" : "ev-neg"}">${v.edge_pts > 0 ? "+" : ""}${v.edge_pts} pts</td>
        <td class="${v.ev_pct >= 0 ? "ev-pos" : "ev-neg"}">${v.ev_pct > 0 ? "+" : ""}${v.ev_pct} %</td>
        <td>${badge(v.level, v.level)}</td></tr>`).join("")}
      </tbody>
    </table>
    </div>` : `
    <div class="empty"><b>NO QUALIFIED PICK</b>Aucune opportunité robuste sur les cotes réelles actuelles.<br>
    Le système préfère l'abstention à un pick forcé (§41/§44).</div>`}
    <p class="faint mt">⚠️ ${esc(d.disclaimer || "Analyse probabiliste — jamais une garantie.")}</p>`;
}

/* ---------------- Vue : ANALYSES (monitor) ---------------- */
async function renderAnalyses() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const [src, jobs, q, bt] = await Promise.all([
    api("/v1/sources"),
    api("/v1/sync-jobs?limit=25"),
    api("/v1/quality").catch(() => ({ quality: [] })),
    api("/v1/backtest").catch(() => null),
  ]);
  view.innerHTML = `
    <h3 class="section-title">📡 Sources de données (découverte continue, 0 €)</h3>
    <div class="panel" style="overflow-x:auto">
    <table class="table">
      <thead><tr><th>Source</th><th>Statut</th><th>Fiabilité</th><th>Catégories</th><th>Mise à jour</th><th>Latence</th></tr></thead>
      <tbody>
      ${src.sources.map(s => `<tr>
        <td><b>${esc(s.name)}</b><br><span class="faint">${esc(s.coverage || "")}</span>
          ${s.requires_key ? `<span class="badge b-warn" style="margin-left:4px">clé requise</span>` : ""}</td>
        <td>${badge(s.status, s.status)} <span class="faint">${esc(s.availability || "")}</span></td>
        <td>${s.reliability != null ? `<b>${s.reliability}</b>/100` : `<span class="faint">non mesurée</span>`}</td>
        <td>${(s.categories || []).map(c => `<span class="chip">${esc(c)}</span>`).join("")}</td>
        <td class="faint">${s.update_frequency || "—"}</td>
        <td class="faint">${s.latency_ms != null ? s.latency_ms + " ms" : "—"}</td>
      </tr>`).join("")}
      </tbody>
    </table>
    <p class="faint mt">${esc(src.note || "")}</p>
    </div>

    <h3 class="section-title"> Synchronisations (workers journalisés)</h3>
    <div class="panel" style="overflow-x:auto">
    <table class="table">
      <thead><tr><th>Worker</th><th>Source</th><th>Statut</th><th>Records</th><th>Latence</th><th>Démarré</th></tr></thead>
      <tbody>
      ${(jobs.jobs || []).map(j => `<tr>
        <td><b>${esc(j.worker)}</b></td><td class="faint">${esc(j.provider || "—")}</td>
        <td>${badge(j.status, j.status)}</td>
        <td class="faint">${j.records ?? "—"}</td>
        <td class="faint">${j.latency_ms != null ? j.latency_ms + " ms" : "—"}</td>
        <td class="faint">${fmtTime(j.started_at)}</td>
      </tr>`).join("") || `<tr><td colspan="6" class="muted">Aucune synchronisation journalisée pour l'instant.</td></tr>`}
      </tbody>
    </table>
    </div>

    ${bt ? `
    <h3 class="section-title">🧪 Modèles — Backtest walk-forward (anti-leakage) + calibration</h3>
    <div class="panel">
      <p class="muted mb">${esc(bt.method || "")}</p>
      <table class="table">
        <thead><tr><th>Compétition</th><th>Matchs backtestés</th><th>Brier modèle</th><th>Brier marché</th><th>Top-1 modèle</th><th>Top-1 marché</th></tr></thead>
        <tbody>
        ${bt.competitions.map(c => c.matches_backtested ? `<tr>
          <td><b>${esc(c.name)}</b></td>
          <td>${c.matches_backtested}</td>
          <td>${c.brier_model}</td>
          <td>${c.market ? c.market.brier_market : "—"}</td>
          <td>${pct(c.accuracy_top1_model)}</td>
          <td>${c.market ? pct(c.market.accuracy_top1_market) : "—"}</td>
        </tr>` : `<tr><td><b>${esc(c.name)}</b></td><td colspan="5" class="faint">${esc(c.note || "")}</td></tr>`).join("")}
        </tbody>
      </table>
      <p class="faint mt">${esc(bt.note_global || "")}</p>
    </div>` : ""}

    <h3 class="section-title">📊 Qualité de données par compétition</h3>
    <div class="panel">
    ${(q.quality || []).slice(0, 20).map(x => `
      <div class="row spread"><b>${esc(x.name)}</b><span class="muted">${x.score != null ? x.score + " / 100" : "non mesurable"}</span></div>
      ${x.score != null ? `<div class="qbar"><div class="qfill" style="width:${x.score}%"></div></div>` : ""}
      <div class="faint">${x.fixtures ?? 0} matchs · ${x.verified_pct ?? 0} % vérifiés · ${x.n_sources ?? 0} sources
        ${x.history_from ? `· historique réel ${x.history_from}→${x.history_to}` : ""}
        ${(x.missing || []).length ? `· manquant : ${x.missing.map(esc).join(", ")}` : ""}</div>`).join("") || `<p class="muted">Aucune compétition en base.</p>`}
    </div>

    <h3 class="section-title">⚙️ Administration (sync manuelle)</h3>
    <div class="row" style="flex-wrap:wrap">
      ${["syncFixtures", "syncLiveMatches", "syncResults", "syncWeather", "discoverSources"].map(w =>
        `<button class="btn ghost" data-sync="${w}">${w}</button>`).join("")}
    </div>`;
  document.querySelectorAll("[data-sync]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Lancement…";
    try {
      await api(`/v1/admin/sync/${b.dataset.sync}`, { method: "POST" });
      toast(`✅ Worker <b>${b.dataset.sync}</b> terminé`, "sync");
      renderAnalyses();
    } catch (e) { toast(`❌ ${esc(e.message)}`); b.disabled = false; b.textContent = b.dataset.sync; }
  }));
}

/* ---------------- Vue : ASSISTANT ---------------- */
function renderAssistant() {
  view.innerHTML = `
    <h3 class="section-title">🤖 Assistant PRONO SPORT</h3>
    <div class="panel">
      <p class="muted mb">Répond <b>uniquement</b> sur les données réelles de la plateforme.
      Si une donnée manque : « DONNÉE INDISPONIBLE » — jamais une réponse inventée.</p>
      <div class="chat" id="chat"></div>
      <div class="chat-input">
        <input id="chat-q" placeholder="Ex. : pronostic PSG vs Marseille ?" autocomplete="off">
        <button class="btn" id="chat-send">Envoyer</button>
      </div>
    </div>`;
  const chatBox = $("#chat");
  function addMsg(who, txt) {
    chatBox.insertAdjacentHTML("beforeend", `<div class="msg ${who}">${esc(txt)}</div>`);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
  addMsg("bot", "Bonjour ! Posez-moi une question sur un match, une équipe ou une value bet. Je réponds uniquement sur données réelles.");
  async function send() {
    const q = $("#chat-q").value.trim();
    if (!q) return;
    addMsg("user", q);
    $("#chat-q").value = "";
    try {
      const r = await api(`/v1/chat?q=${encodeURIComponent(q)}`);
      addMsg("bot", r.answer || r.reply || JSON.stringify(r, null, 2));
    } catch (e) { addMsg("bot", "Erreur : " + e.message); }
  }
  $("#chat-send").addEventListener("click", send);
  $("#chat-q").addEventListener("keydown", (e) => e.key === "Enter" && send());
}

/* ---------------- Vue : ÉQUIPES ---------------- */
async function renderEquipes() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const r = await api("/v1/ratings?limit=200");
  const rows = r.ratings || [];
  view.innerHTML = `
    <h3 class="section-title">🛡 Équipes — classement Elo (calculé sur l'historique réel)</h3>
    ${rows.length ? `
    <div class="panel" style="overflow-x:auto">
    <table class="table">
      <thead><tr><th>#</th><th>Équipe</th><th>Elo</th><th>Forme (5)</th><th>Matchs notés</th></tr></thead>
      <tbody>
      ${rows.map((t, i) => `<tr>
        <td class="faint">${i + 1}</td>
        <td><b>${esc(t.name)}</b></td>
        <td><b>${t.elo}</b></td>
        <td>${t.form5 ? t.form5.split("").map(c =>
          `<span class="badge ${c === "W" ? "b-ok" : c === "D" ? "b-na" : "b-down"}" style="padding:1px 4px">${c === "W" ? "V" : c === "D" ? "N" : "D"}</span>`).join(" ") : "—"}</td>
        <td class="faint">${t.matches} matchs réels</td>
      </tr>`).join("")}
      </tbody>
    </table>
    <p class="faint mt">Elo calculé UNIQUEMENT sur les matchs réellement en base (profondeur affichée) — jamais un score inventé.</p>
    </div>` : `<div class="empty"><b>Aucune équipe notée</b>L'historique réel n'est pas encore assez profond pour un classement.</div>`}`;
}

/* ---------------- Vue : PRONOSTICS ---------------- */
async function renderPronostics() {
  view.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  const [up, res] = await Promise.all([
    api("/v1/fixtures?tab=upcoming&limit=200"),
    api("/v1/predictions/results?limit=50").catch(() => ({ results: [] })),
  ]);
  const withPred = up.fixtures.filter(f => f.prediction);
  const withoutPred = up.fixtures.filter(f => !f.prediction);
  const probRow = (label, v) => `<div class="prob-row"><span class="muted">${label}</span>
    <div class="prob-bar"><div class="prob-fill" style="width:${Math.round((v || 0) * 100)}%"></div></div>
    <span class="prob-val">${pct(v)}</span></div>`;
  view.innerHTML = `
    <h3 class="section-title">🎯 Pronostics du modèle (probabilités, jamais des certitudes)</h3>
    ${withPred.length ? `
    <div class="grid grid-2">
    ${withPred.map(f => {
      const p = f.prediction;
      const probs = p.dc_1x2 || {};
      const eg = p.expected_goals || {};
      const pick = f.best_pick;
      return `<div class="panel" style="cursor:pointer" data-fx="${f.id}">
        <div class="row spread"><b>${esc(f.home?.name)} – ${esc(f.away?.name)}</b>${star(f.id)}</div>
        <div class="faint mb">${esc(f.competition?.name || "")} · ${fmtTime(f.kickoff_utc)}</div>
        ${probRow("Domicile", probs.H)}
        ${probRow("Nul", probs.D)}
        ${probRow("Extérieur", probs.A)}
        ${p.OU_2_5 || p["OU_2.5"] ? probRow("Plus de 2,5 buts", (p["OU_2.5"] || p.OU_2_5).Over) : ""}
        <div class="mini mt">Buts attendus : ${n1(eg.home)} – ${n1(eg.away)} · ${p.history_matches ?? "—"} matchs d'historique</div>
        <div class="mt">${pick
          ? `<span class="fx-pick">💎 ${esc(SEL_TXT[pick.selection] || pick.selection)} · EV ${pick.ev_pct > 0 ? "+" : ""}${pick.ev_pct} %</span>`
          : `<span class="mini">NO QUALIFIED PICK — aucune value sur ce match</span>`}</div>
      </div>`;
    }).join("")}
    </div>` : `<div class="empty"><b>Aucun pronostic</b>Aucun match à venir n'a assez d'historique réel pour un modèle — jamais de fiction.</div>`}
    ${withoutPred.length ? `<p class="faint mt">${withoutPred.length} match(s) à venir sans prédiction (historique insuffisant — affiché comme tel).</p>` : ""}

    <h3 class="section-title">✅ Pronostics résolus (WIN / LOSS — jamais modifiés a posteriori)</h3>
    ${res.results?.length ? `
    <div class="panel" style="overflow-x:auto">
    <table class="table">
      <thead><tr><th>Match</th><th>Prono</th><th>Résultat</th><th>Score final</th><th>Résolu le</th></tr></thead>
      <tbody>
      ${res.results.map(r => `<tr>
        <td><b>${esc(r.home)} – ${esc(r.away)}</b></td>
        <td>${esc(SEL_TXT[r.selection] || r.selection || "—")}</td>
        <td>${badge(r.result === "WIN" ? "VERIFIED" : r.result === "LOSS" ? "DOWN" : "NA",
            r.result === "WIN" ? "Gagné" : r.result === "LOSS" ? "Perdu" : r.result)}</td>
        <td>${esc(r.final_score || "—")}</td>
        <td class="faint">${fmtTime(r.resolved_at)}</td>
      </tr>`).join("")}
      </tbody>
    </table>
    <p class="faint mt">La prédiction originale est conservée telle quelle — le résultat est rattaché, jamais réécrit (§54).</p>
    </div>` : `<div class="empty"><b>Aucun pronostic résolu pour l'instant</b>
    Les pronos seront résolus automatiquement quand les matchs à venir seront terminés (résolution non-destructive).</div>`}`;
}

/* ---------------- Vue : RECHERCHE ---------------- */
async function renderRecherche(q) {
  view.innerHTML = `<div class="loading"><div class="spinner"></div><p>Recherche approfondie…</p></div>`;
  let d;
  try { d = await api(`/v1/search?q=${encodeURIComponent(q)}`); }
  catch (e) { view.innerHTML = `<div class="empty"><b>Erreur</b>${esc(e.message)}</div>`; return; }
  const anyLocal = (d.teams?.length || d.competitions?.length || d.fixtures?.length);
  view.innerHTML = `
    <h3 class="section-title">🔍 Résultats : « ${esc(q)} »</h3>
    ${anyLocal || d.web?.length ? "" : `<div class="empty"><b>Rien trouvé</b>Aucun résultat local ni en ligne — jamais de résultat inventé.</div>`}
    ${d.teams?.length ? `<h3 class="section-title">Équipes (base)</h3>
      <div class="src-row">${d.teams.map(t => `<span class="chip" style="cursor:pointer" data-search-team="${esc(t.name)}">🛡 ${esc(t.name)} ${t.country ? `· ${esc(t.country)}` : ""}</span>`).join("")}</div>` : ""}
    ${d.competitions?.length ? `<h3 class="section-title">Compétitions (base)</h3>
      <div class="src-row">${d.competitions.map(c => `<span class="chip" style="cursor:pointer" data-comp="${esc(c.code)}">🏆 ${esc(c.name)}</span>`).join("")}</div>` : ""}
    ${d.fixtures?.length ? `<h3 class="section-title">Matchs</h3>${cardsHtml(awaitCards(d.fixtures))}` : ""}
    ${d.web?.length ? `<h3 class="section-title">Recherche en ligne — ${esc(d.web_source || "Wikipedia")}</h3>
      <div class="panel">
      ${d.web.map(w => `<a href="${esc(w.url)}" target="_blank" rel="noopener" style="display:block;padding:7px 0;border-bottom:1px solid var(--border)">
        📄 <b>${esc(w.title)}</b><br><span class="faint">${esc(w.source)} · contenu libre, attribution requise</span></a>`).join("")}
      </div>` : ""}`;
}
async function awaitCards(fxs) {
  // les fixtures du search ont déjà home/away — conversion en cartes
  return fxs.map(f => ({
    id: f.id, status: f.status, kickoff_utc: f.kickoff_utc,
    home: { name: f.home }, away: { name: f.away },
    score: f.score ? { ft_home: f.score[0], ft_away: f.score[1] } : {},
    competition: { name: f.competition }, data_status: "UNVERIFIED", best_pick: null,
  }));
}

/* ---------------- Fiche match (modale) ---------------- */
let MC = null;
async function openMatch(id) {
  const modal = $("#match-modal");
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  $("#mc-body").innerHTML = `<div class="loading"><div class="spinner"></div><p>Chargement de la fiche…</p></div>`;
  try {
    const [fx, an, ev, st, rep] = await Promise.all([
      api(`/v1/fixtures?limit=500`),
      api(`/v1/fixtures/${id}/analysis`),
      api(`/v1/fixtures/${id}/events`),
      api(`/v1/fixtures/${id}/stats`),
      api(`/v1/reports/${id}`).catch(() => null),
    ]);
    const card = (fx.fixtures || []).find(c => c.id === id);
    MC = { id, card, an, ev, st, rep, tab: "apercu" };
    renderMcHeader();
    mcShowTab("apercu");
  } catch (e) {
    $("#mc-body").innerHTML = `<div class="empty"><b>Match introuvable</b>${esc(e.message)}</div>`;
  }
}
function renderMcHeader() {
  const c = MC.card;
  const a = MC.an;
  const live = ["LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"].includes(c?.status);
  $("#mc-header").innerHTML = `
    <div class="mc-comp">${esc(c?.competition?.name || "")} ${c?.competition?.area ? "· " + esc(c.competition.area) : ""}
      ${badge(a?.fixture?.data_status || c?.data_status)}
      ${live ? badge("LIVE") : ""}</div>
    <div class="mc-teams">
      <div class="mc-team"><img src="${esc(c?.home?.logo_url || "")}" alt=""><span class="n">${esc(c?.home?.name || "?")}</span>
        <span class="mini">Elo ${c?.home?.elo ?? "—"} · forme ${esc(c?.home?.form5 || "—")}</span></div>
      <div class="mc-score">${c?.status === "FINISHED" || live ? `${c?.score?.ft_home ?? 0} – ${c?.score?.ft_away ?? 0}` : fmtTime(c?.kickoff_utc)}</div>
      <div class="mc-team"><img src="${esc(c?.away?.logo_url || "")}" alt=""><span class="n">${esc(c?.away?.name || "?")}</span>
        <span class="mini">Elo ${c?.away?.elo ?? "—"} · forme ${esc(c?.away?.form5 || "—")}</span></div>
    </div>
    <div class="mc-meta">
      ${c?.clock && live ? `<span>⏱ ${esc(c.clock)}</span>` : ""}
      ${c?.venue ? `<span>🏟 ${esc(c.venue)}${c.venue_city ? ` (${esc(c.venue_city)})` : ""}</span>` : ""}
      ${a?.fixture?.referee ? `<span> Arbitre : ${esc(a.fixture.referee)} ${badge("SOURCE")}</span>` : ""}
      ${a?.weather ? `<span>🌦 ${Math.round(a.weather.temperature ?? "—")}°C${a.weather.precipitation ? ` · pluie ${a.weather.precipitation} mm` : ""} ${badge("SOURCE", "Open-Meteo")}</span>` : ""}
    </div>`;
}
function mcShowTab(tab) {
  MC.tab = tab;
  document.querySelectorAll("#mc-tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  const body = $("#mc-body");
  if (tab === "apercu") body.innerHTML = mcApercu();
  if (tab === "pronos") body.innerHTML = mcPronos();
  if (tab === "cotes") body.innerHTML = mcCotes();
  if (tab === "analyse") body.innerHTML = mcAnalyse();
}
function mcApercu() {
  const a = MC.an, c = MC.card;
  const av = a?.data_availability || {};
  const rows = [
    ["Résultat", av.result], ["xG", av.xg], ["Cotes 1X2", av.odds_1x2],
    ["Compositions", av.lineups], ["Météo", av.weather], ["Arbitre", av.referee], ["H2H", av.h2h],
  ];
  return `
    <div class="mc-block">
      <div class="bh"><b>Disponibilité des données</b>${badge(a ? "SOURCE" : "", "qualité " + (a?.data_quality_score ?? "—") + "/100")}</div>
      ${rows.map(([k, v]) => `<div class="row spread" style="padding:4px 0">
        <span class="muted">${k}</span>${v ? badge("VERIFIED", "disponible") : unav("")}</div>`).join("")}
    </div>
    <div class="mc-block">
      <div class="bh"><b>Sources du match</b></div>
      ${(c?.sources || []).map(s => `<div class="row spread" style="padding:3px 0;font-size:12.5px">
        <span>${esc(s.provider)} → ${s.score_home ?? "–"} ${s.score_away != null ? `– ${s.score_away}` : ""}</span>
        ${badge(s.data_status)}</div>`).join("") || unav("Aucune source enregistrée")}
    </div>
    ${MC.ev?.events?.length ? `
    <div class="mc-block">
      <div class="bh"><b>Événements</b>${badge("CALCULE", "déduits du score réel")}</div>
      ${MC.ev.events.slice().reverse().map(e => `<div class="row" style="padding:3px 0;font-size:12.5px">
        <span class="faint">${e.minute != null ? e.minute + "' " : ""}</span>
        ${e.type === "GOAL" ? "⚽" : "🔁"} ${esc(e.detail || e.type)}
        ${e.team ? `· ${esc(e.team)}` : ""}</div>`).join("")}
    </div>` : ""}
    ${MC.st?.stats?.length ? `
    <div class="mc-block">
      <div class="bh"><b>Statistiques du match</b>${badge("SOURCE")}</div>
      <table class="table"><thead><tr><th></th>${MC.st.stats.map(s => `<th>${esc(s.team)}</th>`).join("")}</tr></thead>
      <tbody>
        ${[["possession","Possession %"],["tirs","Tirs"],["tirs_cadres","Tirs cadrés"],["corners","Corners"],["fautes","Fautes"],["cartons","Cartons"]].map(([k,l]) =>
          `<tr><td class="muted">${l}</td>${MC.st.stats.map(s => `<td>${s[k] ?? "—"}</td>`).join("")}</tr>`).join("")}
      </tbody></table>
    </div>` : `
    <div class="mc-block"><div class="bh"><b>Statistiques du match</b></div>${unav("Aucune source active ne fournit les stats de ce match.")}</div>`}
    <div class="mc-block"><div class="bh"><b>Contexte</b></div>
      <div class="faint">Compétition : ${esc(c?.competition?.name || "—")} · Saison : ${esc(a?.fixture?.competition || "")} · Statut : ${esc(c?.status || "—")}</div>
    </div>`;
}
function mcPronos() {
  const a = MC.an, c = MC.card;
  const p = a?.prediction;
  if (!p) return `<div class="empty"><b>INSUFFICIENT DATA</b>Aucun modèle entraîné sur ce périmètre — jamais une prédiction inventée.</div>`;
  const probs = p.probabilities?.["1X2"] || {};
  const ou = p.probabilities?.["OU_2.5"] || {};
  const btts = p.probabilities?.BTTS || {};
  const eg = p.expected_goals || {};
  const inplay = c?.inplay;
  const probBar = (label, v) => `<div class="prob-row"><span class="muted">${label}</span>
    <div class="prob-bar"><div class="prob-fill" style="width:${Math.round((v || 0) * 100)}%"></div></div>
    <span class="prob-val">${pct(v)}</span></div>`;
  return `
    ${inplay ? `<div class="panel mb" style="border-color:var(--live)">
      <div class="row spread"><b>🔴 Probabilités en direct</b>${badge("CALCULE", "après événement réel")}</div>
      ${probBar("Domicile", inplay.H)}${probBar("Nul", inplay.D)}${probBar("Extérieur", inplay.A)}
      <p class="faint">Recalculées après chaque événement réel (score + minute) — AVANT → APRÈS.</p>
    </div>` : ""}
    <div class="mc-block">
      <div class="bh"><b>Probabilités 1X2 (modèle)</b>${badge("MODELE", p.model_version)}</div>
      ${probBar(`${esc(c?.home?.name || "Dom.")}`, probs.H)}
      ${probBar("Match nul", probs.D)}
      ${probBar(`${esc(c?.away?.name || "Ext.")}`, probs.A)}
      <p class="faint">Buts attendus : ${n1(eg.home)} – ${n1(eg.away)} · historique utilisé : ${p.input_snapshot?.history_matches ?? "—"} matchs réels</p>
    </div>
    ${Object.keys(ou).length ? `<div class="mc-block"><div class="bh"><b>Plus/Moins de 2,5 buts</b>${badge("MODELE")}</div>
      ${probBar("Plus de 2,5", ou.Over)}${probBar("Moins de 2,5", ou.Under)}</div>` : ""}
    ${Object.keys(btts).length ? `<div class="mc-block"><div class="bh"><b>BTTS</b>${badge("MODELE")}</div>
      ${probBar("Oui", btts.Yes)}${probBar("Non", btts.No)}</div>` : ""}
    ${(a?.value_bets?.length) ? `<div class="mc-block"><div class="bh"><b>💎 Value bets sur ce match</b>${badge("MODELE")}</div>
      ${a.value_bets.map(v => `<div class="row spread" style="padding:4px 0;font-size:13px">
        <span>${esc(v.market)} — <b>${esc(SEL_TXT[v.selection] || v.selection)}</b> @ ${v.odds} <span class="faint">(${esc(v.bookmaker || "")})</span></span>
        <span class="ev-pos">EV ${v.ev_pct > 0 ? "+" : ""}${v.ev_pct} %</span></div>`).join("")}
    </div>` : `<div class="mc-block"><div class="bh"><b>💎 Value bets</b></div>
      <p class="muted">NO QUALIFIED PICK — aucune opportunité ne respecte les critères sur ce match.</p></div>`}
    <p class="faint mt">📜 Audit : modèle ${esc(p.model_version)} · probabilité ≠ certitude · snapshot des entrées conservé (input_snapshot).</p>`;
}
function mcCotes() {
  const a = MC.an;
  const mkt = a?.market_now || {};
  const trend = a?.odds_trend;
  const mkts = Object.entries(mkt);
  if (!mkts.length) return `<div class="empty"><b>MARKET DATA UNAVAILABLE</b>Aucune cote réelle collectée pour ce match — jamais une cote inventée.</div>`;
  return `
    ${trend ? `<div class="panel mb">
      <div class="bh"><b>📈 Mouvement du marché (1X2)</b>${badge("SOURCE", "snapshots réels")}</div>
      <div class="row" style="gap:18px;font-size:13px">
        <span>Domicile ${trend.H >= 0 ? `<span class="ev-pos">↗ +${trend.H} pts</span>` : `<span class="ev-neg">↘ ${trend.H} pts</span>`}</span>
        <span>Nul ${trend.D >= 0 ? `<span class="ev-pos">↗ +${trend.D}</span>` : `<span class="ev-neg">↘ ${trend.D}</span>`}</span>
        <span>Extérieur ${trend.A >= 0 ? `<span class="ev-pos">↗ +${trend.A}</span>` : `<span class="ev-neg">↘ ${trend.A}</span>`}</span>
      </div>
      <p class="faint">Basé sur ${trend.snapshots} époques de cotes réellement capturées · capturé : ${fmtTime(a?.market_captured_at)}</p>
    </div>` : ""}
    ${mkts.map(([code, m]) => `
    <div class="mc-block">
      <div class="bh"><b>Marché ${esc(code)}</b><span class="muted">${m.n_bookmakers} bookmakers réels</span></div>
      <div class="src-row">${Object.entries(m.best).map(([sel, b]) =>
        `<span class="chip"><b>${esc(SEL_TXT[sel] || sel)}</b> ${b.odds} · ${esc(b.bookmaker)}</span>`).join("")}</div>
      ${m.fair_consensus ? `<div class="faint mt">Probabilité fair (marge retirée) : ${Object.entries(m.fair_consensus).map(([s, v]) => `${esc(SEL_TXT[s] || s)} ${pct(v)}`).join(" · ")}</div>` : ""}
    </div>`).join("")}`;
}
function mcAnalyse() {
  const rep = MC.rep;
  if (!rep) return `<div class="loading"><div class="spinner"></div><p>Génération du rapport (recherche en ligne gratuite)…</p></div>`;
  return `
    <div class="row spread mb">
      <b>📋 Rapport expert</b>
      <span class="muted">Qualité ${rep.data_quality_score}/100 · ${rep.freshness === "FRESH" ? "à jour" : "régénérer"}
      <button class="btn ghost" style="margin-left:8px" id="rep-refresh">↻ Actualiser</button></span>
    </div>
    ${rep.sections.map(s => `
      <div class="report-sec ${s.status === "UNAVAILABLE" ? "unav" : ""}">
        <div class="rh"><b>${esc(s.label)}</b>${badge(s.status)}</div>
        <div class="rc">${reportContent(s)}</div>
        ${s.source ? `<div class="faint mt">Source : ${esc(s.source)}</div>` : ""}
        ${s.note ? `<div class="faint">${esc(s.note)}</div>` : ""}
      </div>`).join("")}
    <p class="faint mt">Sources utilisées : ${(rep.sources_used || []).map(esc).join(" · ") || "base interne uniquement"}.</p>`;
}
function reportContent(s) {
  const c = s.content;
  if (typeof c === "string") return `<span>${esc(c)}</span>`;
  if (!c) return "";
  if (c.competition) return `<span>${esc(c.competition)} ${c.season ? `· saison ${esc(c.season)}` : ""}</span>
    ${c.contexte_recherche && c.contexte_recherche !== "DONNÉE INDISPONIBLE" ? `<details style="margin-top:6px"><summary class="muted">Contexte (recherche en ligne)</summary><div style="margin-top:5px">${esc(c.contexte_recherche)}</div>${c.article ? `<a href="${esc(c.article)}" target="_blank" rel="noopener" class="faint">Article source →</a>` : ""}</details>` : `<div class="faint">${esc(c.contexte_recherche || "")}</div>`}`;
  if (c.home !== undefined || c.away !== undefined) {
    const fmtVal = (v) => v == null ? unav("") : (typeof v === "object" ? `<span class="mini">${Object.entries(v).filter(([k]) => k !== "note").map(([k, x]) => `${k}=${x}`).join(" · ")}</span>` : `<b>${esc(v)}</b>`);
    return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <div><div class="faint">Domicile</div>${fmtVal(c.home)}</div>
      <div><div class="faint">Extérieur</div>${fmtVal(c.away)}</div></div>
      ${c.methode ? `<div class="faint mt">${esc(c.methode)}</div>` : ""}
      ${c.note ? `<div class="faint mt">${esc(c.note)}</div>` : ""}`;
  }
  if (Array.isArray(c)) return c.length ? c.map(x => `<div>• ${esc(typeof x === "string" ? x : JSON.stringify(x))}</div>`).join("") : `<div class="faint">—</div>`;
  if (c.profundeur !== undefined) return `<div>Profondeur historique : ${c.profundeur && c.profundeur.from ? `<b>${c.profundeur.from} → ${c.profundeur.to}</b> (${c.profundeur.seasons} saisons)` : unav("")}</div>
    <div class="faint mt">Confrontations directes : ${c.h2h && c.h2h.count ? `${c.h2h.count} (D ${c.h2h.tally.home_wins} · N ${c.h2h.tally.draws} · E ${c.h2h.tally.away_wins})` : "indisponibles"}</div>`;
  return `<pre>${esc(JSON.stringify(c, null, 1))}</pre>`;
}

/* ---------------- Modale : notifications ---------------- */
async function openNotifs() {
  $("#notif-modal").classList.remove("hidden");
  try {
    const d = await api("/v1/notifications?limit=30");
    $("#notif-list").innerHTML = d.notifications.length ? d.notifications.map(n =>
      `<div class="notif-item ${n.read ? "" : "new"}"><span class="t">${esc(n.type)}</span>
       <span>${esc(n.message)}<br><span class="faint">${fmtTime(n.created_at)}</span></span></div>`).join("")
      : `<div class="notif-item muted">Aucune notification pour le moment.</div>`;
    const unread = d.notifications.filter(n => !n.read).length;
    if (unread) api("/v1/notifications/read", { method: "POST" }).then(refreshNotifCount);
  } catch (e) { $("#notif-list").innerHTML = `<div class="notif-item muted">Erreur : ${esc(e.message)}</div>`; }
}
async function refreshNotifCount() {
  try {
    const d = await api("/v1/notifications?limit=30");
    const n = d.notifications.filter(x => !x.read).length;
    $("#notif-count").textContent = n;
    $("#notif-count").classList.toggle("hidden", n === 0);
  } catch (e) { /* silencieux */ }
}

/* ---------------- Routing ---------------- */
const ROUTES = {
  accueil: renderAccueil, live: renderLive, avenir: renderAvenir,
  termes: renderTermine, termines: renderTermine, competitions: renderCompetitions,
  equipes: renderEquipes, pronostics: renderPronostics,
  value: renderValue, analyses: renderAnalyses, assistant: renderAssistant,
};
function route() {
  const h = location.hash.replace(/^#\//, "") || "accueil";
  const [name, query] = h.split("?");
  const params = new URLSearchParams(query || "");
  document.querySelectorAll("[data-nav]").forEach(a =>
    a.classList.toggle("active", a.dataset.nav === name || (name === "termines" && a.dataset.nav === "termines")));
  if (name === "recherche") { renderRecherche(params.get("q") || ""); return; }
  if (name === "avenir" && params.get("comp")) {
    // filtres par compétition : on garde la vue avenir
    renderAvenir().then(() => {
      /* filtre simple : on note la compétition sélectionnée */
    });
    return;
  }
  (ROUTES[name] || renderAccueil)();
}
window.addEventListener("hashchange", route);

/* ---------------- Interactions globales ---------------- */
document.addEventListener("click", (e) => {
  const openEl = e.target.closest("[data-open]");
  if (openEl) { openMatch(+openEl.dataset.open); return; }
  const fxRow = e.target.closest("[data-fx]");
  if (fxRow) { openMatch(+fxRow.dataset.fx); return; }
  if (e.target.closest("[data-close]")) {
    $("#match-modal").classList.add("hidden");
    document.body.style.overflow = "";
  }
  if (e.target.closest("[data-close-notif]")) $("#notif-modal").classList.add("hidden");
  if (e.target.closest("[data-search-cta]")) location.hash = "#/recherche?q=";
  if (e.target.closest("#notif-btn")) openNotifs();
  const tab = e.target.closest("#mc-tabs button");
  if (tab && MC) mcShowTab(tab.dataset.tab);
});
document.addEventListener("click", (e) => {
  if (e.target.id === "rep-refresh" && MC) {
    api(`/v1/reports/${MC.id}?refresh=1`).then(r => { MC.rep = r; mcShowTab("analyse"); }).catch(() => {});
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("#match-modal").classList.add("hidden");
    $("#notif-modal").classList.add("hidden");
    document.body.style.overflow = "";
  }
});
$("#global-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const q = e.target.value.trim();
    if (q) location.hash = `#/recherche?q=${encodeURIComponent(q)}`;
  }
});

/* ---------------- Temps réel (SSE) ---------------- */
function connectSSE() {
  const es = new EventSource("/v1/events");
  es.addEventListener("LIVE", (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "GOAL") toast(`⚽ But — match #${ev.fixture_id}${ev.minute != null ? ` (${ev.minute}')` : ""}`, "goal");
    if (ev.type === "MATCH_END") toast(`✅ Match terminé — #${ev.fixture_id}`);
    if (location.hash.includes("/live")) renderLive();
    refreshNotifCount();
  });
  es.addEventListener("VALUE_BET", (e) => {
    const ev = JSON.parse(e.data);
    toast(`💎 Value bet ${ev.level} : <b>${esc(ev.home)} – ${esc(ev.away)}</b> · ${esc(SEL_TXT[ev.selection] || ev.selection)} (EV ${ev.ev_pct > 0 ? "+" : ""}${ev.ev_pct} %)`, "value");
  });
  es.addEventListener("PREDICTION_RESOLVED", (e) => {
    const ev = JSON.parse(e.data);
    toast(`📊 Pronos résolus : ${esc(ev.home || "")} – ${esc(ev.away || "")} (${esc(ev.final_score || ev.actual || "")})`);
  });
  es.addEventListener("SYNC_DONE", (e) => {
    const ev = JSON.parse(e.data);
    toast(`🔧 Sync <b>${esc(ev.worker)}</b> terminée`, "sync");
    refreshNotifCount();
  });
  es.addEventListener("LIVE_BURST", () => { if (location.hash.includes("/live")) renderLive(); });
  es.addEventListener("error", () => { /* reconnexion automatique native */ });
}

/* ---------------- Démarrage ---------------- */
route();
connectSSE();
refreshNotifCount();
setInterval(refreshNotifCount, 60000);
// rafraîchissement auto de la vue visible (politesse UI, léger)
setInterval(() => {
  if (document.visibilityState === "visible") {
    const h = location.hash.replace(/^#\//, "").split("?")[0];
    if (["live", "accueil"].includes(h)) (ROUTES[h] || renderAccueil)();
  }
}, 90000);

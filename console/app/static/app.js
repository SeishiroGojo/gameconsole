/* GameConsole · interfaz web (sin dependencias).
 *
 * Estructura (programación orientada a objetos, igual que en el servidor):
 *   GameView            clase base: cómo se dibuja y se juega un juego
 *     Connect4View, Game2048View, MinesweeperView
 *   Instance            una partida en pantalla (tarjeta); habla con la API
 *   Panel               panel de control: consulta /api/stats/all y dibuja
 */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, url, body) {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* sin cuerpo */ }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { detail: "No se pudo contactar con el servidor" } };
  }
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 3500);
}

function fmtMs(ms) {
  if (ms == null || isNaN(ms)) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${s % 60} s`;
}
const fmtPct = (x) => (x == null ? "—" : `${Math.round(x * 100)} %`);
const fmtNum = (x, d = 1) => (x == null ? "—" : Number(x).toFixed(d).replace(/\.0+$/, ""));

/* ------------------------------------------------------------------ vistas */

class GameView {
  /** Devuelve el HTML del tablero y enlaza los eventos. Las subclases lo implementan. */
  render(inst) { throw new Error("render() no implementado"); }
  /** Teclado (solo lo usa 2048). */
  onKey(inst, ev) { return false; }
  statusText(inst) {
    const d = inst.data;
    if (d.status === "finished") {
      return {
        WON: ["¡Ganaste!", "win"], LOST: ["Perdiste", "lose"],
        DRAW: ["Empate", ""], ABANDONED: ["Partida abandonada", ""],
      }[d.outcome] || ["Partida terminada", ""];
    }
    return null;
  }
}

class Connect4View extends GameView {
  render(inst) {
    const d = inst.data, s = d.state, over = d.status === "finished";
    const win = new Set((s.winningCells || []).map(([r, c]) => `${r},${c}`));
    const last = s.lastMove ? `${s.lastMove.row},${s.lastMove.col}` : null;
    let cols = "";
    for (let c = 0; c < s.cols; c++) {
      let discs = "";
      for (let r = 0; r < s.rows; r++) {
        const v = s.board[r][c];
        const cls = ["disc", v ? `p${v}` : "", win.has(`${r},${c}`) ? "win" : "", last === `${r},${c}` ? "last" : ""].join(" ");
        discs += `<div class="${cls}"></div>`;
      }
      const off = inst.busy || over || s.awaitingAi;
      cols += `<button class="col" data-col="${c}" ${off ? "disabled" : ""} aria-label="Columna ${c + 1}">${discs}</button>`;
    }
    let status = this.statusText(inst), line, cls = "";
    if (status) [line, cls] = status;
    else if (inst.busy) line = "La computadora está pensando (Prolog)…";
    else if (s.awaitingAi) { line = "Prolog no respondió. Tu jugada ya quedó registrada."; cls = "err"; }
    else line = "Tu turno: elige una columna.";

    const ai = s.aiInfo
      ? `<div class="ai-box">Prolog eligió la columna <b>${s.aiInfo.column + 1}</b> · puntaje ${esc(s.aiInfo.score)} ·
         ${esc(s.aiInfo.nodes)} nodos explorados · profundidad ${esc(s.aiInfo.depth)} · ${esc(s.aiInfo.latencyMs)} ms</div>`
      : `<div class="ai-box">La IA se calcula en Prolog (negamax con poda alfa-beta). Dificultad: <b>${esc(s.difficulty)}</b>.</div>`;

    const retry = !over && s.awaitingAi && !inst.busy ? `<button class="btn primary small" data-act="retry-ai">Reintentar jugada de la IA</button>` : "";
    inst.body.innerHTML = `
      <div class="c4">${cols}</div>
      <div class="legend"><span>Tú</span><span class="ai">Computadora</span></div>
      <p class="status-line ${cls}">${esc(inst.message || line)}</p>${ai}
      <div class="inst-foot">${retry}</div>`;
    inst.body.querySelectorAll(".col").forEach((b) =>
      b.addEventListener("click", () => inst.act({ type: "drop", column: Number(b.dataset.col) })));
  }
}

class Game2048View extends GameView {
  render(inst) {
    const d = inst.data, s = d.state, over = d.status === "finished";
    const tiles = s.board.flat().map((v) => `<div class="tile ${v ? "" : "empty-tile"}" data-v="${v}">${v || ""}</div>`).join("");
    let status = this.statusText(inst), line, cls = "";
    if (status) [line, cls] = status;
    else line = "Usa las flechas del teclado (o los botones).";
    const dis = over || inst.busy ? "disabled" : "";
    inst.body.innerHTML = `
      <div class="score-row"><span>Puntaje <b>${s.score}</b></span><span>Ficha mayor <b>${s.maxTile}</b></span><span>Meta <b>${s.target}</b></span></div>
      <div class="g2048">${tiles}</div>
      <div class="dpad">
        <button class="up" data-dir="up" ${dis} aria-label="Arriba">↑</button>
        <button class="left" data-dir="left" ${dis} aria-label="Izquierda">←</button>
        <button class="down" data-dir="down" ${dis} aria-label="Abajo">↓</button>
        <button class="right" data-dir="right" ${dis} aria-label="Derecha">→</button>
      </div>
      <p class="status-line ${cls}">${esc(inst.message || line)}</p>`;
    inst.body.querySelectorAll("[data-dir]").forEach((b) =>
      b.addEventListener("click", () => inst.act({ type: "move", direction: b.dataset.dir })));
  }
  onKey(inst, ev) {
    const map = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
    const dir = map[ev.key];
    if (!dir) return false;
    if (inst.data.status !== "finished") inst.act({ type: "move", direction: dir });
    return true;
  }
}

class MinesweeperView extends GameView {
  render(inst) {
    const d = inst.data, s = d.state, over = d.status === "finished";
    let cells = "";
    s.cells.forEach((row, r) => row.forEach((c, k) => {
      let cls = "cell", txt = "", dis = over ? "disabled" : "";
      if (c.s === "open") { cls += " open"; if (c.n) { txt = c.n; cls += ` n${c.n}`; } dis = "disabled"; }
      else if (c.s === "flag") cls += c.wrong ? " wrongflag" : " flag";
      else if (c.s === "mine") cls += c.boom ? " boom" : " mine";
      cells += `<button class="${cls}" data-r="${r}" data-c="${k}" ${dis}>${txt}</button>`;
    }));
    let status = this.statusText(inst), line, cls = "";
    if (status) [line, cls] = status;
    else line = inst.flagMode ? "Modo bandera: toca una casilla para marcarla." : "Clic: descubrir · Clic derecho: bandera.";
    inst.body.innerHTML = `
      <div class="score-row"><span>Minas <b>${s.flagsLeft}</b></span><span>Descubiertas <b>${s.revealed}</b></span>
        <label class="toggle"><input type="checkbox" data-flagmode ${inst.flagMode ? "checked" : ""}> modo bandera</label></div>
      <div class="mines" style="grid-template-columns: repeat(${s.cols}, 1fr)">${cells}</div>
      <p class="status-line ${cls}">${esc(inst.message || line)}</p>`;
    inst.body.querySelector("[data-flagmode]").addEventListener("change", (e) => { inst.flagMode = e.target.checked; this.render(inst); });
    inst.body.querySelectorAll(".cell").forEach((b) => {
      const r = Number(b.dataset.r), c = Number(b.dataset.c);
      b.addEventListener("click", () => inst.act({ type: inst.flagMode ? "flag" : "reveal", row: r, col: c }));
      b.addEventListener("contextmenu", (e) => { e.preventDefault(); inst.act({ type: "flag", row: r, col: c }); });
    });
  }
}

const VIEWS = { connect4: new Connect4View(), "game-2048": new Game2048View(), minesweeper: new MinesweeperView() };

/* --------------------------------------------------------------- instancias */

const STORE_KEY = "gameconsole.matches";
const instances = new Map();
let focused = null;

function saveIds() {
  try { sessionStorage.setItem(STORE_KEY, JSON.stringify([...instances.keys()])); } catch (_) { /* sin almacenamiento */ }
}

class Instance {
  constructor(data, options) {
    this.data = data;
    this.options = options || {};
    this.view = VIEWS[data.gameId];
    this.busy = false;
    this.message = "";
    this.flagMode = false;
    this.el = document.createElement("article");
    this.el.className = "instance";
    this.el.tabIndex = 0;
    this.el.innerHTML = `
      <div class="inst-head"><h3></h3><span class="mid"></span><button class="btn small ghost" data-head></button></div>
      <div class="inst-body"></div>`;
    this.body = $(".inst-body", this.el);
    $("h3", this.el).textContent = data.title;
    $(".mid", this.el).textContent = data.matchId.slice(-8);
    $(".mid", this.el).title = data.matchId;
    this.el.addEventListener("pointerdown", () => (focused = this));
    this.el.addEventListener("focusin", () => (focused = this));
    this.render();
  }
  get id() { return this.data.matchId; }

  render() {
    const over = this.data.status === "finished";
    const head = $("[data-head]", this.el);
    head.textContent = over ? "Quitar" : "Abandonar";
    head.onclick = () => (over ? this.remove() : this.abandon());
    this.view.render(this);
    if (over && !$(".inst-foot .again", this.el)) {
      const foot = $(".inst-foot", this.el) || this.body.appendChild(Object.assign(document.createElement("div"), { className: "inst-foot" }));
      const again = Object.assign(document.createElement("button"), { className: "btn primary small again", textContent: "Jugar de nuevo" });
      again.onclick = () => { this.remove(); createMatch(this.data.gameId, this.options); };
      foot.appendChild(again);
    }
    const retry = $('[data-act="retry-ai"]', this.el);
    if (retry) retry.onclick = () => this.retryAi();
  }

  async act(action) {
    if (this.busy || this.data.status === "finished") return;
    this.busy = true; this.message = ""; this.render();
    const r = await api("POST", `/api/matches/${this.id}/actions`, action);
    this.busy = false;
    this.handle(r);
  }
  async retryAi() {
    this.busy = true; this.render();
    const r = await api("POST", `/api/matches/${this.id}/ai`);
    this.busy = false;
    this.handle(r);
  }
  handle(r) {
    if (r.ok) { this.data = r.data; this.message = ""; }
    else if (r.status === 503 && r.data && r.data.match) { this.data = r.data.match; this.message = ""; toast(r.data.error); }
    else this.message = (r.data && (r.data.detail || r.data.error)) || "Error inesperado";
    this.render();
    if (this.message) setTimeout(() => { if (this.message) { this.message = ""; this.render(); } }, 2500);
  }
  async abandon() {
    const r = await api("POST", `/api/matches/${this.id}/abandon`);
    if (r.ok) { this.data = r.data; this.render(); }
  }
  remove() {
    this.el.remove(); instances.delete(this.id); saveIds(); syncEmpty();
  }
}

function syncEmpty() {
  $("#empty").hidden = instances.size > 0;
  $("#instances-count").textContent = instances.size;
  $("#btn-close-finished").hidden = ![...instances.values()].some((i) => i.data.status === "finished");
}

function addInstance(data, options) {
  const inst = new Instance(data, options);
  instances.set(data.matchId, inst);
  $("#instances").prepend(inst.el);
  saveIds(); syncEmpty();
  return inst;
}

async function createMatch(gameId, options) {
  const r = await api("POST", "/api/matches", { gameId, options: options || {} });
  if (!r.ok) { toast((r.data && r.data.detail) || "No se pudo crear la partida"); return; }
  const inst = addInstance(r.data, options);
  inst.el.focus({ preventScroll: true });
}

async function restoreInstances() {
  let ids = [];
  try { ids = JSON.parse(sessionStorage.getItem(STORE_KEY) || "[]"); } catch (_) { /* nada */ }
  for (const id of ids.reverse()) {
    const r = await api("GET", `/api/matches/${id}`);
    if (r.ok) addInstance(r.data);
  }
}

/* ---------------------------------------------------------------- catálogo */

const DIFFICULTIES = {
  connect4: [["easy", "Fácil"], ["medium", "Normal"], ["hard", "Difícil"]],
  minesweeper: [["easy", "9×9 · 10 minas"], ["medium", "12×12 · 24 minas"], ["hard", "16×16 · 40 minas"]],
};
const DEFAULT_DIFF = { connect4: "medium", minesweeper: "easy" };

async function loadCatalog() {
  const r = await api("GET", "/api/games");
  const box = $("#catalog");
  if (!r.ok) { box.textContent = "No se pudo cargar el catálogo."; return; }
  box.innerHTML = "";
  window.CATALOG = r.data;
  for (const g of r.data) {
    const card = document.createElement("div");
    card.className = "game-card";
    const diffs = DIFFICULTIES[g.gameId];
    const select = diffs
      ? `<select aria-label="Dificultad de ${esc(g.title)}">${diffs.map(([v, l]) => `<option value="${v}" ${v === DEFAULT_DIFF[g.gameId] ? "selected" : ""}>${l}</option>`).join("")}</select>`
      : "";
    card.innerHTML = `
      <h3>${esc(g.title)} ${g.mode === "vs_ai" ? '<span class="tag ai">IA en Prolog</span>' : '<span class="tag">1 jugador</span>'}</h3>
      <p>${esc(g.description)}</p>
      <div class="row">${select}<button class="btn primary">Nueva partida</button></div>`;
    $("button", card).addEventListener("click", () => {
      const sel = $("select", card);
      createMatch(g.gameId, sel ? { difficulty: sel.value } : {});
    });
    box.appendChild(card);
  }

  // Demostración de concurrencia: partidas automáticas de los tres juegos.
  const demo = document.createElement("div");
  demo.className = "game-card demo";
  demo.innerHTML = `
    <h3>Demostración <span class="tag">concurrencia</span></h3>
    <p>Lanza partidas automáticas de los tres juegos a la vez (Conecta 4 usa Prolog). Míralas avanzar en el Panel de control.</p>
    <div class="row">
      <select aria-label="Partidas por juego">
        <option value="1">1 por juego</option><option value="2" selected>2 por juego</option>
        <option value="3">3 por juego</option><option value="5">5 por juego</option>
      </select>
      <button class="btn">Lanzar</button>
    </div>`;
  $("button", demo).addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    const r = await api("POST", "/api/demo/bots", { perGame: Number($("select", demo).value) });
    btn.disabled = false;
    toast(r.ok ? `Se lanzaron ${r.data.launched} partidas automáticas. Míralas en el Panel de control.`
               : ((r.data && (r.data.detail || r.data.error)) || "No se pudieron lanzar"));
  });
  box.appendChild(demo);
}

/* ------------------------------------------------------------------- panel */

const Panel = {
  last: null,
  render(data) {
    this.last = data;
    const live = data.live, overall = data.overall, games = data.games || [];
    const alerts = [];
    if (!data.sources.ingestion.ok) alerts.push(`No se pudo consultar GameStats (ingestión, ${esc(data.sources.ingestion.url)}): ${esc(data.sources.ingestion.error)}`);
    if (!data.sources.analysis.ok) alerts.push(`No se pudo consultar GameStats (análisis, ${esc(data.sources.analysis.url)}): ${esc(data.sources.analysis.error)}`);
    const al = $("#panel-alert");
    al.hidden = alerts.length === 0;
    al.innerHTML = alerts.join("<br>");

    const t = (live && live.totals) || { started: 0, active: 0, finished: 0, events: 0 };
    const o = overall || {};
    $("#kpis-general").innerHTML = [
      kpi("Partidas iniciadas", t.started, "accent", "instancias ejecutadas"),
      kpi("En curso ahora", t.active, "", "se actualiza en vivo"),
      kpi("Terminadas", t.finished),
      kpi("Eventos recibidos", t.events),
      kpi("Partidas analizadas", o.matches ?? "—", "", `${o.games ?? 0} juego(s)`),
      kpi("Victorias", o.won ?? "—", "good"),
      kpi("Derrotas", o.lost ?? "—", "bad"),
      kpi("Empates / abandonos", o.matches == null ? "—" : `${o.draws} / ${o.abandoned}`),
      kpi("Tasa de victoria", o.matches ? fmtPct(o.winRate) : "—", "", "sin contar abandonos"),
      kpi("Duración media", o.matches ? fmtMs(o.avgDurationMs) : "—"),
      kpi("Jugadas totales", o.totalMoves ?? "—"),
      kpi("Decisiones de la IA", o.totalAiDecisions ?? "—"),
    ].join("");

    const catalog = window.CATALOG || [];
    $("#game-stats").innerHTML = catalog.map((g) => this.gameCard(g, live, games)).join("");

    const p = data.console.publisher;
    $("#kpis-publisher").innerHTML = [
      kpi("Enviados", p.published, "good"), kpi("En cola", p.pending), kpi("Reintentos", p.retries),
      kpi("Rechazados", p.rejected), kpi("Descartados", p.dropped, p.dropped ? "bad" : ""),
    ].join("");

    const f = $("#freshness");
    const ok = data.sources.ingestion.ok && data.sources.analysis.ok;
    f.className = "freshness" + (ok ? " live" : "");
    f.textContent = `${ok ? "en vivo · " : "con errores · "}actualizado ${new Date(data.fetchedAt).toLocaleTimeString()}`;
  },
  gameCard(g, live, games) {
    const l = ((live && live.games) || []).find((x) => x.gameId === g.gameId) || { started: 0, active: 0, finished: 0, events: 0 };
    const a = games.find((x) => x.gameId === g.gameId);
    const done = a ? a.matches : 0;
    const seg = (n, cls) => (done ? `<i class="${cls}" style="width:${(n / done) * 100}%"></i>` : "");
    let rows = "";
    if (a) {
      rows += row("Partidas analizadas", a.matches);
      rows += row("Victorias · derrotas", `${a.won} · ${a.lost}`);
      rows += row("Empates · abandonos", `${a.draws} · ${a.abandoned}`);
      rows += row("Tasa de victoria", fmtPct(a.winRate));
      rows += row("Duración media", fmtMs(a.avgDurationMs));
      rows += row("Jugadas por partida", fmtNum(a.avgMoves));
      if (g.mode === "vs_ai") rows += row("Decisiones de la IA por partida", fmtNum(a.avgAiDecisions));
      if (a.avgScore != null) { rows += row("Puntaje medio", fmtNum(a.avgScore, 0)); rows += row("Mejor puntaje", a.bestScore); }
    }
    return `
      <div class="gs-card">
        <h4>${esc(g.title)} ${g.mode === "vs_ai" ? '<span class="tag ai">IA en Prolog</span>' : ""}</h4>
        <div class="live-row">
          <div><b>${l.started}</b><span>iniciadas</span></div>
          <div class="act"><b>${l.active}</b><span>en curso</span></div>
          <div><b>${l.finished}</b><span>terminadas</span></div>
        </div>
        ${a ? `<div class="bar" title="victorias / derrotas / empates / abandonos">${seg(a.won, "w")}${seg(a.lost, "l")}${seg(a.draws, "d")}${seg(a.abandoned, "a")}</div>
        <table class="gs-table">${rows}</table>` : `<p class="gs-empty">Aún no hay partidas terminadas de este juego.</p>`}
      </div>`;
  },
};
const kpi = (label, value, cls = "", sub = "") =>
  `<div class="kpi ${cls}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
const row = (k, v) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`;

async function pollStats() {
  const r = await api("GET", "/api/stats/all");
  if (r.ok) Panel.render(r.data);
  const gs = $("#chip-ingestion");
  const ok = r.ok && r.data.sources.ingestion.ok && r.data.sources.analysis.ok;
  gs.className = "chip " + (ok ? "ok" : "bad");
}
async function pollHealth() {
  const r = await api("GET", "/health");
  $("#chip-prolog").className = "chip " + (r.ok && r.data.prolog ? "ok" : "bad");
}

/* ------------------------------------------------------------------- inicio */

function showView(name) {
  for (const v of ["console", "panel"]) $(`#view-${v}`).hidden = v !== name;
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.view === name)));
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "panel") pollStats();
}

document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));
$("#btn-close-finished").addEventListener("click", () => {
  [...instances.values()].filter((i) => i.data.status === "finished").forEach((i) => i.remove());
});
document.addEventListener("keydown", (ev) => {
  if (!focused || !instances.has(focused.id) || ["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) return;
  if (focused.view.onKey(focused, ev)) ev.preventDefault();
});

(async function init() {
  await loadCatalog();
  await restoreInstances();
  syncEmpty();
  showView(location.hash === "#panel" ? "panel" : "console");
  pollHealth(); pollStats();
  setInterval(pollStats, 2000);
  setInterval(pollHealth, 5000);
})();

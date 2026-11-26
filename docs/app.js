// DevOps Radio — renderiza a playlist do dia a partir de data/today.json (ou data/days/<data>.json).
// Todo texto vindo dos dados entra via textContent (nunca innerHTML).

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const fmtDur = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const fmtHours = (min) => `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`;

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function renderHeader(day) {
  const d = new Date(day.date + "T12:00:00");
  $("#date").textContent = d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });
  $("#theme").textContent = day.title;
  $("#desc").textContent = day.description;
  const chips = $("#genres");
  chips.replaceChildren(...day.genres.map((g) => el("span", "chip", g)));
  const bpms = day.tracks.map((t) => t.bpm);
  const instr = day.tracks.filter((t) => t.instrumental >= 0.5).length;
  $("#s-tracks").textContent = day.tracks.length;
  $("#s-dur").textContent = fmtHours(day.duration_min);
  $("#s-bpm").textContent = `${Math.min(...bpms)}–${Math.max(...bpms)}`;
  $("#s-instr").textContent = `${Math.round((100 * instr) / day.tracks.length)}%`;
  document.title = `DevOps Radio · ${day.title}`;
}

function renderRepo(day) {
  if (!day.repo_url) return;
  const a = $("#repo");
  a.href = day.repo_url.startsWith("http") ? day.repo_url : `https://${day.repo_url}`;
  a.textContent = day.repo_url.replace(/^https?:\/\//, "");
}

function renderPlayer(day) {
  if (!day.playlist_id) return;
  $("#player").src = `https://open.spotify.com/embed/playlist/${encodeURIComponent(day.playlist_id)}?utm_source=generator&theme=0`;
  $("#open-spotify").href = `https://open.spotify.com/playlist/${encodeURIComponent(day.playlist_id)}`;
}

function renderTable(day) {
  const tbody = $("#tracks tbody");
  tbody.replaceChildren();
  for (const t of day.tracks) {
    const tr = el("tr");
    tr.dataset.n = t.n;
    tr.append(el("td", "n", String(t.n).padStart(2, "0")));
    const tdT = el("td");
    tdT.append(el("div", "t-title", t.title), el("div", "t-artist", t.artists.join(", ")));
    tr.append(tdT);
    const tdG = el("td", "hide-sm");
    tdG.append(el("span", "genre", t.genre));
    tr.append(tdG);
    tr.append(el("td", "num", t.bpm));
    const tdK = el("td");
    if (t.camelot) tdK.append(el("span", "key", t.camelot));
    tr.append(tdK);
    const tdE = el("td", "hide-sm");
    const meter = el("div", "meter");
    meter.title = `Energia ${Math.round(t.energy * 100)}%`;
    meter.setAttribute("role", "meter");
    meter.setAttribute("aria-valuenow", Math.round(t.energy * 100));
    meter.setAttribute("aria-valuemin", 0);
    meter.setAttribute("aria-valuemax", 100);
    const fill = el("span");
    fill.style.width = `${Math.round(t.energy * 100)}%`;
    meter.append(fill);
    tdE.append(meter);
    tr.append(tdE);
    tr.append(el("td", "num hide-sm", fmtDur(t.duration_s)));
    const tdP = el("td");
    const a = el("a", "play", "↗");
    a.href = `https://open.spotify.com/track/${encodeURIComponent(t.id)}`;
    a.target = "_blank";
    a.rel = "noopener";
    a.setAttribute("aria-label", `Abrir ${t.title} no Spotify`);
    tdP.append(a);
    tr.append(tdP);
    tr.addEventListener("mouseenter", () => chartApi && chartApi.highlight(t.n));
    tr.addEventListener("mouseleave", () => chartApi && chartApi.highlight(null));
    tbody.append(tr);
  }
}

let chartApi = null;

function renderChart(day) {
  const box = $("#chart");
  const tip = $("#tooltip");
  box.replaceChildren();
  const W = 640, H = 340, m = { t: 12, r: 12, b: 28, l: 40 };
  const tr = day.tracks;
  const lo = Math.floor((Math.min(...tr.map((t) => t.bpm)) - 2) / 2) * 2;
  const hi = Math.ceil((Math.max(...tr.map((t) => t.bpm)) + 2) / 2) * 2;
  const x = (i) => m.l + ((i - 1) / Math.max(1, tr.length - 1)) * (W - m.l - m.r);
  const y = (b) => m.t + (1 - (b - lo) / (hi - lo)) * (H - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });

  // grade + eixo Y (ticks limpos)
  const span = hi - lo;
  const step = span <= 12 ? 2 : span <= 30 ? 5 : span <= 60 ? 10 : 20;
  const grid = svgEl("g", { class: "grid" });
  const axis = svgEl("g", { class: "axis" });
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    grid.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }));
    const t = svgEl("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end" });
    t.textContent = v;
    axis.append(t);
  }
  for (const n of [1, Math.round(tr.length / 2), tr.length]) {
    const t = svgEl("text", { x: x(n), y: H - 8, "text-anchor": "middle" });
    t.textContent = `#${n}`;
    axis.append(t);
  }
  svg.append(grid, axis);

  const pts = tr.map((t) => [x(t.n), y(t.bpm)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  svg.append(svgEl("path", { class: "area", d: `${d}L${x(tr.length)},${H - m.b}L${x(1)},${H - m.b}Z` }));
  svg.append(svgEl("path", { class: "line", d }));
  // rótulo seletivo: só o fim da linha
  const last = tr[tr.length - 1];
  const endDot = svgEl("circle", { class: "dot", cx: x(last.n), cy: y(last.bpm), r: 4.5 });
  svg.append(endDot);

  const cross = svgEl("line", { class: "cross", y1: m.t, y2: H - m.b, visibility: "hidden" });
  const hot = svgEl("circle", { class: "hot", r: 6, visibility: "hidden" });
  svg.append(cross, hot);
  const hit = svgEl("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" });
  svg.append(hit);
  box.append(svg);

  function show(n, clientX, clientY) {
    if (n == null) {
      cross.setAttribute("visibility", "hidden");
      hot.setAttribute("visibility", "hidden");
      tip.hidden = true;
      document.querySelectorAll("#tracks tr.hot").forEach((r) => r.classList.remove("hot"));
      return;
    }
    const t = tr[n - 1];
    cross.setAttribute("x1", x(n)); cross.setAttribute("x2", x(n));
    cross.setAttribute("visibility", "visible");
    hot.setAttribute("cx", x(n)); hot.setAttribute("cy", y(t.bpm));
    hot.setAttribute("visibility", "visible");
    tip.replaceChildren(el("b", null, `#${t.n} ${t.title}`), el("div", null, t.artists.join(", ")),
      el("div", "muted", `${t.bpm} BPM · ${t.camelot || "–"} · energia ${Math.round(t.energy * 100)}%`));
    tip.hidden = false;
    const card = box.closest(".card").getBoundingClientRect();
    const sb = svg.getBoundingClientRect();
    const px = clientX ?? sb.left + (x(n) / W) * sb.width;
    const py = clientY ?? sb.top + (y(t.bpm) / H) * sb.height;
    const left = Math.min(px - card.left + 14, card.width - tip.offsetWidth - 8);
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${py - card.top + 14}px`;
    document.querySelectorAll("#tracks tr.hot").forEach((r) => r.classList.remove("hot"));
    const row = document.querySelector(`#tracks tr[data-n="${n}"]`);
    if (row) row.classList.add("hot");
  }
  function nearest(evt) {
    const sb = svg.getBoundingClientRect();
    const vx = ((evt.clientX - sb.left) / sb.width) * W;
    const i = Math.round(((vx - m.l) / (W - m.l - m.r)) * (tr.length - 1)) + 1;
    return Math.min(tr.length, Math.max(1, i));
  }
  hit.addEventListener("pointermove", (e) => show(nearest(e), e.clientX, e.clientY));
  hit.addEventListener("pointerleave", () => show(null));

  chartApi = { highlight: (n) => show(n) };
}

function renderWeek(day) {
  const ol = $("#week");
  ol.replaceChildren(...day.week.map((w) => {
    const li = el("li", w.weekday === day.weekday ? "today" : "");
    const title = w.title.split("·").slice(1).join("·").trim() || w.title;
    li.append(el("div", "d", w.name), el("div", "w-title", title), el("div", "w-genres", w.genres.join(" · ")));
    return li;
  }));
}

async function load(path) {
  const day = await getJSON(path);
  renderHeader(day);
  renderPlayer(day);
  renderRepo(day);
  renderTable(day);
  renderChart(day);
  renderWeek(day);
  return day;
}

async function init() {
  try {
    const day = await load("data/today.json");
    const idx = await getJSON("data/index.json").catch(() => ({ days: [day.date] }));
    const sel = $("#archive");
    sel.replaceChildren(...idx.days.map((d) => {
      const o = el("option", null, new Date(d + "T12:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" }));
      o.value = d;
      if (d === day.date) o.selected = true;
      return o;
    }));
    sel.addEventListener("change", () => load(`data/days/${encodeURIComponent(sel.value)}.json`));
  } catch (err) {
    $("#theme").textContent = "Não consegui carregar a playlist de hoje.";
    console.error(err);
  }
}

init();

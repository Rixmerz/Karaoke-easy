/* Karaoke Easy — interfaz (Tauri o navegador). */
const $ = id => document.getElementById(id);
const T = window.__TAURI__ || null;           // APIs nativas cuando corre dentro de Tauri
const API = { base: "", token: "" };
const fmt = s => { s = Math.max(0, s | 0); return (s / 60 | 0) + ":" + String(s % 60).padStart(2, "0"); };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const NOTES_S = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"], NOTES_F = ["C","Db","D","Eb","E","F","Gb","G","Ab","A","Bb","B"];
const FLAT_MAJ = new Set([1,3,5,8,10]), FLAT_MIN = new Set([0,2,3,5,7,10]);
function keyName(t, m) { t = ((t % 12) + 12) % 12; return ((m ? FLAT_MIN : FLAT_MAJ).has(t) ? NOTES_F : NOTES_S)[t] + (m ? "m" : ""); }
function hueOf(s) { let h = 0; for (const ch of (s || "x")) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }

async function api(path, body) {
  const opt = { headers: { "X-Token": API.token } };
  if (body !== undefined) { opt.method = "POST"; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(API.base + "api/" + path, opt);
  if (!r.ok) throw new Error((await r.text()).slice(0, 200) || r.status);
  return r.json();
}
const media = (id, name) => `${API.base}media/${id}/${name}?t=${encodeURIComponent(API.token)}`;

function toast(msg, kind = "", ms = 3500) {
  const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
  $("toasts").appendChild(t); setTimeout(() => t.remove(), ms);
}
function modal(title, body, buttons) {
  $("mTitle").textContent = title; $("mBody").innerHTML = body; const B = $("mBtns"); B.innerHTML = "";
  for (const b of buttons) {
    const el = document.createElement("button"); el.className = "btn " + (b.primary ? "pri" : "ghost"); el.innerHTML = b.label;
    el.onclick = async () => { if (b.onclick && (await b.onclick()) === false) return; closeModal(); }; B.appendChild(el);
  }
  $("modal").classList.add("on"); setTimeout(() => $("mBody").querySelector("input,textarea,select")?.focus(), 50);
}
function closeModal() { $("modal").classList.remove("on"); }
$("modal").onclick = e => { if (e.target.id === "modal") closeModal(); };
function editSong(s) {
  modal("Editar canción", `<label>Título</label><input class="field" id="eTitle" value="${esc(s.title || "")}">
    <label>Artista</label><input class="field" id="eArtist" value="${esc(s.artist || "")}">`, [
    { label: "Cancelar" },
    { label: "Guardar", primary: true, onclick: async () => {
        await api("edit?id=" + s.id, { title: $("eTitle").value.trim(), artist: $("eArtist").value.trim() });
        toast("Guardado", "ok", 1500); loadLibrary(); } }]);
}
function loading(on, txt) { $("loading").style.display = on ? "flex" : "none"; if (txt) $("loadingTxt").textContent = txt; }

// ---------------- navegación ----------------
function go(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("on", v.id === "v-" + view));
  document.querySelectorAll(".nav button").forEach(b => b.classList.toggle("on", b.dataset.view === view));
  if (view === "library") loadLibrary();
  if (view === "settings") { loadSettings(); refreshModels(); }
}
document.querySelectorAll("[data-view]").forEach(b => b.onclick = () => go(b.dataset.view));
document.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));

// ---------------- biblioteca ----------------
let LIB = [], LISTS = { favorites: [], playlists: [] }, TAB = "all";
async function loadLibrary() {
  try { [LIB, LISTS] = await Promise.all([api("library"), api("lists")]); } catch (e) { LIB = LIB || []; }
  renderLibrary();
}
const saveLists = async () => { LISTS = await api("lists", LISTS); };
const isFav = id => LISTS.favorites.includes(id);
async function toggleFav(id) {
  LISTS.favorites = isFav(id) ? LISTS.favorites.filter(x => x !== id) : [...LISTS.favorites, id];
  await saveLists(); renderLibrary();
}
function tabSongs(tab) {
  if (tab === "fav") return LIB.filter(s => isFav(s.id));
  const pl = LISTS.playlists.find(p => p.id === tab);
  if (pl) return pl.songs.map(id => LIB.find(s => s.id === id)).filter(Boolean);
  return LIB;
}
function renderTabs() {
  const T2 = $("libTabs"); if (!LIB.length) { T2.innerHTML = ""; return; }
  if (TAB !== "all" && TAB !== "fav" && !LISTS.playlists.some(p => p.id === TAB)) TAB = "all";
  const tabs = [["all", "Todas", "library"], ["fav", `Favoritas (${LISTS.favorites.filter(id => LIB.some(s => s.id === id)).length})`, "heart"],
    ...LISTS.playlists.map(p => [p.id, `${p.name} (${p.songs.length})`, "list-music"])];
  T2.innerHTML = tabs.map(([id, name, ic]) => `<button class="tab ${TAB === id ? "on" : ""}" data-tab="${esc(id)}">${icon(ic, 14)} ${esc(name)}</button>`).join("")
    + `<button class="tab add" id="newList">${icon("list-plus", 14)} Nueva lista</button>`;
  T2.querySelectorAll("[data-tab]").forEach(b => {
    b.onclick = () => { TAB = b.dataset.tab; renderLibrary(); };
    const pl = LISTS.playlists.find(p => p.id === b.dataset.tab);
    if (pl) b.oncontextmenu = e => { e.preventDefault(); listMenu(e, pl); };
  });
  $("newList").onclick = () => newList();
}
function newList(addId) {
  modal("Nueva lista", `<label>Nombre</label><input class="field" id="lName" placeholder="Ej.: Fiesta, Ensayo, Rock en español">`, [
    { label: "Cancelar" },
    { label: "Crear", primary: true, onclick: async () => {
        const name = $("lName").value.trim(); if (!name) return false;
        const pl = { id: "l" + Date.now().toString(36), name, songs: addId ? [addId] : [] };
        LISTS.playlists.push(pl); await saveLists(); TAB = addId ? TAB : pl.id; renderLibrary();
        toast(addId ? `Añadida a “${name}”` : `Lista “${name}” creada`, "ok", 1800); } }]);
}
function listMenu(e, pl) {
  closeMenu();
  const m = document.createElement("div"); m.className = "menu"; m.id = "menu";
  m.innerHTML = `<button data-a="party">${icon("party-popper", 15)} Modo fiesta con esta lista</button><button data-a="rename">${icon("pencil", 15)} Renombrar</button><button data-a="del">${icon("trash-2", 15)} Borrar lista</button>`;
  m.style.left = Math.min(e.clientX, innerWidth - 230) + "px"; m.style.top = e.clientY + "px";
  m.onclick = async ev => {
    const a = ev.target.closest("button")?.dataset.a; closeMenu();
    if (a === "party") startParty(pl.songs.slice(), false);
    if (a === "rename") modal("Renombrar lista", `<input class="field" id="lName" value="${esc(pl.name)}">`, [{ label: "Cancelar" },
      { label: "Guardar", primary: true, onclick: async () => { pl.name = $("lName").value.trim() || pl.name; await saveLists(); renderLibrary(); } }]);
    if (a === "del") modal("Borrar lista", `<p>¿Borrar la lista “${esc(pl.name)}”? Las canciones no se borran.</p>`, [{ label: "Cancelar" },
      { label: "Borrar", primary: true, onclick: async () => { LISTS.playlists = LISTS.playlists.filter(p => p !== pl); TAB = "all"; await saveLists(); renderLibrary(); } }]);
  };
  document.body.appendChild(m); setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
}
function addToList(s) {
  const pls = LISTS.playlists;
  modal("Añadir a lista", (pls.length ? `<div class="checks">${pls.map((p, i) => `<label><input type="checkbox" data-i="${i}" ${p.songs.includes(s.id) ? "checked" : ""}> ${esc(p.name)}</label>`).join("")}</div>`
    : `<p class="sub">Aún no tienes listas.</p>`), [
    { label: `${icon("list-plus", 15)} Nueva lista`, onclick: () => { setTimeout(() => newList(s.id), 0); } },
    { label: "Listo", primary: true, onclick: async () => {
        document.querySelectorAll(".checks input").forEach(c => { const p = pls[+c.dataset.i];
          const has = p.songs.includes(s.id); if (c.checked && !has) p.songs.push(s.id); if (!c.checked && has) p.songs = p.songs.filter(x => x !== s.id); });
        await saveLists(); renderLibrary(); } }]);
}
function renderLibrary() {
  renderTabs();
  const q = $("libSearch").value.toLowerCase(), sort = $("libSort").value;
  let items = tabSongs(TAB).filter(s => ((s.title || "") + " " + (s.artist || "")).toLowerCase().includes(q));
  if (sort === "title") items.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
  if (sort === "artist") items.sort((a, b) => (a.artist || "").localeCompare(b.artist || ""));
  $("libCount").textContent = LIB.length ? `${LIB.length} canción${LIB.length > 1 ? "es" : ""}` : "";
  $("libEmpty").hidden = LIB.length > 0;
  const g = $("libGrid"); g.innerHTML = "";
  for (const s of items) {
    const h = hueOf(s.title), c = document.createElement("div"); c.className = "card";
    const bg = s.cover ? `background-image:url('${media(s.id, "cover.jpg")}')`
      : `background:linear-gradient(135deg,hsl(${h} 70% 45%),hsl(${(h + 60) % 360} 70% 22%))`;
    c.innerHTML = `<div class="cover" style="${bg}">${s.cover ? "" : `<span class="ini">${esc((s.title || "?")[0].toUpperCase())}</span>`}
      <div class="playo"><span>${icon("play", 24)}</span></div></div><button class="more" title="Más opciones">${icon("ellipsis")}</button>
      <div class="meta"><button class="fav ${isFav(s.id) ? "on" : ""}" title="Favorita">${icon("heart", 18)}</button><b>${esc(s.title || "(sin título)")}</b><span>${esc(s.artist || "Artista desconocido")}</span>
      <div class="chips">${s.key ? `<span class="chip">${icon("music-2", 12)} ${esc(s.key)}</span>` : ""}${s.duration ? `<span class="chip">${fmt(s.duration)}</span>` : ""}</div></div>`;
    c.onclick = () => openSong(s.id);
    c.querySelector(".more").onclick = e => { e.stopPropagation(); songMenu(e, s); };
    c.querySelector(".fav").onclick = e => { e.stopPropagation(); toggleFav(s.id); };
    c.oncontextmenu = e => { e.preventDefault(); songMenu(e, s); };
    g.appendChild(c);
  }
  if (LIB.length && !items.length) g.innerHTML = `<p class="sub">${q ? `Sin resultados para “${esc(q)}”.` : TAB === "fav" ? "Marca canciones con el corazón para verlas aquí." : "Esta lista está vacía. Usa ⋯ › Añadir a lista en una canción."}</p>`;
}
$("libSearch").oninput = renderLibrary; $("libSort").onchange = renderLibrary;
function songMenu(e, s) {
  closeMenu();
  const m = document.createElement("div"); m.className = "menu"; m.id = "menu";
  m.innerHTML = `<button data-a="play">${icon("play", 15)} Cantar</button><button data-a="fav">${icon("heart", 15)} ${isFav(s.id) ? "Quitar de favoritas" : "Añadir a favoritas"}</button><button data-a="list">${icon("list-plus", 15)} Añadir a lista…</button><button data-a="edit">${icon("pencil", 15)} Editar título y artista</button><button data-a="folder">${icon("folder-open", 15)} Abrir carpeta</button><button data-a="remove">${icon("trash-2", 15)} Quitar de la biblioteca</button>`;
  m.style.left = Math.min(e.clientX, innerWidth - 210) + "px"; m.style.top = e.clientY + "px";
  m.onclick = async ev => {
    const a = ev.target.closest("button")?.dataset.a; closeMenu();
    if (a === "play") openSong(s.id);
    if (a === "fav") toggleFav(s.id);
    if (a === "list") addToList(s);
    if (a === "edit") editSong(s);
    if (a === "folder") openPath(s.folder.replace(/[\\/]reproductor$/, ""));
    if (a === "remove") { await api("delete?id=" + s.id, {}); toast("Quitada de la biblioteca (los archivos se conservan)"); loadLibrary(); }
  };
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
}
function closeMenu() { $("menu")?.remove(); }

// ---------------- modo fiesta ----------------
let PARTY = null;   // {ids:[...], i}
function startParty(ids, shuffle) {
  ids = ids.filter(id => LIB.some(s => s.id === id));
  if (!ids.length) return toast("No hay canciones para el modo fiesta", "err");
  if (shuffle) for (let i = ids.length - 1; i > 0; i--) { const j = Math.random() * (i + 1) | 0; [ids[i], ids[j]] = [ids[j], ids[i]]; }
  PARTY = { ids, i: 0 }; openSong(ids[0]);
  toast(`Modo fiesta: ${ids.length} canciones`, "ok", 2500);
}
$("partyBtn").onclick = () => {
  const cur = tabSongs(TAB), favs = LIB.filter(s => isFav(s.id));
  const opts = [["view", `Lo que estoy viendo (${cur.length})`], ["fav", `Favoritas (${favs.length})`], ["all", `Toda la biblioteca (${LIB.length})`]];
  modal("Modo fiesta", `<p class="sub">Las canciones se reproducen una tras otra, con una pantalla de “Siguiente” entre cada una.</p>
    <div class="radio">${opts.map(([v, n], i) => `<label class="switch"><input type="radio" name="pq" value="${v}" ${i === 0 ? "checked" : ""} style="width:18px;height:18px;appearance:auto"> ${n}</label>`).join("")}</div>
    <label class="switch" style="margin-top:14px"><input type="checkbox" id="pShuffle"> Orden aleatorio</label>`, [
    { label: "Cancelar" },
    { label: `${icon("party-popper", 15)} Empezar`, primary: true, onclick: () => {
        const v = document.querySelector("input[name=pq]:checked").value;
        const list = v === "fav" ? favs : v === "all" ? LIB : cur;
        startParty(list.map(s => s.id), $("pShuffle").checked); } }]);
};

async function openPath(p) {
  try {
    if (T?.opener) await T.opener.openPath(p);
    else toast("Carpeta: " + p, "", 6000);
  } catch (e) { toast("No se pudo abrir: " + p, "err"); }
}

// ---------------- nueva canción ----------------
let QUEUE = [], semitones = 0;
const EXT = ["mp3", "mp4", "wav", "m4a", "flac", "mkv", "mov", "webm", "ogg", "aac"];
function addInputs(list) {
  let n = 0;
  for (let x of list) {
    x = (x || "").trim(); if (!x) continue;
    const isUrl = /^(https?:\/\/|www\.)/i.test(x);
    if (!isUrl && !EXT.includes(x.split(".").pop().toLowerCase())) { toast("Formato no compatible: " + x.split(/[\\/]/).pop(), "err"); continue; }
    if (!QUEUE.includes(x)) { QUEUE.push(x); n++; }
  }
  renderQueue();
  if (QUEUE.length === 1 && n) guessLyricFields(QUEUE[0]);
}
function nameOf(x) { return /^(https?:\/\/|www\.)/i.test(x) ? x : x.split(/[\\/]/).pop(); }
function guessLyricFields(x) {
  if (/^(https?:\/\/|www\.)/i.test(x)) return;
  let n = nameOf(x).replace(/\.[^.]+$/, "").replace(/^[0-9a-f]{6,}-/, "").replace(/_/g, " ").replace(/[\(\[].*?[\)\]]/g, "");
  n = n.replace(/\b(official|video|audio|lyrics?|hd|4k|vevo)\b.*$/i, "").trim();
  const [a, ...t] = n.split(" - ");
  if (t.length) { $("lyArtist").value = a.trim(); $("lyTitle").value = t.join(" - ").replace(/\s*-\s*\w*vevo\s*$/i, "").trim(); }
  else { $("lyTitle").value = n; }
}
function renderQueue() {
  const box = $("queue"); box.innerHTML = "";
  QUEUE.forEach((x, i) => {
    const d = document.createElement("div"); d.className = "qi";
    d.innerHTML = `<span style="color:var(--mut)">${icon(/^(https?:|www\.)/i.test(x) ? "link" : "file-audio")}</span><span class="n">${esc(nameOf(x))}</span><button class="x" title="Quitar">${icon("x", 16)}</button>`;
    d.querySelector(".x").onclick = () => { QUEUE.splice(i, 1); renderQueue(); };
    box.appendChild(d);
  });
  $("create").disabled = !QUEUE.length;
  $("create").textContent = QUEUE.length > 1 ? `Crear ${QUEUE.length} karaokes` : "Crear karaoke";
  $("lyNote").style.display = QUEUE.length > 1 ? "block" : "none";
  $("lyrOpt").style.opacity = QUEUE.length > 1 ? .5 : 1;
}
$("addLinks").onclick = () => { addInputs($("links").value.split(/\n|;|\s+(?=https?:)/)); $("links").value = ""; };
$("clearQ").onclick = () => { QUEUE = []; renderQueue(); };
$("pathIn").onkeydown = e => { if (e.key === "Enter") { addInputs([$("pathIn").value]); $("pathIn").value = ""; } };
$("drop").onclick = async () => {
  if (T?.dialog) {
    const r = await T.dialog.open({ multiple: true, filters: [{ name: "Audio y video", extensions: EXT }] });
    if (r) addInputs(Array.isArray(r) ? r : [r]);
  } else { $("pathIn").style.display = "block"; $("pathIn").focus(); }
};
// arrastrar y soltar (Tauri entrega rutas reales)
if (T?.webview) {
  T.webview.getCurrentWebview().onDragDropEvent(ev => {
    const t = ev.payload.type;
    $("drop").classList.toggle("over", t === "over" || t === "enter");
    if (t === "drop") { go("new"); addInputs(ev.payload.paths || []); }
  });
}
document.addEventListener("dragover", e => e.preventDefault());
document.addEventListener("drop", e => e.preventDefault());
document.addEventListener("paste", e => {
  if ($("player").classList.contains("on") || ["TEXTAREA", "INPUT"].includes(e.target.tagName)) return;
  const t = e.clipboardData.getData("text"); if (/https?:\/\//.test(t)) { go("new"); addInputs(t.split(/\s+/)); toast("Enlace añadido", "ok", 1500); }
});
document.addEventListener("keydown", e => {
  if ($("player").classList.contains("on")) return;
  if ((e.ctrlKey || e.metaKey) && (e.key === "n" || e.key === "N")) { e.preventDefault(); go("new"); }
  if ((e.ctrlKey || e.metaKey) && (e.key === "f" || e.key === "F")) { e.preventDefault(); go("library"); $("libSearch").focus(); }
  if (e.key === "Escape") closeModal();
});
function updSt() { $("stV").textContent = semitones === 0 ? "Original" : (semitones > 0 ? "+" : "") + semitones + " semitono" + (Math.abs(semitones) > 1 ? "s" : ""); }
$("stUp").onclick = () => { semitones = Math.min(6, semitones + 1); updSt(); };
$("stDown").onclick = () => { semitones = Math.max(-6, semitones - 1); updSt(); };
$("lySearch").onclick = async () => {
  const box = $("lyRes"); box.innerHTML = '<span class="sub">Buscando…</span>';
  try {
    const res = await api("lyrics_search", { artist: $("lyArtist").value, title: $("lyTitle").value });
    box.innerHTML = res.length ? "" : '<span class="sub">No se encontró. Puedes pegar la letra abajo.</span>';
    for (const r of res) {
      const b = document.createElement("button");
      b.textContent = `${r.artist} — ${r.title} · ${r.album || ""} · ${r.duration ? fmt(r.duration) : ""} ${r.synced ? "· sincronizada" : ""}`;
      b.onclick = () => { $("lyText").value = r.text; box.innerHTML = `<span class="sub">${icon("check", 14)} Letra elegida</span>`; };
      box.appendChild(b);
    }
  } catch (e) { box.innerHTML = '<span class="sub">Sin conexión para buscar la letra.</span>'; }
};
$("create").onclick = async () => {
  if (!QUEUE.length) return;
  if (!MODELS_READY) { toast("Primero descarga los componentes en Ajustes", "err"); go("settings"); return; }
  const single = QUEUE.length === 1;
  const options = { semitones, language: $("optLang").value || null, use_source_video: $("optVideoBg").checked, guide_track: $("optGuide").checked };
  if (single) Object.assign(options, { lyrics: $("lyText").value.trim() || null, artist: $("lyArtist").value.trim(), title: $("lyTitle").value.trim() });
  try {
    await api("jobs", { inputs: QUEUE, options });
    toast(single ? "¡Listo! Tu canción se está preparando." : `${QUEUE.length} canciones en preparación.`, "ok");
    QUEUE = []; renderQueue(); $("lyText").value = ""; $("lyRes").innerHTML = ""; $("lyArtist").value = $("lyTitle").value = "";
    go("jobs"); pollJobs();
  } catch (e) { toast("No se pudo iniciar: " + e.message, "err"); }
};

// ---------------- en proceso ----------------
let JOBS = [], knownDone = new Set(), firstPoll = true;
async function pollJobs() {
  try { JOBS = await api("jobs"); } catch (e) { return; }
  const active = JOBS.filter(j => j.state === "running" || j.state === "queued").length;
  $("jobsBadge").hidden = !active; $("jobsBadge").textContent = active;
  for (const j of JOBS) {
    if ((j.state === "done" || j.state === "error") && !knownDone.has(j.id)) {
      knownDone.add(j.id);
      if (!firstPoll) notifyDone(j);
    }
  }
  firstPoll = false;
  if ($("v-jobs").classList.contains("on")) renderJobs();
}
function mbs(b) { return b == null ? "" : b >= 1048576 ? (b / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.round(b / 1024) + " KB"; }
function dlLine(d) {
  if (!d) return "";
  if (d.phase === "start") return `${icon("loader-circle", 14, "spinning")} Conectando con el sitio y buscando el video…`;
  if (d.phase === "merge") return `${icon("loader-circle", 14, "spinning")} Descarga completa, uniendo audio y video…`;
  const pct = d.fraction != null ? Math.round(d.fraction * 100) + " %" : mbs(d.bytes);
  const parts = [`Descargando ${pct}`];
  if (d.total) parts.push(`${mbs(d.bytes)} de ${mbs(d.total)}`);
  if (d.speed) parts.push(mbs(d.speed) + "/s");
  if (d.eta != null) parts.push(d.eta < 60 ? `faltan ${Math.max(1, Math.round(d.eta))} s` : `faltan ~${Math.round(d.eta / 60)} min`);
  const slow = d.speed != null && d.speed < 150 * 1024;
  return `${icon("download", 14)} ${parts.join(" · ")}` + (slow ? ` <span class="warnTxt">· descarga lenta</span>` : "")
    + (d.fraction != null ? `<div class="pbar thin"><i style="width:${Math.round(d.fraction * 100)}%"></i></div>` : "");
}
function eta(s) { if (s == null) return "calculando…"; if (s < 60) return "menos de 1 min"; return "faltan ~" + Math.round(s / 60) + " min"; }
function renderJobs() {
  const L = $("jobsList"); $("jobsEmpty").style.display = JOBS.length ? "none" : "block";
  const open = new Set([...L.querySelectorAll("details[open]")].map(d => d.dataset.id));
  L.innerHTML = "";
  for (const j of [...JOBS].reverse()) {
    const ci = j.steps.findIndex(s => s.key === j.step);
    const steps = j.steps.map((s, i) => {
      const cls = j.state === "done" || i < ci ? "done" : (i === ci && j.state === "running" ? "cur" : "");
      return (i ? `<div class="conn ${j.state === "done" || i <= ci ? "done" : ""}"></div>` : "") +
        `<div class="st ${cls}"><div class="dot">${cls === "done" ? icon("check", 13) : i + 1}</div>${esc(s.name)}</div>`;
    }).join("");
    const label = { queued: "En espera", running: "Preparando", done: "Lista", error: "Error", cancelled: "Cancelada" }[j.state];
    const pct = Math.round(j.fraction * 100);
    const d = document.createElement("div"); d.className = "job " + j.state;
    d.innerHTML = `<div class="top"><div class="t"><b>${esc(j.title)}</b><span>${esc(j.artist || "")}</span></div>
        <span class="state ${j.state}">${label}</span>
        ${j.state === "running" || j.state === "queued" ? `<button class="btn sm ghost" data-c="${j.id}">Cancelar</button>` : ""}
        ${j.state === "done" && j.result?.song_id ? `<button class="btn sm pri" data-p="${j.result.song_id}">${icon("play", 15)} Cantar</button><button class="btn sm" title="Abrir carpeta" data-f="${esc(j.result.folder)}">${icon("folder-open", 15)}</button>` : ""}</div>
      ${j.state === "cancelled" ? "" : `<div class="steps">${steps}</div>
      <div class="pbar"><i style="width:${pct}%"></i></div>
      <div class="pinfo"><span>${pct} %</span><span>${j.state === "running" ? eta(j.eta) : j.state === "queued" ? "esperando turno" : ""}</span></div>
      ${j.state === "running" && j.download ? `<div class="dl">${dlLine(j.download)}</div>` : ""}`}
      ${j.state === "error" ? `<div class="errmsg">${icon("circle-alert", 15)} ${esc(j.error || "No se pudo preparar esta canción.")}
        ${/robot|navegador/.test(j.error || "") ? ` <button class="btn sm" data-go2="settings">Abrir Ajustes</button>` : ""}</div>` : ""}
      ${j.log?.length ? `<details data-id="${j.id}" ${open.has(j.id) ? "open" : ""}><summary class="sub" style="cursor:pointer;margin-top:10px">Detalles técnicos</summary><pre class="log">${esc(j.log.join("\n"))}</pre></details>` : ""}`;
    L.appendChild(d);
  }
  L.querySelectorAll("[data-c]").forEach(b => b.onclick = async () => { await api(`jobs/${b.dataset.c}/cancel`, {}); toast("Cancelada"); pollJobs(); });
  L.querySelectorAll("[data-p]").forEach(b => b.onclick = () => openSong(b.dataset.p));
  L.querySelectorAll("[data-go2]").forEach(b => b.onclick = () => go(b.dataset.go2));
  L.querySelectorAll("[data-f]").forEach(b => b.onclick = () => openPath(b.dataset.f));
}
$("clearJobs").onclick = async () => { await api("jobs/clear", {}); pollJobs(); };
async function notifyDone(j) {
  const ok = j.state === "done";
  toast(ok ? `“${j.title}” está lista para cantar` : `No se pudo preparar “${j.title}”`, ok ? "ok" : "err", 6000);
  if (ok && $("v-library").classList.contains("on")) loadLibrary();
  try {
    const N = T?.notification; if (!N || document.hasFocus()) return;
    let g = await N.isPermissionGranted(); if (!g) g = (await N.requestPermission()) === "granted";
    if (g) N.sendNotification({ title: "Karaoke Easy", body: ok ? `“${j.title}” está lista para cantar` : `No se pudo preparar “${j.title}”` });
  } catch (e) { }
}

// ---------------- ajustes ----------------
async function loadSettings() {
  const s = await api("settings");
  $("sOut").value = s.output_dir; $("sLang").value = s.language || ""; $("sQuality").value = s.quality;
  $("sVideoBg").checked = s.use_source_video; $("sGuide").checked = s.guide_track; $("sCookies").value = s.cookies_browser || "";
  $("sTheme").value = localStorage.getItem("ke_theme") || "dark";
  $("optVideoBg").checked = s.use_source_video; $("optGuide").checked = s.guide_track; $("optLang").value = s.language || "";
}
async function saveSettings() {
  await api("settings", { output_dir: $("sOut").value.trim(), language: $("sLang").value || null, quality: $("sQuality").value,
    use_source_video: $("sVideoBg").checked, guide_track: $("sGuide").checked, cookies_browser: $("sCookies").value });
  toast("Ajustes guardados", "ok", 1500);
}
["sOut", "sLang", "sQuality", "sVideoBg", "sGuide", "sCookies"].forEach(id => $(id).onchange = saveSettings);
$("sTheme").onchange = () => { localStorage.setItem("ke_theme", $("sTheme").value); applyTheme(); };
function applyTheme() { document.documentElement.dataset.theme = localStorage.getItem("ke_theme") || "dark"; }
$("sOutPick").onclick = async () => {
  if (!T?.dialog) return toast("Escribe la ruta de la carpeta en el campo.");
  const r = await T.dialog.open({ directory: true }); if (r) { $("sOut").value = r; saveSettings(); }
};
$("sOutOpen").onclick = () => openPath($("sOut").value);
$("sUpd").onclick = () => checkUpdate(true);
$("sDiag").onclick = async () => {
  const d = await api("diag");
  modal("Registro de diagnóstico", `<p class="sub">${esc(d.path)}</p><pre class="log" style="max-height:50vh">${esc(d.tail.split("\n").slice(-200).join("\n") || "(vacío)")}</pre>`,
    [{ label: "Copiar", onclick: async () => { await navigator.clipboard.writeText(d.tail); toast("Copiado", "ok", 1500); return false; } }, { label: "Cerrar", primary: true }]);
};
$("sDiagCopy").onclick = async () => { const d = await api("diag"); try { await navigator.clipboard.writeText(d.tail); toast("Registro copiado: pégalo en el chat", "ok"); } catch (e) { toast("No se pudo copiar", "err"); } };

// ---------------- actualizaciones ----------------
let VERSION = "0";
const vnum = v => v.split(".").map(n => +n || 0);
const newer = (a, b) => { const x = vnum(a), y = vnum(b); for (let i = 0; i < 3; i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); } return false; };
let BUNDLED = true;
async function checkUpdate(manual) {
  try {
    const r = await (await fetch("https://api.github.com/repos/Rixmerz/Karaoke-easy/releases/latest")).json();
    const v = (r.tag_name || "").replace(/^v/, "");
    if (v && newer(v, VERSION)) {
      const box = $("updateBox"); box.style.display = "block"; box.innerHTML = `${icon("download", 15)} <b>Versión ${esc(v)} disponible</b><br>Haz clic para actualizar`;
      box.onclick = () => updateFlow(r, v);
      if (manual) updateFlow(r, v);
    } else if (manual) toast("Ya tienes la última versión", "ok");
  } catch (e) { if (manual) toast("No se pudo comprobar (¿sin internet?)", "err"); }
}
function updateFlow(rel, v) {
  const assets = (rel.assets || []).filter(a => /^KaraokeEasy-Setup-.*\.exe$/i.test(a.name));
  const asset = assets.find(a => BUNDLED ? !/Ligero/i.test(a.name) : /Ligero/i.test(a.name)) || assets[0];
  if (!asset || !T?.core) { T?.opener ? T.opener.openUrl(rel.html_url) : open(rel.html_url); return; }
  const mb = Math.round(asset.size / 1048576);
  modal(`Actualizar a la versión ${esc(v)}`, `<p>Se descargará la actualización (${mb} MB) y se instalará automáticamente. La app se reiniciará al terminar.</p>
    <div class="pbar updbar" id="uBar"><i></i></div><p class="sub" id="uTxt">Tu biblioteca y tus ajustes se conservan.</p>`, [
    { label: "Más tarde" },
    { label: `${icon("download", 15)} Actualizar ahora`, primary: true, onclick: async () => {
        const btn = $("mBtns").lastElementChild; btn.disabled = true;
        await api("update/download", { url: asset.browser_download_url });
        const poll = setInterval(async () => {
          const st = await api("update");
          $("uBar").querySelector("i").style.width = Math.round(st.progress * 100) + "%";
          $("uTxt").textContent = st.state === "running" ? `Descargando… ${Math.round(st.progress * 100)} %` : st.state === "error" ? "Error: " + st.error : "Descarga completa";
          if (st.state === "done") { clearInterval(poll); $("uTxt").textContent = "Instalando… la app se reiniciará sola.";
            try { await T.core.invoke("run_installer", { path: st.path }); } catch (e) { $("uTxt").textContent = "No se pudo instalar: " + e; } }
          if (st.state === "error") { clearInterval(poll); btn.disabled = false; }
        }, 600);
        return false; } }]);
}
// ---------------- componentes (instalador ligero) ----------------
let MODELS_READY = true;
async function refreshModels() {
  let m; try { m = await api("models"); } catch (e) { return; }
  MODELS_READY = m.ready; $("needModels").hidden = m.ready;
  const d = m.download, bar = $("mBar");
  if (m.ready) { $("sModels").textContent = BUNDLED ? "Incluidos en esta instalación" : "Descargados y listos"; $("sModelsBtn").hidden = true; bar.style.display = "none"; return true; }
  $("sModelsBtn").hidden = d.state === "running" || d.state === "extracting";
  bar.style.display = d.state === "running" || d.state === "extracting" ? "block" : "none";
  bar.querySelector("i").style.width = Math.round(d.progress * 100) + "%";
  $("sModels").textContent = d.state === "running" ? `Descargando… ${Math.round(d.progress * 100)} %` : d.state === "extracting" ? "Instalando componentes…"
    : d.state === "error" ? "Error al descargar: " + d.error : "Necesarios para crear karaokes (descarga única de ≈1,2 GB)";
  return false;
}
$("sModelsBtn").onclick = async () => {
  await api("models/download", {}); refreshModels();
  const t = setInterval(async () => { const ok = await refreshModels(); const st = (await api("models")).download.state;
    if (ok || st === "error") { clearInterval(t); if (ok) toast("Componentes listos. ¡Ya puedes crear karaokes!", "ok"); } }, 1000);
};

// ---------------- primer arranque ----------------
function onboarding(step = 0) {
  const steps = [
    ["Bienvenido a Karaoke Easy", `<p>Convierte cualquier canción en un karaoke: <b>quita la voz</b>, prepara la <b>letra sincronizada</b> y te deja cantar con <b>el tono que prefieras</b>.</p>
      <p class="sub">Funciona sin internet (solo lo usa para buscar letras y descargar enlaces).</p>`],
    ["¿Dónde guardamos tus karaokes?", `<p class="sub">Aquí se guardan los videos, las pistas sin voz y tu biblioteca.</p>
      <div class="row"><input class="field" id="obOut" style="flex:1" value="${esc($("sOut").value)}"><button class="btn sm" id="obPick">Elegir…</button></div>`],
    ["Así se canta", `<div class="checks" style="gap:10px">
      <div>${icon("plus", 16)} <b>Nueva canción</b>: arrastra un archivo o pega un enlace.</div>
      <div>${icon("mic", 16)} <b>Voz</b>: súbela o bájala en vivo (tecla V).</div>
      <div>${icon("music-2", 16)} <b>Tono</b>: + y − para cantarla más alta o más baja.</div>
      <div>${icon("party-popper", 16)} <b>Modo fiesta</b>: varias canciones seguidas.</div>
      <div>${icon("monitor", 16)} <b>Segunda pantalla</b>: la letra en la TV, los controles en tu PC.</div></div>`]];
  const [title, body] = steps[step], last = step === steps.length - 1;
  modal(title, body + `<p class="sub" style="text-align:center;margin-top:16px">${steps.map((_, i) => i === step ? "●" : "○").join(" ")}</p>`, [
    ...(step ? [{ label: "Atrás", onclick: () => { setTimeout(() => onboarding(step - 1), 0); } }] : [{ label: "Omitir", onclick: () => localStorage.setItem("ke_onboarded", "1") }]),
    { label: last ? "¡Empezar!" : "Siguiente", primary: true, onclick: async () => {
        if (step === 1 && $("obOut").value.trim() && $("obOut").value.trim() !== $("sOut").value) { $("sOut").value = $("obOut").value.trim(); await saveSettings(); }
        if (last) { localStorage.setItem("ke_onboarded", "1"); go("new"); } else setTimeout(() => onboarding(step + 1), 0); } }]);
  if (step === 1) $("obPick").onclick = async () => { if (!T?.dialog) return; const r = await T.dialog.open({ directory: true }); if (r) $("obOut").value = r; };
}

// ---------------- autoprueba de punta a punta (como un usuario) ----------------
async function e2eSelftest(url) {
  const say = m => T.core.invoke("selftest_log", { msg: m }).catch(() => { });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  closeModal();
  go("new"); $("links").value = url; $("addLinks").click();
  say(`cola: ${JSON.stringify(QUEUE)} · botón crear ${$("create").disabled ? "DESACTIVADO" : "activo"}`);
  if ($("create").disabled) { say("ERROR: el botón Crear karaoke quedó desactivado"); return false; }
  $("create").click();
  const t0 = Date.now(); let last = "", job = null;
  while (Date.now() - t0 < 15 * 60 * 1000) {
    await sleep(1000);
    job = JOBS[JOBS.length - 1];
    const card = document.querySelector("#jobsList .job");
    const txt = job ? `${job.state} paso=${job.step} ${Math.round(job.fraction * 100)}% ${card ? "| tarjeta: " + card.querySelector(".state")?.textContent + (card.querySelector(".dl") ? " · " + card.querySelector(".dl").innerText : "") : "| SIN TARJETA"}` : "sin trabajo en la lista";
    if (txt !== last) { say(`${Math.round((Date.now() - t0) / 1000)}s ${txt}`); last = txt; }
    if (job && ["done", "error", "cancelled"].includes(job.state)) break;
  }
  if (!job || job.state !== "done") { say("ERROR: " + (job ? job.state + " " + (job.error || "") : "no se creó el trabajo")); (job?.log || []).slice(-30).forEach(l => say("  " + l)); return false; }
  // la canción nueva debe aparecer en la biblioteca y abrirse en el reproductor
  go("library"); await loadLibrary();
  const sid = job.result?.song_id;
  if (!LIB.some(s => s.id === sid)) { say("ERROR: la canción no apareció en la biblioteca"); return false; }
  await openSong(sid); for (let i = 0; i < 20 && inst.readyState < 1; i++) await sleep(500);
  const okPlayer = $("player").classList.contains("on") && inst.readyState >= 1 && lines.length > 0;
  say(`reproductor: abierto=${$("player").classList.contains("on")} audio=${inst.readyState} versos=${lines.length}`);
  return okPlayer;
}

// ---------------- arranque ----------------
function splash(txt) { if (txt) $("splashTxt").textContent = txt; }
async function boot() {
  applyTheme(); hydrateIcons(); $("play").innerHTML = icon("play", 20);
  if (new URLSearchParams(location.search).get("view") === "lyrics") { $("splash").remove(); return; }  // segunda pantalla
  if (T?.core) {
    splash("Iniciando el motor…");
    const info = await T.core.invoke("engine_info");          // {url, token, selftest}
    API.base = info.url; API.token = info.token; window.SELFTEST = info.selftest; window.SELFTEST_URL = info.selftest_url;
  } else {
    API.base = location.origin + "/"; API.token = new URLSearchParams(location.search).get("t") || "";
  }
  try { const vi = await api("version"); VERSION = vi.version; BUNDLED = vi.bundled_models; } catch (e) { }
  await refreshModels();
  $("ver").textContent = VERSION; $("sAbout").textContent = "Karaoke Easy " + VERSION;
  await loadSettings().catch(() => { });
  splash("Cargando tu biblioteca…");
  await loadLibrary();
  $("splash").classList.add("hide"); setTimeout(() => $("splash").remove(), 400);
  try { if (!localStorage.getItem("ke_onboarded") && !window.SELFTEST) onboarding(); } catch (e) { }
  pollJobs(); setInterval(pollJobs, 1000);
  setTimeout(() => checkUpdate(false), 4000);
  if (window.SELFTEST && T?.core) {      // prueba automática de la app instalada
    let ok = Array.isArray(LIB) && VERSION !== "0";
    if (ok && window.SELFTEST_URL) ok = await e2eSelftest(window.SELFTEST_URL);
    await T.core.invoke("selftest_done", { ok });
  }
}
boot().catch(e => {
  splash("No se pudo iniciar Karaoke Easy: " + (e.message || e));
  document.querySelector("#splash .spin")?.remove();
});

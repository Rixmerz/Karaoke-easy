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
  if (view === "settings") loadSettings();
}
document.querySelectorAll("[data-view]").forEach(b => b.onclick = () => go(b.dataset.view));
document.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));

// ---------------- biblioteca ----------------
let LIB = [];
async function loadLibrary() {
  try { LIB = await api("library"); } catch (e) { LIB = []; }
  renderLibrary();
}
function renderLibrary() {
  const q = $("libSearch").value.toLowerCase(), sort = $("libSort").value;
  let items = LIB.filter(s => ((s.title || "") + " " + (s.artist || "")).toLowerCase().includes(q));
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
      <div class="meta"><b>${esc(s.title || "(sin título)")}</b><span>${esc(s.artist || "Artista desconocido")}</span>
      <div class="chips">${s.key ? `<span class="chip">${icon("music-2", 12)} ${esc(s.key)}</span>` : ""}${s.duration ? `<span class="chip">${fmt(s.duration)}</span>` : ""}</div></div>`;
    c.onclick = () => openSong(s.id);
    c.querySelector(".more").onclick = e => { e.stopPropagation(); songMenu(e, s); };
    g.appendChild(c);
  }
  if (LIB.length && !items.length) g.innerHTML = `<p class="sub">Sin resultados para “${esc(q)}”.</p>`;
}
$("libSearch").oninput = renderLibrary; $("libSort").onchange = renderLibrary;
function songMenu(e, s) {
  closeMenu();
  const m = document.createElement("div"); m.className = "menu"; m.id = "menu";
  m.innerHTML = `<button data-a="play">${icon("play", 15)} Cantar</button><button data-a="edit">${icon("pencil", 15)} Editar título y artista</button><button data-a="folder">${icon("folder-open", 15)} Abrir carpeta</button><button data-a="remove">${icon("trash-2", 15)} Quitar de la biblioteca</button>`;
  m.style.left = Math.min(e.clientX, innerWidth - 210) + "px"; m.style.top = e.clientY + "px";
  m.onclick = async ev => {
    const a = ev.target.dataset.a; closeMenu();
    if (a === "play") openSong(s.id);
    if (a === "edit") editSong(s);
    if (a === "folder") openPath(s.folder.replace(/[\\/]reproductor$/, ""));
    if (a === "remove") { await api("delete?id=" + s.id, {}); toast("Quitada de la biblioteca (los archivos se conservan)"); loadLibrary(); }
  };
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
}
function closeMenu() { $("menu")?.remove(); }

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
      <div class="pinfo"><span>${pct} %</span><span>${j.state === "running" ? eta(j.eta) : j.state === "queued" ? "esperando turno" : ""}</span></div>`}
      ${j.state === "error" ? `<div class="errmsg">No se pudo preparar esta canción. ${esc(j.error || "")}</div>` : ""}
      ${j.log?.length ? `<details data-id="${j.id}" ${open.has(j.id) ? "open" : ""}><summary class="sub" style="cursor:pointer;margin-top:10px">Detalles técnicos</summary><pre class="log">${esc(j.log.join("\n"))}</pre></details>` : ""}`;
    L.appendChild(d);
  }
  L.querySelectorAll("[data-c]").forEach(b => b.onclick = async () => { await api(`jobs/${b.dataset.c}/cancel`, {}); toast("Cancelada"); pollJobs(); });
  L.querySelectorAll("[data-p]").forEach(b => b.onclick = () => openSong(b.dataset.p));
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
  $("sVideoBg").checked = s.use_source_video; $("sGuide").checked = s.guide_track;
  $("sTheme").value = localStorage.getItem("ke_theme") || "dark";
  $("optVideoBg").checked = s.use_source_video; $("optGuide").checked = s.guide_track; $("optLang").value = s.language || "";
}
async function saveSettings() {
  await api("settings", { output_dir: $("sOut").value.trim(), language: $("sLang").value || null, quality: $("sQuality").value,
    use_source_video: $("sVideoBg").checked, guide_track: $("sGuide").checked });
  toast("Ajustes guardados", "ok", 1500);
}
["sOut", "sLang", "sQuality", "sVideoBg", "sGuide"].forEach(id => $(id).onchange = saveSettings);
$("sTheme").onchange = () => { localStorage.setItem("ke_theme", $("sTheme").value); applyTheme(); };
function applyTheme() { document.documentElement.dataset.theme = localStorage.getItem("ke_theme") || "dark"; }
$("sOutPick").onclick = async () => {
  if (!T?.dialog) return toast("Escribe la ruta de la carpeta en el campo.");
  const r = await T.dialog.open({ directory: true }); if (r) { $("sOut").value = r; saveSettings(); }
};
$("sOutOpen").onclick = () => openPath($("sOut").value);
$("sUpd").onclick = () => checkUpdate(true);

// ---------------- actualizaciones ----------------
let VERSION = "0";
const vnum = v => v.split(".").map(n => +n || 0);
const newer = (a, b) => { const x = vnum(a), y = vnum(b); for (let i = 0; i < 3; i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); } return false; };
async function checkUpdate(manual) {
  try {
    const r = await (await fetch("https://api.github.com/repos/Rixmerz/Karaoke-easy/releases/latest")).json();
    const v = (r.tag_name || "").replace(/^v/, "");
    if (v && newer(v, VERSION)) {
      const box = $("updateBox"); box.style.display = "block"; box.innerHTML = `${icon("download", 15)} <b>Versión ${esc(v)} disponible</b><br>Haz clic para actualizar`;
      box.onclick = () => T?.opener ? T.opener.openUrl(r.html_url) : open(r.html_url);
      if (manual) toast(`Hay una versión nueva: ${v}`, "ok");
    } else if (manual) toast("Ya tienes la última versión ✓", "ok");
  } catch (e) { if (manual) toast("No se pudo comprobar (¿sin internet?)", "err"); }
}

// ---------------- arranque ----------------
function splash(txt) { if (txt) $("splashTxt").textContent = txt; }
async function boot() {
  applyTheme(); hydrateIcons(); $("play").innerHTML = icon("play", 20);
  if (T?.core) {
    splash("Iniciando el motor…");
    const info = await T.core.invoke("engine_info");          // {url, token, selftest}
    API.base = info.url; API.token = info.token; window.SELFTEST = info.selftest;
  } else {
    API.base = location.origin + "/"; API.token = new URLSearchParams(location.search).get("t") || "";
  }
  try { VERSION = (await api("version")).version; } catch (e) { }
  $("ver").textContent = VERSION; $("sAbout").textContent = "Karaoke Easy " + VERSION;
  await loadSettings().catch(() => { });
  splash("Cargando tu biblioteca…");
  await loadLibrary();
  $("splash").classList.add("hide"); setTimeout(() => $("splash").remove(), 400);
  pollJobs(); setInterval(pollJobs, 1000);
  setTimeout(() => checkUpdate(false), 4000);
  if (window.SELFTEST && T?.core) {      // prueba automática de la app instalada
    const ok = Array.isArray(LIB) && VERSION !== "0";
    await T.core.invoke("selftest_done", { ok });
  }
}
boot().catch(e => {
  splash("No se pudo iniciar Karaoke Easy: " + (e.message || e));
  document.querySelector("#splash .spin")?.remove();
});

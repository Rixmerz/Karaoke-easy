/* Reproductor (letra en vivo, voz, tono, velocidad, A-B, ajuste de sincronía). */
let song=null,lines=[],undo=[],dirty=false;
let inst=new Audio(),voz=new Audio(),ctx=null,gInst,gVoz,gMaster;
let pitch=0,speed=1,A=null,B=null,editMode=false;
inst.preload=voz.preload="auto";inst.crossOrigin=voz.crossOrigin="anonymous";
for(const a of [inst,voz]){a.preservesPitch=true;a.mozPreservesPitch=true;a.webkitPreservesPitch=true}
const video=$("bgvideo");

function setupAudio(){
  if(ctx)return;
  ctx=new (window.AudioContext||window.webkitAudioContext)();
  gMaster=ctx.createGain();gMaster.connect(ctx.destination);
  gInst=ctx.createGain();gVoz=ctx.createGain();
  ctx.createMediaElementSource(inst).connect(gInst).connect(gMaster);
  ctx.createMediaElementSource(voz).connect(gVoz).connect(gMaster);
  applyVoice();applyVol();
}
function applyVoice(){const v=+$("voice").value;$("voiceV").textContent=v+" %";if(gVoz)gVoz.gain.value=v/100;try{localStorage.setItem("ke_voice",v)}catch(e){}if(typeof savePref==="function")savePref("voice",v)}
function applyVol(){if(gMaster)gMaster.gain.value=(+$("vol").value)/100}

// ---------- Canción ----------
async function openSong(id){
  loading(true,"Cargando canción…");
  try{song=await api("song?id="+encodeURIComponent(id))}catch(e){loading(false);toast("No se pudo abrir la canción","err");return}
  $("player").classList.add("on");
  lines=song.lines;undo=[];dirty=false;pitch=0;speed=1;A=B=null;
  let h=0;for(const ch of (song.title||"x"))h=(h*31+ch.charCodeAt(0))%360;document.documentElement.style.setProperty("--hue",h);
  $("t1").textContent=song.title||"";$("t2").textContent=(song.artist||"")+(song.key_name?"  ·  Tono "+song.key_name:"");
  document.title=(song.title||"Karaoke")+" — Karaoke Easy";
  inst.src=media(id,"inst.m4a");voz.src=media(id,"voz.m4a");
  if(song.has_video){video.src=media(id,"video");video.style.display="block"}else{video.removeAttribute("src");video.style.display="none"}
  try{$("voice").value=localStorage.getItem("ke_voice")??0}catch(e){}
  applyVoice();updPitch();updSpeed();drawMarks();buildList();drawAB();
  inst.load();voz.load();
  await waitMeta();
  loading(false);seekTo(0);
  updParty();broadcastSong();
  const pr=prefs(id);
  if(pr.voice!=null){$("voice").value=pr.voice;applyVoice()}
  if(pr.speed&&pr.speed!==1){speed=pr.speed;updSpeed()}
  if(pr.pitch){await setPitch(pr.pitch)}
  if(PARTY)play();
}
// ---------- preferencias por canción (tono, velocidad, voz) ----------
function prefs(id){try{return JSON.parse(localStorage.getItem("ke_pref_"+id)||"{}")}catch(e){return {}}}
function savePref(k,v){if(!song)return;const p=prefs(song.id);p[k]=v;try{localStorage.setItem("ke_pref_"+song.id,JSON.stringify(p))}catch(e){}}
function drawMarks(){const m=$("marks");m.innerHTML="";const d=song.duration||inst.duration||1;
  for(const l of lines){const i=document.createElement("i");i.style.left=(l[0].s/d*100)+"%";m.appendChild(i)}}
function buildList(){const box=$("lineList");box.innerHTML="";lines.forEach((l,i)=>{const d=document.createElement("div");d.className="li";d.dataset.i=i;
  d.innerHTML=`<small>${fmt(l[0].s)}</small>`;d.appendChild(document.createTextNode(l.map(w=>w.w).join(" ")));d.onclick=()=>seekTo(Math.max(0,l[0].s-1.5));box.appendChild(d)})}

// ---------- Transporte ----------
function isPlaying(){return !inst.paused}
async function play(){setupAudio();if(ctx.state==="suspended")await ctx.resume();
  voz.currentTime=inst.currentTime;if(song?.has_video)video.currentTime=inst.currentTime;
  await Promise.all([inst.play(),voz.play(),song?.has_video?video.play().catch(()=>{}):null]);$("play").innerHTML=icon("pause",20)}
function pause(){inst.pause();voz.pause();video.pause();$("play").innerHTML=icon("play",20)}
function toggle(){isPlaying()?pause():play()}
function waitMeta(ms=20000){return new Promise(res=>{if(inst.readyState>=1)return res(true);
  const done=ok=>{clearTimeout(to);inst.removeEventListener("loadedmetadata",h);res(ok)};const h=()=>done(true);
  const to=setTimeout(()=>done(false),ms);inst.addEventListener("loadedmetadata",h)})}
function seekTo(t){if(inst.readyState<1){inst.addEventListener("loadedmetadata",()=>seekTo(t),{once:true});return}
  t=Math.max(0,Math.min(t,(inst.duration||song.duration||0)-0.05));inst.currentTime=voz.currentTime=t;if(song?.has_video)video.currentTime=t}
$("play").onclick=toggle;
$("seek").oninput=e=>seekTo(e.target.value/1000*(inst.duration||song.duration));
inst.onended=()=>{pause();onSongEnd()};

// voz
$("voice").oninput=applyVoice;$("vol").oninput=applyVol;
// tono
function updPitch(){$("pitchV").textContent=(pitch>0?"+":"")+pitch+(song?.key?"  "+keyName(song.key[0]+pitch,song.key[1]):"")}
async function setPitch(p){p=Math.max(-6,Math.min(6,p));if(p===pitch)return;
  const was=isPlaying(),t=inst.currentTime;pause();loading(true,`Cambiando el tono a ${keyName(song.key[0]+p,song.key[1])}… (la primera vez tarda unos segundos)`);
  try{const r=await api(`pitch?id=${song.id}&st=${p}`);
    inst.src=media(song.id,r.inst);voz.src=media(song.id,r.voz);pitch=p;updPitch();updSpeed();
    inst.load();voz.load();await waitMeta();seekTo(t);savePref("pitch",p);if(was)play()}
  catch(e){toast("No se pudo cambiar el tono: "+e.message,3500)}finally{loading(false)}}
$("pUp").onclick=()=>setPitch(pitch+1);$("pDown").onclick=()=>setPitch(pitch-1);
// velocidad
function updSpeed(){for(const a of [inst,voz,video])a.playbackRate=speed;$("speedV").textContent=Math.round(speed*100)+" %"}
function setSpeed(s){speed=Math.round(Math.max(.5,Math.min(1.25,s))*20)/20;updSpeed();savePref("speed",speed);toast("Velocidad "+Math.round(speed*100)+" %")}
$("sUp").onclick=()=>setSpeed(speed+.05);$("sDown").onclick=()=>setSpeed(speed-.05);
// A-B
function drawAB(){const ab=$("ab"),d=inst.duration||song?.duration||1;if(A==null){ab.style.display="none";return}
  const b=B??A;ab.style.display="block";ab.style.left=(A/d*100)+"%";ab.style.width=Math.max(.3,(b-A)/d*100)+"%";
  $("aBtn").classList.toggle("on",A!=null);$("bBtn").classList.toggle("on",B!=null)}
$("aBtn").onclick=()=>{A=inst.currentTime;B=null;drawAB();toast("Inicio del tramo marcado")};
$("bBtn").onclick=()=>{if(A==null)return;B=Math.max(A+.5,inst.currentTime);drawAB();toast("Repitiendo el tramo");seekTo(A)};
$("abClear").onclick=()=>{A=B=null;drawAB();$("aBtn").classList.remove("on");$("bBtn").classList.remove("on")};
// pantalla completa, lista, editor
async function setFull(on){try{if(T?.window){await T.window.getCurrentWindow().setFullscreen(on)}else if(on)await document.documentElement.requestFullscreen();else if(document.fullscreenElement)await document.exitFullscreen()}catch(e){}}
let isFull=false;$("fsBtn").onclick=()=>{isFull=!isFull;setFull(isFull)};
function closePlayer(){if(dirty&&!confirm("Hay cambios de sincronía sin guardar. ¿Salir igualmente?"))return;
  pause();PARTY=null;$("nextUp").classList.remove("on");clearInterval(nuTimer);isFull=false;setFull(false);$("player").classList.remove("on");editMode=false;$("edit").classList.remove("open");loadLibrary()}
$("back").onclick=closePlayer;
$("listBtn").onclick=()=>$("side").classList.toggle("open");
$("editBtn").onclick=()=>{editMode=!editMode;$("edit").classList.toggle("open",editMode);$("editBtn").classList.toggle("on",editMode);if(editMode)$("side").classList.add("open")};

// ---------- Editor de sincronía ----------
function curLine(t){let i=-1;for(let k=0;k<lines.length;k++){if(lines[k][0].s-0.05<=t)i=k;else break}return i}
function snapshot(){setTimeout(broadcastSong,0);undo.push(JSON.stringify(lines));if(undo.length>100)undo.shift();dirty=true;$("editInfo").textContent="cambios sin guardar"}
function shiftLine(i,dt){if(i<0||i>=lines.length)return;for(const w of lines[i]){w.s=+(w.s+dt).toFixed(3);w.e=+(w.e+dt).toFixed(3)}}
function nudge(dt,all){snapshot();if(all){for(let i=0;i<lines.length;i++)shiftLine(i,dt);toast(`Toda la letra ${dt>0?"+":""}${Math.round(dt*1000)} ms`)}
  else{const i=Math.max(0,curLine(inst.currentTime+0.3));shiftLine(i,dt);toast(`Verso ${i+1}: ${dt>0?"+":""}${Math.round(dt*1000)} ms`)}drawMarks();buildList()}
function tapNext(){const t=inst.currentTime,i=curLine(t)+1;if(i>=lines.length)return;snapshot();shiftLine(i,t-lines[i][0].s);
  // mantener el orden: empujar los siguientes si se solapan
  for(let k=i+1;k<lines.length;k++){const d=lines[k-1][lines[k-1].length-1].s+0.1-lines[k][0].s;if(d>0)shiftLine(k,d);else break}
  toast(`Verso ${i+1} empieza en ${fmt(t)}`);drawMarks();buildList()}
async function save(){try{await api(`save?id=${song.id}`,{lines});dirty=false;$("editInfo").textContent="guardado";toast("Sincronía guardada","ok",1500)}
  catch(e){toast("Error al guardar","err")}}
$("saveBtn").onclick=save;$("undoBtn").onclick=()=>{if(!undo.length)return;lines=JSON.parse(undo.pop());drawMarks();buildList();toast("Deshecho")};
window.addEventListener("beforeunload",e=>{if(dirty){e.preventDefault();e.returnValue=""}});

// ---------- Teclado ----------
document.addEventListener("keydown",e=>{
  if(!$("player").classList.contains("on")||e.target.tagName==="INPUT"&&e.target.type!=="range")return;
  const k=e.key;
  if(k===" "){e.preventDefault();toggle()}
  else if(k==="v"||k==="V"){$("voice").value=+$("voice").value>0?0:100;applyVoice();toast("Voz "+$("voice").value+" %")}
  else if(k==="ArrowUp"){e.preventDefault();$("voice").value=Math.min(100,+$("voice").value+10);applyVoice()}
  else if(k==="ArrowDown"){e.preventDefault();$("voice").value=Math.max(0,+$("voice").value-10);applyVoice()}
  else if(k==="ArrowRight"){e.preventDefault();seekTo(inst.currentTime+5)}
  else if(k==="ArrowLeft"){e.preventDefault();seekTo(inst.currentTime-5)}
  else if(k==="+"||k==="="){setPitch(pitch+1)}else if(k==="-"||k==="_"){setPitch(pitch-1)}
  else if(k==="]"){setSpeed(speed+.05)}else if(k==="["){setSpeed(speed-.05)}
  else if(k==="a"||k==="A"){$("aBtn").click()}else if(k==="b"||k==="B"){$("bBtn").click()}
  else if(k==="Escape"){if(A!=null)$("abClear").click();else closePlayer()}
  else if(k==="f"||k==="F"){$("fsBtn").click()}else if(k==="l"||k==="L"){$("listBtn").click()}else if(k==="e"||k==="E"){$("editBtn").click()}
  else if(editMode&&(k===","||k==="<")){nudge(-0.05,e.shiftKey||k==="<")}
  else if(editMode&&(k==="."||k===">")){nudge(0.05,e.shiftKey||k===">")}
  else if(editMode&&k==="Enter"){e.preventDefault();tapNext()}
  else if((e.ctrlKey||e.metaKey)&&(k==="s"||k==="S")){e.preventDefault();save()}
});
let idleT;document.addEventListener("mousemove",()=>{$("player").classList.remove("idle");clearTimeout(idleT);idleT=setTimeout(()=>{if(isPlaying())$("player").classList.add("idle")},2500)});

// ---------- Dibujo de la letra ----------
function renderLine(el,line,t){
  if(!line){el.innerHTML="";el.dataset.k="";return}
  const key=line[0].s+"|"+line.length+"|"+line[0].w;
  if(el.dataset.k!==key){el.dataset.k=key;el.innerHTML="";for(const w of line){const s=document.createElement("span");s.className="w";s.textContent=w.w;el.appendChild(s)}}
  const spans=el.children;
  for(let i=0;i<line.length;i++){const w=line[i],end=i+1<line.length?line[i+1].s:w.e;let p=(t-w.s)/Math.max(.05,end-w.s);p=Math.max(0,Math.min(1,p));spans[i].style.setProperty("--p",p)}
}
function frame(){
  requestAnimationFrame(frame);if(!song||!$("player").classList.contains("on"))return;
  const t=REMOTE?remoteTime():inst.currentTime,d=inst.duration||song.duration||1;
  if(!REMOTE)tick(t);
  if(!REMOTE&&isPlaying()){ // sincronía de voz y vídeo con la pista principal
    if(Math.abs(voz.currentTime-t)>0.06)voz.currentTime=t;
    if(song.has_video&&Math.abs(video.currentTime-t)>0.25)video.currentTime=t;
    if(A!=null&&B!=null&&t>=B)seekTo(A);
  }
  if(document.activeElement!==$("seek"))$("seek").value=t/d*1000;
  $("time").textContent=fmt(t)+" / "+fmt(d);
  const ci=curLine(t),cur=lines[ci],nxt=lines[ci+1];
  const lead=1.6;let show0=cur,show1=nxt;
  if(ci<0){show0=null;show1=null;if(lines[0]&&lines[0][0].s-t<lead*2){show0=lines[0];show1=lines[1]}}
  else{const curEnd=cur[cur.length-1].e;if(t>curEnd+0.6&&nxt){ // entre versos: adelantar el siguiente
      if(nxt[0].s-t<lead*2||nxt[0].s-curEnd<6){show0=nxt;show1=lines[ci+2]}else{show0=null;show1=null}}}
  renderLine($("L0"),show0,t);renderLine($("L1"),show1,t);
  // título al inicio
  const first=lines[0]?lines[0][0].s:4;$("ptitle").style.opacity=(t<first-4.5)?1:0;
  // cuenta atrás y espera
  const upcoming=ci<0?lines[0]:nxt,prevEnd=ci<0?0:cur[cur.length-1].e;
  let dotsHtml="",wait="";
  if(upcoming){const st=upcoming[0].s,gap=st-prevEnd,left=st-t;
    if(gap>=4&&left>0){
      if(left>8&&t>prevEnd+0.5)wait=`Instrumental — la voz vuelve en ${Math.ceil(left)} s`;
      if(left<=4.2){const beats=song.beats||[];let ticks=[];
        const bi=beats.findIndex(b=>b>st+0.12);const j=(bi<0?beats.length:bi);
        if(j>=4){ticks=beats.slice(j-4,j)}if(ticks.length!==4||st-ticks[0]>5){ticks=[0,1,2,3].map(k=>st-4+k)}
        dotsHtml=ticks.map(tk=>`<span class="pd${t>=tk?" on":""}">●</span>`).join("")}}}
  $("dots").innerHTML=dotsHtml;$("wait").textContent=wait;
  if($("side").classList.contains("open")){for(const el of $("lineList").children)el.classList.toggle("cur",+el.dataset.i===ci)}
}
requestAnimationFrame(frame);


// ---------- modo fiesta ----------
let nuTimer=null;
function updParty(){const on=!!PARTY;$("partyTag").hidden=!on;$("partySkip").hidden=!on||PARTY.i>=PARTY.ids.length-1;
  if(on)$("partyPos").textContent=`Fiesta ${PARTY.i+1}/${PARTY.ids.length}`}
function onSongEnd(){
  if(!PARTY)return;
  if(PARTY.i>=PARTY.ids.length-1){toast("¡Fin del modo fiesta! 🎉","ok",4000);PARTY=null;updParty();return}
  showNext();
}
function showNext(){
  const nid=PARTY.ids[PARTY.i+1],s=LIB.find(x=>x.id===nid)||{};
  $("nuTitle").textContent=s.title||"";$("nuArtist").textContent=s.artist||"";
  $("nextUp").classList.add("on");let n=8;const tickN=()=>{$("nuCount").textContent=n;$("nextUp").querySelector(".ring").style.setProperty("--pc",(8-n)/8*100)};tickN();
  clearInterval(nuTimer);nuTimer=setInterval(()=>{n--;tickN();if(n<=0)goNext()},1000);
}
function goNext(skip){clearInterval(nuTimer);$("nextUp").classList.remove("on");if(!PARTY)return;
  PARTY.i+=skip?2:1;if(PARTY.i>=PARTY.ids.length){PARTY=null;updParty();return}openSong(PARTY.ids[PARTY.i])}
$("nuGo").onclick=()=>goNext();$("nuSkip").onclick=()=>goNext(true);
$("nuEnd").onclick=()=>{clearInterval(nuTimer);$("nextUp").classList.remove("on");PARTY=null;updParty()};
$("partySkip").onclick=()=>{if(PARTY){pause();PARTY.i++;openSong(PARTY.ids[PARTY.i])}};

// ---------- estilo de la letra ----------
const COLORS=["","#ff4d6d","#ffd23f","#3ddc97","#33c5ff","#b98cff","#ffffff"];
function lyrStyle(){try{return JSON.parse(localStorage.getItem("ke_lyr")||"{}")}catch(e){return {}}}
function applyLyrStyle(st=lyrStyle()){const P=$("player").style;
  P.setProperty("--lyr-scale",(st.size||100)/100);
  if(st.font)P.setProperty("--lyr-font",st.font);else P.removeProperty("--lyr-font");
  if(st.color)P.setProperty("--sung",st.color);else P.removeProperty("--sung");}
function saveLyrStyle(ch){const st=Object.assign(lyrStyle(),ch);try{localStorage.setItem("ke_lyr",JSON.stringify(st))}catch(e){}applyLyrStyle(st);renderSwatches();broadcastSong()}
function renderSwatches(){const st=lyrStyle();$("lyrColors").innerHTML=COLORS.map(c=>`<span class="sw ${(st.color||"")===c?"on":""}" data-c="${c}" title="${c?c:"Automático"}" style="background:${c||"conic-gradient(#ff4d6d,#ffd23f,#3ddc97,#33c5ff,#b98cff,#ff4d6d)"}"></span>`).join("");
  $("lyrColors").querySelectorAll(".sw").forEach(el=>el.onclick=()=>saveLyrStyle({color:el.dataset.c}))}
$("styleBtn").onclick=e=>{e.stopPropagation();$("stylePop").classList.toggle("open");const st=lyrStyle();$("lyrSize").value=st.size||100;$("lyrFont").value=st.font||"";renderSwatches()};
$("stylePop").onclick=e=>e.stopPropagation();document.addEventListener("click",()=>$("stylePop").classList.remove("open"));
$("lyrSize").oninput=()=>saveLyrStyle({size:+$("lyrSize").value});$("lyrFont").onchange=()=>saveLyrStyle({font:$("lyrFont").value});
applyLyrStyle();

// ---------- segunda pantalla ----------
const REMOTE=new URLSearchParams(location.search).get("view")==="lyrics";
const chan=("BroadcastChannel" in window)?new BroadcastChannel("ke-sync"):null;
let lastTick=0,remote={t:0,playing:false,rate:1,at:0};
function songMsg(){return song&&{type:"song",song:{id:song.id,title:song.title,artist:song.artist,key_name:song.key_name,beats:song.beats,duration:song.duration},
  lines,hue:getComputedStyle(document.documentElement).getPropertyValue("--hue"),style:lyrStyle()}}
function broadcastSong(){if(chan&&!REMOTE&&song)chan.postMessage(songMsg())}
function tick(t){const now=performance.now();if(!chan||now-lastTick<100)return;lastTick=now;chan.postMessage({type:"tick",t,playing:isPlaying(),rate:speed})}
function remoteTime(){return remote.t+(remote.playing?(performance.now()-remote.at)/1000*remote.rate:0)}
if(chan)chan.onmessage=e=>{const m=e.data;
  if(!REMOTE){if(m.type==="hello")broadcastSong();return}
  if(m.type==="song"){song=m.song;lines=m.lines;document.documentElement.style.setProperty("--hue",m.hue);applyLyrStyle(m.style||{});
    $("t1").textContent=song.title||"";$("t2").textContent=(song.artist||"")+(song.key_name?"  ·  Tono "+song.key_name:"");$("player").classList.add("on")}
  if(m.type==="tick"){remote={t:m.t,playing:m.playing,rate:m.rate,at:performance.now()}}};
$("screen2Btn").onclick=async()=>{
  try{
    if(T?.webviewWindow){const W=T.webviewWindow.WebviewWindow;const ex=await W.getByLabel("lyrics");if(ex){await ex.setFocus();return}
      new W("lyrics",{url:"index.html?view=lyrics",title:"Karaoke Easy — Letra",width:1280,height:720,backgroundColor:"#07070c"})}
    else window.open("?view=lyrics","kelyrics","width=1280,height=720");
    toast("Lleva la ventana nueva a la otra pantalla y haz doble clic para pantalla completa","",5000);
  }catch(e){toast("No se pudo abrir la segunda pantalla: "+e,"err")}};
if(REMOTE){document.body.classList.add("lyrics-only");$("player").classList.add("on");
  document.addEventListener("dblclick",async()=>{try{if(T?.window){const w=T.window.getCurrentWindow();await w.setFullscreen(!(await w.isFullscreen()))}else if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen()}catch(e){}});
  chan&&chan.postMessage({type:"hello"})}

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
  updParty();broadcastSong();REF=null;resetScore();$("result").classList.remove("on");if(scoring)loadRef();
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
  d.innerHTML=`<small>${fmt(l[0].s)}</small><span class="tx"></span><span class="nb"><button data-d="-1" title="Antes 0,05 s">−</button><button data-d="1" title="Después 0,05 s">+</button></span>`;
  d.querySelector(".tx").textContent=l.map(w=>w.w).join(" ");
  d.onclick=e=>{const b=e.target.closest("button");if(b){e.stopPropagation();snapshot();shiftLine(i,0.05*+b.dataset.d);drawMarks();buildList();updEditCur();return}seekTo(Math.max(0,l[0].s-1.5))};box.appendChild(d)})}

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
  recStop();micOff();pause();PARTY=null;DUEL=null;$("turn").classList.remove("on");$("ranking").classList.remove("on");$("nextUp").classList.remove("on");clearInterval(nuTimer);isFull=false;setFull(false);$("player").classList.remove("on");editMode=false;dirty=false;$("edit").classList.remove("open");$("player").classList.remove("editing");setSide(false);loadLibrary()}
$("back").onclick=closePlayer;
function setSide(on){$("side").classList.toggle("open",on);$("listBtn").classList.toggle("on",on)}
$("listBtn").onclick=()=>setSide(!$("side").classList.contains("open"));$("sideClose").onclick=()=>setSide(false);
function setEdit(on){if(!on&&dirty&&!confirm("Hay cambios sin guardar en la sincronía. ¿Salir sin guardar?\n(Pulsa Cancelar y luego Guardar para conservarlos)"))return;
  editMode=on;$("edit").classList.toggle("open",on);$("editBtn").classList.toggle("on",on);$("player").classList.toggle("editing",on);setSide(on);updEditCur()}
$("editBtn").onclick=()=>setEdit(!editMode);$("editClose").onclick=()=>setEdit(false);
$("eLm").onclick=()=>nudge(-0.05,false);$("eLp").onclick=()=>nudge(0.05,false);$("eAm").onclick=()=>nudge(-0.05,true);$("eAp").onclick=()=>nudge(0.05,true);$("eTap").onclick=()=>tapNext();
let lastCur=-2;function updEditCur(){if(!editMode)return;const i=Math.max(0,curLine(inst.currentTime+0.3));lastCur=i;const l=lines[i];$("eCurTxt").textContent=l?`${i+1}. ${l.map(w=>w.w).join(" ")}  (${fmt(l[0].s)})`:"—"}

// ---------- Editor de sincronía ----------
function curLine(t){let i=-1;for(let k=0;k<lines.length;k++){if(lines[k][0].s-0.05<=t)i=k;else break}return i}
function snapshot(){setTimeout(broadcastSong,0);undo.push(JSON.stringify(lines));if(undo.length>100)undo.shift();dirty=true;$("editInfo").textContent="cambios sin guardar";$("editInfo").classList.add("dirty")}
function shiftLine(i,dt){if(i<0||i>=lines.length)return;for(const w of lines[i]){w.s=+(w.s+dt).toFixed(3);w.e=+(w.e+dt).toFixed(3)}}
function nudge(dt,all){snapshot();if(all){for(let i=0;i<lines.length;i++)shiftLine(i,dt);toast(`Toda la letra ${dt>0?"+":""}${Math.round(dt*1000)} ms`)}
  else{const i=Math.max(0,curLine(inst.currentTime+0.3));shiftLine(i,dt);toast(`Verso ${i+1}: ${dt>0?"+":""}${Math.round(dt*1000)} ms`)}drawMarks();buildList();updEditCur()}
function tapNext(){const t=inst.currentTime,i=curLine(t)+1;if(i>=lines.length)return;snapshot();shiftLine(i,t-lines[i][0].s);
  // mantener el orden: empujar los siguientes si se solapan
  for(let k=i+1;k<lines.length;k++){const d=lines[k-1][lines[k-1].length-1].s+0.1-lines[k][0].s;if(d>0)shiftLine(k,d);else break}
  toast(`Verso ${i+1} empieza en ${fmt(t)}`);drawMarks();buildList()}
async function save(){try{await api(`save?id=${song.id}`,{lines});dirty=false;$("editInfo").textContent="guardado ✓";$("editInfo").classList.remove("dirty");toast("Sincronía guardada","ok",1500)}
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
  else if(editMode&&(e.ctrlKey||e.metaKey)&&(k==="z"||k==="Z")){e.preventDefault();$("undoBtn").click()}
});
let idleT;document.addEventListener("mousemove",()=>{$("player").classList.remove("idle");clearTimeout(idleT);idleT=setTimeout(()=>{if(isPlaying())$("player").classList.add("idle")},2500)});

// ---------- Dibujo de la letra ----------
function renderLine(el,line,t){
  if(!line){el.innerHTML="";el.dataset.k="";return}
  const key=line[0].s+"|"+line.length+"|"+line[0].w;
  if(el.dataset.k!==key){el.dataset.k=key;el.innerHTML="";for(const w of line){const s=document.createElement("span");s.className="w";s.textContent=w.w;el.appendChild(s)}}
  const spans=el.children;
  for(let i=0;i<line.length;i++){const w=line[i],nx=i+1<line.length?line[i+1].s:w.e,sung=Math.max(w.e,w.s+.05),end=nx-sung>.25?sung:nx;let p=(t-w.s)/Math.max(.05,end-w.s);p=Math.max(0,Math.min(1,p));spans[i].style.setProperty("--p",p)}
}
function frame(){
  requestAnimationFrame(frame);if(!song||!$("player").classList.contains("on"))return;
  const t=REMOTE?remoteTime():inst.currentTime,d=inst.duration||song.duration||1;
  if(!REMOTE){tick(t);scoreFrame(t)}
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
  if($("side").classList.contains("open")){for(const el of $("lineList").children){const on=+el.dataset.i===ci;if(on&&!el.classList.contains("cur")&&editMode)el.scrollIntoView({block:"nearest",behavior:"smooth"});el.classList.toggle("cur",on)}}
  if(editMode&&curLine(inst.currentTime+0.3)!==lastCur)updEditCur();
}
requestAnimationFrame(frame);


// ---------- modo fiesta ----------
let nuTimer=null;
function updParty(){if(DUEL)return updDuelTag();const on=!!PARTY;$("partyTag").hidden=!on;$("partySkip").hidden=!on||PARTY.i>=PARTY.ids.length-1;
  if(on)$("partyPos").textContent=`Fiesta ${PARTY.i+1}/${PARTY.ids.length}`}
function onSongEnd(){
  recStop();
  if(DUEL)return duelTurnEnd();
  if(showResult()&&!PARTY)return;
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
$("partySkip").onclick=()=>{if(DUEL){pause();return duelTurnEnd()}if(PARTY){pause();PARTY.i++;openSong(PARTY.ids[PARTY.i])}};

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
  if(typeof licAllows==="function"&&!licAllows("party"))return licenseBlocked("La segunda pantalla es parte del plan Eventos.");
  try{
    if(T?.webviewWindow){const W=T.webviewWindow.WebviewWindow;const ex=await W.getByLabel("lyrics");if(ex){await ex.setFocus();return}
      new W("lyrics",{url:"index.html?view=lyrics",title:"Karaoke Easy — Letra",width:1280,height:720,backgroundColor:"#07070c"})}
    else window.open("?view=lyrics","kelyrics","width=1280,height=720");
    toast("Lleva la ventana nueva a la otra pantalla y haz doble clic para pantalla completa","",5000);
  }catch(e){toast("No se pudo abrir la segunda pantalla: "+e,"err")}};
if(REMOTE){document.body.classList.add("lyrics-only");$("player").classList.add("on");
  document.addEventListener("dblclick",async()=>{try{if(T?.window){const w=T.window.getCurrentWindow();await w.setFullscreen(!(await w.isFullscreen()))}else if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen()}catch(e){}});
  chan&&chan.postMessage({type:"hello"})}

// ---------- micrófono con eco ----------
// Cada entrada (micrófono del PC o un teléfono) tiene su propia cadena: volumen + eco → gMaster,
// y un analizador para la afinación. `mic` es la entrada que se puntúa ahora.
let mic=null; // {key, stream?, src, gain, wet, an, buf, floor, hist}
const MICS={}; // "local" | "p1".."p4" -> cadena
function impulse(sec=2.2,decay=3){const n=ctx.sampleRate*sec,b=ctx.createBuffer(2,n,ctx.sampleRate);
  for(let c=0;c<2;c++){const d=b.getChannelData(c);for(let i=0;i<n;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/n,decay)}return b}
let IMPULSE=null;
function buildChain(key,src){
  const gain=ctx.createGain(),dry=ctx.createGain(),wet=ctx.createGain();
  const conv=ctx.createConvolver();conv.buffer=IMPULSE||(IMPULSE=impulse());
  const delay=ctx.createDelay(1),fb=ctx.createGain();delay.delayTime.value=0.13;fb.gain.value=0.28;
  src.connect(gain);gain.connect(dry).connect(gMaster);
  gain.connect(conv).connect(wet);gain.connect(delay);delay.connect(fb).connect(delay);delay.connect(wet);wet.connect(gMaster);
  const hp=ctx.createBiquadFilter();hp.type="highpass";hp.frequency.value=90;const lp=ctx.createBiquadFilter();lp.type="lowpass";lp.frequency.value=1500;
  const an=ctx.createAnalyser();an.fftSize=2048;src.connect(hp).connect(lp).connect(an);
  const ch={key,src,gain,wet,an,buf:new Float32Array(2048),floor:0.004,hist:[]};MICS[key]=ch;
  if(recDest){gain.connect(recDest);ch.recConnected=true}
  applyMic();return ch}
function dropChain(key){const ch=MICS[key];if(!ch)return;try{ch.src.disconnect();ch.gain.disconnect();ch.wet.disconnect()}catch(e){}delete MICS[key];
  if(mic===ch){mic=MICS.local||Object.values(MICS)[0]||null}updMicUI()}
function useMic(key){if(MICS[key]){mic=MICS[key];mic.hist=[];updMicUI();return true}return false}
function micLabel(key){if(key==="local")return "Micrófono del PC";const p=PH.phones.find(x=>"p"+x.slot===key);return p?p.name:"Teléfono "+key.slice(1)}
function updMicUI(){const on=!!MICS.local;$("micBtn").classList.toggle("on",on);$("micBtn").innerHTML=icon(on?"mic":"mic-off",15)+" Micrófono";
  const n=PH.phones.length;$("phoneBtn").classList.toggle("on",PH.active);$("phoneBtn").innerHTML=icon("smartphone",15)+" Teléfono"+(n?` (${n})`:"");
  const sel=$("micSel");if(sel){const keys=Object.keys(MICS);sel.hidden=keys.length<2;
    sel.innerHTML=keys.map(k=>`<option value="${k}" ${mic&&mic.key===k?"selected":""}>${esc(micLabel(k))}</option>`).join("")}}
async function micOn(){
  setupAudio();if(ctx.state==="suspended")await ctx.resume();
  if(MICS.local){mic=MICS.local;return}
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
  const ch=buildChain("local",ctx.createMediaStreamSource(stream));ch.stream=stream;
  if(!mic||mic.key==="local"||!DUEL)mic=ch;updMicUI();
  toast("Micrófono activo. Usa audífonos para evitar acoples.","ok",3500);
}
function micOff(){const ch=MICS.local;if(!ch)return;ch.stream.getTracks().forEach(t=>t.stop());dropChain("local")}
function applyMic(){for(const ch of Object.values(MICS)){ch.gain.gain.value=+$("micVol").value/100;ch.wet.gain.value=+$("echo").value/100*0.9}
  try{localStorage.setItem("ke_mic",JSON.stringify({vol:$("micVol").value,echo:$("echo").value,sens:$("micSens").value}))}catch(e){}}
try{const m=JSON.parse(localStorage.getItem("ke_mic")||"{}");if(m.vol)$("micVol").value=m.vol;if(m.echo)$("echo").value=m.echo;if(m.sens)$("micSens").value=m.sens}catch(e){}
$("micVol").oninput=applyMic;$("micSens").oninput=applyMic;$("echo").oninput=applyMic;
$("micBtn").onclick=async()=>{if(MICS.local)return micOff();try{await micOn()}catch(e){toast("No se pudo usar el micrófono: "+(e.message||e),"err",5000)}};
$("micSel").onchange=e=>useMic(e.target.value);

// ---------- teléfono como micrófono ----------
// El motor abre un servidor HTTPS en la red local solo mientras esto está activo. Los teléfonos
// envían PCM 16 bits a 24 kHz; aquí llega por un WebSocket local y un AudioWorklet lo reproduce
// con un pequeño colchón contra el jitter del wifi (40 ms, máximo 150 ms).
const PH={active:false,ws:null,phones:[],info:null,nodes:{},stats:{frames:0,delay:null,buf:{}},workletReady:null};
const PLAY_WORKLET=`class Ph extends AudioWorkletProcessor{
  constructor(){super();this.N=sampleRate*2|0;this.q=new Float32Array(this.N);this.w=0;this.r=0;this.primed=false;
    this.ratio=24000/sampleRate;this.pos=0;this.prev=0;this.target=sampleRate*0.04|0;this.max=sampleRate*0.15|0;this.k=0;
    this.port.onmessage=e=>{const s=new Int16Array(e.data);let p=this.pos;const L=s.length;
      // remuestreo lineal 24 kHz -> frecuencia del PC
      while(p<L){const i=Math.floor(p),f=p-i,a=i===0?this.prev:s[i-1]/32768,b=s[i]/32768;this.q[this.w%this.N]=a+(b-a)*f;this.w++;p+=this.ratio}
      this.pos=p-L;this.prev=s[L-1]/32768;
      if(this.w-this.r>this.max)this.r=this.w-this.target}} // demasiado atraso: saltar al colchón objetivo
  process(_,outputs){const o=outputs[0][0];const have=this.w-this.r;
    if(!this.primed){if(have>=this.target)this.primed=true;else{o.fill(0);return true}}
    for(let i=0;i<o.length;i++){if(this.r<this.w){o[i]=this.q[this.r%this.N];this.r++}else{o[i]=0;this.primed=false}}
    if(++this.k%50===0)this.port.postMessage(have/sampleRate*1000);return true}}
registerProcessor("ke-phone",Ph);`;
function phoneWorklet(){setupAudio();return PH.workletReady||(PH.workletReady=ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([PLAY_WORKLET],{type:"text/javascript"}))))}
async function phoneSync(phones){
  PH.phones=phones||[];await phoneWorklet();
  const want=new Set(PH.phones.map(p=>"p"+p.slot));
  for(const k of Object.keys(PH.nodes))if(!want.has(k)){try{PH.nodes[k].disconnect()}catch(e){}delete PH.nodes[k];dropChain(k)}
  for(const p of PH.phones){const k="p"+p.slot;if(PH.nodes[k])continue;
    const node=new AudioWorkletNode(ctx,"ke-phone",{numberOfInputs:0,outputChannelCount:[1]});node.port.onmessage=e=>PH.stats.buf[k]=e.data;
    PH.nodes[k]=node;buildChain(k,node);
    if(!mic||(!DUEL&&mic.key==="local"&&!MICS.local))mic=MICS[k];
    toast(`📱 ${p.name} conectado como micrófono`,"ok",3000)}
  updMicUI();renderPhoneList();
}
function phoneSocket(){
  if(PH.ws)return;const ws=new WebSocket(API.base.replace(/^http/,"ws")+"api/phonemic/ws?t="+encodeURIComponent(API.token));
  ws.binaryType="arraybuffer";PH.ws=ws;
  ws.onmessage=e=>{
    if(typeof e.data==="string"){const m=JSON.parse(e.data);if(m.type==="status"){PH.active=m.active;phoneSync(m.phones)}return}
    const b=e.data,slot=new Uint8Array(b,0,1)[0],node=PH.nodes["p"+slot];
    PH.stats.frames++;PH.stats.delay=Date.now()-new DataView(b,8,8).getFloat64(0,true); // solo es exacto si ambos relojes coinciden
    if(node){const pcm=b.slice(16);node.port.postMessage(pcm,[pcm])}};
  ws.onclose=()=>{PH.ws=null;if(PH.active)setTimeout(phoneSocket,1000)};
}
async function phoneStart(){
  setupAudio();if(ctx.state==="suspended")await ctx.resume();
  loading(true,"Preparando la conexión segura para el teléfono… (solo la primera vez tarda unos segundos)");
  try{PH.info=await api("phonemic/start",{});PH.active=true}catch(e){toast("No se pudo activar el teléfono: "+e.message,"err",6000);return false}finally{loading(false)}
  await phoneWorklet();phoneSocket();return true}
async function phoneStop(){try{await api("phonemic/stop",{})}catch(e){}PH.active=false;PH.info=null;try{PH.ws&&PH.ws.close()}catch(e){}PH.ws=null;await phoneSync([]);updMicUI()}
function renderPhoneList(){const el=$("phList");if(!el)return;
  el.innerHTML=PH.phones.length?PH.phones.map(p=>`<div class="phrow">${icon("smartphone",16)} <b>${esc(p.name)}</b><span class="sub">micrófono ${p.slot}</span>${mic&&mic.key==="p"+p.slot?'<span class="tagok">puntúa</span>':`<button class="btn sm" data-use="p${p.slot}">Puntuar con este</button>`}</div>`).join("")
    :`<p class="sub">Esperando teléfonos… (hasta 4, para duetos)</p>`;
  el.querySelectorAll("[data-use]").forEach(b=>b.onclick=()=>{useMic(b.dataset.use);renderPhoneList()})}
async function phoneDialog(){
  if(!PH.active&&!(await phoneStart()))return;const i=PH.info;
  modal("Micrófono del teléfono",`<div class="phqr"><div class="qr">${i.qr}</div><div>
      <ol class="phsteps"><li>Conecta el teléfono al <b>mismo wifi</b> que este PC.</li><li>Escanea el código con la cámara.</li>
      <li>La primera vez el navegador avisa que la conexión “no es privada”: toca <b>Configuración avanzada → Continuar</b> (en iPhone: <b>Mostrar detalles → visitar este sitio web</b>). Es tu propio PC.</li>
      <li>Toca <b>Empezar</b> y permite el micrófono.</li></ol>
      <p class="sub">O escribe: <code>${esc(i.url)}</code><br>Código de emparejamiento: <b class="code">${esc(i.code)}</b> · huella del certificado ${esc(i.fingerprint||"")}</p></div></div>
    <div id="phList"></div>`,[{label:"Apagar teléfono",onclick:phoneStop},{label:"Listo",primary:true}]);
  renderPhoneList()}
$("phoneBtn").onclick=()=>phoneDialog();
window.KE_PHONE_STATS=()=>({active:PH.active,phones:PH.phones.length,frames:PH.stats.frames,delay:PH.stats.delay,buf:PH.stats.buf,mic:mic&&mic.key});

// ---------- detección de tono y puntuación ----------
let view={mid:62,range:16,init:false},REF=null,scoring=false,score={hit:0,tot:0},trail=[];
function detectPitch(){ // autocorrelación: devuelve nota MIDI (float) o null
  if(!mic)return null;const b=mic.buf;mic.an.getFloatTimeDomainData(b);
  let rms=0;for(let i=0;i<b.length;i++)rms+=b[i]*b[i];rms=Math.sqrt(rms/b.length);
  // filtro de ruido: aprende el nivel de fondo (baja rápido, sube despacio) y exige voz claramente por encima
  mic.floor=rms<mic.floor?mic.floor*0.9+rms*0.1:mic.floor*0.998+rms*0.002;
  const sens=+($("micSens")?.value??50),gate=Math.max(0.008,mic.floor*3)*(2-sens/100*1.5);
  if(rms<gate){mic.hist=[];return null}
  const sr=ctx.sampleRate,minL=Math.floor(sr/1000),maxL=Math.floor(sr/75);let best=-1,bestC=0;
  for(let L=minL;L<=maxL;L++){let c=0;for(let i=0;i<b.length-L;i+=2)c+=b[i]*b[i+L];if(c>bestC){bestC=c;best=L}}
  let e=0;for(let i=0;i<b.length;i+=2)e+=b[i]*b[i];if(best<0||bestC/e<0.65){mic.hist=[];return null}
  const m=69+12*Math.log2(sr/best/440);
  // estabilidad: mediana de las 3 últimas lecturas; un pico aislado (ruido, golpe) no cuenta
  mic.hist.push(m);if(mic.hist.length>3)mic.hist.shift();if(mic.hist.length<2)return null;
  const h=mic.hist.slice().sort((a,b)=>a-b);return h[h.length>>1];
}
function refAt(t){if(!REF)return null;const i=Math.round(t/REF.hop);const v=REF.midi[i];return v==null?null:v+pitch}
async function loadRef(){REF=null;try{REF=await api("pitchref?id="+song.id)}catch(e){}}
function resetScore(){score={hit:0,tot:0};trail=[];view.init=false;$("scoreV").textContent="0"}
async function setScoring(on){
  scoring=on;$("player").classList.toggle("scoring",scoring);$("scoreBtn").classList.toggle("on",scoring);
  if(scoring){if(!REF){loading(true,"Preparando la línea de notas…");await loadRef();loading(false)}resetScore();
    if(!mic){try{await micOn()}catch(e){toast("Activa el micrófono para puntuar","err")}}}
}
$("scoreBtn").onclick=()=>setScoring(!scoring);
function scoreFrame(t){
  if(!scoring||!isPlaying())return;
  const sung=detectPitch(),ref=refAt(t);
  if(sung!=null)trail.push([t,sung]);while(trail.length&&trail[0][0]<t-4)trail.shift();
  // el micrófono llega con retraso (~50-250 ms; el teléfono suma ~100 ms): comparar con la referencia reciente más parecida
  if(ref!=null){score.tot++;if(sung!=null){let best=99;for(let dt=0,lag=mic.key==="local"?0.25:0.4;dt<=lag;dt+=0.05){const r=refAt(t-dt);if(r!=null){const d=Math.abs(((sung-r)%12+18)%12-6);if(d<best)best=d}}if(best<=1)score.hit++}}
  const pct=score.tot?Math.round(score.hit/score.tot*100):0;$("scoreV").textContent=pct;
  $("scoreHint").textContent=sung!=null&&ref!=null?(()=>{const d=((sung-ref)%12+18)%12-6;return Math.abs(d)<=1?"¡afinado!":d>0?"un poco alto":"un poco bajo"})():"";
  drawNotes(t,sung);
}
function drawNotes(t,sung){
  const c=$("notes"),W=c.clientWidth,H=c.clientHeight;if(c.width!==W*devicePixelRatio){c.width=W*devicePixelRatio;c.height=H*devicePixelRatio}
  const g=c.getContext("2d");g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);g.clearRect(0,0,W,H);
  const span=8,x=tt=>(tt-(t-span*0.35))/span*W;
  // centrar en la tesitura de la ventana visible
  let lo=99,hi=0;for(let k=-3;k<=5;k+=0.1){const r=refAt(t+k);if(r!=null){lo=Math.min(lo,r);hi=Math.max(hi,r)}}
  if(lo>hi){lo=view.mid-7;hi=view.mid+7}
  // la vista se mueve suave y solo cuando las notas se salen del margen (antes saltaba en cada cuadro)
  const tMid=(lo+hi)/2,tRange=Math.max(16,hi-lo+8);
  if(!view.init){view.mid=tMid;view.range=tRange;view.init=true}
  if(Math.abs(tMid-view.mid)>view.range*0.2)view.mid+=(tMid-view.mid)*0.04;
  if(tRange>view.range||tRange<view.range*0.7)view.range+=(tRange-view.range)*0.04;
  const mid=view.mid,range=view.range,y=m=>H/2-(m-mid)/range*H;
  g.fillStyle="#ffffff10";g.fillRect(0,0,W,H);
  g.fillStyle=getComputedStyle($("player")).getPropertyValue("--sung")||"#3df";g.globalAlpha=.55;
  for(let k=-span*0.35;k<span*0.65;k+=REF.hop){const r=refAt(t+k);if(r!=null)g.fillRect(x(t+k),y(r)-4,W/span*REF.hop+1,8)}
  g.globalAlpha=1;g.strokeStyle="#fff";g.lineWidth=2;g.beginPath();
  // la voz cantada se dibuja en la octava más cercana a la referencia
  let prevT=-9;for(const [tt,m] of trail){const r=refAt(tt)??mid;let mm=m;while(mm-r>6)mm-=12;while(r-mm>6)mm+=12;
    if(tt-prevT>0.3)g.moveTo(x(tt),y(mm));else g.lineTo(x(tt),y(mm));prevT=tt}g.stroke();
  g.fillStyle="#ffffff55";g.fillRect(x(t)-1,0,2,H);
}
function showResult(){if(!scoring||!score.tot)return false;const pct=Math.round(score.hit/score.tot*100);
  $("resScore").textContent=pct;$("resMsg").textContent=pct>=85?"¡Increíble! Afinación de estudio 🎤":pct>=65?"¡Muy bien cantado!":pct>=40?"¡Bien! Sigue practicando":"¡A practicar un poco más!";
  $("result").classList.add("on");return true}
$("resAgain").onclick=()=>{$("result").classList.remove("on");resetScore();seekTo(0);play()};
$("resClose").onclick=()=>$("result").classList.remove("on");

// ---------- grabación ----------
let rec=null,recDest=null,recT0=0,recTimer=null;
function ensureRecDest(){if(recDest)return recDest;setupAudio();recDest=ctx.createMediaStreamDestination();gMaster.connect(recDest);return recDest}
async function recStart(){
  ensureRecDest();if(!mic){try{await micOn()}catch(e){toast("Se grabará solo la pista (sin micrófono)","",3500)}}
  for(const ch of Object.values(MICS))if(!ch.recConnected){ch.gain.connect(recDest);ch.recConnected=true}
  const mime=MediaRecorder.isTypeSupported("audio/webm;codecs=opus")?"audio/webm;codecs=opus":"";
  const chunks=[];rec=new MediaRecorder(recDest.stream,mime?{mimeType:mime,audioBitsPerSecond:192000}:{});
  rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
  rec.onstop=async()=>{clearInterval(recTimer);$("player").classList.remove("recording");$("recBtn").classList.remove("on");
    const blob=new Blob(chunks,{type:rec.mimeType||"audio/webm"});if(blob.size<2000)return toast("Grabación vacía","err");
    loading(true,"Guardando tu grabación…");
    try{const r=await fetch(API.base+"api/recording?id="+song.id,{method:"POST",headers:{"X-Token":API.token,"Content-Type":"application/octet-stream"},body:blob});
      const j=await r.json();if(!r.ok)throw new Error(j.error);
      toast("Grabación guardada: "+j.file.split(/[\\/]/).pop(),"ok",6000);if(T?.opener)T.opener.revealItemInDir(j.file).catch(()=>{});}
    catch(e){toast("No se pudo guardar la grabación: "+e.message,"err",6000)}finally{loading(false)}};
  rec.start(1000);recT0=Date.now();$("player").classList.add("recording");$("recBtn").classList.add("on");
  recTimer=setInterval(()=>$("recTime").textContent=fmt((Date.now()-recT0)/1000),500);if(!isPlaying())play();
}
function recStop(){if(rec&&rec.state!=="inactive")rec.stop()}
$("recBtn").onclick=()=>rec&&rec.state==="recording"?recStop():recStart();


// ---------- duelo por turnos ----------
let DUEL=null; // {cfg, players:[{name,mic}], turns:[{round,player,song}], i, scores:[[pct...]...], last}
const MIC_OPTS=[["local","Micrófono del PC"],["p1","Teléfono 1"],["p2","Teléfono 2"],["p3","Teléfono 3"],["p4","Teléfono 4"]];
function duelSetup(prev){
  if(typeof licAllows==="function"&&!licAllows("party"))return licenseBlocked("El duelo es parte del modo fiesta.");
  const pool=(typeof tabSongs==="function"?tabSongs(TAB):LIB);const songs=pool.length?pool:LIB;
  if(!songs.length)return toast("Primero añade canciones a la biblioteca","err");
  const cfg=prev||{players:[{name:"Jugador 1",mic:"local"},{name:"Jugador 2",mic:"local"}],mode:"same",rounds:1,first:songs[0].id};
  const row=(p,i)=>`<div class="drow"><input class="field" maxlength="24" value="${esc(p.name)}" placeholder="Nombre">
    <select class="field">${MIC_OPTS.map(([v,n])=>`<option value="${v}" ${p.mic===v?"selected":""}>${n}</option>`).join("")}</select>
    <button class="btn sm ghost" data-rm="${i}" title="Quitar">${icon("x",14)}</button></div>`;
  modal("Duelo por turnos",`<p class="sub">Cada jugador canta su turno y se suma su puntuación de afinación. Al final, el ranking.</p>
    <label>Jugadores (2 a 8)</label><div id="dPlayers"></div>
    <button class="btn sm" id="dAdd" style="margin-top:8px">${icon("plus",14)} Añadir jugador</button>
    <label>Canciones <span class="sub">(${songs.length} en ${pool.length?"lo que estás viendo":"la biblioteca"})</span></label>
    <div class="radio"><label class="opt"><input type="radio" name="dm" value="same" ${cfg.mode==="same"?"checked":""}><span class="dot"></span><span class="n">Todos cantan la misma canción</span><span class="c">más justo</span></label>
      <label class="opt"><input type="radio" name="dm" value="each" ${cfg.mode==="each"?"checked":""}><span class="dot"></span><span class="n">Una canción distinta por jugador</span><span class="c">al azar</span></label></div>
    <label>Primera canción</label><select class="field" id="dFirst">${songs.map(s=>`<option value="${s.id}" ${s.id===cfg.first?"selected":""}>${esc(s.title||"(sin título)")}${s.artist?" — "+esc(s.artist):""}</option>`).join("")}</select>
    <label>Rondas</label><select class="field" id="dRounds">${[1,2,3,4,5].map(n=>`<option ${n===cfg.rounds?"selected":""}>${n}</option>`).join("")}</select>
    <p class="sub" style="margin-top:12px">${icon("smartphone",14)} Para cantar con el teléfono, el jugador lo elige en su fila; el código QR aparece en su turno.</p>`,[
    {label:"Cancelar"},
    {label:`${icon("trophy",15)} Empezar duelo`,primary:true,onclick:()=>{const c=read();if(c.players.length<2){toast("Se necesitan al menos 2 jugadores","err");return false}duelStart(c,songs.map(s=>s.id))}}]);
  let players=cfg.players.map(p=>({...p}));
  const read=()=>{syncRows();return {players:players.map((p,i)=>({name:p.name.trim()||`Jugador ${i+1}`,mic:p.mic})),
    mode:document.querySelector("input[name=dm]:checked").value,rounds:+$("dRounds").value,first:$("dFirst").value}};
  const syncRows=()=>$("dPlayers").querySelectorAll(".drow").forEach((r,i)=>{players[i].name=r.querySelector("input").value;players[i].mic=r.querySelector("select").value});
  const draw=()=>{$("dPlayers").innerHTML=players.map(row).join("");$("dAdd").disabled=players.length>=8;
    $("dPlayers").querySelectorAll("[data-rm]").forEach(b=>{b.disabled=players.length<=2;b.onclick=()=>{syncRows();players.splice(+b.dataset.rm,1);draw()}})};
  $("dAdd").onclick=()=>{syncRows();if(players.length<8)players.push({name:`Jugador ${players.length+1}`,mic:"local"});draw()};
  draw();
}
function duelStart(cfg,pool){
  DUEL={cfg,pool,players:cfg.players,turns:DuelLogic.makeTurns(cfg.players,pool,cfg.mode,cfg.rounds,cfg.first),i:0,scores:cfg.players.map(()=>[]),last:null};
  PARTY=null;$("ranking").classList.remove("on");duelTurn();
}
function updDuelTag(){const on=!!DUEL;$("partyTag").hidden=!on;$("partySkip").hidden=!on;
  if(on){const t=DUEL.turns[DUEL.i];$("partyPos").textContent=`Duelo · ${DUEL.players[t.player].name} · ${DUEL.i+1}/${DUEL.turns.length}`;$("partySkip").title="Terminar este turno"}
  else $("partySkip").title="Siguiente canción"}
async function duelTurn(){
  const t=DUEL.turns[DUEL.i],p=DUEL.players[t.player];
  if(!song||song.id!==t.song||!$("player").classList.contains("on"))await openSong(t.song);else{pause();seekTo(0)}
  if(!DUEL)return;
  if(!scoring)await setScoring(true);else if(!REF)await loadRef();
  if(p.mic!=="local"&&!PH.active)await phoneStart();
  updDuelTag();showTurn();
}
function showTurn(){
  const t=DUEL.turns[DUEL.i],p=DUEL.players[t.player],s=LIB.find(x=>x.id===t.song)||song||{},rounds=DUEL.cfg.rounds;
  $("tuInfo").textContent=(rounds>1?`Ronda ${t.round+1} de ${rounds} · `:"")+`Turno ${DUEL.i+1} de ${DUEL.turns.length}`;
  $("tuName").textContent="Turno de "+p.name;$("tuSong").textContent=(s.title||"")+(s.artist?" — "+s.artist:"");
  $("tuLast").textContent=DUEL.last?`${DUEL.last.name}: ${DUEL.last.pct} puntos`:"";
  const ph=p.mic!=="local",ok=!ph||!!MICS[p.mic];
  $("tuMic").innerHTML=icon(ph?"smartphone":"mic",15)+" "+(ph?(ok?esc(micLabel(p.mic)):`${esc(micLabel(p.mic))} no está conectado — se usará el del PC si no lo conectas`):"Micrófono del PC");
  $("tuMic").classList.toggle("warn",!ok);$("tuQR").hidden=!ph;
  $("tuBoard").innerHTML=DuelLogic.ranking(DUEL.players,DUEL.scores).filter(r=>r.turns).map(r=>`<span>${esc(r.name)} <b>${r.avg}</b></span>`).join("");
  $("turn").classList.add("on");
}
async function duelGo(){
  const p=DUEL.players[DUEL.turns[DUEL.i].player];
  if(p.mic==="local"||!MICS[p.mic]){try{await micOn();useMic("local")}catch(e){toast("No se pudo usar el micrófono: "+(e.message||e),"err",5000)}}
  else useMic(p.mic);
  $("turn").classList.remove("on");resetScore();seekTo(0);await play();
}
function duelTurnEnd(){
  if(!DUEL)return;pause();const t=DUEL.turns[DUEL.i],p=DUEL.players[t.player];
  const pct=score.tot?Math.round(score.hit/score.tot*100):0;DUEL.scores[t.player].push(pct);DUEL.last={name:p.name,pct};
  DUEL.i++;if(DUEL.i>=DUEL.turns.length)return showRanking();
  duelTurn();
}
function showRanking(){
  const rows=DuelLogic.ranking(DUEL.players,DUEL.scores),medal=["🥇","🥈","🥉"];
  const tie=rows.length>1&&rows[1].place===1;
  $("rkWinner").textContent=tie?"¡Empate!":`¡Gana ${rows[0].name}!`;
  $("rkList").innerHTML=rows.map(r=>`<div class="rk${r.place===1?" win":""}"><span class="pl">${medal[r.place-1]||r.place+"º"}</span><span class="nm">${esc(r.name)}</span><span class="pts"><b>${r.avg}</b> pts</span><span class="sub">mejor ${r.best}</span></div>`).join("");
  $("turn").classList.remove("on");$("ranking").classList.add("on");
}
$("tuGo").onclick=()=>duelGo();
$("tuSkip").onclick=()=>{if(!DUEL)return;resetScore();duelTurnEnd()};
$("tuQR").onclick=async()=>{await phoneDialog();const close=$("mBtns").lastElementChild;if(close){const f=close.onclick;close.onclick=async()=>{await f();if(DUEL&&$("turn").classList.contains("on"))showTurn()}}};
$("tuEnd").onclick=()=>{$("turn").classList.remove("on");if(DUEL&&DUEL.scores.some(s=>s.length))showRanking();else{DUEL=null;updParty()}};
$("rkAgain").onclick=()=>{const d=DUEL;$("ranking").classList.remove("on");duelStart(d.cfg,d.pool)};
$("rkClose").onclick=()=>{$("ranking").classList.remove("on");DUEL=null;updParty()};
$("duelBtn").onclick=()=>duelSetup();

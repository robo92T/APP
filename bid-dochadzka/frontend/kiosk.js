/* Terminál na stenu ("pípačka").
   Čítanie čipu:
   1) USB čítačka v režime klávesnice – napíše UID a Enter do skrytého poľa (funguje všade),
   2) Web NFC (Chrome na Androide s NFC) – ak je k dispozícii, číta sériové číslo čipu.
   Pri výpadku siete sa záznamy uložia v zariadení a odošlú sa po obnovení spojenia. */
"use strict";
const $ = (s) => document.querySelector(s);
const K = { key: localStorage.getItem("kiosk_key"), info: null, queue: JSON.parse(localStorage.getItem("kiosk_queue") || "[]"), timer: null, busy: false, online: true };
const pad = (n) => String(n).padStart(2, "0");
const nowLocal = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtH = (h) => (Math.round((h || 0) * 100) / 100).toLocaleString("sk-SK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------- zvuk (pípnutie) cez WebAudio – bez zvukových súborov
let actx;
function beep(ok = true) {
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = ok ? [[880, 0], [1320, 0.11]] : [[220, 0], [180, 0.18]];
    for (const [f, t] of notes) {
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = ok ? "sine" : "square"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, actx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.35, actx.currentTime + t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + t + (ok ? 0.12 : 0.25));
      o.connect(g).connect(actx.destination); o.start(actx.currentTime + t); o.stop(actx.currentTime + t + 0.3);
    }
    if (navigator.vibrate) navigator.vibrate(ok ? 60 : [80, 60, 80]);
  } catch (e) { /* bez zvuku */ }
}

async function api(path, body) {
  const r = await fetch("/api/kiosk/" + path, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Device-Key": K.key }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.detail || "Chyba " + r.status); e.status = r.status; throw e; }
  return d;
}

// ---------- ľavý panel: hodiny
function tick() {
  const d = new Date();
  $("#time").innerHTML = `${pad(d.getHours())}:${pad(d.getMinutes())}<small>${pad(d.getSeconds())}</small>`;
  const ds = d.toLocaleDateString("sk-SK", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("#date").textContent = ds.charAt(0).toUpperCase() + ds.slice(1);
}
setInterval(tick, 1000); tick();

function setNet(on) { K.online = on; $("#net").className = "net" + (on ? "" : " off"); $("#net span").textContent = on ? "online" : "offline – záznamy sa ukladajú"; drawQueue(); }
function drawQueue() { const q = $("#queue"); q.textContent = K.queue.length ? `Neodoslané: ${K.queue.length}` : ""; q.style.display = K.queue.length ? "block" : "none"; }

// ---------- obrazovky
const R = () => $("#right");
function idle() {
  clearTimeout(K.timer); K.busy = false;
  R().innerHTML = `<div class="screen idle"><div class="rings"><span></span><span></span><span></span><div class="chip">📶</div></div>
    <h1>Priložte čip</h1><p>Príchod · odchod · obed · lekár · služobne</p></div>`;
  focusInput();
}
function setup(msg) {
  R().innerHTML = `<div class="screen"><div class="setup"><h1>Nastavenie terminálu</h1>
    <p>Zadajte kľúč terminálu z administrácie (Správa → Terminály). Kľúč sa uloží len v tomto zariadení.</p>
    ${msg ? `<p style="color:#c62828;font-weight:700">${esc(msg)}</p>` : ""}
    <input id="key" type="password" autocomplete="off" placeholder="kľúč terminálu"><button id="save">Uložiť a spustiť</button></div></div>`;
  $("#save").onclick = async () => { K.key = $("#key").value.trim(); localStorage.setItem("kiosk_key", K.key); start(); };
}
function initials(name) { return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase(); }

function showEmployee(uid, info) {
  K.busy = true;
  const reasons = K.info.reasons;
  const stTxt = info.state === "in" ? `V práci od ${info.since.slice(11, 16)}` : info.state === "away" ? `Mimo pracoviska (${esc((reasons.find((r) => r.code === info.reason) || {}).name || info.reason)}) od ${info.since.slice(11, 16)}` : "Mimo práce";
  let actions = "";
  if (info.state === "in") {
    actions = `<button class="act main" data-k="OUT">🏠 Odchod domov<span class="bar" style="animation-duration:6s"></span></button>` +
      reasons.map((r) => `<button class="act" data-k="OUT" data-r="${esc(r.code)}">${esc(r.icon)} ${esc(r.name)}</button>`).join("");
  } else {
    actions = `<button class="act main" data-k="IN">${info.state === "away" ? "↩ Návrat" : "▶ Príchod"}<span class="bar" style="animation-duration:4s"></span></button>`;
  }
  R().innerHTML = `<div class="screen">
    <div class="who"><div class="av">${esc(initials(info.employee.name))}</div><div><div class="nm">${esc(info.employee.name)}</div><div class="st">${stTxt}${info.shift ? " · zmena " + esc(info.shift) : ""}</div></div></div>
    <div class="stats"><div class="stat"><b>${fmtH(info.today_h)} h</b><span>dnes</span></div><div class="stat"><b>${info.month_balance_h > 0 ? "+" : ""}${fmtH(info.month_balance_h)} h</b><span>saldo do včera</span></div><div class="stat"><b>${info.vacation_left ?? "–"}</b><span>dovolenka (dni)</span></div></div>
    <div class="actions">${actions}</div><button class="cancel" id="cancel">✕ Zrušiť</button></div>`;
  R().querySelectorAll(".act").forEach((b) => (b.onclick = () => punch(uid, b.dataset.k, b.dataset.r || null)));
  $("#cancel").onclick = idle;
  // automatické potvrdenie hlavnej akcie (príchod 4 s, odchod 6 s) – netreba sa dotýkať obrazovky
  const main = R().querySelector(".act.main");
  clearTimeout(K.timer);
  K.timer = setTimeout(() => main && main.click(), info.state === "in" ? 6000 : 4000);
}

function showOfflineChoice(uid) {
  K.busy = true;
  R().innerHTML = `<div class="screen"><div class="who"><div class="av">!</div><div><div class="nm">Bez spojenia so serverom</div><div class="st">Vyberte akciu – záznam sa uloží a odošle neskôr</div></div></div>
    <div class="actions" style="margin-top:3vh"><button class="act main" data-k="IN">▶ Príchod</button><button class="act home" data-k="OUT">🏠 Odchod</button>
    ${K.info.reasons.map((r) => `<button class="act" data-k="OUT" data-r="${esc(r.code)}">${esc(r.icon)} ${esc(r.name)}</button>`).join("")}</div><button class="cancel" id="cancel">✕ Zrušiť</button></div>`;
  R().querySelectorAll(".act").forEach((b) => (b.onclick = () => queuePunch(uid, b.dataset.k, b.dataset.r || null)));
  $("#cancel").onclick = idle;
  K.timer = setTimeout(idle, 15000);
}

function result(ok, title, text) {
  clearTimeout(K.timer);
  beep(ok);
  R().innerHTML = `<div class="screen result ${ok ? "" : "err"}"><div class="mark">${ok ? "✓" : "✕"}</div><h1>${esc(title)}</h1><p>${esc(text || "")}</p></div>`;
  K.timer = setTimeout(idle, ok ? 2600 : 4500);
}

// ---------- logika
async function onUid(raw) {
  const uid = raw.trim();
  if (!uid || K.busy) return;
  K.busy = true;
  try {
    const info = await api("identify", { uid });
    setNet(true);
    beep(true);
    showEmployee(uid, info);
  } catch (e) {
    if (e.status === 404) result(false, "Neznámy čip", "Čip nie je priradený – kontaktujte personálne oddelenie.");
    else if (e.status === 401) setup("Kľúč terminálu je neplatný.");
    else if (!e.status) { setNet(false); beep(true); showOfflineChoice(uid); }
    else result(false, "Chyba", e.message);
  }
}

async function punch(uid, kind, reason) {
  clearTimeout(K.timer);
  try {
    const r = await api("punch", { uid, kind, reason });
    const label = kind === "IN" ? "Príchod" : reason ? (K.info.reasons.find((x) => x.code === reason) || {}).name : "Odchod";
    result(true, r.duplicate ? "Už zaznamenané" : `${label} ${r.ts.slice(11, 16)}`, r.name + (kind === "OUT" && !reason ? " – pekný zvyšok dňa!" : ""));
  } catch (e) {
    if (!e.status) { queuePunch(uid, kind, reason); return; }
    result(false, "Záznam sa nepodaril", e.message);
  }
}

function queuePunch(uid, kind, reason) {
  K.queue.push({ uid, kind, reason, offline_ts: nowLocal() });
  localStorage.setItem("kiosk_queue", JSON.stringify(K.queue));
  drawQueue();
  result(true, "Uložené v termináli", "Odošle sa automaticky po obnovení spojenia.");
}

async function flushQueue() {
  if (!K.queue.length || !K.key) return;
  const rest = [];
  for (const item of K.queue) {
    try { await api("punch", item); setNet(true); }
    catch (e) { if (!e.status) { rest.push(item); setNet(false); } /* chybné (napr. neznámy čip) sa zahodia – vidno v audite servera */ }
  }
  K.queue = rest; localStorage.setItem("kiosk_queue", JSON.stringify(rest)); drawQueue();
}
setInterval(flushQueue, 30000);

// ---------- vstup z čítačky
function focusInput() { const i = $("#uid"); if (i && document.activeElement !== i && !$("#key")) i.focus(); }
document.addEventListener("click", (e) => { if (!e.target.closest("button,input")) focusInput(); });
setInterval(focusInput, 2000);
$("#uid").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); const v = e.target.value; e.target.value = ""; onUid(v); }
});

async function startNfc() {
  if (!("NDEFReader" in window)) return;
  try {
    const r = new NDEFReader();
    await r.scan();
    r.onreading = (ev) => onUid(ev.serialNumber.replace(/:/g, ""));
    r.onreadingerror = () => {};
  } catch (e) { /* NFC nie je povolené – ostáva USB čítačka */ }
}

async function start() {
  if (!K.key) return setup();
  try {
    K.info = await api("info");
    localStorage.setItem("kiosk_info", JSON.stringify(K.info));
    setNet(true);
  } catch (e) {
    if (e.status === 401 || e.status === 403) return setup(e.message);
    K.info = JSON.parse(localStorage.getItem("kiosk_info") || '{"reasons":[],"device":{}}');
    setNet(false);
  }
  $("#dev").textContent = (K.info.device && K.info.device.name) || "";
  idle();
  startNfc();
  flushQueue();
}
// demo / test: ?uid=XXXX simuluje priloženie čipu
start().then(() => { const u = new URLSearchParams(location.search).get("uid"); if (u) setTimeout(() => onUid(u), 300); });

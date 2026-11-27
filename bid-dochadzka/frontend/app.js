/* BID Dochádzka – webová a mobilná aplikácia (PWA). Čistý JavaScript bez knižníc.
   Štruktúra: pomocné funkcie -> API -> stránky (render*) -> router. */
"use strict";

// ---------------------------------------------------------------- pomocné funkcie
const $ = (s, r = document) => r.querySelector(s);
function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.setAttribute("style", v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "html") n.innerHTML = v; // používa sa len pre statické ikony
    else if (k in n && typeof v !== "string") n[k] = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}
const fmtH = (h) => (h === null || h === undefined ? "–" : (Math.round(h * 100) / 100).toLocaleString("sk-SK", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const fmtSigned = (h) => (h > 0 ? "+" : "") + fmtH(h);
const DAYS = ["Po", "Ut", "St", "Št", "Pi", "So", "Ne"];
const MONTHS = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september", "október", "november", "december"];
const pad = (n) => String(n).padStart(2, "0");
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const thisMonth = () => todayISO().slice(0, 7);
const fmtDate = (iso) => { if (!iso) return ""; const [y, m, d] = iso.slice(0, 10).split("-"); return `${+d}. ${+m}. ${y}`; };
const fmtTime = (iso) => (iso ? iso.slice(11, 16) : "");
const monthLabel = (m) => { const [y, mm] = m.split("-"); return `${MONTHS[+mm - 1]} ${y}`; };
const shiftMonth = (m, delta) => { let [y, mm] = m.split("-").map(Number); mm += delta; while (mm < 1) { mm += 12; y--; } while (mm > 12) { mm -= 12; y++; } return `${y}-${pad(mm)}`; };
const initials = (f, l) => ((f || "?")[0] + (l || "")[0]).toUpperCase();

function toast(msg, err = false) {
  const t = el("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 6000 : 3500);
}

function modal(title, body, buttons = []) {
  const bg = el("div", { class: "modal-bg" });
  const close = () => bg.remove();
  const m = el("div", { class: "modal", role: "dialog" },
    el("header", {}, el("h2", {}, title), el("button", { class: "btn ghost x", onclick: close, "aria-label": "Zavrieť" }, "✕")),
    el("div", { class: "body" }, body),
    buttons.length ? el("footer", {}, buttons.map((b) => el("button", { class: "btn " + (b.cls || ""), onclick: async () => { if (b.click) { const r = await b.click(); if (r !== false) close(); } else close(); } }, b.label))) : null);
  bg.append(m);
  bg.addEventListener("mousedown", (e) => { if (e.target === bg) close(); });
  document.body.append(bg);
  const f = m.querySelector("input,select,textarea");
  if (f) setTimeout(() => f.focus(), 50);
  return { close, el: m };
}

function field(label, input, cls = "") { return el("div", { class: cls }, el("label", {}, label), input); }
function input(name, value = "", attrs = {}) { return el("input", { name, value: value ?? "", ...attrs }); }
function select(name, options, value, attrs = {}) {
  const s = el("select", { name, ...attrs }, options.map(([v, t]) => el("option", { value: v ?? "" }, t)));
  s.value = value ?? "";
  return s;
}
function formData(root) {
  const o = {};
  root.querySelectorAll("input,select,textarea").forEach((i) => {
    if (!i.name) return;
    if (i.type === "checkbox") { if (i.dataset.multi) { o[i.name] = o[i.name] || []; if (i.checked) o[i.name].push(i.value); } else o[i.name] = i.checked; }
    else o[i.name] = i.value;
  });
  return o;
}

// ---------------------------------------------------------------- API
const API = {
  token: localStorage.getItem("bid_token"),
  async call(method, path, body) {
    const r = await fetch("/api" + path, {
      method, headers: { "Content-Type": "application/json", ...(this.token ? { Authorization: "Bearer " + this.token } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401 && !path.startsWith("/login")) { this.logout(false); throw new Error("Prihláste sa znova"); }
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.blob();
    if (!r.ok) { const msg = (data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "Chyba " + r.status; const e = new Error(msg); e.data = data; e.status = r.status; throw e; }
    return data;
  },
  get(p) { return this.call("GET", p); },
  post(p, b = {}) { return this.call("POST", p, b); },
  put(p, b) { return this.call("PUT", p, b); },
  del(p) { return this.call("DELETE", p); },
  logout(server = true) { if (server && this.token) fetch("/api/logout", { method: "POST", headers: { Authorization: "Bearer " + this.token } }); this.token = null; localStorage.removeItem("bid_token"); S.me = null; renderLogin(); },
  async download(path) {
    const r = await fetch("/api" + path, { headers: { Authorization: "Bearer " + this.token } });
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Export zlyhal"); }
    const blob = await r.blob();
    const name = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "export";
    const a = el("a", { href: URL.createObjectURL(blob), download: name });
    document.body.append(a); a.click(); a.remove();
  },
};

const S = { me: null, meta: null, month: thisMonth() };
const has = (...roles) => S.me && (S.me.roles.includes("admin") || roles.some((r) => S.me.roles.includes(r)));
const typeOf = (code) => (S.meta?.absence_types || []).find((t) => t.code === code) || { name: code, color: "#6b7a90", icon: "•" };

// ---------------------------------------------------------------- prihlásenie
function renderLogin(msg) {
  document.body.className = "";
  const app = $("#app");
  app.replaceChildren();
  const totp = el("div", { class: "hide" }, field("Kód z autentifikačnej aplikácie (2FA)", input("totp", "", { inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6 })));
  const err = el("div", { class: "alert err hide" });
  const form = el("form", { class: "grid", onsubmit: async (e) => {
    e.preventDefault();
    const d = formData(form);
    err.classList.add("hide");
    try {
      const r = await API.post("/login", d);
      API.token = r.token; localStorage.setItem("bid_token", r.token);
      await boot(r);
    } catch (ex) {
      if (ex.data?.totp_required) { totp.classList.remove("hide"); totp.querySelector("input").focus(); err.textContent = ex.data.detail; }
      else err.textContent = ex.message;
      err.classList.remove("hide");
    }
  } },
    field("Používateľské meno", input("username", "", { autocomplete: "username", required: true, autocapitalize: "none" })),
    field("Heslo", input("password", "", { type: "password", autocomplete: "current-password", required: true })),
    totp, err,
    el("button", { class: "btn primary big", type: "submit" }, "Prihlásiť sa"),
    el("small", {}, "Zabudnuté heslo vám obnoví personálne oddelenie."));
  app.append(el("div", { class: "login-wrap" },
    el("div", { class: "login-art" },
      el("div", { class: "brand" }, el("div", { class: "mark" }, "BID"), el("div", { class: "name" }, "Bratislavská integrovaná doprava", el("span", {}, "a.s."))),
      el("div", {}, el("h1", {}, "Dochádzka, dovolenky a zmeny na jednom mieste"), el("div", { class: "stripe" }),
        el("p", {}, "Záznam príchodov a odchodov čipom, žiadosti z mobilu, schvaľovanie nadriadeným, rozpis služieb dispečingu 24/7 a podklady pre mzdy.")),
      el("small", { style: "opacity:.7" }, "Interný systém – prístup len pre zamestnancov BID a.s.")),
    el("div", { class: "login-form" }, el("div", { class: "card" }, el("h2", {}, "Prihlásenie"), msg ? el("div", { class: "alert" }, msg) : null, form))));
}

async function boot(loginInfo) {
  S.me = await API.get("/me");
  S.meta = await API.get("/meta");
  renderShell();
  if (loginInfo?.must_change_pw) changePasswordDialog(true);
  else if (loginInfo?.totp_setup_required) { toast("Pre vašu rolu je povinné dvojfaktorové overenie – nastavte ho v profile.", true); location.hash = "#/profil"; }
  route();
}

// ---------------------------------------------------------------- rozloženie
const NAV = [
  { group: "Ja" },
  { h: "#/prehlad", ico: "🏠", t: "Prehľad", tab: true },
  { h: "#/dochadzka", ico: "🕘", t: "Moja dochádzka", tab: true, need: () => S.me.employee },
  { h: "#/ziadosti", ico: "🌴", t: "Žiadosti", tab: true, need: () => S.me.employee },
  { group: "Tím", need: () => has("veduci", "personalista") },
  { h: "#/schvalovanie", ico: "✅", t: "Schvaľovanie", tab: true, need: () => has("veduci"), badge: "approve" },
  { h: "#/tim", ico: "👥", t: "Tím a prítomnosť", need: () => has("veduci", "personalista") },
  { h: "#/rozpis", ico: "📅", t: "Rozpis zmien 24/7", need: () => has("veduci", "personalista") },
  { group: "Mzdy", need: () => has("personalista") },
  { h: "#/mzdy", ico: "📤", t: "Uzávierka a export", need: () => has("personalista") },
  { group: "Správa", need: () => has("admin", "personalista") },
  { h: "#/sprava/struktura", ico: "🏢", t: "Organizačná štruktúra", need: () => has("personalista") },
  { h: "#/sprava/zamestnanci", ico: "🪪", t: "Zamestnanci a účty", need: () => has("personalista") },
  { h: "#/sprava/rezimy", ico: "⏱", t: "Pracovné režimy a zmeny", need: () => has("personalista") },
  { h: "#/sprava/ciselniky", ico: "📚", t: "Dôvody a sviatky", need: () => has("personalista") },
  { h: "#/sprava/exporty", ico: "🧾", t: "Exportné profily", need: () => has("personalista") },
  { h: "#/sprava/terminaly", ico: "📟", t: "Terminály", need: () => has("admin") && S.me.roles.includes("admin") },
  { h: "#/sprava/audit", ico: "🛡", t: "Audit a nastavenia", need: () => S.me.roles.includes("admin") },
];

function renderShell() {
  const e = S.me.employee;
  const name = e ? `${e.first_name} ${e.last_name}` : S.me.username;
  const app = $("#app");
  app.replaceChildren(
    el("header", { class: "topbar" },
      el("a", { class: "brand", href: "#/prehlad" }, el("div", { class: "mark" }, "BID"), el("div", { class: "name" }, "Dochádzka", el("span", {}, "BID a.s."))),
      el("div", { class: "spacer" }),
      el("div", { class: "clock", id: "clock" }),
      el("a", { class: "user", href: "#/profil", style: "color:#fff;text-decoration:none" }, el("span", { class: "uname" }, name), el("div", { class: "avatar" }, initials(e?.first_name || S.me.username, e?.last_name)))),
    el("div", { class: "layout" },
      el("nav", { class: "sidebar nav", id: "sidenav" }),
      el("main", { id: "main" })),
    el("nav", { class: "tabbar", id: "tabbar" }));
  const side = $("#sidenav"), tab = $("#tabbar");
  for (const n of NAV) {
    if (n.need && !n.need()) continue;
    if (n.group) { side.append(el("div", { class: "group" }, n.group)); continue; }
    side.append(el("a", { href: n.h, "data-h": n.h }, el("span", { class: "ico" }, n.ico), n.t, n.badge ? el("span", { class: "badge yellow hide", id: "badge-" + n.badge }) : null));
    if (n.tab) tab.append(el("a", { href: n.h, "data-h": n.h }, el("span", { class: "ico" }, n.ico), n.t.split(" ")[0]));
  }
  tab.append(el("a", { href: "#/menu", "data-h": "#/menu" }, el("span", { class: "ico" }, "☰"), "Viac"));
  side.append(el("div", { class: "group" }, "Účet"), el("a", { href: "#/profil", "data-h": "#/profil" }, el("span", { class: "ico" }, "👤"), "Profil a bezpečnosť"),
    el("a", { href: "#", onclick: (ev) => { ev.preventDefault(); API.logout(); } }, el("span", { class: "ico" }, "⎋"), "Odhlásiť"));
  const tick = () => { const c = $("#clock"); if (c) c.textContent = new Date().toLocaleString("sk-SK", { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" }); };
  tick(); clearInterval(S.clockTimer); S.clockTimer = setInterval(tick, 15000);
  refreshBadges();
}

async function refreshBadges() {
  if (!has("veduci")) return;
  try {
    const r = await API.get("/requests?scope=approve");
    const b = $("#badge-approve");
    if (b) { b.textContent = r.length; b.classList.toggle("hide", !r.length); }
  } catch (e) { /* ticho */ }
}

function page(title, sub, actions, ...content) {
  const main = $("#main");
  main.replaceChildren(el("div", { class: "page-head" }, el("div", {}, el("h1", {}, title), sub ? el("div", { class: "sub" }, sub) : null), actions ? el("div", { class: "actions" }, actions) : null), ...content.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  window.scrollTo(0, 0);
  return main;
}

function monthPicker(onChange) {
  const span = el("span", {}, monthLabel(S.month));
  const go = (d) => { S.month = shiftMonth(S.month, d); span.textContent = monthLabel(S.month); onChange(); };
  return el("div", { class: "month-picker" }, el("button", { class: "btn", onclick: () => go(-1), title: "Predchádzajúci" }, "‹"), span, el("button", { class: "btn", onclick: () => go(1), title: "Nasledujúci" }, "›"));
}

// ---------------------------------------------------------------- PREHĽAD
async function renderDashboard() {
  const e = S.me.employee;
  page(`Dobrý deň${e ? ", " + e.first_name : ""}`, new Date().toLocaleDateString("sk-SK", { weekday: "long", day: "numeric", month: "long", year: "numeric" }), null, el("div", { class: "empty" }, "Načítavam…"));
  const blocks = [];
  if (e) {
    const att = await API.get(`/attendance/${e.id}?month=${thisMonth()}`);
    const today = att.days.find((d) => d.day === todayISO()) || {};
    const st = att.state;
    const stateTxt = st.state === "in" ? "V práci" : st.state === "away" ? `Mimo pracoviska – ${typeOf(st.reason).name}` : "Mimo práce";
    const reasons = S.meta.absence_types.filter((t) => t.kiosk);
    const punch = async (kind, reason) => {
      try { await API.post("/punch", { kind, reason, source: matchMedia("(max-width: 900px)").matches ? "mobile" : "web" }); toast(kind === "IN" ? "Príchod zaznamenaný" : "Odchod zaznamenaný"); renderDashboard(); }
      catch (ex) { toast(ex.message, true); }
    };
    const status = el("div", { class: "card status-card" },
      el("div", { class: "row" }, el("span", { class: "status-pill" }, el("span", { class: "dot " + st.state }), stateTxt), st.since ? el("small", { style: "color:#cfd8e6" }, "od " + fmtTime(st.since) + (st.since.slice(0, 10) !== todayISO() ? " (" + fmtDate(st.since) + ")" : "")) : null),
      el("div", { class: "grid g3 mt" },
        el("div", {}, el("div", { style: "opacity:.75;font-size:.8rem" }, "DNES ODPRACOVANÉ"), el("div", { class: "big" }, fmtH(today.worked_h || 0) + " h")),
        el("div", {}, el("div", { style: "opacity:.75;font-size:.8rem" }, "PLÁN NA DNES"), el("div", { class: "big" }, today.shift ? today.shift + " · " + fmtH(today.planned_h) + " h" : fmtH(today.planned_h || 0) + " h")),
        el("div", {}, el("div", { style: "opacity:.75;font-size:.8rem" }, "SALDO MESIACA (DO VČERA)"), el("div", { class: "big" }, fmtSigned(att.summary.balance_to_date_h || 0) + " h"))),
      e.allow_remote ? el("div", { class: "punch-row" },
        st.state !== "in" ? el("button", { class: "btn yellow big", onclick: () => punch("IN") }, "▶ ", st.state === "away" ? "Návrat / príchod" : "Príchod") : null,
        st.state === "in" ? el("button", { class: "btn yellow big", onclick: () => punch("OUT") }, "■ Odchod domov") : null,
        st.state === "in" ? reasons.map((r) => el("button", { class: "btn big", onclick: () => punch("OUT", r.code) }, r.icon + " " + r.name)) : null)
        : el("div", { class: "mt", style: "opacity:.8;position:relative;z-index:1" }, "Príchod a odchod zaznamenávajte čipom na termináli."));
    blocks.push(status);
    const v = att.vacation;
    const warnDays = att.days.filter((d) => d.warnings.length);
    blocks.push(el("div", { class: "grid g4 mt" },
      kpi("Dovolenka – zostatok", fmtH(v.left).replace(",00", "") + " dní", `nárok ${v.entitlement} + prenos ${v.carry} · čaká ${v.pending}`),
      kpi("Odpracované v mesiaci", fmtH(att.summary.worked_h) + " h", `fond ${fmtH(att.summary.fond_h)} h`),
      kpi("Nočná práca", fmtH(att.summary.night_h) + " h", "22:00 – 06:00"),
      kpi("Upozornenia", String(warnDays.length), warnDays.length ? "dni na kontrolu" : "všetko v poriadku", warnDays.length ? "neg" : "pos")));
    const reqs = (await API.get("/requests?scope=mine")).filter((r) => r.status === "pending" || r.date_to >= todayISO()).slice(0, 5);
    blocks.push(el("div", { class: "grid g2 mt" },
      el("div", { class: "card" }, el("h2", {}, "Moje žiadosti"), reqs.length ? el("div", { class: "list" }, reqs.map(reqItem)) : el("div", { class: "empty" }, "Žiadne aktuálne žiadosti"),
        el("div", { class: "mt" }, el("a", { class: "btn primary", href: "#/ziadosti" }, "+ Nová žiadosť"))),
      el("div", { class: "card" }, el("h2", {}, "Upozornenia v dochádzke"), warnDays.length ? el("div", { class: "list" }, warnDays.slice(0, 6).map((d) => el("div", { class: "req" }, el("div", { class: "icon", style: "background:var(--warn)" }, "!"), el("div", { class: "main" }, el("b", {}, fmtDate(d.day)), el("div", { class: "muted" }, d.warnings.join(" · ")))))) : el("div", { class: "empty" }, "✓ Bez upozornení"),
        el("small", {}, "Opravu záznamu požiadajte u nadriadeného."))));
  }
  if (has("veduci", "personalista")) {
    const [pres, appr] = await Promise.all([API.get("/presence"), has("veduci") ? API.get("/requests?scope=approve") : Promise.resolve([])]);
    const inN = pres.filter((p) => p.state === "in").length;
    blocks.push(el("div", { class: "grid g3 mt" },
      kpi("Teraz v práci", `${inN} / ${pres.length}`, "vo vašej pôsobnosti"),
      kpi("Na schválenie", String(appr.length), appr.length ? "žiadostí čaká" : "nič nečaká", appr.length ? "neg" : ""),
      kpi("Neprítomní dnes", String(pres.filter((p) => p.absence).length), "dovolenka, PN, OČR…")));
  }
  const main = page(`Dobrý deň${e ? ", " + e.first_name : ""}`, new Date().toLocaleDateString("sk-SK", { weekday: "long", day: "numeric", month: "long", year: "numeric" }), null, ...blocks);
  if (!e && !blocks.length) main.append(el("div", { class: "card" }, "Účet nie je prepojený so zamestnancom."));
}

function kpi(label, value, hint, cls = "") {
  return el("div", { class: "card kpi accent" }, el("div", { class: "label" }, label), el("div", { class: "value " + cls }, value), hint ? el("div", { class: "hint" }, hint) : null);
}

// ---------------------------------------------------------------- DOCHÁDZKA (mesačný výkaz)
async function renderAttendance(empId) {
  empId = empId || S.me.employee?.id;
  const load = async () => {
    const att = await API.get(`/attendance/${empId}?month=${S.month}`);
    const emp = att.employee;
    const canEdit = has("veduci", "personalista") && (empId !== S.me.employee?.id || has("personalista")) && !att.locked;
    const s = att.summary;
    const absSummary = Object.entries(s.absence_h || {}).map(([k, v]) => el("span", { class: "tag", style: `background:${typeOf(k).color}` }, `${typeOf(k).name}: ${fmtH(v)} h` + (s.absence_days?.[k] ? ` / ${s.absence_days[k]} d` : "")));
    const rows = att.days.map((d) => {
      const dt = new Date(d.day + "T00:00");
      const cls = [d.weekday >= 5 ? "weekend" : "", d.holiday && d.holiday_day_off ? "holiday" : "", d.day === todayISO() ? "today" : "", canEdit ? "clickable" : ""].join(" ");
      const tl = el("div", { class: "timeline" });
      if (d.plan_from && d.plan_to) { const a = toMin(d.plan_from), b = toMin(d.plan_to) <= a ? 1440 : toMin(d.plan_to); tl.append(el("div", { class: "plan", style: `left:${a / 14.4}%;width:${(b - a) / 14.4}%` })); }
      for (const iv of d.intervals) {
        const a = toMin(iv.from), b = toMin(iv.to);
        const color = iv.kind === "WORK" ? "" : `background:${typeOf(iv.kind).color}`;
        tl.append(el("div", { class: "seg " + (iv.kind === "WORK" ? "WORK" : "") + (iv.open ? " open" : ""), style: `left:${a / 14.4}%;width:${Math.max(b - a, 4) / 14.4}%;${color}`, title: `${iv.from}–${iv.to} ${iv.kind === "WORK" ? "práca" : typeOf(iv.kind).name}` }));
      }
      return el("tr", { class: cls, onclick: canEdit ? () => dayDialog(emp, d, att.events, load) : null },
        el("td", { style: "white-space:nowrap" }, el("b", {}, dt.getDate() + "."), " ", el("span", { class: "muted" }, DAYS[d.weekday])),
        el("td", {}, d.shift ? el("span", { class: "tag", style: `background:${shiftColor(d.shift)};color:${d.shift === "D" ? "#0b2d5b" : "#fff"}` }, d.shift) : null, d.holiday ? el("div", { style: "max-width:190px" }, el("small", {}, (d.holiday_day_off ? "🎉 " : "") + d.holiday.split(" (")[0])) : null),
        el("td", { class: "num" }, d.planned_h ? fmtH(d.planned_h) : ""),
        el("td", {}, d.first_in || ""), el("td", {}, d.last_out || ""),
        el("td", {}, tl),
        el("td", { class: "num" }, el("b", {}, d.worked_h ? fmtH(d.worked_h) : "")),
        el("td", { class: "num" }, d.night_h ? fmtH(d.night_h) : ""),
        el("td", {}, Object.entries(d.absences).map(([k, v]) => el("span", { class: "tag", style: `background:${typeOf(k).color};margin-right:3px` }, `${k} ${fmtH(v)}`)), d.auto_break_h ? el("span", { class: "badge grey", title: "automaticky odpočítaná prestávka (§ 91 ZP)" }, "−" + fmtH(d.auto_break_h) + " prest.") : null),
        el("td", {}, d.warnings.map((w) => el("div", {}, el("span", { class: "badge warn" }, "⚠ " + w)))));
    });
    const isMine = empId === S.me.employee?.id;
    page(isMine ? "Moja dochádzka" : `Dochádzka – ${emp.first_name} ${emp.last_name}`, `${emp.position || ""} · os. č. ${emp.personal_number} · úväzok ${emp.fte * 100} %`,
      [monthPicker(load), att.locked ? el("span", { class: "badge err" }, "🔒 Mesiac uzavretý") : null, !isMine ? el("a", { class: "btn", href: "#/tim" }, "← Tím") : null],
      el("div", { class: "grid g4" },
        kpi("Fond pracovného času", fmtH(s.fond_h) + " h", `${s.plan_days || 0} plánovaných dní`),
        kpi("Odpracované", fmtH(s.worked_h) + " h", `${s.worked_days || 0} dní · víkend ${fmtH(s.weekend_h)} h`),
        kpi("Noc / sviatok", `${fmtH(s.night_h)} / ${fmtH(s.holiday_h)} h`, `náhrada za sviatok ${fmtH(s.holiday_paid_h)} h`),
        kpi("Saldo (celý mesiac)", fmtSigned(s.balance_h) + " h", `do včera ${fmtSigned(s.balance_to_date_h || 0)} h`, s.balance_h < 0 ? "neg" : "pos")),
      absSummary.length ? el("div", { class: "card mt" }, el("div", { class: "row" }, el("b", {}, "Neprítomnosti:"), absSummary)) : null,
      el("div", { class: "table-wrap mt" }, el("table", {},
        el("thead", {}, el("tr", {}, ["Deň", "Zmena", "Plán", "Príchod", "Odchod", "Časová os 0–24 h", "Odprac.", "Noc", "Neprítomnosť", "Upozornenia"].map((h, i) => el("th", { class: [2, 6, 7].includes(i) ? "num" : "" }, h)))),
        el("tbody", {}, rows))),
      canEdit ? el("p", { class: "muted" }, "Kliknutím na deň otvoríte záznamy a môžete ich opraviť. Každá oprava sa ukladá do auditného záznamu.") : null);
  };
  await load();
}
const toMin = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
const shiftColor = (c) => (S.meta.shift_types.find((s) => s.code === c) || {}).color || "#999";

function dayDialog(emp, d, events, reload) {
  const dayEvents = events.filter((e) => e.ts.startsWith(d.day));
  const list = el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Čas", "Typ", "Dôvod", "Zdroj", "Poznámka", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, dayEvents.length ? dayEvents.map((e) => el("tr", { style: e.deleted ? "text-decoration:line-through;opacity:.5" : "" },
      el("td", {}, fmtTime(e.ts)), el("td", {}, e.kind === "IN" ? "Príchod" : "Odchod"), el("td", {}, e.reason ? typeOf(e.reason).name : ""), el("td", {}, e.source), el("td", {}, e.note || ""),
      el("td", {}, !e.deleted ? el("button", { class: "btn small danger", onclick: async () => { const note = prompt("Dôvod zmazania záznamu:"); if (!note) return; try { await API.del(`/events/${e.id}?note=${encodeURIComponent(note)}`); toast("Záznam zmazaný"); m.close(); reload(); } catch (ex) { toast(ex.message, true); } } }, "Zmazať") : "zmazaný")))
      : el("tr", {}, el("td", { colspan: 6, class: "empty" }, "Žiadne záznamy")))));
  const f = el("div", { class: "form mt" },
    field("Čas", input("time", "", { type: "time", required: true })),
    field("Typ", select("kind", [["IN", "Príchod"], ["OUT", "Odchod"]], "OUT")),
    field("Dôvod odchodu", select("reason", [["", "– koniec práce –"], ...S.meta.absence_types.filter((t) => t.kiosk).map((t) => [t.code, t.name])], "")),
    field("Dôvod opravy (povinné)", input("note", "", { placeholder: "napr. zabudnutý odchod, potvrdené vedúcim" })));
  const m = modal(`${emp.first_name} ${emp.last_name} – ${fmtDate(d.day)}`, el("div", {}, list, el("h3", { class: "mt" }, "Pridať záznam"), f), [
    { label: "Zavrieť" },
    { label: "Uložiť opravu", cls: "primary", click: async () => {
      const v = formData(f);
      if (!v.time) { toast("Zadajte čas", true); return false; }
      try { await API.post("/events", { employee_id: emp.id, ts: `${d.day}T${v.time}:00`, kind: v.kind, reason: v.kind === "OUT" ? v.reason : null, note: v.note }); toast("Oprava uložená"); reload(); }
      catch (ex) { toast(ex.message, true); return false; }
    } }]);
}

// ---------------------------------------------------------------- ŽIADOSTI
function reqItem(r, actions) {
  const st = { pending: ["warn", "čaká na schválenie"], approved: ["ok", "schválená"], rejected: ["err", "zamietnutá"], cancelled: ["grey", "zrušená"] }[r.status];
  const range = r.date_from === r.date_to ? fmtDate(r.date_from) : `${fmtDate(r.date_from)} – ${fmtDate(r.date_to)}`;
  return el("div", { class: "req" },
    el("div", { class: "icon", style: `background:${r.color || typeOf(r.type_code).color}` }, r.icon || typeOf(r.type_code).icon),
    el("div", { class: "main" }, el("b", {}, r.type_name || typeOf(r.type_code).name), r.first_name && actions ? el("span", {}, " · " + r.first_name + " " + r.last_name) : null,
      el("div", { class: "muted" }, range, r.half_day ? " (pol dňa)" : "", r.time_from ? ` ${r.time_from}–${r.time_to}` : "", r.note ? " · " + r.note : ""),
      r.decision_note ? el("div", { class: "muted" }, "Vyjadrenie: " + r.decision_note) : null),
    el("span", { class: "badge " + st[0] }, st[1]), actions || null);
}

async function renderRequests() {
  const types = S.meta.absence_types.filter((t) => t.request);
  const f = el("form", { class: "form" });
  const typeSel = select("type_code", types.map((t) => [t.code, `${t.icon} ${t.name}`]), "DOV");
  const timeRow = el("div", { class: "full form hide", style: "grid-template-columns:1fr 1fr" }, field("Čas od", input("time_from", "", { type: "time" })), field("Čas do", input("time_to", "", { type: "time" })));
  const hint = el("div", { class: "full alert hide" });
  const upd = () => {
    const t = types.find((x) => x.code === typeSel.value);
    timeRow.classList.toggle("hide", !["LEKAR", "LEKAR_DOP"].includes(t.code));
    hint.classList.toggle("hide", !!t.needs_approval);
    hint.textContent = t.needs_approval ? "" : "Tento druh sa neschvaľuje – ide o oznámenie (napr. PN, OČR). Doklad odovzdajte personálnemu oddeleniu.";
  };
  typeSel.addEventListener("change", upd);
  f.append(field("Druh", typeSel, "full"), field("Od", input("date_from", todayISO(), { type: "date", required: true })), field("Do", input("date_to", todayISO(), { type: "date", required: true })),
    timeRow, el("label", { class: "check full" }, el("input", { type: "checkbox", name: "half_day" }), "Len polovica dňa"),
    field("Poznámka pre nadriadeného", el("textarea", { name: "note", rows: 2, maxlength: 500 }), "full"), hint,
    el("div", { class: "full row" }, el("button", { class: "btn primary big", type: "submit" }, "Odoslať žiadosť"),
      S.me.approvers.length ? el("small", {}, "Schvaľuje: " + S.me.approvers.map((a) => a.first_name + " " + a.last_name).join(", ")) : el("small", {}, "Schvaľovateľ nie je nastavený – kontaktujte personálne")));
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = formData(f);
    if (!d.date_to) d.date_to = d.date_from;
    try { const r = await API.post("/requests", d); toast(r.status === "approved" ? "Oznámenie zaevidované" : "Žiadosť odoslaná nadriadenému"); renderRequests(); }
    catch (ex) { toast(ex.message, true); }
  });
  upd();
  const mine = await API.get("/requests?scope=mine");
  const att = await API.get(`/attendance/${S.me.employee.id}?month=${thisMonth()}`);
  const v = att.vacation;
  page("Žiadosti", "Dovolenka, lekár, náhradné voľno, služobná cesta, home office, PN/OČR", null,
    el("div", { class: "grid g4 mb" }, kpi("Nárok " + v.year, fmtH(v.total).replace(",00", "") + " d", `ročný ${v.entitlement} + prenos ${v.carry}`), kpi("Čerpané", fmtH(v.taken).replace(",00", "") + " d", "schválené"), kpi("Čaká", fmtH(v.pending).replace(",00", "") + " d", "na schválenie"), kpi("Zostáva", fmtH(v.left_after_pending).replace(",00", "") + " d", "po schválení čakajúcich", v.left_after_pending < 0 ? "neg" : "pos")),
    el("div", { class: "grid g2" },
      el("div", { class: "card" }, el("h2", {}, "Nová žiadosť"), f),
      el("div", { class: "card" }, el("h2", {}, "Moje žiadosti"), mine.length ? el("div", { class: "list" }, mine.map((r) => reqItem(r, (r.status === "pending" || (r.status === "approved" && r.date_from > todayISO())) ? el("button", { class: "btn small danger", onclick: async () => { if (!confirm("Zrušiť žiadosť?")) return; try { await API.post(`/requests/${r.id}/cancel`); toast("Zrušené"); renderRequests(); } catch (ex) { toast(ex.message, true); } } }, "Zrušiť") : null))) : el("div", { class: "empty" }, "Zatiaľ žiadne žiadosti"))));
}

// ---------------------------------------------------------------- SCHVAĽOVANIE
async function renderApprovals() {
  const pend = await API.get("/requests?scope=approve");
  const team = (await API.get("/requests?scope=team")).filter((r) => r.status === "approved");
  const decide = async (r, action) => {
    let note = "";
    if (action === "reject") { note = prompt("Dôvod zamietnutia (zamestnanec ho uvidí):"); if (note === null) return; }
    try { await API.post(`/requests/${r.id}/${action}`, { note }); toast(action === "approve" ? "Schválené" : "Zamietnuté"); refreshBadges(); renderApprovals(); }
    catch (ex) { toast(ex.message, true); }
  };
  page("Schvaľovanie", "Žiadosti vašich podriadených", [monthPicker(renderApprovals)],
    el("div", { class: "grid g2" },
      el("div", { class: "card" }, el("h2", {}, "Čaká na vás ", el("span", { class: "badge yellow" }, pend.length)),
        pend.length ? el("div", { class: "list" }, pend.map((r) => reqItem(r, el("div", { class: "row" }, el("button", { class: "btn small ok", onclick: () => decide(r, "approve") }, "✓ Schváliť"), el("button", { class: "btn small danger", onclick: () => decide(r, "reject") }, "✕ Zamietnuť"))))) : el("div", { class: "empty" }, "✓ Všetko vybavené")),
      el("div", { class: "card" }, el("h2", {}, "Kalendár neprítomností tímu – " + monthLabel(S.month)), teamCalendar(team, pend))));
}

function teamCalendar(approved, pending) {
  const [y, m] = S.month.split("-").map(Number);
  const first = new Date(y, m - 1, 1), n = new Date(y, m, 0).getDate();
  const cal = el("div", { class: "cal" }, DAYS.map((d) => el("div", { class: "h" }, d)));
  for (let i = 0; i < (first.getDay() + 6) % 7; i++) cal.append(el("div"));
  for (let d = 1; d <= n; d++) {
    const iso = `${S.month}-${pad(d)}`;
    const wd = (new Date(y, m - 1, d).getDay() + 6) % 7;
    const cell = el("div", { class: "d" + (wd >= 5 ? " we" : "") }, el("div", { class: "n" }, d));
    for (const r of [...approved, ...pending]) if (r.date_from <= iso && r.date_to >= iso) cell.append(el("div", { class: "ev", style: `background:${r.color};${r.status === "pending" ? "opacity:.55;border:1px dashed #000" : ""}`, title: `${r.first_name} ${r.last_name} – ${r.type_name}` }, `${r.icon} ${r.last_name}`));
    cal.append(cell);
  }
  return el("div", {}, cal, el("small", {}, "Priesvitné = čakajúce žiadosti. Pomáha odhaliť prekrývanie dovoleniek."));
}

// ---------------------------------------------------------------- TÍM
async function renderTeam() {
  const pres = await API.get("/presence");
  const q = el("input", { placeholder: "Hľadať meno alebo útvar…", style: "max-width:320px" });
  const tbody = el("tbody");
  const draw = () => {
    const t = q.value.toLowerCase();
    tbody.replaceChildren(...pres.filter((p) => !t || (p.name + " " + (p.unit || "")).toLowerCase().includes(t)).map((p) => el("tr", { class: "clickable", onclick: () => (location.hash = "#/dochadzka/" + p.id) },
      el("td", {}, el("span", { class: "dot " + p.state }), " ", el("b", {}, p.name)), el("td", {}, p.unit || ""), el("td", {}, p.position || ""),
      el("td", {}, p.state === "in" ? el("span", { class: "badge ok" }, "v práci") : p.state === "away" ? el("span", { class: "badge warn" }, typeOf(p.reason).name) : el("span", { class: "badge grey" }, "mimo")),
      el("td", {}, p.since ? fmtDate(p.since) + " " + fmtTime(p.since) : ""),
      el("td", {}, p.shift ? el("span", { class: "tag", style: `background:${shiftColor(p.shift)}` }, p.shift) : ""),
      el("td", {}, p.absence ? el("span", { class: "tag", style: `background:${typeOf(p.absence).color}` }, typeOf(p.absence).name) : ""))));
  };
  q.addEventListener("input", draw);
  draw();
  const counts = { in: pres.filter((p) => p.state === "in").length, away: pres.filter((p) => p.state === "away").length, abs: pres.filter((p) => p.absence).length };
  page("Tím a prítomnosť", "Aktuálny stav – kto je v práci", [el("button", { class: "btn", onclick: renderTeam }, "↻ Obnoviť")],
    el("div", { class: "grid g4 mb" }, kpi("V práci", String(counts.in), "práve teraz"), kpi("Krátkodobo mimo", String(counts.away), "obed, lekár, služobne"), kpi("Neprítomní", String(counts.abs), "dovolenka, PN…"), kpi("Spolu", String(pres.length), "vo vašej pôsobnosti")),
    el("div", { class: "toolbar" }, q),
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Zamestnanec", "Útvar", "Funkcia", "Stav", "Od", "Zmena dnes", "Neprítomnosť"].map((h) => el("th", {}, h)))), tbody)));
}

// ---------------------------------------------------------------- ROZPIS ZMIEN 24/7
async function renderRoster() {
  const units = S.meta.units;
  S.rosterUnit = S.rosterUnit || (units.find((u) => u.kind === "dispecing") || units[0]).id;
  let active = "D";
  const changes = new Map();
  const load = async () => {
    const r = await API.get(`/roster?unit_id=${S.rosterUnit}&month=${S.month}`);
    changes.clear();
    const st = S.meta.shift_types;
    const palette = el("div", { class: "palette" }, st.map((s) => el("button", { class: "btn small" + (s.code === active ? " sel" : ""), style: `background:${s.color};color:${["V", "D"].includes(s.code) ? "#0b2d5b" : "#fff"}`, onclick: (e) => { active = s.code; palette.querySelectorAll(".btn").forEach((b) => b.classList.remove("sel")); e.currentTarget.classList.add("sel"); } }, `${s.code} – ${s.name}`)),
      el("button", { class: "btn small", onclick: (e) => { active = ""; palette.querySelectorAll(".btn").forEach((b) => b.classList.remove("sel")); e.currentTarget.classList.add("sel"); } }, "⌫ Vymazať"));
    const head = el("tr", {}, el("th", {}, "Zamestnanec"), r.days.map((d) => { const dt = new Date(d + "T00:00"); const wd = (dt.getDay() + 6) % 7; return el("th", { class: (wd >= 5 ? "we" : "") + (r.holidays[d] ? " hol" : ""), title: r.holidays[d] || "" }, dt.getDate(), el("br"), DAYS[wd]); }), el("th", { class: "num" }, "Plán h"), el("th", { class: "num" }, "Norma h"));
    const body = r.rows.map((row) => {
      const sumCell = el("td", { class: "num", style: "padding:0 8px" }, fmtH(row.planned_h));
      return el("tr", {}, el("td", { class: "name" }, `${row.employee.last_name} ${row.employee.first_name}`, row.schedule_kind !== "shift" ? el("small", { class: "muted" }, " (nie zmenový)") : null),
        r.days.map((d) => {
          const code = row.cells[d] || "";
          const wd = (new Date(d + "T00:00").getDay() + 6) % 7;
          const b = el("button", { class: "cell", style: code ? `background:${shiftColor(code)};color:${["V", "D"].includes(code) ? "#0b2d5b" : "#fff"}` : "", disabled: r.locked,
            onclick: () => { const c = active; b.textContent = c; b.setAttribute("style", c ? `background:${shiftColor(c)};color:${["V", "D"].includes(c) ? "#0b2d5b" : "#fff"}` : ""); changes.set(row.employee.id + "|" + d, { employee_id: row.employee.id, day: d, shift_code: c }); saveBtn.disabled = false; saveBtn.textContent = `Uložiť zmeny (${changes.size})`; } }, code);
          return el("td", { class: wd >= 5 ? "we" : "" }, b);
        }), sumCell,
        el("td", { class: "num", style: "padding:0 8px" }, el("span", { class: row.planned_h > row.norm_h + 0.01 ? "neg" : "" }, fmtH(row.norm_h))));
    });
    const saveBtn = el("button", { class: "btn primary", disabled: true, onclick: async () => { try { await API.put("/roster", { cells: [...changes.values()] }); toast("Rozpis uložený"); load(); } catch (ex) { toast(ex.message, true); } } }, "Uložiť zmeny");
    const unitSel = select("unit", units.map((u) => [u.id, u.name]), S.rosterUnit, { onchange: (e) => { S.rosterUnit = +e.target.value; load(); } });
    page("Rozpis zmien", "Plánovanie služieb – dispečing 24/7 a zmenové pracoviská", [unitSel, monthPicker(load), el("button", { class: "btn", onclick: () => generateDialog(r, load) }, "⚙ Generovať podľa cyklu"), saveBtn],
      r.locked ? el("div", { class: "alert err" }, "Mesiac je uzavretý – rozpis nie je možné meniť.") : null,
      el("div", { class: "card mb" }, el("div", { class: "row" }, el("b", {}, "Paleta:"), palette), el("small", {}, "Vyberte zmenu a klikajte do mriežky. Norma = týždenný fond × úväzok / 5 × počet pracovných dní mesiaca (orientačne, nepretržitá prevádzka max. 37,5 h/týždeň – § 85 ods. 5 ZP).")),
      el("div", { class: "table-wrap" }, el("table", { class: "roster" }, el("thead", {}, head), el("tbody", {}, body))));
  };
  await load();
}

function generateDialog(r, reload) {
  const shiftEmps = r.rows.filter((x) => x.schedule_kind === "shift");
  const f = el("div", { class: "form" },
    field("Cyklus zmien (kódy oddelené čiarkou)", input("pattern", "D,N,V,V"), "full"),
    field("Kotviaci dátum cyklu", input("anchor", "2026-01-01", { type: "date" }), "full"),
    el("div", { class: "full" }, el("label", {}, "Posun v cykle pre zamestnancov (tímy A/B/C/D = 0/1/2/3)"),
      shiftEmps.map((x, i) => el("div", { class: "row", style: "margin:4px 0" }, el("label", { class: "check", style: "min-width:220px" }, el("input", { type: "checkbox", name: "e" + x.employee.id, checked: true }), `${x.employee.last_name} ${x.employee.first_name}`), el("input", { name: "o" + x.employee.id, type: "number", value: i % 4, style: "width:90px" })))));
  modal("Generovať rozpis – " + monthLabel(S.month), f, [{ label: "Zrušiť" }, { label: "Vygenerovať", cls: "primary", click: async () => {
    const d = formData(f);
    const employees = shiftEmps.filter((x) => d["e" + x.employee.id]).map((x) => ({ employee_id: x.employee.id, offset: +d["o" + x.employee.id] || 0 }));
    try { await API.post("/roster/generate", { month: S.month, pattern: d.pattern.split(",").map((s) => s.trim().toUpperCase()), anchor: d.anchor, employees }); toast("Rozpis vygenerovaný"); reload(); }
    catch (ex) { toast(ex.message, true); return false; }
  } }]);
}

// ---------------------------------------------------------------- MZDY / EXPORT
async function renderPayroll() {
  S.payUnit = S.payUnit ?? "";
  const load = async () => {
    const [rep, profiles] = await Promise.all([API.get(`/report?month=${S.month}${S.payUnit ? "&unit_id=" + S.payUnit : ""}`), API.get("/export-profiles")]);
    const codes = [...new Set(rep.rows.flatMap((r) => Object.keys(r.summary.absence_h || {})))];
    const tot = (k) => rep.rows.reduce((a, r) => a + (r.summary[k] || 0), 0);
    const prof = select("profile", profiles.map((p) => [p.id, `${p.name} [${p.fmt.toUpperCase()}]`]), profiles[0]?.id);
    const unitSel = select("unit", [["", "Celá spoločnosť"], ...S.meta.units.map((u) => [u.id, u.name])], S.payUnit, { onchange: (e) => { S.payUnit = e.target.value; load(); } });
    const warnN = rep.rows.reduce((a, r) => a + (r.summary.warnings || 0), 0);
    page("Uzávierka a export pre mzdy", "Podklady pre mzdový systém – " + monthLabel(S.month),
      [unitSel, monthPicker(load)],
      el("div", { class: "grid g4" }, kpi("Zamestnanci", String(rep.rows.length), "v exporte"), kpi("Odpracované spolu", fmtH(tot("worked_h")) + " h", "fond " + fmtH(tot("fond_h")) + " h"), kpi("Nočná / sviatok", fmtH(tot("night_h")) + " / " + fmtH(tot("holiday_h")) + " h", ""), kpi("Upozornenia", String(warnN), warnN ? "pred uzávierkou skontrolujte" : "pripravené na uzávierku", warnN ? "neg" : "pos")),
      el("div", { class: "card mt" }, el("div", { class: "row" },
        el("b", {}, "Export:"), el("div", { style: "min-width:340px" }, prof),
        el("button", { class: "btn primary", onclick: async () => { try { await API.download(`/export?month=${S.month}&profile_id=${prof.value}${S.payUnit ? "&unit_id=" + S.payUnit : ""}`); toast("Export stiahnutý"); } catch (ex) { toast(ex.message, true); } } }, "⬇ Stiahnuť"),
        el("span", { class: "spacer", style: "flex:1" }),
        rep.locked ? el("span", { class: "badge err" }, "🔒 Mesiac uzavretý") : el("button", { class: "btn yellow", onclick: async () => { if (!confirm(`Uzavrieť ${monthLabel(S.month)}? Po uzavretí nebude možné meniť záznamy ani žiadosti.`)) return; try { await API.post("/month-lock", { month: S.month }); toast("Mesiac uzavretý"); load(); } catch (ex) { toast(ex.message, true); } } }, "🔒 Uzavrieť mesiac"),
        rep.locked && S.me.roles.includes("admin") ? el("button", { class: "btn danger", onclick: async () => { if (!confirm("Odomknúť mesiac?")) return; await API.post("/month-lock", { month: S.month, unlock: true }); load(); } }, "Odomknúť") : null),
        el("small", {}, "Formát, kódovanie, oddeľovač a stĺpce sa nastavujú v Správa → Exportné profily podľa importnej šablóny vášho mzdového systému.")),
      el("div", { class: "table-wrap mt" }, el("table", {},
        el("thead", {}, el("tr", {}, ["Os. č.", "Zamestnanec", "Útvar", "Úväzok", "Fond", "Odprac.", "Noc", "So/Ne", "Sviatok", "Saldo", "Dov. dni", ...codes, "⚠"].map((h, i) => el("th", { class: i > 2 ? "num" : "" }, h)))),
        el("tbody", {}, rep.rows.map((r) => { const s = r.summary; return el("tr", { class: "clickable", onclick: () => (location.hash = "#/dochadzka/" + r.employee.id) },
          el("td", {}, r.employee.personal_number), el("td", {}, el("b", {}, `${r.employee.last_name} ${r.employee.first_name}`)), el("td", {}, r.unit || ""),
          el("td", { class: "num" }, r.employee.fte), el("td", { class: "num" }, fmtH(s.fond_h)), el("td", { class: "num" }, el("b", {}, fmtH(s.worked_h))), el("td", { class: "num" }, fmtH(s.night_h)),
          el("td", { class: "num" }, fmtH(s.weekend_h)), el("td", { class: "num" }, fmtH(s.holiday_h)), el("td", { class: "num " + (s.balance_h < 0 ? "neg" : "pos") }, fmtSigned(s.balance_h)),
          el("td", { class: "num" }, s.vacation_days || ""), codes.map((c) => el("td", { class: "num" }, s.absence_h?.[c] ? fmtH(s.absence_h[c]) : "")),
          el("td", { class: "num" }, s.warnings ? el("span", { class: "badge warn" }, s.warnings) : "")); })))));
  };
  await load();
}

// ---------------------------------------------------------------- SPRÁVA – štruktúra
const KINDS = [["spolocnost", "Spoločnosť"], ["riaditel", "Riaditeľ"], ["usek", "Úsek"], ["odbor", "Odbor"], ["oddelenie", "Oddelenie"], ["dispecing", "Dispečing / zmenové pracovisko"], ["stredisko", "Stredisko"], ["skupina", "Pracovná skupina"]];
async function renderStructure() {
  const [units, emps] = await Promise.all([API.get("/units"), API.get("/employees")]);
  const byParent = {};
  units.forEach((u) => (byParent[u.parent_id ?? "root"] = byParent[u.parent_id ?? "root"] || []).push(u));
  const tree = (pid) => el("ul", { class: "tree" }, (byParent[pid] || []).map((u) => el("li", {},
    el("div", { class: "node kind-" + u.kind },
      el("div", { class: "kind" }, (KINDS.find((k) => k[0] === u.kind) || [0, u.kind])[1]),
      el("div", {}, el("div", { class: "title" }, u.name, u.short ? ` (${u.short})` : ""), el("div", { class: "meta" }, `Vedúci: ${u.manager_name || "–"}`, u.deputy_name ? ` · zástupca: ${u.deputy_name}` : "", ` · ${u.headcount} zam.`, u.cost_center ? ` · stredisko ${u.cost_center}` : "")),
      el("div", { class: "ops" }, el("button", { class: "btn small", onclick: () => unitDialog({ parent_id: u.id, kind: "oddelenie" }, units, emps) }, "+ podriadený"), el("button", { class: "btn small", onclick: () => unitDialog(u, units, emps) }, "Upraviť"))),
    byParent[u.id] ? tree(u.id) : null)));
  page("Organizačná štruktúra", "Strom: spoločnosť → riaditeľ → úseky → odbory → oddelenia. Vedúci útvaru schvaľuje žiadosti celého podstromu.", [el("button", { class: "btn primary", onclick: () => unitDialog({ kind: "usek" }, units, emps) }, "+ Nový útvar")],
    el("div", { class: "card" }, tree("root")));
}
function unitDialog(u, units, emps) {
  const empOpts = [["", "– nikto –"], ...emps.map((e) => [e.id, `${e.last_name} ${e.first_name}`])];
  const f = el("div", { class: "form" },
    field("Názov", input("name", u.name, { required: true }), "full"), field("Skratka", input("short", u.short)), field("Druh", select("kind", KINDS, u.kind)),
    field("Nadriadený útvar", select("parent_id", [["", "– najvyššia úroveň –"], ...units.filter((x) => x.id !== u.id).map((x) => [x.id, x.name])], u.parent_id)),
    field("Stredisko (nákladové)", input("cost_center", u.cost_center)),
    field("Vedúci (schvaľovateľ)", select("manager_id", empOpts, u.manager_id)), field("Zástupca vedúceho", select("deputy_id", empOpts, u.deputy_id)));
  modal(u.id ? "Upraviť útvar" : "Nový útvar", f, [
    u.id ? { label: "Zmazať", cls: "danger", click: async () => { if (!confirm("Zmazať útvar?")) return false; try { await API.del("/units/" + u.id); toast("Zmazané"); S.meta = await API.get("/meta"); renderStructure(); } catch (ex) { toast(ex.message, true); return false; } } } : null,
    { label: "Zrušiť" },
    { label: "Uložiť", cls: "primary", click: async () => { try { await API.post("/units", { ...formData(f), id: u.id }); toast("Uložené"); S.meta = await API.get("/meta"); renderStructure(); } catch (ex) { toast(ex.message, true); return false; } } }].filter(Boolean));
}

// ---------------------------------------------------------------- SPRÁVA – zamestnanci
const ROLES = [["zamestnanec", "Zamestnanec"], ["veduci", "Vedúci (schvaľuje, rozpis)"], ["personalista", "Personalista / mzdy"], ["admin", "Administrátor"]];
async function renderEmployees() {
  const emps = await API.get("/employees");
  const q = el("input", { placeholder: "Hľadať…", style: "max-width:280px" });
  const tbody = el("tbody");
  const draw = () => {
    const t = q.value.toLowerCase();
    tbody.replaceChildren(...emps.filter((e) => !t || `${e.first_name} ${e.last_name} ${e.personal_number} ${e.unit_name}`.toLowerCase().includes(t)).map((e) => el("tr", { class: "clickable", onclick: () => employeeDialog(e, emps) },
      el("td", {}, e.personal_number), el("td", {}, el("b", {}, `${e.last_name} ${e.first_name}`), e.active ? null : el("span", { class: "badge grey" }, " neaktívny")), el("td", {}, e.unit_name || ""), el("td", {}, e.position || ""),
      el("td", {}, e.schedule_name || ""), el("td", { class: "num" }, e.fte), el("td", {}, e.chip_uid ? el("span", { class: "badge ok", title: e.chip_uid }, "● " + e.chip_uid.slice(0, 8) + "…") : el("span", { class: "badge err" }, "bez čipu")),
      el("td", {}, e.username ? el("span", {}, e.username, " ", (e.roles || "").split(",").filter((r) => r !== "zamestnanec").map((r) => el("span", { class: "badge" }, r))) : el("span", { class: "muted" }, "bez účtu")))));
  };
  q.addEventListener("input", draw); draw();
  page("Zamestnanci a účty", `${emps.length} zamestnancov`, [el("button", { class: "btn primary", onclick: () => employeeDialog({ fte: 1, vacation_days: 25, active: 1, schedule_id: S.meta.schedules[0]?.id }, emps) }, "+ Nový zamestnanec")],
    el("div", { class: "toolbar" }, q),
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Os. č.", "Meno", "Útvar", "Funkcia", "Pracovný režim", "Úväzok", "Čip", "Účet a roly"].map((h) => el("th", {}, h)))), tbody)));
}
function employeeDialog(e, emps) {
  const roles = (e.roles || "zamestnanec").split(",");
  const chip = input("chip_uid", e.chip_uid, { placeholder: "Kliknite sem a priložte čip k USB čítačke" });
  const f = el("div", { class: "form" },
    el("h3", { class: "full" }, "Osobné údaje"),
    field("Osobné číslo (väzba na mzdy)", input("personal_number", e.personal_number, { required: true })), field("Titul", input("title", e.title)),
    field("Meno", input("first_name", e.first_name, { required: true })), field("Priezvisko", input("last_name", e.last_name, { required: true })),
    field("E-mail", input("email", e.email, { type: "email" })), field("Telefón", input("phone", e.phone)),
    el("h3", { class: "full mt" }, "Zaradenie a pracovný čas"),
    field("Útvar", select("org_unit_id", [["", "–"], ...S.meta.units.map((u) => [u.id, u.name])], e.org_unit_id)), field("Funkcia", input("position", e.position)),
    field("Priamy nadriadený (výnimka)", select("manager_id", [["", "podľa štruktúry (vedúci útvaru)"], ...emps.filter((x) => x.id !== e.id).map((x) => [x.id, `${x.last_name} ${x.first_name}`])], e.manager_id)),
    field("Pracovný režim", select("schedule_id", S.meta.schedules.map((s) => [s.id, s.name]), e.schedule_id)),
    field("Úväzok (1 = plný, 0,5 = polovičný)", input("fte", e.fte, { type: "number", step: "0.05", min: "0.05", max: "1" })),
    field("Nástup / ukončenie", el("div", { class: "row" }, input("start_date", e.start_date, { type: "date", style: "flex:1" }), input("end_date", e.end_date, { type: "date", style: "flex:1" }))),
    field("Dovolenka – ročný nárok (dni)", input("vacation_days", e.vacation_days, { type: "number", step: "0.5" })), field("Prenesená z min. roka (dni)", input("vacation_carry", e.vacation_carry ?? 0, { type: "number", step: "0.5" })),
    el("h3", { class: "full mt" }, "Čip a terminál"),
    field("UID čipu", chip, "full"),
    el("label", { class: "check full" }, el("input", { type: "checkbox", name: "allow_remote", checked: !!e.allow_remote }), "Smie zaznamenať príchod/odchod z mobilu alebo webu (napr. práca v teréne)"),
    el("label", { class: "check full" }, el("input", { type: "checkbox", name: "active", checked: e.active !== 0 }), "Aktívny zamestnanec"),
    el("h3", { class: "full mt" }, "Používateľský účet"),
    field("Prihlasovacie meno", input("username", e.username, { autocapitalize: "none" })),
    el("div", {}, el("label", {}, "Roly"), ROLES.map(([v, t]) => el("label", { class: "check" }, el("input", { type: "checkbox", name: "roles", value: v, "data-multi": "1", checked: roles.includes(v) }), t))));
  chip.addEventListener("keydown", (ev) => { if (ev.key === "Enter") ev.preventDefault(); });
  modal(e.id ? `${e.first_name} ${e.last_name}` : "Nový zamestnanec", f, [
    e.id && e.username ? { label: "Resetovať heslo", cls: "danger", click: async () => { if (!confirm("Vygenerovať nové heslo?")) return false; const r = await API.post(`/employees/${e.id}/reset-password`); showSecret("Nové dočasné heslo", r.password, "Odovzdajte ho zamestnancovi osobne. Pri prvom prihlásení si ho musí zmeniť."); } } : null,
    e.id ? { label: "Dochádzka", click: () => (location.hash = "#/dochadzka/" + e.id) } : null,
    { label: "Zrušiť" },
    { label: "Uložiť", cls: "primary", click: async () => {
      const d = formData(f);
      if (!d.roles?.length) d.roles = ["zamestnanec"];
      try { const r = await API.post("/employees", { ...d, id: e.id }); toast("Uložené"); if (r.initial_password) showSecret("Účet vytvorený", r.initial_password, `Prihlasovacie meno: ${d.username}. Heslo odovzdajte zamestnancovi – pri prvom prihlásení si ho zmení.`); renderEmployees(); }
      catch (ex) { toast(ex.message, true); return false; }
    } }].filter(Boolean));
}
function showSecret(title, secret, text) { modal(title, el("div", {}, el("p", {}, text), el("div", { class: "keybox" }, secret)), [{ label: "Rozumiem", cls: "primary" }]); }

// ---------------------------------------------------------------- SPRÁVA – režimy a zmeny
async function renderSchedules() {
  S.meta = await API.get("/meta");
  const kindName = { fixed: "Pevný", flex: "Pružný", shift: "Zmenový / nepretržitý" };
  page("Pracovné režimy a typy zmien", "Rozvrhnutie pracovného času, úväzky sa nastavujú pri zamestnancovi", [el("button", { class: "btn primary", onclick: () => scheduleDialog({ kind: "fixed", weekly_hours: 37.5, params: { start: "07:30", end: "15:30", break_min: 30, workdays: [0, 1, 2, 3, 4] } }) }, "+ Nový režim")],
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Názov", "Druh", "Týždenný fond", "Parametre", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, S.meta.schedules.map((s) => el("tr", {}, el("td", {}, el("b", {}, s.name)), el("td", {}, kindName[s.kind]), el("td", { class: "num" }, fmtH(s.weekly_hours) + " h"),
        el("td", { class: "mono" }, s.kind === "fixed" ? `${s.params.start}–${s.params.end}, prestávka ${s.params.break_min} min` : s.kind === "flex" ? `rámec ${s.params.window_from}–${s.params.window_to}, jadro ${s.params.core_from}–${s.params.core_to}` : `cyklus ${(s.params.pattern || []).join("-")}, min. odpočinok ${s.params.min_rest_h ?? 12} h`),
        el("td", {}, el("button", { class: "btn small", onclick: () => scheduleDialog(s) }, "Upraviť"))))))),
    el("h2", { class: "mt" }, "Typy zmien"),
    el("div", { class: "toolbar" }, el("button", { class: "btn", onclick: () => shiftDialog({ break_min: 30, color: "#4f9de0" }) }, "+ Nový typ zmeny")),
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Kód", "Názov", "Od", "Do", "Prestávka", "Prestávka v prac. čase", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, S.meta.shift_types.map((s) => el("tr", {}, el("td", {}, el("span", { class: "tag", style: `background:${s.color};color:${["V", "D"].includes(s.code) ? "#0b2d5b" : "#fff"}` }, s.code)), el("td", {}, s.name), el("td", {}, s.start || "–"), el("td", {}, s.end || "–"), el("td", {}, s.break_min + " min"), el("td", {}, s.break_paid ? "áno (§ 91 ods. 5 ZP)" : "nie"),
        el("td", {}, el("button", { class: "btn small", onclick: () => shiftDialog(s) }, "Upraviť"))))))));
}
function scheduleDialog(s) {
  const p = s.params || {};
  const kind = select("kind", [["fixed", "Pevný"], ["flex", "Pružný"], ["shift", "Zmenový / nepretržitý (24/7)"]], s.kind);
  const box = el("div", { class: "full form" });
  const draw = () => {
    box.replaceChildren();
    if (kind.value === "fixed") box.append(field("Začiatok", input("start", p.start || "07:30", { type: "time" })), field("Koniec", input("end", p.end || "15:30", { type: "time" })), field("Prestávka (min)", input("break_min", p.break_min ?? 30, { type: "number" })));
    if (kind.value === "flex") box.append(field("Rámec od", input("window_from", p.window_from || "06:00", { type: "time" })), field("Rámec do", input("window_to", p.window_to || "19:00", { type: "time" })), field("Jadro od", input("core_from", p.core_from || "09:00", { type: "time" })), field("Jadro do", input("core_to", p.core_to || "14:00", { type: "time" })), field("Prestávka (min)", input("break_min", p.break_min ?? 30, { type: "number" })));
    if (kind.value === "shift") box.append(field("Predvolený cyklus", input("pattern", (p.pattern || ["D", "N", "V", "V"]).join(","))), field("Minimálny odpočinok medzi zmenami (h)", input("min_rest_h", p.min_rest_h ?? 12, { type: "number" })), el("small", { class: "full" }, "Fond sa počíta z rozpisu zmien. Odpočinok možno v nepretržitej prevádzke skrátiť až na 8 h s náhradou do 30 dní (§ 92 ods. 2 ZP)."));
    if (kind.value !== "shift") box.append(el("div", { class: "full" }, el("label", {}, "Pracovné dni"), DAYS.map((d, i) => el("label", { class: "check", style: "display:inline-flex" }, el("input", { type: "checkbox", name: "wd" + i, checked: (p.workdays || [0, 1, 2, 3, 4]).includes(i) }), d))));
  };
  kind.addEventListener("change", draw); draw();
  const f = el("div", { class: "form" }, field("Názov", input("name", s.name), "full"), field("Druh", kind), field("Týždenný pracovný čas (h)", input("weekly_hours", s.weekly_hours, { type: "number", step: "0.25" })), box);
  modal(s.id ? "Upraviť režim" : "Nový režim", f, [{ label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => {
    const d = formData(f);
    const params = {};
    for (const k of ["start", "end", "window_from", "window_to", "core_from", "core_to"]) if (d[k]) params[k] = d[k];
    if (d.break_min !== undefined) params.break_min = +d.break_min;
    if (d.min_rest_h !== undefined) params.min_rest_h = +d.min_rest_h;
    if (d.pattern) params.pattern = d.pattern.split(",").map((x) => x.trim().toUpperCase());
    if (d.kind !== "shift") params.workdays = [0, 1, 2, 3, 4, 5, 6].filter((i) => d["wd" + i]);
    try { await API.post("/schedules", { id: s.id, name: d.name, kind: d.kind, weekly_hours: +d.weekly_hours, params }); toast("Uložené"); renderSchedules(); } catch (ex) { toast(ex.message, true); return false; }
  } }]);
}
function shiftDialog(s) {
  const f = el("div", { class: "form" }, field("Kód (1–4 znaky)", input("code", s.code, { maxlength: 4, readOnly: !!s.code })), field("Názov", input("name", s.name)),
    field("Začiatok", input("start", s.start, { type: "time" })), field("Koniec (môže byť po polnoci)", input("end", s.end, { type: "time" })),
    field("Prestávka (min)", input("break_min", s.break_min, { type: "number" })), field("Farba", input("color", s.color, { type: "color" })),
    el("label", { class: "check full" }, el("input", { type: "checkbox", name: "break_paid", checked: !!s.break_paid }), "Prestávka bez prerušenia práce – započítava sa do pracovného času (dispečing)"));
  modal(s.code ? "Typ zmeny " + s.code : "Nový typ zmeny", f, [{ label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => { try { await API.post("/shift-types", formData(f)); toast("Uložené"); renderSchedules(); } catch (ex) { toast(ex.message, true); return false; } } }]);
}

// ---------------------------------------------------------------- SPRÁVA – číselníky
async function renderCodebooks() {
  S.meta = await API.get("/meta");
  const year = +(S.month.slice(0, 4));
  const hol = await API.get("/holidays?year=" + year);
  const ca = { work: "započíta sa ako práca", paid: "platená / ospravedlnená", unpaid: "neplatená / dávka", break: "prestávka" };
  page("Dôvody neprítomnosti a sviatky", "Tlačidlá na termináli, druhy žiadostí, mzdové kódy", [el("button", { class: "btn primary", onclick: () => absenceDialog({ counts_as: "paid", request: 1, needs_approval: 1, color: "#6b7a90", icon: "•", sort: 50 }) }, "+ Nový dôvod")],
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["", "Kód", "Názov", "Vplyv na čas", "Terminál", "Žiadosť", "Schvaľuje sa", "Čerpá dovolenku", "Mzdový kód", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, S.meta.absence_types.map((t) => el("tr", {}, el("td", {}, el("span", { class: "tag", style: `background:${t.color}` }, t.icon)), el("td", { class: "mono" }, t.code), el("td", {}, el("b", {}, t.name)), el("td", {}, ca[t.counts_as]),
        el("td", {}, t.kiosk ? "✓" : ""), el("td", {}, t.request ? "✓" : ""), el("td", {}, t.needs_approval ? "✓" : "oznámenie"), el("td", {}, t.uses_vacation ? "✓" : ""), el("td", { class: "mono" }, t.payroll_code || ""),
        el("td", {}, el("button", { class: "btn small", onclick: () => absenceDialog(t) }, "Upraviť"))))))),
    el("div", { class: "page-head mt" }, el("h2", {}, "Sviatky " + year), el("div", { class: "actions" }, el("button", { class: "btn", onclick: async () => { await API.post("/holidays/generate", { year }); renderCodebooks(); } }, "Doplniť zo zákona"), el("button", { class: "btn", onclick: () => holidayDialog({ day: `${year}-01-01`, day_off: 1, surcharge: 1 }) }, "+ Pridať deň"))),
    el("div", { class: "alert warn" }, "Podľa zákona č. 241/1993 Z. z. v znení zákona č. 261/2025 Z. z.: 1. 9., 28. 10. a 17. 11. nie sú dňami pracovného pokoja; v roku 2026 ani 8. 5. a 15. 9. (§ 4b). Mzdové zvýhodnenie za prácu v tieto dni overte podľa usmernenia MPSVR SR a nastavte stĺpec „Príplatok“."),
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Dátum", "Názov", "Deň pracovného pokoja", "Príplatok za sviatok", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, hol.map((h) => el("tr", { class: h.day_off ? "holiday" : "" }, el("td", {}, fmtDate(h.day) + " " + DAYS[(new Date(h.day + "T00:00").getDay() + 6) % 7]), el("td", {}, h.name), el("td", {}, h.day_off ? "áno" : "nie"), el("td", {}, h.surcharge ? "áno" : "nie"),
        el("td", {}, el("button", { class: "btn small", onclick: () => holidayDialog(h) }, "Upraviť"))))))));
}
function absenceDialog(t) {
  const f = el("div", { class: "form" }, field("Kód", input("code", t.code, { readOnly: !!t.code })), field("Názov", input("name", t.name)),
    field("Vplyv na pracovný čas", select("counts_as", [["work", "Započíta sa ako práca (služobne, HO)"], ["paid", "Platená / ospravedlnená (lekár, dovolenka)"], ["unpaid", "Neplatená alebo dávka SP (súkromne, PN)"], ["break", "Prestávka (nezapočíta sa)"]], t.counts_as)),
    field("Mzdový kód", input("payroll_code", t.payroll_code)), field("Ikona (emoji)", input("icon", t.icon)), field("Farba", input("color", t.color, { type: "color" })), field("Poradie", input("sort", t.sort, { type: "number" })),
    el("div", { class: "full" }, [["kiosk", "Tlačidlo na termináli (krátky odchod)"], ["request", "Dá sa žiadať v aplikácii"], ["needs_approval", "Vyžaduje schválenie nadriadeným"], ["uses_vacation", "Čerpá dovolenku"]].map(([k, l]) => el("label", { class: "check" }, el("input", { type: "checkbox", name: k, checked: !!t[k] }), l))));
  modal(t.code ? "Dôvod " + t.code : "Nový dôvod", f, [{ label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => { try { await API.post("/absence-types", formData(f)); toast("Uložené"); renderCodebooks(); } catch (ex) { toast(ex.message, true); return false; } } }]);
}
function holidayDialog(h) {
  const f = el("div", { class: "form" }, field("Dátum", input("day", h.day, { type: "date" })), field("Názov", input("name", h.name)),
    el("label", { class: "check" }, el("input", { type: "checkbox", name: "day_off", checked: !!h.day_off }), "Deň pracovného pokoja"), el("label", { class: "check" }, el("input", { type: "checkbox", name: "surcharge", checked: !!h.surcharge }), "Príplatok za prácu vo sviatok"));
  modal("Sviatok", f, [h.name ? { label: "Zmazať", cls: "danger", click: async () => { await API.post("/holidays", { day: h.day, delete: true }); renderCodebooks(); } } : null, { label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => { await API.post("/holidays", formData(f)); toast("Uložené"); renderCodebooks(); } }].filter(Boolean));
}

// ---------------------------------------------------------------- SPRÁVA – exportné profily
async function renderExportProfiles() {
  const profiles = await API.get("/export-profiles");
  page("Exportné profily pre mzdový systém", "Každý profil = jedna importná šablóna (stĺpce, formát, kódovanie)", [el("button", { class: "btn primary", onclick: () => profileDialog({ fmt: "csv", level: "month", delimiter: ";", encoding: "cp1250", decimal: ",", columns: [{ field: "personal_number", header: "OsCislo" }] }) }, "+ Nový profil")],
    el("div", { class: "list" }, profiles.map((p) => el("div", { class: "req" }, el("div", { class: "icon", style: "background:var(--navy)" }, p.fmt.toUpperCase().slice(0, 3)), el("div", { class: "main" }, el("b", {}, p.name), el("div", { class: "muted mono" }, `${p.level} · ${p.fmt} · oddeľovač "${p.delimiter}" · ${p.encoding} · desatinná ${p.decimal}`), el("div", { class: "muted" }, p.columns.map((c) => c.header).join(" | "))),
      el("button", { class: "btn small", onclick: () => profileDialog(p) }, "Upraviť")))));
}
function profileDialog(p) {
  const cols = el("textarea", { name: "columns", rows: 10, class: "mono" }, p.columns.map((c) => `${c.field} | ${c.header}`).join("\n"));
  const f = el("div", { class: "form" }, field("Názov", input("name", p.name), "full"),
    field("Formát", select("fmt", [["csv", "CSV"], ["xlsx", "Excel XLSX"], ["xml", "XML"], ["json", "JSON"]], p.fmt)),
    field("Úroveň riadkov", select("level", [["month", "1 riadok = zamestnanec za mesiac"], ["day", "1 riadok = deň"], ["absence", "1 riadok = druh neprítomnosti (mzdová zložka)"]], p.level)),
    field("Oddeľovač (CSV)", input("delimiter", p.delimiter)), field("Kódovanie", select("encoding", [["utf-8-sig", "UTF-8 s BOM (Excel)"], ["utf-8", "UTF-8"], ["cp1250", "Windows-1250 (staršie mzdové systémy)"]], p.encoding)),
    field("Desatinný znak", select("decimal", [[",", "čiarka"], [".", "bodka"]], p.decimal)),
    field("Stĺpce: pole | názov v súbore (jeden na riadok)", cols, "full"),
    el("small", { class: "full mono" }, "Polia: personal_number, last_name, first_name, full_name, org_unit, cost_center, fte, month, fond_h, plan_days, worked_days, worked_h, night_h, weekend_h, holiday_h, holiday_paid_h, paid_absence_h, balance_h, over_fond_h, vacation_days, auto_break_h; denné: day, shift, planned_h, first_in, last_out, absences, warnings; neprítomnosti: code, payroll_code, name, days, cal_days, hours. Dynamicky: abs_h:KÓD (hodiny), abs_d:KÓD (pracovné dni), abs_k:KÓD (kalendárne dni)."));
  modal(p.id ? "Upraviť profil" : "Nový profil", f, [{ label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => {
    const d = formData(f);
    d.columns = cols.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [field, ...h] = l.split("|"); return { field: field.trim(), header: (h.join("|").trim() || field.trim()) }; });
    try { await API.post("/export-profiles", { ...d, id: p.id }); toast("Uložené"); renderExportProfiles(); } catch (ex) { toast(ex.message, true); return false; }
  } }]);
}

// ---------------------------------------------------------------- SPRÁVA – terminály
async function renderDevices() {
  const devs = await API.get("/devices");
  page("Terminály na stenu", "Každý terminál má vlastný tajný kľúč. Kľúč sa zobrazí len raz.", [el("button", { class: "btn primary", onclick: () => deviceDialog({}) }, "+ Nový terminál")],
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Názov", "Umiestnenie", "Povolené IP", "Naposledy online", "Stav", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, devs.map((d) => { const online = d.last_seen && (Date.now() - new Date(d.last_seen).getTime()) < 5 * 60000; return el("tr", {}, el("td", {}, el("b", {}, d.name)), el("td", {}, d.location || ""), el("td", { class: "mono" }, d.allowed_ip || "ľubovoľná"),
        el("td", {}, d.last_seen ? fmtDate(d.last_seen) + " " + fmtTime(d.last_seen) : "nikdy"), el("td", {}, d.active ? el("span", { class: "badge " + (online ? "ok" : "warn") }, online ? "online" : "offline") : el("span", { class: "badge grey" }, "vypnutý")),
        el("td", {}, el("button", { class: "btn small", onclick: () => deviceDialog(d) }, "Upraviť"))); })))),
    el("div", { class: "card mt" }, el("h2", {}, "Ako nastaviť terminál"), el("ol", {},
      el("li", {}, "Na tablete otvorte adresu ", el("code", {}, location.origin + "/kiosk"), " (Android: Fully Kiosk Browser alebo Chrome + pripnutie obrazovky)."),
      el("li", {}, "Zadajte kľúč terminálu (zobrazí sa pri vytvorení). Uloží sa len v tomto zariadení."),
      el("li", {}, "Pripojte USB čítačku čipov (režim emulácie klávesnice) cez USB-C OTG adaptér s napájaním."),
      el("li", {}, "Odporúčame obmedziť terminál na IP adresu z internej siete (pole Povolené IP)."))));
}
function deviceDialog(d) {
  const f = el("div", { class: "form" }, field("Názov", input("name", d.name), "full"), field("Umiestnenie", input("location", d.location), "full"), field("Povolené IP (čiarkou)", input("allowed_ip", d.allowed_ip), "full"),
    d.id ? el("label", { class: "check" }, el("input", { type: "checkbox", name: "active", checked: d.active !== 0 }), "Aktívny") : null,
    d.id ? el("label", { class: "check" }, el("input", { type: "checkbox", name: "rotate_key" }), "Vygenerovať nový kľúč (starý prestane platiť)") : null);
  modal(d.id ? "Terminál" : "Nový terminál", f, [{ label: "Zrušiť" }, { label: "Uložiť", cls: "primary", click: async () => { const r = await API.post("/devices", { ...formData(f), id: d.id }); if (r.key) showSecret("Kľúč terminálu", r.key, "Zadajte ho na termináli pri prvom spustení. Kľúč sa už znova nezobrazí."); renderDevices(); } }]);
}

// ---------------------------------------------------------------- SPRÁVA – audit a nastavenia
async function renderAudit() {
  const [log, st] = await Promise.all([API.get("/audit?limit=300"), API.get("/settings")]);
  const f = el("div", { class: "form" },
    field("Názov spoločnosti", input("company", st.company), "full"),
    el("label", { class: "check" }, el("input", { type: "checkbox", name: "auto_break", checked: !!st.auto_break }), "Automaticky odpočítať prestávku 30 min pri zmene nad 6 h (§ 91 ZP)"),
    field("Minimálny odpočinok medzi zmenami (h)", input("min_rest_h", st.min_rest_h, { type: "number" })),
    field("Ochrana pred dvojitým priložením čipu (s)", input("kiosk_debounce_s", st.kiosk_debounce_s, { type: "number" })),
    field("Platnosť prihlásenia (h)", input("session_hours", st.session_hours, { type: "number" })),
    field("Povinné 2FA pre roly (čiarkou)", input("require_totp_roles", (st.require_totp_roles || []).join(",")), "full"));
  page("Audit a nastavenia", "Kto, kedy a čo zmenil – nemenný záznam", null,
    el("div", { class: "card" }, el("h2", {}, "Nastavenia systému"), f, el("div", { class: "mt" }, el("button", { class: "btn primary", onclick: async () => { const d = formData(f); d.min_rest_h = +d.min_rest_h; d.kiosk_debounce_s = +d.kiosk_debounce_s; d.session_hours = +d.session_hours; d.require_totp_roles = d.require_totp_roles.split(",").map((x) => x.trim()).filter(Boolean); await API.post("/settings", d); toast("Nastavenia uložené"); } }, "Uložiť nastavenia"))),
    el("h2", { class: "mt" }, "Auditný záznam (posledných 300)"),
    el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Čas", "Používateľ", "Akcia", "Objekt", "IP", "Detail"].map((h) => el("th", {}, h)))),
      el("tbody", {}, log.map((a) => el("tr", {}, el("td", { class: "mono" }, a.ts.replace("T", " ")), el("td", {}, a.username || "–"), el("td", {}, el("span", { class: "badge" + (a.action.includes("fail") ? " err" : "") }, a.action)), el("td", {}, `${a.entity || ""} ${a.entity_id || ""}`), el("td", { class: "mono" }, a.ip || ""), el("td", { class: "mono", style: "max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap", title: a.detail || "" }, a.detail || "")))))));
}

// ---------------------------------------------------------------- PROFIL
function changePasswordDialog(forced) {
  const f = el("div", { class: "form" }, field("Súčasné heslo", input("old", "", { type: "password" }), "full"), field("Nové heslo (min. 10 znakov, písmeno a číslica)", input("new", "", { type: "password" }), "full"), field("Nové heslo znova", input("new2", "", { type: "password" }), "full"));
  modal(forced ? "Zmeňte si dočasné heslo" : "Zmena hesla", f, [{ label: "Uložiť heslo", cls: "primary", click: async () => { const d = formData(f); if (d.new !== d.new2) { toast("Heslá sa nezhodujú", true); return false; } try { await API.post("/me/password", d); toast("Heslo zmenené"); } catch (ex) { toast(ex.message, true); return false; } } }]);
}
async function renderProfile() {
  const e = S.me.employee;
  const totpBox = el("div");
  const startTotp = async () => {
    const r = await API.post("/me/totp/start");
    const code = input("code", "", { placeholder: "6-miestny kód", inputmode: "numeric", maxlength: 6, style: "max-width:200px" });
    totpBox.replaceChildren(el("p", {}, "1. V aplikácii Microsoft Authenticator / Google Authenticator pridajte účet ručne pomocou kľúča:"), el("div", { class: "keybox" }, r.secret), el("p", {}, "2. Zadajte kód, ktorý aplikácia zobrazí:"),
      el("div", { class: "row" }, code, el("button", { class: "btn primary", onclick: async () => { try { await API.post("/me/totp/confirm", { secret: r.secret, code: code.value }); toast("Dvojfaktorové overenie zapnuté"); S.me = await API.get("/me"); renderProfile(); } catch (ex) { toast(ex.message, true); } } }, "Overiť a zapnúť")),
      el("small", { class: "mono" }, r.uri));
  };
  page("Profil a bezpečnosť", S.me.username, null,
    el("div", { class: "grid g2" },
      el("div", { class: "card" }, el("h2", {}, "Môj profil"), e ? el("div", {}, el("p", {}, el("b", {}, `${e.title ? e.title + " " : ""}${e.first_name} ${e.last_name}`), el("br"), e.position || "", el("br"), S.me.unit?.name || ""),
        el("p", {}, "Osobné číslo: ", el("b", {}, e.personal_number), el("br"), "Úväzok: ", el("b", {}, e.fte * 100 + " %"), el("br"), "Čip: ", e.chip_uid ? el("span", { class: "badge ok" }, "priradený") : el("span", { class: "badge err" }, "nepriradený")),
        el("p", {}, "Schvaľovateľ žiadostí: ", el("b", {}, S.me.approvers.map((a) => a.first_name + " " + a.last_name).join(", ") || "–"))) : el("p", {}, "Technický účet"),
        el("p", {}, "Roly: ", S.me.roles.map((r) => el("span", { class: "badge", style: "margin-right:4px" }, r)))),
      el("div", { class: "card" }, el("h2", {}, "Bezpečnosť"),
        el("div", { class: "row mb" }, el("button", { class: "btn", onclick: () => changePasswordDialog(false) }, "🔑 Zmeniť heslo"), el("button", { class: "btn danger", onclick: () => API.logout() }, "⎋ Odhlásiť")),
        el("h3", {}, "Dvojfaktorové overenie (2FA)"), S.me.totp ? el("div", { class: "alert" }, "✓ Zapnuté. Pri prihlásení zadávate kód z aplikácie.") : el("div", {}, el("p", { class: "muted" }, "Odporúčané pre všetkých, povinné pre administrátorov."), el("button", { class: "btn primary", onclick: startTotp }, "Zapnúť 2FA"), totpBox)),
      el("div", { class: "card" }, el("h2", {}, "Inštalácia aplikácie do mobilu"),
        el("p", {}, el("b", {}, "Android (Chrome): "), "menu ⋮ → „Nainštalovať aplikáciu“ / „Pridať na plochu“."),
        el("p", {}, el("b", {}, "iPhone (Safari): "), "Zdieľať ⬆ → „Pridať na plochu“."),
        el("p", {}, el("b", {}, "Windows (Edge/Chrome): "), "ikona ⊕ v adresnom riadku → „Inštalovať“."))));
}

function renderMenu() {
  page("Menu", null, null, el("div", { class: "list" }, NAV.filter((n) => !n.group && (!n.need || n.need())).map((n) => el("a", { class: "req", href: n.h, style: "text-decoration:none" }, el("div", { class: "icon", style: "background:var(--navy)" }, n.ico), el("div", { class: "main" }, el("b", {}, n.t)))),
    el("a", { class: "req", href: "#/profil", style: "text-decoration:none" }, el("div", { class: "icon", style: "background:var(--navy)" }, "👤"), el("div", { class: "main" }, el("b", {}, "Profil a bezpečnosť")))));
}

// ---------------------------------------------------------------- router
const ROUTES = {
  "prehlad": renderDashboard, "dochadzka": (id) => renderAttendance(id ? +id : null), "ziadosti": renderRequests, "schvalovanie": renderApprovals,
  "tim": renderTeam, "rozpis": renderRoster, "mzdy": renderPayroll, "sprava/struktura": renderStructure, "sprava/zamestnanci": renderEmployees,
  "sprava/rezimy": renderSchedules, "sprava/ciselniky": renderCodebooks, "sprava/exporty": renderExportProfiles, "sprava/terminaly": renderDevices,
  "sprava/audit": renderAudit, "profil": renderProfile, "menu": renderMenu,
};
async function route() {
  if (!S.me) return;
  const h = (location.hash || "#/prehlad").slice(2);
  let fn = ROUTES[h], arg = null;
  if (!fn) { const parts = h.split("/"); arg = parts.pop(); fn = ROUTES[parts.join("/")]; }
  if (!fn) { fn = renderDashboard; }
  document.querySelectorAll("[data-h]").forEach((a) => a.classList.toggle("active", ("#/" + h).startsWith(a.dataset.h)));
  try { await fn(arg); } catch (ex) { console.error(ex); if (S.me) page("Chyba", null, null, el("div", { class: "alert err" }, ex.message)); }
}
window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- štart
(async () => {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  if (!API.token) return renderLogin();
  try { await boot(); } catch (e) { renderLogin(); }
})();

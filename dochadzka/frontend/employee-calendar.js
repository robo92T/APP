/* Employee-owned attendance & request calendars. All data is read from authenticated /api/me/* endpoints. */
(()=>{
"use strict";
const $=q=>document.querySelector(q);
const safe=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const today=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-")};
const pad=n=>String(n).padStart(2,"0");
const monthKey=(y,m)=>String(y)+"-"+pad(m);
const dayKey=(y,m,d)=>monthKey(y,m)+"-"+pad(d);
const fromKey=k=>{const [y,m,d]=k.split("-").map(Number);return new Date(y,m-1,d)};
const shortHours=n=>{const v=Math.round(Math.abs(Number(n)||0));return (Number(n)<0?"-":"")+Math.floor(v/60)+":"+pad(v%60)};
const labels={vacation:"Dovolenka",doctor:"Lekár",accompany:"Sprevádzanie",doctor_unpaid:"Lekár (neplatené)",accompany_unpaid:"Sprevádzanie (neplatené)",sick:"PN",ocr:"OČR",home_office:"Home office",unpaid:"Neplatené voľno",paid_leave:"Platené voľno",other:"Iné",business_trip:"Služobná cesta",training:"Školenie"};
const eventsLabel={in:"Príchod",out:"Odchod",break_start:"Začiatok prestávky",break_end:"Koniec prestávky"};
const statusLabel={pending:"Čaká na schválenie",approved:"Schválené",rejected:"Zamietnuté",cancelled:"Zrušené"};
const state={attendance:null,requests:null,admin:null};
let adminRequestId=0;
function makePeriod(year,month,move){const d=new Date(year,month-1+move,1);return {year:d.getFullYear(),month:d.getMonth()+1}};
function daysWithAbsences(items,y,m){const out={};const max=new Date(y,m,0).getDate();for(const a of items){for(let d=1;d<=max;d++){const k=dayKey(y,m,d);if(k>=a.start&&k<=a.end)(out[k]??=[]).push(a)}}return out}
function shell(mode,y,m,selected,marked){
 const monthName=new Intl.DateTimeFormat("sk-SK",{month:"long",year:"numeric"}).format(new Date(y,m-1,1));
 const days=["PO","UT","ST","ŠT","PI","SO","NE"];
 const first=(new Date(y,m-1,1).getDay()+6)%7,maximum=new Date(y,m,0).getDate();
 let grid='<div class="bid-calendar-weekdays">'+days.map(x=>'<span>'+x+'</span>').join("")+'</div><div class="bid-calendar-days">';
 for(let cell=0;cell<Math.ceil((first+maximum)/7)*7;cell++){
  const n=cell-first+1,k=dayKey(y,m,n),inside=n>=1&&n<=maximum;
  if(!inside){grid+='<span class="bid-calendar-outside" aria-hidden="true"></span>';continue}
  const marks=marked[k]||[];
  const dots=marks.slice(0,3).map(x=>'<i class="bid-dot bid-dot-'+safe(x)+'"></i>').join("");
  const active=k===selected?" selected":"",current=k===today()?" today":"";
  grid+='<button type="button" class="bid-calendar-day'+active+current+'" data-cal-day="'+k+'" aria-pressed="'+(k===selected)+'" aria-label="'+safe(k)+'"><span>'+n+'</span><span class="bid-calendar-dots">'+dots+'</span></button>';
 }
 grid+='</div>';
 return '<section class="bid-calendar-panel" aria-label="'+(mode==="requests"?"Kalendár žiadostí":"Kalendár dochádzky")+'"><div class="bid-calendar-head"><h3>'+(mode==="admin"?"Kalendár dochádzky":mode==="attendance"?"Moja dochádzka":"Moje žiadosti")+'</h3><div class="bid-calendar-controls"><button type="button" data-cal-move="-1" aria-label="Predchádzajúci mesiac">‹</button><strong>'+safe(monthName)+'</strong><button type="button" data-cal-move="1" aria-label="Nasledujúci mesiac">›</button></div></div>'+grid+'</section>';
}
function activateCalendar(mode,year,month,renderSelection){
 const root=mode==="admin"?$("#adminCalendar"):$("#content");if(!root)return;root.querySelectorAll("[data-cal-day]").forEach(b=>b.onclick=()=>{state[mode].selected=b.dataset.calDay;root.querySelectorAll("[data-cal-day]").forEach(el=>{const chosen=el===b;el.classList.toggle("selected",chosen);el.setAttribute("aria-pressed",String(chosen))});renderSelection()});
 root.querySelectorAll("[data-cal-move]").forEach(b=>b.onclick=()=>{const next=makePeriod(year,month,Number(b.dataset.calMove));if(mode==="attendance")void openAttendance(next.year,next.month);else if(mode==="admin")void openAdmin(state.admin.employeeId,next.year,next.month);else void openRequests(next.year,next.month)});
}

function punchMinutes(event){
 const raw=String(event.time||"");
 if(!/^\d{2}:\d{2}$/.test(raw))return NaN;
 const [h,m]=raw.split(":").map(Number);
 return h<=23&&m<=59?h*60+m:NaN;
}
function timelineMarkup(events){
 const sorted=[...events].filter(e=>Number.isFinite(punchMinutes(e))).sort((a,b)=>punchMinutes(a)-punchMinutes(b));
 let since=null,activity=null,segments=[];
 function push(end){
  if(since===null||activity===null||end<=since)return;
  segments.push({from:since,to:end,type:activity});
 }
 for(const e of sorted){
  const at=punchMinutes(e);
  if(e.kind==="in"){since=at;activity="work"}
  else if(e.kind==="break_start"&&activity==="work"){push(at);since=at;activity="pause"}
  else if(e.kind==="break_end"&&activity==="pause"){push(at);since=at;activity="work"}
  else if(e.kind==="out"&&activity!==null){push(at);since=null;activity=null}
 }
 const spans=segments.map(x=>'<span class="bid-timeline-segment bid-timeline-'+x.type+'" style="left:'+(100*x.from/1440).toFixed(3)+'%;width:'+(100*(x.to-x.from)/1440).toFixed(3)+'%" title="'+(x.type==="pause"?"Prestávka":"Práca")+' '+String(Math.floor(x.from/60)).padStart(2,"0")+':'+String(x.from%60).padStart(2,"0")+' – '+String(Math.floor(x.to/60)).padStart(2,"0")+':'+String(x.to%60).padStart(2,"0")+'"></span>').join("");
 const marks=sorted.map(e=>{
   const time=punchMinutes(e);const pos=Math.max(0,Math.min(100,100*time/1440));
   return '<span class="bid-timeline-marker" style="left:'+pos.toFixed(3)+'%" title="'+safe(e.time)+' '+safe(eventsLabel[e.kind]||e.kind)+'"></span>';
 }).join("");
 return '<div class="bid-timeline-wrap"><div class="bid-timeline-title"><span>Časová os dňa</span><small>00:00 – 24:00</small></div><div class="bid-timeline-track">'+spans+marks+'</div><div class="bid-timeline-ticks"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div><div class="bid-timeline-legend"><span><i class="bid-legend-work"></i> Práca</span><span><i class="bid-legend-pause"></i> Prestávka</span><span><i class="bid-legend-mark"></i> Pípnutie</span></div></div>';
}
function showAttendanceDay(mode="attendance"){
 const s=state[mode],detail=mode==="admin"?$("#bid-admin-day"):$("#bid-cal-detail");
 if(!s||!detail)return;
 const key=s.selected,row=s.days.find(x=>x.day===key),events=s.events.filter(x=>x.day===key),req=s.absByDay[key]||[];
 const niceDate=new Intl.DateTimeFormat("sk-SK",{weekday:"long",day:"numeric",month:"long",year:"numeric"}).format(fromKey(key));
 const tags=req.map(x=>'<span class="bid-day-tag bid-day-tag-'+safe(x.status)+'">'+safe(labels[x.kind]||x.kind)+' · '+safe(statusLabel[x.status]||x.status)+'</span>').join("");
 const head='<div class="bid-daily-heading"><div><span class="bid-daily-eyebrow">DENNÝ PREHĽAD</span><h3>'+safe(niceDate)+'</h3></div><span class="bid-daily-hours">'+shortHours(row?.worked_minutes||0)+' h</span></div>';
 const totals=[["Odpracované",row?.worked_minutes, "work"],["Prestávky",row?.break_minutes,"pause"],["Pracovný fond",row?.planned_minutes,"plan"],["Saldo",row?.saldo_minutes,"saldo"]];
 const cards='<div class="bid-daily-metrics">'+totals.map(([title,num,tone])=>'<div class="bid-daily-metric"><small>'+title+'</small><strong class="'+tone+'">'+(tone==="saldo"&&Number(num)>0?"+":"")+shortHours(num||0)+' h</strong></div>').join("")+'</div>';
 const eventsSorted=[...events].sort((a,b)=>String(a.time).localeCompare(String(b.time)));
 const log=eventsSorted.length?eventsSorted.map((x,i)=>{
  const kind=["in","out","break_start","break_end"].includes(x.kind)?x.kind:"other";
  const icon={in:"↘",out:"↗",break_start:"☕",break_end:"↩",other:"•"}[kind];
  return '<div class="bid-event-line"><span class="bid-event-symbol bid-event-'+kind+'">'+icon+'</span><div class="bid-event-main"><strong>'+safe(eventsLabel[x.kind]||x.kind)+'</strong><small>'+safe(x.origin==="demo"?"Ukážkové pípnutie":x.origin==="rfid"?"RFID":"Dochádzkový záznam")+'</small></div><time>'+safe(x.time)+'</time></div>'
 }).join(""):'<p class="bid-empty">Pre tento deň nie sú uložené žiadne príchody ani odchody.</p>';
 const absSection=req.length?'<div class="bid-absence-line"><strong>Neprítomnosti a žiadosti</strong><div class="bid-absence-tags">'+tags+'</div></div>':"";
 const warn=(row?.warnings||[]).length?'<div class="bid-calendar-warnings">Na preverenie: '+safe(row.warnings.join(", "))+'</div>':"";
 detail.innerHTML=head+cards+timelineMarkup(eventsSorted)+'<div class="bid-events-title">Záznamy dňa <span>'+eventsSorted.length+'</span></div><div class="bid-event-list">'+log+'</div>'+absSection+warn+'<p class="bid-timeline-footnote">Celkové hodiny a saldo sa počítajú na serveri. Časová os zobrazuje iba úseky potvrdené pípnutím; automaticky odpočítané prestávky a zmeny cez polnoc nemusia byť na osi úplné.</p>';
}
async function openAttendance(year,month,selected){
 const current=fromKey(today());year=year||current.getFullYear();month=month||current.getMonth()+1;
 const period=monthKey(year,month),prev=state.attendance;
 selected=selected||((prev&&prev.year===year&&prev.month===month)?prev.selected:(period===today().slice(0,7)?today():dayKey(year,month,1)));
 const [times,calendar]=await Promise.all([api("/api/me/attendance?year="+year+"&month="+month),api("/api/me/calendar?year="+year+"&month="+month)]);
 const byDay=daysWithAbsences(calendar.absences,year,month),marks={};
 times.rows.forEach(x=>{if(x.worked_minutes>0)(marks[x.day]??=[]).push("work")});
 Object.keys(byDay).forEach(k=>(byDay[k]||[]).forEach(x=>(marks[k]??=[]).push(x.status==="approved"?"approved":x.status==="pending"?"pending":"rejected")));
 state.attendance={year,month,selected,days:times.rows,events:calendar.events,absByDay:byDay};
 $("#content").innerHTML=shell("attendance",year,month,selected,marks)+'<div class="bid-month-totals"><span>Odpracované <b>'+shortHours(times.total_worked_minutes)+' h</b></span><span>Saldo <b>'+shortHours(times.total_saldo_minutes)+' h</b></span></div><section id="bid-cal-detail" class="bid-day-panel" aria-live="polite"></section><p class="subtle">Údaje sú dostupné len pre tvoje zamestnanecké konto. Po kliknutí na deň uvidíš jednotlivé zaznamenané udalosti.</p>';
 activateCalendar("attendance",year,month,showAttendanceDay);showAttendanceDay();
}

async function openAdmin(employeeId,year,month,selected){
 const holder=$("#adminCalendar");if(!holder)return;
 employeeId=Number(employeeId);
 if(!Number.isInteger(employeeId)||employeeId<=0){holder.innerHTML='<p class="bid-empty">Vyber zamestnanca.</p>';return;}
 const current=fromKey(today());
 year=year||current.getFullYear();month=month||current.getMonth()+1;
 const period=monthKey(year,month),prev=state.admin,requestId=++adminRequestId;
 selected=selected||((prev&&prev.employeeId===employeeId&&prev.year===year&&prev.month===month)?prev.selected:(period===today().slice(0,7)?today():dayKey(year,month,1)));
 holder.innerHTML='<div class="bid-calendar-loading" role="status">Načítavam mesačný kalendár…</div>';
 try{
   const data=await api("/api/admin/employee-calendar/"+employeeId+"?year="+year+"&month="+month);
   if(requestId!==adminRequestId||!$("#adminCalendar")||Number($("#empSelect")?.value)!==employeeId)return;
   const byDay=daysWithAbsences(data.absences,year,month),marks={};
   data.rows.forEach(x=>{if(x.worked_minutes>0)(marks[x.day]??=[]).push("work")});
   Object.keys(byDay).forEach(k=>(byDay[k]||[]).forEach(x=>(marks[k]??=[]).push(x.status==="approved"?"approved":x.status==="pending"?"pending":"rejected")));
   state.admin={employeeId,year,month,selected,days:data.rows,events:data.events,absByDay:byDay};
   holder.innerHTML='<div class="bid-admin-intro"><strong>Kalendár · '+safe(data.employee_name)+'</strong><span>Vyber deň a zobraz jeho detail</span></div>'+shell("admin",year,month,selected,marks)+'<div class="bid-month-totals"><span>Odpracované <b>'+shortHours(data.total_worked_minutes)+' h</b></span><span>Saldo <b>'+(data.total_saldo_minutes>0?"+":"")+shortHours(data.total_saldo_minutes)+' h</b></span></div><section id="bid-admin-day" class="bid-day-panel" aria-live="polite"></section>';
   activateCalendar("admin",year,month,()=>showAttendanceDay("admin"));
   showAttendanceDay("admin");
 }catch(error){
   if(requestId===adminRequestId&&$("#adminCalendar"))holder.innerHTML='<div class="error">'+safe(error.message||"Kalendár nie je dostupný.")+'</div>';
 }
}
function showRequestsDay(){
 const s=state.requests,el=$("#bid-requests-detail");if(!s||!el)return;
 const matches=s.absByDay[s.selected]||[];
 const name=new Intl.DateTimeFormat("sk-SK",{weekday:"long",day:"numeric",month:"long"}).format(fromKey(s.selected));
 el.innerHTML='<div class="bid-day-title"><strong>'+safe(name)+'</strong><span>'+matches.length+' žiadostí</span></div>'+(matches.length?matches.map(x=>'<div class="bid-activity"><span>●</span><strong>'+safe(labels[x.kind]||x.kind)+'</strong><small>'+safe(statusLabel[x.status]||x.status)+'</small></div>').join(""):'<p class="bid-empty">Na tento deň nemáš žiadnu žiadosť.</p>');
 const form=$("#bid-request-form");
 if(form){form.elements.start.value=s.selected;form.elements.end.value=s.selected}
}
async function openRequests(year,month,selected){
 const current=fromKey(today());year=year||current.getFullYear();month=month||current.getMonth()+1;
 const period=monthKey(year,month),prev=state.requests;
 selected=selected||((prev&&prev.year===year&&prev.month===month)?prev.selected:(period===today().slice(0,7)?today():dayKey(year,month,1)));
 const calendar=await api("/api/me/calendar?year="+year+"&month="+month);
 const byDay=daysWithAbsences(calendar.absences,year,month),marks={};
 Object.keys(byDay).forEach(k=>(byDay[k]||[]).forEach(x=>(marks[k]??=[]).push(x.status==="approved"?"approved":x.status==="pending"?"pending":"rejected")));
 state.requests={year,month,selected,absByDay:byDay};
 const options=[["vacation","Dovolenka"],["sick","PN – oznámenie"],["ocr","OČR"],["doctor","Lekár"],["accompany","Sprevádzanie"],["doctor_unpaid","Lekár – neplatené"],["accompany_unpaid","Sprevádzanie – neplatené"],["home_office","Home office"],["unpaid","Neplatené voľno"],["other","Iné"]];
 $("#content").innerHTML=shell("requests",year,month,selected,marks)+'<section id="bid-requests-detail" class="bid-day-panel" aria-live="polite"></section><div class="bid-calendar-legend"><span><i class="bid-dot bid-dot-approved"></i> Schválené</span><span><i class="bid-dot bid-dot-pending"></i> Čakajúce</span><span><i class="bid-dot bid-dot-rejected"></i> Zamietnuté</span></div><div class="bid-request-panel" id="bid-request-create"><h3>+ Nová žiadosť</h3><form id="bid-request-form"><label>Druh<select name="kind">'+options.map(x=>'<option value="'+x[0]+'">'+x[1]+'</option>').join("")+'</select></label><div class="bid-request-dates"><label>Od<input type="date" name="start" required></label><label>Do<input type="date" name="end" required></label></div><label>Minúty (iba časť dňa)<input type="number" name="minutes" min="1" max="1440" placeholder="napr. 120"></label><label>Poznámka<input name="note" maxlength="400"></label><button type="submit" class="primary">Odoslať žiadosť</button></form></div>';
 const rows=calendar.absences.slice().sort((a,b)=>a.start.localeCompare(b.start));
 const requestList='<div class="bid-request-history"><h3>Žiadosti v zobrazenom mesiaci <span>'+rows.length+'</span></h3>'+
   (rows.length?rows.map(x=>'<button type="button" class="bid-request-history-item" data-request-day="'+safe(x.start<monthKey(year,month)+'-01'?monthKey(year,month)+'-01':x.start)+'">'+
     '<span><strong>'+safe(labels[x.kind]||x.kind)+'</strong><small>'+safe(x.start)+' – '+safe(x.end)+'</small></span>'+
     '<em class="bid-day-tag bid-day-tag-'+safe(x.status)+'">'+safe(statusLabel[x.status]||x.status)+'</em></button>').join(""):'<p class="bid-empty">Za zobrazený mesiac zatiaľ neevidujeme žiadnu žiadosť.</p>')+'</div>';
 $("#bid-request-create").insertAdjacentHTML("beforebegin",requestList);
 document.querySelectorAll(".bid-request-history-item").forEach(button=>button.onclick=()=>{
   const day=button.dataset.requestDay;
   if(day.slice(0,7)===monthKey(year,month)){
     const target=document.querySelector('[data-cal-day="'+day+'"]');
     target?.click();
   }
   document.querySelector("#bid-requests-detail")?.scrollIntoView({behavior:"smooth",block:"nearest"});
 });
 activateCalendar("requests",year,month,showRequestsDay);showRequestsDay();
 $("#bid-request-form").onsubmit=async e=>{
   e.preventDefault();
   const form=e.target,submit=form.querySelector('button[type="submit"]');
   const p=Object.fromEntries(new FormData(form));p.minutes=p.minutes?Number(p.minutes):null;
   if(p.end<p.start){toast("Dátum do musí byť rovnaký alebo neskorší než dátum od.",true);return}
   submit.disabled=true;
   try{
     const created=await api("/api/me/absences",{method:"POST",body:JSON.stringify(p)});
     const [targetYear,targetMonth]=p.start.split("-").map(Number);
     await openRequests(targetYear,targetMonth,p.start);
     const notice=document.createElement("div");
     notice.className="bid-request-success";notice.setAttribute("role","status");
     notice.innerHTML='<strong>✓ Žiadosť č. '+safe(created.id)+' bola uložená</strong><span>'+safe(labels[p.kind]||p.kind)+' · '+safe(p.start)+' – '+safe(p.end)+' · '+safe(statusLabel[created.status]||created.status)+'</span>';
     document.querySelector(".bid-request-history")?.insertAdjacentElement("beforebegin",notice);
     notice.scrollIntoView({behavior:"smooth",block:"nearest"});
     toast("Žiadosť bola úspešne uložená.");
   }catch(err){
     toast(err.message||"Žiadosť sa nepodarilo uložiť.",true);
     const existing=document.querySelector("#bid-request-error");
     if(existing)existing.remove();
     const error=document.createElement("p");error.id="bid-request-error";error.className="error";error.setAttribute("role","alert");error.textContent=err.message||"Žiadosť sa nepodarilo uložiť.";
     if(document.body.contains(form))form.prepend(error);
   }finally{
     if(document.body.contains(submit))submit.disabled=false;
   }
 };
}
window.BIDEmployeeCalendar={attendance:openAttendance,requests:openRequests,admin:openAdmin};
})();
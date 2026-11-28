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
const state={attendance:null,requests:null};
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
 return '<section class="bid-calendar-panel" aria-label="'+(mode==="attendance"?"Kalendár dochádzky":"Kalendár žiadostí")+'"><div class="bid-calendar-head"><h3>'+(mode==="attendance"?"Moja dochádzka":"Moje žiadosti")+'</h3><div class="bid-calendar-controls"><button type="button" data-cal-move="-1" aria-label="Predchádzajúci mesiac">‹</button><strong>'+safe(monthName)+'</strong><button type="button" data-cal-move="1" aria-label="Nasledujúci mesiac">›</button></div></div>'+grid+'</section>';
}
function activateCalendar(mode,year,month,renderSelection){
 const root=$("#content");root.querySelectorAll("[data-cal-day]").forEach(b=>b.onclick=()=>{state[mode].selected=b.dataset.calDay;root.querySelectorAll("[data-cal-day]").forEach(el=>{const chosen=el===b;el.classList.toggle("selected",chosen);el.setAttribute("aria-pressed",String(chosen))});renderSelection()});
 root.querySelectorAll("[data-cal-move]").forEach(b=>b.onclick=()=>{const next=makePeriod(year,month,Number(b.dataset.calMove));if(mode==="attendance")void openAttendance(next.year,next.month);else void openRequests(next.year,next.month)});
}
function showAttendanceDay(){
 const s=state.attendance,detail=$("#bid-cal-detail");if(!s||!detail)return;
 const key=s.selected,row=s.days.find(x=>x.day===key),events=s.events.filter(x=>x.day===key),req=(s.absByDay[key]||[]);
 const header='<div class="bid-day-title"><strong>'+safe(new Intl.DateTimeFormat("sk-SK",{weekday:"long",day:"numeric",month:"long"}).format(fromKey(key)))+'</strong><span>Odpracované '+shortHours(row?.worked_minutes||0)+' h</span></div>';
 const evMarkup=events.length?events.map(x=>'<div class="bid-activity"><span>'+safe(x.time)+'</span><strong>'+safe(eventsLabel[x.kind]||x.kind)+'</strong><small>'+safe(x.origin==="demo"?"Ukážkový záznam":"Dochádzka")+'</small></div>').join(""):'<p class="bid-empty">Pre tento deň nie sú zaznamenané príchody ani odchody.</p>';
 const absMarkup=req.map(x=>'<div class="bid-activity bid-activity-absence"><span>◉</span><strong>'+safe(labels[x.kind]||x.kind)+'</strong><small>'+safe(statusLabel[x.status]||x.status)+'</small></div>').join("");
 const footer=row?'<div class="bid-cal-summary"><span>Práca: '+shortHours(row.worked_minutes)+' h</span><span>Prestávka: '+shortHours(row.break_minutes)+' h</span><span>Fond: '+shortHours(row.planned_minutes)+' h</span><span>Saldo: '+shortHours(row.saldo_minutes)+' h</span></div>':'';
 detail.innerHTML=header+evMarkup+absMarkup+footer;
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
 activateCalendar("requests",year,month,showRequestsDay);showRequestsDay();
 $("#bid-request-form").onsubmit=async e=>{e.preventDefault();const p=Object.fromEntries(new FormData(e.target));p.minutes=p.minutes?Number(p.minutes):null;if(p.end<p.start){toast("Dátum do musí byť rovnaký alebo neskorší než dátum od.",true);return}try{await api("/api/me/absences",{method:"POST",body:JSON.stringify(p)});toast("Žiadosť bola odoslaná.");await openRequests(year,month,selected)}catch(err){toast(err.message,true)}};
}
window.BIDEmployeeCalendar={attendance:openAttendance,requests:openRequests};
})();
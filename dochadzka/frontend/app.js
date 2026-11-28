let token=sessionStorage.getItem('attendance_token')||'',currentUser=null,employees=[],view='dashboard';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>(Math.abs(n||0)/60).toLocaleString('sk-SK',{maximumFractionDigits:2})+' h',localDate=d=>{const x=d||new Date();return [x.getFullYear(),String(x.getMonth()+1).padStart(2,'0'),String(x.getDate()).padStart(2,'0')].join('-')};
const monthStart=()=>localDate(new Date(new Date().getFullYear(),new Date().getMonth(),1));
function toast(msg,bad=false){const e=$('#toast');e.textContent=msg;e.style.background=bad?'#a4334d':'#173351';e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3700)}
async function api(url,opts={}){const r=await fetch(url,{...opts,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...(opts.headers||{})}});let d;try{d=await r.json()}catch{d={detail:'Neznáma odpoveď servera'}}if(!r.ok){if(r.status===401&&url!='/api/auth/login'){logout();throw Error('Relácia vypršala. Prihláste sa.')};throw Error(typeof d.detail==='string'?d.detail:'Server vrátil chybu '+r.status)}return d}
function logout(){token='';currentUser=null;sessionStorage.removeItem('attendance_token');$('#app').classList.add('hidden');$('#login').classList.remove('hidden')}
async function init(){if(!token){logout();return}try{currentUser=await api('/api/auth/me');$('#userBadge').textContent=currentUser.username.toUpperCase();$('#login').classList.add('hidden');$('#app').classList.remove('hidden');$('#today').textContent=new Intl.DateTimeFormat('sk-SK',{dateStyle:'long'}).format(new Date());if(currentUser.must_change_password){document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('hidden',n.dataset.view!=='accounts'));view='accounts';navigate('accounts');return}if(currentUser.role==='scheduler'){
  employees=await api('/api/scheduler/employees');
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('hidden',!['shifts','accounts'].includes(n.dataset.view)));
  view='shifts';
}else if(['employee','manager','auditor'].includes(currentUser.role)){employees=[];document.querySelectorAll('.nav').forEach(n=>{n.classList.toggle('hidden',!['dashboard','requests','accounts'].includes(n.dataset.view))});view='dashboard';}else{document.querySelectorAll('.nav').forEach(n=>n.classList.remove('hidden'));await refreshEmployees();}navigate(view);updateStorageWarning();refreshLegalNoticeBanner()}catch(e){logout();toast(e.message,true)}}
async function refreshEmployees(){try{employees=await api('/api/employees')}catch(e){employees=[];toast(e.message,true)}}
const choose=(id='empSelect')=>'<select id="'+id+'">'+employees.map(e=>'<option value="'+e.id+'">'+esc(e.name)+'</option>').join('')+'</select>';
function head(title){$('#pageTitle').textContent=title;$('#breadcrumb').textContent=title.toUpperCase();document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===view))}
async function navigate(name){if(currentUser?.must_change_password)name='accounts';if(currentUser?.role==='scheduler'&&!['shifts','accounts'].includes(name)){name='shifts'}if(['employee','manager','auditor'].includes(currentUser?.role)&&!['dashboard','requests','accounts'].includes(name)){name='dashboard'}view=name;const map={dashboard:'Prehľad dochádzky',groupReport:'Hromadný výkaz dochádzky',approvalCenter:'Kontrola a plánovanie',travel:'Služobné cesty a náhrady',meals:'Stravovanie a nároky',employees:'Zamestnanci',organization:'Organizačná štruktúra',exports:'Exportné profily',quality:'Kontrola dochádzky',corrections:'Opravy záznamov',legal:'Zákonné nároky',legalMonitor:'Monitor legislatívy',requests:'Neprítomnosti',shifts:'Rozpis zmien',reports:'Výkazy a saldo',terminal:'Dochádzkové terminály',payroll:'Uzávierka a export',accounts:'Používateľské účty',holidays:'Sviatky Slovenskej republiky'};head(map[name]||'Dochádzka');try{await ({dashboard,groupReportView,approvalCenterView,travelView,mealsView,employeesView,organizationView,exportProfilesView,qualityView,correctionsView,legalView,legalMonitorView,requests,shifts,reports,terminal,accounts,holidaysView,payrollView}[{dashboard:'dashboard',groupReport:'groupReportView',approvalCenter:'approvalCenterView',travel:'travelView',meals:'mealsView',employees:'employeesView',organization:'organizationView',exports:'exportProfilesView',quality:'qualityView',corrections:'correctionsView',legal:'legalView',legalMonitor:'legalMonitorView',requests:'requests',shifts:'shifts',reports:'reports',terminal:'terminal',payroll:'payrollView',accounts:'accounts',holidays:'holidaysView'}[name]])()}catch(e){$('#content').innerHTML='<div class="error">'+esc(e.message)+'</div>';toast(e.message,true)}}
async function employeePasswordView(){
$('#content').innerHTML='<div class="panel"><h3>Zmeniť heslo</h3><form id="selfPassword"><label class="field"><span>Aktuálne heslo</span><input type="password" name="old_password" autocomplete="current-password" required></label><label class="field"><span>Nové heslo (min. 12 znakov)</span><input type="password" name="new_password" autocomplete="new-password" minlength="12" required></label><button class="primary">Uložiť nové heslo</button></form></div>';
const mfaBox=document.createElement('div');mfaBox.className='panel';mfaBox.innerHTML='<h3>Bezpečnosť účtu</h3><button class="secondary" id="enableMfa">Zapnúť dvojfaktorové overenie</button><div id="mfaSetupPanel"></div>';$('#content').append(mfaBox);$('#enableMfa').onclick=setupMfa;
$('#selfPassword').onsubmit=async ev=>{ev.preventDefault();try{await api('/api/auth/password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(ev.target)))});ev.target.reset();toast('Heslo zmenené');await init()}catch(e){toast(e.message,true)}};
}
async function auditorDashboard(){
 const list=await api('/api/audit?limit=100');
 $('#content').innerHTML='<div class="panel"><h3>Audit posledných operácií</h3><div class="notice">Audit má iba režim čítania. Zmeny údajov musí vykonať oprávnený personalista alebo administrátor.</div><div class="scroll"><table><thead><tr><th>Čas</th><th>Používateľ</th><th>Akcia</th><th>Detail</th></tr></thead><tbody>'+list.map(x=>'<tr><td>'+esc(String(x.at).slice(0,19))+'</td><td>'+esc(x.actor)+'</td><td>'+esc(x.action)+'</td><td>'+esc(x.detail)+'</td></tr>').join('')+'</tbody></table></div></div>';
}
async function managerDashboard(){
 const list=await api('/api/team/absences');
 const pending=list.filter(x=>x.status==='pending');
 const [yr,mo]=localDate().slice(0,7).split('-').map(Number);
 const attendance=await api('/api/workflow/team-month/'+yr+'/'+mo).catch(()=>({rows:[]}));
 $('#content').innerHTML='<div class="stats"><div class="stat"><div class="stat-icon">▣</div><div class="value">'+pending.length+'</div><small>Čakajúce schválenia</small></div><div class="stat"><div class="stat-icon">♙</div><div class="value">'+new Set(list.map(x=>x.employee_id)).size+'</div><small>Ľudia so žiadosťami</small></div></div><div class="panel"><div class="section-top"><h3>Žiadosti tímu</h3><button class="primary" data-go="requests">Otvoriť schvaľovanie</button></div><p class="muted">Zobrazené sú len žiadosti priamo priradených podriadených. Vlastné žiadosti sa nedajú schváliť.</p>'+ (pending.length?'<div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Druh</th><th>Od</th><th>Do</th><th>Rozhodnutie</th></tr></thead><tbody>'+pending.map(x=>'<tr><td>'+esc(x.employee_name)+'</td><td>'+esc(x.kind)+'</td><td>'+esc(x.start)+'</td><td>'+esc(x.end)+'</td><td><div class="actions"><button class="primary mini" data-quick-absence="'+x.id+'" data-decision="approve">Schváliť</button><button class="secondary mini danger" data-quick-absence="'+x.id+'" data-decision="reject">Zamietnuť</button></div></td></tr>').join('')+'</tbody></table></div>':'<p class="empty">Žiadne otvorené žiadosti.</p>')+'</div>';
 $('#content').insertAdjacentHTML('beforeend','<div class="panel"><div class="section-top"><div><h3>Potvrdenie dochádzky tímu</h3><span class="muted">Kontrola zamestnanca → potvrdenie vedúceho → mesačná uzávierka HR</span></div></div><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Stav</th><th>Akcia</th></tr></thead><tbody>'+attendance.rows.map(r=>'<tr><td>'+esc(r.name)+'</td><td>'+esc(r.status.status)+'</td><td>'+(r.status.status==='reviewed'?'<button class="primary mini" data-team-confirm="'+r.employee_id+'">Potvrdiť</button>':'—')+'</td></tr>').join('')+'</tbody></table></div></div>');
 wireQuickAbsenceActions($('#content'),true);
 document.querySelectorAll('[data-team-confirm]').forEach(x=>x.onclick=async()=>{if(!confirm('Potvrdiť skontrolovanú dochádzku?'))return;try{await api('/api/workflow/confirm',{method:'POST',body:JSON.stringify({employee_id:Number(x.dataset.teamConfirm),year:yr,month:mo,note:'Potvrdenie vedúcim'})});toast('Dochádzka tímu potvrdená');managerDashboard()}catch(e){toast(e.message,true)}});

}
async function managerRequests(){
 const list=await api('/api/team/absences');
 $('#content').innerHTML='<div class="panel"><h3>Schvaľovanie priamych podriadených</h3><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Druh</th><th>Od</th><th>Do</th><th>Stav</th><th>Akcia</th></tr></thead><tbody>'+list.map(x=>'<tr><td>'+esc(x.employee_name)+'</td><td>'+esc(x.kind)+'</td><td>'+esc(x.start)+'</td><td>'+esc(x.end)+'</td><td>'+esc(x.status)+'</td><td>'+(x.status==='pending'?'<button class="secondary mini" data-team-approve="'+x.id+'">Schváliť</button> <button class="secondary mini danger" data-team-reject="'+x.id+'">Zamietnuť</button>':'—')+'</td></tr>').join('')+'</tbody></table></div></div>';
 for(const b of document.querySelectorAll('[data-team-approve],[data-team-reject]')){b.onclick=async()=>{const id=b.dataset.teamApprove||b.dataset.teamReject;const decision=b.dataset.teamApprove?'approve':'reject';try{await api('/api/team/absences/'+id+'/'+decision,{method:'POST'});toast('Žiadosť vybavená');managerRequests()}catch(e){toast(e.message,true)}}}
}
async function employeeDashboard(){
const d=await api('/api/me/summary');
const remoteStatus=await api('/api/me/remote-status').catch(()=>({remote_punch_enabled:false,approved_home_office:false,state:'off'}));
const [reviewYear,reviewMonth]=d.period.split('-').map(Number);
const ownDays=await api('/api/me/attendance?year='+reviewYear+'&month='+reviewMonth).catch(()=>({rows:[],total_saldo_minutes:0}));
const reviewStatus=await api('/api/workflow/my-month?year='+reviewYear+'&month='+reviewMonth).catch(()=>({status:'pending'}));
$('#content').innerHTML='<p class="intro">Vitaj, <strong>'+esc(d.name)+'</strong>. Tu je prehľad tvojich vlastných údajov za '+esc(d.period)+'.</p><div class="stats"><div class="stat"><div class="stat-icon">◷</div><div class="value">'+fmt(d.worked_minutes)+'</div><small>Uzavreté odpracované hodiny</small></div><div class="stat"><div class="stat-icon">▣</div><div class="value">'+d.requests.length+'</div><small>Žiadosti v mesiaci</small></div><div class="stat"><div class="stat-icon">◈</div><div class="value">'+(d.last_event?esc(d.last_event.kind):'—')+'</div><small>Posledné pípnutie</small></div><div class="stat"><div class="stat-icon">♙</div><div class="value">'+fmt(d.weekly_minutes)+'</div><small>Týždenný úväzok</small></div></div><div class="panel"><div class="section-top"><h3>Moje žiadosti</h3><button class="primary" data-go="requests">+ Nová žiadosť</button><button id="selfPdf" class="secondary">Môj výkaz PDF</button></div><div class="scroll"><table><thead><tr><th>Typ</th><th>Od</th><th>Do</th><th>Stav</th></tr></thead><tbody>'+d.requests.map(x=>'<tr><td>'+esc(x.kind)+'</td><td>'+esc(x.start)+'</td><td>'+esc(x.end)+'</td><td><span class="pill '+esc(x.status)+'">'+esc(x.status)+'</span></td></tr>').join('')+'</tbody></table></div></div><div class="notice">'+esc(d.note)+(d.warnings.length?' Upozornenia: '+d.warnings.map(esc).join(', '):'')+'</div>';
  const remote=document.createElement('div');remote.className='panel';remote.innerHTML='<div class="section-top"><div><h3>Home office · pípnutie na diaľku</h3><span class="muted">Serverový čas, prihlásený účet a iba v schválený deň</span></div><span class="pill '+(remoteStatus.approved_home_office?'approved':'pending')+'">'+(remoteStatus.approved_home_office?'Schválené':'Nie je schválené')+'</span></div><p class="intro">Aktuálny stav: <strong>'+esc(remoteStatus.state==='working'?'Pracujem':remoteStatus.state==='break'?'Prestávka':'Mimo práce')+'</strong></p><label class="gr-gps-check"><input id="remoteAskGps" type="checkbox"> Voliteľne jednorazovo poskytnúť polohu pri pípnutí. Súradnice sa neukladajú.</label><div class="actions"><button data-remote-kind="in" class="primary" '+(!remoteStatus.remote_punch_enabled||remoteStatus.state!=='off'?'disabled':'')+'>Príchod · home office</button><button data-remote-kind="break_start" class="secondary" '+(!remoteStatus.remote_punch_enabled||remoteStatus.state!=='working'?'disabled':'')+'>Prestávka</button><button data-remote-kind="break_end" class="secondary" '+(!remoteStatus.remote_punch_enabled||remoteStatus.state!=='break'?'disabled':'')+'>Koniec prestávky</button><button data-remote-kind="out" class="secondary" '+(!remoteStatus.remote_punch_enabled||remoteStatus.state!=='working'?'disabled':'')+'>Odchod</button></div><p class="subtle">Home office musí najprv schváliť HR. GPS nie je dôkazom výkonu práce a je voliteľné. Neprebieha priebežné sledovanie.</p>';$('#content').append(remote);
  document.querySelectorAll('[data-remote-kind]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Zaznamenať '+btn.textContent+' podľa času servera?'))return;btn.disabled=true;const p={kind:btn.dataset.remoteKind};try{if($('#remoteAskGps').checked){if(!navigator.geolocation)throw Error('Geolokácia nie je dostupná. Vypni GPS alebo použi podporovaný prehliadač.');const coord=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(x=>resolve(x.coords),reject,{enableHighAccuracy:false,timeout:12000,maximumAge:0}));p.gps_lat=coord.latitude;p.gps_lon=coord.longitude;p.gps_accuracy_m=coord.accuracy;p.gps_permission_confirmed=true;}await api('/api/me/remote-punch',{method:'POST',body:JSON.stringify(p)});toast('Home office pípnutie uložené');employeeDashboard()}catch(e){toast(e.message||'Pípnutie zlyhalo',true);btn.disabled=false}});
  const own=document.createElement('div');own.className='panel';own.innerHTML='<div class="section-top"><div><h3>Moja denná dochádzka</h3><span class="muted">Príchody, odchody, home office, prestávky a saldo</span></div><strong>Saldo: '+groupReportHour(ownDays.total_saldo_minutes,true)+'</strong></div><div class="scroll"><table><thead><tr><th>Deň</th><th>Príchod</th><th>Odchod</th><th>Práca</th><th>Prestávka</th><th>Fond</th><th>Saldo</th><th>Zložka</th></tr></thead><tbody>'+ownDays.rows.map(x=>'<tr><td>'+esc(x.day)+'</td><td>'+esc(x.in||'—')+'</td><td>'+esc(x.out||'—')+'</td><td>'+groupReportHour(x.worked_minutes)+'</td><td>'+groupReportHour(x.break_minutes)+'</td><td>'+groupReportHour(x.planned_minutes)+'</td><td>'+groupReportHour(x.saldo_minutes,true)+'</td><td>'+esc(x.component==='home_office'?'Home office':x.component||'Práca')+'</td></tr>').join('')+'</tbody></table></div><p class="subtle">'+esc(ownDays.note||'Údaje sú orientačné.')+'</p>';$('#content').append(own);
  const review=document.createElement('div');review.className='panel';review.innerHTML='<div class="section-top"><div><h3>Kontrola mojej dochádzky</h3><span class="muted">Skontroluj svoj mesačný výkaz a potom ho potvrď.</span></div><span class="pill">'+esc(reviewStatus.status==='confirmed'?'Potvrdené vedúcim':reviewStatus.status==='reviewed'?'Skontrolované':'Čaká na kontrolu')+'</span></div><button id="reviewMyMonth" class="primary" '+(reviewStatus.status!=='pending'?'disabled':'')+'>Označiť ako skontrolované</button><p class="subtle">Kontrola neuzatvára dochádzku ani nemodifikuje pípnutia.</p>';$('#content').append(review);
  $('#reviewMyMonth').onclick=async()=>{if(!confirm('Potvrdiť kontrolu svojho výkazu za '+d.period+'?'))return;try{await api('/api/workflow/review',{method:'POST',body:JSON.stringify({employee_id:currentUser.employee_id,year:reviewYear,month:reviewMonth,note:'Kontrola vlastného výkazu'})});toast('Kontrola zaznamenaná');employeeDashboard()}catch(e){toast(e.message,true)}};
  $('#selfPdf')?.addEventListener('click',async()=>{const period=localDate().slice(0,7);const [year,month]=period.split('-');try{await fetchProtectedFile('/api/me/monthly-pdf?year='+year+'&month='+Number(month),'moja_dochadzka_'+period+'.pdf');toast('PDF výkaz uložený')}catch(e){toast(e.message,true)}});
}
async function fetchProtectedFile(url,filename){
  const res=await fetch(url,{headers:{Authorization:'Bearer '+token},cache:'no-store'});
  if(!res.ok){const err=await res.json().catch(()=>({detail:'Export sa nepodaril'}));throw new Error(err.detail||'Export zlyhal')}
  const blob=await res.blob(),link=document.createElement('a'),object=URL.createObjectURL(blob);
  link.href=object;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(object),1500);
}
async function payrollView(){
  const today=localDate().slice(0,7);
  const closed=await api('/api/payroll/months');
  $('#content').innerHTML='<div class="grid2"><div class="panel"><h3>Mesačná uzávierka a mzdové podklady</h3><div class="notice">Výpočty sú kontrolné, nejde o právne záväzný výplatný podklad. Uzávierka blokuje úpravy rozpisu a neprítomností v uzavretom mesiaci.</div><label class="field"><span>Vyber mesiac</span><input id="payrollPeriod" type="month" value="'+today+'"></label><div class="actions"><button id="payrollExport" class="primary">Export CSV</button><button id="payrollClose" class="secondary">Uzavrieť mesiac</button><button id="payrollOpen" class="secondary">Odomknúť mesiac</button><button id="encryptedBackup" class="secondary">Šifrovaná záloha dát</button></div></div><div class="panel"><h3>História uzávierok</h3><div class="scroll"><table><thead><tr><th>Obdobie</th><th>Uzavrel</th><th>Dátum</th></tr></thead><tbody>'+closed.map(x=>'<tr><td>'+x.year+'-'+String(x.month).padStart(2,'0')+'</td><td>'+esc(x.closed_by)+'</td><td>'+esc(String(x.closed_at).slice(0,16))+'</td></tr>').join('')+'</tbody></table></div></div></div>';
  const period=()=>($('#payrollPeriod').value||today).split('-').map(Number);
  $('#payrollExport').onclick=async()=>{const [y,m]=period();try{await fetchProtectedFile('/api/payroll/export.csv?year='+y+'&month='+m,'mzdy_dochadzka_'+y+'_'+String(m).padStart(2,'0')+'.csv');toast('Export hotový')}catch(e){toast(e.message,true)}};
  $('#payrollClose').onclick=async()=>{const [y,m]=period();try{const precheck=await api('/api/workflow/close-precheck/'+y+'/'+m);if(!precheck.ready){toast('Chýbajú potvrdenia: '+precheck.missing.length+' zamestnancov',true);if(!confirm('Niektorí zamestnanci nemajú potvrdenú dochádzku. Otvoriť kontrolu a plánovanie?'))return;return approvalCenterView(y+'-'+String(m).padStart(2,'0'))}if(!confirm('Dochádzky sú potvrdené. Uzavrieť mesiac '+y+'-'+m+'?'))return;await api('/api/payroll/close/'+y+'/'+m,{method:'POST'});toast('Mesiac uzavretý');payrollView()}catch(e){toast(e.message,true)}};
  $('#payrollOpen').onclick=async()=>{const [y,m]=period();if(!confirm('Odomknúť mesiac '+y+'-'+m+'? Operácia sa zaznamená do auditu.'))return;try{await api('/api/payroll/reopen/'+y+'/'+m,{method:'POST'});toast('Mesiac odomknutý');payrollView()}catch(e){toast(e.message,true)}};
  $('#encryptedBackup').onclick=async()=>{
    if(currentUser?.role!=='admin')return toast('Šifrovanú zálohu môže vytvoriť len administrátor',true);
    const passphrase=prompt('Heslo na šifrovanie zálohy (min. 16 znakov). Bez tohto hesla sa záloha nedá obnoviť. Neulož ho do GitHubu.');
    if(!passphrase)return;
    if(passphrase.length<16)return toast('Heslo zálohy musí mať aspoň 16 znakov',true);
    const confirmPass=prompt('Potvrď heslo zálohy');
    if(passphrase!==confirmPass)return toast('Heslá sa nezhodujú',true);
    try{
      const response=await fetch('/api/admin/backup',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({passphrase}),cache:'no-store'});
      if(!response.ok){const err=await response.json().catch(()=>({detail:'Zálohu sa nepodarilo vytvoriť'}));throw Error(err.detail||'Zálohu sa nepodarilo vytvoriť')}
      const blob=await response.blob();const url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download='bid-dochadzka-'+localDate()+'.bidbak';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
      toast('Šifrovaná záloha stiahnutá. Bezpečne si ju odlož mimo GitHubu.');
    }catch(error){toast(error.message,true)}
  };

  if(currentUser?.role==='admin'){
    try{
      const backups=await api('/api/admin/backups/status');
      const el=document.createElement('div');el.className='panel';
      el.innerHTML='<div class="section-top"><div><h3>Automatické šifrované zálohy</h3><span class="muted">Trvalý PostgreSQL + súkromné zálohovacie úložisko, nie GitHub</span></div><button id="backupRunNow" class="secondary" '+(backups.configured?'':'disabled')+'>Spustiť overenú zálohu</button></div><div class="notice">'+esc(backups.note)+'</div><p><strong>Trvalá databáza:</strong> '+(backups.persistent_database?'Áno':'Nie')+' · <strong>S3 úložisko:</strong> '+esc(backups.destination)+' · <strong>Automatické zálohy:</strong> '+(backups.scheduler_enabled?'Zapnuté (iba počas behu servera)':'Vypnuté')+'</p><div class="scroll"><table><thead><tr><th>Spustenie</th><th>Stav</th><th>Veľkosť</th><th>Výsledok</th></tr></thead><tbody>'+backups.runs.map(x=>'<tr><td>'+esc(x.started_at||'—')+'</td><td>'+esc(x.status)+'</td><td>'+x.size_bytes+' B</td><td>'+esc(x.error||'—')+'</td></tr>').join('')+'</tbody></table></div>';
      $('#content').append(el);
      $('#backupRunNow').onclick=async()=>{if(!confirm('Spustiť a overiť šifrovanú zálohu do súkromného S3?'))return;try{const result=await api('/api/admin/backups/run',{method:'POST'});toast('Záloha '+result.status);payrollView()}catch(e){toast(e.message,true)}};
    }catch(error){toast(error.message,true)}
  }

}
async function employeeRequests(){
const d=await api('/api/me/summary');
const types=[['vacation','Dovolenka'],['sick','PN – oznámenie'],['doctor','Lekár'],['accompany','Sprevádzanie'],['doctor_unpaid','Lekár neplatené'],['accompany_unpaid','Sprevádzanie neplatené'],['ocr','OČR'],['home_office','Home office – práca na diaľku'],['unpaid','Neplatené voľno'],['other','Iná prekážka']];
$('#content').innerHTML='<div class="grid2"><div class="panel"><h3>Požiadať o neprítomnosť</h3><form id="selfAbsence"><label class="field"><span>Druh</span><select name="kind">'+types.map(([v,n])=>'<option value="'+v+'">'+n+'</option>').join('')+'</select></label><div class="form-grid"><label class="field"><span>Od</span><input type="date" name="start" value="'+localDate()+'" required></label><label class="field"><span>Do</span><input type="date" name="end" value="'+localDate()+'" required></label></div><label class="field"><span>Minúty (iba čiastočný deň)</span><input type="number" name="minutes" min="1" max="1440"></label><label class="field"><span>Poznámka</span><input name="note" maxlength="400"></label><button class="primary">Odoslať žiadosť</button></form></div><div class="panel"><h3>Moje žiadosti</h3><div class="scroll"><table><thead><tr><th>Druh</th><th>Obdobie</th><th>Stav</th></tr></thead><tbody>'+d.requests.map(x=>'<tr><td>'+esc(x.kind)+'</td><td>'+esc(x.start)+' – '+esc(x.end)+'</td><td><span class="pill '+esc(x.status)+'">'+esc(x.status)+'</span></td></tr>').join('')+'</tbody></table></div></div></div>';
$('#selfAbsence').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.minutes=p.minutes?Number(p.minutes):null;try{await api('/api/me/absences',{method:'POST',body:JSON.stringify(p)});toast('Žiadosť bola odoslaná');employeeRequests()}catch(e){toast(e.message,true)}};
}
const absenceLabels={vacation:'Dovolenka',doctor:'Lekár',accompany:'Sprevádzanie',doctor_unpaid:'Lekár – neplatené',accompany_unpaid:'Sprevádzanie – neplatené',sick:'PN',ocr:'OČR',home_office:'Home office',business_trip:'Služobná cesta',training:'Školenie',paid_leave:'Platené voľno',unpaid:'Neplatené voľno',maternity:'Materská',paternity:'Otcovská',parental:'Rodičovská',wedding:'Svadba',funeral:'Pohreb',blood_donation:'Darovanie krvi',other:'Iné'};
async function dashboard(){
 if(currentUser?.role==='employee')return employeeDashboard();
 if(currentUser?.role==='manager')return managerDashboard();
 if(currentUser?.role==='auditor')return auditorDashboard();
 const abs=await api('/api/absences');
 const pending=abs.filter(x=>x.status==='pending');
 $('#content').innerHTML='<div class="stats"><div class="stat"><div class="stat-icon">♙</div><div class="value">'+employees.length+'</div><small>Zamestnanci</small></div><div class="stat"><div class="stat-icon">▣</div><div class="value">'+pending.length+'</div><small>Žiadosti na schválenie</small></div><div class="stat"><div class="stat-icon">◷</div><div class="value">'+new Date().getFullYear()+'</div><small>Aktuálny rok</small></div><div class="stat"><div class="stat-icon">◈</div><div class="value">RFID</div><small>Podpora Raspberry Pi</small></div></div><div class="grid2"><div class="panel"><div class="section-top"><h3>Rýchle akcie</h3></div><div class="actions"><button class="primary" data-go="employees">+ Zamestnanec</button><button class="secondary" data-go="requests">+ Neprítomnosť</button><button class="secondary" data-go="reports">Výkazy</button></div><p class="intro">Spravuj tím, čerpanie dovoleniek a príchody z terminálov. Na mobile použi spodnú navigáciu a tlačidlo Viac.</p></div><div class="panel"><div class="section-top"><h3>Čakajúce žiadosti</h3><button class="secondary mini" data-go="requests">Všetky žiadosti ('+pending.length+')</button></div>'+tableAbs(pending.slice(0,8),true)+'</div></div><div class="notice">Výpočty nárokov a pracovného fondu sú orientačné. Pred mzdovou uzávierkou ich treba skontrolovať s pracovným rozvrhom a platnou legislatívou.</div>';
 wireQuickAbsenceActions($('#content'),false);
}
function tableAbs(rows,actions=false){
 if(!rows.length)return '<p class="empty">Žiadne čakajúce žiadosti.</p>';
 return '<div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Typ</th><th>Od</th><th>Do</th><th>Stav</th>'+(actions?'<th>Rozhodnutie</th>':'')+'</tr></thead><tbody>'+rows.map(a=>'<tr><td>'+esc(employees.find(e=>e.id===a.employee_id)?.name||a.employee_id)+'</td><td>'+esc(absenceLabels[a.kind]||a.kind)+'</td><td>'+esc(a.start)+'</td><td>'+esc(a.end)+'</td><td><span class="pill '+esc(a.status)+'">'+esc(a.status==='pending'?'Čaká na schválenie':a.status)+'</span></td>'+(actions?'<td><div class="actions"><button class="primary mini" data-quick-absence="'+a.id+'" data-decision="approve">✓ Schváliť</button><button class="secondary mini danger" data-quick-absence="'+a.id+'" data-decision="reject">✕ Zamietnuť</button></div></td>':'')+'</tr>').join('')+'</tbody></table></div>';
}
function wireQuickAbsenceActions(root,team=false){
 root.querySelectorAll('[data-quick-absence]').forEach(button=>button.onclick=async()=>{
  const absenceId=Number(button.dataset.quickAbsence),decision=button.dataset.decision;
  if(!Number.isInteger(absenceId)||!['approve','reject'].includes(decision))return;
  const action=decision==='approve'?'schváliť':'zamietnuť';
  if(!confirm('Naozaj '+action+' žiadosť č. '+absenceId+'?'))return;
  const row=button.closest('tr');
  const all=row?.querySelectorAll('[data-quick-absence]')||[];
  all.forEach(b=>b.disabled=true);
  try{
   const endpoint=team?'/api/team/absences/'+absenceId+'/'+decision:'/api/absences/'+absenceId+'/'+decision;
   await api(endpoint,{method:'POST'});
   toast(decision==='approve'?'Žiadosť bola schválená':'Žiadosť bola zamietnutá');
   if(team)await managerDashboard();else await dashboard();
  }catch(error){all.forEach(b=>b.disabled=false);toast(error.message,true)}
 });
}
let hrRows=[],hrTemplates=[];
const hrDate=v=>v?String(v).slice(0,10):'';
const hrOption=(value,label,selected)=>'<option value="'+esc(value)+'" '+(String(value)===String(selected)?'selected':'')+'>'+esc(label)+'</option>';
async function employeesView(){
  const [people,templates]=await Promise.all([api('/api/hr/employees'),api('/api/hr/shift-templates')]);
  hrRows=people;hrTemplates=templates;
  $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Zamestnanci a účty</h3><span class="muted">'+people.length+' zamestnancov · kliknutím otvoríš detail</span></div><div class="actions"><input id="hrSearch" placeholder="Hľadať meno, číslo, útvar…" aria-label="Hľadať zamestnancov"><label class="field hr-period"><span>Obdobie PDF</span><input id="hrPdfMonth" type="month" value="'+localDate().slice(0,7)+'"></label><button class="primary" id="hrNew">+ Nový zamestnanec</button></div></div><div id="hrGrid" class="scroll"></div></div><div class="panel"><div class="section-top"><h3>Pracovné zmeny a šablóny</h3><button class="secondary" id="hrNewTemplate">+ Nová šablóna zmeny</button></div><div class="shift-pills">'+templates.map(t=>'<span class="shift-pill">'+esc(t.name)+' · '+esc(t.start)+'–'+esc(t.end)+'</span>').join('')+'</div><p class="subtle">Šablóna v profile nastaví predvolený režim zamestnanca. Konkrétne zmeny po dňoch sa plánujú v časti Zmeny a plán.</p></div><div id="hrModalHost"></div>';
  const grid=()=>{
    const q=($('#hrSearch').value||'').trim().toLocaleLowerCase('sk-SK');
    const shown=people.filter(p=>[p.name,p.personal_number,p.department,p.job_title].some(v=>String(v||'').toLocaleLowerCase('sk-SK').includes(q)));
    $('#hrGrid').innerHTML='<table class="hr-table"><thead><tr><th>Os. č.</th><th>Meno a priezvisko</th><th>Útvar / pozícia</th><th>Úväzok</th><th>RFID čip</th><th>Pracovný režim</th><th>Stav</th><th></th></tr></thead><tbody>'+shown.map(p=>'<tr><td>'+esc(p.personal_number)+'</td><td><strong>'+esc(p.name)+'</strong><div class="subtle">'+esc(p.email)+'</div></td><td>'+esc(p.department||'—')+'<div class="subtle">'+esc(p.job_title)+'</div></td><td>'+esc(p.fte).replace('.',',')+'</td><td>'+(p.card_uid?'<span class="pill approved">'+esc(p.card_uid)+'</span>':'—')+'</td><td>'+esc(hrTemplates.find(t=>t.id===p.shift_template_id)?.name||p.work_regime||'—')+'</td><td><span class="pill '+(p.active?'approved':'rejected')+'">'+(p.active?'Aktívny':'Neaktívny')+'</span></td><td><button class="secondary mini" data-hr-edit="'+p.id+'">Upraviť</button> <button class="secondary mini" data-hr-pdf="'+p.id+'">PDF</button></td></tr>').join('')+'</tbody></table>'+(shown.length?'':'<p class="empty">Nenašli sa žiadni zamestnanci.</p>');
    document.querySelectorAll('[data-hr-edit]').forEach(btn=>btn.onclick=()=>openHrEditor(Number(btn.dataset.hrEdit)));
    document.querySelectorAll('[data-hr-pdf]').forEach(btn=>btn.onclick=()=>downloadEmployeePdf(Number(btn.dataset.hrPdf)));
  };
  $('#hrSearch').oninput=grid;grid();
  $('#hrNew').onclick=()=>openHrEditor(null);
  $('#hrNewTemplate').onclick=openHrTemplateEditor;
  const nfc=document.createElement('div');nfc.className='panel';nfc.innerHTML='<div class="section-top"><div><h3>NFC / RFID čipy zamestnancov</h3><span class="muted">Priraď čip k zamestnancovi · podporuje mobilné NDEF NFC alebo USB čítačku s klávesnicovým výstupom</span></div></div><div class="form-grid"><label class="field"><span>Zamestnanec</span><select id="nfcEmployee">'+people.map(x=>'<option value="'+x.id+'">'+esc(x.name)+' · '+esc(x.personal_number)+'</option>').join('')+'</select></label><label class="field"><span>UID čipu v hexadecimálnom tvare</span><input id="nfcUid" maxlength="128" placeholder="04:A1:B2:C3 alebo UID z čítačky"></label></div><div class="actions"><button id="nfcScanAndroid" class="secondary">Načítať NFC cez mobil</button><button id="nfcAssign" class="primary">Priradiť zamestnancovi</button></div><p class="subtle">Web NFC funguje na podporovanom Android Chrome pre NDEF čipy. Bežné RFID 125 kHz a niektoré karty MIFARE nemusia cez mobil fungovať – použi externú USB čítačku. UID čipu možno klonovať, nie je to samostatné bezpečné prihlásenie.</p>';$('#content').append(nfc);
  $('#nfcUid').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('#nfcAssign').click()}});
  $('#nfcScanAndroid').onclick=async()=>{if(!('NDEFReader' in window))return toast('Web NFC tu nie je podporované. Použi Chrome na Androide alebo USB čítačku.',true);try{const reader=new NDEFReader();await reader.scan();toast('Prilož NFC čip k telefónu');reader.onreading=ev=>{if(!ev.serialNumber){toast('Táto NFC karta neposkytuje sériové číslo. Použi externú čítačku.',true);return;}$('#nfcUid').value=ev.serialNumber.toUpperCase();toast('NFC identifikátor načítaný – potvrď priradenie')}}catch(e){toast(e.message||'NFC čítanie nie je dostupné',true)}};
  $('#nfcAssign').onclick=async()=>{const uid=$('#nfcUid').value.trim().toUpperCase(),employee_id=Number($('#nfcEmployee').value);if(!uid)return toast('Načítaj alebo zadaj UID čipu',true);if(!confirm('Priradiť UID '+uid+' vybranému zamestnancovi? Existujúci čip sa zmení.'))return;try{await api('/api/hr/nfc/assign',{method:'POST',body:JSON.stringify({employee_id,tag_uid:uid})});toast('Čip priradený s auditom');employeesView()}catch(e){toast(e.message,true)}};
}
async function downloadEmployeePdf(employeeId){
  const period=$('#hrPdfMonth')?.value||localDate().slice(0,7);
  const [year,month]=period.split('-').map(Number);
  if(!year||!month)return toast('Zvoľ mesiac výkazu',true);
  try{
    const response=await fetch('/api/reports/monthly/'+employeeId+'/pdf?year='+year+'&month='+month,{headers:{Authorization:'Bearer '+token},cache:'no-store'});
    if(!response.ok){
      const err=await response.json().catch(()=>({detail:'PDF export zlyhal'}));
      throw new Error(typeof err.detail==='string'?err.detail:'PDF export zlyhal');
    }
    const blob=await response.blob();
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;link.download='dochadzka_'+employeeId+'_'+year+'_'+String(month).padStart(2,'0')+'.pdf';
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),2000);
    toast('PDF výkaz bol pripravený');
  }catch(error){toast(error.message,true)}
}
function closeHrModal(){const modal=$('#hrModalHost');if(modal)modal.innerHTML=''}
function openHrEditor(id){
 const p=id?hrRows.find(e=>e.id===id):null;
 if(id&&!p)return toast('Zamestnanec neexistuje',true);
 const val=(field,defaultValue='')=>esc(p?.[field]??defaultValue);
 const f=(label,name,value,extra='')=>'<label class="field"><span>'+label+'</span><input name="'+name+'" value="'+esc(value??'')+'" '+extra+'></label>';
 const templateOptions='<option value="">Bez šablóny</option>'+hrTemplates.map(t=>hrOption(t.id,t.name,p?.shift_template_id??'')).join('');
 const managers='<option value="">Podľa organizačnej štruktúry</option>'+hrRows.filter(x=>x.id!==id).map(x=>hrOption(x.id,x.name,p?.manager_id??'')).join('');
 const regimes=[['fixed','Pevný'],['flexible','Pružný'],['rotating','Zmenový'],['part_time','Skrátený úväzok'],['individual','Individuálny'],['dispatcher','Dispečer 11 h + 1 h prestávka'],['agreement_activity','Dohoda o pracovnej činnosti (max. 10 h/týž.)'],['agreement_student','Brigádnická práca študentov'],['agreement_seasonal','Sezónna dohoda (priemer max. 40 h/týž.)'],['agreement_task','Dohoda o vykonaní práce (350 h/rok)']].map(([v,n])=>hrOption(v,n,p?.work_regime??'fixed')).join('');
 const full=(p?.name||'Nový zamestnanec');
 $('#hrModalHost').innerHTML='<div class="hr-backdrop"><div class="hr-dialog" role="dialog" aria-modal="true" aria-labelledby="hrTitle"><header class="hr-dialog-head"><div class="hr-avatar">♙</div><div><h3 id="hrTitle">'+esc(full)+'</h3><p class="muted">'+(p?'Upraviť údaje zamestnanca':'Založiť nového zamestnanca')+'</p></div><button class="secondary" id="hrClose" type="button" aria-label="Zavrieť">✕</button></header><form id="hrForm"><div class="hr-dialog-body"><h4>♙ Osobné údaje</h4><div class="form-grid">'+
 f('Osobné číslo *','personal_number',p?.personal_number||'', 'required maxlength="32"')+f('Titul','title',p?.title||'')+
 f('Meno *','first_name',p?.first_name||'','required')+f('Priezvisko *','last_name',p?.last_name||'','required')+
 f('E-mail','email',p?.email||'','type="email"')+f('Telefón','phone',p?.phone||'')+
 '</div><h4>▣ Zaradenie a pracovný čas</h4><div class="form-grid">'+
 f('Útvar','department',p?.department||'')+f('Funkcia','job_title',p?.job_title||'')+
 '<label class="field"><span>Priamy nadriadený</span><select name="manager_id">'+managers+'</select></label>'+
 '<label class="field"><span>Pracovný režim</span><select name="work_regime">'+regimes+'</select></label>'+
 f('Úväzok (1 = plný; 0,5 = polovičný)','fte',p?.fte??1,'type="number" step="0.05" min="0.05" max="1" required')+
 f('Týždenný fond (minúty) *','weekly_minutes',p?.weekly_minutes??2400,'type="number" min="60" max="3600" required')+
 f('Nástup *','start_date',hrDate(p?.start_date)||localDate(),'type="date" required')+
 f('Ukončenie','end_date',hrDate(p?.end_date),'type="date"')+
 f('Dovolenka – ročný nárok (dni)','annual_leave_days',p?.annual_leave_days??25,'type="number" step="0.5" min="0" max="100"')+
 f('Prenesená dovolenka (dni)','carryover_days',p?.carryover_days??0,'type="number" step="0.5" min="0" max="100"')+
 f('Pracovných dní týždenne','work_days',p?.work_days??5,'type="number" min="1" max="7"')+
 f('RFID UID karty','card_uid',p?.card_uid||'')+
 '</div><div class="hr-shift-section"><h4>◷ Výber zmeny</h4><div class="form-grid"><label class="field"><span>Šablóna zmeny</span><select name="shift_template_id" id="hrShiftSelect">'+templateOptions+'</select></label><div id="hrShiftPreview" class="hr-shift-preview"></div></div><p class="subtle">Výber šablóny uloží predvolený režim. Nenahrádza rozpis jednotlivých dní.</p></div><label class="hr-active"><input type="checkbox" name="active" '+(p&&!p.active?'':'checked')+'> Aktívny zamestnanec</label></div><footer class="hr-dialog-footer">'+(p?'<button type="button" id="hrResetPassword" class="secondary">Resetovať heslo</button><button type="button" id="hrGoTimesheet" class="secondary">Dochádzka</button>':'')+'<button type="button" id="hrCancel" class="secondary">Zrušiť</button><button type="submit" class="primary">✓ Uložiť</button></footer></form></div></div>';
 const preview=()=>{const t=hrTemplates.find(x=>x.id===Number($('#hrShiftSelect').value));$('#hrShiftPreview').innerHTML=t?'<strong>'+esc(t.name)+'</strong><span>'+esc(t.start)+'–'+esc(t.end)+' · prestávka '+t.break_minutes+' min</span><span>'+esc(t.description)+'</span>':'<span>Vyber predvolenú pracovnú zmenu.</span>'};
 $('#hrShiftSelect').onchange=preview;preview();
 $('#hrClose').onclick=closeHrModal;$('#hrCancel').onclick=closeHrModal;
 if(p){
 $('#hrGoTimesheet').onclick=()=>{closeHrModal();navigate('reports')};
 $('#hrResetPassword').onclick=async()=>{
  if(!confirm('Resetovať heslo zamestnanca '+p.name+'? Staré heslo prestane platiť.'))return;
  try{
   const result=await api('/api/auth/employees/'+p.id+'/reset-password',{method:'POST'});
   prompt('Jednorazové dočasné heslo pre '+result.username+'. Skopíruj ho a odovzdaj bezpečným kanálom; pri prihlásení je povinná zmena hesla.',result.temporary_password);
   toast('Dočasné heslo bolo vytvorené');
  }catch(error){toast(error.message,true)}
 };
}
 $('#hrForm').onsubmit=async ev=>{
  ev.preventDefault();const d=Object.fromEntries(new FormData(ev.target));
  for(const key of ['weekly_minutes','work_days'])d[key]=Number(d[key]);
  for(const key of ['fte','annual_leave_days','carryover_days'])d[key]=Number(d[key]);
  d.active=!!ev.target.querySelector('[name="active"]').checked;
  d.manager_id=d.manager_id?Number(d.manager_id):null;
  d.shift_template_id=d.shift_template_id?Number(d.shift_template_id):null;
  d.end_date=d.end_date||null;
  d.card_uid=d.card_uid.trim()||null;
  try{
    await api(p?'/api/hr/employees/'+p.id:'/api/hr/employees',{method:p?'PUT':'POST',body:JSON.stringify(d)});
    toast(p?'Zamestnanec aktualizovaný':'Zamestnanec vytvorený');closeHrModal();await refreshEmployees();await employeesView()
  }catch(error){toast(error.message,true)}
 };
}
function openHrTemplateEditor(){
 $('#hrModalHost').innerHTML='<div class="hr-backdrop"><div class="hr-dialog hr-dialog-small" role="dialog" aria-modal="true"><header class="hr-dialog-head"><h3>Nová šablóna zmeny</h3><button class="secondary" id="hrTemplateClose">✕</button></header><form id="hrTemplateForm"><div class="hr-dialog-body"><label class="field"><span>Názov zmeny</span><input name="name" required placeholder="Napríklad Ranná 07:00–15:00"></label><div class="form-grid"><label class="field"><span>Začiatok</span><input type="time" name="start" value="07:00" required></label><label class="field"><span>Koniec</span><input type="time" name="end" value="15:00" required></label><label class="field"><span>Prestávka (min)</span><input type="number" name="break_minutes" value="30" min="0" max="240"></label><label class="field"><span>Pracovné dni / týždeň</span><input type="number" name="work_days" value="5" min="1" max="7"></label></div><label class="field"><span>Popis</span><input name="description" maxlength="250"></label></div><footer class="hr-dialog-footer"><button class="secondary" id="hrTemplateCancel" type="button">Zrušiť</button><button class="primary" type="submit">Uložiť šablónu</button></footer></form></div></div>';
 $('#hrTemplateClose').onclick=closeHrModal;$('#hrTemplateCancel').onclick=closeHrModal;
 $('#hrTemplateForm').onsubmit=async ev=>{ev.preventDefault();const data=Object.fromEntries(new FormData(ev.target));data.break_minutes=Number(data.break_minutes);data.work_days=Number(data.work_days);try{await api('/api/hr/shift-templates',{method:'POST',body:JSON.stringify(data)});toast('Šablóna vytvorená');closeHrModal();employeesView()}catch(e){toast(e.message,true)}};
}
async function requests(){if(currentUser?.role==='employee')return employeeRequests();if(currentUser?.role==='manager')return managerRequests();if(currentUser?.role==='auditor')return auditorDashboard();const list=await api('/api/absences');$('#content').innerHTML='<div class="grid2"><div class="panel"><h3>Nová neprítomnosť</h3><form id="absenceForm"><label class="field"><span>Zamestnanec</span>'+choose()+'</label><label class="field"><span>Druh neprítomnosti</span><select name="kind">'+[['vacation','Dovolenka'],['doctor','Lekár'],['accompany','Sprevádzanie'],['doctor_unpaid','Lekár – neplatené'],['accompany_unpaid','Sprevádzanie – neplatené'],['sick','PN'],['ocr','OČR'],['paid_leave','Platené voľno'],['unpaid','Neplatené voľno'],['business_trip','Služobná cesta'],['home_office','Home office – práca na diaľku'],['training','Školenie'],['wedding','Svadba'],['funeral','Pohreb'],['blood_donation','Darovanie krvi'],['maternity','Materská'],['paternity','Otcovská'],['parental','Rodičovská']].map(([v,n])=>'<option value="'+v+'">'+n+'</option>').join('')+'</select></label><div class="form-grid"><label class="field"><span>Od</span><input name="start" type="date" value="'+localDate()+'" required></label><label class="field"><span>Do</span><input name="end" type="date" value="'+localDate()+'" required></label></div><label class="field"><span>Počet minút (iba pri čiastočnom dni)</span><input type="number" name="minutes" min="1" placeholder="napr. 120"></label><label class="field"><span>Poznámka</span><input name="note" maxlength="400"></label><button class="primary">Odoslať žiadosť</button></form></div><div class="panel"><h3>Schvaľovanie a história</h3><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Typ</th><th>Dátum</th><th>Stav</th><th>Akcia</th></tr></thead><tbody>'+list.map(a=>'<tr><td>'+esc(employees.find(e=>e.id===a.employee_id)?.name||a.employee_id)+'</td><td>'+esc(a.kind)+'</td><td>'+a.start+' – '+a.end+'</td><td><span class="pill '+a.status+'">'+a.status+'</span></td><td>'+ (a.status==='pending'?'<div class="actions"><button class="secondary mini" data-approve="'+a.id+'">✓</button><button class="secondary mini danger" data-reject="'+a.id+'">✕</button></div>':'—')+'</td></tr>').join('')+'</tbody></table></div></div></div>';$('#absenceForm').onsubmit=async e=>{e.preventDefault();const p=Object.fromEntries(new FormData(e.target));p.employee_id=Number($('#empSelect').value);p.minutes=p.minutes?Number(p.minutes):null;try{await api('/api/absences',{method:'POST',body:JSON.stringify(p)});toast('Žiadosť bola založená');requests()}catch(e){toast(e.message,true)}};document.querySelectorAll('[data-approve],[data-reject]').forEach(x=>x.onclick=async()=>{try{await api('/api/absences/'+(x.dataset.approve||x.dataset.reject)+'/'+(x.dataset.approve?'approve':'reject'),{method:'POST'});toast('Stav žiadosti zmenený');requests()}catch(e){toast(e.message,true)}})}
async function shifts(){
const start=monthStart(),end=localDate(new Date(new Date().getFullYear(),new Date().getMonth()+1,0));
const [list,shiftPresets]=await Promise.all([api('/api/shifts?start='+start+'&end='+end),api('/api/shift-presets')]);
$('#content').innerHTML='<div class="grid2"><div class="panel"><h3>Naplánovať zmenu</h3><form id="shiftForm"><label class="field"><span>Prednastavená zmena</span><select name="preset" id="shiftPreset"><option value="">Ručne nastaviť</option>'+Object.entries(shiftPresets).map(([id,p])=>'<option value="'+id+'">'+esc(p.label)+'</option>').join('')+'</select></label><label class="field"><span>Zamestnanec</span>'+choose()+'</label><label class="field"><span>Deň zmeny</span><input type="date" name="day" value="'+localDate()+'" required></label><div class="form-grid"><label class="field"><span>Začiatok</span><input name="start_time" type="time" value="08:00"></label><label class="field"><span>Koniec</span><input name="end_time" type="time" value="16:30"></label><label class="field"><span>Plánované minúty</span><input name="planned_minutes" type="number" value="480" min="0" max="1440"></label><label class="field"><span>Poznámka</span><input name="note" maxlength="200"></label></div><button class="primary">Uložiť zmenu</button></form></div><div class="panel"><h3>Zmeny tento mesiac</h3><div class="scroll"><table><thead><tr><th>Deň</th><th>Zamestnanec</th><th>Čas</th><th>Plán</th></tr></thead><tbody>'+list.map(x=>'<tr><td>'+x.day+'</td><td>'+esc(employees.find(e=>e.id===x.employee_id)?.name||x.employee_id)+'</td><td>'+esc(x.start_time)+' – '+esc(x.end_time)+'</td><td>'+fmt(x.planned_minutes)+'</td></tr>').join('')+'</tbody></table></div></div></div><div class="panel"><h3>Generovanie cyklu dispečingu 24/7</h3><p class="intro">Vyber zamestnanca a obdobie. Cyklus D–N–V–V znamená denná, nočná, voľno, voľno. Počty minút musia zodpovedať internému rozvrhu a schváleným prestávkam.</p><form id="cycleForm"><div class="form-grid"><label class="field"><span>Zamestnanec</span>'+choose('cycleEmployee')+'</label><label class="field"><span>Cyklus</span><select name="cycle"><option value="D-N-V-V">D – N – V – V</option><option value="R-P-V-V">Polzmena R – P – V – V</option><option value="H-V-H-V">Polzmena – voľno</option><option value="D-D-N-N-V-V-V-V">D – D – N – N – V – V – V – V</option></select></label><label class="field"><span>Od</span><input type="date" name="start" value="'+start+'" required></label><label class="field"><span>Do</span><input type="date" name="end" value="'+end+'" required></label><label class="field"><span>Posun cyklu (dni)</span><input type="number" name="offset" min="0" max="365" value="0"></label><label class="field"><span>Plánované minúty za dennú/nočnú (orientačne)</span><input type="number" name="day_minutes" min="0" max="1440" value="660"></label><label class="field"><span>Plánované minúty nočnej</span><input type="number" name="night_minutes" min="0" max="1440" value="660"></label></div><label class="hr-active"><input type="checkbox" name="overwrite"> Prepísať už naplánované zmeny (bez potvrdenia nie)</label><p><button class="primary" type="submit">Vygenerovať zmeny</button></p></form></div><div class="notice">TPP: 8 h čistý fond + 30 min prestávka (typicky 8:00–16:30). Dispečer: 11 h práce + 60 min prestávka (06:00–18:00 alebo 18:00–06:00). Prestávku pípaj, ak ju reálne čerpáš; ak chýba, bude v kontrolnom výkaze odpočítaná automaticky. Polzmena 6 h nemá automatický odpočet. Rozpis a zákonné odpočinky musí potvrdiť HR.</div>';
if(currentUser?.role!=='scheduler'){
 const premiumPanel=document.createElement('div');
 premiumPanel.className='panel';
 premiumPanel.innerHTML='<div class="section-top"><div><h3>Zákonné príplatky – kontrolný výpočet 2026</h3><span class="muted">Nočná, sobota, nedeľa, sviatok · hrubé zákonné minimá bez interných výnimiek</span></div></div><div class="form-grid"><label class="field"><span>Zamestnanec</span>'+choose('premiumEmployee')+'</label><label class="field"><span>Mesiac</span><input type="month" id="premiumMonth" value="'+monthStart().slice(0,7)+'"></label><label class="field"><span>Priemerný hodinový zárobok (€), potrebný pre sviatok</span><input id="premiumAverage" type="number" step="0.01" min="0" placeholder="napr. 15,00"></label><label class="field"><span>Nočná riziková práca</span><select id="premiumRisk"><option value="false">Nie</option><option value="true">Áno – vyšší zákonný koeficient</option></select></label></div><button id="premiumCalculate" class="primary">Vypočítať príplatky</button><div id="premiumResult"></div><p class="subtle">Tento výpočet sám osebe nevytvára mzdové nároky. Pri nerovnomerných zmenách a sviatkoch treba preveriť pravidlá § 122 až 123, KZ a náhradné voľno.</p>';
 $('#content').append(premiumPanel);
 $('#premiumCalculate').onclick=async()=>{const id=Number($('#premiumEmployee').value),[year,month]=$('#premiumMonth').value.split('-').map(Number),avg=$('#premiumAverage').value;const params=new URLSearchParams({year:String(year),month:String(month),risk_night:$('#premiumRisk').value});if(avg)params.set('average_hourly',avg);try{const d=await api('/api/premiums/'+id+'?'+params);const a=d.amounts;$('#premiumResult').innerHTML='<div class="travel-kpis">'+[['Nočné',d.night_min,a.night_eur],['Sobota',d.saturday_min,a.saturday_eur],['Nedeľa',d.sunday_min,a.sunday_eur],['Sviatok',d.holiday_min,a.holiday_eur]].map(([label,mins,eur])=>'<div class="gr-stat"><span>'+label+'</span><strong>'+(eur===null?'Doplň priemer':Number(eur).toFixed(2)+' €')+'</strong><small>'+fmt(mins)+' práce</small></div>').join('')+'</div><div class="notice">'+d.warnings.map(x=>esc(x)).join(' · ')+'</div>'}catch(e){toast(e.message,true)}};
}
$('#shiftPreset').onchange=()=>{
 const preset=shiftPresets[$('#shiftPreset').value];
 if(!preset)return;
 const form=$('#shiftForm');
 form.querySelector('[name="start_time"]').value=preset.start_time;
 form.querySelector('[name="end_time"]').value=preset.end_time;
 form.querySelector('[name="planned_minutes"]').value=preset.planned_minutes;
};
$('#shiftForm').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.employee_id=Number($('#empSelect').value);p.planned_minutes=Number(p.planned_minutes);if(!p.preset)delete p.preset;try{await api('/api/shifts',{method:'POST',body:JSON.stringify(p)});toast('Zmena uložená');shifts()}catch(e){toast(e.message,true)}};
$('#cycleForm').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.employee_id=Number($('#cycleEmployee').value);p.offset=Number(p.offset);p.day_minutes=Number(p.day_minutes);p.night_minutes=Number(p.night_minutes);p.overwrite=ev.target.querySelector('[name="overwrite"]').checked;if(p.overwrite&&!confirm('Prepísať existujúce zmeny v období?'))return;try{const result=await api('/api/shifts/generate-cycle',{method:'POST',body:JSON.stringify(p)});toast('Vygenerované zmeny: '+result.created_or_updated);shifts()}catch(e){toast(e.message,true)}};
}
async function reports(){$('#content').innerHTML='<div class="panel"><h3>Výkazy a zostatky</h3><div class="toolbar"><label class="field"><span>Zamestnanec</span>'+choose()+'</label><label class="field"><span>Od</span><input id="reportFrom" type="date" value="'+monthStart()+'"></label><label class="field"><span>Do</span><input id="reportTo" type="date" value="'+localDate()+'"></label><button class="primary" id="loadReport">Zobraziť</button></div><div id="reportResult" class="muted">Vyber zamestnanca a obdobie.</div></div>';$('#loadReport').onclick=async()=>{try{const id=$('#empSelect').value,start=$('#reportFrom').value,end=$('#reportTo').value;const t=await api('/api/timesheet/'+id+'?start='+start+'&end='+end),b=await api('/api/balances/'+id+'/'+new Date(start).getFullYear()),saldo=await api('/api/saldo/'+id+'?start='+start+'&end='+end);$('#reportResult').innerHTML='<div class="notice">Saldo za zvolené obdobie: <strong>'+ (saldo.totals.saldo_minutes<0?'-':'+')+fmt(saldo.totals.saldo_minutes) +'</strong> | plán '+fmt(saldo.totals.planned_minutes)+' | započítané voľno '+fmt(saldo.totals.credited_minutes)+'</div><div class="stats"><div class="stat"><small>Odpracované</small><div class="value">'+fmt(t.total_worked_minutes)+'</div></div><div class="stat"><small>Dovolenka čerpaná</small><div class="value">'+fmt(b.vacation.used_minutes)+'</div></div><div class="stat"><small>Lekár čerpaný</small><div class="value">'+fmt(b.doctor.used_minutes)+'</div></div><div class="stat"><small>Sprevádzanie čerpané</small><div class="value">'+fmt(b.accompany.used_minutes)+'</div></div></div><div class="scroll"><table><thead><tr><th>Príchod</th><th>Odchod</th><th>Hrubý čas</th><th>Prestávka</th><th>Odpracované</th></tr></thead><tbody>'+t.pairs.map(x=>'<tr><td>'+esc(x.in)+'</td><td>'+esc(x.out)+'</td><td>'+fmt(x.gross_minutes)+'</td><td>'+fmt(x.break_minutes)+'</td><td>'+fmt(x.net_minutes)+'</td></tr>').join('')+'</tbody></table></div><p class="muted">'+t.warnings.map(esc).join(' · ')+'</p><p class="subtle">Referenčný ročný nárok na dovolenku: '+fmt(b.vacation.illustrative_full_year_minutes)+' – vyžaduje potvrdenie HR.</p>'}catch(e){toast(e.message,true)}}}
async function terminal(){
 const devices=await api('/api/devices');
 const items=devices.map(d=>'<tr><td>'+esc(d.name)+'</td><td>'+esc(d.location||'—')+'</td><td>'+esc(d.active?'Aktívny':'Deaktivovaný')+'</td><td>'+esc(d.last_seen?String(d.last_seen).slice(0,19):'—')+'</td><td>'+(d.active?'<button class="secondary mini" data-rotate-device="'+d.id+'">Nový kľúč</button> <button class="secondary mini" data-disable-device="'+d.id+'">Deaktivovať</button>':'—')+'</td></tr>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>RFID terminály BID</h3><span class="muted">Tablet alebo Raspberry Pi · vlastný bezpečnostný kľúč pre každé zariadenie</span></div><button class="primary" id="openKiosk">Otvoriť pípačku</button></div><div class="notice">Terminál používa HTTPS, idempotentné záznamy, vlastný kľúč a šifrovanú offline frontu do 72 hodín. Na zariadení treba nastaviť číslo terminálu a jeho tajný kľúč.</div><div class="scroll"><table><thead><tr><th>Terminál</th><th>Umiestnenie</th><th>Stav</th><th>Posledný kontakt</th><th>Akcie</th></tr></thead><tbody>'+items+'</tbody></table></div></div><div class="panel"><h3>Nový terminál</h3><form id="createDevice"><div class="form-grid"><label class="field"><span>Názov zariadenia</span><input name="name" required placeholder="Vstupná hala – tablet"></label><label class="field"><span>Umiestnenie</span><input name="location" placeholder="BID · vchod"></label><label class="field"><span>Voliteľná povolená IP adresa</span><input name="allowed_ip" placeholder="Nechaj prázdne, ak sa IP mení"></label></div><button class="primary" type="submit">Vytvoriť terminál</button></form><p class="subtle">Nový kľúč uvidíš iba raz. Starý kľúč po rotácii prestane fungovať a neodoslaná fronta na zariadení musí byť pred rotáciou synchronizovaná.</p></div>';
 $('#openKiosk').onclick=()=>window.open('/kiosk','_blank','noopener');
 $('#createDevice').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));if(!p.allowed_ip)p.allowed_ip=null;try{const result=await api('/api/devices',{method:'POST',body:JSON.stringify(p)});prompt('ID terminálu: '+result.id+'. Tajný kľúč (zobrazuje sa len raz, odovzdaj bezpečne do kiosku):',result.device_key);toast('Terminál vytvorený');terminal()}catch(e){toast(e.message,true)}};
 document.querySelectorAll('[data-rotate-device]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Rotácia kľúča zneplatní starý kľúč a nevysynchronizované dáta. Pokračovať?'))return;try{const d=await api('/api/devices/'+btn.dataset.rotateDevice+'/rotate',{method:'POST'});prompt('Nový kľúč terminálu '+d.device_id+' (zobrazuje sa len raz):',d.device_key);toast('Kľúč terminálu obnovený');terminal()}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-disable-device]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Deaktivovať terminál?'))return;try{await api('/api/devices/'+btn.dataset.disableDevice+'/disable',{method:'POST'});toast('Terminál deaktivovaný');terminal()}catch(e){toast(e.message,true)}});
}
async function holidaysView(year=new Date().getFullYear()){
const list=await api('/api/calendar/'+year);
$('#content').innerHTML='<div class="panel"><div class="section-top"><h3>Sviatky a pracovné dni SR</h3><div class="toolbar"><input id="holidayYear" type="number" min="2020" max="2040" value="'+year+'"><button id="holidayLoad" class="primary">Zobraziť</button></div></div><div class="notice">Od roku 2026 sa pri vybraných sviatkoch mení režim pracovného pokoja. 8. máj a 15. september sú v roku 2026 bežné pracovné dni; 1. september a 17. november nie sú dňami pracovného pokoja. Pri práci cez víkend sa pracovný deň určuje aj podľa rozvrhu.</div><div class="scroll"><table><thead><tr><th>Dátum</th><th>Názov sviatku</th><th>Režim pre štandardný pracovný týždeň</th></tr></thead><tbody>'+list.map(x=>'<tr><td>'+x.date+'</td><td>'+esc(x.name)+'</td><td><span class="pill '+(x.day_off?'pending':'approved')+'">'+(x.day_off?'Voľno / víkend':'Pracovný deň')+'</span></td></tr>').join('')+'</tbody></table></div></div>';
$('#holidayLoad').onclick=()=>holidaysView(Number($('#holidayYear').value));
}
async function accounts(){
if(currentUser?.must_change_password||['employee','manager','auditor','scheduler'].includes(currentUser?.role))return employeePasswordView();
$('#content').innerHTML='<div class="grid2"><div class="panel"><h3>Zmena môjho hesla</h3><form id="pwForm"><label class="field"><span>Aktuálne heslo</span><input type="password" name="old_password" minlength="8" autocomplete="current-password" required></label><label class="field"><span>Nové heslo</span><input type="password" name="new_password" minlength="12" autocomplete="new-password" required></label><button class="primary">Zmeniť heslo</button></form></div><div class="panel"><h3>Nový používateľský účet</h3><p class="muted">Účty môže vytvoriť administrátor a personalista. Administrátorskú rolu môže prideliť len administrátor.</p><form id="accountForm"><label class="field"><span>Používateľské meno</span><input name="username" minlength="3" required></label><label class="field"><span>Heslo (min. 12 znakov)</span><input name="password" type="password" minlength="12" required></label><label class="field"><span>Rola</span><select name="role"><option value="employee">Zamestnanec</option><option value="manager">Vedúci</option><option value="hr">Personalista</option><option value="auditor">Audítor</option><option value="scheduler">Plánovač zmien (len rozpis)</option><option value="admin">Administrátor</option></select></label><label class="field"><span>Priradený zamestnanec (voliteľné)</span><select name="employee_id"><option value="">Bez priradenia</option>'+employees.map(e=>'<option value="'+e.id+'">'+esc(e.name)+'</option>').join('')+'</select></label><button class="primary">Vytvoriť účet</button></form></div></div>';
$('#pwForm').onsubmit=async ev=>{ev.preventDefault();try{await api('/api/auth/password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(ev.target)))});ev.target.reset();toast('Heslo bolo zmenené');await init()}catch(e){toast(e.message,true)}};
const mfaBlock=document.createElement('div');mfaBlock.className='panel';mfaBlock.innerHTML='<h3>Dvojfaktorové overenie (MFA)</h3><p class="muted">Prihlásenie chránené jednorazovým kódom z autentifikačnej aplikácie. Ak stratíš mobil, potrebuješ bezpečnostný reset účtu.</p><button id="enableMfa" class="secondary">Nastaviť MFA</button><div id="mfaSetupPanel"></div>';
$('#content').append(mfaBlock);
$('#enableMfa').onclick=setupMfa;
$('#accountForm').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));const query=new URLSearchParams({role:p.role});if(p.employee_id)query.set('employee_id',p.employee_id);try{await api('/api/auth/accounts?'+query,{method:'POST',body:JSON.stringify({username:p.username,password:p.password})});ev.target.reset();toast('Používateľský účet vytvorený')}catch(e){toast(e.message,true)}};
}
async function setupMfa(){
  try{
    const old=prompt('Pre aktiváciu MFA zadaj svoje aktuálne heslo:');
    if(!old)return;
    const r=await api('/api/auth/mfa/setup',{method:'POST',body:JSON.stringify({password:old})});
    const box=$('#mfaSetupPanel');
    if(!box)return;
    box.innerHTML='<div class="notice">Do Microsoft Authenticator alebo Google Authenticator zadaj nasledujúci tajný kľúč manuálne. Neukladaj ho na GitHub ani nezdieľaj.</div><label class="field"><span>Tajný kľúč</span><input id="mfaSecret" readonly value="'+esc(r.secret)+'"></label><label class="field"><span>Overovací 6-ciferný kód</span><input id="mfaConfirm" inputmode="numeric" maxlength="8" autocomplete="one-time-code"></label><button class="primary" id="mfaFinish">Potvrdiť a zapnúť MFA</button>';
    $('#mfaFinish').onclick=async()=>{try{await api('/api/auth/mfa/confirm',{method:'POST',body:JSON.stringify({code:$('#mfaConfirm').value.trim()})});box.innerHTML='<p class="notice">Dvojfaktorové overenie je zapnuté. Pri ďalšom prihlásení zadaj heslo aj kód z aplikácie.</p>';toast('MFA aktivované')}catch(e){toast(e.message,true)}};
  }catch(e){toast(e.message,true)}
}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>navigate(b.dataset.view));document.addEventListener('click',e=>{const go=e.target.closest('[data-go]');if(go)navigate(go.dataset.go)});$('#logout').onclick=logout;$('#loginForm').onsubmit=async e=>{e.preventDefault();try{const d=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('#username').value,password:$('#password').value,otp:$('#loginOtp').value.trim()||null})});token=d.access_token;sessionStorage.setItem('attendance_token',token);$('#password').value='';$('#loginOtp').value='';await init()}catch(err){toast(err.message,true)}};init();
// Progressive Web App: native prompt when available; platform instructions otherwise.
// No background attendance, offline punch queue, or personnel API caching.
let installPrompt=null;
const pwaStandalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
function pwaPlatform(){
 const ua=navigator.userAgent||'';
 if(/iPad|iPhone|iPod/.test(ua)||(/Macintosh/.test(ua)&&navigator.maxTouchPoints>1))return 'ios';
 if(/Android/i.test(ua))return 'android';
 if(/Windows/i.test(ua))return 'windows';
 if(/Macintosh|Mac OS X/.test(ua))return 'mac';
 return 'other';
}
function pwaHelp(){
 const kind=pwaPlatform();
 const isSafari=/Safari/i.test(navigator.userAgent)&&!/CriOS|FxiOS|EdgiOS|Chrome|Chromium|Edg/i.test(navigator.userAgent);
 if(kind==='ios')return [
  'Otvor https://sk-dochadzka-preview.onrender.com/ v Safari na iPhone alebo iPade.',
  'V Safari otvor Zdieľať (ikona štvorca so šípkou).',
  'Vyber Pridať na plochu (Add to Home Screen) a potvrď Pridať.',
  'Na domovskej obrazovke sa objaví ikona BID Dochádzka.'];
 if(kind==='android')return [
  'Otvor tento portál v Google Chrome na Androide.',
  'Vpravo hore otvor menu ⋮.',
  'Vyber Inštalovať aplikáciu alebo Pridať na plochu a potvrď.',
  'Ikona BID Dochádzka sa zobrazí na domovskej obrazovke.'];
 if(kind==='windows')return [
  'Otvor tento portál v Microsoft Edge alebo Google Chrome.',
  'Edge: menu ⋯ → Aplikácie → Nainštalovať túto lokalitu ako aplikáciu.',
  'Chrome: menu ⋮ → Uložiť a zdieľať / Prenášať a zdieľať → Inštalovať stránku ako aplikáciu (názvy sa môžu líšiť).',
  'Po inštalácii môžeš ikonu pripnúť na panel úloh, ponuku Štart a podľa ponuky prehliadača vytvoriť odkaz na ploche.'];
 if(kind==='mac')return [
  'Otvor portál v Safari alebo Chrome.',
  'Safari: Súbor → Pridať do Docku (vyžaduje kompatibilný macOS).',
  'Chrome: menu ⋮ → Inštalovať stránku ako aplikáciu.',
  'Aplikáciu potom otvoríš z Docku alebo Launchpadu.'];
 return ['Otvor aplikáciu v prehliadači s podporou PWA.','V menu vyhľadaj Inštalovať alebo Pridať na domovskú obrazovku.'];
}
function openPwaInstallDialog(){
 const modal=$('#pwaInstallModal');
 if(!modal)return;
 const list=$('#pwaInstallSteps');
 list.innerHTML=pwaHelp().map(step=>'<li>'+esc(step)+'</li>').join('');
 const native=$('#pwaNativeInstall');
 native.classList.toggle('hidden',!installPrompt||pwaStandalone());
 $('#pwaInstallMessage').textContent=pwaStandalone()?
  'BID Dochádzka už beží ako nainštalovaná webová aplikácia.':
  'Jedným kliknutím alebo podľa nasledujúceho návodu si pridáš ikonu BID Dochádzka na zariadenie.';
 modal.classList.remove('hidden');
}
function closePwaInstallDialog(){$('#pwaInstallModal')?.classList.add('hidden')}
window.addEventListener('beforeinstallprompt',event=>{
 event.preventDefault();
 installPrompt=event;
 // The install button stays visible even when the browser does not fire the event.
});
document.querySelectorAll('[data-install-app]').forEach(button=>button.addEventListener('click',openPwaInstallDialog));
$('#pwaInstallClose')?.addEventListener('click',closePwaInstallDialog);
$('#pwaInstallDone')?.addEventListener('click',closePwaInstallDialog);
$('#pwaInstallModal')?.addEventListener('click',event=>{if(event.target.id==='pwaInstallModal')closePwaInstallDialog()});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closePwaInstallDialog()});
$('#pwaNativeInstall')?.addEventListener('click',async()=>{
 if(!installPrompt)return;
 try{
  const promptEvent=installPrompt;
  installPrompt=null;
  await promptEvent.prompt();
  const choice=await promptEvent.userChoice;
  if(choice.outcome==='accepted'){closePwaInstallDialog();toast('Inštalácia aplikácie bola potvrdená')}
  else {toast('Inštaláciu si môžeš spustiť aj neskôr');openPwaInstallDialog()}
 }catch(error){toast('Použi inštalačný postup v návode pre prehliadač',true);openPwaInstallDialog()}
});
window.addEventListener('appinstalled',()=>{installPrompt=null;closePwaInstallDialog();toast('BID Dochádzka bola nainštalovaná')});
if('serviceWorker' in navigator){
 window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(error=>console.warn('PWA service worker:',error)));
}

async function updateStorageWarning(){
  try{
    const response=await fetch('/health',{cache:'no-store'});
    const status=await response.json();
    const banner=$('#demoBanner');
    if(banner){
      banner.classList.toggle('hidden',!status.demo_mode);
      banner.textContent=status.demo_mode?'UKÁŽKOVÉ ÚDAJE · '+(status.demo_employees||0)+' fiktívnych zamestnancov · žiadne reálne osobné údaje':'';
    }
    const el=$('#storageWarning');
    if(!el)return;
    el.classList.toggle('hidden',!!status.persistent);
    el.textContent=status.persistent?'':'UPOZORNENIE: Údaje sú v dočasnom úložisku a pri reštarte sa môžu stratiť. Nepoužívaj produkčné osobné údaje. V administrácii si môžeš stiahnuť šifrovanú zálohu.';
  }catch{const el=$('#storageWarning');if(el){el.classList.remove('hidden');el.textContent='Úložisko sa nepodarilo overiť.'}}
}


async function organizationView(){
 const [units,people,memberships]=await Promise.all([api('/api/org/units'),api('/api/hr/employees'),api('/api/org/memberships')]);
 const options='<option value="">Bez nadriadeného útvaru</option>'+units.map(u=>'<option value="'+u.id+'">'+esc('· '.repeat(u.depth)+u.name)+'</option>').join('');
 const empOptions='<option value="">Nepriradený</option>'+people.map(p=>'<option value="'+p.id+'">'+esc(p.name)+'</option>').join('');
 const tableRows=units.map(u=>'<tr><td><span style="padding-left:'+Math.min(140,12*u.depth)+'px">'+esc(u.name)+'</span></td><td>'+esc(u.kind)+'</td><td>'+esc(u.cost_center||'—')+'</td><td>'+esc(people.find(p=>p.id===u.manager_id)?.name||'—')+'</td><td>'+u.employee_count+'</td><td><button class="secondary mini" data-unit-edit="'+u.id+'">Upraviť</button> <button class="secondary mini" data-unit-delete="'+u.id+'">Zmazať</button></td></tr>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Organizačná štruktúra BID</h3><span class="muted">Strom útvarov, vedúci, zástupcovia, nákladové strediská</span></div></div><div class="scroll"><table><thead><tr><th>Útvar</th><th>Typ</th><th>Stredisko</th><th>Vedúci</th><th>Ľudia</th><th>Akcie</th></tr></thead><tbody>'+tableRows+'</tbody></table></div></div><div class="grid2"><div class="panel"><h3 id="orgFormTitle">Nový útvar</h3><form id="orgForm"><input type="hidden" name="unit_id"><label class="field"><span>Názov útvaru</span><input name="name" required></label><div class="form-grid"><label class="field"><span>Typ</span><select name="kind"><option>spoločnosť</option><option>úsek</option><option>odbor</option><option selected>oddelenie</option><option>dispečing</option><option>tím</option></select></label><label class="field"><span>Nákladové stredisko</span><input name="cost_center"></label><label class="field"><span>Nadriadený útvar</span><select name="parent_id">'+options+'</select></label><label class="field"><span>Skratka</span><input name="short"></label><label class="field"><span>Vedúci</span><select name="manager_id">'+empOptions+'</select></label><label class="field"><span>Zástupca</span><select name="deputy_id">'+empOptions+'</select></label></div><button class="primary">Uložiť útvar</button></form></div><div class="panel"><h3>Zaradenie zamestnanca</h3><form id="orgMembership"><label class="field"><span>Zamestnanec</span><select name="employee_id">'+people.map(p=>'<option value="'+p.id+'">'+esc(p.name)+'</option>').join('')+'</select></label><label class="field"><span>Útvar</span><select name="unit_id">'+options+'</select></label><button class="primary">Uložiť zaradenie</button></form><p class="subtle">Nadriadení majú prístup k podriadeným v rámci svojho organizačného podstromu. Priama výnimka z profilu zamestnanca zostáva zachovaná.</p><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Útvar</th></tr></thead><tbody>'+memberships.map(m=>'<tr><td>'+esc(people.find(p=>p.id===m.employee_id)?.name||m.employee_id)+'</td><td>'+esc(units.find(u=>u.id===m.unit_id)?.name||m.unit_id)+'</td></tr>').join('')+'</tbody></table></div></div></div>';
 const form=$('#orgForm');
 form.onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(form));const id=p.unit_id;delete p.unit_id;for(const key of ['parent_id','manager_id','deputy_id'])p[key]=p[key]?Number(p[key]):null;p.active=true;try{await api(id?'/api/org/units/'+id:'/api/org/units',{method:id?'PUT':'POST',body:JSON.stringify(p)});toast('Útvar bol uložený');organizationView()}catch(e){toast(e.message,true)}};
 $('#orgMembership').onsubmit=async ev=>{ev.preventDefault();const d=Object.fromEntries(new FormData(ev.target));d.employee_id=Number(d.employee_id);d.unit_id=d.unit_id?Number(d.unit_id):null;try{await api('/api/org/memberships',{method:'PUT',body:JSON.stringify(d)});toast('Zaradenie aktualizované');organizationView()}catch(e){toast(e.message,true)}};
 document.querySelectorAll('[data-unit-edit]').forEach(btn=>btn.onclick=()=>{const u=units.find(x=>x.id===Number(btn.dataset.unitEdit));if(!u)return;form.elements.unit_id.value=u.id;for(const field of ['name','kind','short','cost_center','parent_id','manager_id','deputy_id'])form.elements[field].value=u[field]??'';$('#orgFormTitle').textContent='Upraviť: '+u.name;form.scrollIntoView({behavior:'smooth',block:'center'})});
 document.querySelectorAll('[data-unit-delete]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Zmazať tento útvar? Zmazanie je možné len pri prázdnom útvare.'))return;try{await api('/api/org/units/'+btn.dataset.unitDelete,{method:'DELETE'});toast('Útvar zmazaný');organizationView()}catch(e){toast(e.message,true)}});
}
async function exportProfilesView(){
 const profiles=await api('/api/exports/profiles');
 const types={month:['personal_number','full_name','month','fond_min','worked_min','credited_min','saldo_min','night_min','saturday_min','sunday_min','holiday_min','vacation_min','doctor_min','accompany_min','ocr_calendar_days','warnings'],day:['personal_number','full_name','day','first_in','last_out','planned_min','worked_min','credited_min','saldo_min','absence','warnings'],absence:['personal_number','full_name','kind','start','end','minutes','status','month']};
 const period=localDate().slice(0,7);
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Exportné profily mzdového systému</h3><p class="muted">Formát, kódovanie, stĺpce a úroveň záznamov podľa importu mzdového programu.</p></div><label class="field"><span>Obdobie</span><input id="exportsPeriod" type="month" value="'+period+'"></label></div><div class="scroll"><table><thead><tr><th>Profil</th><th>Formát</th><th>Úroveň</th><th>Kódovanie</th><th>Stĺpce</th><th></th></tr></thead><tbody>'+profiles.map(p=>'<tr><td><strong>'+esc(p.name)+'</strong></td><td>'+esc(p.format.toUpperCase())+'</td><td>'+esc(p.level)+'</td><td>'+esc(p.encoding)+'</td><td>'+p.columns.length+'</td><td><button class="primary mini" data-download-profile="'+p.id+'">Stiahnuť</button></td></tr>').join('')+'</tbody></table></div></div><div class="panel"><h3>Vytvoriť vlastný exportný profil</h3><form id="newExportProfile"><div class="form-grid"><label class="field"><span>Názov</span><input name="name" required maxlength="140"></label><label class="field"><span>Formát</span><select name="file_format"><option value="csv">CSV</option><option value="xlsx">Excel XLSX</option><option value="json">JSON</option><option value="xml">XML</option></select></label><label class="field"><span>Úroveň</span><select name="level"><option value="month">Mesačný súhrn</option><option value="day">Denné riadky</option><option value="absence">Neprítomnosti</option></select></label><label class="field"><span>Kódovanie CSV</span><select name="encoding"><option value="utf-8">UTF-8</option><option value="cp1250">Windows-1250</option></select></label><label class="field"><span>Oddeľovač CSV</span><select name="delimiter"><option value=";">Bodkočiarka</option><option value=",">Čiarka</option><option value="&#9;">Tabulátor</option></select></label></div><label class="field"><span>Stĺpce, oddelené čiarkou</span><textarea name="columns" rows="3" required>'+types.month.join(',')+'</textarea></label><p class="muted" id="exportAvailable"></p><button class="primary">Uložiť profil</button></form><p class="subtle">Príplatky, nadčas a skutočný nárok na mzdu sa nezaraďujú automaticky. Exporty sú kontrolné podklady pre mzdy.</p></div>';
 const show=()=>{$('#exportAvailable').textContent='Dostupné stĺpce: '+types[$('#newExportProfile').elements.level.value].join(', ')};
 $('#newExportProfile').elements.level.onchange=()=>{$('#newExportProfile').elements.columns.value=types[$('#newExportProfile').elements.level.value].join(',');show()};show();
 document.querySelectorAll('[data-download-profile]').forEach(btn=>btn.onclick=async()=>{const p=profiles.find(x=>x.id===Number(btn.dataset.downloadProfile));const [year,month]=($('#exportsPeriod').value||period).split('-').map(Number);try{await fetchProtectedFile('/api/exports/download/'+p.id+'?year='+year+'&month='+month,'bid-export-'+year+'-'+month+'.'+p.format);toast('Export pripravený')}catch(e){toast(e.message,true)}});
 $('#newExportProfile').onsubmit=async ev=>{ev.preventDefault();const data=Object.fromEntries(new FormData(ev.target));data.columns=data.columns.split(',').map(x=>x.trim()).filter(Boolean);try{await api('/api/exports/profiles',{method:'POST',body:JSON.stringify(data)});toast('Profil vytvorený');exportProfilesView()}catch(e){toast(e.message,true)}};
}
async function legalView(){
 const people=await api('/api/hr/employees');
 const year=new Date().getFullYear();
 const opts=people.map(e=>'<option value="'+e.id+'">'+esc(e.name)+'</option>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Zákonné nároky a limity</h3><p class="muted">§ 141 Zákonníka práce · oddelený sviatok, deň pokoja a príplatok</p></div><div class="actions"><select id="legalEmployee">'+opts+'</select><input id="legalYear" type="number" value="'+year+'" min="2020" max="2100"><button class="primary" id="legalLoad">Zobraziť</button></div></div><div id="legalInfo"></div></div>';
 const load=async()=>{const id=Number($('#legalEmployee').value),y=Number($('#legalYear').value);if(!id)return;try{const [detail,calendar]=await Promise.all([api('/api/legal/employees/'+id+'/'+y),api('/api/legal/calendar/'+y)]);const doctor=detail.doctor,acc=detail.accompany;$('#legalInfo').innerHTML='<div class="stats"><div class="stat"><strong>Lekár</strong><div class="value">'+fmt(doctor.used.minutes)+'</div><small>Limit: '+doctor.limit_days+' dní, zostatok orientačne '+fmt(doctor.remaining_reference_minutes)+'</small></div><div class="stat"><strong>Sprevádzanie</strong><div class="value">'+fmt(acc.used.minutes)+'</div><small>Limit: '+acc.limit_days+' dní, ďalšie HR schválené '+acc.additional_days_approved_by_hr+' dní</small></div></div><div class="notice">'+esc(detail.warning)+'</div><div class="actions"><button id="extra7" class="secondary">Priznať zákonných ďalších 7 dní (po preverení HR)</button><button id="extra0" class="secondary">Zrušiť osobitný nárok</button></div><h3>Kalendár sviatkov a mzdových zvýhodnení</h3><div class="scroll"><table><thead><tr><th>Dátum</th><th>Názov</th><th>Deň pracovného pokoja</th><th>Sviatok na mzdové účely</th></tr></thead><tbody>'+calendar.holidays.map(h=>'<tr><td>'+esc(h.date)+'</td><td>'+esc(h.name)+'</td><td>'+ (h.is_day_off?'Áno':'Nie')+'</td><td>'+ (h.premium_reference?'Áno':'Nie')+'</td></tr>').join('')+'</tbody></table></div>';for(const [button,n] of [['extra7',7],['extra0',0]])$('#'+button).onclick=async()=>{if(n&&!confirm('Potvrdzuješ, že HR overilo všetky zákonné podmienky?'))return;try{await api('/api/legal/employees/'+id+'/escort/'+y,{method:'PUT',body:JSON.stringify({extra_days:n})});toast('Zákonný limit upravený');load()}catch(e){toast(e.message,true)}}}catch(e){$('#legalInfo').innerHTML='<div class="error">'+esc(e.message)+'</div>'}};
 $('#legalLoad').onclick=load;load();
}


async function qualityView(){
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Kontroly pracovného času</h3><span class="muted">Dvojité príchody, chýbajúce odchody, odpočinok, prestávky a týždenné limity</span></div><div class="actions"><input id="qualityMonth" type="month" value="'+localDate().slice(0,7)+'"><button class="primary" id="qualityLoad">Skontrolovať</button></div></div><div id="qualityResult"></div></div>';
 const load=async()=>{const [year,month]=$('#qualityMonth').value.split('-').map(Number);try{const result=await api('/api/quality/monthly?year='+year+'&month='+month);$('#qualityResult').innerHTML='<div class="stats"><div class="stat"><strong>Kontrolné upozornenia</strong><div class="value">'+result.count+'</div><small>Vyžadujú preverenie pred uzávierkou</small></div></div><div class="notice">'+esc(result.disclaimer)+'</div><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Dátum</th><th>Kontrola</th><th>Upozornenie</th></tr></thead><tbody>'+(result.findings.map(x=>'<tr><td>'+esc(x.employee)+'</td><td>'+esc(x.at)+'</td><td>'+esc(x.code)+'</td><td>'+esc(x.message)+'</td></tr>').join('')||'<tr><td colspan="4">V tomto období neboli zistené uvedené typy chýb.</td></tr>')+'</tbody></table></div>'}catch(e){$('#qualityResult').innerHTML='<div class="error">'+esc(e.message)+'</div>'}};
 $('#qualityLoad').onclick=load;load();
}


async function correctionsView(){
 const people=await api('/api/hr/employees'),today=localDate();
 const opts=people.map(p=>'<option value="'+p.id+'">'+esc(p.name)+' ('+esc(p.personal_number)+')</option>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Oprava dochádzkových záznamov</h3><span class="muted">Každá úprava zostane v histórii a vyžaduje povinný dôvod</span></div></div><div class="form-grid"><label class="field"><span>Zamestnanec</span><select id="correctEmployee">'+opts+'</select></label><label class="field"><span>Od</span><input id="correctStart" type="date" value="'+monthStart()+'"></label><label class="field"><span>Do</span><input id="correctEnd" type="date" value="'+today+'"></label><button id="correctLoad" class="secondary">Načítať záznamy</button></div><div class="scroll" id="correctionList"></div></div><div class="panel"><h3>Manuálne doplniť chýbajúci záznam</h3><form id="correctAddForm"><div class="form-grid"><label class="field"><span>Druh</span><select name="kind"><option value="in">Príchod</option><option value="out">Odchod</option><option value="break_start">Začiatok prestávky</option><option value="break_end">Koniec prestávky</option></select></label><label class="field"><span>Čas</span><input name="occurred_at" type="datetime-local" value="'+today+'T08:00" required></label><label class="field"><span>Dôvod (min. 8 znakov)</span><input name="reason" minlength="8" maxlength="400" required placeholder="Zabudnutý čip, overené vedúcim"></label></div><button class="primary">Doplniť záznam s auditom</button></form></div>';
 const load=async()=>{const id=Number($('#correctEmployee').value),start=$('#correctStart').value,end=$('#correctEnd').value;if(!id)return;try{const events=await api('/api/corrections/events?employee_id='+id+'&start='+start+'&end='+end);$('#correctionList').innerHTML='<table><thead><tr><th>Čas</th><th>Typ</th><th>Zdroj</th><th>Akcie</th></tr></thead><tbody>'+events.map(e=>'<tr><td>'+esc(new Date(e.at).toLocaleString('sk-SK'))+'</td><td>'+esc(e.kind)+'</td><td>'+esc(e.origin)+'</td><td>'+(e.kind!=='void'?'<button class="secondary mini" data-punch-edit="'+e.id+'">Upraviť</button> <button class="secondary mini" data-punch-void="'+e.id+'">Zneplatniť</button>':'—')+' <button class="secondary mini" data-punch-history="'+e.id+'">História</button></td></tr>').join('')+'</tbody></table>';
 document.querySelectorAll('[data-punch-void]').forEach(btn=>btn.onclick=async()=>{const reason=prompt('Dôvod zneplatnenia (min. 8 znakov):');if(!reason||reason.length<8)return;try{await api('/api/corrections/'+btn.dataset.punchVoid+'/void',{method:'POST',body:JSON.stringify({reason})});toast('Záznam zneplatnený, audit uložený');load()}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-punch-edit]').forEach(btn=>btn.onclick=async()=>{const record=events.find(e=>e.id===Number(btn.dataset.punchEdit));if(!record)return;const local=new Date(record.at);const pad=n=>String(n).padStart(2,'0');const localValue=local.getFullYear()+'-'+pad(local.getMonth()+1)+'-'+pad(local.getDate())+'T'+pad(local.getHours())+':'+pad(local.getMinutes());const time=prompt('Nový dátum a čas YYYY-MM-DDTHH:MM:',localValue);if(!time)return;const kind=prompt('Typ: in, out, break_start, break_end:',record.kind);if(!['in','out','break_start','break_end'].includes(kind))return toast('Neplatný typ',true);const reason=prompt('Dôvod úpravy (min. 8 znakov):');if(!reason||reason.length<8)return;const d=new Date(time);if(!Number.isFinite(d.getTime()))return toast('Neplatný čas',true);try{await api('/api/corrections/'+record.id,{method:'POST',body:JSON.stringify({kind,occurred_at:d.toISOString(),reason})});toast('Záznam opravený, história zachovaná');load()}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-punch-history]').forEach(btn=>btn.onclick=async()=>{try{const changes=await api('/api/corrections/history/'+btn.dataset.punchHistory);alert(changes.map(x=>x.action+' · '+x.actor+' · '+x.reason+' · '+String(x.at).slice(0,19)).join('\n')||'Záznam zatiaľ nemá históriu opráv')}catch(e){toast(e.message,true)}});
 }catch(e){$('#correctionList').innerHTML='<div class="error">'+esc(e.message)+'</div>'}};
 $('#correctLoad').onclick=load;
 $('#correctAddForm').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.employee_id=Number($('#correctEmployee').value);p.occurred_at=new Date(p.occurred_at).toISOString();try{await api('/api/corrections/manual',{method:'POST',body:JSON.stringify(p)});toast('Chýbajúci záznam doplnený');ev.target.reset();load()}catch(e){toast(e.message,true)}};
 load();
}


async function legalMonitorView(){
 const [status,notices,rules,proposals,history]=await Promise.all([
  api('/api/legal-monitor/status'),
  api('/api/legal-monitor/notices'),
  api('/api/legal-monitor/rules'),
  api('/api/legal-monitor/proposals'),
  api('/api/legal-monitor/history')
 ]);
 const isAdmin=currentUser?.role==='admin';
 const officialLink=url=>(/^https:\/\/(www\.)?(slov-lex\.sk|ip\.gov\.sk)\//i.test(url))
   ?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Otvoriť oficiálny zdroj ↗</a>'
   :'—';
 const sources=status.sources.map(x=>'<tr><td><strong>'+esc(x.title)+'</strong><div class="subtle">'+esc(x.topic)+'</div></td><td>'+(x.error?'<span class="pill rejected">Chyba kontroly</span>':x.baseline_set?'<span class="pill approved">Sledované</span>':'<span class="pill">Čaká na prvú kontrolu</span>')+'</td><td>'+esc(x.checked_at?new Date(x.checked_at).toLocaleString('sk-SK'):'—')+'</td><td>'+officialLink(x.url)+(x.error?'<p class="subtle">'+esc(x.error)+'</p>':'')+'</td></tr>').join('');
 const changes=notices.map(n=>'<article class="legal-notice"><div class="section-top"><div><strong>'+esc(n.title)+'</strong><p class="subtle">Zistené '+esc(new Date(n.detected_at).toLocaleString('sk-SK'))+' · '+esc(n.authority)+'</p></div><span class="pill '+(n.status==='new'?'pending':'approved')+'">'+esc(n.status)+'</span></div><p class="subtle">Zmena obsahu stránky sama osebe nemusí znamenať novelu zákona.</p><pre class="legal-diff">'+esc(n.summary)+'</pre><div class="actions">'+officialLink(n.url)+(n.status==='new'?'<button class="secondary mini" data-notice-review="'+n.id+'">Označiť ako prečítané</button>':'')+(isAdmin?'<button class="secondary mini" data-notice-propose="'+n.id+'">Navrhnúť úpravu pravidla</button>':'')+'</div></article>').join('');
 const proposalRows=proposals.map(p=>'<tr><td>'+p.id+'</td><td>'+esc(rules.find(r=>r.key===p.key)?.label||p.key)+'</td><td>'+p.proposed_value+'</td><td>'+esc(p.effective_date)+'</td><td>'+esc(p.created_by)+'</td><td>'+esc(p.status)+'</td><td>'+(p.status==='pending'&&isAdmin?'<button class="primary mini" data-proposal-approve="'+p.id+'">Potvrdiť</button> <button class="secondary mini" data-proposal-reject="'+p.id+'">Zamietnuť</button>':'—')+'</td></tr>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Monitor zmien zákonov a usmernení</h3><span class="muted">Slov-Lex a Národný inšpektorát práce · informovanie bez automatickej zmeny pravidiel</span></div>'+(isAdmin?'<button class="primary" id="legalCheckNow">Skontrolovať oficiálne stránky</button>':'')+'</div><div class="stats"><div class="stat"><strong>Nové upozornenia</strong><div class="value">'+status.new_notices+'</div><small>Vyžadujú právne posúdenie</small></div><div class="stat"><strong>Zdroje</strong><div class="value">'+status.sources.length+'</div><small>Automatická kontrola pri bežiacom serveri</small></div></div><div class="notice">Zmena webovej stránky ≠ zmena zákona. Systém <strong>nikdy automaticky neupraví</strong> nároky. Najskôr musí administrátor po overení právneho predpisu schváliť presnú hodnotu a dátum účinnosti. Kontrola je na bezplatnom Renderi iba orientačná, pretože server môže spať.</div><div class="scroll"><table><thead><tr><th>Zdroj</th><th>Stav</th><th>Posledná kontrola</th><th>Odkaz</th></tr></thead><tbody>'+sources+'</tbody></table></div></div>'+
 '<div class="panel"><h3>Oznámené zmeny ('+notices.length+')</h3>'+(changes||'<p class="empty">Zatiaľ nebola zistená zmena oproti uloženej východiskovej verzii. Prvá kontrola vytvorí iba východiskový stav.</p>')+'</div>'+
 '<div class="grid2"><div class="panel"><h3>Aktívne referenčné pravidlá</h3><div class="scroll"><table><thead><tr><th>Pravidlo</th><th>Hodnota</th></tr></thead><tbody>'+rules.map(x=>'<tr><td>'+esc(x.label)+'</td><td>'+x.active_value+'</td></tr>').join('')+'</tbody></table></div><p class="subtle">Zmena pravidla sa použije len od schváleného dátumu účinnosti. Samotné mzdové nároky musí ďalej preveriť HR.</p></div>'+
 '<div class="panel"><h3>História schválených hodnôt</h3><div class="scroll"><table><thead><tr><th>Pravidlo</th><th>Od</th><th>Hodnota</th><th>Schválil</th><th>Akcia</th></tr></thead><tbody>'+history.slice(0,20).map(h=>'<tr><td>'+esc(h.key)+'</td><td>'+esc(h.effective_date)+'</td><td>'+h.value+'</td><td>'+esc(h.approved_by)+'</td><td>'+(isAdmin&&history.find(x=>x.key===h.key)?.id===h.id?'<button class="secondary mini" data-legal-rollback="'+h.id+'">Vrátiť</button>':'—')+'</td></tr>').join('')+'</tbody></table></div></div></div>'+
 '<div class="panel"><h3>Návrhy na zmenu zákonných parametrov</h3><div class="scroll"><table><thead><tr><th>ID</th><th>Pravidlo</th><th>Navrhovaná hodnota</th><th>Účinnosť</th><th>Navrhol</th><th>Stav</th><th>Rozhodnutie</th></tr></thead><tbody>'+proposalRows+'</tbody></table></div></div>'+
 (isAdmin?'<div class="panel hidden" id="legalProposalPanel"><h3>Pripraviť návrh – bez automatického použitia</h3><form id="legalProposalForm"><input type="hidden" name="notice_id"><div class="form-grid"><label class="field"><span>Pravidlo</span><select name="rule_key">'+rules.map(x=>'<option value="'+esc(x.key)+'">'+esc(x.label)+'</option>').join('')+'</select></label><label class="field"><span>Nová hodnota (dni, centy alebo tisíciny € podľa označenia)</span><input type="number" name="new_value" min="0" max="100000" required></label><label class="field"><span>Dátum účinnosti podľa predpisu</span><input type="date" name="effective_date" required></label></div><label class="field"><span>Právne zdôvodnenie a presné ustanovenie</span><textarea rows="3" name="rationale" minlength="20" required></textarea></label><button class="primary">Vytvoriť návrh na schválenie</button></form></div>':'');
 if(isAdmin)$('#legalCheckNow').onclick=async()=>{const btn=$('#legalCheckNow');btn.disabled=true;btn.textContent='Kontrolujem zdroje…';try{const result=await api('/api/legal-monitor/check',{method:'POST'});toast('Skontrolované: '+result.checked+' zdrojov, zmeny: '+result.changes+', chyby: '+result.errors.length);legalMonitorView()}catch(e){toast(e.message,true);btn.disabled=false;btn.textContent='Skontrolovať oficiálne stránky'}};
 document.querySelectorAll('[data-notice-review]').forEach(btn=>btn.onclick=async()=>{try{await api('/api/legal-monitor/notices/'+btn.dataset.noticeReview+'/review',{method:'POST'});legalMonitorView()}catch(e){toast(e.message,true)}});
 if(isAdmin){
   document.querySelectorAll('[data-notice-propose]').forEach(btn=>btn.onclick=()=>{
     $('#legalProposalPanel').classList.remove('hidden');
     $('#legalProposalForm').elements.notice_id.value=btn.dataset.noticePropose;
     $('#legalProposalPanel').scrollIntoView({behavior:'smooth',block:'center'});
   });
   document.querySelectorAll('[data-legal-rollback]').forEach(btn=>btn.onclick=async()=>{const id=Number(btn.dataset.legalRollback);const justification=prompt('Dôvod vrátenia poslednej schválenej hodnoty (min. 12 znakov):');if(!justification||justification.length<12)return;if(!confirm('Vytvoriť auditovanú vratnú verziu pravidla s účinnosťou od dneška?'))return;try{await api('/api/legal-monitor/history/'+id+'/rollback',{method:'POST',body:JSON.stringify({justification})});toast('Vratná verzia zapísaná do histórie');legalMonitorView()}catch(e){toast(e.message,true)}});
   $('#legalProposalForm').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.notice_id=Number(p.notice_id);p.new_value=Number(p.new_value);if(!confirm('Vytvoriť návrh? Bez následného potvrdenia administrátora sa pravidlo nezmení.'))return;try{await api('/api/legal-monitor/proposals',{method:'POST',body:JSON.stringify(p)});toast('Návrh vytvorený, čaká na schválenie');legalMonitorView()}catch(e){toast(e.message,true)}};
   for(const action of ['approve','reject'])document.querySelectorAll('[data-proposal-'+action+']').forEach(btn=>btn.onclick=async()=>{
     const id=btn.dataset['proposal'+action[0].toUpperCase()+action.slice(1)];
     const justification=prompt(action==='approve'?'Potvrď právne overenie, dátum účinnosti a presné ustanovenie (min. 12 znakov):':'Uveď dôvod zamietnutia (min. 12 znakov):');
     if(!justification||justification.length<12)return;
     if(action==='approve'&&!confirm('Naozaj schváliť nový zákonný parameter? Táto zmena ovplyvní budúce referenčné výpočty.'))return;
     try{await api('/api/legal-monitor/proposals/'+id+'/'+action,{method:'POST',body:JSON.stringify({justification})});toast('Rozhodnutie auditované');legalMonitorView()}catch(e){toast(e.message,true)}
   });
 }
}


async function refreshLegalNoticeBanner(){
 const banner=$('#legalNoticeBanner');
 if(!banner)return;
 if(!['admin','hr'].includes(currentUser?.role)){banner.classList.add('hidden');return}
 try{
   const status=await api('/api/legal-monitor/status');
   const count=status.new_notices||0;
   banner.classList.toggle('hidden',count===0);
   if(count)banner.innerHTML='<strong>Legislatívna kontrola: '+count+' nové upozornenia</strong><span>Pravidlá sa bez schválenia nemenia.</span><button id="reviewLegalAlerts" class="secondary mini">Zobraziť návrhy</button>';
   if(count)$('#reviewLegalAlerts').onclick=()=>navigate('legalMonitor');
 }catch{banner.classList.add('hidden')}
}


let groupReportState={mode:'day',day:localDate(),month:localDate().slice(0,7),
    department:'all',status:'all',search:'',sortKey:'name',sortDesc:false,selectedEmployee:null};

function groupReportHour(minutes,signed=false){
 const n=Number(minutes||0),abs=Math.abs(n);
 return (signed&&n>0?'+':n<0?'−':'')+String(Math.floor(abs/60)).padStart(2,'0')+':'+String(abs%60).padStart(2,'0');
}
function groupStatusLabel(state){
 const s=state==='present'?'Prítomný':state==='break'?'Prestávka':state==='absent'?'Neprítomnosť':state==='away'?'Mimo / odpracované':'Bez záznamu';
 return s;
}
let groupReportPresetsLoaded={};
async function groupReportView(){
 const st=groupReportState;
 if(!groupReportPresetsLoaded[st.mode]){
   groupReportPresetsLoaded[st.mode]=true;
   try{const stored=JSON.parse(localStorage.getItem('bid-group-saved-view-'+st.mode)||'null');
     if(stored&&typeof stored==='object'){
       for(const key of ['department','status','sortKey','sortDesc','search'])
         if(Object.prototype.hasOwnProperty.call(stored,key))st[key]=stored[key];
     }}catch{}
 }
 $('#content').innerHTML='<div class="group-report"><div class="panel group-report-toolbar"><div class="section-top"><div><h3>Hromadný výkaz dochádzky</h3><span class="muted">Všetci zamestnanci na jednom mieste · denné pípnutia a mesačné časové zložky</span></div><div class="actions"><button id="grColumns" class="secondary">Zobrazené stĺpce</button><button id="grSaveView" class="secondary">Uložiť pohľad</button><button id="grCsv" class="secondary"><span>⇩</span> CSV</button><button id="grXlsx" class="primary"><span>▤</span> Excel</button></div></div><div id="grColumnPicker" class="gr-column-picker hidden"></div><div class="group-report-filter-row"><div class="group-report-toggle"><button id="grDay" class="'+(st.mode==='day'?'selected':'')+'">Denná dochádzka</button><button id="grMonth" class="'+(st.mode==='month'?'selected':'')+'">Mesačný hromadný výkaz</button></div><label class="field"><span>Obdobie</span><input id="grDate" type="'+(st.mode==='day'?'date':'month')+'" value="'+esc(st.mode==='day'?st.day:st.month)+'"></label><label class="field"><span>Útvar</span><select id="grDept"><option value="all">Všetky útvary</option></select></label><label class="field"><span>Stav</span><select id="grStatus"><option value="all">Všetky stavy</option>'+(st.mode==='day'?'<option value="present">Prítomní</option><option value="break">Na prestávke</option><option value="absent">Neprítomnosti</option><option value="away">Mimo / odpracované</option><option value="unrecorded">Bez záznamu</option>':'<option value="errors">S upozorneniami</option><option value="hours">S odpracovanými hodinami</option>')+'</select></label><label class="field gr-search"><span>Hľadať</span><input id="grSearch" placeholder="Meno, osobné číslo, pozícia…" value="'+esc(st.search)+'"></label><button class="secondary" id="grRefresh">Obnoviť</button></div><div class="group-report-legend"><span>● Časy sú z evidovaných RFID záznamov</span><span>● Saldo a zložky sú informatívne</span><span>● Kliknutím na zamestnanca otvoríš detail</span></div></div><div id="grStats" class="group-report-stats"></div><div class="panel group-report-table-panel"><div class="section-top"><div><h3 id="grTableTitle">Prehľad zamestnancov</h3><p class="subtle" id="grCount"></p></div><span class="muted">↔ Tabuľku možno posúvať vodorovne</span></div><div id="grTable" class="group-report-scroll"></div><div id="grTableTotals"></div></div><div id="grWageEditor" class="panel"></div><div class="panel"><div class="notice" id="grDisclaimer">Načítavam údaje…</div></div><div id="grDetail"></div></div>';
 const dateLabel=()=>st.mode==='day'?st.day:st.month;
 const params=()=>st.mode==='day'?'mode=day&day='+encodeURIComponent(st.day):
     'mode=month&year='+encodeURIComponent(st.month.split('-')[0])+'&month='+encodeURIComponent(st.month.split('-')[1]);
 let dataset=null;
 const render=()=>{
  if(!dataset)return;
  const rows=dataset.rows||[],fields=dataset.columns||[];
  const departments=[...new Set(rows.map(r=>r.department||'Bez útvaru'))].sort((a,b)=>a.localeCompare(b,'sk'));
  const editor=$('#grWageEditor');
  if(editor&&!editor.dataset.initialized){
    editor.dataset.initialized='1';
    editor.innerHTML='<div class="section-top"><div><h3>Mzdové zložky pracovného času</h3><span class="muted">HR zápis · celý pracovný deň, interval alebo podľa pípnutí · kontrola duplicít a audit</span></div></div><form id="grWageForm"><div class="form-grid"><label class="field"><span>Zamestnanec</span><select name="employee_id" id="grWagePerson">'+rows.map(p=>'<option value="'+p.employee_id+'">'+esc(p.name)+' · '+esc(p.personal_number)+'</option>').join('')+'</select></label><label class="field"><span>Mzdová zložka</span><select name="kind"><option value="business_trip">Služobná cesta</option><option value="service_errand">Služobné dôvody – vybavovanie mimo pracoviska</option><option value="doctor">Lekár</option><option value="accompany">Lekár – sprevádzanie</option><option value="home_office">Home office</option></select></label><label class="field"><span>Deň</span><input name="day" type="date" required value="'+(st.mode==='day'?st.day:st.month+'-01')+'"></label><label class="field"><span>Rozsah</span><select name="mode" id="grWageMode"><option value="all_day">Celý pracovný deň podľa fondu</option><option value="time_range">Časový interval</option><option value="punched">Podľa dochádzkových pípnutí</option></select></label><label class="field gr-wage-time"><span>Od</span><input name="starts_at" type="time" value="08:00"></label><label class="field gr-wage-time"><span>Do</span><input name="ends_at" type="time" value="12:00"></label></div><label class="field"><span>Pracovný dôvod / miesto / poznámka</span><input name="note" required minlength="8" maxlength="400" placeholder="Napr. rokovanie v meste, vybavenie na úrade, lekár…"></label><button class="primary" type="submit">Pridať mzdovú zložku s auditom</button></form><div id="grWageRecords"></div><p class="subtle">Jeden deň môže mať viac neprekrývajúcich sa časových intervalov rôznych zložiek. Pôvodný záznam sa pri oprave nemaže, ale auditovane ruší. Služobná cesta môže mať osobitný cestovný príkaz; jeho celkové trvanie sa automaticky nepovažuje za pracovný čas.</p>';
    const form=$('#grWageForm'),mode=$('#grWageMode');
    const toggle=()=>form.querySelectorAll('.gr-wage-time').forEach(x=>x.classList.toggle('hidden',mode.value!=='time_range'));
    mode.onchange=toggle;toggle();
    form.onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(form));p.employee_id=Number(p.employee_id);if(p.mode==='time_range'){const make=value=>{const [hour,minute]=value.split(':').map(Number);const d=new Date(p.day+'T00:00:00');d.setHours(hour,minute,0,0);return d.toISOString()};p.starts_at=make(p.starts_at);p.ends_at=make(p.ends_at);}else{p.starts_at=null;p.ends_at=null;}if(!confirm('Zapísať mzdovú zložku '+p.kind+'?'))return;try{await api('/api/wage-components',{method:'POST',body:JSON.stringify(p)});toast('Mzdová zložka uložená');load()}catch(e){toast(e.message,true)}};
  }
  $('#grDept').innerHTML='<option value="all">Všetky útvary</option>'+departments.map(d=>'<option value="'+esc(d)+'">'+esc(d)+'</option>').join('');
  if(departments.includes(st.department))$('#grDept').value=st.department;
  else{st.department='all';$('#grDept').value='all'}
  $('#grStatus').value=st.status;
  $('#grDisclaimer').textContent=dataset.note;
  const q=st.search.toLocaleLowerCase('sk-SK').trim();
  const shown=rows.filter(r=>(st.department==='all'||(r.department||'Bez útvaru')===st.department)&&
    (st.status==='all'||(st.mode==='day'?r.status_key===st.status:st.status==='errors'?Number(r.warnings)>0:Number(r.worked_min)>0))&&
    (!q||[r.name,r.personal_number,r.department,r.job_title,r.component].some(v=>String(v||'').toLocaleLowerCase('sk-SK').includes(q))));
  const fieldMap={date:'Dátum',personal_number:'Os. č.',name:'Zamestnanec',department:'Útvar',job_title:'Pozícia',status:'Stav',first_in:'Príchod',last_out:'Odchod',last_punch:'Posledné pípnutie',planned_min:'Fond',worked_min:'Odpracované',break_min:'Prestávka',credited_min:'Uznané voľno',saldo_min:'Saldo',component:'Zložka / neprítomnosť',warnings:'Kontrola',
    presence:'Aktuálny stav',vacation_min:'Dovolenka',doctor_min:'Lekár',accompany_min:'Sprevádzanie',home_office_min:'Home office',business_trip_min:'Služobná cesta',service_errand_min:'Služobné dôvody',travel_duration_min:'Trvanie cesty',sick_min:'PN',ocr_min:'OČR',doctor_unpaid_min:'Lekár – neplatené',accompany_unpaid_min:'Sprevádzanie – neplatené',maternity_min:'Materská',paternity_min:'Otcovská',parental_min:'Rodičovská',unpaid_min:'Neplatené voľno',paid_leave_min:'Platené voľno',training_min:'Školenie',wedding_min:'Svadba',funeral_min:'Pohreb',blood_donation_min:'Darovanie krvi',other_min:'Iná neprítomnosť',other_absence_min:'Ostatné voľno',night_min:'Nočná práca',saturday_min:'Sobota',sunday_min:'Nedeľa',holiday_min:'Sviatok',attendance_days:'Pracovné dni'};
  const defaultColumns=st.mode==='day'?['personal_number','name','department','job_title','status','first_in','last_out','planned_min','worked_min','break_min','credited_min','saldo_min','doctor_min','accompany_min','home_office_min','business_trip_min','service_errand_min','component','warnings']:
    ['personal_number','name','department','presence','planned_min','worked_min','break_min','credited_min','saldo_min','vacation_min','doctor_min','accompany_min','home_office_min','business_trip_min','service_errand_min','sick_min','ocr_min','warnings'];
  const allComponents=['vacation_min','doctor_min','accompany_min','home_office_min','business_trip_min','service_errand_min','travel_duration_min','sick_min','ocr_min','doctor_unpaid_min','accompany_unpaid_min','maternity_min','paternity_min','parental_min','unpaid_min','paid_leave_min','training_min','wedding_min','funeral_min','blood_donation_min','other_min','other_absence_min'];
  const available=[...new Set([...defaultColumns,...allComponents,...(st.mode==='month'?['night_min','saturday_min','sunday_min','holiday_min','attendance_days']:['last_punch','date'])])];
  const key='bid-group-columns-v3-'+st.mode;
  const stored=(()=>{try{const data=JSON.parse(localStorage.getItem(key)||'null');return Array.isArray(data)?data:null}catch{return null}})();
  const columns=stored?available.filter(x=>stored.includes(x)):defaultColumns;
  if(!columns.includes('name'))columns.unshift('name');
  const picker=$('#grColumnPicker');
  picker.innerHTML='<div class="gr-columns-top"><strong>Vyber zobrazené stĺpce</strong><button id="grColumnReset" class="secondary mini">Predvolené</button></div><div class="gr-columns-grid">'+available.map(col=>'<label><input type="checkbox" data-gr-col="'+col+'" '+(columns.includes(col)?'checked':'')+'> '+esc(fieldMap[col]||col)+'</label>').join('')+'</div><p class="subtle">OČR, PN a všetky ostatné zložky sú dostupné vo výbere. Nastavenie sa ukladá v tomto prehliadači.</p>';
  picker.querySelectorAll('[data-gr-col]').forEach(x=>x.onchange=()=>{
   const selected=[...picker.querySelectorAll('[data-gr-col]:checked')].map(e=>e.dataset.grCol);
   if(!selected.includes('name'))selected.unshift('name');
   localStorage.setItem(key,JSON.stringify(selected));render();
  });
  $('#grColumnReset').onclick=()=>{localStorage.removeItem(key);render()};
  const sorted=[...shown].sort((a,b)=>{
    const x=a[st.sortKey]??'',y=b[st.sortKey]??'';
    const result=typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y),'sk',{numeric:true});
    return st.sortDesc?-result:result;
  });
  const stat=(label,note,value,cls='')=>'<div class="gr-stat '+cls+'"><span>'+label+'</span><strong>'+value+'</strong><small>'+note+'</small></div>';
  if(st.mode==='day'){
    const counts={present:0,absent:0,break:0,away:0,unrecorded:0};
    for(const r of shown)counts[r.status_key]=(counts[r.status_key]||0)+1;
    const worked=shown.reduce((v,r)=>v+Number(r.worked_min||0),0);
    $('#grStats').innerHTML=stat('Zamestnanci','Vo vybranom prehľade',shown.length)+
      stat('Prítomní*','Posledný príchod',counts.present,'present')+
      stat('Neprítomnosti','Dovolenka, PN, OČR a ďalšie',counts.absent,'absent')+
      stat('Mimo / odpracované','Posledný odchod alebo uzavretá zmena',counts.away,'away')+
      stat('Odpracované spolu','Ukončené pracovné intervaly',groupReportHour(worked));
  }else{
    const sum=k=>shown.reduce((v,r)=>v+Number(r[k]||0),0);
    $('#grStats').innerHTML=stat('Zamestnanci','Vo vybranom prehľade',shown.length)+
      stat('Fond','Plánované hodiny',groupReportHour(sum('planned_min')))+
      stat('Odpracované','Ukončené intervaly',groupReportHour(sum('worked_min')),'present')+
      stat('Uznané voľno','Kontrolná hodnota',groupReportHour(sum('credited_min')))+
      stat('Saldo','Orientačný súčet',groupReportHour(sum('saldo_min'),true))+
      stat('Kontrolné nálezy','Zamestnanci s upozornením',shown.filter(r=>Number(r.warnings)>0).length,'absent');
  }
  $('#grTableTitle').textContent=(st.mode==='day'?'Denná dochádzka · '+st.day:'Hromadný mesačný výkaz · '+st.month);
  $('#grCount').textContent='Zobrazených '+shown.length+' z '+rows.length+' zamestnancov. Klikni na meno pre detail.';
  const [componentYear,componentMonth]=(st.mode==='day'?st.day.slice(0,7):st.month).split('-');
  api('/api/wage-components?year='+componentYear+'&month='+componentMonth).then(entries=>{
    const node=$('#grWageRecords');if(!node)return;
    const records=entries.filter(x=>x.active).slice(0,30);
    node.innerHTML='<h4>Ručné mzdové zložky v období</h4>'+(records.length?'<div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Deň</th><th>Zložka</th><th>Rozsah</th><th>Akcia</th></tr></thead><tbody>'+records.map(x=>'<tr><td>'+esc(rows.find(p=>p.employee_id===x.employee_id)?.name||String(x.employee_id))+'</td><td>'+esc(x.day)+'</td><td>'+esc(fieldMap[x.kind+'_min']||x.kind)+'</td><td>'+esc(x.mode)+'</td><td><button class="secondary mini" data-wage-cancel="'+x.id+'">Zrušiť</button></td></tr>').join('')+'</tbody></table></div>':'<p class="subtle">Zatiaľ bez ručných klasifikácií.</p>');
    node.querySelectorAll('[data-wage-cancel]').forEach(btn=>btn.onclick=async()=>{const reason=prompt('Dôvod storna (aspoň 8 znakov):');if(!reason||reason.length<8)return;try{await api('/api/wage-components/'+btn.dataset.wageCancel+'/cancel',{method:'POST',body:JSON.stringify({reason})});toast('Zložka auditovane zrušená');load()}catch(e){toast(e.message,true)}});
  }).catch(()=>{});

  const header='<thead><tr>'+columns.map(k=>'<th data-gr-sort="'+k+'" class="'+(k==='name'?'gr-sticky-name':k==='personal_number'?'gr-sticky-id':'')+'">'+esc(fieldMap[k]||k)+(st.sortKey===k?(st.sortDesc?' ▼':' ▲'):'')+'</th>').join('')+'<th>Detail</th></tr></thead>';
  const v=(r,key)=>{
   if(key==='name')return '<button class="gr-name" data-gr-person="'+r.employee_id+'">'+esc(r.name)+'</button><small>'+esc(r.personal_number)+'</small>';
   if(key==='status')return '<span class="gr-status gr-status-'+esc(r.status_key)+'"><span class="gr-dot">●</span>'+esc(r.status)+'</span>';
   if(key==='presence')return '<span class="gr-presence">'+esc(r.presence)+'</span>';
   if(key==='component')return r.component&&r.component!=='—'?'<span class="gr-component">'+esc(r.component)+'</span>':'—';
   if(key==='warnings')return st.mode==='day'?(r.warnings?.length?'<span class="gr-alert" title="'+esc(r.warnings.join('; '))+'">⚠ '+r.warnings.length+'</span>':'<span class="gr-clear">✓</span>'):(r.warnings?'<span class="gr-alert">⚠ '+r.warnings+'</span>':'<span class="gr-clear">✓</span>');
   if(/_min$/.test(key))return '<span class="gr-num '+(key==='saldo_min'?(r[key]<0?'gr-negative':'gr-positive'):'')+'">'+groupReportHour(r[key],key==='saldo_min')+'</span>';
   return esc(r[key]??'—');
  };
  $('#grTable').innerHTML='<table class="gr-grid">'+header+'<tbody>'+sorted.map((r,i)=>'<tr class="'+(r.warnings?.length||r.warnings>0?'gr-needs-check':'')+'">'+columns.map(k=>'<td class="'+(k==='name'?'gr-sticky-name':k==='personal_number'?'gr-sticky-id':'')+'">'+v(r,k)+'</td>').join('')+'<td><button class="secondary mini" data-gr-person="'+r.employee_id+'">Otvoriť</button></td></tr>').join('')+'</tbody></table>'+(sorted.length?'':'<p class="empty">Pre zvolené filtre nie sú záznamy.</p>');
  const aggregateFields=['planned_min','worked_min','break_min','credited_min','saldo_min','doctor_min','accompany_min','home_office_min','business_trip_min','service_errand_min'];
  $('#grTableTotals').innerHTML='<div class="gr-totals"><strong>Súčet zobrazených</strong>'+aggregateFields.map(k=>'<span>'+esc(fieldMap[k])+': <b>'+groupReportHour(shown.reduce((v,r)=>v+Number(r[k]||0),0),k==='saldo_min')+'</b></span>').join('')+'</div>';
  document.querySelectorAll('[data-gr-sort]').forEach(x=>x.onclick=()=>{const key=x.dataset.grSort;if(st.sortKey===key)st.sortDesc=!st.sortDesc;else{st.sortKey=key;st.sortDesc=false}render()});
  document.querySelectorAll('[data-gr-person]').forEach(x=>x.onclick=()=>openGroupReportPerson(Number(x.dataset.grPerson),rows));
 };
 const load=async()=>{try{dataset=await api('/api/group-report?'+params());render()}catch(error){$('#grTable').innerHTML='<div class="error">'+esc(error.message)+'</div>';toast(error.message,true)}};
 $('#grDay').onclick=()=>{st.mode='day';st.status='all';groupReportView()};
 $('#grMonth').onclick=()=>{st.mode='month';st.status='all';groupReportView()};
 $('#grDate').onchange=e=>{if(st.mode==='day')st.day=e.target.value;else st.month=e.target.value;load()};
 $('#grDept').onchange=e=>{st.department=e.target.value;render()};
 $('#grStatus').onchange=e=>{st.status=e.target.value;render()};
 $('#grSearch').oninput=e=>{st.search=e.target.value;render()};
 $('#grRefresh').onclick=load;
 const download=async ext=>{const filename='bid_hromadna_dochadzka_'+st.mode+'_'+dateLabel()+'.'+ext;try{await fetchProtectedFile('/api/group-report/export?'+params()+'&file_format='+ext,filename);toast('Export '+ext.toUpperCase()+' pripravený')}catch(error){toast(error.message,true)}};
 $('#grColumns').onclick=()=>$('#grColumnPicker').classList.toggle('hidden');
 $('#grSaveView').onclick=()=>{try{const state={mode:st.mode,department:st.department,status:st.status,sortKey:st.sortKey,sortDesc:st.sortDesc,search:st.search};localStorage.setItem('bid-group-saved-view-'+st.mode,JSON.stringify(state));toast('Rozloženie a filtre uložené v tomto prehliadači')}catch(e){toast('Rozloženie sa nepodarilo uložiť',true)}};
 $('#grCsv').onclick=()=>download('csv');
 $('#grXlsx').onclick=()=>download('xlsx');
 await load();
}
async function openGroupReportPerson(id,rows){
 const r=rows.find(p=>p.employee_id===id);
 if(!r)return;
 const div=$('#grDetail');
 const period=groupReportState.mode==='day'?groupReportState.day:groupReportState.month;
 const label=groupReportState.mode==='day'?'Vybraný deň':'Vybraný mesiac';
 div.innerHTML='<div class="gr-detail-backdrop"><div class="gr-detail-sheet" role="dialog" aria-modal="true" aria-labelledby="grDetailTitle"><div class="section-top"><div><span class="muted">OSOBNÝ DOCHÁDZKOVÝ DETAIL</span><h3 id="grDetailTitle">'+esc(r.name)+'</h3><p>'+esc(r.department||'Bez útvaru')+' · '+esc(r.job_title||'—')+'</p></div><button id="grClose" class="secondary">✕ Zavrieť</button></div><div class="gr-detail-metrics"><div><span>Odpracované</span><strong>'+groupReportHour(r.worked_min)+'</strong></div><div><span>Fond</span><strong>'+groupReportHour(r.planned_min)+'</strong></div><div><span>Saldo</span><strong>'+groupReportHour(r.saldo_min,true)+'</strong></div></div><div class="gr-detail-body"><p><b>'+label+':</b> '+esc(period)+'</p><p><b>Osobné číslo:</b> '+esc(r.personal_number)+'</p><p><b>Pracovné zaradenie:</b> '+esc(r.department||'—')+' · '+esc(r.job_title||'—')+'</p>'+(groupReportState.mode==='day'?'<p><b>Príchod:</b> '+esc(r.first_in||'—')+' · <b>Odchod:</b> '+esc(r.last_out||'—')+'</p><p><b>Stav:</b> '+esc(r.status)+'</p><p><b>Zložka:</b> '+esc(r.component||'—')+'</p>':'<p><b>Aktuálna evidencia:</b> '+esc(r.presence)+'</p><p><b>Dovolenka:</b> '+groupReportHour(r.vacation_min)+' · <b>Lekár:</b> '+groupReportHour(r.doctor_min)+' · <b>Sprevádzanie:</b> '+groupReportHour(r.accompany_min)+'</p>')+'<div class="notice">Výpočty sú informačné a nevzniká tým rozhodnutie o mzdovom zvýhodnení ani o nadčase.</div></div><div class="actions gr-detail-actions"><button class="primary" id="grPersonPdf">Mesačný PDF výkaz</button><button class="secondary" id="grPersonCorrections">Záznamy a opravy</button></div></div></div>';
 $('#grClose').onclick=()=>div.innerHTML='';
 div.querySelector('.gr-detail-backdrop').onclick=e=>{if(e.target.classList.contains('gr-detail-backdrop'))div.innerHTML=''};
 $('#grPersonPdf').onclick=async()=>{const month=period.slice(0,7),[year,number]=month.split('-');try{await fetchProtectedFile('/api/reports/monthly/'+id+'/pdf?year='+year+'&month='+Number(number),'dochadzka_'+r.personal_number+'_'+month+'.pdf');toast('PDF výkaz pripravený')}catch(e){toast(e.message,true)}};
 $('#grPersonCorrections').onclick=()=>{div.innerHTML='';navigate('corrections')};
}


async function approvalCenterView(selectedPeriod){
 const period=selectedPeriod||localDate().slice(0,7);
 const [year,month]=period.split('-').map(Number);
 const [status,check,people]=await Promise.all([
  api('/api/workflow/month/'+year+'/'+month),
  api('/api/workflow/close-precheck/'+year+'/'+month),
  api('/api/hr/employees')
 ]);
 const pill=(state)=>state==='confirmed'?'<span class="pill approved">Potvrdené</span>':state==='reviewed'?'<span class="pill pending">Skontrolované</span>':'<span class="pill">Čaká na kontrolu</span>';
 const personal=people.map(e=>'<option value="'+e.id+'">'+esc(e.name)+' ('+esc(e.personal_number)+')</option>').join('');
 const rows=status.rows.map(r=>'<tr><td>'+esc(r.name)+'</td><td>'+pill(r.status.status)+'</td><td>'+esc(r.status.reviewed_by||'—')+'</td><td>'+esc(r.status.confirmed_by||'—')+'</td><td><button class="secondary mini" data-review-employee="'+r.employee_id+'">Kontrola HR</button> '+(r.status.status==='reviewed'?'<button class="primary mini" data-confirm-employee="'+r.employee_id+'">Potvrdiť</button>':'')+(r.status.status==='confirmed'?'<button class="secondary mini" data-unconfirm-employee="'+r.employee_id+'">Odomknúť</button>':'')+'</td></tr>').join('');
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Kontrola → Potvrdenie → Uzávierka</h3><span class="muted">Postup podľa agendy Aktion, prispôsobený existujúcemu systému BID</span></div><div class="actions"><input id="approvalPeriod" type="month" value="'+period+'"><button id="approvalReload" class="secondary">Načítať obdobie</button></div></div><div class="stats"><div class="stat"><strong>Zamestnanci</strong><div class="value">'+status.rows.length+'</div><small>Aktívni v období</small></div><div class="stat"><strong>Potvrdené</strong><div class="value">'+status.rows.filter(x=>x.status.status==='confirmed').length+'</div><small>Overené vedúcim / HR</small></div><div class="stat"><strong>Chýbajúce potvrdenia</strong><div class="value">'+check.missing.length+'</div><small>Pred mesačnou uzávierkou</small></div></div><div class="notice">Kontrola sama osebe nemení dochádzkové pípnutia. Potvrdenie uzamyká schvaľovací stav osoby; finálna mesačná uzávierka zostáva v pôvodnom module. Pred uzavretím skontroluj upozornenia a výkazy.</div><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Stav</th><th>Kontroloval</th><th>Potvrdil</th><th>Akcia</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>'+
 '<div class="panel"><div class="section-top"><div><h3>Hromadné zadanie neprítomnosti</h3><span class="muted">Vyber zamestnancov a najprv skontroluj simuláciu zápisu</span></div></div><form id="aktionBulkForm"><div class="form-grid"><label class="field"><span>Typ neprítomnosti</span><select name="kind"><option value="vacation">Dovolenka</option><option value="doctor">Lekár</option><option value="accompany">Sprevádzanie</option><option value="paid_leave">Platené voľno</option><option value="unpaid">Neplatené voľno</option><option value="training">Školenie</option><option value="business_trip">Pracovná cesta</option><option value="ocr">OČR (oznámenie)</option><option value="sick">PN (oznámenie)</option></select></label><label class="field"><span>Od</span><input type="date" name="start" value="'+localDate()+'" required></label><label class="field"><span>Do</span><input type="date" name="end" value="'+localDate()+'" required></label><label class="field"><span>Minúty – voliteľné iba pre jeden deň</span><input type="number" name="minutes" min="1" max="1440" placeholder="Celodenné voľno"></label></div><label class="field"><span>Dôvod (aspoň 8 znakov)</span><input name="reason" minlength="8" maxlength="400" required placeholder="Schválené HR, interný pokyn…"></label><div class="gr-bulk-people"><label><input id="aktionSelectAll" type="checkbox"> Vybrať všetkých</label><div class="gr-bulk-grid">'+people.map(x=>'<label class="gr-bulk-person"><input type="checkbox" name="people" value="'+x.id+'"> '+esc(x.name)+'<small>'+esc(x.department||'')+'</small></label>').join('')+'</div></div><div class="actions"><button type="button" class="secondary" id="aktionBulkPreview">Skontrolovať bez uloženia</button><button type="submit" class="primary" id="aktionBulkCommit" disabled>Potvrdiť a uložiť hromadne</button></div><div id="aktionBulkResult" class="notice">Pred uložením sa overia zamestnanci, termíny, duplicity, existujúce neprítomnosti a uzávierky.</div></form></div>';
 $('#approvalReload').onclick=()=>{const [y,m]=$('#approvalPeriod').value.split('-').map(Number);approvalCenterView($('#approvalPeriod').value)};
 const change=(employee_id,path,note)=>api('/api/workflow/'+path,{method:'POST',body:JSON.stringify({employee_id,year,month,note})});
 document.querySelectorAll('[data-review-employee]').forEach(x=>x.onclick=async()=>{if(!confirm('Označiť dochádzku ako skontrolovanú v rámci HR?'))return;try{await change(Number(x.dataset.reviewEmployee),'review','Kontrola HR');toast('Kontrola zaevidovaná');approvalCenterView(period)}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-confirm-employee]').forEach(x=>x.onclick=async()=>{if(!confirm('Potvrdiť dochádzku zamestnanca?'))return;try{await change(Number(x.dataset.confirmEmployee),'confirm','Overené vedúcim alebo HR');toast('Dochádzka potvrdená');approvalCenterView(period)}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-unconfirm-employee]').forEach(x=>x.onclick=async()=>{const note=prompt('Dôvod odomknutia (aspoň 8 znakov):');if(!note||note.length<8)return;try{await change(Number(x.dataset.unconfirmEmployee),'unconfirm',note);toast('Potvrdenie zrušené s auditom');approvalCenterView(period)}catch(e){toast(e.message,true)}});
 const form=$('#aktionBulkForm'),commit=$('#aktionBulkCommit'),feedback=$('#aktionBulkResult');
 let verified=null;
 $('#aktionSelectAll').onchange=e=>form.querySelectorAll('[name="people"]').forEach(x=>x.checked=e.target.checked);
 const currentPayload=()=>{const p=Object.fromEntries(new FormData(form));p.employee_ids=[...form.querySelectorAll('[name="people"]:checked')].map(x=>Number(x.value));delete p.people;p.minutes=p.minutes?Number(p.minutes):null;return p};
 form.onchange=()=>{verified=null;commit.disabled=true};
 $('#aktionBulkPreview').onclick=async()=>{const p=currentPayload();if(!p.employee_ids.length){toast('Najprv vyber zamestnancov',true);return}try{const result=await api('/api/bulk-absence',{method:'POST',body:JSON.stringify({...p,dry_run:true})});verified=JSON.stringify(p);feedback.textContent='Overenie úspešné: '+result.count+' zamestnancov, '+result.kind+', '+result.start+' – '+result.end+'. Pred uložením skontroluj správnosť údajov.';commit.disabled=false;toast('Hromadný zápis prešiel kontrolou')}catch(e){verified=null;commit.disabled=true;feedback.textContent='Zápis sa nedá vykonať: '+e.message;toast(e.message,true)}};
 form.onsubmit=async ev=>{ev.preventDefault();const p=currentPayload();if(JSON.stringify(p)!==verified)return toast('Parametre sa zmenili. Spusť kontrolu znovu.',true);if(!confirm('Naozaj vytvoriť '+p.employee_ids.length+' schválených neprítomností? Záznam bude auditovaný.'))return;try{const result=await api('/api/bulk-absence',{method:'POST',body:JSON.stringify({...p,dry_run:false})});toast('Hromadne uložené: '+result.count+' zamestnancov');approvalCenterView(period)}catch(e){commit.disabled=true;toast(e.message,true)}};
}
async function loadApprovalPeriod(year,month){
 const data=await api('/api/workflow/month/'+year+'/'+month);
 $('#content .panel .scroll tbody').innerHTML=data.rows.map(r=>'<tr><td>'+esc(r.name)+'</td><td>'+esc(r.status.status)+'</td><td>'+esc(r.status.reviewed_by||'—')+'</td><td>'+esc(r.status.confirmed_by||'—')+'</td></tr>').join('');
}


function euroTravel(v){return Number(v||0).toLocaleString('sk-SK',{minimumFractionDigits:2,maximumFractionDigits:2})+' €'}
function travelLocalDatetime(value){
 const x=new Date(value),two=n=>String(n).padStart(2,'0');
 return x.getFullYear()+'-'+two(x.getMonth()+1)+'-'+two(x.getDate())+'T'+two(x.getHours())+':'+two(x.getMinutes());
}
async function travelView(){
 const [trips,people]=await Promise.all([api('/api/travel'),api('/api/hr/employees')]);
 const personOpts=people.map(p=>'<option value="'+p.id+'">'+esc(p.name)+' ('+esc(p.personal_number)+')</option>').join('');
 const rows=trips.map(t=>'<tr><td>'+t.id+'</td><td><strong>'+esc(t.employee_name)+'</strong><small>'+esc(t.destination)+'</small></td><td>'+esc(new Date(t.starts_at).toLocaleString('sk-SK'))+'</td><td>'+esc(new Date(t.ends_at).toLocaleString('sk-SK'))+'</td><td><span class="pill '+esc(t.status)+'">'+esc(t.status==='approved'?'Schválené':t.status==='draft'?'Na schválenie':'Zrušené')+'</span></td><td>'+euroTravel(t.meal_allowance_eur)+'</td><td>'+euroTravel(t.travel_total_eur)+'</td><td><strong>'+euroTravel(t.to_pay_eur)+'</strong></td><td><button class="secondary mini" data-trip-detail="'+t.id+'">Podrobnosti</button></td></tr>').join('');
 const sum=key=>trips.filter(t=>t.status==='approved').reduce((n,t)=>n+Number(t[key]||0),0);
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Služobné cesty a cestovné náhrady</h3><span class="muted">Tuzemské cesty, stravné, bezplatné jedlá, kilometrovné a vyúčtovanie</span></div><button id="travelExport" class="secondary">⇩ Export CSV</button></div><div class="travel-kpis"><div class="gr-stat"><span>Schválené cesty</span><strong>'+trips.filter(t=>t.status==='approved').length+'</strong><small>Aktívne vyúčtovania</small></div><div class="gr-stat"><span>Stravné spolu</span><strong>'+euroTravel(sum('meal_allowance_eur'))+'</strong><small>Len schválené cesty</small></div><div class="gr-stat"><span>Cestovné náhrady spolu</span><strong>'+euroTravel(sum('travel_total_eur'))+'</strong><small>Bez preddavkov</small></div></div><div class="scroll"><table><thead><tr><th>ID</th><th>Zamestnanec / cieľ</th><th>Odchod</th><th>Návrat</th><th>Stav</th><th>Stravné</th><th>Náhrady</th><th>Doplatok</th><th>Akcia</th></tr></thead><tbody>'+rows+'</tbody></table></div></div><div class="panel"><h3>Nový cestovný príkaz / vyúčtovanie</h3><form id="travelNew"><div class="form-grid"><label class="field"><span>Zamestnanec</span><select name="employee_id">'+personOpts+'</select></label><label class="field"><span>Účel pracovnej cesty</span><input name="purpose" required minlength="5" placeholder="Pracovné rokovanie, školenie…"></label><label class="field"><span>Miesto / cieľ</span><input name="destination" required placeholder="Bratislava, Trnava…"></label><label class="field"><span>Začiatok</span><input type="datetime-local" name="starts_at" required value="'+localDate()+'T08:00"></label><label class="field"><span>Koniec</span><input type="datetime-local" name="ends_at" required value="'+localDate()+'T17:00"></label><label class="field"><span>Doprava</span><select name="transport"><option value="public">Verejná doprava</option><option value="company_car">Služobné vozidlo</option><option value="private_car">Súkromné vozidlo (po dohode)</option><option value="other">Iné</option></select></label><label class="field"><span>Počet km (súkromné vozidlo)</span><input type="number" step="0.1" min="0" name="private_car_km" value="0"></label><label class="field"><span>Spotreba (l/100 km)</span><input type="number" step="0.001" min="0" name="fuel_l_per_100km" value="0"></label><label class="field"><span>Cena paliva (€/l)</span><input type="number" step="0.001" min="0" name="fuel_price_eur_l" value="0"></label><label class="field"><span>Dopravné výdavky €</span><input type="number" step="0.01" min="0" name="public_transport_eur" value="0"></label><label class="field"><span>Ubytovanie €</span><input type="number" step="0.01" min="0" name="lodging_eur" value="0"></label><label class="field"><span>Ostatné výdavky €</span><input type="number" step="0.01" min="0" name="other_expenses_eur" value="0"></label><label class="field"><span>Preddavok €</span><input type="number" step="0.01" min="0" name="advance_eur" value="0"></label></div><label class="field"><span>Poznámka</span><textarea name="note" rows="2" placeholder="Účel, doklady, preplatené náklady…"></textarea></label><button class="primary">Vytvoriť cestu a vypočítať stravné</button></form><div class="notice">Od 1.12.2026 je tuzemské stravné 9,80 / 14,60 / 21,70 € podľa trvania. Do 30.11.2026 platí 9,30 / 13,80 / 20,60 €. Bezplatné jedlá sa kráti zo sadzby najvyššieho pásma. Zahraničné cesty zatiaľ vyžadujú samostatné vyúčtovanie.</div></div><div id="travelDetails"></div>';
 $('#travelExport').onclick=async()=>{try{await fetchProtectedFile('/api/travel/summary.csv','bid_sluzobne_cesty.csv');toast('CSV cestovných náhrad pripravené')}catch(e){toast(e.message,true)}};
 $('#travelNew').onsubmit=async ev=>{ev.preventDefault();const p=Object.fromEntries(new FormData(ev.target));p.employee_id=Number(p.employee_id);for(const field of ['private_car_km','fuel_l_per_100km','fuel_price_eur_l','public_transport_eur','lodging_eur','other_expenses_eur','advance_eur'])p[field]=Number(p[field]||0);p.starts_at=new Date(p.starts_at).toISOString();p.ends_at=new Date(p.ends_at).toISOString();try{const result=await api('/api/travel',{method:'POST',body:JSON.stringify(p)});toast('Pracovná cesta vytvorená; stravné je vypočítané po dňoch');travelView()}catch(e){toast(e.message,true)}};
 const details=id=>{
  const t=trips.find(x=>x.id===id);if(!t)return;
  const items=t.meal_days.map(day=>'<tr><td>'+esc(day.day)+'</td><td>'+day.hours+' h</td><td>'+esc(day.band)+'</td><td>'+euroTravel(day.gross_eur)+'</td><td>'+euroTravel(day.deduction_reference_eur)+'</td><td><strong>'+euroTravel(day.meal_allowance_eur)+'</strong></td><td>'+(t.status==='draft'?'<button class="secondary mini" data-trip-meal="'+esc(day.day)+'">Bezplatné jedlá</button>':'—')+'</td></tr>').join('');
  $('#travelDetails').innerHTML='<div class="panel"><div class="section-top"><div><h3>Vyúčtovanie č. '+t.id+' · '+esc(t.employee_name)+'</h3><p class="muted">'+esc(t.purpose)+' · '+esc(t.destination)+'</p></div><button class="secondary" id="tripCloseDetail">Zavrieť</button></div><div class="travel-kpis"><div class="gr-stat"><span>Stravné</span><strong>'+euroTravel(t.meal_allowance_eur)+'</strong><small>Po krátení jedál</small></div><div class="gr-stat"><span>Kilometrovné a palivo</span><strong>'+euroTravel(t.mileage_eur+t.fuel_eur)+'</strong><small>Po schválení nákladov</small></div><div class="gr-stat"><span>Výdavky</span><strong>'+euroTravel(t.expenses_eur)+'</strong><small>Doprava, hotel, iné</small></div><div class="gr-stat"><span>Vyúčtovanie</span><strong>'+euroTravel(t.to_pay_eur)+'</strong><small>Po odpočítaní preddavku</small></div></div><div class="scroll"><table><thead><tr><th>Dátum</th><th>Trvanie</th><th>Pásmo</th><th>Nárok</th><th>Krátenie</th><th>Stravné na výplatu</th><th>Jedlá</th></tr></thead><tbody>'+items+'</tbody></table></div><div class="notice">Výpočet je orientačný. Pracovná cesta automaticky neznamená rovnaký počet odpracovaných hodín. Ak zamestnanec počas cesty pracoval na pravidelnom pracovisku, osobitne over nárok na stravovací lístok.</div><div class="actions">'+(t.status==='draft'?'<button id="travelApprove" class="primary">Schváliť vyúčtovanie</button><button id="travelCancel" class="secondary">Zrušiť cestu</button>':'')+'</div></div>';
  $('#tripCloseDetail').onclick=()=>$('#travelDetails').innerHTML='';
  document.querySelectorAll('[data-trip-meal]').forEach(btn=>btn.onclick=async()=>{
    const day=btn.dataset.tripMeal,prev=t.meal_days.find(x=>x.day===day);
    const breakfast=confirm('Bezplatné raňajky v deň '+day+'?');
    const lunch=confirm('Bezplatný obed v deň '+day+'?');
    const dinner=confirm('Bezplatná večera v deň '+day+'?');
    const cannot_use_provided=(breakfast||lunch||dinner)&&confirm('Nemohol zamestnanec jedlá využiť bez vlastného zavinenia? Ak áno, nekrátiť a preveriť zdôvodnenie.');
    try{await api('/api/travel/'+id+'/meal',{method:'PUT',body:JSON.stringify({day,breakfast,lunch,dinner,cannot_use_provided})});toast('Jedlá a stravné prepočítané');travelView()}catch(e){toast(e.message,true)}
  });
  const approve=$('#travelApprove');if(approve)approve.onclick=async()=>{const reason=prompt('Dôvod schválenia / overenie cestovných dokladov (min. 8 znakov):');if(!reason||reason.length<8)return;try{await api('/api/travel/'+id+'/approve',{method:'POST',body:JSON.stringify({reason})});toast('Vyúčtovanie schválené');travelView()}catch(e){toast(e.message,true)}};
  const cancel=$('#travelCancel');if(cancel)cancel.onclick=async()=>{const reason=prompt('Dôvod zrušenia (min. 8 znakov):');if(!reason||reason.length<8)return;try{await api('/api/travel/'+id+'/cancel',{method:'POST',body:JSON.stringify({reason})});toast('Cesta zrušená');travelView()}catch(e){toast(e.message,true)}};
  $('#travelDetails').scrollIntoView({behavior:'smooth',block:'start'});
 };
 document.querySelectorAll('[data-trip-detail]').forEach(x=>x.onclick=()=>details(Number(x.dataset.tripDetail)));
}
async function mealsView(){
 const period=localDate().slice(0,7);
 $('#content').innerHTML='<div class="panel"><div class="section-top"><div><h3>Stravovacie lístky a nárok na stravu</h3><p class="muted">Každý zamestnanec a deň · podmienka viac ako 4 hodiny práce · pracovné cesty osobitne</p></div><div class="actions"><input id="mealPeriod" type="month" value="'+period+'"><button id="mealLoad" class="primary">Prepočítať</button><button id="mealExport" class="secondary">⇩ Export CSV</button></div></div><div id="mealOverview"></div></div><div class="panel"><h3>Právne pravidlá a výnimky</h3><p>Bežný príspevok za pracovný deň a stravné počas pracovnej cesty sa posudzujú samostatne. Pri pracovnej ceste môže bežný nárok vzniknúť, ak zamestnanec na pravidelnom pracovisku odpracoval viac ako štyri hodiny. Rozvrh dlhší ako 11 hodín môže viesť k ďalšiemu príspevku, ale nie automaticky.</p><div class="notice">Tento prehľad nevyhodnocuje individuálne rozšírenie nároku podľa interného predpisu BID napríklad počas dovolenky alebo iných prekážok. Tieto dni vyžadujú HR kontrolu.</div></div>';
 const load=async()=>{const [year,month]=$('#mealPeriod').value.split('-').map(Number);try{
 const data=await api('/api/meals/month?year='+year+'&month='+month);
 const labels={eligible:'Nárok',not_eligible:'Bez nároku',requires_regular_workplace_review:'Preveriť pracovisko',travel_allowance_only:'Stravné na ceste',travel_details_missing:'Doplniť cestu'};
 const table=data.employees.map(p=>'<tr><td><button class="gr-name" data-meal-person="'+p.employee_id+'">'+esc(p.name)+'</button></td><td>'+p.meal_ticket_days+'</td><td>'+euroTravel(p.trip_meal_eur)+'</td><td>'+p.days.filter(d=>d.meal_ticket_status==='requires_regular_workplace_review'||d.meal_ticket_status==='travel_details_missing').length+'</td><td><button class="secondary mini" data-meal-person="'+p.employee_id+'">Denný detail</button></td></tr>').join('');
 $('#mealOverview').innerHTML='<div class="travel-kpis"><div class="gr-stat"><span>Nároky na lístok</span><strong>'+data.total_tickets+'</strong><small>Počet dní so splnenou podmienkou</small></div><div class="gr-stat"><span>Stravné na cestách</span><strong>'+euroTravel(data.travel_meals_eur)+'</strong><small>Zoznam schválených ciest</small></div><div class="gr-stat"><span>Zamestnanci</span><strong>'+data.employees.length+'</strong><small>Aktívni v mesiaci</small></div></div><div class="scroll"><table><thead><tr><th>Zamestnanec</th><th>Dni s nárokom</th><th>Stravné z ciest</th><th>Na preverenie</th><th>Akcie</th></tr></thead><tbody>'+table+'</tbody></table></div><div id="mealDailyDetails"></div><p class="subtle">'+esc(data.note)+'</p>';
 document.querySelectorAll('[data-meal-person]').forEach(el=>el.onclick=()=>{
  const emp=data.employees.find(x=>x.employee_id===Number(el.dataset.mealPerson));if(!emp)return;
  const detail=emp.days.map(d=>'<tr><td>'+esc(d.day)+'</td><td>'+groupReportHour(d.worked_minutes)+'</td><td>'+esc(labels[d.meal_ticket_status]||d.meal_ticket_status)+'</td><td>'+(d.meal_ticket_eligible?'✓ 1':'—')+'</td><td>'+euroTravel(d.trip_meal_eur)+'</td><td>'+euroTravel(d.ticket_min_value_eur)+'</td><td>'+euroTravel(d.employer_min_eur)+'</td></tr>').join('');
  $('#mealDailyDetails').innerHTML='<div class="panel"><h3>Denný prehľad · '+esc(emp.name)+'</h3><div class="scroll"><table><thead><tr><th>Deň</th><th>Odpracované</th><th>Stav</th><th>Lístok</th><th>Stravné na ceste</th><th>Min. poukážka</th><th>Min. príspevok zamestnávateľa</th></tr></thead><tbody>'+detail+'</tbody></table></div></div>';
  $('#mealDailyDetails').scrollIntoView({behavior:'smooth',block:'start'});
 });
 }catch(e){$('#mealOverview').innerHTML='<div class="error">'+esc(e.message)+'</div>';toast(e.message,true)}};
 $('#mealLoad').onclick=load;
 $('#mealExport').onclick=async()=>{const [y,m]=$('#mealPeriod').value.split('-').map(Number);try{await fetchProtectedFile('/api/meals/month.csv?year='+y+'&month='+m,'bid_stravne_'+y+'_'+String(m).padStart(2,'0')+'.csv');toast('Mesačné stravovanie exportované')}catch(e){toast(e.message,true)}};
 await load();
}

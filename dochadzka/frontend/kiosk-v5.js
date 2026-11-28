/* BID kiosk v5: individual device secrets, encrypted offline queue, deduplicated replay. */
const $ = selector => document.querySelector(selector);
const storeName='bid-terminal-encrypted-queue-v1';
let cfg={id:Number(sessionStorage.getItem('bid_device_id')||0),key:sessionStorage.getItem('bid_device_key')||''};
let busy=false,mode='auto',syncing=false;
function clock(){const n=new Date();$('#clock').textContent=n.toLocaleTimeString('sk-SK',{hour:'2-digit',minute:'2-digit'});$('#date').textContent=n.toLocaleDateString('sk-SK',{dateStyle:'full'})}
clock();setInterval(clock,1000);
function message(text,good=false){$('#feedback').className='flash '+(good?'ok':'bad');$('#feedback').textContent=text;setTimeout(()=>{if($('#feedback').textContent===text)$('#feedback').textContent=''},7000)}
function headers(){return {'Content-Type':'application/json','X-Device-Id':String(cfg.id),'X-Device-Key':cfg.key}}
function dbOpen(){return new Promise((resolve,reject)=>{const req=indexedDB.open(storeName,1);req.onupgradeneeded=()=>req.result.createObjectStore('events',{keyPath:'event_id'});req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
async function dbAction(mode,fn){
 const db=await dbOpen();
 return new Promise((resolve,reject)=>{
  const tx=db.transaction('events',mode),store=tx.objectStore('events');
  const req=fn(store);
  req.onsuccess=()=>resolve(req.result);
  req.onerror=()=>reject(req.error);
  tx.oncomplete=()=>db.close();tx.onerror=()=>db.close();
 });
}
async function offlineKey(){
 if(!cfg.key)throw Error('Chýba kľúč terminálu');
 const bytes=new TextEncoder().encode(cfg.key);
 const digest=await crypto.subtle.digest('SHA-256',bytes);
 return crypto.subtle.importKey('raw',digest,{name:'AES-GCM'},false,['encrypt','decrypt']);
}
async function encryptRecord(record){
 const iv=crypto.getRandomValues(new Uint8Array(12));
 const key=await offlineKey();
 const encoded=new TextEncoder().encode(JSON.stringify(record));
 const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv},key,encoded);
 return {event_id:record.event_id,created_at:record.occurred_at,iv:Array.from(iv),encrypted:Array.from(new Uint8Array(encrypted))};
}
async function decryptRecord(record){
 const key=await offlineKey();
 const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:new Uint8Array(record.iv)},key,new Uint8Array(record.encrypted));
 return JSON.parse(new TextDecoder().decode(plain));
}
async function queueCount(){const all=await dbAction('readonly',store=>store.getAll());$('#queueCount').textContent=all.length;return all}
async function enqueue(record){
 const all=await queueCount();if(all.length>=500)throw Error('Fronta je plná. Kontaktuj správcu.');
 const encrypted=await encryptRecord(record);
 await dbAction('readwrite',store=>store.put(encrypted));await queueCount();
}
async function request(path,data){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),9000);
 try{
  const response=await fetch(path,{method:'POST',headers:headers(),body:JSON.stringify(data),signal:controller.signal,cache:'no-store'});
  const body=await response.json().catch(()=>({detail:'Neznáma odpoveď'}));
  if(!response.ok){
    const err=Error(typeof body.detail==='string'?body.detail:'Server odmietol požiadavku');
    err.server=true;err.status=response.status;throw err;
  }
  return body;
 }finally{clearTimeout(timeout)}
}
async function flushQueue(){
 if(syncing||!cfg.id||!cfg.key)return;
 syncing=true;const original=$('#syncBtn').textContent;$('#syncBtn').disabled=true;
 try{
  const all=await queueCount();
  for(const entry of all){
   let body;
   try{body=await decryptRecord(entry)}catch{message('Niektorá fronta sa nedá dešifrovať. Over kľúč zariadenia.');break}
   const age=Date.now()-new Date(body.occurred_at).getTime();
   if(age>72*3600*1000){message('Záznam starší než 72 hodín vyžaduje ručnú kontrolu HR.');break}
   try{
    await request('/api/devices/punch',body);
    await dbAction('readwrite',store=>store.delete(entry.event_id));
   }catch(error){
    // Unauthorized, bad UID and old records MUST remain for manual resolution.
    if(error.server)message('Neodoslaná udalosť: '+error.message);
    break;
   }
  }
  await queueCount();
 }catch(error){message('Synchronizácia zlyhala: '+error.message)}
 finally{syncing=false;$('#syncBtn').disabled=false;$('#syncBtn').textContent=original}
}
$('#configure').onclick=()=>{
 const id=prompt('ID terminálu z administrácie BID',String(cfg.id||''));if(!id)return;
 const key=prompt('Tajný kľúč terminálu (nikdy ho neukladaj do GitHubu):');if(!key)return;
 cfg={id:Number(id),key:key.trim()};
 sessionStorage.setItem('bid_device_id',String(cfg.id));
 sessionStorage.setItem('bid_device_key',cfg.key);
 message('Terminál nastavený. Kľúč je platný len pre toto zariadenie.',true);
 $('#uid').focus();flushQueue();
};
$('#syncBtn').onclick=flushQueue;
document.querySelectorAll('[data-mode]').forEach(btn=>btn.onclick=()=>{
 mode=btn.dataset.mode;
 document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('chosen',x.dataset.mode===mode));
 $('#uid').focus();
});
function beep(ok){
 try{
  const ctx=new (window.AudioContext||window.webkitAudioContext)();
  const osc=ctx.createOscillator(),gain=ctx.createGain();
  osc.connect(gain);gain.connect(ctx.destination);
  osc.type='sine';osc.frequency.value=ok?820:225;gain.gain.value=0.1;
  osc.start();osc.stop(ctx.currentTime+0.12);osc.onended=()=>ctx.close()
 }catch{}
}
async function scan(uid){
 if(busy)return;if(!cfg.key||!cfg.id){message('Najprv nastav terminál a jeho kľúč.');return}
 busy=true;
 const occurred_at=new Date().toISOString();
 let kind=mode==='auto'?'in':mode, employee=null;
 try{
  // Resolve automatic in/out only if server can be reached.
  if(mode==='auto'){
   try{
    const identified=await request('/api/devices/identify',{uid});
    kind=identified.suggested_kind;employee=identified.name;
   }catch(error){
    if(error.server){message(error.message);beep(false);return}
    message('Server je nedostupný. Pre offline záznam vyber Príchod alebo Odchod.');return;
   }
  }
  const record={uid,kind,event_id:crypto.randomUUID(),occurred_at};
  try{
   const result=await request('/api/devices/punch',record);
   message((employee||result.employee||'Dochádzka')+' · '+(kind==='in'?'Príchod':kind==='out'?'Odchod':'Prestávka')+' zaznamenaný',true);
   beep(true);flushQueue();
  }catch(error){
   if(error.server){message(error.message);beep(false);return}
   await enqueue(record);
   message('Sieť je nedostupná. Udalosť je ZAŠIFROVANÁ vo fronte a odošle sa po pripojení.',true);
   beep(true);
  }
 }catch(error){message(error.message);beep(false)}
 finally{busy=false;$('#uid').focus()}
}
$('#nfcStart').onclick=async()=>{
 if(!('NDEFReader' in window)){message('Web NFC vyžaduje podporovaný Android Chrome a NDEF čip. Použi USB čítačku.');return}
 if(!cfg.id||!cfg.key){message('Najprv nastav terminál a jeho kľúč.');return}
 try{
  const reader=new NDEFReader();await reader.scan();
  message('NFC je pripravené. Prilož NDEF čip k telefónu alebo tabletu.',true);
  reader.onreading=ev=>{
   const uid=(ev.serialNumber||'').trim().toUpperCase();
   if(!uid){message('Čip neodovzdal sériové číslo. Použi RFID čítačku.');return}
   scan(uid);
  };
  reader.onreadingerror=()=>message('NFC čip sa nepodarilo prečítať.');
  $('#nfcStart').disabled=true;$('#nfcStart').textContent='NFC aktívne';
 }catch(error){message('NFC sa nepodarilo aktivovať: '+error.message)}
};
$('#uid').addEventListener('keydown',e=>{if(e.key!=='Enter')return;e.preventDefault();const uid=$('#uid').value.trim();$('#uid').value='';if(uid)scan(uid)});
window.addEventListener('online',flushQueue);
setInterval(flushQueue,45000);
queueCount().catch(()=>message('Tento prehliadač nepodporuje offline frontu.'));
$('#uid').focus();
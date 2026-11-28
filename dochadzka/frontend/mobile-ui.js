// BID Dochádzka — touch-friendly, role-aware mobile navigation.
// The existing desktop menu remains the source of truth for permissions and routes.
(()=>{
  const $=selector=>document.querySelector(selector);
  const dock=$('#mobileBottomNav'),overlay=$('#mobileMoreOverlay'),list=$('#mobileMoreList'),search=$('#mobileMoreSearch');
  if(!dock||!overlay||!list)return;
  const title={dashboard:'Prehľad',organization:'Organizácia',employees:'Zamestnanci',requests:'Žiadosti',shifts:'Rozpis zmien',travel:'Služobné cesty',meals:'Stravovanie',approvalCenter:'Kontrola',groupReport:'Hromadný výkaz',reports:'Výkazy',corrections:'Opravy záznamov',quality:'Kontrola údajov',payroll:'Uzávierka',exports:'Exporty',legal:'Zákonné nároky',legalMonitor:'Legislatíva',holidays:'Sviatky SR',terminal:'Terminály',accounts:'Môj účet'};
  const icons={
    dashboard:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    employees:'<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2"/><path d="M16 6a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5"/>',
    requests:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-12 5 3 3 5-5"/>',
    reports:'<path d="M5 3h10l4 4v14H5z"/><path d="M14 3v5h5M8 17l3-3 2 2 3-4"/>',
    shifts:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
    accounts:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    more:'<path d="M4 7h16M4 12h16M4 17h16"/>'
  };
  const pict=key=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+(icons[key]||icons.reports)+'</svg>';
  const allLinks=()=>[...document.querySelectorAll('.sidebar nav .nav')].filter(el=>!el.classList.contains('hidden'));
  const current=()=>document.querySelector('.sidebar nav .nav.active')?.dataset.view||'dashboard';
  let lastKeys='';
  function closeMenu(){overlay.classList.add('hidden');document.body.classList.remove('mobile-menu-open');$('#mobileMoreToggle')?.setAttribute('aria-expanded','false');}
  function openMenu(){buildMenu();search.value='';filterMenu();overlay.classList.remove('hidden');document.body.classList.add('mobile-menu-open');$('#mobileMoreToggle')?.setAttribute('aria-expanded','true');setTimeout(()=>search.focus(),50)}
  async function go(name){closeMenu();if(typeof window.navigate==='function'){window.scrollTo({top:0,behavior:'auto'});await window.navigate(name);schedule()}}
  function buildMenu(){
    list.innerHTML=allLinks().map(el=>{
      const key=el.dataset.view;
      return '<button type="button" class="mobile-more-item'+(key===current()?' active':'')+'" data-mobile-menu-view="'+key+'">'+pict(key)+'<span>'+(title[key]||key)+'</span></button>';
    }).join('');
  }
  function filterMenu(){
    const term=search.value.toLocaleLowerCase('sk').trim();
    [...list.querySelectorAll('[data-mobile-menu-view]')].forEach(b=>b.hidden=!!term&&!b.textContent.toLocaleLowerCase('sk').includes(term));
  }
  function render(){
    const links=allLinks().map(el=>el.dataset.view);
    const chosen=['dashboard','employees','requests','reports','shifts','accounts'].filter(k=>links.includes(k)).slice(0,4);
    const keys=chosen.join(',');
    const selected=current();
    if(keys!==lastKeys||!dock.children.length){
      dock.innerHTML=chosen.map(key=>'<button type="button" class="mobile-tab" data-mobile-tab="'+key+'">'+pict(key)+'<span>'+(title[key]||key)+'</span></button>').join('')+'<button type="button" class="mobile-tab" id="mobileMoreToggle" aria-expanded="false" aria-haspopup="dialog">'+pict('more')+'<span>Viac</span></button>';
      lastKeys=keys;
    }
    [...dock.querySelectorAll('[data-mobile-tab]')].forEach(b=>{
      const active=b.dataset.mobileTab===selected;
      b.classList.toggle('active',active);
      if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
    });
    const more=$('#mobileMoreToggle');
    if(more)more.classList.toggle('active',!chosen.includes(selected));
  }
  let pending=false;
  function schedule(){if(pending)return;pending=true;queueMicrotask(()=>{pending=false;render();adaptTables()})}
  function adaptTables(){
    const route=current();
    if(route!=='dashboard'&&route!=='requests')return;
    document.querySelectorAll('#content .scroll > table').forEach(t=>{
      if(t.classList.contains('mobile-card-table')||t.classList.contains('gr-grid')||t.classList.contains('hr-table'))return;
      const heads=[...t.querySelectorAll('thead th')].map(h=>h.textContent.trim());
      if(heads.length<3||heads.length>8||t.querySelector('tbody td[colspan]'))return;
      const rows=[...t.querySelectorAll('tbody tr')];
      if(!rows.length)return;
      rows.forEach(row=>[...row.querySelectorAll(':scope > td')].forEach((cell,i)=>cell.setAttribute('data-label',heads[i]||'Údaj')));
      t.classList.add('mobile-card-table');
      t.closest('.scroll')?.classList.add('mobile-card-scroll');
    });
  }
  dock.addEventListener('click',e=>{
    const button=e.target.closest('button');
    if(!button)return;
    if(button.id==='mobileMoreToggle'){overlay.classList.contains('hidden')?openMenu():closeMenu();return;}
    if(button.dataset.mobileTab)void go(button.dataset.mobileTab);
  });
  list.addEventListener('click',e=>{const b=e.target.closest('[data-mobile-menu-view]');if(b)void go(b.dataset.mobileMenuView)});
  search.addEventListener('input',filterMenu);
  $('#mobileMoreClose')?.addEventListener('click',closeMenu);
  $('#mobileLogout')?.addEventListener('click',()=>{closeMenu();if(typeof window.logout==='function')window.logout()});
  overlay.addEventListener('click',e=>{if(e.target===overlay)closeMenu()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu()});
  new MutationObserver(schedule).observe($('.sidebar nav'),{subtree:true,attributes:true,attributeFilter:['class']});
  new MutationObserver(schedule).observe($('#content'),{childList:true,subtree:true});
  new MutationObserver(schedule).observe($('#app'),{attributes:true,attributeFilter:['class']});
  render();adaptTables();
})();

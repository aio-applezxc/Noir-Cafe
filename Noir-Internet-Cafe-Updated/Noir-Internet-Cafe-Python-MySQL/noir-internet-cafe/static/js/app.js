/* NOIR browser client. Accounts and business data are read/written through the Python API. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths = {
    grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    monitor:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
    receipt:'<path d="M5 3h14v18l-3-2-4 2-4-2-3 2zM8 8h8M8 12h8"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    wallet:'<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 9V5a2 2 0 0 1 2-2h13m-2 10h5"/>',
    search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/>',
    close:'<path d="M5 5l14 14M19 5 5 19"/>',
    users:'<circle cx="9" cy="8" r="3"/><path d="M2 20v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2m2-13a3 3 0 0 1 0 6m1 7h3v-2a5 5 0 0 0-4-5"/>',
    activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2"/>',
    trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
    print:'<path d="M6 8V3h12v5M6 17H3V8h18v9h-3M6 14h12v7H6zM17 11h1"/>'
  };
  const icon = (name, cls='') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
  const money = value => new Intl.NumberFormat('en-PH', {style:'currency',currency:'PHP'}).format(Number(value || 0));
  const duration = minutes => minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2,'0')}m`;
  const labelRole = value => value === 'administrator' ? 'Administrator' : 'Member';
  const initials = name => String(name).split(/\s+/).filter(Boolean).slice(0,2).map(p => p[0]).join('').toUpperCase();
  let user=null, csrf='', timezone='Asia/Manila', authMode='login', ready=false, allowRegistration=true;
  let page='Overview', stationFilter='all', search='', accountSearch='', invoiceFilter='all', invoicePage=1;
  let data={stations:[],sessions:[],bookings:[],finances:{}}, accounts=[], invoices=[], hasMore=false, activity=[];
  let assets=[], maintenance=[];
  let clockOffset=0, toastTimer, modalReturnFocus=null, busyRefresh=false, refreshAgain=false, runningRefresh=null, submitPending=false;
  const isAdmin = () => user?.role === 'administrator';
  const stationById = id => data.stations.find(s => s.id === Number(id));
  const available = () => data.stations.filter(s => s.status === 'available');
  const elapsed = value => Math.max(0, Math.floor((Date.now()+clockOffset-new Date(value).getTime())/60000));
  const remainingSeconds = deadline => Math.max(0, Math.ceil((new Date(deadline).getTime()-Date.now()-clockOffset)/1000));
  const countdown = deadline => {
    if (!deadline) return 'Not set';
    const seconds=remainingSeconds(deadline);
    return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,'0')).join(':');
  };
  const sessionMinutes = live => Math.max(1,Math.ceil((Math.min(Date.now()+clockOffset,live.planned_end_at?new Date(live.planned_end_at).getTime():Infinity)-new Date(live.started_at).getTime())/60000));
  const pageLabel = name => !isAdmin()?({Overview:'My session',Stations:'Available stations',Billing:'My billing'}[name]||name):name;
  const time = value => value ? new Date(value).toLocaleString('en-PH',{timeZone:timezone,month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}) : '—';
  const button = (label, action, dark=false, glyph='plus') => `<button class="btn ${dark?'dark':''}" data-action="${action}">${icon(glyph)}${label}</button>`;
  const empty = (title, description, action='') => `<div class="empty-state"><div class="empty-icon">${icon('monitor')}</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;

  async function api(path, method='GET', body) {
    let response;
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    try {
      response = await fetch(`/api${path}`, {method, credentials:'same-origin',cache:'no-store',signal:controller.signal,
        headers: {'Accept':'application/json', ...(method !== 'GET' ? {'Content-Type':'application/json','X-CSRF-Token':csrf}: {})},
        ...(body !== undefined ? {body:JSON.stringify(body)} : {})});
    } catch (_) { throw new Error('Cannot reach NOIR. Check your connection and try again.'); }
    finally {clearTimeout(timeout);}
    let value;
    try { value = await response.json(); } catch (_) { throw new Error('The server returned an unexpected response. Please try again.'); }
    if (value.csrf_token) csrf = value.csrf_token;
    if (!response.ok) {
      if (response.status === 401 && user && path !== '/auth/login') {
        user=null; closeModal(true); showAuth();
      }
      const error = new Error(value.error || 'The request could not be completed.');
      error.status = response.status;
      throw error;
    }
    return value;
  }
  function toast(message) {
    $('toastRoot').innerHTML=`<div class="toast">${esc(message)}</div>`;
    clearTimeout(toastTimer); toastTimer=setTimeout(() => $('toastRoot').replaceChildren(),4500);
  }
  function setAuthMode(mode) {
    authMode = mode==='register' && allowRegistration ? 'register' : 'login';
    const registering=authMode==='register';
    $('authTitle').textContent=registering?'Make yourself at home.':'Welcome back.';
    $('authDescription').textContent=registering?'Create your NOIR member account.':'Sign in to your account to continue.';
    $('registerNameField').hidden=!registering; $('authName').required=registering;
    $('confirmPasswordField').hidden=!registering; $('authConfirm').required=registering;
    $('passwordHelp').hidden=!registering;
    $('authPassword').minLength=registering?12:1;
    $('authPassword').autocomplete=registering?'new-password':'current-password';
    document.querySelectorAll('[data-auth-mode]').forEach(b=>b.classList.toggle('selected',b.dataset.authMode===authMode));
    $('authTabs').hidden=!allowRegistration;
    $('authSubmit').textContent=registering?'Create account':'Sign in';
    $('authError').hidden=true; $('authSuccess').hidden=true;
  }
  function showAuth() {
    $('appScreen').hidden=true; $('authScreen').hidden=false;
    $('content').replaceChildren(); $('printArea').replaceChildren();
    $('profileButton').replaceChildren(); $('navigation').replaceChildren();
    $('authForm').reset(); setAuthMode('login'); $('authSubmit').disabled=!ready;
    $('authEmail').focus();
    accounts=[]; invoices=[]; activity=[]; data={stations:[],sessions:[],bookings:[],finances:{}};
  }
  async function boot() {
    $('authSubmit').disabled=true;
    try {
      const info=await api('/auth/me');
      ready=true; user=info.user; allowRegistration=info.allow_registration;
      timezone=info.timezone; clockOffset=new Date(info.server_time).getTime()-Date.now();
      if (user) await showWorkspace(); else showAuth();
    } catch (error) {
      ready=false; $('authScreen').hidden=false; $('appScreen').hidden=true;
      $('authError').textContent=error.message; $('authError').hidden=false;
      $('authSubmit').textContent='Retry connection'; $('authSubmit').disabled=false;
    }
  }
  $('authForm').addEventListener('submit', async event => {
    event.preventDefault(); if (!ready) { await boot(); return; }
    $('authError').hidden=true; $('authSuccess').hidden=true;
    const body={email:$('authEmail').value,password:$('authPassword').value};
    if (authMode==='register' && body.password!==$('authConfirm').value) {
      $('authError').textContent='Passwords do not match.'; $('authError').hidden=false; return;
    }
    $('authSubmit').disabled=true;
    try {
      if (authMode==='register') {
        body.name=$('authName').value;
        const response=await api('/auth/register','POST',body);
        setAuthMode('login'); $('authPassword').value=''; $('authConfirm').value='';
        $('authSuccess').textContent=response.message; $('authSuccess').hidden=false;
        $('authPassword').focus();
      } else {
        const response=await api('/auth/login','POST',body); user=response.user;
        $('authForm').reset(); page='Overview'; await showWorkspace();
      }
    } catch (error) { $('authError').textContent=error.message; $('authError').hidden=false; }
    finally { $('authSubmit').disabled=false; }
  });

  async function showWorkspace() {
    $('authScreen').hidden=true; $('appScreen').hidden=false;
    $('footerTimezone').textContent=`Philippine pesos · ${timezone}`;
    $('content').innerHTML='<div class="loading">Loading your café…</div>';
    renderNavigation(); await refresh();
  }
  function renderNavigation() {
    const links=isAdmin()?[['Overview','grid'],['Stations','monitor'],['Bookings','calendar'],['Billing','receipt'],['Inventory','monitor'],['Maintenance','activity'],['Reports','receipt'],['Accounts','users'],['Activity','activity']]:[['Overview','clock'],['Stations','monitor'],['Billing','receipt']];
    $('navigation').innerHTML=`<div class="nav-caption">${isAdmin()?'Management':'Your café'}</div>`+links.map(([name,glyph])=>`<button class="nav-item ${page===name?'active':''}" data-nav="${name}" aria-label="${pageLabel(name)}" ${page===name?'aria-current="page"':''}>${icon(glyph)}<span>${pageLabel(name)}</span>${name==='Bookings'?`<span class="count">${data.bookings.length}</span>`:''}</button>`).join('');
    $('crumb').textContent=pageLabel(page);
    $('date').textContent=new Date().toLocaleDateString('en-PH',{timeZone:timezone,weekday:'short',month:'short',day:'numeric',year:'numeric'});
    $('profileButton').innerHTML=`<span class="avatar">${esc(initials(user.name))}</span><span>${esc(user.name)}<small>${labelRole(user.role)}</small></span>`;
    $('mobileProfile').textContent=initials(user.name);
  }
  async function ensureAccounts(force=false) {
    if (isAdmin() && (!accounts.length || force)) accounts=(await api('/accounts')).accounts;
  }
  async function refresh() {
    if (!user) return;
    if (busyRefresh) {refreshAgain=true;return runningRefresh;}
    busyRefresh=true;
    runningRefresh=(async()=>{
      try {
        do {
          refreshAgain=false; const requestedPage=page;
          const response=await api('/dashboard');
          if (!user) return;
          data=response; clockOffset=new Date(response.server_time).getTime()-Date.now();
          $('connectionError').hidden=true; $('connectionStatus').textContent='Connected';
          $('syncLabel').textContent=`Updated ${new Date().toLocaleTimeString('en-PH',{hour:'numeric',minute:'2-digit'})}`;
          if (requestedPage==='Accounts') await ensureAccounts(true);
          if (requestedPage==='Billing') {
            const response=await api(`/invoices?page=${invoicePage}&status=${invoiceFilter}`);
            invoices=response.invoices; hasMore=response.has_more;
          }
          if (isAdmin() && ['Inventory','Maintenance','Reports'].includes(requestedPage)) assets=(await api('/assets')).assets;
          if (isAdmin() && requestedPage==='Maintenance') maintenance=(await api('/maintenance')).maintenance;
          if (requestedPage==='Activity') activity=(await api('/activity')).activity;
          if (user && requestedPage===page) render(); else refreshAgain=Boolean(user);
        } while (refreshAgain && user);
      } catch (error) {
        $('connectionError').textContent=error.message+' Displayed information may be out of date.';
        $('connectionError').hidden=false; $('connectionStatus').textContent='Connection interrupted';
      } finally {busyRefresh=false;}
    })();
    return runningRefresh;
  }
  async function navigate(name) {
    if (!user) return;
    if (!['Overview','Stations','Bookings','Billing','Accounts','Activity','Inventory','Maintenance','Reports','Profile'].includes(name)) return;
    if (['Bookings','Accounts','Activity','Inventory','Maintenance','Reports'].includes(name) && !isAdmin()) return;
    page=name; search=''; stationFilter='all'; invoicePage=1;
    renderNavigation(); render(); window.scrollTo({top:0,behavior:'instant'});
    // A concurrent refresh re-reads the current page after receiving its dashboard result.
    await refresh();
  }
  function heading(title,description,actions='') {
    return `<div class="intro"><div><div class="eyebrow">${isAdmin()?'Café management':'Member workspace'} / ${esc(pageLabel(page))}</div><h1>${title}</h1><p>${description}</p></div><div class="actions">${actions}</div></div>`;
  }
  function controls() {
    return isAdmin()?button('New booking','booking',false,'calendar')+button('Start session','start',true):'';
  }
  function metrics() {
    const count=data.stations.filter(s=>s.status==='occupied').length;
    const entries=[['Total stations',data.stations.length,'Across your café floor','monitor'],['Active sessions',count,'In use right now','clock'],['Available PCs',available().length,'Ready for walk-ins','grid'],["Today’s revenue",money(data.finances.revenue),`${data.finances.payments||0} payments recorded`,'wallet']];
    return `<div class="metrics">${entries.map(([title,value,foot,glyph])=>`<div class="metric"><div class="metric-head">${title}${icon(glyph)}</div><div class="metric-number ${typeof value==='string'?'money-number':''}">${typeof value==='number'?String(value).padStart(2,'0'):value}</div><div class="metric-foot">${foot}</div></div>`).join('')}</div>`;
  }
  function stationCard(s,editable=false) {
    const label={occupied:'In use',reserved:'Reserved',available:'Available',maintenance:'Maintenance'}[s.status];
    const note=s.session?`${s.session.customer_name} · ${duration(elapsed(s.session.started_at))}`:s.booking?`Reserved · ${s.booking.customer_name}`:s.status==='available'?`${money(s.hourly_rate)} / hour`:s.status==='maintenance'?'Temporarily unavailable':label;
    const canAct=isAdmin();
    if (!isAdmin()) return `<article class="station available readonly"><div class="station-top">${icon('monitor','station-icon')}<span class="status-pill">Available</span></div><div class="station-id">${esc(s.name)}</div><div class="station-note">${money(s.hourly_rate)} / hour</div></article>`;
    return `<div class="station-card-wrap"><button class="station ${s.status==='occupied'?'busy':s.status}" data-station="${s.id}" ${canAct?'':'disabled'} aria-label="${esc(s.name)}, ${label}"><div class="station-top">${icon('monitor','station-icon')}<span class="status-pill">${label}</span></div><div class="station-id">${esc(s.name)}</div><div class="station-note">${esc(note)}</div></button>${editable&&isAdmin()?`<div class="station-actions"><button class="station-edit" data-edit-station="${s.id}">Edit station ↗</button><button class="station-delete" data-delete-station="${s.id}" aria-label="Delete ${esc(s.name)}">${icon('trash')}Delete</button></div>`:''}</div>`;
  }
  function stationGrid(full=false) {
    const rows=data.stations.filter(s=>(stationFilter==='all'||s.status===stationFilter)&&`${s.name} ${s.session?.customer_name||''} ${s.booking?.customer_name||''}`.toLowerCase().includes(search.toLowerCase()));
    return `<div class="stations ${full?'full-stations':''}">${rows.map(s=>stationCard(s,full)).join('')||empty(data.stations.length?'No matching stations.':'Your floor starts here.',data.stations.length?'Try another search or filter.':isAdmin()?'Add your first computer and set its hourly rate.':'Your Administrator is setting up the café.',isAdmin()&&!data.stations.length?button('Add station','add-station',true):'')}</div>`;
  }
  function livePanel() {
    return `<div class="panel"><div class="panel-header"><div><h2 class="panel-title">${isAdmin()?'Live sessions':'Your sessions'}</h2><p class="panel-sub">Time well spent</p></div><button class="link" data-nav="Stations">View floor</button></div><div class="session-list">${data.sessions.slice(0,5).map(s=>`<div class="session-row"><span class="session-avatar">${esc(initials(s.customer_name))}</span><span class="session-info"><b>${esc(s.customer_name)}</b><small>${esc(s.station_name)} · ${money(s.hourly_rate)}/hr</small></span><span class="session-time">${duration(elapsed(s.started_at))}</span></div>`).join('')||'<div class="empty">No active sessions.</div>'}</div></div>`;
  }
  function bookingsTable(limit) {
    const rows=limit?data.bookings.slice(0,limit):data.bookings;
    return `<div class="panel table-wrap"><table class="table"><thead><tr><th>Customer</th><th>Station</th><th>Arrival</th><th>Status</th><th>Actions</th></tr></thead><tbody>${rows.map(b=>`<tr><td><strong>${esc(b.customer_name)}</strong></td><td>${esc(b.station_name)}</td><td>${time(b.scheduled_at)}</td><td><span class="table-badge">Reserved</span></td><td>${isAdmin()?`<button class="link" data-checkin="${b.id}">Check in</button> &nbsp; `:''}<button class="link" data-cancel-booking="${b.id}">Cancel</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-cell">No upcoming reservations.</td></tr>'}</tbody></table></div>`;
  }
  function billingTable() {
    return `<div class="panel table-wrap"><table class="table"><thead><tr><th>Invoice</th><th>Customer / station</th><th>Duration</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody>${invoices.map(i=>`<tr><td><strong>#${String(i.id).padStart(5,'0')}</strong><div class="hint">${time(i.created_at)}</div></td><td><strong>${esc(i.customer_name)}</strong><div class="hint">${esc(i.station_name)}</div></td><td>${duration(i.minutes)}</td><td><strong>${money(i.amount)}</strong></td><td><span class="table-badge ${i.payment_id?'':'dark'}">${i.payment_id?'Paid':'Unpaid'}</span></td><td><button class="link" data-invoice="${i.id}">${!i.payment_id&&isAdmin()?'Record payment':'View invoice'}</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty-cell">No invoices in this view.</td></tr>'}</tbody></table></div><div class="page-controls"><button class="btn small" data-invoice-page="${invoicePage-1}" ${invoicePage<=1?'disabled':''}>Previous</button><span>Page ${invoicePage}</span><button class="btn small" data-invoice-page="${invoicePage+1}" ${hasMore?'':'disabled'}>Next</button></div>`;
  }
  function accountsTable() {
    const rows=accounts.filter(a=>`${a.name} ${a.email} ${labelRole(a.role)}`.toLowerCase().includes(accountSearch.toLowerCase()));
    return `<div class="panel table-wrap"><table class="table"><thead><tr><th>Name</th><th>Email address</th><th>Role</th><th>Status</th><th>Action</th></tr></thead><tbody>${rows.map(a=>`<tr><td><strong>${esc(a.name)}</strong></td><td>${esc(a.email)}</td><td>${labelRole(a.role)}</td><td><span class="table-badge ${a.active?'':'dark'}">${a.active?'Active':'Disabled'}</span></td><td><button class="link" data-account="${a.id}">Manage</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-cell">No matching accounts.</td></tr>'}</tbody></table></div>`;
  }
  function memberHelp() {
    return `<div class="member-help">${icon('users')}<span>For bookings, session time, or payments, please speak with the café administrator.</span></div>`;
  }
  function memberStations() {
    return `<section class="panel member-availability"><div class="panel-header"><div><h2 class="panel-title">Ready when you are</h2><p class="panel-sub">Current availability · updated every 15 seconds</p></div><span class="table-badge">${available().length} available</span></div><div class="stations member-stations">${available().map(s=>stationCard(s)).join('')||empty('No stations available','Please check again shortly or ask the administrator for assistance.')}</div></section>`;
  }
  function memberSession(live) {
    return `<section class="time-card"><div class="time-card-head"><div class="eyebrow">CURRENT SESSION · ${esc(live.station_name)}</div>${icon('clock')}</div><h2>Remaining time</h2><span class="remaining-time" role="timer" aria-live="off" data-countdown="${esc(live.planned_end_at||'')}">${countdown(live.planned_end_at)}</span><p class="session-status" data-time-status="${esc(live.planned_end_at||'')}">${live.planned_end_at?`Session ends ${time(live.planned_end_at)}`:'This earlier session has no time limit yet. Ask the administrator to set your remaining time.'}</p><dl class="session-facts"><div><dt>Station</dt><dd>${esc(live.station_name)}</dd></div><div><dt>Hourly rate</dt><dd>${money(live.hourly_rate)}</dd></div><div><dt>Current charge (est.)</dt><dd data-charge="${live.id}">${money(sessionMinutes(live)*Number(live.hourly_rate)/60)}</dd></div></dl></section>`;
  }
  function memberCurrentCharges() {
    if (!data.sessions.length) return '';
    return `<section class="panel member-availability"><div class="panel-header"><div><h2 class="panel-title">Current session charges</h2><p class="panel-sub">Estimates update as you use your station. Final invoices appear when sessions end.</p></div></div><div class="session-list">${data.sessions.map(live=>`<div class="session-row"><span class="session-avatar">${icon('monitor')}</span><span class="session-info"><b>${esc(live.station_name)}</b><small>${money(live.hourly_rate)} / hour</small></span><strong data-charge="${live.id}">${money(sessionMinutes(live)*Number(live.hourly_rate)/60)}</strong></div>`).join('')}</div></section>`;
  }
  function memberOverview() {
    const sessions=data.sessions.length?data.sessions.map(memberSession).join(''):`<section class="time-card"><div class="time-card-head"><div class="eyebrow">YOUR SESSION</div>${icon('clock')}</div><h2>Remaining time</h2><span class="remaining-time">No active session</span><p class="session-status">Your countdown will appear here when the administrator starts a session for your account.</p></section>`;
    return heading(`Welcome, ${esc(user.name.split(' ')[0])}.`,'Your time, station availability, and billing in one place.')+`<div class="member-summary"><div class="member-sessions">${sessions}</div><div class="member-side"><div class="metric"><div class="metric-head">Outstanding balance${icon('receipt')}</div><div class="metric-number money-number">${money(data.finances.outstanding)}</div><div class="metric-foot">Unpaid invoices from completed sessions</div><button class="link" data-nav="Billing">View my billing →</button></div><div class="metric"><div class="metric-head">Available stations${icon('monitor')}</div><div class="metric-number">${String(available().length).padStart(2,'0')}</div><div class="metric-foot">Ready to use at the café</div><button class="link" data-nav="Stations">View available stations →</button></div></div></div>`+memberStations()+memberHelp();
  }
  function updateClocks() {
    document.querySelectorAll('[data-countdown]').forEach(node=>{node.textContent=countdown(node.dataset.countdown);});
    document.querySelectorAll('[data-time-status]').forEach(node=>{if(node.dataset.timeStatus && remainingSeconds(node.dataset.timeStatus)===0) node.textContent='Time complete. Your final invoice will appear after the next update.';});
    document.querySelectorAll('[data-charge]').forEach(node=>{const live=data.sessions.find(s=>s.id===Number(node.dataset.charge));if(live) node.textContent=money(sessionMinutes(live)*Number(live.hourly_rate)/60);});
  }
  function render() {
    if (!user) return;
    renderNavigation(); let html='';
    if (page==='Overview') html=isAdmin()?heading('Your café at a glance.','Welcome back. Here’s what’s happening on your floor.',controls())+metrics()+`<div class="content-grid"><div class="panel"><div class="panel-header"><div><h2 class="panel-title">Station overview</h2><p class="panel-sub">Select a station to manage it</p></div><div class="legend"><span><i class="busy"></i> In use</span><span><i class="free"></i> Available</span><span><i class="reserved"></i> Reserved</span></div></div>${stationGrid()}</div><div class="right-stack">${livePanel()}<div class="outline-card"><div class="eyebrow">AT THE COUNTER</div><h3>Keep the day in balance.</h3><p>${money(data.finances.outstanding)} in unpaid invoices. Review sessions and record payments when received.</p><button class="btn small" data-nav="Billing">Open billing${icon('arrow')}</button></div></div></div><div class="section-head"><h2>Upcoming bookings</h2><button class="link" data-nav="Bookings">See all bookings ${icon('arrow')}</button></div>${bookingsTable(4)}`:memberOverview();
    if (page==='Stations') html=isAdmin()?heading('Stations.','Every station, in one place.',button('Add station','add-station',false,'monitor')+button('Start session','start',true))+metrics()+`<div class="filters">${['all','available','occupied','reserved','maintenance'].map(f=>`<button class="chip ${stationFilter===f?'selected':''}" data-filter="${f}">${f[0].toUpperCase()+f.slice(1)}</button>`).join('')}<div class="search-wrap">${icon('search')}<input class="search" id="stationSearch" placeholder="Search station or customer" aria-label="Search stations" value="${esc(search)}"></div></div><div class="panel" id="stationResults">${stationGrid(true)}</div>`:heading('Available stations.','See which computers are ready to use.')+memberStations()+memberHelp();
    if (page==='Bookings' && isAdmin()) html=heading('Bookings.','Reservations are held until check-in or cancellation.',button('New booking','booking',true,'calendar'))+`<div class="section-head"><h2>Upcoming reservations (${data.bookings.length})</h2></div>`+bookingsTable();
    if (page==='Billing') html=heading(isAdmin()?'Billing.':'My billing.',isAdmin()?'Review invoices and payments recorded at the café.':'Your session charges, invoices, and payment history.')+(!isAdmin()?memberCurrentCharges():'')+`<div class="metrics two"><div class="metric"><div class="metric-head">${isAdmin()?"Today’s revenue":"Your payments today"}${icon('wallet')}</div><div class="metric-number money-number">${money(data.finances.revenue)}</div><div class="metric-foot">${data.finances.payments||0} recorded payments</div></div><div class="metric"><div class="metric-head">Outstanding balance${icon('receipt')}</div><div class="metric-number money-number">${money(data.finances.outstanding)}</div><div class="metric-foot">${isAdmin()?'Awaiting payment':'Completed sessions · pay at the counter'}</div></div></div><div class="filters">${['all','unpaid','paid'].map(f=>`<button class="chip ${invoiceFilter===f?'selected':''}" data-invoice-filter="${f}">${f[0].toUpperCase()+f.slice(1)}</button>`).join('')}</div>`+billingTable();
    if (page==='Accounts') html=heading('Accounts.','Manage the people who use your café.',button('Create account','account',true,'users'))+`<div class="filters account-filter"><div class="search-wrap">${icon('search')}<input class="search" id="accountSearch" placeholder="Search name or email" aria-label="Search accounts" value="${esc(accountSearch)}"></div></div><div id="accountResults">${accountsTable()}</div>`;
    if (page==='Activity') html=heading('Activity.','The latest 100 recorded account and café actions.')+`<div class="panel table-wrap"><table class="table"><thead><tr><th>When</th><th>Administrator / member</th><th>Action</th><th>Details</th></tr></thead><tbody>${activity.map(a=>`<tr><td>${time(a.created_at)}</td><td>${esc(a.actor_name||'Server console')}</td><td><span class="table-badge">${esc(a.action)}</span></td><td class="wrap">${esc(a.detail)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty-cell">No recorded activity.</td></tr>'}</tbody></table></div>`;
    if (isAdmin() && page==='Inventory') html=inventoryPage();
    if (isAdmin() && page==='Maintenance') html=maintenancePage();
    if (isAdmin() && page==='Reports') html=reportsPage();
    if (page==='Profile') html=heading('Your account.','Your NOIR profile and sign-in settings.')+`<div class="panel profile-panel"><dl class="account-details"><div><dt>Name</dt><dd>${esc(user.name)}</dd></div><div><dt>Email address</dt><dd>${esc(user.email)}</dd></div><div><dt>Role</dt><dd>${labelRole(user.role)}</dd></div><div><dt>Member since</dt><dd>${time(user.created_at)}</dd></div></dl><div class="profile-actions actions">${button('Change password','password',true,'user')}<button class="btn" data-action="logout">Sign out</button></div></div>`;
    $('content').innerHTML=html; updateClocks();
  }


  const field = (label,name,value='',type='text',extra='') => `<div class="field"><label for="pf-${name}">${esc(label)}</label><input id="pf-${name}" name="${name}" type="${type}" value="${esc(value ?? '')}" ${extra}></div>`;
  const selectField = (label,name,value,options) => `<div class="field"><label for="pf-${name}">${esc(label)}</label><select id="pf-${name}" name="${name}">${options.map(([id,label])=>`<option value="${esc(id)}" ${String(value??'')===String(id)?'selected':''}>${esc(label)}</option>`).join('')}</select></div>`;
  function inventoryPage() {
    return heading('Inventory.','Hardware, network addresses, and security reviews for every device.',button('Add device','asset',true,'monitor'))+
      `<div class="metrics two"><div class="metric"><div class="metric-head">Recorded devices</div><div class="metric-number">${assets.length}</div><div class="metric-foot">${assets.filter(a=>a.status==='repair').length} awaiting repair</div></div><div class="metric"><div class="metric-head">Recorded purchase cost</div><div class="metric-number money-number">${money(assets.reduce((n,a)=>n+Number(a.purchase_cost),0))}</div><div class="metric-foot">Includes retired devices · manually entered</div></div></div>`+
      `<div class="panel table-wrap"><table class="table"><thead><tr><th>Device</th><th>Hardware / OS</th><th>Network</th><th>Review</th><th></th></tr></thead><tbody>${assets.map(a=>`<tr><td><strong>${esc(a.asset_tag)} · ${esc(a.name)}</strong><small>${esc(a.category)} · ${esc(a.location||'Location not set')} · ${esc(a.status)}</small></td><td class="wrap">${esc(a.cpu||'CPU not recorded')}<small>${a.ram_gb} GB RAM · ${esc(a.storage||'Storage not recorded')}</small><small>${esc(a.os_version||'OS not recorded')}</small></td><td>${esc(a.ip_address||'IP not recorded')}<small>${esc(a.mac_address||'MAC not recorded')}</small><small>${esc(a.hostname)}</small></td><td>${esc(a.security_status.replaceAll('_',' '))}<small>${esc(a.checked_on||'No review date')}</small></td><td><button class="btn small" data-asset="${a.id}">Edit</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-cell">Add your first device to begin the inventory.</td></tr>'}</tbody></table></div><p class="hint">These are admin records. Saving an IP does not change the PC or router configuration. Asset status does not change station availability; manage that under Stations.</p>`;
  }
  function assetModal(id) {
    if (!isAdmin()) return;
    const a=assets.find(a=>a.id===Number(id))||{};
    const stationChoices=[['','Not linked to a station'],...data.stations.map(s=>[s.id,s.name])];
    if(a.station_id&&!data.stations.some(s=>s.id===a.station_id))stationChoices.push([a.station_id,`${a.station_name||'Station'} (removed)`]);
    const body=`<div class="form-section">Device details</div><div class="form-grid">`+
      field('Asset tag','asset_tag',a.asset_tag,'text','required maxlength="40" placeholder="NOIR-PC-01"')+
      field('Device name','name',a.name,'text','required maxlength="80" placeholder="Customer PC 01"')+
      selectField('Category','category',a.category||'pc',[['pc','PC'],['server','Server'],['network','Network device'],['printer','Printer'],['other','Other']])+
      selectField('Linked station','station_id',a.station_id,stationChoices)+field('Location','location',a.location,'text','maxlength="120"')+
      selectField('Asset status','status',a.status||'active',[['active','Active'],['repair','Repair'],['retired','Retired']])+`</div><div class="form-section">Hardware and operating system</div><div class="form-grid">`+
      [['CPU','cpu'],['Motherboard','motherboard'],['Storage','storage'],['Power supply','psu'],['Input devices','input_devices'],['Output devices','output_devices'],['Network adapter','nic'],['OS and version','os_version']].map(([label,key])=>field(label,key,a[key],'text','maxlength="120"')).join('')+
      field('Memory (GB)','ram_gb',a.ram_gb||0,'number','min="0" max="4096" step="1" required')+field('Purchase cost (PHP)','purchase_cost',a.purchase_cost||0,'number','min="0" max="9999999999" step="0.01" required')+
      `</div><div class="form-section">Network address</div><p class="hint">Enter the address already configured on your PC or router. Leave blank if unknown.</p><div class="form-grid">`+
      field('IPv4 address','ip_address',a.ip_address,'text','maxlength="15" placeholder="192.168.20.101"')+field('MAC address','mac_address',a.mac_address,'text','maxlength="17" placeholder="00:1A:2B:3C:4D:5E"')+field('Hostname','hostname',a.hostname,'text','maxlength="63" placeholder="NOIR-PC-01"')+
      `</div><div class="form-section">Security review</div><div class="form-grid">`+
      selectField('Review status','security_status',a.security_status||'not_checked',[['not_checked','Not checked'],['review_needed','Review needed'],['verified','Verified by administrator']])+field('Review date','checked_on',a.checked_on,'date')+`</div>`+
      field('Review evidence / notes','security_notes',a.security_notes,'text','maxlength="500" placeholder="Firewall enabled, antivirus updated, updates checked; evidence filename"')+
      field('Other notes','notes',a.notes,'text','maxlength="500"');
    modal(a.id?'Edit device':'Add device',body,'Save device',async values=>{
      await api(a.id?`/assets/${a.id}`:'/assets',a.id?'PATCH':'POST',values);
      closeModal(true);await refresh();toast('Device record saved.');
    });
    $('modalForm').closest('.modal').classList.add('wide-modal');
  }
  function maintenancePage() {
    return heading('Maintenance.','Track faults, scheduled work, and completed repairs.',button('Log maintenance','maintenance',true,'plus'))+
      `<div class="panel table-wrap"><table class="table"><thead><tr><th>Device / issue</th><th>Schedule</th><th>Technician</th><th>Status / cost</th><th></th></tr></thead><tbody>${maintenance.map(m=>`<tr><td class="wrap"><strong>${esc(m.asset_tag)} · ${esc(m.asset_name)}</strong>${esc(m.issue)}<small>${esc(m.action_taken)}</small></td><td>${esc(m.scheduled_on||'Not scheduled')}<small>Completed: ${esc(m.completed_on||'—')}</small></td><td>${esc(m.technician||'Unassigned')}</td><td>${esc(m.status.replaceAll('_',' '))}<small>${money(m.cost)}</small></td><td><button class="btn small" data-maintenance="${m.id}">Edit</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-cell">No maintenance records yet.</td></tr>'}</tbody></table></div><p class="hint">For a broken PC, first mark its station under maintenance. Delete the station if it is permanently removed. Keep the device record and repair history.</p>`;
  }
  function maintenanceModal(id) {
    if (!isAdmin()) return;
    if(!assets.length){toast('Add a device in Inventory first.');return;}
    const m=maintenance.find(m=>m.id===Number(id))||{};
    modal(m.id?'Update maintenance':'Log maintenance',selectField('Device','asset_id',m.asset_id,assets.map(a=>[a.id,`${a.asset_tag} · ${a.name}`]))+
      field('Issue or scheduled task','issue',m.issue,'text','required minlength="2" maxlength="500"')+
      field('Action taken','action_taken',m.action_taken,'text','maxlength="500"')+
      field('Technician','technician',m.technician,'text','maxlength="80"')+`<div class="form-grid">`+
      field('Scheduled date','scheduled_on',m.scheduled_on,'date')+field('Completed date','completed_on',m.completed_on,'date')+
      selectField('Status','status',m.status||'open',[['open','Open'],['in_progress','In progress'],['completed','Completed']])+
      field('Cost (PHP)','cost',m.cost||0,'number','min="0" max="9999999999" step="0.01" required')+`</div>`,'Save maintenance',async values=>{
        await api(m.id?`/maintenance/${m.id}`:'/maintenance',m.id?'PATCH':'POST',values);
        closeModal(true);await refresh();toast('Maintenance record saved.');
      });
  }
  function reportsPage() {
    return heading('Reports.','Export records for your café review and project documentation.')+
      `<div class="panel report-list">${[['assets','Hardware and network inventory','Device specifications, IP addresses, costs, and security reviews.'],['maintenance','Maintenance history','Faults, scheduled tasks, technicians, and repair costs.'],['usage','Station usage','All sessions, their deadlines, and recorded end times. Times are UTC.'],['payments','Recorded payments','Payments received, methods, and invoice references. Times are UTC.']].map(([key,title,desc])=>`<div class="report-row"><div><h2>${title}</h2><p>${desc}</p></div><a class="btn" href="/api/reports/${key}.csv" download>Export CSV</a></div>`).join('')}</div><p class="hint">Exports contain café records. Store them in the administrator’s protected folder. For a complete database backup, use scripts/backup.py from the server console; CSV reports are not database backups.</p>`;
  }

  function closeModal(force=false) {
    if (submitPending && !force) return;
    $('modalRoot').replaceChildren();
    if (modalReturnFocus?.isConnected) modalReturnFocus.focus();
  }
  function modal(title,body,submitLabel,onSubmit) {
    modalReturnFocus=document.activeElement;
    $('modalRoot').innerHTML=`<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle"><div class="modal-head"><div><div class="eyebrow">NOIR / ${isAdmin()?'MANAGEMENT':'MEMBER'}</div><h2 id="modalTitle">${esc(title)}</h2></div><button class="round-button" data-close aria-label="Close">${icon('close')}</button></div><form id="modalForm">${body}<div id="modalError" class="form-error" role="alert" hidden></div><div class="modal-actions"><button type="button" class="btn" data-close>Close</button>${submitLabel?`<button class="btn dark" type="submit">${esc(submitLabel)}</button>`:''}</div></form></div></div>`;
    $('modalForm').addEventListener('submit',async event=>{
      event.preventDefault(); if (submitPending||!onSubmit) return;
      const values=Object.fromEntries(new FormData(event.currentTarget));
      submitPending=true; $('modalError').hidden=true;
      const controls=[...event.currentTarget.querySelectorAll('button')]; controls.forEach(b=>b.disabled=true);
      try { await onSubmit(values); }
      catch (error) { if ($('modalError')) {$('modalError').textContent=error.message;$('modalError').hidden=false;} else toast(error.message); }
      finally { submitPending=false; controls.forEach(b=>b.disabled=false); }
    });
    ($('modalForm').querySelector('input,select,button')||$('modalTitle')).focus();
  }
  function customerFields() {
    return `<div class="field"><label for="customerAccount">Customer account</label><select id="customerAccount" name="user_id"><option value="">Walk-in guest</option>${accounts.filter(a=>a.active).map(a=>`<option value="${a.id}">${esc(a.name)} — ${esc(a.email)}</option>`).join('')}</select></div><div class="field"><label for="customerName">Walk-in customer name</label><input id="customerName" name="customer_name" required minlength="2" maxlength="80" placeholder="Customer name"></div>`;
  }
  function stationOptions(rows,selected) {
    return rows.map(s=>`<option value="${s.id}" ${s.id===Number(selected)?'selected':''}>${esc(s.name)} · ${money(s.hourly_rate)}/hr</option>`).join('');
  }
  async function bookingModal(sid) {
    if (!isAdmin()) return;
    if (!available().length) {toast('No stations are available to reserve.');return;}
    await ensureAccounts();
    const future=new Date(Date.now()+3600000);
    const local=new Date(future.getTime()-future.getTimezoneOffset()*60000).toISOString().slice(0,16);
    modal('New booking',`${customerFields()}<div class="field"><label for="bookStation">Station</label><select id="bookStation" name="station_id" required>${stationOptions(available(),sid)}</select></div><div class="field"><label for="bookAt">Arrival time (your device time)</label><input id="bookAt" name="scheduled_at" type="datetime-local" required value="${local}"></div><p class="hint">This station is held immediately until check-in or cancellation. Choose an arrival time within 30 days.</p>`,'Create booking',async values=>{
      values.scheduled_at=new Date(values.scheduled_at).toISOString();
      await api('/bookings','POST',values); closeModal(true); await refresh(); toast('Booking created.');
    });
  }
  async function startModal(sid,bookingId) {
    if (!isAdmin()) return;
    const booking=data.bookings.find(b=>b.id===Number(bookingId));
    const choices=booking?[stationById(booking.station_id)]:available();
    if (!choices.length) {toast('No available stations. Check in a reservation or free a station first.');return;}
    await ensureAccounts();
    modal(booking?'Check in booking':'Start a session',`${booking?`<p class="modal-subtitle">Check in <strong>${esc(booking.customer_name)}</strong> on ${esc(booking.station_name)}.</p>`:customerFields()}<div class="field"><label for="sessionStation">Station</label><select id="sessionStation" name="station_id" required>${stationOptions(choices,sid)}</select></div><div class="field"><label for="sessionDuration">Session time (minutes)</label><input id="sessionDuration" name="duration_minutes" type="number" min="1" max="1440" step="1" value="60" required></div><p class="hint">The session ends when the countdown reaches zero. Billing uses time consumed, rounded up to the next minute. Select a customer account to show their countdown and billing when they sign in.</p>`,'Start session',async values=>{
      if (booking) values.booking_id=booking.id;
      await api('/sessions','POST',values);closeModal(true);await refresh();toast('Session started.');
    });
  }
  function endModal(s) {
    if (!isAdmin()) return;
    const live=s.session;
    const estimatedMinutes=sessionMinutes(live);
    modal(`End ${s.name} session`,`<p class="modal-subtitle">Complete the session for <strong>${esc(live.customer_name)}</strong>.</p><div class="modal-summary"><span>Estimated ${duration(estimatedMinutes)}</span><strong>${money(estimatedMinutes*Number(live.hourly_rate)/60)}</strong></div><p class="hint">${live.planned_end_at?`Scheduled end: ${time(live.planned_end_at)}.`:'This earlier session has no time limit.'} Ending now creates an unpaid invoice.</p><button class="btn small" type="button" data-session-time="${live.id}">${icon('clock')}Set remaining time</button>`,'End and create invoice',async()=>{
      const response=await api(`/sessions/${live.id}/end`,'POST',{});
      closeModal(true);await refresh();submitPending=false;await invoiceModal(response.invoice_id);toast('Session ended. Invoice created.');
    });
  }
  function stationModal(s) {
    if (!isAdmin() || !s) return;
    if (s.status==='available') return startModal(s.id);
    if (s.status==='occupied') return endModal(s);
    if (s.status==='reserved') return startModal(s.id,s.booking.id);
    return editStation(s.id);
  }
  function editStation(id) {
    if (!isAdmin()) return;
    const s=stationById(id);
    modal(s?'Edit station':'Add a station',`<div class="field"><label for="stationName">Station name</label><input id="stationName" name="name" minlength="1" maxlength="40" required placeholder="PC 01" value="${esc(s?.name||'')}"></div><div class="field"><label for="hourlyRate">Hourly rate (PHP)</label><input id="hourlyRate" name="hourly_rate" type="number" min="0.01" max="100000" step="0.01" required placeholder="Enter your rate" value="${s?esc(s.hourly_rate):''}"></div>${s?`<div class="field"><label class="checkbox-label"><input name="maintenance" type="checkbox" ${s.maintenance?'checked':''}> Under maintenance</label></div><p class="hint">An active or reserved station must be freed before maintenance. Rate changes apply to new sessions.</p>`:''}`,s?'Save station':'Add station',async values=>{
      values.maintenance=values.maintenance==='on';
      await api(s?`/stations/${s.id}`:'/stations',s?'PATCH':'POST',values);
      closeModal(true);await refresh();toast(s?'Station updated.':'Station added.');
    });
  }
  function deleteStation(id) {
    if (!isAdmin()) return;
    const s=stationById(id); if (!s) return;
    if (['occupied','reserved'].includes(s.status)) {
      modal('Station is in use',`<p class="modal-subtitle">End the active session or cancel the booking for <strong>${esc(s.name)}</strong> before deleting this station.</p>`,null); return;
    }
    modal('Delete station',`<p class="modal-subtitle">Remove <strong>${esc(s.name)}</strong> from the café floor? It will no longer be available for sessions or bookings.</p><p class="hint">Previous sessions, invoices, and payment records will remain available.</p>`,'Delete station',async()=>{
      await api(`/stations/${s.id}`,'DELETE',{});closeModal(true);await refresh();toast('Station removed. Billing history preserved.');
    });
    $('modalForm').querySelector('[type="submit"]').classList.add('danger');
  }
  function sessionTimeModal(id) {
    if (!isAdmin()) return;
    const live=data.sessions.find(s=>s.id===Number(id)); if (!live) return;
    modal('Set remaining time',`<p class="modal-subtitle">Update the remaining time for ${esc(live.customer_name)} on <strong>${esc(live.station_name)}</strong>.</p><div class="field"><label for="remainingMinutes">Minutes from now</label><input id="remainingMinutes" name="remaining_minutes" type="number" min="1" max="1440" step="1" required value="${live.planned_end_at?Math.min(1440,Math.max(1,Math.ceil(remainingSeconds(live.planned_end_at)/60))):60}"></div><p class="hint">This replaces the remaining time. Billing continues at the session’s original hourly rate.</p>`,'Update time',async values=>{
      await api(`/sessions/${live.id}/time`,'PATCH',values);closeModal(true);await refresh();toast('Remaining time updated.');
    });
  }
  function cancelBookingModal(id) {
    if (!isAdmin()) return;
    const b=data.bookings.find(item=>item.id===Number(id)); if (!b) return;
    modal('Cancel booking',`<p class="modal-subtitle">Release <strong>${esc(b.station_name)}</strong> reserved for ${esc(b.customer_name)} at ${time(b.scheduled_at)}?</p>`,'Cancel booking',async()=>{
      await api(`/bookings/${b.id}/cancel`,'POST',{});closeModal(true);await refresh();toast('Booking cancelled.');
    });
  }
  async function accountModal(id) {
    if (!isAdmin()) return;
    await ensureAccounts();const a=accounts.find(item=>item.id===Number(id));
    modal(a?'Manage account':'Create account',`<div class="field"><label for="accountName">Full name</label><input id="accountName" name="name" required minlength="2" maxlength="80" value="${esc(a?.name||'')}"></div><div class="field"><label for="accountEmail">Email address</label><input id="accountEmail" name="email" type="email" required maxlength="254" value="${esc(a?.email||'')}"></div>${a?'':`<div class="field"><label for="accountPassword">Password</label><input id="accountPassword" name="password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"><p class="hint">At least 12 characters. The user can change this after signing in.</p></div>`}<div class="field"><label for="accountRole">Role</label><select id="accountRole" name="role"><option value="member" ${a?.role==='member'?'selected':''}>Member</option><option value="administrator" ${a?.role==='administrator'?'selected':''}>Administrator</option></select></div>${a?`<div class="field"><label class="checkbox-label"><input type="checkbox" name="active" ${a.active?'checked':''}> Account active</label></div><p class="hint">Disabling an account immediately revokes its logins. Existing café sessions and bookings remain available for management.</p>`:''}`,a?'Save changes':'Create account',async values=>{
      values.active=values.active==='on';
      await api(a?`/accounts/${a.id}`:'/accounts',a?'PATCH':'POST',values);
      if (a?.id===user.id) user=(await api('/auth/me')).user;
      await ensureAccounts(true);closeModal(true);await refresh();toast(a?'Account updated.':'Account created.');
    });
  }
  function invoiceDetails(i) {
    const pairs=[['Customer',i.customer_name],['Station',i.station_name],['Started',time(i.started_at)],['Ended',time(i.ended_at)],['Duration',duration(i.minutes)],['Hourly rate',money(i.hourly_rate)],['Status',i.payment_id?'Paid':'Unpaid']];
    if (i.payment_id) pairs.push(['Payment method',{cash:'Cash',ewallet:'E-wallet',bank:'Bank transfer'}[i.method]],['Paid at',time(i.paid_at)],['Reference',i.reference||'—']);
    return `<div class="invoice-lines">${pairs.map(([name,value])=>`<div class="invoice-line"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join('')}</div><div class="invoice-total">${money(i.amount)}</div>`;
  }
  async function invoiceModal(id) {
    const i=(await api(`/invoices/${id}`)).invoice;
    const canPay=isAdmin()&&!i.payment_id;
    modal(`Invoice #${String(i.id).padStart(5,'0')}`,invoiceDetails(i)+`<button class="btn small" type="button" data-print="${i.id}">${icon('print')}Print ${i.payment_id?'payment record':'invoice'}</button>`+(canPay?`<div class="field"><label for="paymentMethod">Payment received by</label><select id="paymentMethod" name="method"><option value="cash">Cash</option><option value="ewallet">E-wallet</option><option value="bank">Bank transfer</option></select></div><div class="field"><label for="paymentReference">Payment reference <span id="referenceHint">(optional for cash)</span></label><input id="paymentReference" name="reference" maxlength="100" placeholder="Transaction reference"></div><p class="hint">Confirm only after receiving the full payment. This records a payment already received at the counter.</p>`:''),canPay?'Record payment':null,async values=>{
      await api(`/invoices/${i.id}/pay`,'POST',values);closeModal(true);await refresh();toast('Payment recorded.');
    });
  }
  function passwordModal() {
    modal('Change password',`<div class="field"><label for="currentPassword">Current password</label><input id="currentPassword" name="current_password" type="password" autocomplete="current-password" required maxlength="128"></div><div class="field"><label for="newPassword">New password</label><input id="newPassword" name="new_password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"></div><div class="field"><label for="confirmNewPassword">Confirm new password</label><input id="confirmNewPassword" name="confirm_password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"></div><p class="hint">All your devices will be signed out after the password changes.</p>`,'Update password',async values=>{
      if (values.new_password!==values.confirm_password) throw new Error('New passwords do not match.');
      await api('/auth/password','POST',values);closeModal(true);user=null;showAuth();toast('Password updated. Please sign in again.');
    });
  }
  async function printInvoice(id) {
    const i=(await api(`/invoices/${id}`)).invoice;
    $('printArea').innerHTML=`<article class="print-receipt"><h1>NOIR</h1><p>INTERNET CAFÉ</p><h2>${i.payment_id?'Payment record':'Invoice'} #${String(i.id).padStart(5,'0')}</h2>${invoiceDetails(i)}<p class="receipt-footer">Thank you for choosing NOIR.<br>Times shown in ${esc(timezone)}. Currency: PHP.<br>Café billing record.</p></article>`;
    window.print();
  }
  document.addEventListener('click',async event=>{
    const target=event.target.closest('button'); if (!target||target.disabled) return;
    try {
      if (target.hasAttribute('data-close')) {closeModal();return;}
      if (target.dataset.authMode) {setAuthMode(target.dataset.authMode);return;}
      if (target.dataset.nav) {await navigate(target.dataset.nav);return;}
      if (target.dataset.asset) {assetModal(target.dataset.asset);return;}
      if (target.dataset.maintenance) {maintenanceModal(target.dataset.maintenance);return;}
      if (target.dataset.station) {await stationModal(stationById(target.dataset.station));return;}
      if (target.dataset.deleteStation) {deleteStation(target.dataset.deleteStation);return;}
      if (target.dataset.sessionTime) {sessionTimeModal(target.dataset.sessionTime);return;}
      if (target.dataset.editStation) {editStation(target.dataset.editStation);return;}
      if (target.dataset.filter) {stationFilter=target.dataset.filter;render();return;}
      if (target.dataset.checkin) {const b=data.bookings.find(b=>b.id===Number(target.dataset.checkin));await startModal(b.station_id,b.id);return;}
      if (target.dataset.cancelBooking) {cancelBookingModal(target.dataset.cancelBooking);return;}
      if (target.dataset.account) {await accountModal(target.dataset.account);return;}
      if (target.dataset.invoice) {await invoiceModal(target.dataset.invoice);return;}
      if (target.dataset.print) {await printInvoice(target.dataset.print);return;}
      if (target.dataset.invoiceFilter) {invoiceFilter=target.dataset.invoiceFilter;invoicePage=1;await refresh();return;}
      if (target.dataset.invoicePage) {invoicePage=Number(target.dataset.invoicePage);await refresh();return;}
      if (target.dataset.action==='asset') assetModal();
      if (target.dataset.action==='maintenance') maintenanceModal();
      if (target.dataset.action==='booking') await bookingModal();
      if (target.dataset.action==='start') await startModal();
      if (target.dataset.action==='add-station') editStation();
      if (target.dataset.action==='account') await accountModal();
      if (target.dataset.action==='password') passwordModal();
      if (target.dataset.action==='refresh') await refresh();
      if (target.dataset.action==='logout') {await api('/auth/logout','POST',{});user=null;closeModal(true);showAuth();toast('Signed out.');}
    } catch (error) {toast(error.message);}
  });
  document.addEventListener('input',event=>{
    if (event.target.id==='stationSearch') {search=event.target.value;$('stationResults').innerHTML=stationGrid(true);}
    if (event.target.id==='accountSearch') {accountSearch=event.target.value;$('accountResults').innerHTML=accountsTable();}
  });
  document.addEventListener('change',event=>{
    if (event.target.id==='customerAccount') {$('customerName').disabled=Boolean(event.target.value);$('customerName').required=!event.target.value;}
    if (event.target.id==='paymentMethod') {$('paymentReference').required=event.target.value!=='cash';$('referenceHint').textContent=event.target.value==='cash'?'(optional for cash)':'(required)';}
  });
  document.addEventListener('keydown',event=>{
    if (!$('modalRoot').firstChild) return;
    if (event.key==='Escape') closeModal();
    if (event.key==='Tab') {
      const focusable=[...$('modalRoot').querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]')];
      const first=focusable[0],last=focusable[focusable.length-1];
      if (event.shiftKey&&document.activeElement===first) {event.preventDefault();last.focus();}
      else if (!event.shiftKey&&document.activeElement===last) {event.preventDefault();first.focus();}
    }
  });
  $('modalRoot').addEventListener('click',event=>{if(event.target.classList.contains('modal-backdrop'))closeModal();});
  setInterval(()=>{
    if (user&&!document.hidden&&!$('modalRoot').firstChild&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)) refresh();
  },15000);
  setInterval(()=>{if(user&&!document.hidden) updateClocks();},1000);
  boot();
})();

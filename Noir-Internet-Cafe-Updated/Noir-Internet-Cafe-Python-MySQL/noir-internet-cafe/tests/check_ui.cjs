const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const project=require('node:path').resolve(__dirname,'..');
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',addEventListener(){},replaceChildren(){},focus(){},querySelector(){return null;},querySelectorAll(){return[];}});return elements.get(id);}
const document={getElementById:element,addEventListener(){},querySelectorAll(){return[];},activeElement:null};
let src=fs.readFileSync(project+'/static/js/app.js','utf8');
src=src.replace('  boot();',`globalThis.test={render,navigate,countdown,sessionMinutes,bookingModal,startModal,deleteStation,stationModal,
  set:(u,d,p)=>{user=u;data=d;page=p;clockOffset=0;},getPage:()=>page};`);
const context={document,console,Intl,Date,setInterval(){},setTimeout(){},clearTimeout(){},AbortController,window:{scrollTo(){}},fetch(){throw Error('Unexpected network mutation');}};
vm.createContext(context);vm.runInContext(src,context);
const t=context.test;
const now=Date.now();
const session={id:1,station_id:1,station_name:'PC 01',user_id:2,customer_name:'Test Member',hourly_rate:'60',started_at:new Date(now-30*60000).toISOString(),planned_end_at:new Date(now+30*60000).toISOString()};
const stations=[{id:1,name:'PC 01',status:'occupied',hourly_rate:'60',session},{id:2,name:'PC 02',status:'available',hourly_rate:'60'},{id:3,name:'PC 03',status:'maintenance',hourly_rate:'60'}];
const data={stations,sessions:[session],bookings:[],finances:{outstanding:'20',revenue:'60',payments:1}};
const member={id:2,name:'Test Member',role:'member',email:'member@test.example'};
for(const page of ['Overview','Stations','Billing']) {
  t.set(member,data,page);t.render();
  const nav=element('navigation').innerHTML,html=element('content').innerHTML;
  assert(!nav.includes('Bookings')&&!nav.includes('Accounts')&&!nav.includes('Activity')&&!nav.includes('Inventory')&&!nav.includes('Maintenance')&&!nav.includes('Reports'));
  for(const action of ['data-action="booking"','data-action="start"','data-delete-station','data-edit-station','data-cancel-booking'])assert(!html.includes(action),page+' exposes '+action);
  if(page==='Overview'){assert(html.includes('Remaining time'));assert(html.includes('data-countdown'));assert(html.includes('Outstanding balance'));}
  if(page==='Stations'){assert(html.includes('PC 02'));assert(!html.includes('PC 01'));assert(!html.includes('PC 03'));assert(!html.includes('data-station='));}
}
t.set(member,data,'Overview');t.navigate('Bookings');t.navigate('Inventory');t.navigate('Maintenance');t.navigate('Reports');assert.equal(t.getPage(),'Overview');
t.bookingModal();t.startModal();t.deleteStation(2);assert.equal(element('modalRoot').innerHTML,'');
t.set(member,{...data,sessions:[],stations:[]},'Overview');t.render();assert(element('content').innerHTML.includes('No active session'));
t.set(member,{...data,sessions:[{...session,planned_end_at:null}]},'Overview');t.render();assert(element('content').innerHTML.includes('no time limit yet'));
assert.equal(t.countdown(null),'Not set');assert.equal(t.countdown(new Date(now-1000).toISOString()),'00:00:00');
assert.equal(t.sessionMinutes({...session,started_at:new Date(now-2*3600000).toISOString(),planned_end_at:new Date(now-3600000).toISOString()}),60);
for(const page of ['Overview','Stations','Bookings','Accounts','Activity','Billing','Inventory','Maintenance','Reports']) {
 t.set({...member,role:'administrator'},data,page);t.render();
 assert(element('navigation').innerHTML.includes('Bookings'));
 if(page==='Stations') {assert.equal((element('content').innerHTML.match(/data-delete-station=/g)||[]).length,3);assert(element('content').innerHTML.includes('Start session'));}
}
const css=fs.readFileSync(project+'/static/css/styles.css','utf8');
const main=css.match(/\.main\s*\{([^}]+)\}/)[1];
assert(main.includes('margin:0 auto'));assert(main.includes('align-self:start'));
console.log('PASS: member/admin page rendering, read-only controls, guarded navigation, timer states, station delete controls, shared top alignment.');

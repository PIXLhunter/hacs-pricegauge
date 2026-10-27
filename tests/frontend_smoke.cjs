// Minimal DOM contract test, not a real browser layout test.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node {constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.style={};this.isConnected=true;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}attachShadow(){return this.shadowRoot=new Node('shadow');}setAttribute(){}addEventListener(){}dispatchEvent(){}click(){if(this.onclick)this.onclick();}}
global.HTMLElement=Node;global.document={createElement:t=>new Node(t),createElementNS:(ns,t)=>new Node(t),createTextNode:t=>({textContent:t})};global.customElements={get:()=>null,define:(name,cls)=>global.Panel=cls};global.confirm=()=>true;
vm.runInThisContext(fs.readFileSync('custom_components/price_monitor/frontend/panel.js','utf8'));
const p=new Panel();p.data={products:[],settings:{},logs:[]};p.render();
function all(n){return [n,...n.children.flatMap(c=>c.children?all(c):[c])];}
assert(all(p.shadowRoot).some(n=>n.textContent==='Nothing tracked yet'));
assert(all(p.shadowRoot).some(n=>n.className==='brand-mark'));
const add=all(p.shadowRoot).find(n=>n.textContent==='+ Add product');assert(add.className.includes('primary'));add.onclick();
assert(p.draft);assert(all(p.shadowRoot).some(n=>n.textContent==='Load page for inspection'));
p.draft=null;p.error='connection failed';p.render();assert(all(p.shadowRoot).some(n=>n.className==='error'));
p.newSeller({id:'p',name:'P',ean:'',currency:'EUR'},'https://example.com/p');assert(p.draft.product_id==='p');
p.viewMode='logs';p.draft=null;p.render();assert(all(p.shadowRoot).some(n=>n.textContent==='Download logs'));
console.log('5 frontend DOM smoke checks passed');

const chartPanel=new Panel();chartPanel.data={products:[],settings:{},logs:[]};const chart=chartPanel.chart({currency:'EUR',sellers:[{store:'Shop A',history:[{at:'2026-10-13T00:00:00Z',price:100},{at:'2026-10-14T00:00:00Z',price:110}]}]});assert(all(chart).some(n=>n.className==='legend-item'));
console.log('Legend smoke check passed');
const settingsPanel=new Panel();settingsPanel.data={products:[],logs:[],settings:{notify_entities:[{entity_id:'notify.phone',name:'Phone (entity)'},{entity_id:'notify.mobile_app_phone',name:'notify.mobile_app_phone (action)'}],notify_entity:'notify.phone',notify_price_drop:true,notify_drop_percent:5,monthly_budget:250,reserve:25,checks_per_month:4,reset_day:1,interval:60,country:'nl',language:'en',has_api_key:false}};settingsPanel.viewMode='settings';settingsPanel.render();assert(all(settingsPanel.shadowRoot).some(n=>n.textContent==='Phone notifications'));assert(all(settingsPanel.shadowRoot).some(n=>n.textContent==='Send test notification'));console.log('Notification settings smoke check passed');
const reportPanel=new Panel();reportPanel.data={products:[],logs:[],settings:{},reports:[{generated_at:'2026-10-27T05:00:00Z',reason:'scheduled',products:[{name:'Baby cream',currency:'EUR',unit:'/item',minimum:4,average:5,maximum:6,minimum_change_percent:-12.5,retailers:3}]}]};reportPanel.viewMode='reports';reportPanel.render();assert(all(reportPanel.shadowRoot).some(n=>n.textContent==='Price reports'));assert(all(reportPanel.shadowRoot).some(n=>String(n.textContent||'').includes('Min 4.00 EUR/item (-12.5%)')));console.log('Reports smoke check passed');

const versionPanel=new Panel();versionPanel.data={products:[],logs:[],reports:[],settings:{version:'0.4.0'}};versionPanel.render();assert(all(versionPanel.shadowRoot).some(n=>n.textContent==='v0.4.0'&&n.className==='version-note'));console.log('Version note smoke check passed');

const shortlistPanel=new Panel();shortlistPanel.data={products:[{id:'p',name:'Cream',currency:'EUR',summary:{average:1,minimum:1,maximum:1,retailers:1,unit:'/item'},sellers:[],offers:[],notify_target:'notify.wife',notify_enabled:true}],logs:[],reports:[],settings:{version:'0.4.0',notify_shortlist:['notify.me','notify.wife'],notify_entities:[{entity_id:'notify.me',name:'Me'},{entity_id:'notify.wife',name:'Wife'}]}};shortlistPanel.render();assert(all(shortlistPanel.shadowRoot).some(n=>n.tag==='select'&&n.value==='notify.wife'));console.log('Per-product notification shortlist smoke check passed');

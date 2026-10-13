// Minimal DOM contract test, not a real browser layout test.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node {constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.style={};this.isConnected=true;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}attachShadow(){return this.shadowRoot=new Node('shadow');}setAttribute(){}addEventListener(){}dispatchEvent(){}click(){if(this.onclick)this.onclick();}}
global.HTMLElement=Node;global.document={createElement:t=>new Node(t),createTextNode:t=>({textContent:t})};global.customElements={get:()=>null,define:(name,cls)=>global.Panel=cls};global.confirm=()=>true;
vm.runInThisContext(fs.readFileSync('custom_components/price_monitor/frontend/panel.js','utf8'));
const p=new Panel();p.data={products:[],settings:{},logs:[]};p.render();
function all(n){return [n,...n.children.flatMap(c=>c.children?all(c):[c])];}
assert(all(p.shadowRoot).some(n=>n.textContent==='No products tracked yet. Press the red Add product button.'));
const add=all(p.shadowRoot).find(n=>n.textContent==='Add product');assert(add.className==='red');add.onclick();
assert(p.draft);assert(all(p.shadowRoot).some(n=>n.textContent==='Load page for inspection'));
p.draft=null;p.error='connection failed';p.render();assert(all(p.shadowRoot).some(n=>n.className==='error'));
p.newSeller({id:'p',name:'P',ean:'',currency:'EUR'},'https://example.com/p');assert(p.draft.product_id==='p');
p.viewMode='logs';p.draft=null;p.render();assert(all(p.shadowRoot).some(n=>n.textContent==='Download logs'));
console.log('5 frontend DOM smoke checks passed');

class PriceMonitorPanel extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:'open'}); this.rows=[]; this.loading=false; }
  set hass(value) { this._hass=value; if (!this.started && this.isConnected) {this.started=true;this.refresh();} }
  connectedCallback() { if(this._hass && !this.started){this.started=true;this.refresh();} }
  async refresh() {
    try { this.rows=await this._hass.callWS({type:'price_monitor/panel_list'});this.render(); }
    catch(e){this.shadowRoot.textContent='Cannot load Price Monitor: '+(e.message||String(e));}
  }
  el(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
  render(){
    const root=this.shadowRoot;root.replaceChildren();
    const style=this.el('style');style.textContent=`:host{display:block;padding:24px;color:var(--primary-text-color);font-family:Arial,sans-serif}article{border:1px solid var(--divider-color);border-radius:12px;padding:18px;margin:16px 0;background:var(--card-background-color)}label{display:block;margin:12px 0}input,select{display:block;box-sizing:border-box;width:100%;max-width:650px;padding:10px;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:4px}button,a{margin:8px 12px 8px 0}button{padding:10px;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:var(--primary-color)}.toolbar{display:flex;align-items:center;gap:12px}`;root.append(style);
    const toolbar=this.el('div');toolbar.className='toolbar';
    const menu=this.el('button','☰');menu.setAttribute('aria-label','Open sidebar');menu.onclick=()=>this.dispatchEvent(new CustomEvent('hass-toggle-menu',{bubbles:true,composed:true}));
    const refresh=this.el('button','Refresh overview');refresh.onclick=()=>this.refresh();
    toolbar.append(menu,this.el('h2','Price Monitor'),refresh);root.append(toolbar);
    root.append(this.el('p','Open a store, inspect the correct price, then test its CSS selector against the HTML Home Assistant actually downloads. Tests make one retailer request, never a SerpApi request.'));
    if(!this.rows.length)root.append(this.el('p','No retailer entries. Add a monitor entry through Settings → Devices & services.'));
    for(const row of this.rows){
      const card=this.el('article');card.append(this.el('h3',row.title));
      card.append(this.el('p',`Setup: ${row.state} | Last runtime price: ${row.price??'unavailable'} ${row.currency}`));
      try{const url=new URL(row.url);if(['http:','https:'].includes(url.protocol)){const a=this.el('a','Open actual website ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';card.append(a);}}catch{}
      const inputs={};
      for(const [key,label] of [['selector','CSS selector (blank = automatic extraction)'],['attribute','Attribute (blank = element text)']]){
        const l=this.el('label',label);const i=this.el('input');i.value=row[key]||'';l.append(i);inputs[key]=i;card.append(l);
      }
      const l=this.el('label','Decimal separator');const select=this.el('select');for(const v of ['auto','.',',']){const o=this.el('option',v);o.value=v;select.append(o);}select.value=row.decimal_separator;l.append(select);card.append(l);inputs.decimal_separator=select;
      const test=this.el('button','Test selector');const save=this.el('button','Save and retry setup');save.disabled=true;
      const output=this.el('pre','No test yet.');
      const payload=()=>({entry_id:row.entry_id,selector:inputs.selector.value,attribute:inputs.attribute.value,decimal_separator:select.value});
      let tested='';
      for(const i of Object.values(inputs))i.addEventListener('input',()=>{save.disabled=true;tested='';});
      test.onclick=async()=>{test.disabled=true;save.disabled=true;output.textContent='Testing retailer HTML…';const p=payload();try{const r=await this._hass.callWS({type:'price_monitor/panel_test',...p});output.textContent=JSON.stringify(r,null,2);tested=r.ok?JSON.stringify(p):'';save.disabled=!r.ok;}catch(e){output.textContent=e.message||String(e);}finally{test.disabled=false;}};
      save.onclick=async()=>{const p=payload();if(JSON.stringify(p)!==tested)return;save.disabled=true;try{await this._hass.callWS({type:'price_monitor/panel_save',...p});output.textContent='Saved. Setup retried. Refresh overview to check status.';}catch(e){output.textContent=e.message||String(e);}};
      card.append(test,save,output);root.append(card);
    }
  }
}
if(!customElements.get('price-monitor-panel'))customElements.define('price-monitor-panel',PriceMonitorPanel);

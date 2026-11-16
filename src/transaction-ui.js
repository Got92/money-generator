import {localToday} from './calendar.js';
import {positions,previewTransaction,transactionsBefore} from './finance.js';

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={buy:'Acheter',sell:'Vendre',deposit:'Déposer',withdrawal:'Retirer',dividend:'Dividende',split:'Split / regroupement',exchange:'Change',adjustment:'Correction de quantité',opening:'Position initiale'};
const fmt=(v,c='')=>v==null?'Indisponible':new Intl.NumberFormat('fr-FR',{maximumFractionDigits:6}).format(v)+(c?' '+c:'');
const defined=o=>Object.fromEntries(Object.entries(o||{}).filter(([,v])=>v!==undefined&&v!==null&&v!==''));
const trade=t=>['buy','sell'].includes(t);

export function openTransaction({dialog,data,portfolioId,rates=[],quotes=data.marketData||{},original=null,commit,after,importStatement,loadRates}){
 let draft={id:crypto.randomUUID(),portfolioId,type:'buy',date:localToday(),fee:0,currency:'',...original,...(original?{currency:original.currency||'EUR'}:{})};
 let instrument=original?.ticker?{ticker:original.ticker,...(data.marketData?.[original.ticker]||{}),...(data.instrumentRegistry||[]).find(x=>x.ticker===original.ticker),currency:original.currency}:null;
 let generation=0,searchTimer,review=null,quoteInfo='',lookupBusy=false,indicativePrice=null;
 if(original?.ticker){const q=quotes[original.ticker];if(q?.priceDate&&q?.source)quoteInfo=`Dernier cours indicatif : ${fmt(q.price,q.currency)} · ${q.priceDate} · ${q.source}. Prix enregistré conservé.`;}
 const localInstruments=()=>{
  const map=new Map();
  for(const ticker of [...new Set([...Object.keys(quotes),...data.transactions.map(t=>t.ticker).filter(Boolean),...(data.instrumentRegistry||[]).map(x=>x.ticker)])]){
   map.set(ticker,{ticker,...quotes[ticker],...defined((data.instrumentRegistry||[]).find(x=>x.ticker===ticker))});
  }
  return [...map.values()];
 };
 const previewQuotes=()=>instrument?.source?{...quotes,[instrument.ticker]:instrument}:quotes;
 const fail=e=>{dialog.querySelector('#error').textContent=e.message||String(e)};
 const field=(key,label,{type='text',required=false,value=draft[key]??'',min}={})=>`<label>${label}<input name="${key}" type="${type}" value="${esc(value)}" ${required?'required':''} ${type==='number'?'step="any"':''} ${min!==undefined?`min="${min}"`:''} ${/Currency$|^currency$/.test(key)?'pattern="[A-Za-z]{3}" maxlength="3"':''}></label>`;
 function capture(){
  const f=dialog.querySelector('form');if(!f)return;
  for(const [key,value] of new FormData(f))if(key!=='instrumentSearch')draft[key]=value;
 }
 function candidate(){
  const t={...draft};
  t.ticker=String(instrument?.ticker||t.ticker||'').trim().toUpperCase();
  for(const key of ['currency','settlementCurrency','targetCurrency'])if(t[key])t[key]=t[key].trim().toUpperCase();
  if(instrument?.id)t.instrumentId=instrument.id;else if(t.ticker!==original?.ticker)delete t.instrumentId;
  if(trade(t.type)&&!instrument&&!t.ticker)throw Error('Sélectionnez un titre dans les suggestions.');
  if(!t.currency)throw Error('La devise du titre est inconnue. Renseignez-la dans les paramètres avancés.');
  if(t.type==='exchange'&&data.portfolios.find(p=>p.id===t.portfolioId)?.cashMode!=='multi')throw Error('Le change exige des soldes par devise.');
  return t;
 }
 function showPreview(){
  const box=dialog.querySelector('#transactionPreview');if(!box)return;
  const button=dialog.querySelector('#reviewTransaction');button.disabled=true;
  try{
   const t=candidate(),p=previewTransaction(data.transactions,t,previewQuotes(),rates,data.portfolios.find(x=>x.id===t.portfolioId)?.cashMode);
   box.innerHTML=summary(t,p);button.disabled=lookupBusy;
  }catch(e){box.textContent=e.message}
 }
 function summary(t,p){
  const cash=Object.entries(p.movement).filter(([,n])=>n!==0).map(([c,n])=>`${n<0?'Cash débité':'Cash crédité'} : ${fmt(Math.abs(n),c)} · solde ${fmt(p.balancesBefore[c]||0,c)} → ${fmt(p.balancesAfter[c]||0,c)}`).join('<br>')||'Aucun mouvement de cash.';
  return `${trade(t.type)?`<p>Montant hors frais : ${fmt(p.gross,t.currency)} · Frais : ${fmt(p.fee,t.settlementCurrency||t.currency)}</p>`:''}<p>${cash}</p>${data.portfolios.find(x=>x.id===t.portfolioId)?.cashMode!=='multi'?`<p>Cash du portefeuille en EUR : ${fmt(p.cashBeforeEUR,'EUR')} → ${fmt(p.cashAfterEUR,'EUR')}</p>`:''}${t.ticker?`<p>Quantité : ${fmt(p.quantityBefore)} → ${fmt(p.quantityAfter)}<br>PRU de référence en EUR : ${fmt(p.averageBefore,'EUR')} → ${fmt(p.averageAfter,'EUR')}<br>Pondération après opération : ${p.weight==null?'Indisponible':fmt(p.weight,'%')}</p>`:''}<small>Calcul à la date de l’opération. PRU et pondération indisponibles si le change ou les cours manquent. Toute la chronologie est contrôlée.</small>`;
 }
 function available(){
  const box=dialog.querySelector('#heldQuantity');if(!box)return;
  try{const t=candidate();const ps=positions(transactionsBefore(data.transactions,t),draft.portfolioId,{},true,rates);const p=ps.find(x=>t.instrumentId&&x.instrumentId?x.instrumentId===t.instrumentId:x.ticker===t.ticker);box.textContent=`Quantité détenue au ${draft.date} : ${fmt(p?.quantity||0)}`;}catch{box.textContent='Sélectionnez un titre pour afficher la quantité détenue.'}
 }
 function render(){
  generation++;clearTimeout(searchTimer);lookupBusy=false;
  const kind=draft.type,isTrade=trade(kind),hasInstrument=isTrade||['dividend','split','adjustment','opening'].includes(kind);
  const options=isTrade?['buy','sell']:['deposit','withdrawal'].includes(kind)?['deposit','withdrawal']:['dividend','split','adjustment',...(data.portfolios.find(p=>p.id===draft.portfolioId)?.cashMode==='multi'?['exchange']:[]),'opening'];
  dialog.innerHTML=`<form><div class="cardhead"><h2>${original?'Modifier une transaction':'Ajouter une transaction'}</h2><button type="button" class="close" data-cancel aria-label="Fermer">×</button></div>
   <nav class="actions" aria-label="Opérations"><button type="button" class="outline" data-kind="buy">Acheter / vendre</button><button type="button" class="outline" data-kind="deposit">Déposer / retirer du cash</button><button type="button" class="outline" id="importStatement">Importer un relevé</button><button type="button" class="outline" data-kind="dividend">Autres opérations</button></nav>
   <label>Opération<select name="type">${options.map(k=>`<option value="${k}" ${kind===k?'selected':''}>${labels[k]}</option>`).join('')}</select></label>
   ${hasInstrument?`<label>Titre<input name="instrumentSearch" autocomplete="off" maxlength="80" placeholder="Nom ou symbole, ex. MSFT" value="${esc(instrument?`${instrument.ticker} — ${instrument.name||instrument.ticker}`:'')}"></label><div id="instrumentSuggestions" aria-label="Suggestions de titres"></div><p id="instrumentInfo" class="muted">${esc(instrument?[instrument.ticker,instrument.exchange,instrument.currency,instrument.isin].filter(Boolean).join(' · '):'Sélectionnez la cotation exacte.')} ${esc(quoteInfo)}</p>`:''}
   <label>Portefeuille<select name="portfolioId">${data.portfolios.map(p=>`<option value="${esc(p.id)}" ${p.id===draft.portfolioId?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label>
   ${field('date',kind==='opening'?'Date de début du suivi':'Date',{type:'date',required:true})}
   ${isTrade||kind==='opening'?`<div class="formgrid">${field('quantity','Quantité',{type:'number',min:0,required:true})}${field('price',kind==='opening'?'PRU de référence':'Prix unitaire',{type:'number',min:0,required:true})}</div>`:''}
   ${kind==='sell'?'<p id="heldQuantity" role="status"></p>':''}
   ${['deposit','withdrawal','dividend','exchange'].includes(kind)?field('amount',kind==='exchange'?'Montant débité':'Montant',{type:'number',min:0,required:true}):''}
   ${kind==='split'?field('ratio','Ratio du split (2 pour 2:1)',{type:'number',min:0,required:true}):''}
   ${kind==='adjustment'?field('quantityDelta','Correction signée de quantité',{type:'number',required:true}):''}
   ${['split','adjustment'].includes(kind)?field('note','Motif',{required:true}):''}
   ${kind==='opening'?'<p class="notice">Historique incomplet : cette position de départ ne représente pas un achat. Aucun cash débité, aucune transaction antérieure reconstituée. La performance historique depuis l’origine est indisponible.</p>':''}
   ${kind==='exchange'?field('targetCurrency','Devise reçue',{required:true})+field('targetAmount','Montant reçu',{type:'number',min:0,required:true}):''}
   ${!hasInstrument?field('currency','Devise',{required:true}):`<p>Devise : <b id="transactionCurrency">${esc(draft.currency||'À identifier')}</b></p>`}
   <details ${original?.settlementCurrency?'open':''}><summary>Frais facultatifs et paramètres avancés</summary>
   ${isTrade?field('fee','Frais facultatifs',{type:'number',min:0}):''}
   ${hasInstrument?field('currency','Devise de la transaction',{required:true})+field('ticker','Symbole manuel (si recherche indisponible)',{value:instrument?.ticker||draft.ticker||''}):''}
   ${isTrade?field('settlementCurrency','Devise réelle de règlement')+field('settlementAmount','Montant net réel, frais inclus',{type:'number',min:0})+field('settlementFee','Frais inclus dans le règlement',{type:'number',min:0})+'<p class="muted">Renseignez uniquement les montants du relevé. Avec un règlement réel, les frais du prix doivent être à zéro. Aucun taux ou règlement n’est estimé.</p>':''}
   ${field('brokerRef','Référence courtier')}${!['split','adjustment'].includes(kind)?field('note','Note'):''}</details>
   <section class="notice" aria-label="Impact financier"><h3>Impact avant confirmation</h3><div id="transactionPreview" role="status" aria-live="polite"></div></section>
   <p id="error" class="error" role="alert"></p><div class="modal-actions"><button type="button" class="outline" data-cancel>Annuler</button><button type="submit" class="primary" id="reviewTransaction">Vérifier l’opération</button></div><p class="muted">Enregistrement dans Atlas uniquement. Aucun ordre transmis à un courtier.</p></form>`;
  dialog.oncancel=e=>{if(dialog.dataset.saving)e.preventDefault()};
  dialog.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>{generation++;dialog.close()});
  dialog.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{capture();switchKind(b.dataset.kind)});
  dialog.querySelector('#importStatement').onclick=()=>{generation++;importStatement()};
  dialog.querySelector('[name=type]').onchange=e=>{capture();switchKind(e.target.value)};
  dialog.querySelector('[name=portfolioId]').onchange=()=>{capture();render()};
  dialog.querySelector('form').oninput=e=>{
   if(e.target.name==='instrumentSearch'){instrument=null;draft.ticker='';delete draft.instrumentId;draft.currency='';dialog.querySelector('[name=ticker]').value='';dialog.querySelector('[name=currency]').value='';dialog.querySelector('#transactionCurrency').textContent='À identifier';dialog.querySelector('#instrumentInfo').textContent='Sélectionnez la cotation exacte.';lookupBusy=false;generation++;clearTimeout(searchTimer);const term=e.target.value.trim();suggest(localInstruments().filter(i=>`${i.ticker} ${i.name||''}`.toLowerCase().includes(term.toLowerCase())));const turn=generation;if(term)searchTimer=setTimeout(()=>search(term,turn),250)}
   else {capture();if(e.target.name==='ticker'){instrument=null;delete draft.instrumentId;}}
   if(dialog.querySelector('#transactionCurrency'))dialog.querySelector('#transactionCurrency').textContent=draft.currency||'À identifier';available();showPreview();
  };
  dialog.querySelector('form').onsubmit=e=>{e.preventDefault();capture();try{const t=candidate();review={t,p:previewTransaction(data.transactions,t,previewQuotes(),rates,data.portfolios.find(x=>x.id===t.portfolioId)?.cashMode)};confirmStep()}catch(error){fail(error)}};
  if(!dialog.open)dialog.showModal();
  if(hasInstrument&&!instrument)suggest(localInstruments());
  available();showPreview();
 }
 function switchKind(type){
  // Retain legacy metadata only when editing the same operation family.
  const previous=draft;draft={id:previous.id,portfolioId:previous.portfolioId,date:previous.date,type,currency:previous.currency||data.portfolios.find(p=>p.id===previous.portfolioId)?.currency||'EUR',fee:0};
  if(trade(type)&&trade(previous.type))draft={...previous,type};
  else {instrument=null;quoteInfo='';indicativePrice=null;}
  render();
 }
 function suggest(items){
  const box=dialog.querySelector('#instrumentSuggestions');if(!box)return;box.replaceChildren();
  for(const item of items.slice(0,15)){
   const b=document.createElement('button');b.type='button';b.className='instrument-suggestion outline';b.textContent=[item.name||item.ticker,item.ticker,item.exchange||'Place inconnue',item.currency||'Devise inconnue',item.isin].filter(Boolean).join(' · ');b.onclick=()=>select(item);box.append(b);
  }
 }
 async function search(term,turn){
  try{const r=await fetch('/api/market/search?q='+encodeURIComponent(term)),body=await r.json();if(turn!==generation||!dialog.open)return;if(!r.ok)throw Error(body.error||'Recherche indisponible.');
   const local=localInstruments(),items=body.data.map(x=>{const saved=local.find(i=>i.ticker===x.symbol);return {name:x.name,exchange:x.region,currency:x.currency,isin:x.isin,...defined(saved),ticker:x.symbol}});
   const seen=new Set(items.map(i=>i.ticker));suggest([...local.filter(i=>!seen.has(i.ticker)&&`${i.ticker} ${i.name||''}`.toLowerCase().includes(term.toLowerCase())),...items]);
   dialog.querySelector('#instrumentInfo').textContent=items.length?'Recherche Yahoo Finance : sélectionnez une cotation.':'Aucun résultat fournisseur. Utilisez un titre enregistré ou le mode avancé.';
  }catch(e){if(turn===generation&&dialog.open)dialog.querySelector('#instrumentInfo').textContent=e.message+' Les titres enregistrés restent disponibles.'}
 }
 async function select(item){
  capture();clearTimeout(searchTimer);++generation;if(indicativePrice!==null&&Number(draft.price)===indicativePrice)draft.price='';indicativePrice=null;instrument=item;draft.ticker=item.ticker;draft.currency=item.currency||'';quoteInfo='';
  const apply=async q=>{
   if(!dialog.open)return;capture();
   // Keep a verified registry identity; never merge two listings by ISIN or company name.
   instrument={...q,...defined(item),currency:item.currency||q.currency};draft.currency=instrument.currency||'';
   if(trade(draft.type)&&!original&&!draft.price&&Number.isFinite(q.price)&&q.priceDate&&q.source&&q.currency===draft.currency){draft.price=q.price;indicativePrice=q.price;}
   quoteInfo=q.priceDate&&q.source?`Dernier cours indicatif : ${fmt(q.price,q.currency)} · ${q.priceDate} · ${q.source}. Vérifiez le prix d’exécution.`:'Cours daté et sourcé indisponible : saisissez le prix exécuté.';
   lookupBusy=false;render();
   if(loadRates&&draft.currency&&draft.currency!=='EUR'){const turn=generation;try{const loaded=await loadRates(draft.currency);if(turn===generation&&dialog.open){rates=loaded;capture();available();showPreview()}}catch{if(turn===generation&&dialog.open)dialog.querySelector('#instrumentInfo').append(' Change indisponible : PRU en EUR non calculable.')}}
  };
  render();
  const cached=quotes[item.ticker];if(cached?.currency&&cached.priceDate&&cached.source){await apply(cached);return}
  lookupBusy=true;showPreview();const active=generation;
  try{const r=await fetch('/api/market/company?symbol='+encodeURIComponent(item.ticker)),body=await r.json();if(active!==generation||!dialog.open)return;if(!r.ok)throw Error(body.error||'Cours indisponible.');
   await apply(body.data);
  }catch(e){if(active===generation&&dialog.open){lookupBusy=false;quoteInfo=e.message;render()}}
 }
 function confirmStep(){
  generation++;const {t,p}=review;
  dialog.innerHTML=`<form><h2>Confirmer · ${esc(labels[t.type])}</h2><p>${esc(t.ticker||'Liquidités')} · ${esc(t.date)} · ${esc(data.portfolios.find(x=>x.id===t.portfolioId)?.name)}</p>${summary(t,p)}<p id="error" class="error" role="alert"></p><div class="modal-actions"><button type="button" class="outline" data-cancel>Annuler</button><button type="button" class="outline" id="backTransaction">Modifier</button><button type="submit" class="primary" id="confirmTransaction">Confirmer l’enregistrement</button></div></form>`;
  dialog.querySelector('[data-cancel]').onclick=()=>{if(!dialog.dataset.saving)dialog.close()};dialog.querySelector('#backTransaction').onclick=()=>{if(!dialog.dataset.saving)render()};
  dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();if(dialog.dataset.saving)return;dialog.dataset.saving='1';const button=dialog.querySelector('#confirmTransaction');button.disabled=true;try{previewTransaction(data.transactions,t,previewQuotes(),rates,data.portfolios.find(x=>x.id===t.portfolioId)?.cashMode);await commit(t,instrument?.source?instrument:null);dialog.close();after()}catch(error){fail(error);button.disabled=false}finally{delete dialog.dataset.saving}};
 }
 dialog.addEventListener('close',()=>{generation++;clearTimeout(searchTimer)},{once:true});
 render();
}

import {loadHistory,loadFx,sessionRates,cacheSummary} from './session-market.js';
import {intradayPortfolio,intradayBenchmark} from './intraday.js';
import {positions,cashBalances} from './finance.js';
import {performanceSeries,benchmarkSeries,selectPeriod} from './performance.js';
const BENCH={'none':'Aucun','^GSPC':'S&P 500 (indice de prix)','URTH':'MSCI World (ETF URTH, prix)'};
let period='1M',benchmark='none';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function performancePanel(){return `<div class="cardhead"><div><div class="eyebrow">PERFORMANCE</div><h2>Évolution du portefeuille</h2></div><button id="refreshHistory" class="outline">Actualiser les historiques</button></div><div class="performance-controls"><div>${['1D','1W','1M','YTD','MAX'].map(p=>`<button class="outline" data-period="${p}" aria-pressed="${p===period}">${p}</button>`).join(' ')}</div><label>Comparer <select id="benchmark">${Object.entries(BENCH).map(([k,v])=>`<option value="${k}" ${k===benchmark?'selected':''}>${v}</option>`).join('')}</select></label></div><div id="historyChart" role="status" class="chart-empty">Chargement de l’historique…</div><p id="historyStatus" class="muted"></p><div class="cardfoot">1D : cours intrajournaliers Yahoo (pas de cinq minutes), dernière séance disponible. Autres périodes : clôtures quotidiennes. TWR : flux externes supposés en fin de journée. XIRR annualisé depuis l’origine. Indices en EUR, dividendes des indices exclus.</div>`}
export function wirePerformance({data,selected,onRatesLoaded=()=>{}}){
 const panel=document.querySelector('#historyChart');if(!panel)return;
 const status=document.querySelector('#historyStatus');const tx=data.transactions.filter(t=>t.portfolioId===selected);const tickers=[...new Set(tx.filter(t=>['buy','sell'].includes(t.type)).map(t=>t.ticker))];
 let generation=0;
 async function draw(){const turn=++generation;try{
  if(selected==='demo'){panel.innerHTML='Les cours fictifs du portefeuille démo n’ont pas d’historique.';return}
  if(!tx.length){panel.innerHTML='Ajoutez des transactions pour afficher la performance.';return}
  if(period==='1D'){await drawIntraday(turn);return}
  const symbols=[...new Set([...tickers,...(benchmark==='none'?[]:[benchmark])])];
  const results=await Promise.allSettled(symbols.map(s=>loadHistory(s)));if(turn!==generation)return;
  const rows=results.flatMap(r=>r.status==='fulfilled'?r.value:[]);
  const currencies=new Set([...rows.map(r=>r.currency),...tx.flatMap(t=>[t.currency,t.targetCurrency])].filter(c=>c&&c!=='EUR'));
  const before=JSON.stringify(sessionRates());await Promise.allSettled([...currencies].map(c=>loadFx(c)));if(turn!==generation)return;
  status.textContent=cacheSummary(symbols,[...currencies]);
  if(JSON.stringify(sessionRates())!==before){onRatesLoaded();return}
  const body={data:rows};
  const result=performanceSeries(tx,selected,body.data,sessionRates(),new Date().toISOString().slice(0,10),data.portfolios.find(p=>p.id===selected)?.cashMode||'converted');const dates=selectPeriod(result.points,period);const valid=dates.filter(p=>p.index!==null);if(valid.length<2){panel.innerHTML='Historique insuffisant : actualisez les cours et les taux de change nécessaires.';return}
  const bench=benchmark==='none'?[]:benchmarkSeries(dates,body.data,sessionRates(),benchmark);const aligned=benchmark==='none'?-1:dates.findIndex((p,i)=>p.index!==null&&bench[i]?.value!=null);const first=aligned>=0?dates[aligned]:valid[0],last=valid.at(-1), reference=first.index;const b0=aligned>=0?bench[aligned].value:null;const gap=dates.slice(dates.indexOf(first),dates.indexOf(last)+1).some(p=>p.index===null);if(!reference){panel.textContent='Rendement indisponible : valeur initiale nulle.';return}
  const lines=dates.map((p,i)=>({date:p.date,portfolio:p.index===null||p.date<first.date?null:(p.index/reference-1)*100,benchmark:p.date>=first.date&&bench[i]?.value!=null&&b0?(bench[i].value/b0-1)*100:null}));
  const all=lines.flatMap(p=>[p.portfolio,p.benchmark]).filter(Number.isFinite);const min=Math.min(...all,0),max=Math.max(...all,0),span=max-min||1;const x=i=>20+i*560/Math.max(lines.length-1,1),y=v=>175-(v-min)*145/span;
  function paths(key){let parts=[],part=[];lines.forEach((p,i)=>{if(p[key]===null){if(part.length)parts.push(part);part=[]}else part.push(`${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`)});if(part.length)parts.push(part);return parts.map(path=>`<polyline fill="none" stroke="${key==='portfolio'?'#428a61':'#7c94c9'}" stroke-width="2.5" points="${path.join(' ')}"/>`).join('')}
  panel.className='history-plot';panel.innerHTML=`<div class="performance-summary"><b>TWR ${gap?'indisponible':((last.index/reference-1)*100).toFixed(2)+' %'}</b><span>XIRR annualisé : ${result.xirr===null?'indisponible':(result.xirr*100).toFixed(2)+' %'}</span></div><svg viewBox="0 0 600 200" role="img" aria-label="Rendement du portefeuille et de l’indice sélectionné"><line x1="20" x2="580" y1="${y(0)}" y2="${y(0)}" stroke="#e2e9e4"/>${paths('portfolio')}${paths('benchmark')}</svg><div class="performance-summary"><span>${esc(first.date)}</span><span>${esc(last.date)}</span></div><p class="muted">● Portefeuille ${benchmark==='none'?'':' · <span style="color:#7c94c9">● '+esc(BENCH[benchmark])+'</span>'}</p>`;
  status.textContent=cacheSummary(symbols,[...currencies])+' '+(dates.some(p=>p.value===null)?'Certaines dates sont indisponibles ; la courbe est interrompue. ':'')+(benchmark!=='none'&&!b0?'Indice ou taux de change indisponible : actualisez les historiques et le change.':'');
 }catch(e){if(turn===generation)panel.textContent=e.message}}
 async function drawIntraday(turn){
  panel.className='chart-empty';panel.textContent='Chargement des cours intrajournaliers…';status.textContent='';
  const cashMode=data.portfolios.find(p=>p.id===selected)?.cashMode||'converted';
  const symbols=tickers,series={};
  const get=async symbol=>{const response=await fetch('/api/market/intraday?symbol='+encodeURIComponent(symbol));const result=await response.json();if(!response.ok)throw Error(result.error);series[symbol]=result.data};
  await Promise.allSettled(symbols.map(get));if(turn!==generation)return;
  if(benchmark!=='none')try{await get(benchmark)}catch{};
  const sessionDate=symbols.map(s=>series[s]?.sessionDate).filter(Boolean).sort().at(-1);
  if(!sessionDate)throw Error('Aucun cours intrajournalier disponible pour ce portefeuille.');
  const prior=tx.filter(t=>t.date<sessionDate),held=positions(prior,selected,{},false,sessionRates());
  if(held.some(p=>!series[p.ticker]))throw Error('Cours intrajournalier indisponible pour une position.');
  const balances=cashMode==='multi'?cashBalances(prior,selected):{};
  const currencies=new Set([...held.map(p=>series[p.ticker].currency),...Object.keys(balances),...(series[benchmark]?[series[benchmark].currency]:[])].filter(c=>c!=='EUR'));
  await Promise.allSettled([...currencies].map(c=>get(c+'EUR=X')));if(turn!==generation)return;
  const points=intradayPortfolio(tx,selected,series,sessionRates(),cashMode,sessionDate);
  const valid=points.filter(p=>p.value!==null);if(valid.length<2)throw Error('Cours ou taux de change intrajournaliers insuffisants pour valoriser le portefeuille.');
  const comparisons=benchmark==='none'?[]:intradayBenchmark(points,series,benchmark);
  const aligned=benchmark==='none'?-1:points.findIndex((p,i)=>p.value!==null&&comparisons[i]!=null);
  const first=aligned>=0?points[aligned]:valid[0],last=valid.at(-1),base=first.value,b0=aligned>=0?comparisons[aligned]:null;
  if(base<=0)throw Error('Valeur initiale du portefeuille insuffisante pour calculer le rendement.');
  const gap=points.slice(points.indexOf(first),points.indexOf(last)+1).some(p=>p.value===null);
  const lines=points.map((p,i)=>({timestamp:p.timestamp,portfolio:p.value===null||p.timestamp<first.timestamp?null:(p.value/base-1)*100,benchmark:p.timestamp>=first.timestamp&&comparisons[i]!=null&&b0?(comparisons[i]/b0-1)*100:null}));
  const values=lines.flatMap(p=>[p.portfolio,p.benchmark]).filter(Number.isFinite),min=Math.min(...values,0),max=Math.max(...values,0),span=max-min||1;
  const start=Date.parse(points[0].timestamp),duration=Date.parse(points.at(-1).timestamp)-start||1,x=t=>20+(Date.parse(t)-start)*560/duration,y=v=>175-(v-min)*145/span;
  function paths(key){const paths=[];let segment=[];for(const p of lines){if(p[key]===null){if(segment.length)paths.push(segment);segment=[]}else segment.push(`${x(p.timestamp).toFixed(1)},${y(p[key]).toFixed(1)}`)}if(segment.length)paths.push(segment);return paths.map(a=>`<polyline fill="none" stroke="${key==='portfolio'?'#428a61':'#7c94c9'}" stroke-width="2.5" points="${a.join(' ')}"/>`).join('')}
  const fmt=t=>new Intl.DateTimeFormat('fr-FR',{dateStyle:'short',timeStyle:'short'}).format(new Date(t));
  panel.className='history-plot';panel.innerHTML=`<div class="performance-summary"><b>Variation 1D ${gap?'indisponible':((last.value/base-1)*100).toFixed(2)+' %'}</b><span>Dernière séance disponible · pas de 5 min</span></div><svg viewBox="0 0 600 200" role="img" aria-label="Variation intrajournalière du portefeuille et de l’indice sélectionné"><line x1="20" x2="580" y1="${y(0)}" y2="${y(0)}" stroke="#e2e9e4"/>${paths('portfolio')}${paths('benchmark')}</svg><div class="performance-summary"><span>${esc(fmt(first.timestamp))}</span><span>${esc(fmt(last.timestamp))}</span></div><p class="muted">● Portefeuille ${benchmark==='none'?'':' · <span style="color:#7c94c9">● '+esc(BENCH[benchmark])+'</span>'}</p>`;
  status.textContent=(gap?'Certains cours sont indisponibles ; la courbe est interrompue. ':'')+(benchmark!=='none'&&!b0?'Comparaison intrajournalière ou taux de change indisponible.':'');
 }
 document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>{period=b.dataset.period;document.querySelectorAll('[data-period]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));draw()});
 document.querySelector('#benchmark').onchange=e=>{benchmark=e.target.value;draw()};
 document.querySelector('#refreshHistory').onclick=async e=>{
  const button=e.currentTarget;button.disabled=true;
  try{
   if(period==='1D'){await draw();return}
   status.textContent='Actualisation des historiques…';
   const symbols=[...new Set([...tickers,...(benchmark==='none'?[]:[benchmark])])];
   if(!symbols.length)throw Error('Aucun titre à actualiser.');
   const results=await Promise.allSettled(symbols.map(s=>loadHistory(s,true)));
   const currencies=[...new Set([...tx.flatMap(t=>[t.currency,t.targetCurrency]),...results.flatMap(r=>r.status==='fulfilled'?r.value.map(q=>q.currency):[])].filter(c=>c&&c!=='EUR'))];
   const previousRates=JSON.stringify(sessionRates());
   await Promise.allSettled(currencies.map(c=>loadFx(c,true)));
   await draw();
   if(JSON.stringify(sessionRates())!==previousRates)onRatesLoaded();
  }catch(err){status.textContent=err.message}finally{button.disabled=false}
 };
 draw();
}

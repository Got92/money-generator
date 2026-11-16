// The API is the source of derived ratios; this module only selects and displays observations.
const SERIES={
 revenue:['Chiffre d’affaires','Produits des activités ordinaires.','metrics'],
 diluted_eps:['Bénéfice dilué par action','Résultat par action diluée publié.','metrics'],
 ebitda:['EBITDA','Résultat avant intérêts, impôts, dépréciation et amortissement.','metrics'],
 ebit:['EBIT','Résultat avant intérêts et impôts.','metrics'],
 net_income:['Résultat net','Résultat net publié.','metrics'],
 free_cash_flow:['Flux de trésorerie libre','Flux de trésorerie libre publié par le fournisseur.','metrics'],
 roic:['ROIC','Rendement des capitaux investis, selon la formule fournie.','ratios'],
 operating_margin:['Marge opérationnelle','Résultat opérationnel rapporté au chiffre d’affaires.','ratios'],
 fcf_margin:['Marge de flux libre','Flux de trésorerie libre rapporté au chiffre d’affaires.','ratios'],
 net_debt:['Dette nette','Dette nette publiée.','metrics'],
 diluted_average_shares:['Actions diluées moyennes','Nombre moyen d’actions diluées de la période, distinct des actions en circulation.','metrics']
};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:4}).format(n);
const textValue=v=>Array.isArray(v)?v.map(x=>typeof x==='object'?JSON.stringify(x):String(x)).join(', '):typeof v==='object'&&v!==null?JSON.stringify(v):String(v??'non communiqué');

export function windowPoints(points,years){
 const sorted=(points||[]).filter(p=>/^\d{4}-\d{2}-\d{2}$/.test(p.periodEnd||'')).slice().sort ( (a,b)=>a.periodEnd.localeCompare(b.periodEnd));
 if(!sorted.length)return [];
 const latest=sorted.at(-1).periodEnd, cutoff=new Date(latest+'T00:00:00Z');cutoff.setUTCFullYear(cutoff.getUTCFullYear()-years);
 return sorted.filter(p=>p.periodEnd>=cutoff.toISOString().slice(0,10));
}
function renderPlot(rows,label){
 const valid=rows.filter(r=>Number.isFinite(r.value));
 if(!valid.length)return '<p class="muted">Aucune valeur disponible dans cette fenêtre.</p>';
 const min=Math.min(...valid.map(r=>r.value)),max=Math.max(...valid.map(r=>r.value)),span=max-min||1;
 const first=Date.parse(rows[0].date+'T00:00:00Z'),last=Date.parse(rows.at(-1).date+'T00:00:00Z');
 const x=i=>first===last?300:30+(Date.parse(rows[i].date+'T00:00:00Z')-first)*540/(last-first), y=v=>180-(v-min)*150/span;
 // Break lines across missing observations. A single point is still visible.
 let paths='',run=[];const flush=()=>{if(run.length>1)paths+=`<polyline fill="none" stroke="#4b9b6d" stroke-width="2" points="${run.join(' ')}"/>`;run=[]};
 rows.forEach((r,i)=>{if(Number.isFinite(r.value))run.push(`${x(i)},${y(r.value)}`);else flush()});flush();
 return `<div class="history-plot"><svg viewBox="0 0 600 210" role="img" aria-label="${esc(label)}"><line x1="30" x2="570" y1="180" y2="180" stroke="#dce8df"/>${paths}${rows.map((r,i)=>Number.isFinite(r.value)?`<circle cx="${x(i)}" cy="${y(r.value)}" r="4" fill="#347b50"><title>${esc(r.date)} : ${esc(fmt(r.value))} ${esc(r.unit)}</title></circle>`:'').join('')}</svg></div><div class="performance-summary"><span>${esc(rows[0].date)}</span><span>Min : ${esc(fmt(min))} · Max : ${esc(fmt(max))} ${esc(valid[0].unit)}</span><span>${esc(rows.at(-1).date)}</span></div>`;
}
export function renderCompanyDashboard(symbol,profile){
 const metrics=profile?.metrics||{},value=v=>Number.isFinite(v)?fmt(v):'Indisponible';
 return `<section class="card section" id="companyDashboard" data-symbol="${esc(symbol)}"><h2>Évolution de l’entreprise</h2><p class="muted">Capitalisation : ${esc(value(metrics.marketCap))} · Valeur d’entreprise : ${esc(value(metrics.enterpriseValue??profile?.enterpriseValue))} · Devise : ${esc(profile?.currency||'non communiquée')}. Source du profil : ${esc(profile?.source||'non communiquée')} ; récupéré : ${esc(profile?.fetchedAt||'date inconnue')}.</p><p class="muted">Les données du profil sont actuelles et ne sont pas attribuées aux périodes historiques.</p><div class="actions"><button class="outline" id="dashboardLoad">Charger les historiques</button><label>Période <select id="dashboardPeriod"><option value="annual">Annuel</option><option value="quarterly">Trimestre</option><option value="ttm">TTM (quatre trimestres)</option></select></label><label>Fenêtre <select id="dashboardYears"><option value="3">3 ans</option><option value="5">5 ans</option><option value="10">10 ans</option></select></label><label>Indicateur <select id="dashboardSeries">${Object.entries(SERIES).map(([k,v])=>`<option value="${k}">${esc(v[0])}</option>`).join('')}</select></label></div><div id="dashboardResult" role="status">Chargez les historiques pour afficher les observations disponibles.</div><h2>Évolution du cours</h2><div id="dashboardPrice" role="status">Chargez les historiques pour afficher les cours disponibles.</div></section>`;
}
export function wireCompanyDashboard(){
 const root=document.querySelector('#companyDashboard');if(!root)return;
 const result=root.querySelector('#dashboardResult'),price=root.querySelector('#dashboardPrice'),period=root.querySelector('#dashboardPeriod'),years=root.querySelector('#dashboardYears'),series=root.querySelector('#dashboardSeries');let body=null,prices=null,request=0,priceRequest=0;
 async function get(url){const r=await fetch(url);const b=await r.json();if(!r.ok)throw Error(b.error||'Données indisponibles.');return b}
 function draw(){
  if(!body)return;const [label,definition,group]=SERIES[series.value],points=windowPoints(body.points,Number(years.value));
  const rows=points.map(p=>{const o=p[group]?.[series.value];return {date:p.periodEnd,value:typeof o?.value==='number'?o.value:null,unit:[o?.unit,o?.currency].filter(Boolean).join(' ')||'unité non communiquée',object:o}});
  const units=new Set(rows.filter(r=>Number.isFinite(r.value)).map(r=>r.unit));
  const chart=units.size>1?'<p class="error">Graphique indisponible : unités ou devises différentes entre les périodes.</p>':renderPlot(rows,label);
  const full=(body.points||[]).map(p=>p.periodEnd).filter(Boolean).sort();
  result.innerHTML=`${body.fetch?.error?`<p class="error">Actualisation impossible : ${esc(body.fetch.error)}. Les données conservées sont affichées.</p>`:''}<p class="muted">${esc(definition)} Fenêtre de ${esc(years.value)} ans précédant la dernière période disponible ; couverture totale : ${full.length?esc(full[0])+' à '+esc(full.at(-1))+' ('+full.length+' périodes)':'aucune période'}. ${rows.length} période(s) dans la fenêtre. La couverture ne garantit pas un historique complet. Les devises historiques Yahoo peuvent ne pas être vérifiées.</p>${chart}<div class="tablewrap"><table><thead><tr><th>FIN DE PÉRIODE</th><th>VALEUR / UNITÉ</th><th>SOURCE / QUALITÉ</th><th>DÉFINITION / FORMULE / RAISON</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.date)}</td><td>${Number.isFinite(r.value)?esc(fmt(r.value))+' '+esc(r.unit):'Indisponible'}</td><td>${esc(textValue(r.object?.source))} · ${esc(textValue(r.object?.quality||r.object?.status))} · ${esc(textValue(r.object?.fetchedAt))}</td><td>${esc(r.object?.definition||definition)}${r.object?.formula?' · '+esc(r.object.formula):''}${r.object?.inputs?' · Entrées : '+esc(textValue(r.object.inputs)):''}${r.object?.reason?' · '+esc(r.object.reason):!r.object?' · Observation absente':''}</td></tr>`).join('')||'<tr><td colspan="4">Aucune période disponible.</td></tr>'}</tbody></table></div>`;
 }
 function drawPrice(){if(!prices)return;const rows=windowPoints((prices.data||[]).map(p=>({periodEnd:p.date,value:p.price,unit:p.currency||'devise non communiquée'})),Number(years.value)).map(p=>({date:p.periodEnd,value:p.value,unit:p.unit}));const units=new Set(rows.filter(r=>Number.isFinite(r.value)).map(r=>r.unit));const c=prices.cache||{};price.innerHTML=`<p class="muted">Cours de clôture disponibles · source : ${esc(textValue(c.sources))} · récupération : ${esc(c.lastSuccessAt||'date inconnue')} · état : ${esc(c.status||'non communiqué')}${c.warning?' · '+esc(c.warning):''}. Couverture : ${esc(c.firstDate||'inconnue')} à ${esc(c.lastDate||'inconnue')}.</p>`+(units.size>1?'<p class="error">Graphique indisponible : devises différentes.</p>':renderPlot(rows,'Cours historique'))}
 async function load(){const id=++request;body=null;result.textContent='Chargement des fondamentaux…';try{const b=await get('/api/fundamentals/ratios?'+new URLSearchParams({symbol:root.dataset.symbol,period:period.value}));if(!root.isConnected||id!==request)return;body=b;draw()}catch(e){if(root.isConnected&&id===request)result.textContent='Erreur de chargement des fondamentaux : '+e.message}}
 async function loadPrice(){const id=++priceRequest;prices=null;price.textContent='Chargement des cours…';try{const b=await get('/api/market/history?'+new URLSearchParams({symbol:root.dataset.symbol}));if(!root.isConnected||id!==priceRequest)return;prices=b;drawPrice()}catch(e){if(root.isConnected&&id===priceRequest)price.textContent='Erreur de chargement des cours : '+e.message}}
 root.querySelector('#dashboardLoad').onclick=()=>{load();loadPrice()};period.onchange=()=>load();years.onchange=()=>{draw();drawPrice()};series.onchange=draw;
}

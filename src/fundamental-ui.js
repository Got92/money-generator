// Explicit loading keeps company navigation responsive and avoids implicit network fetches.
export function wireFundamentals(){
  const root=document.querySelector('#fundamentalHistory'); if(!root)return;
  const result=root.querySelector('#fundamentalResult'), period=root.querySelector('#fundamentalPeriod'), download=root.querySelector('#downloadFundamentals');
  let body=null, requestId=0;
  const labels={revenue:'Chiffre d’affaires',gross_profit:'Marge brute',ebitda:'EBITDA',ebit:'Résultat opérationnel (EBIT)',net_income:'Résultat net',diluted_eps:'Bénéfice dilué par action',diluted_average_shares:'Nombre moyen d’actions diluées',assets:'Total des actifs',equity:'Capitaux propres',cash:'Trésorerie et équivalents',short_debt:'Dette à court terme',long_debt:'Dette à long terme',net_debt:'Dette nette',working_capital:'Fonds de roulement',operating_cash_flow:'Flux de trésorerie opérationnel',capex:'Dépenses d’investissement',free_cash_flow:'Flux de trésorerie libre',stock_based_compensation:'Rémunération en actions',dividends:'Dividendes versés',buybacks:'Rachats d’actions'};
  const units={currency:'devise', 'currency/share':'devise par action',shares:'actions'};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function load(refresh){
    const request=++requestId; result.textContent='Chargement des états financiers…'; download.disabled=true; body=null;
    try{
      const query=new URLSearchParams({symbol:root.dataset.symbol,period:period.value,refresh:refresh?'1':'0'});
      const response=await fetch('/api/fundamentals/history?'+query); const data=await response.json();
      if(!response.ok)throw Error(data.error||'Données indisponibles.');
      if(!root.isConnected || request!==requestId)return;
      body=data; download.disabled=false;
      const warning=data.fetch.error?`<p class="error">Actualisation impossible : ${esc(data.fetch.error)}. Les données conservées sont affichées.</p>`:'';
      const coverage=data.coverage.periodEnds.length?`Fins de période disponibles : ${esc(data.coverage.firstPeriodEnd)} à ${esc(data.coverage.lastPeriodEnd)} (${data.coverage.periodEnds.length} périodes).`:'Aucune donnée disponible pour cette période.';
      const missing=(data.coverage.byPeriod||[]).filter(p=>p.missingMetrics.length).map(p=>`<li>${esc(p.periodEnd)} : ${p.missingMetrics.length} indicateur(s) manquant(s) — ${p.missingMetrics.map(m=>esc(labels[m]||m)).join(', ')}</li>`).join('');
      result.innerHTML=warning+`<p class="muted">${coverage} Les dates de publication sont inconnues lorsque le fournisseur ne les indique pas. Montants et signes sont ceux du fournisseur ; aucune valeur absente n’est remplacée par zéro.</p><p class="notice">La devise financière Yahoo provient des métadonnées actuelles : elle n’est pas vérifiée pour chaque période historique. Les changements de devise et la comparabilité entre périodes ne sont pas garantis.</p>${missing?`<details><summary>Indicateurs manquants par période</summary><ul>${missing}</ul></details>`:''}`+(data.data.length?`<div class="tablewrap"><table><thead><tr><th>FIN DE PÉRIODE</th><th>ÉTAT</th><th>INDICATEUR</th><th>VALEUR</th><th>UNITÉ / DEVISE</th><th>SOURCE / RÉCUPÉRATION</th></tr></thead><tbody>${data.data.map(r=>`<tr><td>${esc(r.periodEnd)}</td><td>${esc({income:'Résultat',balance:'Bilan',cashflow:'Flux'}[r.statement])}</td><td>${esc(labels[r.metric]||r.metric)}</td><td>${esc(new Intl.NumberFormat('fr-FR',{maximumFractionDigits:4}).format(r.value))}</td><td>${esc(units[r.unit]||r.unit)} ${esc(r.currency||'')}</td><td>${esc(r.source)} · ${esc(r.fetchedAt)}</td></tr>`).join('')}</tbody></table></div>`:'');
    }catch(e){if(root.isConnected && request===requestId)result.textContent='Erreur : '+(e.message||'Données indisponibles.');}
  }
  root.querySelector('#loadFundamentals').onclick=()=>load(false);
  root.querySelector('#refreshFundamentals').onclick=()=>load(true);
  period.onchange=()=>{requestId++;body=null;download.disabled=true;result.textContent='Sélectionnez « Charger » pour cette période.'};
  download.onclick=()=>{if(!body)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)],{type:'application/json'}));a.download=`atlas-fondamentaux-${root.dataset.symbol}-${period.value}.json`;a.click();URL.revokeObjectURL(a.href)};
}

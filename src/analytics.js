import {calculateAllocation} from './allocation.js';
import {fxObservation} from './finance.js';
const assetLabels={EQUITY:'Actions',ETF:'ETF',MUTUALFUND:'Fonds communs',BOND:'Obligations',CURRENCY:'Devises',CRYPTOCURRENCY:'Cryptomonnaies',FUTURE:'Contrats à terme',OPTION:'Options',INDEX:'Indices'};
export function renderAllocation({positions,cashEntries,field,basis,esc,money}) {
 const result=calculateAllocation(positions,cashEntries,field,basis);
 if(result.status==='missing')return '<p class="muted">Allocation indisponible : cours ou taux de change manquant pour la base choisie.</p>';
 if(result.status==='nonpositive')return '<p class="muted">Allocation indisponible : la valeur de la base choisie est nulle ou négative.</p>';
 return result.groups.map((g,i)=>{const label=g.cash?'Liquidités':g.category===null?'Non renseigné':field==='assetClass'?(assetLabels[g.category]||g.category):g.category;return `<div class="allocation"><span><i style="background:${['#a6e9c5','#789de2','#dbbb85','#aab4c5'][i%4]}"></i>${esc(label)}</span><b>${(g.weight*100).toFixed(1)} %</b></div>${g.weight>=0&&g.weight<=1?`<div class="track"><span style="width:${g.weight*100}%"></span></div>`:''}<small class="muted">${money(g.value)}</small>`}).join('')||'<p class="muted">Aucune allocation disponible.</p>';
}
function observationText(observation, esc) {
 if(!observation)return 'taux indisponible';
 return `${esc(observation.from)}/EUR : ${esc(observation.rate)} · date ${esc(observation.date||'inconnue')} · source ${esc(observation.source||'inconnue')} · récupéré le ${esc(observation.fetchedAt||'date inconnue')}`;
}
export function renderProvenance({positions,cashEntries,basis,rates,demo,esc,money}) {
 const result=calculateAllocation(positions,cashEntries,'sector',basis);
 const base=result.denominator===null?'indisponible':money(result.denominator);
 const positionRows=positions.map(p=>{
  const q=p.quote, currency=q?.currency;
  const fx=currency==='EUR'?'conversion EUR directe':currency?observationText(fxObservation(rates,currency,'EUR',q?.priceDate||'9999-12-31'),esc):'devise et taux inconnus';
  return `<li>${esc(p.ticker)} : cours ${q?.price==null?'indisponible':esc(q.price)+' '+esc(currency||'devise inconnue')} · date ${esc(q?.priceDate||'inconnue')} · source ${esc(demo?'Démonstration fictive':q?.source||'inconnue')} · récupéré le ${esc(q?.fetchedAt||'date inconnue')} · ${fx}</li>`;
 }).join('')||'<li>Aucune position.</li>';
 const cashRows=basis==='total'?cashEntries.map(c=>{
  if(c.converted){const obs=c.observations.map(o=>`${esc(o.currency)} au ${esc(o.date)} : ${observationText(o.observation,esc)}`).join(' ; ');return `<li>Liquidités converties en EUR aux dates des flux : ${obs||'aucun taux étranger nécessaire'}.</li>`}
  const fx=c.currency==='EUR'||c.value===0?'conversion EUR directe ou solde nul':observationText(c.observations[0],esc);
  return `<li>Liquidités ${esc(c.currency)} : ${fx}.</li>`;
 }).join('')||'<li>Aucune liquidité.</li>':'';
 return `<section class="card section"><h2>Base et sources</h2><p class="muted">Dénominateur ${basis==='total'?'positions et liquidités signées':'positions investies'} : ${esc(base)}. Chaque poids est la valeur de la catégorie divisée par ce dénominateur ; les positions sont valorisées au cours daté, converti en EUR au dernier taux connu à cette date. Les liquidités multidevises utilisent le dernier taux connu à la date du calcul.</p><ul class="muted">${positionRows}${cashRows}</ul></section>`;
}
export function renderAnalytics({header,positions,cashEntries,basis,esc,money,rates=[],demo=false}) {
 const fields=[['sector','Secteur'],['industry','Industrie'],['currency','Devise de cotation'],['country','Pays du profil'],['assetClass','Classe d’actifs']];
 return header('ANALYSE','Analytics & Risk','Comprendre la composition de vos investissements.')+`<section class="card section"><label>Base de calcul <select id="allocationBasis" aria-label="Base de calcul de l’allocation"><option value="invested" ${basis==='invested'?'selected':''}>Positions investies uniquement</option><option value="total" ${basis==='total'?'selected':''}>Positions et liquidités</option></select></label><p class="muted">Les valeurs sont converties en EUR. Les liquidités négatives réduisent le total et peuvent donner des poids négatifs ou supérieurs à 100 %. La devise de cotation et le pays du profil ne représentent pas nécessairement l’exposition économique. Les fonds ne sont pas analysés par transparence.</p></section><div class="grid">${fields.map(([field,label])=>`<section class="card"><h2>Allocation par ${label.toLowerCase()}</h2>${renderAllocation({positions,cashEntries,field,basis,esc,money})}</section>`).join('')}</div>${renderProvenance({positions,cashEntries,basis,rates,demo,esc,money})}`;
}

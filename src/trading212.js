// Conservative adapter for Trading 212 history CSV variants. Reject ambiguous settlements.
export const HEADERS=['date','type','ticker','quantity','price','fee','amount','currency','brokerRef','sourceIsin','note','settlementCurrency','settlementAmount','settlementFee'];
const ACTIONS={'market buy':'buy','limit buy':'buy','stop buy':'buy','market sell':'sell','limit sell':'sell','stop sell':'sell','deposit':'deposit','withdrawal':'withdrawal','dividend':'dividend','dividend (dividend)':'dividend'};
const CHARGES=['Currency conversion fee','Stamp duty reserve tax','French transaction tax','Charge amount','Withholding tax','Taxes'];
export function isTrading212(headers){return headers.includes('Action')&&headers.includes('Time')&&headers.includes('ID')&&(headers.includes('Ticker')||headers.some(h=>h==='Total'||/^Total \([A-Z]{3}\)$/.test(h)))}
export function normalizeTrading212(headers,rows){
 const totalColumns=headers.filter(h=>h==='Total'||/^Total \([A-Z]{3}\)$/.test(h));
 if(totalColumns.length!==1)throw Error('Trading 212 : une colonne Total avec sa devise est requise.');
 const num=(value,label,line,required=false)=>{if(!value){if(required)throw Error(`Ligne ${line} : ${label} requis.`);return 0}const raw=value.replace(',','.');if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw)||!Number.isFinite(Number(raw)))throw Error(`Ligne ${line} : ${label} invalide.`);return Number(raw)};
 const records=rows.map((cells,i)=>({line:i+2,record:Object.fromEntries(headers.map((h,j)=>[h,(cells[j]||'').trim()]))}));
 const parsed=records.map(({line,record:r})=>{
  const action=(r.Action||'').toLowerCase(),type=ACTIONS[action];if(!type)throw Error(`Ligne ${line} : action Trading 212 non prise en charge (${r.Action}). Aucun import effectué.`);
  if(!/^\d{4}-\d{2}-\d{2}(?:[ T].*)?$/.test(r.Time||'')||!Number.isFinite(Date.parse(r.Time)))throw Error(`Ligne ${line} : date Trading 212 invalide.`);
  if(!r.ID)throw Error(`Ligne ${line} : identifiant Trading 212 absent.`);
  const totalHeader=totalColumns[0],totalCurrency=(totalHeader.match(/\(([A-Z]{3})\)$/)||[])[1]||r['Currency (Total)'];
  if(!/^[A-Z]{3}$/.test(totalCurrency||''))throw Error(`Ligne ${line} : devise du total inconnue.`);
  const rawTotal=num(r[totalHeader],'total',line,true),total=Math.abs(rawTotal);if(total<=0||((type==='deposit'||type==='dividend')&&rawTotal<0))throw Error(`Ligne ${line} : signe ou total incohérent.`);
  let fee=0;
  for(const base of CHARGES){
   const columns=headers.filter(h=>h===base||new RegExp('^'+base.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+' \\([A-Z]{3}\\)$').test(h));
   if(columns.length>1)throw Error(`Ligne ${line} : plusieurs colonnes ${base}.`);
   if(!columns.length)continue;const column=columns[0],value=Math.abs(num(r[column],base,line));if(!value)continue;
   const currency=(column.match(/\(([A-Z]{3})\)$/)||[])[1]||r[`Currency (${base})`];
   if(!currency||currency!==totalCurrency)throw Error(`Ligne ${line} : devise des frais ${base} inconnue ou différente ; conversion manuelle requise.`);
   if(type==='buy'||type==='sell')fee+=value;else throw Error(`Ligne ${line} : frais ou retenue fiscale sur flux à vérifier manuellement.`);
  }
  for(const h of headers){
   if(/^Currency \(/.test(h)||CHARGES.some(base=>h===base||h.startsWith(base+' (')))continue;
   if(/fee|tax|charge/i.test(h)&&r[h]&&num(r[h],h,line)!==0)throw Error(`Ligne ${line} : frais ou taxe non pris en charge (${h}).`);
  }
  let ticker='',quantity='',price='',amount='',currency=totalCurrency,settlementCurrency='',settlementAmount='',settlementFee='';
  if(type==='buy'||type==='sell'){
   ticker=r.Ticker||'';quantity=num(r['No. of shares'],'quantité',line,true);price=num(r['Price / share'],'prix',line,true);currency=r['Currency (Price / share)'];
   if(!ticker||!quantity||quantity<0||price<=0||!/^[A-Z]{3}$/.test(currency||''))throw Error(`Ligne ${line} : titre, quantité, prix ou devise manquant.`);
   if(currency!==totalCurrency){
    if(type==='buy'&&fee>=total)throw Error(`Ligne ${line} : frais supérieurs au règlement.`);
    settlementCurrency=totalCurrency;settlementAmount=total;settlementFee=fee;fee=0;
   }else{
    const expected=quantity*price+(type==='buy'?fee:-fee);if(Math.abs(expected-total)>.05)throw Error(`Ligne ${line} : total incompatible avec quantité, prix et frais. Vérifiez le relevé.`);
   }
  }else {amount=total;if(type==='dividend')ticker=r.Ticker||'';if(type==='dividend'&&r.ISIN&&!ticker)throw Error(`Ligne ${line} : symbole du dividende absent ; correspondance manuelle requise.`)}
  return {stamp:Date.parse(r.Time),line,values:[r.Time.slice(0,10),type,ticker,quantity,price,fee||'',amount,currency,'trading212:'+r.ID,r.ISIN||'',type==='dividend'?'Dividende net selon le total du relevé':'',settlementCurrency,settlementAmount,settlementFee]};
 });
 parsed.sort((a,b)=>a.stamp-b.stamp||a.line-b.line);
 return {headers:HEADERS,rows:parsed.map(x=>x.values.map(String))};
}

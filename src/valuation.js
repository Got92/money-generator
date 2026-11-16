// FCFF is discounted at WACC and net debt is deducted; FCFE uses cost of equity without a debt adjustment.
export function dcf({fcf,growth,projections,discount,terminal,netDebt=0,shares,years=5,method='FCFF'}){
 if(!['FCFF','FCFE'].includes(method))throw Error('Méthode DCF invalide.');
 if(!Number.isFinite(discount)||!Number.isFinite(terminal)||!Number.isFinite(shares)||!Number.isFinite(netDebt)||shares<=0||terminal<=-1||discount<=terminal||discount<=-1)throw Error('Actions positives et taux d’actualisation supérieur à la croissance terminale (taux supérieurs à −100 %) requis.');
 if(method==='FCFE'&&netDebt!==0)throw Error('La dette nette ne doit pas être déduite des FCFE.');
 let flows=projections;
 if(!flows){if(!Number.isFinite(fcf)||fcf<=0||!Number.isFinite(growth)||growth<=-1||years!==5)throw Error('Hypothèses de flux invalides.');let cash=fcf;flows=Array.from({length:years},()=>cash*=1+growth)}
 if(!Array.isArray(flows)||flows.length!==5||flows.some(v=>!Number.isFinite(v))||flows[4]<=0)throw Error('Cinq flux annuels valides et un flux terminal positif sont requis.');
 const pv=flows.reduce((sum,flow,i)=>sum+flow/(1+discount)**(i+1),0);
 const terminalValue=flows[4]*(1+terminal)/(discount-terminal);
 const perShare=(pv+terminalValue/(1+discount)**5-(method==='FCFF'?netDebt:0))/shares;
 if(!Number.isFinite(perShare))throw Error('Résultat non calculable.');return perShare;
}

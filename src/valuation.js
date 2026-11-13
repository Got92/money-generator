// DCF sur flux disponibles aux actionnaires après dette nette, unités monétaires cohérentes.
export function dcf({fcf,growth,discount,terminal,netDebt,shares,years=5}){
 for(const v of [fcf,growth,discount,terminal,netDebt,shares,years])if(!Number.isFinite(v))throw Error('Toutes les hypothèses doivent être renseignées.');
 if(fcf<=0||shares<=0||years!==5||growth<=-1||terminal<=-1||discount<=terminal||discount<=-1)throw Error('FCF et nombre d’actions positifs ; taux d’actualisation supérieur à la croissance terminale et taux supérieurs à −100 %.');
 let cash=fcf,pv=0;for(let i=1;i<=years;i++){cash*=1+growth;pv+=cash/(1+discount)**i}const terminalValue=cash*(1+terminal)/(discount-terminal);const perShare=(pv+terminalValue/(1+discount)**years-netDebt)/shares;if(!Number.isFinite(perShare))throw Error('Résultat non calculable.');return perShare;
}

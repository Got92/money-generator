import {localToday} from './calendar.js';
export function quoteFreshness(q,today=localToday()){
 if(!q||!q.priceDate||!q.currency||!Number.isFinite(q.price)||q.price<=0)return 'Cours indisponible';
 const day=Date.parse(q.priceDate+'T00:00:00Z'),now=Date.parse(today+'T00:00:00Z');
 if(!Number.isFinite(day)||!Number.isFinite(now)||new Date(day).toISOString().slice(0,10)!==q.priceDate)return 'Date de cours invalide';
 const age=(now-day)/86400000;if(age<0)return 'Date de cours future';return age>7?'Cours périmé (plus de 7 jours)':'Cours récent (7 jours maximum)';
}

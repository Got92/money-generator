// Each document owns its cache; it is never sent to the state API or stored on disk.
const histories=new Map(),fx=new Map();
async function getJson(url){const response=await fetch(url,{cache:'no-store'});const body=await response.json();if(!response.ok)throw Error(body.error||'Données indisponibles.');return body.data}
export async function loadHistory(symbol,refresh=false){if(!refresh&&histories.has(symbol))return histories.get(symbol);const rows=await getJson('/api/market/history?symbol='+encodeURIComponent(symbol));histories.set(symbol,rows);return rows}
export async function loadFx(currency,refresh=false){if(currency==='EUR')return [];if(!refresh&&fx.has(currency))return fx.get(currency);const rows=await getJson('/api/market/fx?from='+encodeURIComponent(currency)+'&to=EUR');fx.set(currency,rows);return rows}
export function sessionRates(){return [...fx.values()].flat()}

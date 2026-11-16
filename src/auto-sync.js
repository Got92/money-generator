// A single attempt per day while a real portfolio is open and the page is visible.
export function shouldAutoSync({data,visible,lastAttempt,now=Date.now()}){
 if(!data||!visible||!data.portfolios.some(p=>p.id!=='demo'))return false;
 if(!data.watchlist.length&&!data.transactions.some(t=>t.portfolioId!=='demo'&&['buy','sell','opening'].includes(t.type)))return false;
 const last=Number(lastAttempt||0);return Number.isFinite(last)&&Number.isFinite(now)&&now-last>=86400000;
}

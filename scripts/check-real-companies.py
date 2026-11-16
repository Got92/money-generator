"""Optional live smoke test; use a disposable ATLAS_DB, never a personal database."""
import json, math, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if not os.environ.get('ATLAS_DB'):
    raise SystemExit('ATLAS_DB jetable requis pour cette vérification.')
import server, market, fundamental_metrics, quality_score

node_script='''
import {evaluateScenario} from './src/scenario-model.js';
let raw='';for await (const chunk of process.stdin)raw+=chunk;
const x=JSON.parse(raw),s={method:'FCFF',projectionMode:'growth',initialFcf:x.fcf,years:Array.from({length:5},()=>({growth:.05})),discount:.1,terminalGrowth:.02,postYear5Growth:.02,netDebt:x.netDebt,shares:x.shares,marginOfSafety:.2,currency:x.currency,unit:x.currency};
const result=evaluateScenario(s,x.price);
const flows=Array.from({length:5},(_,i)=>x.fcf*1.05**(i+1));
const independent=(flows.reduce((sum,f,i)=>sum+f/(1.1**(i+1)),0)+(flows[4]*1.02/.08)/(1.1**5)-x.netDebt)/x.shares;
if(!Number.isFinite(result.fairValue)||Math.abs(result.fairValue-independent)>1e-8*Math.max(1,Math.abs(independent)))throw Error('DCF incohérent');
console.log(JSON.stringify({fairValue:result.fairValue,upside:result.upside}));
'''
failed=False
for symbol in ('SCHW','SPGI','AIR.PA'):
    try:
        q=market.company(symbol)
        history=server.fundamental_history.get(symbol,'annual',True)
        ratios=fundamental_metrics.calculate_fundamentals(history['data'],'annual',q)
        score=quality_score.score_company(ratios,sector_type=ratios['methodology']['sectorType'])
        if score['score'] is None and not score['reason']: raise ValueError('Score indisponible sans motif.')
        if score['score'] is not None and not 0<=score['score']<=100: raise ValueError('Score hors bornes.')
        recorded=server.valuation_history_store.record(q)
        valuation=server.valuation_history_store.get(symbol)
        available=[k for k,v in valuation['metrics'].items() if v.get('current')]
        m=q['metrics']; fcf=m.get('freeCashFlow');shares=m.get('shares');debt=m.get('totalDebt');cash=m.get('totalCash')
        inputs=[fcf,shares,debt,cash,q.get('price')]
        if (q.get('financialCurrency')==q.get('currency') and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in inputs) and fcf>0 and shares>0 and q['price']>0):
            scenario={'fcf':fcf,'shares':shares,'netDebt':debt-cash,'price':q['price'],'currency':q['currency']}
            result=subprocess.run(['node','--input-type=module','-e',node_script],cwd=ROOT,input=json.dumps(scenario),text=True,capture_output=True,check=True)
            dcf={'status':'calculated','result':json.loads(result.stdout),'note':'Hypothèses fictives : croissance 5 %, actualisation 10 %, terminal 2 %.'}
        else: dcf={'status':'unavailable','note':'FCF, dette, cash, actions, cours ou devise comparable indisponible.'}
        print(json.dumps({'symbol':symbol,'priceDate':q['priceDate'],'currency':q['currency'],'annualObservations':len(history['data']),'annualPeriods':len(ratios['points']),'qualityScore':score['score'],'qualityReason':score['reason'],'qualityCoverage':score['coverage'],'snapshotRecorded':recorded,'availableMultiples':available,'dcf':dcf},ensure_ascii=False),flush=True)
    except Exception as e:
        failed=True
        print(json.dumps({'symbol':symbol,'error':str(e)},ensure_ascii=False),flush=True)
if failed: sys.exit(1)

"""Portfolio allocation targets, independent of rewritten snapshot tables."""
import datetime
import math

DIMENSIONS = ('position', 'sector', 'industry')

def migrate(db):
    if db.execute('SELECT 1 FROM schema_migrations WHERE version=6').fetchone(): return
    db.execute('CREATE TABLE allocation_target_configs (portfolio_id TEXT PRIMARY KEY, basis TEXT NOT NULL, revision INTEGER NOT NULL)')
    db.execute('''CREATE TABLE allocation_targets (portfolio_id TEXT NOT NULL, dimension TEXT NOT NULL,
        key TEXT NOT NULL, target REAL NOT NULL, minimum REAL NOT NULL, maximum REAL NOT NULL,
        PRIMARY KEY(portfolio_id, dimension, key))''')
    db.execute('INSERT INTO schema_migrations VALUES(6,?,?)', ('allocation_targets_v6', datetime.datetime.now(datetime.timezone.utc).isoformat()))

def validate(obj):
    if not isinstance(obj, dict): raise ValueError('Configuration invalide.')
    pid=obj.get('portfolioId'); basis=obj.get('basis'); rows=obj.get('targets')
    if not isinstance(pid,str) or not pid.strip() or basis not in ('invested','total') or not isinstance(rows,list): raise ValueError('Configuration invalide.')
    sums={d:0 for d in DIMENSIONS}; seen=set(); clean=[]
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Cible invalide.')
        d=row.get('dimension'); key=row.get('key')
        if d not in DIMENSIONS or not isinstance(key,str) or not key.strip() or key!=key.strip() or (d,key) in seen: raise ValueError('Dimension ou clé invalide ou en double.')
        seen.add((d,key)); values=[]
        for field in ('min','target','max'):
            n=row.get(field)
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 0<=n<=1: raise ValueError('Les poids doivent être compris entre 0 et 1.')
            values.append(n)
        lo,target,hi=values
        if not lo<=target<=hi: raise ValueError('La cible doit être comprise entre ses bornes.')
        sums[d]+=target
        clean.append({'dimension':d,'key':key,'target':target,'min':lo,'max':hi})
    if any(v>1+1e-9 for v in sums.values()): raise ValueError('La somme des cibles par dimension ne peut dépasser 100 %.')
    revision=obj.get('revision')
    if revision is not None and (isinstance(revision,bool) or not isinstance(revision,int) or revision<0): raise ValueError('Révision invalide.')
    return pid,basis,clean,revision

def get(db, pid):
    if not isinstance(pid,str) or not pid.strip(): raise ValueError('Portefeuille requis.')
    if not db.execute('SELECT 1 FROM portfolios WHERE id=?',(pid,)).fetchone(): raise ValueError('Portefeuille introuvable.')
    config=db.execute('SELECT basis,revision FROM allocation_target_configs WHERE portfolio_id=?',(pid,)).fetchone()
    rows=db.execute('SELECT dimension,key,target,minimum,maximum FROM allocation_targets WHERE portfolio_id=? ORDER BY dimension,key',(pid,)).fetchall()
    return {'portfolioId':pid,'basis':config[0] if config else 'invested','targets':[dict(zip(('dimension','key','target','min','max'),r)) for r in rows],'revision':config[1] if config else 0}

def put(db, obj):
    pid,basis,rows,revision=validate(obj)
    current=get(db,pid)
    if revision is not None and revision!=current['revision']: raise RuntimeError('Les cibles ont changé dans un autre onglet. Rechargez la page.')
    new=current['revision']+1
    db.execute('INSERT INTO allocation_target_configs VALUES(?,?,?) ON CONFLICT(portfolio_id) DO UPDATE SET basis=excluded.basis,revision=excluded.revision',(pid,basis,new))
    db.execute('DELETE FROM allocation_targets WHERE portfolio_id=?',(pid,))
    db.executemany('INSERT INTO allocation_targets VALUES(?,?,?,?,?,?)',[(pid,r['dimension'],r['key'],r['target'],r['min'],r['max']) for r in rows])
    return get(db,pid)

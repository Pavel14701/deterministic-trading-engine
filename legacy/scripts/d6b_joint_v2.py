"""D.6b: joint ranking retry - label/objective/regularization variants.
Labels: pess_R (terminal, high variance) vs r_reach = min(mfe_r, target)-cost
(path-capped, low variance).  Models: LambdaRank vs regression (lower
variance).  Strong reg: leaves=7, mcs=100, ff=0.7, l2=10, 150 trees.
"""
import sys
from pathlib import Path
import lightgbm as lgb, numpy as np, polars as pl
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from ai.src.mtf_model import (apply_rule_table, build_features,
    candidate_key, fit_rule_table, trade_curve_stats)
from ai.src.state_machine import run_state_machine
from ai.src.mtf import resample_ohlcv
from scripts.d6_joint_rank import sim, pess  # reuse (executes once)

raw = resample_ohlcv(pl.read_parquet(REPO/'data/okx/raw_BTC-USDT_1m.parquet'),'1h')
o,h,l,c = (raw[k].to_numpy() for k in ('open','high','low','close'))
stop = candidate_key(pl.read_parquet(REPO/'data/mtf_dataset/BTCUSDT_1h.parquet').filter(
    (pl.col('execution')=='market') & pl.col('r_net').is_not_nan()
    & (pl.col('exit_idx')>=0) & pl.col('risk_unit').is_not_nan())).sort('_cand')
stop = (stop.with_columns(pl.struct(pl.exclude('_cand')).map_elements(pess,
        return_dtype=pl.Float64).alias('r_pess'))
    .with_columns((pl.min_horizontal('mfe_r', 'target')
        - pl.lit(0.25)).alias('r_reach')))
feats = build_features(stop, ('rule',))
trm = (stop['split']=='train').to_numpy()
sizes = stop.group_by('_cand').len().sort('_cand')['len'].to_numpy()
csp = stop.group_by('_cand').agg(pl.col('split').first()).sort('_cand')['split'].to_numpy()
tr_sizes = sizes[csp=='train']
table = fit_rule_table(stop.filter(pl.col('split')=='train'))
fmt = pl.format('{}|{}', pl.col('regime_dir'), pl.col('side'))
PAR = dict(n_estimators=150, learning_rate=0.05, num_leaves=7,
           min_child_samples=100, colsample_bytree=0.7, reg_lambda=10.0,
           random_state=7, verbosity=-1)
for lab in ('r_pess','r_reach'):
    y = stop[lab].to_numpy()
    rel = np.clip(np.round((y+2)*2),0,12).astype(int)
    for kind in ('rank','reg'):
        if kind=='rank':
            m = lgb.LGBMRanker(objective='lambdarank', label_gain=list(range(13)), **PAR)
            m.fit(feats[trm], rel[trm], group=tr_sizes, callbacks=[])
        else:
            m = lgb.LGBMRegressor(**PAR); m.fit(feats[trm], y[trm])
        sc = m.predict(feats)
        picks = (stop.with_columns(pl.Series('rs', sc)).sort(['_cand','rs'])
            .group_by('_cand').last()
            .with_columns(fmt.replace_strict([f'{r}|{s}' for (r,s) in table],
                list(table.values()), default='x').alias('tr'))
            .filter(pl.col('rule')==pl.col('tr')).sort('entry_idx'))
        out=[]
        for s in ('val','test'):
            sig=[]
            for r in picks.filter(pl.col('split')==s).iter_rows(named=True):
                i0=int(r['entry_idx'])+1
                if i0>=raw.height: continue
                ro,rp,jx = sim(o,h,l,c,i0,r['side'],r['sl_price'],r['tp_price'],48,r['atr_i'])
                if not np.isfinite(ro): continue
                sig.append({'cand':r['_cand'],'decision_idx':int(r['entry_idx']),
                    'side':r['side'],'priority':0.0,'r_net':float(rp),
                    'r_opt':float(ro),'exit_idx':jx})
            taken,_ = run_state_machine(sig)
            rp = np.array([t['r_net'] for t in taken])
            out.append((rp.mean(), trade_curve_stats(rp)['max_dd_r'], rp.size))
        (v,vd,vn),(t,td,tn) = out
        print(f'{lab:8s} {kind:5s} val={v:+.3f} test={t:+.3f} n={tn} dd={td:.1f}R')

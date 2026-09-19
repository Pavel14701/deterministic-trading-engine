"""D.6: joint cost-aware ranking over (stop rule x TP target) pairs.

D.4 ranked stop rules at fixed TP=2R; D.5 fixed TP by hand.  Here the
ranker sees ALL (rule, target) rows and picks the best pair per
candidate - TP aggression becomes a ranked dimension, not a hyper-
parameter.  Labels = pess R (D.3 cost model incl. gap).  Baseline:
D.5 unified +0.490R (test pess)."""
import sys
from pathlib import Path
import lightgbm as lgb, numpy as np, polars as pl
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from ai.src.mtf_model import (apply_rule_table, build_features,
    candidate_key, fit_rule_table, trade_curve_stats)
from ai.src.state_machine import run_state_machine
from ai.src.mtf import resample_ohlcv
GEN_SLIP, COMM, GAP, E_MULT, X_MULT = 0.0005, 0.001, 0.25, 2.0, 2.0

def sim(o, h, l, c, i0, side, sl, tp, hold, atr):
    sign = 1.0 if side == 'long' else -1.0
    fill = o[i0]; risk = abs(fill - sl)
    if risk <= 0: return np.nan, np.nan, -1
    cost_r = (2*COMM*fill + GEN_SLIP*fill)/risk
    pe = E_MULT*GEN_SLIP*fill/risk
    last = min(len(c)-1, i0+47)
    for held, j in enumerate(range(i0, last+1)):
        hs = l[j] <= sl if sign > 0 else h[j] >= sl
        ht = h[j] >= tp if sign > 0 else l[j] <= tp
        if hs:
            r = sign*(sl*(1-sign*GEN_SLIP)-fill)/risk - cost_r
            return r, r-pe-(X_MULT-1)*GEN_SLIP*abs(sl)/risk-GAP*atr/risk, j
        if ht:
            r = sign*(tp-fill)/risk - cost_r
            return r, r-pe, j
        if held == 47:
            px = c[j]*(1-sign*GEN_SLIP); r = sign*(px-fill)/risk - cost_r
            return r, r-pe-(X_MULT-1)*GEN_SLIP*abs(px)/risk, j
    return np.nan, np.nan, -1

def pess(row):
    sign = 1.0 if row['side']=='long' else -1.0
    risk, fill = row['risk_unit'], row['fill_price']
    d = E_MULT*GEN_SLIP*fill/risk
    if row['exit_reason']=='sl':
        d += (X_MULT-1)*GEN_SLIP*abs(row['sl_price'])/risk + GAP*row['atr_i']/risk
    elif row['exit_reason']=='time':
        d += (X_MULT-1)*GEN_SLIP*abs(row['exit_price'])/risk
    return row['r_net']-d

raw = resample_ohlcv(pl.read_parquet(REPO/'data/okx/raw_BTC-USDT_1m.parquet'),'1h')
o,h,l,c = (raw[k].to_numpy() for k in ('open','high','low','close'))
stop = candidate_key(pl.read_parquet(REPO/'data/mtf_dataset/BTCUSDT_1h.parquet').filter(
    (pl.col('execution')=='market') & pl.col('r_net').is_not_nan()
    & (pl.col('exit_idx')>=0) & pl.col('risk_unit').is_not_nan())).sort('_cand')
print('panel rows:', stop.height, 'targets:', sorted(stop['target'].unique().to_list()))
stop = stop.with_columns(pl.struct(pl.exclude('_cand')).map_elements(pess,
    return_dtype=pl.Float64).alias('r_pess'))
feats = build_features(stop, ('rule',))
split_row = stop['split'].to_numpy(); trm = split_row=='train'
sizes = stop.group_by('_cand').len().sort('_cand')['len'].to_numpy()
csp = stop.group_by('_cand').agg(pl.col('split').first()).sort('_cand')['split'].to_numpy()
rel = np.clip(np.round((stop['r_pess'].to_numpy()+2)*2),0,12).astype(int)
rk = lgb.LGBMRanker(objective='lambdarank', n_estimators=300, learning_rate=0.05,
    num_leaves=15, min_child_samples=30, label_gain=list(range(13)),
    random_state=7, verbosity=-1)
rk.fit(feats[trm], rel[trm], group=sizes[csp=='train'], callbacks=[])
stop = stop.with_columns(pl.Series('rs', rk.predict(feats)))
table = fit_rule_table(stop.filter(pl.col('split')=='train'))
fmt = pl.format('{}|{}', pl.col('regime_dir'), pl.col('side'))
if __name__ == "__main__":
    for tag, gate in (('joint ungated', False), ('joint +gate', True)):
        picks = (stop.sort(['_cand','rs']).group_by('_cand').last()
            .with_columns(fmt.replace_strict([f'{r}|{s}' for (r,s) in table],
                list(table.values()), default='x').alias('tr')))
        if gate: picks = picks.filter(pl.col('rule')==pl.col('tr'))
        picks = picks.sort('entry_idx')
        for s in ('val','test'):
            sig = []
            for r in picks.filter(pl.col('split')==s).iter_rows(named=True):
                i0 = int(r['entry_idx'])+1
                if i0 >= raw.height: continue
                ro, rp, jx = sim(o,h,l,c,i0,r['side'],r['sl_price'],r['tp_price'],48,r['atr_i'])
                if not np.isfinite(ro): continue
                sig.append({'cand':r['_cand'],'decision_idx':int(r['entry_idx']),
                    'side':r['side'],'priority':0.0,'r_net':float(rp),'r_opt':float(ro),
                    'exit_idx':jx})
            taken,_ = run_state_machine(sig)
            rp = np.array([t['r_net'] for t in taken])
            ro = np.array([t['r_opt'] for t in taken])
            dd = trade_curve_stats(rp)['max_dd_r']
            print(f'{tag:14s} {s:5s} opt={ro.mean():+.3f} pess={rp.mean():+.3f} '
                  f'ratio={rp.mean()/ro.mean():.2f} n={rp.size} dd={dd:.1f}R')

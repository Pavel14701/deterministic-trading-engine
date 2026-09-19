"""Backtest the trained model against simple baselines on the test split.

Usage (from the repo root):

    uv run python scripts/backtest.py --data data/okx7 \
        --model runs/okx7/best.pt --out runs/okx7/backtest.json

For every (base timeframe, asset) slice of the TEST segment the script
simulates long-only trading on the same rules the labels were built
with (TP/SL at close +/- ATR multiples, max hold, commission +
slippage from configs/ai.yaml ``risk``) and compares the signals of:

- ``transformer`` - the trained EntryExitTransformer (window argmax);
- ``rf``          - RandomForest classifier on the same per-bar features;
- ``logreg``      - multinomial logistic regression on the same features;
- ``ridge``       - RidgeClassifier (fast linear-regression-style baseline);
- ``mlp``         - sklearn MLPClassifier (simple neural baseline);
- ``lgbm``        - LightGBM classifier (if the package is installed);
- ``xgb``         - XGBoost classifier (if the package is installed);
- ``random``      - entries/exits at the transformer's signal rates
                    (sanity floor).

Reported per model: trade count, win rate, profit factor, total return,
max drawdown, plus action-class accuracy / macro-F1 on the labelled
bars.  Results are broken down per base timeframe.

Notes:
- prices in the features are scaled per asset by a constant, so all
  PnL math runs on ratios (%), which is scale-invariant;
- the transformer predicts via sliding windows (seq_len from the
  config); baselines see only the current bar's features, so they have
  strictly less information - that is the point of a baseline.

"""

from __future__ import annotations

import argparse
import json
import sys
import zlib

from pathlib import Path

import numpy as np
import polars as pl


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PRICE_COLS = ["open", "high", "low", "close", "volume"]
TP_SL_COLS = ["tp", "sl"]
IGNORE = -100


def _load_cfg() -> dict:
    """Parse the risk block of configs/ai.yaml (no yaml dep needed)."""
    import re

    text = (REPO / "configs" / "ai.yaml").read_text(encoding="utf-8")
    risk: dict = {}
    in_risk = False
    for line in text.splitlines():
        if re.match(r"^risk:", line):
            in_risk = True
            continue
        if in_risk:
            m = re.match(r"^  (\w+):\s*([^#]+)", line)
            if not m:
                if line and not line.startswith(" "):
                    break
                continue
            key, val = m.group(1), m.group(2).strip()
            try:
                risk[key] = float(val) if "." in val else int(val)
            except ValueError:
                risk[key] = val.strip("'\"") or None
    return risk


def simulate(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    sig: np.ndarray,
    tp: np.ndarray,
    sl: np.ndarray,
    commission: float,
    slippage: float,
    max_hold: int,
) -> dict:
    """Long-only backtest driven by 0/1/2 signals (close prices)."""
    n = len(close)
    cash = 1.0
    equity = np.full(n, 1.0)
    trades: list[float] = []
    entry = tp_p = sl_p = 0.0
    i_pos = -1
    in_pos = False
    for i in range(n):
        if in_pos:
            exit_price: float | None = None
            if low[i] <= sl_p:  # pessimistic: SL before TP in one bar
                exit_price = sl_p
            elif high[i] >= tp_p:
                exit_price = tp_p
            elif sig[i] == 2:
                exit_price = float(close[i])
            elif max_hold and i - i_pos >= max_hold:
                exit_price = float(close[i])
            if exit_price is not None:
                ret = (
                    exit_price
                    * (1 - slippage)
                    * (1 - commission)
                    / (entry * (1 + slippage) * (1 + commission))
                    - 1.0
                )
                cash *= 1.0 + ret
                trades.append(ret)
                in_pos = False
        elif sig[i] == 1 and np.isfinite(tp[i]) and np.isfinite(sl[i]):
            entry = float(close[i])
            tp_p, sl_p = float(tp[i]), float(sl[i])
            i_pos = i
            in_pos = True
        equity[i] = cash
    total = np.asarray(trades) if trades else np.zeros(0)
    wins = total[total > 0]
    losses = total[total < 0]
    peak = np.maximum.accumulate(equity)
    max_dd = float(((peak - equity) / peak).max()) if n else 0.0
    pf = (
        float(wins.sum() / abs(losses.sum()))
        if len(losses) and losses.sum() != 0
        else (float("inf") if len(wins) else 0.0)
    )
    return {
        "n_trades": len(total),
        "win_rate": (
            round(float((total > 0).mean()), 4) if len(total) else 0.0
        ),
        "profit_factor": round(pf, 3),
        "total_return_pct": round((cash - 1.0) * 100, 3),
        "max_drawdown_pct": round(max_dd * 100, 3),
    }


def _f1_macro(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Macro-F1 over the classes actually present in the truth."""
    out = []
    for c in np.unique(y_true):
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        if tp:
            prec, rec = tp / (tp + fp), tp / (tp + fn)
            out.append(2 * prec * rec / (prec + rec))
        else:
            out.append(0.0)
    return float(np.mean(out))


def _fill_missing_sig(df: pl.DataFrame, sig_cols: list[str]) -> pl.DataFrame:
    """Add union signal columns missing from a per-base frame.

    Uses the same neutral fills as ``train_okx._merge_bases`` so a
    single set of models fitted on the merged (union) table predicts
    consistently on every base: 10.0 for ``dist_*`` columns ("zone far
    away" feature cap) and 0.0 for everything else.
    """
    missing = [c for c in sig_cols if c not in df.columns]
    if not missing:
        return df
    return df.hstack(
        pl.DataFrame(
            {
                c: pl.Series(
                    np.full(
                        df.height,
                        10.0 if "dist" in c else 0.0,
                        dtype=np.float32,
                    )
                )
                for c in missing
            }
        )
    )


def _fit_baselines(
    train_df: pl.DataFrame, feature_cols: list[str], seed: int
) -> dict:
    """Train RF and LogReg on the flattened per-bar feature table."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    y = train_df["action"].to_numpy()
    fit_mask = y != IGNORE
    x_all = train_df.select(feature_cols).to_numpy().astype(np.float32)
    x_fit, y_fit = x_all[fit_mask], y[fit_mask]

    rng = np.random.default_rng(seed)
    cap = 300_000
    if len(x_fit) > cap:  # RF does not need 3M rows to be a baseline
        idx = rng.choice(len(x_fit), cap, replace=False)
        x_rf, y_rf = x_fit[idx], y_fit[idx]
    else:
        x_rf, y_rf = x_fit, y_fit

    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=14,
        min_samples_leaf=5,
        n_jobs=-1,
        random_state=seed,
        class_weight="balanced_subsample",
    )
    rf.fit(x_rf, y_rf)

    cap_lr = 500_000
    if len(x_fit) > cap_lr:
        idx = rng.choice(len(x_fit), cap_lr, replace=False)
        x_lr, y_lr = x_fit[idx], y_fit[idx]
    else:
        x_lr, y_lr = x_fit, y_fit
    scaler = StandardScaler().fit(x_lr)
    lr = LogisticRegression(max_iter=300, C=1.0)
    lr.fit(scaler.transform(x_lr), y_lr)

    # Ridge classifier: a plain linear ("regression"-style) baseline on
    # the same scaled features as logreg.
    from sklearn.linear_model import RidgeClassifier
    from sklearn.neural_network import MLPClassifier

    ridge = RidgeClassifier(alpha=1.0).fit(
        scaler.transform(x_lr), y_lr
    )

    # Simple MLP: modest size, bounded epochs, early stopping.
    cap_mlp = 200_000
    if len(x_fit) > cap_mlp:
        idx = rng.choice(len(x_fit), cap_mlp, replace=False)
        x_mlp, y_mlp = x_fit[idx], y_fit[idx]
    else:
        x_mlp, y_mlp = x_fit, y_fit
    mlp = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        max_iter=40,
        early_stopping=True,
        n_iter_no_change=3,
        random_state=seed,
    ).fit(scaler.transform(x_mlp), y_mlp)

    est: dict = {
        "rf": rf,
        "lr": lr,
        "ridge": ridge,
        "mlp": mlp,
        "scaler": scaler,
    }

    # Gradient-boosted baselines: LightGBM / XGBoost when installed.
    cap_gb = 300_000
    if len(x_fit) > cap_gb:
        idx = rng.choice(len(x_fit), cap_gb, replace=False)
        x_gb, y_gb = x_fit[idx], y_fit[idx]
    else:
        x_gb, y_gb = x_fit, y_fit
    try:
        from lightgbm import LGBMClassifier

        lgbm = LGBMClassifier(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=63,
            n_jobs=-1,
            random_state=seed,
            verbose=-1,
        ).fit(x_gb, y_gb)
        est["lgbm"] = lgbm
    except ImportError:
        print("lightgbm is not installed - skipping lgbm baseline",
              flush=True)
    try:
        from xgboost import XGBClassifier

        # XGBClassifier requires 0-based contiguous class ids; ours are
        # {1, 2}, so shift down for fitting and back up at predict time.
        xgb = XGBClassifier(
            n_estimators=400,
            learning_rate=0.05,
            max_depth=8,
            tree_method="hist",
            n_jobs=-1,
            random_state=seed,
        ).fit(x_gb, y_gb - 1)
        est["xgb"] = xgb
        est["xgb_shift"] = 1
    except ImportError:
        print("xgboost is not installed - skipping xgb baseline",
              flush=True)
    return est


def _transformer_signals(
    data: Path,
    tdir: Path,
    model_path: Path,
    seq_len: int,
    device: str | None,
    batch_size: int,
    n_rows: int,
) -> np.ndarray:
    """Argmax action per bar over one base's test frame (-1 = no window)."""
    import torch

    from ai.src.config import load_config
    from ai.src.io import load_order_blocks_parquet
    from ai.src.training import build_loader_from_parquet
    from ai.src.transformer import EntryExitTransformer

    meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    ind_cols = list(meta["ind_cols"])
    sig_cols = list(meta["sig_cols"] or [])
    cfg = load_config(REPO / "configs" / "ai.yaml").model
    model = EntryExitTransformer(
        n_price_feats=len(PRICE_COLS),
        n_ind_feats=len(ind_cols),
        n_sig_feats=len(sig_cols),
        n_tp_sl_feats=len(TP_SL_COLS),
        hidden_size=cfg.hidden_size,
        num_layers=cfg.num_layers,
        num_heads=cfg.num_heads,
        outcome_mode=cfg.outcome_mode,
        n_patterns=cfg.n_patterns,
        max_seq_len=cfg.max_seq_len,
        max_ob_seq_len=cfg.max_ob_seq_len,
        ob_embedding_dim=cfg.ob_embedding_dim,
        atr_global=cfg.atr_global,
    )
    state = torch.load(
        REPO / model_path, map_location="cpu", weights_only=True
    )
    model.load_state_dict(state)
    dev = torch.device(
        device or ("cuda" if torch.cuda.is_available() else "cpu")
    )
    model.to(dev).eval()

    obs = load_order_blocks_parquet(str(tdir / "order_blocks.parquet"))
    raw = pl.read_parquet(tdir / "features.parquet")
    feat_filled = _fill_missing_sig(raw, sig_cols)
    features_path = tdir / "features.parquet"
    if feat_filled.width != raw.width:
        features_path = tdir / "features.filled.parquet"
        feat_filled.write_parquet(features_path)
    try:
        loader, _ = build_loader_from_parquet(
            features_path=str(features_path),
            labels_path=str(tdir / "labels.parquet"),
            order_blocks=obs,
            seq_len=seq_len,
            price_cols=PRICE_COLS,
            ind_cols=ind_cols,
            sig_cols=sig_cols,
            tp_sl_cols=TP_SL_COLS,
            batch_size=batch_size,
            shuffle=False,
        )
        sig = np.full(n_rows, -1, dtype=np.int8)
        with torch.inference_mode():
            for batch in loader:
                (prices, inds, sigs, tp, sl, obs_b, _a, _o, _p, sb, _bi) = (
                    batch
                )
                logits, _out, _ = model(
                    prices.to(dev), inds.to(dev), sigs.to(dev),
                    tp.to(dev), sl.to(dev), obs_b,
                )
                idx = sb.numpy() + seq_len - 1
                # Model emits per-position logits (B, T, 3); the signal
                # for the bar at a window's end is its last position.
                sig[idx] = logits[:, -1, :].argmax(dim=-1).cpu().numpy()
    finally:
        if features_path != tdir / "features.parquet":
            features_path.unlink()
    return sig


def _slice_rows(
    ts: np.ndarray, segs: list[tuple[str, int, int]]
) -> list[tuple[str, int, int]]:
    """(instrument, row_lo, row_hi) per asset inside one segment file."""
    rows = []
    for inst, t0, t1 in segs:
        idx = np.flatnonzero((ts >= t0) & (ts <= t1))
        if len(idx):
            rows.append((inst, int(idx[0]), int(idx[-1]) + 1))
    return rows


def main() -> None:
    """Run the backtest comparison and persist the report."""
    ap = argparse.ArgumentParser(description="Backtest vs baselines")
    ap.add_argument("--data", default="data/okx7")
    ap.add_argument("--model", default="runs/okx7/best.pt")
    ap.add_argument("--out", default="runs/okx7/backtest.json")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--seq-len", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--skip-transformer",
        action="store_true",
        help="skip the transformer (baselines only)",
    )
    args = ap.parse_args()

    data = REPO / args.data
    meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    bases: list[str | None] = list(meta.get("bases") or [None])
    ind_cols = list(meta["ind_cols"])
    sig_cols = list(meta["sig_cols"] or [])
    feature_cols = PRICE_COLS + ind_cols + sig_cols
    seq_len = args.seq_len or int(meta.get("seq_len") or 128)
    risk = _load_cfg()
    commission = float(risk.get("commission_pct", 0.001))
    slippage = float(risk.get("slippage_pct", 0.0005))
    max_hold = int(risk.get("max_bars_hold", 20) or 0)

    # ---- baselines: one RF + one LogReg on the merged train table ----
    from scripts.train_okx import _merge_bases

    merged = data / "_merged"
    if not (merged / "train_features.parquet").is_file():
        _merge_bases(data, "train", bases, sig_cols)
    train_df = pl.read_parquet(merged / "train_features.parquet")
    train_df = train_df.with_columns(
        pl.read_parquet(merged / "train_labels.parquet")["action"]
        .alias("action")
    )
    print(f"fitting baselines on {train_df.height} train rows ...", flush=True)
    estimators = _fit_baselines(train_df, feature_cols, args.seed)
    del train_df

    models = [
        m
        for m in (
            "transformer", "rf", "logreg", "ridge", "mlp", "lgbm",
            "xgb", "random",
        )
        # 'logreg' is always available (its estimator key is 'lr');
        # lgbm/xgb depend on the packages being installed.
        if m in ("transformer", "random", "logreg") or m in estimators
    ]
    acc: dict[str, list[int]] = {m: [0, 0] for m in models}  # hit, n
    f1s: dict[str, list[float]] = {m: [] for m in models}
    trades_n: dict[str, int] = {m: 0 for m in models}
    rets: dict[str, list[float]] = {m: [] for m in models}
    detail: dict[str, dict] = {m: {} for m in models}
    tf_sig_cache: dict[str, np.ndarray] = {}

    for b in bases:
        btag = b or "default"
        tdir = data / "test" / b if b else data / "test"
        feat = _fill_missing_sig(
            pl.read_parquet(tdir / "features.parquet"), sig_cols
        )
        lbl = pl.read_parquet(tdir / "labels.parquet")
        ts = feat["ts"].to_numpy()
        y_true = lbl["action"].to_numpy()
        seg_meta = []
        for inst, info in meta["assets"].items():
            node = (
                info["bases"][b]["segments"]["test"]
                if "bases" in info
                else info["segments"]["test"]
            )
            seg_meta.append((inst, int(node["ts_start"]), int(node["ts_end"])))
        slices = _slice_rows(ts, seg_meta)

        x_arr = feat.select(feature_cols).to_numpy().astype(np.float32)
        sig_rf = estimators["rf"].predict(x_arr)
        prob_lr = estimators["lr"].predict_proba(
            estimators["scaler"].transform(x_arr)
        )
        sig_lr = estimators["lr"].classes_[prob_lr.argmax(axis=1)]
        x_scaled = estimators["scaler"].transform(x_arr)
        sig_ridge = estimators["ridge"].predict(x_scaled)
        sig_mlp = estimators["mlp"].predict(x_scaled)
        sig_lgbm = (
            estimators["lgbm"].predict(x_arr)
            if "lgbm" in estimators
            else None
        )
        sig_xgb = (
            estimators["xgb"].predict(x_arr)
            + estimators.get("xgb_shift", 0)
            if "xgb" in estimators
            else None
        )

        if not args.skip_transformer and btag not in tf_sig_cache:
            tf_sig_cache[btag] = _transformer_signals(
                data, tdir, REPO / args.model, seq_len, args.device,
                args.batch_size, feat.height,
            )
        p_in, p_out = 0.02, 0.02
        if btag in tf_sig_cache:
            ref = tf_sig_cache[btag]
            reg = ref[(y_true != IGNORE) & (ref >= 0)]
            if len(reg):
                p_in = max(float((reg == 1).mean()), 0.001)
                p_out = max(float((reg == 2).mean()), 0.001)

        close = feat["close"].to_numpy()
        high = feat["high"].to_numpy()
        low = feat["low"].to_numpy()
        tp_arr = feat["tp"].to_numpy()
        sl_arr = feat["sl"].to_numpy()

        for inst, lo, hi in slices:
            signals: dict[str, np.ndarray] = {
                "rf": sig_rf[lo:hi].astype(np.int64),
                "logreg": sig_lr[lo:hi].astype(np.int64),
                "ridge": sig_ridge[lo:hi].astype(np.int64),
                "mlp": sig_mlp[lo:hi].astype(np.int64),
            }
            if sig_lgbm is not None:
                signals["lgbm"] = sig_lgbm[lo:hi].astype(np.int64)
            if sig_xgb is not None:
                signals["xgb"] = sig_xgb[lo:hi].astype(np.int64)
            if btag in tf_sig_cache:
                signals["transformer"] = tf_sig_cache[btag][lo:hi].astype(
                    np.int64
                )
            rng = np.random.default_rng(
                (args.seed + zlib.crc32(inst.encode())) % (2**31)
            )
            noise = rng.random(hi - lo)
            sig_rand = np.zeros(hi - lo, dtype=np.int64)
            sig_rand[noise < p_in] = 1
            sig_rand[noise > 1 - p_out] = 2
            signals["random"] = sig_rand

            for m, sig_m in signals.items():
                res = simulate(
                    close[lo:hi], high[lo:hi], low[lo:hi], sig_m,
                    tp_arr[lo:hi], sl_arr[lo:hi],
                    commission, slippage, max_hold,
                )
                trades_n[m] += res["n_trades"]
                rets[m].append(res["total_return_pct"])
                detail[m][f"{btag}/{inst}"] = res

            lbl_mask = y_true[lo:hi] != IGNORE
            y_t = y_true[lo:hi][lbl_mask]
            for m, sig_m in signals.items():
                pred = sig_m[lbl_mask]
                if m == "transformer":
                    known = pred >= 0
                    pred, y_sub = pred[known], y_t[known]
                else:
                    y_sub = y_t
                if not len(y_sub):
                    continue
                acc[m][0] += int((pred == y_sub).sum())
                acc[m][1] += len(y_sub)
                f1s[m].append(_f1_macro(y_sub, pred))
        print(f"[{btag}] slices: {len(slices)}, rows: {feat.height}",
              flush=True)

    report: dict = {
        "config": {
            "seq_len": seq_len,
            "commission_pct": commission,
            "slippage_pct": slippage,
            "max_bars_hold": max_hold,
            "bases": [str(x) for x in bases],
        },
        "models": {},
    }
    hdr = (
        f"\n{'model':<12}{'trades':>8}{'winrate':>9}{'ret%/slice':>12}"
        f"{'acc':>8}{'macroF1':>9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for m in models:
        a = round(acc[m][0] / acc[m][1], 4) if acc[m][1] else None
        f = round(float(np.mean(f1s[m])), 4) if f1s[m] else None
        r = round(float(np.mean(rets[m])), 3) if rets[m] else 0.0
        report["models"][m] = {
            "n_trades": trades_n[m],
            "mean_slice_return_pct": r,
            "action_accuracy": a,
            "macro_f1": f,
            "by_slice": detail[m],
        }
        print(
            f"{m:<12}{trades_n[m]:>8}"
            f"{a if a is not None else float('nan'):>9.4f}"
            f"{r:>12.3f}"
            f"{a if a is not None else float('nan'):>8.4f}"
            f"{f if f is not None else float('nan'):>9.4f}"
        )
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    main()







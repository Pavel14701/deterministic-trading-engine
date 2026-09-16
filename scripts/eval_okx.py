"""Evaluate a trained EntryExitTransformer on the test segment.

Usage (from the repo root, after train_okx.py):

    uv run python scripts/eval_okx.py --data data/okx --model runs/okx/best.pt

Loads the model checkpoint (raw state_dict saved by train_one_round),
rebuilds the architecture from configs/ai.yaml + meta.json (the same
way quickstart does), runs inference over the test segment and writes
runs/okx/eval.json with accuracy / precision / recall per action class,
a confusion matrix and the outcome-AUC.

Note: architecture CLI overrides used at training time (hidden_size,
num_layers, num_heads, seq_len) must be repeated here via the same
flags, otherwise the checkpoint will not load.
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PRICE_COLS = ["open", "high", "low", "close", "volume"]
TP_SL_COLS = ["tp", "sl"]
IGNORE = -100


def _action_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Per-class accuracy/precision/recall + confusion matrix (3 classes)."""
    labels = [0, 1, 2]
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y_true, y_pred, strict=True):
        cm[t, p] += 1
    out: dict = {"confusion_matrix": cm.tolist()}
    names = {0: "hold", 1: "entry", 2: "exit"}
    for c in labels:
        tp = int(cm[c, c])
        fp = int(cm[:, c].sum() - tp)
        fn = int(cm[c, :].sum() - tp)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[names[c]] = {
            "support": int(cm[c, :].sum()),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
        }
    out["accuracy"] = round(float((y_true == y_pred).mean()), 4)
    return out


def _auc(y_true: np.ndarray, score: np.ndarray) -> float | None:
    """Rank-based AUC (Mann-Whitney); None when a class is missing."""
    pos = score[y_true == 1]
    neg = score[y_true == 0]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(score) + 1)
    return float(
        (ranks[y_true == 1].sum() - len(pos) * (len(pos) + 1) / 2)
        / (len(pos) * len(neg))
    )


def main() -> None:
    """Run the test-segment evaluation and persist runs/okx/eval.json."""
    import torch  # heavy import kept lazy

    from ai.src.config import load_config
    from ai.src.io import load_order_blocks_parquet
    from ai.src.metrics import compute_action_accuracy, compute_trade_metrics
    from ai.src.training import build_loader_from_parquet
    from ai.src.transformer import EntryExitTransformer

    ap = argparse.ArgumentParser(description="Evaluate on the test segment")
    ap.add_argument("--data", default="data/okx")
    ap.add_argument("--model", default="runs/okx/best.pt")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--seq-len", type=int, default=None)
    ap.add_argument("--hidden-size", type=int, default=None)
    ap.add_argument("--num-layers", type=int, default=None)
    ap.add_argument("--num-heads", type=int, default=None)
    ap.add_argument("--out", default="runs/okx/eval.json")
    args = ap.parse_args()

    data = REPO / args.data
    meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    ind_cols = list(meta["ind_cols"])
    sig_cols = list(meta.get("sig_cols") or [])
    cfg = load_config(REPO / "configs" / "ai.yaml")
    m = cfg.model
    seq_len = args.seq_len or m.seq_len

    model = EntryExitTransformer(
        n_price_feats=len(PRICE_COLS),
        n_ind_feats=len(ind_cols),
        n_sig_feats=len(sig_cols),
        n_tp_sl_feats=len(TP_SL_COLS),
        hidden_size=args.hidden_size or m.hidden_size,
        num_layers=args.num_layers or m.num_layers,
        num_heads=args.num_heads or m.num_heads,
        outcome_mode=m.outcome_mode,
        n_patterns=m.n_patterns,
        max_seq_len=m.max_seq_len,
        max_ob_seq_len=m.max_ob_seq_len,
        ob_embedding_dim=m.ob_embedding_dim,
        atr_global=m.atr_global,
    )
    if seq_len > m.max_seq_len:
        raise ValueError(
            f"--seq-len {seq_len} exceeds the model capacity "
            f"(max_seq_len={m.max_seq_len} from configs/ai.yaml)"
        )
    state = torch.load(
        REPO / args.model, map_location="cpu", weights_only=True
    )
    model.load_state_dict(state)
    device = torch.device(
        args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    )
    model.to(device).eval()

    obs = load_order_blocks_parquet(
        str(data / "test" / "order_blocks.parquet")
    )
    loader, _df = build_loader_from_parquet(
        features_path=str(data / "test" / "features.parquet"),
        labels_path=str(data / "test" / "labels.parquet"),
        order_blocks=obs,
        seq_len=seq_len,
        price_cols=PRICE_COLS,
        ind_cols=ind_cols,
        sig_cols=sig_cols,
        tp_sl_cols=TP_SL_COLS,
        batch_size=args.batch_size,
        shuffle=False,
    )

    all_logits: list[torch.Tensor] = []
    all_tgt: list[torch.Tensor] = []
    all_out: list[torch.Tensor] = []
    with torch.inference_mode():
        for batch in loader:
            (prices, inds, sigs, tp, sl, obs_b, act, outc, _pat, _si, _bi) = (
                batch
            )
            logits, _out_logits, _ = model(
                prices.to(device),
                inds.to(device),
                sigs.to(device),
                tp.to(device),
                sl.to(device),
                obs_b,
            )
            mask = act != IGNORE
            if mask.any():
                all_logits.append(logits[mask].cpu())
                all_tgt.append(act[mask].cpu())
                all_out.append(outc[mask].cpu())
    if not all_logits:
        raise RuntimeError("no labelled bars in the test segment")
    logits = torch.cat(all_logits)
    y_true = torch.cat(all_tgt).numpy()
    y_pred = logits.argmax(dim=-1).numpy()
    outcome = torch.cat(all_out).numpy()

    action_acc = compute_action_accuracy(
        torch.tensor(logits), torch.tensor(y_true)
    )
    trade_metrics = compute_trade_metrics(
        torch.tensor(logits), torch.tensor(y_true), torch.tensor(outcome)
    )
    p_entry = torch.softmax(logits, dim=-1)[:, 1].numpy()
    report = {
        "device": str(device),
        "n_samples": len(y_true),
        "action": _action_metrics(y_true, y_pred),
        "action_accuracy_detail": action_acc,
        "trade_metrics": trade_metrics,
        "outcome_auc_entry": _auc(y_true, p_entry),
    }
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    main()

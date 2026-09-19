"""Train EntryExitTransformer on MTF candidate windows (D.2 step 2).

Task: binary classification per candidate window - "did the best stop
rule win" (y = best market r_net > 0).  The outcome head logit at the
decision bar (last position) is the training signal; the resulting
probability ``p_trf`` is later used as a third voice in the consensus
gate (see eval_trf_ab.py).

Model: ai.src.transformer.EntryExitTransformer with a small config
(2 layers, hidden 64) - the candidate sample is only ~2k train windows.
Order blocks are not passed (empty lists): the time encoder over the
normalised OHLCV+ATR window is the signal under test.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.src.transformer import EntryExitTransformer  # noqa: E402


def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    """Rank-based AUC (no sklearn dependency)."""
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1)
    sp = np.asarray(p, dtype=np.float64)
    for v in np.unique(sp):
        m = sp == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def forward_probs(model, dev, xb: torch.Tensor, batch: int) -> np.ndarray:
    """Outcome-head probability at the decision bar for a tensor."""
    model.eval()
    probs = []
    with torch.no_grad():
        for k in range(0, xb.shape[0], batch):
            x = xb[k : k + batch].to(dev)
            _, out_logits, _ = model(
                x[:, :, :5],
                x[:, :, 5:6],
                x[:, :, 6:7],
                x[:, :, 7:8],
                x[:, :, 8:9],
                [[] for _ in range(x.shape[0])],
            )
            probs.append(torch.sigmoid(out_logits[:, -1, 0]).cpu().numpy())
    return np.concatenate(probs)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="D.2: train EntryExitTransformer on MTF windows"
    )
    ap.add_argument("--npz", required=True)
    ap.add_argument("--out", default="data/trf_model")
    ap.add_argument("--window", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument(
        "--device", default="cuda" if torch.cuda.is_available() else "cpu"
    )
    args = ap.parse_args()

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = torch.device(args.device)

    data = np.load(REPO / args.npz, allow_pickle=False)
    X = data["X"].astype(np.float32)
    y = data["y"].astype(np.float32)
    split = data["split"].astype(str)
    masks = {s: split == s for s in ("train", "val", "test")}

    model = EntryExitTransformer(
        n_price_feats=5,
        n_ind_feats=1,
        n_sig_feats=1,
        n_tp_sl_feats=2,
        hidden_size=64,
        num_layers=2,
        num_heads=4,
        dropout=0.3,
        max_seq_len=args.window,
        outcome_mode="binary",
        n_action_classes=3,
        n_patterns=2,
        ob_embedding_dim=8,
    ).to(dev)

    Xt = {s: torch.from_numpy(X[m]) for s, m in masks.items()}
    yt = {s: torch.from_numpy(y[m]) for s, m in masks.items()}
    n_pos = float(y[masks["train"]].sum())
    pos_w = (len(y[masks["train"]]) - n_pos) / max(n_pos, 1.0)
    loss_fn = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pos_w, device=dev)
    )
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    best_val, best_state, bad = np.inf, None, 0
    n_train = Xt["train"].shape[0]
    for epoch in range(args.epochs):
        model.train()
        perm = torch.randperm(n_train)
        last = 0.0
        for k in range(0, n_train, args.batch):
            idx = perm[k : k + args.batch]
            xb = Xt["train"][idx].to(dev)
            yb = yt["train"][idx].float().to(dev)
            _, out_logits, _ = model(
                xb[:, :, :5],
                xb[:, :, 5:6],
                xb[:, :, 6:7],
                xb[:, :, 7:8],
                xb[:, :, 8:9],
                [[] for _ in range(xb.shape[0])],
            )
            loss = loss_fn(out_logits[:, -1, 0], yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            last = float(loss.item())

        eps = 1e-6
        val_p = forward_probs(model, dev, Xt["val"], args.batch)
        val_bce = -np.mean(
            yt["val"].numpy() * np.log(val_p + eps)
            + (1 - yt["val"].numpy()) * np.log(1 - val_p + eps)
        )
        print(
            f"epoch {epoch:3d} train_bce={last:.4f} val_bce={val_bce:.4f} "
            f"val_auc={auc_score(yt['val'].numpy(), val_p):.3f}",
            flush=True,
        )
        if val_bce < best_val - 1e-4:
            best_val, bad = float(val_bce), 0
            best_state = {
                k: v.detach().cpu().clone()
                for k, v in model.state_dict().items()
            }
        else:
            bad += 1
            if bad >= args.patience:
                print(f"early stop at epoch {epoch}")
                break

    model.load_state_dict(best_state)
    torch.save(best_state, out_dir / "entryexit_mtf.pt")
    tr_p = forward_probs(model, dev, Xt["train"], args.batch)
    va_p = forward_probs(model, dev, Xt["val"], args.batch)
    te_p = forward_probs(model, dev, Xt["test"], args.batch)

    probs = np.concatenate([tr_p, va_p, te_p]).astype(np.float32)
    ys = np.concatenate([y[masks[s]] for s in ("train", "val", "test")])
    sp = np.concatenate([np.full(int(m.sum()), s) for s, m in masks.items()])
    np.savez_compressed(out_dir / "probs.npz", p=probs, y=ys, split=sp)
    report = {
        "val_bce": best_val,
        "train_auc": auc_score(ys[sp == "train"], tr_p),
        "val_auc": auc_score(ys[sp == "val"], va_p),
        "test_auc": auc_score(ys[sp == "test"], te_p),
        "win_rate": float(ys.mean()),
        "n": int(ys.size),
    }
    (out_dir / "train_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("report:", report, flush=True)


if __name__ == "__main__":
    main()


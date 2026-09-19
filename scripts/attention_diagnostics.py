"""Attention diagnostics for the rejected transformer (D.2 use #2).

Question: does the time encoder attend to any specific bars before the
decision bar, or is attention flat (=> no temporal structure worth
engineering into LGBM features)?

Method: forward-hook on the first self-attention layer, average over
heads and over all candidate windows of a split, read the attention
row of the LAST-position query (the decision bar) -> a mass profile
over "bars before decision".  Report the profile in coarse buckets,
its entropy vs the uniform baseline, and the top-5 attended offsets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ai.src.transformer import EntryExitTransformer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="D.2: attention profile")
    ap.add_argument("--npz", default="data/trf_dataset/BTCUSDT_1h_win.npz")
    ap.add_argument("--ckpt", default="data/trf_model/entryexit_mtf.pt")
    ap.add_argument("--splits", nargs="+", default=["val", "test"])
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = np.load(REPO / args.npz, allow_pickle=False)
    X = data["X"].astype(np.float32)
    split = data["split"].astype(str)
    T = X.shape[1]

    model = EntryExitTransformer(
        n_price_feats=5,
        n_ind_feats=1,
        n_sig_feats=1,
        n_tp_sl_feats=2,
        hidden_size=64,
        num_layers=2,
        num_heads=4,
        dropout=0.0,
        max_seq_len=T,
        outcome_mode="binary",
        n_action_classes=3,
        n_patterns=2,
        ob_embedding_dim=8,
    ).to(dev)
    model.load_state_dict(
        torch.load(REPO / args.ckpt, map_location=dev, weights_only=True)
    )
    model.eval()

    layer0 = model.time_encoder.layers[0].self_attn

    def attn_rows(x: torch.Tensor) -> torch.Tensor:
        """Layer-0 self-attention weights, heads averaged: (B, T, T)."""
        feats = torch.cat(
            [x[:, :, :5], x[:, :, 5:6], x[:, :, 6:7], x[:, :, 7:8], x[:, :, 8:9]],
            dim=-1,
        )
        emb = model.time_input_proj(feats)
        emb = emb + model.time_pos_encoding[:, : x.shape[1], :].to(dev)
        _, w = layer0(emb, emb, emb, need_weights=True)
        return w.detach().cpu().numpy()

    profile = np.zeros(T, dtype=np.float64)
    total = 0
    for s in args.splits:
        xs = torch.from_numpy(X[split == s])
        for k in range(0, xs.shape[0], args.batch):
            x = xs[k : k + args.batch].to(dev)
            with torch.no_grad():
                w = attn_rows(x)  # heads averaged by need_weights
            profile += w[:, -1, :].sum(axis=0)  # query = decision bar
            total += x.shape[0]

    profile /= max(total, 1)
    uni = 1.0 / T
    entropy = float(-(profile * np.log(profile + 1e-12)).sum())
    max_entropy = float(np.log(T))
    offsets = np.arange(T)[::-1]  # bars before decision (0 = decision bar)
    order = np.argsort(profile)[::-1][:8]
    top = {f"-{int(offsets[i])}": round(float(profile[i]), 4) for i in order}

    report = {
        "n_windows": int(total),
        "splits": args.splits,
        "uniform_mass": round(uni, 5),
        "entropy_bits": round(entropy / np.log(2), 3),
        "max_entropy_bits": round(max_entropy / np.log(2), 3),
        "top5_offsets_bars_before_decision": top,
        "mass_last_5_bars": round(float(profile[-5:].sum()), 4),
        "mass_expected_if_uniform_last_5": round(5 * uni, 4),
        "mass_first_10_bars_oldest": round(float(profile[:10].sum()), 4),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

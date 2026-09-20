"""Unit tests for the EntryExitTransformer model.

This module tests the transformer model's forward pass in different modes
(binary, multiclass, regression) and verifies shape correctness and
device movement.
"""

from typing import Any

import pytest
import torch

from ai.transformer import EntryExitTransformer


@pytest.mark.unit
def test_transformer_forward(
    model_params: dict[str, Any],
    sample_batch_tensors: dict[str, Any],
) -> None:
    """Test the forward pass of EntryExitTransformer in binary outcome mode.

    The model should produce action, outcome, and pattern logits with
    correct shapes.  Outcome logits shape is (B, T, 1) for binary mode.

    Args:
        model_params: Fixture with model hyperparameters.
        sample_batch_tensors: Fixture with input tensors.

    Asserts:
        - Action logits shape: (B, T, 3)
        - Outcome logits shape: (B, T, 1)
        - Pattern logits shape: (B, T, n_patterns)

    """
    model = EntryExitTransformer(**model_params)
    batch = sample_batch_tensors
    action_logits, outcome_logits, pattern_logits = model(
        batch["prices"],
        batch["indicators"],
        batch["signals"],
        batch["tp"],
        batch["sl"],
        batch["order_blocks"],
    )
    B, T = batch["prices"].shape[0], batch["prices"].shape[1]  # noqa: N806
    assert action_logits.shape == (B, T, 3)
    assert outcome_logits.shape == (B, T, 1)  # binary mode
    assert pattern_logits.shape == (B, T, model_params["n_patterns"])


@pytest.mark.unit
def test_transformer_outcome_multiclass(
    model_params: dict[str, Any],
    sample_batch_tensors: dict[str, Any],
) -> None:
    """Test the forward pass with multiclass outcome mode.

    The outcome head should produce logits of shape (B, T, n_outcome_classes).

    Args:
        model_params: Fixture with model hyperparameters.
        sample_batch_tensors: Fixture with input tensors.

    Asserts:
        - Outcome logits shape: (B, T, 3) when n_outcome_classes=3.

    """
    params = model_params.copy()
    params["outcome_mode"] = "multiclass"
    params["n_outcome_classes"] = 3
    model = EntryExitTransformer(**params)
    batch = sample_batch_tensors
    _, outcome_logits, _ = model(
        batch["prices"],
        batch["indicators"],
        batch["signals"],
        batch["tp"],
        batch["sl"],
        batch["order_blocks"],
    )
    B, T = batch["prices"].shape[0], batch["prices"].shape[1]  # noqa: N806
    assert outcome_logits.shape == (B, T, 3)


@pytest.mark.unit
def test_transformer_outcome_regression(
    model_params: dict[str, Any],
    sample_batch_tensors: dict[str, Any],
) -> None:
    """Test the forward pass with regression outcome mode.

    The outcome head should produce logits of shape (B, T, 1).

    Args:
        model_params: Fixture with model hyperparameters.
        sample_batch_tensors: Fixture with input tensors.

    Asserts:
        - Outcome logits shape: (B, T, 1).

    """
    params = model_params.copy()
    params["outcome_mode"] = "regression"
    model = EntryExitTransformer(**params)
    batch = sample_batch_tensors
    _, outcome_logits, _ = model(
        batch["prices"],
        batch["indicators"],
        batch["signals"],
        batch["tp"],
        batch["sl"],
        batch["order_blocks"],
    )
    B, T = batch["prices"].shape[0], batch["prices"].shape[1]  # noqa: N806
    assert outcome_logits.shape == (B, T, 1)


@pytest.mark.unit
def test_transformer_device_movement(
    model_params: dict[str, Any],
    sample_batch_tensors: dict[str, Any],
) -> None:
    """Test that the model correctly moves tensors to the GPU if available.

    The test checks that after moving the model and inputs to CUDA,
    all output tensors reside on the CUDA device.

    Args:
        model_params: Fixture with model hyperparameters.
        sample_batch_tensors: Fixture with input tensors.

    Skips:
        If CUDA is not available, the test is skipped.

    """
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
    model = EntryExitTransformer(**model_params).to("cuda")
    batch = sample_batch_tensors
    # Move inputs to CUDA
    prices = batch["prices"].to("cuda")
    indicators = batch["indicators"].to("cuda")
    signals = batch["signals"].to("cuda")
    tp = batch["tp"].to("cuda")
    sl = batch["sl"].to("cuda")
    action_logits, outcome_logits, pattern_logits = model(
        prices, indicators, signals, tp, sl, batch["order_blocks"]
    )
    assert action_logits.device.type == "cuda"
    assert outcome_logits.device.type == "cuda"
    assert pattern_logits.device.type == "cuda"


# --- moved from tests/test_ob_pipeline.py (repo restructure v2): these
# --- tests reference the archived EntryExitTransformer and live here now.
def test_transformer_encodes_all_ob_fields():
    import torch

    from ai.transformer import EntryExitTransformer

    model = EntryExitTransformer(
        n_price_feats=5,
        n_ind_feats=2,
        n_sig_feats=2,
        hidden_size=16,
        num_layers=1,
        num_heads=2,
        max_seq_len=32,
        max_ob_seq_len=8,
    )
    ob = _mk_ob(timeframe="1H", retest_idx=20)
    numeric, type_id, structure_id, trend_id, tf_id = model._encode_ob(ob, 8)
    assert numeric.shape == (7,)
    assert type_id in (0, 1) and structure_id in (0, 1, 2, 3)
    assert trend_id in (0, 1, 2) and tf_id == 3  # '1H' maps to 3
    # forward pass with the enriched OB
    b, t = 1, 8
    prices = torch.randn(b, t, 5)
    out = model(
        prices,
        torch.randn(b, t, 2),
        torch.randn(b, t, 2),
        torch.randn(b, t, 1),
        torch.randn(b, t, 1),
        [[ob]],
    )
    assert out[0].shape == (b, t, 3)



def test_vectorised_ob_encoding_matches_per_block():
    """`_encode_obs` must reproduce `_encode_ob` row by row.

    The vectorised path is an optimisation only: identical numerics,
    identical categorical ids, and an empty block list must still yield a
    valid (padded) OB sequence.

    """
    import torch

    from ai.transformer import EntryExitTransformer

    model = EntryExitTransformer(
        n_price_feats=5,
        n_ind_feats=2,
        n_sig_feats=2,
        hidden_size=16,
        num_layers=1,
        num_heads=2,
        max_seq_len=32,
        max_ob_seq_len=8,
    )
    obs = [
        _mk_ob(
            id=0,
            block_type="demand",
            structure_label="fresh",
            trend_direction="up",
            timeframe="1m",
            retest_idx=-1,
        ),
        _mk_ob(
            id=1,
            block_type="supply",
            structure_label="retested",
            trend_direction="down",
            timeframe="1H",
            retest_idx=20,
        ),
        _mk_ob(
            id=2,
            block_type="demand",
            structure_label=None,
            trend_direction=None,
            timeframe="15m",
            retest_idx=3,
        ),
    ]
    device = torch.device("cpu")
    numeric, type_ids, struct_ids, trend_ids, tf_ids = model._encode_obs(
        obs, 32, device
    )
    assert numeric.shape == (3, 7)
    for k, ob in enumerate(obs):
        n, t_id, s_id, tr_id, tf_id = model._encode_ob(ob, 32)
        assert torch.allclose(numeric[k], n)
        assert (type_ids[k], struct_ids[k], trend_ids[k], tf_ids[k]) == (
            t_id,
            s_id,
            tr_id,
            tf_id,
        )
    # no blocks in a window: empty sequence, but the forward pass still works
    out = model(
        torch.randn(1, 8, 5),
        torch.randn(1, 8, 2),
        torch.randn(1, 8, 2),
        torch.randn(1, 8, 1),
        torch.randn(1, 8, 1),
        [[]],
    )
    assert out[0].shape == (1, 8, 3)


"""Sign-convention pin for per-asset slow carry (v3).

pos=+1 means SHORT perp (entered on positive funding) and must earn
+f; pos=-1 means LONG perp (entered on negative funding) and must
earn -f.  Regression guard: both v2 and v3 shipped a mirrored-sign
bug at least once.
"""
import numpy as np

from experiments.carry.funding_carry_v3 import per_asset_stream


def test_short_side_earns_positive_funding():
    n = 30
    s = per_asset_stream(np.full(n, 0.0003), np.full(n, 0.0003))
    # entry on day 0: carry 3bp minus half-RT 10bp = -7bp; held days pure +3bp
    assert abs(s[0] - (0.0003 - 0.001)) < 1e-12
    assert (s[1:] > 0).all()
    assert abs(s[1:] - 0.0003).max() < 1e-12


def test_long_side_earns_negative_funding():
    n = 30
    s = per_asset_stream(np.full(n, -0.0003), np.full(n, -0.0003))
    assert abs(s[0] - (0.0003 - 0.001)) < 1e-12  # -f = +3bp, same cost
    assert (s[1:] > 0).all()


def test_exit_on_sign_flip_charges_cost():
    n = 20
    sig = np.full(n, 0.0003)
    sig[10:] = -0.0001  # signal flips sign -> exit
    s = per_asset_stream(np.full(n, 0.0003), sig)
    assert s[10] < 0  # exit half-cost exceeds the day's carry
    assert (s[11:] == 0).all()  # flat afterwards


def test_dead_zone_no_entry():
    n = 30
    s = per_asset_stream(np.full(n, 0.0001), np.full(n, 0.0001))
    assert (s == 0).all()  # |sig| < 2bp: never enters


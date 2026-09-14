"""Signature tests (stdlib HMAC, OKX v5 scheme)."""

from okx.src.signing import sign_request, sign_ws_login


def test_rest_signature_deterministic() -> None:
    a = sign_request(
        "secret", "1700000000000", "GET", "/account/config", ""
    )
    b = sign_request(
        "secret", "1700000000000", "GET", "/account/config", ""
    )
    assert a == b
    assert a.endswith("=")  # base64 of 32 bytes
    assert len(a) == 44


def test_rest_signature_depends_on_every_part() -> None:
    base = sign_request("s", "1", "GET", "/p", "")
    assert base != sign_request("s2", "1", "GET", "/p", "")
    assert base != sign_request("s", "2", "GET", "/p", "")
    assert base != sign_request("s", "1", "POST", "/p", "")
    assert base != sign_request("s", "1", "GET", "/p2", "")
    assert base != sign_request("s", "1", "GET", "/p", "{}")


def test_ws_login_uses_self_verify_path() -> None:
    ws = sign_ws_login("s", "1", "{}")
    rest = sign_request("s", "1", "GET", "/users/self/verify", "{}")
    assert ws == rest

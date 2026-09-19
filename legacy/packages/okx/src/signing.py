"""OKX request signatures (TZ-15 section 3). stdlib only.

REST: base64(HMAC-SHA256(ts + method + requestPath + body, secret)).
WS login: the same over ts + "GET/users/self/verify" + body.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


WS_LOGIN_PATH = "/users/self/verify"


def sign_request(
    secret: str, timestamp: str, method: str, request_path: str, body: str
) -> str:
    """REST signature for the OK-ACCESS-SIGN header."""
    msg = f"{timestamp}{method.upper()}{request_path}{body}"
    return base64.b64encode(
        hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()


def sign_ws_login(secret: str, timestamp: str, body: str) -> str:
    """WS ``login`` op signature (fixed GET/users/self/verify path)."""
    return sign_request(secret, timestamp, "GET", WS_LOGIN_PATH, body)

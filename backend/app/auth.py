"""Who is asking: a short-lived token from the frontend server, which runs the GitHub sign-in.

A token is base64url(JSON payload) + "." + base64url(HMAC-SHA256 of that text), signed with
AUTH_SECRET. The frontend server and this server share the secret, and only they can make a token.
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

AUDIENCE = "api"  # a session cookie has another audience, so it cannot be sent here as a token


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class Viewer:
    id: str  # "github:<numeric account ID>", which stays the same if the user name changes
    login: str


def _signature(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def sign_token(payload: dict, secret: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{body}.{_signature(body, secret)}"


def verify_token(token: str, secret: str) -> Viewer:
    body, dot, signature = token.partition(".")
    if not dot or not hmac.compare_digest(_signature(body, secret), signature):
        raise InvalidToken("Bad signature.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        viewer = Viewer(id=str(payload["sub"]), login=str(payload["login"]))
        expires, audience = float(payload["exp"]), payload["aud"]
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise InvalidToken("Bad payload.") from exc
    if audience != AUDIENCE or expires <= time.time():
        raise InvalidToken("Expired or not for this server.")
    return viewer

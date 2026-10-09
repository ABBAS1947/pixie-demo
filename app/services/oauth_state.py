"""OAuth state management — prevents CSRF on OAuth callbacks.

Each authorization request generates a cryptographically random nonce,
stores it server-side with the user ID and expiry, and uses the nonce
as the OAuth `state` parameter. The callback must consume the nonce
exactly once within the TTL window.
"""

import secrets
import threading
import time
from dataclasses import dataclass, field

# In-memory store — sufficient for single-process dev/beta.
# For multi-worker production, move to Redis or a DB table.
_NONCES: dict[str, "_OAuthState"] = {}
_NONCE_TTL = 600  # 10 minutes
_MAX_NONCES = 1000
_MAX_NONCES_PER_USER = 3
_NONCE_LOCK = threading.Lock()


class OAuthStateLimitExceeded(Exception):
    """The process-local OAuth state store is at capacity."""


@dataclass
class _OAuthState:
    user_id: str
    code_verifier: str = ""
    created_at: float = field(default_factory=time.time)
    used: bool = False

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > _NONCE_TTL


def generate_oauth_state(user_id: str, code_verifier: str = "") -> str:
    """Generate a one-time nonce bound to the given user ID and PKCE verifier."""
    with _NONCE_LOCK:
        _cleanup_locked()
        user_states = sum(1 for state in _NONCES.values() if state.user_id == user_id)
        if user_states >= _MAX_NONCES_PER_USER or len(_NONCES) >= _MAX_NONCES:
            raise OAuthStateLimitExceeded("Too many pending OAuth authorizations")
        nonce = secrets.token_urlsafe(32)
        _NONCES[nonce] = _OAuthState(user_id=user_id, code_verifier=code_verifier)
        return nonce


def consume_oauth_state(nonce: str) -> tuple[str, str] | None:
    """Consume a nonce and return (user_id, code_verifier), or None if invalid."""
    with _NONCE_LOCK:
        state = _NONCES.pop(nonce, None)
    if state is None:
        return None
    if state.used:
        return None
    if state.expired:
        return None
    state.used = True
    return state.user_id, state.code_verifier


def _cleanup():
    """Evict expired nonces periodically."""
    with _NONCE_LOCK:
        _cleanup_locked()


def _cleanup_locked():
    """Evict expired nonces; caller must hold _NONCE_LOCK."""
    now = time.time()
    expired = [k for k, v in _NONCES.items() if (now - v.created_at) > _NONCE_TTL]
    for k in expired:
        _NONCES.pop(k, None)

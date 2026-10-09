"""Auth: Supabase JWT validation.

The backend never trusts a client-supplied user_id. Identity comes only
from the JWT. Real Supabase user tokens are ES256 (asymmetric) and are
verified against the project's JWKS public key. Dev mode (auth_dev_mode=True)
also accepts HS256 tokens minted locally by create_dev_token so the flow is
testable without a live Supabase round-trip.
"""

from datetime import datetime, timedelta, timezone
import logging

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidAlgorithmError, PyJWKClientConnectionError

from app.core.config import settings

SECRET_KEY = settings.supabase_jwt_secret
ALGORITHM = "HS256"
logger = logging.getLogger(__name__)


class AuthVerificationUnavailable(Exception):
    """The verifier could not reach Supabase to retrieve signing keys."""


def create_token(user_id: str) -> str:
    """Compatibility helper for local HS256 tokens used in dev/test flows."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    """Validate a locally-issued HS256 token. Returns payload or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_dev_token(auth_id: str, *, minutes: int = 60) -> str:
    """Mint a dev-mode HS256 JWT. Only valid while auth_dev_mode is on."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": auth_id,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "aud": "authenticated",
        "role": "authenticated",
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Singleton JWKS client (PyJWKClient caches the fetched key set)."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        )
    return _jwks_client


def decode_token(token: str) -> dict:
    """Validate a JWT and return its claims. Raises jwt.PyJWTError on failure."""
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")

    try:
        # Supabase asymmetric user tokens carry a kid and are verified via JWKS.
        if algorithm != "HS256" or not settings.auth_dev_mode:
            if algorithm not in {"ES256", "RS256"}:
                raise InvalidAlgorithmError("Unsupported Supabase JWT signing algorithm")
            key = _get_jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
                options={"require": ["exp", "sub", "aud", "iss"]},
                leeway=60,  # tolerate local clock skew vs Supabase's server clock
            )

        # Dev fallback: locally-minted HS256 token.
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated", options={"require": ["exp", "sub", "aud"]}, leeway=60)
    except PyJWKClientConnectionError as exc:
        logger.warning("Supabase JWKS endpoint is unavailable")
        raise AuthVerificationUnavailable from exc
    except Exception as exc:
        # Keep the bearer token out of logs while making auth failures diagnosable.
        logger.warning("Supabase JWT validation failed (alg=%s, error=%s)", algorithm, type(exc).__name__)
        raise

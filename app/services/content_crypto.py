"""Versioned AEAD envelopes and self-hosted OpenBao envelope-key registry.

No plaintext fallback, root tokens, exportable transit keys, or embedded keys.
Authorization is performed by callers; AAD independently binds ciphertext to
the expected owner/resource/field. Registry snapshots contain wrapped keys.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

PREFIX = "pixie:v1:"
MAX_BYTES = 50 * 1024 * 1024


class CryptoUnavailable(RuntimeError):
    pass


class CiphertextInvalid(ValueError):
    pass


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def owner_id(value: str | uuid.UUID) -> str:
    return str(uuid.UUID(str(value)))


def atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class OpenBaoRegistry:
    """Separate wrapped-key files, bounded cache; snapshots need expiry tracking."""

    def __init__(self):
        self._cache: dict[tuple[str, str, str], tuple[float, bytes]] = {}
        self._lock = threading.RLock()

    def _path(self, domain: str, owner: str) -> Path:
        if domain not in {"private", "school", "integration"}:
            raise CiphertextInvalid("Invalid encryption domain")
        root = Path(settings.key_registry_root).resolve()
        directory = root / domain
        path = directory / f"{owner_id(owner)}.json"
        if directory.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise CryptoUnavailable("Unsafe key registry path")
        return path

    def _transit(self, operation: str, domain: str, payload: dict) -> dict:
        if not settings.openbao_url.startswith("https://"):
            raise CryptoUnavailable("OpenBao TLS is required")
        try:
            token = Path(settings.openbao_token_file).read_text().strip()
            if not token:
                raise ValueError("empty credential")
            with httpx.Client(timeout=5, verify=settings.openbao_ca_file or True, follow_redirects=False) as client:
                response = client.post(
                    f"{settings.openbao_url.rstrip('/')}/v1/transit/{operation}/pixie-{settings.deployment_environment}-{domain}",
                    headers={"X-Vault-Token": token}, json=payload,
                )
                response.raise_for_status()
                return response.json()["data"]
        except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
            raise CryptoUnavailable("Key service is unavailable") from exc

    def _context(self, domain: str, owner: str, version: str) -> str:
        return _b64(_json([settings.deployment_environment, domain, owner_id(owner), version]))

    def provision(self, domain: str, owner: str) -> str:
        """Create once; caller must serialize provisioning across processes."""
        path = self._path(domain, owner)
        with self._lock:
            if path.exists():
                return json.loads(path.read_text())["active"]
            version = str(uuid.uuid4())
            key = secrets.token_bytes(32)
            wrapped = self._transit("encrypt", domain, {
                "plaintext": _b64(key), "associated_data": self._context(domain, owner, version),
            })["ciphertext"]
            atomic_private_write(path, _json({"active": version, "versions": {version: wrapped}}))
            return version

    def current_version(self, domain: str, owner: str) -> str:
        try:
            return json.loads(self._path(domain, owner).read_text())["active"]
        except (OSError, ValueError, KeyError) as exc:
            raise CryptoUnavailable("Owner encryption key is unavailable") from exc

    def key(self, domain: str, owner: str, version: str) -> bytes:
        owner = owner_id(owner)
        path = self._path(domain, owner)
        with self._lock:
            # Check live registry even on cache hits; deleted keys stay deleted.
            try:
                wrapped = json.loads(path.read_text())["versions"][version]
            except (OSError, ValueError, KeyError) as exc:
                raise CryptoUnavailable("Owner encryption key is unavailable") from exc
            cache_key = (domain, owner, version)
            cached = self._cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            decoded = self._transit("decrypt", domain, {
                "ciphertext": wrapped, "associated_data": self._context(domain, owner, version),
            })["plaintext"]
            key = _unb64(decoded)
            if len(key) != 32:
                raise CryptoUnavailable("Invalid data key")
            if len(self._cache) >= 128:
                self._cache.clear()
            self._cache[cache_key] = (time.monotonic() + 30, key)
            return key

    def retire(self, domain: str, owner: str) -> None:
        with self._lock:
            self._path(domain, owner).unlink(missing_ok=True)
            self._cache = {k: v for k, v in self._cache.items() if k[:2] != (domain, owner_id(owner))}

    def rotate(self, domain: str, owner: str) -> str:
        """Caller holds an owner DB lock; old versions remain for live content."""
        path = self._path(domain, owner)
        with self._lock:
            data = json.loads(path.read_text())
            version = str(uuid.uuid4())
            wrapped = self._transit("encrypt", domain, {
                "plaintext": _b64(secrets.token_bytes(32)),
                "associated_data": self._context(domain, owner, version),
            })["ciphertext"]
            data["versions"][version] = wrapped
            data["active"] = version
            atomic_private_write(path, _json(data))
            return version

    def rewrap(self, domain: str, owner: str) -> None:
        path = self._path(domain, owner)
        with self._lock:
            data = json.loads(path.read_text())
            for version, wrapped in data["versions"].items():
                data["versions"][version] = self._transit("rewrap", domain, {
                    "ciphertext": wrapped, "associated_data": self._context(domain, owner, version),
                })["ciphertext"]
            atomic_private_write(path, _json(data))


registry = OpenBaoRegistry()
_capacity = threading.BoundedSemaphore(2)


def seal(content: bytes, *, domain: str, owner: str, resource: str, field: str, keys=registry) -> str:
    if len(content) > MAX_BYTES:
        raise ValueError("Encrypted object exceeds size limit")
    with _capacity:
        version = keys.current_version(domain, owner)
        header = {"v": 1, "alg": "AES-256-GCM", "environment": settings.deployment_environment,
                  "domain": domain, "owner": owner_id(owner), "resource": str(resource),
                  "field": field, "key": version}
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(keys.key(domain, owner, version)).encrypt(nonce, content, _json(header))
        return PREFIX + _b64(_json({"header": header, "nonce": _b64(nonce), "ciphertext": _b64(encrypted)}))


def unseal(envelope: str, *, domain: str, owner: str, resource: str, field: str, keys=registry) -> bytes:
    if not envelope.startswith(PREFIX) or len(envelope) > 100 * 1024 * 1024:
        raise CiphertextInvalid("Encrypted content required")
    with _capacity:
        try:
            data = json.loads(_unb64(envelope[len(PREFIX):]))
            header = data["header"]
            expected = {"v": 1, "alg": "AES-256-GCM", "environment": settings.deployment_environment,
                        "domain": domain, "owner": owner_id(owner), "resource": str(resource),
                        "field": field, "key": header["key"]}
            if header != expected:
                raise ValueError("context mismatch")
            nonce = _unb64(data["nonce"])
            ciphertext = _unb64(data["ciphertext"])
            if len(nonce) != 12 or len(ciphertext) > MAX_BYTES + 16:
                raise ValueError("invalid size")
            return AESGCM(keys.key(domain, owner, header["key"])).decrypt(nonce, ciphertext, _json(header))
        except CryptoUnavailable:
            raise
        except Exception as exc:
            raise CiphertextInvalid("Encrypted content could not be authenticated") from exc

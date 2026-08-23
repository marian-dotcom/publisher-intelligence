"""Password hashing (Argon2id) and CSPRNG session-token helpers.

Security invariants: one-way password hashing with explicit configured
parameters; session secrets are cryptographically random; the database stores
only a SHA-256 representation of the opaque session token, never the raw
credential.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Explicitly configured Argon2id parameters (testable per EP-025a plan).
HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

SESSION_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Invalid hash encoding must not leak implementation details.
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()

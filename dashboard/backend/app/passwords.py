"""
Password hashing for real user accounts (app_user table, Phase 3) — replaces
the plaintext-in-.env single admin credential app/auth.py used to compare
against directly.

bcrypt handles its own salting and is deliberately slow (tunable work
factor) — this is the standard choice for password storage, not a general
hashing primitive.
"""

import bcrypt


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(plaintext: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode(), password_hash.encode())
    except ValueError:
        # Malformed hash (shouldn't happen for rows this app wrote itself) —
        # fail closed rather than raising into the login endpoint.
        return False

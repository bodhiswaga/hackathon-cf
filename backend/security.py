import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split('$')
    if len(parts) == 2:  # Preserve accounts from the MVP; rehash after login.
        salt, digest = parts
        iterations = 260000
    else:
        _, rounds, salt, digest = parts
        iterations = int(rounds)
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex(), digest)

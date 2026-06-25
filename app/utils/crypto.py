import base64
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Fixed, non-secret salt — the security boundary here is "ties to this
# machine", not "resists a determined attacker with disk access"; a
# per-install random salt would need its own persisted storage and
# wouldn't add real protection against someone who already has the DB file.
_SALT = b"job-hunt-assistant-llm-keys-v1"


def _machine_key() -> bytes:
    machine_id = str(uuid.getnode()).encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(machine_id))


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return Fernet(_machine_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return Fernet(_machine_key()).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Machine changed (new uuid.getnode()) or the DB was copied to
        # another box — fail soft so a stale/foreign key just looks
        # "not configured" instead of crashing Settings on load.
        return ""

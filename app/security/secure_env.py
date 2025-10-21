from __future__ import annotations
import base64, json, os
from pathlib import Path
from typing import Optional

import keyring  # pip install keyring
from dotenv import load_dotenv, set_key

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

SERVICE_NAME = "sportsthread_app_env"
PASSPHRASE_USERNAME = "env_passphrase"

def _derive_key(passphrase: str, salt_b64: str) -> bytes:
    salt = base64.b64decode(salt_b64)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        iterations=200_000, backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

def _decrypt_env(enc_path: Path, passphrase: str) -> str:
    payload = json.loads(enc_path.read_text())
    key = _derive_key(passphrase, payload["salt"])
    data = base64.b64decode(payload["ct"])
    env_bytes = Fernet(key).decrypt(data)
    return env_bytes.decode()

def _store_passphrase(passphrase: str) -> None:
    keyring.set_password(SERVICE_NAME, PASSPHRASE_USERNAME, passphrase)

def _get_passphrase() -> Optional[str]:
    try:
        return keyring.get_password(SERVICE_NAME, PASSPHRASE_USERNAME)
    except Exception:
        return None

def ensure_env(app_dir: Path, prompt_for_passphrase) -> None:
    """
    Load an existing .env; else, if .env.enc present, decrypt it.
    `prompt_for_passphrase` is a callable that shows a GUI prompt and returns str|None.
    """
    # 1) If .env exists, just load it.
    env_path = app_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        return

    # 2) If there is an encrypted env, decrypt using keychain or prompt.
    enc_path = app_dir / ".env.enc"
    if enc_path.exists():
        passphrase = _get_passphrase()
        if not passphrase:
            passphrase = prompt_for_passphrase()
            if not passphrase:
                return  # user canceled; app will show its normal missing-config UI
            _store_passphrase(passphrase)

        try:
            content = _decrypt_env(enc_path, passphrase)
        except Exception:
            # bad passphrase; prompt once more
            passphrase = prompt_for_passphrase(error="Passphrase incorrect. Try again.")
            if not passphrase:
                return
            _store_passphrase(passphrase)
            content = _decrypt_env(enc_path, passphrase)

        # Write decrypted .env locally (private to user’s machine) and load.
        env_path.write_text(content, encoding="utf-8")
        load_dotenv(env_path)
        return

    # 3) Fallbacks: allow CWD/home if present
    load_dotenv()  # CWD
    load_dotenv(Path.home() / ".config" / "sportsthread" / ".env")

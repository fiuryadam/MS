from __future__ import annotations
import json
import keyring
from google.oauth2.credentials import Credentials
from msc.config import KEYRING_SERVICE, KEYRING_USERNAME


def save_credentials(creds: Credentials) -> None:
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(data))


def load_credentials() -> Credentials | None:
    raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not raw:
        return None
    data = json.loads(raw)
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )


def delete_credentials() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass

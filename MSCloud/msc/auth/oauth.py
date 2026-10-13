from __future__ import annotations
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from msc.auth.tokens import delete_credentials, load_credentials, save_credentials
from msc.config import SCOPES
from msc.paths import credentials_path

log = logging.getLogger(__name__)


class CredentialsError(Exception):
    """Missing or invalid OAuth configuration."""


def get_credentials() -> Credentials | None:
    creds = load_credentials()
    if not creds:
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.exception("Failed to refresh credentials")
            return None
        save_credentials(creds)
        return creds
    log.warning("Stored credentials unusable")
    return None


def login_interactive() -> Credentials:
    path = credentials_path()
    if not path.is_file():
        raise CredentialsError(
            f"Missing {path.name}. Copy credentials.json.example and add your OAuth client."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        authorization_prompt_message="",
        success_message="Signed in. You can close this tab and return to MSCloud.",
    )
    save_credentials(creds)
    return creds


def logout() -> None:
    delete_credentials()

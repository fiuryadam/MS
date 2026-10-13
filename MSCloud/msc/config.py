APP_NAME = "MSCloud"
KEYRING_SERVICE = "MSCloud"
KEYRING_USERNAME = "google_oauth"

SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_ROOT_ID = "root"

GOOGLE_EXPORT: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

FOLDER_MIME = "application/vnd.google-apps.folder"

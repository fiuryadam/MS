# MSCloud

Desktop Google Drive client (Python + PySide6) for school assignment phase 1: OAuth sign-in, browse My Drive, upload, download selected files to a folder (Google Docs export as DOCX/XLSX/PPTX), open in external apps.

## Setup

1. **Python 3.11+** recommended.

2. Create virtual environment inside `MSCloud`:

   ```powershell
   cd MSCloud
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Google Cloud Console**

   - Create a project (or use existing).
   - Enable **Google Drive API**.
   - Create **OAuth client ID** → Application type **Desktop app**.
   - Download JSON and save as `MSCloud/credentials.json` (never commit this file).

4. If the app is in testing mode, add your Google account under OAuth consent screen → Test users.

## Run

```powershell
cd MSCloud
.\.venv\Scripts\Activate.ps1
python -m msc
```

Sign in opens your browser; tokens are stored in the Windows Credential Manager (keyring), not in the project folder.

## Data locations

| Item | Location |
|------|----------|
| SQLite metadata cache | `%LOCALAPPDATA%\MSCloud\msc.sqlite` |
| Logs | `%LOCALAPPDATA%\MSCloud\logs\msc.log` |
| Crash dumps | `%LOCALAPPDATA%\MSCloud\logs\crash.log` |
| OAuth client secrets | `MSCloud/credentials.json` (local only) |

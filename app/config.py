"""App-wide configuration, read from environment variables (optionally loaded
from a local .env file — see .env.example). No secrets are ever committed:
.env is gitignored."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VISION_MODEL = os.environ.get("AI_UGC_VISION_MODEL", "claude-sonnet-5")

# KIE (video generation)
KIE_API_KEY = os.environ.get("KIE_API_KEY", "")
KIE_MODEL = os.environ.get("KIE_MODEL", "gemini-omni-video")

# Google Drive (public hosting for KIE's input images; later also Phase 4 video save).
# A service account is simplest for a backend service — no interactive OAuth flow.
# Share the target Drive folder(s) with the service account's email address.
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_DRIVE_INPUT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_INPUT_FOLDER_ID", "")

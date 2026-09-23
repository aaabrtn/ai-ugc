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

# Public image hosting for KIE's input images uses KIE's own File Upload API
# (see app/integrations/kie.py) — no separate credential, reuses KIE_API_KEY.

# Cost tracking: KIE's task-status API doesn't return a per-task price, so
# instead of guessing at an undocumented field, the app uses a flat rate you
# provide here — accurate as long as every video is submitted with the same
# settings the app always uses (10s, 9:16, 720p), which it is. Check your KIE
# dashboard/pricing page for the credit cost of that combination, and how much
# USD your credits actually cost (top-up amount / credits received) if you
# want a $ figure too. Leave blank to just not show a video-generation cost.
KIE_CREDITS_PER_VIDEO = os.environ.get("KIE_CREDITS_PER_VIDEO", "")
KIE_USD_PER_CREDIT = os.environ.get("KIE_USD_PER_CREDIT", "")

"""Anonymous, zero-config public image hosting via catbox.moe. Used to make
locally-uploaded reference photos briefly fetchable by KIE's servers, which
can't reach localhost. No account or credentials needed — uploads are
anonymous, and once made, the file is reachable by anyone who has the exact
URL (there's no owner account to revoke or delete through)."""

from pathlib import Path

import httpx

CATBOX_API_URL = "https://catbox.moe/user/api.php"

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class CatboxError(Exception):
    """The upload ran but failed."""


def upload_public_image(path: Path) -> str:
    mime_type = MIME_TYPES.get(path.suffix.lower(), "image/jpeg")
    try:
        with path.open("rb") as f:
            resp = httpx.post(
                CATBOX_API_URL,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (path.name, f, mime_type)},
                timeout=60,
            )
    except httpx.RequestError as e:
        raise CatboxError(f"Couldn't reach catbox.moe: {e}") from e

    text = resp.text.strip()
    if resp.status_code != 200 or not text.startswith("https://"):
        raise CatboxError(f"catbox.moe upload failed: {text or f'HTTP {resp.status_code}'}")

    return text

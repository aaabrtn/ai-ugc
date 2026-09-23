import uuid
from pathlib import Path

import httpx

from app.scraping.methods import USER_AGENT

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def download_image(dest_dir: Path, image_url: str, timeout: float = 10.0) -> Path:
    """Download a remote image into dest_dir. Raises on any failure — the caller
    decides what a failed download means for the overall fetch."""
    resp = httpx.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = ALLOWED_IMAGE_TYPES.get(content_type)
    if not ext:
        raise ValueError(f"Unsupported image content type: {content_type or 'unknown'}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = dest_dir / filename
    dest_path.write_bytes(resp.content)
    return dest_path

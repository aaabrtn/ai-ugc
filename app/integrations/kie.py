"""KIE API client for video generation (Gemini Omni family).

Reference: https://docs.kie.ai — `POST /api/v1/jobs/createTask` (model
`gemini-omni-video`) to submit, `GET /api/v1/jobs/recordInfo` to poll.
Generation is asynchronous: createTask returns a `taskId` immediately, not a
finished video — the caller polls recordInfo (or supplies a callback URL,
which this app doesn't use since it has no public endpoint to receive one).

Also includes upload_public_image, which uses KIE's own File Upload API
(a different host, kieai.redpandaai.co) to host local reference photos at a
public URL KIE's video/character endpoints can fetch — no third-party host
needed, and no separate credential beyond the same KIE_API_KEY.
"""

import json
from pathlib import Path

import httpx

from app.config import KIE_API_KEY, KIE_MODEL

KIE_BASE_URL = "https://api.kie.ai"
FILE_UPLOAD_BASE_URL = "https://kieai.redpandaai.co"

# KIE's own quota rule for this endpoint: images + videos*2 + character_ids <= 7.
# We never send video_list, so this simplifies to images + character_ids <= 7.
MAX_INPUT_SLOTS = 7

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class KieNotConfigured(Exception):
    """No KIE API key is set up."""


class KieError(Exception):
    """The KIE API call ran but failed, or returned something unusable."""


def _auth_header() -> dict:
    if not KIE_API_KEY:
        raise KieNotConfigured(
            "No KIE API key is configured. Set KIE_API_KEY in your environment (see .env.example) to "
            "enable video generation."
        )
    return {"Authorization": f"Bearer {KIE_API_KEY}"}


def _headers() -> dict:
    return {**_auth_header(), "Content-Type": "application/json"}


def upload_public_image(path: Path) -> str:
    """Uploads a local image to KIE's own file storage and returns a public
    URL KIE's other endpoints can fetch it from. Uploaded files are temporary
    (auto-deleted within roughly a day) — fine here since the URL is used
    immediately in the same request, never relied on afterward."""
    mime_type = MIME_TYPES.get(path.suffix.lower(), "image/jpeg")
    try:
        with path.open("rb") as f:
            resp = httpx.post(
                f"{FILE_UPLOAD_BASE_URL}/api/file-stream-upload",
                headers=_auth_header(),
                files={"file": (path.name, f, mime_type)},
                timeout=60,
            )
    except httpx.RequestError as e:
        raise KieError(f"Couldn't reach KIE's file upload service: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise KieError(f"KIE's file upload returned an unreadable response (HTTP {resp.status_code}).") from e

    file_url = (payload.get("data") or {}).get("fileUrl")
    if not file_url:
        raise KieError(payload.get("msg") or f"KIE's file upload didn't return a file URL (HTTP {resp.status_code}).")
    return file_url


def image_budget(character_ids: list[str], character_uses_body: bool) -> int:
    """How many image_urls slots remain after reserving space for character_ids.
    A character with a portrait+body reference pair costs 2 slots each; a
    portrait-only character costs 1."""
    per_character = 2 if character_uses_body else 1
    used = len(character_ids) * per_character
    return max(0, MAX_INPUT_SLOTS - used)


def submit_video_task(
    *,
    prompt: str,
    character_ids: list[str],
    image_urls: list[str],
    duration: str = "10",
    aspect_ratio: str = "9:16",
    resolution: str = "720p",
) -> str:
    body = {
        "model": KIE_MODEL,
        "input": {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        },
    }
    if character_ids:
        body["input"]["character_ids"] = character_ids
    if image_urls:
        body["input"]["image_urls"] = image_urls

    try:
        resp = httpx.post(f"{KIE_BASE_URL}/api/v1/jobs/createTask", headers=_headers(), json=body, timeout=30)
    except httpx.RequestError as e:
        raise KieError(f"Couldn't reach KIE: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise KieError(f"KIE returned an unreadable response (HTTP {resp.status_code}).") from e

    task_id = (payload.get("data") or {}).get("taskId")
    if not task_id:
        raise KieError(payload.get("msg") or f"KIE didn't return a task ID (HTTP {resp.status_code}).")
    return task_id


def create_character(*, descriptions: str, image_urls: list[str], character_name: str = "") -> dict:
    """Registers a new character with KIE (`gemini-omni-character`). Returns the raw
    `data` object: at least `characterId`, plus `characterName`/`imageUrl`/`bodyImageUrl`.
    `image_urls` must already be publicly fetchable — index 0 is the portrait, an
    optional index 1 is a body reference photo (max 2 images total)."""
    body = {"descriptions": descriptions, "image_urls": image_urls[:2]}
    if character_name:
        body["character_name"] = character_name

    try:
        resp = httpx.post(f"{KIE_BASE_URL}/api/v1/omni/character/create", headers=_headers(), json=body, timeout=60)
    except httpx.RequestError as e:
        raise KieError(f"Couldn't reach KIE: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise KieError(f"KIE returned an unreadable response (HTTP {resp.status_code}).") from e

    data = payload.get("data")
    if not data or not data.get("characterId"):
        raise KieError(payload.get("msg") or f"KIE didn't return a character ID (HTTP {resp.status_code}).")
    return data


def get_task_detail(task_id: str) -> dict:
    """Returns the raw `data` object from KIE's recordInfo response: at least
    `state` (waiting/queuing/generating/success/fail), and on success
    `resultJson` (a JSON *string*, not yet parsed) containing resultUrls."""
    try:
        resp = httpx.get(
            f"{KIE_BASE_URL}/api/v1/jobs/recordInfo",
            headers=_headers(),
            params={"taskId": task_id},
            timeout=30,
        )
    except httpx.RequestError as e:
        raise KieError(f"Couldn't reach KIE: {e}") from e

    try:
        payload = resp.json()
    except ValueError as e:
        raise KieError(f"KIE returned an unreadable response (HTTP {resp.status_code}).") from e

    data = payload.get("data")
    if not data:
        raise KieError(payload.get("msg") or f"KIE returned no task data (HTTP {resp.status_code}).")
    return data


def parse_result_urls(task_detail: dict) -> list[str]:
    raw = task_detail.get("resultJson")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed.get("resultUrls", [])

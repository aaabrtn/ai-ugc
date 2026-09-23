"""AI vision analysis of reference photos, used to write the precise, concrete
descriptions the SOP requires (garment, persona, setting) — the photos do the
heavy lifting rather than anyone typing out physical descriptions by hand."""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from app.config import ANTHROPIC_API_KEY, VISION_MODEL

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class VisionNotConfigured(Exception):
    """No AI vision provider is set up — this is a configuration gap, not a
    transient failure, so callers should surface it distinctly."""


class VisionError(Exception):
    """The AI vision call ran but failed or returned something unusable."""


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise VisionNotConfigured(
            "No AI vision provider is configured. Set ANTHROPIC_API_KEY in your environment "
            "(see .env.example) to enable prompt generation."
        )
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _image_blocks(image_paths: list[Path]) -> list[dict]:
    blocks = []
    for path in image_paths:
        media_type = MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
    return blocks


def _call_vision(image_paths: list[Path], instruction: str, max_tokens: int) -> str:
    if not image_paths:
        raise VisionError("No reference photos were available to analyze.")
    client = _client()
    content = _image_blocks(image_paths) + [{"type": "text", "text": instruction}]
    try:
        message = client.messages.create(
            model=VISION_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        raise VisionError(f"The AI vision request failed: {e}") from e
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    if not text:
        raise VisionError("The AI vision request returned an empty response.")
    return text


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise VisionError(f"The AI vision response wasn't valid JSON: {e}") from e


@dataclass
class GarmentAnalysis:
    description: str
    back_detail: str
    loose_elements: str
    category_note: str
    is_lingerie_or_sleepwear: bool


GARMENT_INSTRUCTION = """You are analyzing product reference photos of a single fashion garment, for a \
video generation prompt. Write a precise, product-accurate description a video model can use — concrete \
physical detail only (colour, material/texture, fit, hardware, trims), never vague or generic language. \
Describe construction details (buckles, rings, ties, ruffle tiers) as concrete physical objects with \
position, size and behaviour, not abstract jargon. If there is any loose or hanging fabric element (a \
drape, tie, sash), note that it moves independently from the fitted parts of the garment.

Respond with ONLY a JSON object (no markdown fences, no other text), with these exact keys:
{
  "description": "<full precise garment description, 2-4 sentences>",
  "back_detail": "<what's visible from behind, if visible in the photos -- hardware, open back, ties; \
empty string if not visible or not applicable>",
  "loose_elements": "<any free-moving element like a drape/tie/sash and how it moves; empty string if none>",
  "category_note": "<one short phrase naming the garment type, e.g. 'wrap dress', 'two-piece linen set'>",
  "is_lingerie_or_sleepwear": <true or false -- true if this garment is lingerie, underwear, or sleepwear \
rather than outerwear meant to be worn out of the house>
}"""


def analyze_garment(image_paths: list[Path], additional_context: str = "") -> GarmentAnalysis:
    instruction = GARMENT_INSTRUCTION
    if additional_context.strip():
        instruction += (
            "\n\nAdditional context supplied about this product (texture, thickness, or other detail not "
            f"obvious from the photos alone) — fold this in where relevant:\n{additional_context.strip()}"
        )
    raw = _call_vision(image_paths, instruction, max_tokens=700)
    data = _parse_json(raw)
    return GarmentAnalysis(
        description=str(data.get("description", "")).strip(),
        back_detail=str(data.get("back_detail", "")).strip(),
        loose_elements=str(data.get("loose_elements", "")).strip(),
        category_note=str(data.get("category_note", "")).strip(),
        is_lingerie_or_sleepwear=bool(data.get("is_lingerie_or_sleepwear", False)),
    )


PERSONA_INSTRUCTION = """You are analyzing reference photos of a person, for a video generation prompt. \
Her face will never be shown in the video (it stays covered by her phone throughout), so do NOT describe \
facial features. Instead, write a short, natural-language physical description covering only what stays \
visible: hair (colour, length, style, texture), skin tone, visible build/physique, and any visible \
accessories, tattoos, or other distinguishing marks. Concrete and specific, not generic. Respond with \
2-3 sentences of plain prose only — no preamble, no markdown, no JSON."""


def analyze_persona(image_paths: list[Path]) -> str:
    return _call_vision(image_paths, PERSONA_INSTRUCTION, max_tokens=300)


SETTING_INSTRUCTION = """You are analyzing reference photos of a filming location (a room with a mirror, \
used for short selfie-style videos), for a video generation prompt. Write a short, concrete description of \
the room: the mirror, background objects, wall/floor finish, and the lighting quality (describe it as \
ordinary, unenhanced room lighting -- never studio-quality). Respond with 2-3 sentences of plain prose \
only -- no preamble, no markdown, no JSON."""


def analyze_setting(image_paths: list[Path]) -> str:
    return _call_vision(image_paths, SETTING_INSTRUCTION, max_tokens=300)

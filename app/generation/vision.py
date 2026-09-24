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

# Anthropic's published per-model rate, in USD per million tokens, as of this
# writing — used only to turn real token counts (from the API's own response)
# into a dollar figure. Unlisted models fall back to no cost estimate rather
# than a wrong one.
PRICING_PER_MTOK_USD = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}


@dataclass
class VisionUsage:
    """Real token counts from one Anthropic API call, plus the dollar cost
    those tokens imply at today's published rate for the model that was
    actually called — never estimated or guessed."""

    input_tokens: int
    output_tokens: int
    model: str

    @property
    def cost_usd(self) -> float | None:
        rates = PRICING_PER_MTOK_USD.get(self.model)
        if not rates:
            return None
        input_rate, output_rate = rates
        return (self.input_tokens / 1_000_000) * input_rate + (self.output_tokens / 1_000_000) * output_rate

    def __add__(self, other: "VisionUsage") -> "VisionUsage":
        return VisionUsage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens, self.model)


ZERO_USAGE = VisionUsage(0, 0, VISION_MODEL)


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


def _call_vision(image_paths: list[Path], instruction: str, max_tokens: int) -> tuple[str, VisionUsage]:
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
    usage = VisionUsage(message.usage.input_tokens, message.usage.output_tokens, VISION_MODEL)
    return text, usage


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
  "category_note": "<one short phrase naming the garment type, e.g. 'wrap dress', 'two-piece linen set'>"
}"""


def analyze_garment(image_paths: list[Path], additional_context: str = "") -> tuple[GarmentAnalysis, VisionUsage]:
    instruction = GARMENT_INSTRUCTION
    if additional_context.strip():
        instruction += (
            "\n\nAdditional context supplied about this product (texture, thickness, or other detail not "
            f"obvious from the photos alone) — fold this in where relevant:\n{additional_context.strip()}"
        )
    raw, usage = _call_vision(image_paths, instruction, max_tokens=700)
    data = _parse_json(raw)
    return (
        GarmentAnalysis(
            description=str(data.get("description", "")).strip(),
            back_detail=str(data.get("back_detail", "")).strip(),
            loose_elements=str(data.get("loose_elements", "")).strip(),
            category_note=str(data.get("category_note", "")).strip(),
        ),
        usage,
    )


PERSONA_INSTRUCTION = """You are analyzing reference photos of a person, for a video generation prompt. \
Her face will never be shown in the video (it stays covered by her phone throughout), so do NOT describe \
facial features. Instead, write a short, natural-language physical description covering only what stays \
visible: hair (colour, length, style, texture), skin tone, visible build/physique, and any visible \
accessories, tattoos, or other distinguishing marks. Concrete and specific, not generic. Respond with \
2-3 sentences of plain prose only — no preamble, no markdown, no JSON."""


def analyze_persona(image_paths: list[Path]) -> tuple[str, VisionUsage]:
    return _call_vision(image_paths, PERSONA_INSTRUCTION, max_tokens=300)


SETTING_INSTRUCTION = """You are analyzing reference photos of a filming location (a room with a mirror, \
used for short selfie-style videos), for a video generation prompt. Write a short, concrete description of \
the room: the mirror, background objects, wall/floor finish, and the lighting quality (describe it as \
ordinary, unenhanced room lighting -- never studio-quality). Respond with 2-3 sentences of plain prose \
only -- no preamble, no markdown, no JSON."""


def analyze_setting(image_paths: list[Path]) -> tuple[str, VisionUsage]:
    return _call_vision(image_paths, SETTING_INSTRUCTION, max_tokens=300)


MOVEMENT_VARIATION_INSTRUCTION = """You are writing choreography variations for a fixed video template \
used in AI UGC fashion content. The video always has this exact 5-cut structure and timing, which must \
NOT change -- only the specific action within each cut varies between versions:

Cut 1 (0-2s): Opening hook -- she is already at the mirror, phone already raised and gripped in her \
hand, caught mid-action (e.g. catching herself mid-step, settling from a quick body movement) as if the \
video just started rolling. NEVER a walk-in, entrance, or approach toward the mirror/camera -- the phone \
is already in her hand, already raised, from the very first frame, full stop.
Cut 2 (2-4s): A three-quarter turn to one side (never more than three-quarter, never a full back turn), \
showing the garment's fit over the hip and silhouette.
Cut 3 (4-6s): A three-quarter turn to the opposite side (never more than three-quarter, never a full back \
turn), revealing back_detail="{back_detail}" if applicable, otherwise the garment's silhouette from this side.
Cut 4 (6-8s): Front-facing, a natural gesture where her free hand touches loose_element="{loose_elements}" \
if applicable, otherwise the fabric's texture -- an unconscious gesture, not a deliberate close-up (no \
zoom, no macro shot).
Cut 5 (8-10s): Front-facing, an ending movement, settling and holding on a bright final beat.

Write {count} DIFFERENT versions of this choreography. Each version must:
- Follow the exact 5-beat structure and timing above -- same number of cuts, same emotional arc, same \
narrative purpose per cut.
- Cut 1 never shows her walking toward, entering, or approaching the mirror/camera, or reaching for, \
picking up, or grabbing the phone -- every version opens already mid-selfie, phone already raised and \
gripped in her hand from the first frame. This is a hard rule, not a style choice: a walk-in or approach \
at the start renders as the phone floating in frame, unheld, before she grabs it -- physically \
impossible for a continuous selfie POV, and must never appear.
- Never exceed a three-quarter turn in either turn cut (cuts 2 and 3), never a full back-turn.
- Feel genuinely different in specific action from every other version -- vary the exact opening \
movement (within the frame, not into it), turn style, gesture, energy, and ending pose.
- Stay entirely natural, candid, unscripted-feeling selfie-mirror content -- no props, no camera tricks, \
no zoom or macro shots, no choreographed dance moves.
- Be concrete, specific physical actions (not vague or abstract), 1-2 sentences per cut, each ending in a \
full stop.

Respond with ONLY a JSON object (no markdown fences, no other text), with this exact shape:
{{"variations": [{{"cut1": "...", "cut2": "...", "cut3": "...", "cut4": "...", "cut5": "..."}}, ...]}}
with exactly {count} entries in the "variations" array."""


def generate_movement_variations(count: int, garment: GarmentAnalysis) -> tuple[list[list[str]], VisionUsage]:
    """Writes `count` distinct 5-beat choreography variations for the SOP's
    fixed 5-cut structure/timing -- so a batch of videos for the same
    character/product move differently from each other, while every other SOP
    rule (three-quarter turn cap, grip/garment-permanence lines, anatomy,
    authenticity, etc.) stays byte-identical across the batch, since those are
    assembled separately in template.py and never touched here. Text-only
    call, no reference photos needed."""
    if not ANTHROPIC_API_KEY:
        raise VisionNotConfigured(
            "No AI vision provider is configured. Set ANTHROPIC_API_KEY in your environment "
            "(see .env.example) to enable batch generation."
        )
    instruction = MOVEMENT_VARIATION_INSTRUCTION.format(
        count=count,
        back_detail=garment.back_detail or "not visible/applicable",
        loose_elements=garment.loose_elements or "none",
    )
    client = _client()
    try:
        message = client.messages.create(
            model=VISION_MODEL,
            max_tokens=400 * count + 400,
            messages=[{"role": "user", "content": instruction}],
        )
    except anthropic.APIError as e:
        raise VisionError(f"The AI request for movement variations failed: {e}") from e

    text = "".join(block.text for block in message.content if block.type == "text").strip()
    if not text:
        raise VisionError("The AI request for movement variations returned an empty response.")
    usage = VisionUsage(message.usage.input_tokens, message.usage.output_tokens, VISION_MODEL)

    data = _parse_json(text)
    variations = []
    for entry in data.get("variations") or []:
        beats = [str(entry.get(f"cut{i}", "")).strip() for i in range(1, 6)]
        if all(beats):
            variations.append(beats)

    if len(variations) < count:
        raise VisionError(
            f"Expected {count} usable movement variations from the AI response, got {len(variations)}."
        )
    return variations[:count], usage

"""Deterministic assembly of the full video-generation prompt from a character's
persona/setting descriptions, a garment analysis, and the SOP's locked 5-cut
structure. This is plain string templating, not an AI call — the SOP's hard
rules (three-quarter turns only, repeated grip language, etc.) are guaranteed
by construction here, which is what makes them mechanically checkable
afterward in sop_check.py.

Sections are written as clearly separated, labeled blocks rather than one
monolithic paragraph, per SOP §11 ("garment analysis, identity/scene lock, and
motion choreography live in separate pipeline nodes") — that also makes them
trivially splittable once Phase 3 knows KIE's actual multi-field input shape.
"""

from app.generation.garment_focus import GARMENT_TYPE_LABELS, GARMENT_TYPE_POSSESSIVES
from app.generation.vision import GarmentAnalysis

# Per-garment-type "focus" language -- used only when a product has an
# explicit garment_type set (Andrew's own classification, not AI-guessed).
# Draws attention to the promoted item through natural gesture and turn
# framing only -- camera zoom/macro and cropping tighter than "full outfit
# visible" stay hard-forbidden regardless of what's being promoted (SOP §4,
# §8), so "focus" can only ever be expressed this way, not through framing.
FOCUS_BEATS = {
    "trousers": {
        "turn": "showing the trousers' fit through the hip and leg",
        "touch": "grazes along the outer seam of the trousers at her thigh",
    },
    "shorts": {
        "turn": "showing the shorts' fit through the hip and leg",
        "touch": "briefly adjusts the hem of the shorts at her thigh",
    },
    "dress": {
        "turn": "showing the dress's silhouette and the movement of the skirt",
        "touch": "smooths the fabric of the dress at her hip",
    },
    "top": {
        "turn": "showing the top's fit through the shoulders and torso",
        "touch": "adjusts the hem of the top at her waist",
    },
    "jacket": {
        "turn": "showing the jacket's fit through the shoulders and silhouette",
        "touch": "touches the zipper pull or collar of the jacket",
    },
}

FOCUS_SECTION_TEMPLATE = (
    "This video is promoting the {label} specifically. Her movement and the natural hand gesture in the "
    "front-facing cut are chosen to draw attention to the {possessive} fit and detail — never through "
    "zooming, cropping, or changing camera framing (the full outfit stays visible head-to-toe throughout, "
    "exactly as stated above) — only through her natural body language and where her free hand goes."
)

GRIP_LINE = (
    "her phone-holding hand keeps a continuous, unbroken grip on the phone throughout this cut — it "
    "never floats, drifts, separates, or becomes independent of her hand — held up over her face the "
    "entire time"
)

# Cut-1-only. Observed failure: a video opened with the phone floating, unheld,
# in the middle of the frame, with her then walking in and picking it up --
# physically impossible for a continuous selfie POV (the camera *is* the
# phone in her hand; there is no "before" she's holding it). GRIP_LINE alone
# (repeated every cut) wasn't enough to stop this, since it describes
# continuity within a cut, not the state of the very first frame -- this line
# closes that gap explicitly. See SOP §1 rule 10.
FRAME_ONE_ANCHOR_LINE = (
    "the very first frame already shows the phone fully raised and gripped in her hand, already "
    "mid-selfie — there is no walking toward, entering, or approaching the mirror or camera at the "
    "start of the video, and no reaching for, picking up, or grabbing the phone at any point; it is "
    "never shown resting on a surface, propped up, or floating in frame, unheld, at the start or at "
    "any other moment"
)

# Same rule as FRAME_ONE_ANCHOR_LINE, restated in the top-level ANATOMY & PHYSICS
# block (applies regardless of which cut_beats are used) rather than repeated
# once more per cut like GRIP_LINE/GARMENT_PERMANENCE_LINE -- this one only
# concerns the video's opening state, not every cut. Kept as its own named
# constant (not inlined) so sop_check.py can exclude this exact sentence when
# scanning for forbidden entrance phrases -- otherwise the rule's own negation
# ("never opens with her walking toward...") would trip its own check.
FRAME_ONE_PHYSICS_LINE = (
    "the video never opens with her walking toward, entering, or approaching the mirror or camera — "
    "the phone is already fully raised and gripped in her hand from the very first frame, never shown "
    "resting on a surface, propped up, or floating in frame, unheld, at the start or at any other point"
)

# Mirrors GRIP_LINE's fix for hand-detachment: repeated in every single cut (not
# stated once) because a garment fade/disappear-on-contact glitch was observed
# where the top-level [GARMENT] mention alone wasn't enough to hold through 5
# cuts of contact and movement. See SOP §1 rule 9.
GARMENT_PERMANENCE_LINE = (
    "the outfit itself stays fully opaque, solid, and completely unchanged in colour, texture, and "
    "coverage throughout this cut — it never fades, thins, dissolves, or disappears at any point, "
    "including exactly where her hand touches or rests against it"
)

# Observed failure: a product that was full-length joggers rendered as shorts.
# GARMENT_PERMANENCE_LINE only guarantees colour/opacity/coverage stay
# constant -- it says nothing about the garment's actual length/silhouette
# being correct in the first place. Stated once in [GARMENT] (not per cut,
# since this is a single "get it right" attribute of the whole video, not a
# per-cut contact-triggered drift like fading) alongside the AI-written
# silhouette_note, which is the other half of this fix -- see SOP §9.
GARMENT_SILHOUETTE_LINE = (
    "the garment's exact length and silhouette above is precise and must be rendered exactly as "
    "described — it is never rendered shorter, longer, cropped differently, or as a different style of "
    "garment at any point in the video (full-length trousers never render as shorts, a maxi skirt never "
    "renders as a mini, long sleeves never render as short)"
)

DEFAULT_MOVEMENT_NOTE = "Default SOP movement pace applies: roughly 1.2x natural speed, energetic but never frantic or glitchy."


def _cut(number: int, time_range: str, beat: str) -> str:
    beat = beat.strip()
    if beat and not beat.endswith((".", "!", "?")):
        beat += "."  # normalizes AI-written variation beats to the same shape as the hardcoded defaults
    frame_one = f" {FRAME_ONE_ANCHOR_LINE.capitalize()}." if number == 1 else ""
    return f"Cut {number} ({time_range}) — {beat} {GRIP_LINE.capitalize()}. {GARMENT_PERMANENCE_LINE.capitalize()}.{frame_one}"


def _fabric_touch_detail(garment: GarmentAnalysis) -> str:
    if garment.loose_elements:
        return f"feels {garment.loose_elements}"
    return "feels the fabric's texture"


def _back_detail_beat(garment: GarmentAnalysis) -> str:
    if garment.back_detail:
        return f"revealing {garment.back_detail}"
    return "showing the garment's silhouette from this side"


def _default_cut_beats(garment: GarmentAnalysis, garment_type: str = "") -> list[str]:
    """The SOP's original, locked choreography -- used whenever no variation
    (see generate_movement_variations) is supplied, so single-video generation
    behaves exactly as it always has whenever no garment_type is set. When one
    is set, the turn (cut 2) and touch (cut 4) beats specifically showcase that
    garment instead of the generic "outfit" language -- see FOCUS_BEATS."""
    focus = FOCUS_BEATS.get(garment_type)
    turn_phrase = focus["turn"] if focus else "showing the garment's fit over the hip and silhouette"
    touch_action = f"her free hand {focus['touch']}" if focus else f"her free hand naturally {_fabric_touch_detail(garment)}"
    return [
        "The video starts already mid-motion, as if caught mid-action — she's already right at the "
        "mirror, phone already raised, catching herself mid-step and settling straight into a hip roll.",
        f"She stands a natural arm's-length-plus from the mirror before turning — a three-quarter turn to "
        f"one side, never more, {turn_phrase}.",
        f"A three-quarter turn to the opposite side, never rotating fully away, {_back_detail_beat(garment)}.",
        f"Front-facing, a shimmy/bounce — {touch_action} as she moves, an unconscious gesture rather than "
        "a deliberate close-up (no zoom, no macro shot).",
        "Front-facing, a spin-in-place snap within the three-quarter limit, settling and holding on a "
        "bright final beat.",
    ]


def assemble_prompt(
    *,
    persona_description: str,
    characteristics: str,
    setting_description: str,
    garment: GarmentAnalysis,
    movement_notes: str,
    cut_beats: list[str] | None = None,
    garment_type: str = "",
) -> str:
    """`cut_beats`, if given, must have exactly 5 entries -- one specific action
    per cut, replacing the SOP's default choreography (see
    generate_movement_variations for how a batch produces distinct sets of
    these) while every other rule assembled below -- timing, turn limits,
    grip/garment-permanence lines, anatomy, authenticity -- stays identical
    regardless of which beats are used.

    `garment_type`, if it names one of FOCUS_BEATS, adds a [FOCUS] section and
    (when `cut_beats` is None) shapes the default turn/touch beats to
    specifically showcase that garment -- e.g. "trousers" for a product whose
    trousers are what the video is actually promoting. Empty/unknown values
    are always safe: identical output to before this feature existed."""
    movement_line = movement_notes.strip() or DEFAULT_MOVEMENT_NOTE

    persona_parts = [persona_description.strip()]
    if characteristics.strip():
        persona_parts.append(characteristics.strip())
    persona_block = " ".join(p for p in persona_parts if p)

    garment_block = garment.description.strip()
    silhouette_line = garment.silhouette_note.strip()
    if silhouette_line and not silhouette_line.endswith((".", "!", "?")):
        silhouette_line += "."

    focus_lines: list[str] = []
    if garment_type in GARMENT_TYPE_LABELS:
        label = GARMENT_TYPE_LABELS[garment_type]
        focus_lines = [
            "",
            "[FOCUS]",
            FOCUS_SECTION_TEMPLATE.format(label=label, possessive=GARMENT_TYPE_POSSESSIVES[garment_type]),
        ]

    beats = cut_beats if cut_beats is not None else _default_cut_beats(garment, garment_type)
    assert len(beats) == 5, "cut_beats must have exactly 5 entries, one per cut"

    cuts = [
        _cut(1, "0-2s", beats[0]),
        _cut(2, "2-4s", beats[1]),
        _cut(3, "4-6s", beats[2]),
        _cut(4, "6-8s", beats[3]),
        _cut(5, "8-10s", beats[4]),
    ]

    lines = [
        "10-second silent vertical selfie mirror video. No audio, no voiceover, no room tone, no "
        "subtitles, no on-screen text or captions, no watermark, no logos, no visible AI-generation "
        "branding anywhere in the output. Five hard jump-cuts, roughly 2 seconds each, no cross-fades "
        "or smoothing between cuts.",
        "",
        "[PERSONA]",
        persona_block,
        "Her full face is never revealed in any cut — only hair, jawline, neck, and body are visible. "
        "Her phone is held directly over her face for the entire video, naturally and partially "
        "obscuring it; her arm is genuinely positioned to hold the phone up, not artificially blocking "
        "the shot. Her mouth never moves and her lips stay fully still throughout.",
        "",
        "[SETTING]",
        setting_description.strip(),
        "This exact room, mirror, and background stay 100% visually identical across all five cuts — "
        "zero drift; only her pose, angle, and movement change between cuts. The camera reads as "
        "propped casually and imperfectly, off-centre, at a slightly awkward angle — not a centred or "
        "professional composition. Lighting is ordinary and unenhanced, never studio-quality. There is "
        "obvious, visible camera wobble that reacts to her body movement — weight shifts, steps — like "
        "a handheld phone genuinely reacting to a moving body.",
        "",
        "[GARMENT]",
        garment_block,
        *([silhouette_line] if silhouette_line else []),
        GARMENT_SILHOUETTE_LINE.capitalize() + ".",
        "The full outfit is visible head-to-toe throughout and is the primary visual subject of the "
        "video — never crop out the lower half of the garment. Her ankles and feet are never shown, at "
        "any point — the frame always crops above the ankle; this is a camera-framing choice only and "
        "never a reason to shorten the garment itself — the garment's true length (as described above) "
        "extends exactly as far as stated, regardless of what the frame crops out.",
        *focus_lines,
        "",
        "[ANATOMY & PHYSICS — applies to every cut]",
        "Exactly one hand holds the phone at all times; that grip is continuous and unbroken for the "
        "full 10 seconds, and is a solid object under normal gravity and human hand mechanics. If her "
        "phone-holding hand is doing anything else, it's stated explicitly — the free hand is the only "
        "one available for touching fabric or hair. No turn, in either direction, ever exceeds a "
        "three-quarter rotation — never a full back-turn, which is anatomically impossible in a selfie "
        "POV. Anatomy stays completely consistent frame to frame, with no extra arms, hands, or "
        "duplicated body parts. The garment itself is a solid, continuously-worn object for the entire "
        "video — it stays fully opaque and unchanged in coverage everywhere on her body, including "
        "exactly where her free hand touches or rests against it; it never fades, thins, dissolves, or "
        "disappears at any point, in any cut. " + FRAME_ONE_PHYSICS_LINE.capitalize() + ".",
        "",
        "[CUT-BY-CUT CHOREOGRAPHY — movement pace " + movement_line + "]",
        *cuts,
        "",
        "[AUTHENTICITY]",
        "Realism comes from imperfection, not polish: no glitches, stickers, effects, props, studio "
        "lighting, or \"professional\" feel of any kind. Natural skin, natural asymmetry, natural "
        "imperfections — a stray hair, an imperfect angle, uneven light — read as authentic and are "
        "never smoothed out. Even in the stillest beat there is baseline restlessness — small weight "
        "shifts, tiny steps; nothing reads as posed or frozen.",
    ]

    return "\n".join(lines).strip()

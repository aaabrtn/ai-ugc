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

from app.generation.vision import GarmentAnalysis

GRIP_LINE = (
    "her phone-holding hand keeps a continuous, unbroken grip on the phone throughout this cut — it "
    "never floats, drifts, separates, or becomes independent of her hand — held up over her face the "
    "entire time"
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

DEFAULT_MOVEMENT_NOTE = "Default SOP movement pace applies: roughly 1.2x natural speed, energetic but never frantic or glitchy."


def _cut(number: int, time_range: str, beat: str) -> str:
    beat = beat.strip()
    if beat and not beat.endswith((".", "!", "?")):
        beat += "."  # normalizes AI-written variation beats to the same shape as the hardcoded defaults
    return f"Cut {number} ({time_range}) — {beat} {GRIP_LINE.capitalize()}. {GARMENT_PERMANENCE_LINE.capitalize()}."


def _fabric_touch_detail(garment: GarmentAnalysis) -> str:
    if garment.loose_elements:
        return f"feels {garment.loose_elements}"
    return "feels the fabric's texture"


def _back_detail_beat(garment: GarmentAnalysis) -> str:
    if garment.back_detail:
        return f"revealing {garment.back_detail}"
    return "showing the garment's silhouette from this side"


def _default_cut_beats(garment: GarmentAnalysis) -> list[str]:
    """The SOP's original, locked choreography -- used whenever no variation
    (see generate_movement_variations) is supplied, so single-video generation
    behaves exactly as it always has."""
    return [
        "The video starts already mid-motion, as if caught mid-action — she walks quickly toward the "
        "mirror, then catches herself and steps back slightly, settling into a hip roll.",
        "She stands a natural arm's-length-plus from the mirror before turning — a three-quarter turn to "
        "one side, never more, showing the garment's fit over the hip and silhouette.",
        f"A three-quarter turn to the opposite side, never rotating fully away, {_back_detail_beat(garment)}.",
        f"Front-facing, a shimmy/bounce — her free hand naturally {_fabric_touch_detail(garment)} as she "
        "moves, an unconscious gesture rather than a deliberate close-up (no zoom, no macro shot).",
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
) -> str:
    """`cut_beats`, if given, must have exactly 5 entries -- one specific action
    per cut, replacing the SOP's default choreography (see
    generate_movement_variations for how a batch produces distinct sets of
    these) while every other rule assembled below -- timing, turn limits,
    grip/garment-permanence lines, anatomy, authenticity -- stays identical
    regardless of which beats are used."""
    movement_line = movement_notes.strip() or DEFAULT_MOVEMENT_NOTE

    persona_parts = [persona_description.strip()]
    if characteristics.strip():
        persona_parts.append(characteristics.strip())
    persona_block = " ".join(p for p in persona_parts if p)

    garment_block = garment.description.strip()

    beats = cut_beats if cut_beats is not None else _default_cut_beats(garment)
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
        "The full outfit is visible head-to-toe throughout and is the primary visual subject of the "
        "video — never crop out the lower half of the garment. Her ankles and feet are never shown, at "
        "any point — the frame always crops above the ankle.",
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
        "disappears at any point, in any cut.",
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

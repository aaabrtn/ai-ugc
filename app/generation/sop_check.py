"""Automated checks against the assembled prompt, mapped from the SOP's
Pre-Send Checklist. These are true by construction (the template in
template.py never writes a full-turn or a single top-level grip mention), so
they're defense-in-depth against a future template bug rather than expected
to ever fail — nothing here blocks prompt generation.

Checks the SOP itself says can't be automated (they're about the rendered
video, not the prompt text — garment accuracy against the real photos,
background drift across cuts, ankles never appearing) are listed as
"manual" for Andrew to confirm by eye, per the SOP's own instruction to map
what can be automated and leave the rest as a manual visual checklist.
"""

from dataclasses import dataclass

from app.generation.garment_focus import GARMENT_TYPE_LABELS
from app.generation.template import FRAME_ONE_ANCHOR_LINE, FRAME_ONE_PHYSICS_LINE, GARMENT_SILHOUETTE_LINE
from app.generation.vision import GarmentAnalysis

# Observed failure: a video opened with the phone floating, unheld, in the
# middle of the frame, with her then walking in and picking it up --
# physically impossible for a continuous selfie POV. These phrases are the
# ones that were found to trigger it (see SOP §1 rule 10) -- if any of them
# ever appears in an assembled prompt (including an AI-written batch
# variation, which isn't fixed template text and so isn't automatically safe
# the way the hardcoded default is), that's a real regression worth catching
# before the prompt is ever approved.
FORBIDDEN_ENTRANCE_PHRASES = (
    "walks toward",
    "walking toward",
    "walks to the mirror",
    "approaches the mirror",
    "approaches the camera",
    "enters the frame",
    "enters frame",
    "picks up the phone",
    "picking up the phone",
    "reaches for the phone",
    "reaching for the phone",
    "grabs the phone",
    "grabbing the phone",
    "phone is propped",
    "phone rests on",
    "phone sitting on",
)


@dataclass
class SopCheck:
    id: str
    label: str
    status: str  # "pass" | "fail" | "manual"
    detail: str


def run_sop_checks(prompt_text: str, garment: GarmentAnalysis, garment_type: str = "") -> list[SopCheck]:
    checks: list[SopCheck] = []

    def add(check_id: str, label: str, condition: bool, pass_detail: str, fail_detail: str):
        checks.append(
            SopCheck(
                id=check_id,
                label=label,
                status="pass" if condition else "fail",
                detail=pass_detail if condition else fail_detail,
            )
        )

    add(
        "grip_repeated",
        "One phone, one gripping hand, restated per cut",
        prompt_text.count("continuous, unbroken grip") >= 5,
        "Grip-continuity language appears in every cut.",
        "The grip-continuity phrase doesn't appear once per cut as expected.",
    )

    add(
        "garment_permanence_repeated",
        "Garment never fades/disappears on contact, restated per cut",
        prompt_text.count("never fades, thins, dissolves, or disappears") >= 5,
        "Garment-permanence language appears in every cut.",
        "The garment-permanence phrase doesn't appear once per cut as expected.",
    )

    add(
        "three_quarter_only",
        "No turn exceeds three-quarter rotation",
        "three-quarter" in prompt_text and "full turn" not in prompt_text.lower() and "180" not in prompt_text,
        "Only three-quarter-turn language is present.",
        "Found language suggesting a fuller rotation than the SOP allows.",
    )

    add(
        "opening_mid_motion",
        "Opening cut starts mid-motion, not static",
        "already mid-motion" in prompt_text,
        "Cut 1 explicitly starts mid-motion.",
        "Cut 1 doesn't explicitly start mid-motion.",
    )

    add(
        "frame_one_anchor",
        "Video opens already mid-selfie — phone already raised, no walk-in",
        "already shows the phone fully raised and gripped in her hand" in prompt_text,
        "Cut 1 explicitly states the phone is already raised and gripped from the very first frame.",
        "Couldn't find the frame-one anchor instruction — Cut 1 may not guarantee the phone is already "
        "in hand from frame one.",
    )

    # The rule's own negation ("never opens with her walking toward...") would
    # otherwise trip this same check, since it necessarily names the concept
    # it's forbidding (see SOP §1 rule 6 on writing physics in positive terms
    # -- this is the one place a negation is unavoidable, so instead of
    # rephrasing it into something more awkward, the check excludes exactly
    # those two known-safe sentences before scanning for actual violations.
    scan_text = prompt_text.lower()
    for safe_line in (FRAME_ONE_ANCHOR_LINE, FRAME_ONE_PHYSICS_LINE):
        scan_text = scan_text.replace(safe_line.lower(), "")

    add(
        "no_walk_in_or_pickup",
        "No walk-in, approach, or phone pick-up language anywhere in the prompt",
        not any(phrase in scan_text for phrase in FORBIDDEN_ENTRANCE_PHRASES),
        "No walk-in/approach/pick-up-the-phone language found.",
        "Found language suggesting she walks toward/enters the frame or picks up the phone — this can "
        "render as the phone floating in frame, unheld, before she grabs it, which is impossible for a "
        "continuous selfie POV. Review Cut 1 before approving.",
    )

    add(
        "five_cuts",
        "All 5 cuts are hard jumps, ~2s each, ~1.2x pace",
        prompt_text.count("Cut ") == 5,
        "Exactly 5 labeled cuts are present.",
        f"Found {prompt_text.count('Cut ')} labeled cuts instead of 5.",
    )

    add(
        "face_covered",
        "Face covered by phone in every cut",
        "held directly over her face" in prompt_text or "held up over her face" in prompt_text,
        "Persona section states the phone stays over her face for the full video.",
        "Couldn't find the face-cover instruction in the persona section.",
    )

    add(
        "fabric_touch_natural",
        "Free hand touches fabric naturally at some point (no zoom)",
        "free hand" in prompt_text and "no zoom" in prompt_text,
        "A natural fabric-touch beat is present, with zoom explicitly excluded.",
        "Couldn't confirm a natural, non-zoomed fabric-touch beat.",
    )

    add(
        "silence",
        "Zero audio, mouth never moves, no captions/text",
        "no audio" in prompt_text.lower() and "mouth never moves" in prompt_text,
        "Silence and stillness of the mouth are both stated.",
        "Couldn't confirm both the silence and still-mouth instructions.",
    )

    add(
        "background_identical",
        "Background identical across every cut",
        "100% visually identical" in prompt_text,
        "Setting section states the background is identical across all cuts.",
        "Couldn't find the background-consistency instruction.",
    )

    add(
        "garment_detail",
        "Garment described precisely, with real product detail",
        len(garment.description) >= 40,
        "The garment description has real, specific detail.",
        "The garment description looks too short/generic — review it before approving.",
    )

    add(
        "garment_silhouette_stated",
        "Garment length/silhouette stated explicitly (not left to be inferred)",
        bool(garment.silhouette_note.strip()),
        "The garment's exact length/silhouette is explicitly stated.",
        "No explicit length/silhouette statement found for this garment — review before approving. A "
        "vague description here previously caused full-length joggers to render as shorts.",
    )

    add(
        "garment_silhouette_locked",
        "Prompt states the garment's silhouette must render exactly as described",
        GARMENT_SILHOUETTE_LINE.lower() in prompt_text.lower(),
        "The silhouette-lock instruction is present in the prompt.",
        "Couldn't find the silhouette-lock instruction in the assembled prompt.",
    )

    if garment_type in GARMENT_TYPE_LABELS:
        label = GARMENT_TYPE_LABELS[garment_type]
        add(
            "focus_stated",
            f"Promoted garment ({label}) is named as the video's visual focus",
            "[FOCUS]" in prompt_text and label in prompt_text.split("[FOCUS]", 1)[1][:400],
            f"The [FOCUS] section names the {label} as what this video is promoting.",
            f"Expected a [FOCUS] section naming the {label} since this product's garment_type is set, but "
            "didn't find one.",
        )

    add(
        "ankles_hidden",
        "Ankles/feet never shown",
        "ankles and feet are never shown" in prompt_text,
        "Framing section explicitly excludes ankles and feet.",
        "Couldn't find the ankles/feet exclusion instruction.",
    )

    add(
        "no_watermark",
        "No watermark/branding anywhere in prompt or expected output",
        "no watermark" in prompt_text.lower() and "branding" in prompt_text.lower(),
        "Watermark/branding are explicitly excluded.",
        "Couldn't find the watermark/branding exclusion instruction.",
    )

    checks.append(
        SopCheck(
            id="visual_review",
            label="Garment description and photos match the real product",
            status="manual",
            detail="The AI-written garment description above is a starting point — check it against the actual product photos before approving.",
        )
    )
    checks.append(
        SopCheck(
            id="video_review",
            label="Rendered video: background stays identical, no glitches, ankles never shown",
            status="manual",
            detail="These depend on the actual render, not the prompt text — confirm once the video is generated (Phase 3).",
        )
    )

    return checks


def has_blocking_failure(checks: list[SopCheck]) -> bool:
    return any(c.id == "content_boundary" and c.status == "fail" for c in checks)

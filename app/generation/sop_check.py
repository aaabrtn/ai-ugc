"""Automated checks against the assembled prompt, mapped from the SOP's
Pre-Send Checklist. Most of these are true by construction (the template in
template.py never writes a full-turn or a single top-level grip mention), so
they're defense-in-depth against a future template bug rather than expected
to ever fail. The one genuinely substantive, content-dependent check is the
lingerie/sleepwear content-boundary rule (SOP §10) — that's a real gate, not
a formality, and a failure there blocks prompt generation entirely rather
than just getting flagged.

Checks the SOP itself says can't be automated (they're about the rendered
video, not the prompt text — garment accuracy against the real photos,
background drift across cuts, ankles never appearing) are listed as
"manual" for Andrew to confirm by eye, per the SOP's own instruction to map
what can be automated and leave the rest as a manual visual checklist.
"""

from dataclasses import dataclass

from app.generation.vision import GarmentAnalysis


@dataclass
class SopCheck:
    id: str
    label: str
    status: str  # "pass" | "fail" | "manual"
    detail: str


def run_sop_checks(prompt_text: str, garment: GarmentAnalysis) -> list[SopCheck]:
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

    # The one real content-boundary gate — everything else below is
    # defense-in-depth on a template we control.
    add(
        "content_boundary",
        "No lingerie/sleepwear garments",
        not garment.is_lingerie_or_sleepwear,
        "Garment reads as outerwear.",
        "This garment was classified as lingerie/sleepwear/underwear — this framework never uses that "
        "category, regardless of framing. Prompt generation is blocked; use a different product.",
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

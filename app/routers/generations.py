import dataclasses
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.config import KIE_MODEL, KIE_USD_PER_CREDIT, VISION_MODEL
from app.database import DATA_DIR, get_db
from app.generation.sop_check import has_blocking_failure, run_sop_checks
from app.generation.template import assemble_prompt
from app.generation.vision import (
    VisionError,
    VisionNotConfigured,
    VisionUsage,
    analyze_garment,
    analyze_persona,
    analyze_setting,
    generate_movement_variations,
)
from app.integrations.kie import (
    KieError,
    KieNotConfigured,
    credits_for,
    get_credit_balance,
    get_task_detail,
    image_budget,
    parse_result_urls,
    submit_video_task,
    upload_public_image,
)
from app.models import Character, FetchStatus, Generation, GenerationStage, ImageKind, Product, VideoStatus, gen_id
from app.schemas import CharacterSummaryOut, GarmentAnalysisOut, GenerationOut, ProductSummaryOut, SopCheckOut

router = APIRouter()

CHARACTER_UPLOADS_DIR = DATA_DIR / "uploads"
PRODUCT_UPLOADS_DIR = DATA_DIR / "uploads" / "products"
VIDEO_UPLOADS_DIR = DATA_DIR / "uploads" / "generations"

POLL_TIMEOUT = timedelta(minutes=15)  # matches KIE's own "stop polling after 10-15 minutes" guidance

ALLOWED_DURATIONS = {"8", "10"}
ALLOWED_ASPECT_RATIOS = {"16:9", "9:16"}
ALLOWED_RESOLUTIONS = {"720p", "1080p", "4k"}

MAX_BATCH_SIZE = 5  # caps one click's blast radius -- KIE bills each video independently, no bulk discount

# Caps how many finished videos' files stay on disk at once, since hosted
# storage is billed by the GB unlike running this locally. Everything else
# about an older generation (prompt, cost, timings) stays in History forever
# -- only the video file itself gets deleted once it ages past this many
# more-recent ones.
MAX_STORED_VIDEOS = 50


def product_summary(product: Product) -> ProductSummaryOut:
    thumbnail_url = f"/uploads/products/{product.images[0].file_path}" if product.images else ""
    return ProductSummaryOut(
        id=product.id,
        name=product.name,
        fetch_status=product.fetch_status,
        thumbnail_url=thumbnail_url,
    )


def character_summary(character: Character) -> CharacterSummaryOut:
    thumbnail_url = f"/uploads/{character.identity_images[0].file_path}" if character.identity_images else ""
    return CharacterSummaryOut(
        id=character.id,
        name=character.name,
        kie_character_id=character.kie_character_id or "",
        thumbnail_url=thumbnail_url,
    )


def generation_to_out(g: Generation) -> GenerationOut:
    garment_analysis = None
    if g.garment_analysis_json:
        garment_analysis = GarmentAnalysisOut(**json.loads(g.garment_analysis_json))

    sop_checks = []
    if g.sop_check_results_json:
        sop_checks = [SopCheckOut(**c) for c in json.loads(g.sop_check_results_json)]

    total_cost = None
    if g.vision_cost_usd is not None or g.kie_usd_cost is not None:
        total_cost = (g.vision_cost_usd or 0) + (g.kie_usd_cost or 0)

    # Real generation time: from the moment "Generate Video" actually submitted
    # to KIE, to the moment it reached a terminal state -- not from when the
    # script/prompt was created, which can include however long it sat in
    # review first. None until both timestamps exist.
    generation_seconds = None
    if g.video_submitted_at and g.video_completed_at:
        generation_seconds = (g.video_completed_at - g.video_submitted_at).total_seconds()

    return GenerationOut(
        id=g.id,
        character_id=g.character_id,
        character=character_summary(g.character),
        product_id=g.product_id,
        product=product_summary(g.product),
        stage=g.stage,
        garment_analysis=garment_analysis,
        generated_prompt=g.generated_prompt or "",
        sop_check_results=sop_checks,
        duration=g.duration,
        aspect_ratio=g.aspect_ratio,
        resolution=g.resolution,
        batch_id=g.batch_id or "",
        batch_index=g.batch_index,
        kie_task_id=g.kie_task_id or "",
        video_status=g.video_status,
        video_error=g.video_error or "",
        video_url=f"/uploads/generations/{g.video_local_path}" if g.video_local_path else "",
        video_archived=g.video_archived,
        vision_cost_usd=g.vision_cost_usd,
        kie_credits_cost=g.kie_credits_cost,
        kie_usd_cost=g.kie_usd_cost,
        total_cost_usd=total_cost,
        generation_seconds=generation_seconds,
        created_at=g.created_at,
    )


@router.get("", response_model=List[GenerationOut])
def list_generations(db: Session = Depends(get_db)):
    generations = db.query(Generation).order_by(Generation.created_at.desc()).all()
    return [generation_to_out(g) for g in generations]


@router.get("/cost-estimate")
def cost_estimate(duration: str, resolution: str, count: int = 1):
    """Live pre-generation estimate for the Generator form — declared before
    the /{generation_id} route below so FastAPI doesn't try to match
    "cost-estimate" as a generation id. `count` scales the total for a batch
    (each video is billed independently by KIE -- no bulk discount)."""
    credits = credits_for(duration, resolution)
    if credits is None:
        return {"credits": None, "usd": None, "per_video_credits": None, "per_video_usd": None}
    usd = credits * float(KIE_USD_PER_CREDIT) if KIE_USD_PER_CREDIT else None
    return {
        "credits": credits * count,
        "usd": usd * count if usd is not None else None,
        "per_video_credits": credits,
        "per_video_usd": usd,
    }


@router.get("/kie-balance")
def kie_balance():
    """Live remaining KIE credit balance for the Generator header -- declared
    before /{generation_id} for the same routing reason as /cost-estimate.
    Never raises: a missing key or an unreachable/erroring KIE is reported as
    `error` so the header can show "unavailable" instead of breaking the page."""
    try:
        return {"credits": get_credit_balance(), "error": None}
    except (KieNotConfigured, KieError) as e:
        return {"credits": None, "error": str(e)}


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    return generation_to_out(g)


@router.post("", response_model=GenerationOut)
def create_generation(
    character_id: str = Form(...),
    product_id: str = Form(...),
    duration: str = Form("8"),
    aspect_ratio: str = Form("9:16"),
    resolution: str = Form("1080p"),
    db: Session = Depends(get_db),
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if product.fetch_status != FetchStatus.success or not product.images:
        raise HTTPException(400, "This product has no photos to generate a script from")
    if duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"Duration must be one of {sorted(ALLOWED_DURATIONS)}")
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise HTTPException(400, f"Aspect ratio must be one of {sorted(ALLOWED_ASPECT_RATIOS)}")
    if resolution not in ALLOWED_RESOLUTIONS:
        raise HTTPException(400, f"Resolution must be one of {sorted(ALLOWED_RESOLUTIONS)}")

    generation = Generation(
        character_id=character_id,
        product_id=product_id,
        stage=GenerationStage.draft,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation_to_out(generation)


@router.post("/batch", response_model=List[GenerationOut])
def create_batch(
    character_id: str = Form(...),
    product_id: str = Form(...),
    duration: str = Form("8"),
    aspect_ratio: str = Form("9:16"),
    resolution: str = Form("1080p"),
    count: int = Form(...),
    db: Session = Depends(get_db),
):
    """Creates `count` approved generations in one shot, same character/
    product/settings, each with its own distinct movement choreography (see
    generate_movement_variations) but every SOP rule the template enforces
    separately held identical across all of them -- ready for the frontend to
    submit-video on each, back-to-back, for true simultaneous generation."""
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if product.fetch_status != FetchStatus.success or not product.images:
        raise HTTPException(400, "This product has no photos to generate a script from")
    if duration not in ALLOWED_DURATIONS:
        raise HTTPException(400, f"Duration must be one of {sorted(ALLOWED_DURATIONS)}")
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise HTTPException(400, f"Aspect ratio must be one of {sorted(ALLOWED_ASPECT_RATIOS)}")
    if resolution not in ALLOWED_RESOLUTIONS:
        raise HTTPException(400, f"Resolution must be one of {sorted(ALLOWED_RESOLUTIONS)}")
    if not (1 <= count <= MAX_BATCH_SIZE):
        raise HTTPException(400, f"count must be between 1 and {MAX_BATCH_SIZE}")

    # Persona/setting/garment analysis runs at most once here and is reused for
    # every generation in the batch -- identical caching behaviour to the
    # single-generation flow (generate_prompt), just amortized over N videos.
    vision_input_tokens = 0
    vision_output_tokens = 0
    try:
        if not character.persona_description:
            identity_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.identity
            ]
            character.persona_description, usage = analyze_persona(identity_paths)
            vision_input_tokens += usage.input_tokens
            vision_output_tokens += usage.output_tokens

        if not character.setting_description:
            setting_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.setting
            ]
            character.setting_description, usage = analyze_setting(setting_paths)
            vision_input_tokens += usage.input_tokens
            vision_output_tokens += usage.output_tokens

        garment_paths = [PRODUCT_UPLOADS_DIR / img.file_path for img in product.images]
        garment, usage = analyze_garment(garment_paths, additional_context=product.additional_context or "")
        vision_input_tokens += usage.input_tokens
        vision_output_tokens += usage.output_tokens

        variations, movement_usage = generate_movement_variations(count, garment, garment_type=product.garment_type)
    except VisionNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, f"Couldn't generate batch prompts: {e}") from e

    garment_json = json.dumps(dataclasses.asdict(garment))
    batch_id = gen_id()

    results = []
    for i in range(count):
        prompt_text = assemble_prompt(
            persona_description=character.persona_description,
            characteristics=character.characteristics or "",
            setting_description=character.setting_description,
            garment=garment,
            movement_notes="",
            cut_beats=variations[i],
            garment_type=product.garment_type,
        )
        checks = run_sop_checks(prompt_text, garment, garment_type=product.garment_type)

        g = Generation(
            character_id=character_id,
            product_id=product_id,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            batch_id=batch_id,
            batch_index=i + 1,
            garment_analysis_json=garment_json,
            sop_check_results_json=json.dumps([dataclasses.asdict(c) for c in checks]),
            # The one-off persona/setting/garment analysis (if actually incurred
            # this call) is attributed entirely to the first generation; the one
            # shared movement-variation call is split evenly across all of them
            # -- each generation's own vision_cost_usd stays meaningful on its
            # own without double-counting a cost only ever spent once.
            vision_input_tokens=(vision_input_tokens if i == 0 else 0) + movement_usage.input_tokens // count,
            vision_output_tokens=(vision_output_tokens if i == 0 else 0) + movement_usage.output_tokens // count,
        )
        if has_blocking_failure(checks):
            g.stage = GenerationStage.blocked
        else:
            g.stage = GenerationStage.approved
            g.generated_prompt = prompt_text
        g.vision_cost_usd = VisionUsage(g.vision_input_tokens, g.vision_output_tokens, VISION_MODEL).cost_usd

        db.add(g)
        results.append(g)

    db.commit()
    for g in results:
        db.refresh(g)
    return [generation_to_out(g) for g in results]


@router.delete("/{generation_id}")
def delete_generation(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    video_dir = VIDEO_UPLOADS_DIR / g.id
    db.delete(g)
    db.commit()
    if video_dir.exists():
        shutil.rmtree(video_dir, ignore_errors=True)
    return {"ok": True}


@router.post("/{generation_id}/generate", response_model=GenerationOut)
def generate_prompt(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")

    character = g.character
    product = g.product

    # Only calls actually made *this* time count toward this generation's cost —
    # if persona/setting were already cached (from an earlier generation, or from
    # KIE character registration), they cost nothing extra here.
    vision_input_tokens = 0
    vision_output_tokens = 0

    try:
        if not character.persona_description:
            identity_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.identity
            ]
            character.persona_description, usage = analyze_persona(identity_paths)
            vision_input_tokens += usage.input_tokens
            vision_output_tokens += usage.output_tokens

        if not character.setting_description:
            setting_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.setting
            ]
            character.setting_description, usage = analyze_setting(setting_paths)
            vision_input_tokens += usage.input_tokens
            vision_output_tokens += usage.output_tokens

        garment_paths = [PRODUCT_UPLOADS_DIR / img.file_path for img in product.images]
        garment, usage = analyze_garment(garment_paths, additional_context=product.additional_context or "")
        vision_input_tokens += usage.input_tokens
        vision_output_tokens += usage.output_tokens
    except VisionNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, f"Couldn't generate a prompt: {e}") from e

    g.vision_input_tokens = vision_input_tokens
    g.vision_output_tokens = vision_output_tokens
    g.vision_cost_usd = VisionUsage(vision_input_tokens, vision_output_tokens, VISION_MODEL).cost_usd

    g.garment_analysis_json = json.dumps(dataclasses.asdict(garment))

    prompt_text = assemble_prompt(
        persona_description=character.persona_description,
        characteristics=character.characteristics or "",
        setting_description=character.setting_description,
        garment=garment,
        movement_notes="",
        garment_type=product.garment_type,
    )

    checks = run_sop_checks(prompt_text, garment, garment_type=product.garment_type)
    g.sop_check_results_json = json.dumps([dataclasses.asdict(c) for c in checks])

    if has_blocking_failure(checks):
        g.stage = GenerationStage.blocked
        g.generated_prompt = ""
    else:
        g.stage = GenerationStage.prompt_generated
        g.generated_prompt = prompt_text

    db.commit()
    db.refresh(g)
    return generation_to_out(g)


@router.put("/{generation_id}/approve", response_model=GenerationOut)
def approve_prompt(generation_id: str, edited_prompt: str = Form(...), db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    if g.stage not in (GenerationStage.prompt_generated, GenerationStage.approved):
        raise HTTPException(400, "This script doesn't have a generated prompt to approve")
    if not edited_prompt.strip():
        raise HTTPException(400, "Prompt can't be empty")

    g.generated_prompt = edited_prompt
    g.stage = GenerationStage.approved
    db.commit()
    db.refresh(g)
    return generation_to_out(g)


def _select_reference_photos(character: Character, product: Product, budget: int) -> list[Path]:
    """Which local photos to host publicly and send as image_urls, within KIE's
    input-slot budget. Identity is covered by character_ids, so this only needs
    setting (the room) and garment (the product) references — setting first,
    since it defines the fixed backdrop, then garment photos filling the rest."""
    setting_paths = [CHARACTER_UPLOADS_DIR / img.file_path for img in character.setting_images]
    garment_paths = [PRODUCT_UPLOADS_DIR / img.file_path for img in product.images]
    return (setting_paths + garment_paths)[:budget]


def _download_video(generation_id: str, video_url: str) -> str:
    """Downloads the finished video locally — KIE's result URL expires in ~24h,
    so this happens immediately on detecting success, not left for later."""
    dest_dir = VIDEO_UPLOADS_DIR / generation_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "video.mp4"
    with httpx.stream("GET", video_url, timeout=120, follow_redirects=True) as resp:
        resp.raise_for_status()
        with dest_path.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return f"{generation_id}/video.mp4"


@router.post("/{generation_id}/submit-video", response_model=GenerationOut)
def submit_video(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    if g.stage != GenerationStage.approved:
        raise HTTPException(400, "Approve the prompt before generating a video")
    # Idempotency guard: a task already in flight or already finished must never be
    # resubmitted — a second click (or the one-click flow's own brief in-between
    # render exposing this same button while it's already mid-submit) would create
    # a second real, separately-billed KIE task with no way to reconcile which one
    # "wins." Only not_started (never submitted) or fail (previous attempt failed,
    # legitimately eligible for "Try Again") may proceed.
    if g.video_status not in (VideoStatus.not_started, VideoStatus.fail):
        raise HTTPException(
            409,
            f"A video is already {g.video_status.value} for this script — refusing to submit a second one. "
            "Wait for it to finish, or check History.",
        )

    character = g.character
    if not character.kie_character_id:
        raise HTTPException(
            422,
            f"'{character.name}' has no KIE character ID yet. Add one on the character's profile — it "
            "has to be created in KIE's own dashboard first (see the app README).",
        )

    budget = image_budget([character.kie_character_id], character.kie_character_has_body)
    reference_paths = _select_reference_photos(character, g.product, budget)

    try:
        image_urls = [upload_public_image(p) for p in reference_paths]
    except KieNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except KieError as e:
        raise HTTPException(502, f"Couldn't prepare reference photos for KIE: {e}") from e

    try:
        task_id = submit_video_task(
            prompt=g.generated_prompt,
            character_ids=[character.kie_character_id],
            image_urls=image_urls,
            duration=g.duration,
            aspect_ratio=g.aspect_ratio,
            resolution=g.resolution,
        )
    except KieNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except KieError as e:
        raise HTTPException(502, f"KIE rejected the video request: {e}") from e

    g.kie_task_id = task_id
    g.kie_model_used = KIE_MODEL
    g.video_status = VideoStatus.waiting
    g.video_submitted_at = datetime.utcnow()
    g.video_error = ""

    # Estimated, not live — KIE's task-status API has no per-task price field.
    # credits_for looks up the real published rate for the exact settings this
    # generation actually used, not a flat guess.
    credits = credits_for(g.duration, g.resolution)
    if credits is not None:
        g.kie_credits_cost = credits
        g.kie_usd_cost = credits * float(KIE_USD_PER_CREDIT) if KIE_USD_PER_CREDIT else None

    db.commit()
    db.refresh(g)
    return generation_to_out(g)


def _archive_old_videos(db: Session, keep: int = MAX_STORED_VIDEOS) -> None:
    """Deletes the video FILE for any generation beyond the `keep` most
    recently completed ones that still have one stored -- the row itself
    (prompt, cost, timings) is untouched and stays in History forever. Runs
    after every new video finishes downloading, so storage never grows
    past `keep` videos' worth regardless of how many get generated."""
    stored = (
        db.query(Generation)
        .filter(Generation.video_local_path != "", Generation.video_archived.is_(False))
        .order_by(Generation.video_completed_at.desc())
        .all()
    )
    to_archive = stored[keep:]
    if not to_archive:
        return
    for g in to_archive:
        shutil.rmtree(VIDEO_UPLOADS_DIR / g.id, ignore_errors=True)
        g.video_local_path = ""
        g.video_archived = True
    db.commit()


def refresh_video_status(db: Session, g: Generation) -> Generation:
    """Checks KIE for this generation's current task state and updates the row
    accordingly. Shared by the /video-status endpoint (polled by the browser)
    and the background poller (app/background.py, polled by the server itself
    regardless of whether any browser is open) so both paths update the DB the
    same way and a video's fate is never left depending on a tab staying open."""
    if g.video_status in (VideoStatus.not_started, VideoStatus.success, VideoStatus.fail):
        return g  # nothing to check — not submitted yet, or already terminal

    if g.video_submitted_at and datetime.utcnow() - g.video_submitted_at > POLL_TIMEOUT:
        g.video_status = VideoStatus.fail
        g.video_error = (
            f"No result from KIE after {int(POLL_TIMEOUT.total_seconds() // 60)} minutes. The task may "
            f"still be running — check kie.ai/logs for task {g.kie_task_id}."
        )
        g.video_completed_at = datetime.utcnow()
        db.commit()
        db.refresh(g)
        return g

    detail = get_task_detail(g.kie_task_id)  # KieNotConfigured/KieError left for the caller to handle

    state = detail.get("state", "")
    if state == "success":
        result_urls = parse_result_urls(detail)
        if not result_urls:
            g.video_status = VideoStatus.fail
            g.video_error = "KIE reported success but returned no video URL."
        else:
            try:
                g.video_local_path = _download_video(g.id, result_urls[0])
                g.video_result_url = result_urls[0]
                g.video_status = VideoStatus.success
            except httpx.HTTPError as e:
                g.video_status = VideoStatus.fail
                g.video_error = f"Video generated, but couldn't be downloaded: {e}"
    elif state == "fail":
        g.video_status = VideoStatus.fail
        g.video_error = detail.get("failMsg") or "Generation failed."
    elif state in (VideoStatus.waiting.value, VideoStatus.queuing.value, VideoStatus.generating.value):
        g.video_status = VideoStatus(state)
    # any other/unknown state: leave as-is, just report current state back

    if g.video_status in (VideoStatus.success, VideoStatus.fail) and not g.video_completed_at:
        g.video_completed_at = datetime.utcnow()

    db.commit()
    db.refresh(g)

    if g.video_status == VideoStatus.success:
        _archive_old_videos(db)
        db.refresh(g)

    return g


@router.get("/{generation_id}/video-status", response_model=GenerationOut)
def video_status(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    if g.video_status == VideoStatus.not_started:
        raise HTTPException(400, "Video generation hasn't been submitted yet")

    try:
        g = refresh_video_status(db, g)
    except (KieNotConfigured, KieError) as e:
        raise HTTPException(502, str(e)) from e

    return generation_to_out(g)

import dataclasses
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.config import KIE_MODEL
from app.database import DATA_DIR, get_db
from app.generation.sop_check import has_blocking_failure, run_sop_checks
from app.generation.template import assemble_prompt
from app.generation.vision import VisionError, VisionNotConfigured, analyze_garment, analyze_persona, analyze_setting
from app.integrations.catbox import CatboxError, upload_public_image
from app.integrations.kie import KieError, KieNotConfigured, get_task_detail, image_budget, parse_result_urls, submit_video_task
from app.models import Character, FetchStatus, Generation, GenerationStage, ImageKind, Product, VideoStatus
from app.schemas import CharacterSummaryOut, GarmentAnalysisOut, GenerationOut, ProductSummaryOut, SopCheckOut

router = APIRouter()

CHARACTER_UPLOADS_DIR = DATA_DIR / "uploads"
PRODUCT_UPLOADS_DIR = DATA_DIR / "uploads" / "products"
VIDEO_UPLOADS_DIR = DATA_DIR / "uploads" / "generations"

POLL_TIMEOUT = timedelta(minutes=15)  # matches KIE's own "stop polling after 10-15 minutes" guidance


def product_summary(product: Product) -> ProductSummaryOut:
    thumbnail_url = f"/uploads/products/{product.images[0].file_path}" if product.images else ""
    return ProductSummaryOut(
        id=product.id,
        name=product.name,
        fetch_status=product.fetch_status,
        thumbnail_url=thumbnail_url,
    )


def generation_to_out(g: Generation) -> GenerationOut:
    garment_analysis = None
    if g.garment_analysis_json:
        garment_analysis = GarmentAnalysisOut(**json.loads(g.garment_analysis_json))

    sop_checks = []
    if g.sop_check_results_json:
        sop_checks = [SopCheckOut(**c) for c in json.loads(g.sop_check_results_json)]

    return GenerationOut(
        id=g.id,
        character_id=g.character_id,
        character=CharacterSummaryOut.model_validate(g.character),
        product_id=g.product_id,
        product=product_summary(g.product),
        stage=g.stage,
        garment_analysis=garment_analysis,
        generated_prompt=g.generated_prompt or "",
        sop_check_results=sop_checks,
        kie_task_id=g.kie_task_id or "",
        video_status=g.video_status,
        video_error=g.video_error or "",
        video_url=f"/uploads/generations/{g.video_local_path}" if g.video_local_path else "",
        created_at=g.created_at,
    )


@router.get("", response_model=List[GenerationOut])
def list_generations(db: Session = Depends(get_db)):
    generations = db.query(Generation).order_by(Generation.created_at.desc()).all()
    return [generation_to_out(g) for g in generations]


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

    generation = Generation(character_id=character_id, product_id=product_id, stage=GenerationStage.draft)
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation_to_out(generation)


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

    try:
        if not character.persona_description:
            identity_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.identity
            ]
            character.persona_description = analyze_persona(identity_paths)

        if not character.setting_description:
            setting_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.setting
            ]
            character.setting_description = analyze_setting(setting_paths)

        garment_paths = [PRODUCT_UPLOADS_DIR / img.file_path for img in product.images]
        garment = analyze_garment(garment_paths, additional_context=product.additional_context or "")
    except VisionNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, f"Couldn't generate a prompt: {e}") from e

    g.garment_analysis_json = json.dumps(dataclasses.asdict(garment))

    prompt_text = assemble_prompt(
        persona_description=character.persona_description,
        characteristics=character.characteristics or "",
        setting_description=character.setting_description,
        garment=garment,
        movement_notes="",
    )

    checks = run_sop_checks(prompt_text, garment)
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
    except CatboxError as e:
        raise HTTPException(502, f"Couldn't prepare reference photos for KIE: {e}") from e

    try:
        task_id = submit_video_task(
            prompt=g.generated_prompt,
            character_ids=[character.kie_character_id],
            image_urls=image_urls,
            duration="10",
            aspect_ratio="9:16",
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

    db.commit()
    db.refresh(g)
    return generation_to_out(g)


@router.get("/{generation_id}/video-status", response_model=GenerationOut)
def video_status(generation_id: str, db: Session = Depends(get_db)):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(404, "Script not found")
    if g.video_status == VideoStatus.not_started:
        raise HTTPException(400, "Video generation hasn't been submitted yet")
    if g.video_status in (VideoStatus.success, VideoStatus.fail):
        return generation_to_out(g)  # terminal — no need to hit KIE again

    if g.video_submitted_at and datetime.utcnow() - g.video_submitted_at > POLL_TIMEOUT:
        g.video_status = VideoStatus.fail
        g.video_error = (
            f"No result from KIE after {int(POLL_TIMEOUT.total_seconds() // 60)} minutes. The task may "
            f"still be running — check kie.ai/logs for task {g.kie_task_id}."
        )
        db.commit()
        db.refresh(g)
        return generation_to_out(g)

    try:
        detail = get_task_detail(g.kie_task_id)
    except (KieNotConfigured, KieError) as e:
        raise HTTPException(502, str(e)) from e

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

    db.commit()
    db.refresh(g)
    return generation_to_out(g)

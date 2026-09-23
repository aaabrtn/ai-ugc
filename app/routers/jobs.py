import dataclasses
import json
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import DATA_DIR, get_db
from app.generation.sop_check import has_blocking_failure, run_sop_checks
from app.generation.template import assemble_prompt
from app.generation.vision import GarmentAnalysis, VisionError, VisionNotConfigured, analyze_garment, analyze_persona, analyze_setting
from app.models import Character, FetchStatus, ImageKind, Job, JobImage, JobStage
from app.schemas import CharacterSummaryOut, GarmentAnalysisOut, JobImageOut, JobOut, SopCheckOut
from app.scraping.download import ALLOWED_IMAGE_TYPES, download_image
from app.scraping.fetch import build_failure_message, fetch_product

router = APIRouter()

UPLOADS_DIR = DATA_DIR / "uploads" / "jobs"
CHARACTER_UPLOADS_DIR = DATA_DIR / "uploads"


def job_to_out(job: Job) -> JobOut:
    def img_out(img: JobImage) -> JobImageOut:
        return JobImageOut(
            id=img.id,
            url=f"/uploads/jobs/{img.file_path}",
            source_url=img.source_url or "",
            original_filename=img.original_filename or "",
        )

    garment_analysis = None
    if job.garment_analysis_json:
        garment_analysis = GarmentAnalysisOut(**json.loads(job.garment_analysis_json))

    sop_checks = []
    if job.sop_check_results_json:
        sop_checks = [SopCheckOut(**c) for c in json.loads(job.sop_check_results_json)]

    return JobOut(
        id=job.id,
        character_id=job.character_id,
        character=CharacterSummaryOut.model_validate(job.character),
        source_url=job.source_url or "",
        fetch_method_used=job.fetch_method_used or "",
        fetch_status=job.fetch_status,
        fetch_error=job.fetch_error or "",
        product_title=job.product_title or "",
        product_description=job.product_description or "",
        stage=job.stage,
        garment_analysis=garment_analysis,
        generated_prompt=job.generated_prompt or "",
        sop_check_results=sop_checks,
        created_at=job.created_at,
        images=[img_out(i) for i in job.images],
    )


def save_manual_upload(job_id: str, upload: UploadFile) -> JobImage:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {upload.content_type}")
    ext = ALLOWED_IMAGE_TYPES[upload.content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_dir = UPLOADS_DIR / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return JobImage(
        job_id=job_id,
        file_path=f"{job_id}/{filename}",
        original_filename=upload.filename or "",
    )


@router.get("", response_model=List[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [job_to_out(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job_to_out(job)


@router.post("", response_model=JobOut)
def create_job(
    character_id: str = Form(...),
    source_url: str = Form(""),
    manual_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")

    source_url = source_url.strip()
    manual_files = [f for f in manual_images if f.filename]

    if not source_url and not manual_files:
        raise HTTPException(400, "Provide a product URL or upload product images")

    job = Job(character_id=character_id, source_url=source_url, fetch_status=FetchStatus.failed)
    db.add(job)
    db.flush()  # assign job.id

    scraped_images: list[str] = []
    title, description, method_used, url_fetch_error = "", "", "", ""

    if source_url:
        result, attempts = fetch_product(source_url)
        if result:
            scraped_images = result.images
            title, description, method_used = result.title, result.description, result.method
        else:
            url_fetch_error = build_failure_message(source_url, attempts)

    downloaded_any = False
    if scraped_images:
        dest_dir = UPLOADS_DIR / job.id
        for img_url in scraped_images:
            try:
                saved_path = download_image(dest_dir, img_url)
            except Exception:  # noqa: BLE001 — any single image failing shouldn't abort the job
                continue
            rel_path = f"{job.id}/{saved_path.name}"
            db.add(JobImage(job_id=job.id, file_path=rel_path, source_url=img_url))
            downloaded_any = True

        if downloaded_any:
            job.fetch_status = FetchStatus.success
            job.fetch_method_used = method_used
            job.product_title = title
            job.product_description = description
        else:
            url_fetch_error = (
                url_fetch_error
                or f"Found {len(scraped_images)} image link(s) on the page via {method_used}, "
                "but couldn't download any of them."
            )

    if job.fetch_status != FetchStatus.success:
        if manual_files:
            for f in manual_files:
                db.add(save_manual_upload(job.id, f))
            job.fetch_status = FetchStatus.success
            job.fetch_method_used = "manual_upload"
            if source_url:
                job.fetch_error = f"{url_fetch_error} Used manually uploaded photos instead."
        else:
            job.fetch_status = FetchStatus.failed
            job.fetch_error = url_fetch_error or "No product URL or images were provided."

    db.commit()
    db.refresh(job)
    return job_to_out(job)


@router.delete("/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job_dir = UPLOADS_DIR / job.id
    db.delete(job)
    db.commit()
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"ok": True}


@router.post("/{job_id}/generate", response_model=JobOut)
def generate_prompt(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.fetch_status != FetchStatus.success or not job.images:
        raise HTTPException(400, "This product has no fetched photos to generate a prompt from")

    character = job.character

    try:
        if not character.persona_description:
            identity_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path
                for img in character.images
                if img.kind == ImageKind.identity
            ]
            character.persona_description = analyze_persona(identity_paths)

        if not character.setting_description:
            setting_paths = [
                CHARACTER_UPLOADS_DIR / img.file_path for img in character.images if img.kind == ImageKind.setting
            ]
            character.setting_description = analyze_setting(setting_paths)

        garment_paths = [UPLOADS_DIR / img.file_path for img in job.images]
        garment = analyze_garment(garment_paths)
    except VisionNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, f"Couldn't generate a prompt: {e}") from e

    job.garment_analysis_json = json.dumps(dataclasses.asdict(garment))

    prompt_text = assemble_prompt(
        persona_description=character.persona_description,
        characteristics=character.characteristics or "",
        setting_description=character.setting_description,
        garment=garment,
        movement_notes="",
    )

    checks = run_sop_checks(prompt_text, garment)
    job.sop_check_results_json = json.dumps([dataclasses.asdict(c) for c in checks])

    if has_blocking_failure(checks):
        job.stage = JobStage.blocked
        job.generated_prompt = ""
    else:
        job.stage = JobStage.prompt_generated
        job.generated_prompt = prompt_text

    db.commit()
    db.refresh(job)
    return job_to_out(job)


@router.put("/{job_id}/approve", response_model=JobOut)
def approve_prompt(job_id: str, edited_prompt: str = Form(...), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.stage not in (JobStage.prompt_generated, JobStage.approved):
        raise HTTPException(400, "This product doesn't have a generated prompt to approve")
    if not edited_prompt.strip():
        raise HTTPException(400, "Prompt can't be empty")

    job.generated_prompt = edited_prompt
    job.stage = JobStage.approved
    db.commit()
    db.refresh(job)
    return job_to_out(job)

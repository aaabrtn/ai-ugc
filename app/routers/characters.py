import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import DATA_DIR, get_db
from app.generation.vision import VisionError, VisionNotConfigured, analyze_persona
from app.integrations.kie import KieError, KieNotConfigured, create_character as kie_create_character, upload_public_image
from app.models import Character, CharacterImage, ImageKind
from app.schemas import CharacterOut, ImageOut

router = APIRouter()

UPLOADS_DIR = DATA_DIR / "uploads"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def character_to_out(c: Character) -> CharacterOut:
    def img_out(img: CharacterImage) -> ImageOut:
        return ImageOut(
            id=img.id,
            kind=img.kind,
            url=f"/uploads/{img.file_path}",
            original_filename=img.original_filename or "",
        )

    return CharacterOut(
        id=c.id,
        name=c.name,
        characteristics=c.characteristics or "",
        setting_locked=c.setting_locked,
        persona_description=c.persona_description or "",
        setting_description=c.setting_description or "",
        kie_character_id=c.kie_character_id or "",
        kie_character_has_body=c.kie_character_has_body,
        created_at=c.created_at,
        updated_at=c.updated_at,
        identity_images=[img_out(i) for i in c.identity_images],
        setting_images=[img_out(i) for i in c.setting_images],
    )


def save_upload(character_id: str, kind: str, upload: UploadFile) -> CharacterImage:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {upload.content_type}")
    ext = Path(upload.filename or "").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    rel_dir = Path(character_id) / kind
    abs_dir = UPLOADS_DIR / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / filename
    with abs_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return CharacterImage(
        character_id=character_id,
        kind=ImageKind(kind),
        file_path=str(rel_dir / filename).replace("\\", "/"),
        original_filename=upload.filename or "",
    )


@router.get("", response_model=List[CharacterOut])
def list_characters(db: Session = Depends(get_db)):
    chars = db.query(Character).order_by(Character.created_at.desc()).all()
    return [character_to_out(c) for c in chars]


@router.get("/{character_id}", response_model=CharacterOut)
def get_character(character_id: str, db: Session = Depends(get_db)):
    c = db.get(Character, character_id)
    if not c:
        raise HTTPException(404, "Character not found")
    return character_to_out(c)


@router.post("", response_model=CharacterOut)
def create_character(
    name: str = Form(...),
    characteristics: str = Form(""),
    kie_character_id: str = Form(""),
    kie_character_has_body: bool = Form(True),
    identity_images: List[UploadFile] = File(default=[]),
    setting_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    name = name.strip()
    identity_files = [f for f in identity_images if f.filename]
    setting_files = [f for f in setting_images if f.filename]

    if not name:
        raise HTTPException(400, "Name is required")
    if not identity_files:
        raise HTTPException(400, "At least one character reference photo is required")
    if not setting_files:
        raise HTTPException(400, "At least one settings reference photo is required")

    character = Character(
        name=name,
        characteristics=characteristics,
        kie_character_id=kie_character_id.strip(),
        kie_character_has_body=kie_character_has_body,
        setting_locked=True,  # setting photos are locked as soon as they're first saved
    )
    db.add(character)
    db.flush()  # assign character.id before saving files against it

    for f in identity_files:
        db.add(save_upload(character.id, "identity", f))
    for f in setting_files:
        db.add(save_upload(character.id, "setting", f))

    db.commit()
    db.refresh(character)
    return character_to_out(character)


@router.put("/{character_id}", response_model=CharacterOut)
def update_character(
    character_id: str,
    name: str = Form(...),
    characteristics: str = Form(""),
    kie_character_id: str = Form(""),
    kie_character_has_body: bool = Form(True),
    confirm_setting_change: bool = Form(False),
    remove_image_ids: str = Form(""),
    identity_images: List[UploadFile] = File(default=[]),
    setting_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")

    name = name.strip()
    if not name:
        raise HTTPException(400, "Name is required")

    remove_ids = [i for i in remove_image_ids.split(",") if i]
    images_to_remove = (
        db.query(CharacterImage)
        .filter(CharacterImage.id.in_(remove_ids), CharacterImage.character_id == character.id)
        .all()
        if remove_ids
        else []
    )
    new_identity_files = [f for f in identity_images if f.filename]
    new_setting_files = [f for f in setting_images if f.filename]

    identity_touched = bool(new_identity_files) or any(
        img.kind == ImageKind.identity for img in images_to_remove
    )
    setting_touched = bool(new_setting_files) or any(
        img.kind == ImageKind.setting for img in images_to_remove
    )
    if character.setting_locked and setting_touched and not confirm_setting_change:
        raise HTTPException(
            409,
            "This character's setting is locked. This will change the look of all future videos with this "
            "character — confirm to proceed.",
        )

    remaining_identity = (
        len(character.identity_images)
        - sum(1 for img in images_to_remove if img.kind == ImageKind.identity)
        + len(new_identity_files)
    )
    remaining_setting = (
        len(character.setting_images)
        - sum(1 for img in images_to_remove if img.kind == ImageKind.setting)
        + len(new_setting_files)
    )
    if remaining_identity < 1:
        raise HTTPException(400, "Character must have at least one character reference photo")
    if remaining_setting < 1:
        raise HTTPException(400, "Character must have at least one settings reference photo")

    character.name = name
    character.characteristics = characteristics
    character.kie_character_id = kie_character_id.strip()
    character.kie_character_has_body = kie_character_has_body
    character.setting_locked = True

    # Cached AI-vision descriptions go stale the moment their source photos change;
    # clearing them here means the next prompt generation regenerates from the new photos.
    if identity_touched:
        character.persona_description = ""
    if setting_touched:
        character.setting_description = ""

    for img in images_to_remove:
        abs_path = UPLOADS_DIR / img.file_path
        if abs_path.exists():
            abs_path.unlink()
        db.delete(img)

    for f in new_identity_files:
        db.add(save_upload(character.id, "identity", f))
    for f in new_setting_files:
        db.add(save_upload(character.id, "setting", f))

    db.commit()
    db.refresh(character)
    return character_to_out(character)


@router.delete("/{character_id}")
def delete_character(character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")
    char_dir = UPLOADS_DIR / character.id
    db.delete(character)
    db.commit()
    if char_dir.exists():
        shutil.rmtree(char_dir, ignore_errors=True)
    return {"ok": True}


@router.post("/{character_id}/register-kie", response_model=CharacterOut)
def register_kie_character(character_id: str, db: Session = Depends(get_db)):
    """Registers this character with KIE (gemini-omni-character) and saves the
    returned character ID — the app-driven alternative to pasting in an ID for a
    character already created in KIE's own dashboard."""
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")
    if not character.identity_images:
        raise HTTPException(400, "This character needs at least one reference photo first")

    # KIE takes at most 2 images: index 0 portrait, index 1 an optional body shot.
    # The character's own upload order decides which photos those are.
    reference_images = character.identity_images[:2]
    has_body = len(reference_images) > 1

    try:
        if not character.persona_description:
            identity_paths = [UPLOADS_DIR / img.file_path for img in character.identity_images]
            character.persona_description = analyze_persona(identity_paths)
    except VisionNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, f"Couldn't describe this character: {e}") from e

    descriptions = character.persona_description
    if character.characteristics:
        descriptions = f"{descriptions} {character.characteristics}".strip()

    try:
        image_urls = [upload_public_image(UPLOADS_DIR / img.file_path) for img in reference_images]
    except KieNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except KieError as e:
        raise HTTPException(502, f"Couldn't prepare reference photos for KIE: {e}") from e

    try:
        result = kie_create_character(descriptions=descriptions, image_urls=image_urls, character_name=character.name)
    except KieNotConfigured as e:
        raise HTTPException(422, str(e)) from e
    except KieError as e:
        raise HTTPException(502, f"KIE rejected the character registration: {e}") from e

    character.kie_character_id = result["characterId"]
    character.kie_character_has_body = has_body

    db.commit()
    db.refresh(character)
    return character_to_out(character)

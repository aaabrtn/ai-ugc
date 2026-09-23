import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import DATA_DIR, get_db
from app.models import Character, CharacterImage, ConsentStatus, ImageKind
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
        consent_status=c.consent_status,
        face_shape=c.face_shape or "",
        hair_color=c.hair_color or "",
        hair_style=c.hair_style or "",
        hair_texture=c.hair_texture or "",
        skin_tone=c.skin_tone or "",
        eyes=c.eyes or "",
        build=c.build or "",
        signature_accessories=c.signature_accessories or "",
        tattoos=c.tattoos or "",
        default_expression=c.default_expression or "",
        characteristics_notes=c.characteristics_notes or "",
        setting_description=c.setting_description or "",
        setting_locked=c.setting_locked,
        movement_notes=c.movement_notes or "",
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
    consent_status: ConsentStatus = Form(ConsentStatus.internal_only),
    face_shape: str = Form(""),
    hair_color: str = Form(""),
    hair_style: str = Form(""),
    hair_texture: str = Form(""),
    skin_tone: str = Form(""),
    eyes: str = Form(""),
    build: str = Form(""),
    signature_accessories: str = Form(""),
    tattoos: str = Form(""),
    default_expression: str = Form(""),
    characteristics_notes: str = Form(""),
    setting_description: str = Form(""),
    movement_notes: str = Form(""),
    identity_images: List[UploadFile] = File(default=[]),
    setting_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    if not name.strip():
        raise HTTPException(400, "Name is required")
    if not setting_description.strip():
        raise HTTPException(400, "Setting description is required")

    character = Character(
        name=name.strip(),
        consent_status=consent_status,
        face_shape=face_shape,
        hair_color=hair_color,
        hair_style=hair_style,
        hair_texture=hair_texture,
        skin_tone=skin_tone,
        eyes=eyes,
        build=build,
        signature_accessories=signature_accessories,
        tattoos=tattoos,
        default_expression=default_expression,
        characteristics_notes=characteristics_notes,
        setting_description=setting_description.strip(),
        setting_locked=True,  # setting is locked as soon as it's first saved
        movement_notes=movement_notes,
    )
    db.add(character)
    db.flush()  # assign character.id before saving files against it

    for f in identity_images:
        if f.filename:
            db.add(save_upload(character.id, "identity", f))
    for f in setting_images:
        if f.filename:
            db.add(save_upload(character.id, "setting", f))

    db.commit()
    db.refresh(character)
    return character_to_out(character)


@router.put("/{character_id}", response_model=CharacterOut)
def update_character(
    character_id: str,
    name: str = Form(...),
    consent_status: ConsentStatus = Form(...),
    face_shape: str = Form(""),
    hair_color: str = Form(""),
    hair_style: str = Form(""),
    hair_texture: str = Form(""),
    skin_tone: str = Form(""),
    eyes: str = Form(""),
    build: str = Form(""),
    signature_accessories: str = Form(""),
    tattoos: str = Form(""),
    default_expression: str = Form(""),
    characteristics_notes: str = Form(""),
    setting_description: str = Form(""),
    movement_notes: str = Form(""),
    confirm_setting_change: bool = Form(False),
    remove_image_ids: str = Form(""),
    identity_images: List[UploadFile] = File(default=[]),
    setting_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(404, "Character not found")
    if not name.strip():
        raise HTTPException(400, "Name is required")

    remove_ids = [i for i in remove_image_ids.split(",") if i]
    images_to_remove = (
        db.query(CharacterImage)
        .filter(CharacterImage.id.in_(remove_ids), CharacterImage.character_id == character.id)
        .all()
        if remove_ids
        else []
    )
    new_setting_images = [f for f in setting_images if f.filename]

    setting_text_changed = setting_description.strip() and setting_description.strip() != (
        character.setting_description or ""
    ).strip()
    setting_images_touched = bool(new_setting_images) or any(
        img.kind == ImageKind.setting for img in images_to_remove
    )

    if character.setting_locked and (setting_text_changed or setting_images_touched) and not confirm_setting_change:
        raise HTTPException(
            409,
            "This character's setting is locked. This will change the look of all future videos with this "
            "character — confirm to proceed.",
        )

    character.name = name.strip()
    character.consent_status = consent_status
    character.face_shape = face_shape
    character.hair_color = hair_color
    character.hair_style = hair_style
    character.hair_texture = hair_texture
    character.skin_tone = skin_tone
    character.eyes = eyes
    character.build = build
    character.signature_accessories = signature_accessories
    character.tattoos = tattoos
    character.default_expression = default_expression
    character.characteristics_notes = characteristics_notes
    character.movement_notes = movement_notes

    if setting_text_changed:
        character.setting_description = setting_description.strip()
    if not character.setting_locked and setting_description.strip():
        character.setting_description = setting_description.strip()
    character.setting_locked = True

    for img in images_to_remove:
        abs_path = UPLOADS_DIR / img.file_path
        if abs_path.exists():
            abs_path.unlink()
        db.delete(img)

    for f in identity_images:
        if f.filename:
            db.add(save_upload(character.id, "identity", f))
    for f in new_setting_images:
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

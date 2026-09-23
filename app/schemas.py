from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from app.models import ConsentStatus, ImageKind


class ImageOut(BaseModel):
    id: str
    kind: ImageKind
    url: str
    original_filename: str

    model_config = ConfigDict(from_attributes=True)


class CharacterOut(BaseModel):
    id: str
    name: str
    consent_status: ConsentStatus

    face_shape: str
    hair_color: str
    hair_style: str
    hair_texture: str
    skin_tone: str
    eyes: str
    build: str
    signature_accessories: str
    tattoos: str
    default_expression: str
    characteristics_notes: str

    setting_description: str
    setting_locked: bool

    movement_notes: str

    created_at: datetime
    updated_at: datetime

    identity_images: List[ImageOut]
    setting_images: List[ImageOut]

    model_config = ConfigDict(from_attributes=True)

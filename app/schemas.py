from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from app.models import ImageKind


class ImageOut(BaseModel):
    id: str
    kind: ImageKind
    url: str
    original_filename: str

    model_config = ConfigDict(from_attributes=True)


class CharacterOut(BaseModel):
    id: str
    name: str
    characteristics: str
    setting_locked: bool

    created_at: datetime
    updated_at: datetime

    identity_images: List[ImageOut]
    setting_images: List[ImageOut]

    model_config = ConfigDict(from_attributes=True)

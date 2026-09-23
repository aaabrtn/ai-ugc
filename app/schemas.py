from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from app.models import FetchStatus, ImageKind


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


class CharacterSummaryOut(BaseModel):
    """Lightweight character shape for dropdowns/selectors elsewhere in the app."""

    id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class JobImageOut(BaseModel):
    id: str
    url: str
    source_url: str
    original_filename: str

    model_config = ConfigDict(from_attributes=True)


class JobOut(BaseModel):
    id: str
    character_id: str
    character: CharacterSummaryOut

    source_url: str
    fetch_method_used: str
    fetch_status: FetchStatus
    fetch_error: str

    product_title: str
    product_description: str

    created_at: datetime

    images: List[JobImageOut]

    model_config = ConfigDict(from_attributes=True)

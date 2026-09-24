from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models import FetchStatus, GenerationStage, ImageKind, VideoStatus


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

    persona_description: str
    setting_description: str

    kie_character_id: str
    kie_character_has_body: bool

    created_at: datetime
    updated_at: datetime

    identity_images: List[ImageOut]
    setting_images: List[ImageOut]

    model_config = ConfigDict(from_attributes=True)


class CharacterSummaryOut(BaseModel):
    """Lightweight character shape for dropdowns/selectors elsewhere in the app."""

    id: str
    name: str
    kie_character_id: str
    thumbnail_url: str = ""

    model_config = ConfigDict(from_attributes=True)


class ProductImageOut(BaseModel):
    id: str
    url: str
    source_url: str
    original_filename: str

    model_config = ConfigDict(from_attributes=True)


class ProductOut(BaseModel):
    id: str
    name: str

    source_url: str
    fetch_method_used: str
    fetch_status: FetchStatus
    fetch_error: str

    description: str
    additional_context: str

    created_at: datetime
    updated_at: datetime

    images: List[ProductImageOut]

    model_config = ConfigDict(from_attributes=True)


class ProductSummaryOut(BaseModel):
    """Lightweight product shape for dropdowns/selectors elsewhere in the app."""

    id: str
    name: str
    fetch_status: FetchStatus
    thumbnail_url: str = ""

    model_config = ConfigDict(from_attributes=True)


class GarmentAnalysisOut(BaseModel):
    description: str
    silhouette_note: str = ""  # default so old generations (stored before this field existed) still load
    back_detail: str
    loose_elements: str
    category_note: str


class SopCheckOut(BaseModel):
    id: str
    label: str
    status: str  # pass | fail | manual
    detail: str


class GenerationOut(BaseModel):
    id: str
    character_id: str
    character: CharacterSummaryOut
    product_id: str
    product: ProductSummaryOut

    stage: GenerationStage
    garment_analysis: Optional[GarmentAnalysisOut]
    generated_prompt: str
    sop_check_results: List[SopCheckOut]

    duration: str
    aspect_ratio: str
    resolution: str
    batch_id: str = ""  # shared across every generation created together by "Generate Batch"; "" if none
    batch_index: Optional[int] = None  # 1-indexed position within that batch; None outside a batch

    kie_task_id: str
    video_status: VideoStatus
    video_error: str
    video_url: str  # the app's own locally-served copy, once downloaded

    # Cost tracking — see the comment on the Generation model for what's exact
    # (vision) vs. a configured estimate (kie).
    vision_cost_usd: Optional[float] = None
    kie_credits_cost: Optional[float] = None
    kie_usd_cost: Optional[float] = None
    total_cost_usd: Optional[float] = None  # sum of whichever of the above are known; None if neither is

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

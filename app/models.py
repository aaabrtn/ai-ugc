import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class ImageKind(str, enum.Enum):
    identity = "identity"
    setting = "setting"


class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)

    # Free-text context only — physical traits are read directly from the
    # reference photos, not entered as structured fields.
    characteristics = Column(Text, default="")

    # Setting reference photos — locked once first saved (see routers/characters.py)
    setting_locked = Column(Boolean, default=False, nullable=False)

    # AI-vision-generated descriptions, cached here so they're computed once per
    # character rather than on every prompt generation. Never user-edited directly —
    # regenerated (lazily, on next prompt generation) whenever the underlying photos
    # change. Empty until first computed (e.g. no AI vision provider configured yet).
    persona_description = Column(Text, default="")
    setting_description = Column(Text, default="")

    # KIE character reference (Gemini Omni). Not created via our API — KIE requires
    # publicly-hosted images to register a character, which our locally-uploaded
    # photos aren't; instead this is entered manually once you've created the
    # character in KIE's own dashboard/playground. Required for video generation.
    kie_character_id = Column(String, default="")
    # Whether that KIE character was registered with a body reference image (not
    # just a portrait) — affects how much of KIE's 7-slot input quota it reserves.
    kie_character_has_body = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    images = relationship(
        "CharacterImage",
        back_populates="character",
        cascade="all, delete-orphan",
        order_by="CharacterImage.created_at",
    )

    @property
    def identity_images(self):
        return [img for img in self.images if img.kind == ImageKind.identity]

    @property
    def setting_images(self):
        return [img for img in self.images if img.kind == ImageKind.setting]


class CharacterImage(Base):
    __tablename__ = "character_images"

    id = Column(String, primary_key=True, default=gen_id)
    character_id = Column(String, ForeignKey("characters.id"), nullable=False)
    kind = Column(Enum(ImageKind), nullable=False)
    file_path = Column(String, nullable=False)  # path relative to data/uploads/
    original_filename = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    character = relationship("Character", back_populates="images")


class FetchStatus(str, enum.Enum):
    success = "success"
    failed = "failed"


class VideoStatus(str, enum.Enum):
    not_started = "not_started"
    waiting = "waiting"  # KIE's own states, used as-is once submitted
    queuing = "queuing"
    generating = "generating"
    success = "success"
    fail = "fail"


class Product(Base):
    """A catalogue entry: a product's photos and info, independent of any
    character. Fetched once (or added manually), reused across as many
    Generations (different characters, or retries) as you like."""

    __tablename__ = "products"

    id = Column(String, primary_key=True, default=gen_id)

    # Editable — defaults to the scraped page title but can be renamed to
    # something short and memorable.
    name = Column(String, nullable=False)

    source_url = Column(String, default="")
    fetch_method_used = Column(String, default="")  # structured_data / html_scrape / headless_browser / manual_upload
    fetch_status = Column(Enum(FetchStatus), nullable=False)
    fetch_error = Column(Text, default="")  # human-readable; set when fetch_status == failed, or as a note on fallback

    description = Column(Text, default="")  # scraped from the product page, read-only in the UI
    # Free-text, user-supplied: texture, thickness, anything not visible in the
    # photos themselves. Folded into the garment vision analysis as extra context.
    additional_context = Column(Text, default="")
    # Which garment this product actually is (trousers/shorts/dress/top/jacket),
    # set by Andrew, not AI-guessed. Drives the generation prompt's optional
    # [FOCUS] section (app/generation/garment_focus.py) so a video's movement
    # and gesture draw attention to this specific item when it's the one being
    # promoted. "" (the default) means unspecified -- no focus behaviour at all,
    # identical to how every product behaved before this feature existed.
    garment_type = Column(String, default="", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    images = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.created_at",
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(String, primary_key=True, default=gen_id)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    file_path = Column(String, nullable=False)  # path relative to data/uploads/
    source_url = Column(String, default="")  # original remote URL, if scraped
    original_filename = Column(String, default="")  # if manually uploaded
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="images")


class GenerationStage(str, enum.Enum):
    draft = "draft"  # character + product picked, no prompt yet
    blocked = "blocked"  # prompt generation was refused (e.g. content-boundary check failed)
    prompt_generated = "prompt_generated"  # prompt generated, awaiting review/edits
    approved = "approved"  # Andrew approved the (possibly edited) prompt


class Generation(Base):
    """One script: a specific character paired with a specific product. Holds
    the generated prompt, its SOP checks, and (Phase 3) the video attempt."""

    __tablename__ = "generations"

    id = Column(String, primary_key=True, default=gen_id)
    character_id = Column(String, ForeignKey("characters.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)

    stage = Column(Enum(GenerationStage), nullable=False, default=GenerationStage.draft)
    garment_analysis_json = Column(Text, default="")  # JSON-encoded GarmentAnalysis, for display/debugging
    generated_prompt = Column(Text, default="")
    sop_check_results_json = Column(Text, default="")  # JSON-encoded list of check results

    # Video settings, chosen once on the Generator form and carried through to
    # whichever flow eventually submits to KIE — duration in seconds ("8"/"10"),
    # resolution ("720p"/"1080p"/"4k"). Also what CREDIT_TABLE is keyed on.
    duration = Column(String, default="10", nullable=False)
    aspect_ratio = Column(String, default="9:16", nullable=False)
    resolution = Column(String, default="720p", nullable=False)

    # Groups generations created together by "Generate Batch" -- same character
    # and product, distinct movement choreography per video (see
    # generate_movement_variations) -- so History can show them together. NULL
    # for every generation created singly; never set after creation.
    batch_id = Column(String, nullable=True)
    # 1-indexed position within that batch. Batch siblings are created in the
    # same request and can share a created_at down to the second, which would
    # otherwise collide in the DD-MM-YY-HH-MM generation ID shown in History --
    # this disambiguates them (e.g. "...-14-05-2"). NULL outside a batch.
    batch_index = Column(Integer, nullable=True)

    # Video generation (Phase 3)
    kie_task_id = Column(String, default="")
    kie_model_used = Column(String, default="")
    video_status = Column(Enum(VideoStatus), nullable=False, default=VideoStatus.not_started)
    video_error = Column(Text, default="")
    video_submitted_at = Column(DateTime, nullable=True)
    # Set the moment video_status reaches a terminal state (success or fail) --
    # video_submitted_at to video_completed_at is the actual generation time
    # (KIE's real render duration), shown in History. Deliberately not the
    # time since the script/prompt was created, which can include however
    # long it sat in review before "Generate Video" was actually clicked.
    video_completed_at = Column(DateTime, nullable=True)
    # KIE's result URL expires ~24h after generation, so the video is downloaded
    # locally as soon as success is detected — video_local_path is what actually
    # gets played back and, later, uploaded to Drive. video_result_url is kept only
    # for reference/debugging.
    video_result_url = Column(Text, default="")
    video_local_path = Column(String, default="")

    # Cost tracking. Vision figures are exact — real token counts from the AI
    # vision calls this generation actually made (0 if persona/setting were
    # already cached from an earlier generation), priced at Anthropic's
    # published rate. KIE figures are a configured estimate (see config.py —
    # KIE's API has no per-task price field), not a live-verified charge.
    vision_input_tokens = Column(Integer, default=0, nullable=False)
    vision_output_tokens = Column(Integer, default=0, nullable=False)
    vision_cost_usd = Column(Float, nullable=True)
    kie_credits_cost = Column(Float, nullable=True)
    kie_usd_cost = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    character = relationship("Character")
    product = relationship("Product")

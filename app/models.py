import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
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


class JobStage(str, enum.Enum):
    fetched = "fetched"  # product photos in, no prompt generated yet
    blocked = "blocked"  # prompt generation was refused (e.g. content-boundary check failed)
    prompt_generated = "prompt_generated"  # prompt generated, awaiting review/edits
    approved = "approved"  # Andrew approved the (possibly edited) prompt


class VideoStatus(str, enum.Enum):
    not_started = "not_started"
    waiting = "waiting"  # KIE's own states, used as-is once submitted
    queuing = "queuing"
    generating = "generating"
    success = "success"
    fail = "fail"


class Job(Base):
    """A single product → video attempt. Phase 4 adds Drive upload of the
    finished video on top of this row."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=gen_id)
    character_id = Column(String, ForeignKey("characters.id"), nullable=False)

    source_url = Column(String, default="")
    fetch_method_used = Column(String, default="")  # structured_data / html_scrape / headless_browser / manual_upload
    fetch_status = Column(Enum(FetchStatus), nullable=False)
    fetch_error = Column(Text, default="")  # human-readable; set when fetch_status == failed, or as a note on fallback

    product_title = Column(String, default="")
    product_description = Column(Text, default="")

    stage = Column(Enum(JobStage), nullable=False, default=JobStage.fetched)
    garment_analysis_json = Column(Text, default="")  # JSON-encoded GarmentAnalysis, for display/debugging
    generated_prompt = Column(Text, default="")
    sop_check_results_json = Column(Text, default="")  # JSON-encoded list of check results

    # Video generation (Phase 3)
    kie_task_id = Column(String, default="")
    kie_model_used = Column(String, default="")
    video_status = Column(Enum(VideoStatus), nullable=False, default=VideoStatus.not_started)
    video_error = Column(Text, default="")
    video_submitted_at = Column(DateTime, nullable=True)
    # KIE's result URL expires ~24h after generation, so the video is downloaded
    # locally as soon as success is detected — video_local_path is what actually
    # gets played back and, later, uploaded to Drive. video_result_url is kept only
    # for reference/debugging.
    video_result_url = Column(Text, default="")
    video_local_path = Column(String, default="")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    character = relationship("Character")
    images = relationship(
        "JobImage",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobImage.created_at",
    )


class JobImage(Base):
    __tablename__ = "job_images"

    id = Column(String, primary_key=True, default=gen_id)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    file_path = Column(String, nullable=False)  # path relative to data/uploads/
    source_url = Column(String, default="")  # original remote URL, if scraped
    original_filename = Column(String, default="")  # if manually uploaded
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="images")

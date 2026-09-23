import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class ConsentStatus(str, enum.Enum):
    cleared = "cleared"
    internal_only = "internal_only"


class ImageKind(str, enum.Enum):
    identity = "identity"
    setting = "setting"


class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    consent_status = Column(Enum(ConsentStatus), nullable=False, default=ConsentStatus.internal_only)

    # Structured characteristics
    face_shape = Column(String, default="")
    hair_color = Column(String, default="")
    hair_style = Column(String, default="")
    hair_texture = Column(String, default="")
    skin_tone = Column(String, default="")
    eyes = Column(String, default="")
    build = Column(String, default="")
    signature_accessories = Column(String, default="")
    tattoos = Column(String, default="")
    default_expression = Column(String, default="")
    characteristics_notes = Column(Text, default="")

    # Setting — locked once first saved (see routers/characters.py)
    setting_description = Column(Text, default="")
    setting_locked = Column(Boolean, default=False, nullable=False)

    # Optional house-style movement override; blank = use SOP default
    movement_notes = Column(Text, default="")

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

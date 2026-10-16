"""SQLAlchemy models and session."""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

engine = create_engine(os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'pipeline.db'}"))
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str]
    path: Mapped[str]
    doc_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="received")  # received -> needs_review | approved | failed
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    fields: Mapped[list["Field"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan", order_by="Field.id"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "filename": self.filename, "doc_type": self.doc_type, "status": self.status,
            "error": self.error, "created_at": self.created_at.isoformat(),
            "fields": [f.to_dict() for f in self.fields],
        }


class Field(Base):
    __tablename__ = "fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    name: Mapped[str]
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float]
    error: Mapped[str | None]
    source: Mapped[str] = mapped_column(default="llm")  # llm | human
    reviewed: Mapped[bool] = mapped_column(default=False)
    document: Mapped[Document] = relationship(back_populates="fields")

    def to_dict(self) -> dict:
        return {
            "name": self.name, "value": self.value, "confidence": self.confidence,
            "error": self.error, "source": self.source, "reviewed": self.reviewed,
        }


Base.metadata.create_all(engine)

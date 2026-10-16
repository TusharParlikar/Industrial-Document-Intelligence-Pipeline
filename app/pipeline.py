"""Orchestration: extract -> LLM -> score -> route, plus reviewer actions."""
import logging
from typing import Any

from sqlalchemy import select

from app.db import Document, Field, Session
from app.extract import extract_text
from app.llm import extract_fields
from app.schemas import SCHEMAS
from app.scoring import route, score_fields, validation_errors

log = logging.getLogger(__name__)


def process(doc_id: int) -> None:
    with Session() as s:
        doc = s.get(Document, doc_id)
        try:
            text, quality = extract_text(doc.path)
            schema = SCHEMAS[doc.doc_type]
            scored = score_fields(extract_fields(text, doc.doc_type, schema), text, quality, schema)
        except Exception as e:
            log.exception("processing document %s failed", doc_id)
            doc.status, doc.error = "failed", f"{type(e).__name__}: {e}"
            s.commit()
            return
        doc.fields = [Field(**f, source="llm") for f in scored]
        doc.status, doc.error = route(scored), None
        s.commit()


def list_documents(status: str | None = None, doc_type: str | None = None) -> list[Document]:
    query = select(Document).order_by(Document.id)
    if status:
        query = query.where(Document.status == status)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    with Session() as s:
        return list(s.scalars(query))


def get_document(doc_id: int) -> Document | None:
    with Session() as s:
        return s.get(Document, doc_id)


def update_fields(doc_id: int, corrections: dict[str, Any]) -> Document:
    """Apply reviewer corrections and re-validate the whole record."""
    with Session() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise LookupError(f"document {doc_id} not found")
        by_name = {f.name: f for f in doc.fields}
        unknown = set(corrections) - set(by_name)
        if unknown:
            raise ValueError(f"unknown fields: {sorted(unknown)}")
        for name, value in corrections.items():
            f = by_name[name]
            f.value, f.source, f.reviewed, f.confidence = value, "human", True, 1.0

        schema = SCHEMAS[doc.doc_type]
        data = {f.name: f.value for f in doc.fields}
        errors = validation_errors(schema, data)
        if not errors:  # store normalized values ("12.5" -> 12.5, dates as ISO)
            data = schema.model_validate(data).model_dump(mode="json")
        for f in doc.fields:
            f.error = errors.get(f.name)
            if f.error:
                f.confidence = 0.0
            elif not errors:
                f.value = data[f.name]
        s.commit()
        return doc


def approve(doc_id: int) -> Document:
    with Session() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise LookupError(f"document {doc_id} not found")
        invalid = [f.name for f in doc.fields if f.error]
        if doc.status == "failed" or invalid:
            raise ValueError(f"cannot approve, invalid fields: {invalid}" if invalid else "processing failed")
        for f in doc.fields:
            f.reviewed = True
        doc.status = "approved"
        s.commit()
        return doc

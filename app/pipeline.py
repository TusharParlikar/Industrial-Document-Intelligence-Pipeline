"""Orchestration: extract -> LLM -> score -> route, plus reviewer actions."""
import logging
from typing import Any

from sqlalchemy import select

from app.db import Document, Field, Session
from app.extract import extract_text
from app.llm import extract_fields
from app.schemas import SCHEMAS
from app.scoring import route, score_fields

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

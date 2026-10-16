"""REST API. Run: uvicorn app.api:app --reload"""
import uuid
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import pipeline
from app.db import DATA_DIR, Document, Session
from app.llm import MODEL
from app.scoring import THRESHOLD

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
DocType = Literal["order_form", "technical_data_sheet", "bill_of_materials"]
Status = Literal["received", "needs_review", "approved", "failed"]

app = FastAPI(title="Industrial Document Intelligence Pipeline")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "threshold": THRESHOLD}


@app.get("/documents")
def list_documents(status: Status | None = None, doc_type: DocType | None = None):
    return [d.to_dict() for d in pipeline.list_documents(status=status, doc_type=doc_type)]


@app.post("/documents", status_code=202)
def upload(file: UploadFile, background: BackgroundTasks, doc_type: DocType = Form("order_form")):
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ALLOWED:
        raise HTTPException(415, f"unsupported file type, expected one of {sorted(ALLOWED)}")
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"  # never trust the client filename for paths
    path.write_bytes(file.file.read())  # ponytail: no size cap, put a limit in the reverse proxy
    with Session() as s:
        doc = Document(filename=file.filename, path=str(path), doc_type=doc_type)
        s.add(doc)
        s.commit()
    background.add_task(pipeline.process, doc.id)
    return {"id": doc.id, "status": doc.status}


@app.get("/documents/{doc_id}")
def get_document(doc_id: int):
    doc = pipeline.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return doc.to_dict()


@app.get("/documents/{doc_id}/file")
def document_file(doc_id: int):
    doc = pipeline.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return FileResponse(doc.path, filename=doc.filename)


@app.post("/documents/{doc_id}/reprocess", status_code=202)
def reprocess(doc_id: int, background: BackgroundTasks):
    try:
        doc = pipeline.reset_for_reprocess(doc_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    background.add_task(pipeline.process, doc.id)
    return {"id": doc.id, "status": doc.status}


@app.get("/review/queue")
def review_queue():
    return [d.to_dict() for d in pipeline.list_documents(status="needs_review")]


@app.patch("/documents/{doc_id}/fields")
def update_fields(doc_id: int, corrections: dict[str, Any]):
    try:
        return pipeline.update_fields(doc_id, corrections).to_dict()
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/documents/{doc_id}/approve")
def approve(doc_id: int):
    try:
        return pipeline.approve(doc_id).to_dict()
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/records")
def records(doc_type: DocType | None = None):
    return [
        {"id": d.id, "doc_type": d.doc_type, "filename": d.filename, "data": {f.name: f.value for f in d.fields}}
        for d in pipeline.list_documents(status="approved", doc_type=doc_type)
    ]

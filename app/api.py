"""REST API. Run: uvicorn app.api:app --reload"""
import uuid
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile

from app import pipeline
from app.db import DATA_DIR, Document, Session

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
DocType = Literal["order_form", "technical_data_sheet", "bill_of_materials"]

app = FastAPI(title="Industrial Document Intelligence Pipeline")


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

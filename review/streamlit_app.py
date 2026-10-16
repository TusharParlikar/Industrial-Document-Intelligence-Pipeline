"""Streamlit front end for the REST API. Run: streamlit run review/streamlit_app.py

Talks to the backend only over HTTP (API_URL), so it can run on a different machine than the API.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd
import pymupdf
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
DOC_TYPES = ["order_form", "technical_data_sheet", "bill_of_materials"]
STATUSES = ["received", "needs_review", "approved", "failed"]
ICON = {"received": "⏳", "needs_review": "⚠️", "approved": "✅", "failed": "❌"}


class ApiError(Exception):
    pass


def api(method: str, path: str, **kwargs):
    r = requests.request(method, f"{API}{path}", timeout=30, **kwargs)
    is_json = r.headers.get("content-type", "").startswith("application/json")
    if not r.ok:
        detail = r.json().get("detail", r.text) if is_json else r.text
        raise ApiError(f"{r.status_code}: {detail}")
    return r.json() if is_json else r.content


def label(doc_type: str) -> str:
    return doc_type.replace("_", " ").title()


@st.cache_data(show_spinner=False)
def page_images(doc_id: int, filename: str) -> list[bytes]:
    data = api("GET", f"/documents/{doc_id}/file")
    with pymupdf.open(stream=data, filetype=Path(filename).suffix.lstrip(".")) as doc:
        return [page.get_pixmap(dpi=110).tobytes("png") for page in doc]


def fields_table(doc: dict, threshold: float) -> None:
    rows = [{
        "": "⚠️" if f["error"] or f["confidence"] < threshold else "✅",
        "field": f["name"],
        "value": json.dumps(f["value"]) if isinstance(f["value"], (list, dict)) else f["value"],
        "confidence": f["confidence"],
        "source": f["source"],
        "error": f["error"],
    } for f in doc["fields"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
        "value": st.column_config.TextColumn(width="large"),
    })


# ---------------------------------------------------------------- pages

def upload_page():
    st.header("Upload documents")
    doc_type = st.selectbox("Document type", DOC_TYPES, format_func=label)
    files = st.file_uploader("PDF or scanned image", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"],
                             accept_multiple_files=True)
    if not st.button("Process", type="primary", disabled=not files):
        return

    ids = []
    for f in files:
        try:
            ids.append(api("POST", "/documents", files={"file": (f.name, f.getvalue())}, data={"doc_type": doc_type})["id"])
        except ApiError as e:
            st.error(f"{f.name}: {e}")

    done = {}
    with st.status(f"Extracting {len(ids)} document(s) with the LLM…", expanded=True) as status:
        deadline = time.time() + 300
        while len(done) < len(ids) and time.time() < deadline:
            for i in ids:
                if i not in done:
                    doc = api("GET", f"/documents/{i}")
                    if doc["status"] != "received":
                        done[i] = doc
                        st.write(f"{ICON[doc['status']]} #{i} {doc['filename']} → **{doc['status']}**")
            time.sleep(1.5)
        finished = len(done) == len(ids)
        status.update(label="Done" if finished else "Still processing, check the Documents page",
                      state="complete" if finished else "running")

    for doc in done.values():
        with st.expander(f"#{doc['id']} {doc['filename']} · {ICON[doc['status']]} {doc['status']}", expanded=True):
            if doc["error"]:
                st.error(doc["error"])
            else:
                fields_table(doc, THRESHOLD)
    if any(d["status"] == "needs_review" for d in done.values()):
        st.page_link(review, label="Go to review", icon="⚠️")


def documents_page():
    st.header("Documents")
    docs = api("GET", "/documents")[::-1]  # newest first
    counts = {s: sum(d["status"] == s for d in docs) for s in STATUSES}
    for col, s in zip(st.columns(4), STATUSES):
        col.metric(f"{ICON[s]} {s.replace('_', ' ')}", counts[s])

    shown = st.pills("Status", STATUSES, selection_mode="multi", default=STATUSES, format_func=lambda s: f"{ICON[s]} {s}")
    docs = [d for d in docs if d["status"] in shown]
    if not docs:
        st.info("No documents yet. Upload one first.")
        return

    table = pd.DataFrame([{
        "id": d["id"], "file": d["filename"], "type": label(d["doc_type"]), "status": f"{ICON[d['status']]} {d['status']}",
        "min confidence": min((f["confidence"] for f in d["fields"]), default=None),
        "created": d["created_at"][:19].replace("T", " "), "error": d["error"],
    } for d in docs])
    picked = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          column_config={"min confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    if not picked.selection.rows:
        st.caption("Select a row to see its fields.")
        return

    doc = docs[picked.selection.rows[0]]
    st.subheader(f"#{doc['id']} {doc['filename']}")
    if doc["error"]:
        st.error(doc["error"])
    if doc["status"] == "failed" and st.button("Reprocess", icon=":material/refresh:"):
        try:
            api("POST", f"/documents/{doc['id']}/reprocess")
            st.toast(f"#{doc['id']} queued again, refresh in a few seconds", icon="⏳")
        except ApiError as e:
            st.error(str(e))
    left, right = st.columns([2, 3])
    with right:
        fields_table(doc, THRESHOLD)
        st.download_button("Download JSON", json.dumps(doc, indent=2), f"document_{doc['id']}.json", "application/json")
    with left:
        try:
            for img in page_images(doc["id"], doc["filename"]):
                st.image(img)
        except Exception as e:  # corrupt uploads are exactly the ones that fail to render
            st.warning(f"Cannot render file: {e}")


def review_page():
    st.header("Review queue")
    queue = api("GET", "/review/queue")
    if not queue:
        st.success("Nothing to review.")
        return

    doc = st.selectbox("Document", queue, format_func=lambda d: f"#{d['id']} · {d['filename']} · {label(d['doc_type'])}")
    source, form = st.columns(2)
    with source:
        for img in page_images(doc["id"], doc["filename"]):
            st.image(img)

    with form:
        corrections = {}
        for f in doc["fields"]:
            flagged = f["error"] or f["confidence"] < THRESHOLD
            text = f"{'⚠️ ' if flagged else ''}{f['name']} · confidence {f['confidence']:.2f}"
            if f["error"]:
                st.error(f"{f['name']}: {f['error']}")
            key = f"{doc['id']}-{f['name']}"
            if isinstance(f["value"], list):
                original = pd.DataFrame(f["value"])
                edited = st.data_editor(original, num_rows="dynamic", key=key, width="stretch")
                st.caption(text)
                if not edited.equals(original):
                    corrections[f["name"]] = edited.astype(object).where(edited.notna(), None).to_dict("records")
            else:
                original = "" if f["value"] is None else str(f["value"])
                value = st.text_input(text, original, key=key)
                if value != original:
                    corrections[f["name"]] = value.strip() or None

        if st.button("Save and approve", type="primary"):
            try:
                if corrections:
                    api("PATCH", f"/documents/{doc['id']}/fields", json=corrections)
                api("POST", f"/documents/{doc['id']}/approve")
                st.toast(f"#{doc['id']} approved", icon="✅")
                st.rerun()
            except ApiError as e:
                st.error(str(e))


def records_page():
    st.header("Approved records")
    doc_type = st.selectbox("Document type", [None, *DOC_TYPES], format_func=lambda t: "All" if t is None else label(t))
    records = api("GET", "/records", params={"doc_type": doc_type} if doc_type else None)
    if not records:
        st.info("No approved records yet.")
        return
    st.download_button("Download all as JSON", json.dumps(records, indent=2), "records.json", "application/json")
    for r in records[::-1]:
        with st.expander(f"#{r['id']} {r['filename']} · {label(r['doc_type'])}"):
            scalars = {k: v for k, v in r["data"].items() if not isinstance(v, list)}
            st.dataframe(pd.DataFrame([scalars]), hide_index=True, width="stretch")
            for k, v in r["data"].items():
                if isinstance(v, list):
                    st.caption(k)
                    st.dataframe(pd.DataFrame(v), hide_index=True, width="stretch")


# ---------------------------------------------------------------- app

st.set_page_config(page_title="Document Intelligence", page_icon="📄", layout="wide")

try:
    health = api("GET", "/health")
except requests.ConnectionError:
    st.error(f"Backend not reachable at {API}. Start it with `uvicorn app.api:app`.")
    st.stop()
THRESHOLD = health["threshold"]

with st.sidebar:
    st.success(f"Backend connected · `{health['model']}`")
    st.caption(f"Auto-approve threshold: **{THRESHOLD}** · API: {API}")

review = st.Page(review_page, title=f"Review ({len(api('GET', '/review/queue'))})", icon=":material/rate_review:")
st.navigation([
    st.Page(upload_page, title="Upload", icon=":material/upload_file:", default=True),
    st.Page(documents_page, title="Documents", icon=":material/description:"),
    review,
    st.Page(records_page, title="Records", icon=":material/database:"),
]).run()

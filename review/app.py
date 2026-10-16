"""Human-review UI. Run: streamlit run review/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # streamlit only puts review/ on the path

import pandas as pd
import pymupdf
import streamlit as st

from app import pipeline
from app.scoring import THRESHOLD

st.set_page_config(page_title="Document Review", layout="wide")
st.title("Review queue")

queue = pipeline.list_documents(status="needs_review")
if not queue:
    st.success("Nothing to review.")
    st.stop()

doc = st.selectbox("Document", queue, format_func=lambda d: f"#{d.id} · {d.filename} · {d.doc_type}")
source, form = st.columns(2)

with source:
    with pymupdf.open(doc.path) as pdf:
        for page in pdf:
            st.image(page.get_pixmap(dpi=110).tobytes("png"))

with form:
    corrections = {}
    for f in doc.fields:
        flagged = f.error or f.confidence < THRESHOLD
        label = f"{'⚠️ ' if flagged else ''}{f.name} · confidence {f.confidence:.2f}"
        if f.error:
            st.error(f"{f.name}: {f.error}")
        if isinstance(f.value, list):
            original = pd.DataFrame(f.value)
            df = st.data_editor(original, num_rows="dynamic", key=f"{doc.id}-{f.name}", width="stretch")
            st.caption(label)
            if not df.equals(original):
                corrections[f.name] = df.astype(object).where(df.notna(), None).to_dict("records")
        else:
            original = "" if f.value is None else str(f.value)
            text = st.text_input(label, original, key=f"{doc.id}-{f.name}")
            if text != original:
                corrections[f.name] = text.strip() or None

    if st.button("Save and approve", type="primary"):
        updated = pipeline.update_fields(doc.id, corrections) if corrections else doc
        try:
            pipeline.approve(updated.id)
            st.success("Approved.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

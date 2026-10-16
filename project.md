# Industrial Document Intelligence Pipeline
github-httpsgithub.comTusharParlikarIndustrial-Document-Intelligence-Pipeline.git

## Description

An end-to-end pipeline that turns messy industrial documents (order forms, technical data sheets, BOMs) into clean, validated, structured data.

Documents are uploaded as PDFs or scans. The system extracts text (with OCR for scanned files), uses an LLM to pull out key fields into a fixed JSON schema, and validates every field with Pydantic. Each field gets a confidence score. Fields that score high are saved automatically. Fields that score low go to a human-review UI, where a person can correct them before they are saved. Approved records are stored in a database and exposed through a REST API, so other systems can use the data directly.

The goal is to cut manual data entry, reduce errors in product and order data, and keep a human in the loop only where the model is unsure.

**Key features**
- Handles both digital and scanned PDFs
- LLM-based field extraction into a strict schema
- Pydantic validation (types, ranges, required fields)
- Per-field confidence scoring with an auto-approve threshold
- Human-review UI for low-confidence fields
- REST API and database storage for approved records
- Optional automation hook (Power Automate / UiPath)

## Technologies Used

**Language**
- Python

**Document processing and OCR**
- PyMuPDF / pdfplumber (text and table extraction from digital PDFs)
- Tesseract OCR via pytesseract (scanned PDFs and images)
- pdf2image / Pillow (page-to-image conversion and preprocessing)

**AI / extraction**
- LLM API (ollama) for structured field extraction
- Prompt-based extraction with JSON output

**Validation**
- Pydantic (schema definition and validation)

**Backend**
- FastAPI (REST API)
- SQLAlchemy (ORM)
- SQLite (development) / PostgreSQL (production)

**Human-review UI**
- Streamlit

**Automation (optional)**
- Power Automate or UiPath (workflow trigger and RPA integration)

**Testing and tooling**
- pytest
- Docker
- Git / GitHub
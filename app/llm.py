"""LLM field extraction via LangChain + Ollama."""
import os

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel

MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
MAX_CHARS = 12_000  # ponytail: truncates long documents, chunk + merge if multi-page BOMs get cut off

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You extract structured data from industrial documents ({doc_type}). "
     "Return only JSON that matches the schema. Copy values exactly as they appear in the document. "
     "Use null for any value that is not in the document. Never guess."),
    ("human", "Document text:\n\n{text}"),
])


def extract_fields(text: str, doc_type: str, schema: type[BaseModel]) -> dict:
    """Return the raw extracted dict. Validation happens later so errors can be reported per field."""
    llm = ChatOllama(model=MODEL, temperature=0, format=schema.model_json_schema(), reasoning=False)
    chain = (PROMPT | llm | JsonOutputParser()).with_retry(stop_after_attempt=3)
    return chain.invoke({"doc_type": doc_type.replace("_", " "), "text": text[:MAX_CHARS]})

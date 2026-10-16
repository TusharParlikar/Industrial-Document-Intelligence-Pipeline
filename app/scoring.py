"""Per-field validation, confidence scoring and routing."""
import os
import re
from datetime import date

from pydantic import BaseModel, ValidationError

THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
# A null may mean "not in the document" or "the model missed it". We cannot tell, so a person confirms.
# ponytail: flat score, check for the field's label in the text if too many docs land in review
MISSING_SCORE = 0.5
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]


def validation_errors(schema: type[BaseModel], data: dict) -> dict[str, str]:
    """Map top-level field name -> first validation error message."""
    try:
        schema.model_validate(data)
        return {}
    except ValidationError as e:
        errors: dict[str, str] = {}
        for err in e.errors():
            errors.setdefault(str(err["loc"][0]) if err["loc"] else "_document", err["msg"])
        return errors


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _leaves(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _leaves(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v)
    elif value not in (None, ""):
        yield value


def _found(leaf, text: str, numbers: set[float]) -> bool:
    if isinstance(leaf, (int, float)) and not isinstance(leaf, bool):
        return float(leaf) in numbers
    s = _norm(leaf)
    if s in text:
        return True
    try:  # the model returns ISO dates, the document may not
        d = date.fromisoformat(s)
        return any(_norm(d.strftime(f)) in text for f in DATE_FORMATS)
    except ValueError:
        pass
    return all(token in text for token in s.split())


def grounding(value, text: str) -> float:
    """Fraction of the value's leaves that appear in the source text. Absent values get MISSING_SCORE."""
    leaves = list(_leaves(value))
    if not leaves:
        return MISSING_SCORE
    norm = _norm(text)
    # ponytail: "1,500.00" style only, European "1.500,00" will not match
    numbers = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
    return sum(_found(leaf, norm, numbers) for leaf in leaves) / len(leaves)


def score_fields(data: dict, text: str, source_quality: float, schema: type[BaseModel]) -> list[dict]:
    errors = validation_errors(schema, data)
    fields = []
    for name in schema.model_fields:
        value = data.get(name)
        confidence = 0.0 if name in errors else source_quality * grounding(value, text)
        fields.append({"name": name, "value": value, "confidence": round(confidence, 3), "error": errors.get(name)})
    return fields


def route(fields: list[dict]) -> str:
    return "approved" if all(f["confidence"] >= THRESHOLD for f in fields) else "needs_review"

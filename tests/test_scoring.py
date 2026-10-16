from app.schemas import OrderForm, TechnicalDataSheet
from app.scoring import MISSING_SCORE, grounding, route, score_fields, validation_errors

TEXT = """PURCHASE ORDER  PO-4471
Date: 03/14/2026
Customer: Acme Hydraulics Ltd
Part HX-200  Hydraulic valve  qty 12 pcs  unit price 1,250.00
Total: USD 15,000.00
"""

GOOD = {
    "order_number": "PO-4471",
    "order_date": "2026-03-14",
    "customer_name": "Acme Hydraulics Ltd",
    "line_items": [{"part_number": "HX-200", "description": "Hydraulic valve", "quantity": 12, "unit": "pcs", "unit_price": 1250.0}],
    "total_amount": 15000.0,
    "currency": "USD",
}


def test_grounding():
    assert grounding("PO-4471", TEXT) == 1.0
    assert grounding(15000.0, TEXT) == 1.0          # "15,000.00" in text
    assert grounding("2026-03-14", TEXT) == 1.0     # ISO vs 03/14/2026
    assert grounding(None, TEXT) == MISSING_SCORE   # unverifiable, a person confirms
    assert grounding("PO-9999", TEXT) == 0.0        # hallucinated
    assert grounding([{"a": "HX-200", "b": 99}], TEXT) == 0.0      # one bad leaf sinks the field
    assert grounding([{"a": "HX-200", "b": None}], TEXT) == MISSING_SCORE
    assert grounding(-20, "Operating temperature: -20 C to 180 C") == 1.0
    assert grounding(4471, TEXT) == 1.0             # "PO-4471" is not -4471


def test_clean_document_auto_approves():
    fields = score_fields(GOOD, TEXT, 1.0, OrderForm)
    assert all(f["confidence"] == 1.0 and f["error"] is None for f in fields)
    assert route(fields) == "approved"


def test_hallucination_and_invalid_go_to_review():
    bad = {**GOOD, "customer_name": "Globex Corp", "line_items": [{**GOOD["line_items"][0], "quantity": -1}]}
    fields = {f["name"]: f for f in score_fields(bad, TEXT, 1.0, OrderForm)}
    assert fields["customer_name"]["confidence"] == 0.0
    assert fields["line_items"]["confidence"] == 0.0 and fields["line_items"]["error"]
    assert route(list(fields.values())) == "needs_review"


def test_low_ocr_quality_goes_to_review():
    assert route(score_fields(GOOD, TEXT, 0.6, OrderForm)) == "needs_review"


def test_cross_field_rule():
    errors = validation_errors(TechnicalDataSheet, {
        "product_name": "Valve", "model_number": "V1", "operating_temp_min_c": 80, "operating_temp_max_c": -20,
    })
    assert set(errors) == {"operating_temp_max_c"}


def test_missing_value_goes_to_review():
    assert route(score_fields({**GOOD, "currency": None}, TEXT, 1.0, OrderForm)) == "needs_review"


def test_dropped_nested_key_goes_to_review():
    item = {k: v for k, v in GOOD["line_items"][0].items() if k != "description"}
    fields = {f["name"]: f for f in score_fields({**GOOD, "line_items": [item]}, TEXT, 1.0, OrderForm)}
    assert fields["line_items"]["confidence"] == MISSING_SCORE

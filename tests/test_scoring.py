from app.schemas import OrderForm, TechnicalDataSheet
from app.scoring import grounding, route, score_fields, validation_errors

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
    assert grounding(None, TEXT) == 1.0             # absent value is not a hallucination
    assert grounding("PO-9999", TEXT) == 0.0        # hallucinated
    assert grounding([{"a": "HX-200", "b": 99}], TEXT) == 0.5


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


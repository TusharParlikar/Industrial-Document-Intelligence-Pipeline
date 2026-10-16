"""Target schemas, one Pydantic model per document type."""
from datetime import date

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    part_number: str
    description: str | None = None
    quantity: float = Field(gt=0)
    unit: str | None = None
    unit_price: float | None = Field(default=None, ge=0)


class OrderForm(BaseModel):
    order_number: str
    order_date: date | None = None
    customer_name: str
    line_items: list[LineItem] = Field(min_length=1)
    total_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)


SCHEMAS: dict[str, type[BaseModel]] = {
    "order_form": OrderForm,
}

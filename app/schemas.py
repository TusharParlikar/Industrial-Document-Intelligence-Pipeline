"""Target schemas, one Pydantic model per document type."""
from datetime import date

from pydantic import BaseModel, Field, ValidationInfo, field_validator


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


class TechnicalDataSheet(BaseModel):
    product_name: str
    model_number: str
    manufacturer: str | None = None
    material: str | None = None
    operating_temp_min_c: float | None = None
    operating_temp_max_c: float | None = None
    max_pressure_bar: float | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, gt=0)

    @field_validator("operating_temp_max_c")
    @classmethod
    def max_above_min(cls, v: float | None, info: ValidationInfo) -> float | None:
        low = info.data.get("operating_temp_min_c")
        if v is not None and low is not None and v < low:
            raise ValueError("must be >= operating_temp_min_c")
        return v


SCHEMAS: dict[str, type[BaseModel]] = {
    "order_form": OrderForm,
    "technical_data_sheet": TechnicalDataSheet,
}

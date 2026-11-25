"""Pydantic models: request validation (Turkish messages) and response shape."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .countries import COUNTRIES

MODES = ("best_sellers", "top_rated", "value", "custom")
BADGES = ("best_seller", "top_rated", "value")
MAX_PRICE_SPREAD = 3  # price_max may be at most 3x price_min


def _clean(text):
    return " ".join((text or "").split())


class Filters(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_rating: Optional[float] = None
    limit: int = 10

    @field_validator("min_price", "max_price")
    @classmethod
    def _price(cls, v):
        if v is not None and v < 0:
            raise ValueError("Bütçe 0'dan küçük olamaz.")
        return v

    @field_validator("min_rating")
    @classmethod
    def _rating(cls, v):
        if v is not None and not (3.0 <= v <= 4.9):
            raise ValueError("Minimum puan 3,0 ile 4,9 arasında olmalı.")
        return v

    @field_validator("limit")
    @classmethod
    def _limit(cls, v):
        if v not in (5, 10):
            raise ValueError("Sonuç sayısı 5 veya 10 olmalı.")
        return v

    @model_validator(mode="after")
    def _range(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("En düşük bütçe, en yüksek bütçeden büyük olamaz.")
        return self


class SearchRequest(BaseModel):
    query: str
    country: Optional[str] = None
    mode: str = "best_sellers"
    filters: Filters = Field(default_factory=Filters)
    custom_criteria: str = ""

    @field_validator("query", mode="before")
    @classmethod
    def _query(cls, v):
        v = _clean(v if isinstance(v, str) else "")
        if len(v) < 2:
            raise ValueError("Lütfen ne almak istediğini yaz (en az 2 karakter).")
        if len(v) > 100:
            raise ValueError("Ürün adı en fazla 100 karakter olabilir.")
        return v

    @field_validator("country", mode="before")
    @classmethod
    def _country(cls, v):
        if v in (None, ""):
            return None
        if not isinstance(v, str) or v.upper() not in COUNTRIES:
            raise ValueError("Desteklenmeyen ülke.")
        return v.upper()

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v not in MODES:
            raise ValueError("Geçersiz listeleme ölçütü.")
        return v

    @field_validator("custom_criteria", mode="before")
    @classmethod
    def _custom(cls, v):
        v = _clean(v if isinstance(v, str) else "")
        if len(v) > 300:
            raise ValueError("Ek istekler en fazla 300 karakter olabilir.")
        return v

    @model_validator(mode="after")
    def _custom_required(self):
        if self.mode == "custom" and not self.custom_criteria:
            raise ValueError("Özel modda ek isteklerini yazman gerekiyor.")
        return self


def error_fields(exc):
    """Turn a pydantic ValidationError into {field: Turkish message}."""
    fields = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p != "__root__"]
        name = ".".join(loc) if loc else "custom_criteria"
        msg = err.get("msg", "")
        if err.get("type") == "value_error":
            msg = msg.removeprefix("Value error, ")
        else:
            msg = "Geçersiz değer."
        # Model-level validators report no field; map them to the field they concern.
        if not loc:
            if "Özel modda" in msg:
                name = "custom_criteria"
            elif "bütçe" in msg:
                name = "filters.max_price"
        fields.setdefault(name, msg)
    return fields


# --- Response ---------------------------------------------------------------

class Source(BaseModel):
    title: str = Field(min_length=1)
    url: str

    @field_validator("url")
    @classmethod
    def _https(cls, v):
        if not v.startswith("https://") or len(v) < 12:
            raise ValueError("source url must be https")
        return v


class Product(BaseModel):
    rank: int = 0
    name: str = Field(min_length=1)
    brand: Optional[str] = None
    # Price is mandatory: a product without a usable price is never listed.
    price_min: float = Field(gt=0)
    price_max: Optional[float] = Field(default=None, gt=0)
    # Where the price was verified (host name). Set by the app, never trusted from the model.
    price_source: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    rating_count: Optional[int] = Field(default=None, ge=0)
    rating_source: Optional[str] = None
    popularity_note: Optional[str] = None
    value_score: Optional[float] = Field(default=None, ge=0, le=10)
    badges: list[Literal["best_seller", "top_rated", "value"]] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    why_ranked: Optional[str] = None
    sources: list[Source] = Field(min_length=1)

    @model_validator(mode="after")
    def _price_consistency(self):
        if self.price_max is None:
            self.price_max = self.price_min  # a single known price
        if self.price_max < self.price_min:
            raise ValueError("price_max is lower than price_min")
        if self.price_max > self.price_min * MAX_PRICE_SPREAD:
            # One product with a >3x price spread usually means variants or accessories were mixed.
            raise ValueError("price range is too wide to describe one product")
        return self


class SearchResult(BaseModel):
    query: str
    country: str
    currency: str
    mode: str
    generated_at: str
    summary: str = ""
    products: list[Product]
    data_note: str = "Veriler web'den yapay zekâ ile derlenmiştir; fiyat ve stoklar değişebilir."

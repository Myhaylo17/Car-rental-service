import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

Category = Literal["economy", "sedan", "suv", "premium", "van"]
Transmission = Literal["automatic", "manual"]
FuelType = Literal["petrol", "diesel", "hybrid", "electric"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterInput(InputModel):
    email: EmailStr = Field(max_length=254)
    full_name: str = Field(min_length=2, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=128)
    password_confirmation: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = " ".join(unicodedata.normalize("NFC", value).split())
        if len(value) < 2 or any(
            unicodedata.category(c).startswith("C") for c in value
        ):
            raise ValueError("Name must contain 2-100 printable characters.")
        return value

    @model_validator(mode="after")
    def validate_password(self) -> "RegisterInput":
        password = self.password.get_secret_value()
        if password != self.password_confirmation.get_secret_value():
            raise ValueError("Passwords do not match.")
        if any(unicodedata.category(c).startswith("C") for c in password):
            raise ValueError("Control characters are not allowed in passwords.")
        if not password.strip() or password != password.strip():
            raise ValueError("Password cannot begin or end with whitespace.")
        weak = {"password123456", "123456789012", "qwerty123456", "passwordpassword"}
        if password.lower() in weak or len(set(password)) < 5:
            raise ValueError("Choose a less predictable password.")
        local_part = str(self.email).split("@")[0]
        if len(local_part) >= 4 and local_part in password.lower():
            raise ValueError("Password must not contain the email username.")
        return self


class LoginInput(InputModel):
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RefreshInput(InputModel):
    refresh_token: SecretStr = Field(min_length=40, max_length=128)


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str


class TokenOutput(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CarOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    brand: str
    model: str
    year: int
    category: str
    transmission: str
    fuel_type: str
    seats: int
    daily_price: Decimal
    currency: str
    description: str


class CarFilters(InputModel):
    q: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=60)
    category: Category | None = None
    transmission: Transmission | None = None
    fuel_type: FuelType | None = None
    min_seats: int | None = Field(default=None, ge=1, le=9)
    min_price: Decimal | None = Field(
        default=None, ge=0, le=1000000, max_digits=10, decimal_places=2
    )
    max_price: Decimal | None = Field(
        default=None, ge=0, le=1000000, max_digits=10, decimal_places=2
    )
    start_date: date | None = None
    end_date: date | None = None
    sort: Literal["price_asc", "price_desc", "newest"] = "price_asc"
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_ranges(self) -> "CarFilters":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Provide both start_date and end_date.")
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date.")
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price must not exceed max_price.")
        return self


class CarPage(BaseModel):
    items: list[CarOutput]
    total: int
    page: int
    page_size: int


class BookingInput(InputModel):
    car_id: int = Field(gt=0)
    start_date: date
    end_date: date


class BookingOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    car_id: int
    start_date: date
    end_date: date
    status: str
    daily_price: Decimal
    total_price: Decimal
    currency: str
    created_at: datetime
    cancelled_at: datetime | None


class AssistantInput(InputModel):
    message: str = Field(min_length=3, max_length=2000)


class AssistantPlan(BaseModel):
    """Only allow-listed catalog filters can be selected by the model."""

    q: str | None = Field(default=None, max_length=100)
    brand: str | None = Field(default=None, max_length=60)
    category: Category | None = None
    transmission: Transmission | None = None
    fuel_type: FuelType | None = None
    min_seats: int | None = Field(default=None, ge=1, le=9)
    max_price: float | None = Field(default=None, ge=0, le=1000000)
    start_date: date | None = None
    end_date: date | None = None


class AssistantRanking(BaseModel):
    car_ids: list[int] = Field(max_length=5)


class AssistantOutput(BaseModel):
    message: str
    applied_filters: CarFilters
    cars: list[CarOutput]

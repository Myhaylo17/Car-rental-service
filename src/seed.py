"""Idempotent development seed: ``python -m src.seed``.

Inserts only what is missing, keyed by natural keys (car slug, user email,
deterministic booking/idempotency UUIDs, favorite pair). Existing rows are never
updated or deleted. Sessions, refresh tokens and the email outbox are not seeded.
The shared demo password comes from SEED_USER_PASSWORD (env or .env).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.schemas import RegisterInput
from src.config import Settings, get_settings
from src.domain.booking import rental_total, validate_period
from src.domain.errors import DomainError
from src.infrastructure.database import engine, session_factory, utcnow
from src.infrastructure.models import Booking, Car, Favorite, User
from src.infrastructure.security import Argon2Passwords

# slug, brand, model, year, category, transmission, fuel, seats, UAH/day, description
# fmt: off
CARS: list[tuple[str, str, str, int, str, str, str, int, str, str]] = [
    ("hyundai-i10", "Hyundai", "i10", 2023, "economy", "manual", "petrol", 4, "900.00",
     "Компактний міський хетчбек: легко паркуватися, низька витрата пального."),
    ("kia-picanto", "Kia", "Picanto", 2022, "economy", "automatic", "petrol", 4,
     "950.00", "Малий автомат для міста; зручний для поїздок удвох."),
    ("skoda-fabia", "Skoda", "Fabia", 2022, "economy", "manual", "petrol", 5,
     "1000.00", "Практичний хетчбек для міста й коротких поїздок."),
    ("renault-clio", "Renault", "Clio", 2024, "economy", "manual", "petrol", 5,
     "1050.00", "Свіжий економний хетчбек на п'ять місць."),
    ("ford-focus", "Ford", "Focus", 2021, "economy", "manual", "diesel", 5,
     "1100.00", "Дизельний хетчбек для довших маршрутів за помірну ціну."),
    ("nissan-leaf", "Nissan", "Leaf", 2022, "economy", "automatic", "electric", 5,
     "1400.00", "Електромобіль для міста: тихий, без викидів, автоматична коробка."),
    ("toyota-corolla", "Toyota", "Corolla", 2023, "sedan", "automatic", "hybrid", 5,
     "1500.00", "Економний гібридний седан для міста й траси."),
    ("toyota-prius", "Toyota", "Prius", 2022, "sedan", "automatic", "hybrid", 5,
     "1550.00", "Гібрид з дуже низькою витратою пального для щоденних поїздок."),
    ("honda-civic", "Honda", "Civic", 2022, "sedan", "automatic", "petrol", 5,
     "1600.00", "Динамічний седан з автоматичною коробкою для комфортної їзди."),
    ("skoda-octavia", "Skoda", "Octavia", 2023, "sedan", "automatic", "diesel", 5,
     "1700.00", "Просторий дизельний седан для сім'ї та далеких поїздок."),
    ("mazda-6", "Mazda", "6", 2021, "sedan", "automatic", "petrol", 5,
     "1750.00", "Елегантний бензиновий седан з комфортним салоном."),
    ("vw-passat", "Volkswagen", "Passat", 2022, "sedan", "automatic", "diesel", 5,
     "1900.00", "Місткий дизельний седан для ділових і сімейних поїздок."),
    ("nissan-qashqai", "Nissan", "Qashqai", 2023, "suv", "automatic", "petrol", 5,
     "2100.00", "Компактний кросовер для міста та поїздок за місто."),
    ("kia-sportage", "Kia", "Sportage", 2023, "suv", "automatic", "diesel", 5,
     "2300.00", "Сімейний дизельний кросовер з просторим салоном."),
    ("toyota-rav4", "Toyota", "RAV4", 2024, "suv", "automatic", "hybrid", 5,
     "2400.00", "Гібридний кросовер для сім'ї: економний і комфортний."),
    ("vw-tiguan", "Volkswagen", "Tiguan", 2022, "suv", "automatic", "diesel", 5,
     "2450.00", "Універсальний дизельний кросовер для міста й подорожей."),
    ("hyundai-tucson", "Hyundai", "Tucson", 2024, "suv", "automatic", "hybrid", 5,
     "2500.00", "Сучасний гібридний кросовер з автоматичною коробкою."),
    ("skoda-kodiaq", "Skoda", "Kodiaq", 2023, "suv", "automatic", "diesel", 7,
     "2900.00", "Семимісний дизельний кросовер для великої родини."),
    ("hyundai-ioniq5", "Hyundai", "Ioniq 5", 2024, "suv", "automatic", "electric", 5,
     "3000.00", "Електричний кросовер для комфортних міських і міжміських поїздок."),
    ("bmw-530", "BMW", "530", 2023, "premium", "automatic", "diesel", 5,
     "3200.00", "Преміальний седан для ділових поїздок і дальніх маршрутів."),
    ("tesla-model-3", "Tesla", "Model 3", 2023, "premium", "automatic", "electric", 5,
     "3300.00", "Преміальний електричний седан з автоматичною коробкою."),
    ("audi-a6", "Audi", "A6", 2022, "premium", "automatic", "diesel", 5,
     "3400.00", "Комфортний преміальний седан для далеких поїздок."),
    ("mercedes-e-class", "Mercedes-Benz", "E-Class", 2023, "premium", "automatic",
     "diesel", 5, "3600.00", "Представницький седан для ділових поїздок."),
    ("volvo-xc90", "Volvo", "XC90", 2023, "premium", "automatic", "hybrid", 7,
     "4500.00", "Преміальний семимісний гібридний кросовер для великої компанії."),
    ("ford-transit-custom", "Ford", "Transit Custom", 2023, "van", "manual", "diesel",
     9, "2700.00", "Місткий мікроавтобус для груп до дев'яти осіб."),
    ("vw-transporter", "Volkswagen", "Transporter", 2022, "van", "manual", "diesel",
     8, "2800.00", "Місткий дизельний мікроавтобус для групи або вантажу."),
    ("mercedes-vito", "Mercedes-Benz", "Vito", 2022, "van", "automatic", "diesel", 8,
     "3100.00", "Мікроавтобус з автоматичною коробкою для груп до восьми осіб."),
]

# fmt: on

# Hidden from the catalog (is_active=False): verifies search/favorites filtering.
INACTIVE_CAR = (
    "peugeot-208-inactive-demo",
    "Peugeot",
    "208",
    2020,
    "economy",
    "manual",
    "petrol",
    5,
    "950.00",
    "Демо-авто вилучене з каталогу; в пошуку не показується.",
)

USERS = [
    ("anna.demo@example.com", "Анна Коваль"),
    ("oleh.demo@example.com", "Олег Бондар"),
    ("iryna.demo@example.com", "Ірина Мельник"),  # no favorites/bookings: empty state
]

FAVORITES = {
    "anna.demo@example.com": ["toyota-rav4", "hyundai-tucson", "tesla-model-3"],
    "oleh.demo@example.com": [
        "toyota-corolla",
        "vw-transporter",
        "skoda-kodiaq",
        "peugeot-208-inactive-demo",  # present in DB but hidden in the favorites list
    ],
}

# email, slug, label, start offset (days from today), length (days), status
BOOKINGS = [
    ("anna.demo@example.com", "toyota-rav4", "a", 14, 3, "confirmed"),
    ("anna.demo@example.com", "bmw-530", "b", 45, 5, "confirmed"),
    ("anna.demo@example.com", "skoda-fabia", "c", 20, 2, "cancelled"),
    ("oleh.demo@example.com", "vw-transporter", "a", 10, 4, "confirmed"),
    ("oleh.demo@example.com", "toyota-corolla", "b", 30, 2, "confirmed"),
]


def ensure_safe_environment(settings: Settings) -> None:
    if settings.app_env.strip().lower() in {"prod", "production"}:
        raise SystemExit("Refusing to seed: APP_ENV is production.")


def demo_password(settings: Settings) -> str:
    password = settings.seed_user_password.get_secret_value()
    if not password:
        raise SystemExit(
            "SEED_USER_PASSWORD is empty. Set it in .env (12+ characters, not "
            "containing the user's e-mail name) and run the seed again."
        )
    for email, name in USERS:
        try:
            RegisterInput(
                email=email,
                full_name=name,
                password=password,
                password_confirmation=password,
            )
        except ValidationError as exc:
            reasons = "; ".join(error["msg"] for error in exc.errors())
            raise SystemExit(
                f"SEED_USER_PASSWORD rejected by the registration rules: {reasons}"
            ) from None
    return password


def seed_id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "car-rental-dev-seed:" + ":".join(parts)))


async def seed_cars(session: AsyncSession) -> tuple[dict[str, Car], int]:
    cars: dict[str, Car] = {}
    created = 0
    for slug, brand, model, year, category, gear, fuel, seats, price, text in [
        *CARS,
        INACTIVE_CAR,
    ]:
        car = await session.scalar(select(Car).where(Car.slug == slug))
        if car is None:
            car = Car(
                slug=slug,
                brand=brand,
                model=model,
                year=year,
                category=category,
                transmission=gear,
                fuel_type=fuel,
                seats=seats,
                daily_price=Decimal(price),
                currency="UAH",
                description=text,
                is_active=slug != INACTIVE_CAR[0],
            )
            session.add(car)
            created += 1
        cars[slug] = car
    await session.flush()
    return cars, created


async def seed_users(
    session: AsyncSession, password: str
) -> tuple[dict[str, User], int]:
    users: dict[str, User] = {}
    created = 0
    hasher = Argon2Passwords()
    for email, name in USERS:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                full_name=name,
                password_hash=await hasher.hash(password),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            created += 1
        users[email] = user
    await session.flush()
    return users, created


async def seed_favorites(
    session: AsyncSession, users: dict[str, User], cars: dict[str, Car]
) -> int:
    created = 0
    for email, slugs in FAVORITES.items():
        for slug in slugs:
            key = (users[email].id, cars[slug].id)
            if await session.get(Favorite, key) is None:
                session.add(Favorite(user_id=key[0], car_id=key[1]))
                created += 1
    await session.flush()
    return created


async def seed_bookings(
    session: AsyncSession, users: dict[str, User], cars: dict[str, Car]
) -> tuple[int, list[str]]:
    """Future bookings that satisfy the booking rules; none enqueue e-mail."""
    created = 0
    skipped: list[str] = []
    today = datetime.now(UTC).date()
    for email, slug, label, offset, length, status in BOOKINGS:
        booking_id = seed_id("booking", email, slug, label)
        if await session.get(Booking, booking_id) is not None:
            continue
        car = cars[slug]
        start = today + timedelta(days=offset)
        end = start + timedelta(days=length)
        try:
            validate_period(start, end, today)
        except DomainError as exc:
            skipped.append(f"{slug} {label}: {exc.code}")
            continue
        if status == "confirmed":
            overlap = await session.scalar(
                select(Booking.id)
                .where(
                    Booking.car_id == car.id,
                    Booking.status == "confirmed",
                    Booking.start_date < end,
                    Booking.end_date > start,
                )
                .limit(1)
            )
            if overlap is not None:
                skipped.append(f"{slug} {label}: dates already booked")
                continue
        now = utcnow()
        session.add(
            Booking(
                id=booking_id,
                user_id=users[email].id,
                car_id=car.id,
                start_date=start,
                end_date=end,
                status=status,
                daily_price=car.daily_price,
                total_price=rental_total(car.daily_price, start, end),
                currency=car.currency,
                idempotency_key=seed_id("key", email, slug, label),
                created_at=now,
                cancelled_at=now if status == "cancelled" else None,
            )
        )
        created += 1
    await session.flush()
    return created, skipped


async def main() -> None:
    settings = get_settings()
    ensure_safe_environment(settings)
    password = demo_password(settings)
    try:
        async with session_factory() as session, session.begin():
            cars, new_cars = await seed_cars(session)
            users, new_users = await seed_users(session, password)
            new_favorites = await seed_favorites(session, users, cars)
            new_bookings, skipped = await seed_bookings(session, users, cars)
    finally:
        await engine.dispose()
    print(
        f"Seed finished. Created: cars={new_cars}, users={new_users}, "
        f"favorites={new_favorites}, bookings={new_bookings}."
    )
    for item in skipped:
        print(f"Booking skipped: {item}")


if __name__ == "__main__":
    asyncio.run(main())

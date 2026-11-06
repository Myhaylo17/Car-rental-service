from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from src.api.composition import authentication
from src.api.dependencies import Database, Principal, client_ip, limiter
from src.application.assistant import AssistantService
from src.application.bookings import BookingService
from src.application.schemas import (
    AssistantInput,
    AssistantOutput,
    BookingInput,
    BookingOutput,
    CarFilters,
    CarOutput,
    CarPage,
    LoginInput,
    RefreshInput,
    RegisterInput,
    TokenOutput,
    UserOutput,
)
from src.config import get_settings
from src.infrastructure.bookings import SqlBookingStore
from src.infrastructure.catalog import SqlCatalog
from src.infrastructure.favorites import SqlFavorites
from src.infrastructure.gemini import GeminiRecommendations

router = APIRouter(prefix="/api/v1")


@router.post(
    "/auth/register", response_model=UserOutput, status_code=201, tags=["Auth"]
)
async def register(data: RegisterInput, request: Request, db: Database) -> UserOutput:
    await limiter(request).check("register-ip", client_ip(request), 5, 3600)
    return await authentication(db).register(data)


@router.post("/auth/login", response_model=TokenOutput, tags=["Auth"])
async def login(
    data: LoginInput, request: Request, response: Response, db: Database
) -> TokenOutput:
    response.headers["Cache-Control"] = "no-store"
    await limiter(request).check("login-ip", client_ip(request), 30, 900)
    await limiter(request).check("login-email", str(data.email), 10, 900)
    return await authentication(db).login(data)


@router.post("/auth/refresh", response_model=TokenOutput, tags=["Auth"])
async def refresh(
    data: RefreshInput, request: Request, response: Response, db: Database
) -> TokenOutput:
    response.headers["Cache-Control"] = "no-store"
    await limiter(request).check("refresh-ip", client_ip(request), 60, 900)
    return await authentication(db).refresh(data.refresh_token.get_secret_value())


@router.post("/auth/logout", status_code=204, tags=["Auth"])
async def logout(current: Principal, db: Database) -> Response:
    await authentication(db).logout(current[1])
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/auth/me", response_model=UserOutput, tags=["Auth"])
async def me(current: Principal) -> UserOutput:
    return current[0]


@router.get("/cars", response_model=CarPage, tags=["Cars"])
async def cars(db: Database, filters: Annotated[CarFilters, Query()]) -> CarPage:
    return await SqlCatalog(db).search(filters)


@router.get("/cars/{car_id}", response_model=CarOutput, tags=["Cars"])
async def car(car_id: int, db: Database) -> CarOutput:
    return await SqlCatalog(db).get(car_id)


@router.post(
    "/bookings", response_model=BookingOutput, status_code=201, tags=["Bookings"]
)
async def create_booking(
    data: BookingInput,
    current: Principal,
    db: Database,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> BookingOutput:
    return await BookingService(SqlBookingStore(db)).create(
        current[0].id, str(idempotency_key), data
    )


@router.get("/bookings", response_model=list[BookingOutput], tags=["Bookings"])
async def list_bookings(
    current: Principal,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[BookingOutput]:
    return await SqlBookingStore(db).list_owned(current[0].id, limit, offset)


@router.get("/bookings/{booking_id}", response_model=BookingOutput, tags=["Bookings"])
async def get_booking(
    booking_id: UUID, current: Principal, db: Database
) -> BookingOutput:
    return await SqlBookingStore(db).get_owned(str(booking_id), current[0].id)


@router.post(
    "/bookings/{booking_id}/cancel", response_model=BookingOutput, tags=["Bookings"]
)
async def cancel_booking(
    booking_id: UUID, current: Principal, db: Database
) -> BookingOutput:
    return await BookingService(SqlBookingStore(db)).cancel(
        current[0].id, str(booking_id)
    )


@router.get("/favorites", response_model=list[CarOutput], tags=["Favorites"])
async def list_favorites(
    current: Principal,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[CarOutput]:
    return await SqlFavorites(db).list_owned(current[0].id, limit, offset)


@router.put("/favorites/{car_id}", status_code=204, tags=["Favorites"])
async def add_favorite(car_id: int, current: Principal, db: Database) -> Response:
    await SqlFavorites(db).add(current[0].id, car_id)
    return Response(status_code=204)


@router.delete("/favorites/{car_id}", status_code=204, tags=["Favorites"])
async def remove_favorite(car_id: int, current: Principal, db: Database) -> Response:
    await SqlFavorites(db).remove(current[0].id, car_id)
    return Response(status_code=204)


@router.post(
    "/assistant/recommendations", response_model=AssistantOutput, tags=["Assistant"]
)
async def assistant(
    data: AssistantInput,
    request: Request,
    current: Principal,
    db: Database,
) -> AssistantOutput:
    await limiter(request).check("assistant-user", str(current[0].id), 10, 3600)
    service = AssistantService(SqlCatalog(db), GeminiRecommendations(get_settings()))
    return await service.recommend(data.message)

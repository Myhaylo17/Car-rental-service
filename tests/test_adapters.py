from unittest.mock import AsyncMock

import pytest

from src.application.assistant import AssistantService
from src.application.schemas import CarFilters
from src.domain.errors import DomainError
from src.infrastructure.catalog import SqlCatalog


async def test_ai_cannot_invent_car_records(factory):
    async with factory() as session:
        model = AsyncMock()
        model.plan.return_value = {"category": "sedan"}
        model.rank.return_value = [999999, 1, 1]
        result = await AssistantService(SqlCatalog(session), model).recommend(
            "Сімейне авто"
        )
        assert [c.id for c in result.cars] == [1]
        assert (
            result.cars[0].daily_price
            == (await SqlCatalog(session).search(CarFilters())).items[0].daily_price
        )


async def test_ai_invalid_date_range_rejected(factory):
    model = AsyncMock()
    model.plan.return_value = {"start_date": "2028-01-02", "end_date": "2028-01-01"}
    async with factory() as session:
        with pytest.raises(DomainError) as error:
            await AssistantService(SqlCatalog(session), model).recommend(
                "Invalid dates"
            )
        assert error.value.status == 422

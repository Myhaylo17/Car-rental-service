from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from src.application.schemas import AssistantPlan
from src.config import get_settings
from src.domain.errors import DomainError
from src.infrastructure import gemini


async def test_sdk_adapter_serializes_schema_and_closes_client(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "google_api_key": SecretStr("dummy"),
            "google_model": "configured-model",
        }
    )
    models = SimpleNamespace(
        generate_content=AsyncMock(
            return_value=SimpleNamespace(
                text='{"category":"suv","max_price":2500}',
            )
        )
    )
    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(models=models)
    client = MagicMock(return_value=SimpleNamespace(aio=context))
    monkeypatch.setattr(gemini.genai, "Client", client)
    result = await gemini.GeminiRecommendations(settings).plan("SUV до 2500 грн")
    assert result["category"] == "suv"
    context.__aexit__.assert_awaited_once()
    config = models.generate_content.call_args.kwargs["config"]
    assert config.response_schema is AssistantPlan


async def test_missing_google_configuration_returns_503():
    settings = get_settings().model_copy(update={"google_api_key": SecretStr("")})
    with pytest.raises(DomainError) as error:
        await gemini.GeminiRecommendations(settings).plan("Car")
    assert error.value.status == 503

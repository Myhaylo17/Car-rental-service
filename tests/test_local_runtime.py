from fastapi.testclient import TestClient

from src.main import create_application


def test_lifespan_and_login_throttling_without_external_services():
    # Fail before touching the DB: this endpoint creates no valid registration.
    app = create_application()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        limiter = app.state.limiter
        assert limiter.__class__.__name__ == "InMemoryRateLimiter"


async def test_console_email_does_not_connect_to_smtp(monkeypatch, caplog):
    import logging
    from unittest.mock import AsyncMock

    from src.config import get_settings
    from src.infrastructure import email
    from src.infrastructure.models import EmailOutbox

    smtp = AsyncMock()
    monkeypatch.setattr(email.aiosmtplib, "send", smtp)
    event = EmailOutbox(
        id="test",
        recipient="test@example.com",
        subject="Test booking",
        payload={
            "event": "confirmed",
            "booking": {
                "id": "test",
                "car_id": 1,
                "start_date": "2027-01-01",
                "end_date": "2027-01-03",
                "total_price": "3000.00",
                "currency": "UAH",
            },
        },
    )
    with caplog.at_level(logging.INFO):
        await email.deliver_email(
            event, get_settings().model_copy(update={"email_backend": "console"})
        )
    smtp.assert_not_awaited()
    assert "DEV EMAIL (not sent)" in caplog.text

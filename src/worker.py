import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from src.config import get_settings
from src.infrastructure.database import engine, session_factory, utcnow
from src.infrastructure.email import deliver_email
from src.infrastructure.models import EmailOutbox

logger = logging.getLogger(__name__)


async def process_one() -> bool:
    async with session_factory() as session, session.begin():
        event = await session.scalar(
            select(EmailOutbox)
            .where(
                EmailOutbox.sent_at.is_(None),
                EmailOutbox.dead_letter.is_(False),
                EmailOutbox.available_at <= utcnow(),
            )
            .order_by(EmailOutbox.available_at, EmailOutbox.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return False
        event.attempts += 1
        try:
            # Row lock is intentionally held during bounded SMTP I/O.
            await deliver_email(event, get_settings())
        except Exception as exc:
            logger.warning(
                "Email attempt failed event=%s type=%s", event.id, type(exc).__name__
            )
            event.dead_letter = event.attempts >= 8
            event.available_at = utcnow() + timedelta(
                seconds=min(3600, 2**event.attempts * 10)
            )
        else:
            event.sent_at = utcnow()
        return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        while True:
            try:
                if not await process_one():
                    await asyncio.sleep(2)
            except Exception as exc:
                logger.error("Worker iteration failed: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

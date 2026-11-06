import logging
from email.message import EmailMessage

import aiosmtplib

from src.config import Settings
from src.infrastructure.models import EmailOutbox


async def deliver_email(event: EmailOutbox, settings: Settings) -> None:
    booking = event.payload["booking"]
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = event.recipient
    message["Subject"] = event.subject
    message["Message-ID"] = f"<{event.id}@car-rental.local>"
    message.set_content(
        f"Booking: {booking['id']}\n"
        f"Status: {event.payload['event']}\n"
        f"Car ID: {booking['car_id']}\n"
        f"Period: {booking['start_date']} to {booking['end_date']} "
        "(return date excluded)\n"
        f"Total: {booking['total_price']} {booking['currency']}\n"
    )
    if settings.email_backend == "console":
        logging.getLogger(__name__).info(
            "DEV EMAIL (not sent):\n%s", message.as_string()
        )
        return
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password.get_secret_value() or None,
        start_tls=settings.smtp_starttls,
        use_tls=settings.smtp_use_tls,
        timeout=15,
    )

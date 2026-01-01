import logging
import asyncio
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

# from src.database import async_session
from src.notifications import EmailSenderInterface
from src.config import get_accounts_email_notificator
from src.tasks.celery_app import celery_app

from src.config.get_settings import get_settings  # ← direct import
from src.notifications import EmailSender  # ← the real class
from typing import TypeVar, Awaitable

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_async(coro: Awaitable[T]) -> T:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    finally:
        asyncio.set_event_loop(None)


def get_accounts_email_notificator_celery() -> EmailSender:
    settings = get_settings()

    return EmailSender(
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        email=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        template_dir=settings.PATH_TO_EMAIL_TEMPLATES_DIR,
        activation_email_template_name=settings.ACTIVATION_EMAIL_TEMPLATE_NAME,
        activation_complete_email_template_name=settings.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME,
        password_email_template_name=settings.PASSWORD_RESET_TEMPLATE_NAME,
        password_complete_email_template_name=settings.PASSWORD_RESET_COMPLETE_TEMPLATE_NAME,
        comment_reply_template_name=settings.COMMENT_REPLY_TEMPLATE_NAME,
        comment_like_template_name=settings.COMMENT_LIKE_TEMPLATE_NAME,
        payment_email_template_name=settings.PAYMENT_EMAIL_TEMPLATE_NAME
    )


@celery_app.task(
    name="src.tasks.comment_notifications.send_comment_reply_email",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
def send_comment_reply_email(
    self,
    email: str,
    parent_preview: str,
    current_preview: str,
    reply_link: str,
) -> None:
    """Send email when someone replies to a comment"""

    try:
        email_sender = get_accounts_email_notificator_celery()

        run_async(
            email_sender.send_comment_reply_email(
                email, parent_preview, current_preview, reply_link
            )
        )

        logger.info(f"Reply email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send reply email to {email}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.tasks.comment_notifications.send_comment_like_email",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
def send_comment_like_email(
    self,
    email: str,
    parent_preview: str,
    comment_link: str,
) -> None:
    """Send email when someone likes a comment."""

    try:
        email_sender = get_accounts_email_notificator_celery()

        run_async(
            email_sender.send_comment_like_email(email, parent_preview, comment_link)
        )

        logger.info(f"Like email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send like email to {email}: {exc}")
        raise self.retry(exc=exc)

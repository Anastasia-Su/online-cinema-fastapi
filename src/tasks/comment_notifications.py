import logging
import asyncio
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
# from src.database import async_session
from src.notifications import EmailSenderInterface
from src.config import get_accounts_email_notificator
from src.tasks.celery_app import celery_app

from src.config.get_settings import get_settings   # ← direct import
from src.notifications import EmailSender           # ← the real class

logger = logging.getLogger(__name__)

@celery_app.task(
    name="src.tasks.comment_notifications.send_comment_reply_email", bind=True, max_retries=5, default_retry_delay=60
)
async def send_comment_reply_email(
    self,
    email,
    # recipient_email: str,
    # recipient_username: str,
    # actor_username: str,
    # movie_title: str,
    parent_preview,
    current_preview,
    reply_link: str,
):
    """Send email when someone replies to a comment"""
    try:
        settings = get_settings()

        # CREATE EMAIL SENDER ONCE, AT IMPORT TIME — SAFE AND FAST
        email_sender = EmailSender(
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
        )   
        
        
        await email_sender.send_comment_reply_email(email, parent_preview, current_preview, reply_link)
        

        # # Use same email sender as your auth emails
        
        # loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(loop)
        # loop.run_until_complete(
        #     email_sender.send_templated_email(
        #         to=recipient_email,
        #         subject=subject,
        #         template_name="emails/comment_reply.html",
        #         context=context,
        #     )
        # )
        # loop.close()

        logger.info(f"Reply email sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send reply email to {email}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(name="src.tasks.comment_notifications.send_comment_like_email", bind=True, max_retries=5, default_retry_delay=60)
def send_comment_like_email(
    self,
    recipient_email: str,
    recipient_username: str,
    actor_username: str,
    movie_title: str,
    comment_link: str,
):
    """Send email when someone likes a comment (coalesced — only once per user)"""
    try:
        email_sender: EmailSenderInterface = get_accounts_email_notificator()
        
        subject = f"{actor_username} liked your comment on \"{movie_title}\""
        context = {
            "recipient_username": recipient_username,
            "actor_username": actor_username,
            "movie_title": movie_title,
            "comment_link": comment_link,
        }

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            email_sender.send_templated_email(
                to=recipient_email,
                subject=subject,
                template_name="emails/comment_like.html",
                context=context,
            )
        )
        loop.close()

        logger.info(f"Like email sent to {recipient_email}")
    except Exception as exc:
        logger.error(f"Failed to send like email: {exc}")
        raise self.retry(exc=exc)
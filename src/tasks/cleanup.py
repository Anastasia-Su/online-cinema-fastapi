
from datetime import datetime, timezone
from sqlalchemy import delete, select
from src.database.models.accounts import ActivationTokenModel, PasswordResetTokenModel
from src.database.session_db import AsyncSessionLocal

@celery.task(name="src.tasks.cleanup_expired_tokens")
def cleanup_expired_tokens():
    # Use sync session or run async via asyncio.run, here using sync pattern assuming session is sync.
    from sqlalchemy.orm import Session
    from src.database.session_db import SessionLocal  # if you have sync SessionLocal
    with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        session.execute(delete(ActivationTokenModel).where(ActivationTokenModel.expires_at < now))
        session.execute(delete(PasswordResetTokenModel).where(PasswordResetTokenModel.expires_at < now))
        session.commit()

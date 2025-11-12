
from datetime import datetime, timezone
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker
from src.database.models.accounts import ActivationTokenModel, PasswordResetTokenModel
from src.database.session_db import sync_engine
from src.tasks.celery_app import celery
from typing import cast


SessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)
@celery.task(name="cleanup_expired_tokens")
def cleanup_expired_tokens():
    """Delete expired activation and password reset tokens."""
    now = datetime.now(timezone.utc)
    
    with SessionLocal() as session:
        session.execute(
            delete(ActivationTokenModel).where(ActivationTokenModel.expires_at < now)
            
        )
        session.execute(
            delete(PasswordResetTokenModel).where(PasswordResetTokenModel.expires_at < now)
        )
        session.commit()
    print(f"[Celery] Expired tokens cleaned up at {now.isoformat()}")

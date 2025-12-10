
import os
import asyncio
from fastapi.testclient import TestClient
os.environ["ENVIRONMENT"] = "testing"

from src.database.session_sqlite import AsyncSQLiteSessionLocal
AsyncSessionLocal = AsyncSQLiteSessionLocal

import pytest_asyncio, pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_accounts_email_notificator, get_s3_storage_client
from src.database import (
    reset_database,
    get_db_contextmanager,
    UserGroupEnum,
    UserGroupModel,
)
from src.config.get_settings import get_settings

# from src.database.populate import CSVDatabaseSeeder
from src.main import app
from src.security.interfaces import JWTAuthManagerInterface
from src.security.token_manager import JWTAuthManager
from src.storages import S3StorageClient
from tests.doubles.fakes.storage import FakeS3Storage
from tests.doubles.stubs.emails import StubEmailSender

import aioredis


import asyncio
import pytest

# @pytest.fixture(autouse=True)  # ← NOT pytest_asyncio.fixture — SYNC FIXTURE!
# def fresh_event_loop():
#     """
#     Gives every test its own fresh event loop.
#     This is the ONLY way to make httpx.AsyncClient work on Windows with multiple tests.
#     """
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     yield
#     loop.close()
# @pytest_asyncio.fixture(autouse=True)
# async def fresh_event_loop():
#     """
#     This gives EVERY test its own fresh event loop.
#     This is the ONLY way to make AsyncClient work on Windows with multiple tests.
#     """
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     yield
#     if not loop.is_closed():
#         loop.close()
# @pytest_asyncio.fixture
# async def redis_client():
#     redis = await aioredis.from_url("redis://localhost", decode_responses=True)
#     yield redis
#     await redis.close()
    
from src.database.session_sqlite import sqlite_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

# conftest.py — THE FINAL, BULLETPROOF db_session (copy-paste this)

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


# @pytest_asyncio.fixture
# async def db_session():
#     """
#     Perfect, bulletproof AsyncSession for tests:
#     - Uses the same engine as the app
#     - One transaction per test
#     - Auto rollback
#     - NO "closed transaction"
#     - NO "different loop"
#     - NO StopAsyncIteration
#     """
#     from src.database.session_sqlite import sqlite_engine

#     AsyncSessionLocal = async_sessionmaker(
#         bind=sqlite_engine,
#         expire_on_commit=False,
#         class_=AsyncSession,
#     )

#     session = AsyncSessionLocal()
    
#     # Start transaction
#     await session.begin()
    
#     try:
#         yield session
#     finally:
#         # Rollback and close — this fixes "closed transaction" error
#         await session.rollback()
#         await session.close()
    
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "order: Specify the order of test execution")
    config.addinivalue_line("markers", "unit: Unit tests")


from src.database.populate_db import seed_movies, seed_user_groups, seed_users

             
@pytest_asyncio.fixture(scope="function", autouse=True)
async def reset_db(request):
    """
    Reset the SQLite database before each test function, except for tests marked with 'e2e'.

    By default, this fixture ensures that the database is cleared and recreated before every
    test function to maintain test isolation. However, if the test is marked with 'e2e',
    the database reset is skipped to allow preserving state between end-to-end tests.
    """
    if "e2e" in request.keywords:
        yield
    else:
        await reset_database()
        yield


@pytest_asyncio.fixture(scope="session")
async def reset_db_once_for_e2e(request):
    """
    Reset the database once for end-to-end tests.

    This fixture is intended to be used for end-to-end tests at the session scope,
    ensuring the database is reset before running E2E tests.
    """
    await reset_database()

# @pytest_asyncio.fixture
# async def db_session():
#     session = AsyncSessionLocal()
#     await session.begin()
#     # try:
#     yield session
#     # finally:
#     #     await session.rollback()
#     #     await session.close()



# @pytest_asyncio.fixture(autouse=True, scope="session", name="seed_database")
# async def setup_database(request):
#     from src.database import Base
#     # from src.database.populate_db import seed_user_groups, seed_movies, seed_users
#     if "no_seed" in request.keywords:
#         return
#     # Create all tables
#     async with sqlite_engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)

#     # Seed data
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             await seed_user_groups(session)
#             await seed_movies(session, num_movies=50)
#             await seed_users(session)
       
# THIS RUNS ONCE — SEED DATA
# @pytest_asyncio.fixture(autouse=True, scope="session")
# async def seed_once():
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             from src.database.populate_db import seed_user_groups, seed_movies, seed_users
#             await seed_user_groups(session)
#             await seed_movies(session, num_movies=50)
#             await seed_users(session)
#             await session.commit()
            
@pytest_asyncio.fixture(name="seed_database", autouse=True)
async def fixture_seed_database(request, reset_db, db_session):
    if "no_seed" in request.keywords:
        return
    
    # async with AsyncSessionLocal() as session:
    # session_factory = request.getfixturevalue("TestSessionLocal")
    # async with session_factory() as session:
    await seed_user_groups(db_session)
    await seed_movies(db_session, num_movies=50)
    await seed_users(db_session)
    await db_session.commit()

    


@pytest_asyncio.fixture(scope="session")
async def settings():
    """
    Provide application settings.

    This fixture returns the application settings by calling get_settings().
    """
    return get_settings()


@pytest_asyncio.fixture(scope="function")
async def email_sender_stub():
    """
    Provide a stub implementation of the email sender.

    This fixture returns an instance of StubEmailSender for testing purposes.
    """
    return StubEmailSender()


@pytest_asyncio.fixture(scope="function")
async def s3_storage_fake():
    """
    Provide a fake S3 storage client.

    This fixture returns an instance of FakeS3Storage for testing purposes.
    """
    return FakeS3Storage()


@pytest_asyncio.fixture(scope="session")
async def s3_client(settings):
    """
    Provide an S3 storage client.

    This fixture returns an instance of S3StorageClient configured with the application settings.
    """
    return S3StorageClient(
        endpoint_url=settings.S3_STORAGE_ENDPOINT,
        access_key=settings.S3_STORAGE_ACCESS_KEY,
        secret_key=settings.S3_STORAGE_SECRET_KEY,
        bucket_name=settings.S3_BUCKET_NAME,
    )


# @pytest_asyncio.fixture(autouse=True)
# def prevent_loop_closure():
#     # loop = asyncio.get_event_loop()
#     # original_close = loop.close
#     # loop.close = lambda: None  # prevent closure
#     # yield
#     # loop.close = original_close
#     loop = asyncio.get_event_loop()
#     original_close = loop.close
    
#     def fake_close():
#         pass  # do nothing
    
#     loop.close = fake_close
    
#     yield
    
#     # Restore original close (optional)
#     loop.close = original_close
    
@pytest_asyncio.fixture(scope="function")
async def client(email_sender_stub, s3_storage_fake):
    """
    Provide an asynchronous HTTP client for testing.

    Overrides the dependencies for email sender and S3 storage with test doubles.
    """
    app.dependency_overrides[get_accounts_email_notificator] = lambda: email_sender_stub
    app.dependency_overrides[get_s3_storage_client] = lambda: s3_storage_fake

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        async_client._transport._loop = None
        yield async_client
    # with TestClient(app) as client:
    #     yield client
        

    app.dependency_overrides.clear()

# from fastapi.testclient import TestClient
# from src.main import app

# @pytest.fixture(scope="function")
# def client(email_sender_stub, s3_storage_fake):
#     app.dependency_overrides[get_accounts_email_notificator] = lambda: email_sender_stub
#     app.dependency_overrides[get_s3_storage_client] = lambda: s3_storage_fake

#     with TestClient(app) as client:
#         yield client

#     app.dependency_overrides.clear()
    
@pytest_asyncio.fixture(scope="session")
async def e2e_client():
    """
    Provide an asynchronous HTTP client for end-to-end tests.

    This client is available at the session scope.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    Provide an async database session for database interactions.

    This fixture yields an async session using `get_db_contextmanager`, ensuring that the session
    is properly closed after each test.
    """
    async with get_db_contextmanager() as session:
        yield session


@pytest_asyncio.fixture(scope="session")
async def e2e_db_session():
    """
    Provide an async database session for end-to-end tests.

    This fixture yields an async session using `get_db_contextmanager` at the session scope,
    ensuring that the same session is used throughout the E2E test suite.
    Note: Using a session-scoped DB session in async tests may lead to shared state between tests,
    so use this fixture with caution if tests run concurrently.
    """
    async with get_db_contextmanager() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def jwt_manager() -> JWTAuthManagerInterface:
    """
    Asynchronous fixture to create a JWT authentication manager instance.

    This fixture retrieves the application settings via `get_settings()` and uses them to
    instantiate a `JWTAuthManager`. The manager is configured with the secret keys for
    access and refresh tokens, as well as the JWT signing algorithm specified in the settings.

    Returns:
        JWTAuthManagerInterface: An instance of JWTAuthManager configured with the appropriate
        secret keys and algorithm.
    """
    settings = get_settings()
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM,
    )


# @pytest_asyncio.fixture(scope="function")
# async def seed_user_groups(db_session: AsyncSession):
#     """
#     Asynchronously seed the UserGroupModel table with default user groups.

#     This fixture inserts all user groups defined in UserGroupEnum into the database and commits the transaction.
#     It then yields the asynchronous database session for further testing.
#     """
#     groups = [{"name": group.value} for group in UserGroupEnum]
#     await db_session.execute(insert(UserGroupModel).values(groups))
#     await db_session.commit()
#     yield db_session


# @pytest_asyncio.fixture(scope="function")
# async def seed_database(db_session):
#     """
#     Seed the database with test data if it is empty.

#     This fixture initializes a `CSVDatabaseSeeder` and ensures the test database is populated before
#     running tests that require existing data.

#     :param db_session: The async database session fixture.
#     :type db_session: AsyncSession
#     """
#     settings = get_settings()
#     seeder = CSVDatabaseSeeder(csv_file_path=settings.PATH_TO_MOVIES_CSV, db_session=db_session)

#     if not await seeder.is_db_populated():
#         await seeder.seed()

#     yield db_session


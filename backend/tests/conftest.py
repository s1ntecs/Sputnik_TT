import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base, get_session
from src.main import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@backend-db:5433/test_api",
)


async def _ensure_database_exists(url: str) -> None:
    parsed = make_url(url)
    target_db = parsed.database
    admin_url = parsed.set(database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target_db},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{target_db}"'))
    finally:
        await admin_engine.dispose()


@pytest.fixture(scope="session")
async def engine():
    await _ensure_database_exists(TEST_DB_URL)
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE files, alerts RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def stub_celery(monkeypatch):
    from src.scanning import tasks

    monkeypatch.setattr(tasks.scan_file_for_threats, "delay", lambda *a, **kw: None)
    monkeypatch.setattr(tasks.extract_file_metadata, "delay", lambda *a, **kw: None)
    monkeypatch.setattr(tasks.send_file_alert, "delay", lambda *a, **kw: None)


@pytest.fixture
async def client(session) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    from src.core import config

    settings = config.get_settings()
    settings.storage_dir = tmp_path
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr("src.files.storage.get_settings", lambda: settings)
    return tmp_path

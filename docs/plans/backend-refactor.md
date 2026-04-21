# Backend refactor plan

## Цель

Переписать бэкенд из плоского `src/` в feature-based архитектуру, принятую в FastAPI-сообществе для небольших-растущих сервисов; сохранить всю бизнес-логику; починить найденные баги; реализовать одну неочевидную оптимизацию (streaming + non-blocking disk I/O при загрузке); покрыть ключевую логику простыми тестами.

## Ограничения

- Не коммитить. Правки в ветке `main` напрямую.
- Не оставлять легаси-функций в исходниках (старые файлы удаляются после миграции).
- Бизнес-логику не менять. Дедупа, новых фич, хешей содержимого не добавляем.

## Архитектурные решения

- **Feature-based layout** (`files/`, `alerts/`, `scanning/` + `core/`). Каждая фича — самодостаточный пакет: router + schemas + service + models.
- **`pydantic-settings`** для конфигурации — один `Settings`-объект, читается из env.
- **Зависимости FastAPI** для сессии БД (`Depends(get_session)`), объекта файла (`Depends(get_file_or_404)`) — облегчает тесты и убирает ad-hoc `async with async_session_maker()` из бизнес-логики.
- **Чистые функции** для scan/metadata логики; Celery-таски — тонкие обёртки. Это даёт быстрые юнит-тесты без Celery.
- **`lifespan`** вместо сайд-эффектов на импорте (создание storage-директории, инициализация engine).
- **Custom exceptions + handlers** вместо `raise HTTPException` из сервиса — сервис не знает про HTTP.
- **Streaming upload**: `aiofiles` + чанки по 1 МБ, подсчёт `size` на лету. Заменяет блокирующий `write_bytes(await upload_file.read())`.
- **Обновление `processing_status` в скан-таске** — отдельный коммит до выполнения проверок, чтобы клиент видел «processing».

### Что НЕ делаем (сознательно)

- **sha256 / дедуп** — меняет бизнес-логику, не просит ТЗ.
- **pypdf** — поле именуется `approx_page_count`, контракт «приблизительно» намеренный; чиним regex-баг, не меняем подход.
- **Инлайнинг scan-таска в хендлер** (убрать Celery-хоп для сканирования, т.к. оно metadata-only). Технически это дало бы ещё одну оптимизацию, но это архитектурное изменение пайплайна — оставляем как будущее улучшение, упоминаем в README. Сейчас не трогаем.

## Целевая структура

```
backend/
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── files/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── storage.py
│   │   └── dependencies.py
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── service.py
│   └── scanning/
│       ├── __init__.py
│       ├── celery_app.py
│       ├── tasks.py
│       ├── scan.py
│       └── metadata.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_scan.py
│   │   ├── test_metadata.py
│   │   └── test_storage.py
│   └── api/
│       └── test_files.py
└── migrations/
    └── ...                              # env.py обновить под новые импорты
```

## Баги, которые чиним по ходу рефакторинга

1. `tasks.py` читает `REDIS_URL`, в `.env.dev` задан `CELERY_BROKER_URL` — унифицировать через Settings.
2. `create_file` буферизует весь файл в RAM через `upload_file.read()` + блокирующий `write_bytes` — заменить на aiofiles-стриминг.
3. Файл пишется на диск до коммита в БД; при ошибке БД остаётся orphan. Добавить cleanup в try/except.
4. PDF `content.count(b"/Type /Page")` ловит и `/Type /Pages` — regex с правильной границей. Чтение файла **остаётся буферизованным** (как в оригинале), меняется только способ подсчёта.
5. ~~Для text/* `read_text` + `splitlines` — дважды в памяти~~ — **не трогаем**: `splitlines()` имеет свою семантику (считает `hello\nworld\n\nend` как 4 строки из-за непустого хвоста), стриминговая замена через `count("\n")` даст 3 — это изменение бизнес-поведения, запрещено ТЗ. Перенос 1-в-1 в новый модуль.
6. `processing_status = "processing"` в скан-таске не коммитится отдельно — клиент никогда не видит статус.
7. `FileResponse(filename=original_name)` потенциально ломается на кириллице — **перед правкой снять smoke на старом коде**: `curl -OJ http://localhost:8000/files/{id}/download` с файлом `привет.txt`. Если Starlette уже корректно кодирует через RFC 5987 — правка не нужна, оставляем как есть (меньше diff = меньше риска). Регрессионный тест добавляем в любом случае.
8. `FileUpdate.title` без валидации + `Form(...)` в POST без валидации — добавить симметричную валидацию `min_length=1, max_length=255` и на POST, и на PATCH.
9. Глобальный `_worker_loop` в tasks.py — заменить на `asyncio.run()` per task (просто и безопасно).
10. `STORAGE_DIR.mkdir()` и `engine` на импорте — в lifespan.
11. `get_file_path` в service.py не используется, логика продублирована в хендлере — оставляем только в сервисе.
12. Отсутствие индексов на `alerts.file_id`, `files.created_at`, `alerts.created_at` — новая миграция.

---

## Задачи

Каждая задача — минимальный коммитабельный кусок (коммитов не делаем, но гранулярность такая, как если бы делали).

### Задача 1. Обновить зависимости и сборку

**Файлы:**
- `backend/pyproject.toml`
- `backend/uv.lock` (регенерируется)
- `docker-compose.dev.yml`
- `.env.dev`

Добавить runtime-зависимости `aiofiles`, `pydantic-settings`. Ввести dev-группу c `pytest`, `pytest-asyncio`, `httpx`.

```toml
[project]
name = "backend"
version = "0.1.0"
description = "File exchange service"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "aiofiles>=24.1.0",
    "alembic>=1.18.4",
    "asyncpg>=0.30.0",
    "celery[redis]>=5.6.3",
    "fastapi>=0.135.3",
    "pydantic>=2.12.5",
    "pydantic-settings>=2.7.0",
    "python-multipart>=0.0.20",
    "sqlalchemy>=2.0.48",
    "uvicorn>=0.42.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Регенерация lock-файла (локально, до пересборки контейнера):**
```
uv lock
```
Проверить, что `backend/uv.lock` обновился, чтобы `uv sync --locked` в Dockerfile прошёл.

**Дев-контейнер должен иметь dev-зависимости.** В Dockerfile стоит `UV_NO_DEV=1` — это правильно для prod-сборки, но для dev-compose нужно переопределить в рантайме.

В `.env.dev` добавить:
```
UV_NO_DEV=0
```

В `docker-compose.dev.yml` для сервиса `backend` заменить `command`, чтобы перед запуском uvicorn синхронизировались dev-зависимости:

```yaml
backend:
  build: ./backend
  command: sh -c "uv sync --locked && uvicorn src.main:app --host 0.0.0.0 --reload --port 8000"
  ...
```

(Если `UV_NO_DEV=0` как env — `uv sync` подтянет dev-группу.)

**Проверка (в этот момент кода на main.py ещё нет, делаем после Задачи 20 в рамках Задачи 27; шаг верификации для Задачи 1 — только то, что `uv lock` прошёл и `backend/uv.lock` изменился).**

---

### Задача 2. `src/core/config.py` — Settings

**Файл:** `backend/src/core/config.py`

```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.dev", extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_host: str
    pgport: int = Field(alias="PGPORT")
    postgres_db: str

    celery_broker_url: str = "redis://backend-redis:6379/0"

    storage_dir: Path = Path(__file__).resolve().parent.parent.parent / "storage" / "files"
    upload_chunk_size: int = 1024 * 1024  # 1 MB

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.pgport}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Также создать пустые `backend/src/core/__init__.py` и `backend/src/__init__.py` (если нет).

---

### Задача 3. `src/core/database.py` — engine и сессия

**Файл:** `backend/src/core/database.py`

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings

_settings = get_settings()
engine = create_async_engine(_settings.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session
```

`engine` создаётся на импорте модуля — это нормально для async-драйвера (соединения не открываются до первого запроса). Важно только не трогать диск на импорте — диск переедет в lifespan.

---

### Задача 4. `src/core/exceptions.py` — доменные исключения и хендлеры

**Файл:** `backend/src/core/exceptions.py`

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Domain error"


class FileNotFound(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "File not found"


class StoredFileMissing(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Stored file not found"


class EmptyUpload(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "File is empty"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

Сервис бросает эти исключения, а не `HTTPException`. Это развязывает сервис от HTTP.

---

### Задача 5. `src/core/logging.py` — простой logging setup

**Файл:** `backend/src/core/logging.py`

```python
import logging


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```

Минимум. Чтобы `logger = logging.getLogger(__name__)` был виден в stdout Docker.

---

### Задача 6. `src/files/models.py`

**Файл:** `backend/src/files/models.py`

Переносим `StoredFile` как есть. `Base` тоже переносим — один общий в `src/core/database.py` быть не обязан, но так удобнее импортировать в миграции.

Финальный вариант — вынести `Base` в `src/core/database.py`:

```python
# src/core/database.py (дополнение)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

Тогда `src/files/models.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class StoredFile(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    scan_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scan_details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requires_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

Добавили `index=True` на `created_at` (используется в `order_by` в `list_files`).

---

### Задача 7. `src/files/schemas.py`

**Файл:** `backend/src/files/schemas.py`

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_name: str
    mime_type: str
    size: int
    processing_status: str
    scan_status: str | None
    scan_details: str | None
    metadata_json: dict | None
    requires_attention: bool
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
```

Добавлена валидация `title` (баг #8).

---

### Задача 8. `src/files/storage.py` — стриминг-запись на диск

**Файл:** `backend/src/files/storage.py`

Это ядро неочевидной оптимизации: не буферизуем файл в RAM, не блокируем event loop.

```python
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from src.core.config import get_settings
from src.core.exceptions import EmptyUpload


async def stream_to_disk(upload_file: UploadFile) -> tuple[str, str, int]:
    """
    Возвращает (file_id, stored_name, size_bytes). Пишет файл чанками,
    не удерживая его целиком в памяти и не блокируя event loop.
    При пустом файле чистит за собой и бросает EmptyUpload.
    """
    settings = get_settings()
    file_id = str(uuid4())
    suffix = Path(upload_file.filename or "").suffix
    stored_name = f"{file_id}{suffix}"
    stored_path = settings.storage_dir / stored_name

    size = 0
    async with aiofiles.open(stored_path, "wb") as out:
        while chunk := await upload_file.read(settings.upload_chunk_size):
            await out.write(chunk)
            size += len(chunk)

    if size == 0:
        stored_path.unlink(missing_ok=True)
        raise EmptyUpload()

    return file_id, stored_name, size


def delete_stored(stored_name: str) -> None:
    settings = get_settings()
    path = settings.storage_dir / stored_name
    path.unlink(missing_ok=True)
```

`upload_file.read(chunk_size)` уже async — Starlette читает из клиентского сокета чанками. С aiofiles запись — тоже non-blocking. Пик RAM = размер одного чанка (1 МБ), не размер файла.

---

### Задача 9. Тест: storage действительно стримит, а не буферизует

**Файл:** `backend/tests/unit/test_storage.py`

Цель — защитить оптимизацию от регрессии. Стандартный `io.BytesIO` + `UploadFile` пропустит даже старый `await upload_file.read()` + `write_bytes()`, потому что мы проверяем итоговый размер/содержимое. Нужно **трекать вызовы `read(size)`** и ассертить:
- было больше одного вызова `read` (иначе это буферизация),
- ни один вызов не был `read()` или `read(-1)` (иначе читаем всё сразу),
- размер чанка не превосходит `upload_chunk_size`.

```python
import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.exceptions import EmptyUpload
from src.files.storage import stream_to_disk


class _ReadTrackingStream(io.BytesIO):
    """BytesIO, запоминающий каждый вызов read(size)."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_calls: list[int | None] = []

    def read(self, size: int = -1) -> bytes:  # noqa: D401
        self.read_calls.append(size)
        return super().read(size)


def _make_upload(content: bytes, filename: str = "test.txt") -> tuple[UploadFile, _ReadTrackingStream]:
    stream = _ReadTrackingStream(content)
    upload = UploadFile(
        file=stream,
        filename=filename,
        headers=Headers({"content-type": "text/plain"}),
    )
    return upload, stream


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    from src.core.config import Settings

    def _fake_settings():
        s = Settings()
        s.storage_dir = tmp_path
        s.upload_chunk_size = 1024 * 1024
        return s

    monkeypatch.setattr("src.files.storage.get_settings", _fake_settings)
    return tmp_path


async def test_stream_to_disk_writes_file_and_returns_correct_size(isolated_storage):
    data = b"x" * (3 * 1024 * 1024 + 123)  # > chunk_size, чтобы стриминг действительно проявился
    upload, _ = _make_upload(data, "big.bin")

    _, stored_name, size = await stream_to_disk(upload)

    assert size == len(data)
    assert (isolated_storage / stored_name).read_bytes() == data


async def test_stream_to_disk_reads_in_chunks_not_whole_file(isolated_storage):
    chunk_size = 1024 * 1024
    data = b"x" * (chunk_size * 3 + 7)
    upload, stream = _make_upload(data, "big.bin")

    await stream_to_disk(upload)

    # Должно быть >1 вызова read (стриминг)
    assert len(stream.read_calls) > 1, f"expected chunked reads, got {stream.read_calls}"
    # Ни одного read() или read(-1) — иначе это полная буферизация
    assert all(s is not None and s > 0 for s in stream.read_calls), stream.read_calls
    # Ни один чанк не больше лимита
    assert max(stream.read_calls) == chunk_size


async def test_stream_to_disk_empty_file_raises_and_cleans_up(isolated_storage):
    upload, _ = _make_upload(b"", "empty.txt")

    with pytest.raises(EmptyUpload):
        await stream_to_disk(upload)

    assert list(isolated_storage.iterdir()) == []
```

Запуск: `pytest tests/unit/test_storage.py -v`. Все три теста зелёные.

**Почему это ловит регрессию:** если кто-то упростит `stream_to_disk` обратно до `await upload_file.read()` + `out.write(...)` — в `read_calls` окажется один вызов `read(-1)` (или один `read()` без аргумента), и тест `test_stream_to_disk_reads_in_chunks_not_whole_file` упадёт.

---

### Задача 10. `src/files/service.py` — бизнес-логика

**Файл:** `backend/src/files/service.py`

```python
from pathlib import Path

import mimetypes

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import FileNotFound, StoredFileMissing
from src.files.models import StoredFile
from src.files.storage import delete_stored, stream_to_disk


async def list_files(session: AsyncSession) -> list[StoredFile]:
    result = await session.execute(select(StoredFile).order_by(StoredFile.created_at.desc()))
    return list(result.scalars().all())


async def get_file(session: AsyncSession, file_id: str) -> StoredFile:
    file_item = await session.get(StoredFile, file_id)
    if not file_item:
        raise FileNotFound()
    return file_item


async def create_file(session: AsyncSession, title: str, upload_file: UploadFile) -> StoredFile:
    file_id, stored_name, size = await stream_to_disk(upload_file)

    mime_type = (
        upload_file.content_type
        or mimetypes.guess_type(stored_name)[0]
        or "application/octet-stream"
    )
    file_item = StoredFile(
        id=file_id,
        title=title,
        original_name=upload_file.filename or stored_name,
        stored_name=stored_name,
        mime_type=mime_type,
        size=size,
        processing_status="uploaded",
    )
    try:
        session.add(file_item)
        await session.commit()
        await session.refresh(file_item)
    except Exception:
        delete_stored(stored_name)
        raise
    return file_item


async def update_file(session: AsyncSession, file_id: str, title: str) -> StoredFile:
    file_item = await get_file(session, file_id)
    file_item.title = title
    await session.commit()
    await session.refresh(file_item)
    return file_item


async def delete_file(session: AsyncSession, file_id: str) -> None:
    file_item = await get_file(session, file_id)
    delete_stored(file_item.stored_name)
    await session.delete(file_item)
    await session.commit()


async def get_file_with_path(session: AsyncSession, file_id: str) -> tuple[StoredFile, Path]:
    file_item = await get_file(session, file_id)
    stored_path = get_settings().storage_dir / file_item.stored_name
    if not stored_path.exists():
        raise StoredFileMissing()
    return file_item, stored_path
```

Ключевые отличия от старой `service.py`:
- Сессия приходит аргументом (DI), а не через `async with async_session_maker()`.
- Бросает доменные исключения, не `HTTPException`.
- `create_file` чистит файл на диске при провале БД (баг #3).
- Оптимизация: запись стримится через `stream_to_disk`.

---

### Задача 11. `src/files/dependencies.py`

**Файл:** `backend/src/files/dependencies.py`

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.files import service
from src.files.models import StoredFile


async def get_file_or_404(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> StoredFile:
    return await service.get_file(session, file_id)
```

---

### Задача 12. `src/files/router.py`

**Файл:** `backend/src/files/router.py`

```python
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.files import service
from src.files.dependencies import get_file_or_404
from src.files.models import StoredFile
from src.files.schemas import FileItem, FileUpdate
from src.scanning.tasks import scan_file_for_threats

router = APIRouter(prefix="/files", tags=["files"])

TitleForm = Annotated[str, Form(min_length=1, max_length=255)]


@router.get("", response_model=list[FileItem])
async def list_files_view(session: AsyncSession = Depends(get_session)):
    return await service.list_files(session)


@router.post("", response_model=FileItem, status_code=status.HTTP_201_CREATED)
async def create_file_view(
    title: TitleForm,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    file_item = await service.create_file(session, title=title, upload_file=file)
    scan_file_for_threats.delay(file_item.id)
    return file_item


@router.get("/{file_id}", response_model=FileItem)
async def get_file_view(file_item: StoredFile = Depends(get_file_or_404)):
    return file_item


@router.patch("/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    session: AsyncSession = Depends(get_session),
):
    return await service.update_file(session, file_id=file_id, title=payload.title)


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),
):
    file_item, stored_path = await service.get_file_with_path(session, file_id)
    encoded = quote(file_item.original_name)
    return FileResponse(
        path=stored_path,
        media_type=file_item.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"
        },
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_view(
    file_id: str,
    session: AsyncSession = Depends(get_session),
):
    await service.delete_file(session, file_id)
```

`Content-Disposition` с `filename*=UTF-8''...` (RFC 5987) — корректно передаёт не-ASCII имена (баг #7).

---

### Задача 13. `src/alerts/*` — перенос по аналогии

Переносим `Alert` модель, схему, сервис в `backend/src/alerts/`.

**Файлы:**
- `backend/src/alerts/models.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
```

- `backend/src/alerts/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: str
    level: str
    message: str
    created_at: datetime
```

- `backend/src/alerts/service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.models import Alert


async def list_alerts(session: AsyncSession) -> list[Alert]:
    result = await session.execute(select(Alert).order_by(Alert.created_at.desc()))
    return list(result.scalars().all())


async def create_alert(session: AsyncSession, file_id: str, level: str, message: str) -> Alert:
    alert = Alert(file_id=file_id, level=level, message=message)
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert
```

- `backend/src/alerts/router.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts import service
from src.alerts.schemas import AlertItem
from src.core.database import get_session

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertItem])
async def list_alerts_view(session: AsyncSession = Depends(get_session)):
    return await service.list_alerts(session)
```

---

### Задача 14. `src/scanning/scan.py` — чистая функция скана

**Файл:** `backend/src/scanning/scan.py`

```python
from dataclasses import dataclass
from pathlib import Path

SUSPICIOUS_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".sh", ".js"})
MAX_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ScanResult:
    status: str           # "clean" | "suspicious"
    details: str
    requires_attention: bool


def scan(original_name: str, mime_type: str, size: int) -> ScanResult:
    reasons: list[str] = []
    extension = Path(original_name).suffix.lower()

    if extension in SUSPICIOUS_EXTENSIONS:
        reasons.append(f"suspicious extension {extension}")
    if size > MAX_SIZE_BYTES:
        reasons.append("file is larger than 10 MB")
    if extension == ".pdf" and mime_type not in {"application/pdf", "application/octet-stream"}:
        reasons.append("pdf extension does not match mime type")

    if reasons:
        return ScanResult(status="suspicious", details=", ".join(reasons), requires_attention=True)
    return ScanResult(status="clean", details="no threats found", requires_attention=False)
```

Чистая функция, легко тестируется, легко расширяется.

---

### Задача 15. Тест: scan.py

**Файл:** `backend/tests/unit/test_scan.py`

```python
from src.scanning.scan import scan


def test_clean_pdf_with_matching_mime():
    result = scan("doc.pdf", "application/pdf", 1024)
    assert result.status == "clean"
    assert result.requires_attention is False


def test_exe_is_suspicious():
    result = scan("installer.exe", "application/octet-stream", 1024)
    assert result.status == "suspicious"
    assert "suspicious extension .exe" in result.details


def test_oversized_file_is_suspicious():
    result = scan("huge.txt", "text/plain", 11 * 1024 * 1024)
    assert result.status == "suspicious"
    assert "larger than 10 MB" in result.details


def test_pdf_with_wrong_mime_is_suspicious():
    result = scan("doc.pdf", "image/jpeg", 1024)
    assert result.status == "suspicious"
    assert "pdf extension does not match mime type" in result.details


def test_multiple_reasons_combined():
    result = scan("script.sh", "text/plain", 20 * 1024 * 1024)
    assert result.status == "suspicious"
    assert "suspicious extension .sh" in result.details
    assert "larger than 10 MB" in result.details
```

Запуск: `pytest tests/unit/test_scan.py -v`.

---

### Задача 16. `src/scanning/metadata.py` — извлечение метаданных

**Файл:** `backend/src/scanning/metadata.py`

**Что меняем:** только фикс regex-бага подсчёта PDF-страниц.
**Что НЕ меняем:** стратегию чтения — и текстовые файлы, и PDF читаются целиком, как в оригинале. Логика `splitlines()` сохраняется 1-в-1, иначе ломаем бизнес-поведение (см. бага #5 в начале плана). Стриминг тут не делаем — оптимизация сосредоточена в upload-пути.

```python
import re
from pathlib import Path

PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")


def extract(stored_path: Path, original_name: str, mime_type: str, size: int) -> dict:
    metadata: dict = {
        "extension": Path(original_name).suffix.lower(),
        "size_bytes": size,
        "mime_type": mime_type,
    }

    if mime_type.startswith("text/"):
        content = stored_path.read_text(encoding="utf-8", errors="ignore")
        metadata["line_count"] = len(content.splitlines())
        metadata["char_count"] = len(content)
    elif mime_type == "application/pdf":
        metadata["approx_page_count"] = _count_pdf_pages(stored_path)

    return metadata


def _count_pdf_pages(path: Path) -> int:
    data = path.read_bytes()
    count = len(PDF_PAGE_RE.findall(data))
    return max(count, 1)
```

Разница с оригиналом минимальная:
- `content.count(b"/Type /Page")` → `PDF_PAGE_RE.findall(data)` с правильной границей слова — фикс бага #4.
- Всё остальное идентично.

---

### Задача 17. Тест: metadata.py + регрессия PDF /Pages

**Файл:** `backend/tests/unit/test_metadata.py`

```python
from pathlib import Path

from src.scanning.metadata import extract


def test_text_file_line_and_char_count(tmp_path: Path):
    p = tmp_path / "sample.txt"
    p.write_bytes(b"hello\nworld\n\nend")  # splitlines -> ['hello','world','','end'] = 4

    meta = extract(p, "sample.txt", "text/plain", size=p.stat().st_size)

    # Сохраняем поведение оригинала: len(content.splitlines())
    assert meta["line_count"] == 4
    assert meta["char_count"] == 16
    assert meta["extension"] == ".txt"


def test_text_file_trailing_newline_not_counted_as_extra_line(tmp_path: Path):
    # Регрессия на семантику splitlines: "a\nb\n" -> ['a','b'] = 2, не 3
    p = tmp_path / "trail.txt"
    p.write_bytes(b"a\nb\n")

    meta = extract(p, "trail.txt", "text/plain", size=p.stat().st_size)
    assert meta["line_count"] == 2


def test_pdf_page_count_ignores_pages_root(tmp_path: Path):
    # Минимальный синтетический PDF: 1 корневой /Pages, 3 /Page
    p = tmp_path / "doc.pdf"
    p.write_bytes(
        b"%PDF-1.4\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R 4 0 R 5 0 R]>> endobj\n"
        b"3 0 obj <</Type /Page>> endobj\n"
        b"4 0 obj <</Type /Page>> endobj\n"
        b"5 0 obj <</Type /Page>> endobj\n"
    )

    meta = extract(p, "doc.pdf", "application/pdf", size=p.stat().st_size)

    assert meta["approx_page_count"] == 3  # НЕ 4 (как было со старым regex)


def test_pdf_with_no_pages_returns_at_least_one(tmp_path: Path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    meta = extract(p, "broken.pdf", "application/pdf", size=p.stat().st_size)
    assert meta["approx_page_count"] == 1


def test_non_text_non_pdf_has_no_counts(tmp_path: Path):
    p = tmp_path / "img.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0")
    meta = extract(p, "img.jpg", "image/jpeg", size=p.stat().st_size)
    assert "line_count" not in meta
    assert "approx_page_count" not in meta
    assert meta["extension"] == ".jpg"
```

Второй тест — прямая регрессия бага #4.

---

### Задача 18. `src/scanning/celery_app.py`

**Файл:** `backend/src/scanning/celery_app.py`

```python
from celery import Celery

from src.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "file_tasks",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_broker_url,
)
celery_app.autodiscover_tasks(["src.scanning"])
```

Унификация env (баг #1). `docker-compose.dev.yml` уже запускает worker c `-A src.scanning.celery_app` — надо будет обновить команду (Задача 23).

---

### Задача 19. `src/scanning/tasks.py` — Celery-обёртки

**Файл:** `backend/src/scanning/tasks.py`

```python
import asyncio
import logging

from src.alerts.service import create_alert
from src.core.config import get_settings
from src.core.database import async_session_maker
from src.files.models import StoredFile
from src.scanning.celery_app import celery_app
from src.scanning.metadata import extract
from src.scanning.scan import scan

logger = logging.getLogger(__name__)


@celery_app.task(name="scan_file_for_threats")
def scan_file_for_threats(file_id: str) -> None:
    asyncio.run(_scan_file_for_threats(file_id))


@celery_app.task(name="extract_file_metadata")
def extract_file_metadata(file_id: str) -> None:
    asyncio.run(_extract_file_metadata(file_id))


@celery_app.task(name="send_file_alert")
def send_file_alert(file_id: str) -> None:
    asyncio.run(_send_file_alert(file_id))


async def _scan_file_for_threats(file_id: str) -> None:
    async with async_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            logger.warning("scan: file %s not found", file_id)
            return

        file_item.processing_status = "processing"
        await session.commit()  # баг #6: клиент должен видеть "processing"

        result = scan(file_item.original_name, file_item.mime_type, file_item.size)
        file_item.scan_status = result.status
        file_item.scan_details = result.details
        file_item.requires_attention = result.requires_attention
        await session.commit()

    extract_file_metadata.delay(file_id)


async def _extract_file_metadata(file_id: str) -> None:
    async with async_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            logger.warning("metadata: file %s not found", file_id)
            return

        stored_path = get_settings().storage_dir / file_item.stored_name
        if not stored_path.exists():
            file_item.processing_status = "failed"
            file_item.scan_status = file_item.scan_status or "failed"
            file_item.scan_details = "stored file not found during metadata extraction"
            await session.commit()
            send_file_alert.delay(file_id)
            return

        file_item.metadata_json = extract(
            stored_path,
            file_item.original_name,
            file_item.mime_type,
            file_item.size,
        )
        file_item.processing_status = "processed"
        await session.commit()

    send_file_alert.delay(file_id)


async def _send_file_alert(file_id: str) -> None:
    async with async_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return

        if file_item.processing_status == "failed":
            level, message = "critical", "File processing failed"
        elif file_item.requires_attention:
            level, message = "warning", f"File requires attention: {file_item.scan_details}"
        else:
            level, message = "info", "File processed successfully"

        await create_alert(session, file_id=file_id, level=level, message=message)
```

Ключевые изменения vs старого `tasks.py`:
- Заменён глобальный `_worker_loop` на `asyncio.run()` (баг #9). Каждая таска — свежий event loop. Надёжно, Celery worker с `prefork` пулом не ловит leaks.
- `processing_status = "processing"` коммитится отдельно (баг #6).
- Используются чистые функции `scan()` / `extract()` — тестируются отдельно от Celery.

---

### Задача 20. `src/main.py` — сборка приложения

**Файл:** `backend/src/main.py`

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.alerts.router import router as alerts_router
from src.core.config import get_settings
from src.core.exceptions import register_exception_handlers
from src.core.logging import setup_logging
from src.files.router import router as files_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(files_router)
    app.include_router(alerts_router)
    return app


app = create_app()
```

`mkdir` переехал в lifespan (баг #10).

---

### Задача 21. Удалить старые файлы

Удалить:
- `backend/src/app.py`
- `backend/src/models.py`
- `backend/src/schemas.py`
- `backend/src/service.py`
- `backend/src/tasks.py`

Проверка: `grep -r "from src.service" backend/` → пусто; `from src.models` → пусто; и т.д.

---

### Задача 22. Обновить `migrations/env.py`

**Файл:** `backend/migrations/env.py`

```python
# было:
# from src.service import DB_URL
# from src.models import Base
# import src.models

# стало:
from src.alerts.models import Alert  # noqa: F401 — для autogenerate
from src.core.config import get_settings
from src.core.database import Base
from src.files.models import StoredFile  # noqa: F401

config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

Импорты моделей нужны чтобы Alembic увидел их в `Base.metadata`.

---

### Задача 23. Миграция: индексы

Новая миграция для добавленных `index=True`:

```
docker exec -it backend alembic revision --autogenerate -m "indexes"
docker exec -it backend alembic upgrade head
```

Проверить, что `op.create_index` создаётся для `files.created_at`, `alerts.file_id`, `alerts.created_at`.

---

### Задача 24. Обновить `docker-compose.dev.yml`

Команда worker указывает на `src.tasks.celery_app` — поменять на `src.scanning.celery_app`:

```yaml
backend-worker:
  command: [ 'celery', '-A', 'src.scanning.celery_app', 'worker', '-l', 'info' ]
```

Команда backend — `uvicorn src.app:app` → `uvicorn src.main:app`:

```yaml
backend:
  command: uvicorn src.main:app --host 0.0.0.0 --reload --port 8000
```

---

### Задача 25. `tests/conftest.py` — фикстуры

**Файл:** `backend/tests/conftest.py`

Для API-тестов нужен реальный Postgres. Подключаемся к существующему из docker-compose, к отдельной БД `test_api`. Перед сессией — создаём схему. Между тестами — `TRUNCATE ... RESTART IDENTITY CASCADE` (rollback не годится, потому что сам код в `service.py` вызывает `session.commit()`, и откат транзакции теста его не достанет). Плюс autouse-фикстура подменяет `scan_file_for_threats.delay` на no-op, чтобы тесты не ломились в Redis.

```python
import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base, get_session
from src.main import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@backend-db:5433/test_api",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
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
    # Жёсткая изоляция: чистим все таблицы после теста.
    # Endpoints вызывают commit(), поэтому rollback() в тесте не помог бы.
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE files, alerts RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def stub_celery(monkeypatch):
    """API-тесты не должны зависеть от Redis/Celery: подменяем .delay на no-op."""
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
    """Подменяет storage-директорию на tmp_path во всех местах, где она читается."""
    from src.core import config

    original = config.get_settings()
    original.storage_dir = tmp_path
    monkeypatch.setattr(config, "get_settings", lambda: original)
    return tmp_path
```

**Важно:** перед запуском нужно создать БД `test_api` в Postgres. Команда в Задаче 27.

---

### Задача 26. API-тесты

**Файл:** `backend/tests/api/test_files.py`

```python
from io import BytesIO


async def test_create_and_list_file(client):
    resp = await client.post(
        "/files",
        data={"title": "hello"},
        files={"file": ("hello.txt", BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "hello"
    assert body["size"] == 2
    assert body["processing_status"] == "uploaded"

    listing = await client.get("/files")
    assert listing.status_code == 200
    assert any(item["id"] == body["id"] for item in listing.json())


async def test_empty_file_rejected(client):
    resp = await client.post(
        "/files",
        data={"title": "empty"},
        files={"file": ("empty.txt", BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File is empty"


async def test_update_file_title(client):
    up = await client.post(
        "/files",
        data={"title": "old"},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.patch(f"/files/{file_id}", json={"title": "new"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "new"


async def test_update_rejects_empty_title(client):
    up = await client.post(
        "/files",
        data={"title": "t"},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.patch(f"/files/{file_id}", json={"title": ""})
    assert resp.status_code == 422  # pydantic validation


async def test_create_rejects_empty_title_symmetric_with_patch(client):
    resp = await client.post(
        "/files",
        data={"title": ""},
        files={"file": ("a.txt", BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 422


async def test_download_cyrillic_filename_header(client):
    up = await client.post(
        "/files",
        data={"title": "кириллица"},
        files={"file": ("привет.txt", BytesIO(b"hi"), "text/plain")},
    )
    file_id = up.json()["id"]

    resp = await client.get(f"/files/{file_id}/download")
    assert resp.status_code == 200

    # RFC 5987: должен присутствовать filename*=UTF-8'' с percent-encoded именем
    cd = resp.headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in cd
    # %D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82 = "привет"
    assert "%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82" in cd
```

**Автоиспользуемый `stub_celery` в conftest гарантирует, что `scan_file_for_threats.delay(...)` из хендлера — no-op, живой Redis/Celery для API-тестов не нужен.**

---

### Задача 26.1. Тест: cleanup файла при провале БД

**Файл:** `backend/tests/unit/test_service_cleanup.py`

Регрессия на баг #3 (оркестрировать stream-на-диск и коммит так, чтобы при исключении коммита файл удалялся).

```python
import io
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.files import service


@pytest.fixture
def fake_upload():
    return UploadFile(
        file=io.BytesIO(b"content"),
        filename="a.txt",
        headers=Headers({"content-type": "text/plain"}),
    )


async def test_create_file_removes_stored_file_when_commit_fails(
    isolated_storage,
    fake_upload,
):
    failing_session = AsyncMock()
    failing_session.add = lambda _obj: None
    failing_session.commit.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await service.create_file(failing_session, title="x", upload_file=fake_upload)

    # Файл не должен остаться на диске
    assert list(isolated_storage.iterdir()) == []
```

Использует фикстуру `isolated_storage` из conftest. Цель — зафиксировать контракт «при провале БД — диск чистим».

---

### Задача 27. Прогон тестов и smoke

1. **Рестарт с обновлением зависимостей.** Контейнер backend в dev-compose теперь стартует через `sh -c "uv sync --locked && uvicorn ..."` — при `up --build` dev-зависимости (pytest/httpx) уже будут в контейнере.
   ```
   docker compose -f docker-compose.dev.yml up --build
   ```
   Ожидаем: в логах `backend` виден успешный `uv sync`, затем uvicorn стартует.

2. **Применить миграции:**
   ```
   docker exec -it backend alembic upgrade head
   ```

3. **Создать тестовую БД:**
   ```
   docker exec -it backend-db psql -U postgres -c "CREATE DATABASE test_api;"
   ```
   Таблицы в `test_api` создадутся автоматически фикстурой `engine` (через `Base.metadata.create_all`).

4. **Перед ручной правкой download-заголовка — baseline smoke:** залить файл с кириллическим именем на **старом** коде (если он ещё доступен) и посмотреть, ломается ли заголовок:
   ```
   curl -F "title=t" -F "file=@привет.txt" http://localhost:8000/files
   curl -i http://localhost:8000/files/<id>/download | head -20
   ```
   Это помогает решить — достаточно ли собственной логики Starlette или нужна явная RFC 5987 кодировка (сейчас в плане — явная).

5. **Юнит-тесты:**
   ```
   docker exec -it backend pytest tests/unit -v
   ```
   Ожидаем: все зелёные. Если какой-то падает — разбираем до перехода к API.

6. **API-тесты:**
   ```
   docker exec -it backend pytest tests/api -v
   ```
   Ожидаем: все зелёные. Redis не требуется — Celery замокан в conftest.

7. **Smoke (интеграционный):** `curl http://localhost:8000/docs` → UI открывается; `POST /files` с реальным файлом → запись появляется в `/files`, через 1–3 сек `processing_status` становится `processed`, в `/alerts` появляется запись info-уровня. Проверить и подозрительный файл (`.exe`) — должен вернуть `requires_attention=true` и alert level=warning.

---

## Порядок выполнения и проверки

Предлагаю группировать задачи так (каждая группа — мини-веха, можно остановиться и проверить):

1. **Core** (1–5): зависимости, lock, dev-сборка, settings, database, exceptions, logging.
2. **Files** (6–12) + юнит-тест storage (9) с проверкой чанковых read().
3. **Alerts** (13).
4. **Scanning** (14–19) + юнит-тесты scan/metadata (15, 17) с регрессиями PDF `/Pages` и splitlines-семантики.
5. **Сборка** (20–24): main.py, удаление старого, миграция, docker-compose.
6. **Тесты** (25, 26, 26.1) + **smoke** (27): conftest с truncate + autouse-заглушкой Celery, API-тесты (пустой/полный title, кириллица в download), юнит-тест cleanup при провале БД.

После группы 5 приложение должно стартовать и работать эквивалентно старому (с исправленными багами и стримингом). Группа 6 — финальная валидация.

## Что будет в README после рефакторинга

Короткая секция:
- Новая структура.
- Какие баги починены (перечень).
- Неочевидная оптимизация: streaming upload + non-blocking I/O — описать в 2 абзаца.
- Замечание: scan-таск можно было бы инлайнить в handler (metadata-only), но это архитектурное изменение пайплайна — оставлено как возможное будущее улучшение.
- Как запускать тесты.

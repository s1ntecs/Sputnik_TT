## Тестовое задание на позицию Fullstack разработчика (Python + React)

**Вводные:**
1. Здесь представлен MVP проект файлообменника. Он позволяет загружать файлы, проверяет их на подозрительный контент и отправляет алерты;
2. Репозиторий содержит в себе бэкенд и фронтенд части;
3. В обоих частях присутствуют баги, неоптимизированный код, неудачные архитектурные решения.

**Задачи:**
1. Проведите рефакторинг бэкенда, не ломая бизнес-логики: предложите свое видение архитектуры и реализуйте его;
2. (Дополнительно) На бэкенде есть возможность неочевидной оптимизации - выполните ее;
3. (Дополнительно) Разбейте логику фронтенда на слои;

**Запуск:**
1. ```docker compose -f docker-compose.dev.yml up```
2. ```docker exec -it backend alembic upgrade head```


**Открыть фронт:** ```http://localhost:3000/test``` 

**Открыть бэк:** ```http://localhost:8000/docs```

---

## Что сделано

Поведение API и UI не менялось - только внутреннее устройство. Ниже от самого заметного к деталям.

### Найденные баги

- **Celery-воркер жил на самодельном event-loop** (`run_in_worker_loop` в `tasks.py`): один общий loop на все таски, переиспользование после закрытия. Заменено на `asyncio.run(...)` со свежим engine на задачу — изолированные loop и соединения, без гонок.
- **иконка ссылалась на `/public/favicon.ico`** в `layout.tsx`. `/public/`.
- **Разделяемый `engine`/`sessionmaker`** между веб-приложением и воркером через общий модуль при том, что у них разные жизненные циклы. Развели: воркер держит свой engine, API - свой, создаваемый из `Depends(get_session)`.

### Backend - архитектура

```
src/
  core/        # config, database, exception handlers, logging
  files/       # router, service, models, schemas, storage, dependencies
  alerts/      # router, service, models, schemas
  scanning/    # celery_app, tasks, scan.py, metadata.py
  main.py      # create_app() + lifespan + CORS + регистрация роутеров
```

Дополнительно:
- `get_session` как FastAPI-зависимость вместо `async with session_maker()` в каждом сервисе - упрощает транзакции и тесты.
- Сканирование разделено: `scanning/scan.py` (правила), `scanning/metadata.py` (извлечение), `scanning/tasks.py` (celery-обёртка).

### Добавленные зависимости

- **`aiofiles`** - в `files/storage.py` запись аплоада идёт async-ом (`await aiofiles.open(...).write(...)`). Раньше был блокирующий.
- **`pydantic-settings`** - один типизированный `Settings` в `core/config.py`.
- **dev:** `pytest` + `pytest-asyncio` + `httpx` — под них написаны тесты на `scanning/scan`, `scanning/metadata`, `files/storage`, `/files`.

### Backend - оптимизация (доп. задача)

Списки `/files` и `/alerts` всегда сортируются по `created_at DESC`, `/alerts` часто фильтруется по `file_id`. Добавлены индексы:

- `ix_files_created_at`
- `ix_alerts_created_at`
- `ix_alerts_file_id`

Добавил 

### Frontend

Была одна `page.tsx` на ~320 строк, теперь разделил на компоненты.:

```
src/
  lib/         # чистые функции: formatDate, formatSize, getLevelVariant, getProcessingVariant
  api/         # client.ts (apiFetch + API_BASE_URL), files.ts, alerts.ts - DTO + fetch-обёртки
  hooks/       # useDashboardData (files+alerts), useFileUpload - вся state-логика страницы
  components/  # PageHeader, FilesTable, AlertsTable, UploadModal - презентационные, без fetch
  app/page.tsx # тонкая композиция + единый errorMessage
```

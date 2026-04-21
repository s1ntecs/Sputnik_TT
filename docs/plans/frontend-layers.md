# Frontend layering plan

> **Для агентов:** используйте суб-скилл `superpowers:subagent-driven-development` или `superpowers:executing-plans` для пошагового выполнения. Чекбоксы (`- [ ]`) — для трекинга.

**Цель:** Разбить фронтенд (`frontend/src/app/page.tsx`, 367 строк) на явные слои. Сохранить 100% текущего поведения и разметки. Страница становится тонкой композицией.

**Архитектура:** Слои `api/` (доступ к данным) → `hooks/` (состояние и оркестрация) → `components/` (презентация) → `lib/` (чистые утилиты). `app/page.tsx` — только композиция.

**Tech Stack:** Next.js 16.1.6 (App Router), React 18.3.1, react-bootstrap, TypeScript.

---

## Ограничения

- **Поведение и разметку не менять.** Включая: порядок и связность loading-состояний таблиц, порядок сброса ошибок, тексты ошибок, поведение модалки при закрытии/открытии.
- **Контракт с бэком не менять** (URL, методы, схемы JSON).
- Не добавлять то, чего нет в ТЗ: env-конфиг URL, тесты, deduping, loading skeletons, авто-рефреш.
- Не коммитить (правки в `main` напрямую — повторяем подход бекенд-рефакторинга).
- Бизнес-логику не трогаем — рефакторинг структурный.

## Архитектурные решения

- **4 слоя:**
  - `api/` — доступ к сети (`apiFetch` + функции вида `listFiles`, `uploadFile`). Здесь же типы DTO, потому что они 1-в-1 с контрактом бэка — живут с API.
  - `hooks/` — пользовательские хуки с состоянием и жизненным циклом (`useDashboardData`, `useFileUpload`). Хуки — клей между api и UI.
  - `components/` — «dumb» презентация (`FilesTable`, `AlertsTable`, `UploadModal`, `PageHeader`). Получают пропсы, не знают про fetch, не держат бизнес-состояния.
  - `lib/` — чистые функции без сайд-эффектов (`format.ts`, `status.ts`).
- **`page.tsx` как композитор.** Страница только собирает хуки и прокидывает их данные в компоненты. Плюс держит **один** `errorMessage` (см. ниже).
- **Один хук для дэшборда — `useDashboardData`.** Сейчас `loadData()` загружает files и alerts одним `Promise.all`; при фейле ЛЮБОГО из них setState обоих массивов **не происходит** (throw до `setFiles/setAlerts`), и `isLoading` — один на обе таблицы. Разделять на `useFiles`+`useAlerts` — это семантическая регрессия (частичные апдейты, два независимых спиннера). Поэтому один хук: `Promise.all → throw-or-set-both`, один `isLoading`.
- **Единый `errorMessage` в `page.tsx`.** Оригинал сбрасывает `errorMessage` в начале каждого действия (`loadData`, `handleSubmit`) и пишет туда и сетевые, и валидационные ошибки — одно активное сообщение в любой момент. Если держать `error` внутри каждого хука — ошибки «живут» параллельно, приоритизировать их нельзя без регрессии. Поэтому: хуки **не держат свой `error` state** и принимают колбэки `onStart`/`onError`/`onSuccess`. Page передаёт им `() => setErrorMessage(null)` и `(msg) => setErrorMessage(msg)`. Семантика «одно сообщение, сбрасывается перед действием» сохраняется.
- **Тексты ошибок фиксированы в хуках.** `apiFetch` бросает исключение с техническим сообщением, хук его ловит и передаёт в `onError` **фиксированную строку**, как в оригинале: «Не удалось загрузить данные» / «Не удалось загрузить файл» / «Укажите название и выберите файл».
- **URL бэка — константа в одном месте** (`api/client.ts`). Сейчас `http://localhost:8000` фигурирует в 3 местах литералом. Консолидация — прямое следствие слоя API, не выход за ТЗ.
- **Хук-форма.** `useFileUpload` держит `title`, `selectedFile`, `isSubmitting`, метод `submit()` и `reset()`. Сброс формы — **только внутри `submit()` после успеха** (как в оригинале). При открытии/закрытии модалки ничего не сбрасывается.
- **`"use client"` только в `page.tsx`.** Остальные файлы в `hooks/` и `components/` импортируются исключительно из `page.tsx` (уже client boundary). По документации Next.js, дочерние модули наследуют клиентскую среду через импорт из client boundary. Отдельная директива на каждом файле лишняя и расширяет client boundary без причины. См. https://nextjs.org/docs/app/api-reference/directives/use-client.

### Что НЕ делаем (сознательно)

- **Тесты.** ТЗ не просит; добавление vitest/jest — инфраструктурная работа вне скоупа.
- **Env-var для API URL.** Значение в одной константе — уже достаточно. `NEXT_PUBLIC_API_URL` — отдельная DevOps-задача.
- **React Query / SWR.** Данные обновляются явно по клику «Обновить» и после загрузки — нативных `useState/useEffect` хватает. TanStack Query — overkill и меняет поведение (фоновый рефетч).
- **Формат валидации.** Сейчас `if (!title.trim() || !selectedFile)` — оставляем.
- **Feature-Sliced Design** (`entities/features/widgets`). Для 1 страницы и 2 ресурсов — лишний оверхед.
- **Дедуп/подсветку частичных фейлов.** `useDashboardData` падает целиком ради эквивалентности оригиналу.

## Целевая структура

```
frontend/src/
├── app/
│   ├── layout.tsx                 # без изменений (см. Задачу 16 как опцию)
│   └── page.tsx                   # тонкая композиция
├── api/
│   ├── client.ts                  # API_BASE_URL, apiFetch<T>()
│   ├── files.ts                   # FileItem, listFiles, uploadFile, getDownloadUrl
│   └── alerts.ts                  # AlertItem, listAlerts
├── hooks/
│   ├── useDashboardData.ts        # files + alerts + isLoading (один Promise.all)
│   └── useFileUpload.ts
├── components/
│   ├── PageHeader.tsx
│   ├── FilesTable.tsx
│   ├── AlertsTable.tsx
│   └── UploadModal.tsx
└── lib/
    ├── format.ts                  # formatDate, formatSize
    └── status.ts                  # getLevelVariant, getProcessingVariant
```

## Порядок рефакторинга

Принцип: **двигаться листьями внутрь**. Сначала выносим то, что не зависит ни от чего (чистые утилиты), затем — слои всё выше к странице.

1. `lib/` — чистые утилиты.
2. `api/` — типы и функции доступа.
3. `hooks/` — состояние и оркестрация.
4. `components/` — презентационные.
5. `app/page.tsx` — сжать до композиции.
6. Smoke-верификация.
7. (Опционально) фикс favicon.

---

## Задачи

### Задача 1. `lib/format.ts` — форматтеры

**Файлы:**
- Создать: `frontend/src/lib/format.ts`
- Изменить: `frontend/src/app/page.tsx`

- [ ] **Шаг 1: Создать `frontend/src/lib/format.ts`** с переносом функций 1-в-1 из `page.tsx:42-59`.

```ts
export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
```

- [ ] **Шаг 2: Заменить инлайн-функции в `page.tsx` на импорт.**

В `page.tsx` удалить блок `function formatDate(...)` и `function formatSize(...)` (строки 42–59). Добавить:

```ts
import { formatDate, formatSize } from "../lib/format";
```

(`tsconfig.json` не содержит `baseUrl` — используем относительные пути. `page.tsx` лежит в `src/app/`, `lib/format.ts` — в `src/lib/`, итог `../lib/format`.)

- [ ] **Шаг 3: Собрать проект.**

Локально: `cd frontend && npm run build`. Или: `docker compose -f docker-compose.dev.yml up frontend`.
Ожидаемо: сборка успешна, TS-ошибок нет.

---

### Задача 2. `lib/status.ts` — маппинг статусов на badge-варианты

**Файлы:**
- Создать: `frontend/src/lib/status.ts`
- Изменить: `frontend/src/app/page.tsx`

- [ ] **Шаг 1: Создать `frontend/src/lib/status.ts`** с переносом из `page.tsx:61-87`.

```ts
export function getLevelVariant(level: string): string {
  if (level === "critical") {
    return "danger";
  }

  if (level === "warning") {
    return "warning";
  }

  return "success";
}

export function getProcessingVariant(status: string): string {
  if (status === "failed") {
    return "danger";
  }

  if (status === "processing") {
    return "warning";
  }

  if (status === "processed") {
    return "success";
  }

  return "secondary";
}
```

- [ ] **Шаг 2: Заменить инлайн-функции в `page.tsx` на импорт.**

Удалить блоки `function getLevelVariant` и `function getProcessingVariant`. Добавить:

```ts
import { getLevelVariant, getProcessingVariant } from "../lib/status";
```

- [ ] **Шаг 3: Собрать. Сборка должна пройти.**

---

### Задача 3. `api/client.ts` — базовый URL и fetcher

**Файлы:**
- Создать: `frontend/src/api/client.ts`

- [ ] **Шаг 1: Создать `frontend/src/api/client.ts`.**

```ts
export const API_BASE_URL = "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}
```

Важно:
- `apiFetch` — **технический слой**. Текст исключения не предназначен для UI; хуки ловят и подменяют на фиксированные пользовательские сообщения (см. Задачи 6–7).
- `cache: "no-store"` по умолчанию — повторяет поведение `page.tsx`.
- Upload идёт через `fetch` напрямую в `api/files.ts` — тело `FormData`, блок специфичен, не переусложняем сигнатуру.

- [ ] **Шаг 2: Собрать.**

---

### Задача 4. `api/files.ts` — DTO и функции файлов

**Файлы:**
- Создать: `frontend/src/api/files.ts`

- [ ] **Шаг 1: Создать `frontend/src/api/files.ts`.**

```ts
import { API_BASE_URL, apiFetch } from "./client";

export type FileItem = {
  id: string;
  title: string;
  original_name: string;
  mime_type: string;
  size: number;
  processing_status: string;
  scan_status: string | null;
  scan_details: string | null;
  metadata_json: Record<string, unknown> | null;
  requires_attention: boolean;
  created_at: string;
  updated_at: string;
};

export function listFiles(): Promise<FileItem[]> {
  return apiFetch<FileItem[]>("/files");
}

export async function uploadFile(params: { title: string; file: File }): Promise<FileItem> {
  const formData = new FormData();
  formData.append("title", params.title);
  formData.append("file", params.file);

  const response = await fetch(`${API_BASE_URL}/files`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("upload_failed");
  }

  return (await response.json()) as FileItem;
}

export function getDownloadUrl(fileId: string): string {
  return `${API_BASE_URL}/files/${fileId}/download`;
}
```

Заметки:
- В `uploadFile` бросаем технический маркер `"upload_failed"` — хук подставит пользовательский текст.
- `listFiles` пробрасывает исключение вверх без своей обёртки.

- [ ] **Шаг 2: Собрать.**

---

### Задача 5. `api/alerts.ts` — DTO и функция алертов

**Файлы:**
- Создать: `frontend/src/api/alerts.ts`

- [ ] **Шаг 1: Создать `frontend/src/api/alerts.ts`.**

```ts
import { apiFetch } from "./client";

export type AlertItem = {
  id: number;
  file_id: string;
  level: string;
  message: string;
  created_at: string;
};

export function listAlerts(): Promise<AlertItem[]> {
  return apiFetch<AlertItem[]>("/alerts");
}
```

- [ ] **Шаг 2: Собрать.**

---

### Задача 6. `hooks/useDashboardData.ts` — files + alerts одним Promise.all

**Файлы:**
- Создать: `frontend/src/hooks/useDashboardData.ts`

**Дизайн хука:** строгое эквивалентие `loadData()` из оригинала.
- Один `Promise.all([listFiles(), listAlerts()])`.
- При фейле ЛЮБОГО запроса — throw до setState, ни `files`, ни `alerts` не обновляются (как в оригинале через `if (!filesResponse.ok || !alertsResponse.ok) throw`).
- Один `isLoading` на оба массива.
- **Не держит свой `error`.** Принимает `onStart` (для сброса ошибки) и `onError` (для публикации). Вызывающий (page) управляет единым errorMessage.

- [ ] **Шаг 1: Создать `frontend/src/hooks/useDashboardData.ts`.**

```ts
import { useCallback, useEffect, useState } from "react";

import { AlertItem, listAlerts } from "../api/alerts";
import { FileItem, listFiles } from "../api/files";

type UseDashboardDataOptions = {
  onStart?: () => void;
  onError?: (message: string) => void;
};

type UseDashboardDataResult = {
  files: FileItem[];
  alerts: AlertItem[];
  isLoading: boolean;
  reload: () => Promise<void>;
};

export function useDashboardData(options: UseDashboardDataOptions = {}): UseDashboardDataResult {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const { onStart, onError } = options;

  const reload = useCallback(async () => {
    setIsLoading(true);
    onStart?.();

    try {
      const [filesData, alertsData] = await Promise.all([listFiles(), listAlerts()]);
      setFiles(filesData);
      setAlerts(alertsData);
    } catch {
      onError?.("Не удалось загрузить данные");
    } finally {
      setIsLoading(false);
    }
  }, [onStart, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { files, alerts, isLoading, reload };
}
```

Заметки:
- Текст ошибки зафиксирован — «Не удалось загрузить данные» (как `page.tsx:111`).
- При фейле `setFiles`/`setAlerts` не вызываются; предыдущие значения сохраняются (или пустые массивы на первом запуске) — эквивалентно оригиналу.
- Колбэки стабилизируются за счёт деструктуризации в `options` и включения в deps `reload`. Вызывающий должен передать их в стабильном виде (через `useCallback` или ссылаться на `setState`, которая стабильна — см. Задачу 13).

- [ ] **Шаг 2: Собрать.**

---

### Задача 7. `hooks/useFileUpload.ts` — состояние и сабмит формы

**Файлы:**
- Создать: `frontend/src/hooks/useFileUpload.ts`

**Дизайн:** эквивалент `handleSubmit` из `page.tsx:131-165`.
- Валидация: пустой title или отсутствие файла → передаёт в `onError("Укажите название и выберите файл")` и return.
- Сетевой фейл → `onError("Не удалось загрузить файл")`.
- Успех → `reset()` (очищает title и selectedFile) + `onSuccess()`.
- `onStart` вызывается перед реальной отправкой (после прохождения валидации) — как в оригинале `setErrorMessage(null)` до POST.
- **Важно:** в оригинале `setErrorMessage(null)` вызывается сразу после валидации перед `setIsSubmitting(true)` — т.е. даже валидационная ошибка сбрасывается перед сабмитом. Но если валидация фейлится, она сама себя проставляет. Порядок: (1) валидация → если не прошла, `onError(validation_msg)` и return; (2) если прошла, `onStart` (сбросить) + `setIsSubmitting(true)` + запрос.

- [ ] **Шаг 1: Создать `frontend/src/hooks/useFileUpload.ts`.**

```ts
import { useCallback, useState } from "react";

import { uploadFile } from "../api/files";

type UseFileUploadOptions = {
  onStart?: () => void;
  onError?: (message: string) => void;
  onSuccess?: () => void | Promise<void>;
};

type UseFileUploadResult = {
  title: string;
  setTitle: (value: string) => void;
  selectedFile: File | null;
  setSelectedFile: (file: File | null) => void;
  isSubmitting: boolean;
  submit: () => Promise<void>;
};

export function useFileUpload(options: UseFileUploadOptions = {}): UseFileUploadResult {
  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { onStart, onError, onSuccess } = options;

  const submit = useCallback(async () => {
    if (!title.trim() || !selectedFile) {
      onError?.("Укажите название и выберите файл");
      return;
    }

    setIsSubmitting(true);
    onStart?.();

    try {
      await uploadFile({ title: title.trim(), file: selectedFile });
      setTitle("");
      setSelectedFile(null);
      await onSuccess?.();
    } catch {
      onError?.("Не удалось загрузить файл");
    } finally {
      setIsSubmitting(false);
    }
  }, [title, selectedFile, onStart, onError, onSuccess]);

  return {
    title,
    setTitle,
    selectedFile,
    setSelectedFile,
    isSubmitting,
    submit,
  };
}
```

Заметки:
- `reset()` **не экспонируется и не вызывается извне**. Сброс формы — только после успеха (как в оригинале `setTitle(""); setSelectedFile(null);` после `response.ok`). Это сохраняет поведение закрытия модалки: ввёл → закрыл крестиком → открыл снова → поля остались.
- Тексты ошибок — фиксированные, 1-в-1 с `page.tsx:135`, `page.tsx:153`.
- В оригинале `setErrorMessage(null)` вызывается сразу после валидации и до `setIsSubmitting(true)`. Здесь порядок: `setIsSubmitting(true)` → `onStart()`. Визуально это неразличимо (оба до начала await). Но для строгости можно поменять местами — ставить `onStart()` до `setIsSubmitting`. Без разницы для UX, оставляем как выше.

- [ ] **Шаг 2: Собрать.**

---

### Задача 8. `components/PageHeader.tsx`

**Файлы:**
- Создать: `frontend/src/components/PageHeader.tsx`

**Правило:** без `"use client"`. Файл импортируется только из `page.tsx` (уже client boundary) — наследует клиентскую среду через импорт.

- [ ] **Шаг 1: Создать `frontend/src/components/PageHeader.tsx`.** Разметка идентична `page.tsx:171-190`.

```tsx
import { Button, Card } from "react-bootstrap";

type PageHeaderProps = {
  onReload: () => void;
  onAddFile: () => void;
};

export function PageHeader({ onReload, onAddFile }: PageHeaderProps) {
  return (
    <Card className="shadow-sm border-0 mb-4">
      <Card.Body className="p-4">
        <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
          <div>
            <h1 className="h3 mb-2">Управление файлами</h1>
            <p className="text-secondary mb-0">
              Загрузка файлов, просмотр статусов обработки и ленты алертов.
            </p>
          </div>
          <div className="d-flex gap-2">
            <Button variant="outline-secondary" onClick={onReload}>
              Обновить
            </Button>
            <Button variant="primary" onClick={onAddFile}>
              Добавить файл
            </Button>
          </div>
        </div>
      </Card.Body>
    </Card>
  );
}
```

- [ ] **Шаг 2: Собрать.**

---

### Задача 9. `components/FilesTable.tsx`

**Файлы:**
- Создать: `frontend/src/components/FilesTable.tsx`

- [ ] **Шаг 1: Создать файл.** Разметка идентична `page.tsx:198-276`.

```tsx
import { Badge, Button, Card, Spinner, Table } from "react-bootstrap";

import { FileItem, getDownloadUrl } from "../api/files";
import { formatDate, formatSize } from "../lib/format";
import { getProcessingVariant } from "../lib/status";

type FilesTableProps = {
  files: FileItem[];
  isLoading: boolean;
};

export function FilesTable({ files, isLoading }: FilesTableProps) {
  return (
    <Card className="shadow-sm border-0 mb-4">
      <Card.Header className="bg-white border-0 pt-4 px-4">
        <div className="d-flex justify-content-between align-items-center">
          <h2 className="h5 mb-0">Файлы</h2>
          <Badge bg="secondary">{files.length}</Badge>
        </div>
      </Card.Header>
      <Card.Body className="px-4 pb-4">
        {isLoading ? (
          <div className="d-flex justify-content-center py-5">
            <Spinner animation="border" />
          </div>
        ) : (
          <div className="table-responsive">
            <Table hover bordered className="align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>Название</th>
                  <th>Файл</th>
                  <th>MIME</th>
                  <th>Размер</th>
                  <th>Статус</th>
                  <th>Проверка</th>
                  <th>Создан</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {files.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-4 text-secondary">
                      Файлы пока не загружены
                    </td>
                  </tr>
                ) : (
                  files.map((file) => (
                    <tr key={file.id}>
                      <td>
                        <div className="fw-semibold">{file.title}</div>
                        <div className="small text-secondary">{file.id}</div>
                      </td>
                      <td>{file.original_name}</td>
                      <td>{file.mime_type}</td>
                      <td>{formatSize(file.size)}</td>
                      <td>
                        <Badge bg={getProcessingVariant(file.processing_status)}>
                          {file.processing_status}
                        </Badge>
                      </td>
                      <td>
                        <div className="d-flex flex-column gap-1">
                          <Badge bg={file.requires_attention ? "warning" : "success"}>
                            {file.scan_status ?? "pending"}
                          </Badge>
                          <span className="small text-secondary">
                            {file.scan_details ?? "Ожидает обработки"}
                          </span>
                        </div>
                      </td>
                      <td>{formatDate(file.created_at)}</td>
                      <td className="text-nowrap">
                        <Button
                          as="a"
                          href={getDownloadUrl(file.id)}
                          variant="outline-primary"
                          size="sm"
                        >
                          Скачать
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </Table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
```

Заметки:
- `<Button as="a" href={...}>` — в оригинале работает без явного каста (TS `strict: false`). Оставляем идентично.

- [ ] **Шаг 2: Собрать.**

---

### Задача 10. `components/AlertsTable.tsx`

**Файлы:**
- Создать: `frontend/src/components/AlertsTable.tsx`

- [ ] **Шаг 1: Создать файл.** Разметка идентична `page.tsx:278-327`.

```tsx
import { Badge, Card, Spinner, Table } from "react-bootstrap";

import { AlertItem } from "../api/alerts";
import { formatDate } from "../lib/format";
import { getLevelVariant } from "../lib/status";

type AlertsTableProps = {
  alerts: AlertItem[];
  isLoading: boolean;
};

export function AlertsTable({ alerts, isLoading }: AlertsTableProps) {
  return (
    <Card className="shadow-sm border-0">
      <Card.Header className="bg-white border-0 pt-4 px-4">
        <div className="d-flex justify-content-between align-items-center">
          <h2 className="h5 mb-0">Алерты</h2>
          <Badge bg="secondary">{alerts.length}</Badge>
        </div>
      </Card.Header>
      <Card.Body className="px-4 pb-4">
        {isLoading ? (
          <div className="d-flex justify-content-center py-5">
            <Spinner animation="border" />
          </div>
        ) : (
          <div className="table-responsive">
            <Table hover bordered className="align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>ID</th>
                  <th>File ID</th>
                  <th>Уровень</th>
                  <th>Сообщение</th>
                  <th>Создан</th>
                </tr>
              </thead>
              <tbody>
                {alerts.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-4 text-secondary">
                      Алертов пока нет
                    </td>
                  </tr>
                ) : (
                  alerts.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td className="small">{item.file_id}</td>
                      <td>
                        <Badge bg={getLevelVariant(item.level)}>{item.level}</Badge>
                      </td>
                      <td>{item.message}</td>
                      <td>{formatDate(item.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </Table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
```

- [ ] **Шаг 2: Собрать.**

---

### Задача 11. `components/UploadModal.tsx`

**Файлы:**
- Создать: `frontend/src/components/UploadModal.tsx`

- [ ] **Шаг 1: Создать файл.** Разметка идентична `page.tsx:331-364`.

```tsx
import { FormEvent } from "react";
import { Button, Form, Modal } from "react-bootstrap";

type UploadModalProps = {
  show: boolean;
  title: string;
  isSubmitting: boolean;
  onTitleChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onHide: () => void;
  onSubmit: () => Promise<void>;
};

export function UploadModal({
  show,
  title,
  isSubmitting,
  onTitleChange,
  onFileChange,
  onHide,
  onSubmit,
}: UploadModalProps) {
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit();
  }

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Добавить файл</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Название</Form.Label>
            <Form.Control
              value={title}
              onChange={(event) => onTitleChange(event.target.value)}
              placeholder="Например, Договор с подрядчиком"
            />
          </Form.Group>
          <Form.Group>
            <Form.Label>Файл</Form.Label>
            <Form.Control
              type="file"
              onChange={(event) =>
                onFileChange((event.target as HTMLInputElement).files?.[0] ?? null)
              }
            />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={onHide}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Загрузка..." : "Сохранить"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
```

- [ ] **Шаг 2: Собрать.**

---

### Задача 12. Переписать `app/page.tsx` как композицию

**Файлы:**
- Изменить: `frontend/src/app/page.tsx` (полная замена)

**Ключ:** page.tsx держит `errorMessage`, передаёт `setErrorMessage` / `clearError` в хуки через колбэки. Это единственное место, где агрегируется ошибка.

- [ ] **Шаг 1: Полностью заменить содержимое `frontend/src/app/page.tsx`.**

```tsx
"use client";

import { useCallback, useState } from "react";
import { Alert, Col, Container, Row } from "react-bootstrap";

import { AlertsTable } from "../components/AlertsTable";
import { FilesTable } from "../components/FilesTable";
import { PageHeader } from "../components/PageHeader";
import { UploadModal } from "../components/UploadModal";
import { useDashboardData } from "../hooks/useDashboardData";
import { useFileUpload } from "../hooks/useFileUpload";

export default function Page() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const clearError = useCallback(() => setErrorMessage(null), []);
  const reportError = useCallback((message: string) => setErrorMessage(message), []);

  const data = useDashboardData({
    onStart: clearError,
    onError: reportError,
  });

  const upload = useFileUpload({
    onStart: clearError,
    onError: reportError,
    onSuccess: async () => {
      setShowModal(false);
      await data.reload();
    },
  });

  return (
    <Container fluid className="py-4 px-4 bg-light min-vh-100">
      <Row className="justify-content-center">
        <Col xxl={10} xl={11}>
          <PageHeader
            onReload={() => void data.reload()}
            onAddFile={() => setShowModal(true)}
          />

          {errorMessage ? (
            <Alert variant="danger" className="shadow-sm">
              {errorMessage}
            </Alert>
          ) : null}

          <FilesTable files={data.files} isLoading={data.isLoading} />
          <AlertsTable alerts={data.alerts} isLoading={data.isLoading} />
        </Col>
      </Row>

      <UploadModal
        show={showModal}
        title={upload.title}
        isSubmitting={upload.isSubmitting}
        onTitleChange={upload.setTitle}
        onFileChange={upload.setSelectedFile}
        onHide={() => setShowModal(false)}
        onSubmit={upload.submit}
      />
    </Container>
  );
}
```

**Проверка эквивалентности поведения:**
- **Единый `errorMessage`** — один state в page. Хуки не дублируют.
- **Сброс ошибки перед действием.** `clearError` передаётся как `onStart` в оба хука. Перед reload/submit вызывается — семантика `setErrorMessage(null)` из `page.tsx:101,140`.
- **Один `isLoading` на обе таблицы.** `data.isLoading` передаётся в обе таблицы — идентично оригиналу.
- **Частичный апдейт не происходит.** `useDashboardData` делает `Promise.all` и на любом фейле уходит в catch до setState — эквивалент `throw new Error` из `page.tsx:109-111`.
- **Модалка.** `onAddFile` → `setShowModal(true)` (ничего не сбрасывает). `onHide` → `setShowModal(false)` (ничего не сбрасывает). Сброс формы — **только внутри** `useFileUpload.submit` после успеха. Эквивалент `page.tsx:331,156-158`.
- **После успешной загрузки:** закрывается модалка → reload dashboard. Эквивалент `page.tsx:156-159`. Реализовано в `onSuccess` выше.
- **Валидация формы.** При пустом title/файле — `onError("Укажите название и выберите файл")` из `useFileUpload`, что эквивалентно `page.tsx:134-136`.
- **`clearError`/`reportError` стабильны** (обёрнуты в `useCallback` с пустым deps) — `useDashboardData` не будет бесконечно перевыполнять `reload` из-за меняющихся колбэков. `onSuccess` в `useFileUpload` — нестабильный (замыкание), но это OK, потому что `submit` в `useFileUpload` в deps имеет его и пересоздаётся — а вызывается только явно из `onSubmit` модалки, без useEffect.

- [ ] **Шаг 2: Собрать проект.**

```
cd frontend && npm run build
```

Ожидаемо: сборка успешна.

- [ ] **Шаг 3: Пробежаться по diff `page.tsx`.** Убедиться: никакого fetch, никакого useState для данных files/alerts, никакого форматирования, никаких маппингов статусов, никакого `http://localhost:8000` литералом. Только композиция и один `errorMessage`.

---

### Задача 13. Smoke-тест в браузере

**Файлы:** нет изменений.

- [ ] **Шаг 1: Поднять стек.**

```
docker compose -f docker-compose.dev.yml up
docker exec -it backend alembic upgrade head
```

- [ ] **Шаг 2: Открыть `http://localhost:3000/test`.**

Ожидаемо:
- Шапка «Управление файлами» и две кнопки.
- Две карточки: «Файлы» и «Алерты».
- При пустой БД — «Файлы пока не загружены» / «Алертов пока нет».
- Оба спиннера показываются и исчезают одновременно (ровно один `isLoading`).

- [ ] **Шаг 3: Загрузить файл (happy path).**

1. Клик «Добавить файл».
2. Ввести title, выбрать любой небольшой txt.
3. Клик «Сохранить» → модалка закрывается, файл в таблице.
4. После обработки Celery — клик «Обновить» → статус `processed`.

- [ ] **Шаг 4: Проверить валидацию формы.**

Открыть модалку, оставить title пустым, не выбирать файл → «Сохранить» → красный Alert «Укажите название и выберите файл». Модалка **не** закрывается.

- [ ] **Шаг 5: Проверить сохранение формы при закрытии модалки (регрессия поведения).**

1. Открыть модалку, ввести title «Test», выбрать файл.
2. Закрыть крестиком (не нажимая «Сохранить»).
3. Снова открыть модалку.
4. Ожидаемо: title «Test» и выбранный файл **сохранились** (как в оригинале).

- [ ] **Шаг 6: Проверить скачивание.**

Клик «Скачать» в строке файла → браузер скачивает оригинальный файл с корректным именем.

- [ ] **Шаг 7: Проверить ошибку API.**

1. `docker compose stop backend`.
2. Клик «Обновить» → красный Alert «Не удалось загрузить данные».
3. `docker compose -f docker-compose.dev.yml up -d backend`.
4. Клик «Обновить» → Alert пропадает, данные загружаются.

- [ ] **Шаг 8: Проверить эквивалентность ошибки upload.**

1. `docker compose stop backend`.
2. Попробовать загрузить файл через модалку → Alert «Не удалось загрузить файл». Модалка остаётся открытой. Поля title/файл сохраняются.
3. Поднять backend обратно.

---

### Задача 14. Финальная ревизия

**Файлы:** проверка.

- [ ] **Шаг 1: В `page.tsx` нет артефактов.**

```
grep -n "fetch\|formatDate\|formatSize\|getLevelVariant\|getProcessingVariant\|http://localhost" frontend/src/app/page.tsx
```

Ожидаемо: пусто.

- [ ] **Шаг 2: `"use client"` только в `page.tsx`.**

```
grep -rn "use client" frontend/src/
```

Ожидаемо: единственное вхождение — `frontend/src/app/page.tsx:1`.

- [ ] **Шаг 3: Нет хардкода `http://localhost` вне `api/client.ts`.**

```
grep -rn "http://localhost" frontend/src/
```

Ожидаемо: единственное вхождение — `frontend/src/api/client.ts`.

- [ ] **Шаг 4: Размер `page.tsx` — менее ~75 строк.**

- [ ] **Шаг 5: `npm run build` — финальный.**

---

### Задача 15 (опциональная). Фикс favicon

**Scope:** **не слой, а косметический баг фронта,** подмеченный по пути. Делать по желанию пользователя — не включать в ядро рефакторинга.

**Файл:** `frontend/src/app/layout.tsx:20`

Текущее: `<link rel="icon" href="/public/favicon.ico" sizes="any" />`
Next.js сервит `public/` из корня, значит правильный путь — `/favicon.ico` (а не `/public/...`). Текущая ссылка даёт 404.

- [ ] **Шаг 1: В `layout.tsx:20` заменить** `href="/public/favicon.ico"` на `href="/favicon.ico"`.

- [ ] **Шаг 2: Открыть `http://localhost:3000/test`**, проверить, что favicon подхватывается (вкладка браузера).

---

## Проверка плана (self-review)

- ✅ **Покрытие ТЗ.** Все слои: api (`client`, `files`, `alerts`), hooks (`useDashboardData`, `useFileUpload`), components (4), lib (`format`, `status`). Страница сжата.
- ✅ **Эквивалентность поведения.** Явные проверки в Задаче 12 и smoke-сценариях 3–8.
- ✅ **Единый loading и единый errorMessage** — сохранены (Задачи 6, 12).
- ✅ **Фиксированные тексты ошибок** — «Не удалось загрузить данные» / «Не удалось загрузить файл» / «Укажите название и выберите файл» (Задачи 6, 7).
- ✅ **Модалка не сбрасывает форму при открытии/закрытии** — только внутри `submit()` после успеха (Задача 7, smoke-сценарий 5).
- ✅ **`"use client"` только в `page.tsx`** (Задачи 8–11, ревизия в 14).
- ✅ **Тех-стек актуализирован** (Next.js 16.1.6, React 18.3.1).
- ✅ **Нет плейсхолдеров.** Полный код в каждой задаче.
- ✅ **Консистентность типов.** `FileItem`/`AlertItem` 1-в-1 с `page.tsx:18-39`.
- ✅ **Опциональный фикс favicon** вынесен отдельно (Задача 15).

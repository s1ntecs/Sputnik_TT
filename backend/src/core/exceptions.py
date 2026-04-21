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

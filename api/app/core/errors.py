"""Error envelope `{ error: { code, message, hint } }` and secret-masking for logs."""

from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError

from app.core.embeddings import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingRateLimitError,
    EmbeddingUnavailableError,
)

log = logging.getLogger("demokit")

MASK = "••••"
SECRET_PATTERNS = [
    (re.compile(r"(mongodb(?:\+srv)?://[^:/@\s]+:)[^@\s]+@"), rf"\g<1>{MASK}@"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), rf"\g<1>{MASK}"),
    (re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"), rf"\g<1>{MASK}"),
    (re.compile(r"\b(sk|pa|al)-[A-Za-z0-9_-]{8,}"), rf"\g<1>-{MASK}"),
]
AUTH_ERROR_CODES = {13, 18, 8000}


class AppError(Exception):
    def __init__(self, code: str, message: str, hint: str = "", status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "hint": self.hint}}


def mask_secrets(text: str, known: list[str] | None = None) -> str:
    for secret in known or []:
        if len(secret) >= 4:
            text = text.replace(secret, MASK)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def to_app_error(exc: BaseException) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, ServerSelectionTimeoutError):
        return AppError(
            "ATLAS_UNREACHABLE",
            "Could not reach the Atlas cluster.",
            "Check the Atlas IP access list, VPN, and that the cluster is running.",
            503,
        )
    if isinstance(exc, OperationFailure) and exc.code in AUTH_ERROR_CODES:
        return AppError(
            "AUTH_FAILED",
            "Atlas rejected the credentials.",
            "Check the database user and password in the connection string.",
            502,
        )
    if isinstance(exc, ConfigurationError):
        return AppError(
            "INVALID_URI",
            mask_secrets(str(exc)),
            "Use a mongodb+srv:// connection string from the Atlas Connect dialog.",
            400,
        )
    if isinstance(exc, EmbeddingAuthError):
        return AppError(
            "EMBEDDING_AUTH",
            "The embedding provider rejected the API key.",
            "Check the API key and, for Voyage, the base URL (Atlas keys use ai.mongodb.com).",
            502,
        )
    if isinstance(exc, EmbeddingRateLimitError):
        return AppError(
            "EMBEDDING_RATE_LIMIT",
            "The embedding provider is rate limiting requests.",
            "Wait a minute and try again.",
            503,
        )
    if isinstance(exc, EmbeddingUnavailableError | EmbeddingError):
        return AppError(
            "EMBEDDING_UNAVAILABLE",
            mask_secrets(str(exc)) or "The embedding provider request failed.",
            "Check network access to the provider and the selected model.",
            503,
        )
    if isinstance(exc, OperationFailure):
        return AppError("MONGODB_ERROR", mask_secrets(str(exc)), "", 400)
    return AppError("INTERNAL", "Unexpected server error.", "See the API log for details.", 500)


def register_error_handlers(app: FastAPI) -> None:
    async def handle(_: Request, exc: Exception) -> JSONResponse:
        err = to_app_error(exc)
        if err.status >= 500 and err.code == "INTERNAL":
            log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(err.body(), status_code=err.status)

    async def handle_validation(_: Request, exc: Exception) -> JSONResponse:
        errors = exc.errors() if isinstance(exc, RequestValidationError) else []
        msg = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', [])[1:])}: {e.get('msg')}" for e in errors
        )
        err = AppError("VALIDATION_ERROR", msg or "Invalid request.", "Check the form values.", 422)
        return JSONResponse(err.body(), status_code=422)

    app.add_exception_handler(RequestValidationError, handle_validation)
    for exc_type in (
        AppError,
        ServerSelectionTimeoutError,
        OperationFailure,
        ConfigurationError,
        EmbeddingError,
        Exception,
    ):
        app.add_exception_handler(exc_type, handle)


def install_log_masking(known_secrets: Callable[[], list[str]]) -> None:
    """Mask URIs and keys in every log record, including tracebacks."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_demokit_masking", False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        try:
            known = known_secrets()
        except Exception:
            known = []
        try:
            record.msg = mask_secrets(record.getMessage(), known)
            record.args = None
        except Exception:
            pass
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = mask_secrets(
                "".join(traceback.format_exception(*record.exc_info)), known
            ).rstrip()
        return record

    factory._demokit_masking = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)

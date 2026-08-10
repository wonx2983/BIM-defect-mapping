"""Custom exception classes and FastAPI exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    def __init__(self, detail: str, error_code: str = "APP_ERROR", status_code: int = 500):
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(detail)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail=detail, error_code="NOT_FOUND", status_code=404)


class UnauthorizedError(AppException):
    """Authentication required or invalid credentials."""

    def __init__(self, detail: str = "Invalid credentials"):
        super().__init__(detail=detail, error_code="UNAUTHORIZED", status_code=401)


class ForbiddenError(AppException):
    """Insufficient permissions."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(detail=detail, error_code="FORBIDDEN", status_code=403)


class ValidationError(AppException):
    """Request validation failed."""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(detail=detail, error_code="VALIDATION_ERROR", status_code=422)


class ConflictError(AppException):
    """Resource conflict (e.g., duplicate email)."""

    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(detail=detail, error_code="CONFLICT", status_code=409)


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
        )

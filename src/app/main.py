from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.chore import lifespan
from app.services.crud_item_store import router as item_store_router
from app.services.orders import orders_api_router, webhooks_api_router
from app.shared.exceptions import AppException, InternalError
from app.shared.responses import ErrorResponse, ValidationErrorResponse
from app.shared.logger import get_logger

logger = get_logger(__name__)


app = FastAPI(title="OpenTaberna API", lifespan=lifespan)


# Global exception handler for AppException
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handle all AppException instances and convert them to HTTP responses.

    The ErrorResponse.from_exception method automatically maps error categories
    to appropriate HTTP status codes (404, 422, 401, 403, 400, 500, 502).
    """
    error_response = ErrorResponse.from_exception(exc)
    return JSONResponse(
        status_code=error_response.status_code,
        content=error_response.model_dump(mode="json"),
    )


# Handler for FastAPI/Pydantic request validation errors (wrong types, missing fields, etc.)
@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle FastAPI RequestValidationError and convert to our standard ValidationErrorResponse.

    FastAPI raises this for invalid path/query params and request body validation failures.
    Maps Pydantic's raw error format to our structured ValidationErrorResponse so the
    actual 422 response always matches the schema documented in /docs.
    """
    validation_errors = [
        {
            "loc": list(error["loc"]),
            "msg": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    error_response = ValidationErrorResponse(
        message="Validation failed",
        validation_errors=validation_errors,
    )
    return JSONResponse(
        status_code=422,
        content=error_response.model_dump(mode="json"),
    )


# Catch-all exception handler for unexpected errors
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all unexpected exceptions and convert them to structured error responses.

    This is a safety net for any exceptions not caught by AppException handler.
    Logs the error for debugging and returns a generic 500 error to the client.
    """
    logger.error(
        "Unhandled exception occurred",
        extra={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=True,
    )

    # Wrap in InternalError for consistent error response structure
    error = InternalError(
        message="An unexpected error occurred",
        context={
            "error_type": type(exc).__name__,
        },
        original_exception=exc,
    )
    error_response = ErrorResponse.from_exception(error)
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(mode="json"),
    )


origins = ["*"]  # Consider restricting this in a production environment

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include crud-item-store router
app.include_router(item_store_router, prefix="/v1")

# Include orders service routers
app.include_router(orders_api_router, prefix="/v1")
app.include_router(webhooks_api_router, prefix="/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

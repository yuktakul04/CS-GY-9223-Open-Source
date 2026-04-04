"""FastAPI application for the chat client service."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chat_client_service.routers.auth import router as auth_router
from chat_client_service.routers.chat import router as chat_router


class HealthResponse(BaseModel):
    """Health endpoint response payload."""

    status: str


app = FastAPI(
    title="Chat Client Service",
    description="FastAPI service exposing Telegram chat operations over HTTP.",
    version="0.1.0",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Return a JSON 500 response for any unhandled exception."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {exc}"},
    )


@app.get("/health")
def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok")


app.include_router(auth_router)
app.include_router(chat_router)

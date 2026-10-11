import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.logging import DefaultFormatter

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.training_groups import router as training_groups_router
from app.core.config import get_settings
from app.core.errors import AuthError
from app.db.session import dispose_engine
from app.services.oauth_service import init_google_oauth


def _configure_app_logging() -> None:
    """Use uvicorn's level prefix for app.* loggers (not only uvicorn.*)."""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter(fmt="%(levelprefix)s %(name)s %(message)s"))
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


_configure_app_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize OAuth on startup and dispose the DB engine on shutdown."""
    init_google_oauth(settings)
    yield
    await dispose_engine()


app = FastAPI(title="Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(training_groups_router)


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    """Map domain AuthError to a FastAPI-style JSON error response."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

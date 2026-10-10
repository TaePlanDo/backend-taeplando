from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.errors import AuthError
from app.db.session import dispose_engine
from app.services.oauth_service import init_google_oauth

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


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    """Map domain AuthError to a FastAPI-style JSON error response."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

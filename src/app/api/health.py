from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    """Liveness probe used by local checks and deploy health checks."""
    return {"status": "ok"}

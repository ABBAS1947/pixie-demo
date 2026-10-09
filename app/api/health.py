from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.runtime import API_INSTANCE_ID, BUILD_REVISION, EXPECTED_DB_REVISION

router = APIRouter()


@router.get("/health")
async def health(response: Response) -> dict:
    """Health and process identity for client recovery; never cache this response."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    result = {
        "status": "ok",
        "build_revision": BUILD_REVISION,
        "expected_db_revision": EXPECTED_DB_REVISION,
        "api_instance_id": API_INSTANCE_ID,
    }
    # Only expose details in dev mode
    if settings.auth_dev_mode:
        result["model"] = settings.deepseek_model
        result["honcho"] = settings.honcho_base_url
    return result

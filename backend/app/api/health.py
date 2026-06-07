from fastapi import APIRouter

from app.services.mineru_api import MineruApiClient

router = APIRouter()


@router.get("/system/mineru-health")
def mineru_health():
    return MineruApiClient().health()

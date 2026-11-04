from fastapi import APIRouter
from backend.app.api.v1.links import router as links_router

api_router = APIRouter()
api_router.include_router(links_router)

from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.api.v1 import api_router
from backend.app.core.config import settings
from backend.app.core.database import Base, engine, get_db
from backend.app.services.link_service import LinkNotFoundError, record_click_and_get_target


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Open-source, self-hosted URL shortening platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes under /api/v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["system"])
def health_check():
    """Health check endpoint to verify backend operational readiness."""
    return {"status": "ok", "app": settings.PROJECT_NAME, "version": "0.1.0"}


@app.get("/{short_code}", include_in_schema=False)
def redirect_to_target(
    short_code: str,
    db: Session = Depends(get_db),
):
    """
    Resolve destination URL, atomically record visitor click, and issue a 307 Temporary Redirect.
    
    A 307 redirect prevents client and proxy caching to preserve accurate click measurement.
    """
    try:
        target_url = record_click_and_get_target(db, short_code)
        return RedirectResponse(
            url=target_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
    except LinkNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Short link '{short_code}' not found or inactive."},
        )

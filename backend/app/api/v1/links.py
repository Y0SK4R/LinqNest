from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import URLValidationError
from backend.app.schemas.link import LinkCreate, LinkResponse, LinkStats
from backend.app.services.link_service import (
    CodeAlreadyExistsError,
    CollisionRetryExceededError,
    ReservedCodeError,
    create_link,
    get_link_by_code,
    list_links,
)

router = APIRouter(prefix="/links", tags=["links"])


def build_response(link, base_url: str) -> LinkResponse:
    short_url = f"{base_url.rstrip('/')}/{link.short_code}"
    return LinkResponse(
        id=link.id,
        short_code=link.short_code,
        short_url=short_url,
        original_url=link.original_url,
        title=link.title,
        click_count=link.click_count,
        is_active=link.is_active,
        created_at=link.created_at,
    )


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_new_link(
    link_in: LinkCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a shortened URL with optional custom code and title."""
    base_url = str(request.base_url).rstrip("/") if request else settings.BASE_URL
    try:
        link = create_link(db, link_in)
        return build_response(link, base_url)
    except URLValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_URL", "message": str(e)},
        )
    except (CodeAlreadyExistsError, ReservedCodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CODE_EXISTS", "message": str(e)},
        )
    except CollisionRetryExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "COLLISION_EXHAUSTION", "message": str(e)},
        )


@router.get("", response_model=list[LinkResponse])
def get_links(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List links sorted by newest first."""
    base_url = str(request.base_url).rstrip("/") if request else settings.BASE_URL
    links = list_links(db, skip=skip, limit=limit)
    return [build_response(link, base_url) for link in links]


@router.get("/{short_code}/stats", response_model=LinkStats)
def get_link_statistics(
    short_code: str,
    db: Session = Depends(get_db),
):
    """Retrieve performance statistics for a specific short link."""
    link = get_link_by_code(db, short_code)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Link with code '{short_code}' not found."},
        )
    return link

import secrets
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.core.security import validate_and_sanitize_url
from backend.app.models.link import Link
from backend.app.schemas.link import LinkCreate

BASE62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
RESERVED_ROUTES = {
    "api",
    "docs",
    "redoc",
    "openapi.json",
    "static",
    "health",
    "favicon.ico",
    "robots.txt",
}


class LinkServiceError(Exception):
    """Base exception for link service errors."""
    pass


class CodeAlreadyExistsError(LinkServiceError):
    """Raised when a custom code is already in use."""
    pass


class ReservedCodeError(LinkServiceError):
    """Raised when a requested custom code conflicts with internal API routes."""
    pass


class CollisionRetryExceededError(LinkServiceError):
    """Raised when automatic short code generation exceeds maximum retry limit."""
    pass


class LinkNotFoundError(LinkServiceError):
    """Raised when a short code does not exist or is deactivated."""
    pass


def generate_random_code(length: int = 6) -> str:
    """Generate a cryptographically secure random Base62 string."""
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))


def create_link(db: Session, link_in: LinkCreate, check_dns: bool = True) -> Link:
    """
    Validate target URL, resolve or generate short code, and persist Link.
    
    Ensures collision avoidance, validates protocol constraints, and blocks SSRF vectors.
    """
    sanitized_url = validate_and_sanitize_url(link_in.original_url, check_dns=check_dns)

    if link_in.custom_code:
        custom_code = link_in.custom_code.strip()
        if custom_code.lower() in RESERVED_ROUTES:
            raise ReservedCodeError(f"The code '{custom_code}' is reserved by system routing.")

        existing = db.query(Link).filter(Link.short_code == custom_code).first()
        if existing:
            raise CodeAlreadyExistsError(f"The short code '{custom_code}' is already in use.")

        short_code = custom_code
        link = Link(
            short_code=short_code,
            original_url=sanitized_url,
            title=link_in.title.strip() if link_in.title else None,
            click_count=0,
            is_active=True,
        )
        db.add(link)
        try:
            db.commit()
            db.refresh(link)
            return link
        except IntegrityError:
            db.rollback()
            raise CodeAlreadyExistsError(f"The short code '{custom_code}' is already in use.")

    # Generate random unique code with collision retry logic
    for attempt in range(settings.MAX_RETRY_COLLISIONS):
        code = generate_random_code(settings.CODE_LENGTH)
        if code.lower() in RESERVED_ROUTES:
            continue

        existing = db.query(Link).filter(Link.short_code == code).first()
        if existing:
            continue

        link = Link(
            short_code=code,
            original_url=sanitized_url,
            title=link_in.title.strip() if link_in.title else None,
            click_count=0,
            is_active=True,
        )
        db.add(link)
        try:
            db.commit()
            db.refresh(link)
            return link
        except IntegrityError:
            db.rollback()
            continue

    raise CollisionRetryExceededError(
        f"Unable to allocate a unique short code after {settings.MAX_RETRY_COLLISIONS} attempts."
    )


def get_link_by_code(db: Session, short_code: str) -> Link | None:
    """Query a link by its short code."""
    return db.query(Link).filter(Link.short_code == short_code).first()


def record_click_and_get_target(db: Session, short_code: str) -> str:
    """
    Increment click count and return destination URL.
    
    Raises LinkNotFoundError if the link is not found or inactive.
    """
    link = db.query(Link).filter(Link.short_code == short_code, Link.is_active == True).first()
    if not link:
        raise LinkNotFoundError(f"Active short link '{short_code}' not found.")

    link.click_count += 1
    db.commit()
    return link.original_url


def list_links(db: Session, skip: int = 0, limit: int = 50) -> list[Link]:
    """Retrieve links ordered by most recently created."""
    return db.query(Link).order_by(Link.created_at.desc()).offset(skip).limit(limit).all()

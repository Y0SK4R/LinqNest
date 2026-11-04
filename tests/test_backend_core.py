import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.core.security import URLValidationError, validate_and_sanitize_url
from backend.app.models.link import Link
from backend.app.schemas.link import LinkCreate
from backend.app.services.link_service import (
    CodeAlreadyExistsError,
    LinkNotFoundError,
    ReservedCodeError,
    create_link,
    get_link_by_code,
    record_click_and_get_target,
)

# In-memory database with StaticPool for isolated unit tests
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_url_validation_disallowed_schemes():
    disallowed = [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html;base64,PHNjcmlwdD4=",
        "ftp://example.com/file.txt",
        "gopher://example.com",
    ]
    for url in disallowed:
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url(url, check_dns=False)


def test_url_validation_ssrf_and_private_ips():
    ssrf_vectors = [
        "http://127.0.0.1/admin",
        "http://localhost:8080",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/secret",
        "http://192.168.1.1/router",
        "http://172.16.0.5/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://server.local/",
        "http://cluster.internal/",
    ]
    for url in ssrf_vectors:
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url(url, check_dns=False)


def test_url_validation_embedded_credentials():
    with pytest.raises(URLValidationError):
        validate_and_sanitize_url("https://user:password@example.com/path", check_dns=False)


def test_url_validation_valid_http_https():
    valid_urls = [
        "https://example.com",
        "http://example.org/path?query=1#frag",
        "https://sub.domain.org:8443/test",
    ]
    for url in valid_urls:
        sanitized = validate_and_sanitize_url(url, check_dns=False)
        assert sanitized.startswith("http")


def test_create_link_random_code(db_session):
    link_in = LinkCreate(original_url="https://example.com/docs")
    link = create_link(db_session, link_in, check_dns=False)

    assert link.id is not None
    assert len(link.short_code) == 6
    assert link.click_count == 0
    assert link.is_active is True
    assert link.original_url == "https://example.com/docs"


def test_create_link_custom_code(db_session):
    link_in = LinkCreate(
        original_url="https://example.com/custom",
        custom_code="my-doc",
        title="My Document",
    )
    link = create_link(db_session, link_in, check_dns=False)
    assert link.short_code == "my-doc"
    assert link.title == "My Document"

    # Duplicate custom code must fail with CodeAlreadyExistsError
    with pytest.raises(CodeAlreadyExistsError):
        create_link(db_session, link_in, check_dns=False)


def test_reserved_code_prevention(db_session):
    link_in = LinkCreate(original_url="https://example.com", custom_code="api")
    with pytest.raises(ReservedCodeError):
        create_link(db_session, link_in, check_dns=False)


def test_record_click_and_redirect(db_session):
    link_in = LinkCreate(original_url="https://example.com/target", custom_code="click-test")
    link = create_link(db_session, link_in, check_dns=False)

    target_url = record_click_and_get_target(db_session, "click-test")
    assert target_url == "https://example.com/target"

    updated_link = get_link_by_code(db_session, "click-test")
    assert updated_link.click_count == 1

    # Inactive or nonexistent code raises LinkNotFoundError
    with pytest.raises(LinkNotFoundError):
        record_click_and_get_target(db_session, "nonexistent")

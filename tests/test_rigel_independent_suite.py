import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.core.security import URLValidationError, validate_and_sanitize_url
from backend.app.main import app
from backend.app.models.link import Link
from backend.app.schemas.link import LinkCreate
from backend.app.services.link_service import (
    CodeAlreadyExistsError,
    CollisionRetryExceededError,
    LinkNotFoundError,
    ReservedCodeError,
    create_link,
    get_link_by_code,
    record_click_and_get_target,
)

# Isolated Test Database
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


# =========================================================================
# 1. SECURITY & ADVERSARIAL VALIDATION (RIGEL GATING SUITE)
# =========================================================================

class TestSecurityAdversarialSuite:
    """Rigorous boundary and adversarial security verification."""

    @pytest.mark.parametrize("malicious_url", [
        "javascript:alert(document.domain)",
        "JAVASCRIPT:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "file:///etc/passwd",
        "file:///C:/Windows/win.ini",
        "vbscript:msgbox(1)",
        "ftp://ftp.example.com/file",
        "gopher://gopher.floodgap.com",
        "ws://echo.websocket.org",
        "wss://echo.websocket.org",
        "mailto:test@example.com",
        "blob:https://example.com/uuid",
    ])
    def test_disallowed_schemes_rejected(self, malicious_url):
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url(malicious_url, check_dns=False)

    @pytest.mark.parametrize("ssrf_host", [
        "http://localhost/admin",
        "http://localhost:8080/metrics",
        "http://127.0.0.1/status",
        "http://127.0.0.1:3000/",
        "http://[::1]/private",
        "http://0.0.0.0:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://10.255.255.254/db",
        "http://172.16.0.1/admin",
        "http://172.31.255.255/intranet",
        "http://192.168.0.1/gateway",
        "http://192.168.1.254/config",
        "http://app.local/",
        "http://service.internal/",
        "http://workstation.lan/",
        "http://router.home/",
        "http://internal.corp/",
    ])
    def test_ssrf_and_private_hostnames_rejected(self, ssrf_host):
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url(ssrf_host, check_dns=False)

    def test_embedded_credentials_blocked(self):
        vectors = [
            "https://admin:password@example.com/dashboard",
            "http://user:secret@sub.domain.org/",
            "https://user@example.com/",
        ]
        for v in vectors:
            with pytest.raises(URLValidationError):
                validate_and_sanitize_url(v, check_dns=False)

    def test_url_length_boundaries(self):
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url("", check_dns=False)

        with pytest.raises(URLValidationError):
            validate_and_sanitize_url("   ", check_dns=False)

        # 2048 chars max allowed
        valid_long_url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
        assert len(valid_long_url) == 2048
        sanitized = validate_and_sanitize_url(valid_long_url, check_dns=False)
        assert sanitized == valid_long_url

        too_long_url = valid_long_url + "b"
        with pytest.raises(URLValidationError):
            validate_and_sanitize_url(too_long_url, check_dns=False)


# =========================================================================
# 2. CUSTOM CODE INTEGRITY & COLLISION TESTS
# =========================================================================

class TestCustomCodeAndCollisionSuite:
    """Verifies custom code boundaries, collision retries, and reserved pathing."""

    @pytest.mark.parametrize("reserved", [
        "api", "API", "docs", "Docs", "redoc", "REDOC", "static", "health", "HEALTH"
    ])
    def test_alphanumeric_reserved_routes_rejected(self, db_session, reserved):
        link_in = LinkCreate(original_url="https://example.com/doc", custom_code=reserved)
        with pytest.raises(ReservedCodeError):
            create_link(db_session, link_in, check_dns=False)

    @pytest.mark.parametrize("dotted_reserved", [
        "openapi.json", "favicon.ico", "robots.txt"
    ])
    def test_dotted_reserved_routes_blocked_at_schema(self, dotted_reserved):
        # Dotted routes fail custom_code regex validation (^[\w-]{3,16}$)
        with pytest.raises(ValidationError):
            LinkCreate(original_url="https://example.com/doc", custom_code=dotted_reserved)

    def test_custom_code_duplicate_collision_prevention(self, db_session):
        link_1 = LinkCreate(original_url="https://example.com/page1", custom_code="unique-alias")
        create_link(db_session, link_1, check_dns=False)

        link_2 = LinkCreate(original_url="https://example.com/page2", custom_code="unique-alias")
        with pytest.raises(CodeAlreadyExistsError):
            create_link(db_session, link_2, check_dns=False)

    def test_automatic_shortcode_uniqueness(self, db_session):
        generated_codes = set()
        for i in range(25):
            link_in = LinkCreate(original_url=f"https://example.com/item/{i}")
            link = create_link(db_session, link_in, check_dns=False)
            assert len(link.short_code) == 6
            assert link.short_code not in generated_codes
            generated_codes.add(link.short_code)


# =========================================================================
# 3. REDIRECTION, STATE & STATS VERIFICATION
# =========================================================================

class TestRedirectionAndLifecycleSuite:
    """Verifies redirect mechanics, click telemetry, and lifecycle state."""

    def test_redirect_307_and_click_counter_progression(self, db_session):
        link_in = LinkCreate(original_url="https://example.com/target-page", custom_code="redirect-test")
        create_link(db_session, link_in, check_dns=False)

        # Initial click count must be 0
        link = get_link_by_code(db_session, "redirect-test")
        assert link.click_count == 0

        # Simulate 5 consecutive redirects
        for expected_count in range(1, 6):
            target = record_click_and_get_target(db_session, "redirect-test")
            assert target == "https://example.com/target-page"
            fresh_link = get_link_by_code(db_session, "redirect-test")
            assert fresh_link.click_count == expected_count

    def test_nonexistent_or_deactivated_link_handling(self, db_session):
        with pytest.raises(LinkNotFoundError):
            record_click_and_get_target(db_session, "missing-code")

        # Deactivated link
        deactivated = Link(
            short_code="disabled-link",
            original_url="https://example.com/off",
            is_active=False,
            click_count=0
        )
        db_session.add(deactivated)
        db_session.commit()

        with pytest.raises(LinkNotFoundError):
            record_click_and_get_target(db_session, "disabled-link")


# =========================================================================
# 4. FULL API CONTRACT & END-TO-END WORKFLOW VERIFICATION
# =========================================================================

class TestApiContractWorkflowSuite:
    """Full HTTP API validation covering Lin & Pixel shared contracts."""

    def test_e2e_create_redirect_and_stats_cycle(self, client):
        # 1. Create short link
        payload = {
            "original_url": "https://example.com/product/launch",
            "custom_code": "launch26",
            "title": "Product Launch 2026",
        }
        res = client.post("/api/v1/links", json=payload)
        assert res.status_code == 201
        body = res.json()
        assert body["short_code"] == "launch26"
        assert body["short_url"].endswith("/launch26")
        assert body["click_count"] == 0
        assert body["title"] == "Product Launch 2026"

        # 2. Issue Redirect
        redirect_res = client.get("/launch26", follow_redirects=False)
        assert redirect_res.status_code == 307
        assert redirect_res.headers["location"] == "https://example.com/product/launch"

        # 3. Verify Stats Telemetry
        stats_res = client.get("/api/v1/links/launch26/stats")
        assert stats_res.status_code == 200
        stats_body = stats_res.json()
        assert stats_body["click_count"] == 1
        assert stats_body["short_code"] == "launch26"

        # 4. Listing includes the newly created link
        list_res = client.get("/api/v1/links?skip=0&limit=10")
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(item["short_code"] == "launch26" for item in items)

    def test_api_rejection_of_duplicate_custom_code(self, client):
        payload = {"original_url": "https://example.com/first", "custom_code": "dupe-check"}
        res1 = client.post("/api/v1/links", json=payload)
        assert res1.status_code == 201

        res2 = client.post("/api/v1/links", json=payload)
        assert res2.status_code == 409
        err = res2.json()
        assert err["detail"]["code"] == "CODE_EXISTS"

    def test_api_rejection_of_invalid_custom_code_characters(self, client):
        # Invalid characters (spaces, special chars) should return 422
        bad_payload = {"original_url": "https://example.com/test", "custom_code": "bad/code"}
        res = client.post("/api/v1/links", json=bad_payload)
        assert res.status_code == 422

    def test_api_redirect_404_on_unknown_code(self, client):
        res = client.get("/definitely-does-not-exist", follow_redirects=False)
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "NOT_FOUND"

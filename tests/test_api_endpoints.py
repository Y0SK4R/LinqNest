import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.main import app

# StaticPool ensures the in-memory SQLite database persists across connections during test execution
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

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
    Base.metadata.drop_all(bind=engine)


def test_api_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_create_and_redirect_link(client):
    payload = {
        "original_url": "https://example.com/test-article",
        "custom_code": "my-post",
        "title": "Test Article",
    }
    create_res = client.post("/api/v1/links", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["short_code"] == "my-post"
    assert data["click_count"] == 0

    # Test redirection (307)
    redirect_res = client.get("/my-post", follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers["location"] == "https://example.com/test-article"

    # Test stats endpoint reflects click
    stats_res = client.get("/api/v1/links/my-post/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["click_count"] == 1


def test_api_ssrf_rejected(client):
    payload = {
        "original_url": "http://127.0.0.1:8000/secret",
    }
    res = client.post("/api/v1/links", json=payload)
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "INVALID_URL"

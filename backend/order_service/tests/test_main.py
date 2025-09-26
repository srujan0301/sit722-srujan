import logging
import time
from unittest.mock import AsyncMock, patch

import pytest
from app.db import SessionLocal, engine, get_db, Base
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

# Try importing PRODUCT_SERVICE_URL safely
try:
    from app.main import PRODUCT_SERVICE_URL
except ImportError:
    PRODUCT_SERVICE_URL = "http://localhost:8001"

# Suppress noisy logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("app.main").setLevel(logging.WARNING)


# --- Pytest Fixtures ---
@pytest.fixture(scope="session", autouse=True)
def setup_database_for_tests():
    """Drop and recreate tables before running tests.
       Works with SQLite (CI) or Postgres (local/dev)."""
    max_retries = 5
    retry_delay_seconds = 2
    for i in range(max_retries):
        try:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            break
        except OperationalError as e:
            logging.warning(
                f"Test DB setup failed: {e}. Retrying {i+1}/{max_retries}..."
            )
            time.sleep(retry_delay_seconds)
            if i == max_retries - 1:
                pytest.fail(f"Could not set up test DB after {max_retries} attempts: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected DB setup error: {e}", pytrace=True)
    yield


@pytest.fixture(scope="function")
def db_session_for_test():
    connection = engine.connect()
    transaction = connection.begin()
    db = SessionLocal(bind=connection)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield db
    finally:
        transaction.rollback()
        db.close()
        connection.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def mock_httpx_client():
    with patch("app.main.httpx.AsyncClient") as mock_async_client_cls:
        mock_client_instance = AsyncMock()
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client_instance
        yield mock_client_instance


# --- Tests ---
def test_read_root(client: TestClient):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Order Service!"}


def test_health_check(client: TestClient):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "order-service"}

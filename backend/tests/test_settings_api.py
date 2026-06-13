from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models.base import Base
from main import app


def test_settings_accepts_all_mineru_api_backends():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        for backend in [
            "pipeline",
            "vlm-auto-engine",
            "vlm-http-client",
            "hybrid-auto-engine",
            "hybrid-http-client",
        ]:
            response = client.put(
                "/api/settings",
                headers={"X-User-Id": f"settings-{backend}"},
                json={
                    "force_ocr": False,
                    "ocr_lang": "ch",
                    "formula_recognition": True,
                    "table_recognition": True,
                    "backend": backend,
                },
            )

            assert response.status_code == 200
            assert response.json()["backend"] == backend
    finally:
        app.dependency_overrides.clear()

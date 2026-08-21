"""SharedSecretMiddleware (app/api/auth_gate.py) -- the opt-in gate for
public deployments. Real TestClient against the real app instance, only
`settings.app_shared_secret` monkeypatched, matching the existing
`anthropic_api_key` monkeypatch pattern in test_api.py.
"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_unset_secret_leaves_every_route_open(monkeypatch):
    monkeypatch.setattr(settings, "app_shared_secret", None)

    response = client.get("/domains")

    assert response.status_code == 200


def test_set_secret_rejects_a_request_with_no_header(monkeypatch):
    monkeypatch.setattr(settings, "app_shared_secret", "correct-secret")

    response = client.get("/domains")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_set_secret_rejects_a_wrong_header(monkeypatch):
    monkeypatch.setattr(settings, "app_shared_secret", "correct-secret")

    response = client.get("/domains", headers={"x-app-secret": "wrong-secret"})

    assert response.status_code == 401


def test_set_secret_accepts_the_matching_header(monkeypatch):
    monkeypatch.setattr(settings, "app_shared_secret", "correct-secret")

    response = client.get("/domains", headers={"x-app-secret": "correct-secret"})

    assert response.status_code == 200

import json
from pathlib import Path

from fastapi.testclient import TestClient

from yantu.app import create_app
from yantu.version import VERSION


def test_release_version_matches_api_and_package(tmp_path):
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == VERSION
    app = create_app(f"sqlite:///{tmp_path / 'release.db'}", tmp_path / "uploads")
    with TestClient(app) as client:
        assert client.get("/healthz").json()["version"] == VERSION
        assert client.get("/api/v1/system/status").json()["data"]["version"] == VERSION
        assert client.get("/openapi.json").json()["info"]["version"] == VERSION

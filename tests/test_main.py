from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from main import app, get_client


class FakeAzdoClient:
    def __init__(self) -> None:
        self.builds = []

    def fetch_builds(self, *, branch, days, top):  # noqa: D401
        """Mimic the Azure client fetch step."""

        return {}

    def transform_builds(self, raw, *, timezone_name, wildcard_pattern=None):  # noqa: D401
        """Return the preset builds for the test."""

        return list(self.builds)


@pytest.fixture()
def api_client():
    fake = FakeAzdoClient()
    app.dependency_overrides[get_client] = lambda: fake
    client = TestClient(app)
    try:
        yield client, fake
    finally:
        app.dependency_overrides.pop(get_client, None)


def test_pipeline_filter_matches_partial_name(api_client):
    client, fake = api_client
    fake.builds = [
        {"id": 1, "pipelineName": "API Build", "result": "succeeded"},
        {"id": 2, "pipelineName": "UI Deploy", "result": "failed"},
    ]

    response = client.get("/api/builds?pipeline=api")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["builds"][0]["pipelineName"] == "API Build"


def test_pipeline_filter_ignores_case_and_whitespace(api_client):
    client, fake = api_client
    fake.builds = [
        {"id": 3, "pipelineName": "infra sync", "result": "succeeded"},
        {"id": 4, "pipelineName": "Reporting Deploy", "result": "failed"},
    ]

    response = client.get("/api/builds?pipeline=%20deploy%20")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["builds"][0]["pipelineName"] == "Reporting Deploy"

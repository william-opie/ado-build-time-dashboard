from __future__ import annotations

from app.clients.azure_devops import AzureDevOpsClient
from app.config import Settings


def make_client() -> AzureDevOpsClient:
    settings = Settings(azdo_org="org", azdo_project="project", azdo_pat="token")
    return AzureDevOpsClient(settings)


def test_transform_builds_sorted_by_finish_time_descending():
    client = make_client()
    raw = {
        "value": [
            {
                "id": 1,
                "buildNumber": "build-1",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "startTime": "2025-10-15T10:00:00Z",
                "finishTime": "2025-10-15T10:10:00Z",
            },
            {
                "id": 2,
                "buildNumber": "build-2",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "startTime": "2025-11-14T09:00:00Z",
                "finishTime": "2025-11-14T09:15:00Z",
            },
        ]
    }

    builds = client.transform_builds(raw, timezone_name="UTC")

    assert [build["id"] for build in builds] == [2, 1]
    assert builds[0]["startTimestamp"] > builds[1]["startTimestamp"]


def test_transform_builds_uses_start_time_when_finish_missing():
    client = make_client()
    raw = {
        "value": [
            {
                "id": 3,
                "buildNumber": "build-3",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "startTime": "2025-12-01T12:00:00Z",
                "finishTime": None,
            },
            {
                "id": 4,
                "buildNumber": "build-4",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "startTime": "2025-11-30T12:00:00Z",
                "finishTime": None,
            },
        ]
    }

    builds = client.transform_builds(raw, timezone_name="UTC")

    assert [build["id"] for build in builds] == [3, 4]
    assert builds[0]["startTimestamp"] > builds[1]["startTimestamp"]


def test_transform_builds_start_timestamp_falls_back_when_missing_start():
    client = make_client()
    raw = {
        "value": [
            {
                "id": 5,
                "buildNumber": "build-5",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "queueTime": "2025-11-01T12:00:00Z",
                "finishTime": "2025-11-01T12:10:00Z",
                "startTime": None,
            },
            {
                "id": 6,
                "buildNumber": "build-6",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "queueTime": "2025-10-01T12:00:00Z",
                "finishTime": "2025-10-01T12:10:00Z",
                "startTime": None,
            },
        ]
    }

    builds = client.transform_builds(raw, timezone_name="UTC")

    assert [build["id"] for build in builds] == [5, 6]
    assert builds[0]["startTimestamp"] > builds[1]["startTimestamp"]

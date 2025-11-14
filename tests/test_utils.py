import time
from unittest import mock

from app.cache import TTLCache
from app.clients.azure_devops import AzureDevOpsClient
from app.config import Settings
from app.utils import branch_has_wildcard, normalize_branch


def test_normalize_branch_prefixes_refs():
    assert normalize_branch("main") == "refs/heads/main"
    assert normalize_branch("refs/tags/v1") == "refs/tags/v1"


def test_branch_has_wildcard():
    assert branch_has_wildcard("release/*")
    assert not branch_has_wildcard("refs/heads/main")


def test_ttl_cache_expires():
    cache = TTLCache(1)
    cache.set("foo", "bar")
    assert cache.get("foo") == "bar"
    time.sleep(1.1)
    assert cache.get("foo") is None


def test_transform_builds_converts_timezone():
    settings = Settings(azdo_org="org", azdo_project="proj", azdo_pat="dummy-token")
    client = AzureDevOpsClient(settings)
    client._cache.set = mock.Mock()  # avoid caching real call
    raw = {
        "value": [
            {
                "id": 1,
                "buildNumber": "123",
                "definition": {"name": "Pipe"},
                "sourceBranch": "refs/heads/main",
                "result": "succeeded",
                "status": "completed",
                "startTime": "2024-01-01T00:00:00Z",
                "finishTime": "2024-01-01T00:30:00Z",
            }
        ]
    }
    builds = client.transform_builds(raw, timezone_name="UTC")
    assert builds[0]["durationSeconds"] == 1800
    assert builds[0]["startTime"] == "1/1/2024 12:00 AM"

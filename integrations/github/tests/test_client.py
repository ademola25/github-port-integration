import pytest
from httpx import AsyncClient
from client import GitHubClient


@pytest.mark.asyncio
async def test_get_pull_requests(httpx_mock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/user/test-repo/pulls?state=all&per_page=100",
        method="GET",
        json=[{"id": 1, "title": "Test PR", "repository": {"name": "test-repo"}}],
    )
    client = GitHubClient("https://api.github.com", "fake-token")
    client._client = AsyncClient()
    try:
        async for prs in client.get_pull_requests("user", "test-repo"):
            assert prs[0]["title"] == "Test PR"
    finally:
        await client._client.aclose()

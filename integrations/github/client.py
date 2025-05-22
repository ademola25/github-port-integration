from typing import Any, AsyncGenerator, Optional
import asyncio
import re
import time
import httpx
import logging

from port_ocean.utils import http_async_client
from enum import Enum

logger = logging.getLogger(__name__)


class GithubEndpoints(Enum):
    LIST_REPOSITORIES = "user/repos"
    LIST_PULL_REQUESTS = "repos/{owner}/{repo}/pulls"
    LIST_ISSUES = "repos/{owner}/{repo}/issues"
    LIST_TEAMS = "orgs/{org}/teams"
    LIST_WORKFLOWS = "repos/{owner}/{repo}/actions/workflows"
    LIST_FILES = "repos/{owner}/{repo}/contents/{path}"
    GET_README = "repos/{owner}/{repo}/readme"
    CREATE_WEBHOOK = "repos/{owner}/{repo}/hooks"


class GitHubClient:
    DEFAULT_BASE_URL = "https://api.github.com"
    DEFAULT_API_VERSION = "2022-11-28"
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BACKOFF_FACTOR = 2

    def __init__(
        self,
        base_url: str,
        token: str,
        api_version: str = DEFAULT_API_VERSION,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = http_async_client
        self.api_version = api_version
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.NEXT_PATTERN = re.compile(r'<([^>]+)>; rel="next"')
        self.pagination_header_name = "Link"
        self.rate_limit_status_code = 429
        self.forbidden_status_code = 403
        self.not_found_status_code = 404

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.api_version,
        }

    async def _handle_rate_limit(self, response: httpx.Response) -> bool:
        if response.status_code in (
            self.rate_limit_status_code,
            self.forbidden_status_code,
        ):
            remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
            reset_time = response.headers.get("X-RateLimit-Reset")
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                sleep_duration = int(retry_after)
                logger.warning(
                    f"Rate limit hit (Retry-After). " f"Sleeping for {sleep_duration}s"
                )
                await asyncio.sleep(sleep_duration)
                return True
            if remaining == "0" and reset_time:
                sleep_duration = max(0, int(reset_time) - int(time.time()))
                logger.warning(
                    f"Rate limit hit. Sleeping for {sleep_duration}s until {reset_time}"
                )
                await asyncio.sleep(sleep_duration)
                return True
        return False

    async def _send_api_request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        ignore_status_codes: Optional[list[int]] = None,
    ) -> httpx.Response | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.debug(f"Sending {method} request to {url}")

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=data,
                    timeout=30,
                )
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if await self._handle_rate_limit(e.response):
                    if attempt < self.max_retries:
                        sleep_duration = self.backoff_factor * (2**attempt)
                        logger.info(
                            f"Retrying after {sleep_duration}s (attempt {attempt + 1})"
                        )
                        await asyncio.sleep(sleep_duration)
                        continue
                if (
                    ignore_status_codes
                    and e.response.status_code in ignore_status_codes
                ):
                    logger.info(
                        f"Ignoring status code {e.response.status_code} "
                        f"for {method} {url}"
                    )
                    return None
                if e.response.status_code == self.not_found_status_code:
                    logger.info(f"Resource not found: {url}")
                    return None
                logger.error(f"HTTP error for {method} {url}: {e.response.status_code}")
                raise

            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    sleep_duration = self.backoff_factor * (2**attempt)
                    logger.warning(
                        f"Network error for {method} {url}. "
                        f"Retrying in {sleep_duration}s"
                    )
                    await asyncio.sleep(sleep_duration)
                    continue
                logger.error(f"Max retries reached for {method} {url}: {e}")
                raise

    async def _get_paginated_data(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        ignore_status_codes: Optional[list[int]] = None,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        params = params or {}
        params["per_page"] = 100
        while True:
            response = await self._send_api_request(
                method="get",
                path=url,
                params=params,
                ignore_status_codes=ignore_status_codes,
            )
            if not response:
                break
            json_data = response.json()
            yield json_data if isinstance(json_data, list) else [json_data]

            link_header = response.headers.get(self.pagination_header_name, "")
            match = self.NEXT_PATTERN.search(link_header)
            if not match:
                break
            url = match.group(1).replace(self.base_url, "").lstrip("/")

    async def get_repositories(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        logger.info("Fetching repositories")
        async for repos in self._get_paginated_data(
            GithubEndpoints.LIST_REPOSITORIES.value,
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield repos

    async def get_pull_requests(
        self, owner: str, repo: str
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        logger.info(f"Fetching pull requests for {owner}/{repo}")
        async for prs in self._get_paginated_data(
            GithubEndpoints.LIST_PULL_REQUESTS.value.format(owner=owner, repo=repo),
            params={"state": "all"},
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield prs

    async def get_issues(
        self, owner: str, repo: str
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        logger.info(f"Fetching issues for {owner}/{repo}")
        async for issues in self._get_paginated_data(
            GithubEndpoints.LIST_ISSUES.value.format(owner=owner, repo=repo),
            params={"state": "all"},
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield issues

    async def get_teams(self, org: str) -> AsyncGenerator[list[dict[str, Any]], None]:
        logger.info(f"Fetching teams for organization {org}")
        async for teams in self._get_paginated_data(
            GithubEndpoints.LIST_TEAMS.value.format(org=org),
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield teams

    async def get_workflows(
        self, owner: str, repo: str
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        logger.info(f"Fetching workflows for {owner}/{repo}")
        async for data in self._get_paginated_data(
            GithubEndpoints.LIST_WORKFLOWS.value.format(owner=owner, repo=repo),
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield data.get("workflows", []) if isinstance(data, dict) else []

    async def get_files(
        self, repository: dict[str, Any], path: str = ""
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        owner = repository["owner"]["login"]
        repo = repository["name"]
        logger.info(f"Fetching files for {owner}/{repo} at path {path}")
        async for files in self._get_paginated_data(
            GithubEndpoints.LIST_FILES.value.format(owner=owner, repo=repo, path=path),
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        ):
            yield files

    async def get_folders(
        self, repository: dict[str, Any]
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for items in self.get_files(repository, path=""):
            folders = [item for item in items if item["type"] == "dir"]
            logger.info(f"Found {len(folders)} folders in {repository['full_name']}")
            yield folders

    async def get_readme(self, repository: dict[str, Any]) -> str | None:
        owner = repository["owner"]["login"]
        repo = repository["name"]
        logger.info(f"Fetching README for {owner}/{repo}")
        response = await self._send_api_request(
            method="get",
            path=GithubEndpoints.GET_README.value.format(owner=owner, repo=repo),
            ignore_status_codes=[
                self.forbidden_status_code,
                self.not_found_status_code,
            ],
        )
        if response:
            return (
                response.json().get("content", "").decode("base64")
                if response.json().get("encoding") == "base64"
                else None
            )
        return None

    async def setup_webhooks(self, webhook_url: str) -> None:
        async for repos in self.get_repositories():
            for repo in repos:
                owner = repo["owner"]["login"]
                repo_name = repo["name"]
                webhook_data = {
                    "name": "web",
                    "active": True,
                    "events": ["push", "pull_request", "issues"],
                    "config": {
                        "url": webhook_url,
                        "content_type": "json",
                        "insecure_ssl": "0",
                    },
                }
                logger.info(f"Creating webhook for {owner}/{repo_name}")
                await self._send_api_request(
                    method="post",
                    path=GithubEndpoints.CREATE_WEBHOOK.value.format(
                        owner=owner, repo=repo_name
                    ),
                    data=webhook_data,
                    ignore_status_codes=[self.forbidden_status_code, 422],
                )

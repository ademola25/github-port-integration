from enum import StrEnum
from typing import Any
from fastapi import Request
import os

from port_ocean.context.ocean import ocean
import logging
from client_factory import create_github_client
from port_ocean.core.ocean_types import ASYNC_GENERATOR_RESYNC_TYPE
from webhook import WebhookHandler

logger = logging.getLogger(__name__)


class ObjectKind(StrEnum):
    REPOSITORY = "repository"
    PULL_REQUEST = "pull-request"
    ISSUE = "issue"
    TEAM = "team"
    WORKFLOW = "workflow"
    FILE = "file"
    FOLDER = "folder"


MAX_BATCH_SIZE = 100


@ocean.on_resync(ObjectKind.REPOSITORY)
async def on_resync_repository(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        processed_repos = [
            {
                "id": str(repo["id"]),
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "html_url": repo["html_url"],
                "fork": repo["fork"],
                "created_at": repo["created_at"],
                "updated_at": repo["updated_at"],
                "pushed_at": repo["pushed_at"],
                "size": repo["size"],
                "stargazers_count": repo["stargazers_count"],
                "default_branch": repo["default_branch"],
                "readme": await github_client.get_readme(repo),  # Fetch README content
            }
            for repo in repo_batch
        ]
        for i in range(0, len(processed_repos), MAX_BATCH_SIZE):
            logger.info(
                f"Yielding batch of {len(processed_repos[i:i+MAX_BATCH_SIZE])} repositories"
            )
            yield processed_repos[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.PULL_REQUEST)
async def on_resync_pull_request(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        for repo in repo_batch:
            owner, repo_name = repo["full_name"].split("/")
            async for pr_batch in github_client.get_pull_requests(owner, repo_name):
                processed_prs = [
                    {
                        "id": str(pr["id"]),
                        "head": {"repo": {"name": repo["name"]}},
                        "title": pr["title"],
                        "user": {"login": pr["user"]["login"]},
                        "assignees": [
                            assignee["login"] for assignee in pr.get("assignees", [])
                        ],
                        "requested_reviewers": [
                            reviewer["login"]
                            for reviewer in pr.get("requested_reviewers", [])
                        ],
                        "status": pr["state"],
                        "closed_at": pr.get("closed_at"),
                        "updated_at": pr.get("updated_at"),
                        "merged_at": pr.get("merged_at"),
                        "created_at": pr["created_at"],
                        "html_url": pr["html_url"],
                        "repo": repo["name"],
                    }
                    for pr in pr_batch
                ]
                for i in range(0, len(processed_prs), MAX_BATCH_SIZE):
                    logger.info(
                        f"Yielding batch of {len(processed_prs[i:i+MAX_BATCH_SIZE])} pull requests for {repo['full_name']}"
                    )
                    yield processed_prs[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.ISSUE)
async def on_resync_issue(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        for repo in repo_batch:
            owner, repo_name = repo["full_name"].split("/")
            async for issue_batch in github_client.get_issues(owner, repo_name):
                processed_issues = [
                    {
                        "id": str(issue["id"]),
                        "repo": repo["name"],
                        "title": issue["title"],
                        "user": {"login": issue["user"]["login"]},
                        "assignees": [
                            assignee["login"] for assignee in issue.get("assignees", [])
                        ],
                        "labels": [label["name"] for label in issue.get("labels", [])],
                        "state": issue["state"],
                        "created_at": issue["created_at"],
                        "closed_at": issue.get("closed_at"),
                        "updated_at": issue.get("updated_at"),
                        "body": issue.get("body"),
                        "number": issue["number"],
                        "html_url": issue["html_url"],
                        "pull_request": issue.get("pull_request"),
                    }
                    for issue in issue_batch
                    if not issue.get("pull_request")  # Filter out pull requests
                ]
                for i in range(0, len(processed_issues), MAX_BATCH_SIZE):
                    logger.info(
                        f"Yielding batch of {len(processed_issues[i:i+MAX_BATCH_SIZE])} issues for {repo['full_name']}"
                    )
                    yield processed_issues[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.TEAM)
async def on_resync_team(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    org = ocean.integration_config.get("github_org")
    if not org:
        logger.warning("GITHUB_ORG not set, skipping team resync")
        return
    async for team_batch in github_client.get_teams(org):
        processed_teams = [
            {
                "id": str(team["id"]),
                "name": team["name"],
                "slug": team["slug"],
                "description": team["description"],
                "permission": team["permission"],
                "notification_setting": team["notification_setting"],
                "html_url": team["html_url"],
            }
            for team in team_batch
        ]
        for i in range(0, len(processed_teams), MAX_BATCH_SIZE):
            logger.info(
                f"Yielding batch of {len(processed_teams[i:i+MAX_BATCH_SIZE])} teams"
            )
            yield processed_teams[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.WORKFLOW)
async def on_resync_workflow(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        for repo in repo_batch:
            owner, repo_name = repo["full_name"].split("/")
            async for workflow_batch in github_client.get_workflows(owner, repo_name):
                processed_workflows = [
                    {
                        "id": str(workflow["id"]),
                        "repo": repo["name"],
                        "name": workflow["name"],
                        "path": workflow["path"],
                        "state": workflow["state"],
                        "created_at": workflow["created_at"],
                        "updated_at": workflow["updated_at"],
                        "html_url": workflow["html_url"],
                    }
                    for workflow in workflow_batch
                ]
                for i in range(0, len(processed_workflows), MAX_BATCH_SIZE):
                    logger.info(
                        f"Yielding batch of {len(processed_workflows[i:i+MAX_BATCH_SIZE])} workflows for {repo['full_name']}"
                    )
                    yield processed_workflows[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.FILE)
async def on_resync_file(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        for repo in repo_batch:
            async for file_batch in github_client.get_files(repo):
                processed_files = [
                    {
                        "id": f"{repo['name']}_{file['sha']}",
                        "repo": repo["name"],
                        "path": file["path"],
                        "name": file["name"],
                        "type": file["type"],
                        "html_url": file["html_url"],
                        "size": file["size"],
                    }
                    for file in file_batch
                    if file["type"] == "file"
                ]
                for i in range(0, len(processed_files), MAX_BATCH_SIZE):
                    logger.info(
                        f"Yielding batch of {len(processed_files[i:i+MAX_BATCH_SIZE])} files for {repo['full_name']}"
                    )
                    yield processed_files[i : i + MAX_BATCH_SIZE]


@ocean.on_resync(ObjectKind.FOLDER)
async def on_resync_folder(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    logger.info(f"Starting resync for {kind}")
    github_client = create_github_client()
    async for repo_batch in github_client.get_repositories():
        for repo in repo_batch:
            async for folder_batch in github_client.get_folders(repo):
                processed_folders = [
                    {
                        "id": f"{repo['name']}_{folder['sha']}",
                        "repo": repo["name"],
                        "path": folder["path"],
                        "name": folder["name"],
                        "type": folder["type"],
                        "html_url": folder["html_url"],
                    }
                    for folder in folder_batch
                ]
                for i in range(0, len(processed_folders), MAX_BATCH_SIZE):
                    logger.info(
                        f"Yielding batch of {len(processed_folders[i:i+MAX_BATCH_SIZE])} folders for {repo['full_name']}"
                    )
                    yield processed_folders[i : i + MAX_BATCH_SIZE]


@ocean.on_start()
async def on_start() -> None:
    logger.info("Starting GitHub integration")
    github_client = create_github_client()
    if ocean.integration_config.get("enable_webhooks", False):
        webhook_url = ocean.integration_config.get("webhook_url")
        if not webhook_url:
            logger.warning("Webhook URL not provided, skipping webhook setup")
            return
        logger.info("Setting up GitHub webhooks")
        await github_client.setup_webhooks(webhook_url)


@ocean.router.post("/webhook")
async def github_webhook(request: Request) -> tuple[dict[str, Any], int]:
    webhook_secret = ocean.integration_config.get("webhook_secret") or os.getenv(
        "GITHUB_WEBHOOK_SECRET"
    )
    if not webhook_secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not set, cannot process webhook")
        return {"ok": False, "error": "Webhook secret not configured"}, 400
    webhook_handler = WebhookHandler(webhook_secret)
    return await webhook_handler.handle_webhook(request)
